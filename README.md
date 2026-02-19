# Superset Data Entry Plugin

A Flask-AppBuilder plugin that adds dynamic data entry form capabilities to Apache Superset.

## Features

- ✅ **Dynamic Form Builder** - Create forms through UI without writing code
- ✅ **Advanced Validation** - Type checking, constraints, regex patterns, custom validators
- ✅ **Role-Based Access** - Leverage Superset's existing role system
- ✅ **Auto Table Management** - Automatically creates and migrates database tables
- ✅ **Zero Coupling** - Works with any Superset version
- ✅ **Reusable** - Install in any Superset instance

## Installation

### Install from private Git (Option A)

Use the same Python environment as Superset. Replace `YOUR_ORG` and repo name with your GitHub org and repo.

```bash
# Default branch (e.g. main)
pip install --no-deps git+https://github.com/YOUR_ORG/superset-data-entry-plugin.git@main

# Private repo with token
pip install --no-deps "git+https://USERNAME:TOKEN@github.com/YOUR_ORG/superset-data-entry-plugin.git@main"

# SSH
pip install --no-deps "git+ssh://git@github.com/YOUR_ORG/superset-data-entry-plugin.git@main"

# Pin to a tag
pip install --no-deps git+https://github.com/YOUR_ORG/superset-data-entry-plugin.git@v1.0.0
```

Always use `--no-deps` to avoid upgrading Superset's Flask/SQLAlchemy. Then see **Configure Superset** and **Run migrations** below.

### Install from a local directory

```bash
cd superset-data-entry-plugin
pip install --no-deps -e .
```

### Configure Superset

Add to your `superset_config.py`:

```python
import os

DATA_ENTRY_DB_CONFIG = {
    'host': os.environ.get('SUPERSET_APPBASE_DB_HOST', 'localhost'),
    'port': int(os.environ.get('SUPERSET_APPBASE_DB_PORT', '5432')),
    'username': os.environ.get('SUPERSET_APPBASE_DB_USER', 'your_user'),
    'password': os.environ.get('SUPERSET_APPBASE_DB_PASSWORD', 'your_password'),
    'database': os.environ.get('SUPERSET_APPBASE_DB_NAME', 'your_database'),
}

def FLASK_APP_MUTATOR(app):
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from superset_init_plugin import init_data_entry_plugin
        init_data_entry_plugin(app)
    except Exception as e:
        print(f"⚠️  Failed to load data entry plugin: {e}")
```

Create `superset_init_plugin.py` in the same directory as `superset_config.py`:

```python
import logging
logger = logging.getLogger(__name__)

def init_data_entry_plugin(app):
    try:
        from superset_data_entry import register_plugin
        plugin_instance = register_plugin(app.appbuilder)
        logger.info("✅ Data Entry Plugin initialized successfully")
        return plugin_instance
    except Exception as e:
        logger.error(f"❌ Plugin initialization failed: {e}")
        return None
```

### Run database migrations

Run the SQL in the `migrations/` folder on your PostgreSQL (the one in `DATA_ENTRY_DB_CONFIG`):

- `migrations/V6__create_form_configurations_table.sql`
- `migrations/V7__create_form_fields_table.sql`

Then restart Superset.

## Usage

1. **Data Entry** → **Data Entry Forms** – list and open forms
2. **Data Entry** → **Configure Forms** (admin) – create/edit forms and fields
3. **Enter Data** / **View Data** on each form card

See **DEPLOY_DATA_ENTRY_PLUGIN_OTHER_PROJECTS.md** for full deployment in other projects.

## Field Types

- `text`, `textarea`, `number`, `integer`, `decimal`, `date`, `datetime`, `time`, `select`, `checkbox`, `boolean`

## License

Apache License 2.0
