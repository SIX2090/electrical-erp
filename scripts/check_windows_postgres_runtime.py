from __future__ import annotations

import os
import platform
import sys


MIN_SUPPORTED_BUILD = 17763  # Windows Server 2019 / Windows 10 1809
LOCAL_HOSTS = {"", "127.0.0.1", "localhost", "::1"}


def _windows_build() -> int:
    if hasattr(sys, "getwindowsversion"):
        try:
            return int(sys.getwindowsversion().build)
        except (AttributeError, ValueError):
            pass
    try:
        return int(platform.version().split(".")[-1])
    except (ValueError, IndexError):
        return 0


def main() -> int:
    if os.name != "nt":
        print("windows_postgres_runtime_check=skipped_non_windows")
        return 0

    pg_host = os.environ.get("PG_HOST", "127.0.0.1").strip().lower()
    if pg_host not in LOCAL_HOSTS:
        print("windows_postgres_runtime_check=skipped_external_postgres")
        return 0

    if os.environ.get("ALLOW_UNSUPPORTED_WINDOWS_POSTGRES") == "1":
        print("windows_postgres_runtime_check=overridden")
        return 0

    build = _windows_build()
    print(f"windows_build={build}")
    if build and build < MIN_SUPPORTED_BUILD:
        print("unsupported_windows_for_bundled_postgres=1")
        print("Bundled PostgreSQL 18 requires Windows Server 2019 or newer.")
        print("Use Windows Server 2019/2022/2025, or configure PG_HOST to an external PostgreSQL server.")
        return 1

    print("windows_postgres_runtime_check=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
