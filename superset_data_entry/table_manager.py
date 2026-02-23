"""
Manages dynamic table creation and schema migrations for form data storage
"""
from sqlalchemy import text, inspect
from sqlalchemy.exc import ProgrammingError
import hashlib
import json
import logging

logger = logging.getLogger(__name__)


class TableManager:
    """
    Handles creation and migration of data tables based on form configurations
    """
    
    # Mapping of form field types to PostgreSQL column types
    FIELD_TYPE_MAPPING = {
        'text': 'VARCHAR(255)',
        'textarea': 'TEXT',
        'number': 'NUMERIC(10, 2)',
        'integer': 'INTEGER',
        'decimal': 'NUMERIC(10, 2)',
        'date': 'DATE',
        'datetime': 'TIMESTAMP',
        'time': 'TIME',
        'boolean': 'BOOLEAN',
        'select': 'VARCHAR(100)',
        'checkbox': 'BOOLEAN',
    }
    
    @classmethod
    def create_table_from_config(cls, form_config, engine):
        """
        Create a new PostgreSQL table based on form configuration
        
        Args:
            form_config: FormConfiguration object with fields
            engine: SQLAlchemy engine for application database
        
        Returns:
            bool: True if successful
        
        Raises:
            ValueError: If table already exists
        """
        table_name = form_config.table_name
        
        # Check if table already exists
        if cls.table_exists(table_name, engine):
            raise ValueError(f"Table {table_name} already exists")
        
        # Build CREATE TABLE statement
        columns = []
        columns.append("id SERIAL PRIMARY KEY")
        
        # Add columns for each form field
        for field in sorted(form_config.fields, key=lambda f: f.field_order):
            column_def = cls._field_to_column_def(field)
            columns.append(column_def)
        
        # Add audit columns
        columns.append("created_by VARCHAR(255)")
        columns.append("created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        columns.append("updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        columns.append("location_id VARCHAR(100)")
        
        create_sql = f"""
            CREATE TABLE {table_name} (
                {', '.join(columns)}
            );
        """
        
        # Create indexes
        index_sql = f"""
            CREATE INDEX idx_{table_name}_created_at ON {table_name}(created_at DESC);
        """
        
        # Execute table creation
        try:
            with engine.begin() as conn:
                conn.execute(text(create_sql))
                conn.execute(text(index_sql))
            
            logger.info(f"✅ Created table: {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to create table {table_name}: {e}")
            raise
    
    @classmethod
    def _field_to_column_def(cls, field) -> str:
        """
        Convert FormField to SQL column definition
        
        Args:
            field: FormField object
        
        Returns:
            str: SQL column definition (e.g., "shift_duration_hours NUMERIC(10,2) NOT NULL")
        """
        # Get PostgreSQL type
        pg_type = cls.FIELD_TYPE_MAPPING.get(field.field_type, 'VARCHAR(255)')
        
        # Nullable constraint
        nullable = "NOT NULL" if field.is_required else "NULL"
        
        # Default value
        default = ""
        if field.default_value:
            if field.field_type in ['text', 'textarea', 'select']:
                default = f"DEFAULT '{field.default_value}'"
            elif field.field_type in ['boolean', 'checkbox']:
                default = f"DEFAULT {field.default_value.upper()}"
            elif field.field_type in ['number', 'integer', 'decimal']:
                default = f"DEFAULT {field.default_value}"
        
        return f"{field.field_name} {pg_type} {nullable} {default}".strip()
    
    @classmethod
    def table_exists(cls, table_name: str, engine) -> bool:
        """
        Check if table exists in database
        
        Args:
            table_name: Name of the table
            engine: SQLAlchemy engine
        
        Returns:
            bool: True if table exists
        """
        inspector = inspect(engine)
        return table_name in inspector.get_table_names()
    
    @classmethod
    def get_table_columns(cls, table_name: str, engine) -> list:
        """
        Get list of column names for a table
        
        Args:
            table_name: Name of the table
            engine: SQLAlchemy engine
        
        Returns:
            list: List of column names
        """
        inspector = inspect(engine)
        try:
            columns = inspector.get_columns(table_name)
            return [col['name'] for col in columns]
        except Exception as e:
            logger.error(f"Failed to get columns for {table_name}: {e}")
            return []
    
    @classmethod
    def migrate_schema(cls, form_config, engine):
        """
        Migrate table schema when form fields change
        - Adds new columns for new fields
        - Does NOT remove columns (for data safety)
        - Does NOT modify existing columns (for data safety)
        
        Args:
            form_config: FormConfiguration object with fields
            engine: SQLAlchemy engine
        
        Returns:
            bool: True if successful
        """
        table_name = form_config.table_name
        
        # If table doesn't exist, create it
        if not cls.table_exists(table_name, engine):
            logger.info(f"Table {table_name} doesn't exist, creating...")
            return cls.create_table_from_config(form_config, engine)
        
        # Get existing columns
        existing_columns = cls.get_table_columns(table_name, engine)
        
        # Find new fields that need to be added
        new_fields = [
            f for f in form_config.fields
            if f.field_name not in existing_columns
        ]
        
        if not new_fields:
            logger.info(f"✅ No schema changes needed for {table_name}")
            return True
        
        # Add new columns
        try:
            with engine.begin() as conn:
                for field in new_fields:
                    column_def = cls._field_to_column_def(field)
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_def};"
                    
                    try:
                        conn.execute(text(alter_sql))
                        logger.info(f"✅ Added column {field.field_name} to {table_name}")
                    except ProgrammingError as e:
                        logger.warning(f"⚠️  Failed to add column {field.field_name}: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Schema migration failed for {table_name}: {e}")
            raise
    
    @classmethod
    def compute_schema_hash(cls, form_config) -> str:
        """
        Compute SHA256 hash of form schema for version tracking
        
        Args:
            form_config: FormConfiguration object
        
        Returns:
            str: SHA256 hash of schema
        """
        schema_dict = {
            'table_name': form_config.table_name,
            'fields': [
                {
                    'name': f.field_name,
                    'type': f.field_type,
                    'required': f.is_required,
                    'order': f.field_order
                }
                for f in sorted(form_config.fields, key=lambda x: x.field_order)
            ]
        }
        
        schema_json = json.dumps(schema_dict, sort_keys=True)
        return hashlib.sha256(schema_json.encode()).hexdigest()
    
    @classmethod
    def drop_table(cls, table_name: str, engine):
        """
        Drop a table (use with caution!)
        Only for development or admin operations
        
        Args:
            table_name: Name of table to drop
            engine: SQLAlchemy engine
        """
        try:
            with engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE;"))
            
            logger.warning(f"⚠️  Dropped table: {table_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to drop table {table_name}: {e}")
            raise
    
    @classmethod
    def validate_table_schema(cls, form_config, engine) -> dict:
        """
        Validate that table schema matches form configuration
        
        Args:
            form_config: FormConfiguration object
            engine: SQLAlchemy engine
        
        Returns:
            dict: Validation result with 'valid' boolean and 'issues' list
        """
        table_name = form_config.table_name
        
        if not cls.table_exists(table_name, engine):
            return {
                'valid': False,
                'issues': [f"Table {table_name} does not exist"]
            }
        
        existing_columns = cls.get_table_columns(table_name, engine)
        form_field_names = [f.field_name for f in form_config.fields]
        
        issues = []
        
        # Check for missing columns
        missing_columns = [
            fname for fname in form_field_names
            if fname not in existing_columns
        ]
        
        if missing_columns:
            issues.append(f"Missing columns: {', '.join(missing_columns)}")
        
        # Check for required audit columns
        required_audit_columns = ['id', 'created_by', 'created_at', 'updated_at', 'location_id']
        missing_audit = [
            col for col in required_audit_columns
            if col not in existing_columns
        ]
        
        if missing_audit:
            issues.append(f"Missing audit columns: {', '.join(missing_audit)}")
        
        return {
            'valid': len(issues) == 0,
            'issues': issues
        }
