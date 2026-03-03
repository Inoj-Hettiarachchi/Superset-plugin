"""
Runs plugin migrations from package-bundled SQL files.
Used automatically on plugin load when required tables are missing.

Migration history is tracked in the ``plugin_schema_migrations`` table so
each versioned file is applied exactly once, regardless of how many times
``run_migrations`` is called.
"""
import logging
import os
import re
from sqlalchemy import text

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r'^V(\d+)__.*\.sql$')


def _discover_migration_files() -> list:
    """
    Return a sorted list of migration SQL filenames found in the package's
    ``migrations/`` directory.  Files must match ``V<number>__<description>.sql``.
    Auto-discovery means new migration files are picked up without touching
    this module.
    """
    # Try importlib.resources first (Python 3.9+), fall back to filesystem.
    all_names = []
    try:
        from importlib.resources import files
        pkg = files("superset_data_entry") / "migrations"
        all_names = [entry.name for entry in pkg.iterdir()]
    except Exception:
        mig_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
        try:
            all_names = os.listdir(mig_dir)
        except OSError:
            all_names = []

    sql_files = [f for f in all_names if _VERSION_RE.match(f)]
    sql_files.sort(key=lambda f: int(_VERSION_RE.match(f).group(1)))
    return sql_files


def _ensure_tracking_table(conn) -> None:
    """Create ``plugin_schema_migrations`` if it does not already exist."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS plugin_schema_migrations (
            version    VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP   DEFAULT CURRENT_TIMESTAMP
        )
    """))


def _get_applied_migrations(conn) -> set:
    """Return the set of migration filenames already recorded as applied."""
    try:
        result = conn.execute(text("SELECT version FROM plugin_schema_migrations"))
        return {row[0] for row in result}
    except Exception:
        return set()


def _record_migration(conn, filename: str) -> None:
    """Mark a migration file as applied (idempotent via ON CONFLICT DO NOTHING)."""
    conn.execute(
        text(
            "INSERT INTO plugin_schema_migrations (version) VALUES (:v) "
            "ON CONFLICT DO NOTHING"
        ),
        {"v": filename},
    )


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
    Apply all pending versioned SQL migrations in order.

    - Idempotent: already-applied migrations are skipped (tracked in
      ``plugin_schema_migrations``).
    - Auto-discovers files matching ``V<n>__*.sql`` in the package migrations
      directory, so no hardcoded list needs to be maintained.
    """
    # Bootstrap the tracking table first (always safe to call).
    with engine.begin() as bootstrap_conn:
        _ensure_tracking_table(bootstrap_conn)

    migration_files = _discover_migration_files()
    if not migration_files:
        logger.warning("No migration files found in superset_data_entry/migrations/")
        return

    for filename in migration_files:
        # Open a fresh connection per migration so one failure doesn't
        # contaminate the next migration's connection state.
        with engine.begin() as conn:
            applied = _get_applied_migrations(conn)
            if filename in applied:
                logger.info(f"⏭️  Already applied: {filename}")
                continue

            try:
                sql = _read_migration_sql(filename)
                segments = _split_sql_statements(sql)
                statements = [
                    _strip_sql_comments(s) for s in segments
                    if _strip_sql_comments(s)
                ]
                if not statements:
                    logger.warning(f"No executable statements in {filename}; skipping")
                    _record_migration(conn, filename)
                    continue

                logger.info(f"Applying {filename} ({len(statements)} statement(s))")
                for stmt in statements:
                    conn.execute(text(stmt))
                _record_migration(conn, filename)
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
