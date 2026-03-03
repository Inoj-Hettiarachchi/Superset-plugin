"""
Shared utility helpers for the Data Entry Plugin.
"""
import re

_IDENT_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


def pg_ident(name: str) -> str:
    """
    Validate and double-quote a PostgreSQL identifier to prevent SQL injection.

    The name must start with a letter or underscore and contain only
    alphanumeric characters and underscores.  Raises ValueError for anything
    that doesn't match so that bad data is rejected loudly rather than
    silently producing broken SQL.

    Examples::
        pg_ident("my_table")   -> '"my_table"'
        pg_ident("bad-name")   -> raises ValueError
    """
    if not _IDENT_RE.match(name or ''):
        raise ValueError(
            f"Unsafe SQL identifier {name!r}: only letters, digits and underscores "
            "are allowed and the name must not be empty."
        )
    return f'"{name}"'
