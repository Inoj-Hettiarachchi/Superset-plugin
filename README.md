# Superset Data Entry Plugin

A Flask-AppBuilder plugin that adds dynamic data entry form capabilities to Apache Superset.

## Quick setup in a new project

1. **Install:** `pip install --no-deps git+https://github.com/YOUR_ORG/REPO_NAME.git@main`
2. **Run setup:** `superset-data-entry-setup` (or `superset-data-entry-setup --config-dir /path/to/superset/config`)
3. **Add the printed snippet** to your `superset_config.py`
4. **Restart Superset** — plugin tables are created automatically on first load

See **[SETUP_NEW_PROJECT.md](SETUP_NEW_PROJECT.md)** for the full step-by-step guide.

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

Always use `--no-deps` to avoid upgrading Superset's Flask/SQLAlchemy. For the simplest path, run **superset-data-entry-setup** and follow [SETUP_NEW_PROJECT.md](SETUP_NEW_PROJECT.md).

### Install from a local directory

```bash
cd superset-data-entry-plugin
pip install --no-deps -e .
```

### Configure Superset (manual option)

If you prefer not to use the setup script, add the `FLASK_APP_MUTATOR` to `superset_config.py` and create `superset_init_plugin.py` in the same directory (see [SETUP_NEW_PROJECT.md](SETUP_NEW_PROJECT.md) for the exact snippet and init file content). The plugin uses Superset's database (`SQLALCHEMY_DATABASE_URI`); **migrations run automatically** on first plugin load — no need to run SQL by hand.

## Usage

1. **Data Entry** → **Data Entry Forms** – list and open forms
2. **Data Entry** → **Configure Forms** (admin) – create/edit forms and fields
3. **Enter Data** / **View Data** on each form card

See **DEPLOY_DATA_ENTRY_PLUGIN_OTHER_PROJECTS.md** for full deployment in other projects.

## Field Types

- `text`, `textarea`, `number`, `integer`, `decimal`, `date`, `datetime`, `time`, `select`, `checkbox`, `boolean`

## License

Apache License 2.0
