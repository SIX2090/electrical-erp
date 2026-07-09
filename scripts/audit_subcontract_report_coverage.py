from pathlib import Path
import os
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.first_machine_trial_utils import load_trial_password

REPORTS = {
    "/inventory/reports/subcontract-wip": "subcontract-wip",
    "/inventory/reports/subcontract-execution": "subcontract-execution",
    "/inventory/reports/subcontract-inout-detail": "subcontract-inout-detail",
    "/inventory/reports/subcontract-variance": "subcontract-variance",
    "/inventory/reports/subcontract-payable-reconcile": "subcontract-payable-reconcile",
}


def read_text(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def assert_contains(findings, name, text, needle):
    if needle not in text:
        findings.append(f"{name}: missing {needle}")


def main():
    os.environ.setdefault("PG_PASSWORD", "admin")
    os.environ.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
    os.environ.setdefault("INVENTORY_SECRET_KEY", "subcontract-report-coverage-audit")
    os.environ.setdefault("WTF_CSRF_ENABLED", "0")

    findings = []
    report_routes = read_text("routes/report_routes.py")
    module_report_data = read_text("routes/module_report_data.py")
    base_template = read_text("templates/base.html")
    pilot_permissions = read_text("services/pilot_permissions.py")
    help_service = read_text("services/erp_help_service.py")

    for path, key in REPORTS.items():
        assert_contains(findings, "report_routes", report_routes, path)
        assert_contains(findings, "module_report_data_path", module_report_data, path)
        assert_contains(findings, "module_report_data_key", module_report_data, f'"{key}"')
        assert_contains(findings, "base_menu", base_template, path)
        assert_contains(findings, "pilot_permissions", pilot_permissions, path)
        assert_contains(findings, "help_service", help_service, path)

    write_action_needles = ("methods=[\"POST\"", "@app.post(", "新增委外", "保存", "提交", "审核")
    for path in REPORTS:
        route_context_start = report_routes.find(path)
        route_context = report_routes[max(route_context_start - 120, 0): route_context_start + 220] if route_context_start >= 0 else ""
        if any(needle in route_context for needle in write_action_needles[:2]):
            findings.append(f"report_routes: write route near {path}")

    try:
        from app import create_app

        app = create_app()
        app.testing = True
        with app.test_client() as client:
            login = client.post(
                "/login",
                data={"username": "pilot_purchase", "password": load_trial_password("pilot_purchase")},
                follow_redirects=False,
            )
            if login.status_code not in {302, 303}:
                findings.append(f"runtime: pilot_purchase login failed status={login.status_code}")
            else:
                for path in REPORTS:
                    response = client.get(path, follow_redirects=False)
                    if response.status_code != 200:
                        findings.append(f"runtime: {path} status={response.status_code}")
    except Exception as exc:
        findings.append(f"runtime: {type(exc).__name__}: {exc}")

    if findings:
        print("subcontract_report_coverage_audit=failed")
        for finding in findings:
            print(f"- {finding}")
        raise SystemExit(1)

    print("subcontract_report_coverage_audit=ok")
    print(f"checked_reports={len(REPORTS)}")


if __name__ == "__main__":
    main()
