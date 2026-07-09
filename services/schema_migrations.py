MIGRATIONS = [
    (
        "20260520_001_login_attempts",
        """
        CREATE TABLE IF NOT EXISTS login_attempts (
            username VARCHAR(80) PRIMARY KEY,
            failures INTEGER DEFAULT 0,
            locked_until TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ),
    (
        "20260520_002_document_sequences",
        """
        CREATE TABLE IF NOT EXISTS document_sequences (
            prefix VARCHAR(40) NOT NULL,
            scope VARCHAR(80) NOT NULL DEFAULT '',
            last_value INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (prefix, scope)
        )
        """,
    ),
    (
        "20260520_003_rate_limit_windows",
        """
        CREATE TABLE IF NOT EXISTS rate_limit_windows (
            limiter_key VARCHAR(160) NOT NULL,
            window_start BIGINT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (limiter_key, window_start)
        )
        """,
    ),
    (
        "20260521_001_equipment_oee",
        """
        CREATE TABLE IF NOT EXISTS equipment (
            id SERIAL PRIMARY KEY,
            code VARCHAR(80) UNIQUE,
            name VARCHAR(160) NOT NULL,
            model VARCHAR(160),
            work_center VARCHAR(160),
            manufacturer VARCHAR(160),
            purchase_date DATE,
            status VARCHAR(50) DEFAULT '启用',
            maintenance_status VARCHAR(80) DEFAULT '正常',
            rated_capacity NUMERIC(14, 3) DEFAULT 0,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS code VARCHAR(80);
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS name VARCHAR(160);
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS model VARCHAR(160);
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS work_center VARCHAR(160);
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS manufacturer VARCHAR(160);
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS purchase_date DATE;
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '启用';
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS maintenance_status VARCHAR(80) DEFAULT '正常';
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS rated_capacity NUMERIC(14, 3) DEFAULT 0;
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE equipment ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE equipment DROP CONSTRAINT IF EXISTS equipment_status_check;
        ALTER TABLE equipment ADD CONSTRAINT equipment_status_check
            CHECK (status IS NULL OR status IN ('operational','maintenance','repair','idle','disposed','启用','正常','停用','维修中','封存','active'));

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
        """,
    ),
    (
        "20260521_002_finance_period_close",
        """
        CREATE TABLE IF NOT EXISTS accounting_periods (
            id SERIAL PRIMARY KEY,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            status VARCHAR(50) DEFAULT 'open',
            closed_by INTEGER,
            closed_at TIMESTAMP,
            UNIQUE (year, month)
        );
        ALTER TABLE accounting_periods ADD COLUMN IF NOT EXISTS year INTEGER;
        ALTER TABLE accounting_periods ADD COLUMN IF NOT EXISTS month INTEGER;
        ALTER TABLE accounting_periods ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'open';
        ALTER TABLE accounting_periods ADD COLUMN IF NOT EXISTS closed_by INTEGER;
        ALTER TABLE accounting_periods ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP;

        CREATE TABLE IF NOT EXISTS finance_period_closes (
            id SERIAL PRIMARY KEY,
            period_id INTEGER REFERENCES accounting_periods(id),
            period_label VARCHAR(20) NOT NULL,
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (period_label)
        );

        CREATE TABLE IF NOT EXISTS financial_reports (
            id SERIAL PRIMARY KEY,
            report_type VARCHAR(80),
            period_id INTEGER,
            data JSONB DEFAULT '{}'::jsonb,
            status VARCHAR(50) DEFAULT 'draft',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE financial_reports ADD COLUMN IF NOT EXISTS report_type VARCHAR(80);
        ALTER TABLE financial_reports ADD COLUMN IF NOT EXISTS period_id INTEGER;
        ALTER TABLE financial_reports ADD COLUMN IF NOT EXISTS data JSONB DEFAULT '{}'::jsonb;
        ALTER TABLE financial_reports ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'draft';
        ALTER TABLE financial_reports ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE financial_reports ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE financial_reports DROP CONSTRAINT IF EXISTS financial_reports_status_check;
        ALTER TABLE financial_reports ADD CONSTRAINT financial_reports_status_check
            CHECK (status IS NULL OR status IN ('draft','reviewed','approved','generated','closed','preview'));
        CREATE UNIQUE INDEX IF NOT EXISTS financial_reports_period_type_uidx
            ON financial_reports(period_id, report_type);
        """,
    ),
    (
        "20260525_001_inventory_project_trace",
        """
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE inventory_balances ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE transfer_orders ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE transfer_orders ADD COLUMN IF NOT EXISTS from_location_id INTEGER;
        ALTER TABLE transfer_orders ADD COLUMN IF NOT EXISTS to_location_id INTEGER;
        CREATE TABLE IF NOT EXISTS transfer_order_items (
            id SERIAL PRIMARY KEY,
            transfer_id INTEGER NOT NULL REFERENCES transfer_orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            quantity NUMERIC NOT NULL,
            lot_no VARCHAR(100),
            serial_no VARCHAR(100),
            unit_cost NUMERIC DEFAULT 0,
            remark TEXT
        );
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS from_location_id INTEGER;
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS to_location_id INTEGER;
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE inventory_check_orders ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE inventory_check_orders ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS line_warehouse_id INTEGER;
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS line_location_id INTEGER;
        """,
    ),
    (
        "20260525_002_subcontract_payable_closure",
        """
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS product_id INTEGER;
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS quantity NUMERIC(14, 3) DEFAULT 0;
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS unit_price NUMERIC(14, 4) DEFAULT 0;
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS doc_type VARCHAR(80);
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS doc_id INTEGER;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS doc_no VARCHAR(120);
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS doc_date DATE;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS balance NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS finance_remark TEXT;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS next_follow_up_date DATE;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS due_date DATE;
        CREATE UNIQUE INDEX IF NOT EXISTS supplier_payables_doc_uidx
            ON supplier_payables(doc_type, doc_id)
            WHERE doc_type IS NOT NULL AND doc_id IS NOT NULL;
        """,
    ),
    (
        "20260525_003_shipment_service_card_closure",
        """
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS sales_order_id INTEGER;
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS machine_model VARCHAR(160);
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS product_id INTEGER;
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS customer_id INTEGER;
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '待安装';
        CREATE UNIQUE INDEX IF NOT EXISTS machine_service_cards_sales_serial_uidx
            ON machine_service_cards(sales_order_id, serial_no)
            WHERE sales_order_id IS NOT NULL AND serial_no IS NOT NULL;
        """,
    ),
    (
        "20260525_004_user_status",
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'normal';
        UPDATE users SET status='normal' WHERE status IS NULL OR status='';
        """,
    ),
    (
        "20260526_001_sales_document_closure",
        """
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS customer_id INTEGER;
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS receiver_name VARCHAR(160);
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS receiver_phone VARCHAR(80);
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS delivery_address TEXT;
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS logistics_provider VARCHAR(160);
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS logistics_no VARCHAR(160);
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS signoff_status VARCHAR(80) DEFAULT '未签收';
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS source_type VARCHAR(80) DEFAULT 'sales_order';
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS shipped_amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS amount_with_tax NUMERIC(14, 2) DEFAULT 0;

        ALTER TABLE sales_shipment_items ADD COLUMN IF NOT EXISTS unit_price NUMERIC(14, 4) DEFAULT 0;
        ALTER TABLE sales_shipment_items ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE sales_shipment_items ADD COLUMN IF NOT EXISTS cost_amount NUMERIC(14, 2) DEFAULT 0;

        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS receivable_id INTEGER;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS status VARCHAR(80) DEFAULT '已确认';
        """,
    ),
    (
        "20260527_001_sales_optional_document_trace_fields",
        """
        ALTER TABLE quotation_headers ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE quotation_headers ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE quotation_headers ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);

        ALTER TABLE sales_returns ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE sales_returns ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE sales_returns ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        """,
    ),
    (
        "20260527_002_sales_return_amount_basis",
        """
        ALTER TABLE sales_returns ADD COLUMN IF NOT EXISTS amount_with_tax NUMERIC(14, 2) DEFAULT 0;
        UPDATE sales_returns
        SET amount_with_tax=COALESCE(
            NULLIF(amount_with_tax,0),
            quantity * unit_price * (1 + COALESCE(tax_rate,0) / 100),
            0
        )
        WHERE amount_with_tax IS NULL OR amount_with_tax=0;
        """,
    ),
    (
        "20260527_003_inventory_document_trace_fields",
        """
        ALTER TABLE inventory_balances ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE transfer_orders ADD COLUMN IF NOT EXISTS from_location_id INTEGER;
        ALTER TABLE transfer_orders ADD COLUMN IF NOT EXISTS to_location_id INTEGER;
        CREATE TABLE IF NOT EXISTS transfer_order_items (
            id SERIAL PRIMARY KEY,
            transfer_id INTEGER NOT NULL REFERENCES transfer_orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            quantity NUMERIC NOT NULL,
            lot_no VARCHAR(100),
            serial_no VARCHAR(100),
            unit_cost NUMERIC DEFAULT 0,
            remark TEXT
        );
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS from_location_id INTEGER;
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS to_location_id INTEGER;
        ALTER TABLE inventory_check_orders ADD COLUMN IF NOT EXISTS location_id INTEGER;
        """,
    ),
    (
        "20260527_004_inventory_assembly_documents",
        """
        DO $$
        BEGIN
            IF to_regclass('inventory_assembly_orders') IS NULL
               AND EXISTS (SELECT 1 FROM pg_type WHERE typname='inventory_assembly_orders') THEN
                DROP TYPE inventory_assembly_orders;
            END IF;
            IF to_regclass('inventory_assembly_items') IS NULL
               AND EXISTS (SELECT 1 FROM pg_type WHERE typname='inventory_assembly_items') THEN
                DROP TYPE inventory_assembly_items;
            END IF;
        END $$;
        CREATE TABLE IF NOT EXISTS inventory_assembly_orders (
            id SERIAL PRIMARY KEY,
            assembly_no VARCHAR(120) NOT NULL UNIQUE,
            doc_type VARCHAR(30) NOT NULL DEFAULT 'assembly',
            doc_date DATE NOT NULL DEFAULT CURRENT_DATE,
            warehouse_id INTEGER,
            location_id INTEGER,
            product_id INTEGER NOT NULL,
            quantity NUMERIC(14, 3) NOT NULL DEFAULT 0,
            unit_cost NUMERIC(14, 4) DEFAULT 0,
            lot_no VARCHAR(120),
            serial_no VARCHAR(120),
            project_code VARCHAR(120),
            status VARCHAR(80) NOT NULL DEFAULT '已过账',
            remark TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at TIMESTAMP,
            posted_by INTEGER
        );
        CREATE TABLE IF NOT EXISTS inventory_assembly_items (
            id SERIAL PRIMARY KEY,
            order_id INTEGER NOT NULL REFERENCES inventory_assembly_orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            quantity NUMERIC(14, 3) NOT NULL DEFAULT 0,
            unit_cost NUMERIC(14, 4) DEFAULT 0,
            lot_no VARCHAR(120),
            serial_no VARCHAR(120),
            line_role VARCHAR(30) NOT NULL DEFAULT 'component',
            remark TEXT
        );
        """,
    ),
    (
        "20260527_005_inventory_trace_batch_fields",
        """
        ALTER TABLE batch_tracking ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE batch_tracking ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE batch_tracking ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE batch_tracking ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_batch_tracking_project_serial
            ON batch_tracking (project_code, serial_no);
        CREATE INDEX IF NOT EXISTS idx_batch_tracking_location
            ON batch_tracking (warehouse_id, location_id);
        """,
    ),
    (
        "20260527_006_stock_transaction_source_type",
        """
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        CREATE INDEX IF NOT EXISTS idx_stock_transactions_source
            ON stock_transactions (source_type, reference_no);
        CREATE TABLE IF NOT EXISTS inventory_adjustment_orders (
            id SERIAL PRIMARY KEY,
            adj_no VARCHAR(120) NOT NULL UNIQUE,
            adj_date DATE NOT NULL DEFAULT CURRENT_DATE,
            warehouse_id INTEGER,
            location_id INTEGER,
            project_code VARCHAR(120),
            adj_type VARCHAR(120),
            status VARCHAR(80) NOT NULL DEFAULT '已过账',
            remark TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            posted_at TIMESTAMP,
            posted_by INTEGER
        );
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS order_id INTEGER;
        ALTER TABLE inventory_adjustments DROP CONSTRAINT IF EXISTS inventory_adjustments_adj_no_key;
        CREATE INDEX IF NOT EXISTS idx_inventory_adjustments_order
            ON inventory_adjustments (order_id);
        CREATE INDEX IF NOT EXISTS idx_inventory_adjustments_adj_no
            ON inventory_adjustments (adj_no);
        """,
    ),
    (
        "20260528_001_inventory_other_movement_line_fields",
        """
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS spec VARCHAR(255);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS unit VARCHAR(80);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS available_qty NUMERIC(14, 3) DEFAULT 0;
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS usage_reason TEXT;
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        """,
    ),
    (
        "20260527_007_sales_reconciliation_integrity",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS sales_orders_order_no_uidx
            ON sales_orders(order_no)
            WHERE order_no IS NOT NULL AND order_no<>'';
        CREATE UNIQUE INDEX IF NOT EXISTS sales_shipments_shipment_no_uidx
            ON sales_shipments(shipment_no)
            WHERE shipment_no IS NOT NULL AND shipment_no<>'';
        CREATE UNIQUE INDEX IF NOT EXISTS customer_receipts_receipt_no_uidx
            ON customer_receipts(receipt_no)
            WHERE receipt_no IS NOT NULL AND receipt_no<>'';
        CREATE TABLE IF NOT EXISTS customer_receipt_settlements (
            id SERIAL PRIMARY KEY,
            receipt_id INTEGER NOT NULL REFERENCES customer_receipts(id) ON DELETE CASCADE,
            receivable_id INTEGER NOT NULL REFERENCES customer_receivables(id) ON DELETE CASCADE,
            applied_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS customer_receipt_settlements_receipt_recv_uidx
            ON customer_receipt_settlements(receipt_id, receivable_id);
        """,
    ),
    (
        "20260527_008_customer_receipt_settlement_backfill",
        """
        CREATE TABLE IF NOT EXISTS customer_receipt_settlements (
            id SERIAL PRIMARY KEY,
            receipt_id INTEGER NOT NULL REFERENCES customer_receipts(id) ON DELETE CASCADE,
            receivable_id INTEGER NOT NULL REFERENCES customer_receivables(id) ON DELETE CASCADE,
            applied_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS customer_receipt_settlements_receipt_recv_uidx
            ON customer_receipt_settlements(receipt_id, receivable_id);

        INSERT INTO customer_receipt_settlements (receipt_id, receivable_id, applied_amount)
        SELECT
            r.id,
            r.receivable_id,
            CASE
                WHEN COALESCE(cr.balance, 0) + COALESCE(cr.received_amount, 0) > 0
                    THEN LEAST(COALESCE(r.amount, 0), COALESCE(cr.balance, 0) + COALESCE(cr.received_amount, 0))
                ELSE COALESCE(r.amount, 0)
            END AS applied_amount
        FROM customer_receipts r
        JOIN customer_receivables cr ON cr.id = r.receivable_id
        WHERE r.receivable_id IS NOT NULL
          AND COALESCE(r.amount, 0) > 0
          AND NOT EXISTS (
              SELECT 1
              FROM customer_receipt_settlements s
              WHERE s.receipt_id = r.id
                AND s.receivable_id = r.receivable_id
          )
        ON CONFLICT (receipt_id, receivable_id) DO NOTHING;
        """,
    ),
    (
        "20260527_009_purchase_document_unique_numbers",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS purchase_orders_order_no_uidx
            ON purchase_orders(order_no)
            WHERE order_no IS NOT NULL AND order_no<>'';
        CREATE UNIQUE INDEX IF NOT EXISTS purchase_receipts_receipt_no_uidx
            ON purchase_receipts(receipt_no)
            WHERE receipt_no IS NOT NULL AND receipt_no<>'';
        CREATE UNIQUE INDEX IF NOT EXISTS supplier_payments_payment_no_uidx
            ON supplier_payments(payment_no)
            WHERE payment_no IS NOT NULL AND payment_no<>'';
        """,
    ),
    (
        "20260527_010_supplier_payment_settlement_detail",
        """
        CREATE TABLE IF NOT EXISTS supplier_payment_settlements (
            id SERIAL PRIMARY KEY,
            payment_id INTEGER NOT NULL REFERENCES supplier_payments(id) ON DELETE CASCADE,
            payable_id INTEGER NOT NULL REFERENCES supplier_payables(id) ON DELETE CASCADE,
            applied_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS supplier_payment_settlements_payment_payable_uidx
            ON supplier_payment_settlements(payment_id, payable_id);

        INSERT INTO supplier_payment_settlements (payment_id, payable_id, applied_amount)
        SELECT
            p.id,
            sp.id,
            CASE
                WHEN COALESCE(sp.balance, 0) + COALESCE(sp.paid_amount, 0) > 0
                    THEN LEAST(COALESCE(p.amount, 0), COALESCE(sp.balance, 0) + COALESCE(sp.paid_amount, 0))
                ELSE COALESCE(p.amount, 0)
            END AS applied_amount
        FROM supplier_payments p
        JOIN supplier_payables sp
          ON sp.supplier_id = p.supplier_id
         AND sp.id = (
             SELECT sp2.id
             FROM supplier_payables sp2
             WHERE sp2.supplier_id = p.supplier_id
             ORDER BY sp2.id
             LIMIT 1
         )
        WHERE COALESCE(p.amount, 0) > 0
          AND NOT EXISTS (
              SELECT 1
              FROM supplier_payment_settlements s
              WHERE s.payment_id = p.id
                AND s.payable_id = sp.id
          )
        ON CONFLICT (payment_id, payable_id) DO NOTHING;
        """,
    ),
    (
        "20260531_001_finance_ar_ap_document_flows",
        """
        CREATE TABLE IF NOT EXISTS customer_receipts (id SERIAL PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS supplier_payments (id SERIAL PRIMARY KEY);

        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS receipt_no VARCHAR(120);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS receipt_date DATE DEFAULT CURRENT_DATE;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS customer_id INTEGER;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS payment_method VARCHAR(120);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS bank_account VARCHAR(255);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS receivable_id INTEGER;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS status VARCHAR(80) DEFAULT '已确认';

        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS payment_no VARCHAR(120);
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS payment_date DATE DEFAULT CURRENT_DATE;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS supplier_id INTEGER;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS payment_method VARCHAR(120);
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS bank_account VARCHAR(255);
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS operator_id INTEGER;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS payable_id INTEGER;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS status VARCHAR(80) DEFAULT '已确认';

        CREATE UNIQUE INDEX IF NOT EXISTS customer_receipts_receipt_no_uidx
            ON customer_receipts(receipt_no)
            WHERE receipt_no IS NOT NULL AND receipt_no<>'';
        CREATE UNIQUE INDEX IF NOT EXISTS supplier_payments_payment_no_uidx
            ON supplier_payments(payment_no)
            WHERE payment_no IS NOT NULL AND payment_no<>'';
        CREATE INDEX IF NOT EXISTS idx_customer_receipts_partner_date
            ON customer_receipts(customer_id, receipt_date DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_supplier_payments_partner_date
            ON supplier_payments(supplier_id, payment_date DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_customer_receipt_settlements_receivable
            ON customer_receipt_settlements(receivable_id);
        CREATE INDEX IF NOT EXISTS idx_supplier_payment_settlements_payable
            ON supplier_payment_settlements(payable_id);
        """,
    ),
    (
        "20260528_002_document_line_trace_columns",
        """
        ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE purchase_requisition_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);

        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS line_serial_no VARCHAR(120);
        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS expected_date DATE;

        ALTER TABLE sales_order_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE sales_order_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE sales_order_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE sales_order_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE sales_order_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE sales_order_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE sales_order_items ADD COLUMN IF NOT EXISTS line_serial_no VARCHAR(120);

        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS process_name VARCHAR(255);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS warehouse VARCHAR(120);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS location VARCHAR(120);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS line_serial_no VARCHAR(120);

        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS line_serial_no VARCHAR(120);

        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE wo_material_items ADD COLUMN IF NOT EXISTS line_serial_no VARCHAR(120);

        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS spec VARCHAR(255);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS unit VARCHAR(80);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);

        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS product_id INTEGER;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS quantity NUMERIC(14, 3) DEFAULT 0;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS line_serial_no VARCHAR(120);

        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE inventory_adjustments ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);

        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);

        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);

        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        """,
    ),
    (
        "20260528_003_project_ledger_indexes",
        """
        CREATE INDEX IF NOT EXISTS idx_sales_orders_project_code ON sales_orders(project_code);
        CREATE INDEX IF NOT EXISTS idx_sales_orders_serial_no ON sales_orders(serial_no);
        CREATE INDEX IF NOT EXISTS idx_sales_orders_cost_object_id ON sales_orders(cost_object_id);
        CREATE INDEX IF NOT EXISTS idx_sales_orders_delivery_date ON sales_orders(delivery_date);
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_project_code ON purchase_orders(project_code);
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_serial_no ON purchase_orders(serial_no);
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_cost_object_id ON purchase_orders(cost_object_id);
        CREATE INDEX IF NOT EXISTS idx_purchase_order_items_order_id ON purchase_order_items(order_id);
        CREATE INDEX IF NOT EXISTS idx_work_orders_project_code ON work_orders(project_code);
        CREATE INDEX IF NOT EXISTS idx_work_orders_serial_no ON work_orders(serial_no);
        CREATE INDEX IF NOT EXISTS idx_work_orders_cost_object_id ON work_orders(cost_object_id);
        CREATE INDEX IF NOT EXISTS idx_sales_shipments_project_code ON sales_shipments(project_code);
        CREATE INDEX IF NOT EXISTS idx_sales_shipments_serial_no ON sales_shipments(serial_no);
        CREATE INDEX IF NOT EXISTS idx_supplier_payables_doc ON supplier_payables(doc_type, doc_id, doc_no);
        CREATE INDEX IF NOT EXISTS idx_subcontract_orders_project_code ON subcontract_orders(project_code);
        CREATE INDEX IF NOT EXISTS idx_subcontract_orders_serial_no ON subcontract_orders(serial_no);
        CREATE INDEX IF NOT EXISTS idx_subcontract_orders_cost_object_id ON subcontract_orders(cost_object_id);
        """,
    ),
    (
        "20260529_001_production_status_trace",
        """
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS production_stage VARCHAR(50) DEFAULT '创建';
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS status_changed_by INTEGER;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS responsible_person VARCHAR(120);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS priority VARCHAR(50) DEFAULT '普通';
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS production_type VARCHAR(80);
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS owner_role VARCHAR(80);

        CREATE TABLE IF NOT EXISTS work_order_status_logs (
            id SERIAL PRIMARY KEY,
            work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            from_status VARCHAR(80),
            to_status VARCHAR(80) NOT NULL,
            from_stage VARCHAR(80),
            to_stage VARCHAR(80) NOT NULL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            changed_by INTEGER,
            remark TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_work_order_status_logs_work_order
            ON work_order_status_logs(work_order_id, changed_at DESC);

        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS parent_work_order_id INTEGER;
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS required_date DATE;
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS arrival_status VARCHAR(80) DEFAULT '未发料';
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS shortage_qty NUMERIC(14, 3) DEFAULT 0;
        ALTER TABLE subcontract_orders ADD COLUMN IF NOT EXISTS received_qty NUMERIC(14, 3) DEFAULT 0;
        CREATE INDEX IF NOT EXISTS idx_subcontract_orders_parent_work_order
            ON subcontract_orders(parent_work_order_id);
        CREATE INDEX IF NOT EXISTS idx_subcontract_orders_required_date
            ON subcontract_orders(required_date);
        """,
    ),
    (
        "20260529_002_engineering_technical_confirmation",
        """
        CREATE TABLE IF NOT EXISTS engineering_technical_confirmations (
            id SERIAL PRIMARY KEY,
            confirm_no VARCHAR(80) UNIQUE NOT NULL,
            confirm_date DATE DEFAULT CURRENT_DATE,
            sales_order_id INTEGER,
            product_id INTEGER,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            machine_model VARCHAR(160),
            bom_id INTEGER,
            routing_id INTEGER,
            work_center_id INTEGER,
            drawing_no VARCHAR(160),
            drawing_version VARCHAR(80),
            key_control_points TEXT,
            status VARCHAR(50) DEFAULT '草稿',
            owner VARCHAR(120),
            blocked_reason TEXT,
            next_action VARCHAR(200),
            remark TEXT,
            created_by INTEGER,
            confirmed_by INTEGER,
            confirmed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS confirm_no VARCHAR(80);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS confirm_date DATE DEFAULT CURRENT_DATE;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS sales_order_id INTEGER;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS product_id INTEGER;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS machine_model VARCHAR(160);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS bom_id INTEGER;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS routing_id INTEGER;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS work_center_id INTEGER;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS drawing_no VARCHAR(160);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS drawing_version VARCHAR(80);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS key_control_points TEXT;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '草稿';
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS owner VARCHAR(120);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS next_action VARCHAR(200);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS confirmed_by INTEGER;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_engineering_confirm_no
            ON engineering_technical_confirmations(confirm_no);
        CREATE INDEX IF NOT EXISTS idx_engineering_confirm_project_serial
            ON engineering_technical_confirmations(project_code, serial_no);
        CREATE INDEX IF NOT EXISTS idx_engineering_confirm_sales_order
            ON engineering_technical_confirmations(sales_order_id);
        CREATE INDEX IF NOT EXISTS idx_engineering_confirm_status
            ON engineering_technical_confirmations(status);
        """,
    ),
    (
        "20260530_001_subcontract_document_closure",
        """
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS submitted_by INTEGER;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS audited_by INTEGER;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS audited_at TIMESTAMP;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS voided_by INTEGER;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS posted BOOLEAN DEFAULT FALSE;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP;
        ALTER TABLE subcontract_issue_orders ADD COLUMN IF NOT EXISTS reverse_posted_at TIMESTAMP;

        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS submitted_by INTEGER;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS audited_by INTEGER;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS audited_at TIMESTAMP;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS voided_by INTEGER;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS posted BOOLEAN DEFAULT FALSE;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS reverse_posted_at TIMESTAMP;

        CREATE TABLE IF NOT EXISTS subcontract_issue_lines (
            id SERIAL PRIMARY KEY,
            issue_id INTEGER NOT NULL REFERENCES subcontract_issue_orders(id) ON DELETE CASCADE,
            subcontract_order_id INTEGER,
            product_id INTEGER,
            material_code VARCHAR(120),
            material_name VARCHAR(240),
            material_spec VARCHAR(240),
            unit VARCHAR(80),
            quantity NUMERIC(14, 3) DEFAULT 0,
            warehouse_id INTEGER,
            location_id INTEGER,
            lot_no VARCHAR(120),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_subcontract_issue_lines_issue ON subcontract_issue_lines(issue_id);
        CREATE INDEX IF NOT EXISTS idx_subcontract_issue_lines_product ON subcontract_issue_lines(product_id);

        CREATE TABLE IF NOT EXISTS subcontract_receive_lines (
            id SERIAL PRIMARY KEY,
            receive_id INTEGER NOT NULL REFERENCES subcontract_receive_orders(id) ON DELETE CASCADE,
            subcontract_order_id INTEGER,
            product_id INTEGER,
            material_code VARCHAR(120),
            material_name VARCHAR(240),
            material_spec VARCHAR(240),
            unit VARCHAR(80),
            quantity NUMERIC(14, 3) DEFAULT 0,
            scrap_quantity NUMERIC(14, 3) DEFAULT 0,
            warehouse_id INTEGER,
            location_id INTEGER,
            lot_no VARCHAR(120),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_subcontract_receive_lines_receive ON subcontract_receive_lines(receive_id);
        CREATE INDEX IF NOT EXISTS idx_subcontract_receive_lines_product ON subcontract_receive_lines(product_id);
        """,
    ),
    (
        "20260531_001_after_sale_boundary_fields",
        """
        ALTER TABLE machine_service_return_visits ADD COLUMN IF NOT EXISTS satisfaction_score NUMERIC(3, 1);
        """,
    ),
    (
        "20260531_002_cash_bank_slice",
        """
        CREATE TABLE IF NOT EXISTS cash_bank_accounts (
            id SERIAL PRIMARY KEY,
            account_code VARCHAR(80) NOT NULL UNIQUE,
            account_name VARCHAR(160) NOT NULL,
            account_type VARCHAR(30) NOT NULL DEFAULT 'bank',
            bank_name VARCHAR(160),
            bank_branch VARCHAR(160),
            bank_account_no VARCHAR(120),
            currency VARCHAR(20) NOT NULL DEFAULT 'CNY',
            opening_balance NUMERIC(14, 2) NOT NULL DEFAULT 0,
            current_balance NUMERIC(14, 2) NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            owner_department VARCHAR(120),
            owner_person VARCHAR(120),
            remark TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS account_code VARCHAR(80);
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS account_name VARCHAR(160);
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS account_type VARCHAR(30) NOT NULL DEFAULT 'bank';
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS bank_name VARCHAR(160);
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS bank_branch VARCHAR(160);
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS bank_account_no VARCHAR(120);
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS currency VARCHAR(20) NOT NULL DEFAULT 'CNY';
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS opening_balance NUMERIC(14, 2) NOT NULL DEFAULT 0;
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS current_balance NUMERIC(14, 2) NOT NULL DEFAULT 0;
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'active';
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS owner_department VARCHAR(120);
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS owner_person VARCHAR(120);
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE UNIQUE INDEX IF NOT EXISTS cash_bank_accounts_code_uidx
            ON cash_bank_accounts(account_code);
        CREATE INDEX IF NOT EXISTS idx_cash_bank_accounts_type_status
            ON cash_bank_accounts(account_type, status);

        CREATE TABLE IF NOT EXISTS cash_bank_journal_entries (
            id SERIAL PRIMARY KEY,
            account_id INTEGER REFERENCES cash_bank_accounts(id),
            entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
            entry_no VARCHAR(120),
            source_type VARCHAR(80),
            source_no VARCHAR(120),
            direction VARCHAR(10) NOT NULL DEFAULT 'in',
            amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
            balance_after NUMERIC(14, 2),
            partner_type VARCHAR(40),
            partner_name VARCHAR(160),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            summary TEXT,
            status VARCHAR(30) NOT NULL DEFAULT 'confirmed',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS account_id INTEGER;
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS entry_date DATE NOT NULL DEFAULT CURRENT_DATE;
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS entry_no VARCHAR(120);
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS direction VARCHAR(10) NOT NULL DEFAULT 'in';
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) NOT NULL DEFAULT 0;
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS balance_after NUMERIC(14, 2);
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS partner_type VARCHAR(40);
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS partner_name VARCHAR(160);
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS summary TEXT;
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'confirmed';
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_cash_bank_journal_account_date
            ON cash_bank_journal_entries(account_id, entry_date DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_cash_bank_journal_source
            ON cash_bank_journal_entries(source_type, source_no);
        CREATE INDEX IF NOT EXISTS idx_cash_bank_journal_trace
            ON cash_bank_journal_entries(project_code, serial_no);
        """,
    ),
    (
        "20260531_003_finance_phase1_trace_and_purchase_invoices",
        """
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;

        UPDATE customer_receivables cr
        SET project_code=COALESCE(NULLIF(cr.project_code,''), so.project_code),
            serial_no=COALESCE(NULLIF(cr.serial_no,''), so.serial_no),
            cost_object_id=COALESCE(cr.cost_object_id, so.cost_object_id)
        FROM sales_orders so
        WHERE cr.source_type='sales_order'
          AND (cr.source_id=so.id OR cr.source_no=so.order_no);

        UPDATE customer_receivables cr
        SET project_code=COALESCE(NULLIF(cr.project_code,''), ss.project_code, so.project_code),
            serial_no=COALESCE(NULLIF(cr.serial_no,''), ss.serial_no, so.serial_no),
            cost_object_id=COALESCE(cr.cost_object_id, so.cost_object_id)
        FROM sales_shipments ss
        LEFT JOIN sales_orders so ON so.id=ss.order_id
        WHERE cr.source_type='sales_shipment'
          AND (cr.source_id=ss.id OR cr.source_no=ss.shipment_no);

        CREATE INDEX IF NOT EXISTS idx_customer_receivables_trace
            ON customer_receivables(project_code, serial_no);

        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS due_date DATE;

        UPDATE supplier_payables sp
        SET project_code=COALESCE(NULLIF(sp.project_code,''), po.project_code),
            serial_no=COALESCE(NULLIF(sp.serial_no,''), po.serial_no),
            cost_object_id=COALESCE(sp.cost_object_id, po.cost_object_id)
        FROM purchase_orders po
        WHERE sp.doc_type='purchase_order'
          AND sp.doc_id=po.id;

        UPDATE supplier_payables sp
        SET project_code=COALESCE(NULLIF(sp.project_code,''), pr.project_code, po.project_code),
            serial_no=COALESCE(NULLIF(sp.serial_no,''), pr.serial_no, po.serial_no),
            cost_object_id=COALESCE(sp.cost_object_id, po.cost_object_id)
        FROM purchase_receipts pr
        LEFT JOIN purchase_orders po ON po.id=pr.order_id
        WHERE sp.doc_type='purchase_receipt'
          AND (sp.doc_id=pr.id OR sp.doc_no=pr.receipt_no);

        UPDATE supplier_payables sp
        SET project_code=COALESCE(NULLIF(sp.project_code,''), so.project_code),
            serial_no=COALESCE(NULLIF(sp.serial_no,''), so.serial_no),
            cost_object_id=COALESCE(sp.cost_object_id, so.cost_object_id)
        FROM subcontract_orders so
        WHERE sp.doc_type IN ('subcontract_order','subcontract_receipt')
          AND (sp.doc_id=so.id OR sp.doc_no=so.order_no);

        CREATE INDEX IF NOT EXISTS idx_supplier_payables_trace
            ON supplier_payables(project_code, serial_no);

        CREATE TABLE IF NOT EXISTS purchase_invoices (
            id SERIAL PRIMARY KEY,
            invoice_no VARCHAR(120),
            supplier_id INTEGER,
            source_type VARCHAR(80),
            source_id INTEGER,
            source_no VARCHAR(120),
            invoice_date DATE DEFAULT CURRENT_DATE,
            amount NUMERIC(14, 2) DEFAULT 0,
            tax_amount NUMERIC(14, 2) DEFAULT 0,
            amount_with_tax NUMERIC(14, 2) DEFAULT 0,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            status VARCHAR(80) DEFAULT 'draft',
            remark TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS invoice_no VARCHAR(120);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS supplier_id INTEGER;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS invoice_date DATE DEFAULT CURRENT_DATE;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS amount_with_tax NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS status VARCHAR(80) DEFAULT 'draft';
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE UNIQUE INDEX IF NOT EXISTS purchase_invoices_invoice_no_uidx
            ON purchase_invoices(invoice_no)
            WHERE invoice_no IS NOT NULL AND invoice_no<>'';
        CREATE INDEX IF NOT EXISTS idx_purchase_invoices_source
            ON purchase_invoices(source_type, source_id, source_no);
        CREATE INDEX IF NOT EXISTS idx_purchase_invoices_trace
            ON purchase_invoices(project_code, serial_no);
        CREATE TABLE IF NOT EXISTS sales_invoices (
            id SERIAL PRIMARY KEY
        );
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS invoice_no VARCHAR(120);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS customer_id INTEGER;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS invoice_date DATE DEFAULT CURRENT_DATE;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS tax_amount NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS amount_with_tax NUMERIC(14, 2) DEFAULT 0;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS status VARCHAR(80) DEFAULT 'draft';
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE UNIQUE INDEX IF NOT EXISTS sales_invoices_invoice_no_uidx
            ON sales_invoices(invoice_no)
            WHERE invoice_no IS NOT NULL AND invoice_no<>'';
        CREATE INDEX IF NOT EXISTS idx_sales_invoices_source
            ON sales_invoices(source_type, source_id, source_no);
        CREATE INDEX IF NOT EXISTS idx_sales_invoices_trace
            ON sales_invoices(project_code, serial_no);
        """,
    ),
    (
        "20260601_001_block_dirty_master_text",
        """
        CREATE OR REPLACE FUNCTION block_dirty_master_text()
        RETURNS trigger AS $$
        DECLARE
            column_name TEXT;
            column_value TEXT;
            codepoint INTEGER;
            dirty_codepoints INTEGER[] := ARRAY[
                65533, 38337, 38335, 37721, 37711, 37713, 37714, 37723,
                37734, 37736, 37756, 25652, 37911, 37922, 37826, 38322,
                29831, 23535, 28654, 35120, 31707, 32139, 32495, 38315,
                39582, 65085, 20751, 28186, 31826, 12517, 31825, 26948,
                37727, 8364, 8482, 339
            ];
        BEGIN
            FOREACH column_name IN ARRAY TG_ARGV LOOP
                column_value := to_jsonb(NEW)->>column_name;
                IF column_value IS NULL OR column_value = '' THEN
                    CONTINUE;
                END IF;
                IF POSITION(CHR(63) || CHR(63) || CHR(63) IN column_value) > 0 THEN
                    RAISE EXCEPTION 'dirty ERP master text blocked in %.%', TG_TABLE_NAME, column_name
                        USING ERRCODE = '22023';
                END IF;
                FOREACH codepoint IN ARRAY dirty_codepoints LOOP
                    IF POSITION(chr(codepoint) IN column_value) > 0 THEN
                        RAISE EXCEPTION 'dirty ERP master text blocked in %.%', TG_TABLE_NAME, column_name
                            USING ERRCODE = '22023';
                    END IF;
                END LOOP;
            END LOOP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DO $$
        BEGIN
            IF to_regclass('products') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS trg_block_dirty_products_text ON products;
                CREATE TRIGGER trg_block_dirty_products_text
                    BEFORE INSERT OR UPDATE ON products
                    FOR EACH ROW EXECUTE FUNCTION block_dirty_master_text(
                        'code', 'name', 'category', 'specification', 'unit',
                        'remark', 'aux_unit', 'cost_method', 'item_type',
                        'barcode', 'drawing_no', 'material_grade', 'brand',
                        'origin_place', 'default_warehouse', 'default_location',
                        'default_supplier_name', 'abc_class', 'status'
                    );
            END IF;

            IF to_regclass('suppliers') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS trg_block_dirty_suppliers_text ON suppliers;
                CREATE TRIGGER trg_block_dirty_suppliers_text
                    BEFORE INSERT OR UPDATE ON suppliers
                    FOR EACH ROW EXECUTE FUNCTION block_dirty_master_text(
                        'name', 'contact_person', 'phone', 'address', 'remark'
                    );
            END IF;

            IF to_regclass('customers') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS trg_block_dirty_customers_text ON customers;
                CREATE TRIGGER trg_block_dirty_customers_text
                    BEFORE INSERT OR UPDATE ON customers
                    FOR EACH ROW EXECUTE FUNCTION block_dirty_master_text(
                        'name', 'contact_person', 'phone', 'address',
                        'customer_level', 'remark'
                    );
            END IF;

            IF to_regclass('warehouses') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS trg_block_dirty_warehouses_text ON warehouses;
                CREATE TRIGGER trg_block_dirty_warehouses_text
                    BEFORE INSERT OR UPDATE ON warehouses
                    FOR EACH ROW EXECUTE FUNCTION block_dirty_master_text(
                        'code', 'name', 'remark'
                    );
            END IF;

            IF to_regclass('locations') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS trg_block_dirty_locations_text ON locations;
                CREATE TRIGGER trg_block_dirty_locations_text
                    BEFORE INSERT OR UPDATE ON locations
                    FOR EACH ROW EXECUTE FUNCTION block_dirty_master_text(
                        'code', 'name', 'remark'
                    );
            END IF;
        END;
        $$;
        """,
    ),
    (
        "20260601_002_purchase_order_draft_supplier_optional",
        """
        ALTER TABLE purchase_orders ALTER COLUMN supplier_id DROP NOT NULL;
        """,
    ),
    (
        "20260602_003_operation_log_request_context",
        """
        ALTER TABLE operation_logs ADD COLUMN IF NOT EXISTS request_path VARCHAR(500);
        ALTER TABLE operation_logs ADD COLUMN IF NOT EXISTS request_method VARCHAR(20);
        ALTER TABLE operation_logs ADD COLUMN IF NOT EXISTS remote_addr VARCHAR(80);
        ALTER TABLE operation_logs ADD COLUMN IF NOT EXISTS user_agent TEXT;
        ALTER TABLE operation_logs ADD COLUMN IF NOT EXISTS trace_id VARCHAR(80);
        """,
    ),
    (
        "20260602_004_core_fk_not_valid_constraints",
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='sales_orders')
               AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='customers')
               AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_sales_orders_customer_id_customers_not_valid') THEN
                ALTER TABLE sales_orders
                    ADD CONSTRAINT fk_sales_orders_customer_id_customers_not_valid
                    FOREIGN KEY (customer_id) REFERENCES customers(id) NOT VALID;
            END IF;

            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='sales_order_items')
               AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='sales_orders')
               AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_sales_order_items_order_id_sales_orders_not_valid') THEN
                ALTER TABLE sales_order_items
                    ADD CONSTRAINT fk_sales_order_items_order_id_sales_orders_not_valid
                    FOREIGN KEY (order_id) REFERENCES sales_orders(id) NOT VALID;
            END IF;

            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='purchase_orders')
               AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='suppliers')
               AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_purchase_orders_supplier_id_suppliers_not_valid') THEN
                ALTER TABLE purchase_orders
                    ADD CONSTRAINT fk_purchase_orders_supplier_id_suppliers_not_valid
                    FOREIGN KEY (supplier_id) REFERENCES suppliers(id) NOT VALID;
            END IF;

            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='purchase_order_items')
               AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='purchase_orders')
               AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_purchase_order_items_order_id_purchase_orders_not_valid') THEN
                ALTER TABLE purchase_order_items
                    ADD CONSTRAINT fk_purchase_order_items_order_id_purchase_orders_not_valid
                    FOREIGN KEY (order_id) REFERENCES purchase_orders(id) NOT VALID;
            END IF;

            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='stock_transactions')
               AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='products')
               AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_stock_transactions_product_id_products_not_valid') THEN
                ALTER TABLE stock_transactions
                    ADD CONSTRAINT fk_stock_transactions_product_id_products_not_valid
                    FOREIGN KEY (product_id) REFERENCES products(id) NOT VALID;
            END IF;

            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='work_orders')
               AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='products')
               AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_work_orders_product_id_products_not_valid') THEN
                ALTER TABLE work_orders
                    ADD CONSTRAINT fk_work_orders_product_id_products_not_valid
                    FOREIGN KEY (product_id) REFERENCES products(id) NOT VALID;
            END IF;
        END;
        $$;
        """,
    ),
    (
        "20260603_001_work_order_change_control",
        """
        CREATE TABLE IF NOT EXISTS work_order_change_records (
            id SERIAL PRIMARY KEY,
            change_no VARCHAR(120) NOT NULL UNIQUE,
            work_order_id INTEGER NOT NULL REFERENCES work_orders(id) ON DELETE CASCADE,
            change_type VARCHAR(80) NOT NULL,
            requested_by INTEGER,
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            owner_role VARCHAR(120) DEFAULT '生产计划/技术',
            current_snapshot JSONB DEFAULT '{}'::jsonb,
            proposed_change TEXT,
            impact_assessment TEXT,
            blocked_reason TEXT,
            next_action TEXT,
            downstream_impact TEXT,
            status VARCHAR(80) NOT NULL DEFAULT '已记录',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_work_order_change_records_work_order
            ON work_order_change_records(work_order_id, requested_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_work_order_change_records_status
            ON work_order_change_records(status);
        """,
    ),
    (
        "20260603_002_production_schedule_dispatch_loop",
        """
        CREATE TABLE IF NOT EXISTS production_schedules (
            id SERIAL PRIMARY KEY
        );
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS schedule_no VARCHAR(120);
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS work_order_id INTEGER;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS work_order_process_id INTEGER;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS routing_operation_id INTEGER;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS work_center_id INTEGER;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS planned_start_date DATE;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS planned_end_date DATE;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS actual_start_date DATE;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS actual_end_date DATE;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS owner_role VARCHAR(120) DEFAULT '生产计划';
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS responsible_person VARCHAR(120);
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS next_action TEXT;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS downstream_impact TEXT;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS dispatch_status VARCHAR(80) DEFAULT '待派工';
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS dispatched_to VARCHAR(120);
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMP;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS rescheduled_at TIMESTAMP;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS status VARCHAR(80) DEFAULT 'scheduled';
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS updated_by INTEGER;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE production_schedules ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_production_schedules_work_order
            ON production_schedules(work_order_id);
        CREATE INDEX IF NOT EXISTS idx_production_schedules_work_center_date
            ON production_schedules(work_center_id, planned_start_date, planned_end_date);
        CREATE INDEX IF NOT EXISTS idx_production_schedules_dispatch_status
            ON production_schedules(dispatch_status);
        """,
    ),
    (
        "20260606_001_production_execution_wip_closure",
        """
        CREATE TABLE IF NOT EXISTS operation_reports (id SERIAL PRIMARY KEY);
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS downstream_impact TEXT;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS routing_operation_id INTEGER;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS owner_role VARCHAR(120);
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS downstream_impact TEXT;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS wip_quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_wip_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS downstream_impact TEXT;
        ALTER TABLE production_schedules DROP CONSTRAINT IF EXISTS production_schedules_status_check;
        ALTER TABLE production_schedules ADD CONSTRAINT production_schedules_status_check
            CHECK (status IS NULL OR status IN ('scheduled','dispatched','rescheduled','paused','completed','cancelled'));
        ALTER TABLE work_order_processes DROP CONSTRAINT IF EXISTS work_order_processes_status_check;
        ALTER TABLE work_order_processes ADD CONSTRAINT work_order_processes_status_check
            CHECK (status IS NULL OR status IN ('not_started','ready','in_progress','paused','rework_pending','scrap_pending','completed','cancelled'));
        CREATE INDEX IF NOT EXISTS idx_work_order_processes_status
            ON work_order_processes(status);
        CREATE INDEX IF NOT EXISTS idx_work_order_processes_work_center
            ON work_order_processes(work_center_id);
        CREATE INDEX IF NOT EXISTS idx_operation_reports_process
            ON operation_reports(work_order_process_id, status);
        """,
    ),
    (
        "20260603_002_chart_of_accounts",
        """
        CREATE TABLE IF NOT EXISTS chart_of_accounts (
            id SERIAL PRIMARY KEY,
            code VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            parent_id INTEGER,
            account_type VARCHAR(80) DEFAULT '资产类',
            balance_direction VARCHAR(10) DEFAULT '借方',
            is_leaf BOOLEAN DEFAULT TRUE,
            status VARCHAR(20) DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS parent_id INTEGER;
        ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS account_type VARCHAR(80) DEFAULT '资产类';
        ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS balance_direction VARCHAR(10) DEFAULT '借方';
        ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS is_leaf BOOLEAN DEFAULT TRUE;
        ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'active';
        ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE chart_of_accounts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_chart_of_accounts_parent
            ON chart_of_accounts(parent_id);
        CREATE INDEX IF NOT EXISTS idx_chart_of_accounts_type
            ON chart_of_accounts(account_type);
        CREATE INDEX IF NOT EXISTS idx_chart_of_accounts_status
            ON chart_of_accounts(status);
        """,
    ),
    (
        "20260603_003_inventory_numeric_precision",
        """
        CREATE TABLE IF NOT EXISTS transfer_order_items (
            id SERIAL PRIMARY KEY,
            transfer_id INTEGER NOT NULL REFERENCES transfer_orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            quantity NUMERIC(14,3) NOT NULL,
            lot_no VARCHAR(100),
            serial_no VARCHAR(100),
            unit_cost NUMERIC(14,2) DEFAULT 0,
            amount NUMERIC(14,2) DEFAULT 0,
            remark TEXT
        );
        ALTER TABLE transfer_order_items ALTER COLUMN quantity TYPE NUMERIC(14,3);
        ALTER TABLE transfer_order_items ALTER COLUMN unit_cost TYPE NUMERIC(14,2);
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE transfer_order_items ALTER COLUMN amount TYPE NUMERIC(14,2);
        CREATE TABLE IF NOT EXISTS inventory_check_order_items (
            id SERIAL PRIMARY KEY,
            check_id INTEGER NOT NULL REFERENCES inventory_check_orders(id) ON DELETE CASCADE,
            product_id INTEGER NOT NULL,
            book_qty NUMERIC(14,3) NOT NULL DEFAULT 0,
            actual_qty NUMERIC(14,3) NOT NULL DEFAULT 0,
            diff_qty NUMERIC(14,3) NOT NULL DEFAULT 0,
            lot_no VARCHAR(100),
            serial_no VARCHAR(100),
            unit_cost NUMERIC(14,2) DEFAULT 0,
            amount NUMERIC(14,2) DEFAULT 0
        );
        ALTER TABLE inventory_check_order_items ALTER COLUMN book_qty TYPE NUMERIC(14,3);
        ALTER TABLE inventory_check_order_items ALTER COLUMN actual_qty TYPE NUMERIC(14,3);
        ALTER TABLE inventory_check_order_items ALTER COLUMN diff_qty TYPE NUMERIC(14,3);
        ALTER TABLE inventory_check_order_items ALTER COLUMN unit_cost TYPE NUMERIC(14,2);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE inventory_check_order_items ALTER COLUMN amount TYPE NUMERIC(14,2);
        """,
    ),
    (
        "20260603_005_inventory_check_difference_amount_snapshot",
        """
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE inventory_check_order_items ALTER COLUMN amount TYPE NUMERIC(14,2);
        UPDATE inventory_check_order_items
        SET amount = ROUND(COALESCE(diff_qty, 0) * COALESCE(unit_cost, 0), 2)
        WHERE ABS(COALESCE(amount, 0) - COALESCE(diff_qty, 0) * COALESCE(unit_cost, 0)) > 0.01;
        """,
    ),
    (
        "20260614_001_inventory_balance_trace_consistency",
        """
        ALTER TABLE inventory_balances ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS book_qty_snapshot NUMERIC(14,3);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS book_qty_current NUMERIC(14,3);
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS posted_diff_qty NUMERIC(14,3);

        CREATE INDEX IF NOT EXISTS idx_stock_transactions_reference_or_source
            ON stock_transactions (reference_no, source_doc_no);
        CREATE INDEX IF NOT EXISTS idx_stock_transactions_balance_dims
            ON stock_transactions (product_id, warehouse_id, location_id, project_code, lot_no, serial_no);

        WITH duplicate_balance_groups AS (
            SELECT
                MIN(id) AS keep_id,
                ARRAY_AGG(id ORDER BY id) AS ids,
                SUM(COALESCE(quantity, 0)) AS merged_quantity,
                SUM(COALESCE(locked_qty, 0)) AS merged_locked_qty,
                CASE
                    WHEN SUM(COALESCE(quantity, 0)) <> 0
                    THEN SUM(COALESCE(quantity, 0) * COALESCE(unit_cost, 0)) / NULLIF(SUM(COALESCE(quantity, 0)), 0)
                    ELSE MAX(COALESCE(unit_cost, 0))
                END AS merged_unit_cost,
                MAX(updated_at) AS merged_updated_at
            FROM inventory_balances
            GROUP BY
                product_id,
                COALESCE(warehouse_id, 0),
                COALESCE(location_id, 0),
                COALESCE(project_code, ''),
                COALESCE(lot_no, ''),
                COALESCE(serial_no, '')
            HAVING COUNT(*) > 1
        ),
        updated_keep_rows AS (
            UPDATE inventory_balances ib
            SET
                quantity = dbg.merged_quantity,
                locked_qty = dbg.merged_locked_qty,
                unit_cost = dbg.merged_unit_cost,
                updated_at = COALESCE(dbg.merged_updated_at, NOW())
            FROM duplicate_balance_groups dbg
            WHERE ib.id = dbg.keep_id
            RETURNING dbg.ids, dbg.keep_id
        )
        DELETE FROM inventory_balances ib
        USING updated_keep_rows ukr
        WHERE ib.id = ANY(ukr.ids)
          AND ib.id <> ukr.keep_id;

        CREATE UNIQUE INDEX IF NOT EXISTS idx_inventory_balances_unique_dims
            ON inventory_balances (
                product_id,
                COALESCE(warehouse_id, 0),
                COALESCE(location_id, 0),
                COALESCE(project_code, ''),
                COALESCE(lot_no, ''),
                COALESCE(serial_no, '')
            );
        """,
    ),
    (
        "20260603_004_finance_voucher_system",
        """
        CREATE TABLE IF NOT EXISTS vouchers (
            id SERIAL PRIMARY KEY,
            voucher_no VARCHAR(120) NOT NULL UNIQUE,
            voucher_date DATE NOT NULL DEFAULT CURRENT_DATE,
            voucher_type VARCHAR(80) DEFAULT '记账凭证',
            period_year INTEGER,
            period_month INTEGER,
            total_debit NUMERIC(14,2) DEFAULT 0,
            total_credit NUMERIC(14,2) DEFAULT 0,
            source_type VARCHAR(80),
            source_no VARCHAR(120),
            summary TEXT,
            status VARCHAR(30) DEFAULT '草稿',
            attachment_count INTEGER DEFAULT 0,
            prepared_by INTEGER,
            reviewed_by INTEGER,
            posted_by INTEGER,
            prepared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            posted_at TIMESTAMP,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS voucher_date DATE NOT NULL DEFAULT CURRENT_DATE;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS voucher_type VARCHAR(80) DEFAULT '记账凭证';
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS period_year INTEGER;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS period_month INTEGER;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS total_debit NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS total_credit NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS summary TEXT;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT '草稿';
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS attachment_count INTEGER DEFAULT 0;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS prepared_by INTEGER;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS reviewed_by INTEGER;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS posted_by INTEGER;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS prepared_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_vouchers_date ON vouchers(voucher_date);
        CREATE INDEX IF NOT EXISTS idx_vouchers_status ON vouchers(status);
        CREATE INDEX IF NOT EXISTS idx_vouchers_period ON vouchers(period_year, period_month);

        CREATE TABLE IF NOT EXISTS voucher_lines (
            id SERIAL PRIMARY KEY,
            voucher_id INTEGER NOT NULL REFERENCES vouchers(id) ON DELETE CASCADE,
            line_no INTEGER NOT NULL,
            account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
            summary TEXT,
            debit_amount NUMERIC(14,2) DEFAULT 0,
            credit_amount NUMERIC(14,2) DEFAULT 0,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            partner_type VARCHAR(40),
            partner_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS voucher_id INTEGER;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS line_no INTEGER;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS account_id INTEGER;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS summary TEXT;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS debit_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS credit_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS partner_type VARCHAR(40);
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS partner_id INTEGER;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_voucher_lines_voucher ON voucher_lines(voucher_id);
        CREATE INDEX IF NOT EXISTS idx_voucher_lines_account ON voucher_lines(account_id);

        CREATE TABLE IF NOT EXISTS general_ledger (
            id SERIAL PRIMARY KEY,
            voucher_id INTEGER NOT NULL REFERENCES vouchers(id),
            account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
            account_code VARCHAR(50),
            account_name VARCHAR(255),
            entry_date DATE NOT NULL,
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            debit_amount NUMERIC(14,2) DEFAULT 0,
            credit_amount NUMERIC(14,2) DEFAULT 0,
            summary TEXT,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            voucher_no VARCHAR(120),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS voucher_id INTEGER;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS account_id INTEGER;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS account_code VARCHAR(50);
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS account_name VARCHAR(255);
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS entry_date DATE DEFAULT CURRENT_DATE;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS period_year INTEGER DEFAULT EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS period_month INTEGER DEFAULT EXTRACT(MONTH FROM CURRENT_DATE)::INTEGER;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS debit_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS credit_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS summary TEXT;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS voucher_no VARCHAR(120);
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_general_ledger_account_date ON general_ledger(account_id, entry_date);
        CREATE INDEX IF NOT EXISTS idx_general_ledger_period ON general_ledger(period_year, period_month);
        CREATE INDEX IF NOT EXISTS idx_general_ledger_account_code ON general_ledger(account_code);
        """,
    ),
    (
        "20260604_001_finance_audit_closure_trace",
        """
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS auto_generated BOOLEAN DEFAULT FALSE;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS reversal_of_id INTEGER;
        ALTER TABLE vouchers ADD COLUMN IF NOT EXISTS business_remark TEXT;
        CREATE INDEX IF NOT EXISTS idx_vouchers_source_link
            ON vouchers(source_type, source_id, source_no);

        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        CREATE INDEX IF NOT EXISTS idx_voucher_lines_trace
            ON voucher_lines(project_code, serial_no);

        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        CREATE INDEX IF NOT EXISTS idx_general_ledger_source
            ON general_ledger(source_type, source_id, source_no);
        CREATE INDEX IF NOT EXISTS idx_general_ledger_trace
            ON general_ledger(project_code, serial_no);

        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS account_id INTEGER;
        ALTER TABLE cash_bank_accounts ADD COLUMN IF NOT EXISTS account_code_link VARCHAR(50);

        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS unapplied_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS receipt_kind VARCHAR(80) DEFAULT 'customer_receipt';
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS fund_direction VARCHAR(20) DEFAULT 'in';
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS unapplied_amount NUMERIC(14,2) DEFAULT 0;

        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS expected_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS confirmed_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS variance_amount NUMERIC(14,2) DEFAULT 0;
        CREATE INDEX IF NOT EXISTS idx_supplier_payables_source
            ON supplier_payables(source_type, source_id, source_no);

        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS expected_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS confirmed_amount NUMERIC(14,2) DEFAULT 0;

        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS short_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS scrap_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS deduction_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS variance_amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS variance_reason TEXT;
        ALTER TABLE subcontract_receive_orders ADD COLUMN IF NOT EXISTS responsible_party VARCHAR(120);

        CREATE TABLE IF NOT EXISTS finance_account_mappings (
            id SERIAL PRIMARY KEY,
            mapping_key VARCHAR(80) NOT NULL UNIQUE,
            account_id INTEGER,
            account_code VARCHAR(50),
            account_name VARCHAR(255),
            remark TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_finance_account_mappings_key
            ON finance_account_mappings(mapping_key);

        INSERT INTO chart_of_accounts (code, name, account_type, balance_direction, is_leaf, status, remark)
        VALUES
            ('1002', 'Bank Deposit', 'asset', 'debit', TRUE, 'active', 'Default bank account for generated vouchers'),
            ('1122', 'Accounts Receivable', 'asset', 'debit', TRUE, 'active', 'Default AR account'),
            ('1123', 'Prepayment', 'asset', 'debit', TRUE, 'active', 'Default prepayment account'),
            ('1405', 'Inventory Goods', 'asset', 'debit', TRUE, 'active', 'Default inventory account'),
            ('2202', 'Accounts Payable', 'liability', 'credit', TRUE, 'active', 'Default AP account'),
            ('2203', 'Advance Receipt', 'liability', 'credit', TRUE, 'active', 'Default advance receipt account'),
            ('2221', 'Tax Payable', 'liability', 'credit', TRUE, 'active', 'Default tax account'),
            ('5001', 'Main Business Revenue', 'revenue', 'credit', TRUE, 'active', 'Default revenue account'),
            ('5401', 'Main Business Cost', 'expense', 'debit', TRUE, 'active', 'Default COGS account'),
            ('6602', 'Operating Expense', 'expense', 'debit', TRUE, 'active', 'Default expense account')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO finance_account_mappings (mapping_key, account_code, account_name, remark)
        VALUES
            ('bank', '1002', 'Bank Deposit', 'Generated receipt/payment vouchers'),
            ('accounts_receivable', '1122', 'Accounts Receivable', 'Generated sales invoice vouchers'),
            ('prepayment', '1123', 'Prepayment', 'Unapplied supplier payment'),
            ('inventory', '1405', 'Inventory Goods', 'Purchase receipt and cost carry vouchers'),
            ('accounts_payable', '2202', 'Accounts Payable', 'Generated purchase invoice/payment vouchers'),
            ('advance_receipt', '2203', 'Advance Receipt', 'Unapplied customer receipt'),
            ('tax_payable', '2221', 'Tax Payable', 'Output/input tax placeholder'),
            ('sales_revenue', '5001', 'Main Business Revenue', 'Generated sales invoice vouchers'),
            ('business_cost', '5401', 'Main Business Cost', 'Generated cost carry vouchers'),
            ('operating_expense', '6602', 'Operating Expense', 'Service and indirect expense placeholder')
        ON CONFLICT (mapping_key) DO NOTHING;
        """,
    ),
    (
        "20260603_006_service_card_installation_date_alias",
        """
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS installation_date DATE;
        UPDATE machine_service_cards
        SET installation_date = install_date
        WHERE installation_date IS NULL AND install_date IS NOT NULL;
        """,
    ),
    (
        "20260603_007_account_opening_balances",
        """
        CREATE TABLE IF NOT EXISTS account_opening_balances (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
            year INTEGER NOT NULL,
            month INTEGER NOT NULL DEFAULT 1,
            opening_debit NUMERIC(14,2) DEFAULT 0,
            opening_credit NUMERIC(14,2) DEFAULT 0,
            created_by INTEGER,
            updated_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (account_id, year, month)
        );
        CREATE INDEX IF NOT EXISTS idx_opening_balance_year ON account_opening_balances(year);
        CREATE INDEX IF NOT EXISTS idx_opening_balance_account_year ON account_opening_balances(account_id, year);
        """,
    ),
    (
        "20260605_001_customer_receipt_lines",
        """
        CREATE TABLE IF NOT EXISTS customer_receipt_lines (
            id SERIAL PRIMARY KEY,
            receipt_id INTEGER NOT NULL REFERENCES customer_receipts(id) ON DELETE CASCADE,
            line_no INTEGER NOT NULL DEFAULT 1,
            payment_method VARCHAR(120),
            bank_account VARCHAR(255),
            amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            transaction_no VARCHAR(160),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS receipt_id INTEGER;
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS line_no INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS payment_method VARCHAR(120);
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS bank_account VARCHAR(255);
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS transaction_no VARCHAR(160);
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE customer_receipt_lines ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_customer_receipt_lines_receipt
            ON customer_receipt_lines(receipt_id, line_no);
        """,
    ),
    (
        "20260607_001_customer_receipt_document_kinds",
        """
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS receipt_kind VARCHAR(80) DEFAULT 'customer_receipt';
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS fund_direction VARCHAR(20) DEFAULT 'in';
        UPDATE customer_receipts
        SET receipt_kind='customer_receipt'
        WHERE receipt_kind IS NULL OR receipt_kind='';
        UPDATE customer_receipts
        SET fund_direction='in'
        WHERE fund_direction IS NULL OR fund_direction='';
        CREATE INDEX IF NOT EXISTS idx_customer_receipts_kind_date
            ON customer_receipts(receipt_kind, receipt_date DESC, id DESC);
        """,
    ),
    (
        "20260607_002_supplier_payment_document_kinds",
        """
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS payment_kind VARCHAR(80) DEFAULT 'supplier_payment';
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS fund_direction VARCHAR(20) DEFAULT 'out';
        UPDATE supplier_payments
        SET payment_kind='supplier_payment'
        WHERE payment_kind IS NULL OR payment_kind='';
        UPDATE supplier_payments
        SET fund_direction='out'
        WHERE fund_direction IS NULL OR fund_direction='';
        CREATE INDEX IF NOT EXISTS idx_supplier_payments_kind_date
            ON supplier_payments(payment_kind, payment_date DESC, id DESC);

        CREATE TABLE IF NOT EXISTS supplier_payment_lines (
            id SERIAL PRIMARY KEY,
            payment_id INTEGER NOT NULL REFERENCES supplier_payments(id) ON DELETE CASCADE,
            line_no INTEGER NOT NULL DEFAULT 1,
            payment_method VARCHAR(120),
            bank_account VARCHAR(255),
            amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            transaction_no VARCHAR(160),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS payment_id INTEGER;
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS line_no INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS payment_method VARCHAR(120);
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS bank_account VARCHAR(255);
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS fee_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS transaction_no VARCHAR(160);
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE supplier_payment_lines ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_supplier_payment_lines_payment
            ON supplier_payment_lines(payment_id, line_no);
        """,
    ),
    (
        "20260605_001_project_machine_master",
        """
        CREATE TABLE IF NOT EXISTS project_masters (
            id SERIAL PRIMARY KEY,
            project_code VARCHAR(120) NOT NULL UNIQUE,
            project_name VARCHAR(255),
            customer_id INTEGER,
            product_family VARCHAR(160),
            machine_model VARCHAR(160),
            source_order_no VARCHAR(120),
            owner_name VARCHAR(120),
            planned_delivery_date DATE,
            status VARCHAR(80) DEFAULT '准备',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS project_name VARCHAR(255);
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS customer_id INTEGER;
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS product_family VARCHAR(160);
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS machine_model VARCHAR(160);
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS source_order_no VARCHAR(120);
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS owner_name VARCHAR(120);
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS planned_delivery_date DATE;
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS status VARCHAR(80) DEFAULT '准备';
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE project_masters ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE UNIQUE INDEX IF NOT EXISTS project_masters_project_code_uidx
            ON project_masters(project_code)
            WHERE project_code IS NOT NULL AND project_code <> '';

        CREATE TABLE IF NOT EXISTS machine_serial_masters (
            id SERIAL PRIMARY KEY,
            serial_no VARCHAR(120) NOT NULL UNIQUE,
            project_id INTEGER,
            project_code VARCHAR(120),
            customer_id INTEGER,
            product_id INTEGER,
            product_family VARCHAR(160),
            machine_model VARCHAR(160),
            production_stage VARCHAR(80) DEFAULT '准备',
            service_status VARCHAR(80) DEFAULT '未安装',
            warranty_start_date DATE,
            warranty_end_date DATE,
            status VARCHAR(80) DEFAULT '启用',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS project_id INTEGER;
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS customer_id INTEGER;
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS product_id INTEGER;
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS product_family VARCHAR(160);
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS machine_model VARCHAR(160);
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS production_stage VARCHAR(80) DEFAULT '准备';
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS service_status VARCHAR(80) DEFAULT '未安装';
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS warranty_start_date DATE;
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS warranty_end_date DATE;
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS status VARCHAR(80) DEFAULT '启用';
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE machine_serial_masters ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE UNIQUE INDEX IF NOT EXISTS machine_serial_masters_serial_no_uidx
            ON machine_serial_masters(serial_no)
            WHERE serial_no IS NOT NULL AND serial_no <> '';
        CREATE INDEX IF NOT EXISTS machine_serial_masters_project_code_idx
            ON machine_serial_masters(project_code);
        """,
    ),
    (
        "20260605_002_core_order_creator_fields",
        """
        ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_sales_orders_created_by
            ON sales_orders(created_by);
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_created_by
            ON purchase_orders(created_by);
        """,
    ),
    (
        "20260605_003_service_optional_work_order",
        """
        ALTER TABLE machine_service_order_checklists ALTER COLUMN wo_id DROP NOT NULL;
        ALTER TABLE machine_service_acceptance_checks ALTER COLUMN wo_id DROP NOT NULL;
        """,
    ),
    (
        "20260606_001_engineering_readiness_fields",
        """
        CREATE TABLE IF NOT EXISTS bom_engineering_changes (
            id SERIAL PRIMARY KEY,
            ecn_no VARCHAR(80) UNIQUE NOT NULL,
            title VARCHAR(200) NOT NULL DEFAULT '',
            change_reason TEXT NOT NULL DEFAULT '',
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            owner VARCHAR(80),
            requested_date DATE,
            source_bom_id INTEGER,
            target_bom_id INTEGER,
            impact_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS process_program_no VARCHAR(160);
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS tooling_requirement TEXT;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS inspection_standard TEXT;
        ALTER TABLE engineering_technical_confirmations ADD COLUMN IF NOT EXISTS ecn_impact_summary TEXT;
        CREATE INDEX IF NOT EXISTS idx_engineering_confirm_product
            ON engineering_technical_confirmations(product_id);
        CREATE INDEX IF NOT EXISTS idx_engineering_confirm_bom
            ON engineering_technical_confirmations(bom_id);
        CREATE INDEX IF NOT EXISTS idx_engineering_confirm_routing
            ON engineering_technical_confirmations(routing_id);
        """,
    ),
    (
        "20260606_001b_engineering_drawing_ledger",
        """
        CREATE TABLE IF NOT EXISTS engineering_drawings (
            id SERIAL PRIMARY KEY,
            drawing_no VARCHAR(120) NOT NULL,
            version VARCHAR(40) NOT NULL,
            drawing_name VARCHAR(200) NOT NULL,
            drawing_type VARCHAR(40) NOT NULL DEFAULT 'part',
            status VARCHAR(40) NOT NULL DEFAULT 'draft',
            owner VARCHAR(80),
            released_date DATE,
            source_system VARCHAR(80),
            file_location TEXT,
            change_reason TEXT,
            remark TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (drawing_no, version)
        );
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS effective_date DATE;
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS obsolete_date DATE;
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS release_no VARCHAR(80);
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS approved_by VARCHAR(80);
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS approval_date DATE;
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS security_level VARCHAR(40) DEFAULT 'normal';
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS file_format VARCHAR(40);
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS checksum VARCHAR(160);
        ALTER TABLE engineering_drawings ADD COLUMN IF NOT EXISTS previous_drawing_id INTEGER;

        CREATE TABLE IF NOT EXISTS engineering_drawing_links (
            id SERIAL PRIMARY KEY,
            drawing_id INTEGER NOT NULL REFERENCES engineering_drawings(id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id),
            bom_id INTEGER REFERENCES boms(id),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            usage_scope VARCHAR(80),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS engineering_drawing_change_logs (
            id SERIAL PRIMARY KEY,
            drawing_id INTEGER NOT NULL REFERENCES engineering_drawings(id) ON DELETE CASCADE,
            action VARCHAR(40) NOT NULL,
            change_no VARCHAR(80),
            old_status VARCHAR(40),
            new_status VARCHAR(40),
            reason TEXT,
            impact_scope TEXT,
            operator_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_engineering_drawings_no
            ON engineering_drawings(drawing_no);
        CREATE INDEX IF NOT EXISTS idx_engineering_drawings_status
            ON engineering_drawings(status);
        CREATE INDEX IF NOT EXISTS idx_engineering_drawing_links_drawing
            ON engineering_drawing_links(drawing_id);
        CREATE INDEX IF NOT EXISTS idx_engineering_drawing_logs_drawing
            ON engineering_drawing_change_logs(drawing_id);
        """,
    ),
    (
        "20260606_002_after_sale_warranty_dispatch_claim_closure",
        """
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS warranty_policy VARCHAR(160);
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS warranty_basis VARCHAR(240);
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS warranty_owner VARCHAR(120);
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS next_action VARCHAR(240);
        ALTER TABLE machine_service_cards ADD COLUMN IF NOT EXISTS downstream_impact TEXT;

        ALTER TABLE machine_service_acceptance_checks ADD COLUMN IF NOT EXISTS customer_acceptance_by VARCHAR(120);
        ALTER TABLE machine_service_acceptance_checks ADD COLUMN IF NOT EXISTS customer_acceptance_date DATE;
        ALTER TABLE machine_service_acceptance_checks ADD COLUMN IF NOT EXISTS corrective_action TEXT;
        ALTER TABLE machine_service_acceptance_checks ADD COLUMN IF NOT EXISTS owner VARCHAR(120);
        ALTER TABLE machine_service_acceptance_checks ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE machine_service_acceptance_checks ADD COLUMN IF NOT EXISTS next_action VARCHAR(240);
        ALTER TABLE machine_service_acceptance_checks ADD COLUMN IF NOT EXISTS downstream_impact TEXT;

        ALTER TABLE machine_service_orders ADD COLUMN IF NOT EXISTS warranty_policy VARCHAR(160);
        ALTER TABLE machine_service_orders ADD COLUMN IF NOT EXISTS warranty_decision_basis TEXT;
        ALTER TABLE machine_service_orders ADD COLUMN IF NOT EXISTS customer_acceptance_by VARCHAR(120);
        ALTER TABLE machine_service_orders ADD COLUMN IF NOT EXISTS customer_acceptance_date DATE;
        ALTER TABLE machine_service_orders ADD COLUMN IF NOT EXISTS owner VARCHAR(120);
        ALTER TABLE machine_service_orders ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE machine_service_orders ADD COLUMN IF NOT EXISTS next_action VARCHAR(240);
        ALTER TABLE machine_service_orders ADD COLUMN IF NOT EXISTS downstream_impact TEXT;

        ALTER TABLE machine_service_dispatches ADD COLUMN IF NOT EXISTS owner VARCHAR(120);
        ALTER TABLE machine_service_dispatches ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE machine_service_dispatches ADD COLUMN IF NOT EXISTS next_action VARCHAR(240);
        ALTER TABLE machine_service_dispatches ADD COLUMN IF NOT EXISTS downstream_impact TEXT;

        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS issue_reason VARCHAR(160);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS warranty_scope VARCHAR(80);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS owner VARCHAR(120);
        ALTER TABLE machine_service_order_items ADD COLUMN IF NOT EXISTS downstream_impact TEXT;

        ALTER TABLE machine_service_return_visits ADD COLUMN IF NOT EXISTS owner VARCHAR(120);
        ALTER TABLE machine_service_return_visits ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE machine_service_return_visits ADD COLUMN IF NOT EXISTS downstream_impact TEXT;

        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS claim_owner VARCHAR(120);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS claim_settlement_basis TEXT;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS recovery_date DATE;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS closed_reason TEXT;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS owner VARCHAR(120);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS next_action VARCHAR(240);
        ALTER TABLE machine_service_rmas ADD COLUMN IF NOT EXISTS downstream_impact TEXT;

        CREATE INDEX IF NOT EXISTS idx_service_orders_project_serial_status
            ON machine_service_orders(project_code, serial_no, status);
        CREATE INDEX IF NOT EXISTS idx_service_rmas_project_serial_status
            ON machine_service_rmas(project_code, serial_no, status);
        CREATE INDEX IF NOT EXISTS idx_service_acceptance_project_serial_result
            ON machine_service_acceptance_checks(project_code, serial_no, result);
        """,
    ),
    (
        "20260606_003_product_configuration_boundary",
        """
        CREATE TABLE IF NOT EXISTS product_configurations (
            id SERIAL PRIMARY KEY,
            config_no VARCHAR(80) UNIQUE NOT NULL,
            config_date DATE DEFAULT CURRENT_DATE,
            sales_order_id INTEGER,
            quotation_id INTEGER,
            customer_id INTEGER,
            product_id INTEGER,
            base_bom_id INTEGER,
            project_bom_id INTEGER,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            product_family VARCHAR(160),
            machine_model VARCHAR(160),
            status VARCHAR(40) NOT NULL DEFAULT 'draft',
            owner VARCHAR(120),
            engineering_owner VARCHAR(120),
            blocked_reason TEXT,
            next_action VARCHAR(240),
            downstream_impact TEXT,
            engineering_confirmed_by INTEGER,
            engineering_confirmed_at TIMESTAMP,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            remark TEXT
        );
        CREATE TABLE IF NOT EXISTS product_configuration_items (
            id SERIAL PRIMARY KEY,
            configuration_id INTEGER REFERENCES product_configurations(id) ON DELETE CASCADE,
            line_no INTEGER NOT NULL DEFAULT 1,
            option_group VARCHAR(120),
            option_code VARCHAR(120),
            option_name VARCHAR(200),
            option_type VARCHAR(40) DEFAULT 'optional',
            selected BOOLEAN DEFAULT TRUE,
            required_flag BOOLEAN DEFAULT FALSE,
            conflict_group VARCHAR(120),
            material_id INTEGER,
            bom_item_action VARCHAR(40) DEFAULT 'reference',
            quantity NUMERIC(18,4) DEFAULT 1,
            unit VARCHAR(40),
            estimated_cost NUMERIC(18,2) DEFAULT 0,
            lead_time_days INTEGER DEFAULT 0,
            owner VARCHAR(120),
            blocked_reason TEXT,
            next_action VARCHAR(240),
            downstream_impact TEXT,
            remark TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_product_configurations_status
            ON product_configurations(status);
        CREATE INDEX IF NOT EXISTS idx_product_configurations_project_serial
            ON product_configurations(project_code, serial_no);
        CREATE INDEX IF NOT EXISTS idx_product_configurations_sales_order
            ON product_configurations(sales_order_id);
        CREATE INDEX IF NOT EXISTS idx_product_configuration_items_config
            ON product_configuration_items(configuration_id);
        CREATE INDEX IF NOT EXISTS idx_product_configuration_items_material
            ON product_configuration_items(material_id);
        """,
    ),
    (
        "20260607_004_finance_exchange_adjustments",
        """
        CREATE TABLE IF NOT EXISTS finance_exchange_adjustments (
            id SERIAL PRIMARY KEY,
            doc_no VARCHAR(120) NOT NULL UNIQUE,
            doc_date DATE NOT NULL DEFAULT CURRENT_DATE,
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            period_label VARCHAR(20) NOT NULL,
            base_currency VARCHAR(20) NOT NULL DEFAULT 'CNY',
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            total_gain NUMERIC(14,2) NOT NULL DEFAULT 0,
            total_loss NUMERIC(14,2) NOT NULL DEFAULT 0,
            net_adjustment NUMERIC(14,2) NOT NULL DEFAULT 0,
            voucher_id INTEGER,
            voucher_no VARCHAR(120),
            prepared_by INTEGER,
            audited_by INTEGER,
            audited_at TIMESTAMP,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS doc_no VARCHAR(120);
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS doc_date DATE NOT NULL DEFAULT CURRENT_DATE;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS period_year INTEGER NOT NULL DEFAULT EXTRACT(YEAR FROM CURRENT_DATE)::INTEGER;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS period_month INTEGER NOT NULL DEFAULT EXTRACT(MONTH FROM CURRENT_DATE)::INTEGER;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS period_label VARCHAR(20);
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS base_currency VARCHAR(20) NOT NULL DEFAULT 'CNY';
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'draft';
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS total_gain NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS total_loss NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS net_adjustment NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS voucher_id INTEGER;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS voucher_no VARCHAR(120);
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS prepared_by INTEGER;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS audited_by INTEGER;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS audited_at TIMESTAMP;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE finance_exchange_adjustments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE UNIQUE INDEX IF NOT EXISTS finance_exchange_adjustments_doc_no_uidx
            ON finance_exchange_adjustments(doc_no);
        CREATE INDEX IF NOT EXISTS idx_finance_exchange_adjustments_period
            ON finance_exchange_adjustments(period_year, period_month, status);

        CREATE TABLE IF NOT EXISTS finance_exchange_adjustment_lines (
            id SERIAL PRIMARY KEY,
            adjustment_id INTEGER NOT NULL REFERENCES finance_exchange_adjustments(id) ON DELETE CASCADE,
            line_no INTEGER NOT NULL DEFAULT 1,
            cash_bank_account_id INTEGER,
            account_code VARCHAR(80),
            account_name VARCHAR(160),
            currency VARCHAR(20) NOT NULL,
            foreign_balance NUMERIC(14,2) NOT NULL DEFAULT 0,
            book_rate NUMERIC(18,8) NOT NULL DEFAULT 1,
            closing_rate NUMERIC(18,8) NOT NULL DEFAULT 1,
            book_base_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            closing_base_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            adjustment_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            direction VARCHAR(20) NOT NULL DEFAULT 'gain',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS adjustment_id INTEGER;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS line_no INTEGER NOT NULL DEFAULT 1;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS cash_bank_account_id INTEGER;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS account_code VARCHAR(80);
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS account_name VARCHAR(160);
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS currency VARCHAR(20);
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS foreign_balance NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS book_rate NUMERIC(18,8) NOT NULL DEFAULT 1;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS closing_rate NUMERIC(18,8) NOT NULL DEFAULT 1;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS book_base_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS closing_base_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS adjustment_amount NUMERIC(14,2) NOT NULL DEFAULT 0;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS direction VARCHAR(20) NOT NULL DEFAULT 'gain';
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE finance_exchange_adjustment_lines ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_finance_exchange_adjustment_lines_adjustment
            ON finance_exchange_adjustment_lines(adjustment_id, line_no);

        INSERT INTO finance_account_mappings (mapping_key, account_code, account_name, remark)
        VALUES ('exchange_gain_loss', '6603', 'Exchange Gain/Loss', 'Period-end foreign currency exchange adjustment')
        ON CONFLICT (mapping_key) DO NOTHING;
        """,
    ),
    (
        "20260607_005_audit_approval_and_row_version",
        """
        CREATE SEQUENCE IF NOT EXISTS audit_logs_id_seq;
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY DEFAULT nextval('audit_logs_id_seq'::regclass),
            user_id INTEGER,
            username VARCHAR(64),
            method VARCHAR(10),
            endpoint VARCHAR(256),
            doc_type VARCHAR(64),
            doc_id VARCHAR(64),
            ip_address VARCHAR(45),
            created_at TIMESTAMP DEFAULT NOW()
        );
        ALTER SEQUENCE audit_logs_id_seq OWNED BY audit_logs.id;
        CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_username ON audit_logs(username);

        ALTER TABLE purchase_requisitions ADD COLUMN IF NOT EXISTS approval_status VARCHAR(30) DEFAULT 'approved';
        UPDATE purchase_requisitions
        SET approval_status='approved'
        WHERE approval_status IS NULL OR approval_status='';
        CREATE INDEX IF NOT EXISTS idx_purchase_requisitions_approval_status
            ON purchase_requisitions(approval_status);

        ALTER TABLE sales_orders ADD COLUMN IF NOT EXISTS row_version INTEGER DEFAULT 1;
        ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS row_version INTEGER DEFAULT 1;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS row_version INTEGER DEFAULT 1;
        UPDATE sales_orders SET row_version=1 WHERE row_version IS NULL;
        UPDATE purchase_orders SET row_version=1 WHERE row_version IS NULL;
        UPDATE work_orders SET row_version=1 WHERE row_version IS NULL;

        ALTER TABLE purchase_requisitions ADD COLUMN IF NOT EXISTS urgency VARCHAR(30) DEFAULT 'normal';
        ALTER TABLE purchase_requisitions ADD COLUMN IF NOT EXISTS applicant VARCHAR(120);
        UPDATE purchase_requisitions SET urgency='normal' WHERE urgency IS NULL OR urgency='';
        """,
    ),
    (
        "20260609_001_master_data_completion",
        """
        CREATE TABLE IF NOT EXISTS income_categories (
            id SERIAL PRIMARY KEY,
            code VARCHAR(80) NOT NULL UNIQUE,
            name VARCHAR(160) NOT NULL,
            parent_id INTEGER,
            include_profit BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_income_categories_status ON income_categories(status);

        CREATE TABLE IF NOT EXISTS expense_categories (
            id SERIAL PRIMARY KEY,
            code VARCHAR(80) NOT NULL UNIQUE,
            name VARCHAR(160) NOT NULL,
            parent_id INTEGER,
            include_profit BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_expense_categories_status ON expense_categories(status);

        CREATE TABLE IF NOT EXISTS fee_templates (
            id SERIAL PRIMARY KEY,
            template_no VARCHAR(80) NOT NULL UNIQUE,
            name VARCHAR(160) NOT NULL,
            supplier_name VARCHAR(160),
            department_name VARCHAR(160),
            salesperson_name VARCHAR(160),
            expense_category VARCHAR(160),
            tax_rate NUMERIC(8, 4) DEFAULT 0,
            currency VARCHAR(20) DEFAULT 'CNY',
            payable_amount NUMERIC(14, 2) DEFAULT 0,
            disabled BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_fee_templates_status ON fee_templates(status);

        CREATE TABLE IF NOT EXISTS auxiliary_data (
            id SERIAL PRIMARY KEY,
            category_name VARCHAR(120) NOT NULL,
            code VARCHAR(80) NOT NULL,
            name VARCHAR(160) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category_name, code)
        );
        CREATE INDEX IF NOT EXISTS idx_auxiliary_data_category ON auxiliary_data(category_name, status);

        CREATE TABLE IF NOT EXISTS settlement_terms (
            id SERIAL PRIMARY KEY,
            code VARCHAR(80) NOT NULL UNIQUE,
            name VARCHAR(160) NOT NULL,
            days INTEGER NOT NULL DEFAULT 0,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payment_terms (
            id SERIAL PRIMARY KEY,
            code VARCHAR(80) NOT NULL UNIQUE,
            name VARCHAR(160) NOT NULL,
            direction VARCHAR(30) NOT NULL DEFAULT 'both',
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS currencies (
            id SERIAL PRIMARY KEY,
            code VARCHAR(20) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL,
            symbol VARCHAR(20),
            amount_decimals INTEGER NOT NULL DEFAULT 2,
            price_decimals INTEGER NOT NULL DEFAULT 2,
            rate_type VARCHAR(40) DEFAULT 'floating',
            exchange_rate NUMERIC(18, 8) NOT NULL DEFAULT 1,
            rounding_method VARCHAR(80),
            is_base BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS payment_channels (
            id SERIAL PRIMARY KEY,
            name VARCHAR(160) NOT NULL,
            merchant_no VARCHAR(120),
            channel_type VARCHAR(80),
            settlement_account_code VARCHAR(80),
            settlement_account_name VARCHAR(160),
            wechat_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            alipay_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS voucher_words (
            id SERIAL PRIMARY KEY,
            word VARCHAR(20) NOT NULL UNIQUE,
            sort_order INTEGER NOT NULL DEFAULT 1,
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS voucher_templates (
            id SERIAL PRIMARY KEY,
            category VARCHAR(120) NOT NULL,
            template_name VARCHAR(160) NOT NULL,
            amount_source VARCHAR(120),
            summary VARCHAR(240),
            account_code VARCHAR(80),
            account_name VARCHAR(160),
            auxiliary_accounting VARCHAR(160),
            debit_credit VARCHAR(20),
            amount_ratio NUMERIC(10, 6) DEFAULT 100,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS name VARCHAR(160);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS template_no VARCHAR(80);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS description TEXT;
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS category VARCHAR(120) NOT NULL DEFAULT '常用模板';
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS template_name VARCHAR(160);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS amount_source VARCHAR(120);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS summary VARCHAR(240);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS account_code VARCHAR(80);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS account_name VARCHAR(160);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS auxiliary_accounting VARCHAR(160);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS debit_credit VARCHAR(20);
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS amount_ratio NUMERIC(10, 6) DEFAULT 100;
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'active';
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE voucher_templates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_voucher_templates_category ON voucher_templates(category, status);

        CREATE TABLE IF NOT EXISTS electronic_accounting_archives (
            id SERIAL PRIMARY KEY,
            archive_no VARCHAR(120) NOT NULL UNIQUE,
            name VARCHAR(160) NOT NULL,
            archive_type VARCHAR(80) NOT NULL DEFAULT 'voucher',
            fiscal_period VARCHAR(20),
            storage_provider VARCHAR(120),
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS vat_accounting_data (
            id SERIAL PRIMARY KEY,
            scheme_name VARCHAR(160) NOT NULL,
            fiscal_period VARCHAR(20),
            audit_status VARCHAR(30) NOT NULL DEFAULT 'draft',
            generated_status VARCHAR(30) NOT NULL DEFAULT 'not_generated',
            generated_by VARCHAR(120),
            generated_at TIMESTAMP,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        INSERT INTO income_categories (code, name, include_profit, status)
        VALUES
            ('SR00001', '运费', TRUE, 'active'),
            ('SR00002', '加油费', TRUE, 'active'),
            ('SR00003', '外出餐补', TRUE, 'active'),
            ('SR00004', '装卸费', TRUE, 'active'),
            ('SR00005', '包装费', TRUE, 'active'),
            ('SR00006', '配送费', TRUE, 'active'),
            ('SR00007', '运输设备租赁费', TRUE, 'active'),
            ('SR00008', '运输保险费', TRUE, 'active'),
            ('SR00009', '客户返利', TRUE, 'active')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO expense_categories (code, name, include_profit, status)
        VALUES
            ('ZC00001', '运费', TRUE, 'active'),
            ('ZC00002', '搬运费', TRUE, 'active'),
            ('ZC00003', '加油费', TRUE, 'active'),
            ('ZC00004', '外出餐补', TRUE, 'active'),
            ('ZC00005', '装卸费', TRUE, 'active'),
            ('ZC00006', '包装费', TRUE, 'active'),
            ('ZC00007', '配送费', TRUE, 'active'),
            ('ZC00008', '运输设备租赁费', TRUE, 'active'),
            ('ZC00009', '运输保险费', TRUE, 'active'),
            ('ZC00010', '电费', TRUE, 'active'),
            ('ZC00011', '烧录费', TRUE, 'active'),
            ('ZC00012', '手续费', TRUE, 'active')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO fee_templates (template_no, name, salesperson_name, expense_category, tax_rate, currency, payable_amount, disabled, status)
        VALUES ('FYMB-00001', '包装费', '百草', '包装费', 0, 'CNY', 0, FALSE, 'active')
        ON CONFLICT (template_no) DO NOTHING;

        INSERT INTO auxiliary_data (category_name, code, name, status)
        VALUES
            ('文章分类', 'FZL00001', '文章分类', 'active'),
            ('潜客来源', 'FZL00002', '线上咨询', 'active'),
            ('销售阶段', 'FZL00003', '初步沟通', 'active'),
            ('退料原因', 'FZL00004', '质量不合格', 'active'),
            ('领料用途', 'FZL00005', '生产领用', 'active'),
            ('委外业务类型', 'FZL00006', '委外加工', 'active'),
            ('生产业务类型', 'FZL00007', '项目生产', 'active'),
            ('不合格原因', 'FZL00008', '尺寸超差', 'active'),
            ('价格等级', 'JGDJ01', '价格等级一', 'active'),
            ('价格等级', 'JGDJ02', '价格等级二', 'active'),
            ('交货方式', 'JHFS01', '物流发货', 'active'),
            ('交货方式', 'JHFS03', '车辆配送', 'active'),
            ('退货原因', 'THYY01', '质量不合格', 'active'),
            ('其他入库类型', 'DBCYCL01', '调拨差异处理', 'active')
        ON CONFLICT (category_name, code) DO NOTHING;

        INSERT INTO settlement_terms (code, name, days, is_default, status)
        VALUES
            ('JSQX01', '月结30天，次月底最后一天付款', 30, FALSE, 'active'),
            ('JSQX02', '60天', 60, FALSE, 'active'),
            ('JSQX03', '90天', 90, FALSE, 'active'),
            ('JSQX04', '5号前的业务在每月20号结算', 20, FALSE, 'active'),
            ('JSQX07', '100天准时结算', 100, FALSE, 'active')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO payment_terms (code, name, direction, is_default, status)
        VALUES
            ('SFKTJ-001', '条件1', 'both', TRUE, 'active'),
            ('SFKTJ-002', '款到发货', 'receipt', FALSE, 'active'),
            ('SFKTJ-003', '货到付款', 'payment', FALSE, 'active')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO currencies (code, name, symbol, amount_decimals, price_decimals, rate_type, exchange_rate, rounding_method, is_base, status)
        VALUES
            ('CNY', '人民币', '¥', 2, 4, 'floating', 1, '原币*汇率', TRUE, 'active'),
            ('EUR', '欧元', 'EUR', 2, 2, 'floating', 7.958, '原币*汇率', FALSE, 'active'),
            ('USD', '美元', '$', 2, 2, 'floating', 7, '原币*汇率', FALSE, 'active')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO payment_channels (name, channel_type, status)
        VALUES ('微信支付', 'wechat', 'active'), ('支付宝', 'alipay', 'active')
        ON CONFLICT DO NOTHING;

        INSERT INTO voucher_words (word, sort_order, is_default, status)
        VALUES ('记', 1, TRUE, 'active'), ('转', 2, FALSE, 'active'), ('收', 3, FALSE, 'active'), ('付', 4, FALSE, 'active')
        ON CONFLICT (word) DO NOTHING;

        INSERT INTO voucher_templates (name, is_active, category, template_name, amount_source, summary, account_code, account_name, debit_credit, amount_ratio, status)
        VALUES
            ('销售商品', TRUE, '常用模板', '销售商品', '手工录入', '销售商品', '1122', '应收账款_A客户', '借', 100, 'active'),
            ('销售商品', TRUE, '常用模板', '销售商品', '手工录入', '销售商品', '1405', '库存商品', '贷', 100, 'active'),
            ('报销差旅费', TRUE, '日常开支', '报销差旅费', '金额百分比', '报销差旅费', '560107', '销售费用_差旅费', '借', 100, 'active'),
            ('报销差旅费', TRUE, '日常开支', '报销差旅费', '金额百分比', '报销差旅费', '100201', '银行存款_销售费用-房租', '贷', 100, 'active')
        ON CONFLICT DO NOTHING;

        INSERT INTO electronic_accounting_archives (archive_no, name, archive_type, fiscal_period, storage_provider, status)
        VALUES ('EAA-DEFAULT', '默认电子会计档案', 'voucher', TO_CHAR(CURRENT_DATE, 'YYYY-MM'), 'local', 'active')
        ON CONFLICT (archive_no) DO NOTHING;
        """,
    ),
    (
        "20260611_001_master_data_structured_fields",
        """
        ALTER TABLE customers ADD COLUMN IF NOT EXISTS category_id INTEGER;
        ALTER TABLE customers ADD COLUMN IF NOT EXISTS tax_no VARCHAR(120);
        ALTER TABLE customers ADD COLUMN IF NOT EXISTS invoice_title VARCHAR(200);
        ALTER TABLE customers ADD COLUMN IF NOT EXISTS default_tax_rate NUMERIC(8, 4) DEFAULT 13;
        ALTER TABLE customers ADD COLUMN IF NOT EXISTS settlement_term_id INTEGER;
        ALTER TABLE customers ADD COLUMN IF NOT EXISTS payment_term_id INTEGER;
        ALTER TABLE customers ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '启用';

        ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS category_id INTEGER;
        ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS tax_no VARCHAR(120);
        ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS invoice_title VARCHAR(200);
        ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS default_tax_rate NUMERIC(8, 4) DEFAULT 13;
        ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS settlement_term_id INTEGER;
        ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS payment_term_id INTEGER;
        ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS is_outsourced_processor BOOLEAN DEFAULT FALSE;
        ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '启用';

        ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS category_id INTEGER;
        ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS warehouse_type VARCHAR(80);
        ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '启用';
        ALTER TABLE warehouses ADD COLUMN IF NOT EXISTS default_location_id INTEGER;

        ALTER TABLE locations ADD COLUMN IF NOT EXISTS location_type VARCHAR(80);
        ALTER TABLE locations ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '启用';

        ALTER TABLE units ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '启用';

        ALTER TABLE departments ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '启用';

        ALTER TABLE employees ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT '在职';
        ALTER TABLE employees ADD COLUMN IF NOT EXISTS employment_type VARCHAR(80);
        ALTER TABLE employees ADD COLUMN IF NOT EXISTS hire_date DATE;

        ALTER TABLE products ADD COLUMN IF NOT EXISTS default_supplier_id INTEGER;
        ALTER TABLE products ADD COLUMN IF NOT EXISTS default_warehouse_id INTEGER;
        ALTER TABLE products ADD COLUMN IF NOT EXISTS default_location_id INTEGER;

        CREATE INDEX IF NOT EXISTS idx_customers_category_id ON customers(category_id);
        CREATE INDEX IF NOT EXISTS idx_suppliers_category_id ON suppliers(category_id);
        CREATE INDEX IF NOT EXISTS idx_warehouses_category_id ON warehouses(category_id);
        CREATE INDEX IF NOT EXISTS idx_products_default_supplier_id ON products(default_supplier_id);
        CREATE INDEX IF NOT EXISTS idx_products_default_warehouse_id ON products(default_warehouse_id);
        """,
    ),
    (
        "20260612_005_system_notifications",
        """
        -- 系统内部通知表
        CREATE TABLE IF NOT EXISTS system_notifications (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER,                        -- NULL 表示全局通知
            title VARCHAR(120) NOT NULL,            -- 通知标题
            message TEXT,                           -- 通知内容
            category VARCHAR(40) DEFAULT 'system',  -- 分类：security/backup/system/warning/info
            severity VARCHAR(20) DEFAULT 'info',    -- 严重级别：info/warning/error/critical
            is_read BOOLEAN DEFAULT FALSE,          -- 是否已读
            read_at TIMESTAMP,                      -- 阅读时间
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 创建时间
            expires_at TIMESTAMP,                   -- 过期时间（可选）
            action_url VARCHAR(255),                -- 操作链接（可选）
            related_type VARCHAR(40),               -- 关联对象类型（可选）
            related_id VARCHAR(120)                 -- 关联对象ID（可选）
        );

        CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
            ON system_notifications(user_id, is_read, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notifications_category_time
            ON system_notifications(category, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_notifications_severity
            ON system_notifications(severity, created_at DESC) WHERE is_read = FALSE;
        CREATE INDEX IF NOT EXISTS idx_notifications_expires
            ON system_notifications(expires_at) WHERE expires_at IS NOT NULL;

        COMMENT ON TABLE system_notifications IS '系统内部通知，用于向用户显示消息和提醒';
        """,
    ),
    (
        "20260615_001_system_options_unique_key",
        """
        CREATE TABLE IF NOT EXISTS system_options (
            id SERIAL PRIMARY KEY,
            option_key VARCHAR(120),
            option_value TEXT,
            remark TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE system_options ADD COLUMN IF NOT EXISTS option_key VARCHAR(120);
        ALTER TABLE system_options ADD COLUMN IF NOT EXISTS option_value TEXT;
        ALTER TABLE system_options ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE system_options ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        UPDATE system_options SET option_key=key WHERE option_key IS NULL AND key IS NOT NULL;
        UPDATE system_options SET option_value=value WHERE option_value IS NULL AND value IS NOT NULL;
        DELETE FROM system_options a
        USING system_options b
        WHERE a.option_key IS NOT NULL
          AND b.option_key IS NOT NULL
          AND a.option_key = b.option_key
          AND a.id < b.id;
        UPDATE system_options SET option_key='legacy_option_' || id WHERE option_key IS NULL OR option_key='';
        DROP INDEX IF EXISTS system_options_option_key_uidx;
        ALTER TABLE system_options ALTER COLUMN option_key SET NOT NULL;
        ALTER TABLE system_options DROP CONSTRAINT IF EXISTS system_options_option_key_key;
        ALTER TABLE system_options ADD CONSTRAINT system_options_option_key_key UNIQUE (option_key);
        """,
    ),
    (
        "20260615_002_finance_tax_rates_master",
        """
        CREATE TABLE IF NOT EXISTS tax_rates (
            id SERIAL PRIMARY KEY,
            code VARCHAR(80) NOT NULL UNIQUE,
            name VARCHAR(160) NOT NULL,
            rate NUMERIC(8, 4) NOT NULL DEFAULT 0,
            tax_type VARCHAR(40) NOT NULL DEFAULT 'vat',
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_tax_rates_type_status ON tax_rates(tax_type, status);

        INSERT INTO tax_rates (code, name, rate, tax_type, is_default, status, remark)
        VALUES
            ('VAT13', '增值税13%', 13, 'vat', TRUE, 'active', '常用销售/采购增值税税率'),
            ('VAT09', '增值税9%', 9, 'vat', FALSE, 'active', '常用增值税税率'),
            ('VAT06', '增值税6%', 6, 'vat', FALSE, 'active', '服务类增值税税率'),
            ('VAT03', '增值税3%', 3, 'vat', FALSE, 'active', '小规模纳税人征收率'),
            ('VAT00', '免税/零税率', 0, 'vat', FALSE, 'active', '免税、零税率或不计税业务')
        ON CONFLICT (code) DO NOTHING;
        """,
    ),
    (
        "20260615_003_finance_account_mapping_localization",
        """
        CREATE TABLE IF NOT EXISTS finance_account_mappings (
            id SERIAL PRIMARY KEY,
            mapping_key VARCHAR(80) NOT NULL UNIQUE,
            account_id INTEGER,
            account_code VARCHAR(50),
            account_name VARCHAR(255),
            remark TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_finance_account_mappings_key
            ON finance_account_mappings(mapping_key);

        INSERT INTO chart_of_accounts (code, name, account_type, balance_direction, is_leaf, status, remark)
        VALUES
            ('1002', '银行存款', 'asset', 'debit', TRUE, 'active', '收付款、现金银行和资金流水默认银行科目'),
            ('1122', '应收账款', 'asset', 'debit', TRUE, 'active', '销售开票、应收单和客户往来默认科目'),
            ('1123', '预付账款', 'asset', 'debit', TRUE, 'active', '供应商预付款默认科目'),
            ('1405', '库存商品', 'asset', 'debit', TRUE, 'active', '采购入库、库存成本和成本结转默认科目'),
            ('2202', '应付账款', 'liability', 'credit', TRUE, 'active', '采购开票、应付单和供应商往来默认科目'),
            ('2203', '预收账款', 'liability', 'credit', TRUE, 'active', '客户预收款默认科目'),
            ('2221', '应交税费', 'liability', 'credit', TRUE, 'active', '销项税、进项税和涉税占位默认科目'),
            ('5001', '主营业务收入', 'revenue', 'credit', TRUE, 'active', '销售收入默认科目'),
            ('5401', '主营业务成本', 'expense', 'debit', TRUE, 'active', '销售成本结转默认科目'),
            ('6602', '销售费用', 'expense', 'debit', TRUE, 'active', '费用类单据默认科目'),
            ('6603', '财务费用-汇兑损益', 'expense', 'debit', TRUE, 'active', '期末调汇默认汇兑损益科目')
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            account_type = EXCLUDED.account_type,
            balance_direction = EXCLUDED.balance_direction,
            is_leaf = EXCLUDED.is_leaf,
            status = EXCLUDED.status,
            remark = EXCLUDED.remark;

        INSERT INTO finance_account_mappings (mapping_key, account_code, account_name, remark)
        VALUES
            ('bank', '1002', '银行存款', '收款单、付款单、现金银行日记账和资金流水默认科目'),
            ('accounts_receivable', '1122', '应收账款', '销售发票、应收单和客户往来余额默认科目'),
            ('prepayment', '1123', '预付账款', '供应商预付款和未核销预付默认科目'),
            ('inventory', '1405', '库存商品', '采购入库、库存成本和成本结转默认科目'),
            ('accounts_payable', '2202', '应付账款', '采购发票、应付单和供应商往来余额默认科目'),
            ('advance_receipt', '2203', '预收账款', '客户预收款和未核销预收默认科目'),
            ('tax_payable', '2221', '应交税费', '销项税、进项税和税额占位默认科目'),
            ('sales_revenue', '5001', '主营业务收入', '销售收入凭证默认科目'),
            ('business_cost', '5401', '主营业务成本', '销售成本结转凭证默认科目'),
            ('operating_expense', '6602', '销售费用', '费用类单据默认科目'),
            ('exchange_gain_loss', '6603', '财务费用-汇兑损益', '期末外币调汇默认科目')
        ON CONFLICT (mapping_key) DO UPDATE SET
            account_code = EXCLUDED.account_code,
            account_name = EXCLUDED.account_name,
            remark = EXCLUDED.remark,
            updated_at = CURRENT_TIMESTAMP;

        UPDATE finance_account_mappings fam
        SET account_id = coa.id,
            account_name = coa.name,
            updated_at = CURRENT_TIMESTAMP
        FROM chart_of_accounts coa
        WHERE fam.account_code = coa.code;
        """,
    ),
    (
        "20260616_001_finance_ar_ap_enhancement",
        """
        -- 应收应付增强：补充未核销金额跟踪

        -- 1. 客户收款单增加已核销金额字段（未核销金额已有 unapplied_amount）
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS settled_amount NUMERIC(15,2) DEFAULT 0;
        ALTER TABLE customer_receipts ADD COLUMN IF NOT EXISTS unapplied_amount NUMERIC(15,2) DEFAULT 0;

        -- 2. 供应商付款单增加已核销金额字段（未核销金额已有 unapplied_amount）
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS settled_amount NUMERIC(15,2) DEFAULT 0;
        ALTER TABLE supplier_payments ADD COLUMN IF NOT EXISTS unapplied_amount NUMERIC(15,2) DEFAULT 0;

        -- 3. 客户应收账款补充字段（如果不存在）
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS invoice_no VARCHAR(120);
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS invoice_date DATE;

        -- 4. 供应商应付账款补充字段（如果不存在）
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS invoice_no VARCHAR(120);
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS invoice_date DATE;

        -- 5. 创建客户应收明细表（如果需要按物料/服务明细展开）
        CREATE TABLE IF NOT EXISTS customer_receivable_items (
            id SERIAL PRIMARY KEY,
            receivable_id INTEGER NOT NULL REFERENCES customer_receivables(id) ON DELETE CASCADE,
            line_no INTEGER,
            item_code VARCHAR(50),
            item_name VARCHAR(200),
            specification VARCHAR(200),
            unit VARCHAR(20),
            quantity NUMERIC(15,3),
            unit_price NUMERIC(15,4),
            amount NUMERIC(15,2),
            tax_rate NUMERIC(5,2),
            tax_amount NUMERIC(15,2),
            total_amount NUMERIC(15,2),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            source_doc_type VARCHAR(80),
            source_doc_id INTEGER,
            source_doc_no VARCHAR(120),
            source_doc_line_id INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE customer_receivable_items ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80);
        ALTER TABLE customer_receivable_items ADD COLUMN IF NOT EXISTS source_doc_id INTEGER;
        ALTER TABLE customer_receivable_items ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        ALTER TABLE customer_receivable_items ADD COLUMN IF NOT EXISTS source_doc_line_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_receivable_items_receivable_id ON customer_receivable_items(receivable_id);
        CREATE INDEX IF NOT EXISTS idx_receivable_items_source ON customer_receivable_items(source_doc_type, source_doc_id);

        -- 6. 创建供应商应付明细表（如果需要按物料/服务明细展开）
        CREATE TABLE IF NOT EXISTS supplier_payable_items (
            id SERIAL PRIMARY KEY,
            payable_id INTEGER NOT NULL REFERENCES supplier_payables(id) ON DELETE CASCADE,
            line_no INTEGER,
            item_code VARCHAR(50),
            item_name VARCHAR(200),
            specification VARCHAR(200),
            unit VARCHAR(20),
            quantity NUMERIC(15,3),
            unit_price NUMERIC(15,4),
            amount NUMERIC(15,2),
            tax_rate NUMERIC(5,2),
            tax_amount NUMERIC(15,2),
            total_amount NUMERIC(15,2),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            source_doc_type VARCHAR(80),
            source_doc_id INTEGER,
            source_doc_no VARCHAR(120),
            source_doc_line_id INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE supplier_payable_items ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80);
        ALTER TABLE supplier_payable_items ADD COLUMN IF NOT EXISTS source_doc_id INTEGER;
        ALTER TABLE supplier_payable_items ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        ALTER TABLE supplier_payable_items ADD COLUMN IF NOT EXISTS source_doc_line_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_payable_items_payable_id ON supplier_payable_items(payable_id);
        CREATE INDEX IF NOT EXISTS idx_payable_items_source ON supplier_payable_items(source_doc_type, source_doc_id);

        -- 7. 创建付款申请单表（用于付款审批流程）
        CREATE TABLE IF NOT EXISTS finance_payment_requests (
            id SERIAL PRIMARY KEY,
            request_no VARCHAR(50) UNIQUE NOT NULL,
            request_date DATE NOT NULL,
            supplier_id INTEGER,
            supplier_name VARCHAR(200),
            supplier_code VARCHAR(100),
            amount NUMERIC(15,2) NOT NULL DEFAULT 0,
            currency VARCHAR(10) DEFAULT 'CNY',
            exchange_rate NUMERIC(10,6) DEFAULT 1,
            base_amount NUMERIC(15,2),
            payment_terms TEXT,
            payment_purpose TEXT,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            cost_object_id INTEGER,
            requested_payment_date DATE,
            requested_by INTEGER,
            requested_by_name VARCHAR(100),
            approved_by INTEGER,
            approved_by_name VARCHAR(100),
            approved_at TIMESTAMP,
            status VARCHAR(20) DEFAULT 'draft',
            approval_status VARCHAR(20) DEFAULT 'pending',
            approval_notes TEXT,
            payment_id INTEGER,
            payment_no VARCHAR(50),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_by INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_payment_requests_supplier ON finance_payment_requests(supplier_id);
        CREATE INDEX IF NOT EXISTS idx_payment_requests_status ON finance_payment_requests(status);
        CREATE INDEX IF NOT EXISTS idx_payment_requests_approval ON finance_payment_requests(approval_status);
        CREATE INDEX IF NOT EXISTS idx_payment_requests_date ON finance_payment_requests(request_date);

        -- 8. 创建应收票据表（承兑汇票、商业汇票等）
        CREATE TABLE IF NOT EXISTS finance_receivable_bills (
            id SERIAL PRIMARY KEY,
            bill_no VARCHAR(50) UNIQUE NOT NULL,
            bill_type VARCHAR(50) DEFAULT 'bank_acceptance',
            bill_date DATE NOT NULL,
            customer_id INTEGER,
            customer_name VARCHAR(200),
            amount NUMERIC(15,2) NOT NULL DEFAULT 0,
            currency VARCHAR(10) DEFAULT 'CNY',
            maturity_date DATE,
            drawer VARCHAR(200),
            drawee VARCHAR(200),
            endorser VARCHAR(200),
            bank_name VARCHAR(200),
            bank_account VARCHAR(100),
            status VARCHAR(20) DEFAULT 'received',
            collection_status VARCHAR(20) DEFAULT 'pending',
            collected_at TIMESTAMP,
            collected_amount NUMERIC(15,2) DEFAULT 0,
            discount_amount NUMERIC(15,2) DEFAULT 0,
            receivable_id INTEGER,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_by INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_receivable_bills_customer ON finance_receivable_bills(customer_id);
        CREATE INDEX IF NOT EXISTS idx_receivable_bills_status ON finance_receivable_bills(status);
        CREATE INDEX IF NOT EXISTS idx_receivable_bills_maturity ON finance_receivable_bills(maturity_date);

        -- 9. 创建应付票据表
        CREATE TABLE IF NOT EXISTS finance_payable_bills (
            id SERIAL PRIMARY KEY,
            bill_no VARCHAR(50) UNIQUE NOT NULL,
            bill_type VARCHAR(50) DEFAULT 'bank_acceptance',
            bill_date DATE NOT NULL,
            supplier_id INTEGER,
            supplier_name VARCHAR(200),
            amount NUMERIC(15,2) NOT NULL DEFAULT 0,
            currency VARCHAR(10) DEFAULT 'CNY',
            maturity_date DATE,
            drawer VARCHAR(200),
            drawee VARCHAR(200),
            payee VARCHAR(200),
            bank_name VARCHAR(200),
            bank_account VARCHAR(100),
            status VARCHAR(20) DEFAULT 'issued',
            payment_status VARCHAR(20) DEFAULT 'pending',
            paid_at TIMESTAMP,
            paid_amount NUMERIC(15,2) DEFAULT 0,
            payable_id INTEGER,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            updated_by INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_payable_bills_supplier ON finance_payable_bills(supplier_id);
        CREATE INDEX IF NOT EXISTS idx_payable_bills_status ON finance_payable_bills(status);
        CREATE INDEX IF NOT EXISTS idx_payable_bills_maturity ON finance_payable_bills(maturity_date);

        -- 10. 初始化现有收款单的已核销金额和未核销金额（已审核的收款单）
        UPDATE customer_receipts
        SET settled_amount = COALESCE(
            (SELECT SUM(COALESCE(applied_amount, 0))
             FROM customer_receipt_settlements
             WHERE receipt_id = customer_receipts.id),
            0
        ),
        unapplied_amount = COALESCE(amount, 0) - COALESCE(
            (SELECT SUM(COALESCE(applied_amount, 0))
             FROM customer_receipt_settlements
             WHERE receipt_id = customer_receipts.id),
            0
        )
        WHERE status IN ('posted', 'confirmed', '已确认', '已审核')
          AND (settled_amount IS NULL OR settled_amount = 0);

        -- 11. 初始化现有付款单的已核销金额和未核销金额（已审核的付款单）
        UPDATE supplier_payments
        SET settled_amount = COALESCE(
            (SELECT SUM(COALESCE(applied_amount, 0))
             FROM supplier_payment_settlements
             WHERE payment_id = supplier_payments.id),
            0
        ),
        unapplied_amount = COALESCE(amount, 0) - COALESCE(
            (SELECT SUM(COALESCE(applied_amount, 0))
             FROM supplier_payment_settlements
             WHERE payment_id = supplier_payments.id),
            0
        )
        WHERE status IN ('posted', 'confirmed', '已确认', '已审核')
          AND (settled_amount IS NULL OR settled_amount = 0);
        """,
    ),
    (
        "20260616_002_finance_invoice_enhancement",
        """
        -- 发票管理增强：支持三单匹配、发票勾稽、自动生成应收应付

        -- 1. 销售发票增强字段
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS invoice_code VARCHAR(50);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS invoice_type VARCHAR(50) DEFAULT 'vat_invoice';
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS tax_rate NUMERIC(5,2) DEFAULT 13;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS buyer_name VARCHAR(200);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS buyer_tax_no VARCHAR(50);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS buyer_address VARCHAR(200);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS buyer_phone VARCHAR(50);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS buyer_bank VARCHAR(200);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS buyer_account VARCHAR(100);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS issuer VARCHAR(100);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS reviewer VARCHAR(100);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS payee VARCHAR(100);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS invoice_status VARCHAR(20) DEFAULT 'draft';
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS red_invoice_id INTEGER;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS red_invoice_no VARCHAR(120);
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS receivable_id INTEGER;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS approved_by INTEGER;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS updated_by INTEGER;
        ALTER TABLE sales_invoices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

        -- 2. 采购发票增强字段
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS invoice_code VARCHAR(50);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS invoice_type VARCHAR(50) DEFAULT 'vat_invoice';
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS tax_rate NUMERIC(5,2) DEFAULT 13;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS seller_name VARCHAR(200);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS seller_tax_no VARCHAR(50);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS seller_address VARCHAR(200);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS seller_phone VARCHAR(50);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS seller_bank VARCHAR(200);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS seller_account VARCHAR(100);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS arrival_date DATE;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS certification_date DATE;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS certification_status VARCHAR(20) DEFAULT 'pending';
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS invoice_status VARCHAR(20) DEFAULT 'draft';
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS red_invoice_id INTEGER;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS red_invoice_no VARCHAR(120);
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS payable_id INTEGER;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS approved_by INTEGER;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS updated_by INTEGER;
        ALTER TABLE purchase_invoices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

        -- 3. 创建销售发票明细表
        CREATE TABLE IF NOT EXISTS sales_invoice_items (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES sales_invoices(id) ON DELETE CASCADE,
            line_no INTEGER,
            item_code VARCHAR(50),
            item_name VARCHAR(200),
            specification VARCHAR(200),
            unit VARCHAR(20),
            quantity NUMERIC(15,3),
            unit_price NUMERIC(15,4),
            amount NUMERIC(15,2),
            tax_rate NUMERIC(5,2),
            tax_amount NUMERIC(15,2),
            total_amount NUMERIC(15,2),
            source_doc_type VARCHAR(80),
            source_doc_id INTEGER,
            source_doc_no VARCHAR(120),
            source_doc_line_id INTEGER,
            sales_order_id INTEGER,
            sales_order_no VARCHAR(120),
            delivery_id INTEGER,
            delivery_no VARCHAR(120),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE sales_invoice_items ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80);
        ALTER TABLE sales_invoice_items ADD COLUMN IF NOT EXISTS source_doc_id INTEGER;
        ALTER TABLE sales_invoice_items ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        ALTER TABLE sales_invoice_items ADD COLUMN IF NOT EXISTS source_doc_line_id INTEGER;
        ALTER TABLE sales_invoice_items ADD COLUMN IF NOT EXISTS sales_order_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_sales_invoice_items_invoice ON sales_invoice_items(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_sales_invoice_items_source ON sales_invoice_items(source_doc_type, source_doc_id);
        CREATE INDEX IF NOT EXISTS idx_sales_invoice_items_order ON sales_invoice_items(sales_order_id);

        -- 4. 创建采购发票明细表
        CREATE TABLE IF NOT EXISTS purchase_invoice_items (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES purchase_invoices(id) ON DELETE CASCADE,
            line_no INTEGER,
            item_code VARCHAR(50),
            item_name VARCHAR(200),
            specification VARCHAR(200),
            unit VARCHAR(20),
            quantity NUMERIC(15,3),
            unit_price NUMERIC(15,4),
            amount NUMERIC(15,2),
            tax_rate NUMERIC(5,2),
            tax_amount NUMERIC(15,2),
            total_amount NUMERIC(15,2),
            source_doc_type VARCHAR(80),
            source_doc_id INTEGER,
            source_doc_no VARCHAR(120),
            source_doc_line_id INTEGER,
            purchase_order_id INTEGER,
            purchase_order_no VARCHAR(120),
            receipt_id INTEGER,
            receipt_no VARCHAR(120),
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE purchase_invoice_items ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80);
        ALTER TABLE purchase_invoice_items ADD COLUMN IF NOT EXISTS source_doc_id INTEGER;
        ALTER TABLE purchase_invoice_items ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        ALTER TABLE purchase_invoice_items ADD COLUMN IF NOT EXISTS source_doc_line_id INTEGER;
        ALTER TABLE purchase_invoice_items ADD COLUMN IF NOT EXISTS purchase_order_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_purchase_invoice_items_invoice ON purchase_invoice_items(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_purchase_invoice_items_source ON purchase_invoice_items(source_doc_type, source_doc_id);
        CREATE INDEX IF NOT EXISTS idx_purchase_invoice_items_order ON purchase_invoice_items(purchase_order_id);

        -- 5. 创建发票与应收应付关联表（一对多：一张发票可以关联多张应收/应付）
        CREATE TABLE IF NOT EXISTS sales_invoice_receivables (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES sales_invoices(id) ON DELETE CASCADE,
            receivable_id INTEGER NOT NULL REFERENCES customer_receivables(id) ON DELETE CASCADE,
            allocated_amount NUMERIC(15,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (invoice_id, receivable_id)
        );
        CREATE INDEX IF NOT EXISTS idx_sales_invoice_receivables_invoice ON sales_invoice_receivables(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_sales_invoice_receivables_receivable ON sales_invoice_receivables(receivable_id);

        CREATE TABLE IF NOT EXISTS purchase_invoice_payables (
            id SERIAL PRIMARY KEY,
            invoice_id INTEGER NOT NULL REFERENCES purchase_invoices(id) ON DELETE CASCADE,
            payable_id INTEGER NOT NULL REFERENCES supplier_payables(id) ON DELETE CASCADE,
            allocated_amount NUMERIC(15,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (invoice_id, payable_id)
        );
        CREATE INDEX IF NOT EXISTS idx_purchase_invoice_payables_invoice ON purchase_invoice_payables(invoice_id);
        CREATE INDEX IF NOT EXISTS idx_purchase_invoice_payables_payable ON purchase_invoice_payables(payable_id);

        -- 6. 为应收应付表增加发票关联字段（向后兼容单张发票场景）
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS invoice_id INTEGER;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS invoice_id INTEGER;

        -- 7. 创建索引优化查询性能
        CREATE INDEX IF NOT EXISTS idx_customer_receivables_invoice ON customer_receivables(invoice_id) WHERE invoice_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_supplier_payables_invoice ON supplier_payables(invoice_id) WHERE invoice_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_sales_invoices_receivable ON sales_invoices(receivable_id) WHERE receivable_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_purchase_invoices_payable ON purchase_invoices(payable_id) WHERE payable_id IS NOT NULL;
        """,
    ),
    (
        "20260617_001_finance_missing_tables",
        """
        -- 1. Chart of Accounts
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

        -- 2. GL Account Balances
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
        CREATE INDEX IF NOT EXISTS idx_gl_account_balances_period ON gl_account_balances(period_year, period_month);

        -- 3. Voucher Entries
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
        CREATE INDEX IF NOT EXISTS idx_voucher_entries_voucher ON voucher_entries(voucher_id);

        -- 4. Period Closing
        CREATE TABLE IF NOT EXISTS period_closing (
            id SERIAL PRIMARY KEY,
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            closing_date DATE,
            status VARCHAR(50) DEFAULT 'open',
            revenue NUMERIC(16, 2) DEFAULT 0,
            cost NUMERIC(16, 2) DEFAULT 0,
            gross_profit NUMERIC(16, 2) DEFAULT 0,
            profit_transfer_voucher_id INTEGER,
            closed_by INTEGER,
            closed_at TIMESTAMP,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (period_year, period_month)
        );
        ALTER TABLE period_closing ADD COLUMN IF NOT EXISTS profit_transfer_voucher_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_period_closing_period ON period_closing(period_year, period_month);

        -- 5. Project Cost Ledger
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
        CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_project ON project_cost_ledger(project_code);
        CREATE INDEX IF NOT EXISTS idx_project_cost_ledger_date ON project_cost_ledger(cost_date);

        -- 6. Serial Cost Ledger
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
        CREATE INDEX IF NOT EXISTS idx_serial_cost_ledger_serial ON serial_cost_ledger(serial_no);
        CREATE INDEX IF NOT EXISTS idx_serial_cost_ledger_date ON serial_cost_ledger(cost_date);

        -- 7. Inventory Costing
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
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_product ON inventory_costing(product_id);

        -- 8. Inventory Transactions
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
        CREATE INDEX IF NOT EXISTS idx_inventory_transactions_date ON inventory_transactions(transaction_date);
        CREATE INDEX IF NOT EXISTS idx_inventory_transactions_product ON inventory_transactions(product_id);

        -- 9. Financial Report Log
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
        CREATE INDEX IF NOT EXISTS idx_financial_report_log_type ON financial_report_log(report_type);
        """,
    ),
    (
        "20260618_001_invoice_item_total_amount_compat",
        """
        ALTER TABLE sales_invoice_items ADD COLUMN IF NOT EXISTS total_amount NUMERIC(15, 2) DEFAULT 0;
        ALTER TABLE purchase_invoice_items ADD COLUMN IF NOT EXISTS total_amount NUMERIC(15, 2) DEFAULT 0;

        UPDATE sales_invoice_items
        SET total_amount = COALESCE(amount_with_tax, amount, quantity * unit_price, 0)
        WHERE total_amount IS NULL OR total_amount = 0;

        UPDATE purchase_invoice_items
        SET total_amount = COALESCE(amount_with_tax, amount, quantity * unit_price, 0)
        WHERE total_amount IS NULL OR total_amount = 0;
        """,
    ),
    (
        "20260618_002_finance_ar_ap_amount_alias",
        """
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS amount NUMERIC(15, 2) DEFAULT 0;

        UPDATE customer_receivables
        SET total_amount = COALESCE(NULLIF(total_amount, 0), amount, expected_amount, confirmed_amount, 0)
        WHERE total_amount IS NULL OR total_amount = 0;

        UPDATE customer_receivables
        SET amount = COALESCE(total_amount, amount, expected_amount, confirmed_amount, 0)
        WHERE amount IS NULL
           OR ABS(COALESCE(amount, 0) - COALESCE(total_amount, amount, expected_amount, confirmed_amount, 0)) > 0.01;

        UPDATE customer_receivables
        SET balance = GREATEST(COALESCE(total_amount, amount, 0) - COALESCE(received_amount, 0), 0)
        WHERE ABS(COALESCE(balance, 0) - GREATEST(COALESCE(total_amount, amount, 0) - COALESCE(received_amount, 0), 0)) > 0.01;

        CREATE OR REPLACE FUNCTION sync_customer_receivable_amount_alias()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.total_amount IS NULL OR NEW.total_amount = 0 THEN
                NEW.total_amount := COALESCE(NEW.amount, NEW.expected_amount, NEW.confirmed_amount, 0);
            END IF;
            NEW.amount := COALESCE(NEW.total_amount, NEW.amount, 0);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_customer_receivables_amount_alias ON customer_receivables;
        CREATE TRIGGER trg_customer_receivables_amount_alias
        BEFORE INSERT OR UPDATE OF total_amount, amount, expected_amount, confirmed_amount
        ON customer_receivables
        FOR EACH ROW
        EXECUTE FUNCTION sync_customer_receivable_amount_alias();

        WITH settlement AS (
            SELECT receipt_id, SUM(COALESCE(applied_amount, 0)) AS applied_amount
            FROM customer_receipt_settlements
            GROUP BY receipt_id
        )
        UPDATE customer_receipts r
        SET settled_amount = settlement.applied_amount,
            unapplied_amount = GREATEST(COALESCE(r.amount, 0) - settlement.applied_amount, 0)
        FROM settlement
        WHERE r.id = settlement.receipt_id
          AND (
              ABS(COALESCE(r.settled_amount, 0) - settlement.applied_amount) > 0.01
              OR ABS(COALESCE(r.unapplied_amount, 0) - GREATEST(COALESCE(r.amount, 0) - settlement.applied_amount, 0)) > 0.01
          );

        WITH settlement AS (
            SELECT payment_id, SUM(COALESCE(applied_amount, 0)) AS applied_amount
            FROM supplier_payment_settlements
            GROUP BY payment_id
        )
        UPDATE supplier_payments p
        SET settled_amount = settlement.applied_amount,
            unapplied_amount = GREATEST(COALESCE(p.amount, 0) - settlement.applied_amount, 0)
        FROM settlement
        WHERE p.id = settlement.payment_id
          AND (
              ABS(COALESCE(p.settled_amount, 0) - settlement.applied_amount) > 0.01
              OR ABS(COALESCE(p.unapplied_amount, 0) - GREATEST(COALESCE(p.amount, 0) - settlement.applied_amount, 0)) > 0.01
          );
        """,
    ),
    (
        "20260618_003_cash_bank_journal_source_id",
        """
        ALTER TABLE cash_bank_journal_entries ADD COLUMN IF NOT EXISTS source_id INTEGER;

        UPDATE cash_bank_journal_entries j
        SET source_id = r.id
        FROM customer_receipts r
        WHERE j.source_id IS NULL
          AND j.source_type IN (
              'customer_receipt', 'customer_advance_receipt', 'customer_receipt_refund',
              'customer_advance_refund', 'customer_other_income', 'customer_other_income_refund'
          )
          AND j.source_no = r.receipt_no;

        UPDATE cash_bank_journal_entries j
        SET source_id = p.id
        FROM supplier_payments p
        WHERE j.source_id IS NULL
          AND j.source_type IN (
              'supplier_payment', 'supplier_advance_payment', 'supplier_payment_refund',
              'supplier_advance_refund', 'supplier_other_expense', 'supplier_other_expense_refund'
          )
          AND j.source_no = p.payment_no;

        CREATE INDEX IF NOT EXISTS idx_cash_bank_journal_entries_source
            ON cash_bank_journal_entries(source_type, source_id, source_no);
        """,
    ),
    (
        "20260618_001_core_fk_and_index_reinforcement",
        """
        -- 补建核心业务表外键索引（提升 JOIN 和 FK 检查性能）
        CREATE INDEX IF NOT EXISTS idx_customer_receivables_customer_id
            ON customer_receivables(customer_id);
        CREATE INDEX IF NOT EXISTS idx_supplier_payables_supplier_id
            ON supplier_payables(supplier_id);
        CREATE INDEX IF NOT EXISTS idx_sales_shipments_order_id
            ON sales_shipments(order_id);
        CREATE INDEX IF NOT EXISTS idx_purchase_receipts_order_id
            ON purchase_receipts(order_id);
        CREATE INDEX IF NOT EXISTS idx_work_order_processes_work_order_id
            ON work_order_processes(work_order_id);
        CREATE INDEX IF NOT EXISTS idx_wo_material_items_work_order_id
            ON wo_material_items(wo_id);
        CREATE INDEX IF NOT EXISTS idx_machine_service_order_items_service_order_id
            ON machine_service_order_items(order_id);

        -- Validate existing NOT VALID foreign keys when the constraint exists.
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sales_orders_customer_id_fk') THEN
                ALTER TABLE sales_orders VALIDATE CONSTRAINT sales_orders_customer_id_fk;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'purchase_orders_supplier_id_fk') THEN
                ALTER TABLE purchase_orders VALIDATE CONSTRAINT purchase_orders_supplier_id_fk;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'stock_transactions_product_id_fk') THEN
                ALTER TABLE stock_transactions VALIDATE CONSTRAINT stock_transactions_product_id_fk;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'work_orders_product_id_fk') THEN
                ALTER TABLE work_orders VALIDATE CONSTRAINT work_orders_product_id_fk;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sales_order_items_order_id_fk') THEN
                ALTER TABLE sales_order_items VALIDATE CONSTRAINT sales_order_items_order_id_fk;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'purchase_order_items_order_id_fk') THEN
                ALTER TABLE purchase_order_items VALIDATE CONSTRAINT purchase_order_items_order_id_fk;
            END IF;
        END $$;
        """,
    ),
    (
        "20260619_001_round1_inventory_fk_and_indexes",
        """
        -- BUG-DB-01: inventory_transactions 缺少外键约束
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'inventory_transactions_product_id_fk'
            ) THEN
                ALTER TABLE inventory_transactions
                    ADD CONSTRAINT inventory_transactions_product_id_fk
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'inventory_transactions_warehouse_id_fk'
            ) THEN
                ALTER TABLE inventory_transactions
                    ADD CONSTRAINT inventory_transactions_warehouse_id_fk
                    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE SET NULL;
            END IF;
        END $$;

        -- BUG-DB-03: inventory_costing 缺少外键约束
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'inventory_costing_product_id_fk'
            ) THEN
                ALTER TABLE inventory_costing
                    ADD CONSTRAINT inventory_costing_product_id_fk
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE RESTRICT;
            END IF;
        END $$;

        -- 补充查询索引（项目/机号/单号维度）
        CREATE INDEX IF NOT EXISTS idx_inventory_transactions_project
            ON inventory_transactions(project_code) WHERE project_code IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_inventory_transactions_serial
            ON inventory_transactions(serial_no) WHERE serial_no IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_inventory_transactions_reference
            ON inventory_transactions(reference_no) WHERE reference_no IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_date
            ON inventory_costing(costing_date);
        CREATE INDEX IF NOT EXISTS idx_inventory_costing_warehouse
            ON inventory_costing(warehouse_id) WHERE warehouse_id IS NOT NULL;

        -- BUG-DB-04: document_sequences 唯一约束（已由 PRIMARY KEY 覆盖，补充校验）
        -- 此处仅添加 updated_at 索引以辅助并发审计
        CREATE INDEX IF NOT EXISTS idx_document_sequences_updated
            ON document_sequences(updated_at);
        """,
    ),
    (
        "20260619_001_pick_lists_schema",
        """
        CREATE TABLE IF NOT EXISTS pick_lists (id SERIAL PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS pick_list_items (id SERIAL PRIMARY KEY);
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS doc_type VARCHAR(60);
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS doc_no VARCHAR(80);
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS pick_no VARCHAR(80);
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS doc_date DATE;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS pick_date DATE;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS work_order_id INTEGER;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS status VARCHAR(40) DEFAULT 'draft';
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS approved_by INTEGER;
        ALTER TABLE pick_lists ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS pick_list_id INTEGER;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS pick_id INTEGER;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS wo_material_item_id INTEGER;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS product_id INTEGER;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS posted_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(120);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS line_serial_no VARCHAR(120);
        ALTER TABLE pick_list_items ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        """,
    ),
    (
        "20260619_002_operation_reports_schema",
        """
        CREATE TABLE IF NOT EXISTS operation_reports (id SERIAL PRIMARY KEY);
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS report_no VARCHAR(80);
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS work_order_id INTEGER;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS work_order_process_id INTEGER;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS routing_operation_id INTEGER;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS report_type VARCHAR(40);
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS report_date DATE;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS status VARCHAR(40) DEFAULT '草稿';
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS operator_id INTEGER;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS work_center_id INTEGER;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS start_time TIMESTAMP;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS end_time TIMESTAMP;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS labor_hours NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS equipment_hours NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS good_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS rework_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS scrap_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS next_action TEXT;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS downstream_impact TEXT;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS submitted_by INTEGER;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS audited_by INTEGER;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS audited_at TIMESTAMP;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS voided_by INTEGER;
        ALTER TABLE operation_reports ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS sequence_no INTEGER;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS routing_operation_id INTEGER;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS operation_no VARCHAR(80);
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS operation_name VARCHAR(160);
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS work_center_id INTEGER;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS planned_quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS actual_quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS good_quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS rework_quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS scrap_quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS labor_hours NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS equipment_hours NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS status VARCHAR(80);
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS qc_status VARCHAR(80);
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS owner_role VARCHAR(120);
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS blocked_reason TEXT;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS next_action TEXT;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS downstream_impact TEXT;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS wip_quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP;
        ALTER TABLE work_order_processes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_completed_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_rework_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_scrap_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS operation_wip_qty NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_orders ADD COLUMN IF NOT EXISTS downstream_impact TEXT;
        ALTER TABLE work_order_processes DROP CONSTRAINT IF EXISTS work_order_processes_status_check;
        ALTER TABLE work_order_processes ADD CONSTRAINT work_order_processes_status_check CHECK (status IS NULL OR status IN ('not_started','ready','in_progress','paused','rework_pending','scrap_pending','completed','cancelled'));
        """,
    ),
    (
        "20260619_003_work_order_cost_schema",
        """
        CREATE TABLE IF NOT EXISTS work_order_costs (id SERIAL PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS work_order_cost_lines (id SERIAL PRIMARY KEY);
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS work_order_id INTEGER;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS material_cost NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS subcontract_cost NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS labor_cost NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS overhead_cost NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS rework_cost NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS scrap_cost NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS service_allocated_cost NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS total_cost NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_costs ADD COLUMN IF NOT EXISTS last_calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS work_order_id INTEGER;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS cost_object_id INTEGER;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS cost_type VARCHAR(80);
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS source_type VARCHAR(80);
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS source_id INTEGER;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS source_no VARCHAR(120);
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS product_id INTEGER;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS amount NUMERIC(14,2) DEFAULT 0;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE work_order_cost_lines ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_work_order_costs_work_order ON work_order_costs(work_order_id);
        CREATE INDEX IF NOT EXISTS idx_work_order_cost_lines_work_order ON work_order_cost_lines(work_order_id);
        CREATE INDEX IF NOT EXISTS idx_work_order_cost_lines_source ON work_order_cost_lines(source_type, source_id);
        """,
    ),
    (
        "20260619_004_print_templates_schema",
        """
        CREATE TABLE IF NOT EXISTS print_templates (
            id SERIAL PRIMARY KEY,
            template_code VARCHAR(80) UNIQUE NOT NULL,
            template_name VARCHAR(160) NOT NULL,
            document_type VARCHAR(80) NOT NULL,
            category VARCHAR(80) NOT NULL DEFAULT '',
            print_type VARCHAR(40) NOT NULL DEFAULT '单据打印',
            status VARCHAR(20) NOT NULL DEFAULT 'enabled',
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            layout_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            content_html TEXT NOT NULL DEFAULT '',
            remark TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE print_templates ADD COLUMN IF NOT EXISTS category VARCHAR(80) NOT NULL DEFAULT '';
        ALTER TABLE print_templates ADD COLUMN IF NOT EXISTS print_type VARCHAR(40) NOT NULL DEFAULT '单据打印';
        ALTER TABLE print_templates ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'enabled';
        ALTER TABLE print_templates ADD COLUMN IF NOT EXISTS is_default BOOLEAN NOT NULL DEFAULT FALSE;
        ALTER TABLE print_templates ADD COLUMN IF NOT EXISTS layout_json JSONB NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE print_templates ADD COLUMN IF NOT EXISTS content_html TEXT NOT NULL DEFAULT '';
        ALTER TABLE print_templates ADD COLUMN IF NOT EXISTS remark TEXT NOT NULL DEFAULT '';
        CREATE INDEX IF NOT EXISTS print_templates_document_type_idx ON print_templates(document_type);
        CREATE INDEX IF NOT EXISTS print_templates_category_idx ON print_templates(category);
        """,
    ),
    (
        "20260619_005_production_completion_schema",
        """
        CREATE TABLE IF NOT EXISTS production_completion_orders (
            id SERIAL PRIMARY KEY,
            completion_no VARCHAR(120) UNIQUE NOT NULL,
            completion_date DATE NOT NULL DEFAULT CURRENT_DATE,
            work_order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity NUMERIC(14,4) NOT NULL DEFAULT 0,
            failed_quantity NUMERIC(14,4) NOT NULL DEFAULT 0,
            unit_cost NUMERIC(14,4) NOT NULL DEFAULT 0,
            warehouse_id INTEGER,
            location_id INTEGER,
            lot_no VARCHAR(120),
            serial_no VARCHAR(120),
            project_code VARCHAR(120),
            status VARCHAR(40) NOT NULL DEFAULT '草稿',
            remark TEXT,
            created_by INTEGER,
            submitted_by INTEGER,
            submitted_at TIMESTAMP,
            audited_by INTEGER,
            audited_at TIMESTAMP,
            posted_by INTEGER,
            posted_at TIMESTAMP,
            reverse_posted_by INTEGER,
            reverse_posted_at TIMESTAMP,
            voided_by INTEGER,
            voided_at TIMESTAMP,
            wo_complete_item_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS completion_no VARCHAR(120);
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS completion_date DATE DEFAULT CURRENT_DATE;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS work_order_id INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS product_id INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS failed_quantity NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS unit_cost NUMERIC(14,4) DEFAULT 0;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS serial_no VARCHAR(120);
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS project_code VARCHAR(120);
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS status VARCHAR(40) DEFAULT '草稿';
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS remark TEXT;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS submitted_by INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS audited_by INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS audited_at TIMESTAMP;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS posted_by INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS posted_at TIMESTAMP;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS reverse_posted_by INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS reverse_posted_at TIMESTAMP;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS voided_by INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS voided_at TIMESTAMP;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS wo_complete_item_id INTEGER;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        ALTER TABLE production_completion_orders ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_production_completion_no ON production_completion_orders(completion_no);
        CREATE INDEX IF NOT EXISTS idx_production_completion_work_order ON production_completion_orders(work_order_id);
        CREATE INDEX IF NOT EXISTS idx_production_completion_project_serial ON production_completion_orders(project_code, serial_no);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_production_completion_legacy_item ON production_completion_orders(wo_complete_item_id) WHERE wo_complete_item_id IS NOT NULL;
        ALTER TABLE wo_complete_items ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80);
        ALTER TABLE wo_complete_items ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        ALTER TABLE wo_complete_items ADD COLUMN IF NOT EXISTS reverse_posted BOOLEAN DEFAULT FALSE;
        ALTER TABLE wo_complete_items ADD COLUMN IF NOT EXISTS reverse_posted_at TIMESTAMP;
        """,
    ),
    (
        "20260619_006_general_ledger_status",
        """
        ALTER TABLE general_ledger ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT 'active';
        CREATE INDEX IF NOT EXISTS idx_general_ledger_status ON general_ledger(status);
        """,
    ),
    (
        "20260619_007_trace_engine_schema",
        """
        CREATE TABLE IF NOT EXISTS trace_links (
            id SERIAL PRIMARY KEY,
            source_doc_type VARCHAR(80) NOT NULL,
            source_doc_id INTEGER NOT NULL,
            source_doc_no VARCHAR(120),
            source_line_id INTEGER,
            source_line_no VARCHAR(80),
            target_doc_type VARCHAR(80) NOT NULL,
            target_doc_id INTEGER NOT NULL,
            target_doc_no VARCHAR(120),
            target_line_id INTEGER,
            target_line_no VARCHAR(80),
            link_type VARCHAR(40) NOT NULL,
            link_strength VARCHAR(20) NOT NULL DEFAULT 'hard',
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER,
            created_event VARCHAR(80)
        );
        CREATE INDEX IF NOT EXISTS idx_trace_links_source
            ON trace_links(source_doc_type, source_doc_id);
        CREATE INDEX IF NOT EXISTS idx_trace_links_target
            ON trace_links(target_doc_type, target_doc_id);
        CREATE INDEX IF NOT EXISTS idx_trace_links_project
            ON trace_links(project_code)
            WHERE project_code IS NOT NULL AND project_code <> '';
        CREATE INDEX IF NOT EXISTS idx_trace_links_serial
            ON trace_links(serial_no)
            WHERE serial_no IS NOT NULL AND serial_no <> '';
        CREATE INDEX IF NOT EXISTS idx_trace_links_created_at
            ON trace_links(created_at);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_trace_links_edge_coalesced
            ON trace_links(
                source_doc_type,
                source_doc_id,
                COALESCE(source_line_id, 0),
                target_doc_type,
                target_doc_id,
                COALESCE(target_line_id, 0),
                link_type
            );

        CREATE TABLE IF NOT EXISTS trace_snapshots (
            id SERIAL PRIMARY KEY,
            doc_type VARCHAR(80) NOT NULL,
            doc_id INTEGER NOT NULL,
            doc_no VARCHAR(120),
            snapshot_event VARCHAR(40) NOT NULL,
            snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            snapshot_by INTEGER,
            project_code VARCHAR(120),
            serial_no VARCHAR(120),
            header_payload JSONB NOT NULL,
            lines_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
            trace_context_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_hash CHAR(64),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_trace_snapshots_doc
            ON trace_snapshots(doc_type, doc_id);
        CREATE INDEX IF NOT EXISTS idx_trace_snapshots_doc_no
            ON trace_snapshots(doc_type, doc_no);
        CREATE INDEX IF NOT EXISTS idx_trace_snapshots_project
            ON trace_snapshots(project_code)
            WHERE project_code IS NOT NULL AND project_code <> '';
        CREATE INDEX IF NOT EXISTS idx_trace_snapshots_serial
            ON trace_snapshots(serial_no)
            WHERE serial_no IS NOT NULL AND serial_no <> '';
        CREATE INDEX IF NOT EXISTS idx_trace_snapshots_event
            ON trace_snapshots(doc_type, doc_id, snapshot_event);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_trace_snapshots_event_hash
            ON trace_snapshots(doc_type, doc_id, snapshot_event, source_hash)
            WHERE source_hash IS NOT NULL;
        """,
    ),
    (
        "20260619_008_bug_report_data_schema_fixes",
        """
        -- Red flush and traceability compatibility columns.
        ALTER TABLE stock_transactions ADD COLUMN IF NOT EXISTS source_doc_id INTEGER;
        CREATE INDEX IF NOT EXISTS idx_stock_transactions_source_doc_id
            ON stock_transactions(source_doc_type, source_doc_id);
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS source_doc_type VARCHAR(80);
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS source_doc_id INTEGER;
        ALTER TABLE voucher_lines ADD COLUMN IF NOT EXISTS source_doc_no VARCHAR(120);
        UPDATE voucher_lines
        SET source_doc_type=COALESCE(source_doc_type, source_type),
            source_doc_id=COALESCE(source_doc_id, source_id),
            source_doc_no=COALESCE(source_doc_no, source_no)
        WHERE source_type IS NOT NULL OR source_id IS NOT NULL OR source_no IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_voucher_lines_source_doc
            ON voucher_lines(source_doc_type, source_doc_id);

        -- Dirty status cleanup.
        UPDATE sales_invoices
        SET status='draft'
        WHERE status=CHR(63) || CHR(63) || CHR(63);
        UPDATE work_orders
        SET status='生产中'
        WHERE status='in_progress';
        UPDATE sales_orders
        SET status='已审核'
        WHERE status='submitted';
        UPDATE purchase_orders
        SET status='已完成'
        WHERE status='completed';
        UPDATE customer_receivables
        SET status='未收款'
        WHERE status='open';
        UPDATE supplier_payables
        SET status='未付款'
        WHERE status IN ('open','unpaid');
        UPDATE vouchers v
        SET status='draft',
            posted_by=NULL,
            posted_at=NULL,
            updated_at=CURRENT_TIMESTAMP,
            remark=COALESCE(remark,'') || ' | 自动回退：过账凭证无明细'
        WHERE status IN ('posted','已过账')
          AND NOT EXISTS (SELECT 1 FROM voucher_lines vl WHERE vl.voucher_id=v.id);

        -- Invalid inventory rows are repaired without deleting business history.
        UPDATE inventory_balances
        SET warehouse_id=(SELECT id FROM warehouses ORDER BY id LIMIT 1),
            updated_at=CURRENT_TIMESTAMP
        WHERE warehouse_id IS NULL
          AND EXISTS (SELECT 1 FROM warehouses);
        UPDATE stock_transactions
        SET warehouse_id=(SELECT id FROM warehouses ORDER BY id LIMIT 1),
            remark=COALESCE(remark,'') || ' | 自动补齐默认仓库'
        WHERE warehouse_id IS NULL
          AND EXISTS (SELECT 1 FROM warehouses);
        UPDATE stock_transactions
        SET remark=COALESCE(remark,'') || ' | 清理测试source_type=' || source_type,
            source_type=NULL
        WHERE source_type IN ('phase5_verifier','phase4_verifier','first_machine_baseline');

        CREATE UNIQUE INDEX IF NOT EXISTS uq_inventory_balances_trace_dimension
            ON inventory_balances(
                product_id,
                COALESCE(warehouse_id, 0),
                COALESCE(location_id, 0),
                COALESCE(lot_no, ''),
                COALESCE(serial_no, ''),
                COALESCE(project_code, '')
            );
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname='inventory_balances_required_keys_chk'
            ) THEN
                ALTER TABLE inventory_balances
                    ADD CONSTRAINT inventory_balances_required_keys_chk
                    CHECK (product_id IS NOT NULL AND warehouse_id IS NOT NULL) NOT VALID;
            END IF;
        END $$;
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname='stock_transactions_required_keys_chk'
            ) THEN
                ALTER TABLE stock_transactions
                    ADD CONSTRAINT stock_transactions_required_keys_chk
                    CHECK (product_id IS NOT NULL AND warehouse_id IS NOT NULL AND quantity IS NOT NULL) NOT VALID;
            END IF;
        END $$;
        """,
    ),
    (
        "20260619_009_bug_report_12_followup_fixes",
        """
        -- Red-flush AR/AP audit fields.
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE customer_receivables ADD COLUMN IF NOT EXISTS updated_by INTEGER;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS created_by INTEGER;
        ALTER TABLE supplier_payables ADD COLUMN IF NOT EXISTS updated_by INTEGER;
        CREATE INDEX IF NOT EXISTS idx_customer_receivables_created_by
            ON customer_receivables(created_by);
        CREATE INDEX IF NOT EXISTS idx_supplier_payables_created_by
            ON supplier_payables(created_by);

        UPDATE customer_receivables cr
        SET created_by=COALESCE(cr.created_by, si.created_by),
            updated_by=COALESCE(cr.updated_by, si.updated_by, si.created_by)
        FROM sales_invoices si
        WHERE cr.invoice_id=si.id
          AND (cr.created_by IS NULL OR cr.updated_by IS NULL);
        UPDATE supplier_payables sp
        SET created_by=COALESCE(sp.created_by, pi.created_by),
            updated_by=COALESCE(sp.updated_by, pi.updated_by, pi.created_by)
        FROM purchase_invoices pi
        WHERE sp.invoice_id=pi.id
          AND (sp.created_by IS NULL OR sp.updated_by IS NULL);

        -- Dirty purchase invoice status cleanup.
        UPDATE purchase_invoices
        SET status='draft'
        WHERE status=CHR(63) || CHR(63) || CHR(63);

        -- Empty voucher headers must not carry nonzero totals.
        UPDATE vouchers v
        SET total_debit=0,
            total_credit=0,
            status='draft',
            posted_by=NULL,
            posted_at=NULL,
            updated_at=CURRENT_TIMESTAMP,
            remark=TRIM(BOTH ' ' FROM CONCAT(COALESCE(v.remark, ''), ' | auto-cleared empty voucher header totals'))
        WHERE (COALESCE(v.total_debit,0) <> 0 OR COALESCE(v.total_credit,0) <> 0)
          AND NOT EXISTS (SELECT 1 FROM voucher_lines vl WHERE vl.voucher_id=v.id);

        -- Backfill a minimal process row for historical work orders that have no process trace.
        WITH default_op AS (
            SELECT id, sequence, operation_no, operation_name, work_center_id
            FROM routing_operations
            WHERE is_active IS DISTINCT FROM FALSE
            ORDER BY sequence NULLS LAST, id
            LIMIT 1
        )
        INSERT INTO work_order_processes (
            work_order_id, process_operation_id, planned_quantity, actual_quantity,
            good_quantity, status, sequence_no, operation_no, operation_name,
            work_center_id, owner_role, next_action, downstream_impact, updated_at
        )
        SELECT
            wo.id,
            default_op.id,
            COALESCE(wo.quantity, 0),
            CASE
                WHEN lower(COALESCE(wo.status, '')) IN ('completed', 'done')
                  OR COALESCE(wo.status, '') LIKE '%完工%'
                THEN COALESCE(wo.quantity, 0)
                ELSE 0
            END,
            CASE
                WHEN lower(COALESCE(wo.status, '')) IN ('completed', 'done')
                  OR COALESCE(wo.status, '') LIKE '%完工%'
                THEN COALESCE(wo.quantity, 0)
                ELSE 0
            END,
            CASE
                WHEN lower(COALESCE(wo.status, '')) IN ('completed', 'done')
                  OR COALESCE(wo.status, '') LIKE '%完工%'
                THEN 'completed'
                WHEN lower(COALESCE(wo.status, '')) IN ('cancelled', 'voided')
                  OR COALESCE(wo.status, '') LIKE '%取消%'
                  OR COALESCE(wo.status, '') LIKE '%作废%'
                THEN 'cancelled'
                WHEN COALESCE(wo.status, '') <> ''
                THEN 'in_progress'
                ELSE 'not_started'
            END,
            COALESCE(default_op.sequence, 10),
            COALESCE(default_op.operation_no, 'OP10'),
            COALESCE(default_op.operation_name, 'Backfilled operation'),
            default_op.work_center_id,
            COALESCE(wo.owner_role, 'production'),
            COALESCE(wo.blocked_reason, 'Backfilled historical work-order process for traceability.'),
            COALESCE(wo.downstream_impact, 'Restores process trace for historical work-order reconciliation.'),
            CURRENT_TIMESTAMP
        FROM work_orders wo
        CROSS JOIN default_op
        WHERE NOT EXISTS (
            SELECT 1 FROM work_order_processes wop WHERE wop.work_order_id=wo.id
        );
        """,
    ),
    (
        "20260620_001_data_scope_service",
        """
        CREATE TABLE IF NOT EXISTS data_scope_rules (
            id SERIAL PRIMARY KEY,
            subject_type VARCHAR(20) NOT NULL,
            subject_id VARCHAR(80) NOT NULL,
            scope_type VARCHAR(40) NOT NULL,
            scope_value VARCHAR(160) NOT NULL,
            permission VARCHAR(20) NOT NULL DEFAULT 'view',
            status VARCHAR(20) NOT NULL DEFAULT 'enabled',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_data_scope_rules_subject
            ON data_scope_rules(subject_type, subject_id, permission, status);
        CREATE INDEX IF NOT EXISTS idx_data_scope_rules_scope
            ON data_scope_rules(scope_type, scope_value, permission, status);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_data_scope_rule
            ON data_scope_rules(subject_type, subject_id, scope_type, scope_value, permission);

        CREATE TABLE IF NOT EXISTS data_access_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            role VARCHAR(80),
            resource_type VARCHAR(80),
            resource_id VARCHAR(120),
            action VARCHAR(40) NOT NULL DEFAULT 'view',
            allowed BOOLEAN NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_data_access_logs_user_time
            ON data_access_logs(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_data_access_logs_resource
            ON data_access_logs(resource_type, resource_id, created_at DESC);
        """,
    ),
    (
        "20260620_002_sales_shipments_inventory_posted",
        """
        ALTER TABLE sales_shipments ADD COLUMN IF NOT EXISTS inventory_posted BOOLEAN DEFAULT FALSE;
        """,
    ),
    (
        "20260621_001_p0_trace_integrity",
        """
        CREATE TABLE IF NOT EXISTS trace_integrity_findings (
            id SERIAL PRIMARY KEY,
            finding_type VARCHAR(80) NOT NULL,
            doc_type VARCHAR(80),
            doc_id INTEGER,
            doc_no VARCHAR(120),
            project_code VARCHAR(80),
            serial_no VARCHAR(80),
            description TEXT,
            severity VARCHAR(20) DEFAULT 'warning',
            status VARCHAR(20) DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_trace_integrity_status
            ON trace_integrity_findings(status, severity);
        CREATE INDEX IF NOT EXISTS idx_trace_integrity_doc
            ON trace_integrity_findings(doc_type, doc_id);
        """,
    ),
    (
        "20260621_002_p0_bom_versions",
        """
        CREATE TABLE IF NOT EXISTS bom_versions (
            id SERIAL PRIMARY KEY,
            bom_id INTEGER NOT NULL REFERENCES boms(id) ON DELETE CASCADE,
            version_no VARCHAR(40) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            effective_date DATE,
            expire_date DATE,
            approved_by INTEGER,
            approved_at TIMESTAMP,
            change_note TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(bom_id, version_no)
        );
        CREATE INDEX IF NOT EXISTS idx_bom_versions_bom
            ON bom_versions(bom_id, version_no);
        CREATE INDEX IF NOT EXISTS idx_bom_versions_status
            ON bom_versions(status, effective_date, expire_date);

        CREATE TABLE IF NOT EXISTS work_order_bom_snapshots (
            id SERIAL PRIMARY KEY,
            work_order_id INTEGER NOT NULL,
            bom_version_id INTEGER,
            snapshot_json JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_wo_bom_snapshots_wo
            ON work_order_bom_snapshots(work_order_id);

        CREATE TABLE IF NOT EXISTS work_order_process_snapshots (
            id SERIAL PRIMARY KEY,
            work_order_id INTEGER NOT NULL,
            route_version_id INTEGER,
            snapshot_json JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_wo_process_snapshots_wo
            ON work_order_process_snapshots(work_order_id);

        CREATE TABLE IF NOT EXISTS work_order_drawing_snapshots (
            id SERIAL PRIMARY KEY,
            work_order_id INTEGER NOT NULL,
            drawing_version_id INTEGER,
            snapshot_json JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_wo_drawing_snapshots_wo
            ON work_order_drawing_snapshots(work_order_id);

        CREATE TABLE IF NOT EXISTS ecn_impact_results (
            id SERIAL PRIMARY KEY,
            ecn_id INTEGER NOT NULL,
            affected_type VARCHAR(80) NOT NULL,
            affected_id INTEGER,
            affected_no VARCHAR(120),
            impact_level VARCHAR(20) DEFAULT 'medium',
            action_required TEXT,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ecn_impact_ecn
            ON ecn_impact_results(ecn_id, status);
        CREATE INDEX IF NOT EXISTS idx_ecn_impact_affected
            ON ecn_impact_results(affected_type, affected_id);
        """,
    ),
    (
        "20260621_003_p0_mrp_engine",
        """
        CREATE TABLE IF NOT EXISTS mrp_runs (
            id SERIAL PRIMARY KEY,
            run_no VARCHAR(60) NOT NULL UNIQUE,
            source_type VARCHAR(40) NOT NULL,
            source_id INTEGER,
            source_no VARCHAR(120),
            project_code VARCHAR(80),
            serial_no VARCHAR(80),
            bom_version_id INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            kitting_rate NUMERIC(5,2) DEFAULT 0,
            total_gross_qty NUMERIC(18,4) DEFAULT 0,
            total_net_qty NUMERIC(18,4) DEFAULT 0,
            shortage_line_count INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mrp_runs_source
            ON mrp_runs(source_type, source_id);
        CREATE INDEX IF NOT EXISTS idx_mrp_runs_project_serial
            ON mrp_runs(project_code, serial_no);

        CREATE TABLE IF NOT EXISTS mrp_run_items (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES mrp_runs(id) ON DELETE CASCADE,
            material_id INTEGER,
            material_code VARCHAR(80),
            material_name VARCHAR(200),
            material_spec VARCHAR(200),
            material_unit VARCHAR(40),
            bom_level INTEGER DEFAULT 0,
            gross_qty NUMERIC(18,4) DEFAULT 0,
            available_qty NUMERIC(18,4) DEFAULT 0,
            locked_qty NUMERIC(18,4) DEFAULT 0,
            reserved_qty NUMERIC(18,4) DEFAULT 0,
            purchase_on_order_qty NUMERIC(18,4) DEFAULT 0,
            production_on_order_qty NUMERIC(18,4) DEFAULT 0,
            outsource_on_order_qty NUMERIC(18,4) DEFAULT 0,
            net_qty NUMERIC(18,4) DEFAULT 0,
            suggestion_type VARCHAR(40) DEFAULT 'none',
            required_date DATE,
            project_code VARCHAR(80),
            serial_no VARCHAR(80),
            source_bom_item_id INTEGER,
            parent_material_id INTEGER,
            loss_rate NUMERIC(8,4) DEFAULT 0,
            substitute_for INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mrp_run_items_run
            ON mrp_run_items(run_id);
        CREATE INDEX IF NOT EXISTS idx_mrp_run_items_material
            ON mrp_run_items(material_id);

        CREATE TABLE IF NOT EXISTS mrp_suggestions (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES mrp_runs(id) ON DELETE CASCADE,
            suggestion_type VARCHAR(40) NOT NULL,
            material_id INTEGER,
            material_code VARCHAR(80),
            material_name VARCHAR(200),
            qty NUMERIC(18,4) NOT NULL DEFAULT 0,
            required_date DATE,
            project_code VARCHAR(80),
            serial_no VARCHAR(80),
            status VARCHAR(20) NOT NULL DEFAULT 'open',
            converted_doc_type VARCHAR(60),
            converted_doc_id INTEGER,
            converted_doc_no VARCHAR(120),
            converted_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_mrp_suggestions_run
            ON mrp_suggestions(run_id, status);
        CREATE INDEX IF NOT EXISTS idx_mrp_suggestions_status
            ON mrp_suggestions(status, suggestion_type);
        """,
    ),
    (
        "20260621_004_p0_cost_engine",
        """
        CREATE TABLE IF NOT EXISTS cost_runs (
            id SERIAL PRIMARY KEY,
            run_no VARCHAR(60) NOT NULL UNIQUE,
            period VARCHAR(20),
            project_code VARCHAR(80),
            serial_no VARCHAR(80),
            work_order_id INTEGER,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            total_material_cost NUMERIC(18,4) DEFAULT 0,
            total_labor_cost NUMERIC(18,4) DEFAULT 0,
            total_overhead_cost NUMERIC(18,4) DEFAULT 0,
            total_outsource_cost NUMERIC(18,4) DEFAULT 0,
            total_quality_cost NUMERIC(18,4) DEFAULT 0,
            total_service_cost NUMERIC(18,4) DEFAULT 0,
            total_cost NUMERIC(18,4) DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cost_runs_project_serial
            ON cost_runs(project_code, serial_no);
        CREATE INDEX IF NOT EXISTS idx_cost_runs_period
            ON cost_runs(period, status);

        CREATE TABLE IF NOT EXISTS cost_run_items (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES cost_runs(id) ON DELETE CASCADE,
            cost_type VARCHAR(40) NOT NULL,
            source_type VARCHAR(80),
            source_id INTEGER,
            source_no VARCHAR(120),
            product_id INTEGER,
            quantity NUMERIC(18,4) DEFAULT 0,
            unit_cost NUMERIC(18,4) DEFAULT 0,
            amount NUMERIC(18,4) NOT NULL DEFAULT 0,
            project_code VARCHAR(80),
            serial_no VARCHAR(80),
            work_order_id INTEGER,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cost_run_items_run
            ON cost_run_items(run_id, cost_type);
        CREATE INDEX IF NOT EXISTS idx_cost_run_items_source
            ON cost_run_items(source_type, source_id);

        CREATE TABLE IF NOT EXISTS cost_reconciliation_results (
            id SERIAL PRIMARY KEY,
            period VARCHAR(20),
            project_code VARCHAR(80),
            serial_no VARCHAR(80),
            business_cost NUMERIC(18,4) DEFAULT 0,
            inventory_cost NUMERIC(18,4) DEFAULT 0,
            gl_cost NUMERIC(18,4) DEFAULT 0,
            difference NUMERIC(18,4) DEFAULT 0,
            status VARCHAR(20) DEFAULT 'open',
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_cost_recon_period
            ON cost_reconciliation_results(period, status);
        """,
    ),
    (
        "20260621_005_p0_data_permissions",
        """
        CREATE TABLE IF NOT EXISTS data_permission_rules (
            id SERIAL PRIMARY KEY,
            subject_type VARCHAR(20) NOT NULL DEFAULT 'user',
            subject_id VARCHAR(80) NOT NULL,
            scope_type VARCHAR(40) NOT NULL,
            scope_id VARCHAR(120) NOT NULL,
            scope_label VARCHAR(200),
            permission VARCHAR(20) NOT NULL DEFAULT 'view',
            status VARCHAR(20) NOT NULL DEFAULT 'enabled',
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_data_permission_rule
            ON data_permission_rules(subject_type, subject_id, scope_type, scope_id, permission);
        CREATE INDEX IF NOT EXISTS idx_data_permission_subject
            ON data_permission_rules(subject_type, subject_id, status);
        """,
    ),
    (
        "20260621_006_p0_bom_substitutes",
        """
        CREATE TABLE IF NOT EXISTS bom_substitute_materials (
            id SERIAL PRIMARY KEY,
            bom_item_id INTEGER NOT NULL,
            substitute_product_id INTEGER NOT NULL,
            priority INTEGER NOT NULL DEFAULT 1,
            ratio NUMERIC(18,6) NOT NULL DEFAULT 1,
            allow_auto_substitute BOOLEAN NOT NULL DEFAULT FALSE,
            approval_status VARCHAR(20) NOT NULL DEFAULT 'approved',
            approved_by INTEGER,
            approved_at TIMESTAMP,
            remark VARCHAR(500),
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_bom_substitute_bom_item
            ON bom_substitute_materials(bom_item_id);
        CREATE INDEX IF NOT EXISTS idx_bom_substitute_product
            ON bom_substitute_materials(substitute_product_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bom_substitute_item_product
            ON bom_substitute_materials(bom_item_id, substitute_product_id);

        CREATE TABLE IF NOT EXISTS ecn_action_tasks (
            id SERIAL PRIMARY KEY,
            ecn_id INTEGER NOT NULL,
            impact_result_id INTEGER,
            task_type VARCHAR(40) NOT NULL,
            affected_doc_type VARCHAR(40),
            affected_doc_id INTEGER,
            affected_doc_no VARCHAR(80),
            action_description VARCHAR(500),
            action_status VARCHAR(20) NOT NULL DEFAULT 'pending',
            assigned_to INTEGER,
            resolved_by INTEGER,
            resolved_at TIMESTAMP,
            resolution_remark VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_ecn_action_tasks_ecn
            ON ecn_action_tasks(ecn_id);
        CREATE INDEX IF NOT EXISTS idx_ecn_action_tasks_status
            ON ecn_action_tasks(action_status);
        """,
    ),
    (
        "20260622_001_cost_variance_and_export_approval",
        """
        -- P2-B3: cost_run_items 增加标准成本与差异列
        ALTER TABLE cost_run_items
            ADD COLUMN IF NOT EXISTS standard_cost NUMERIC(18,4) DEFAULT 0,
            ADD COLUMN IF NOT EXISTS variance_amount NUMERIC(18,4) DEFAULT 0,
            ADD COLUMN IF NOT EXISTS variance_reason VARCHAR(500);

        -- P3-B5: 导出审批流表
        CREATE TABLE IF NOT EXISTS export_approval_requests (
            id SERIAL PRIMARY KEY,
            requester_id INTEGER NOT NULL,
            requester_name VARCHAR(80),
            resource_type VARCHAR(60) NOT NULL,
            resource_id VARCHAR(120),
            resource_label VARCHAR(200),
            export_format VARCHAR(20) DEFAULT 'csv',
            filter_summary VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            approver_id INTEGER,
            approver_name VARCHAR(80),
            approved_at TIMESTAMP,
            approval_remark VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_export_approval_status
            ON export_approval_requests(status, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_export_approval_requester
            ON export_approval_requests(requester_id);
        """,
    ),
    (
        "20260622_002_mrp_bom_snapshot_binding",
        """
        -- P5-B1: mrp_runs 绑定 BOM 快照 ID
        ALTER TABLE mrp_runs
            ADD COLUMN IF NOT EXISTS bom_snapshot_id INTEGER;

        CREATE INDEX IF NOT EXISTS idx_mrp_runs_bom_snapshot
            ON mrp_runs(bom_snapshot_id);
        """,
    ),
    (
        "20260622_003_bank_statement_import",
        """
        -- C-2: 银行对账单导入与匹配
        CREATE TABLE IF NOT EXISTS bank_statements (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES cash_bank_accounts(id),
            statement_no VARCHAR(120),
            statement_date DATE NOT NULL DEFAULT CURRENT_DATE,
            period_year INTEGER,
            period_month INTEGER,
            opening_balance NUMERIC(14,2) DEFAULT 0,
            closing_balance NUMERIC(14,2) DEFAULT 0,
            total_deposits NUMERIC(14,2) DEFAULT 0,
            total_withdrawals NUMERIC(14,2) DEFAULT 0,
            currency VARCHAR(20) DEFAULT 'CNY',
            status VARCHAR(30) NOT NULL DEFAULT 'imported',
            source_file VARCHAR(255),
            imported_by INTEGER,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_bank_statements_account_date
            ON bank_statements(account_id, statement_date DESC);
        CREATE INDEX IF NOT EXISTS idx_bank_statements_status
            ON bank_statements(status);

        CREATE TABLE IF NOT EXISTS bank_statement_lines (
            id SERIAL PRIMARY KEY,
            statement_id INTEGER NOT NULL REFERENCES bank_statements(id) ON DELETE CASCADE,
            line_no INTEGER NOT NULL DEFAULT 0,
            transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
            amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            direction VARCHAR(10) NOT NULL DEFAULT 'in',
            counterparty_name VARCHAR(200),
            counterparty_account VARCHAR(120),
            counterparty_bank VARCHAR(160),
            summary TEXT,
            bank_reference VARCHAR(200),
            matched_journal_id INTEGER,
            match_status VARCHAR(20) NOT NULL DEFAULT 'unmatched',
            matched_at TIMESTAMP,
            matched_by INTEGER,
            match_method VARCHAR(20),
            match_score NUMERIC(5,2),
            match_remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(statement_id, line_no)
        );
        CREATE INDEX IF NOT EXISTS idx_bank_statement_lines_statement
            ON bank_statement_lines(statement_id, line_no);
        CREATE INDEX IF NOT EXISTS idx_bank_statement_lines_match_status
            ON bank_statement_lines(match_status, transaction_date DESC);
        CREATE INDEX IF NOT EXISTS idx_bank_statement_lines_journal
            ON bank_statement_lines(matched_journal_id)
            WHERE matched_journal_id IS NOT NULL;
        """,
    ),
    (
        "20260622_004_fx_period_end_adjustment",
        """
        -- C-5: 外汇期末调整
        CREATE TABLE IF NOT EXISTS exchange_rate_history (
            id SERIAL PRIMARY KEY,
            currency_code VARCHAR(20) NOT NULL,
            rate_date DATE NOT NULL,
            rate_to_base NUMERIC(18,8) NOT NULL,
            rate_type VARCHAR(40) DEFAULT 'period_end',
            source VARCHAR(120),
            remark TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(currency_code, rate_date, rate_type)
        );
        CREATE INDEX IF NOT EXISTS idx_exchange_rate_history_currency_date
            ON exchange_rate_history(currency_code, rate_date DESC);

        CREATE TABLE IF NOT EXISTS fx_adjustment_runs (
            id SERIAL PRIMARY KEY,
            run_no VARCHAR(120) NOT NULL UNIQUE,
            period_year INTEGER NOT NULL,
            period_month INTEGER NOT NULL,
            adjustment_date DATE NOT NULL DEFAULT CURRENT_DATE,
            total_gain_loss NUMERIC(14,2) DEFAULT 0,
            ar_adjustment NUMERIC(14,2) DEFAULT 0,
            ap_adjustment NUMERIC(14,2) DEFAULT 0,
            cash_adjustment NUMERIC(14,2) DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            voucher_id INTEGER,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            remark TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_fx_adjustment_runs_period
            ON fx_adjustment_runs(period_year, period_month);

        CREATE TABLE IF NOT EXISTS fx_adjustment_lines (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL REFERENCES fx_adjustment_runs(id) ON DELETE CASCADE,
            source_type VARCHAR(80) NOT NULL,
            source_id INTEGER,
            source_no VARCHAR(120),
            partner_type VARCHAR(40),
            partner_name VARCHAR(160),
            currency_code VARCHAR(20) NOT NULL,
            original_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            original_rate NUMERIC(18,8) DEFAULT 1,
            base_amount_original NUMERIC(14,2) DEFAULT 0,
            period_end_rate NUMERIC(18,8) DEFAULT 1,
            base_amount_adjusted NUMERIC(14,2) DEFAULT 0,
            gain_loss_amount NUMERIC(14,2) DEFAULT 0,
            adjustment_type VARCHAR(20) DEFAULT 'unrealized',
            account_code VARCHAR(80),
            account_name VARCHAR(160),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_fx_adjustment_lines_run
            ON fx_adjustment_lines(run_id);
        CREATE INDEX IF NOT EXISTS idx_fx_adjustment_lines_source
            ON fx_adjustment_lines(source_type, source_id);
        """,
    ),
    (
        "20260622_005_transfer_approval_flow",
        """
        ALTER TABLE transfer_orders
            ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) DEFAULT 'not_required',
            ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS submitted_by VARCHAR(80),
            ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS approved_by VARCHAR(80),
            ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP,
            ADD COLUMN IF NOT EXISTS rejected_by VARCHAR(80),
            ADD COLUMN IF NOT EXISTS approval_remark TEXT;
        CREATE INDEX IF NOT EXISTS idx_transfer_orders_approval_status
            ON transfer_orders(approval_status);
        """,
    ),
    (
        "20260622_006_archive_tables",
        """
        CREATE TABLE IF NOT EXISTS document_archive_records (
            id SERIAL PRIMARY KEY,
            archive_batch_no VARCHAR(40) NOT NULL UNIQUE,
            archive_date DATE NOT NULL,
            source_table VARCHAR(80) NOT NULL,
            date_column VARCHAR(40) NOT NULL DEFAULT 'created_at',
            date_from DATE,
            date_to DATE NOT NULL,
            record_count INTEGER DEFAULT 0,
            status VARCHAR(20) DEFAULT 'completed',
            archived_by VARCHAR(80),
            remark TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_document_archive_records_source
            ON document_archive_records(source_table, date_to);
        CREATE INDEX IF NOT EXISTS idx_document_archive_records_batch
            ON document_archive_records(archive_batch_no);
        """,
    ),
    (
        "20260622_007_purchase_order_item_expected_date",
        """
        ALTER TABLE purchase_order_items ADD COLUMN IF NOT EXISTS expected_date DATE;
        CREATE INDEX IF NOT EXISTS idx_purchase_order_items_expected_date
            ON purchase_order_items(expected_date);
        """,
    ),
    (
        "20260622_008_bom_ecn_change_details",
        """
        CREATE TABLE IF NOT EXISTS bom_engineering_change_details (
            id SERIAL PRIMARY KEY,
            ecn_id INTEGER NOT NULL REFERENCES bom_engineering_changes(id) ON DELETE CASCADE,
            material VARCHAR(255),
            specification VARCHAR(255),
            unit VARCHAR(80),
            old_value TEXT,
            new_value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_bom_ecn_details_ecn_id
            ON bom_engineering_change_details(ecn_id);
        """,
    ),
    (
        "20260622_009_subcontract_items_extra_columns",
        """
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS process_name VARCHAR(255);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS warehouse VARCHAR(120);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS location VARCHAR(120);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS lot_no VARCHAR(120);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS source_line_no VARCHAR(80);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS line_project_code VARCHAR(120);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS line_serial_no VARCHAR(120);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS material_code VARCHAR(120);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS material_name VARCHAR(255);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS material_spec VARCHAR(255);
        ALTER TABLE subcontract_items ADD COLUMN IF NOT EXISTS material_unit VARCHAR(80);
        """,
    ),
    (
        "20260624_001_purchase_receipt_item_warehouse",
        """
        ALTER TABLE purchase_receipt_items ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        UPDATE purchase_receipt_items pri
        SET warehouse_id = pr.warehouse_id
        FROM purchase_receipts pr
        WHERE pri.receipt_id = pr.id
          AND pri.warehouse_id IS NULL;
        CREATE INDEX IF NOT EXISTS idx_purchase_receipt_items_warehouse_id
            ON purchase_receipt_items(warehouse_id);
        """,
    ),
    (
        "20260625_001_perf_indexes_audit_logs",
        """
        CREATE INDEX IF NOT EXISTS idx_audit_logs_doc
            ON audit_logs(doc_type, doc_id);
        CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id
            ON audit_logs(user_id);
        """,
    ),
    (
        "20260625_002_perf_indexes_purchase_receipts",
        """
        CREATE INDEX IF NOT EXISTS idx_purchase_receipts_status
            ON purchase_receipts(status);
        CREATE INDEX IF NOT EXISTS idx_purchase_receipts_project_code
            ON purchase_receipts(project_code);
        CREATE INDEX IF NOT EXISTS idx_purchase_receipts_receipt_date
            ON purchase_receipts(receipt_date);
        """,
    ),
    (
        "20260625_003_perf_indexes_order_status",
        """
        CREATE INDEX IF NOT EXISTS idx_sales_orders_status
            ON sales_orders(status);
        CREATE INDEX IF NOT EXISTS idx_purchase_orders_status
            ON purchase_orders(status);
        CREATE INDEX IF NOT EXISTS idx_work_orders_status
            ON work_orders(status);
        CREATE INDEX IF NOT EXISTS idx_subcontract_orders_supplier_id
            ON subcontract_orders(supplier_id);
        CREATE INDEX IF NOT EXISTS idx_subcontract_orders_status
            ON subcontract_orders(status);
        """,
    ),
    (
        "20260625_004_perf_indexes_operation_logs",
        """
        CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at
            ON operation_logs(created_at);
        """,
    ),
    (
        "20260627_001_inventory_line_warehouse_location",
        """
        -- 出入库单据明细统一具备 仓库/库位 字段。
        -- 启用库位与否由运行时按该仓库是否在 locations 表存在库位记录判定（不加标志位）。
        -- 调拨明细按 调出仓库/调出库位/调入仓库/调入库位 四列存储。
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS from_warehouse_id INTEGER;
        ALTER TABLE transfer_order_items ADD COLUMN IF NOT EXISTS to_warehouse_id INTEGER;
        UPDATE transfer_order_items toi
        SET from_warehouse_id = hdr.from_warehouse_id
        FROM transfer_orders hdr
        WHERE toi.transfer_id = hdr.id
          AND toi.from_warehouse_id IS NULL
          AND hdr.from_warehouse_id IS NOT NULL;
        UPDATE transfer_order_items toi
        SET to_warehouse_id = hdr.to_warehouse_id
        FROM transfer_orders hdr
        WHERE toi.transfer_id = hdr.id
          AND toi.to_warehouse_id IS NULL
          AND hdr.to_warehouse_id IS NOT NULL;

        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS location_id INTEGER;
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS line_warehouse_id INTEGER;
        ALTER TABLE inventory_check_order_items ADD COLUMN IF NOT EXISTS line_location_id INTEGER;
        UPDATE inventory_check_order_items ici
        SET warehouse_id = ico.warehouse_id
        FROM inventory_check_orders ico
        WHERE ici.check_id = ico.id
          AND ici.warehouse_id IS NULL
          AND ico.warehouse_id IS NOT NULL;
        UPDATE inventory_check_order_items ici
        SET location_id = ico.location_id
        FROM inventory_check_orders ico
        WHERE ici.check_id = ico.id
          AND ici.location_id IS NULL
          AND ico.location_id IS NOT NULL;
        UPDATE inventory_check_order_items
        SET line_warehouse_id = warehouse_id
        WHERE line_warehouse_id IS NULL
          AND warehouse_id IS NOT NULL;
        UPDATE inventory_check_order_items
        SET line_location_id = location_id
        WHERE line_location_id IS NULL
          AND location_id IS NOT NULL;

        ALTER TABLE purchase_receipt_items ADD COLUMN IF NOT EXISTS location_id INTEGER;

        ALTER TABLE sales_shipment_items ADD COLUMN IF NOT EXISTS warehouse_id INTEGER;
        ALTER TABLE sales_shipment_items ADD COLUMN IF NOT EXISTS location_id INTEGER;

        -- 组装/拆卸明细沿用既有 line_warehouse_id/line_location_id 命名，此处仅做正式登记。
        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS line_warehouse_id INTEGER;
        ALTER TABLE inventory_assembly_items ADD COLUMN IF NOT EXISTS line_location_id INTEGER;
        """,
    ),
    (
        "20260628_001_inventory_movement_documents",
        """
        CREATE TABLE IF NOT EXISTS inventory_movement_documents (
            id SERIAL PRIMARY KEY,
            doc_no VARCHAR(80) NOT NULL UNIQUE,
            direction VARCHAR(10) NOT NULL,
            movement_kind VARCHAR(30) NOT NULL,
            transaction_type VARCHAR(30) NOT NULL,
            tx_date DATE NOT NULL,
            warehouse_id INTEGER NOT NULL,
            location_id INTEGER,
            project_code VARCHAR(120),
            remark TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            approval_status VARCHAR(20) NOT NULL DEFAULT 'not_required',
            submitted_at TIMESTAMP,
            submitted_by VARCHAR(80),
            audited_at TIMESTAMP,
            audited_by VARCHAR(80),
            voided_at TIMESTAMP,
            voided_by VARCHAR(80),
            approval_remark TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by VARCHAR(80),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_movement_documents_status
            ON inventory_movement_documents(status);
        CREATE INDEX IF NOT EXISTS idx_inventory_movement_documents_direction
            ON inventory_movement_documents(direction);
        CREATE INDEX IF NOT EXISTS idx_inventory_movement_documents_tx_date
            ON inventory_movement_documents(tx_date);
        CREATE INDEX IF NOT EXISTS idx_inventory_movement_documents_kind_status
            ON inventory_movement_documents(movement_kind, status);

        CREATE TABLE IF NOT EXISTS inventory_movement_lines (
            id SERIAL PRIMARY KEY,
            doc_id INTEGER NOT NULL REFERENCES inventory_movement_documents(id) ON DELETE CASCADE,
            line_no INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity NUMERIC(14,3) NOT NULL,
            unit_cost NUMERIC(14,2) NOT NULL DEFAULT 0,
            amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            lot_no VARCHAR(120),
            serial_no VARCHAR(120),
            line_project_code VARCHAR(120),
            line_warehouse_id INTEGER,
            line_location_id INTEGER,
            usage_reason TEXT,
            source_doc_no VARCHAR(120),
            source_line_no VARCHAR(80),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(doc_id, line_no)
        );
        CREATE INDEX IF NOT EXISTS idx_inventory_movement_lines_doc_id
            ON inventory_movement_lines(doc_id);
        CREATE INDEX IF NOT EXISTS idx_inventory_movement_lines_product
            ON inventory_movement_lines(product_id);
        """,
    ),
    (
        "20260628_002_inventory_movement_backfill_posted",
        """
        -- Backfill header records for already-posted stock_transactions rows so the
        -- new draft/audit flow can list and inspect historical documents uniformly.
        -- Defensive: on a fresh database (no stock_transactions table yet) the
        -- backfill is a no-op; on existing installations it mirrors legacy rows
        -- into inventory_movement_documents / inventory_movement_lines.
        -- Idempotent: ON CONFLICT (doc_no) DO NOTHING.
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables
                       WHERE table_schema = current_schema()
                         AND table_name = 'stock_transactions') THEN
                INSERT INTO inventory_movement_documents
                    (doc_no, direction, movement_kind, transaction_type, tx_date,
                     warehouse_id, location_id, project_code, remark, status,
                     audited_at, created_at, updated_at)
                SELECT
                    st.reference_no,
                    CASE WHEN st.transaction_type IN ('其他入库','销售退货入库') THEN 'in' ELSE 'out' END,
                    CASE st.transaction_type
                        WHEN '其他入库' THEN 'other_inbound'
                        WHEN '其他出库' THEN 'other_outbound'
                        WHEN '销售退货入库' THEN 'sales_return'
                        WHEN '采购退货出库' THEN 'purchase_return'
                    END,
                    st.transaction_type,
                    MAX(st.transaction_date)::date,
                    MAX(st.warehouse_id),
                    MAX(st.location_id),
                    MAX(st.project_code),
                    MAX(st.remark),
                    'posted',
                    MAX(st.created_at),
                    MAX(st.created_at),
                    MAX(st.created_at)
                FROM stock_transactions st
                WHERE st.transaction_type IN ('其他入库','其他出库','销售退货入库','采购退货出库')
                  AND st.reference_no IS NOT NULL
                  AND st.reference_no <> ''
                GROUP BY st.reference_no, st.transaction_type
                ON CONFLICT (doc_no) DO NOTHING;

                INSERT INTO inventory_movement_lines
                    (doc_id, line_no, product_id, quantity, unit_cost, amount,
                     lot_no, serial_no, line_project_code, line_warehouse_id,
                     line_location_id, usage_reason, source_doc_no, source_line_no,
                     created_at)
                SELECT
                    d.id,
                    ROW_NUMBER() OVER (PARTITION BY st.reference_no, st.transaction_type ORDER BY st.id),
                    st.product_id,
                    st.quantity,
                    COALESCE(st.unit_cost, 0),
                    COALESCE(st.amount, st.quantity * COALESCE(st.unit_cost, 0)),
                    st.lot_no,
                    st.serial_no,
                    st.project_code,
                    st.warehouse_id,
                    st.location_id,
                    st.usage_reason,
                    st.source_doc_no,
                    st.source_line_no,
                    COALESCE(st.created_at, NOW())
                FROM stock_transactions st
                JOIN inventory_movement_documents d ON d.doc_no = st.reference_no
                WHERE st.transaction_type IN ('其他入库','其他出库','销售退货入库','采购退货出库')
                ON CONFLICT (doc_id, line_no) DO NOTHING;
            END IF;
        END $$;
        """,
    ),
    (
        "20260628_003_inventory_balance_trace_unique_cleanup",
        """
        ALTER TABLE inventory_balances
            DROP CONSTRAINT IF EXISTS inventory_balances_product_id_warehouse_id_location_id_lot__key;
        DROP INDEX IF EXISTS inventory_balances_product_id_warehouse_id_location_id_lot__key;
        """,
    ),
    (
        "20260629_001_service_acceptance_document_number",
        """
        ALTER TABLE machine_service_acceptance_checks
            ADD COLUMN IF NOT EXISTS acceptance_no VARCHAR(80);
        UPDATE machine_service_acceptance_checks
        SET acceptance_no = 'SA-LEGACY-' || id::text
        WHERE acceptance_no IS NULL OR acceptance_no = '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_service_acceptance_acceptance_no
            ON machine_service_acceptance_checks(acceptance_no)
            WHERE acceptance_no IS NOT NULL AND acceptance_no <> '';
        """,
    ),
    (
        "20260629_002_document_number_rules",
        """
        CREATE TABLE IF NOT EXISTS erp_code_rules (
            rule_key VARCHAR(120) PRIMARY KEY,
            target_type VARCHAR(40) NOT NULL,
            prefix VARCHAR(40) NOT NULL,
            date_format VARCHAR(20) NOT NULL DEFAULT 'YYYYMMDD',
            sequence_length INTEGER NOT NULL DEFAULT 4,
            separator VARCHAR(8) NOT NULL DEFAULT '',
            reset_scope VARCHAR(20) NOT NULL DEFAULT 'daily',
            manual_allowed BOOLEAN NOT NULL DEFAULT TRUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            remark TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_erp_code_rules_target_active
            ON erp_code_rules(target_type, is_active);
        INSERT INTO erp_code_rules
            (rule_key, target_type, prefix, date_format, sequence_length, separator, reset_scope, manual_allowed, is_active, remark)
        VALUES
            ('document:purchase_requisitions.req_no', 'document', 'PR', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '采购申请单据编号规则'),
            ('document:purchase_orders.order_no', 'document', 'PO', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '采购订单单据编号规则'),
            ('document:purchase_receipts.receipt_no', 'document', 'PIR', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '采购入库单据编号规则'),
            ('document:sales_orders.order_no', 'document', 'SO', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '销售订单单据编号规则'),
            ('document:sales_shipments.shipment_no', 'document', 'SS', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '销售发货单据编号规则'),
            ('document:work_orders.wo_no', 'document', 'WO', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '生产工单单据编号规则'),
            ('document:subcontract_orders.order_no', 'document', 'OS', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '委外订单单据编号规则'),
            ('document:subcontract_issue_orders.issue_no', 'document', 'OSI', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '委外发料单据编号规则'),
            ('document:subcontract_receive_orders.receive_no', 'document', 'OSR', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '委外收回单据编号规则'),
            ('document:transfer_orders.transfer_no', 'document', 'TR', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '库存调拨单据编号规则'),
            ('document:inventory_check_orders.check_no', 'document', 'IC', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '库存盘点单据编号规则'),
            ('document:inventory_adjustments.adj_no', 'document', 'IA', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '库存调整单据编号规则'),
            ('document:machine_service_acceptance_checks.acceptance_no', 'document', 'SA', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '安装验收单据编号规则'),
            ('document:machine_service_orders.order_no', 'document', 'SVO', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '服务单单据编号规则'),
            ('document:machine_service_rmas.rma_no', 'document', 'RMA', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '服务RMA单据编号规则'),
            ('document:customer_receipts.receipt_no', 'document', 'CR', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '收款单单据编号规则'),
            ('document:supplier_payments.payment_no', 'document', 'SP', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '付款单单据编号规则'),
            ('document:sales_invoices.invoice_no', 'document', 'SI', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '销售发票单据编号规则'),
            ('document:purchase_invoices.invoice_no', 'document', 'PI', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '采购发票单据编号规则'),
            ('document:vouchers.voucher_no', 'document', 'V', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '会计凭证编号规则')
        ON CONFLICT (rule_key) DO NOTHING;
        """,
    ),
    (
        "20260629_003_remaining_document_header_numbers",
        """
        ALTER TABLE machine_service_cards
            ADD COLUMN IF NOT EXISTS card_no VARCHAR(80);
        UPDATE machine_service_cards
        SET card_no = 'SC-LEGACY-' || id::text
        WHERE card_no IS NULL OR card_no = '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_machine_service_cards_card_no
            ON machine_service_cards(card_no)
            WHERE card_no IS NOT NULL AND card_no <> '';

        ALTER TABLE machine_service_return_visits
            ADD COLUMN IF NOT EXISTS visit_no VARCHAR(80);
        UPDATE machine_service_return_visits
        SET visit_no = 'SV-LEGACY-' || id::text
        WHERE visit_no IS NULL OR visit_no = '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_machine_service_return_visits_visit_no
            ON machine_service_return_visits(visit_no)
            WHERE visit_no IS NOT NULL AND visit_no <> '';

        ALTER TABLE customer_receivables
            ADD COLUMN IF NOT EXISTS receivable_no VARCHAR(80);
        UPDATE customer_receivables
        SET receivable_no = 'AR-LEGACY-' || id::text
        WHERE receivable_no IS NULL OR receivable_no = '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_receivables_receivable_no
            ON customer_receivables(receivable_no)
            WHERE receivable_no IS NOT NULL AND receivable_no <> '';

        INSERT INTO erp_code_rules
            (rule_key, target_type, prefix, date_format, sequence_length, separator, reset_scope, manual_allowed, is_active, remark)
        VALUES
            ('document:machine_service_cards.card_no', 'document', 'SC', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '设备服务档案编号规则'),
            ('document:machine_service_return_visits.visit_no', 'document', 'SV', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '服务回访单编号规则'),
            ('document:customer_receivables.receivable_no', 'document', 'AR', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '应收单编号规则')
        ON CONFLICT (rule_key) DO NOTHING;
        """,
    ),
    (
        "20260629_004_supplier_payable_document_number",
        """
        ALTER TABLE supplier_payables
            ADD COLUMN IF NOT EXISTS payable_no VARCHAR(80);
        UPDATE supplier_payables
        SET payable_no = 'AP-LEGACY-' || id::text
        WHERE payable_no IS NULL OR payable_no = '';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_supplier_payables_payable_no
            ON supplier_payables(payable_no)
            WHERE payable_no IS NOT NULL AND payable_no <> '';

        INSERT INTO erp_code_rules
            (rule_key, target_type, prefix, date_format, sequence_length, separator, reset_scope, manual_allowed, is_active, remark)
        VALUES
            ('document:supplier_payables.payable_no', 'document', 'AP', 'YYYYMMDD', 4, '', 'daily', TRUE, FALSE, '应付单编号规则')
        ON CONFLICT (rule_key) DO NOTHING;
        """,
    ),
    (
        "20260630_001_quality_inspection_code_rule_table",
        """
        UPDATE erp_code_rules
        SET rule_key='document:quality_inspection_records.inspection_no',
            updated_at=CURRENT_TIMESTAMP
        WHERE rule_key='document:quality_inspections.inspection_no'
          AND NOT EXISTS (
              SELECT 1
              FROM erp_code_rules existing
              WHERE existing.rule_key='document:quality_inspection_records.inspection_no'
          );

        UPDATE erp_code_rules
        SET is_active=FALSE,
            updated_at=CURRENT_TIMESTAMP
        WHERE rule_key='document:quality_inspections.inspection_no';
        """,
    ),
]


def ensure_schema_migrations(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(80) PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def apply_schema_migrations(cur, migrations=None):
    ensure_schema_migrations(cur)
    # 按版本名字典序执行，确保时间线一致（YYYYMMDD_NNN 前缀自然排序）
    sorted_migrations = sorted(migrations or MIGRATIONS, key=lambda m: m[0])
    applied = []
    for version, sql in sorted_migrations:
        cur.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (version,))
        if cur.fetchone():
            continue
        cur.execute(sql)
        cur.execute("INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT (version) DO NOTHING", (version,))
        applied.append(version)
    return applied
