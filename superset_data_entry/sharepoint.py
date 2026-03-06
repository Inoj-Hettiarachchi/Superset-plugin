"""
SharePoint export integration for the data entry plugin.

Provides **manual-only** bulk upload to a SharePoint document library.

Upload is triggered via the "Upload to SharePoint" button on the data grid:

- **Seed mode** (first upload, or ``force=True``): fetches ALL rows and
  uploads a fresh ``{form_name}.csv``, replacing any existing file.
- **Incremental mode**: fetches only rows created *after*
  ``form_config.sharepoint_last_uploaded_at`` and appends them to the
  existing file.  Returns ``"no_new_rows"`` if nothing has changed.

Improvements over initial implementation:
- MSAL token caching per (tenant, client) -- avoids round-trip on every call
- Retry with exponential backoff on 429/5xx (transient failures)
- ETag-based optimistic locking on CSV PUT to prevent concurrent-write data loss
- Extracted ``_prepare_connection`` helper -- no credential code duplication
- Consistent ``_serialize_row`` usage on all code paths
- Fernet-encrypted client secrets (see ``decrypt_secret``)

Required Azure App Registration permissions (application, not delegated):
  - ``Files.ReadWrite.All``  *or*  ``Sites.ReadWrite.All``

All public methods raise on error.  Callers in views.py catch exceptions and
return appropriate error messages.
"""
import csv
import io
import logging
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MSAL token caching
# ---------------------------------------------------------------------------

@lru_cache(maxsize=32)
def _get_msal_app(tenant_id: str, client_id: str, client_secret: str):
    """Return a cached MSAL ConfidentialClientApplication."""
    try:
        import msal
    except ImportError as exc:
        raise ImportError(
            "The 'msal' package is required for SharePoint export. "
            "Install it with: pip install msal"
        ) from exc

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    return msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
    )


# ---------------------------------------------------------------------------
# requests Session with retry
# ---------------------------------------------------------------------------

def _build_http_session():
    """Return a ``requests.Session`` with automatic retry on transient errors.

    Retries on HTTP 429 (throttled), 500, 502, 503, 504 with exponential
    backoff (0.5 s, 1 s, 2 s).
    """
    import requests
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.retry import Retry
    except ImportError:
        from requests.packages.urllib3.util.retry import Retry

    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "PUT"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ---------------------------------------------------------------------------
# Fernet helpers (encrypt / decrypt client secrets)
# ---------------------------------------------------------------------------

def _get_fernet():
    """Return a Fernet instance using the key from Superset config, or None
    if no key is configured (plain-text fallback).
    """
    try:
        from flask import current_app
        key = current_app.config.get("DATA_ENTRY_SECRET_KEY")
        if not key:
            return None
        from cryptography.fernet import Fernet
        return Fernet(key if isinstance(key, bytes) else key.encode())
    except Exception:
        return None


