"""
Flask-AppBuilder views for data entry plugin
Provides web UI for form management and data entry

Access is controlled by a single FAB view "Data Entry" with three permissions (Security > List Permissions):
- can_configure_forms: create and configure forms (form builder)
- can_manage_data: view form list, enter data, view grid, edit/delete entries
- can_entry_only: view form list and submit entries only (no grid, no edit/delete)
Having any of these = has access to the plugin (1). None = no access (2).
"""
from flask_appbuilder import BaseView, expose, has_access
from flask import render_template, request, jsonify, flash, redirect, url_for, Response, current_app
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import csv
import io
import json
import logging
import os

from .dao import FormConfigDAO, FormFieldDAO, DataEntryDAO
from .validation import ValidationEngine
from .table_manager import TableManager
from .form_access import (
    user_can_enter_data_for_form,
    user_can_configure_form,
    get_available_role_names,
)

logger = logging.getLogger(__name__)

# Single FAB view and three permission levels (Security > List Permissions)
DATA_ENTRY_VIEW = "Data Entry"
PERM_CONFIGURE_FORMS = "can_configure_forms"   # (3) create/configure forms
PERM_MANAGE_DATA = "can_manage_data"           # (4) view data, manage entries (grid, edit, delete)
PERM_ENTRY_ONLY = "can_entry_only"             # (5) only submit entries (no grid/edit/delete)


def _sm():
    return current_app.appbuilder.sm


def can_configure_forms():
    """(3) Can create forms and configure forms."""
    try:
        return _sm().has_access(PERM_CONFIGURE_FORMS, DATA_ENTRY_VIEW)
    except Exception:
        return False


def can_manage_data():
    """(4) Can view data in forms and manage data (grid, edit, delete)."""
    try:
        return _sm().has_access(PERM_MANAGE_DATA, DATA_ENTRY_VIEW)
    except Exception:
        return False


def can_entry_only():
    """(5) Can only make data entry (submit; no grid view or edit/delete)."""
    try:
        return _sm().has_access(PERM_ENTRY_ONLY, DATA_ENTRY_VIEW)
    except Exception:
        return False


def has_plugin_access():
    """(1) Has access to the plugin (has any of the three permissions)."""
    return can_configure_forms() or can_manage_data() or can_entry_only()


def is_superset_admin():
    """True if the current user has the configured FAB admin role (default: 'Admin').

    Uses sm.auth_role_admin to read the configured admin role name, then checks
    the current user's roles via sm.get_user_roles() — avoids SQLAlchemy
    lazy-load issues and works across all FAB/Superset versions.
    """
    try:
        from flask_login import current_user
        sm = _sm()
        # auth_role_admin is the configured admin role name, e.g. "Admin"
        admin_role_name = sm.auth_role_admin
        # Prefer flask_login's current_user (always populated in a request context)
        user = current_user if (current_user and getattr(current_user, 'is_authenticated', False)) \
            else getattr(__import__('flask').g, 'user', None)
        if not user:
            return False
        try:
            # sm.get_user_roles() is the official FAB way to fetch roles
            user_roles = sm.get_user_roles(user) or []
            return any(getattr(r, 'name', '') == admin_role_name for r in user_roles)
        except Exception:
            # Last-resort fallback: direct attribute access
            roles = getattr(user, 'roles', None) or []
            return any(getattr(r, 'name', '') == admin_role_name for r in roles)
    except Exception:
        return False


def can_access_form_list_and_submit():
    """Can see form list and submit entries (4 or 5)."""
    return can_manage_data() or can_entry_only()


def can_access_grid():
    """Can view data grid and edit/delete entries (4 only)."""
    return can_manage_data()


def _require_login():
    """Redirect to login if current user is not authenticated. Return None if OK, else redirect response."""
    from flask import g
    if not getattr(g, "user", None) or not getattr(g.user, "is_authenticated", True):
        try:
            login_url = current_app.appbuilder.sm.get_url_for_login(request.url)
            return redirect(login_url or "/login")
        except Exception:
            return redirect("/login")
    return None

