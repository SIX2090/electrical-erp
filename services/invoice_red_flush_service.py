# -*- coding: utf-8 -*-
"""
发票红冲服务
提供销售发票和采购发票的红冲功能
"""
from decimal import Decimal
from datetime import datetime
import logging

from services.transaction_utils import cursor_db_helpers

logger = logging.getLogger(__name__)


def _table_columns(query_db, table_name):
    rows = query_db(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table_name,)
    )
    return {row.get('column_name') for row in rows}


def _filter_fields(fields, columns):
    return {key: value for key, value in fields.items() if key in columns}


def _amount(row, *names):
    for name in names:
        if name in row and row.get(name) is not None:
            return Decimal(str(row.get(name) or 0))
    return Decimal("0")


def _insert_returning_id(query_db, execute_db, table_name, fields):
    field_names = ', '.join(fields.keys())
    placeholders = ', '.join(['%s'] * len(fields))
    row = query_db(
        f"INSERT INTO {table_name} ({field_names}) VALUES ({placeholders}) RETURNING id",
        tuple(fields.values()),
        one=True,
    )
    if not row:
        return None
    if isinstance(row, dict):
        return row.get('id')
    if isinstance(row, (list, tuple)) and row:
        first = row[0]
        return first.get('id') if isinstance(first, dict) else first
    return row


def _red_item_fields(item, red_invoice_id, item_columns, kind):
    line_no = item.get('line_no') if 'line_no' in item else item.get('line_number')
    amount_without_tax = -_amount(item, 'amount_without_tax', 'amount', 'total_amount')
    fields = {
        'invoice_id': red_invoice_id,
        'line_no': line_no,
        'line_number': line_no,
        'product_id': item.get('product_id'),
        'item_code': item.get('item_code'),
        'item_name': item.get('item_name'),
        'specification': item.get('specification'),
        'unit': item.get('unit'),
        'quantity': -_amount(item, 'quantity'),
        'unit_price': item.get('unit_price'),
        'amount_without_tax': amount_without_tax,
        'amount': amount_without_tax,
        'total_amount': amount_without_tax,
        'tax_rate': item.get('tax_rate'),
        'tax_amount': -_amount(item, 'tax_amount'),
        'amount_with_tax': -_amount(item, 'amount_with_tax'),
        'project_code': item.get('project_code'),
        'serial_no': item.get('serial_no'),
        'remark': item.get('remark'),
    }
    if kind == 'sales':
        fields.update({
            'sales_order_id': item.get('sales_order_id'),
            'sales_order_no': item.get('sales_order_no'),
            'shipment_id': item.get('shipment_id'),
            'delivery_id': item.get('delivery_id'),
            'delivery_no': item.get('delivery_no'),
            'source_doc_type': item.get('source_doc_type'),
            'source_doc_id': item.get('source_doc_id'),
            'source_doc_no': item.get('source_doc_no'),
            'source_doc_line_id': item.get('source_doc_line_id'),
        })
    else:
        fields.update({
            'purchase_order_id': item.get('purchase_order_id'),
            'purchase_order_no': item.get('purchase_order_no'),
            'order_item_id': item.get('order_item_id'),
            'receipt_id': item.get('receipt_id'),
            'receipt_no': item.get('receipt_no'),
            'receipt_item_id': item.get('receipt_item_id'),
            'source_doc_type': item.get('source_doc_type'),
            'source_doc_id': item.get('source_doc_id'),
            'source_doc_no': item.get('source_doc_no'),
            'source_doc_line_id': item.get('source_doc_line_id'),
        })
    return _filter_fields(fields, item_columns)


