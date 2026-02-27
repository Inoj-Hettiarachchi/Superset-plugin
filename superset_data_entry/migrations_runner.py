"""
Runs plugin migrations from package-bundled SQL files.
Used automatically on plugin load when required tables are missing.
"""
import logging
import os
from sqlalchemy import text

logger = logging.getLogger(__name__)

MIGRATION_FILES = [
    "V6__create_form_configurations_table.sql",
    "V7__create_form_fields_table.sql",
    "V8__add_allowed_role_names_to_form_configurations.sql",
    "V9__allow_duplicate_form_names_unique_table_name.sql",
]


def _read_migration_sql(filename: str) -> str:
    """Read SQL from package migrations folder (importlib.resources or filesystem fallback)."""
    try:
        from importlib.resources import files
        pkg = files("superset_data_entry")
        path = pkg / "migrations" / filename
        return path.read_text(encoding="utf-8")
    except ImportError:
        try:
            from importlib.resources import read_text
            return read_text("superset_data_entry.migrations", filename, encoding="utf-8")
        except Exception:
            pass
    # Fallback: read from filesystem relative to this package (e.g. editable install)
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fallback_path = os.path.join(pkg_dir, "migrations", filename)
    if os.path.isfile(fallback_path):
        with open(fallback_path, encoding="utf-8") as f:
            return f.read()
    raise FileNotFoundError(f"Migration file not found: {filename} (tried package resources and {fallback_path})")


def _strip_sql_comments(segment: str) -> str:
    """Remove leading/trailing full-line comments and leave executable SQL."""
    lines = []
    for line in segment.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _split_sql_statements(sql: str):
    """
    Split SQL into statements by ';', but do not split on semicolons inside
    dollar-quoted strings ($$ ... $$). This allows DO $$ ... END $$; blocks.
    """
    statements = []
    current = []
    in_dollar = False
    i = 0
    n = len(sql)
    while i < n:
        if sql[i : i + 2] == "$$":
            current.append("$$")
            i += 2
            in_dollar = not in_dollar
            continue
        if not in_dollar and sql[i] == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(sql[i])
        i += 1
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def run_migrations(engine):
    """
    Run V6, V7, and V8 migrations. Safe to call multiple times (SQL uses IF NOT EXISTS).
    """
    for filename in MIGRATION_FILES:
        try:
            sql = _read_migration_sql(filename)
            # Split by semicolon, but not inside dollar-quoted $$ ... $$ (e.g. DO blocks).
            segments = _split_sql_statements(sql)
            statements = []
            for seg in segments:
                stmt = _strip_sql_comments(seg)
                if stmt:
                    statements.append(stmt)
            if not statements:
                logger.warning(f"No executable statements in {filename}; skipping")
                continue
            logger.info(f"Applying {filename} ({len(statements)} statement(s))")
            with engine.begin() as conn:
                for stmt in statements:
                    conn.execute(text(stmt))
            logger.info(f"✅ Migration applied: {filename}")
        except Exception as e:
            logger.error(f"❌ Migration failed {filename}: {e}")
            raise


def main():
    """CLI entry point: run plugin migrations using DB URI from env or --database-uri."""
    import argparse
    from sqlalchemy import create_engine

    parser = argparse.ArgumentParser(
        description="Run Data Entry Plugin migrations (form_configurations, form_fields, allowed_role_names)."
    )
    parser.add_argument(
        "--database-uri",
        "-d",
        default=None,
        help="Database URI (default: SQLALCHEMY_DATABASE_URI or SUPERSET_SQLALCHEMY_DATABASE_URI env).",
    )
    args = parser.parse_args()
    uri = args.database_uri or os.environ.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("SUPERSET_SQLALCHEMY_DATABASE_URI")
    if not uri:
        logger.error("No database URI. Set SQLALCHEMY_DATABASE_URI or SUPERSET_SQLALCHEMY_DATABASE_URI, or pass --database-uri")
        raise SystemExit(1)
    logger.info("Running migrations...")
    engine = create_engine(uri, pool_pre_ping=True)
    run_migrations(engine)
    logger.info("Done.")


if __name__ == "__main__":
    main()
