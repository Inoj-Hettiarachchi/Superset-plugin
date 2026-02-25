"""
Data Access Objects for form configurations and dynamic data operations
"""
from sqlalchemy import text, create_engine
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

from .models import FormConfiguration, FormField
from .form_access import _user_role_names, _normalize_role_set

logger = logging.getLogger(__name__)


def _role_names_for_username_from_db(session: Session, username: str) -> List[str]:
    """Load role names for a user from FAB tables (ab_user, ab_user_role, ab_role). Fallback when user.roles is not populated."""
    if not username:
        return []
    try:
        result = session.execute(
            text("""
                SELECT ar.name FROM ab_role ar
                INNER JOIN ab_user_role aur ON aur.role_id = ar.id
                INNER JOIN ab_user au ON au.id = aur.user_id
                WHERE au.username = :username
            """),
            {"username": username},
        )
        return [row[0] for row in result if row[0]]
    except Exception as e:
        logger.debug("Could not load roles from DB for user %s: %s", username, e)
        return []


class FormConfigDAO:
    """Data access object for form configurations"""
    
    @staticmethod
    def get_all(session: Session) -> List[FormConfiguration]:
        """Get all form configurations"""
        return session.query(FormConfiguration).all()
    
    @staticmethod
    def get_all_active(session: Session) -> List[FormConfiguration]:
        """Get all active form configurations (no user filter)."""
        return session.query(FormConfiguration).filter(
            FormConfiguration.is_active == True
        ).order_by(FormConfiguration.title).all()

    @staticmethod
    def get_all_active_for_user(session: Session, user) -> List[FormConfiguration]:
        """
        Get active forms the user can access: owner or has a role in allowed_role_names.
        """
        if not user:
            return []
        forms = session.query(FormConfiguration).filter(
            FormConfiguration.is_active == True
        ).order_by(FormConfiguration.title).all()
        username = getattr(user, "username", None)
        role_names = _user_role_names(user)
        if not role_names and username:
            role_names = _role_names_for_username_from_db(session, username)
        user_roles = _normalize_role_set(role_names)
        out = []
        for f in forms:
            if f.created_by == username:
                out.append(f)
                continue
            allowed = f.allowed_role_names or []
            form_allowed = _normalize_role_set(allowed)
            if user_roles & form_allowed:
                out.append(f)
        return out
    
    @staticmethod
    def get_by_id(session: Session, form_id: int) -> Optional[FormConfiguration]:
        """Get form configuration by ID"""
        return session.query(FormConfiguration).filter(
            FormConfiguration.id == form_id
        ).first()
    
    @staticmethod
    def get_by_name(session: Session, name: str) -> Optional[FormConfiguration]:
        """Get form configuration by name"""
        return session.query(FormConfiguration).filter(
            FormConfiguration.name == name
        ).first()
    
    @staticmethod
    def create(session: Session, data: dict, created_by: str) -> FormConfiguration:
        """Create new form configuration"""
        form = FormConfiguration(
            name=data['name'],
            title=data['title'],
            description=data.get('description'),
            table_name=data['table_name'],
            is_active=data.get('is_active', True),
            allow_edit=data.get('allow_edit', True),
            allow_delete=data.get('allow_delete', False),
            created_by=created_by,
            allowed_role_names=data.get('allowed_role_names') or [],
        )
        
        session.add(form)
        session.flush()  # Get the ID
        
        # Add fields if provided
        if 'fields' in data:
            for field_data in data['fields']:
                field = FormField(
                    form_id=form.id,
                    **field_data
                )
                session.add(field)
        
        session.commit()
        return form
    
    @staticmethod
    def update(session: Session, form_id: int, data: dict) -> Optional[FormConfiguration]:
        """Update form configuration (including allowed_role_names)."""
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form:
            return None
        # Always persist allowed_role_names when present in payload
        if 'allowed_role_names' in data:
            val = data['allowed_role_names']
            form.allowed_role_names = list(val) if isinstance(val, (list, tuple)) else ([] if val is None else [])
        for key in ['title', 'description', 'is_active', 'allow_edit', 'allow_delete']:
            if key in data:
                setattr(form, key, data[key])
        form.updated_at = datetime.utcnow()
        session.commit()
        return form
    
    @staticmethod
    def delete(session: Session, form_id: int) -> bool:
        """Delete form configuration"""
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form:
            return False
        
        session.delete(form)
        session.commit()
        return True