def _red_related_fields(kind, red_invoice_id, red_invoice_no, original_invoice, amount_with_tax, red_invoice_data, current_user_id, related_columns):
    red_date = red_invoice_data.get('red_invoice_date', datetime.now().date())
    if kind == 'sales':
        fields = {
            'customer_id': original_invoice.get('customer_id'),
            'source_type': 'sales_invoice',
            'source_id': red_invoice_id,
            'source_no': red_invoice_no,
            'receivable_date': red_date,
            'total_amount': amount_with_tax,
            'amount': amount_with_tax,
            'received_amount': 0,
            'balance': amount_with_tax,
            'status': '未收款',
            'remark': f'红冲发票 {original_invoice.get("invoice_no")}',
            'project_code': original_invoice.get('project_code'),
            'serial_no': original_invoice.get('serial_no'),
            'invoice_id': red_invoice_id,
            'created_by': current_user_id,
            'updated_by': current_user_id,
        }
    else:
        fields = {
            'supplier_id': original_invoice.get('supplier_id'),
            'doc_type': 'purchase_invoice',
            'doc_id': red_invoice_id,
            'doc_no': red_invoice_no,
            'doc_date': red_date,
            'source_type': 'purchase_invoice',
            'source_id': red_invoice_id,
            'source_no': red_invoice_no,
            'amount': amount_with_tax,
            'paid_amount': 0,
            'balance': amount_with_tax,
            'status': '未付款',
            'finance_remark': f'红冲发票 {original_invoice.get("invoice_no")}',
            'project_code': original_invoice.get('project_code'),
            'serial_no': original_invoice.get('serial_no'),
            'invoice_id': red_invoice_id,
            'invoice_no': red_invoice_no,
            'invoice_date': red_date,
            'created_by': current_user_id,
            'updated_by': current_user_id,
        }
    return _filter_fields(fields, related_columns)