# Get the template folder path for this plugin
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FOLDER = os.path.join(PLUGIN_DIR, 'templates')


def get_db_session():
    """Get database session and shared engine from Flask app context"""
    from flask import current_app
    engine = current_app.config['DATA_ENTRY_ENGINE']
    Session = sessionmaker(bind=engine)
    return Session(), engine


class FormListView(BaseView):
    """
    View to list all data entry forms.
    Access: has_plugin_access (any of can_configure_forms, can_manage_data, can_entry_only).
    """
    base_template = "data_entry/minimal_base.html"
    route_base = "/data-entry/forms"
    default_view = "list"
    class_permission_name = DATA_ENTRY_VIEW
    base_permissions = [PERM_CONFIGURE_FORMS, PERM_MANAGE_DATA, PERM_ENTRY_ONLY]

    def is_accessible(self):
        return has_plugin_access()

    @expose('/list/')
    def list(self):
        """Show list of all active forms (allowed for can_manage_data or can_entry_only)."""
        r = _require_login()
        if r is not None:
            return r
        if not can_access_form_list_and_submit():
            flash("You do not have permission to view the form list", "danger")
            return redirect(url_for("FormBuilderView.build") if can_configure_forms() else "/")
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            forms = FormConfigDAO.get_all_active_for_user(session, g.user)
            return self.render_template(
                'data_entry/form_list.html',
                forms=forms,
                can_create_form=is_superset_admin(),
                can_view_data=can_access_form_list_and_submit(),
                current_username=g.user.username if g.user else None,
                is_admin=is_superset_admin(),
            )
        except Exception as e:
            logger.error(f"Error loading form list: {e}")
            flash(f"Error loading forms: {str(e)}", "danger")
            return self.render_template('data_entry/error.html', error=str(e))
        finally:
            if session:
                session.close()


