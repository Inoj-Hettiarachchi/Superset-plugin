"""
Runs plugin migrations from package-bundled SQL files.
Used automatically on plugin load when required tables are missing.
"""
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATION_FILES = [
    "V6__create_form_configurations_table.sql",
    "V7__create_form_fields_table.sql",
]


def _read_migration_sql(filename: str) -> str:
    """Read SQL from package migrations folder."""
    try:
        from importlib.resources import files
        pkg = files("superset_data_entry")
        path = pkg / "migrations" / filename
        return path.read_text(encoding="utf-8")
    except ImportError:
        # Python 3.8: use read_text
        from importlib.resources import read_text
        return read_text("superset_data_entry.migrations", filename, encoding="utf-8")


def run_migrations(engine):
    """
    Run V6 and V7 migrations if not already applied.
    Safe to call multiple times (SQL uses IF NOT EXISTS).
    """
    for filename in MIGRATION_FILES:
        try:
            sql = _read_migration_sql(filename)
            # Execute each statement (split by semicolon, skip comments/empty)
            statements = [
                s.strip() for s in sql.split(";")
                if s.strip() and not s.strip().startswith("--")
            ]
            with engine.begin() as conn:
                for stmt in statements:
                    if stmt:
                        conn.execute(text(stmt))
            logger.info(f"✅ Migration applied: {filename}")
        except Exception as e:
            logger.error(f"❌ Migration failed {filename}: {e}")
            raise
