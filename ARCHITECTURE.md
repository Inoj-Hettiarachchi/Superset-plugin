# Superset Data Entry Plugin — Architecture

This document describes the architecture of the complete implementation.

---

## 1. High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         APACHE SUPERSET (Host)                                    │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │  superset_config.py  →  FLASK_APP_MUTATOR  →  register_plugin(appbuilder)   │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    SUPERSET DATA ENTRY PLUGIN                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ __init__.py  │  │   views.py   │  │   api.py     │  │  validation.py        │  │
│  │ (Bootstrap)  │  │ (Web UI)     │  │ (REST API)   │  │  table_manager.py      │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────────┬─────────────┘  │
│         │                 │                 │                      │               │
│         └─────────────────┴─────────────────┴──────────────────────┘               │
│                                          │                                          │
│                          ┌───────────────┴───────────────┐                         │
│                          │  dao.py (Data Access)         │                         │
│                          │  models.py (ORM entities)     │                         │
│                          └───────────────┬───────────────┘                         │
└──────────────────────────────────────────┼─────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│              SUPERSET DATABASE (SQLALCHEMY_DATABASE_URI)                          │
│  ┌─────────────────────────┐   ┌─────────────────────────────────────────────┐  │
│  │ form_configurations     │   │  Dynamic tables (one per form)                │  │
│  │ form_fields             │   │  e.g. vessel_shift_config, profile_details   │  │
│  └─────────────────────────┘   └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Entry Point & Bootstrap (`__init__.py`)

**Role:** Register the plugin with Superset and wire all layers.

| Step | Method | Responsibility |
|------|--------|----------------|
| 1 | `_setup_template_folder()` | Add plugin Jinja2 template folder via `ChoiceLoader` so plugin templates are found first. |
| 2 | `_setup_static_files()` | Register Flask Blueprint at `/data-entry-plugin/static/` for JS/CSS (avoids CSP issues). |
| 3 | `_setup_database()` | Read `SQLALCHEMY_DATABASE_URI` from Superset config; create shared `DATA_ENTRY_ENGINE` and store in `app.config`. |
| 4 | `_register_views()` | Register FAB views (FormListView, FormBuilderView, DataEntryView, DataGridView) and menu entries. |
| 5 | `_register_api()` | Mount API blueprint at `/api/v1/data-entry`. |
| 6 | `_health_check()` | Verify DB connectivity and presence of `form_configurations` and `form_fields` tables. |

**Integration:** Superset calls `FLASK_APP_MUTATOR(app)`; host project calls `init_data_entry_plugin(app)` which invokes `register_plugin(app.appbuilder)` → `SupersetDataEntryPlugin(appbuilder)`.

---

## 3. Data Layer

### 3.1 Database

- **Single database:** Superset’s own DB (`SQLALCHEMY_DATABASE_URI`). No separate `DATA_ENTRY_DB_CONFIG`.
- **Shared engine:** One SQLAlchemy engine per app, stored in `app.config['DATA_ENTRY_ENGINE']`. Views and API use `get_db_session()` to obtain a session and this engine.

### 3.2 Schema (metadata tables)

| Table | Purpose |
|-------|--------|
| `form_configurations` | Form metadata: name, title, description, `table_name`, is_active, allow_edit, allow_delete, audit fields. |
| `form_fields` | Per-form field definitions: field_name, field_label, field_type, field_order, is_required, validation_rules (JSONB), options (JSONB), etc. |

Created by migrations: `migrations/V6__create_form_configurations_table.sql`, `migrations/V7__create_form_fields_table.sql`.

### 3.3 Dynamic tables

- One **dynamic table** per form (name = `form_configurations.table_name`).
- Created/updated by **TableManager** from form configuration (field types → PostgreSQL column types).
- Each table has: `id` (SERIAL), form-defined columns, plus `created_by`, `created_at`, `updated_at`.

### 3.4 Models (`models.py`)

| Model | Table | Role |
|-------|--------|------|
| `FormConfiguration` | `form_configurations` | Form metadata; relationship to `FormField`. |
| `FormField` | `form_fields` | Field definitions; `validation_rules` and `options` as JSONB. |

Used by DAO layer with the plugin’s engine/session (not Superset’s FAB session).

### 3.5 Data Access (`dao.py`)

| DAO | Responsibility |
|-----|----------------|
| **FormConfigDAO** | CRUD for `FormConfiguration` (get_all, get_all_active, get_by_id, get_by_name, create, update, delete). |
| **FormFieldDAO** | CRUD for `FormField` (get_by_form_id, create, update, delete). |
| **DataEntryDAO** | Operations on **dynamic** tables: get_all (paginated), get_by_id, insert, update, delete, search. Uses raw SQL via `engine` (no ORM for dynamic tables). |

---

## 4. Business Logic Layer

### 4.1 Table Manager (`table_manager.py`)

