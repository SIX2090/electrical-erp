from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("PG_PASSWORD", "admin")
os.environ.setdefault("INVENTORY_SECRET_KEY", "audit-secret")
os.environ.setdefault("WTF_CSRF_ENABLED", "0")

from app import create_app  # noqa: E402
from scripts.audit_full_system_operator_simulation import OUT_PATH as FULL_SYSTEM_OUT  # noqa: E402
from services.env_config import get_pg_password  # noqa: E402


REPORT_MD = ROOT / "logs" / "erp_bug_hunter_report.md"
REPORT_JSON = ROOT / "logs" / "erp_bug_hunter_findings.json"
FRONTEND_JSON = ROOT / "logs" / "erp_frontend_bug_audit" / "findings.json"


@dataclass
class Finding:
    severity: str
    module: str
    bug_type: str
    location: str
    title: str
    actual: str
    expected: str
    reproduce: list[str]
    evidence: dict[str, Any]
    owner: str = "unassigned"


def connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        dbname=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
        cursor_factory=RealDictCursor,
    )


def qident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def safe_print(text: str) -> None:
    print(text.encode("ascii", "backslashreplace").decode("ascii"))


def run_command(args: list[str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.setdefault("PG_PASSWORD", "admin")
    completed = subprocess.run(
        args,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        timeout=180,
    )
    return completed.returncode, completed.stdout


DIRTY_CODEPOINTS = {
    0xFFFD,
    0x95C1,
    0x95BF,
    0x95B8,
    0x95BB,
    0x9359,
    0x934F,
    0x9351,
    0x9352,
    0x935B,
    0x9366,
    0x9368,
    0x937C,
    0x6434,
    0x9417,
    0x9422,
    0x93C2,
    0x95B2,
    0x7487,
    0xFE3D,
    0x510F,
    0x6E1A,
    0x7C32,
    0x30E5,
    0x7C31,
    0x6944,
    0x935F,
    0x7019,
    0x5A34,
    0x5A4A,
    0x7ED7,
    0x68E3,
    0x6FC2,
    0x20AC,
    0x2122,
    0x0153,
}

EXPECTED_BLOCKED_GET_PATHS = {
    "/chart-of-accounts",
    "/finance/opening-balances",
    "/finance/vouchers/new",
}

RESOURCE_MISSING_GET_PATHS = {
    "/api/project-machine-ledger/resolve",
}


def looks_dirty_text(value: Any) -> bool:
    text = "" if value is None else str(value)
    if not text:
        return False
    if "???" in text or "\x00" in text:
        return True
    dirty_count = sum(1 for ch in text if ord(ch) in DIRTY_CODEPOINTS)
    private_count = sum(1 for ch in text if 0xE000 <= ord(ch) <= 0xF8FF)
    if private_count:
        return True
    if dirty_count >= 2:
        return True
    return dirty_count == 1 and ("?" in text or len(text) <= 4)


def response_looks_dirty(response) -> bool:
    content_type = (response.content_type or "").lower()
    raw = response.get_data()
    if "text/csv" in content_type or "application/csv" in content_type:
        text = raw.decode("utf-8-sig", errors="replace")
        return "\ufffd" in text or "\x00" in text or "???" in text
    return looks_dirty_text(response.get_data(as_text=True))


def short_value(value: Any) -> str:
    return str(value or "").encode("ascii", "backslashreplace").decode("ascii")[:180]


def add_command_finding(findings: list[Finding], name: str, returncode: int, output: str, severity: str = "high") -> None:
    if returncode == 0:
        return
    findings.append(
        Finding(
            severity=severity,
            module="system",
            bug_type="audit_gate",
            location=name,
            title=f"{name} failed",
            actual=f"Command exited with {returncode}.",
            expected="Audit command should pass before trial or release.",
            reproduce=[f"Run `{name}` from the project root."],
            evidence={"output_tail": output[-3000:]},
            owner="system administrator",
        )
    )


def audit_runtime_pages(findings: list[Finding]) -> None:
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False, "LOGIN_RATE_LIMIT": 1000})
    exact_paths = sorted(
        rule.rule
        for rule in app.url_map.iter_rules()
        if "GET" in rule.methods
        and "<" not in rule.rule
        and not rule.rule.startswith("/static")
    )
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = 1
            session["username"] = "bug_hunter"
            session["role"] = "admin"
        for path in exact_paths:
            response = client.get(path, follow_redirects=False)
            if response.status_code >= 500:
                findings.append(
                    Finding(
                        severity="critical",
                        module="page",
                        bug_type="http_500",
                        location=path,
                        title="Page returns server error",
                        actual=f"GET returned HTTP {response.status_code}.",
                        expected="Normal ERP pages should not return 5xx.",
                        reproduce=[f"Login as admin.", f"Open `{path}`."],
                        evidence={"status_code": response.status_code},
                        owner="route owner",
                    )
                )
            elif response.status_code == 404:
                if path in EXPECTED_BLOCKED_GET_PATHS or path in RESOURCE_MISSING_GET_PATHS:
                    continue
                findings.append(
                    Finding(
                        severity="high",
                        module="page",
                        bug_type="http_404",
                        location=path,
                        title="Registered page returns not found",
                        actual="GET returned HTTP 404.",
                        expected="Registered exact routes should be reachable or hidden.",
                        reproduce=[f"Login as admin.", f"Open `{path}`."],
                        evidence={"status_code": response.status_code},
                        owner="route owner",
                    )
                )
            if response_looks_dirty(response):
                findings.append(
                    Finding(
                        severity="critical",
                        module="page",
                        bug_type="visible_mojibake",
                        location=path,
                        title="Page contains visible dirty text marker",
                        actual="Response body contains replacement characters, placeholder question marks, or mojibake codepoints.",
                        expected="Operator-facing ERP pages must show clean Chinese business text.",
                        reproduce=[f"Login as admin.", f"Open `{path}`.", "Search the page source for dirty text markers."],
                        evidence={"status_code": response.status_code},
                        owner="frontend/backend route owner",
                    )
                )


