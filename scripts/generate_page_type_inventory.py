from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = ROOT / "MENU_ROLLOUT_CLASSIFICATION.md"
OUTPUT = ROOT / "logs" / "page_type_inventory.md"

ROW_RE = re.compile(
    r"^\|\s*`(?P<path>[^`]+)`\s*\|\s*(?P<page_type>[^|]+?)\s*\|\s*`(?P<level>[^`]+)`\s*\|\s*(?P<reason>.*?)\s*\|$"
)


def parse_rows():
    rows = []
    for line in CLASSIFICATION.read_text(encoding="utf-8-sig").splitlines():
        match = ROW_RE.match(line.strip())
        if not match:
            continue
        rows.append(
            {
                "path": match.group("path").strip(),
                "page_type": match.group("page_type").strip(),
                "level": match.group("level").strip(),
                "reason": match.group("reason").strip(),
            }
        )
    return rows


def render(rows):
    counts = {}
    for row in rows:
        counts[row["level"]] = counts.get(row["level"], 0) + 1
    lines = [
        "# Page Type Inventory",
        "",
        "Generated from `MENU_ROLLOUT_CLASSIFICATION.md`.",
        "",
        "## Summary",
        "",
        "| Level | Count |",
        "|---|---:|",
    ]
    for level in ("live", "fix", "readonly", "internal", "hidden"):
        lines.append(f"| `{level}` | {counts.get(level, 0)} |")
    lines.extend(
        [
            "",
            "## Routes",
            "",
            "| Path | Page Type | Level | Reason / Next Action |",
            "|---|---|---|---|",
        ]
    )
    for row in rows:
        lines.append(f"| `{row['path']}` | {row['page_type']} | `{row['level']}` | {row['reason']} |")
    lines.append("")
    return "\n".join(lines)


def main():
    rows = parse_rows()
    if not rows:
        print("page_type_inventory=failed")
        print("failed | no classification rows parsed")
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(rows), encoding="utf-8")
    print("page_type_inventory=ok")
    print(f"output={OUTPUT.relative_to(ROOT)}")
    print(f"routes={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
