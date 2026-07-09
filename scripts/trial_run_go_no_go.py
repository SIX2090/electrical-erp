from pathlib import Path
import csv
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run_check(args, extra_env=None):
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()


def parse_value(output, key, default=""):
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    return default


def count_csv_rows(path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return len(list(csv.DictReader(fh)))


def add_script_check(rows, item, script, detail_key="checked_items", command_prefix=True, extra_env=None):
    cmd = [sys.executable, script]
    code, out, err = run_check(cmd, extra_env=extra_env)
    script_cmd = script.replace("/", "\\")
    command = f"python {script_cmd}"
    if command_prefix:
        command = f"set INVENTORY_NAV_MODE=gt_pilot && set PG_PASSWORD=%PG_PASSWORD% && {command}"
    rows.append(
        {
            "item": item,
            "status": "PASS" if code == 0 else "FAIL",
            "detail": parse_value(out, detail_key, "see output"),
            "command": command,
        }
    )


def main():
    rows = []

    code, out, err = run_check([sys.executable, "scripts/validate_first_machine_template.py"])
    rows.append(
        {
            "item": "First machine data template",
            "status": "PASS" if code == 0 else "FAIL",
            "detail": f"errors={parse_value(out, 'errors', 'see output')} warnings={parse_value(out, 'warnings', 'see output')}",
            "command": "python scripts\\validate_first_machine_template.py",
        }
    )

    code, out, err = run_check([sys.executable, "scripts/check_first_machine_master_data.py"])
    rows.append(
        {
            "item": "Master data cross-check",
            "status": "PASS" if code == 0 else "FAIL",
            "detail": parse_value(out, "checks", "see output"),
            "command": "set PG_PASSWORD=%PG_PASSWORD% && python scripts\\check_first_machine_master_data.py",
        }
    )

    code, out, err = run_check([sys.executable, "scripts/select_trial_machine_candidates.py"])
    candidate_count = int(parse_value(out, "trial_candidates", "0") or 0)
    rows.append(
        {
            "item": "First machine candidate",
            "status": "PASS" if code == 0 and candidate_count >= 1 else "FAIL",
            "detail": f"trial_candidates={candidate_count}",
            "command": "set PG_PASSWORD=%PG_PASSWORD% && python scripts\\select_trial_machine_candidates.py",
        }
    )

    add_script_check(rows, "Trial user menus", "scripts/audit_trial_user_menus.py", "checked_users")
    add_script_check(rows, "Trial user backend access", "scripts/audit_trial_user_access.py", "checked_users")
    add_script_check(rows, "Trial visible navigation", "scripts/audit_trial_visible_navigation.py")
    add_script_check(rows, "Trial direct access matrix", "scripts/audit_trial_direct_access_matrix.py")
    add_script_check(rows, "Trial high-risk role matrix", "scripts/audit_trial_high_risk_role_matrix.py")
    add_script_check(rows, "Trial POST action scope", "scripts/audit_trial_post_action_scope.py")
    add_script_check(rows, "Trial role permissions page", "scripts/audit_trial_role_permissions_page.py")
    add_script_check(rows, "Trial sales menu entries", "scripts/audit_trial_sales_menu_entries.py")
    add_script_check(rows, "Trial core document fields", "scripts/audit_trial_core_document_fields.py")
    add_script_check(rows, "Trial operator task queues", "scripts/audit_trial_operator_task_queues.py")
    add_script_check(
        rows,
        "Trial release documents",
        "scripts/audit_trial_release_documents.py",
        command_prefix=False,
        extra_env={"TRIAL_RELEASE_ALLOW_PENDING_GO": "1"},
    )
    add_script_check(rows, "Trial issue log validator", "scripts/audit_trial_issue_log_validator.py", command_prefix=False)
    add_script_check(rows, "First machine main line visibility", "scripts/audit_first_machine_workflow.py")
    add_script_check(rows, "First machine shortage to purchase suggestion", "scripts/audit_first_machine_procurement.py")
    add_script_check(rows, "First machine purchase to receipt/payable", "scripts/audit_first_machine_purchase_to_receipt.py")
    add_script_check(rows, "First machine inventory trace", "scripts/audit_first_machine_inventory_trace.py")
    add_script_check(rows, "First machine inventory execution", "scripts/audit_first_machine_inventory_execution.py")
    add_script_check(rows, "First machine work order issue", "scripts/audit_first_machine_work_order_issue.py")
    add_script_check(rows, "First machine quality closure", "scripts/audit_first_machine_quality_closure.py")
    add_script_check(rows, "First machine subcontract closure", "scripts/audit_first_machine_subcontract_closure.py")
    add_script_check(rows, "First machine completion shipment finance", "scripts/audit_first_machine_completion_shipment_finance.py")
    add_script_check(rows, "First machine finance settlement", "scripts/audit_first_machine_finance_settlement.py")
    add_script_check(rows, "First machine service closure", "scripts/audit_first_machine_service_closure.py")
    add_script_check(rows, "First machine lifecycle ledger", "scripts/audit_first_machine_lifecycle_ledger.py")
    add_script_check(rows, "First machine detail runtime text", "scripts/audit_first_machine_detail_runtime_text.py")
    add_script_check(rows, "First machine period close readiness", "scripts/audit_first_machine_period_close_readiness.py")

    code, out, err = run_check([sys.executable, "scripts/validate_trial_issue_log.py"])
    open_blockers = int(parse_value(out, "open_blockers", "0") or 0)
    rows.append(
        {
            "item": "Trial issue log blockers",
            "status": "PASS" if code == 0 and open_blockers == 0 else "FAIL",
            "detail": f"open_blockers={open_blockers}",
            "command": "python scripts\\validate_trial_issue_log.py",
        }
    )

    blockers = [row for row in rows if row["status"] != "PASS"]
    decision = "GO" if not blockers else "NO-GO"
    output_path = ROOT / "release" / "trial_run" / "trial_run_go_no_go.md"
    lines = [
        "# First Machine Trial Run Go/No-Go Check",
        "",
        f"Decision: **{decision}**",
        "",
        "| Check | Status | Result | Command |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(f"| {row['item']} | {row['status']} | {row['detail']} | `{row['command']}` |")
    lines.extend(["", "## Notes", ""])
    if blockers:
        lines.append("The first machine trial run is not ready. Fix the failed checks and run this script again.")
    else:
        lines.append("The first machine trial run prerequisites are satisfied for the checked scope.")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"decision={decision}")
    print(f"report={output_path}")
    for row in rows:
        print(f"{row['status']} | {row['item']} | {row['detail']}")
    return 0 if decision == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