def create_red_invoice(query_db, execute_db, kind, original_invoice_id, red_invoice_data, current_user_id, get_db=None):
    """
    创建红字发票（红冲）

    Args:
        query_db: 数据库查询函数
        execute_db: 数据库执行函数
        kind: 'sales' 或 'purchase'
        original_invoice_id: 原发票ID
        red_invoice_data: 红字发票数据（包含红冲原因等）
        current_user_id: 当前用户ID
        get_db: 可选，数据库连接获取函数，用于事务包裹

    Returns:
        dict: {'success': bool, 'red_invoice_id': int, 'message': str}
    """
    # 确定表名
    if kind == 'sales':
        invoice_table = 'sales_invoices'
        invoice_items_table = 'sales_invoice_items'
        invoice_receivables_table = 'sales_invoice_receivables'
        related_table = 'customer_receivables'
        related_id_field = 'receivable_id'
    elif kind == 'purchase':
        invoice_table = 'purchase_invoices'
        invoice_items_table = 'purchase_invoice_items'
        invoice_payables_table = 'purchase_invoice_payables'
        related_table = 'supplier_payables'
        related_id_field = 'payable_id'
    else:
        return {'success': False, 'message': '不支持的发票类型'}

    invoice_columns = _table_columns(query_db, invoice_table)
    item_columns = _table_columns(query_db, invoice_items_table)
    related_columns = _table_columns(query_db, related_table)
    item_order_column = "line_no" if "line_no" in item_columns else ("line_number" if "line_number" in item_columns else "id")

    # 1. 读取原发票
    original_invoice = query_db(
        f"SELECT * FROM {invoice_table} WHERE id = %s",
        (original_invoice_id,),
        one=True
    )

    if not original_invoice:
        return {'success': False, 'message': '原发票不存在'}

    if original_invoice.get('status') == '已红冲':
        return {'success': False, 'message': '该发票已经红冲，不能重复红冲'}

    if original_invoice.get('invoice_status') != 'issued':
        return {'success': False, 'message': '只能红冲已开具的发票'}

    # 2. 读取原发票明细
    original_items = query_db(
        f"SELECT * FROM {invoice_items_table} WHERE invoice_id = %s ORDER BY {item_order_column}",
        (original_invoice_id,)
    )

    # 3. 生成红字发票号
    red_invoice_no = _generate_red_invoice_no(query_db, invoice_table, original_invoice.get('invoice_no'))

    # 4. 创建红字发票主表（金额取负数）
    amount_without_tax = -_amount(original_invoice, 'amount_without_tax', 'amount', 'total_amount')
    tax_amount = -_amount(original_invoice, 'tax_amount')
    amount_with_tax = -_amount(original_invoice, 'amount_with_tax')

    red_invoice_fields = {
        'invoice_no': red_invoice_no,
        'invoice_type': 'red',  # 红字发票
        'invoice_date': red_invoice_data.get('red_invoice_date', datetime.now().date()),
        'amount_without_tax': amount_without_tax,
        'amount': amount_without_tax,
        'total_amount': amount_without_tax,
        'tax_amount': tax_amount,
        'amount_with_tax': amount_with_tax,
        'status': '已确认',
        'invoice_status': 'red_flushed',  # 红字发票是有效负数发票，状态为已红冲（非作废）
        'remark': red_invoice_data.get('red_reason', '红冲发票'),
        'created_by': current_user_id,
        'updated_by': current_user_id,
        'approved_by': current_user_id,
        'approved_at': datetime.now(),
    }

    # 复制原发票的客户/供应商信息
    if kind == 'sales':
        red_invoice_fields.update({
            'customer_id': original_invoice.get('customer_id'),
            'customer_name': original_invoice.get('customer_name'),
            'buyer_name': original_invoice.get('buyer_name'),
            'buyer_tax_no': original_invoice.get('buyer_tax_no'),
            'buyer_address': original_invoice.get('buyer_address'),
            'buyer_phone': original_invoice.get('buyer_phone'),
            'buyer_bank': original_invoice.get('buyer_bank'),
            'buyer_account': original_invoice.get('buyer_account'),
        })
    else:  # purchase
        red_invoice_fields.update({
            'supplier_id': original_invoice.get('supplier_id'),
            'supplier_name': original_invoice.get('supplier_name'),
            'seller_name': original_invoice.get('seller_name'),
            'seller_tax_no': original_invoice.get('seller_tax_no'),
            'seller_address': original_invoice.get('seller_address'),
            'seller_phone': original_invoice.get('seller_phone'),
            'seller_bank': original_invoice.get('seller_bank'),
            'seller_account': original_invoice.get('seller_account'),
        })

    # 复制其他字段
    copy_fields = ['invoice_code', 'tax_rate', 'currency', 'exchange_rate',
                   'project_code', 'serial_no']
    for field in copy_fields:
        if field in original_invoice:
            red_invoice_fields[field] = original_invoice[field]
    red_invoice_fields = _filter_fields(red_invoice_fields, invoice_columns)

    # 使用事务包裹所有写操作，确保原子性
    if get_db is not None:
        try:
            from services.transaction_utils import db_transaction
            with db_transaction(get_db) as conn:
                with conn.cursor() as cur:
                    tx_query_db, tx_execute_db, _ = cursor_db_helpers(cur)
                    # 插入红字发票主表
                    field_names = ', '.join(red_invoice_fields.keys())
                    placeholders = ', '.join(['%s'] * len(red_invoice_fields))
                    cur.execute(
                        f"INSERT INTO {invoice_table} ({field_names}) VALUES ({placeholders}) RETURNING id",
                        tuple(red_invoice_fields.values())
                    )
                    red_invoice_row = cur.fetchone()
                    if not red_invoice_row:
                        raise RuntimeError("红字发票主表插入失败")
                    red_invoice_id = red_invoice_row['id'] if isinstance(red_invoice_row, dict) else red_invoice_row[0]

                    # 5. 创建红字发票明细（数量和金额取负数）
                    for item in original_items:
                        red_item_fields = _red_item_fields(item, red_invoice_id, item_columns, kind)
                        item_field_names = ', '.join(red_item_fields.keys())
                        item_placeholders = ', '.join(['%s'] * len(red_item_fields))
                        cur.execute(
                            f"INSERT INTO {invoice_items_table} ({item_field_names}) VALUES ({item_placeholders})",
                            tuple(red_item_fields.values())
                        )

                    # 6. 创建红字应收/应付单
                    related_id = original_invoice.get(related_id_field)
                    if related_id:
                        red_related_fields = _red_related_fields(
                            kind, red_invoice_id, red_invoice_no, original_invoice,
                            amount_with_tax, red_invoice_data, current_user_id, related_columns
                        )
                        related_field_names = ', '.join(red_related_fields.keys())
                        related_placeholders = ', '.join(['%s'] * len(red_related_fields))
                        cur.execute(
                            f"INSERT INTO {related_table} ({related_field_names}) VALUES ({related_placeholders}) RETURNING id",
                            tuple(red_related_fields.values())
                        )
                        red_related_row = cur.fetchone()
                        if not red_related_row:
                            raise RuntimeError("红字应收/应付单插入失败")
                        red_related_id = red_related_row['id'] if isinstance(red_related_row, dict) else red_related_row[0]

                        # 更新红字发票的应收/应付ID
                        cur.execute(
                            f"UPDATE {invoice_table} SET {related_id_field} = %s WHERE id = %s",
                            (red_related_id, red_invoice_id)
                        )

                        # 创建关联记录
                        link_table = invoice_receivables_table if kind == 'sales' else invoice_payables_table
                        link_id_field = 'receivable_id' if kind == 'sales' else 'payable_id'
                        cur.execute(
                            f"INSERT INTO {link_table} (invoice_id, {link_id_field}, allocated_amount) VALUES (%s, %s, %s)",
                            (red_invoice_id, red_related_id, amount_with_tax)
                        )

                    # 7. 更新原发票和红字发票的关联关系
                    cur.execute(
                        f"UPDATE {invoice_table} SET red_invoice_id = %s, status = '已红冲', invoice_status = 'red_flushed' WHERE id = %s",
                        (red_invoice_id, original_invoice_id)
                    )
                    cur.execute(
                        f"UPDATE {invoice_table} SET red_invoice_id = %s WHERE id = %s",
                        (original_invoice_id, red_invoice_id)
                    )

                    # 8. 库存回冲（在事务内执行，失败则回滚整个红冲，避免财务/库存不一致）
                    _rollback_inventory_for_red_flush(
                        tx_query_db, tx_execute_db, kind, original_items,
                        red_invoice_no, current_user_id
                    )

            result = {
                'success': True,
                'red_invoice_id': red_invoice_id,
                'red_invoice_no': red_invoice_no,
                'message': f'红字发票 {red_invoice_no} 创建成功'
            }
        except Exception as e:
            logger.exception("红冲发票创建失败: %s", e)
            return {'success': False, 'message': f'红冲失败: {e}'}

        return result

    # 回退路径：无 get_db 时使用原逻辑（保持向后兼容）
    # 插入红字发票
    field_names = ', '.join(red_invoice_fields.keys())
    placeholders = ', '.join(['%s'] * len(red_invoice_fields))
    red_invoice_row = query_db(
        f"""
        INSERT INTO {invoice_table} ({field_names})
        VALUES ({placeholders})
        RETURNING id
        """,
        tuple(red_invoice_fields.values()),
        one=True
    )
    if not red_invoice_row:
        return {'success': False, 'message': '红字发票主表插入失败'}
    red_invoice_id = red_invoice_row.get('id') if isinstance(red_invoice_row, dict) else red_invoice_row[0]

    # 5. 创建红字发票明细（数量和金额取负数）
    for item in original_items:
        red_item_fields = _red_item_fields(item, red_invoice_id, item_columns, kind)
        item_field_names = ', '.join(red_item_fields.keys())
        item_placeholders = ', '.join(['%s'] * len(red_item_fields))
        execute_db(
            f"""
            INSERT INTO {invoice_items_table} ({item_field_names})
            VALUES ({item_placeholders})
            """,
            tuple(red_item_fields.values())
        )

    # 6. 创建红字应收/应付单
    related_id = original_invoice.get(related_id_field)
    if related_id:
        # 创建负数应收/应付单
        red_related_fields = _red_related_fields(
            kind, red_invoice_id, red_invoice_no, original_invoice,
            amount_with_tax, red_invoice_data, current_user_id, related_columns
        )
        related_field_names = ', '.join(red_related_fields.keys())
        related_placeholders = ', '.join(['%s'] * len(red_related_fields))
        red_related_row = query_db(
            f"""
            INSERT INTO {related_table} ({related_field_names})
            VALUES ({related_placeholders})
            RETURNING id
            """,
            tuple(red_related_fields.values()),
            one=True
        )
        if not red_related_row:
            return {'success': False, 'message': '红字应收/应付单插入失败'}
        red_related_id = red_related_row.get('id') if isinstance(red_related_row, dict) else red_related_row[0]

        # 更新红字发票的应收/应付ID
        execute_db(
            f"UPDATE {invoice_table} SET {related_id_field} = %s WHERE id = %s",
            (red_related_id, red_invoice_id)
        )

        # 创建关联记录
        link_table = invoice_receivables_table if kind == 'sales' else invoice_payables_table
        link_id_field = 'receivable_id' if kind == 'sales' else 'payable_id'
        execute_db(
            f"""
            INSERT INTO {link_table} (invoice_id, {link_id_field}, allocated_amount)
            VALUES (%s, %s, %s)
            """,
            (red_invoice_id, red_related_id, amount_with_tax)
        )

    # 7. 更新原发票和红字发票的关联关系
    execute_db(
        f"""
        UPDATE {invoice_table}
        SET red_invoice_id = %s, status = '已红冲', invoice_status = 'red_flushed'
        WHERE id = %s
        """,
        (red_invoice_id, original_invoice_id)
    )

    execute_db(
        f"""
        UPDATE {invoice_table}
        SET red_invoice_id = %s
        WHERE id = %s
        """,
        (original_invoice_id, red_invoice_id)
    )

    # 8. 库存回冲（回退路径无事务，财务记录已提交；
    #    库存回冲失败时返回 success=False，调用方需人工处理财务/库存不一致）
    try:
        _rollback_inventory_for_red_flush(
            query_db, execute_db, kind, original_items,
            red_invoice_no, current_user_id
        )
    except Exception as inv_err:
        logger.exception("红冲库存回冲失败（财务记录已提交，需人工核查）: %s", red_invoice_no)
        return {
            'success': False,
            'red_invoice_id': red_invoice_id,
            'red_invoice_no': red_invoice_no,
            'message': (
                f'红字发票 {red_invoice_no} 已创建，但库存回冲失败，'
                f'财务与库存可能不一致，需人工核查: {inv_err}'
            ),
            'inventory_warning': str(inv_err),
        }

    return {
        'success': True,
        'red_invoice_id': red_invoice_id,
        'red_invoice_no': red_invoice_no,
        'message': f'红字发票 {red_invoice_no} 创建成功',
    }


