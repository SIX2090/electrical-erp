"""Document attachment helpers: table creation and attachment CRUD utilities."""
def ensure_document_attachment_table(execute_db):
    execute_db(
        """
        CREATE TABLE IF NOT EXISTS document_attachments (
            id SERIAL PRIMARY KEY,
            subject_type VARCHAR(64) NOT NULL,
            subject_id INTEGER NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            stored_path VARCHAR(500) NOT NULL,
            content_type VARCHAR(120),
            file_size INTEGER,
            attachment_type VARCHAR(40),
            remark TEXT,
            uploaded_by INTEGER,
            uploaded_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
        )
        """
    )


def fetch_material_attachments(product_id, ensure_attachment_table, query_rows):
    ensure_attachment_table()
    return query_rows(
        """
        SELECT *
        FROM document_attachments
        WHERE subject_type='product' AND subject_id=%s
        ORDER BY uploaded_at DESC, id DESC
        """,
        (product_id,),
    )


def fetch_document_attachments(
    kind,
    subject_id,
    document_subject,
    ensure_attachment_table,
    query_rows,
):
    config = document_subject(kind)
    if not config:
        return []
    ensure_attachment_table()
    return query_rows(
        """
        SELECT *
        FROM document_attachments
        WHERE subject_type=%s AND subject_id=%s
        ORDER BY uploaded_at DESC, id DESC
        """,
        (config["subject_type"], subject_id),
    )


def fetch_document_activity_logs(kind, document, document_subject, query_rows):
    config = document_subject(kind)
    if not config or not document:
        return []
    targets = [str(document.get("id") or "")]
    doc_no = document.get(config["doc_no_field"])
    if doc_no:
        targets.append(str(doc_no))
    return query_rows(
        """
        SELECT id, username, action, target, remark, created_at
        FROM operation_logs
        WHERE action LIKE %s AND target = ANY(%s)
        ORDER BY created_at DESC, id DESC
        LIMIT 50
        """,
        (f"%{config['label']}%", targets),
    )
