# Deploy Data Entry Plugin in Other Projects

This guide explains how to use the Superset Data Entry Plugin in **any other project** that runs Apache Superset. The plugin uses **Superset's database** (`SQLALCHEMY_DATABASE_URI`); **migrations run automatically** on first plugin load.

**Quick setup:** See **[SETUP_NEW_PROJECT.md](SETUP_NEW_PROJECT.md)** and use `superset-data-entry-setup`.

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

Then run `superset-data-entry-setup`, add the printed snippet to `superset_config.py`, and restart. Migrations run automatically on first load.

---

## What You Need in the Other Project

1. **The plugin package** (install via pip from Git, or copy from this repo).
2. **Superset configuration** – `FLASK_APP_MUTATOR` hook and `superset_init_plugin.py` (generate with `superset-data-entry-setup`).
3. **Database** – plugin tables (`form_configurations`, `form_fields`) are created **automatically** on first plugin load; no manual migration step required.
4. **Optional:** Custom validators or seed forms (migrations or UI).

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

### 2. Register the plugin

In the other project’s **`superset_config.py`** add (or merge with existing config):

```python
import os

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

**Note:** The plugin automatically uses Superset's database (`SQLALCHEMY_DATABASE_URI`) - no separate database configuration needed.

### 3. Add the init file

Run **`superset-data-entry-setup`** (from the directory that contains `superset_config.py`, or use `--config-dir`) to create `superset_init_plugin.py`. Or create/copy it manually in the **same directory as `superset_config.py`**:

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

- Install from Git (recommended):

```dockerfile
RUN pip install --no-deps "git+https://github.com/YOUR_ORG/Superset-plugin.git@main"
```

- Or copy the plugin and install locally:

```dockerfile
COPY superset-data-entry-plugin /tmp/superset-data-entry-plugin
RUN pip install --no-deps -e /tmp/superset-data-entry-plugin
```

- Ensure `superset_config.py` and `superset_init_plugin.py` are in the image or mounted (e.g. `/app/superset/`).

**If Superset runs on the host (venv):**

```bash
cd /path/to/superset-data-entry-plugin
pip install --no-deps -e .
```

### 5. Database (migrations run automatically)

**No manual step required.** On first plugin load, the plugin creates `form_configurations` and `form_fields` in Superset's database automatically. Optionally run the SQL in `superset_data_entry/migrations/` or root `migrations/` yourself if needed.

### 6. Restart Superset

- **Docker:** rebuild the Superset image if you changed Dockerfile, then `docker compose up -d superset` (or equivalent).
- **Host:** restart the Superset process (e.g. `superset run` or your systemd/gunicorn command).

### 7. Verify

- Open Superset → top menu should show **Data Entry**.
- Go to **Data Entry → Data Entry Forms** (list may be empty).
- **Data Entry → Configure Forms** (admin) → create a test form and add a field → Save. Then **Data Entry Forms** → your form → **Enter Data** → submit. Data will be in the table you set for that form in **Superset's database**.

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

- Add **`FLASK_APP_MUTATOR`** to that project's `superset_config.py` (plugin uses Superset's existing `SQLALCHEMY_DATABASE_URI`).
- Add **`superset_init_plugin.py`** next to `superset_config.py` (run `superset-data-entry-setup` or use same content as in Option A).
- Ensure `superset_config.py` is loaded by Superset (same path or env as in that project).

### 4. Database (same as Option A)

No manual migration step; plugin creates tables on first load.

### 5. Restart and verify (same as Option A)

Restart Superset and check **Data Entry** menu and form create/enter/view flow.

---

## Configuration summary (any project)

| Item | Where | Purpose |
|------|--------|--------|
| `FLASK_APP_MUTATOR` | `superset_config.py` | Calls `init_data_entry_plugin(app)` so the plugin registers with Superset. |
| `superset_init_plugin.py` | Same dir as `superset_config.py` | Generate with `superset-data-entry-setup`, or copy content from this doc. |
| Plugin tables | Superset's database | Created **automatically** on first load (`form_configurations`, `form_fields`). |

---

## Using it with other projects – checklist

- [ ] Plugin installed (pip from Git or copy) in the environment where Superset runs (e.g. inside Docker image).
- [ ] `superset_config.py` has `FLASK_APP_MUTATOR` that calls `init_data_entry_plugin(app)`.
- [ ] `superset_init_plugin.py` is on the Python path and imports `register_plugin`.
- [ ] Superset restarted after config/plugin changes (migrations run automatically on first load).
- [ ] In Superset: **Data Entry** menu visible; create a form and submit a record; data stored in Superset's database.

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

- **“SQLALCHEMY_DATABASE_URI not found” / “missing values”**  
  Define `SQLALCHEMY_DATABASE_URI` in `superset_config.py` and ensure all keys (`host`, `port`, `username`, `password`, `database`) are set (e.g. via env).

- **“Plugin tables not found”**  
  Tables are created automatically on first load. If you see this briefly, wait for “Migrations completed”. If it persists, ensure Superset's database is reachable and `SQLALCHEMY_DATABASE_URI` is set.

- **Form submit / “Connection” or “commit” errors**  
  Plugin uses SQLAlchemy 2–style `engine.begin()`. Ensure the project’s Superset/env uses a compatible SQLAlchemy version.

- **CSP / script errors on Form Builder or data entry**  
  Plugin serves JS from `/data-entry-plugin/static/` and uses nonces where required. Ensure you didn’t remove the static blueprint or change CSP in a way that blocks those scripts.

---

## Reference: files in this repo

| Path | Use in other project |
|------|----------------------|
| This repo root | Package for install: `pip install .` or install from private Git (see above). |
| `superset_init_plugin.py` | Generated by `superset-data-entry-setup`, or see "Plugin init file" in this doc. Place next to `superset_config.py`. |
| `superset_config.py` (snippet) | Add `FLASK_APP_MUTATOR` only; plugin uses Superset's existing `SQLALCHEMY_DATABASE_URI`. |
| `migrations/` (root or `superset_data_entry/migrations/`) | Bundled in package; plugin runs them automatically on first load. Optional: run manually if needed. |

Once these are in place, the plugin runs in that project and all form data is stored in **Superset's database** (`SQLALCHEMY_DATABASE_URI`).
