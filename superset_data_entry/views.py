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
from datetime import datetime
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
                can_create_form=can_configure_forms(),
                can_view_data=can_access_grid(),
                current_username=g.user.username if g.user else None,
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
        return can_configure_forms()

    @expose('/')
    @expose('/<int:form_id>')
    @has_access
    def build(self, form_id=None):
        """Form builder interface"""
        session = None
        try:
            from flask import g
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
            return self.render_template(
                'data_entry/form_builder.html',
                form_config=form_config,
                available_roles=available_roles,
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
        """Save form configuration with fields (requires can_configure_forms)."""
        if not can_configure_forms():
            return jsonify({'error': 'Access denied'}), 403
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
                }
                if not isinstance(update_data['allowed_role_names'], list):
                    update_data['allowed_role_names'] = list(update_data['allowed_role_names']) if update_data['allowed_role_names'] else []
                form = FormConfigDAO.update(session, form_id, update_data)
                message = "Form updated successfully"
                # Delete existing fields and recreate (simple approach)
                form = FormConfigDAO.get_by_id(session, form_id)
                for field in form.fields:
                    session.delete(field)
                session.commit()
            else:
                # Create new form – ensure allowed_role_names is a list
                allowed = data.get('allowed_role_names')
                if allowed is not None and not isinstance(allowed, list):
                    data = dict(data)
                    data['allowed_role_names'] = list(allowed) if allowed else []
                form = FormConfigDAO.create(session, data, created_by=g.user.username)
                message = "Form created successfully"
            
            # Create/update fields
            if fields_data:
                for field_data in fields_data:
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
            logger.error(f"Error saving form: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500
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
            
            # Save
            record_id = DataEntryDAO.insert(engine, form_config.table_name, data, g.user.username)
            
            return jsonify({
                'success': True,
                'record_id': record_id,
                'message': 'Data submitted successfully'
            })
            
        except Exception as e:
            logger.error(f"Error submitting data: {e}")
            return jsonify({'error': str(e)}), 500
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
    method_permission_name = {"grid": "manage_data", "seed_download": "manage_data", "csv_download": "manage_data", "delete": "manage_data"}

    def is_accessible(self):
        return can_access_grid()

    @expose('/<int:form_id>')
    @has_access
    def grid(self, form_id):
        """Data grid view (requires can_manage_data)."""
        if not can_access_grid():
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
                can_create_form=can_configure_forms()
            )
            
        except Exception as e:
            logger.error(f"Error loading data grid: {e}")
            flash(f"Error: {str(e)}", "danger")
            return redirect('/data-entry/forms/list/')
        finally:
            if session:
                session.close()

    @expose('/<int:form_id>/seed')
    @has_access
    def seed_download(self, form_id):
        """Download form data as a JSON seed file (requires can_manage_data)."""
        if not can_access_grid():
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
    @has_access
    def csv_download(self, form_id):
        """Download form data as CSV (requires can_manage_data)."""
        if not can_access_grid():
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
            headers = ["ID"] + [f.field_label for f in fields_sorted] + ["Created By", "Created At", "Location ID"]
            writer.writerow(headers)

            for rec in records:
                row = [cell_value(rec.get("id"))]
                for fn in field_names:
                    row.append(cell_value(rec.get(fn)))
                row.append(cell_value(rec.get("created_by")))
                row.append(cell_value(rec.get("created_at")))
                row.append(cell_value(rec.get("location_id")))
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
            logger.error(f"Error deleting record: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            if session:
                session.close()
