"""
财务模块数据库迁移 - 补充缺失的表
Migration: 20260616_006 - 补充财务模块缺失的核心表

创建以下表：
1. gl_account_balances - 科目余额表（总账余额）
2. project_cost_ledger - 项目成本台账
3. cabinet_cost_ledger - 柜号成本台账
4. inventory_costing - 存货核算表
5. inventory_transactions - 库存交易明细表
"""

def get_migration_info():
    """获取迁移信息"""
    return {
        "id": "20260616_006",
        "name": "财务模块补充表",
        "description": "创建缺失的财务核心表：科目余额、成本台账、存货核算等",
        "author": "System",
        "created_at": "2026-06-16"
    }


def get_sql_statements():
    """获取SQL语句列表"""

    statements = []

    # 1. 科目余额表 - 用于总账和财务报表
    statements.append("""
        CREATE TABLE IF NOT EXISTS gl_account_balances (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id) ON DELETE CASCADE,
            period_id INTEGER REFERENCES accounting_periods(id),
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            opening_debit NUMERIC(18,2) DEFAULT 0,
            opening_credit NUMERIC(18,2) DEFAULT 0,
            current_debit NUMERIC(18,2) DEFAULT 0,
            current_credit NUMERIC(18,2) DEFAULT 0,
            ending_debit NUMERIC(18,2) DEFAULT 0,
            ending_credit NUMERIC(18,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_id, period_year, period_month)
        )
    """)

    statements.append("COMMENT ON TABLE gl_account_balances IS '科目余额表'")
    statements.append("COMMENT ON COLUMN gl_account_balances.account_id IS '科目ID'")
    statements.append("COMMENT ON COLUMN gl_account_balances.period_year IS '期间年份'")
    statements.append("COMMENT ON COLUMN gl_account_balances.period_month IS '期间月份'")
    statements.append("COMMENT ON COLUMN gl_account_balances.opening_debit IS '期初借方余额'")
    statements.append("COMMENT ON COLUMN gl_account_balances.opening_credit IS '期初贷方余额'")
    statements.append("COMMENT ON COLUMN gl_account_balances.current_debit IS '本期借方发生额'")
    statements.append("COMMENT ON COLUMN gl_account_balances.current_credit IS '本期贷方发生额'")
    statements.append("COMMENT ON COLUMN gl_account_balances.ending_debit IS '期末借方余额'")
    statements.append("COMMENT ON COLUMN gl_account_balances.ending_credit IS '期末贷方余额'")

    statements.append("CREATE INDEX IF NOT EXISTS idx_gl_account_balances_account ON gl_account_balances(account_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_gl_account_balances_period ON gl_account_balances(period_year, period_month)")

    # 2. 项目成本台账表
    statements.append("""
        CREATE TABLE IF NOT EXISTS project_cost_ledger (
            id SERIAL PRIMARY KEY,
            project_code VARCHAR(120) NOT NULL,
            project_name VARCHAR(255),
            cost_object_id INTEGER REFERENCES cost_objects(id),
            cost_date DATE NOT NULL,
            period_year INTEGER,
            period_month INTEGER,
            cost_category VARCHAR(50),
            cost_type VARCHAR(50),
            source_type VARCHAR(80),
            source_id INTEGER,
            source_no VARCHAR(120),
            source_line_id INTEGER,
            description TEXT,
            debit_amount NUMERIC(18,2) DEFAULT 0,
            credit_amount NUMERIC(18,2) DEFAULT 0,
            balance_amount NUMERIC(18,2) DEFAULT 0,
            quantity NUMERIC(14,3),
            unit VARCHAR(20),
            material_code VARCHAR(120),
            material_name VARCHAR(255),
            supplier_id INTEGER,
            supplier_name VARCHAR(255),
            department_id INTEGER,
            department_name VARCHAR(100),
            employee_id INTEGER,
            employee_name VARCHAR(100),
            voucher_id INTEGER REFERENCES vouchers(id),
            voucher_no VARCHAR(120),
            is_posted BOOLEAN DEFAULT FALSE,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
    """)

    statements.append("COMMENT ON TABLE project_cost_ledger IS '项目成本台账'")
    statements.append("COMMENT ON COLUMN project_cost_ledger.project_code IS '项目编号'")
    statements.append("COMMENT ON COLUMN project_cost_ledger.cost_category IS '成本类别（材料/人工/费用/制造费用）'")
    statements.append("COMMENT ON COLUMN project_cost_ledger.cost_type IS '成本类型（直接材料/间接材料/直接人工等）'")
    statements.append("COMMENT ON COLUMN project_cost_ledger.source_type IS '来源类型（采购入库/生产领料/工时/费用单）'")
    statements.append("COMMENT ON COLUMN project_cost_ledger.debit_amount IS '借方金额（成本增加）'")
    statements.append("COMMENT ON COLUMN project_cost_ledger.credit_amount IS '贷方金额（成本减少/转出）'")
    statements.append("COMMENT ON COLUMN project_cost_ledger.balance_amount IS '余额（累计成本）'")

    statements.append("CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_project ON project_cost_ledger(project_code)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_date ON project_cost_ledger(cost_date)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_period ON project_cost_ledger(period_year, period_month)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_source ON project_cost_ledger(source_type, source_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_cost_object ON project_cost_ledger(cost_object_id)")

    # 3. 柜号成本台账表
    statements.append("""
        CREATE TABLE IF NOT EXISTS cabinet_cost_ledger (
            id SERIAL PRIMARY KEY,
            cabinet_no VARCHAR(120) NOT NULL,
            product_id INTEGER,
            product_code VARCHAR(120),
            product_name VARCHAR(255),
            project_code VARCHAR(120),
            cost_object_id INTEGER REFERENCES cost_objects(id),
            cost_date DATE NOT NULL,
            period_year INTEGER,
            period_month INTEGER,
            cost_category VARCHAR(50),
            cost_type VARCHAR(50),
            source_type VARCHAR(80),
            source_id INTEGER,
            source_no VARCHAR(120),
            source_line_id INTEGER,
            description TEXT,
            debit_amount NUMERIC(18,2) DEFAULT 0,
            credit_amount NUMERIC(18,2) DEFAULT 0,
            balance_amount NUMERIC(18,2) DEFAULT 0,
            quantity NUMERIC(14,3),
            unit VARCHAR(20),
            material_code VARCHAR(120),
            material_name VARCHAR(255),
            supplier_id INTEGER,
            supplier_name VARCHAR(255),
            work_order_id INTEGER,
            work_order_no VARCHAR(120),
            voucher_id INTEGER REFERENCES vouchers(id),
            voucher_no VARCHAR(120),
            is_posted BOOLEAN DEFAULT FALSE,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
    """)

    statements.append("COMMENT ON TABLE cabinet_cost_ledger IS '柜号成本台账'")
    statements.append("COMMENT ON COLUMN cabinet_cost_ledger.cabinet_no IS '柜号/序列号'")
    statements.append("COMMENT ON COLUMN cabinet_cost_ledger.cost_category IS '成本类别（材料/人工/费用/制造费用）'")
    statements.append("COMMENT ON COLUMN cabinet_cost_ledger.cost_type IS '成本类型（直接材料/间接材料/直接人工等）'")
    statements.append("COMMENT ON COLUMN cabinet_cost_ledger.source_type IS '来源类型（采购入库/生产领料/工时/费用单）'")
    statements.append("COMMENT ON COLUMN cabinet_cost_ledger.debit_amount IS '借方金额（成本增加）'")
    statements.append("COMMENT ON COLUMN cabinet_cost_ledger.credit_amount IS '贷方金额（成本减少/转出）'")
    statements.append("COMMENT ON COLUMN cabinet_cost_ledger.balance_amount IS '余额（累计成本）'")

    statements.append("CREATE INDEX IF NOT EXISTS idx_cabinet_cost_ledger_serial ON cabinet_cost_ledger(cabinet_no)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_cabinet_cost_ledger_product ON cabinet_cost_ledger(product_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_cabinet_cost_ledger_date ON cabinet_cost_ledger(cost_date)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_cabinet_cost_ledger_period ON cabinet_cost_ledger(period_year, period_month)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_cabinet_cost_ledger_source ON cabinet_cost_ledger(source_type, source_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_cabinet_cost_ledger_cost_object ON cabinet_cost_ledger(cost_object_id)")

    # 4. 存货核算表
    statements.append("""
        CREATE TABLE IF NOT EXISTS inventory_costing (
            id SERIAL PRIMARY KEY,
            material_id INTEGER NOT NULL,
            material_code VARCHAR(120),
            material_name VARCHAR(255),
            warehouse_id INTEGER,
            warehouse_name VARCHAR(100),
            location_id INTEGER,
            location_name VARCHAR(100),
            costing_date DATE NOT NULL,
            period_year INTEGER,
            period_month INTEGER,
            transaction_type VARCHAR(50),
            source_type VARCHAR(80),
            source_id INTEGER,
            source_no VARCHAR(120),
            source_line_id INTEGER,
            quantity NUMERIC(14,3) DEFAULT 0,
            unit VARCHAR(20),
            unit_cost NUMERIC(18,6) DEFAULT 0,
            total_cost NUMERIC(18,2) DEFAULT 0,
            costing_method VARCHAR(50) DEFAULT 'weighted_average',
            balance_quantity NUMERIC(14,3) DEFAULT 0,
            balance_cost NUMERIC(18,2) DEFAULT 0,
            balance_unit_cost NUMERIC(18,6) DEFAULT 0,
            voucher_id INTEGER REFERENCES vouchers(id),
            voucher_no VARCHAR(120),
            is_posted BOOLEAN DEFAULT FALSE,
            is_costed BOOLEAN DEFAULT FALSE,
            costed_at TIMESTAMP,
            costed_by INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
    """)

    statements.append("COMMENT ON TABLE inventory_costing IS '存货核算表'")
    statements.append("COMMENT ON COLUMN inventory_costing.material_id IS '物料ID'")
    statements.append("COMMENT ON COLUMN inventory_costing.costing_date IS '核算日期'")
    statements.append("COMMENT ON COLUMN inventory_costing.transaction_type IS '交易类型（入库/出库/调整）'")
    statements.append("COMMENT ON COLUMN inventory_costing.source_type IS '来源单据类型'")
    statements.append("COMMENT ON COLUMN inventory_costing.quantity IS '数量（正数入库，负数出库）'")
    statements.append("COMMENT ON COLUMN inventory_costing.unit_cost IS '单位成本'")
    statements.append("COMMENT ON COLUMN inventory_costing.total_cost IS '总成本'")
    statements.append("COMMENT ON COLUMN inventory_costing.costing_method IS '核算方法（加权平均/先进先出/移动平均）'")
    statements.append("COMMENT ON COLUMN inventory_costing.balance_quantity IS '结存数量'")
    statements.append("COMMENT ON COLUMN inventory_costing.balance_cost IS '结存成本'")
    statements.append("COMMENT ON COLUMN inventory_costing.balance_unit_cost IS '结存单价'")
    statements.append("COMMENT ON COLUMN inventory_costing.is_costed IS '是否已核算'")

    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_costing_material ON inventory_costing(material_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_costing_warehouse ON inventory_costing(warehouse_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_costing_date ON inventory_costing(costing_date)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_costing_period ON inventory_costing(period_year, period_month)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_costing_source ON inventory_costing(source_type, source_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_costing_is_costed ON inventory_costing(is_costed)")

    # 5. 库存交易明细表（用于存货核算的详细追踪）
    statements.append("""
        CREATE TABLE IF NOT EXISTS inventory_transactions (
            id SERIAL PRIMARY KEY,
            transaction_no VARCHAR(120),
            transaction_date DATE NOT NULL,
            transaction_type VARCHAR(50) NOT NULL,
            material_id INTEGER NOT NULL,
            material_code VARCHAR(120),
            material_name VARCHAR(255),
            specification VARCHAR(255),
            warehouse_id INTEGER,
            warehouse_name VARCHAR(100),
            location_id INTEGER,
            location_name VARCHAR(100),
            quantity NUMERIC(14,3) NOT NULL DEFAULT 0,
            unit VARCHAR(20),
            unit_cost NUMERIC(18,6) DEFAULT 0,
            total_cost NUMERIC(18,2) DEFAULT 0,
            source_type VARCHAR(80),
            source_id INTEGER,
            source_no VARCHAR(120),
            source_line_id INTEGER,
            project_code VARCHAR(120),
            cabinet_no VARCHAR(120),
            batch_no VARCHAR(120),
            supplier_id INTEGER,
            supplier_name VARCHAR(255),
            customer_id INTEGER,
            customer_name VARCHAR(255),
            work_order_id INTEGER,
            work_order_no VARCHAR(120),
            reason TEXT,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
    """)

    statements.append("COMMENT ON TABLE inventory_transactions IS '库存交易明细表'")
    statements.append("COMMENT ON COLUMN inventory_transactions.transaction_type IS '交易类型（采购入库/销售出库/生产领料/完工入库/调拨/盘点调整等）'")
    statements.append("COMMENT ON COLUMN inventory_transactions.quantity IS '数量（正数入库，负数出库）'")
    statements.append("COMMENT ON COLUMN inventory_transactions.unit_cost IS '单位成本'")
    statements.append("COMMENT ON COLUMN inventory_transactions.source_type IS '来源单据类型'")

    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_material ON inventory_transactions(material_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_date ON inventory_transactions(transaction_date)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_type ON inventory_transactions(transaction_type)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_warehouse ON inventory_transactions(warehouse_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_source ON inventory_transactions(source_type, source_id)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_project ON inventory_transactions(project_code)")
    statements.append("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_serial ON inventory_transactions(cabinet_no)")

    return statements


if __name__ == "__main__":
    info = get_migration_info()
    print(f"Migration: {info['id']} - {info['name']}")
    print(f"Description: {info['description']}")
    print(f"\nSQL Statements: {len(get_sql_statements())}")
