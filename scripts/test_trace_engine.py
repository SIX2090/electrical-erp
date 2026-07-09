"""Unit tests for trace_engine.py - core traceability graph logic."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, date
from decimal import Decimal
from services.trace_engine import (
    VALID_LINK_TYPES,
    VALID_LINK_STRENGTHS,
    _clean_text,
    _json_default,
    _stable_hash,
    create_trace_link,
    find_upstream_recursive,
    find_downstream_recursive,
)


class MockQueryDB:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def __call__(self, sql, params=None, one=False):
        self.calls.append({"sql": sql, "params": params, "one": one})
        if one:
            return self.rows[0] if self.rows else None
        return self.rows


class MockExecuteDB:
    def __init__(self):
        self.calls = []

    def __call__(self, sql, params=None):
        self.calls.append({"sql": sql, "params": params})


class MockExecuteAndReturn:
    def __init__(self, return_value=None):
        self.return_value = return_value or {"id": 1}
        self.calls = []

    def __call__(self, sql, params=None):
        self.calls.append({"sql": sql, "params": params})
        return self.return_value


class TestCleanText:
    def test_clean_text_none(self):
        assert _clean_text(None) is None

    def test_clean_text_empty_string(self):
        assert _clean_text("") is None

    def test_clean_text_whitespace(self):
        assert _clean_text("  test  ") == "test"

    def test_clean_text_integer(self):
        assert _clean_text(123) == "123"

    def test_clean_text_float(self):
        assert _clean_text(123.45) == "123.45"


class TestJsonDefault:
    def test_json_default_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = _json_default(dt)
        assert result == "2024-01-15T10:30:45"

    def test_json_default_date(self):
        d = date(2024, 1, 15)
        result = _json_default(d)
        assert result == "2024-01-15"

    def test_json_default_decimal(self):
        result = _json_default(Decimal("123.45"))
        assert result == "123.45"

    def test_json_default_integer(self):
        result = _json_default(123)
        assert result == "123"

    def test_json_default_string(self):
        result = _json_default("test")
        assert result == "test"


class TestStableHash:
    def test_stable_hash_same_content(self):
        header1 = {"key1": "value1", "key2": 123}
        lines1 = [{"line1": "data1"}, {"line2": "data2"}]
        header2 = {"key2": 123, "key1": "value1"}
        lines2 = [{"line1": "data1"}, {"line2": "data2"}]

        hash1 = _stable_hash(header1, lines1)
        hash2 = _stable_hash(header2, lines2)

        assert hash1 == hash2

    def test_stable_hash_different_content(self):
        header1 = {"key1": "value1"}
        lines1 = [{"line1": "data1"}]
        header2 = {"key1": "value2"}
        lines2 = [{"line1": "data1"}]

        hash1 = _stable_hash(header1, lines1)
        hash2 = _stable_hash(header2, lines2)

        assert hash1 != hash2

    def test_stable_hash_empty(self):
        hash1 = _stable_hash(None, None)
        hash2 = _stable_hash({}, [])

        assert hash1 == hash2

    def test_stable_hash_with_special_chars(self):
        header = {"key": "value with 中文 and special !@#$%^&*"}
        lines = [{"line": "data with 特殊字符"}]

        result = _stable_hash(header, lines)

        assert isinstance(result, str)
        assert len(result) == 64


class TestCreateTraceLink:
    def test_create_trace_link_valid_params(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()
        execute_and_return = MockExecuteAndReturn({"id": 1})

        result = create_trace_link(
            query_db,
            execute_db,
            source_doc_type="sales_order",
            source_doc_id=1,
            target_doc_type="sales_shipment",
            target_doc_id=2,
            link_type="source_of",
            link_strength="hard",
            execute_and_return=execute_and_return,
        )

        assert result == 1
        assert len(execute_and_return.calls) == 1

    def test_create_trace_link_missing_source_doc_type(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()

        with pytest.raises(ValueError) as exc_info:
            create_trace_link(
                query_db,
                execute_db,
                source_doc_type="",
                source_doc_id=1,
                target_doc_type="sales_shipment",
                target_doc_id=2,
            )
        assert "source_doc_type and target_doc_type are required" in str(exc_info.value)

    def test_create_trace_link_missing_target_doc_type(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()

        with pytest.raises(ValueError) as exc_info:
            create_trace_link(
                query_db,
                execute_db,
                source_doc_type="sales_order",
                source_doc_id=1,
                target_doc_type=None,
                target_doc_id=2,
            )
        assert "source_doc_type and target_doc_type are required" in str(exc_info.value)

    def test_create_trace_link_missing_source_doc_id(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()

        with pytest.raises(ValueError) as exc_info:
            create_trace_link(
                query_db,
                execute_db,
                source_doc_type="sales_order",
                source_doc_id=None,
                target_doc_type="sales_shipment",
                target_doc_id=2,
            )
        assert "source_doc_id and target_doc_id are required" in str(exc_info.value)

    def test_create_trace_link_missing_target_doc_id(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()

        with pytest.raises(ValueError) as exc_info:
            create_trace_link(
                query_db,
                execute_db,
                source_doc_type="sales_order",
                source_doc_id=1,
                target_doc_type="sales_shipment",
                target_doc_id=None,
            )
        assert "source_doc_id and target_doc_id are required" in str(exc_info.value)

    def test_create_trace_link_invalid_link_type(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()

        with pytest.raises(ValueError) as exc_info:
            create_trace_link(
                query_db,
                execute_db,
                source_doc_type="sales_order",
                source_doc_id=1,
                target_doc_type="sales_shipment",
                target_doc_id=2,
                link_type="invalid_type",
            )
        assert "unsupported trace link_type" in str(exc_info.value)

    def test_create_trace_link_invalid_link_strength(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()

        with pytest.raises(ValueError) as exc_info:
            create_trace_link(
                query_db,
                execute_db,
                source_doc_type="sales_order",
                source_doc_id=1,
                target_doc_type="sales_shipment",
                target_doc_id=2,
                link_strength="invalid",
            )
        assert "unsupported trace link_strength" in str(exc_info.value)

    def test_create_trace_link_default_strength(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()
        execute_and_return = MockExecuteAndReturn({"id": 1})

        result = create_trace_link(
            query_db,
            execute_db,
            source_doc_type="sales_order",
            source_doc_id=1,
            target_doc_type="sales_shipment",
            target_doc_id=2,
            execute_and_return=execute_and_return,
        )

        assert result == 1


class TestFindUpstreamRecursive:
    def test_find_upstream_recursive_empty(self):
        query_db = MockQueryDB([])

        result = find_upstream_recursive(query_db, "sales_shipment", 1, max_depth=2)

        assert result == []

    def test_find_upstream_recursive_one_level(self):
        query_db = MockQueryDB([
            {
                "source_doc_type": "sales_order",
                "source_doc_id": 10,
                "source_doc_no": "SO-001",
                "target_doc_type": "sales_shipment",
                "target_doc_id": 1,
                "link_type": "source_of",
            }
        ])

        result = find_upstream_recursive(query_db, "sales_shipment", 1, max_depth=1)

        assert len(result) == 1
        assert result[0]["depth"] == 1
        assert result[0]["source_doc_type"] == "sales_order"
        assert result[0]["source_doc_id"] == 10
        assert result[0]["label"] == "销售订单"

    def test_find_upstream_recursive_two_levels(self):
        def query_func(sql, params):
            if params[0] == "sales_shipment" and params[1] == 1:
                return [
                    {
                        "source_doc_type": "sales_order",
                        "source_doc_id": 10,
                        "source_doc_no": "SO-001",
                        "target_doc_type": "sales_shipment",
                        "target_doc_id": 1,
                        "link_type": "source_of",
                    }
                ]
            elif params[0] == "sales_order" and params[1] == 10:
                return [
                    {
                        "source_doc_type": "quotation",
                        "source_doc_id": 100,
                        "source_doc_no": "QT-001",
                        "target_doc_type": "sales_order",
                        "target_doc_id": 10,
                        "link_type": "source_of",
                    }
                ]
            return []

        result = find_upstream_recursive(query_func, "sales_shipment", 1, max_depth=2)

        assert len(result) == 2
        depths = [r["depth"] for r in result]
        assert 1 in depths
        assert 2 in depths


class TestFindDownstreamRecursive:
    def test_find_downstream_recursive_empty(self):
        query_db = MockQueryDB([])

        result = find_downstream_recursive(query_db, "sales_order", 1, max_depth=2)

        assert result == []

    def test_find_downstream_recursive_one_level(self):
        query_db = MockQueryDB([
            {
                "source_doc_type": "sales_order",
                "source_doc_id": 1,
                "source_doc_no": "SO-001",
                "target_doc_type": "sales_shipment",
                "target_doc_id": 10,
                "link_type": "source_of",
            }
        ])

        result = find_downstream_recursive(query_db, "sales_order", 1, max_depth=1)

        assert len(result) == 1
        assert result[0]["depth"] == 1
        assert result[0]["target_doc_type"] == "sales_shipment"
        assert result[0]["target_doc_id"] == 10
        assert result[0]["label"] == "销售发货"

    def test_find_downstream_recursive_two_levels(self):
        def query_func(sql, params):
            if params[0] == "sales_order" and params[1] == 1:
                return [
                    {
                        "source_doc_type": "sales_order",
                        "source_doc_id": 1,
                        "source_doc_no": "SO-001",
                        "target_doc_type": "sales_shipment",
                        "target_doc_id": 10,
                        "link_type": "source_of",
                    }
                ]
            elif params[0] == "sales_shipment" and params[1] == 10:
                return [
                    {
                        "source_doc_type": "sales_shipment",
                        "source_doc_id": 10,
                        "source_doc_no": "SH-001",
                        "target_doc_type": "sales_invoice",
                        "target_doc_id": 100,
                        "link_type": "source_of",
                    }
                ]
            return []

        result = find_downstream_recursive(query_func, "sales_order", 1, max_depth=2)

        assert len(result) == 2
        depths = [r["depth"] for r in result]
        assert 1 in depths
        assert 2 in depths


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
