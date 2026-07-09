"""Approval routes: approval flow, pending approval list, and approval history."""
from flask import render_template


def columns(*items):
    return [{"key": key, "label": label} for key, label in items]


def approval_doc_type_label(flow_type):
    value = (flow_type or "").strip().lower()
    labels = {
        "sales_order": "\u9500\u552e\u8ba2\u5355\u5ba1\u6279",
        "purchase_order": "\u91c7\u8d2d\u8ba2\u5355\u5ba1\u6279",
        "purchase_requisition": "\u91c7\u8d2d\u7533\u8bf7\u5ba1\u6279",
        "purchase_request": "\u91c7\u8d2d\u7533\u8bf7\u5ba1\u6279",
        "subcontract_order": "\u59d4\u5916\u8ba2\u5355\u5ba1\u6279",
        "work_order": "\u751f\u4ea7\u5de5\u5355\u5ba1\u6279",
        "inventory_adjustment": "\u5e93\u5b58\u8c03\u6574\u5ba1\u6279",
        "inventory_transfer": "\u5e93\u5b58\u8c03\u62e8\u5ba1\u6279",
        "finance_voucher": "\u8d22\u52a1\u51ed\u8bc1\u5ba1\u6279",
        "payment": "\u4ed8\u6b3e\u5ba1\u6279",
        "receivable": "\u5e94\u6536\u5ba1\u6279",
        "payable": "\u5e94\u4ed8\u5ba1\u6279",
    }
    return labels.get(value, "\u4e1a\u52a1\u5355\u636e\u5ba1\u6279")


def approval_status_label(action):
    value = (action or "").strip().lower()
    if value in {"pending", "submitted", "\u5f85\u5ba1\u6279", "\u5df2\u63d0\u4ea4"}:
        return "\u5f85\u5ba1\u6279"
    if value in {"approved", "\u5df2\u901a\u8fc7", "\u901a\u8fc7"}:
        return "\u5df2\u901a\u8fc7"
    if value in {"rejected", "\u5df2\u9a73\u56de", "\u9a73\u56de"}:
        return "\u5df2\u9a73\u56de"
    return action or "\u5f85\u786e\u8ba4"


def approval_next_step(action):
    value = (action or "").strip().lower()
    if value in {"pending", "submitted", "\u5f85\u5ba1\u6279", "\u5df2\u63d0\u4ea4"}:
        return "\u5ba1\u6279\u901a\u8fc7/\u9a73\u56de"
    if value in {"approved", "\u5df2\u901a\u8fc7", "\u901a\u8fc7"}:
        return "\u7b49\u5f85\u4e0b\u6e38\u6267\u884c"
    if value in {"rejected", "\u5df2\u9a73\u56de", "\u9a73\u56de"}:
        return "\u9000\u56de\u7533\u8bf7\u4eba\u4fee\u6539"
    return "\u67e5\u770b\u5ba1\u6279\u8bb0\u5f55"


def approval_owner(action):
    value = (action or "").strip().lower()
    if value in {"pending", "submitted", "\u5f85\u5ba1\u6279", "\u5df2\u63d0\u4ea4"}:
        return "\u5ba1\u6279\u4eba"
    if value in {"rejected", "\u5df2\u9a73\u56de", "\u9a73\u56de"}:
        return "\u7533\u8bf7\u4eba"
    return "\u6d41\u7a0b\u8d1f\u8d23\u4eba"


def format_approval_time(value):
    if not value:
        return "-"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M")
    text = str(value).strip()
    return text[:16] if len(text) >= 16 else text


