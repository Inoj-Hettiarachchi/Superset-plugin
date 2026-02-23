"""
Data Access Objects for form configurations and dynamic data operations
"""
from sqlalchemy import text, create_engine
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

from .models import FormConfiguration, FormField

logger = logging.getLogger(__name__)


class FormConfigDAO:
    """Data access object for form configurations"""

    @staticmethod
    def _location_filter(query, model, location_ids: Optional[List[str]]):
        """Apply location filter: None = no filter; [] = no rows; else in_(location_ids) or location_id.is_(None)."""
        if location_ids is None:
            return query
        if not location_ids:
            return query.filter(model.id == -1)
        from sqlalchemy import or_
        return query.filter(
            or_(
                model.location_id.in_(location_ids),
                model.location_id.is_(None),
            )
        )

    @staticmethod
    def get_all(session: Session, location_ids: Optional[List[str]] = None) -> List[FormConfiguration]:
        """Get all form configurations, optionally filtered by location_ids (None = no filter)."""
        q = session.query(FormConfiguration)
        q = FormConfigDAO._location_filter(q, FormConfiguration, location_ids)
        return q.all()

    @staticmethod
    def get_all_active(session: Session, location_ids: Optional[List[str]] = None) -> List[FormConfiguration]:
        """Get all active form configurations, optionally filtered by location_ids (None = no filter)."""
        q = session.query(FormConfiguration).filter(FormConfiguration.is_active == True)
        q = FormConfigDAO._location_filter(q, FormConfiguration, location_ids)
        return q.order_by(FormConfiguration.title).all()

    @staticmethod
    def get_by_id(session: Session, form_id: int, location_ids: Optional[List[str]] = None) -> Optional[FormConfiguration]:
        """Get form configuration by ID, optionally restricted by location_ids (None = no filter)."""
        q = session.query(FormConfiguration).filter(FormConfiguration.id == form_id)
        q = FormConfigDAO._location_filter(q, FormConfiguration, location_ids)
        return q.first()
    
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
            location_id=data.get('location_id'),
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
        """Update form configuration"""
        form = FormConfigDAO.get_by_id(session, form_id)
        if not form:
            return None
        
        # Update form fields
        for key in ['title', 'description', 'is_active', 'allow_edit', 'allow_delete', 'location_id']:
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
    def _location_where_clause(location_ids: Optional[List[str]]) -> Tuple[str, Dict]:
        """Return (sql_fragment, params) for location filter. Empty list -> no rows (1=0)."""
        if location_ids is None or not location_ids:
            if location_ids is not None and len(location_ids) == 0:
                return " AND 1 = 0", {}
            return "", {}

        # Use expanding bindparam: WHERE location_id IN :location_ids
        placeholders = ", ".join(f":loc_{i}" for i in range(len(location_ids)))
        params = {f"loc_{i}": loc for i, loc in enumerate(location_ids)}
        return f" AND location_id IN ({placeholders})", params

    @staticmethod
    def get_all(engine, table_name: str, page: int = 1, per_page: int = 25,
                location_ids: Optional[List[str]] = None) -> Tuple[List[Dict], int]:
        """
        Get all records from a data table with pagination.
        If location_ids is [], returns empty. If None, no location filter.
        """
        offset = (page - 1) * per_page
        loc_sql, loc_params = DataEntryDAO._location_where_clause(location_ids)

        with engine.connect() as conn:
            count_query = text(f"SELECT COUNT(*) FROM {table_name} WHERE 1=1{loc_sql}")
            total = conn.execute(count_query, loc_params).scalar()

            query = text(f"""
                SELECT * FROM {table_name}
                WHERE 1=1{loc_sql}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            params = {**loc_params, 'limit': per_page, 'offset': offset}
            result = conn.execute(query, params)
            records = [dict(row._mapping) for row in result]
            return records, total

    @staticmethod
    def get_all_for_export(engine, table_name: str, max_records: int = 50_000,
                           location_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        Get all records from a data table for export/seed (no pagination).
        If location_ids is [], returns empty. If None, no location filter.
        """
        loc_sql, loc_params = DataEntryDAO._location_where_clause(location_ids)
        with engine.connect() as conn:
            query = text(f"""
                SELECT * FROM {table_name}
                WHERE 1=1{loc_sql}
                ORDER BY id ASC
                LIMIT :limit
            """)
            result = conn.execute(query, {**loc_params, 'limit': max_records})
            return [dict(row._mapping) for row in result]

    @staticmethod
    def get_by_id(engine, table_name: str, record_id: int,
                  location_ids: Optional[List[str]] = None) -> Optional[Dict]:
        """Get a single record by ID; if location_ids provided, row's location_id must be in set."""
        loc_sql, loc_params = DataEntryDAO._location_where_clause(location_ids)
        with engine.connect() as conn:
            query = text(f"SELECT * FROM {table_name} WHERE id = :id{loc_sql}")
            result = conn.execute(query, {'id': record_id, **loc_params})
            row = result.first()
            return dict(row._mapping) if row else None
    
    @staticmethod
    def insert(engine, table_name: str, data: Dict[str, Any], username: str,
               location_id: Optional[str] = None) -> int:
        """
        Insert new record into data table.
        location_id is set from form (server-side), not from request body.
        """
        # Add audit fields
        data['created_by'] = username
        data['created_at'] = datetime.utcnow()
        data['updated_at'] = datetime.utcnow()
        if location_id is not None:
            data['location_id'] = location_id

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
    def update(engine, table_name: str, record_id: int, data: Dict[str, Any], username: str,
               location_ids: Optional[List[str]] = None) -> bool:
        """Update existing record; if location_ids provided, row's location_id must be in set."""
        data['updated_at'] = datetime.utcnow()
        set_clause = ', '.join(f"{key} = :{key}" for key in data.keys())
        loc_sql, loc_params = DataEntryDAO._location_where_clause(location_ids)

        query = text(f"""
            UPDATE {table_name}
            SET {set_clause}
            WHERE id = :record_id{loc_sql}
        """)
        data['record_id'] = record_id
        params = {**data, **loc_params}

        with engine.begin() as conn:
            result = conn.execute(query, params)
            return result.rowcount > 0

    @staticmethod
    def delete(engine, table_name: str, record_id: int,
               location_ids: Optional[List[str]] = None) -> bool:
        """Delete record; if location_ids provided, row's location_id must be in set."""
        loc_sql, loc_params = DataEntryDAO._location_where_clause(location_ids)
        query = text(f"DELETE FROM {table_name} WHERE id = :id{loc_sql}")
        with engine.begin() as conn:
            result = conn.execute(query, {'id': record_id, **loc_params})
            return result.rowcount > 0
    
    @staticmethod
    def search(engine, table_name: str, filters: Dict[str, Any], page: int = 1, per_page: int = 25,
               location_ids: Optional[List[str]] = None) -> Tuple[List[Dict], int]:
        """
        Search records with filters.
        If location_ids is [], returns empty. If None, no location filter.
        """
        offset = (page - 1) * per_page
        where_conditions = []
        params = {'limit': per_page, 'offset': offset}

        for idx, (column, value) in enumerate(filters.items()):
            param_name = f'filter_{idx}'
            where_conditions.append(f"{column} = :{param_name}")
            params[param_name] = value

        loc_sql, loc_params = DataEntryDAO._location_where_clause(location_ids)
        params.update(loc_params)
        where_clause = ' AND '.join(where_conditions) if where_conditions else '1=1'
        where_clause = where_clause + loc_sql

        with engine.connect() as conn:
            count_query = text(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}")
            total = conn.execute(count_query, params).scalar()

            query = text(f"""
                SELECT * FROM {table_name}
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """)
            result = conn.execute(query, params)
            records = [dict(row._mapping) for row in result]
            return records, total
