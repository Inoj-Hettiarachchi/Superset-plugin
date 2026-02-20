# Data Entry Plugin – Setup in a New Project

Use this when adding the **Superset Data Entry Plugin** to a new project that runs Apache Superset.

---

## 1. Install the plugin

**In the same Python environment Superset uses** (e.g. inside your Superset Docker image or venv):

```bash
pip install --no-deps "git+https://github.com/Inoj-Hettiarachchi/Superset-plugin.git@main"
```

For a **private** repo, use a token or SSH:

```bash
pip install --no-deps "git+https://<TOKEN>@github.com/Inoj-Hettiarachchi/Superset-plugin.git@main"
# or
pip install --no-deps "git+ssh://git@github.com/Inoj-Hettiarachchi/Superset-plugin.git@main"
```

---

## 2. Add the init file

Create **`superset_init_plugin.py`** in the **same directory as your `superset_config.py`** (e.g. next to Superset’s config):

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
        logger.warning("⚠️  Data Entry Plugin not installed: %s", e)
        return None
    except Exception as e:
        logger.error("❌ Plugin initialization failed: %s", e)
        return None
```

---

## 3. Register the plugin in Superset config

In your project’s **`superset_config.py`**, add (or merge with an existing `FLASK_APP_MUTATOR`):

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
        print("⚠️  Failed to load data entry plugin: %s" % e)
```

No extra database config is needed: the plugin uses Superset’s database (`SQLALCHEMY_DATABASE_URI`).

---

## 4. Create plugin tables (one-time)

The plugin needs two tables in **Superset’s database**: `form_configurations` and `form_fields`.

- If the plugin runs its own migrations on first load, tables may be created automatically.
- If you see errors like `relation "form_configurations" does not exist`, run the migration SQL once against the **same database** Superset uses.

Get the SQL from the plugin repo’s **`migrations/`** (e.g. `V6__create_form_configurations_table.sql` and `V7__create_form_fields_table.sql`) and run them in order on that database.

---

## 5. Restart Superset

- **Docker:** rebuild the Superset image if you changed the Dockerfile, then start the container (e.g. `docker compose up -d superset`).
- **Host:** restart the Superset process.

---

## 6. Verify

- In Superset, the top menu should show **Data Entry**.
- Open **Data Entry → Data Entry Forms** and **Data Entry → Configure Forms** (admin).
- Create a test form, add a field, save, then submit a record; data is stored in Superset’s database.

---

## Checklist

- [ ] Plugin installed (`pip install` from Git) in Superset’s environment
- [ ] `superset_init_plugin.py` next to `superset_config.py`
- [ ] `FLASK_APP_MUTATOR` in `superset_config.py` calling `init_data_entry_plugin(app)`
- [ ] Plugin tables created in Superset’s DB (if not auto-created)
- [ ] Superset restarted
