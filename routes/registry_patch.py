"""Disabled legacy one-off patch script.

This file used to rewrite routes/registry.py by matching large source strings.
Those embedded strings contained mojibake, so rerunning the script could spread
corrupt Chinese labels back into active ERP code.

Do not execute this module. Keep it only as a tombstone so old references fail
with a clear reason instead of silently mutating source files.
"""

raise SystemExit(
    "routes/registry_patch.py is disabled. Use reviewed patches or migrations; "
    "do not run legacy source-rewrite scripts."
)
