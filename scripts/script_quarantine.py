from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "scripts" / "quarantined_script_manifest.json"

# Store suspicious characters as code points so this guard cannot introduce
# new mojibake while detecting historical mojibake.
DIRTY_CODEPOINTS = {
    0xFFFD,
    0x95C1,
    0x95BF,
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
    0x5BEF,
    0x6FEE,
    0x8930,
    0x7BDB,
    0x7DCB,
    0x7EEF,
    0x95AB,
    0x9A9E,
    0xFE3D,
    0x510F,
    0x6E1A,
    0x7C32,
    0x30E5,
    0x7C31,
    0x6944,
    0x935F,
}
DIRTY_CHAR_CODEPOINTS = {0x20AC, 0x2122, 0x0153}
MOJIBAKE_MARKER_CODEPOINTS = {
    0x7019,
    0x95BF,
    0x5A4A,
    0x5A34,
    0x7ED7,
    0x68E3,
    0x6FC2,
    0x93C2,
    0x935A,
    0x7EBE,
    0x941F,
    0x6978,
    0x95B8,
    0x95BB,
    0x9422,
    0x6434,
}
WRITE_TOKENS = (
    "INSERT INTO",
    "UPDATE ",
    "DELETE FROM",
    "ALTER TABLE",
    "ON CONFLICT",
    "_execute_db(",
    "_execute_and_return(",
    "connect_db(",
)
MASTER_DATA_TOKENS = (
    "products",
    "customers",
    "suppliers",
    "warehouses",
    "locations",
    "units",
    "work_centers",
    "production_routings",
    "routing_operations",
    "boms",
    "bom_items",
    "sales_orders",
    "purchase_orders",
    "customer_receivables",
    "supplier_payables",
    "mrp_plans",
    "mrp_requirements",
)


@dataclass(frozen=True)
class BlockedScript:
    path: str
    quarantine_path: str
    reason: str
    owner: str
    status: str


def read_manifest() -> list[BlockedScript]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return [BlockedScript(**item) for item in payload.get("blocked_scripts", [])]


def has_mojibake(text: str) -> bool:
    if any(ord(ch) in DIRTY_CODEPOINTS or ord(ch) in DIRTY_CHAR_CODEPOINTS for ch in text):
        return True
    return sum(1 for ch in text if ord(ch) in MOJIBAKE_MARKER_CODEPOINTS) >= 6


def writes_erp_data(text: str) -> bool:
    upper_text = text.upper()
    has_write = any(token in upper_text for token in WRITE_TOKENS[:5]) or any(token in text for token in WRITE_TOKENS[5:])
    return has_write and any(token in text for token in MASTER_DATA_TOKENS)


def is_blocking_stub(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "SCRIPT_QUARANTINED = True" in text and "raise SystemExit(main())" in text


def audit_quarantine() -> list[str]:
    findings: list[str] = []
    manifest_entries = read_manifest()
    active_paths = {entry.path for entry in manifest_entries}

    for entry in manifest_entries:
        active = ROOT / entry.path
        quarantined = ROOT / entry.quarantine_path
        if entry.status != "quarantined":
            findings.append(f"{entry.path}: manifest status must be quarantined")
        if active.suffix != ".py":
            findings.append(f"{entry.path}: active path must stay a Python entrypoint")
        if not is_blocking_stub(active):
            findings.append(f"{entry.path}: active entrypoint is not a quarantine blocker")
        if not quarantined.exists():
            findings.append(f"{entry.path}: missing quarantined payload {entry.quarantine_path}")
            continue
        if quarantined.suffix == ".py":
            findings.append(f"{entry.quarantine_path}: quarantined payload must not remain directly runnable as .py")
        text = quarantined.read_text(encoding="utf-8", errors="ignore")
        if not writes_erp_data(text):
            findings.append(f"{entry.quarantine_path}: expected ERP write evidence was not detected")

    for script_path in sorted((ROOT / "scripts").glob("*.py")):
        rel = script_path.relative_to(ROOT).as_posix()
        if rel in active_paths or rel == "scripts/script_quarantine.py":
            continue
        text = script_path.read_text(encoding="utf-8", errors="ignore")
        if has_mojibake(text) and writes_erp_data(text):
            findings.append(f"{rel}: dirty ERP writer is not quarantined")
    return findings


def list_blocked() -> int:
    entries = read_manifest()
    print(f"blocked_scripts={len(entries)}")
    for entry in entries:
        print(f"{entry.path} | {entry.status} | {entry.quarantine_path} | {entry.reason}")
    return 0


def run_blocked(script_name: str) -> int:
    for entry in read_manifest():
        if script_name in {entry.path, Path(entry.path).name}:
            print(f"blocked_script={entry.path}")
            print(f"quarantine_path={entry.quarantine_path}")
            print(f"reason={entry.reason}")
            return 2
    print(f"script_not_quarantined={script_name}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and list quarantined dirty ERP scripts.")
    parser.add_argument("--list-blocked", action="store_true", help="List scripts blocked by quarantine.")
    parser.add_argument("--check", action="store_true", help="Verify quarantine manifest and active blockers.")
    parser.add_argument("--run", metavar="SCRIPT", help="Refuse execution for a quarantined script name or path.")
    args = parser.parse_args()

    if args.list_blocked:
        return list_blocked()
    if args.run:
        return run_blocked(args.run)

    findings = audit_quarantine()
    if findings:
        print("script_quarantine=failed")
        for item in findings:
            print(item)
        return 1
    print("script_quarantine=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
