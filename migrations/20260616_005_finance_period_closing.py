"""
财务模块第五期 - 期末处理与财务报表
Migration ID: 20260616_005
Created: 2026-06-16
Description: 创建期末处理和财务报表相关的数据表
"""

MIGRATION_ID = "20260616_005"
MIGRATION_NAME = "财务模块第五期 - 期末处理与财务报表"
MIGRATION_DATE = "2026-06-16"

SQL_STATEMENTS = [
    # ==================== 1. 期末结账表 ====================
    """
    CREATE TABLE IF NOT EXISTS period_closing (
        id SERIAL PRIMARY KEY,
        closing_period VARCHAR(7) NOT NULL UNIQUE,           -- 结账期间(YYYY-MM)
        closing_date DATE NOT NULL,                          -- 结账日期
        closing_status VARCHAR(20) DEFAULT '已结账',          -- 结账状态：已结账/已反结账
        profit_transfer_voucher_id INTEGER,                  -- 损益结转凭证ID
        total_revenue DECIMAL(18,2) DEFAULT 0,               -- 本期收入合计
        total_expense DECIMAL(18,2) DEFAULT 0,               -- 本期费用合计
        net_profit DECIMAL(18,2) DEFAULT 0,                  -- 本期净利润
        closing_checks TEXT,                                 -- 结账检查结果(JSON)
        closed_by INTEGER,                                   -- 结账人
        closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,       -- 结账时间
        unclosed_by INTEGER,                                 -- 反结账人
        unclosed_at TIMESTAMP,                               -- 反结账时间
        unclosing_reason TEXT,                               -- 反结账原因
        remarks TEXT,                                        -- 备注
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    """
    COMMENT ON TABLE period_closing IS '期末结账表'
    """,

    """
    COMMENT ON COLUMN period_closing.closing_period IS '结账期间(YYYY-MM格式)'
    """,

    """
    COMMENT ON COLUMN period_closing.closing_status IS '结账状态：已结账/已反结账'
    """,

    """
    COMMENT ON COLUMN period_closing.profit_transfer_voucher_id IS '损益结转凭证ID'
    """,

    """
    COMMENT ON COLUMN period_closing.total_revenue IS '本期收入合计'
    """,

    """
    COMMENT ON COLUMN period_closing.total_expense IS '本期费用合计'
    """,

    """
    COMMENT ON COLUMN period_closing.net_profit IS '本期净利润(收入-费用)'
    """,

    """
    COMMENT ON COLUMN period_closing.closing_checks IS '结账检查结果(JSON格式)'
    """,

    # ==================== 2. 期末结账表索引 ====================
    """
    CREATE INDEX idx_period_closing_period ON period_closing(closing_period)
    """,

    """
    CREATE INDEX idx_period_closing_status ON period_closing(closing_status)
    """,

    """
    CREATE INDEX idx_period_closing_date ON period_closing(closing_date)
    """,

    # ==================== 3. 财务报表生成记录表 ====================
    """
    CREATE TABLE IF NOT EXISTS financial_report_log (
        id SERIAL PRIMARY KEY,
        report_type VARCHAR(50) NOT NULL,                    -- 报表类型：资产负债表/利润表/现金流量表
        report_period VARCHAR(7) NOT NULL,                   -- 报表期间(YYYY-MM)
        report_data TEXT,                                    -- 报表数据(JSON格式)
        generated_by INTEGER,                                -- 生成人
        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,    -- 生成时间
        remarks TEXT                                         -- 备注
    )
    """,

    """
    COMMENT ON TABLE financial_report_log IS '财务报表生成记录表'
    """,

    """
    COMMENT ON COLUMN financial_report_log.report_type IS '报表类型：资产负债表/利润表/现金流量表'
    """,

    """
    COMMENT ON COLUMN financial_report_log.report_period IS '报表期间(YYYY-MM格式)'
    """,

    """
    COMMENT ON COLUMN financial_report_log.report_data IS '报表数据(JSON格式)'
    """,

    # ==================== 4. 财务报表生成记录表索引 ====================
    """
    CREATE INDEX idx_financial_report_type ON financial_report_log(report_type)
    """,

    """
    CREATE INDEX idx_financial_report_period ON financial_report_log(report_period)
    """,

    """
    CREATE INDEX idx_financial_report_generated_at ON financial_report_log(generated_at)
    """,

    # ==================== 5. 期末结账触发器（更新updated_at） ====================
    """
    CREATE OR REPLACE FUNCTION update_period_closing_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,

    """
    CREATE TRIGGER trigger_update_period_closing_updated_at
    BEFORE UPDATE ON period_closing
    FOR EACH ROW
    EXECUTE FUNCTION update_period_closing_updated_at()
    """,
]

def get_migration_info():
    """获取迁移信息"""
    return {
        "id": MIGRATION_ID,
        "name": MIGRATION_NAME,
        "date": MIGRATION_DATE,
        "sql_count": len(SQL_STATEMENTS),
        "description": "创建期末结账表和财务报表生成记录表，支持期末结账、反结账、损益结转和三大财务报表功能"
    }

def get_sql_statements():
    """获取SQL语句列表"""
    return SQL_STATEMENTS

if __name__ == "__main__":
    info = get_migration_info()
    print(f"Migration ID: {info['id']}")
    print(f"Migration Name: {info['name']}")
    print(f"Migration Date: {info['date']}")
    print(f"SQL Statements: {info['sql_count']}")
    print(f"Description: {info['description']}")