def encrypt_secret(plain: str) -> str:
    """Encrypt *plain* with Fernet if a key is configured, else return as-is."""
    if not plain:
        return plain
    f = _get_fernet()
    if f is None:
        return plain
    return f.encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Decrypt *token* with Fernet if a key is configured, else return as-is."""
    if not token:
        return token
    f = _get_fernet()
    if f is None:
        return token
    try:
        return f.decrypt(token.encode()).decode()
    except Exception:
        # Already plain text or wrong key -- return as-is so existing
        # unencrypted secrets keep working after the key is first configured.
        return token


# ---------------------------------------------------------------------------
# SharePoint errors (used by views.py to return meaningful messages)
# ---------------------------------------------------------------------------

class SharePointAuthError(Exception):
    """Authentication / token acquisition failure."""


class SharePointNotFoundError(Exception):
    """Site, drive, or folder not found."""


class SharePointConflictError(Exception):
    """ETag mismatch -- file was modified concurrently."""


class SharePointCredentialsError(ValueError):
    """Required credentials are missing or incomplete."""


# ---------------------------------------------------------------------------
# SharePointExporter
# ---------------------------------------------------------------------------

class SharePointExporter:
    """Manual-only bulk upload of form data to a SharePoint folder as CSV.

    Each form gets one file: ``{form.table_name}.csv`` inside the configured
    folder.  Column order is determined by the first upload; subsequent
    uploads that contain extra columns have those columns appended at the
    right.
    """

    GRAPH_SCOPE = "https://graph.microsoft.com/.default"
    MAX_ETAG_RETRIES = 2  # retry on ETag conflict up to N times (then force)

    # ------------------------------------------------------------------ #
    # Connection helper (extracted -- no duplication)                       #
    # ------------------------------------------------------------------ #

    def _prepare_connection(self, form_config) -> Tuple[str, str, str, str, str]:
        """Validate credentials and return
        ``(token, site_id, drive_id, folder_path, filename)``.

        Raises:
            SharePointCredentialsError: if any required field is blank.
            SharePointAuthError: if token acquisition fails.
            SharePointNotFoundError: if site/drive resolution fails.
        """
        tenant_id = (form_config.sharepoint_tenant_id or "").strip()
        client_id = (form_config.sharepoint_client_id or "").strip()
        raw_secret = (form_config.sharepoint_client_secret or "").strip()
        site_url = (form_config.sharepoint_site_url or "").strip()
        folder_path = (form_config.sharepoint_folder_path or "").strip("/")
        filename = f"{form_config.table_name}.csv"

        if not all([tenant_id, client_id, raw_secret, site_url]):
            raise SharePointCredentialsError(
                "SharePoint credentials are incomplete. "
                "Please set Tenant ID, Client ID, Client Secret, and Site URL "
                "in the form's SharePoint configuration."
            )

        # Decrypt secret (no-op if Fernet is not configured)
        client_secret = decrypt_secret(raw_secret)

        # Auth (cached MSAL app)
        token = self._acquire_token(tenant_id, client_id, client_secret)

        # Resolve site -> drive
        site_id = self._site_id_from_url(token, site_url)
        drive_id = self._get_drive_id(token, site_id)

        return token, site_id, drive_id, folder_path, filename

    # ------------------------------------------------------------------ #
    # Auth                                                                 #
    # ------------------------------------------------------------------ #

    def _acquire_token(self, tenant_id: str, client_id: str, client_secret: str) -> str:
        """Acquire an OAuth2 bearer token via MSAL (cached app instance)."""
        app = _get_msal_app(tenant_id, client_id, client_secret)
        result = app.acquire_token_for_client(scopes=[self.GRAPH_SCOPE])
        if "access_token" not in result:
            error_desc = result.get("error_description") or result.get("error") or "unknown"
            # Invalidate the cached MSAL app so the next attempt creates a fresh one
            _get_msal_app.cache_clear()
            raise SharePointAuthError(
                f"Authentication failed. Check Tenant ID, Client ID, and "
                f"Client Secret.  (Azure AD: {error_desc})"
            )
        return result["access_token"]

    # ------------------------------------------------------------------ #
    # Graph API helpers                                                    #
    # ------------------------------------------------------------------ #

    def _site_id_from_url(self, token: str, site_url: str) -> str:
        """Resolve a SharePoint site URL to a Graph API site ID."""
        from urllib.parse import urlparse
        parsed = urlparse(site_url)
        hostname = parsed.hostname
        path = parsed.path.rstrip("/")
        url = f"https://graph.microsoft.com/v1.0/sites/{hostname}:{path}"

        http = _build_http_session()
        resp = http.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 30),
        )
        if resp.status_code == 404:
            raise SharePointNotFoundError(
                f"SharePoint site not found. Verify the Site URL: {site_url}"
            )
        resp.raise_for_status()
        return resp.json()["id"]

    def _get_drive_id(self, token: str, site_id: str) -> str:
        """Return the default document-library drive ID for the site."""
        http = _build_http_session()
        url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
        resp = http.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 30),
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _item_path(self, folder_path: str, filename: str) -> str:
        folder = folder_path.strip("/")
        return f"{folder}/{filename}" if folder else filename

    def _download_existing_csv(
        self, token: str, drive_id: str, folder_path: str, filename: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Download existing CSV text from SharePoint.

        Returns:
            ``(csv_text, etag)`` -- csv_text is ``None`` if file does not exist.
        """
        http = _build_http_session()
        # First get the item metadata (for ETag)
        item_url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:/{self._item_path(folder_path, filename)}"
        )
        meta_resp = http.get(
            item_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 30),
        )
        if meta_resp.status_code == 404:
            return None, None
        meta_resp.raise_for_status()
        etag = meta_resp.json().get("eTag")

        # Now download the content
        content_url = item_url + ":/content"
        resp = http.get(
            content_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=(10, 60),
        )
        if resp.status_code == 404:
            return None, None
        resp.raise_for_status()
        return resp.text, etag

    def _upload_csv(
        self,
        token: str,
        drive_id: str,
        folder_path: str,
        filename: str,
        content: str,
        etag: Optional[str] = None,
    ) -> None:
        """PUT (create-or-overwrite) a CSV file in the SharePoint folder.

        If *etag* is provided, the upload uses an ``If-Match`` header for
        optimistic concurrency control.  Raises ``SharePointConflictError``
        if the file was modified since we downloaded it.
        """
        http = _build_http_session()
        url = (
            f"https://graph.microsoft.com/v1.0/drives/{drive_id}"
            f"/root:/{self._item_path(folder_path, filename)}:/content"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/csv",
        }
        if etag:
            headers["If-Match"] = etag

        resp = http.put(
            url,
            headers=headers,
            data=content.encode("utf-8"),
            timeout=(10, 120),
        )

        if resp.status_code == 412:
            raise SharePointConflictError(
                "The SharePoint file was modified by another process. "
                "Please retry the upload."
            )
        if resp.status_code == 404:
            raise SharePointNotFoundError(
                "SharePoint folder not found. Verify the Folder Path setting."
            )
        resp.raise_for_status()

    # ------------------------------------------------------------------ #
    # Test connection (used by the "Test Connection" button)               #
    # ------------------------------------------------------------------ #

    def test_connection(self, form_config) -> str:
        """Validate credentials and reachability without uploading anything.

        Returns a human-readable success message.
        """
        _token, _site_id, drive_id, _folder_path, _filename = (
            self._prepare_connection(form_config)
        )
        return f"Connected successfully. Drive ID: {drive_id[:12]}..."

    # ------------------------------------------------------------------ #
    # Public API -- manual bulk upload only                                #
    # ------------------------------------------------------------------ #

    def upload_incremental(
        self, form_config, engine, force: bool = False
    ) -> Tuple[int, str, Optional[str]]:
        """Bulk-upload form data to SharePoint using watermark-based
        incremental logic.

        Returns:
            ``(rows_uploaded, mode, warning_or_none)``
            - mode: ``"seed"`` | ``"incremental"`` | ``"no_new_rows"``
            - warning: e.g. ``"Exported 50,000 of 63,000 rows (capped)"``
              or ``None``

        Raises:
            SharePointCredentialsError, SharePointAuthError,
            SharePointNotFoundError, SharePointConflictError,
            requests.HTTPError
        """
        token, site_id, drive_id, folder_path, filename = (
            self._prepare_connection(form_config)
        )
        last_uploaded_at = form_config.sharepoint_last_uploaded_at
        is_seed = force or (last_uploaded_at is None)

        if is_seed:
            return self._do_seed(
                engine, form_config, token, drive_id, folder_path, filename
            )
        else:
            return self._do_incremental(
                engine, form_config, token, drive_id,
                folder_path, filename, last_uploaded_at,
            )

    # ------------------------------------------------------------------ #
    # Seed upload                                                          #
    # ------------------------------------------------------------------ #

    def _do_seed(self, engine, form_config, token, drive_id, folder_path, filename):
        from .dao import DataEntryDAO

        rows, total = DataEntryDAO.get_all_for_export(engine, form_config.table_name)
        if not rows:
            logger.info(
                "SharePoint seed upload skipped -- no rows in table (form_id=%s)",
                form_config.id,
            )
            return (0, "seed", None)

        warning = None
        if total > len(rows):
            warning = (
                f"Exported {len(rows):,} of {total:,} rows "
                f"(capped at {len(rows):,})"
            )

        content = self._build_full_csv(rows)

        # Seed always replaces -- no ETag needed
        self._upload_csv(token, drive_id, folder_path, filename, content)

        logger.info(
            "SharePoint seed upload: %d rows to '%s/%s' (form_id=%s)",
            len(rows), folder_path or "<root>", filename, form_config.id,
        )
        return (len(rows), "seed", warning)

    # ------------------------------------------------------------------ #
    # Incremental upload (with ETag retry)                                 #
    # ------------------------------------------------------------------ #

    def _do_incremental(
        self, engine, form_config, token, drive_id,
        folder_path, filename, last_uploaded_at,
    ):
        from .dao import DataEntryDAO

        new_rows, total_new = DataEntryDAO.get_rows_since(
            engine, form_config.table_name, last_uploaded_at,
        )
        if not new_rows:
            logger.info(
                "SharePoint incremental: no new rows since %s (form_id=%s)",
                last_uploaded_at, form_config.id,
            )
            return (0, "no_new_rows", None)

        warning = None
        if total_new > len(new_rows):
            warning = (
                f"Uploaded {len(new_rows):,} of {total_new:,} new rows (capped)"
            )

        # Retry loop for ETag conflicts
        for attempt in range(self.MAX_ETAG_RETRIES + 1):
            existing_csv, etag = self._download_existing_csv(
                token, drive_id, folder_path, filename,
            )

            # Append each new row in chronological order
            content = existing_csv
            for row in new_rows:
                content = self._append_row(content, self._serialize_row(row))

            try:
                self._upload_csv(
                    token, drive_id, folder_path, filename, content, etag=etag,
                )
                break  # success
            except SharePointConflictError:
                if attempt < self.MAX_ETAG_RETRIES:
                    logger.warning(
                        "SharePoint ETag conflict (attempt %d/%d), retrying...",
                        attempt + 1, self.MAX_ETAG_RETRIES,
                    )
                    time.sleep(0.5 * (attempt + 1))
                else:
                    raise  # let caller handle

        logger.info(
            "SharePoint incremental: appended %d rows to '%s/%s' (form_id=%s)",
            len(new_rows), folder_path or "<root>", filename, form_config.id,
        )
        return (len(new_rows), "incremental", warning)

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
            elif hasattr(v, "isoformat"):
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
        - Column merging: existing columns kept in order, new columns appended
          at the right.
        """
        new_cols: List[str] = list(row_data.keys())

        if existing_csv:
            reader = csv.DictReader(io.StringIO(existing_csv))
            existing_cols: List[str] = list(reader.fieldnames or new_cols)
            all_cols = existing_cols + [
                c for c in new_cols if c not in existing_cols
            ]

            output = io.StringIO()
            writer = csv.DictWriter(
                output, fieldnames=all_cols, extrasaction="ignore",
            )
            output.write(existing_csv.rstrip("\n") + "\n")
            writer.writerow({col: row_data.get(col, "") for col in all_cols})
        else:
            output = io.StringIO()
            writer = csv.DictWriter(
                output, fieldnames=new_cols, extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerow(row_data)

        return output.getvalue()
