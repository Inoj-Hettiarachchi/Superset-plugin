"""
SharePoint export integration for the data entry plugin.

Two upload modes are supported:

1. **Per-submission** (``upload_row``): called automatically after each form
   submission when SharePoint export is enabled.  Appends a single row to the
   existing CSV file.

2. **Bulk / incremental** (``upload_incremental``): triggered manually via the
   "Upload to SharePoint" button on the data grid.

   - **Seed mode** (first upload, or ``force=True``): fetches ALL rows and
     uploads a fresh ``{form_name}.csv``, replacing any existing file.
   - **Incremental mode**: fetches only rows created *after*
     ``form_config.sharepoint_last_uploaded_at`` and appends them to the
     existing file.  Returns ``"no_new_rows"`` if nothing has changed.

Required Azure App Registration permissions (application, not delegated):
  - ``Files.ReadWrite.All``  *or*  ``Sites.ReadWrite.All``

All public methods raise on error.  Callers in views.py catch exceptions and
log them without failing the user-facing operation.
"""
import csv
import io
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SharePointExporter:
    """Upload a form-submission dict to a SharePoint folder as a CSV file.

    Each form gets one file: ``{form.name}.csv`` inside the configured folder.
    New rows are appended to an existing file; the file is created on first use.
    Column order is determined by the first submission; subsequent submissions
    that contain extra keys have those keys appended at the right.
    """

    GRAPH_SCOPE = "https://graph.microsoft.com/.default"

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _acquire_token(self, tenant_id: str, client_id: str, client_secret: str) -> str:
        """Acquire an OAuth2 bearer token via MSAL client-credentials flow."""
        try:
            import msal
        except ImportError as exc:
            raise ImportError(
                "The 'msal' package is required for SharePoint export. "
                "Install it with: pip install msal"
            ) from exc

        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential=client_secret,
        )
        result = app.acquire_token_for_client(scopes=[self.GRAPH_SCOPE])
        if "access_token" not in result:
            raise RuntimeError(
                "Failed to acquire SharePoint token: "
                + str(result.get("error_description") or result.get("error") or result)
            )
        return result["access_token"]

    def _site_id_from_url(self, token: str, site_url: str) -> str:
        """Resolve a SharePoint site URL to a Graph API site ID.

        Accepts URLs like ``https://contoso.sharepoint.com/sites/MySite``.
        """
        try:
            import requests
        except ImportError as exc:
            raise ImportError(
                "The 'requests' package is required for SharePoint export. "
                "Install it with: pip install requests"
            ) from exc

        from urllib.parse import urlparse
        parsed = urlparse(site_url)
        hostname = parsed.hostname  # e.g. contoso.sharepoint.com
        path = parsed.path.rstrip("/")  # e.g. /sites/MySite
        url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{path}"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _get_drive_id(self, token: str, site_id: str) -> str:
        """Return the default document-library drive ID for the site."""
        import requests
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _item_path(self, folder_path: str, filename: str) -> str:
        """Build the drive-relative item path, e.g. ``Shared Documents/DataEntry/my_form.csv``."""
        folder = folder_path.strip("/")
        return f"{folder}/{filename}" if folder else filename

    def _download_existing_csv(
        self, token: str, drive_id: str, folder_path: str, filename: str
    ) -> Optional[str]:
        """Download existing CSV text from SharePoint. Returns ``None`` if not found."""
        import requests
        url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:/{self._item_path(folder_path, filename)}:/content"
        )
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.text

    def _upload_csv(
        self,
        token: str,
        drive_id: str,
        folder_path: str,
        filename: str,
        content: str,
    ) -> None:
        """PUT (create-or-overwrite) a CSV file in the SharePoint folder."""
        import requests
        url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:/{self._item_path(folder_path, filename)}:/content"
        )
        resp = requests.put(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "text/csv",
            },
            data=content.encode("utf-8"),
            timeout=60,
        )
        resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def upload_row(self, form_config, row_data: Dict[str, Any]) -> None:
        """Append *row_data* as a new CSV row to ``{form.name}.csv`` in the
        configured SharePoint folder.  Creates the file on first use.

        Raises:
            ValueError: if required credentials are missing.
            RuntimeError: if the OAuth2 token cannot be acquired.
            requests.HTTPError: if any Graph API call fails.
        """
        tenant_id = (form_config.sharepoint_tenant_id or "").strip()
        client_id = (form_config.sharepoint_client_id or "").strip()
        client_secret = (form_config.sharepoint_client_secret or "").strip()
        site_url = (form_config.sharepoint_site_url or "").strip()
        folder_path = (form_config.sharepoint_folder_path or "").strip("/")
        filename = f"{form_config.name}.csv"

        if not all([tenant_id, client_id, client_secret, site_url]):
            raise ValueError(
                "SharePoint export is enabled but credentials are incomplete. "
                "Please set Tenant ID, Client ID, Client Secret, and Site URL "
                "in the form's SharePoint configuration."
            )

        # 1. Auth
        token = self._acquire_token(tenant_id, client_id, client_secret)

        # 2. Resolve site → drive
        site_id = self._site_id_from_url(token, site_url)
        drive_id = self._get_drive_id(token, site_id)

        # 3. Fetch existing file (if any)
        existing_csv = self._download_existing_csv(token, drive_id, folder_path, filename)

        # 4. Build updated CSV content
        new_content = self._append_row(existing_csv, row_data)

        # 5. Upload
        self._upload_csv(token, drive_id, folder_path, filename, new_content)

        logger.info(
            "SharePoint export: appended 1 row to '%s/%s' (form_id=%s)",
            folder_path or "<root>",
            filename,
            form_config.id,
        )

    def upload_incremental(
        self, form_config, engine, force: bool = False
    ) -> Tuple[int, str]:
        """Bulk-upload form data to SharePoint using watermark-based incremental logic.

        **Seed mode** (triggered when ``sharepoint_last_uploaded_at`` is ``None``
        or ``force=True``):
          - Fetches ALL rows via ``DataEntryDAO.get_all_for_export``.
          - Builds a fresh CSV and replaces any existing file in SharePoint.
          - Returns ``(row_count, "seed")``.

        **Incremental mode** (subsequent uploads):
          - Fetches only rows with ``created_at > sharepoint_last_uploaded_at``.
          - If no new rows exist, returns ``(0, "no_new_rows")`` without any
            network call to SharePoint.
          - Otherwise downloads the existing CSV, appends the new rows, and
            re-uploads.
          - Returns ``(row_count, "incremental")``.

        Raises:
            ValueError: if required credentials are missing.
            RuntimeError: if the OAuth2 token cannot be acquired.
            requests.HTTPError: if any Graph API call fails.
        """
        from .dao import DataEntryDAO

        tenant_id = (form_config.sharepoint_tenant_id or "").strip()
        client_id = (form_config.sharepoint_client_id or "").strip()
        client_secret = (form_config.sharepoint_client_secret or "").strip()
        site_url = (form_config.sharepoint_site_url or "").strip()
        folder_path = (form_config.sharepoint_folder_path or "").strip("/")
        filename = f"{form_config.name}.csv"
        last_uploaded_at = form_config.sharepoint_last_uploaded_at

        if not all([tenant_id, client_id, client_secret, site_url]):
            raise ValueError(
                "SharePoint export is enabled but credentials are incomplete. "
                "Please set Tenant ID, Client ID, Client Secret, and Site URL "
                "in the form's SharePoint configuration."
            )

        is_seed = force or (last_uploaded_at is None)

        if is_seed:
            # ---- Seed: upload ALL rows as a fresh file ---- #
            rows = DataEntryDAO.get_all_for_export(engine, form_config.table_name)
            if not rows:
                logger.info(
                    "SharePoint seed upload skipped — no rows in table (form_id=%s)",
                    form_config.id,
                )
                return (0, "seed")

            token = self._acquire_token(tenant_id, client_id, client_secret)
            site_id = self._site_id_from_url(token, site_url)
            drive_id = self._get_drive_id(token, site_id)

            content = self._build_full_csv(rows)
            self._upload_csv(token, drive_id, folder_path, filename, content)
            logger.info(
                "SharePoint seed upload: %d rows to '%s/%s' (form_id=%s)",
                len(rows), folder_path or "<root>", filename, form_config.id,
            )
            return (len(rows), "seed")

        else:
            # ---- Incremental: only rows newer than the watermark ---- #
            new_rows = DataEntryDAO.get_rows_since(
                engine, form_config.table_name, last_uploaded_at
            )
            if not new_rows:
                logger.info(
                    "SharePoint incremental: no new rows since %s (form_id=%s)",
                    last_uploaded_at, form_config.id,
                )
                return (0, "no_new_rows")

            token = self._acquire_token(tenant_id, client_id, client_secret)
            site_id = self._site_id_from_url(token, site_url)
            drive_id = self._get_drive_id(token, site_id)

            # Download existing file (may be absent if manually deleted in SP)
            existing_csv = self._download_existing_csv(
                token, drive_id, folder_path, filename
            )

            # Append each new row in chronological order
            content = existing_csv
            for row in new_rows:
                content = self._append_row(content, self._serialize_row(row))

            self._upload_csv(token, drive_id, folder_path, filename, content)
            logger.info(
                "SharePoint incremental: appended %d rows to '%s/%s' (form_id=%s)",
                len(new_rows), folder_path or "<root>", filename, form_config.id,
            )
            return (len(new_rows), "incremental")

    # ------------------------------------------------------------------ #
    # CSV building                                                         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Python objects in a DB row dict to CSV-safe strings."""
        out = {}
        for k, v in row.items():
            if v is None:
                out[k] = ""
            elif hasattr(v, 'isoformat'):  # datetime / date / time
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out

    @staticmethod
    def _build_full_csv(rows: List[Dict[str, Any]]) -> str:
        """Build a complete CSV from scratch (used for seed uploads)."""
        if not rows:
            return ""
        cols = list(rows[0].keys())
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(SharePointExporter._serialize_row(row))
        return output.getvalue()

    @staticmethod
    def _append_row(existing_csv: Optional[str], row_data: Dict[str, Any]) -> str:
        """Return the full CSV text with *row_data* appended.

        - If *existing_csv* is ``None``, creates a new file with a header row.
        - If the existing file has columns the new row doesn't, those columns
          are written as empty strings.
        - If the new row has extra columns not in the existing file, they are
          appended to the right of the existing columns.
        """
        new_cols: List[str] = list(row_data.keys())

        if existing_csv:
            reader = csv.DictReader(io.StringIO(existing_csv))
            existing_cols: List[str] = list(reader.fieldnames or new_cols)
            # Merge: keep existing order, append genuinely new columns
            all_cols = existing_cols + [c for c in new_cols if c not in existing_cols]

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=all_cols, extrasaction="ignore")

            # Re-write existing content verbatim then add new row
            output.write(existing_csv.rstrip("\n") + "\n")
            writer.writerow({col: row_data.get(col, "") for col in all_cols})
        else:
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=new_cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerow(row_data)

        return output.getvalue()
