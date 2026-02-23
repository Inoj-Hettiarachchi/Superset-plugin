"""
Flask-AppBuilder views for data entry plugin
Provides web UI for form management and data entry
"""
from flask_appbuilder import BaseView, expose, has_access
from flask import render_template, request, jsonify, flash, redirect, url_for, Response
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json
import logging
import os

from .dao import FormConfigDAO, FormFieldDAO, DataEntryDAO
from .validation import ValidationEngine
from .table_manager import TableManager

logger = logging.getLogger(__name__)

# Get the template folder path for this plugin
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FOLDER = os.path.join(PLUGIN_DIR, 'templates')


def get_db_session():
    """Get database session and shared engine from Flask app context"""
    from flask import current_app
    engine = current_app.config['DATA_ENTRY_ENGINE']
    Session = sessionmaker(bind=engine)
    return Session(), engine


def is_admin():
    """Check if current user has admin role"""
    from flask import g
    return any(role.name == 'Admin' for role in g.user.roles)


class FormListView(BaseView):
    """
    View to list all data entry forms
    Main landing page for the plugin
    """
    base_template = "data_entry/minimal_base.html"
    route_base = "/data-entry/forms"
    default_view = "list"
    
    @expose('/list/')
    @has_access
    def list(self):
        """Show list of all active forms"""
        session = None
        try:
            session, engine = get_db_session()
            forms = FormConfigDAO.get_all_active(session)
            
            return self.render_template(
                'data_entry/form_list.html',
                forms=forms,
                is_admin=is_admin()
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
    View for building and editing forms
    Admin only
    """
    base_template = "data_entry/minimal_base.html"
    route_base = "/data-entry/builder"
    default_view = "build"
    
    @expose('/')
    @expose('/<int:form_id>')
    @has_access
    def build(self, form_id=None):
        """Form builder interface"""
        # Check admin permission
        if not is_admin():
            flash("Admin access required", "danger")
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
            
            return self.render_template(
                'data_entry/form_builder.html',
                form_config=form_config
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
        """Save form configuration with fields"""
        if not is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        
        session = None
        try:
            from flask import g
            data = request.json
            session, engine = get_db_session()
            
            # Extract fields from request
            fields_data = data.pop('fields', [])
            
            if 'id' in data and data['id']:
                # Update existing form
                form = FormConfigDAO.update(session, data['id'], data)
                message = "Form updated successfully"
                
                # Delete existing fields and recreate (simple approach)
                for field in form.fields:
                    session.delete(field)
                session.commit()
            else:
                # Create new form
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
    View for entering data via forms
    """
    base_template = "data_entry/minimal_base.html"
    route_base = "/data-entry/entry"
    default_view = "entry"
    
    @expose('/<int:form_id>')
    @has_access
    def entry(self, form_id):
        """Data entry form"""
        session = None
        try:
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            
            if not form_config or not form_config.is_active:
                flash("Form not found or inactive", "danger")
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
    @has_access
    def submit(self, form_id):
        """Submit form data"""
        session = None
        try:
            from flask import g
            session, engine = get_db_session()
            
            form_config = FormConfigDAO.get_by_id(session, form_id)
            if not form_config or not form_config.is_active:
                return jsonify({'error': 'Form not found or inactive'}), 404
            
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
    View for viewing submitted data in table format
    """
    base_template = "data_entry/minimal_base.html"
    route_base = "/data-entry/data"
    default_view = "grid"
    
    @expose('/<int:form_id>')
    @has_access
    def grid(self, form_id):
        """Data grid view"""
        session = None
        try:
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            
            if not form_config:
                flash("Form not found", "danger")
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
                is_admin=is_admin()
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
        """Download form data as a JSON seed file."""
        session = None
        try:
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            if not form_config:
                flash("Form not found", "danger")
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

    @expose('/<int:form_id>/delete/<int:record_id>', methods=['POST'])
    @has_access
    def delete(self, form_id, record_id):
        """Delete a record"""
        session = None
        try:
            session, engine = get_db_session()
            form_config = FormConfigDAO.get_by_id(session, form_id)
            
            if not form_config:
                return jsonify({'error': 'Form not found'}), 404
            
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
