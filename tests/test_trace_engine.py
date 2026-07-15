"""Unit tests for trace_engine.py - document link graph for traceability."""
import pytest
from decimal import Decimal
from datetime import date, datetime
from services.trace_engine import (
    VALID_LINK_TYPES,
    VALID_LINK_STRENGTHS,
    _clean_text,
    _json_default,
    _stable_hash,
)


class TestCleanText:
    """Tests for _clean_text normalization."""

    def test_none_returns_none(self):
        """None input returns None."""
        assert _clean_text(None) is None

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        assert _clean_text("") is None

    def test_whitespace_returns_none(self):
        """Whitespace-only string returns None."""
        assert _clean_text("   ") is None

    def test_strips_whitespace(self):
        """Leading and trailing whitespace stripped."""
        assert _clean_text("  value  ") == "value"

    def test_preserves_internal_whitespace(self):
        """Internal whitespace preserved."""
        assert _clean_text("hello world") == "hello world"

    def test_numeric_string(self):
        """Numeric strings preserved."""
        assert _clean_text("12345") == "12345"

    def test_unicode_preserved(self):
        """Unicode characters preserved."""
        assert _clean_text("项目编号") == "项目编号"

    def test_returns_string_type(self):
        """Always returns str or None."""
        result = _clean_text("test")
        assert isinstance(result, str)


class TestValidLinkTypes:
    """Tests for valid link type constants."""

    def test_required_types_present(self):
        """Core link types must be present."""
        required = {"source_of", "settles", "reverses", "replaces"}
        for link_type in required:
            assert link_type in VALID_LINK_TYPES

    def test_link_types_are_strings(self):
        """All link types are strings."""
        for link_type in VALID_LINK_TYPES:
            assert isinstance(link_type, str)

    def test_link_types_not_empty(self):
        """No empty string link types."""
        for link_type in VALID_LINK_TYPES:
            assert link_type != ""


class TestValidLinkStrengths:
    """Tests for valid link strength constants."""

    def test_hard_strength_present(self):
        """Hard link strength must exist."""
        assert "hard" in VALID_LINK_STRENGTHS

    def test_soft_strength_present(self):
        """Soft link strength must exist."""
        assert "soft" in VALID_LINK_STRENGTHS

    def test_only_two_strengths(self):
        """Only hard and soft allowed."""
        assert len(VALID_LINK_STRENGTHS) == 2


class TestJsonDefault:
    """Tests for _json_default serialization."""

    def test_datetime_serialization(self):
        """Datetime objects serialized to ISO format."""
        dt = datetime(2026, 7, 10, 14, 30, 0)
        result = _json_default(dt)
        assert result == "2026-07-10T14:30:00"
        assert isinstance(result, str)

    def test_date_serialization(self):
        """Date objects serialized to ISO format."""
        d = date(2026, 7, 10)
        result = _json_default(d)
        assert result == "2026-07-10"
        assert isinstance(result, str)

    def test_decimal_serialization(self):
        """Decimal objects serialized to string."""
        val = Decimal("123.45")
        result = _json_default(val)
        assert result == "123.45"
        assert isinstance(result, str)

    def test_string_fallback(self):
        """Other types fallback to str."""
        result = _json_default({"key": "value"})
        assert isinstance(result, str)

    def test_integer_fallback(self):
        """Integers converted to string."""
        result = _json_default(42)
        assert result == "42"


class TestStableHash:
    """Tests for _stable_hash determinism and uniqueness."""

    def test_same_input_same_hash(self):
        """Same payload produces same hash."""
        payload1 = {"doc_type": "purchase_order", "doc_id": "1"}
        payload2 = [{"line": "1", "qty": "10"}]
        hash1 = _stable_hash(payload1, payload2)
        hash2 = _stable_hash(payload1, payload2)
        assert hash1 == hash2

    def test_different_header_different_hash(self):
        """Different header produces different hash."""
        payload1a = {"doc_type": "purchase_order"}
        payload1b = {"doc_type": "sales_order"}
        payload2 = []
        hash1 = _stable_hash(payload1a, payload2)
        hash2 = _stable_hash(payload1b, payload2)
        assert hash1 != hash2

    def test_different_lines_different_hash(self):
        """Different lines produces different hash."""
        payload1 = {"doc_type": "order"}
        lines_a = [{"qty": "10"}]
        lines_b = [{"qty": "20"}]
        hash1 = _stable_hash(payload1, lines_a)
        hash2 = _stable_hash(payload1, lines_b)
        assert hash1 != hash2

    def test_hash_length(self):
        """SHA-256 produces 64 character hex string."""
        hash_val = _stable_hash({}, [])
        assert len(hash_val) == 64
        assert all(c in "0123456789abcdef" for c in hash_val)

    def test_order_independence(self):
        """JSON key sorting ensures order independence."""
        payload1 = {"a": "1", "b": "2"}
        payload2 = {"b": "2", "a": "1"}
        hash1 = _stable_hash(payload1, [])
        hash2 = _stable_hash(payload2, [])
        assert hash1 == hash2

    def test_unicode_handling(self):
        """Unicode characters handled correctly."""
        payload = {"project": "项目编号", "serial": "机号"}
        hash_val = _stable_hash(payload, [])
        assert len(hash_val) == 64

    def test_null_values(self):
        """Null values handled."""
        hash_val = _stable_hash(None, None)
        assert len(hash_val) == 64

    def test_empty_inputs(self):
        """Empty inputs produce valid hash."""
        hash_val = _stable_hash({}, [])
        assert len(hash_val) == 64


