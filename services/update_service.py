"""Offline update package inspection and release metadata reading."""
import json
import os
import re
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path


MANIFEST_NAMES = ("update_manifest.json", "manifest.json")


def project_root():
    """Return the absolute path of the project root directory."""
    return Path(__file__).resolve().parents[1]


def read_current_release(root_dir=None):
    """Read the current release metadata from package info files or environment."""
    root = Path(root_dir) if root_dir else project_root()
    info = {
        "version": os.environ.get("ERP_BUILD", "local"),
        "built_at": os.environ.get("ERP_BUILD", ""),
        "package_name": os.environ.get("ERP_PACKAGE_NAME", "local runtime"),
        "source": "environment",
    }
    info_path = os.environ.get("ERP_PACKAGE_INFO")
    paths = [Path(info_path)] if info_path else []
    paths.append(root / "PACKAGE_INFO.txt")
    for path in paths:
        if not path or not path.exists():
            continue
        try:
            lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError:
            continue
        if lines:
            info["package_name"] = lines[0]
        for line in lines:
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if key == "built_at":
                info["built_at"] = value
                info["version"] = value or info["version"]
            elif key == "package_name":
                info["package_name"] = value or info["package_name"]
        info["source"] = str(path)
        break
    return info


def _version_key(value):
    text = str(value or "").strip()
    if not text or text.lower() == "local":
        return (0,)
    date_value = _parse_datetime(text)
    if date_value:
        return (2, int(date_value.timestamp()))
    numbers = [int(part) for part in re.findall(r"\d+", text)]
    if numbers:
        return (1, *numbers)
    return (0, text)


def _parse_datetime(value):
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%d_%H%M%S", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def _safe_relative_path(value):
    text = str(value or "").replace("\\", "/").strip().lstrip("/")
    if not text or ".." in Path(text).parts:
        return ""
    return text


def _normalise_manifest(raw, package_path, is_zip=False):
    version = str(raw.get("version") or raw.get("built_at") or raw.get("build") or "").strip()
    built_at = str(raw.get("built_at") or "").strip()
    script = _safe_relative_path(raw.get("entry_script") or raw.get("install_script") or raw.get("script") or "")
    return {
        "id": package_path.name,
        "version": version,
        "built_at": built_at,
        "package_name": str(raw.get("package_name") or package_path.name).strip(),
        "notes": str(raw.get("notes") or raw.get("description") or "").strip(),
        "entry_script": script,
        "path": str(package_path),
        "relative_path": str(package_path.relative_to(project_root())) if package_path.is_relative_to(project_root()) else str(package_path),
        "is_zip": is_zip,
        "installable": bool(script and not is_zip),
        "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _read_json_bytes(data):
    return json.loads(data.decode("utf-8-sig"))


def _load_manifest_from_dir(path):
    for name in MANIFEST_NAMES:
        manifest_path = path / name
        if manifest_path.exists():
            try:
                return json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                return None
    return None


def _load_manifest_from_zip(path):
    try:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if Path(name).name in MANIFEST_NAMES:
                    return _read_json_bytes(archive.read(name))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
        return None
    return None


def find_update_packages(root_dir=None):
    root = Path(root_dir) if root_dir else project_root()
    updates_dir = root / "updates"
    if not updates_dir.exists():
        return []
    packages = []
    for path in sorted(updates_dir.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        manifest = None
        is_zip = False
        if path.is_dir():
            manifest = _load_manifest_from_dir(path)
        elif path.is_file() and path.suffix.lower() == ".zip":
            manifest = _load_manifest_from_zip(path)
            is_zip = True
        if not manifest:
            continue
        packages.append(_normalise_manifest(manifest, path, is_zip=is_zip))
    return packages


def get_update_status(root_dir=None):
    root = Path(root_dir) if root_dir else project_root()
    current = read_current_release(root)
    packages = find_update_packages(root)
    current_key = _version_key(current.get("version") or current.get("built_at"))
    for package in packages:
        package["is_newer"] = _version_key(package.get("version") or package.get("built_at")) > current_key
    latest = next((package for package in packages if package["is_newer"]), None)
    return {
        "current": current,
        "packages": packages,
        "latest": latest,
        "has_update": bool(latest),
        "updates_dir": str(root / "updates"),
    }


def launch_update(package_id, root_dir=None):
    root = Path(root_dir) if root_dir else project_root()
    status = get_update_status(root)
    package = next((item for item in status["packages"] if item["id"] == package_id), None)
    if not package:
        raise ValueError("未找到更新包")
    if not package.get("installable"):
        raise ValueError("该更新包未声明可执行安装脚本")
    package_path = Path(package["path"]).resolve()
    updates_dir = (root / "updates").resolve()
    if not package_path.is_relative_to(updates_dir):
        raise ValueError("更新包路径不在 updates 目录内")
    script_path = (package_path / package["entry_script"]).resolve()
    if not script_path.is_file() or not script_path.is_relative_to(package_path):
        raise ValueError("安装脚本不存在或路径非法")

    logs_dir = root / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_path = logs_dir / f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_handle = log_path.open("a", encoding="utf-8")

    suffix = script_path.suffix.lower()
    if suffix == ".ps1":
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
    elif suffix in {".bat", ".cmd"}:
        command = ["cmd", "/c", str(script_path)]
    else:
        command = [str(script_path)]

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags |= subprocess.CREATE_NO_WINDOW
    try:
        process = subprocess.Popen(
            command,
            cwd=str(package_path),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    finally:
        log_handle.close()
    return {"pid": process.pid, "log_path": str(log_path), "package": package}
