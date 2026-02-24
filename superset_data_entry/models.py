"""
SQLAlchemy models for data entry plugin
"""
from flask_appbuilder import Model
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime


class FormConfiguration(Model):
    """
    Model for storing form metadata and configuration
    """
    __tablename__ = 'form_configurations'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    table_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    allow_edit = Column(Boolean, default=True)
    allow_delete = Column(Boolean, default=False)
    created_by = Column(String(255))
    allowed_role_names = Column(JSONB, nullable=True)  # list of role names who can enter data
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    fields = relationship(
        'FormField',
        back_populates='form',
        cascade='all, delete-orphan',
        order_by='FormField.field_order'
    )
    
    def __repr__(self):
        return f'<FormConfiguration {self.name}: {self.title}>'
    
    def to_dict(self, include_fields=False):
        """Convert to dictionary for JSON serialization"""
        data = {
            'id': self.id,
            'name': self.name,
            'title': self.title,
            'description': self.description,
            'table_name': self.table_name,
            'is_active': self.is_active,
            'allow_edit': self.allow_edit,
            'allow_delete': self.allow_delete,
            'created_by': self.created_by,
            'allowed_role_names': self.allowed_role_names if self.allowed_role_names is not None else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_fields:
            data['fields'] = [field.to_dict() for field in self.fields]
        
        return data


class FormField(Model):
    """
    Model for storing individual field configurations within a form
    """
    __tablename__ = 'form_fields'
    
    id = Column(Integer, primary_key=True)
    form_id = Column(Integer, ForeignKey('form_configurations.id'), nullable=False)
    field_name = Column(String(100), nullable=False)
    field_label = Column(String(255), nullable=False)
    field_type = Column(String(50), nullable=False)
    field_order = Column(Integer, nullable=False)
    is_required = Column(Boolean, default=False)
    default_value = Column(Text)
    placeholder = Column(String(255))
    help_text = Column(Text)
    validation_rules = Column(JSONB)
    options = Column(JSONB)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    form = relationship('FormConfiguration', back_populates='fields')
    
    def __repr__(self):
        return f'<FormField {self.field_name}: {self.field_label}>'
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'form_id': self.form_id,
            'field_name': self.field_name,
            'field_label': self.field_label,
            'field_type': self.field_type,
            'field_order': self.field_order,
            'is_required': self.is_required,
            'default_value': self.default_value,
            'placeholder': self.placeholder,
            'help_text': self.help_text,
            'validation_rules': self.validation_rules or {},
            'options': self.options or [],
        }