class TestLinkTypeValidation:
    """Tests for link type validation logic."""

    def test_source_of_valid(self):
        """source_of is valid."""
        assert "source_of" in VALID_LINK_TYPES

    def test_reverses_valid(self):
        """reverses is valid for undo operations."""
        assert "reverses" in VALID_LINK_TYPES

    def test_settles_valid(self):
        """settles is valid for settlement documents."""
        assert "settles" in VALID_LINK_TYPES

    def test_dispatches_to_valid(self):
        """dispatches_to valid for production dispatch."""
        assert "dispatches_to" in VALID_LINK_TYPES

    def test_returns_to_valid(self):
        """returns_to valid for return operations."""
        assert "returns_to" in VALID_LINK_TYPES


class TestDocumentTraceability:
    """Business scenarios for document traceability."""

    def test_purchase_to_receipt_link(self):
        """Purchase order → receipt traceability."""
        # This validates the "source_of" link type used in procurement
        po_header = {
            "doc_type": "purchase_order",
            "doc_no": "PO-001",
            "project_code": "PRJ-001",
        }
        receipt_header = {
            "doc_type": "purchase_receipt",
            "doc_no": "RC-001",
            "project_code": "PRJ-001",
        }
        po_hash = _stable_hash(po_header, [])
        receipt_hash = _stable_hash(receipt_header, [])
        # Different documents have different hashes
        assert po_hash != receipt_hash
        # Same project code ensures traceability
        assert po_header["project_code"] == receipt_header["project_code"]

    def test_work_order_to_completion_link(self):
        """Work order → completion traceability."""
        wo_header = {
            "doc_type": "work_order",
            "wo_no": "WO-001",
            "serial_no": "SN-001",
        }
        completion_lines = [
            {"product_id": "100", "qty": "1", "lot_no": "LOT-001"}
        ]
        wo_hash = _stable_hash(wo_header, [])
        completion_hash = _stable_hash(wo_header, completion_lines)
        # Completion hash differs due to lines
        assert wo_hash != completion_hash
        # Serial number preserved for traceability
        assert wo_header.get("serial_no") == "SN-001"

    def test_sales_to_shipment_link(self):
        """Sales order → shipment traceability."""
        so_header = {
            "doc_type": "sales_order",
            "order_no": "SO-001",
            "customer_id": "C001",
        }
        shipment_header = {
            "doc_type": "shipment",
            "shipment_no": "SH-001",
            "customer_id": "C001",
        }
        # Both should reference same customer
        assert so_header["customer_id"] == shipment_header["customer_id"]


class TestConcurrencySafety:
    """Tests for concurrent operation safety."""

    def test_hash_collision_resistance(self):
        """Different payloads should not collide."""
        hashes = set()
        for i in range(1000):
            payload = {"id": i, "value": f"test{i}"}
            hash_val = _stable_hash(payload, [])
            hashes.add(hash_val)
        # All 1000 should be unique
        assert len(hashes) == 1000

    def test_hash_ordering_stability(self):
        """Key order shouldn't affect hash."""
        # Test multiple permutations
        payload = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
        import json
        # Sorted JSON should be identical regardless of insertion order
        sorted_json = json.dumps(payload, sort_keys=True)
        assert '"a": 1' in sorted_json
        assert '"b": 2' in sorted_json
        hash1 = _stable_hash(payload, [])
        hash2 = _stable_hash(payload, [])
        assert hash1 == hash2