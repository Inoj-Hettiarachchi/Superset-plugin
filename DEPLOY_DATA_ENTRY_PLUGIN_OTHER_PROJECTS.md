# Deploy Data Entry Plugin in Other Projects

This guide explains how to use the Superset Data Entry Plugin in **any other project** that runs Apache Superset. The plugin stores form definitions and submitted data in **your project’s PostgreSQL** (the database you configure).

---

## Install from this repo (private Git – Option A)

If this repo is in a private GitHub (or GitLab/Bitbucket) org, install the plugin in the other project with:

```bash
pip install --no-deps "git+https://github.com/YOUR_ORG/superset-data-entry-plugin.git@main"
```

For private repos, use a token or SSH:

```bash
pip install --no-deps "git+https://<TOKEN>@github.com/YOUR_ORG/superset-data-entry-plugin.git@main"
# or
pip install --no-deps "git+ssh://git@github.com/YOUR_ORG/superset-data-entry-plugin.git@main"
```

Then add the init hook, config, and run migrations (see below).

---

## What You Need in the Other Project

1. **The plugin package** (copy from this repo or install via pip).
2. **Superset configuration** – hook + database config.
3. **Plugin init file** – `superset_init_plugin.py`.
4. **Database** – run migrations so `form_configurations` and `form_fields` exist in your DB.
5. **Optional:** Custom validators or seed forms (migrations or UI).

---

## Option A: Copy Plugin into the Other Project (recommended for one-off use)

Use this when the other project has its own Superset Docker image or venv and you can copy files into it.

### 1. Copy the plugin and init file

From this repo, copy into the other project:

- **Plugin package:**  
  `platform/superset-data-entry-plugin/`  
  → e.g. `other-project/superset-data-entry-plugin/` (or next to their Superset/Docker setup).

- **Init hook:**  
  `platform/superset_init_plugin.py`  
  → same directory as their `superset_config.py` (e.g. `other-project/superset/superset_init_plugin.py` or wherever Superset is configured).

### 2. Point Superset at your project’s database

In the other project’s **`superset_config.py`** add (or merge with existing config):

```python
import os

# Database where form metadata and form data will live (your project's PostgreSQL)
DATA_ENTRY_DB_CONFIG = {
    'host': os.environ.get('SUPERSET_APPBASE_DB_HOST', 'localhost'),
    'port': int(os.environ.get('SUPERSET_APPBASE_DB_PORT', '5432')),
    'username': os.environ.get('SUPERSET_APPBASE_DB_USER', 'your_db_user'),
    'password': os.environ.get('SUPERSET_APPBASE_DB_PASSWORD', 'your_db_password'),
    'database': os.environ.get('SUPERSET_APPBASE_DB_NAME', 'your_database'),
}

# Register the plugin after Superset starts
def FLASK_APP_MUTATOR(app):
    try:
        import sys
        # If init file is next to superset_config.py
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from superset_init_plugin import init_data_entry_plugin
        init_data_entry_plugin(app)
    except Exception as e:
        print(f"⚠️  Failed to load data entry plugin: {e}")
```

Set env vars (or replace defaults) so `DATA_ENTRY_DB_CONFIG` points to **the PostgreSQL instance that project uses** (same DB as the app, or a dedicated one).

### 3. Add the init file

Create or copy **`superset_init_plugin.py`** in the **same directory as `superset_config.py`**:

```python
import logging

logger = logging.getLogger(__name__)

def init_data_entry_plugin(app):
    try:
        from superset_data_entry import register_plugin
        plugin_instance = register_plugin(app.appbuilder)
        logger.info("✅ Data Entry Plugin initialized successfully")
        return plugin_instance
    except ImportError as e:
        logger.warning(f"⚠️  Data Entry Plugin not installed: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Plugin initialization failed: {e}")
        return None
```

### 4. Install the plugin in the Superset environment

**If Superset runs in Docker** (e.g. custom Dockerfile):

- Copy the plugin into the image and install in the same venv Superset uses:

```dockerfile
COPY superset-data-entry-plugin /tmp/superset-data-entry-plugin
RUN /app/.venv/bin/pip install --no-deps -e /tmp/superset-data-entry-plugin
```

- Copy `superset_config.py` and `superset_init_plugin.py` to where Superset loads them (e.g. `/app/superset/` or a mounted path in `sys.path`).

**If Superset runs on the host (venv):**

```bash
cd /path/to/superset-data-entry-plugin
pip install --no-deps -e .
```

### 5. Create plugin tables in your project’s database

Run these migrations **against the same database** you set in `DATA_ENTRY_DB_CONFIG` (your project’s PostgreSQL). You can use Flyway, raw SQL, or your app’s migration runner.

Copy and run the SQL from this repo's **`migrations/`** folder:

- **`migrations/V6__create_form_configurations_table.sql`**
- **`migrations/V7__create_form_fields_table.sql`**

Example (replace with your DB name and user):

```bash
psql -U your_user -d your_database -f migrations/V6__create_form_configurations_table.sql
psql -U your_user -d your_database -f migrations/V7__create_form_fields_table.sql
```

After this, the plugin will create **data tables** (e.g. `profile_details`, `vessel_dp_shift_config`) when you create forms with “Create table” / auto-create enabled.

### 6. Restart Superset

- **Docker:** rebuild the Superset image if you changed Dockerfile, then `docker compose up -d superset` (or equivalent).
- **Host:** restart the Superset process (e.g. `superset run` or your systemd/gunicorn command).

### 7. Verify

- Open Superset → top menu should show **Data Entry**.
- Go to **Data Entry → Data Entry Forms** (list may be empty).
- **Data Entry → Configure Forms** (admin) → create a test form and add a field → Save. Then **Data Entry Forms** → your form → **Enter Data** → submit. Data will be in the table you set for that form in **your project’s PostgreSQL**.

