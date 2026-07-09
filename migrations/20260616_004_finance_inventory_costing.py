# -*- coding: utf-8 -*-
"""
财务模块第四期 Schema 迁移
存货核算与成本管理

迁移内容：
1. 扩展 products 表，添加成本相关字段
2. 扩展 inventory_transactions 表，添加成本字段
3. 创建 inventory_costing 表（存货成本核算表）
4. 创建 project_cost_ledger 表（项目成本台账）
5. 创建 serial_cost_ledger 表（机号成本台账）
6. 创建 project_revenue_ledger 表（项目收入台账）
7. 创建相关索引

迁移ID: 20260616_004_finance_inventory_costing
创建日期: 2026-06-16
"""

MIGRATION_ID = "20260616_004_finance_inventory_costing"
MIGRATION_NAME = "财务模块第四期 - 存货核算与成本管理"


def get_migration_sql():
    """
    返回迁移SQL语句列表
    """
    return [
        # 1. 扩展 products 表
        """
        ALTER TABLE products
        ADD COLUMN IF NOT EXISTS current_cost NUMERIC(14,4) DEFAULT 0,
        ADD COLUMN IF NOT EXISTS standard_cost NUMERIC(14,4) DEFAULT 0,
        ADD COLUMN IF NOT EXISTS last_purchase_cost NUMERIC(14,4) DEFAULT 0,
        ADD COLUMN IF NOT EXISTS cost_method VARCHAR(50) DEFAULT '移动加权平均';
        """,

        """
        COMMENT ON COLUMN products.current_cost IS '当前成本（移动加权平均）';
        """,

        """
        COMMENT ON COLUMN products.standard_cost IS '标准成本（BOM成本）';
        """,

        """
        COMMENT ON COLUMN products.last_purchase_cost IS '最近采购成本';
        """,

        """
        COMMENT ON COLUMN products.cost_method IS '计价方法';
        """,

        # 2. 扩展 inventory_transactions 表
        """
        ALTER TABLE inventory_transactions
        ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,4) DEFAULT 0,
        ADD COLUMN IF NOT EXISTS total_cost NUMERIC(14,2) DEFAULT 0,
        ADD COLUMN IF NOT EXISTS avg_cost_after NUMERIC(14,4) DEFAULT 0;
        """,

        """
        COMMENT ON COLUMN inventory_transactions.unit_cost IS '单位成本';
        """,

        """
        COMMENT ON COLUMN inventory_transactions.total_cost IS '总成本';
        """,

        """
        COMMENT ON COLUMN inventory_transactions.avg_cost_after IS '本次交易后的平均成本';
        """,

        # 3. 创建 inventory_costing 表
        """
        CREATE TABLE IF NOT EXISTS inventory_costing (
            id SERIAL PRIMARY KEY,
            costing_date DATE NOT NULL,
            product_id INTEGER NOT NULL REFERENCES products(id),
            transaction_type VARCHAR(80),
            transaction_id INTEGER,
            transaction_no VARCHAR(120),
            quantity NUMERIC(14,4) NOT NULL,
            unit_cost NUMERIC(14,4) NOT NULL,
            total_cost NUMERIC(14,2) NOT NULL,
            balance_quantity NUMERIC(14,4) NOT NULL,
            balance_amount NUMERIC(14,2) NOT NULL,
            avg_cost NUMERIC(14,4) NOT NULL,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            warehouse_id INTEGER,
            costed_by INTEGER REFERENCES users(id),
            costed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            voucher_generated BOOLEAN DEFAULT FALSE,
            voucher_id INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        COMMENT ON TABLE inventory_costing IS '存货成本核算表';
        """,

        """
        COMMENT ON COLUMN inventory_costing.quantity IS '数量（正数入库，负数出库）';
        """,

        """
        COMMENT ON COLUMN inventory_costing.balance_quantity IS '结存数量';
        """,

        """
        COMMENT ON COLUMN inventory_costing.balance_amount IS '结存金额';
        """,

        """
        COMMENT ON COLUMN inventory_costing.avg_cost IS '平均成本';
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_product
        ON inventory_costing(product_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_date
        ON inventory_costing(costing_date);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_project
        ON inventory_costing(project_code);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_serial
        ON inventory_costing(serial_no);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_transaction
        ON inventory_costing(transaction_type, transaction_id);
        """,

        # 4. 创建 project_cost_ledger 表
        """
        CREATE TABLE IF NOT EXISTS project_cost_ledger (
            id SERIAL PRIMARY KEY,
            project_code VARCHAR(120) NOT NULL,
            project_name VARCHAR(255),
            cost_date DATE NOT NULL,
            cost_type VARCHAR(80) NOT NULL,
            source_type VARCHAR(80),
            source_no VARCHAR(120),
            description TEXT,
            cost_amount NUMERIC(14,2) NOT NULL,
            quantity NUMERIC(14,4),
            unit_cost NUMERIC(14,4),
            department_id INTEGER,
            employee_id INTEGER,
            recorded_by INTEGER REFERENCES users(id),
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            voucher_id INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        COMMENT ON TABLE project_cost_ledger IS '项目成本台账';
        """,

        """
        COMMENT ON COLUMN project_cost_ledger.cost_type IS '成本类型：材料成本、人工成本、委外成本、运输费用等';
        """,

        """
        COMMENT ON COLUMN project_cost_ledger.source_type IS '来源类型：采购入库、生产领料、委外发料等';
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_project_cost_project
        ON project_cost_ledger(project_code);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_project_cost_date
        ON project_cost_ledger(cost_date);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_project_cost_type
        ON project_cost_ledger(cost_type);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_project_cost_source
        ON project_cost_ledger(source_type, source_no);
        """,

        # 5. 创建 serial_cost_ledger 表
        """
        CREATE TABLE IF NOT EXISTS serial_cost_ledger (
            id SERIAL PRIMARY KEY,
            serial_no VARCHAR(120) NOT NULL,
            product_id INTEGER REFERENCES products(id),
            project_code VARCHAR(120),
            cost_date DATE NOT NULL,
            cost_type VARCHAR(80) NOT NULL,
            source_type VARCHAR(80),
            source_no VARCHAR(120),
            description TEXT,
            cost_amount NUMERIC(14,2) NOT NULL,
            quantity NUMERIC(14,4),
            unit_cost NUMERIC(14,4),
            department_id INTEGER,
            employee_id INTEGER,
            recorded_by INTEGER REFERENCES users(id),
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            voucher_id INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        COMMENT ON TABLE serial_cost_ledger IS '机号成本台账';
        """,

        """
        COMMENT ON COLUMN serial_cost_ledger.cost_type IS '成本类型：领料成本、采购成本、委外成本、人工成本等';
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_serial_cost_serial
        ON serial_cost_ledger(serial_no);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_serial_cost_date
        ON serial_cost_ledger(cost_date);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_serial_cost_project
        ON serial_cost_ledger(project_code);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_serial_cost_product
        ON serial_cost_ledger(product_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_serial_cost_source
        ON serial_cost_ledger(source_type, source_no);
        """,

        # 6. 创建 project_revenue_ledger 表
        """
        CREATE TABLE IF NOT EXISTS project_revenue_ledger (
            id SERIAL PRIMARY KEY,
            project_code VARCHAR(120) NOT NULL,
            revenue_date DATE NOT NULL,
            revenue_type VARCHAR(80),
            source_type VARCHAR(80),
            source_no VARCHAR(120),
            customer_id INTEGER REFERENCES customers(id),
            revenue_amount NUMERIC(14,2) NOT NULL,
            cost_amount NUMERIC(14,2) DEFAULT 0,
            gross_profit NUMERIC(14,2) DEFAULT 0,
            gross_margin NUMERIC(8,4) DEFAULT 0,
            recorded_by INTEGER REFERENCES users(id),
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,

        """
        COMMENT ON TABLE project_revenue_ledger IS '项目收入台账';
        """,

        """
        COMMENT ON COLUMN project_revenue_ledger.revenue_type IS '收入类型：销售收入、服务收入等';
        """,

        """
        COMMENT ON COLUMN project_revenue_ledger.gross_profit IS '毛利';
        """,

        """
        COMMENT ON COLUMN project_revenue_ledger.gross_margin IS '毛利率';
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_project_revenue_project
        ON project_revenue_ledger(project_code);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_project_revenue_date
        ON project_revenue_ledger(revenue_date);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_project_revenue_customer
        ON project_revenue_ledger(customer_id);
        """,

        """
        CREATE INDEX IF NOT EXISTS idx_project_revenue_source
        ON project_revenue_ledger(source_type, source_no);
        """,
    ]


def get_rollback_sql():
    """
    返回回滚SQL语句列表
    """
    return [
        # 删除索引
        "DROP INDEX IF EXISTS idx_project_revenue_source;",
        "DROP INDEX IF EXISTS idx_project_revenue_customer;",
        "DROP INDEX IF EXISTS idx_project_revenue_date;",
        "DROP INDEX IF EXISTS idx_project_revenue_project;",

        "DROP INDEX IF EXISTS idx_serial_cost_source;",
        "DROP INDEX IF EXISTS idx_serial_cost_product;",
        "DROP INDEX IF EXISTS idx_serial_cost_project;",
        "DROP INDEX IF EXISTS idx_serial_cost_date;",
        "DROP INDEX IF EXISTS idx_serial_cost_serial;",

        "DROP INDEX IF EXISTS idx_project_cost_source;",
        "DROP INDEX IF EXISTS idx_project_cost_type;",
        "DROP INDEX IF EXISTS idx_project_cost_date;",
        "DROP INDEX IF EXISTS idx_project_cost_project;",

        "DROP INDEX IF EXISTS idx_inventory_costing_transaction;",
        "DROP INDEX IF EXISTS idx_inventory_costing_serial;",
        "DROP INDEX IF EXISTS idx_inventory_costing_project;",
        "DROP INDEX IF EXISTS idx_inventory_costing_date;",
        "DROP INDEX IF EXISTS idx_inventory_costing_product;",

        # 删除表
        "DROP TABLE IF EXISTS project_revenue_ledger;",
        "DROP TABLE IF EXISTS serial_cost_ledger;",
        "DROP TABLE IF EXISTS project_cost_ledger;",
        "DROP TABLE IF EXISTS inventory_costing;",

        # 删除 inventory_transactions 扩展字段
        """
        ALTER TABLE inventory_transactions
        DROP COLUMN IF EXISTS avg_cost_after,
        DROP COLUMN IF EXISTS total_cost,
        DROP COLUMN IF EXISTS unit_cost;
        """,

        # 删除 products 扩展字段
        """
        ALTER TABLE products
        DROP COLUMN IF EXISTS cost_method,
        DROP COLUMN IF EXISTS last_purchase_cost,
        DROP COLUMN IF EXISTS standard_cost,
        DROP COLUMN IF EXISTS current_cost;
        """,
    ]


if __name__ == '__main__':
    print(f"迁移ID: {MIGRATION_ID}")
    print(f"迁移名称: {MIGRATION_NAME}")
    print(f"\n包含 {len(get_migration_sql())} 条SQL语句")
    print(f"包含 {len(get_rollback_sql())} 条回滚语句")