def _generate_red_invoice_no(query_db, invoice_table, original_invoice_no):
    """
    生成红字发票号
    格式：原发票号-R001（如果有多次红冲，递增为-R002, -R003等）
    """
    # 查询同一原发票号的最大红冲序号
    result = query_db(
        f"""
        SELECT invoice_no FROM {invoice_table}
        WHERE invoice_no LIKE %s AND invoice_type = 'red'
        ORDER BY invoice_no DESC
        LIMIT 1
        """,
        (f'{original_invoice_no}-R%',),
        one=True
    )

    if result:
        last_red_no = result['invoice_no']
        # 提取序号部分（例如从"INV001-R002"提取"002"）
        seq_part = last_red_no.split('-R')[-1]
        try:
            next_seq = int(seq_part) + 1
        except ValueError:
            next_seq = 1
    else:
        next_seq = 1

    return f'{original_invoice_no}-R{next_seq:03d}'


def _rollback_inventory_for_red_flush(query_db, execute_db, kind, original_items, red_invoice_no, current_user_id):
    """
    红冲时回冲库存和成本。
    销售红冲：创建入库（退回商品到库存）
    采购红冲：创建出库（退回商品给供应商）

    任何关键失败（仓库不存在、物料找不到、库存过账异常）均抛出异常，
    由调用方决定是否回滚事务或生成待处理记录。
    不再吞掉单行异常后静默成功，避免财务/库存不一致。
    """
    from services.inventory_posting_service import post_inventory_receipt, post_inventory_issue

    # 优先使用原发票明细中的仓库；若原发票未记录仓库，则查询该产品最近的出/入库仓库；最后才回退到第一个仓库
    default_warehouse_id = None
    for item in original_items:
        if item.get('warehouse_id'):
            default_warehouse_id = item.get('warehouse_id')
            break
    if not default_warehouse_id:
        fallback_wh = query_db("SELECT id FROM warehouses ORDER BY id LIMIT 1", one=True)
        if not fallback_wh:
            raise RuntimeError("红冲库存回冲失败：系统中无可用仓库，无法执行库存回冲")
        default_warehouse_id = fallback_wh['id']

    tx_date = datetime.now().date()
    rollback_count = 0
    errors = []

    for item in original_items:
        item_code = item.get('item_code')
        if not item_code:
            continue

        product = query_db("SELECT id FROM products WHERE code = %s", (item_code,), one=True)
        if not product:
            errors.append(f"物料 {item_code} 不存在，无法回冲库存")
            continue

        product_id = product['id']
        quantity = abs(Decimal(str(item.get('quantity') or 0)))
        if quantity == 0:
            continue

        unit_cost = Decimal(str(item.get('unit_price') or 0))
        serial_no = item.get('serial_no', '') or ''

        try:
            if kind == 'sales':
                post_inventory_receipt(
                    query_db, execute_db,
                    product_id=product_id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    tx_date=tx_date,
                    tx_type='sales_red_flush_return',
                    reference_no=red_invoice_no,
                    remark=f'红冲销售发票 {red_invoice_no} 库存回冲',
                    warehouse_id=default_warehouse_id,
                    serial_no=serial_no,
                )
            else:
                post_inventory_issue(
                    query_db, execute_db,
                    product_id=product_id,
                    quantity=quantity,
                    tx_date=tx_date,
                    tx_type='purchase_red_flush_return',
                    reference_no=red_invoice_no,
                    remark=f'红冲采购发票 {red_invoice_no} 库存回冲',
                    unit_cost=unit_cost,
                    warehouse_id=default_warehouse_id,
                    serial_no=serial_no,
                )
            rollback_count += 1
        except Exception as e:
            errors.append(f"物料 {item_code} 库存回冲失败: {e}")

    if errors:
        raise RuntimeError(
            f"红冲库存回冲存在失败项（已回冲 {rollback_count} 项）: "
            + "; ".join(errors)
        )

    logger.info("red flush %s: rolled back %d inventory items", red_invoice_no, rollback_count)


