"""
Unit tests for superset_data_entry.utils (pg_ident helper).
"""
import pytest
from superset_data_entry.utils import pg_ident


class TestPgIdent:
    def test_simple_name(self):
        assert pg_ident("my_table") == '"my_table"'

    def test_uppercase_is_accepted(self):
        assert pg_ident("MyTable") == '"MyTable"'

    def test_underscore_prefix(self):
        assert pg_ident("_private") == '"_private"'

    def test_alphanumeric_with_digits(self):
        assert pg_ident("table_2025") == '"table_2025"'

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            pg_ident("")

    def test_none_raises(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            pg_ident(None)

    def test_hyphen_raises(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            pg_ident("bad-name")

    def test_space_raises(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            pg_ident("bad name")

    def test_semicolon_raises(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            pg_ident("drop;table")

    def test_sql_injection_attempt_raises(self):
        with pytest.raises(ValueError):
            pg_ident("users; DROP TABLE users; --")

    def test_digit_start_raises(self):
        with pytest.raises(ValueError):
            pg_ident("1bad_start")

    def test_dot_raises(self):
        with pytest.raises(ValueError):
            pg_ident("public.table")
