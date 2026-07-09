from pathlib import Path
import csv
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "validate_trial_issue_log.py"

HEADERS = [
    "编号",
    "发现时间",
    "岗位",
    "账号",
    "页面",
    "销售订单号",
    "项目号",
    "机号",
    "问题描述",
    "是否阻断",
    "阻断环节",
    "责任归口",
    "首要处理人",
    "处理状态",
    "处理结果",
    "关闭时间",
    "备注",
]


def run_validator(path):
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def parse_summary(output):
    for line in output.splitlines():
        if line.startswith("rows="):
            parts = {}
            for item in line.split():
                if "=" in item:
                    key, value = item.split("=", 1)
                    parts[key] = value
            return parts
    return {}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def valid_rows():
    return [
        {
            "编号": "TR-T-001",
            "发现时间": "2026-05-26 09:30",
            "岗位": "仓库",
            "账号": "pilot_warehouse",
            "页面": "/inventory/outbound",
            "销售订单号": "SO-GT-TRIAL-20260526-001",
            "项目号": "PJ-GT-TRIAL-20260526-001",
            "机号": "SN-GT-TRIAL-20260526-001",
            "问题描述": "Outbound page cannot submit project material.",
            "是否阻断": "是",
            "阻断环节": "仓库",
            "责任归口": "仓库",
            "首要处理人": "warehouse owner",
            "处理状态": "处理中",
            "处理结果": "",
            "关闭时间": "",
            "备注": "synthetic open blocker",
        },
        {
            "编号": "TR-T-002",
            "发现时间": "2026-05-26 10:00",
            "岗位": "售后",
            "账号": "pilot_service",
            "页面": "/service-orders",
            "销售订单号": "SO-GT-TRIAL-20260526-001",
            "项目号": "PJ-GT-TRIAL-20260526-001",
            "机号": "SN-GT-TRIAL-20260526-001",
            "问题描述": "Service detail text was corrected.",
            "是否阻断": "是",
            "阻断环节": "售后",
            "责任归口": "售后",
            "首要处理人": "service owner",
            "处理状态": "已处理",
            "处理结果": "Runtime text fixed.",
            "关闭时间": "2026-05-26 11:00",
            "备注": "synthetic closed blocker",
        },
    ]


def main():
    checks = []
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        ok_path = tmpdir / "valid_issue_log.csv"
        write_csv(ok_path, valid_rows())
        code, out, err = run_validator(ok_path)
        summary = parse_summary(out)
        checks.append(("valid_sample_exit", code == 0, code))
        checks.append(("valid_sample_rows", summary.get("rows") == "2", summary.get("rows")))
        checks.append(("valid_sample_errors", summary.get("errors") == "0", summary.get("errors")))
        checks.append(("valid_sample_open_blockers", summary.get("open_blockers") == "1", summary.get("open_blockers")))

        bad_rows = valid_rows()
        bad_rows[0]["编号"] = ""
        bad_path = tmpdir / "invalid_issue_log.csv"
        write_csv(bad_path, bad_rows)
        code, out, err = run_validator(bad_path)
        summary = parse_summary(out)
        checks.append(("invalid_sample_exit", code != 0, code))
        checks.append(("invalid_sample_errors", int(summary.get("errors") or 0) >= 1, summary.get("errors")))

    failures = [(name, detail) for name, ok, detail in checks if not ok]
    print("trial_issue_log_validator_audit=ok" if not failures else "trial_issue_log_validator_audit=failed")
    print(f"checked_items={len(checks)}")
    for name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