def render_approval_pending(query_rows, count_rows, render_dashboard):
    rows = query_rows(
        """
        SELECT id, flow_type, reference_no, action, comment, approved_at
        FROM approval_records
        WHERE COALESCE(action,'') IN ('pending','submitted')
        ORDER BY id DESC
        LIMIT 100
        """
    )
    queue_rows = []
    for row in rows:
        reference_no = row.get("reference_no") or row.get("id")
        queue_rows.append(
            {
                "id": row.get("id"),
                "doc_type": approval_doc_type_label(row.get("flow_type")),
                "document_no": reference_no,
                "status": approval_status_label(row.get("action")),
                "next_step": approval_next_step(row.get("action")),
                "owner": approval_owner(row.get("action")),
                "approved_at": format_approval_time(row.get("approved_at")),
                "comment": row.get("comment") or "-",
            }
        )
    return render_dashboard(
        title="\u5f85\u5ba1\u6279",
        subtitle="\u96c6\u4e2d\u67e5\u770b\u5f85\u5904\u7406\u5355\u636e\u3001\u72b6\u6001\u3001\u4e0b\u4e00\u6b65\u548c\u8d23\u4efb\u4eba\uff1b\u7528\u4e8e\u627f\u63a5\u9500\u552e\u3001\u91c7\u8d2d\u3001\u59d4\u5916\u3001\u5de5\u5355\u548c\u8d22\u52a1\u5ba1\u6279\u3002",
        metrics=[
            {"label": "\u5f85\u5904\u7406\u5355\u636e", "value": len(queue_rows), "hint": "\u5f85\u5ba1\u6279\u8bb0\u5f55"},
            {
                "label": "\u91c7\u8d2d\u7533\u8bf7\u5f85\u5904\u7406",
                "value": count_rows(
                    "purchase_requisitions",
                    "COALESCE(status,'') NOT IN ('\u5df2\u5b8c\u6210','\u5df2\u5173\u95ed','\u5df2\u4f5c\u5e9f','completed','closed')",
                ),
                "hint": "\u91c7\u8d2d\u7533\u8bf7",
            },
            {
                "label": "\u9500\u552e\u5f85\u5ba1\u6838",
                "value": count_rows("sales_orders", "COALESCE(status,'') IN ('\u5df2\u63d0\u4ea4','\u5f85\u5ba1\u6838')"),
                "hint": "\u9500\u552e\u5355",
            },
            {
                "label": "\u91c7\u8d2d\u5f85\u5ba1\u6838",
                "value": count_rows("purchase_orders", "COALESCE(status,'') IN ('\u5df2\u63d0\u4ea4','\u5f85\u5ba1\u6838')"),
                "hint": "\u91c7\u8d2d\u5355",
            },
        ],
        shortcuts=[
            {"label": "\u5f85\u5904\u7406\u5355\u636e", "url": "/pending-documents", "icon": "bi-list-check"},
            {"label": "\u91c7\u8d2d\u7533\u8bf7", "url": "/purchase_request", "icon": "bi-file-earmark-plus"},
        ],
        sections=[
            {
                "title": "\u5f85\u5ba1\u6279\u961f\u5217",
                "rows": queue_rows,
                "columns": columns(
                    ("doc_type", "\u5355\u636e\u7c7b\u578b"),
                    ("document_no", "\u5355\u636e\u53f7"),
                    ("status", "\u72b6\u6001"),
                    ("next_step", "\u4e0b\u4e00\u6b65"),
                    ("owner", "\u8d23\u4efb\u4eba"),
                    ("approved_at", "\u65f6\u95f4"),
                    ("comment", "\u5907\u6ce8"),
                ),
                "detail_base": "/approval/records",
            }
        ],
    )


def render_approval_record_detail(record_id, query_one, back_url="/approval/pending"):
    row = query_one(
        """
        SELECT id, flow_type, reference_no, step_id, approver_id, action, comment, approved_at
        FROM approval_records
        WHERE id=%s
        """,
        (record_id,),
    )
    if not row:
        return render_template(
            "approval_record_detail.html",
            record=None,
            back_url=back_url,
        )
    record = {
        "id": row.get("id"),
        "doc_type": approval_doc_type_label(row.get("flow_type")),
        "document_no": row.get("reference_no") or row.get("id"),
        "status": approval_status_label(row.get("action")),
        "next_step": approval_next_step(row.get("action")),
        "owner": approval_owner(row.get("action")),
        "step_id": row.get("step_id") or "-",
        "approver": row.get("approver_id") or approval_owner(row.get("action")),
        "comment": row.get("comment") or "-",
        "approved_at": format_approval_time(row.get("approved_at")),
    }
    return render_template(
        "approval_record_detail.html",
        record=record,
        back_url=back_url,
    )
