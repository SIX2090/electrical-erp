"""baseline schema for existing ERP installation

Revision ID: 20260521_0001
Revises: e3a7c9d2f4b6
Create Date: 2026-05-21 08:25:00

This baseline is intentionally conservative. The application already creates
the broad legacy schema during initialization. This revision records the
go-live infrastructure tables that are now managed as versioned migrations and
keeps the operations idempotent for existing installations.
"""

from alembic import op


revision = "20260521_0001"
down_revision = "e3a7c9d2f4b6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(80) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            username VARCHAR(80) PRIMARY KEY,
            failures INTEGER DEFAULT 0,
            locked_until TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS document_sequences (
            prefix VARCHAR(40) NOT NULL,
            scope VARCHAR(80) NOT NULL DEFAULT '',
            last_value INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (prefix, scope)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limit_windows (
            limiter_key VARCHAR(160) NOT NULL,
            window_start BIGINT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (limiter_key, window_start)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment (
            id SERIAL PRIMARY KEY,
            code VARCHAR(80) UNIQUE,
            name VARCHAR(160) NOT NULL,
            model VARCHAR(160),
            work_center VARCHAR(160),
            manufacturer VARCHAR(160),
            purchase_date DATE,
            status VARCHAR(50) DEFAULT 'operational',
            maintenance_status VARCHAR(80) DEFAULT '正常',
            rated_capacity NUMERIC(14, 3) DEFAULT 0,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("ALTER TABLE equipment ADD COLUMN IF NOT EXISTS work_center VARCHAR(160)")
    op.execute("ALTER TABLE equipment ADD COLUMN IF NOT EXISTS maintenance_status VARCHAR(80) DEFAULT '正常'")
    op.execute("ALTER TABLE equipment ADD COLUMN IF NOT EXISTS rated_capacity NUMERIC(14, 3) DEFAULT 0")
    op.execute("ALTER TABLE equipment ADD COLUMN IF NOT EXISTS remark TEXT")
    op.execute("ALTER TABLE equipment ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    op.execute("ALTER TABLE equipment DROP CONSTRAINT IF EXISTS equipment_status_check")
    op.execute(
        """
        ALTER TABLE equipment ADD CONSTRAINT equipment_status_check
            CHECK (status IS NULL OR status IN ('operational','maintenance','repair','idle','disposed','启用','正常','停用','维修中','封存','active'))
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS equipment_oee_records (
            id SERIAL PRIMARY KEY,
            equipment_id INTEGER REFERENCES equipment(id) ON DELETE CASCADE,
            record_date DATE DEFAULT CURRENT_DATE,
            planned_minutes NUMERIC(14, 2) DEFAULT 0,
            run_minutes NUMERIC(14, 2) DEFAULT 0,
            downtime_minutes NUMERIC(14, 2) DEFAULT 0,
            total_quantity NUMERIC(14, 3) DEFAULT 0,
            good_quantity NUMERIC(14, 3) DEFAULT 0,
            target_quantity NUMERIC(14, 3) DEFAULT 0,
            status VARCHAR(50) DEFAULT '已记录',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS accounting_periods (
            id SERIAL PRIMARY KEY,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            status VARCHAR(50) DEFAULT 'open',
            closed_by INTEGER,
            closed_at TIMESTAMP,
            UNIQUE (year, month)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS finance_period_closes (
            id SERIAL PRIMARY KEY,
            period_id INTEGER REFERENCES accounting_periods(id),
            period_label VARCHAR(20) NOT NULL UNIQUE,
            status VARCHAR(50) DEFAULT 'draft',
            revenue NUMERIC(14, 2) DEFAULT 0,
            cost NUMERIC(14, 2) DEFAULT 0,
            gross_profit NUMERIC(14, 2) DEFAULT 0,
            receivable_balance NUMERIC(14, 2) DEFAULT 0,
            payable_balance NUMERIC(14, 2) DEFAULT 0,
            cash_in NUMERIC(14, 2) DEFAULT 0,
            cash_out NUMERIC(14, 2) DEFAULT 0,
            net_cash_flow NUMERIC(14, 2) DEFAULT 0,
            report_payload JSONB DEFAULT '{}'::jsonb,
            remark TEXT,
            closed_by INTEGER,
            closed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS financial_reports (
            id SERIAL PRIMARY KEY,
            report_type VARCHAR(80),
            period_id INTEGER,
            data JSONB DEFAULT '{}'::jsonb,
            status VARCHAR(50) DEFAULT 'draft',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute("ALTER TABLE financial_reports DROP CONSTRAINT IF EXISTS financial_reports_status_check")
    op.execute(
        """
        ALTER TABLE financial_reports ADD CONSTRAINT financial_reports_status_check
            CHECK (status IS NULL OR status IN ('draft','reviewed','approved','generated','closed','preview'))
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS financial_reports_period_type_uidx
            ON financial_reports(period_id, report_type)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS financial_reports_period_type_uidx")
    op.execute("DROP TABLE IF EXISTS finance_period_closes")
    op.execute("DROP TABLE IF EXISTS equipment_oee_records")