class FormBuilderView(BaseView):
    """
    View for building and editing forms.
    Access: can_configure_forms (3) only.
    """
    base_template = "data_entry/minimal_base.html"
    route_base = "/data-entry/builder"
    default_view = "build"
    class_permission_name = DATA_ENTRY_VIEW
    base_permissions = [PERM_CONFIGURE_FORMS, PERM_MANAGE_DATA, PERM_ENTRY_ONLY]
    method_permission_name = {"build": "configure_forms", "save": "configure_forms"}

    def is_accessible(self):
        # Admin users always have access; also allow anyone with can_configure_forms
        # so the FAB permission system continues to work as a fallback.
        return is_superset_admin() or can_configure_forms()

    @expose('/')
    @expose('/<int:form_id>')
    @has_access
    def build(self, form_id=None):
        """Form builder interface (Admin only)."""
        from flask import g
        if not is_superset_admin():
            flash("Only administrators can create or configure forms.", "danger")
            return redirect('/data-entry/forms/list/')
        session = None
        try:
            form_config = None

            if form_id:
                session, engine = get_db_session()
                form_config = FormConfigDAO.get_by_id(session, form_id)

                if not form_config:
                    flash("Form not found", "warning")
                    return redirect('/data-entry/forms/list/')
                if not user_can_configure_form(g.user, form_config):
                    flash("Only the form owner can configure this form", "danger")
                    return redirect('/data-entry/forms/list/')

            if not session:
                session, engine = get_db_session()
            available_roles = get_available_role_names(engine)
            # Eagerly snapshot the role list into a plain Python set so Jinja2
            # never needs to touch the SQLAlchemy JSONB attribute while rendering.
            selected_roles = set(form_config.allowed_role_names or []) if form_config else set()
            return self.render_template(
                'data_entry/form_builder.html',
                form_config=form_config,
                available_roles=available_roles,
                selected_roles=selected_roles,
            )
        except Exception as e:
            logger.error(f"Error loading form builder: {e}")
            flash(f"Error: {str(e)}", "danger")
            return redirect('/data-entry/forms/list/')
        finally:
            if session:
                session.close()
    
    @expose('/save', methods=['POST'])
    @has_access
    def save(self):
        """Save form configuration with fields (Admin only)."""
        if not is_superset_admin():
            return jsonify({'error': 'Access denied. Only administrators can create or configure forms.'}), 403
        session = None
        try:
            from flask import g
            data = request.json
            session, engine = get_db_session()
            
            # Extract fields from request
            fields_data = data.pop('fields', [])
            
            if 'id' in data and data['id']:
                # Update existing form: only owner can save
                form_id = int(data['id']) if data['id'] else None
                form = FormConfigDAO.get_by_id(session, form_id)
                if not form:
                    return jsonify({'error': 'Form not found'}), 404
                if not user_can_configure_form(g.user, form):
                    return jsonify({'error': 'Only the form owner can update this form'}), 403
                # Build update payload so allowed_role_names is always included (from client)
                update_data = {
                    'title': data.get('title'),
                    'description': data.get('description'),
                    'is_active': data.get('is_active', True),
                    'allow_edit': data.get('allow_edit', True),
                    'allow_delete': data.get('allow_delete', False),
                    'allowed_role_names': data.get('allowed_role_names') if data.get('allowed_role_names') is not None else [],
                    # SharePoint export config
                    'sharepoint_enabled': data.get('sharepoint_enabled', False),
                    'sharepoint_tenant_id': data.get('sharepoint_tenant_id') or None,
                    'sharepoint_client_id': data.get('sharepoint_client_id') or None,
                    'sharepoint_client_secret': data.get('sharepoint_client_secret') or None,
                    'sharepoint_site_url': data.get('sharepoint_site_url') or None,
                    'sharepoint_folder_path': data.get('sharepoint_folder_path') or None,
                }
                if not isinstance(update_data['allowed_role_names'], list):
                    update_data['allowed_role_names'] = list(update_data['allowed_role_names']) if update_data['allowed_role_names'] else []
                form = FormConfigDAO.update(session, form_id, update_data)
                message = "Form updated successfully"
                # Diff-and-patch: update existing fields, add new ones, remove deleted ones
                form = FormConfigDAO.get_by_id(session, form_id)
                incoming_ids = {int(f['id']) for f in fields_data if f.get('id')}
                for existing_field in list(form.fields):
                    if existing_field.id not in incoming_ids:
                        session.delete(existing_field)
                session.flush()
            else:
                # Create new form – ensure allowed_role_names is a list and table_name is unique
                allowed = data.get('allowed_role_names')
                if allowed is not None and not isinstance(allowed, list):
                    data = dict(data)
                    data['allowed_role_names'] = list(allowed) if allowed else []
                else:
                    data = dict(data)
                data['table_name'] = FormConfigDAO.ensure_unique_table_name(
                    session, data.get('table_name') or (data.get('name') or 'form').replace(' ', '_')
                )
                form = FormConfigDAO.create(session, data, created_by=g.user.username)
                message = "Form created successfully"
            
            # Create/update fields
            if fields_data:
                for field_data in fields_data:
                    fid = field_data.get('id')
                    if fid:  # existing field — update in-place
                        FormFieldDAO.update(session, int(fid), field_data)
                    else:    # new field — create
                        field_data['form_id'] = form.id
                        FormFieldDAO.create(session, form.id, field_data)
                message += f" with {len(fields_data)} field(s)"
            
            # Auto-create or migrate table
            if data.get('auto_create_table', False) or fields_data:
                try:
                    # Refresh form to get fields
                    session.refresh(form)
                    
                    if not data.get('id'):
                        # New form - create table
                        TableManager.create_table_from_config(form, engine)
                        message += " and table created"
                    else:
                        # Existing form - migrate schema
                        TableManager.migrate_schema(form, engine)
                        message += " and table updated"
                except Exception as e:
                    logger.warning(f"Failed to create/update table: {e}")
                    message += " but table operation failed"
            
            return jsonify({
                'success': True,
                'message': message,
                'form_id': form.id
            })
            
        except Exception as e:
            logger.error(f"Error saving form: {e}", exc_info=True)
            return jsonify({'error': 'An internal server error occurred'}), 500
        finally:
            if session:
                session.close()


