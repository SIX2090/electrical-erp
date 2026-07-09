import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from routes.finance_routes import _upsert_cash_bank_journal_for_funds_lines


def main():
    calls = []
    account_ids = {"BANK-DEFAULT": 1, "000000": 1}

    def query_one(sql, params=None):
        if "FROM cash_bank_accounts" in sql:
            for value in params or ():
                if value in account_ids:
                    return {"id": account_ids[value]}
        return None

    def execute_db(sql, params=None):
        calls.append((sql, params or ()))

    lines = [
        {
            "line_no": 1,
            "bank_account": "BANK-DEFAULT",
            "amount": Decimal("600.00"),
            "fee_amount": Decimal("0"),
            "transaction_no": "TXN-001",
            "remark": "line one",
        },
        {
            "line_no": 2,
            "bank_account": "000000",
            "amount": Decimal("400.00"),
            "fee_amount": Decimal("2.00"),
            "transaction_no": "TXN-002",
            "remark": "line two",
        },
    ]

    _upsert_cash_bank_journal_for_funds_lines(
        query_one,
        execute_db,
        source_type="customer_receipt",
        source_id=100,
        source_no="CR-MULTI-AUDIT",
        doc_date="2026-06-16",
        direction="in",
        fund_lines=lines,
        partner_type="customer",
        partner_name="audit customer",
        project_code="PJ-AUDIT",
        serial_no="SN-AUDIT",
        summary="audit multiline receipt",
        created_by=1,
    )

    deletes = [call for call in calls if "DELETE FROM cash_bank_journal_entries" in call[0]]
    inserts = [call for call in calls if "INSERT INTO cash_bank_journal_entries" in call[0]]
    entry_nos = [params[2] for _sql, params in inserts]
    amounts = [params[6] for _sql, params in inserts]
    summaries = [params[11] for _sql, params in inserts]

    findings = []
    if len(deletes) != 1:
        findings.append(f"expected_one_delete got={len(deletes)}")
    if len(inserts) != 2:
        findings.append(f"expected_two_inserts got={len(inserts)}")
    if entry_nos != ["CBR-CR-MULTI-AUDIT-1", "CBR-CR-MULTI-AUDIT-2"]:
        findings.append(f"bad_entry_numbers {entry_nos}")
    if amounts != [Decimal("600.00"), Decimal("400.00")]:
        findings.append(f"bad_amounts {amounts}")
    if not all("funds line" in summary for summary in summaries):
        findings.append("missing_line_summary")
    if "fee 2.00" not in summaries[1]:
        findings.append("missing_fee_summary")

    if findings:
        print("finance_cash_bank_multiline_journal_audit=fail")
        for finding in findings:
            print(finding)
        return 1
    print("finance_cash_bank_multiline_journal_audit=ok")
    print("checked_lines=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
