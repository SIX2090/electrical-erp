from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (ROOT / "templates", ROOT / "routes", ROOT / "scripts", ROOT / "services")
SUFFIXES = {".html", ".py"}

# Typical characters produced when UTF-8 Chinese is decoded as GBK/ANSI and
# then saved back as UTF-8. Store as code points so this detector cannot become
# a new source of mojibake.
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
}
DIRTY_CHAR_CODEPOINTS = {0x20AC, 0x2122, 0x0153}


def has_mojibake(text: str) -> bool:
    return any(ord(ch) in DIRTY_CODEPOINTS or ord(ch) in DIRTY_CHAR_CODEPOINTS for ch in text)


def iter_files():
    for base in SCAN_DIRS:
        for path in base.rglob("*"):
            if path.suffix.lower() in SUFFIXES and "__pycache__" not in path.parts:
                yield path


def main() -> int:
    findings: list[tuple[str, int, str]] = []
    for path in sorted(iter_files()):
        rel = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if has_mojibake(line):
                findings.append((rel, line_no, line.strip()[:220]))

    print(f"source_mojibake_findings={len(findings)}")
    for rel, line_no, line in findings[:200]:
        safe_line = line.encode("ascii", "backslashreplace").decode("ascii")
        print(f"{rel}:{line_no}: {safe_line}")
    if len(findings) > 200:
        print(f"... truncated {len(findings) - 200} findings")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
