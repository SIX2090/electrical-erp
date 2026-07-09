"""Pre-delivery audit gate.

Runs the canonical audit suite defined in AGENTS.md "Verification" in order
and prints a single PASS/FAIL summary. Exit code is 0 only when every gate
passes. This is an orchestrator only - it does NOT modify, silence, or
bypass any audit script. If an audit fails, fix the application code.

Usage:
    python scripts/pre_delivery_gate.py
    python scripts/pre_delivery_gate.py --skip-inventory   # skip inventory gate
    python scripts/pre_delivery_gate.py --skip-nav          # skip nav/permission gates

Gates (in order):
    1. compileall         - python -m compileall app.py routes services scripts
    2. source_integrity   - source_integrity=ok, mojibake_findings=0
    3. prelaunch          - errors=0, warnings=0, core_pages=34
    4. crud_completeness  - targets=46, ok=46, errors=0
    5. inventory_balance  - findings=0 (requires PG_PASSWORD, skip with --skip-inventory)
    6. visible_navigation - checked_users=7 (requires INVENTORY_NAV_MODE=gt_pilot + PG_PASSWORD)
    7. direct_access      - PASS (requires INVENTORY_NAV_MODE=gt_pilot + PG_PASSWORD)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _run(cmd: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    """Run a command, return (exit_code, stdout, stderr)."""
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout, proc.stderr


def _check(pattern: str, text: str) -> bool:
    return re.search(pattern, text) is not None


class Gate:
    """One audit gate: name, runner, and pass predicate."""

    def __init__(self, name: str, run_fn, pass_fn, describe_fn):
        self.name = name
        self.run_fn = run_fn
        self.pass_fn = pass_fn
        self.describe_fn = describe_fn
        self.exit_code = 0
        self.output = ""
        self.detail = ""

    def execute(self, base_env: dict[str, str]) -> bool:
        self.exit_code, self.output, self.detail = self.run_fn(base_env)
        return self.pass_fn(self.output, self.detail, self.exit_code)


def gate_compileall():
    def run(env):
        return _run([PYTHON, "-m", "compileall", "app.py", "routes", "services", "scripts"], env)

    def passed(stdout, stderr, code):
        return code == 0 and "error" not in stderr.lower()

    def describe(stdout, stderr, code):
        return "No syntax errors" if passed(stdout, stderr, code) else f"compile errors (code={code})"

    return Gate("compileall", run, passed, describe)


def gate_source_integrity():
    def run(env):
        return _run([PYTHON, "scripts/source_integrity_audit.py"], env)

    def passed(stdout, stderr, code):
        return code == 0 and _check(r"source_integrity=ok", stdout) and _check(r"source_mojibake_findings=0", stdout)

    def describe(stdout, stderr, code):
        return "source_integrity=ok, mojibake=0" if passed(stdout, stderr, code) else f"FAIL: {stdout.strip()[-200:]}"

    return Gate("source_integrity", run, passed, describe)


def gate_prelaunch():
    def run(env):
        return _run([PYTHON, "scripts/erp_prelaunch_audit.py"], env)

    def passed(stdout, stderr, code):
        return (
            code == 0
            and _check(r"errors=0", stdout)
            and _check(r"core_pages=34", stdout)
        )

    def describe(stdout, stderr, code):
        m = re.search(r"(core_pages=\d+ errors=\d+ warnings=\d+)", stdout)
        return m.group(1) if m else ("FAIL: " + stdout.strip()[-200:])

    return Gate("prelaunch", run, passed, describe)


def gate_crud():
    def run(env):
        return _run([PYTHON, "scripts/audit_erp_crud_completeness.py"], env)

    def passed(stdout, stderr, code):
        return (
            code == 0
            and _check(r"erp_crud_targets=46", stdout)
            and _check(r"\bok=46\b", stdout)
            and _check(r"errors=0", stdout)
        )

    def describe(stdout, stderr, code):
        m = re.search(r"(erp_crud_targets=\d+ ok=\d+ warnings=\d+ errors=\d+)", stdout)
        return m.group(1) if m else ("FAIL: " + stdout.strip()[-200:])

    return Gate("crud_completeness", run, passed, describe)


def gate_inventory():
    def run(env):
        env2 = dict(env)
        env2.setdefault("PG_PASSWORD", "admin")
        return _run([PYTHON, "scripts/audit_inventory_balance_consistency.py"], env2)

    def passed(stdout, stderr, code):
        return code == 0 and _check(r"findings=0", stdout)

    def describe(stdout, stderr, code):
        m = re.search(r"findings=(\d+)", stdout)
        return f"findings={m.group(1)}" if m else ("FAIL: " + stdout.strip()[-200:])

    return Gate("inventory_balance", run, passed, describe)


def gate_visible_nav():
    def run(env):
        env2 = dict(env)
        env2.setdefault("PG_PASSWORD", "admin")
        env2.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
        return _run([PYTHON, "scripts/audit_trial_visible_navigation.py"], env2)

    def passed(stdout, stderr, code):
        return code == 0 and _check(r"checked_users=7", stdout)

    def describe(stdout, stderr, code):
        m = re.search(r"checked_users=(\d+)", stdout)
        return f"checked_users={m.group(1)}" if m else ("FAIL: " + stdout.strip()[-200:])

    return Gate("visible_navigation", run, passed, describe)


def gate_direct_access():
    def run(env):
        env2 = dict(env)
        env2.setdefault("PG_PASSWORD", "admin")
        env2.setdefault("INVENTORY_NAV_MODE", "gt_pilot")
        return _run([PYTHON, "scripts/audit_trial_direct_access_matrix.py"], env2)

    def passed(stdout, stderr, code):
        return code == 0 and _check(r"trial_direct_access_matrix_audit=ok", stdout)

    def describe(stdout, stderr, code):
        if passed(stdout, stderr, code):
            return "trial_direct_access_matrix_audit=ok"
        failed = re.findall(r"failed \| [^\n]+", stdout)
        return f"{len(failed)} failures" + (f": {failed[0][:120]}" if failed else "")

    return Gate("direct_access", run, passed, describe)


def main() -> int:
    parser = argparse.ArgumentParser(description="Pre-delivery audit gate")
    parser.add_argument("--skip-inventory", action="store_true", help="skip inventory balance gate")
    parser.add_argument("--skip-nav", action="store_true", help="skip nav/permission gates")
    parser.add_argument("--verbose", action="store_true", help="print full stdout of each gate")
    args = parser.parse_args()

    base_env = dict(os.environ)

    gates = [
        gate_compileall(),
        gate_source_integrity(),
        gate_prelaunch(),
        gate_crud(),
    ]
    if not args.skip_inventory:
        gates.append(gate_inventory())
    if not args.skip_nav:
        gates.append(gate_visible_nav())
        gates.append(gate_direct_access())

    print("=" * 60)
    print("PRE-DELIVERY AUDIT GATE")
    print("=" * 60)

    results: list[tuple[str, bool, str]] = []
    all_passed = True
    for g in gates:
        ok = g.execute(base_env)
        results.append((g.name, ok, g.describe_fn(g.output, g.detail, g.exit_code)))
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {g.name:<22} {g.describe_fn(g.output, g.detail, g.exit_code)}")
        if not ok:
            all_passed = False
        if args.verbose:
            print("    " + g.output.replace("\n", "\n    ")[:800])

    print("-" * 60)
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"Result: {passed}/{total} gates passed")
    if all_passed:
        print("ALL GATES PASSED - safe to deliver")
        return 0
    failed_names = [name for name, ok, _ in results if not ok]
    print(f"FAILED GATES: {', '.join(failed_names)}")
    print("Fix the application code. Do NOT modify audit scripts to make them pass.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