- **Create table:** `create_table_from_config(form_config, engine)` — maps form fields to PostgreSQL types, creates table and index on `created_at`.
- **Schema migration:** `migrate_schema(form_config, engine)` — adds new columns if form fields were added; does not drop columns.
- **Utilities:** `table_exists`, `get_table_columns`, `drop_table`, `validate_table_schema`.
- **Field type mapping:** e.g. text → VARCHAR(255), textarea → TEXT, number → NUMERIC, date → DATE, boolean/checkbox → BOOLEAN, select → VARCHAR(100).

### 4.2 Validation Engine (`validation.py`)

- **Form-level:** `validate_form(form_config, data)` → dict of field_name → list of error messages.
- **Field-level:** `validate_field(value, field_config)` — required, type (int, float, date, etc.), min/max, regex, custom validators.
- **Custom validators:** `ValidationEngine.register_validator(name, callable)` — register per-project validators referenced in `validation_rules` (e.g. `custom_validator: "validate_shift_duration"`).

---

## 5. API Layer (`api.py`)

**Base URL:** `/api/v1/data-entry`  
**Auth:** Uses FAB’s `@has_access`; admin-only where applicable.

| Method | Endpoint | Purpose |
|--------|----------|--------|
| GET | `/forms` | List active forms. |
| GET | `/forms/<id>` | Get form with fields. |
| POST | `/forms` | Create form (admin); can create table via TableManager. |
| PUT | `/forms/<id>` | Update form (admin); can run migrate_schema. |
| DELETE | `/forms/<id>` | Delete form (admin). |
| POST | `/forms/<id>/fields` | Add field to form (admin). |
| GET | `/forms/<id>/entries` | List records (paginated) from form’s dynamic table. |
| POST | `/forms/<id>/entries` | Insert record (with validation). |
| PUT | `/forms/<id>/entries/<record_id>` | Update record. |
| DELETE | `/forms/<id>/entries/<record_id>` | Delete record. |
| POST | `/forms/<id>/validate` | Validate payload without saving. |
| GET | `/health` | Health check (DB + plugin tables). |

All form/config operations use **FormConfigDAO / FormFieldDAO** with session from `get_db_session()`. All entry operations use **DataEntryDAO** with the shared **engine** and the form’s `table_name`. Validation uses **ValidationEngine** before insert/update.

---

## 6. Web UI Layer (`views.py`)

Flask-AppBuilder **BaseView** subclasses; all use `@has_access` and the same `get_db_session()` / DAOs / TableManager / ValidationEngine.

| View | route_base | Exposed routes | Purpose |
|------|------------|----------------|----------|
| **FormListView** | `/data-entry/forms` | `/list/` | List active forms; links to Enter Data / View Data / Configure (admin). |
| **FormBuilderView** | `/data-entry/builder` | `/`, `/<form_id>`, `/save` (POST) | Form builder UI (admin); load/save form and fields; create/update table via TableManager. |
| **DataEntryView** | `/data-entry/entry` | `/<form_id>`, `/<form_id>/submit` (POST) | Single-record data entry form; submit validated via ValidationEngine and DataEntryDAO.insert. |
| **DataGridView** | `/data-entry/data` | `/<form_id>`, `/<form_id>/delete/<record_id>` (POST) | Grid of records; pagination; delete. |

Templates (under `templates/data_entry/`):

- `form_list.html` — form cards, actions.
- `form_builder.html` — configure form and fields.
- `data_entry.html` — one form for data entry.
- `data_grid.html` — table of records.
- `error.html` — error display.

Static assets (under `static/`): `data_entry.js`, `data_grid.js`, `form_builder.js`, `data_entry_plugin.css` — served at `/data-entry-plugin/static/`.

---

## 7. Request Flow Examples

### 7.1 List forms (UI)

1. User opens **Data Entry → Data Entry Forms**.
2. **FormListView.list()** → `get_db_session()` → **FormConfigDAO.get_all_active(session)** → render `form_list.html` with forms.

### 7.2 Create form and table (admin)

1. Admin opens **Configure Forms** → new form.
2. **FormBuilderView.build()** renders `form_builder.html`.
3. On save, **FormBuilderView.save()** (or API `POST /forms`) → **FormConfigDAO.create()** + **FormFieldDAO** for each field.
4. If “create table” is chosen, **TableManager.create_table_from_config(form_config, engine)** runs → new table in Superset DB.

### 7.3 Submit data entry

1. User opens **Enter Data** for a form.
2. **DataEntryView** loads form and fields; renders `data_entry.html`.
3. On submit, **DataEntryView** (or API `POST /forms/<id>/entries`) → **ValidationEngine.validate_form()** → **DataEntryDAO.insert(engine, table_name, data, username)**.

### 7.4 View / edit / delete records

1. **DataGridView** (or API `GET /forms/<id>/entries`) → **DataEntryDAO.get_all(engine, table_name, page, per_page)**.
2. Edit: load record → **DataEntryDAO.update(...)** (with validation).
3. Delete: **DataEntryDAO.delete(engine, table_name, record_id)**.

---

## 8. File Layout Summary

