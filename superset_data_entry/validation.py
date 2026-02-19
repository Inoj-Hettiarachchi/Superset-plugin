"""
Advanced validation engine for data entry forms
Supports type validation, constraints, regex patterns, and custom validators
"""
import re
from datetime import datetime, date, time
from typing import Any, Dict, List, Callable
import logging

logger = logging.getLogger(__name__)


class ValidationEngine:
    """
    Comprehensive validation engine with pluggable custom validators
    """
    
    # Registry for custom validation functions
    CUSTOM_VALIDATORS: Dict[str, Callable] = {}
    
    @classmethod
    def register_validator(cls, name: str, validator_func: Callable[[Any], bool]):
        """
        Register a custom validation function
        
        Args:
            name: Unique name for the validator
            validator_func: Function that takes a value and returns True if valid
        
        Example:
            ValidationEngine.register_validator('validate_shift_duration', lambda v: 1 <= v <= 24)
        """
        cls.CUSTOM_VALIDATORS[name] = validator_func
        logger.info(f"Registered custom validator: {name}")
    
    @classmethod
    def validate_form(cls, form_config, data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Validate entire form submission
        
        Args:
            form_config: FormConfiguration object with fields
            data: Dictionary of field values to validate
        
        Returns:
            Dictionary mapping field names to lists of error messages
        """
        errors = {}
        
        for field in form_config.fields:
            field_errors = cls.validate_field(
                value=data.get(field.field_name),
                field_config=field.to_dict()
            )
            
            if field_errors:
                errors[field.field_name] = field_errors
        
        return errors
    
    @classmethod
    def validate_field(cls, value: Any, field_config: dict) -> List[str]:
        """
        Validate a single field value against its configuration
        
        Args:
            value: The value to validate
            field_config: Dictionary with field configuration
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        field_type = field_config['field_type']
        field_label = field_config['field_label']
        rules = field_config.get('validation_rules', {})
        
        # Required field check
        if field_config.get('is_required'):
            if value is None or value == '' or (isinstance(value, str) and not value.strip()):
                errors.append(f"{field_label} is required")
                return errors  # No point checking other rules if required and empty
        
        # If optional and empty, skip other validations
        if value is None or value == '':
            return errors
        
        # Type validation
        if not cls._validate_type(value, field_type):
            errors.append(f"{field_label} must be a valid {field_type}")
            return errors  # Type mismatch, other validations won't work
        
        # Type-specific validations
        if field_type in ['text', 'textarea']:
            errors.extend(cls._validate_string(value, rules, field_label))
        
        elif field_type in ['number', 'integer', 'decimal']:
            errors.extend(cls._validate_numeric(value, rules, field_label))
        
        elif field_type == 'date':
            errors.extend(cls._validate_date(value, rules, field_label))
        
        elif field_type == 'select':
            errors.extend(cls._validate_select(value, field_config.get('options', []), field_label))
        
        # Pattern validation (regex)
        if 'pattern' in rules and isinstance(value, str):
            if not re.match(rules['pattern'], value):
                msg = rules.get('error_messages', {}).get('pattern', f'{field_label} has invalid format')
                errors.append(msg)
        
        # Custom validator
        if 'custom_validator' in rules:
            validator_name = rules['custom_validator']
            if validator_name in cls.CUSTOM_VALIDATORS:
                try:
                    if not cls.CUSTOM_VALIDATORS[validator_name](value):
                        msg = rules.get('error_messages', {}).get('custom', 
                            f'{field_label} failed validation: {validator_name}')
                        errors.append(msg)
                except Exception as e:
                    logger.error(f"Custom validator {validator_name} failed: {e}")
                    errors.append(f'{field_label} validation error')
            else:
                logger.warning(f"Custom validator {validator_name} not registered")
        
        return errors
    
    @staticmethod
    def _validate_type(value: Any, field_type: str) -> bool:
        """Validate that value matches the expected type"""
        type_validators = {
            'text': lambda v: isinstance(v, str),
            'textarea': lambda v: isinstance(v, str),
            'number': lambda v: isinstance(v, (int, float)),
            'integer': lambda v: isinstance(v, int) or (isinstance(v, float) and v.is_integer()),
            'decimal': lambda v: isinstance(v, (int, float)),
            'boolean': lambda v: isinstance(v, bool),
            'checkbox': lambda v: isinstance(v, bool),
            'date': lambda v: isinstance(v, (date, datetime, str)),
            'datetime': lambda v: isinstance(v, (datetime, str)),
            'time': lambda v: isinstance(v, (time, str)),
            'select': lambda v: True,  # Any value is acceptable for select
        }
        
        validator = type_validators.get(field_type, lambda v: True)
        return validator(value)
    
    @staticmethod
    def _validate_string(value: str, rules: dict, label: str) -> List[str]:
        """Validate string length constraints"""
        errors = []
        
        if 'min_length' in rules and len(value) < rules['min_length']:
            msg = rules.get('error_messages', {}).get('min_length',
                f"{label} must be at least {rules['min_length']} characters")
            errors.append(msg)
        
        if 'max_length' in rules and len(value) > rules['max_length']:
            msg = rules.get('error_messages', {}).get('max_length',
                f"{label} must be at most {rules['max_length']} characters")
            errors.append(msg)
        
        return errors
    
    @staticmethod
    def _validate_numeric(value: float, rules: dict, label: str) -> List[str]:
        """Validate numeric constraints"""
        errors = []
        
        if 'min_value' in rules and value < rules['min_value']:
            msg = rules.get('error_messages', {}).get('min_value',
                f"{label} must be at least {rules['min_value']}")
            errors.append(msg)
        
        if 'max_value' in rules and value > rules['max_value']:
            msg = rules.get('error_messages', {}).get('max_value',
                f"{label} must be at most {rules['max_value']}")
            errors.append(msg)
        
        return errors
    
    @staticmethod
    def _validate_date(value: Any, rules: dict, label: str) -> List[str]:
        """Validate date constraints"""
        errors = []
        
        # Parse string dates if needed
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00')).date()
            except ValueError:
                errors.append(f"{label} must be a valid date")
                return errors
        
        # Future date validation
        if rules.get('no_future_dates') and value > date.today():
            msg = rules.get('error_messages', {}).get('no_future_dates',
                f"{label} cannot be in the future")
            errors.append(msg)
        
        # Past date validation
        if rules.get('no_past_dates') and value < date.today():
            msg = rules.get('error_messages', {}).get('no_past_dates',
                f"{label} cannot be in the past")
            errors.append(msg)
        
        return errors
    
    @staticmethod
    def _validate_select(value: Any, options: List[dict], label: str) -> List[str]:
        """Validate that selected value is in options"""
        errors = []
        
        if not options:
            return errors  # No validation if no options defined
        
        valid_values = [opt.get('value') for opt in options if 'value' in opt]
        
        if value not in valid_values:
            errors.append(f"{label} must be one of the available options")
        
        return errors


# Register default custom validators for Sebastian AS use case
ValidationEngine.register_validator('validate_shift_duration', lambda v: 1 <= float(v) <= 24)
ValidationEngine.register_validator('validate_grace_period', lambda v: 0 <= int(v) <= 60)