class DataEntryView(BaseView):
    """
    View for entering data via forms.
    Access: can_manage_data or can_entry_only (4 or 5).
    """
    base_template = "data_entry/minimal_base.html"
    route_base = "/data-entry/entry"
    default_view = "entry"
    class_permission_name = DATA_ENTRY_VIEW
    base_permissions = [PERM_CONFIGURE_FORMS, PERM_MANAGE_DATA, PERM_ENTRY_ONLY]

    def is_accessible(self):
        return can_access_form_list_and_submit()

    @expose('/<int:form_id>')
    def entry(self, form_id):
        """Data entry form (requires can_manage_data or can_entry_only)."""
        r = _require_login()
        if r is not None:
            return r
        if not can_access_form_list_and_submit():
            flash("Access denied", "danger")
            return redirect("/data-entry/forms/list/")
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            
            if not form_config or not form_config.is_active:
                flash("Form not found or inactive", "danger")
                return redirect('/data-entry/forms/list/')
            if not user_can_enter_data_for_form(g.user, form_config, engine):
                flash("Access denied to this form", "danger")
                return redirect('/data-entry/forms/list/')
            
            return self.render_template(
                'data_entry/data_entry.html',
                form_config=form_config
            )
        except Exception as e:
            logger.error(f"Error loading data entry form: {e}")
            flash(f"Error: {str(e)}", "danger")
            return redirect('/data-entry/forms/list/')
        finally:
            if session:
                session.close()
    
    @expose('/<int:form_id>/submit', methods=['POST'])
    def submit(self, form_id):
        """Submit form data (requires can_manage_data or can_entry_only)."""
        r = _require_login()
        if r is not None:
            return r
        if not can_access_form_list_and_submit():
            return jsonify({'error': 'Access denied'}), 403
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            
            form_config = FormConfigDAO.get_by_id(session, form_id)
            if not form_config or not form_config.is_active:
                return jsonify({'error': 'Form not found or inactive'}), 404
            if not user_can_enter_data_for_form(g.user, form_config, engine):
                return jsonify({'error': 'Access denied to this form'}), 403
            
            data = request.json
            
            # Validate
            errors = ValidationEngine.validate_form(form_config, data)
            if errors:
                return jsonify({'success': False, 'errors': errors}), 400
            
            # Save to PostgreSQL
            record_id = DataEntryDAO.insert(engine, form_config.table_name, data, g.user.username)

            # Optionally export to SharePoint (non-blocking: a SharePoint error never
            # prevents the submission from being recorded in the database)
            if form_config.sharepoint_enabled:
                try:
                    from .sharepoint import SharePointExporter
                    SharePointExporter().upload_row(form_config, data)
                except Exception as sp_err:
                    logger.error(
                        "SharePoint export failed for form %s: %s",
                        form_id, sp_err,
                        exc_info=True,
                    )

            return jsonify({
                'success': True,
                'record_id': record_id,
                'message': 'Data submitted successfully'
            })
            
        except Exception as e:
            logger.error(f"Error submitting data: {e}", exc_info=True)
            return jsonify({'error': 'An internal server error occurred'}), 500
        finally:
            if session:
                session.close()


