# Set Up the Plugin in a New Project

Use this guide to add the Superset Data Entry Plugin to a **new** Superset project. The flow is: **pip install → run setup script → add one snippet to config → restart**. Migrations run automatically on first load.

---

## 1. Install the plugin

Use the **same Python environment** as Superset (virtualenv, conda, or container).

```bash
# From your private Git repo (replace YOUR_ORG and REPO_NAME)
pip install --no-deps "git+https://github.com/YOUR_ORG/REPO_NAME.git@main"

# With token (private repo)
pip install --no-deps "git+https://USERNAME:TOKEN@github.com/YOUR_ORG/REPO_NAME.git@main"

# Or from a local clone
cd /path/to/superset-data-entry-plugin
pip install --no-deps -e .
```

**Important:** Use `--no-deps` so Superset’s existing Flask/SQLAlchemy (and other deps) are not upgraded.

---

## 2. Run the setup script

This creates `superset_init_plugin.py` in your config directory and prints the code you need to add to `superset_config.py`.

```bash
# If you're already in the directory that contains superset_config.py
superset-data-entry-setup

# Or point to that directory
superset-data-entry-setup --config-dir /path/to/your/superset/config
```

To overwrite an existing `superset_init_plugin.py`:

```bash
superset-data-entry-setup --config-dir /path/to/config --force
```

---

## 3. Add the snippet to superset_config.py

The script prints a short block of code. Add it to your `superset_config.py`. Ensure `import os` is at the top of the file (the snippet uses `os.path`).

Example of what you add:

```python
def FLASK_APP_MUTATOR(app):
    try:
        import sys
        config_dir = os.path.dirname(os.path.abspath(__file__))
        if config_dir not in sys.path:
            sys.path.insert(0, config_dir)
        from superset_init_plugin import init_data_entry_plugin
        init_data_entry_plugin(app)
    except Exception as e:
        print("⚠️  Failed to load data entry plugin: %s" % e)
```

---

## 4. Restart Superset

Restart your Superset process (e.g. `superset run`, gunicorn, or Docker).

On **first load**, the plugin will create the required database tables (`form_configurations`, `form_fields`) in Superset’s database automatically. You do **not** need to run any migration SQL by hand.

---

## 5. Verify

- Open Superset in the browser.
- You should see a **Data Entry** menu.
- Go to **Data Entry → Data Entry Forms** (list may be empty).
- **Data Entry → Configure Forms** (admin) to create your first form.

---

## Summary

| Step | Command / action |
|------|-------------------|
| 1 | `pip install --no-deps git+https://...` (or `pip install --no-deps -e .`) |
| 2 | `superset-data-entry-setup` (optionally with `--config-dir`) |
| 3 | Add the printed snippet to `superset_config.py` |
| 4 | Restart Superset |
| 5 | Use **Data Entry** in the UI |

No separate database configuration is required: the plugin uses Superset’s database (`SQLALCHEMY_DATABASE_URI`). No manual migration step: tables are created automatically on first plugin load.
