from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from services.env_config import get_pg_password  # noqa: E402
from services.pilot_permissions import (  # noqa: E402
    PILOT_PERMISSION_ACTIONS,
    PILOT_PERMISSION_FEATURES,
    PILOT_ROLE_LABELS,
    PILOT_ROLE_TRIAL_USERS,
    default_actions_for_role,
    default_groups_for_role,
)


REPORT_PATH = ROOT / "reports" / "role_permission_matrix_findings.json"
ALL_ACTIONS = {item["key"] for item in PILOT_PERMISSION_ACTIONS}
ROLE_KEYS = tuple(PILOT_ROLE_LABELS.keys())
EXPECTED_FEATURE_KEYS = {feature["key"] for feature in PILOT_PERMISSION_FEATURES}
INTENTIONALLY_RESTRICTED: set[tuple[str, str]] = set()

CRITICAL_FEATURE_ACTIONS = {
    "period_close": {"audit", "operate"},
    "finance_exchange_adjustment": {"audit", "operate"},
    "production_completion": {"audit", "operate"},
    "production_completion_edit": {"audit", "operate"},
}

REQUIRED_FEATURE_KEYS = {
    "sales_return_edit",
    "sales_invoice_edit",
    "shipment_edit",
    "supplier_quote_edit",
    "purchase_receipt_edit",
    "purchase_return_edit",
    "purchase_invoice_edit",
    "subcontract_issue",
    "subcontract_receive",
    "work_order_edit",
    "production_issue_edit",
    "production_completion_edit",
    "quality_inspection_edit",
    "period_close",
    "finance_exchange_adjustment",
    "finance_exchange_adjustment_list",
}

CRITICAL_ROUTE_ACTIONS = {
    "/sales-returns/<int:return_id>/edit": ("sales_return_edit", "edit"),
    "/sales-invoices/<int:invoice_id>/edit": ("sales_invoice_edit", "edit"),
    "/shipments/<int:shipment_id>/edit": ("shipment_edit", "edit"),
    "/supplier-quotes/<int:quote_id>/edit": ("supplier_quote_edit", "edit"),
    "/purchase_receipts/<int:receipt_id>/edit": ("purchase_receipt_edit", "edit"),
    "/purchase-returns/<int:return_id>/edit": ("purchase_return_edit", "edit"),
    "/purchase-invoices/<int:invoice_id>/edit": ("purchase_invoice_edit", "edit"),
    "/subcontract_issue/<int:issue_id>/edit": ("subcontract_issue", "edit"),
    "/subcontract_receive/<int:receive_id>/edit": ("subcontract_receive", "edit"),
    "/work-orders/<int:work_order_id>/edit": ("work_order_edit", "edit"),
    "/production-issues/<int:doc_id>/edit": ("production_issue_edit", "edit"),
    "/production-completions/<int:doc_id>/edit": ("production_completion_edit", "edit"),
    "/production-enhance/quality-inspections/<int:inspection_id>/edit": ("quality_inspection_edit", "edit"),
    "/finance/period-close": ("period_close", "operate"),
    "/finance/exchange-adjustment": ("finance_exchange_adjustment", "operate"),
    "/finance/exchange-adjustments": ("finance_exchange_adjustment_list", "view"),
}


@dataclass
class Finding:
    code: str
    role: str
    source: str
    detail: str


def load_local_env() -> None:
    env_file = ROOT / "runtime_local_secrets.cmd"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line.lower().startswith("set "):
            continue
        payload = line[4:].strip()
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]
        if "=" in payload:
            key, value = payload.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def connect():
    load_local_env()
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )


def parse_json_object(value: str | None) -> dict[str, list[str]]:
    if not value:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    parsed: dict[str, list[str]] = {}
    for key, actions in data.items():
        if isinstance(actions, list):
            parsed[str(key)] = sorted({str(action) for action in actions if str(action)})
    return parsed


def parse_groups(value: str | None, role: str) -> set[str]:
    groups = {item.strip() for item in (value or "").split(",") if item.strip()}
    return groups or default_groups_for_role(role)


def load_role_rows() -> dict[str, dict]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.pilot_role_permissions') AS table_name")
        if not cur.fetchone()["table_name"]:
            return {}
        cur.execute("SELECT role, permission_groups, action_permissions FROM pilot_role_permissions")
        return {row["role"]: dict(row) for row in cur.fetchall()}


def load_trial_users() -> dict[str, str]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT username, role FROM users")
        return {row["username"]: row["role"] for row in cur.fetchall()}


def effective_role_matrix(role: str, row: dict | None) -> tuple[set[str], dict[str, list[str]]]:
    groups = parse_groups((row or {}).get("permission_groups"), role)
    default_permissions = {
        key: list(actions)
        for key, actions in default_actions_for_role(role).items()
        if feature_by_key(key)["group"] in groups or role == "admin"
    }
    stored_permissions = parse_json_object((row or {}).get("action_permissions"))
    for key, actions in stored_permissions.items():
        if actions:
            default_permissions[key] = sorted(set(default_permissions.get(key, [])) | set(actions))
    return groups, default_permissions


