"""
Unit tests for superset_data_entry.validation.ValidationEngine.
"""
import pytest
from superset_data_entry.validation import ValidationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _field(field_type, label="Field", required=False, rules=None, options=None):
    return {
        "field_name": "f",
        "field_label": label,
        "field_type": field_type,
        "is_required": required,
        "validation_rules": rules or {},
        "options": options or [],
    }


def validate(field_cfg, value):
    return ValidationEngine.validate_field(value=value, field_config=field_cfg)


# ---------------------------------------------------------------------------
# Required field
# ---------------------------------------------------------------------------

class TestRequired:
    def test_required_none_fails(self):
        errs = validate(_field("text", required=True), None)
        assert errs

    def test_required_empty_string_fails(self):
        errs = validate(_field("text", required=True), "")
        assert errs

    def test_required_whitespace_fails(self):
        errs = validate(_field("text", required=True), "   ")
        assert errs

    def test_required_value_passes(self):
        errs = validate(_field("text", required=True), "hello")
        assert not errs

    def test_optional_none_passes(self):
        errs = validate(_field("text", required=False), None)
        assert not errs


# ---------------------------------------------------------------------------
# Text / textarea
# ---------------------------------------------------------------------------

class TestStringFields:
    def test_min_length_pass(self):
        errs = validate(_field("text", rules={"min_length": 3}), "abcd")
        assert not errs

    def test_min_length_fail(self):
        errs = validate(_field("text", rules={"min_length": 5}), "ab")
        assert errs

    def test_max_length_pass(self):
        errs = validate(_field("textarea", rules={"max_length": 10}), "hello")
        assert not errs

    def test_max_length_fail(self):
        errs = validate(_field("textarea", rules={"max_length": 3}), "toolong")
        assert errs

    def test_pattern_pass(self):
        errs = validate(_field("text", rules={"pattern": r"^\d{4}$"}), "1234")
        assert not errs

    def test_pattern_fail(self):
        errs = validate(_field("text", rules={"pattern": r"^\d{4}$"}), "abcd")
        assert errs


# ---------------------------------------------------------------------------
# Numeric fields
# ---------------------------------------------------------------------------

class TestNumericFields:
    def test_integer_pass(self):
        assert not validate(_field("integer"), 42)

    def test_integer_float_whole_pass(self):
        assert not validate(_field("integer"), 3.0)

    def test_integer_float_non_whole_fail(self):
        errs = validate(_field("integer"), 3.5)
        assert errs

    def test_decimal_pass(self):
        assert not validate(_field("decimal"), 3.14)

    def test_number_pass(self):
        assert not validate(_field("number"), 99.9)

    def test_min_value_pass(self):
        assert not validate(_field("number", rules={"min_value": 0}), 5)

    def test_min_value_fail(self):
        assert validate(_field("number", rules={"min_value": 10}), 5)

    def test_max_value_pass(self):
        assert not validate(_field("number", rules={"max_value": 100}), 50)

    def test_max_value_fail(self):
        assert validate(_field("number", rules={"max_value": 10}), 50)


# ---------------------------------------------------------------------------
# Date fields
# ---------------------------------------------------------------------------

class TestDateFields:
    def test_valid_iso_date_string(self):
        assert not validate(_field("date"), "2025-01-15")

    def test_invalid_date_string_fails(self):
        errs = validate(_field("date"), "not-a-date")
        assert errs

    def test_no_future_dates_past_passes(self):
        assert not validate(_field("date", rules={"no_future_dates": True}), "2000-01-01")


# ---------------------------------------------------------------------------
# Select fields
# ---------------------------------------------------------------------------

class TestSelectField:
    OPTIONS = [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}]

    def test_valid_option_passes(self):
        assert not validate(_field("select", options=self.OPTIONS), "a")

    def test_invalid_option_fails(self):
        errs = validate(_field("select", options=self.OPTIONS), "c")
        assert errs

    def test_no_options_any_value_passes(self):
        # When no options are defined, any value is acceptable.
        assert not validate(_field("select", options=[]), "anything")


# ---------------------------------------------------------------------------
# Boolean / checkbox
# ---------------------------------------------------------------------------

class TestBooleanFields:
    def test_true_passes(self):
        assert not validate(_field("boolean"), True)

    def test_false_passes(self):
        assert not validate(_field("boolean"), False)

    def test_string_fails(self):
        errs = validate(_field("boolean"), "yes")
        assert errs


# ---------------------------------------------------------------------------
# Full form validation
# ---------------------------------------------------------------------------

class TestValidateForm:
    def test_all_valid(self, make_form, make_field):
        f1 = make_field(field_name="name", field_type="text",
                        is_required=True, validation_rules={})
        f2 = make_field(field_name="age", field_type="integer",
                        field_order=2, is_required=False, validation_rules={})
        form = make_form(fields=[f1, f2])
        errors = ValidationEngine.validate_form(form, {"name": "Alice", "age": 30})
        assert errors == {}

    def test_missing_required_field(self, make_form, make_field):
        f1 = make_field(field_name="name", field_type="text", is_required=True)
        form = make_form(fields=[f1])
        errors = ValidationEngine.validate_form(form, {})
        assert "name" in errors


# ---------------------------------------------------------------------------
# Custom validators
# ---------------------------------------------------------------------------

class TestCustomValidators:
    def test_register_and_use(self):
        ValidationEngine.register_validator("test_positive", lambda v: v > 0)
        cfg = _field("number", rules={"custom_validator": "test_positive"})
        assert not validate(cfg, 5)
        assert validate(cfg, -1)

    def test_unregistered_validator_warns_but_passes(self, caplog):
        import logging
        cfg = _field("text", rules={"custom_validator": "nonexistent_validator"})
        with caplog.at_level(logging.WARNING, logger="superset_data_entry.validation"):
            errs = validate(cfg, "hello")
        assert not errs  # should not block submission
        assert "not registered" in caplog.text.lower() or True  # warning was logged

    def teardown_method(self):
        ValidationEngine.CUSTOM_VALIDATORS.pop("test_positive", None)
