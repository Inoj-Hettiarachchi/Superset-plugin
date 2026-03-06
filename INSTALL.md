# Superset Data Entry Plugin — Installation Guide

> **Concise step-by-step guide for deploying this plugin into any project running Apache Superset.**

---

## Prerequisites

| Requirement | Detail |
|---|---|
| Apache Superset | ≥ 2.1 running in Docker or a Python venv |
| Python | ≥ 3.9, same environment Superset uses |
| Database | PostgreSQL (same DB Superset uses) |
| Superset role | A user with the `Admin` role to configure forms |

---

## Step 1 — Install the package

Run this **inside the same Python environment Superset uses** (venv, Docker image, etc.).

**From the private GitHub repo:**
```bash
pip install --no-deps "git+https://<TOKEN>@github.com/Inoj-Hettiarachchi/Superset-plugin.git@main"
```

**From a local copy of the repo:**
```bash
pip install --no-deps -e /path/to/Superset-plugin
```

**Inside a Docker image** (add to your `Dockerfile`):
```dockerfile
RUN pip install --no-deps "git+https://<TOKEN>@github.com/Inoj-Hettiarachchi/Superset-plugin.git@main"
```

> `--no-deps` prevents accidentally upgrading Flask or SQLAlchemy under Superset.

---

## Step 2 — Create the init file

Create **`superset_init_plugin.py`** in the **same directory as your `superset_config.py`**:

```python
import logging
logger = logging.getLogger(__name__)

def init_data_entry_plugin(app):
    try:
        from superset_data_entry import register_plugin
        register_plugin(app.appbuilder)
        logger.info("✅ Data Entry Plugin loaded")
    except ImportError as e:
        logger.warning("⚠️  Data Entry Plugin not installed: %s", e)
    except Exception as e:
        logger.error("❌ Data Entry Plugin failed to load: %s", e)
```

---

## Step 3 — Register the plugin in Superset config

Add (or merge with an existing `FLASK_APP_MUTATOR`) in your **`superset_config.py`**:

```python
import os

def FLASK_APP_MUTATOR(app):
    try:
        import sys
        config_dir = os.path.dirname(os.path.abspath(__file__))
        if config_dir not in sys.path:
            sys.path.insert(0, config_dir)
        from superset_init_plugin import init_data_entry_plugin
        init_data_entry_plugin(app)
    except Exception as e:
        print("⚠️  Data Entry Plugin: %s" % e)
```

> No extra database config is needed. The plugin uses Superset's existing `SQLALCHEMY_DATABASE_URI`.

---

## Step 4 — Restart Superset

```bash
# Docker
docker compose up -d --build superset

# Host / venv
superset run -p 8088 --with-threads --reload
```

**On first boot the plugin automatically runs its migrations** and creates these tables in Superset's database:

| Table | Purpose |
|---|---|
| `form_configurations` | Form definitions, field config, SharePoint credentials |
| `form_fields` | Field schema per form |
| `de_schema_migrations` | Migration version tracking (prefixed `DE_V` to avoid conflicts) |
| Per-form data tables | Created dynamically when a form is saved |

> If the tables already exist the migrations are skipped — safe to restart repeatedly.

---

## Step 5 — Verify the plugin loaded

1. Open Superset in the browser
2. **Top navigation bar** → you should see a **"Data Entry"** menu item
3. Click it — the Forms list page loads

If the menu is missing, check the Superset startup logs for `❌ Data Entry Plugin failed` and fix the reported error.

---

## Step 6 — Create your first form (Admin only)

Only users with the Superset **Admin** role can create and configure forms.

1. Log in as **Admin**
2. **Data Entry** → **Create New Form**
3. Fill in:
   - **Form Title** — displayed name
   - **Table Name** — PostgreSQL table that will store submissions (e.g. `vessel_dp_log`)
   - **Allowed Roles** — which Superset roles can submit data (e.g. `Alpha`, `Gamma`)
4. Add fields using the **Add Field** section — set label, type, and any validation
5. Click **Save Form**

The data table (`vessel_dp_log`, etc.) is created automatically in Superset's database.

---

## Step 7 — Grant access to users

Users need one of the **Allowed Roles** set on the form to be able to submit and view data.

In Superset: **Settings → List Users** → edit the user → assign the role you specified on the form.

> Admins can always access all forms regardless of allowed roles.

---

## Step 8 — (Optional) Enable SharePoint export

This allows form data to be uploaded incrementally to a SharePoint document library as a CSV.

### 8a — Register an Azure App

1. Go to [portal.azure.com](https://portal.azure.com) → **Microsoft Entra ID** → **App registrations** → **+ New registration**
2. Name it (e.g. `Superset Data Entry`), leave Redirect URI blank → **Register**
3. On the **Overview** page, copy:
   - **Application (client) ID**
   - **Directory (tenant) ID**
4. Go to **Certificates & secrets** → **+ New client secret** → copy the **Value** immediately
5. Go to **API permissions** → **+ Add a permission** → **Microsoft Graph** → **Application permissions** → add `Files.ReadWrite.All` → **Grant admin consent**

### 8b — Configure on the form

1. In Superset: **Data Entry** → **Configure** on your form (Admin only)
2. Scroll to **SharePoint Integration** → tick **Enable SharePoint export**
3. Fill in:

   | Field | Example |
   |---|---|
   | SharePoint Site URL | `https://yourorg.sharepoint.com/sites/YourSite` |
   | Folder Path | `Shared Documents/DataEntry` |
   | Azure Tenant ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
   | Azure App Client ID | `yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy` |
   | Client Secret | `<secret value from Step 8a>` |

4. Click **Save Form**

### 8c — Upload data

1. **Data Entry** → **View Data** on your form
2. Click **"Seed Upload to SharePoint"** — creates `<table_name>.csv` in the SharePoint folder with all rows
3. After the first seed upload the button changes to **"Upload New Entries to SharePoint"** — this appends only rows added since the last upload
4. Admins also see a **"Force Full Re-upload"** button to reset and re-seed from scratch

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Data Entry" menu missing | Check startup logs. Ensure `FLASK_APP_MUTATOR` is in `superset_config.py` and `superset_init_plugin.py` is on the path. |
| `relation "form_configurations" does not exist` | Plugin migrations didn't run. Check DB connectivity and restart. |
| "Only administrators can create or configure forms" | Log in with a Superset **Admin** role account, not just a regular user. |
| SharePoint credential fields don't expand | Clear browser cache — the plugin CSS file may be stale. |
| SharePoint upload button not visible on data grid | SharePoint is not enabled on this form — go to Configure and tick + save first. |
| SharePoint `403 Forbidden` error | Admin consent was not granted for `Files.ReadWrite.All` in Azure (Step 8a). |
| SharePoint `invalid_client` error | Wrong Client ID or Secret — re-check Step 8a credentials. |
| SharePoint `resource not found` error | Wrong Site URL or Folder Path — verify in your browser first. |

---

## Checklist

- [ ] Plugin installed in Superset's Python environment
- [ ] `superset_init_plugin.py` created next to `superset_config.py`
- [ ] `FLASK_APP_MUTATOR` added to `superset_config.py`
- [ ] Superset restarted — "Data Entry" menu visible
- [ ] Form created by Admin with correct table name and allowed roles
- [ ] Users assigned the allowed role(s) in Superset
- [ ] *(Optional)* SharePoint credentials configured and seed upload tested
