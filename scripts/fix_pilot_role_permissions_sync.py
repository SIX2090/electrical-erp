"""Fix pilot_role_permissions table to match Python default configuration.

The database had stale permission_groups that were missing the 'master' group
for most roles, causing 364 direct access matrix audit failures.
This script syncs the database to match PILOT_DEFAULT_ROLE_GROUPS and
default_actions_for_role from services.pilot_permissions.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import psycopg2

from services.pilot_permissions import (
    PILOT_DEFAULT_ROLE_GROUPS,
    default_actions_for_role,
)

PG_PASSWORD = os.environ.get("PG_PASSWORD", "admin")

def main():
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        database="wms",
        user="postgres",
        password=PG_PASSWORD,
    )
    cur = conn.cursor()

    print("=== Before fix ===")
    cur.execute("SELECT role, permission_groups FROM pilot_role_permissions ORDER BY role")
    for row in cur.fetchall():
        print(f"  {row[0]:20s} groups={row[1]}")

    print("\n=== Applying fix ===")
    for role, groups in PILOT_DEFAULT_ROLE_GROUPS.items():
        groups_str = ",".join(sorted(groups))
        actions = default_actions_for_role(role)
        actions_json = json.dumps(actions, ensure_ascii=False)
        cur.execute(
            """
            INSERT INTO pilot_role_permissions (role, permission_groups, action_permissions, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (role)
            DO UPDATE SET permission_groups=EXCLUDED.permission_groups,
                          action_permissions=EXCLUDED.action_permissions,
                          updated_at=NOW()
            """,
            (role, groups_str, actions_json),
        )
        print(f"  {role:20s} -> groups={groups_str}, actions={len(actions)} features")

    conn.commit()

    print("\n=== After fix ===")
    cur.execute("SELECT role, permission_groups FROM pilot_role_permissions ORDER BY role")
    for row in cur.fetchall():
        print(f"  {row[0]:20s} groups={row[1]}")

    cur.close()
    conn.close()
    print("\nDone. Re-run audit_trial_direct_access_matrix.py to verify.")


if __name__ == "__main__":
    main()
