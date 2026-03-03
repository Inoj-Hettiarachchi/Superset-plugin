"""
Shared pytest fixtures for the Data Entry Plugin test suite.
"""
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal form / field mocks (no DB required)
# ---------------------------------------------------------------------------

def _make_field(**kwargs):
    """Return a FormField-like mock with sensible defaults."""
    field = MagicMock()
    defaults = dict(
        id=1,
        field_name="test_field",
        field_label="Test Field",
        field_type="text",
        field_order=1,
        is_required=False,
        default_value=None,
        validation_rules={},
        options=[],
        placeholder=None,
        help_text=None,
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(field, k, v)
    field.to_dict.return_value = {k: v for k, v in defaults.items()}
    return field


def _make_form(**kwargs):
    """Return a FormConfiguration-like mock with sensible defaults."""
    form = MagicMock()
    defaults = dict(
        id=1,
        name="test_form",
        title="Test Form",
        table_name="test_form_data",
        is_active=True,
        allow_edit=True,
        allow_delete=False,
        created_by="testuser",
        allowed_role_names=[],
        fields=[],
    )
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(form, k, v)
    return form


@pytest.fixture
def mock_form():
    return _make_form()


@pytest.fixture
def mock_field():
    return _make_field()


@pytest.fixture
def make_field():
    """Factory fixture — call with keyword overrides."""
    return _make_field


@pytest.fixture
def make_form():
    """Factory fixture — call with keyword overrides."""
    return _make_form
