"""Unit tests for data_scope_service.py - core data access scope logic."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from services.data_scope_service import (
    BYPASS_ROLES,
    SUPPORTED_SCOPE_TYPES,
    normalize_role,
    can_bypass_data_scope,
    _clean,
    get_data_scope,
    scope_has_rules,
    build_scope_filter,
    row_allowed,
)


class MockQueryDB:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def __call__(self, sql, params=None):
        self.calls.append({"sql": sql, "params": params})
        return self.rows


class TestNormalizeRole:
    def test_normalize_role_none(self):
        assert normalize_role(None) == ""

    def test_normalize_role_empty(self):
        assert normalize_role("") == ""

    def test_normalize_role_whitespace(self):
        assert normalize_role("  Admin  ") == "admin"

    def test_normalize_role_mixed_case(self):
        assert normalize_role("Manager") == "manager"

    def test_normalize_role_sales(self):
        assert normalize_role("SALES") == "sales"


class TestCanBypassDataScope:
    def test_bypass_admin(self):
        assert can_bypass_data_scope("admin") is True

    def test_bypass_manager(self):
        assert can_bypass_data_scope("manager") is True

    def test_bypass_sales(self):
        assert can_bypass_data_scope("sales") is False

    def test_bypass_warehouse(self):
        assert can_bypass_data_scope("warehouse") is False

    def test_bypass_none(self):
        assert can_bypass_data_scope(None) is False

    def test_bypass_empty(self):
        assert can_bypass_data_scope("") is False


class TestCleanFunction:
    def test_clean_none(self):
        assert _clean(None) == ""

    def test_clean_empty_string(self):
        assert _clean("") == ""

    def test_clean_whitespace(self):
        assert _clean("  test  ") == "test"

    def test_clean_integer(self):
        assert _clean(123) == "123"


class TestGetDataScope:
    def test_get_data_scope_admin_bypass(self):
        query_db = MockQueryDB()

        result = get_data_scope(query_db, user_id=1, role="admin")

        assert result["bypass"] is True
        assert result["rules"] == {}
        assert result["permission"] == "view"

    def test_get_data_scope_manager_bypass(self):
        query_db = MockQueryDB()

        result = get_data_scope(query_db, user_id=1, role="manager")

        assert result["bypass"] is True

    def test_get_data_scope_with_rules(self):
        query_db = MockQueryDB([
            {"scope_type": "project", "scope_value": "PRJ001"},
            {"scope_type": "project", "scope_value": "PRJ002"},
            {"scope_type": "department", "scope_value": "DEP001"},
        ])

        result = get_data_scope(query_db, user_id=1, role="sales")

        assert result["bypass"] is False
        assert result["rules"] == {
            "project": ["PRJ001", "PRJ002"],
            "department": ["DEP001"],
        }

    def test_get_data_scope_no_rules(self):
        query_db = MockQueryDB([])

        result = get_data_scope(query_db, user_id=1, role="sales")

        assert result["bypass"] is False
        assert result["rules"] == {}

    def test_get_data_scope_edit_permission(self):
        query_db = MockQueryDB([
            {"scope_type": "project", "scope_value": "PRJ001"},
        ])

        result = get_data_scope(query_db, user_id=1, role="sales", permission="edit")

        assert result["permission"] == "edit"
        assert result["rules"] == {"project": ["PRJ001"]}


class TestScopeHasRules:
    def test_scope_has_rules_with_rules(self):
        scope = {"bypass": False, "rules": {"project": ["PRJ001"]}}
        assert scope_has_rules(scope) is True

    def test_scope_has_rules_empty_rules(self):
        scope = {"bypass": False, "rules": {}}
        assert scope_has_rules(scope) is False

    def test_scope_has_rules_bypass(self):
        scope = {"bypass": True, "rules": {"project": ["PRJ001"]}}
        assert scope_has_rules(scope) is True

    def test_scope_has_rules_none(self):
        assert scope_has_rules(None) is False


class TestBuildScopeFilter:
    def test_build_scope_filter_bypass(self):
        scope = {"bypass": True, "rules": {}}
        field_map = {"project": "project_code"}

        where_sql, params = build_scope_filter(scope, field_map)

        assert where_sql == ""
        assert params == ()

    def test_build_scope_filter_no_rules(self):
        scope = {"bypass": False, "rules": {}}
        field_map = {"project": "project_code"}

        where_sql, params = build_scope_filter(scope, field_map)

        assert where_sql == ""
        assert params == ()

    def test_build_scope_filter_with_rules(self):
        scope = {"bypass": False, "rules": {"project": ["PRJ001", "PRJ002"]}}
        field_map = {"project": "project_code"}

        where_sql, params = build_scope_filter(scope, field_map)

        assert "IN (%s,%s)" in where_sql
        assert params == ("PRJ001", "PRJ002")

    def test_build_scope_filter_multiple_types(self):
        scope = {
            "bypass": False,
            "rules": {
                "project": ["PRJ001"],
                "department": ["DEP001"],
            },
        }
        field_map = {
            "project": "project_code",
            "department": "department_id",
        }

        where_sql, params = build_scope_filter(scope, field_map)

        assert "project_code" in where_sql
        assert "department_id" in where_sql
        assert params == ("PRJ001", "DEP001")

    def test_build_scope_filter_no_matching_types(self):
        scope = {"bypass": False, "rules": {"serial": ["SER001"]}}
        field_map = {"project": "project_code"}

        where_sql, params = build_scope_filter(scope, field_map)

        assert where_sql == " AND 1=0"
        assert params == ()

    def test_build_scope_filter_with_existing_params(self):
        scope = {"bypass": False, "rules": {"project": ["PRJ001"]}}
        field_map = {"project": "project_code"}

        where_sql, params = build_scope_filter(scope, field_map, params=(1, 2))

        assert params == (1, 2, "PRJ001")


class TestRowAllowed:
    def test_row_allowed_bypass(self):
        scope = {"bypass": True, "rules": {}}
        row = {"project_code": "PRJ001"}

        assert row_allowed(scope, row) is True

    def test_row_allowed_no_rules(self):
        scope = {"bypass": False, "rules": {}}
        row = {"project_code": "PRJ001"}

        assert row_allowed(scope, row) is True

    def test_row_allowed_match_project(self):
        scope = {"bypass": False, "rules": {"project": ["PRJ001", "PRJ002"]}}
        row = {"project_code": "PRJ001"}

        assert row_allowed(scope, row) is True

    def test_row_allowed_no_match(self):
        scope = {"bypass": False, "rules": {"project": ["PRJ001"]}}
        row = {"project_code": "PRJ003"}

        assert row_allowed(scope, row) is False

    def test_row_allowed_match_serial(self):
        scope = {"bypass": False, "rules": {"serial": ["SER001"]}}
        row = {"serial_no": "SER001"}

        assert row_allowed(scope, row) is True

    def test_row_allowed_match_department(self):
        scope = {"bypass": False, "rules": {"department": ["DEP001"]}}
        row = {"department_id": "DEP001"}

        assert row_allowed(scope, row) is True

    def test_row_allowed_match_customer(self):
        scope = {"bypass": False, "rules": {"customer": ["CUST001"]}}
        row = {"customer_id": "CUST001"}

        assert row_allowed(scope, row) is True

    def test_row_allowed_match_supplier(self):
        scope = {"bypass": False, "rules": {"supplier": ["SUPP001"]}}
        row = {"supplier_id": "SUPP001"}

        assert row_allowed(scope, row) is True

    def test_row_allowed_with_custom_field_map(self):
        scope = {"bypass": False, "rules": {"project": ["PRJ001"]}}
        row = {"proj_code": "PRJ001"}
        field_map = {"project": "proj_code"}

        assert row_allowed(scope, row, field_map) is True

    def test_row_allowed_no_match_custom_field_map(self):
        scope = {"bypass": False, "rules": {"project": ["PRJ001"]}}
        row = {"proj_code": "PRJ002"}
        field_map = {"project": "proj_code"}

        assert row_allowed(scope, row, field_map) is False

    def test_row_allowed_none_scope(self):
        row = {"project_code": "PRJ001"}

        assert row_allowed(None, row) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
