from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional


VERSION_STATUS_DRAFT = "draft"
VERSION_STATUS_APPROVED = "approved"
VERSION_STATUS_RELEASED = "released"
VERSION_STATUS_OBSOLETE = "obsolete"

VERSION_STATUS_LABELS = {
    VERSION_STATUS_DRAFT: "草稿",
    VERSION_STATUS_APPROVED: "已审核",
    VERSION_STATUS_RELEASED: "已发布",
    VERSION_STATUS_OBSOLETE: "已作废",
}


def _as_dict(row) -> Dict[str, Any]:
    return dict(row or {})


def _clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_decimal(value, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value is None or str(value).strip() == "":
            return default
        return Decimal(str(value).strip())
    except Exception:
        return default


def list_versions(query_db, bom_id: int) -> List[Dict[str, Any]]:
    """List all versions of a BOM, newest first."""
    if not bom_id:
        return []
    rows = query_db(
        """
        SELECT bv.*, b.bom_no, b.product_id,
               p.code AS product_code, p.name AS product_name,
               p.specification AS product_specification,
               approver.username AS approver_name,
               creator.username AS creator_name
        FROM bom_versions bv
        LEFT JOIN boms b ON b.id=bv.bom_id
        LEFT JOIN products p ON p.id=b.product_id
        LEFT JOIN users approver ON approver.id=bv.approved_by
        LEFT JOIN users creator ON creator.id=bv.created_by
        WHERE bv.bom_id=%s
        ORDER BY
            CASE bv.status
                WHEN 'released' THEN 0
                WHEN 'approved' THEN 1
                WHEN 'draft' THEN 2
                ELSE 3
            END,
            bv.effective_date DESC NULLS LAST,
            bv.id DESC
        """,
        (int(bom_id),),
    )
    result = []
    for row in rows or []:
        item = _as_dict(row)
        item["status_label"] = VERSION_STATUS_LABELS.get(item.get("status"), item.get("status") or "")
        result.append(item)
    return result


def get_version(query_db, version_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific BOM version with header and items snapshot."""
    if not version_id:
        return None
    row = query_db(
        """
        SELECT bv.*, b.bom_no, b.product_id, b.bom_type, b.remark AS bom_remark,
               p.code AS product_code, p.name AS product_name,
               p.specification AS product_specification, p.unit AS product_unit,
               approver.username AS approver_name,
               creator.username AS creator_name
        FROM bom_versions bv
        LEFT JOIN boms b ON b.id=bv.bom_id
        LEFT JOIN products p ON p.id=b.product_id
        LEFT JOIN users approver ON approver.id=bv.approved_by
        LEFT JOIN users creator ON creator.id=bv.created_by
        WHERE bv.id=%s
        """,
        (int(version_id),),
        one=True,
    )
    if not row:
        return None
    item = _as_dict(row)
    item["status_label"] = VERSION_STATUS_LABELS.get(item.get("status"), item.get("status") or "")
    return item


def create_version(
    query_db,
    execute_db,
    execute_and_return,
    bom_id: int,
    version_no: str,
    change_note: str = "",
    created_by: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Create a new BOM version in draft status."""
    bom_id = _to_int(bom_id)
    if not bom_id:
        return None
    version_no = _clean(version_no)
    if not version_no:
        return None
    bom = query_db("SELECT id, bom_no FROM boms WHERE id=%s", (bom_id,), one=True)
    if not bom:
        return None
    existing = query_db(
        "SELECT id FROM bom_versions WHERE bom_id=%s AND version_no=%s",
        (bom_id, version_no),
        one=True,
    )
    if existing:
        return None
    row = execute_and_return(
        """
        INSERT INTO bom_versions (bom_id, version_no, status, change_note, created_by)
        VALUES (%s, %s, 'draft', %s, %s)
        RETURNING id, bom_id, version_no, status
        """,
        (bom_id, version_no, _clean(change_note) or "", _to_int(created_by)),
    )
    if not row:
        return None
    return _as_dict(row)


def approve_version(
    query_db,
    execute_db,
    version_id: int,
    approved_by: Optional[int] = None,
) -> bool:
    """Approve a draft version. Sets status='approved' and approved_at."""
    version_id = _to_int(version_id)
    if not version_id:
        return False
    row = query_db("SELECT id, status FROM bom_versions WHERE id=%s", (version_id,), one=True)
    if not row:
        return False
    current = _as_dict(row).get("status")
    if current != VERSION_STATUS_DRAFT:
        return False
    execute_db(
        """
        UPDATE bom_versions
        SET status='approved', approved_by=%s, approved_at=CURRENT_TIMESTAMP
        WHERE id=%s
        """,
        (_to_int(approved_by), version_id),
    )
    return True


def release_version(query_db, execute_db, version_id: int) -> bool:
    """Release an approved version. Sets status='released', effective_date=today,
    and expires previously released versions of the same BOM.

    Both UPDATEs run in a single statement via CTE so they commit atomically.
    """
    version_id = _to_int(version_id)
    if not version_id:
        return False
    row = query_db(
        "SELECT id, bom_id, status FROM bom_versions WHERE id=%s",
        (version_id,),
        one=True,
    )
    if not row:
        return False
    data = _as_dict(row)
    if data.get("status") not in {VERSION_STATUS_APPROVED, VERSION_STATUS_DRAFT}:
        return False
    today = date.today()
    # Use a CTE so both UPDATEs commit in a single atomic statement.
    execute_db(
        """
        WITH expire_old AS (
            UPDATE bom_versions
            SET status='obsolete', expire_date=%s
            WHERE bom_id=%s AND status='released' AND id<>%s
            RETURNING id
        )
        UPDATE bom_versions
        SET status='released', effective_date=COALESCE(effective_date, %s)
        WHERE id=%s
        """,
        (today, data["bom_id"], version_id, today, version_id),
    )
    return True


def obsolete_version(query_db, execute_db, version_id: int) -> bool:
    """Mark a version as obsolete."""
    version_id = _to_int(version_id)
    if not version_id:
        return False
    row = query_db("SELECT id, status FROM bom_versions WHERE id=%s", (version_id,), one=True)
    if not row:
        return False
    current = _as_dict(row).get("status")
    if current == VERSION_STATUS_OBSOLETE:
        return True
    execute_db(
        "UPDATE bom_versions SET status='obsolete' WHERE id=%s",
        (version_id,),
    )
    return True


def get_active_version(query_db, bom_id: int) -> Optional[Dict[str, Any]]:
    """Get the currently released version for a BOM."""
    bom_id = _to_int(bom_id)
    if not bom_id:
        return None
    row = query_db(
        """
        SELECT bv.*, b.bom_no, b.product_id,
               p.code AS product_code, p.name AS product_name,
               p.specification AS product_specification
        FROM bom_versions bv
        LEFT JOIN boms b ON b.id=bv.bom_id
        LEFT JOIN products p ON p.id=b.product_id
        WHERE bv.bom_id=%s AND bv.status='released'
        ORDER BY bv.effective_date DESC NULLS LAST, bv.id DESC
        LIMIT 1
        """,
        (bom_id,),
        one=True,
    )
    if not row:
        return None
    item = _as_dict(row)
    item["status_label"] = VERSION_STATUS_LABELS.get(item.get("status"), item.get("status") or "")
    return item
