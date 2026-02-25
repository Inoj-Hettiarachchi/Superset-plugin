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
    """Return list of role names for the user (from FAB/Superset user.roles)."""
    if not user:
        return []
    roles = getattr(user, "roles", None)
    if roles is None:
        return []
    # Force evaluation (e.g. lazy-loaded relationship) and collect names
    try:
        role_list = list(roles)
    except Exception:
        role_list = []
    return [str(getattr(r, "name", "") or "").strip() for r in role_list if getattr(r, "name", None)]


def _normalize_role_set(role_list: Any) -> set:
    """Normalize role names to lowercase for comparison; return set of non-empty strings."""
    if not role_list:
        return set()
    if not isinstance(role_list, list):
        role_list = list(role_list) if role_list else []
    return {str(r).strip().lower() for r in role_list if str(r).strip()}


def _user_role_names_from_db(engine, username: str) -> List[str]:
    """Load role names for username from FAB tables. Use when user.roles is not populated."""
    if not engine or not username:
        return []
    try:
        with engine.connect() as conn:
            result = conn.execute(
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


def user_can_enter_data_for_form(user: Any, form: Any, engine=None) -> bool:
    """True if user can view/enter data: owner or has a role in form's allowed_role_names."""
    if not user or not form:
        return False
    if user_is_form_owner(user, form):
        return True
    allowed = form.allowed_role_names
    if not allowed:
        return False
    role_names = _user_role_names(user)
    if not role_names:
        username = getattr(user, "username", None)
        if username and engine:
            role_names = _user_role_names_from_db(engine, username)
    user_roles = _normalize_role_set(role_names)
    form_allowed = _normalize_role_set(allowed)
    return bool(user_roles & form_allowed)


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
