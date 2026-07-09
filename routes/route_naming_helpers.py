"""Route naming helpers: generate Flask endpoint names from URL paths."""
def endpoint(prefix, path):
    value = path.strip("/").replace("<", "").replace(">", "").replace(":", "_")
    value = value.replace("/", "_").replace("-", "_").replace(".", "_") or "root"
    if path.endswith("/") and path != "/":
        value += "_slash"
    return f"{prefix}_{value}"
