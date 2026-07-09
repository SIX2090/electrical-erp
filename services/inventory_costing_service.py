# -*- coding: utf-8 -*-
"""
存货核算服务
实现移动加权平均成本计价法

核心功能：
1. 计算移动加权平均成本
2. 记录存货成本核算明细
3. 核算入库成本（采购入库、完工入库等）
4. 核算出库成本（销售出库、生产领料等）
5. 生成成本凭证
6. 成本查询和报表

作者: AI Assistant
日期: 2026-06-16
"""

from decimal import Decimal
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def calculate_weighted_average_cost(
    query_db,
    product_id: int,
    new_quantity: Decimal,
    new_total_cost: Decimal
) -> Dict:
    """
    计算移动加权平均成本

    公式：新单位成本 = (库存金额 + 入库金额) / (库存数量 + 入库数量)

    Args:
        query_db: 数据库查询函数
        product_id: 产品ID
        new_quantity: 新入库数量
        new_total_cost: 新入库总成本

    Returns:
        {
            'old_quantity': 原库存数量,
            'old_amount': 原库存金额,
            'old_avg_cost': 原平均成本,
            'new_quantity': 新入库数量,
            'new_amount': 新入库金额,
            'balance_quantity': 结存数量,
            'balance_amount': 结存金额,
            'new_avg_cost': 新平均成本
        }
    """
    product = query_db(
        """
        SELECT
            p.id,
            p.code,
            p.name,
            p.cost_method
        FROM products p
        WHERE p.id = %s
        FOR UPDATE
        """,
        (product_id,),
        one=True
    )

    if not product:
        raise ValueError(f"产品ID {product_id} 不存在")

    # inventory_balances is the inventory authority; products fields are compatibility snapshots.
    balance = query_db(
        """
        SELECT
            COALESCE(SUM(quantity), 0) AS quantity,
            COALESCE(SUM(quantity * unit_cost) / NULLIF(SUM(quantity), 0), 0) AS current_cost
        FROM inventory_balances
        WHERE product_id = %s
        """,
        (product_id,),
        one=True,
    ) or {}

    # 转换为Decimal
    old_quantity = Decimal(str(balance.get('quantity') or 0))
    old_avg_cost = Decimal(str(balance.get('current_cost') or 0))
    old_amount = old_quantity * old_avg_cost

    # 计算新的库存和金额
    balance_quantity = old_quantity + new_quantity
    balance_amount = old_amount + new_total_cost

    # 计算新的加权平均成本
    if balance_quantity > 0:
        new_avg_cost = balance_amount / balance_quantity
    else:
        # 库存为0时，保持原成本或使用新成本
        new_avg_cost = old_avg_cost if old_avg_cost > 0 else (
            new_total_cost / new_quantity if new_quantity > 0 else Decimal('0')
        )

    return {
        'old_quantity': old_quantity,
        'old_amount': old_amount,
        'old_avg_cost': old_avg_cost,
        'new_quantity': new_quantity,
        'new_amount': new_total_cost,
        'balance_quantity': balance_quantity,
        'balance_amount': balance_amount,
        'new_avg_cost': new_avg_cost
    }


def get_current_product_cost(query_db, product_id: int) -> Decimal:
    """
    获取产品当前成本

    Args:
        query_db: 数据库查询函数
        product_id: 产品ID

    Returns:
        当前加权平均成本
    """
    row = query_db(
        """
        SELECT
            COALESCE(
                SUM(ib.quantity * ib.unit_cost) / NULLIF(SUM(ib.quantity), 0),
                p.current_cost,
                0
            ) AS current_cost
        FROM products p
        LEFT JOIN inventory_balances ib ON ib.product_id = p.id
        WHERE p.id = %s
        GROUP BY p.id, p.current_cost
        """,
        (product_id,),
        one=True
    )

    if not row:
        return Decimal('0')

    return Decimal(str(row.get('current_cost') or 0))


