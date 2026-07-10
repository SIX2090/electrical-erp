from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple


BYPASS_ROLES = {"admin", "manager"}
SUPPORTED_SCOPE_TYPES = {"project", "cabinet", "department", "customer", "supplier"}


def normalize_role(role):
    return (role or "").strip().lower()


def can_bypass_data_scope(role):
    return normalize_role(role) in BYPASS_ROLES


def _clean(value):
    if value is None:
        return ""
    return str(value).strip()


def _rule_rows(query_db, *, user_id=None, role=None, permission="view"):
    subject_filters = []
    params: List[Any] = [permission]
    if user_id is not None:
        subject_filters.append("(subject_type='user' AND subject_id=%s)")
        params.append(str(user_id))
    role = normalize_role(role)
    if role:
        subject_filters.append("(subject_type='role' AND subject_id=%s)")
        params.append(role)
    if not subject_filters:
        return []
    return query_db(
        f"""
        SELECT scope_type, scope_value
        FROM data_scope_rules
        WHERE permission=%s
          AND status='enabled'
          AND scope_type IN ('project','cabinet','department','customer','supplier')
          AND ({' OR '.join(subject_filters)})
        ORDER BY subject_type, id
        """,
        tuple(params),
    ) or []


def get_data_scope(query_db, *, user_id=None, role=None, permission="view") -> Dict[str, Any]:
    if can_bypass_data_scope(role):
        return {"bypass": True, "rules": {}, "permission": permission}
    rules: Dict[str, set] = {scope_type: set() for scope_type in SUPPORTED_SCOPE_TYPES}
    for row in _rule_rows(query_db, user_id=user_id, role=role, permission=permission):
        scope_type = _clean(row.get("scope_type"))
        scope_value = _clean(row.get("scope_value"))
        if scope_type in rules and scope_value:
            rules[scope_type].add(scope_value)
    return {
        "bypass": False,
        "rules": {key: sorted(values) for key, values in rules.items() if values},
        "permission": permission,
    }


def scope_has_rules(scope: Dict[str, Any]) -> bool:
    return bool((scope or {}).get("rules"))


def build_scope_filter(
    scope: Dict[str, Any],
    field_map: Dict[str, str],
    *,
    params: Iterable[Any] = (),
) -> Tuple[str, Tuple[Any, ...]]:
    if not scope or scope.get("bypass") or not scope_has_rules(scope):
        return "", tuple(params or ())
    clauses = []
    out_params = list(params or ())
    for scope_type, field_expr in field_map.items():
        values = (scope.get("rules") or {}).get(scope_type)
        if not values or not field_expr:
            continue
        placeholders = ",".join(["%s"] * len(values))
        clauses.append(f"COALESCE({field_expr}::text, '') IN ({placeholders})")
        out_params.extend(values)
    if not clauses:
        return " AND 1=0", tuple(out_params)
    return " AND (" + " OR ".join(clauses) + ")", tuple(out_params)


def row_allowed(scope: Dict[str, Any], row: Dict[str, Any], field_map: Dict[str, str] | None = None) -> bool:
    if not scope or scope.get("bypass") or not scope_has_rules(scope):
        return True
    field_map = field_map or {
        "project": "project_code",
        "cabinet": "cabinet_no",
        "department": "department_id",
        "customer": "customer_id",
        "supplier": "supplier_id",
    }
    rules = scope.get("rules") or {}
    for scope_type, row_key in field_map.items():
        values = rules.get(scope_type)
        if values and _clean(row.get(row_key)) in values:
            return True
    return False


def log_data_access(
    execute_db,
    *,
    user_id=None,
    role=None,
    resource_type=None,
    resource_id=None,
    action="view",
    allowed=True,
    reason="",
):
    execute_db(
        """
        INSERT INTO data_access_logs
            (user_id, role, resource_type, resource_id, action, allowed, reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            user_id,
            role,
            resource_type,
            str(resource_id) if resource_id is not None else None,
            action,
            bool(allowed),
            reason,
        ),
    )

