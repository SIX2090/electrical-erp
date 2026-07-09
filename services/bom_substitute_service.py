# -*- coding: utf-8 -*-
"""
BOM 替代料服务 (P0-1 加固)

管理 BOM 行的替代料关系，供 MRP 引擎在主料缺料时按优先级和比例自动替代。

核心功能：
1. 列出/新增/更新/删除替代料
2. 按优先级返回可用替代料列表
3. 审批替代料
4. 供 MRP 引擎调用的替代料查询接口

数据表：bom_substitute_materials（见 schema_migrations 20260621_006）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def list_substitutes(query_rows, bom_item_id: int) -> List[Dict[str, Any]]:
    """列出指定 BOM 行的所有替代料，按优先级升序排列。"""
    rows = query_rows(
        """
        SELECT bs.id, bs.bom_item_id, bs.substitute_product_id,
               bs.priority, bs.ratio, bs.allow_auto_substitute,
               bs.approval_status, bs.remark,
               bs.created_at, bs.updated_at,
               p.code AS substitute_code,
               p.name AS substitute_name,
               p.specification AS substitute_spec,
               p.unit AS substitute_unit,
               bi.product_id AS main_product_id,
               mp.code AS main_code,
               mp.name AS main_name,
               b.bom_no, b.version AS bom_version
        FROM bom_substitute_materials bs
        LEFT JOIN products p ON p.id=bs.substitute_product_id
        LEFT JOIN bom_items bi ON bi.id=bs.bom_item_id
        LEFT JOIN products mp ON mp.id=bi.product_id
        LEFT JOIN boms b ON b.id=bi.bom_id
        WHERE bs.bom_item_id=%s
        ORDER BY bs.priority ASC, bs.id ASC
        """,
        (bom_item_id,),
    ) or []
    return [dict(r) for r in rows]


def list_substitutes_for_product(
    query_rows, bom_item_id: int, only_approved: bool = True
) -> List[Dict[str, Any]]:
    """供 MRP 引擎调用：返回可用于自动替代的替代料列表。"""
    status_filter = "AND bs.approval_status='approved'" if only_approved else ""
    rows = query_rows(
        f"""
        SELECT bs.substitute_product_id, bs.priority, bs.ratio,
               bs.allow_auto_substitute,
               p.code AS substitute_code,
               p.name AS substitute_name,
               p.specification AS substitute_spec,
               p.unit AS substitute_unit
        FROM bom_substitute_materials bs
        LEFT JOIN products p ON p.id=bs.substitute_product_id
        WHERE bs.bom_item_id=%s
          {status_filter}
        ORDER BY bs.priority ASC, bs.id ASC
        """,
        (bom_item_id,),
    ) or []
    return [dict(r) for r in rows]


def create_substitute(
    execute_db,
    *,
    bom_item_id: int,
    substitute_product_id: int,
    priority: int = 1,
    ratio: float = 1.0,
    allow_auto_substitute: bool = False,
    approval_status: str = "approved",
    remark: str = "",
    created_by: Optional[int] = None,
) -> None:
    """新增一条替代料关系。"""
    execute_db(
        """
        INSERT INTO bom_substitute_materials
            (bom_item_id, substitute_product_id, priority, ratio,
             allow_auto_substitute, approval_status, remark, created_by, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
        ON CONFLICT (bom_item_id, substitute_product_id) DO UPDATE
            SET priority=EXCLUDED.priority,
                ratio=EXCLUDED.ratio,
                allow_auto_substitute=EXCLUDED.allow_auto_substitute,
                approval_status=EXCLUDED.approval_status,
                remark=EXCLUDED.remark,
                updated_at=CURRENT_TIMESTAMP
        """,
        (
            bom_item_id,
            substitute_product_id,
            priority,
            ratio,
            allow_auto_substitute,
            approval_status,
            remark,
            created_by,
        ),
    )


def update_substitute(
    execute_db, substitute_id: int, **fields
) -> bool:
    """更新替代料字段。"""
    allowed = {
        "priority", "ratio", "allow_auto_substitute",
        "approval_status", "remark", "approved_by",
    }
    updates = []
    params = []
    for key, value in fields.items():
        if key in allowed and value is not None:
            updates.append(f"{key}=%s")
            params.append(value)
    if not updates:
        return False
    updates.append("updated_at=CURRENT_TIMESTAMP")
    params.append(substitute_id)
    execute_db(
        f"UPDATE bom_substitute_materials SET {', '.join(updates)} WHERE id=%s",
        tuple(params),
    )
    return True


def delete_substitute(execute_db, substitute_id: int) -> bool:
    """删除替代料关系。"""
    execute_db(
        "DELETE FROM bom_substitute_materials WHERE id=%s",
        (substitute_id,),
    )
    return True


def approve_substitute(
    execute_db, substitute_id: int, approved_by: int
) -> bool:
    """审批替代料。"""
    execute_db(
        """
        UPDATE bom_substitute_materials
        SET approval_status='approved',
            approved_by=%s,
            approved_at=CURRENT_TIMESTAMP,
            updated_at=CURRENT_TIMESTAMP
        WHERE id=%s
        """,
        (approved_by, substitute_id),
    )
    return True


def get_substitute(query_db, substitute_id: int) -> Optional[Dict[str, Any]]:
    """获取单条替代料记录。"""
    row = query_db(
        """
        SELECT bs.*, p.code AS substitute_code, p.name AS substitute_name,
               p.specification AS substitute_spec, p.unit AS substitute_unit
        FROM bom_substitute_materials bs
        LEFT JOIN products p ON p.id=bs.substitute_product_id
        WHERE bs.id=%s
        """,
        (substitute_id,),
        one=True,
    )
    return dict(row) if row else None
