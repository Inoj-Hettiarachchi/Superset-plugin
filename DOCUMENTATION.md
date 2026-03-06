# Superset Data Entry Plugin — Comprehensive Documentation

> Version 1.0.0 · Apache Superset ≥ 2.1 · PostgreSQL only

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Permission Model](#3-permission-model)
4. [Database Schema](#4-database-schema)
5. [Migrations](#5-migrations)
6. [Form Configuration](#6-form-configuration)
7. [Field Types & Validation](#7-field-types--validation)
8. [REST API Reference](#8-rest-api-reference)
9. [Web UI Endpoints](#9-web-ui-endpoints)
10. [SharePoint Integration](#10-sharepoint-integration)
11. [Data Access Layer](#11-data-access-layer)
12. [Table Manager](#12-table-manager)
13. [Frontend Assets](#13-frontend-assets)
14. [Configuration Reference](#14-configuration-reference)
15. [Custom Validators](#15-custom-validators)
16. [Security Notes](#16-security-notes)
17. [File Reference](#17-file-reference)

---

## 1. Overview

The **Superset Data Entry Plugin** adds a fully functional data entry system to any Apache Superset instance. It allows administrators to create custom forms, configure field schemas, and let role-based users submit structured data — all stored directly in Superset's PostgreSQL database as first-class tables that can be immediately queried and charted in Superset.

**Key capabilities:**
- Dynamic form builder with drag-and-drop-style field ordering
- Role-based access control at the form level
- Server-side validation with pluggable custom validators
- Data grid with pagination, CSV export, and JSON seed file export
- Optional automatic upload to a Microsoft SharePoint document library (incremental, watermark-based)
- Zero configuration of a separate database — uses Superset's existing `SQLALCHEMY_DATABASE_URI`
- Auto-run SQL migrations on startup (idempotent, safe to restart)

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Apache Superset (Flask)                    │
│                                                               │
│  superset_config.py                                           │
│    └── FLASK_APP_MUTATOR → init_data_entry_plugin(app)        │
│                                 │                             │
│              SupersetDataEntryPlugin.__init__()               │
│              ├── _setup_template_folder()  (Jinja2 loader)    │
│              ├── _setup_static_files()     (Blueprint /static)│
│              ├── _setup_database()         (shared engine)    │
│              ├── _register_views()         (FAB views)        │
│              ├── _register_api()           (Flask blueprint)  │
│              └── _run_startup_checks()     (run migrations)   │
│                                                               │
│  ┌────────────┐  ┌─────────────────┐  ┌──────────────────┐   │
│  │  Web Views │  │   REST API      │  │  SharePoint      │   │
│  │  (views.py)│  │   (api.py)      │  │  (sharepoint.py) │   │
│  └─────┬──────┘  └────────┬────────┘  └────────┬─────────┘   │
│        │                  │                     │             │
│  ┌─────▼──────────────────▼─────────────────────▼──────────┐ │
│  │             Data Access Layer (dao.py)                   │ │
│  │  FormConfigDAO · FormFieldDAO · DataEntryDAO             │ │
│  └──────────────────────────────┬───────────────────────────┘ │
│                                 │                             │
│  ┌──────────────────────────────▼───────────────────────────┐ │
│  │          PostgreSQL (Superset's SQLALCHEMY_DATABASE_URI) │ │
│  │  form_configurations · form_fields · plugin_schema_      │ │
│  │  migrations · <dynamic per-form tables>                  │ │
│  └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Request Flow (data submission)

```
Browser → POST /data-entry/entry/<id>/submit
            │
            ├── _require_login()               check authenticated
            ├── can_access_form_list_and_submit() check FAB permission
            ├── user_can_enter_data_for_form()    check form role allowlist
            ├── ValidationEngine.validate_form()  field-level validation
            ├── DataEntryDAO.insert()             INSERT into <table_name>
            └── SharePointExporter.upload_row()   optional, non-blocking
```

---

## 3. Permission Model

The plugin uses **one FAB view** (`Data Entry`) with **three permissions**. Assign these in Superset under **Settings → Security → List Roles → edit role → Permissions**.

| Permission | FAB Name | What it allows |
|---|---|---|
| **Admin** | Superset `Admin` role | Create/configure forms, all data access, force SharePoint re-upload |
| `can_configure_forms` | `can configure_forms on Data Entry` | Create and configure forms (form builder) |
| `can_manage_data` | `can manage_data on Data Entry` | View data grid, download exports, upload to SharePoint, delete records (if form allows) |
| `can_entry_only` | `can entry_only on Data Entry` | Submit entries + view form list only; no data grid, no delete |

**Access rules summary:**

| Action | Admin | can_configure_forms | can_manage_data | can_entry_only |
|---|:---:|:---:|:---:|:---:|
| Create/configure forms | ✅ | ✅ | ❌ | ❌ |
| View form list | ✅ | ✅ | ✅ | ✅ |
| Submit entries | ✅ | ✅ | ✅ | ✅ |
| View data grid | ✅ | ✅ | ✅ | ✅ |
| Download CSV / seed | ✅ | ✅ | ✅ | ✅ |
| Upload to SharePoint | ✅ | ✅ | ✅ | ✅ |
| Delete records | ✅ | ✅ | ✅ | ❌ |
| Force SP re-upload | ✅ | ❌ | ❌ | ❌ |

### Form-level access

Even if a user has the `can_manage_data` permission, they can only see and submit to forms where either:
- They are the **form creator** (`created_by` matches their username), or
- Their Superset role is listed in the form's **Allowed Roles** (`allowed_role_names`)

Role comparison is **case-insensitive**.

### How admin detection works

The plugin detects admin users via Flask-AppBuilder's `SecurityManager`:

```python
sm.auth_role_admin          # configured admin role name (default: "Admin")
sm.get_user_roles(user)     # list of role objects for the user
flask_login.current_user    # always populated in a request context
```

> **Note:** `current_user_is_admin()` does **not** exist on FAB's SecurityManager. Always use the pattern above.

---

## 4. Database Schema

### `form_configurations`

Stores form metadata and SharePoint credentials.

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL PRIMARY KEY` | |
| `name` | `VARCHAR(100)` | Display name; not required to be unique |
| `title` | `VARCHAR(255)` | UI title |
| `description` | `TEXT` | Optional description |
| `table_name` | `VARCHAR(100) UNIQUE` | Physical PostgreSQL table; **must be unique** |
| `is_active` | `BOOLEAN` | Soft-delete flag; default `true` |
| `allow_edit` | `BOOLEAN` | Allow record editing; default `true` |
| `allow_delete` | `BOOLEAN` | Allow record deletion; default `false` |
| `created_by` | `VARCHAR(255)` | Superset username of creator |
| `allowed_role_names` | `JSONB` | Array of Superset role names allowed to submit |
| `created_at` | `TIMESTAMP` | |
| `updated_at` | `TIMESTAMP` | |
| `sharepoint_enabled` | `BOOLEAN` | Default `false` |
| `sharepoint_tenant_id` | `TEXT` | Azure Directory (tenant) ID |
| `sharepoint_client_id` | `TEXT` | Azure App (client) ID |
| `sharepoint_client_secret` | `TEXT` | **Plain text** — treat as sensitive |
| `sharepoint_site_url` | `TEXT` | Full SharePoint site URL |
| `sharepoint_folder_path` | `TEXT` | Relative folder path in document library |
| `sharepoint_last_uploaded_at` | `TIMESTAMP` | Watermark for incremental uploads |

### `form_fields`

Stores field definitions for each form.

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL PRIMARY KEY` | |
| `form_id` | `INTEGER FK → form_configurations.id` | Cascade delete |
| `field_name` | `VARCHAR(100)` | PostgreSQL column name |
| `field_label` | `VARCHAR(255)` | UI label |
| `field_type` | `VARCHAR(50)` | See field types below |
| `field_order` | `INTEGER` | Display/column order |
| `is_required` | `BOOLEAN` | |
| `default_value` | `TEXT` | |
| `placeholder` | `VARCHAR(255)` | |
| `help_text` | `TEXT` | |
| `validation_rules` | `JSONB` | See validation rules below |
| `options` | `JSONB` | For `select` fields: `[{"value": "x", "label": "X"}]` |
| `created_at` | `TIMESTAMP` | |
| `updated_at` | `TIMESTAMP` | |

### `plugin_schema_migrations`

Internal migration tracking table (auto-created by the plugin).

| Column | Type |
|---|---|
| `version` | `VARCHAR(255) PRIMARY KEY` |
| `applied_at` | `TIMESTAMP` |

### Per-form data tables

Each form creates a dynamic table named by `form_configurations.table_name`. Every such table has:

| Column | Type | Notes |
|---|---|---|
| `id` | `SERIAL PRIMARY KEY` | |
| *form fields* | varies | One column per `form_fields` entry |
| `created_by` | `VARCHAR(255)` | Superset username who submitted |
| `created_at` | `TIMESTAMP` | Submission time (UTC) |
| `updated_at` | `TIMESTAMP` | |

An index on `created_at DESC` is created automatically.

---

## 5. Migrations

All plugin migration files are in `superset_data_entry/migrations/` and are prefixed `DE_V<n>__` to avoid conflicts with the host project's own migrations (Flyway, Alembic, Liquibase, etc.).

| File | What it does |
|---|---|
| `DE_V6__create_form_configurations_table.sql` | Creates `form_configurations` |
| `DE_V7__create_form_fields_table.sql` | Creates `form_fields` |
| `DE_V8__add_allowed_role_names_to_form_configurations.sql` | Adds `allowed_role_names JSONB` |
| `DE_V9__allow_duplicate_form_names_unique_table_name.sql` | Makes `table_name` unique, relaxes `name` uniqueness |
| `DE_V10__add_sharepoint_config.sql` | Adds 6 SharePoint credential columns |
| `DE_V11__add_sharepoint_last_uploaded_at.sql` | Adds `sharepoint_last_uploaded_at` watermark |

**Behaviour:**
- Migrations run automatically at plugin startup via `MigrationsRunner.run_migrations(engine)`
- Each migration is applied **exactly once** (tracked in `plugin_schema_migrations`)
- Safe to restart — already-applied migrations are skipped
- New migration files are auto-discovered; no code changes needed to add more

**Migration file naming convention:**
```
DE_V<integer>__<snake_case_description>.sql
```

---

## 6. Form Configuration

### Creating a form (Admin only)

1. **Data Entry** → **Create New Form** (Admin only)
2. Set:
   - **Form Title** — display name in the UI
   - **Table Name** — the PostgreSQL table that will store data (e.g. `vessel_dp_log`). Must be unique. Auto-suffixed if taken (`vessel_dp_log_2`, etc.)
   - **Description** — optional
   - **Allow Edit / Allow Delete** — whether submitted records can be modified or removed
   - **Allowed Roles** — which Superset roles can submit data (multiselect from available roles)
3. Add fields in the **Fields** section
4. **Save Form** — creates the PostgreSQL table automatically

### `FormConfiguration` serialization (`to_dict`)

The `to_dict(include_fields=False)` method returns:
```json
{
  "id": 1,
  "name": "vessel_dp_log",
  "title": "Vessel DP Log",
  "description": "...",
  "table_name": "vessel_dp_log",
  "is_active": true,
  "allow_edit": true,
  "allow_delete": false,
  "created_by": "admin",
  "allowed_role_names": ["Alpha", "Gamma"],
  "created_at": "2026-03-01T10:00:00",
  "updated_at": "2026-03-06T14:30:00",
  "sharepoint_enabled": false,
  "sharepoint_tenant_id": null,
  "sharepoint_client_id": null,
  "sharepoint_site_url": null,
  "sharepoint_folder_path": null,
  "sharepoint_secret_set": false,
  "sharepoint_last_uploaded_at": null
}
```

> `sharepoint_client_secret` is **never** included in serialized output. `sharepoint_secret_set` (boolean) indicates whether a secret is stored.

---

## 7. Field Types & Validation

### Supported field types

| `field_type` | PostgreSQL type | Input rendered |
|---|---|---|
| `text` | `VARCHAR(255)` | Single-line text input |
| `textarea` | `TEXT` | Multi-line textarea |
| `number` | `NUMERIC(10,2)` | Number input |
| `integer` | `INTEGER` | Integer input |
| `decimal` | `NUMERIC(10,2)` | Decimal input |
| `date` | `DATE` | Date picker |
| `datetime` | `TIMESTAMP` | Datetime picker |
| `time` | `TIME` | Time picker |
| `boolean` | `BOOLEAN` | Toggle / checkbox |
| `checkbox` | `BOOLEAN` | Checkbox |
| `select` | `VARCHAR(100)` | Dropdown (requires `options`) |

### Validation rules (`validation_rules` JSONB)

Set on a field's `validation_rules` column as a JSON object:

```json
{
  "min": 0,
  "max": 100,
  "min_length": 2,
  "max_length": 50,
  "min_date": "2020-01-01",
  "max_date": "2030-12-31",
  "pattern": "^[A-Z]{3}-\\d{4}$",
  "custom_validator": "validate_shift_duration",
  "error_messages": {
    "min": "Value must be at least 0",
    "pattern": "Must be in format ABC-1234",
    "custom": "Shift duration must be between 1 and 24 hours"
  }
}
```

| Rule key | Applies to | Behaviour |
|---|---|---|
| `min` / `max` | number, integer, decimal | Numeric range check |
| `min_length` / `max_length` | text, textarea | String length check |
| `min_date` / `max_date` | date | Date range (ISO format) |
| `pattern` | text, textarea | Python `re.match` |
| `custom_validator` | any | Named validator from `ValidationEngine.CUSTOM_VALIDATORS` |
| `error_messages` | any | Override default error messages per rule |

### Validation behaviour

- `is_required=True` → empty/null value short-circuits all other rules
- If optional and empty → no further validation (skipped cleanly)
- Type mismatch → stops further checks (no point running range checks on wrong type)

---

## 8. REST API Reference

All API endpoints are under `/data-entry-api/`. Authentication uses Superset's session cookie (same as the UI).

### Form Endpoints

#### `GET /data-entry-api/forms`
List all active forms accessible to the current user.
- **Permission:** `can_manage_data` or `can_entry_only`
- **Response:** `200` array of form config objects

#### `GET /data-entry-api/forms/<id>`
Get a single form with its fields.
- **Permission:** `can_manage_data` or `can_entry_only`
- **Response:** `200` form config with `fields` array; `404` if not found or no access

#### `POST /data-entry-api/forms`
Create a new form.
- **Permission:** `can_configure_forms`
- **Body:**
  ```json
  {
    "name": "vessel_dp_log",
    "title": "Vessel DP Log",
    "table_name": "vessel_dp_log",
    "description": "...",
    "allow_edit": true,
    "allow_delete": false,
    "allowed_role_names": ["Alpha"],
    "auto_create_table": true,
    "fields": [ ... ]
  }
  ```
- **Response:** `201` created form; `400` missing required fields

#### `PUT /data-entry-api/forms/<id>`
Update a form (owner only).
- **Permission:** `can_configure_forms` + form owner
- **Response:** `200` updated form; `403` not owner; `404` not found

#### `DELETE /data-entry-api/forms/<id>`
Delete a form config record (does **not** drop the data table).
- **Permission:** `can_configure_forms` + form owner
- **Response:** `200 {"success": true}`

### Field Endpoints

#### `POST /data-entry-api/forms/<id>/fields`
Add a field to a form.
- **Permission:** `can_configure_forms` + form owner
- **Body:** field object (see `FormField` schema above)
- **Response:** `201` created field

### Data Entry Endpoints

#### `GET /data-entry-api/forms/<id>/entries`
List data entries with pagination.
- **Permission:** `can_manage_data`
- **Query params:** `page` (default 1), `per_page` (default 25)
- **Response:**
  ```json
  {
    "entries": [ ... ],
    "total": 150,
    "page": 1,
    "per_page": 25,
    "pages": 6
  }
  ```

#### `POST /data-entry-api/forms/<id>/entries`
Submit a new entry.
- **Permission:** `can_manage_data` or `can_entry_only`
- **Body:** `{ "field_name": value, ... }`
- **Response:** `201 {"success": true, "record_id": 42}`; `400` with `errors` dict on validation failure

#### `PUT /data-entry-api/forms/<id>/entries/<record_id>`
Update an entry (only if `allow_edit=true` on the form).
- **Permission:** `can_manage_data`
- **Response:** `200`; `403` if editing disabled

#### `DELETE /data-entry-api/forms/<id>/entries/<record_id>`
Delete an entry (only if `allow_delete=true` on the form).
- **Permission:** `can_manage_data`
- **Response:** `200`; `403` if deletion disabled

#### `POST /data-entry-api/forms/<id>/validate`
Validate data without saving.
- **Permission:** `can_manage_data` or `can_entry_only`
- **Body:** `{ "field_name": value, ... }`
- **Response:** `{ "valid": true/false, "errors": { "field_name": ["error msg"] } }`

### Health Check

#### `GET /data-entry-api/health`
Returns plugin status. No authentication required.
- **Response:** `{ "status": "ok", "version": "1.0.0", "plugin": "data-entry" }`

---

## 9. Web UI Endpoints

All web UI routes use Superset's standard session authentication (redirect to `/login` if unauthenticated).

| Method | URL | View | Access |
|---|---|---|---|
| `GET` | `/data-entry/forms/list/` | `FormListView.list` | any plugin access |
| `GET` | `/data-entry/builder/` | `FormBuilderView.build` | Admin or `can_configure_forms` |
| `GET` | `/data-entry/builder/<id>` | `FormBuilderView.build` | Admin or `can_configure_forms` |
| `POST` | `/data-entry/builder/save` | `FormBuilderView.save` | Admin only |
| `GET` | `/data-entry/entry/<id>` | `DataEntryView.entry` | `can_manage_data` or `can_entry_only` |
| `POST` | `/data-entry/entry/<id>/submit` | `DataEntryView.submit` | `can_manage_data` or `can_entry_only` |
| `GET` | `/data-entry/data/<id>` | `DataGridView.grid` | `can_manage_data` or `can_entry_only` |
| `GET` | `/data-entry/data/<id>/seed` | `DataGridView.seed_download` | `can_manage_data` or `can_entry_only` |
| `GET` | `/data-entry/data/<id>/csv` | `DataGridView.csv_download` | `can_manage_data` or `can_entry_only` |
| `POST` | `/data-entry/data/<id>/sharepoint-upload` | `DataGridView.sharepoint_upload` | `can_manage_data` or `can_entry_only` |
| `POST` | `/data-entry/data/<id>/delete/<rid>` | `DataGridView.delete` | `can_manage_data` |

### Downloads

- **Seed file** (`/seed`) — JSON format with form metadata + all records. Useful for migrating data between environments.
- **CSV** (`/csv`) — UTF-8 BOM CSV (Excel-compatible). Headers use field labels. Booleans rendered as `Yes`/`No`.

---

## 10. SharePoint Integration

### Overview

The SharePoint integration uses **Microsoft Graph API** with **OAuth2 client-credentials flow** (app-to-app, no user login). Each form gets one CSV file in the configured folder: `{form.name}.csv`.

### Two upload modes

#### Per-submission (`upload_row`)

Called automatically after every successful form submission when `sharepoint_enabled=True`. Appends a single row to the existing CSV. If the file doesn't exist, it is created with headers.

**Flow:**
1. Acquire OAuth2 token (MSAL)
2. Resolve site URL → site ID → drive ID (Graph API)
3. Download existing CSV (returns `None` on 404)
4. Append new row (column-safe merge)
5. PUT updated CSV back to SharePoint

#### Bulk incremental (`upload_incremental`)

Triggered manually via the **"Upload to SharePoint"** button on the data grid.

| Mode | When triggered | What happens |
|---|---|---|
| **Seed** | First upload (`last_uploaded_at` is `NULL`) or `force=True` | Fetches ALL rows, builds fresh CSV, replaces file in SharePoint |
| **Incremental** | Subsequent uploads | Fetches only rows with `created_at > last_uploaded_at`, downloads existing CSV, appends new rows, re-uploads |
| **No new rows** | Incremental but nothing new | Returns immediately, no network call to SharePoint |

After a successful seed or incremental upload, `sharepoint_last_uploaded_at` is updated to the current UTC time (serves as the watermark for the next run).

### Column safety

If a new row contains columns not present in the existing CSV, those columns are appended to the right of the existing header. If the existing CSV has columns the new row doesn't, they are written as empty strings.

### Required Azure permissions

`Files.ReadWrite.All` (Application permission, admin consent required)

Alternatively: `Sites.ReadWrite.All`

### `SharePointExporter` API

```python
from superset_data_entry.sharepoint import SharePointExporter

exporter = SharePointExporter()

# Append one row (called per-submission)
exporter.upload_row(form_config, row_data_dict)

# Bulk upload (seed or incremental)
rows_uploaded, mode = exporter.upload_incremental(form_config, engine, force=False)
# mode: "seed" | "incremental" | "no_new_rows"
```

### Error handling

`upload_row` and `upload_incremental` both raise on failure. In `views.py`, `upload_row` is caught silently so a SharePoint outage never prevents the database insert from succeeding. `upload_incremental` errors are caught and returned as `500` JSON to the browser.

### Dependencies

```
msal>=1.20.0
requests>=2.28.0
```

Both are listed in `requirements.txt` and `setup.py`. Install with:
```bash
pip install msal requests
```

---

## 11. Data Access Layer

### `FormConfigDAO`

| Method | Description |
|---|---|
| `get_all(session)` | All form configs (no filter) |
| `get_all_active(session)` | All active forms (no user filter) |
| `get_all_active_for_user(session, user)` | Active forms where user is owner or has allowed role |
| `get_by_id(session, form_id)` | Single form by ID |
| `get_by_name(session, name)` | First form matching name |
| `ensure_unique_table_name(session, base_name)` | Returns unique table name (adds `_2`, `_3`, ... suffix) |
| `create(session, data, created_by)` | Create form + fields |
| `update(session, form_id, data)` | Update form fields (including SP credentials) |
| `delete(session, form_id)` | Delete form config (does not drop data table) |

**SharePoint secret update rule:** `update()` only overwrites `sharepoint_client_secret` if a non-empty value is sent in the payload. Sending `{"sharepoint_client_secret": ""}` leaves the existing secret unchanged.

### `FormFieldDAO`

| Method | Description |
|---|---|
| `get_by_form_id(session, form_id)` | All fields for a form, ordered by `field_order` |
| `create(session, form_id, data)` | Create a field |
| `update(session, field_id, data)` | Update a field |
| `delete(session, field_id)` | Delete a field |

### `DataEntryDAO`

Operates on dynamic per-form tables using raw SQL (no SQLAlchemy ORM). All table and column identifiers are passed through `pg_ident()` (double-quote escaping) to prevent SQL injection.

| Method | Description |
|---|---|
| `get_all(engine, table_name, page, per_page)` | Paginated records, newest first. Returns `(records, total)` |
| `get_all_for_export(engine, table_name, max_records)` | All records for export, oldest first. Capped at 50,000 |
| `get_rows_since(engine, table_name, since_dt, max_records)` | Records with `created_at > since_dt`, oldest first. Used by SharePoint incremental upload |
| `get_by_id(engine, table_name, record_id)` | Single record dict or `None` |
| `insert(engine, table_name, data, username)` | Insert + add `created_by`/`created_at`/`updated_at`. Returns new `id` |
| `update(engine, table_name, record_id, data, username)` | Update + set `updated_at`. Returns `True` if row was found |
| `delete(engine, table_name, record_id)` | Delete by ID. Returns `True` if row was found |
| `search(engine, table_name, filters, page, per_page)` | Filter by column equality. Returns `(records, total)` |

---

## 12. Table Manager

`TableManager` creates and modifies PostgreSQL tables from form configurations.

### Field type → PostgreSQL mapping

| `field_type` | PostgreSQL |
|---|---|
| `text` | `VARCHAR(255)` |
| `textarea` | `TEXT` |
| `number`, `decimal` | `NUMERIC(10,2)` |
| `integer` | `INTEGER` |
| `date` | `DATE` |
| `datetime` | `TIMESTAMP` |
| `time` | `TIME` |
| `boolean`, `checkbox` | `BOOLEAN` |
| `select` | `VARCHAR(100)` |

### Key methods

```python
TableManager.create_table_from_config(form_config, engine)
# Creates the physical table + created_at index. Raises ValueError if table exists.

TableManager.table_exists(table_name, engine)
# True/False check.

TableManager.migrate_schema(form_config, engine)
# Adds columns for any form fields that don't have a corresponding column yet (ALTER TABLE ADD COLUMN).
# Idempotent — columns that already exist are skipped.

TableManager.get_schema_hash(form_config)
# Returns an MD5 hash of the current field schema — used to detect if a migration is needed.
```

---

## 13. Frontend Assets

Static files are served via a Flask blueprint at `/data-entry-plugin/static/`.

> **CSP Note:** Superset's Content Security Policy blocks inline `style="..."` attributes and inline `<script>` tags. All styles use external CSS classes and all JS is served from the static blueprint.

### Files

| File | Purpose |
|---|---|
| `data_entry_plugin.css` | Plugin-wide styles. Includes `.de-sp-hidden { display: none !important; }` for SharePoint field toggle |
| `data_entry.js` | Form submission logic, field validation feedback, dynamic field rendering |
| `data_grid.js` | Data grid: delete handler, SharePoint upload handler (`doSharePointUpload`) |
| `form_builder.js` | Form builder: field add/remove/reorder, SharePoint credential toggle, save payload |

### Templates

All templates extend `data_entry/minimal_base.html` which is a minimal wrapper around Superset's base template (no heavy Superset sidebar).

| Template | Route |
|---|---|
| `form_list.html` | `/data-entry/forms/list/` |
| `form_builder.html` | `/data-entry/builder/` |
| `data_entry.html` | `/data-entry/entry/<id>` |
| `data_grid.html` | `/data-entry/data/<id>` |
| `error.html` | Error fallback |

### SharePoint UI (data_grid.html)

The SharePoint button group is conditional:
```jinja
{% if form_config.sharepoint_enabled %}
  <!-- Seed Upload / Upload New Entries button -->
  <!-- Force Full Re-upload button (admin only, shown after first seed) -->
  <!-- Last uploaded / Never uploaded badge -->
{% endif %}
```

Button labels change automatically:
- `sharepoint_last_uploaded_at` is `NULL` → **"Seed Upload to SharePoint"**
- `sharepoint_last_uploaded_at` is set → **"Upload New Entries to SharePoint"**

### SharePoint UI (form_builder.html)

```html
<input type="checkbox" id="sharepointEnabled">  <!-- toggles #sharepointFields -->
<div id="sharepointFields" class="de-sp-hidden">
  <!-- 5 credential inputs -->
</div>
```

On page load, `updateSpFields()` in `form_builder.js` runs immediately to handle forms where SP is already enabled (so fields start visible rather than hidden).

---

## 14. Configuration Reference

All configuration lives in Superset's `superset_config.py`. The plugin reads only `SQLALCHEMY_DATABASE_URI` (no other config keys required).

### Minimal config

```python
# superset_config.py

import os

SQLALCHEMY_DATABASE_URI = "postgresql://user:pass@host:5432/superset_db"

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

### `superset_init_plugin.py`

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
        logger.error("❌ Data Entry Plugin failed: %s", e)
```

---

## 15. Custom Validators

Register named validators in `superset_init_plugin.py` (or any module loaded at startup) **after** `register_plugin()`:

```python
from superset_data_entry.validation import ValidationEngine

# Validator function receives the raw field value; return True = valid
ValidationEngine.register_validator(
    'validate_shift_duration',
    lambda v: 1 <= float(v) <= 24
)

ValidationEngine.register_validator(
    'validate_grace_period',
    lambda v: 0 <= int(v) <= 60
)

ValidationEngine.register_validator(
    'validate_vessel_name',
    lambda v: bool(re.match(r'^[A-Z]{2,4}-\d{3,6}$', str(v)))
)
```

Reference them in a field's `validation_rules`:
```json
{
  "custom_validator": "validate_shift_duration",
  "error_messages": {
    "custom": "Shift must be between 1 and 24 hours"
  }
}
```

Validators are global (shared across all forms in the instance). If a referenced validator name is not registered, a warning is logged and the field passes validation.

---

## 16. Security Notes

| Topic | Detail |
|---|---|
| **SQL injection** | All dynamic table/column names are escaped with `pg_ident()` (double-quote wrapping). All values use SQLAlchemy parameterised queries (`:param` style). |
| **CSP** | No inline scripts or styles. All JS served via blueprint; all styles use external CSS classes. |
| **SharePoint secret** | Stored as plain text in `form_configurations.sharepoint_client_secret`. The column is intentionally excluded from `to_dict()` serialisation — the API never exposes it. Encrypt at the database level if required by your security policy. |
| **Access control** | Role checks use `sm.get_user_roles()` — the official FAB API. Falls back to `user.roles` direct access if the SM call fails. |
| **Form access** | Role name comparison is case-insensitive (both sides lowercased before comparison). |
| **CSRF** | All `POST` endpoints are within Superset's CSRF protection via `@has_access`. The SharePoint upload endpoint uses `_require_login()` + `can_access_form_list_and_submit()` checks before any action. |
| **Error exposure** | Internal errors are logged server-side; the client receives only `"An internal server error occurred"` (no stack traces or DB details). |

---

## 17. File Reference

```
superset_data_entry/
│
├── __init__.py              Plugin entry point, SupersetDataEntryPlugin class,
│                            register_plugin(), __version__
│
├── api.py                   REST API blueprint (/data-entry-api/)
│                            All JSON endpoints for forms and data entries
│
├── views.py                 Flask-AppBuilder views (Web UI)
│                            FormListView, FormBuilderView, DataEntryView,
│                            DataGridView, permission helpers
│
├── models.py                SQLAlchemy models: FormConfiguration, FormField
│
├── dao.py                   Data Access Objects: FormConfigDAO, FormFieldDAO,
│                            DataEntryDAO (dynamic table operations)
│
├── sharepoint.py            SharePointExporter class
│                            upload_row(), upload_incremental(), CSV helpers
│
├── validation.py            ValidationEngine with pluggable custom validators
│
├── table_manager.py         Dynamic PostgreSQL table creation and schema migration
│
├── form_access.py           Form-level access control helpers
│                            user_can_enter_data_for_form(), user_is_form_owner()
│
├── migrations_runner.py     Auto-run SQL migrations from migrations/ on startup
│
├── setup_cli.py             superset-data-entry-setup CLI tool
│
├── migrations/
│   ├── DE_V6__create_form_configurations_table.sql
│   ├── DE_V7__create_form_fields_table.sql
│   ├── DE_V8__add_allowed_role_names_to_form_configurations.sql
│   ├── DE_V9__allow_duplicate_form_names_unique_table_name.sql
│   ├── DE_V10__add_sharepoint_config.sql
│   └── DE_V11__add_sharepoint_last_uploaded_at.sql
│
├── static/
│   ├── data_entry_plugin.css   Global styles (.de-sp-hidden, layout)
│   ├── data_entry.js           Form submission + field rendering
│   ├── data_grid.js            Data grid + SharePoint upload handler
│   └── form_builder.js         Form builder + SP credential toggle
│
└── templates/
    └── data_entry/
        ├── minimal_base.html   Lightweight Superset base wrapper
        ├── form_list.html      Form list page
        ├── form_builder.html   Form create/edit page
        ├── data_entry.html     Data submission form
        ├── data_grid.html      Data grid with pagination + SP buttons
        └── error.html          Error fallback page
```
