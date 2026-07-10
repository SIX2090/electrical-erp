from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import psycopg2


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.env_config import get_pg_password  # noqa: E402
from services.schema_migrations import MIGRATIONS, apply_schema_migrations  # noqa: E402


def load_cmd_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("@", "::")) or line.lower().startswith("rem "):
            continue
        if not line.lower().startswith("set "):
            continue
        payload = line[4:].strip()
        if payload.startswith('"') and payload.endswith('"'):
            payload = payload[1:-1]
        if "=" not in payload:
            continue
        key, value = payload.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load_runtime_env() -> None:
    load_cmd_env(ROOT / "runtime_env.cmd")
    load_cmd_env(ROOT / "runtime_local_secrets.cmd")


def connect_db():
    load_runtime_env()
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        database=os.environ.get("PG_DATABASE", "wms"),
        user=os.environ.get("PG_USER", "wms_user"),
        password=get_pg_password(),
    )


def exec_many(cur, statements: list[str]) -> None:
    for statement in statements:
        text = statement.strip()
        if text:
            cur.execute(text)


def ensure_tracking(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(80),
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS version VARCHAR(80)")
    cur.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS migration_id VARCHAR(255)")
    cur.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS migration_name VARCHAR(255)")
    cur.execute("UPDATE schema_migrations SET version=migration_id WHERE version IS NULL AND migration_id IS NOT NULL")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS schema_migrations_version_uidx ON schema_migrations(version)")


def ensure_pre_schema_compatibility(cur) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS inventory_transactions (
            id SERIAL PRIMARY KEY,
            transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            transaction_type VARCHAR(80),
            transaction_no VARCHAR(120),
            product_id INTEGER,
            material_id INTEGER,
            warehouse_id INTEGER,
            quantity NUMERIC(14,4) DEFAULT 0,
            source_type VARCHAR(80),
            source_id INTEGER,
            project_code VARCHAR(120),
            cabinet_no VARCHAR(120),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "ALTER TABLE IF EXISTS stock_transactions ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80)",
        "ALTER TABLE IF EXISTS stock_transactions ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120)",
        "ALTER TABLE IF EXISTS stock_transactions ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80)",
        "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS source_type VARCHAR(80)",
        "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS source_id INTEGER",
        "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS project_code VARCHAR(120)",
        "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS cabinet_no VARCHAR(120)",
        "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS material_id INTEGER",
        "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS warehouse_id INTEGER",
    ]
    common_item_columns = [
        "line_no INTEGER",
        "item_code VARCHAR(50)",
        "item_name VARCHAR(200)",
        "specification VARCHAR(200)",
        "unit VARCHAR(20)",
        "quantity NUMERIC(15,3)",
        "unit_price NUMERIC(15,4)",
        "amount NUMERIC(15,2)",
        "tax_rate NUMERIC(5,2)",
        "tax_amount NUMERIC(15,2)",
        "total_amount NUMERIC(15,2)",
        "source_doc_type VARCHAR(80)",
        "source_doc_id INTEGER",
        "source_doc_no VARCHAR(120)",
        "source_doc_line_id INTEGER",
        "project_code VARCHAR(120)",
        "cabinet_no VARCHAR(120)",
        "remark TEXT",
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
    ]
    for table in ("customer_receivable_items", "supplier_payable_items", "sales_invoice_items", "purchase_invoice_items"):
        for column in common_item_columns:
            statements.append(f"ALTER TABLE IF EXISTS {table} ADD COLUMN IF NOT EXISTS {column}")
    statements.extend(
        [
            "ALTER TABLE IF EXISTS sales_invoice_items ADD COLUMN IF NOT EXISTS sales_order_id INTEGER",
            "ALTER TABLE IF EXISTS sales_invoice_items ADD COLUMN IF NOT EXISTS sales_order_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS sales_invoice_items ADD COLUMN IF NOT EXISTS delivery_id INTEGER",
            "ALTER TABLE IF EXISTS sales_invoice_items ADD COLUMN IF NOT EXISTS delivery_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS purchase_invoice_items ADD COLUMN IF NOT EXISTS purchase_order_id INTEGER",
            "ALTER TABLE IF EXISTS purchase_invoice_items ADD COLUMN IF NOT EXISTS purchase_order_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS purchase_invoice_items ADD COLUMN IF NOT EXISTS receipt_id INTEGER",
            "ALTER TABLE IF EXISTS purchase_invoice_items ADD COLUMN IF NOT EXISTS receipt_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS sales_invoice_receivables ADD COLUMN IF NOT EXISTS invoice_id INTEGER",
            "ALTER TABLE IF EXISTS sales_invoice_receivables ADD COLUMN IF NOT EXISTS receivable_id INTEGER",
            "ALTER TABLE IF EXISTS sales_invoice_receivables ADD COLUMN IF NOT EXISTS allocated_amount NUMERIC(15,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS purchase_invoice_payables ADD COLUMN IF NOT EXISTS invoice_id INTEGER",
            "ALTER TABLE IF EXISTS purchase_invoice_payables ADD COLUMN IF NOT EXISTS payable_id INTEGER",
            "ALTER TABLE IF EXISTS purchase_invoice_payables ADD COLUMN IF NOT EXISTS allocated_amount NUMERIC(15,2) DEFAULT 0",
        ]
    )
    exec_many(cur, statements)


def migration_applied(cur, migration_id: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM schema_migrations
        WHERE version=%s OR migration_id=%s
        LIMIT 1
        """,
        (migration_id, migration_id),
    )
    return cur.fetchone() is not None


def record_migration(cur, migration_id: str, migration_name: str = "") -> None:
    cur.execute(
        """
        INSERT INTO schema_migrations (version, migration_id, migration_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (version) DO UPDATE
        SET migration_id=EXCLUDED.migration_id,
            migration_name=EXCLUDED.migration_name
        """,
        (migration_id, migration_id, migration_name),
    )


def columns_present(cur, table: str, columns: tuple[str, ...]) -> bool:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        """,
        (table,),
    )
    existing = {row[0] for row in cur.fetchall()}
    return all(column in existing for column in columns)


def load_module(relative_path: str, module_name: str):
    path = ROOT / relative_path
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load migration module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalise_sql(migration_id: str, sql: str) -> str:
    text = sql.strip().rstrip(";")
    if migration_id == "20260616_005":
        replacements = {
            "CREATE INDEX idx_period_closing_period": "CREATE INDEX IF NOT EXISTS idx_period_closing_period",
            "CREATE INDEX idx_period_closing_status": "CREATE INDEX IF NOT EXISTS idx_period_closing_status",
            "CREATE INDEX idx_period_closing_date": "CREATE INDEX IF NOT EXISTS idx_period_closing_date",
            "CREATE INDEX idx_financial_report_type": "CREATE INDEX IF NOT EXISTS idx_financial_report_type",
            "CREATE INDEX idx_financial_report_period": "CREATE INDEX IF NOT EXISTS idx_financial_report_period",
            "CREATE INDEX idx_financial_report_generated_at": "CREATE INDEX IF NOT EXISTS idx_financial_report_generated_at",
        }
        for old, new in replacements.items():
            if text.startswith(old):
                text = text.replace(old, new, 1)
    return text


def ensure_finance_compatibility_columns(cur) -> None:
    exec_many(
        cur,
        [
            """
            CREATE TABLE IF NOT EXISTS chart_of_accounts (
                id SERIAL PRIMARY KEY,
                account_code VARCHAR(80),
                account_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS accounting_periods (
                id SERIAL PRIMARY KEY,
                period_year INTEGER,
                period_month INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cost_objects (
                id SERIAL PRIMARY KEY,
                object_code VARCHAR(120),
                object_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS vouchers (
                id SERIAL PRIMARY KEY,
                voucher_no VARCHAR(120),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS product_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS transaction_type VARCHAR(80)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS transaction_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS transaction_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS balance_quantity NUMERIC(14,4) DEFAULT 0",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS balance_amount NUMERIC(14,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS avg_cost NUMERIC(14,4) DEFAULT 0",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS project_code VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS cabinet_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS material_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS material_code VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS material_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS warehouse_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS warehouse_name VARCHAR(100)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS location_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS location_name VARCHAR(100)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS period_year INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS period_month INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS source_type VARCHAR(80)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS source_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS source_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS source_line_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS unit VARCHAR(20)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS costing_method VARCHAR(50) DEFAULT 'weighted_average'",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS balance_cost NUMERIC(18,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS balance_unit_cost NUMERIC(18,6) DEFAULT 0",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS voucher_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS voucher_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS is_posted BOOLEAN DEFAULT FALSE",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS is_costed BOOLEAN DEFAULT FALSE",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS costed_by INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS costed_at TIMESTAMP",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS remark TEXT",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS created_by INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS updated_by INTEGER",
            "ALTER TABLE IF EXISTS inventory_costing ADD COLUMN IF NOT EXISTS voucher_generated BOOLEAN DEFAULT FALSE",
            "ALTER TABLE IF EXISTS inventory_costing ALTER COLUMN material_id DROP NOT NULL",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS cost_object_id INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS period_year INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS period_month INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS cost_category VARCHAR(50)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS source_id INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS source_line_id INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS debit_amount NUMERIC(18,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS credit_amount NUMERIC(18,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS balance_amount NUMERIC(18,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS cost_amount NUMERIC(14,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,4)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS unit VARCHAR(20)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS material_code VARCHAR(120)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS material_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS supplier_id INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS supplier_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS department_name VARCHAR(100)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS employee_name VARCHAR(100)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS voucher_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS voucher_id INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS is_posted BOOLEAN DEFAULT FALSE",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS created_by INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS updated_by INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS recorded_by INTEGER",
            "ALTER TABLE IF EXISTS project_cost_ledger ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS product_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS product_code VARCHAR(120)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS product_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS cost_object_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS period_year INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS period_month INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS cost_category VARCHAR(50)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS source_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS source_line_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS debit_amount NUMERIC(18,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS credit_amount NUMERIC(18,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS balance_amount NUMERIC(18,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS cost_amount NUMERIC(14,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,4)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS unit VARCHAR(20)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS material_code VARCHAR(120)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS material_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS supplier_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS supplier_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS work_order_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS work_order_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS department_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS employee_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS voucher_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS voucher_id INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS is_posted BOOLEAN DEFAULT FALSE",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS created_by INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS updated_by INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS recorded_by INTEGER",
            "ALTER TABLE IF EXISTS cabinet_cost_ledger ADD COLUMN IF NOT EXISTS recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS transaction_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS material_code VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS material_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS specification VARCHAR(255)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS warehouse_name VARCHAR(100)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS location_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS location_name VARCHAR(100)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS unit VARCHAR(20)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(18,6) DEFAULT 0",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS total_cost NUMERIC(18,2) DEFAULT 0",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS source_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS source_line_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS batch_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS supplier_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS supplier_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS customer_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS customer_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS work_order_id INTEGER",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS work_order_no VARCHAR(120)",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS reason TEXT",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS created_by INTEGER",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE IF EXISTS inventory_transactions ADD COLUMN IF NOT EXISTS updated_by INTEGER",
        ],
    )


def apply_list_migration(cur, migration_id: str, migration_name: str, statements: list[str]) -> None:
    if migration_applied(cur, migration_id):
        print(f"migration_skip={migration_id}")
        return
    if migration_id == "20260616_005":
        cur.execute("DROP TRIGGER IF EXISTS trigger_update_period_closing_updated_at ON period_closing")
    for index, sql in enumerate(statements, 1):
        text = normalise_sql(migration_id, sql)
        if text:
            print(f"migration_step={migration_id}:{index}")
            cur.execute(text)
    record_migration(cur, migration_id, migration_name)
    print(f"migration_applied={migration_id}")


def apply_finance_file_migrations(cur) -> None:
    ensure_finance_compatibility_columns(cur)
    migration_004 = load_module("migrations/20260616_004_finance_inventory_costing.py", "migration_004")
    if migration_004:
        apply_list_migration(
            cur,
            migration_004.MIGRATION_ID,
            getattr(migration_004, "MIGRATION_NAME", migration_004.MIGRATION_ID),
            migration_004.get_migration_sql(),
        )
    migration_005 = load_module("migrations/20260616_005_finance_period_closing.py", "migration_005")
    if migration_005:
        info_005 = migration_005.get_migration_info()
        if (
            not migration_applied(cur, info_005["id"])
            and columns_present(cur, "period_closing", ("period_year", "period_month", "status"))
            and columns_present(cur, "financial_report_log", ("period_year", "period_month", "report_data"))
        ):
            record_migration(cur, info_005["id"], info_005.get("name", info_005["id"]))
            print(f"migration_superseded={info_005['id']}")
        else:
            apply_list_migration(cur, info_005["id"], info_005.get("name", info_005["id"]), migration_005.get_sql_statements())
    migration_006 = load_module("migrations/20260616_006_finance_missing_tables.py", "migration_006")
    if migration_006:
        info_006 = migration_006.get_migration_info()
        if (
            not migration_applied(cur, info_006["id"])
            and columns_present(cur, "gl_account_balances", ("account_id", "period_year", "period_month", "ending_balance"))
            and columns_present(cur, "project_cost_ledger", ("project_code", "cost_date", "cost_amount"))
            and columns_present(cur, "cabinet_cost_ledger", ("cabinet_no", "cost_date", "cost_amount"))
            and columns_present(cur, "inventory_costing", ("product_id", "costing_date", "total_cost"))
            and columns_present(cur, "inventory_transactions", ("transaction_date", "product_id", "amount"))
        ):
            record_migration(cur, info_006["id"], info_006.get("name", info_006["id"]))
            print(f"migration_superseded={info_006['id']}")
        else:
            apply_list_migration(cur, info_006["id"], info_006.get("name", info_006["id"]), migration_006.get_sql_statements())


def main() -> int:
    conn = connect_db()
    try:
        with conn.cursor() as cur:
            ensure_tracking(cur)
            ensure_pre_schema_compatibility(cur)
            # The app's migration runner is still the source of truth for normal migrations.
            applied = apply_schema_migrations(cur, MIGRATIONS)
            for version in applied:
                print(f"core_migration_applied={version}")
            apply_finance_file_migrations(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    print("schema_update=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
