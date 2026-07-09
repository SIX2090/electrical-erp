"""Environment-based configuration for database credentials, secret keys, and login security."""
import os


DEFAULT_PG_PASSWORDS = {"", "admin"}
DEFAULT_SECRET_KEYS = {"", "local-installed-secret-change-before-production", "wms-local-5625-10855-10145", "audit-secret", "test-secret"}


def _int_env(name, default):
    value = os.environ.get(name)
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def is_production_env():
    """Return True when the application is configured for production deployment."""
    return os.environ.get("INVENTORY_ENV", os.environ.get("FLASK_ENV", "")).strip().lower() == "production"


def is_local_trial_env():
    """Return True when running in local trial, development, or test mode."""
    env = os.environ.get("INVENTORY_ENV", os.environ.get("FLASK_ENV", "")).strip().lower()
    return env in {"", "local", "local_trial", "development", "dev", "test"}


def get_pg_password():
    """Return the PostgreSQL password from env, enforcing non-default in production."""
    password = os.environ.get("PG_PASSWORD", "")
    if is_production_env() and password in DEFAULT_PG_PASSWORDS:
        raise RuntimeError("PG_PASSWORD must be set to a non-default value in production.")
    return password


def get_inventory_secret_key():
    """Return the Flask secret key from env, enforcing strength in production."""
    secret = os.environ.get("INVENTORY_SECRET_KEY", "")
    if is_production_env() and (secret in DEFAULT_SECRET_KEYS or len(secret) < 32):
        raise RuntimeError("INVENTORY_SECRET_KEY must be set to a strong non-default value in production.")
    return secret


def security_config_status():
    """Return a dict summarizing database password, secret key, and go-live readiness."""
    pg_password = os.environ.get("PG_PASSWORD", "")
    secret = os.environ.get("INVENTORY_SECRET_KEY", "")
    env_name = os.environ.get("INVENTORY_ENV", os.environ.get("FLASK_ENV", "")).strip() or "local_trial"
    local_bootstrapped = os.environ.get("INVENTORY_LOCAL_SECURITY_BOOTSTRAPPED", "") == "1"
    pg_ready = bool(pg_password) and pg_password not in DEFAULT_PG_PASSWORDS
    secret_ready = bool(secret) and secret not in DEFAULT_SECRET_KEYS and len(secret) >= 32
    go_live_ready = is_production_env() and pg_ready and secret_ready
    return {
        "environment": env_name,
        "local_bootstrapped": local_bootstrapped,
        "pg_password_ready": pg_ready,
        "secret_key_ready": secret_ready,
        "go_live_ready": go_live_ready,
        "mode_label": "正式上线" if is_production_env() else "本地试用",
    }


def get_login_max_failures():
    """Return the maximum allowed login failures before lockout (default 5)."""
    return _int_env("LOGIN_MAX_FAILURES", 5)


def get_login_lockout_seconds():
    """Return the lockout duration in seconds after max failures (default 900)."""
    return _int_env("LOGIN_LOCKOUT_SECONDS", 900)


def get_login_rate_limit():
    """Return the rate limit for login attempts per window (default 20)."""
    return _int_env("LOGIN_RATE_LIMIT", 20)


def get_login_rate_limit_window_seconds():
    """Return the rate limit window length in seconds (default 60)."""
    return _int_env("LOGIN_RATE_LIMIT_WINDOW_SECONDS", 60)
