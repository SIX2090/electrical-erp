from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILES = [
    ROOT / "release" / "trial_run" / "trial_run_go_no_go.md",
    ROOT / "release" / "trial_run" / "trial_machine_candidates.md",
    ROOT / "release" / "trial_run" / "trial_machine_candidates.csv",
    ROOT / "release" / "trial_run" / "NEXT_SESSION_HANDOFF.md",
    ROOT / "logs" / "go_live_checklist.md",
    ROOT / "logs" / "erp_prelaunch_audit.md",
    ROOT / "logs" / "page_type_inventory.md",
]

REQUIRED_TEXT = {
    ROOT / "release" / "trial_run" / "trial_run_go_no_go.md": (
        "Decision: **GO**",
        "Trial POST action scope",
        "audit_trial_post_action_scope.py",
    ),
    ROOT / "release" / "trial_run" / "NEXT_SESSION_HANDOFF.md": (
        "Current first-machine trial decision: `GO`",
        "Trial POST action scope",
        "audit_trial_post_action_scope.py",
    ),
}

DIRTY_CODEPOINTS = {0xFFFD, 0x95C1, 0x7487, 0x7F02}


def has_dirty_text(text):
    return "???" in text or any(ord(ch) in DIRTY_CODEPOINTS for ch in text)


def audit_release_documents():
    checks = []
    for path in RELEASE_FILES:
        rel = path.relative_to(ROOT)
        exists = path.exists()
        checks.append((str(rel), "exists", exists, "present" if exists else "missing"))
        if not exists:
            continue
        text = path.read_text(encoding="utf-8-sig")
        checks.append((str(rel), "dirty_markers", not has_dirty_text(text), "clean" if not has_dirty_text(text) else "dirty"))
        required_texts = REQUIRED_TEXT.get(path, ())
        if os.environ.get("TRIAL_RELEASE_ALLOW_PENDING_GO") == "1" and path.name == "trial_run_go_no_go.md":
            required_texts = tuple(item for item in required_texts if item != "Decision: **GO**")
        for required in required_texts:
            checks.append((str(rel), f"required_text:{required}", required in text, "present" if required in text else "missing"))
    return checks


def main():
    checks = audit_release_documents()
    failures = [(source, name, detail) for source, name, ok, detail in checks if not ok]
    print("trial_release_documents_audit=ok" if not failures else "trial_release_documents_audit=failed")
    print(f"checked_items={len(checks)}")
    for source, name, ok, detail in checks:
        print(f"{'ok' if ok else 'failed'} | {source} | {name} | {detail}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