MASTER_SCAN_TARGETS = {
    "products": ("code", "name", "specification", "unit", "category", "remark"),
    "suppliers": ("name", "contact_person", "phone", "address", "remark"),
    "customers": ("name", "contact_person", "phone", "address", "remark"),
    "warehouses": ("name", "code", "remark"),
    "locations": ("name", "code", "remark"),
}


def existing_columns(cur, table: str) -> set[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def table_exists(cur, table: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS table_name", (table,))
    row = cur.fetchone()
    return bool(row and row["table_name"])


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s AND column_name=%s
        """,
        (table, column),
    )
    return cur.fetchone() is not None


def scalar(cur, sql: str, params=()):
    cur.execute(sql, params)
    row = cur.fetchone()
    if not row:
        return None
    return next(iter(row.values()))


def audit_database(findings: list[Finding]) -> None:
    with connect() as conn, conn.cursor() as cur:
        for table, columns in MASTER_SCAN_TARGETS.items():
            if not table_exists(cur, table):
                findings.append(
                    Finding(
                        severity="critical",
                        module="master_data",
                        bug_type="missing_table",
                        location=table,
                        title="Required master-data table is missing",
                        actual=f"`{table}` does not exist.",
                        expected="Core master-data tables must exist.",
                        reproduce=[f"Run `SELECT to_regclass('{table}')`."],
                        evidence={},
                        owner="database owner",
                    )
                )
                continue
            existing = existing_columns(cur, table)
            selected = ["id", *[column for column in columns if column in existing]]
            cur.execute(f"SELECT {', '.join(qident(col) for col in selected)} FROM {qident(table)} ORDER BY id DESC LIMIT 10000")
            dirty_rows = []
            for row in cur.fetchall():
                for column in selected:
                    if column == "id":
                        continue
                    if looks_dirty_text(row.get(column)):
                        dirty_rows.append({"id": row["id"], "column": column, "value": short_value(row.get(column))})
                        break
            if dirty_rows:
                findings.append(
                    Finding(
                        severity="critical",
                        module="master_data",
                        bug_type="dirty_master_data",
                        location=table,
                        title="Master data contains dirty text",
                        actual=f"{len(dirty_rows)} sampled rows contain dirty text.",
                        expected="Master data must not contain mojibake, replacement characters, or placeholder question marks.",
                        reproduce=[f"Open `{table}` master-data page.", "Search for the sampled row ids from the evidence."],
                        evidence={"sample": dirty_rows[:20], "sampled_dirty_rows": len(dirty_rows)},
                        owner="master data owner",
                    )
                )

        if (
            table_exists(cur, "purchase_requisition_items")
            and column_exists(cur, "purchase_requisition_items", "suggested_supplier_id")
            and column_exists(cur, "purchase_requisition_items", "estimated_price")
        ):
            count = scalar(
                cur,
                """
                SELECT COUNT(*)
                FROM purchase_requisition_items
                WHERE COALESCE(suggested_supplier_id,0) <= 0
                  AND COALESCE(estimated_price,0) <= 0
                """,
            )
            if count:
                findings.append(
                    Finding(
                        severity="medium",
                        module="purchase",
                        bug_type="process_blocker",
                        location="purchase_requisition_items",
                        title="Purchase request lines have no supplier and no estimated price",
                        actual=f"{count} lines have neither supplier nor estimated price.",
                        expected="Purchase request lines should retain enough information for downstream purchase order creation.",
                        reproduce=["Open purchase request list.", "Filter lines with empty supplier and zero estimated price."],
                        evidence={"row_count": int(count)},
                        owner="purchase owner",
                    )
                )

        negative_inventory = 0
        if table_exists(cur, "inventory_balances"):
            negative_inventory = int(
                scalar(cur, "SELECT COUNT(*) FROM inventory_balances WHERE COALESCE(quantity,0) < 0") or 0
            )
        if negative_inventory:
            findings.append(
                Finding(
                    severity="high",
                    module="inventory",
                    bug_type="negative_stock",
                    location="inventory_balances",
                    title="Negative inventory balance exists",
                    actual=f"{negative_inventory} balance rows are negative.",
                    expected="Negative stock should be blocked or explicitly approved by policy.",
                    reproduce=["Open inventory balance query.", "Filter quantity less than zero."],
                    evidence={"row_count": negative_inventory},
                    owner="warehouse owner",
                )
            )

        cur.execute(
            """
            SELECT table_name, column_name, numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema='public'
              AND column_name IN ('total_amount','amount','amount_with_tax','tax_amount','unit_price','unit_cost','quantity')
              AND data_type='numeric'
              AND (numeric_precision IS NULL OR numeric_precision < 10 OR numeric_scale IS NULL)
            ORDER BY table_name, column_name
            LIMIT 100
            """
        )
        risky_columns = [dict(row) for row in cur.fetchall()]
        if risky_columns:
            findings.append(
                Finding(
                    severity="low",
                    module="database",
                    bug_type="schema_precision_risk",
                    location="numeric document columns",
                    title="Amount or quantity columns have weak numeric precision",
                    actual=f"{len(risky_columns)} numeric columns have missing or small precision/scale.",
                    expected="ERP amount and quantity columns should have explicit precision and scale.",
                    reproduce=["Run ERP Bug Hunter and inspect JSON evidence."],
                    evidence={"columns": risky_columns[:30]},
                    owner="database owner",
                )
            )


def audit_full_system_simulation(findings: list[Finding]) -> None:
    code, output = run_command([str(ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/audit_full_system_operator_simulation.py"])
    add_command_finding(findings, "scripts/audit_full_system_operator_simulation.py", code, output, "critical")
    if not FULL_SYSTEM_OUT.exists():
        findings.append(
            Finding(
                severity="critical",
                module="system",
                bug_type="missing_audit_output",
                location=str(FULL_SYSTEM_OUT.relative_to(ROOT)),
                title="Full-system simulation did not produce JSON output",
                actual="Expected output file is missing.",
                expected="Workflow simulation should write a machine-readable report.",
                reproduce=["Run `scripts/audit_full_system_operator_simulation.py`."],
                evidence={"command_output": output[-2000:]},
                owner="system administrator",
            )
        )
        return
    data = json.loads(FULL_SYSTEM_OUT.read_text(encoding="utf-8"))
    for row in data.get("page_access", []):
        if not row.get("ok"):
            findings.append(
                Finding(
                    severity="critical",
                    module="page",
                    bug_type="page_access_failed",
                    location=row.get("path", ""),
                    title="Core operator page failed simulation",
                    actual=f"Status code {row.get('status_code')}.",
                    expected="Core operator pages should load for admin audit user.",
                    reproduce=[f"Open `{row.get('path')}` as admin."],
                    evidence=row,
                    owner="route owner",
                )
            )
        if row.get("mojibake"):
            findings.append(
                Finding(
                    severity="critical",
                    module="page",
                    bug_type="visible_mojibake",
                    location=row.get("path", ""),
                    title="Core operator page contains mojibake",
                    actual="Simulation detected dirty visible text.",
                    expected="Operator-facing pages must not contain mojibake.",
                    reproduce=[f"Open `{row.get('path')}` as admin."],
                    evidence=row,
                    owner="route owner",
                )
            )
    for name, result in data.get("post_checks", {}).items():
        if not result.get("ok"):
            findings.append(
                Finding(
                    severity="critical",
                    module="document",
                    bug_type="save_failed",
                    location=name,
                    title="Document save simulation failed",
                    actual=str(result.get("blocked_reason") or result.get("message") or result),
                    expected="Core document save should complete and reconcile generated data.",
                    reproduce=[f"Run full-system simulation.", f"Inspect post check `{name}`."],
                    evidence=result,
                    owner="document workflow owner",
                )
            )
    for key, rows in data.get("business_blockers", {}).items():
        if key == "schema_amount_quantity_risks":
            continue
        if rows:
            findings.append(
                Finding(
                    severity="high",
                    module="business_loop",
                    bug_type="business_blocker",
                    location=key,
                    title=f"Business blocker queue is not empty: {key}",
                    actual=f"{len(rows)} rows were found.",
                    expected="Core blocker queues should be empty or owned with next action.",
                    reproduce=["Run full-system simulation.", f"Inspect `{key}` in the JSON output."],
                    evidence={"sample": rows[:20], "row_count": len(rows)},
                    owner="business process owner",
                )
            )


def audit_frontend_browser(findings: list[Finding]) -> None:
    code, output = run_command([str(ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/erp_frontend_bug_audit.py"])
    loaded_frontend_report = False
    if FRONTEND_JSON.exists():
        loaded_frontend_report = True
        for item in json.loads(FRONTEND_JSON.read_text(encoding="utf-8")):
            findings.append(
                Finding(
                    severity=item.get("severity", "high"),
                    module=item.get("module", "frontend"),
                    bug_type=item.get("bug_type", "frontend"),
                    location=item.get("location", ""),
                    title=item.get("title", "Frontend audit finding"),
                    actual=item.get("actual", ""),
                    expected=item.get("expected", ""),
                    reproduce=item.get("reproduce", []),
                    evidence=item.get("evidence", {}),
                    owner=item.get("owner", "frontend owner"),
                )
            )
    if not loaded_frontend_report:
        add_command_finding(findings, "scripts/erp_frontend_bug_audit.py", code, output, "high")


def audit_gates(findings: list[Finding]) -> None:
    commands = [
        ("source_integrity", [str(ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/source_integrity_audit.py"], "critical"),
        ("source_mojibake", [str(ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/audit_source_mojibake.py"], "critical"),
        ("database_mojibake", [str(ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/audit_database_mojibake.py"], "critical"),
        ("script_quarantine", [str(ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/script_quarantine.py", "--check"], "high"),
        ("prelaunch", [str(ROOT / ".venv" / "Scripts" / "python.exe"), "scripts/erp_prelaunch_audit.py"], "high"),
    ]
    for name, args, severity in commands:
        code, output = run_command(args)
        add_command_finding(findings, name, code, output, severity)


def severity_rank(severity: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(severity, 9)


def write_reports(findings: list[Finding]) -> None:
    findings.sort(key=lambda item: (severity_rank(item.severity), item.module, item.location, item.title))
    REPORT_JSON.parent.mkdir(exist_ok=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "ERP bug hunter: read-only page/database checks plus reversible workflow save simulation.",
        "finding_count": len(findings),
        "findings": [asdict(item) for item in findings],
    }
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for item in findings:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    lines = [
        "# ERP Bug Hunter Report",
        "",
        "## Scope",
        "",
        "- Read-only page, source, release, and database checks.",
        "- Reversible operator save simulation for core document workflows.",
        "- No ERP menu or business module is added by this script.",
        "",
        "## Summary",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Findings: `{len(findings)}`",
        f"- Critical: `{counts.get('critical', 0)}`",
        f"- High: `{counts.get('high', 0)}`",
        f"- Medium: `{counts.get('medium', 0)}`",
        f"- Low: `{counts.get('low', 0)}`",
        "",
        "## Findings",
        "",
    ]
    if not findings:
        lines.append("- No automated findings.")
    for index, item in enumerate(findings, 1):
        lines.extend(
            [
                f"### {index}. {item.title}",
                "",
                f"- Severity: `{item.severity}`",
                f"- Module: `{item.module}`",
                f"- Type: `{item.bug_type}`",
                f"- Location: `{item.location}`",
                f"- Owner: `{item.owner}`",
                f"- Actual: {item.actual}",
                f"- Expected: {item.expected}",
                "- Reproduce:",
            ]
        )
        lines.extend(f"  - {step}" for step in item.reproduce)
        lines.append(f"- Evidence: see `{REPORT_JSON.relative_to(ROOT)}` finding index `{index - 1}`")
        lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    findings: list[Finding] = []
    audit_gates(findings)
    audit_runtime_pages(findings)
    audit_database(findings)
    audit_full_system_simulation(findings)
    audit_frontend_browser(findings)
    write_reports(findings)
    print(f"report={REPORT_MD}")
    print(f"json={REPORT_JSON}")
    print(f"findings={len(findings)}")
    for severity in ("critical", "high", "medium", "low"):
        count = sum(1 for item in findings if item.severity == severity)
        print(f"{severity}={count}")
    for item in findings[:20]:
        safe_print(f"{item.severity} | {item.module} | {item.location} | {item.title}")
    return 1 if any(item.severity in {"critical", "high"} for item in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
