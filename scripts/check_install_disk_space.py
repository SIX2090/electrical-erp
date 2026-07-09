from __future__ import annotations

import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUIRED_MB = 1200


def main(argv: list[str]) -> int:
    required_mb = int(argv[1]) if len(argv) > 1 else DEFAULT_REQUIRED_MB
    usage = shutil.disk_usage(ROOT)
    free_mb = usage.free // (1024 * 1024)
    print(f"install_disk_free_mb={free_mb}")
    print(f"install_disk_required_mb={required_mb}")
    if free_mb < required_mb:
        print(
            "error: insufficient free disk space for PostgreSQL restore; "
            "move the installer to a larger local drive or free space before installing."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
