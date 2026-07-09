import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import get_db_config
from services.app_runtime import connect_db


BAD_SOURCE_TOKENS = {
    "routes/finance_routes.py": [
        "AUTO-\" + hashlib.sha1",
        "INSERT INTO cash_bank_accounts\n            (account_code, account_name, account_type, bank_account_no, status, remark, created_by)",
    ],
    "scripts/backfill_cash_bank_journal.py": [
        "AUTO-",
        "hashlib",
        "INSERT INTO cash_bank_accounts",
    ],
}


def source_findings():
    findings = []
    for relative, tokens in BAD_SOURCE_TOKENS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in tokens:
            if token in text:
                findings.append(f"source_token_present file={relative} token={token!r}")
    return findings


def database_findings():
    findings = []
    with connect_db(get_db_config()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS active_count
                FROM cash_bank_accounts
                WHERE status='active'
                """
            )
            active_count = int((cur.fetchone() or {}).get("active_count") or 0)
            if active_count <= 0:
                findings.append("no_active_cash_bank_account")

            cur.execute(
                """
                SELECT account_code, account_name, remark
                FROM cash_bank_accounts
                WHERE account_code LIKE 'AUTO-%%'
                   OR COALESCE(remark,'') ILIKE %s
                   OR COALESCE(remark,'') ILIKE %s
                ORDER BY id
                LIMIT 20
                """,
                ("%\u81ea\u52a8\u751f\u6210%", "%\u5360\u4f4d%"),
            )
            for row in cur.fetchall():
                findings.append(
                    "placeholder_cash_bank_account "
                    f"code={row.get('account_code')} name={row.get('account_name')} remark={row.get('remark')}"
                )
    return findings


def main():
    findings = source_findings() + database_findings()
    if findings:
        print("finance_cash_bank_account_governance_audit=fail")
        for finding in findings:
            print(finding)
        return 1
    print("finance_cash_bank_account_governance_audit=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