def update_product_cost(execute_db, product_id: int, new_avg_cost: Decimal):
    """
    更新产品当前成本

    Args:
        execute_db: 数据库执行函数
        product_id: 产品ID
        new_avg_cost: 新的平均成本
    """
    execute_db(
        """
        UPDATE products
        SET current_cost = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (new_avg_cost, product_id)
    )


def record_inventory_costing(
    query_db,
    execute_db,
    costing_data: Dict
) -> int:
    """
    记录存货成本核算明细

    Args:
        costing_data: {
            'costing_date': 核算日期,
            'product_id': 产品ID,
            'transaction_type': 交易类型（采购入库、销售出库等）,
            'transaction_id': 交易ID,
            'transaction_no': 交易单号,
            'quantity': 数量（正数入库，负数出库）,
            'unit_cost': 单位成本,
            'total_cost': 总成本,
            'balance_quantity': 结存数量,
            'balance_amount': 结存金额,
            'avg_cost': 平均成本,
            'project_code': 项目号（可选）,
            'serial_no': 机号（可选）,
            'warehouse_id': 仓库ID（可选）,
            'costed_by': 核算人,
            'remark': 备注（可选）
        }

    Returns:
        核算记录ID
    """
    result = execute_db(
        """
        INSERT INTO inventory_costing (
            costing_date,
            product_id,
            transaction_type,
            transaction_id,
            transaction_no,
            quantity,
            unit_cost,
            total_cost,
            balance_quantity,
            balance_amount,
            avg_cost,
            project_code,
            serial_no,
            warehouse_id,
            costed_by,
            remark
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        RETURNING id
        """,
        (
            costing_data.get('costing_date'),
            costing_data.get('product_id'),
            costing_data.get('transaction_type'),
            costing_data.get('transaction_id'),
            costing_data.get('transaction_no'),
            costing_data.get('quantity'),
            costing_data.get('unit_cost'),
            costing_data.get('total_cost'),
            costing_data.get('balance_quantity'),
            costing_data.get('balance_amount'),
            costing_data.get('avg_cost'),
            costing_data.get('project_code'),
            costing_data.get('serial_no'),
            costing_data.get('warehouse_id'),
            costing_data.get('costed_by'),
            costing_data.get('remark')
        )
    )

    if isinstance(result, list) and result:
        return result[0].get('id') if isinstance(result[0], dict) else result[0]
    if isinstance(result, dict):
        return result.get('id')
    if isinstance(result, int):
        return result
    if result is None:
        row = query_db(
            "SELECT id FROM inventory_costing WHERE product_id=%s AND transaction_no=%s ORDER BY id DESC LIMIT 1",
            (costing_data.get('product_id'), costing_data.get('transaction_no')),
            one=True,
        )
        return row.get('id') if row else None
    return None


def cost_inventory_receipt(
    query_db,
    execute_db,
    receipt_data: Dict
) -> Dict:
    """
    核算入库成本

    适用场景：
    - 采购入库
    - 完工入库
    - 其他入库
    - 盘盈

    Args:
        receipt_data: {
            'costing_date': 核算日期,
            'product_id': 产品ID,
            'transaction_type': 交易类型,
            'transaction_id': 交易ID,
            'transaction_no': 交易单号,
            'quantity': 入库数量,
            'unit_cost': 入库单价,
            'project_code': 项目号（可选）,
            'serial_no': 机号（可选）,
            'warehouse_id': 仓库ID（可选）,
            'costed_by': 核算人,
            'remark': 备注（可选）
        }

    Returns:
        {
            'success': True/False,
            'message': 消息,
            'costing_id': 核算记录ID,
            'old_avg_cost': 原平均成本,
            'new_avg_cost': 新平均成本,
            'balance_quantity': 结存数量,
            'balance_amount': 结存金额
        }
    """
    try:
        product_id = receipt_data['product_id']
        quantity = Decimal(str(receipt_data['quantity']))
        unit_cost = Decimal(str(receipt_data['unit_cost']))
        total_cost = quantity * unit_cost

        # 计算新的加权平均成本
        cost_calc = calculate_weighted_average_cost(
            query_db,
            product_id,
            quantity,
            total_cost
        )

        # 记录成本核算
        costing_id = record_inventory_costing(
            query_db,
            execute_db,
            {
                'costing_date': receipt_data.get('costing_date', datetime.now().date()),
                'product_id': product_id,
                'transaction_type': receipt_data.get('transaction_type'),
                'transaction_id': receipt_data.get('transaction_id'),
                'transaction_no': receipt_data.get('transaction_no'),
                'quantity': quantity,
                'unit_cost': unit_cost,
                'total_cost': total_cost,
                'balance_quantity': cost_calc['balance_quantity'],
                'balance_amount': cost_calc['balance_amount'],
                'avg_cost': cost_calc['new_avg_cost'],
                'project_code': receipt_data.get('project_code'),
                'serial_no': receipt_data.get('serial_no'),
                'warehouse_id': receipt_data.get('warehouse_id'),
                'costed_by': receipt_data.get('costed_by'),
                'remark': receipt_data.get('remark')
            }
        )

        # 更新产品当前成本
        update_product_cost(execute_db, product_id, cost_calc['new_avg_cost'])

        # 更新 inventory_transactions 表的成本字段（如果有transaction_id）
        if receipt_data.get('transaction_id'):
            execute_db(
                """
                UPDATE inventory_transactions
                SET unit_cost = %s,
                    total_cost = %s,
                    avg_cost_after = %s
                WHERE id = %s
                """,
                (
                    float(unit_cost),
                    float(total_cost),
                    float(cost_calc['new_avg_cost']),
                    receipt_data['transaction_id']
                )
            )

        return {
            'success': True,
            'message': '入库成本核算成功',
            'costing_id': costing_id,
            'old_avg_cost': cost_calc['old_avg_cost'],
            'new_avg_cost': cost_calc['new_avg_cost'],
            'balance_quantity': cost_calc['balance_quantity'],
            'balance_amount': cost_calc['balance_amount']
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'入库成本核算失败: {str(e)}'
        }


def cost_inventory_issue(
    query_db,
    execute_db,
    issue_data: Dict
) -> Dict:
    """
    核算出库成本

    适用场景：
    - 销售出库
    - 生产领料
    - 委外发料
    - 其他出库
    - 盘亏

    Args:
        issue_data: {
            'costing_date': 核算日期,
            'product_id': 产品ID,
            'transaction_type': 交易类型,
            'transaction_id': 交易ID,
            'transaction_no': 交易单号,
            'quantity': 出库数量（正数）,
            'project_code': 项目号（可选）,
            'serial_no': 机号（可选）,
            'warehouse_id': 仓库ID（可选）,
            'costed_by': 核算人,
            'remark': 备注（可选）
        }

    Returns:
        {
            'success': True/False,
            'message': 消息,
            'costing_id': 核算记录ID,
            'unit_cost': 出库单位成本,
            'total_cost': 出库总成本,
            'avg_cost': 当前平均成本,
            'balance_quantity': 结存数量,
            'balance_amount': 结存金额
        }
    """
    try:
        product_id = issue_data['product_id']
        quantity = Decimal(str(issue_data['quantity']))

        # 获取当前平均成本
        current_cost = get_current_product_cost(query_db, product_id)

        if current_cost == 0:
            # 如果当前成本为0，尝试获取最近采购成本
            last_purchase = query_db(
                "SELECT last_purchase_cost FROM products WHERE id = %s",
                (product_id,),
                one=True
            )
            if last_purchase:
                current_cost = Decimal(str(last_purchase.get('last_purchase_cost') or 0))

        # 计算出库成本
        total_cost = quantity * current_cost

        # 获取当前库存
        product = query_db(
            "SELECT quantity, current_cost FROM products WHERE id = %s",
            (product_id,),
            one=True
        )

        if not product:
            return {
                'success': False,
                'message': f'产品ID {product_id} 不存在，无法核算出库成本'
            }

        old_quantity = Decimal(str(product.get('quantity') or 0))
        old_amount = old_quantity * Decimal(str(product.get('current_cost') or 0))

        # 计算结存
        balance_quantity = old_quantity - quantity
        balance_amount = old_amount - total_cost

        # 记录成本核算（出库数量为负数）
        costing_id = record_inventory_costing(
            query_db,
            execute_db,
            {
                'costing_date': issue_data.get('costing_date', datetime.now().date()),
                'product_id': product_id,
                'transaction_type': issue_data.get('transaction_type'),
                'transaction_id': issue_data.get('transaction_id'),
                'transaction_no': issue_data.get('transaction_no'),
                'quantity': -quantity,  # 出库为负数
                'unit_cost': current_cost,
                'total_cost': -total_cost,  # 出库成本为负数
                'balance_quantity': balance_quantity,
                'balance_amount': balance_amount,
                'avg_cost': current_cost,  # 出库不改变平均成本
                'project_code': issue_data.get('project_code'),
                'serial_no': issue_data.get('serial_no'),
                'warehouse_id': issue_data.get('warehouse_id'),
                'costed_by': issue_data.get('costed_by'),
                'remark': issue_data.get('remark')
            }
        )

        # 更新 inventory_transactions 表的成本字段（如果有transaction_id）
        if issue_data.get('transaction_id'):
            execute_db(
                """
                UPDATE inventory_transactions
                SET unit_cost = %s,
                    total_cost = %s,
                    avg_cost_after = %s
                WHERE id = %s
                """,
                (
                    float(current_cost),
                    float(total_cost),
                    float(current_cost),
                    issue_data['transaction_id']
                )
            )

        return {
            'success': True,
            'message': '出库成本核算成功',
            'costing_id': costing_id,
            'unit_cost': current_cost,
            'total_cost': total_cost,
            'avg_cost': current_cost,
            'balance_quantity': balance_quantity,
            'balance_amount': balance_amount
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'出库成本核算失败: {str(e)}'
        }


def generate_costing_voucher(
    query_db,
    execute_db,
    costing_id: int,
    current_user_id: int
) -> Dict:
    """
    生成成本凭证

    销售出库凭证:
    借：主营业务成本
    贷：库存商品

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        costing_id: 成本核算记录ID
        current_user_id: 当前用户ID

    Returns:
        {
            'success': True/False,
            'message': 消息,
            'voucher_id': 凭证ID,
            'voucher_no': 凭证号
        }
    """
    from services.voucher_generation_service import (
        generate_voucher_number,
        create_voucher_with_lines
    )

    try:
        # 获取成本核算记录
        costing = query_db(
            """
            SELECT
                ic.*,
                p.code AS product_code,
                p.name AS product_name
            FROM inventory_costing ic
            JOIN products p ON ic.product_id = p.id
            WHERE ic.id = %s
            """,
            (costing_id,),
            one=True
        )

        if not costing:
            return {'success': False, 'message': '成本核算记录不存在'}

        # 检查是否已生成凭证
        if costing.get('voucher_generated'):
            return {
                'success': False,
                'message': '该成本核算已生成凭证，不能重复生成'
            }

        # 只为出库生成凭证
        quantity = Decimal(str(costing['quantity']))
        if quantity >= 0:
            return {
                'success': False,
                'message': '只能为出库业务生成成本凭证'
            }

        total_cost = abs(Decimal(str(costing['total_cost'])))

        # 生成凭证号
        voucher_date = costing['costing_date']
        voucher_no = generate_voucher_number(query_db, voucher_date)

        # 准备凭证分录
        lines = [
            {
                'line_no': 1,
                'account_code': '5401',  # 主营业务成本
                'summary': f"销售出库 - {costing['product_name']}",
                'debit_amount': total_cost,
                'credit_amount': Decimal('0'),
                'project_code': costing.get('project_code'),
                'serial_no': costing.get('serial_no')
            },
            {
                'line_no': 2,
                'account_code': '1405',  # 库存商品
                'summary': f"销售出库 - {costing['product_name']}",
                'debit_amount': Decimal('0'),
                'credit_amount': total_cost,
                'project_code': costing.get('project_code'),
                'serial_no': costing.get('serial_no')
            }
        ]

        # 创建凭证
        voucher_id = create_voucher_with_lines(
            query_db,
            execute_db,
            voucher_no=voucher_no,
            voucher_date=voucher_date,
            voucher_type='记账凭证',
            summary=f"销售出库成本结转 - {costing['transaction_no']}",
            source_type='inventory_costing',
            source_no=costing['transaction_no'],
            lines=lines,
            prepared_by=current_user_id
        )

        # 更新成本核算记录的凭证状态
        execute_db(
            """
            UPDATE inventory_costing
            SET voucher_generated = TRUE,
                voucher_id = %s
            WHERE id = %s
            """,
            (voucher_id, costing_id)
        )

        return {
            'success': True,
            'message': '成本凭证生成成功',
            'voucher_id': voucher_id,
            'voucher_no': voucher_no
        }

    except Exception as e:
        return {
            'success': False,
            'message': f'成本凭证生成失败: {str(e)}'
        }


def query_inventory_cost_ledger(
    query_db,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    查询存货成本明细账

    Args:
        filters: {
            'product_id': 产品ID,
            'start_date': 开始日期,
            'end_date': 结束日期,
            'project_code': 项目号,
            'serial_no': 机号,
            'transaction_type': 交易类型
        }

    Returns:
        成本明细账列表
    """
    filters = filters or {}

    where_clauses = ["1=1"]
    params = []

    if filters.get('product_id'):
        where_clauses.append("ic.product_id = %s")
        params.append(filters['product_id'])

    if filters.get('start_date'):
        where_clauses.append("ic.costing_date >= %s")
        params.append(filters['start_date'])

    if filters.get('end_date'):
        where_clauses.append("ic.costing_date <= %s")
        params.append(filters['end_date'])

    if filters.get('project_code'):
        where_clauses.append("ic.project_code = %s")
        params.append(filters['project_code'])

    if filters.get('serial_no'):
        where_clauses.append("ic.serial_no = %s")
        params.append(filters['serial_no'])

    if filters.get('transaction_type'):
        where_clauses.append("ic.transaction_type = %s")
        params.append(filters['transaction_type'])

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    SELECT
        ic.*,
        COALESCE(ic.material_code, p.code) AS product_code,
        COALESCE(ic.material_name, p.name) AS product_name,
        COALESCE(ic.unit, p.unit) AS product_unit,
        COALESCE(ic.avg_cost, ic.unit_cost, 0) AS avg_cost,
        u.username AS costed_by_name
    FROM inventory_costing ic
    LEFT JOIN products p ON ic.product_id = p.id
    LEFT JOIN users u ON ic.costed_by = u.id
    WHERE {where_sql}
    ORDER BY ic.costing_date, ic.id
    """

    return query_db(sql, tuple(params))


def query_inventory_ledger_reconciliation(
    query_db
) -> Dict:
    """
    查询存货与总账对账

    Returns:
        {
            'inventory_amount': 库存金额,
            'ledger_balance': 总账科目余额,
            'difference': 差异,
            'is_balanced': 是否平衡,
            'details': [产品明细列表]
        }
    """
    # 1. 计算库存金额（业务系统）
    products = query_db(
        """
        SELECT
            p.id,
            p.code,
            p.name,
            COALESCE(SUM(ib.quantity), 0) AS quantity,
            COALESCE(SUM(ib.quantity * ib.unit_cost) / NULLIF(SUM(ib.quantity), 0), 0) AS current_cost,
            COALESCE(SUM(ib.quantity * ib.unit_cost), 0) AS amount
        FROM products p
        JOIN inventory_balances ib ON ib.product_id = p.id
        GROUP BY p.id, p.code, p.name
        HAVING COALESCE(SUM(ib.quantity), 0) > 0
        ORDER BY p.code
        """
    )

    inventory_amount = sum(
        Decimal(str(p.get('amount') or 0))
        for p in products
    )

    # 2. 查询总账科目余额（财务系统）
    # 1405 - 库存商品科目
    ledger = query_db(
        """
        SELECT
            COALESCE(SUM(debit_amount), 0) - COALESCE(SUM(credit_amount), 0) AS balance
        FROM general_ledger
        WHERE account_code = '1405' AND COALESCE(status, 'active') = 'active'
        """,
        one=True
    )

    ledger_balance = Decimal(str((ledger or {}).get('balance') or 0))

    # 3. 计算差异
    difference = inventory_amount - ledger_balance
    is_balanced = abs(difference) < Decimal('0.01')

    return {
        'inventory_amount': inventory_amount,
        'ledger_balance': ledger_balance,
        'difference': difference,
        'is_balanced': is_balanced,
        'details': products
    }