```
Superset-plugin/
├── superset_data_entry/
│   ├── __init__.py          # Bootstrap: DB, views, API, health
│   ├── models.py            # FormConfiguration, FormField (ORM)
│   ├── dao.py               # FormConfigDAO, FormFieldDAO, DataEntryDAO
│   ├── table_manager.py     # Create/migrate dynamic tables
│   ├── validation.py       # ValidationEngine (type, rules, custom)
│   ├── api.py              # REST blueprint /api/v1/data-entry
│   ├── views.py             # FAB views (list, builder, entry, grid)
│   ├── templates/data_entry/
│   │   ├── form_list.html
│   │   ├── form_builder.html
│   │   ├── data_entry.html
│   │   ├── data_grid.html
│   │   └── error.html
│   └── static/
│       ├── data_entry.js
│       ├── data_grid.js
│       ├── form_builder.js
│       └── data_entry_plugin.css
├── migrations/
│   ├── V6__create_form_configurations_table.sql
│   └── V7__create_form_fields_table.sql
├── setup.py / pyproject.toml
├── README.md
└── ARCHITECTURE.md (this file)
```

---

## 9. Security & Permissions

### 9.1 How users are managed

**The plugin does not manage users.** User accounts, passwords, and roles are managed entirely by **Apache Superset / Flask-AppBuilder**. The plugin only uses the **currently logged-in user** from the host app:

- **`g.user`** – The authenticated user object (from FAB) in the current request.
- **`g.user.username`** – Stored as **audit** on each record (`created_by` in dynamic tables).
- **`g.user.roles`** – Used only to detect **Admin** for form configuration (see below).

So: create/edit/delete users and assign roles in **Superset’s Security → Users / Roles**. The plugin has no user table and no user CRUD.

### 9.2 Who can enter data?

**Any logged-in user who has permission to access the Data Entry views can enter data.** Access is controlled by **Flask-AppBuilder permissions**, not by the plugin:

- Every view and API route is protected with **`@has_access`**. FAB ties that to **roles** and **permissions** (e.g. permission to open “Data Entry Forms” or “FormBuilderView”, etc.).
- **Who sees the Data Entry menu** is configured in Superset under **Security → Roles**: each role has a set of permissions; if a role has permission for the Data Entry menu/views, users with that role can open the forms list, enter data, view data, and (if Admin) configure forms.
- The plugin does **not** restrict “only role X can submit data”. If a user can reach the data entry form (because their role has the right permissions), they can submit. To restrict data entry to certain roles, you limit which roles have the **Data Entry** (and related) permissions in Superset.

So in practice: **any user type that can access the plugin’s pages can enter data**; “can access” is decided by Superset’s role/permission setup.

### 9.3 User mapping (how the current user is used)

| Use | How it works |
|-----|----------------|
| **Authorization** | `g.user` is the current request’s user. `is_admin()` checks `any(role.name == 'Admin' for role in g.user.roles)`. Only users with the **Admin** role can create/edit/delete forms, open the form builder, or use the corresponding API endpoints. |
| **Audit on records** | On **insert**, `DataEntryDAO.insert(..., username=g.user.username)` sets `created_by` (and `created_at` / `updated_at`) on the row. On **update**, the same `username` can be passed for an “updated by” concept if you add it. So “user mapping” for data is: **Superset username → `created_by` (and optionally updated_by) in the dynamic table**. |
| **Form config audit** | When a form is **created**, `FormConfigDAO.create(..., created_by=g.user.username)` sets `created_by` on `form_configurations`. |

There is **no separate user table or ID** in the plugin: the **username string** from Superset’s user is the only “user identifier” stored.

### 9.4 Summary flow

1. User logs into **Superset** (FAB handles login and session).
2. User opens **Data Entry → Data Entry Forms** (allowed only if their role has the right FAB permissions).
3. **List forms** – `FormListView` / API: `@has_access` allows access; all active forms are shown.
4. **Enter data** – `DataEntryView` / API: `@has_access` allows access; on submit, `g.user.username` is written to `created_by` (and timestamps) on the dynamic table.
5. **Configure forms** – `FormBuilderView` / API: in addition to `@has_access`, the code checks **`is_admin()`**; only users with the **Admin** role can create/edit/delete forms or use the builder.

So: **users are managed in Superset; any user type that can access the plugin can enter data (governed by FAB permissions); user mapping is “current Superset user’s username stored in `created_by` (and similar) on records”.**

- **Authentication:** Delegated to Superset (FAB); plugin uses `g.user` and `@has_access`.
- **Admin-only:** Form create/update/delete and form builder UI check `is_admin()` (role name `"Admin"`).
- **Database:** Single Superset DB; same credentials for metadata and dynamic tables. No separate DB config.

---

## 10. Dependencies

- **Flask** (Superset’s)
- **Flask-AppBuilder** (views, security, BaseView)
- **SQLAlchemy** (engine, session, text, inspect)
- **PostgreSQL** (dialect for metadata and dynamic tables)

Plugin is designed to use Superset’s existing stack; `pip install` with `--no-deps` is recommended to avoid upgrading Superset’s packages.