---

## Option B: Install as a pip package (reusable across projects)

Use this when you want to install the plugin like any other Python package (e.g. from a private PyPI or from source).

### 1. Make the package installable

From this repo:

```bash
cd platform/superset-data-entry-plugin
pip install build
python -m build
# Or: pip install --no-deps -e .
```

Use the built wheel/sdist in the other project, or publish to a private PyPI and install from there.

### 2. In the other project

Install in the **same Python/venv Superset uses**:

```bash
pip install --no-deps /path/to/superset_data_entry_plugin-1.0.0-*.whl
# Or: pip install --no-deps -e /path/to/superset-data-entry-plugin
```

`--no-deps` avoids upgrading Flask/SQLAlchemy under Superset; the plugin relies on Superset’s existing stack.

### 3. Config and init (same as Option A)

- Add **`DATA_ENTRY_DB_CONFIG`** and **`FLASK_APP_MUTATOR`** to that project’s `superset_config.py` (pointing to **that project’s** PostgreSQL).
- Add **`superset_init_plugin.py`** next to `superset_config.py` (same content as in Option A).
- Ensure `superset_config.py` is loaded by Superset (same path or env as in that project).

### 4. Database (same as Option A)

Run **V6** and **V7** migrations on **that project’s** database (the one in `DATA_ENTRY_DB_CONFIG`).

### 5. Restart and verify (same as Option A)

Restart Superset and check **Data Entry** menu and form create/enter/view flow.

---

## Configuration summary (any project)

| Item | Where | Purpose |
|------|--------|--------|
| `DATA_ENTRY_DB_CONFIG` | `superset_config.py` | PostgreSQL that stores `form_configurations`, `form_fields`, and all form data tables. |
| `FLASK_APP_MUTATOR` | `superset_config.py` | Calls `init_data_entry_plugin(app)` so the plugin registers with Superset. |
| `superset_init_plugin.py` | Same dir as `superset_config.py` (or on `sys.path`) | Imports `superset_data_entry` and calls `register_plugin(app.appbuilder)`. |
| V6 + V7 migrations | Your project’s DB (same as `DATA_ENTRY_DB_CONFIG`) | Create `form_configurations` and `form_fields`. |

---

## Using it with other projects – checklist

- [ ] Plugin code available (copied or pip-installed) in the environment where Superset runs.
- [ ] `superset_config.py` has `DATA_ENTRY_DB_CONFIG` pointing to **that project’s** PostgreSQL.
- [ ] `superset_config.py` has `FLASK_APP_MUTATOR` that calls `init_data_entry_plugin(app)`.
- [ ] `superset_init_plugin.py` is on the Python path and imports `register_plugin`.
- [ ] V6 and V7 migrations run on the database in `DATA_ENTRY_DB_CONFIG`.
- [ ] Superset restarted after config/plugin changes.
- [ ] In Superset: **Data Entry** menu visible; create a form and submit a record; check the table in your DB.

---

## Optional: Custom validators (per project)

In the project that uses the plugin, you can register validators so form validation rules (e.g. `custom_validator: "validate_shift_duration"`) work. Do this **after** the plugin is loaded (e.g. in `superset_init_plugin.py` after `register_plugin`, or in a separate module Superset loads at startup):

```python
from superset_data_entry.validation import ValidationEngine

ValidationEngine.register_validator('validate_shift_duration', lambda v: 1 <= float(v) <= 24)
ValidationEngine.register_validator('validate_grace_period', lambda v: 0 <= int(v) <= 60)
```

---

## Optional: Seed forms via migration

To pre-create forms in another project, add a migration (e.g. `V10__seed_my_forms.sql`) that inserts into `form_configurations` and `form_fields` in the same database. Reference this repo’s `migrations/` (or the source project's `app/appbase-schemas/V9__seed_vessel_dp_form_config.sql`) for structure.

---

## Troubleshooting

- **“Data Entry” menu missing**  
  Check Superset logs for plugin import errors. Ensure `FLASK_APP_MUTATOR` runs and `init_data_entry_plugin` is called; ensure `superset_data_entry` is importable (plugin installed, correct Python env).

- **“DATA_ENTRY_DB_CONFIG not found” / “missing values”**  
  Define `DATA_ENTRY_DB_CONFIG` in `superset_config.py` and ensure all keys (`host`, `port`, `username`, `password`, `database`) are set (e.g. via env).

- **“Plugin tables not found”**  
  Run V6 and V7 on the database specified in `DATA_ENTRY_DB_CONFIG` (usually `public` schema).

- **Form submit / “Connection” or “commit” errors**  
  Plugin uses SQLAlchemy 2–style `engine.begin()`. Ensure the project’s Superset/env uses a compatible SQLAlchemy version.

- **CSP / script errors on Form Builder or data entry**  
  Plugin serves JS from `/data-entry-plugin/static/` and uses nonces where required. Ensure you didn’t remove the static blueprint or change CSP in a way that blocks those scripts.

---

## Reference: files in this repo

| Path | Use in other project |
|------|----------------------|
| This repo root | Package for install: `pip install .` or install from private Git (see above). |
| `superset_init_plugin.py` | Not in this repo; see "Plugin init file" section in this doc for contents. Copy into the other project next to their `superset_config.py`. |
| `superset_config.py` | Reference for `FLASK_APP_MUTATOR` and `DATA_ENTRY_DB_CONFIG` only (merge into their config). |
| `migrations/V6__create_form_configurations_table.sql` | Run on their DB. |
| `migrations/V7__create_form_fields_table.sql` | Run on their DB. |

Once these are in place, the plugin runs in that project and all form data is stored in **that project’s PostgreSQL** (the one in `DATA_ENTRY_DB_CONFIG`).
