from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_role_permission_matrix import effective_role_matrix, load_role_rows, verify  # noqa: E402
from services.pilot_permissions import (  # noqa: E402
    PILOT_PERMISSION_ACTIONS,
    PILOT_PERMISSION_FEATURES,
    PILOT_PERMISSION_GROUPS,
    PILOT_ROLE_LABELS,
)


REPORT_DIR = ROOT / "reports"
MARKDOWN_PATH = REPORT_DIR / "role_permission_matrix_report.md"
CSV_PATH = REPORT_DIR / "role_permission_matrix.csv"


def action_label_map() -> dict[str, str]:
    return {item["key"]: item["label"] for item in PILOT_PERMISSION_ACTIONS}


def group_label_map() -> dict[str, str]:
    return {item["key"]: item["label"] for item in PILOT_PERMISSION_GROUPS}


def write_csv(rows: list[dict]) -> None:
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["role", "role_label", "group", "group_label", "feature", "feature_label", "path", "actions"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict], findings: list, summary: dict) -> None:
    lines = [
        "# Role Permission Matrix Report",
        "",
        "## Summary",
        "",
        f"- Roles: `{summary['roles']}`",
        f"- Permission features: `{summary['features']}`",
        f"- Application routes: `{summary['routes']}`",
        f"- Findings: `{summary['findings']}`",
        "",
        "## Findings",
        "",
    ]
    if findings:
        for item in findings:
            lines.append(f"- `{item.code}` `{item.role}` `{item.source}`: {item.detail}")
    else:
        lines.append("- No findings.")
    lines.extend(["", "## Matrix", ""])
    current_role = None
    for row in rows:
        if row["role"] != current_role:
            current_role = row["role"]
            lines.extend(["", f"### {row['role']} - {row['role_label']}", ""])
            lines.append("| Group | Feature | Path | Actions |")
            lines.append("| --- | --- | --- | --- |")
        lines.append(
            f"| {row['group_label']} | {row['feature_label']} | `{row['path']}` | {row['actions']} |"
        )
    MARKDOWN_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_matrix_rows() -> list[dict]:
    action_labels = action_label_map()
    group_labels = group_label_map()
    role_rows = load_role_rows()
    rows: list[dict] = []
    for role, role_label in PILOT_ROLE_LABELS.items():
        groups, permissions = effective_role_matrix(role, role_rows.get(role))
        for feature in PILOT_PERMISSION_FEATURES:
            if role != "admin" and feature["group"] not in groups:
                continue
            actions = permissions.get(feature["key"], [])
            action_text = ", ".join(action_labels.get(action, action) for action in actions)
            rows.append(
                {
                    "role": role,
                    "role_label": role_label,
                    "group": feature["group"],
                    "group_label": group_labels.get(feature["group"], feature["group"]),
                    "feature": feature["key"],
                    "feature_label": feature["label"],
                    "path": feature["path"],
                    "actions": action_text,
                }
            )
    return rows


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    findings, summary = verify()
    rows = build_matrix_rows()
    write_csv(rows)
    write_markdown(rows, findings, summary)
    print("role_permission_report=ok" if not findings else "role_permission_report=with_findings")
    print(f"matrix_rows={len(rows)}")
    print(f"markdown={MARKDOWN_PATH}")
    print(f"csv={CSV_PATH}")
    print(f"findings_json={ROOT / 'reports' / 'role_permission_matrix_findings.json'}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