class FormFieldDAO:
    """Data access object for form fields"""
    
    @staticmethod
    def get_by_form_id(session: Session, form_id: int) -> List[FormField]:
        """Get all fields for a form"""
        return session.query(FormField).filter(
            FormField.form_id == form_id
        ).order_by(FormField.field_order).all()
    
    @staticmethod
    def create(session: Session, form_id: int, data: dict) -> FormField:
        """Create new form field"""
        field = FormField(
            form_id=form_id,
            field_name=data['field_name'],
            field_label=data['field_label'],
            field_type=data['field_type'],
            field_order=data['field_order'],
            is_required=data.get('is_required', False),
            default_value=data.get('default_value'),
            placeholder=data.get('placeholder'),
            help_text=data.get('help_text'),
            validation_rules=data.get('validation_rules'),
            options=data.get('options'),
        )
        
        session.add(field)
        session.commit()
        return field
    
    @staticmethod
    def update(session: Session, field_id: int, data: dict) -> Optional[FormField]:
        """Update form field"""
        field = session.query(FormField).filter(FormField.id == field_id).first()
        if not field:
            return None
        
        for key, value in data.items():
            if hasattr(field, key):
                setattr(field, key, value)
        
        field.updated_at = datetime.utcnow()
        session.commit()
        return field
    
    @staticmethod
    def delete(session: Session, field_id: int) -> bool:
        """Delete form field"""
        field = session.query(FormField).filter(FormField.id == field_id).first()
        if not field:
            return False
        
        session.delete(field)
        session.commit()
        return True


class DataEntryDAO:
    """Data access object for dynamic data table operations"""
    
    @staticmethod
    def get_all(engine, table_name: str, page: int = 1, per_page: int = 25) -> Tuple[List[Dict], int]:
        """
        Get all records from a data table with pagination
        
        Returns:
            Tuple of (records, total_count)
        """
        offset = (page - 1) * per_page
        
        with engine.connect() as conn:
            # Get total count
            count_query = text(f"SELECT COUNT(*) FROM {table_name}")
            total = conn.execute(count_query).scalar()
            
            # Get paginated records
            query = text(f"""
                SELECT * FROM {table_name}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            
            result = conn.execute(query, {'limit': per_page, 'offset': offset})
            records = [dict(row._mapping) for row in result]
            
            return records, total

    @staticmethod
    def get_all_for_export(engine, table_name: str, max_records: int = 50_000) -> List[Dict]:
        """
        Get all records from a data table for export/seed (no pagination).
        Limited to max_records to avoid excessive memory use.
        """
        with engine.connect() as conn:
            query = text(f"""
                SELECT * FROM {table_name}
                ORDER BY id ASC
                LIMIT :limit
            """)
            result = conn.execute(query, {'limit': max_records})
            return [dict(row._mapping) for row in result]
    
    @staticmethod
    def get_by_id(engine, table_name: str, record_id: int) -> Optional[Dict]:
        """Get a single record by ID"""
        with engine.connect() as conn:
            query = text(f"SELECT * FROM {table_name} WHERE id = :id")
            result = conn.execute(query, {'id': record_id})
            row = result.first()
            
            return dict(row._mapping) if row else None
    
    @staticmethod
    def insert(engine, table_name: str, data: Dict[str, Any], username: str) -> int:
        """
        Insert new record into data table
        
        Returns:
            ID of newly created record
        """
        # Add audit fields
        data['created_by'] = username
        data['created_at'] = datetime.utcnow()
        data['updated_at'] = datetime.utcnow()
        
        # Build INSERT query
        columns = ', '.join(data.keys())
        placeholders = ', '.join(f':{key}' for key in data.keys())
        
        query = text(f"""
            INSERT INTO {table_name} ({columns})
            VALUES ({placeholders})
            RETURNING id
        """)
        
        with engine.begin() as conn:
            result = conn.execute(query, data)
            return result.fetchone()[0]
    
    @staticmethod
    def update(engine, table_name: str, record_id: int, data: Dict[str, Any], username: str) -> bool:
        """Update existing record"""
        # Add audit fields
        data['updated_at'] = datetime.utcnow()
        
        # Build UPDATE query
        set_clause = ', '.join(f"{key} = :{key}" for key in data.keys())
        
        query = text(f"""
            UPDATE {table_name}
            SET {set_clause}
            WHERE id = :record_id
        """)
        
        data['record_id'] = record_id
        
        with engine.begin() as conn:
            result = conn.execute(query, data)
            return result.rowcount > 0
    
    @staticmethod
    def delete(engine, table_name: str, record_id: int) -> bool:
        """Delete record"""
        query = text(f"DELETE FROM {table_name} WHERE id = :id")
        
        with engine.begin() as conn:
            result = conn.execute(query, {'id': record_id})
            return result.rowcount > 0
    
    @staticmethod
    def search(engine, table_name: str, filters: Dict[str, Any], page: int = 1, per_page: int = 25) -> Tuple[List[Dict], int]:
        """
        Search records with filters
        
        Args:
            filters: Dictionary of column_name: value pairs
        
        Returns:
            Tuple of (records, total_count)
        """
        offset = (page - 1) * per_page
        
        # Build WHERE clause
        where_conditions = []
        params = {'limit': per_page, 'offset': offset}
        
        for idx, (column, value) in enumerate(filters.items()):
            param_name = f'filter_{idx}'
            where_conditions.append(f"{column} = :{param_name}")
            params[param_name] = value
        
        where_clause = ' AND '.join(where_conditions) if where_conditions else '1=1'
        
        with engine.connect() as conn:
            # Get total count
            count_query = text(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}")
            total = conn.execute(count_query, params).scalar()
            
            # Get records
            query = text(f"""
                SELECT * FROM {table_name}
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            
            result = conn.execute(query, params)
            records = [dict(row._mapping) for row in result]
            
            return records, total
