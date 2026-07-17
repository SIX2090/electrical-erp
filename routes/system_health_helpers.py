"""System health helpers: data health queries, database/route health checks, and backup status."""
from datetime import datetime
from pathlib import Path

from flask import current_app

from routes.display_helpers import _format_timestamp


ROOT_DIR = Path(__file__).resolve().parents[1]
_query_db = None


def configure_system_health_helpers(query_db):
    global _query_db
    _query_db = query_db


def _backup_rows(limit=12):
    backup_dir = ROOT_DIR / "backups"
    if not backup_dir.exists():
        return []
    files = sorted((p for p in backup_dir.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "file_name": path.name,
            "size_mb": f"{path.stat().st_size / 1024 / 1024:.1f}",
            "modified_time": _format_timestamp(path.stat().st_mtime),
        }
        for path in files[:limit]
    ]


def _database_health_rows():
    try:
        row = _query_db(
            """
            SELECT current_database() AS database_name,
                   current_user AS user_name,
                   inet_server_addr()::text AS server_addr,
                   inet_server_port() AS server_port,
                   now() AS checked_at
            """,
            one=True,
        )
        return [
            {
                "id": 1,
                "check_name": "PostgreSQL 连接",
                "status": "正常",
                "database_name": row.get("database_name", "-"),
                "detail": f"{row.get('user_name', '-')}@{row.get('server_addr') or 'local'}:{row.get('server_port') or '-'}",
                "checked_at": row.get("checked_at"),
            }
        ]
    except Exception as exc:
        return [
            {
                "id": 1,
                "check_name": "PostgreSQL 连接",
                "status": "异常",
                "database_name": "-",
                "detail": str(exc)[:220],
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]


def _route_health_rows(route_checks):
    registered_paths = {rule.rule for rule in current_app.url_map.iter_rules()}
    return [
        {
            "id": idx + 1,
            "path": item["path"],
            "route_label": item["route_label"],
            "status": "已注册" if item["path"] in registered_paths else "缺失",
        }
        for idx, item in enumerate(route_checks)
    ]


def _legacy_recent_error_rows(limit=20):
    log_files = []
    for path in [ROOT_DIR / "flask_stderr.log", ROOT_DIR / "flask_stdout.log"]:
        if path.exists():
            log_files.append(path)
    log_dir = ROOT_DIR / "logs"
    if log_dir.exists():
        log_files.extend(path for path in log_dir.glob("*.log") if path.is_file())

    markers = ("error", "exception", "traceback", "failed", "fatal", "错误", "异常", "失败")
    rows = []
    for path in sorted(log_files, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines[-400:]:
            text = line.strip()
            if not text:
                continue
            if any(marker in text.lower() for marker in markers):
                rows.append(
                    {
                        "id": len(rows) + 1,
                        "file_name": path.name,
                        "modified_time": _format_timestamp(path.stat().st_mtime),
                        "message": text[:240],
                    }
                )
                if len(rows) >= limit:
                    return rows
    return rows


def _recent_error_rows(limit=20):
    log_files = []
    for path in [ROOT_DIR / "flask_stderr.log", ROOT_DIR / "flask_stdout.log"]:
        if path.exists():
            log_files.append(path)
    log_dir = ROOT_DIR / "logs"
    if log_dir.exists():
        log_files.extend(path for path in log_dir.glob("*.log") if path.is_file())

    markers = ("error", "exception", "failed", "fatal", "错误", "异常", "失败")
    skip_prefixes = ("Traceback", "File ", "return ", "cur.execute", "psycopg2.", "LINE ")

    def summarize_error(text):
        if " | " in text:
            parts = [part.strip() for part in text.split(" | ") if part.strip()]
            if len(parts) >= 3:
                error_kind = parts[2].split(":", 1)[0].strip().lower()
                if "undefinedcolumn" in error_kind:
                    error_label = "数据库字段缺失类错误"
                elif "syntaxerror" in error_kind:
                    error_label = "SQL 语法类错误"
                elif "programmingerror" in error_kind:
                    error_label = "数据库查询类错误"
                elif "operationalerror" in error_kind:
                    error_label = "数据库连接类错误"
                else:
                    error_label = "服务端错误"
                return f"{parts[0]} | {parts[1]} | {error_label}"
        lowered = text.lower()
        if "undefinedcolumn" in lowered:
            return "数据库字段缺失类错误，详情见服务器日志"
        if "syntaxerror" in lowered:
            return "SQL 语法类错误，详情见服务器日志"
        if "programmingerror" in lowered:
            return "数据库查询类错误，详情见服务器日志"
        if "operationalerror" in lowered:
            return "数据库连接类错误，详情见服务器日志"
        return text[:160]

    rows = []
    for path in sorted(log_files, key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines[-400:]:
            text = line.strip()
            if not text or text.startswith(skip_prefixes):
                continue
            if any(marker in text.lower() for marker in markers):
                rows.append(
                    {
                        "id": len(rows) + 1,
                        "file_name": path.name,
                        "modified_time": _format_timestamp(path.stat().st_mtime),
                        "message": summarize_error(text),
                    }
                )
                if len(rows) >= limit:
                    return rows
    return rows


def _backup_status():
    backup_dir = ROOT_DIR / "backups"
    db_files = sorted(backup_dir.glob("wms_*.dump"), key=lambda p: p.stat().st_mtime, reverse=True) if backup_dir.exists() else []
    source_files = sorted(backup_dir.glob("source_wms1_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True) if backup_dir.exists() else []
    return {
        "db_count": len(db_files),
        "source_count": len(source_files),
        "latest_db": db_files[0].name if db_files else "-",
        "latest_source": source_files[0].name if source_files else "-",
    }