def feature_by_key(key: str) -> dict:
    for feature in PILOT_PERMISSION_FEATURES:
        if feature["key"] == key:
            return feature
    raise KeyError(key)


def app_routes() -> dict[str, set[str]]:
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        methods = set(rule.methods or set()) - {"HEAD", "OPTIONS"}
        routes[rule.rule] = methods
    return routes


def route_exists_for_path(routes: dict[str, set[str]], path: str) -> bool:
    return path in routes or f"{path}/" in routes


def verify() -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    rows = load_role_rows()
    users = load_trial_users()
    routes = app_routes()
    features_by_path = {feature["path"]: feature for feature in PILOT_PERMISSION_FEATURES}

    missing_feature_defs = sorted(REQUIRED_FEATURE_KEYS - EXPECTED_FEATURE_KEYS)
    for key in missing_feature_defs:
        findings.append(Finding("ROLE-MISSING-FEATURES", "-", key, "required feature is not defined"))

    for feature in PILOT_PERMISSION_FEATURES:
        if not route_exists_for_path(routes, feature["path"]):
            findings.append(Finding("FEATURE-NO-ROUTE", "-", feature["key"], feature["path"]))

    for route, (feature_key, required_action) in CRITICAL_ROUTE_ACTIONS.items():
        feature = feature_by_key(feature_key) if feature_key in EXPECTED_FEATURE_KEYS else None
        if route not in routes:
            findings.append(Finding("FEATURE-NO-ROUTE", "-", feature_key, f"critical route missing: {route}"))
            continue
        if not feature or required_action not in feature["default_actions"]:
            findings.append(Finding("ROUTE-NO-FEATURE", "-", route, f"missing {required_action} on {feature_key}"))

    for route, methods in routes.items():
        if "POST" not in methods and "DELETE" not in methods:
            continue
        matched = next(
            (
                feature
                for path, feature in sorted(features_by_path.items(), key=lambda item: len(item[0]), reverse=True)
                if route == path or route.startswith(path + "/")
            ),
            None,
        )
        if not matched:
            continue
        if route.endswith("/new") and "create" not in matched["default_actions"]:
            findings.append(Finding("ROUTE-NO-FEATURE", "-", route, f"{matched['key']} lacks create"))
        if "/edit" in route and "edit" not in matched["default_actions"]:
            findings.append(Finding("ROUTE-NO-FEATURE", "-", route, f"{matched['key']} lacks edit"))
        if "/delete" in route and "delete" not in matched["default_actions"]:
            if "attachment" not in route and "/notes" not in route:
                findings.append(Finding("ROUTE-NO-FEATURE", "-", route, f"{matched['key']} lacks delete"))

    for role in ROLE_KEYS:
        row = rows.get(role)
        groups, permissions = effective_role_matrix(role, row)
        expected_keys = {
            feature["key"]
            for feature in PILOT_PERMISSION_FEATURES
            if feature["group"] in groups or role == "admin"
        }
        for key in sorted(expected_keys):
            actions = set(permissions.get(key, []))
            if not actions and (role, key) not in INTENTIONALLY_RESTRICTED:
                findings.append(Finding("ROLE-MISSING-FEATURES", role, key, "empty action permissions"))
        for key in sorted(set(permissions) - expected_keys):
            findings.append(Finding("ROLE-EXTRA-ACCESS", role, key, "feature is outside role groups"))
        if role == "admin":
            for key in sorted(EXPECTED_FEATURE_KEYS):
                actions = set(permissions.get(key, []))
                missing_actions = ALL_ACTIONS - actions
                if missing_actions:
                    findings.append(Finding("ROLE-MISSING-FEATURES", role, key, f"admin missing actions: {sorted(missing_actions)}"))
        if role == "finance":
            actions = set(permissions.get("period_close", []))
            if not {"audit", "operate"} <= actions:
                findings.append(Finding("ROLE-MISSING-FEATURES", role, "period_close", "finance requires audit and operate"))
        if role == "production":
            actions = set(permissions.get("production_completion", []))
            if not {"audit", "operate"} <= actions:
                findings.append(Finding("ROLE-MISSING-FEATURES", role, "production_completion", "production requires audit and operate"))
        trial_user = PILOT_ROLE_TRIAL_USERS.get(role)
        if trial_user and trial_user not in users:
            findings.append(Finding("TRIAL-USER-MISSING", role, trial_user, "trial user not found in users table"))

    summary = {
        "roles": len(ROLE_KEYS),
        "features": len(PILOT_PERMISSION_FEATURES),
        "routes": len(routes),
        "trial_users": len(users),
        "findings": len(findings),
    }
    return findings, summary


def write_findings(findings: list[Finding], summary: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "summary": summary,
                "findings": [asdict(item) for item in findings],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    findings, summary = verify()
    write_findings(findings, summary)
    print("role_permission_matrix=ok" if not findings else "role_permission_matrix=failed")
    print(f"roles={summary['roles']} features={summary['features']} routes={summary['routes']} findings={summary['findings']}")
    print(f"report={REPORT_PATH}")
    for item in findings[:80]:
        print(f"{item.code} | {item.role} | {item.source} | {item.detail}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
