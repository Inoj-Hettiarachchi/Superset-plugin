"""
Form access control: creator (owner) + role allowlist.
Only the form owner can configure the form and set who can enter data.
Form list and data entry are restricted to owner or users with a role in allowed_role_names.
"""
from typing import List, Optional, Any
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)


def user_is_form_owner(user: Any, form: Any) -> bool:
    """True if the user created the form."""
    if not user or not form:
        return False
    username = getattr(user, "username", None)
    return username is not None and form.created_by == username


def _user_role_names(user: Any) -> List[str]:
    """Return list of role names for the user."""
    if not user:
        return []
    roles = getattr(user, "roles", None) or []
    return [getattr(r, "name", "") or "" for r in roles if getattr(r, "name", None)]


def user_can_enter_data_for_form(user: Any, form: Any) -> bool:
    """True if user can view/enter data: owner or has a role in form's allowed_role_names."""
    if not user or not form:
        return False
    if user_is_form_owner(user, form):
        return True
    allowed = form.allowed_role_names
    if not allowed:
        return False
    if not isinstance(allowed, list):
        allowed = list(allowed) if allowed else []
    user_roles = set(_user_role_names(user))
    return bool(user_roles & set(allowed))


def user_can_configure_form(user: Any, form: Any) -> bool:
    """True if user can edit form config and allowed roles (owner only)."""
    return user_is_form_owner(user, form)


def get_available_role_names(engine) -> List[str]:
    """Fetch all role names from Superset ab_role table for the form builder UI."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT name FROM ab_role ORDER BY name"))
            return [row[0] for row in result if row[0]]
    except Exception as e:
        logger.warning("Could not load roles from ab_role: %s", e)
        return []