class DataGridView(BaseView):
    """
    View for viewing submitted data in table format.
    Access: can_manage_data (4) only (no access for can_entry_only).
    """
    base_template = "data_entry/minimal_base.html"
    route_base = "/data-entry/data"
    default_view = "grid"
    class_permission_name = DATA_ENTRY_VIEW
    base_permissions = [PERM_CONFIGURE_FORMS, PERM_MANAGE_DATA, PERM_ENTRY_ONLY]
    method_permission_name = {"grid": "manage_data", "seed_download": "manage_data", "csv_download": "manage_data", "delete": "manage_data", "sharepoint_upload": "manage_data"}

    def is_accessible(self):
        # entry_only users can view data, download, and upload to SharePoint;
        # manage_data users additionally can delete records.
        return can_access_form_list_and_submit()

    @expose('/<int:form_id>')
    def grid(self, form_id):
        """Data grid view (requires can_manage_data or can_entry_only)."""
        r = _require_login()
        if r is not None:
            return r
        if not can_access_form_list_and_submit():
            flash("You do not have permission to view data", "danger")
            return redirect("/data-entry/forms/list/")
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            
            if not form_config:
                flash("Form not found", "danger")
                return redirect('/data-entry/forms/list/')
            if not user_can_enter_data_for_form(g.user, form_config, engine):
                flash("Access denied to this form", "danger")
                return redirect('/data-entry/forms/list/')
            
            # Get pagination parameters
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 25, type=int)
            
            # Get data
            records, total = DataEntryDAO.get_all(
                engine,
                form_config.table_name,
                page=page,
                per_page=per_page
            )
            
            # Calculate pagination
            total_pages = (total + per_page - 1) // per_page
            
            return self.render_template(
                'data_entry/data_grid.html',
                form_config=form_config,
                records=records,
                total=total,
                page=page,
                per_page=per_page,
                total_pages=total_pages,
                can_create_form=can_configure_forms(),
                can_delete=form_config.allow_delete and can_manage_data(),
                is_admin=is_superset_admin(),
            )
            
        except Exception as e:
            logger.error(f"Error loading data grid: {e}")
            flash(f"Error: {str(e)}", "danger")
            return redirect('/data-entry/forms/list/')
        finally:
            if session:
                session.close()

    @expose('/<int:form_id>/seed')
    def seed_download(self, form_id):
        """Download form data as a JSON seed file (requires can_manage_data or can_entry_only)."""
        r = _require_login()
        if r is not None:
            return r
        if not can_access_form_list_and_submit():
            flash("Access denied", "danger")
            return redirect(request.referrer or "/data-entry/forms/list/")
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            if not form_config:
                flash("Form not found", "danger")
                return redirect('/data-entry/forms/list/')
            if not user_can_enter_data_for_form(g.user, form_config, engine):
                flash("Access denied to this form", "danger")
                return redirect('/data-entry/forms/list/')
            records = DataEntryDAO.get_all_for_export(engine, form_config.table_name)

            def _serialize(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

            payload = {
                "form": {
                    "id": form_config.id,
                    "title": form_config.title,
                    "name": form_config.name,
                    "table_name": form_config.table_name,
                },
                "records": records,
            }
            json_str = json.dumps(payload, indent=2, default=_serialize)
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in form_config.name)
            filename = f"{safe_name}_seed.json"
            return Response(
                json_str,
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        except Exception as e:
            logger.error(f"Error generating seed file: {e}")
            flash(f"Error: {str(e)}", "danger")
            return redirect(request.referrer or '/data-entry/forms/list/')
        finally:
            if session:
                session.close()

    @expose('/<int:form_id>/csv')
    def csv_download(self, form_id):
        """Download form data as CSV (requires can_manage_data or can_entry_only)."""
        r = _require_login()
        if r is not None:
            return r
        if not can_access_form_list_and_submit():
            flash("Access denied", "danger")
            return redirect(request.referrer or "/data-entry/forms/list/")
            flash("Access denied", "danger")
            return redirect(request.referrer or "/data-entry/forms/list/")
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            if not form_config:
                flash("Form not found", "danger")
                return redirect('/data-entry/forms/list/')
            if not user_can_enter_data_for_form(g.user, form_config, engine):
                flash("Access denied to this form", "danger")
                return redirect('/data-entry/forms/list/')
            records = DataEntryDAO.get_all_for_export(engine, form_config.table_name)

            def cell_value(val):
                if val is None:
                    return ""
                if isinstance(val, datetime):
                    return val.strftime("%Y-%m-%d %H:%M:%S")
                if isinstance(val, bool):
                    return "Yes" if val else "No"
                return str(val)

            buf = io.StringIO()
            writer = csv.writer(buf)
            # Header: ID, then form fields (by label), then Created By, Created At
            fields_sorted = sorted(form_config.fields, key=lambda x: x.field_order)
            field_names = [f.field_name for f in fields_sorted]
            headers = ["ID"] + [f.field_label for f in fields_sorted] + ["Created By", "Created At"]
            writer.writerow(headers)

            for rec in records:
                row = [cell_value(rec.get("id"))]
                for fn in field_names:
                    row.append(cell_value(rec.get(fn)))
                row.append(cell_value(rec.get("created_by")))
                row.append(cell_value(rec.get("created_at")))
                writer.writerow(row)

            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in form_config.name)
            filename = f"{safe_name}.csv"
            output = buf.getvalue()
            # UTF-8 BOM for Excel
            bom = "\ufeff"
            return Response(
                bom + output,
                mimetype="text/csv; charset=utf-8",
                headers={"Content-Disposition": f"attachment; filename={filename}"},
            )
        except Exception as e:
            logger.error(f"Error generating CSV: {e}")
            flash(f"Error: {str(e)}", "danger")
            return redirect(request.referrer or '/data-entry/forms/list/')
        finally:
            if session:
                session.close()

    @expose('/<int:form_id>/sharepoint-upload', methods=['POST'])
    def sharepoint_upload(self, form_id):
        """Incremental (or seed) bulk upload to SharePoint.

        Accessible to can_manage_data and can_entry_only users.
        ``force=True`` in the JSON body triggers a full seed re-upload (admin only).
        """
        r = _require_login()
        if r is not None:
            return r
        if not can_access_form_list_and_submit():
            return jsonify({'error': 'Access denied'}), 403
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            if not form_config:
                return jsonify({'error': 'Form not found'}), 404
            if not user_can_enter_data_for_form(g.user, form_config, engine):
                return jsonify({'error': 'Access denied to this form'}), 403
            if not form_config.sharepoint_enabled:
                return jsonify({'error': 'SharePoint export is not enabled for this form'}), 400

            body = request.json or {}
            force = bool(body.get('force', False))

            # Only administrators can force a full re-upload (reset the watermark)
            if force and not is_superset_admin():
                return jsonify({'error': 'Only administrators can force a full re-upload'}), 403

            from .sharepoint import SharePointExporter
            rows_uploaded, mode = SharePointExporter().upload_incremental(
                form_config, engine, force=force
            )

            last_uploaded_at_str = None
            if mode != 'no_new_rows':
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                FormConfigDAO.update(session, form_id, {'sharepoint_last_uploaded_at': now})
                last_uploaded_at_str = now.isoformat()
            elif form_config.sharepoint_last_uploaded_at:
                last_uploaded_at_str = form_config.sharepoint_last_uploaded_at.isoformat()

            return jsonify({
                'success': True,
                'rows_uploaded': rows_uploaded,
                'mode': mode,
                'last_uploaded_at': last_uploaded_at_str,
            })

        except Exception as e:
            logger.error(f"Error uploading to SharePoint: {e}", exc_info=True)
            return jsonify({'error': 'An internal server error occurred'}), 500
        finally:
            if session:
                session.close()

    @expose('/<int:form_id>/delete/<int:record_id>', methods=['POST'])
    @has_access
    def delete(self, form_id, record_id):
        """Delete a record (requires can_manage_data)."""
        if not can_access_grid():
            return jsonify({'error': 'Access denied'}), 403
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            
            if not form_config:
                return jsonify({'error': 'Form not found'}), 404
            if not user_can_enter_data_for_form(g.user, form_config, engine):
                return jsonify({'error': 'Access denied to this form'}), 403
            
            if not form_config.allow_delete:
                return jsonify({'error': 'Deletion not allowed for this form'}), 403
            
            # Delete record
            success = DataEntryDAO.delete(engine, form_config.table_name, record_id)
            
            if not success:
                return jsonify({'error': 'Record not found'}), 404
            
            return jsonify({
                'success': True,
                'message': 'Record deleted successfully'
            })
            
        except Exception as e:
            logger.error(f"Error deleting record: {e}", exc_info=True)
            return jsonify({'error': 'An internal server error occurred'}), 500
        finally:
            if session:
                session.close()
