"""
Unit tests for superset_data_entry.dao (DataEntryDAO query-building logic).

These tests verify that:
- pg_ident is applied to all table / column identifiers
- the caller's data dict is never mutated by insert() or update()
- audit columns are injected automatically
"""
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime


# ---------------------------------------------------------------------------
# DataEntryDAO.insert — dict mutation guard
# ---------------------------------------------------------------------------

class TestDataEntryDAOInsert:
    def _run_insert(self, data):
        from superset_data_entry.dao import DataEntryDAO

        mock_result = MagicMock()
        mock_result.fetchone.return_value = [42]
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_ctx

        original_data = dict(data)
        record_id = DataEntryDAO.insert(mock_engine, "test_table", data, "alice")

        return record_id, data, original_data, mock_conn

    def test_returns_new_record_id(self):
        record_id, _, _, _ = self._run_insert({"field1": "value1"})
        assert record_id == 42

    def test_does_not_mutate_caller_dict(self):
        original = {"field1": "hello"}
        _, data_after, data_before, _ = self._run_insert(dict(original))
        assert data_after == original, "insert() must not mutate the caller's dict"

    def test_audit_fields_injected_in_sql(self):
        _, _, _, conn = self._run_insert({"x": 1})
        executed_sql = str(conn.execute.call_args[0][0])
        # Audit column names should appear in the INSERT statement
        assert "created_by" in executed_sql or "created_at" in executed_sql

    def test_table_name_is_quoted(self):
        _, _, _, conn = self._run_insert({"x": 1})
        executed_sql = str(conn.execute.call_args[0][0])
        assert '"test_table"' in executed_sql

    def test_unsafe_table_name_raises(self):
        from superset_data_entry.dao import DataEntryDAO
        engine = MagicMock()
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            DataEntryDAO.insert(engine, "bad-table!", {"x": 1}, "alice")


# ---------------------------------------------------------------------------
# DataEntryDAO.update — dict mutation guard
# ---------------------------------------------------------------------------

class TestDataEntryDAOUpdate:
    def _run_update(self, data):
        from superset_data_entry.dao import DataEntryDAO

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_ctx

        original_data = dict(data)
        success = DataEntryDAO.update(mock_engine, "test_table", 1, data, "alice")
        return success, data, original_data, mock_conn

    def test_returns_true_on_success(self):
        success, _, _, _ = self._run_update({"field1": "new_val"})
        assert success is True

    def test_does_not_mutate_caller_dict(self):
        original = {"field1": "new_val"}
        _, data_after, data_before, _ = self._run_update(dict(original))
        assert data_after == original, "update() must not mutate the caller's dict"

    def test_table_name_is_quoted(self):
        _, _, _, conn = self._run_update({"x": 1})
        executed_sql = str(conn.execute.call_args[0][0])
        assert '"test_table"' in executed_sql

    def test_unsafe_table_name_raises(self):
        from superset_data_entry.dao import DataEntryDAO
        engine = MagicMock()
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            DataEntryDAO.update(engine, "bad;table", 1, {"x": 1}, "alice")


# ---------------------------------------------------------------------------
# DataEntryDAO.delete
# ---------------------------------------------------------------------------

class TestDataEntryDAODelete:
    def test_returns_true_on_success(self):
        from superset_data_entry.dao import DataEntryDAO

        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_ctx

        result = DataEntryDAO.delete(mock_engine, "test_table", 99)
        assert result is True

    def test_returns_false_when_no_rows_affected(self):
        from superset_data_entry.dao import DataEntryDAO

        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.begin.return_value = mock_ctx

        result = DataEntryDAO.delete(mock_engine, "test_table", 99)
        assert result is False

    def test_unsafe_table_name_raises(self):
        from superset_data_entry.dao import DataEntryDAO
        engine = MagicMock()
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            DataEntryDAO.delete(engine, "'; DROP TABLE users; --", 1)


# ---------------------------------------------------------------------------
# DataEntryDAO.search — column injection guard
# ---------------------------------------------------------------------------

class TestDataEntryDAOSearch:
    def test_unsafe_filter_column_raises(self):
        from superset_data_entry.dao import DataEntryDAO

        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.__iter__ = MagicMock(return_value=iter([]))
        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_conn)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_ctx

        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            DataEntryDAO.search(
                mock_engine, "test_table",
                filters={"'; DROP TABLE users; --": "evil"},
            )
