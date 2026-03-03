"""
Unit tests for superset_data_entry.table_manager.TableManager.

DDL generation is tested without a real database by inspecting the SQL
strings produced by _field_to_column_def and create_table_from_config.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from superset_data_entry.table_manager import TableManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_field(name, ftype, required=False, default=None):
    f = MagicMock()
    f.field_name = name
    f.field_type = ftype
    f.field_order = 1
    f.is_required = required
    f.default_value = default
    return f


# ---------------------------------------------------------------------------
# _field_to_column_def
# ---------------------------------------------------------------------------

class TestFieldToColumnDef:
    def test_text_nullable(self):
        col = TableManager._field_to_column_def(_make_field("note", "text"))
        assert '"note"' in col
        assert "VARCHAR(255)" in col
        assert "NULL" in col
        assert "NOT NULL" not in col

    def test_text_required(self):
        col = TableManager._field_to_column_def(_make_field("note", "text", required=True))
        assert "NOT NULL" in col

    def test_integer_type(self):
        col = TableManager._field_to_column_def(_make_field("qty", "integer"))
        assert "INTEGER" in col

    def test_decimal_type(self):
        col = TableManager._field_to_column_def(_make_field("price", "decimal"))
        assert "NUMERIC" in col

    def test_number_type(self):
        col = TableManager._field_to_column_def(_make_field("val", "number"))
        assert "NUMERIC" in col

    def test_boolean_type(self):
        col = TableManager._field_to_column_def(_make_field("flag", "boolean"))
        assert "BOOLEAN" in col

    def test_date_type(self):
        col = TableManager._field_to_column_def(_make_field("dt", "date"))
        assert "DATE" in col

    def test_datetime_type(self):
        col = TableManager._field_to_column_def(_make_field("ts", "datetime"))
        assert "TIMESTAMP" in col

    def test_unknown_type_falls_back_to_varchar(self):
        col = TableManager._field_to_column_def(_make_field("x", "unknown_type"))
        assert "VARCHAR(255)" in col

    def test_text_default_value_escaped(self):
        # Single quotes in default values must be doubled to avoid SQL injection.
        col = TableManager._field_to_column_def(
            _make_field("note", "text", default="it's ok")
        )
        assert "it''s ok" in col
        assert "DEFAULT" in col

    def test_numeric_default_value(self):
        col = TableManager._field_to_column_def(
            _make_field("qty", "integer", default="5")
        )
        assert "DEFAULT 5" in col

    def test_invalid_numeric_default_skipped(self):
        # A non-numeric default for a numeric field should be silently dropped.
        col = TableManager._field_to_column_def(
            _make_field("qty", "integer", default="not_a_number")
        )
        assert "DEFAULT" not in col

    def test_boolean_default_true(self):
        col = TableManager._field_to_column_def(
            _make_field("active", "boolean", default="true")
        )
        assert "DEFAULT TRUE" in col

    def test_boolean_default_invalid_becomes_false(self):
        col = TableManager._field_to_column_def(
            _make_field("active", "boolean", default="yes")
        )
        assert "DEFAULT FALSE" in col

    def test_identifier_is_quoted(self):
        col = TableManager._field_to_column_def(_make_field("my_field", "text"))
        assert col.startswith('"my_field"')

    def test_unsafe_identifier_raises(self):
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            TableManager._field_to_column_def(_make_field("bad-name", "text"))


# ---------------------------------------------------------------------------
# table_exists
# ---------------------------------------------------------------------------

class TestTableExists:
    def test_returns_true_when_present(self):
        engine = MagicMock()
        with patch("superset_data_entry.table_manager.inspect") as mock_inspect:
            mock_inspect.return_value.get_table_names.return_value = ["my_table"]
            assert TableManager.table_exists("my_table", engine) is True

    def test_returns_false_when_absent(self):
        engine = MagicMock()
        with patch("superset_data_entry.table_manager.inspect") as mock_inspect:
            mock_inspect.return_value.get_table_names.return_value = []
            assert TableManager.table_exists("my_table", engine) is False


# ---------------------------------------------------------------------------
# create_table_from_config
# ---------------------------------------------------------------------------

class TestCreateTableFromConfig:
    def _make_config(self, table_name="test_tbl", fields=None):
        cfg = MagicMock()
        cfg.table_name = table_name
        cfg.fields = fields or []
        return cfg

    def test_raises_if_table_already_exists(self):
        cfg = self._make_config()
        with patch.object(TableManager, "table_exists", return_value=True):
            with pytest.raises(ValueError, match="already exists"):
                TableManager.create_table_from_config(cfg, MagicMock())

    def test_create_executes_sql(self):
        cfg = self._make_config(fields=[_make_field("qty", "integer")])
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.begin.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.begin.return_value.__exit__ = MagicMock(return_value=False)

        with patch.object(TableManager, "table_exists", return_value=False):
            result = TableManager.create_table_from_config(cfg, mock_engine)

        assert result is True
        assert mock_conn.execute.called
        # Both CREATE TABLE and CREATE INDEX should be executed
        assert mock_conn.execute.call_count == 2


# ---------------------------------------------------------------------------
# compute_schema_hash
# ---------------------------------------------------------------------------

class TestComputeSchemaHash:
    def test_hash_is_deterministic(self, make_form, make_field):
        f = make_field(field_name="x", field_type="text", field_order=1)
        form = make_form(table_name="t", fields=[f])
        h1 = TableManager.compute_schema_hash(form)
        h2 = TableManager.compute_schema_hash(form)
        assert h1 == h2

    def test_different_fields_produce_different_hash(self, make_form, make_field):
        f1 = make_field(field_name="x", field_type="text", field_order=1)
        f2 = make_field(field_name="y", field_type="integer", field_order=1)
        form1 = make_form(table_name="t", fields=[f1])
        form2 = make_form(table_name="t", fields=[f2])
        assert TableManager.compute_schema_hash(form1) != TableManager.compute_schema_hash(form2)
