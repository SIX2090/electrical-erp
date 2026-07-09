-- 财务模块修复 - 阶段 3：补齐数据库表
-- 迁移 ID: 20260617_001_finance_missing_tables
--
-- 警告: 执行前必须备份数据库
-- 命令: .venv\Scripts\python.exe scripts\pg_backup.py --output backups\pre_finance_fix_20260617.dump

-- 1. 会计科目表
CREATE TABLE IF NOT EXISTS chart_of_accounts (
    id SERIAL PRIMARY KEY,
    code VARCHAR(80) UNIQUE NOT NULL,
    name VARCHAR(160) NOT NULL,
    account_type VARCHAR(80),
    parent_id INTEGER REFERENCES chart_of_accounts(id),
    is_leaf BOOLEAN DEFAULT TRUE,
    balance_direction VARCHAR(20) DEFAULT 'debit',
    status VARCHAR(50) DEFAULT 'active',
    remark TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE chart_of_accounts IS '会计科目表';
COMMENT ON COLUMN chart_of_accounts.code IS '科目编码';
COMMENT ON COLUMN chart_of_accounts.name IS '科目名称';
COMMENT ON COLUMN chart_of_accounts.account_type IS '科目类型: 资产/负债/权益/收入/费用';
COMMENT ON COLUMN chart_of_accounts.is_leaf IS '是否末级科目';
COMMENT ON COLUMN chart_of_accounts.balance_direction IS '余额方向: debit/credit';

-- 2. 总账科目余额表
CREATE TABLE IF NOT EXISTS gl_account_balances (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL,
    beginning_balance NUMERIC(16, 2) DEFAULT 0,
    debit_amount NUMERIC(16, 2) DEFAULT 0,
    credit_amount NUMERIC(16, 2) DEFAULT 0,
    ending_balance NUMERIC(16, 2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account_id, period_year, period_month)
);

CREATE INDEX IF NOT EXISTS idx_gl_account_balances_period
    ON gl_account_balances(period_year, period_month);

COMMENT ON TABLE gl_account_balances IS '总账科目余额表';

-- 3. 凭证分录表（作为 voucher_lines 的备用）
CREATE TABLE IF NOT EXISTS voucher_entries (
    id SERIAL PRIMARY KEY,
    voucher_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    debit_amount NUMERIC(16, 2) DEFAULT 0,
    credit_amount NUMERIC(16, 2) DEFAULT 0,
    summary TEXT,
    project_code VARCHAR(120),
    serial_no VARCHAR(120),
    partner_type VARCHAR(50),
    partner_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_voucher_entries_voucher
    ON voucher_entries(voucher_id);

COMMENT ON TABLE voucher_entries IS '凭证分录表（备用）';

-- 4. 期末结账记录表
CREATE TABLE IF NOT EXISTS period_closing (
    id SERIAL PRIMARY KEY,
    period_year INTEGER NOT NULL,
    period_month INTEGER NOT NULL,
    closing_date DATE,
    status VARCHAR(50) DEFAULT 'open',
    revenue NUMERIC(16, 2) DEFAULT 0,
    cost NUMERIC(16, 2) DEFAULT 0,
    gross_profit NUMERIC(16, 2) DEFAULT 0,
    closed_by INTEGER,
    closed_at TIMESTAMP,
    remark TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (period_year, period_month)
);

CREATE INDEX IF NOT EXISTS idx_period_closing_period
    ON period_closing(period_year, period_month);

COMMENT ON TABLE period_closing IS '期末结账记录表';

-- 5. 项目成本台账
CREATE TABLE IF NOT EXISTS project_cost_ledger (
    id SERIAL PRIMARY KEY,
    project_code VARCHAR(120) NOT NULL,
    project_name VARCHAR(255),
    cost_date DATE NOT NULL,
    cost_type VARCHAR(80),
    source_type VARCHAR(80),
    source_no VARCHAR(120),
    description TEXT,
    cost_amount NUMERIC(16, 2) DEFAULT 0,
    quantity NUMERIC(14, 3),
    unit_cost NUMERIC(16, 4),
    department_id INTEGER,
    employee_id INTEGER,
    recorded_by INTEGER,
    remark TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_project
    ON project_cost_ledger(project_code);
CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_date
    ON project_cost_ledger(cost_date);
CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_source
    ON project_cost_ledger(source_type, source_no);

COMMENT ON TABLE project_cost_ledger IS '项目成本台账';

-- 6. 序列号成本台账
CREATE TABLE IF NOT EXISTS serial_cost_ledger (
    id SERIAL PRIMARY KEY,
    serial_no VARCHAR(120) NOT NULL,
    cost_date DATE NOT NULL,
    cost_type VARCHAR(80),
    source_type VARCHAR(80),
    source_no VARCHAR(120),
    description TEXT,
    cost_amount NUMERIC(16, 2) DEFAULT 0,
    quantity NUMERIC(14, 3),
    unit_cost NUMERIC(16, 4),
    project_code VARCHAR(120),
    recorded_by INTEGER,
    remark TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_serial_cost_ledger_serial
    ON serial_cost_ledger(serial_no);
CREATE INDEX IF NOT EXISTS idx_serial_cost_ledger_date
    ON serial_cost_ledger(cost_date);
CREATE INDEX IF NOT EXISTS idx_serial_cost_ledger_project
    ON serial_cost_ledger(project_code);

COMMENT ON TABLE serial_cost_ledger IS '序列号成本台账';

-- 7. 库存成本计算表
CREATE TABLE IF NOT EXISTS inventory_costing (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL,
    costing_date DATE NOT NULL,
    costing_method VARCHAR(50) DEFAULT 'weighted_avg',
    unit_cost NUMERIC(16, 4) DEFAULT 0,
    quantity NUMERIC(14, 3) DEFAULT 0,
    total_cost NUMERIC(16, 2) DEFAULT 0,
    warehouse_id INTEGER,
    location_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inventory_costing_product
    ON inventory_costing(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_costing_date
    ON inventory_costing(costing_date);

COMMENT ON TABLE inventory_costing IS '库存成本计算表';

-- 8. 库存交易明细表
CREATE TABLE IF NOT EXISTS inventory_transactions (
    id SERIAL PRIMARY KEY,
    transaction_date DATE NOT NULL,
    product_id INTEGER NOT NULL,
    transaction_type VARCHAR(80),
    quantity NUMERIC(14, 3) DEFAULT 0,
    unit_cost NUMERIC(16, 4) DEFAULT 0,
    amount NUMERIC(16, 2) DEFAULT 0,
    warehouse_id INTEGER,
    location_id INTEGER,
    reference_no VARCHAR(120),
    project_code VARCHAR(120),
    serial_no VARCHAR(120),
    remark TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_inventory_transactions_date
    ON inventory_transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_inventory_transactions_product
    ON inventory_transactions(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_transactions_ref
    ON inventory_transactions(reference_no);

COMMENT ON TABLE inventory_transactions IS '库存交易明细表';

-- 9. 财务报表日志
CREATE TABLE IF NOT EXISTS financial_report_log (
    id SERIAL PRIMARY KEY,
    report_type VARCHAR(80) NOT NULL,
    period_year INTEGER,
    period_month INTEGER,
    generated_by INTEGER,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    report_data JSONB,
    remark TEXT
);

CREATE INDEX IF NOT EXISTS idx_financial_report_log_type
    ON financial_report_log(report_type);
CREATE INDEX IF NOT EXISTS idx_financial_report_log_period
    ON financial_report_log(period_year, period_month);

COMMENT ON TABLE financial_report_log IS '财务报表生成日志';

-- 完成提示
DO $$
BEGIN
    RAISE NOTICE '财务模块表结构补齐完成';
    RAISE NOTICE '已创建 9 张表:';
    RAISE NOTICE '  1. chart_of_accounts';
    RAISE NOTICE '  2. gl_account_balances';
    RAISE NOTICE '  3. voucher_entries';
    RAISE NOTICE '  4. period_closing';
    RAISE NOTICE '  5. project_cost_ledger';
    RAISE NOTICE '  6. serial_cost_ledger';
    RAISE NOTICE '  7. inventory_costing';
    RAISE NOTICE '  8. inventory_transactions';
    RAISE NOTICE '  9. financial_report_log';
END $$;
