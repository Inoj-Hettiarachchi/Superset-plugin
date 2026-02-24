"""
Resolve allowed location_ids for the current user for multi-tenant / RLS.
Users only see and enter data for their assigned location(s).
"""
import re
import logging
from typing import Optional, List

from sqlalchemy import text

logger = logging.getLogger(__name__)


def get_allowed_location_ids(user, engine) -> Optional[List[str]]:
    """
    Get the list of location_ids the user is allowed to access.

    - If user has Admin role, return None (no filter / all locations).
    - Else query Superset DB: ab_user_role -> rls_filter_roles -> row_level_security_filters,
      parse clause for location_id = 'x' or location_id IN ('a','b'), return unique sorted list.
    - If user has no RLS filters, return [].

    Returns:
        None: no filter (admin - can see all)
        []: no locations allowed
        ['loc1', 'loc2', ...]: only these locations
    """
    if not user or not getattr(user, 'roles', None):
        return []

    if any(getattr(r, 'name', None) == 'Admin' for r in user.roles):
        return None

    user_id = getattr(user, 'id', None)
    if user_id is None:
        return []

    try:
        query = text("""
            SELECT DISTINCT rlsf.clause
            FROM ab_user_role aur
            JOIN rls_filter_roles rfr ON aur.role_id = rfr.role_id
            JOIN row_level_security_filters rlsf ON rfr.filter_id = rlsf.id
            WHERE aur.user_id = :user_id
            AND rlsf.clause IS NOT NULL
            AND rlsf.clause != ''
        """)
        with engine.connect() as conn:
            result = conn.execute(query, {'user_id': user_id})
            rows = result.fetchall()
    except Exception as e:
        logger.warning("RLS: could not fetch filters for user %s: %s", user_id, e)
        return []

    location_ids = set()
    single_re = re.compile(r"location_id\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
    in_re = re.compile(r"location_id\s+IN\s*\(([^)]+)\)", re.IGNORECASE)

    for (clause,) in rows:
        if not clause or not isinstance(clause, str):
            continue
        for m in single_re.finditer(clause):
            location_ids.add(m.group(1).strip())
        in_m = in_re.search(clause)
        if in_m:
            inner = in_m.group(1)
            for part in re.findall(r"['\"]([^'\"]+)['\"]", inner):
                location_ids.add(part.strip())

    return sorted(location_ids) if location_ids else []


def user_can_access_location(user, engine, location_id: Optional[str]) -> bool:
    """
    Check if user can access the given location_id.
    Returns True if allowed_location_ids is None (admin) or location_id is in the list or location_id is None (global).
    """
    allowed = get_allowed_location_ids(user, engine)
    if allowed is None:
        return True
    if location_id is None:
        return True
    return location_id in allowed
