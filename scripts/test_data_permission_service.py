"""Unit tests for data_permission_service.py - core permission validation logic."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from services.data_permission_service import (
    SUBJECT_TYPES,
    PERMISSION_TYPES,
    _clean,
    _label_for_scope,
    create_rule,
    update_rule,
    delete_rule,
    get_user_permissions,
    list_rules,
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


class TestCleanFunction:
    def test_clean_none(self):
        assert _clean(None) == ""

    def test_clean_empty_string(self):
        assert _clean("") == ""

    def test_clean_whitespace(self):
        assert _clean("  test  ") == "test"

    def test_clean_integer(self):
        assert _clean(123) == "123"

    def test_clean_float(self):
        assert _clean(123.45) == "123.45"


class TestLabelForScope:
    def test_label_with_explicit_label(self):
        assert _label_for_scope("project", "PRJ001", "项目A") == "项目A"

    def test_label_without_explicit_label(self):
        assert _label_for_scope("project", "PRJ001", "") == "项目:PRJ001"

    def test_label_unknown_scope_type(self):
        assert _label_for_scope("unknown", "ID001", "") == "unknown:ID001"


class TestCreateRule:
    def test_create_rule_valid_params(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()
        execute_and_return = MockExecuteAndReturn({"id": 1})

        rule_id = create_rule(
            query_db,
            execute_db,
            execute_and_return,
            subject_type="user",
            subject_id="1",
            scope_type="project",
            scope_id="PRJ001",
            scope_label="项目A",
            permission="view",
            created_by=1,
        )

        assert rule_id == 1
        assert len(execute_and_return.calls) == 1
        assert "INSERT INTO data_permission_rules" in execute_and_return.calls[0]["sql"]

    def test_create_rule_invalid_subject_type(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()
        execute_and_return = MockExecuteAndReturn()

        with pytest.raises(ValueError) as exc_info:
            create_rule(
                query_db,
                execute_db,
                execute_and_return,
                subject_type="invalid",
                subject_id="1",
                scope_type="project",
                scope_id="PRJ001",
            )
        assert "subject_type must be one of" in str(exc_info.value)

    def test_create_rule_missing_subject_id(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()
        execute_and_return = MockExecuteAndReturn()

        with pytest.raises(ValueError) as exc_info:
            create_rule(
                query_db,
                execute_db,
                execute_and_return,
                subject_type="user",
                subject_id="",
                scope_type="project",
                scope_id="PRJ001",
            )
        assert "subject_id is required" in str(exc_info.value)

    def test_create_rule_invalid_scope_type(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()
        execute_and_return = MockExecuteAndReturn()

        with pytest.raises(ValueError) as exc_info:
            create_rule(
                query_db,
                execute_db,
                execute_and_return,
                subject_type="user",
                subject_id="1",
                scope_type="invalid",
                scope_id="PRJ001",
            )
        assert "scope_type must be one of" in str(exc_info.value)

    def test_create_rule_duplicate(self):
        query_db = MockQueryDB([{"id": 1}])
        execute_db = MockExecuteDB()
        execute_and_return = MockExecuteAndReturn()

        with pytest.raises(ValueError) as exc_info:
            create_rule(
                query_db,
                execute_db,
                execute_and_return,
                subject_type="user",
                subject_id="1",
                scope_type="project",
                scope_id="PRJ001",
                permission="view",
            )
        assert "相同主体、范围和权限的规则已存在" in str(exc_info.value)


class TestUpdateRule:
    def test_update_rule_status(self):
        query_db = MockQueryDB([{
            "subject_type": "user",
            "subject_id": "1",
            "scope_type": "project",
            "scope_id": "PRJ001",
            "permission": "view",
            "status": "enabled",
        }])
        execute_db = MockExecuteDB()

        result = update_rule(query_db, execute_db, 1, status="disabled")

        assert result is True
        assert len(execute_db.calls) >= 1

    def test_update_rule_permission(self):
        query_db = MockQueryDB([{
            "subject_type": "user",
            "subject_id": "1",
            "scope_type": "project",
            "scope_id": "PRJ001",
            "permission": "view",
            "status": "enabled",
        }])
        execute_db = MockExecuteDB()

        result = update_rule(query_db, execute_db, 1, permission="edit")

        assert result is True

    def test_update_rule_invalid_status(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()

        with pytest.raises(ValueError) as exc_info:
            update_rule(query_db, execute_db, 1, status="invalid")
        assert "status must be 'enabled' or 'disabled'" in str(exc_info.value)

    def test_update_rule_no_fields(self):
        query_db = MockQueryDB()
        execute_db = MockExecuteDB()

        result = update_rule(query_db, execute_db, 1)
        assert result is False


class TestDeleteRule:
    def test_delete_rule(self):
        query_db = MockQueryDB([{
            "subject_type": "user",
            "subject_id": "1",
            "scope_type": "project",
            "scope_id": "PRJ001",
            "permission": "view",
        }])
        execute_db = MockExecuteDB()

        result = delete_rule(query_db, execute_db, 1)

        assert result is True
        assert len(execute_db.calls) >= 1


class TestGetUserPermissions:
    def test_get_user_permissions_admin_bypass(self):
        query_db = MockQueryDB()

        result = get_user_permissions(query_db, 1, "admin")

        assert result == {
            "project": ["*"],
            "serial": ["*"],
            "department": ["*"],
            "customer": ["*"],
            "supplier": ["*"],
        }

    def test_get_user_permissions_manager_bypass(self):
        query_db = MockQueryDB()

        result = get_user_permissions(query_db, 1, "manager")

        assert result == {
            "project": ["*"],
            "serial": ["*"],
            "department": ["*"],
            "customer": ["*"],
            "supplier": ["*"],
        }

    def test_get_user_permissions_with_rules(self):
        query_db = MockQueryDB([
            {"scope_type": "project", "scope_id": "PRJ001"},
            {"scope_type": "project", "scope_id": "PRJ002"},
            {"scope_type": "department", "scope_id": "DEP001"},
        ])

        result = get_user_permissions(query_db, 1, "sales")

        assert result["project"] == ["PRJ001", "PRJ002"]
        assert result["department"] == ["DEP001"]
        assert result["serial"] == []
        assert result["customer"] == []
        assert result["supplier"] == []

    def test_get_user_permissions_no_rules(self):
        query_db = MockQueryDB([])

        result = get_user_permissions(query_db, 1, "sales")

        assert all(len(v) == 0 for v in result.values())


class TestListRules:
    def test_list_rules_no_filters(self):
        query_db = MockQueryDB([{
            "id": 1,
            "subject_type": "user",
            "subject_id": "1",
            "scope_type": "project",
            "scope_id": "PRJ001",
            "scope_label": "项目A",
            "permission": "view",
            "status": "enabled",
            "created_by": 1,
            "created_at": "2024-01-01",
            "subject_label": "admin",
        }])

        result = list_rules(query_db)

        assert len(result) == 1
        assert result[0]["id"] == 1
        assert result[0]["subject_type_label"] == "用户"
        assert result[0]["scope_type_label"] == "项目"
        assert result[0]["permission_label"] == "查看"
        assert result[0]["status_label"] == "启用"

    def test_list_rules_filter_by_subject_type(self):
        query_db = MockQueryDB([{
            "id": 1,
            "subject_type": "user",
            "subject_id": "1",
            "scope_type": "project",
            "scope_id": "PRJ001",
            "permission": "view",
            "status": "enabled",
            "subject_label": "",
        }])

        result = list_rules(query_db, subject_type="user")

        assert len(result) == 1
        assert result[0]["subject_type"] == "user"

    def test_list_rules_filter_by_status(self):
        query_db = MockQueryDB([{
            "id": 1,
            "subject_type": "user",
            "subject_id": "1",
            "scope_type": "project",
            "scope_id": "PRJ001",
            "permission": "view",
            "status": "disabled",
            "subject_label": "",
        }])

        result = list_rules(query_db, status="disabled")

        assert len(result) == 1
        assert result[0]["status"] == "disabled"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