def can_red_flush_invoice(query_db, kind, invoice_id):
    """
    检查发票是否可以红冲

    Returns:
        dict: {'can_flush': bool, 'reason': str}
    """
    if kind == 'sales':
        invoice_table = 'sales_invoices'
    elif kind == 'purchase':
        invoice_table = 'purchase_invoices'
    else:
        return {'can_flush': False, 'reason': '不支持的发票类型'}

    invoice = query_db(
        f"SELECT status, invoice_status, red_invoice_id FROM {invoice_table} WHERE id = %s",
        (invoice_id,),
        one=True
    )

    if not invoice:
        return {'can_flush': False, 'reason': '发票不存在'}

    if invoice.get('status') == '已红冲':
        return {'can_flush': False, 'reason': '该发票已经红冲'}

    if invoice.get('invoice_status') != 'issued':
        return {'can_flush': False, 'reason': '只能红冲已开具的发票'}

    if invoice.get('red_invoice_id'):
        return {'can_flush': False, 'reason': '该发票已关联红字发票'}

    return {'can_flush': True, 'reason': ''}


def get_red_invoice_info(query_db, kind, original_invoice_id):
    """
    获取原发票的红字发票信息

    Returns:
        dict or None: 红字发票信息
    """
    if kind == 'sales':
        invoice_table = 'sales_invoices'
    elif kind == 'purchase':
        invoice_table = 'purchase_invoices'
    else:
        return None

    original = query_db(
        f"SELECT red_invoice_id FROM {invoice_table} WHERE id = %s",
        (original_invoice_id,),
        one=True
    )

    if not original or not original.get('red_invoice_id'):
        return None

    red_invoice = query_db(
        f"""
        SELECT id, invoice_no, invoice_date, amount_with_tax, status, remark
        FROM {invoice_table}
        WHERE id = %s
        """,
        (original['red_invoice_id'],),
        one=True
    )

    return red_invoice
