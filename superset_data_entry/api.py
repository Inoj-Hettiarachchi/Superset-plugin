"""
REST API endpoints for data entry plugin
Provides form management and data entry operations
"""
from flask import Blueprint, request, jsonify, g
from flask_appbuilder.security.decorators import has_access
from sqlalchemy.orm import sessionmaker
import logging

from .dao import FormConfigDAO, FormFieldDAO, DataEntryDAO
from .validation import ValidationEngine
from .table_manager import TableManager

logger = logging.getLogger(__name__)

# Create API blueprint
data_entry_api_bp = Blueprint('data_entry_api', __name__)


def get_db_session():
    """Get database session and shared engine from Flask app context"""
    from flask import current_app
    engine = current_app.config['DATA_ENTRY_ENGINE']
    Session = sessionmaker(bind=engine)
    return Session(), engine


def is_admin(user):
    """Check if user has admin role"""
    return any(role.name == 'Admin' for role in user.roles)


# =============================================================================
# Form Configuration Endpoints
# =============================================================================

@data_entry_api_bp.route('/forms', methods=['GET'])
@has_access
def list_forms():
    """
    List all active forms
    
    Returns:
        JSON array of form configurations
    """
    session = None
    try:
        session, engine = get_db_session()
        forms = FormConfigDAO.get_all_active(session)
        return jsonify([f.to_dict() for f in forms])
    except Exception as e:
        logger.error(f"Error listing forms: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@data_entry_api_bp.route('/forms/<int:form_id>', methods=['GET'])
@has_access
def get_form(form_id):
    """
    Get form configuration with fields
    
    Args:
        form_id: Form ID
    
    Returns:
        JSON object with form configuration and fields
    """
    session = None
    try:
        session, engine = get_db_session()
        form = FormConfigDAO.get_by_id(session, form_id)
        
        if not form:
            return jsonify({'error': 'Form not found'}), 404
        
        return jsonify(form.to_dict(include_fields=True))
    except Exception as e:
        logger.error(f"Error getting form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@data_entry_api_bp.route('/forms', methods=['POST'])
@has_access
def create_form():
    """
    Create new form configuration (Admin only)
    
    Request body:
        {
            "name": "vessel_shift_config",
            "title": "Vessel Shift Configuration",
            "description": "...",
            "table_name": "vessel_shift_config",
            "fields": [...]
        }
    
    Returns:
        JSON object with created form
    """
    session = None
    try:
        # Check admin permission
        if not is_admin(g.user):
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.json
        
        # Validate required fields
        required = ['name', 'title', 'table_name']
        if not all(field in data for field in required):
            return jsonify({'error': f'Missing required fields: {required}'}), 400
        
        session, engine = get_db_session()
        
        # Check if form with same name exists
        existing = FormConfigDAO.get_by_name(session, data['name'])
        if existing:
            return jsonify({'error': f'Form with name {data["name"]} already exists'}), 409
        
        # Create form
        form = FormConfigDAO.create(session, data, created_by=g.user.username)
        
        # Create table if auto_create_table is True
        if data.get('auto_create_table', False):
            try:
                TableManager.create_table_from_config(form, engine)
            except Exception as e:
                logger.warning(f"Failed to auto-create table: {e}")
        
        return jsonify(form.to_dict(include_fields=True)), 201
        
    except Exception as e:
        logger.error(f"Error creating form: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@data_entry_api_bp.route('/forms/<int:form_id>', methods=['PUT'])
@has_access
def update_form(form_id):
    """
    Update form configuration (Admin only)
    
    Args:
        form_id: Form ID
    
    Returns:
        JSON object with updated form
    """
    session = None
    try:
        if not is_admin(g.user):
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.json
        session, engine = get_db_session()
        
        form = FormConfigDAO.update(session, form_id, data)
        if not form:
            return jsonify({'error': 'Form not found'}), 404
        
        return jsonify(form.to_dict(include_fields=True))
        
    except Exception as e:
        logger.error(f"Error updating form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@data_entry_api_bp.route('/forms/<int:form_id>', methods=['DELETE'])
@has_access
def delete_form(form_id):
    """
    Delete form configuration (Admin only)
    Does NOT delete the data table
    
    Args:
        form_id: Form ID
    
    Returns:
        Success message
    """
    session = None
    try:
        if not is_admin(g.user):
            return jsonify({'error': 'Admin access required'}), 403
        
        session, engine = get_db_session()
        
        success = FormConfigDAO.delete(session, form_id)
        if not success:
            return jsonify({'error': 'Form not found'}), 404
        
        return jsonify({'success': True, 'message': 'Form deleted'})
        
    except Exception as e:
        logger.error(f"Error deleting form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


# =============================================================================
# Field Management Endpoints
# =============================================================================

@data_entry_api_bp.route('/forms/<int:form_id>/fields', methods=['POST'])
@has_access
def add_field(form_id):
    """
    Add field to form (Admin only)
    
    Args:
        form_id: Form ID
    
    Returns:
        JSON object with created field
    """
    session = None
    try:
        if not is_admin(g.user):
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.json
        session, engine = get_db_session()
        
        # Verify form exists
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form:
            return jsonify({'error': 'Form not found'}), 404
        
        # Create field
        field = FormFieldDAO.create(session, form_id, data)
        
        # Migrate table schema to add new column
        if data.get('auto_migrate', False):
            try:
                TableManager.migrate_schema(form, engine)
            except Exception as e:
                logger.warning(f"Failed to migrate schema: {e}")
        
        return jsonify(field.to_dict()), 201
        
    except Exception as e:
        logger.error(f"Error adding field to form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


# =============================================================================
# Data Entry Endpoints
# =============================================================================

@data_entry_api_bp.route('/forms/<int:form_id>/entries', methods=['GET'])
@has_access
def list_entries(form_id):
    """
    List data entries for a form
    
    Query params:
        page: Page number (default 1)
        per_page: Items per page (default 25)
    
    Returns:
        JSON object with entries and pagination info
    """
    session = None
    try:
        session, engine = get_db_session()
        
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form:
            return jsonify({'error': 'Form not found'}), 404
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        
        records, total = DataEntryDAO.get_all(engine, form.table_name, page, per_page)
        
        return jsonify({
            'entries': records,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        })
        
    except Exception as e:
        logger.error(f"Error listing entries for form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@data_entry_api_bp.route('/forms/<int:form_id>/entries', methods=['POST'])
@has_access
def submit_entry(form_id):
    """
    Submit new data entry
    
    Args:
        form_id: Form ID
    
    Request body:
        JSON object with field values
    
    Returns:
        JSON object with created record ID
    """
    session = None
    try:
        session, engine = get_db_session()
        
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form or not form.is_active:
            return jsonify({'error': 'Form not found or inactive'}), 404
        
        data = request.json
        
        # Validate data
        errors = ValidationEngine.validate_form(form, data)
        if errors:
            return jsonify({'success': False, 'errors': errors}), 400
        
        # Insert data
        record_id = DataEntryDAO.insert(engine, form.table_name, data, g.user.username)
        
        return jsonify({
            'success': True,
            'record_id': record_id,
            'message': 'Data submitted successfully'
        }), 201
        
    except Exception as e:
        logger.error(f"Error submitting entry for form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@data_entry_api_bp.route('/forms/<int:form_id>/entries/<int:record_id>', methods=['PUT'])
@has_access
def update_entry(form_id, record_id):
    """
    Update existing data entry
    
    Args:
        form_id: Form ID
        record_id: Record ID
    
    Returns:
        Success message
    """
    session = None
    try:
        session, engine = get_db_session()
        
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form:
            return jsonify({'error': 'Form not found'}), 404
        
        if not form.allow_edit:
            return jsonify({'error': 'Editing not allowed for this form'}), 403
        
        data = request.json
        
        # Validate data
        errors = ValidationEngine.validate_form(form, data)
        if errors:
            return jsonify({'success': False, 'errors': errors}), 400
        
        # Update data
        success = DataEntryDAO.update(engine, form.table_name, record_id, data, g.user.username)
        
        if not success:
            return jsonify({'error': 'Record not found'}), 404
        
        return jsonify({
            'success': True,
            'message': 'Record updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error updating entry {record_id} for form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@data_entry_api_bp.route('/forms/<int:form_id>/entries/<int:record_id>', methods=['DELETE'])
@has_access
def delete_entry(form_id, record_id):
    """
    Delete data entry
    
    Args:
        form_id: Form ID
        record_id: Record ID
    
    Returns:
        Success message
    """
    session = None
    try:
        session, engine = get_db_session()
        
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form:
            return jsonify({'error': 'Form not found'}), 404
        
        if not form.allow_delete:
            return jsonify({'error': 'Deletion not allowed for this form'}), 403
        
        # Delete data
        success = DataEntryDAO.delete(engine, form.table_name, record_id)
        
        if not success:
            return jsonify({'error': 'Record not found'}), 404
        
        return jsonify({
            'success': True,
            'message': 'Record deleted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error deleting entry {record_id} for form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


# =============================================================================
# Validation Endpoint
# =============================================================================

@data_entry_api_bp.route('/forms/<int:form_id>/validate', methods=['POST'])
@has_access
def validate_data(form_id):
    """
    Validate data without saving
    
    Args:
        form_id: Form ID
    
    Request body:
        JSON object with field values
    
    Returns:
        JSON object with validation result
    """
    session = None
    try:
        session, engine = get_db_session()
        
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form:
            return jsonify({'error': 'Form not found'}), 404
        
        data = request.json
        
        # Validate
        errors = ValidationEngine.validate_form(form, data)
        
        return jsonify({
            'valid': len(errors) == 0,
            'errors': errors
        })
        
    except Exception as e:
        logger.error(f"Error validating data for form {form_id}: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


# =============================================================================
# Health Check Endpoint
# =============================================================================

@data_entry_api_bp.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint
    
    Returns:
        JSON object with plugin status
    """
    from . import __version__
    
    return jsonify({
        'status': 'ok',
        'version': __version__,
        'plugin': 'data-entry'
    })
