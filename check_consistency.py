"""Temporary consistency check script for route/permission/navigation audit."""
import re
import os
import sys

# ============================================================
# 1. Extract all route paths from route files
# ============================================================
def extract_routes_from_files():
    """Extract all @app.route and @bp.route paths from routes/*.py files."""
    route_pattern = re.compile(r'@(?:app|bp)\.route\(\s*["\']([^"\']+)["\']')
    routes = {}  # path -> list of (file, line)
    routes_dir = r'c:\erp\routes'
    for fname in os.listdir(routes_dir):
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(routes_dir, fname)
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            for i, line in enumerate(f, 1):
                m = route_pattern.search(line)
                if m:
                    path = m.group(1)
                    if fname not in routes:
                        routes[fname] = []
                    routes[fname].append((path, i))
    return routes

# ============================================================
# 2. Extract paths from pilot_permissions.py
# ============================================================
def extract_permission_paths():
    """Extract all paths registered in pilot_permissions.py."""
    paths = set()
    fpath = r'c:\erp\services\pilot_permissions.py'
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    # Find all quoted paths in the "paths" sets
    for m in re.finditer(r'"(/[a-zA-Z0-9_/<>\-\.\+]+)"', content):
        paths.add(m.group(1))
    return paths

# ============================================================
# 3. Extract paths from MENU_ROLLOUT_CLASSIFICATION.md
# ============================================================
def extract_menu_paths():
    """Extract all routes from MENU_ROLLOUT_CLASSIFICATION.md."""
    paths = set()
    fpath = r'c:\erp\MENU_ROLLOUT_CLASSIFICATION.md'
    with open(fpath, 'r', encoding='utf-8') as f:
        for line in f:
            # Match table rows like | `/path` | ...
            m = re.match(r'\|\s*`(/[^`]+)`\s*\|', line)
            if m:
                paths.add(m.group(1))
    return paths

# ============================================================
# 4. Extract paths from route_catalog.py
# ============================================================
def extract_catalog_paths():
    """Extract all paths from route_catalog.py DATA_ROUTES, WORKBENCH_ROUTES, REPORT_ROUTES, etc."""
    paths = set()
    fpath = r'c:\erp\routes\route_catalog.py'
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    # Find all quoted paths
    for m in re.finditer(r'"(/[^"]+)"', content):
        p = m.group(1)
        if p.startswith('/'):
            paths.add(p)
    return paths

# ============================================================
# 5. Extract url_for references from templates
# ============================================================
def extract_template_urlfors():
    """Extract endpoint references from templates."""
    refs = {}  # endpoint -> list of (file, line)
    templates_dir = r'c:\erp\templates'
    pattern = re.compile(r"url_for\(\s*['\"]([^'\"]+)['\"]")
    for root, dirs, files in os.walk(templates_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                for i, line in enumerate(f, 1):
                    for m in pattern.finditer(line):
                        ep = m.group(1)
                        if ep not in refs:
                            refs[ep] = []
                        refs[ep].append((os.path.relpath(fpath, templates_dir), i))
    return refs

# ============================================================
# 6. Extract endpoint names from route definitions
# ============================================================
def extract_endpoints():
    """Extract endpoint names from route definitions."""
    endpoints = {}  # endpoint_name -> (file, line, path)
    route_pattern = re.compile(r'@(?:app|bp)\.route\(\s*["\']([^"\']+)["\'].*?endpoint=["\']([^"\']+)["\']')
    routes_dir = r'c:\erp\routes'
    for fname in os.listdir(routes_dir):
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(routes_dir, fname)
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        for m in route_pattern.finditer(content):
            path = m.group(1)
            ep = m.group(2)
            endpoints[ep] = (fname, path)
    return endpoints

# ============================================================
# 7. Extract all registered Flask endpoints from app
# ============================================================
def extract_flask_endpoints():
    """Try to extract endpoint names from the app registration."""
    # We'll parse route registrations instead
    endpoints = set()
    route_pattern = re.compile(r'endpoint=["\']([^"\']+)["\']')
    routes_dir = r'c:\erp\routes'
    for fname in os.listdir(routes_dir):
        if not fname.endswith('.py'):
            continue
        fpath = os.path.join(routes_dir, fname)
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                for m in route_pattern.finditer(line):
                    endpoints.add(m.group(1))
    return endpoints


# ============================================================
# MAIN ANALYSIS
# ============================================================
def main():
    print("=" * 80)
    print("ERP Route/Permission/Navigation Consistency Check")
    print("=" * 80)

    route_files = extract_routes_from_files()
    perm_paths = extract_permission_paths()
    menu_paths = extract_menu_paths()
    catalog_paths = extract_catalog_paths()
    template_refs = extract_template_urlfors()
    flask_endpoints = extract_flask_endpoints()

    # Flatten all route paths from files
    all_route_paths = set()
    for fname, entries in route_files.items():
        for path, line in entries:
            # Normalize: remove trailing slashes except root
            p = path.rstrip('/') if path != '/' else path
            all_route_paths.add(p)

    # Normalize permission paths
    norm_perm = set()
    for p in perm_paths:
        norm_perm.add(p.rstrip('/') if p != '/' else p)

    # Normalize menu paths
    norm_menu = set()
    for p in menu_paths:
        # Remove parameter parts like <int:id>
        norm_menu.add(p.rstrip('/') if p != '/' else p)

    # Normalize catalog paths
    norm_catalog = set()
    for p in catalog_paths:
        norm_catalog.add(p.rstrip('/') if p != '/' else p)

    # ---- Check 1: Routes in files but NOT in permissions ----
    print("\n" + "=" * 80)
    print("CHECK 1: Routes in route files but NOT in pilot_permissions.py")
    print("=" * 80)
    # We need to compare base paths (without parameters)
    def normalize_path(p):
        """Remove parameter segments for comparison."""
        parts = p.split('/')
        result = []
        for part in parts:
            if part.startswith('<') and part.endswith('>'):
                continue
            result.append(part)
        return '/'.join(result) if '/'.join(result) else '/'

    route_base_paths = set()
    route_to_file = {}
    for fname, entries in route_files.items():
        for path, line in entries:
            base = normalize_path(path)
            if not base:
                base = '/'
            route_base_paths.add(base)
            if base not in route_to_file:
                route_to_file[base] = []
            route_to_file[base].append((fname, line, path))

    # Filter out API routes and static/internal paths
    skip_prefixes = ('/api/', '/static', '/_')
    missing_from_perm = []
    for base in sorted(route_base_paths):
        if any(base.startswith(p) for p in skip_prefixes):
            continue
        if base not in norm_perm:
            for fname, line, orig in route_to_file.get(base, []):
                missing_from_perm.append((base, orig, fname, line))

    if missing_from_perm:
        for base, orig, fname, line in missing_from_perm[:50]:
            print(f"  MISSING: {orig:55s} -> {fname}:{line}")
        if len(missing_from_perm) > 50:
            print(f"  ... and {len(missing_from_perm) - 50} more")
    else:
        print("  OK: All routes are registered in permissions")
    print(f"  Total: {len(missing_from_perm)} routes missing from permissions")

    # ---- Check 2: Routes in permissions but NOT in MENU_ROLLOUT_CLASSIFICATION.md ----
    print("\n" + "=" * 80)
    print("CHECK 2: Paths in permissions but NOT in MENU_ROLLOUT_CLASSIFICATION.md")
    print("=" * 80)
    missing_from_menu = []
    for p in sorted(norm_perm):
        if any(p.startswith(pr) for pr in skip_prefixes):
            continue
        if p not in norm_menu:
            missing_from_menu.append(p)

    if missing_from_menu:
        for p in missing_from_menu[:50]:
            print(f"  MISSING: {p}")
        if len(missing_from_menu) > 50:
            print(f"  ... and {len(missing_from_menu) - 50} more")
    else:
        print("  OK: All permission paths are in MENU_ROLLOUT_CLASSIFICATION.md")
    print(f"  Total: {len(missing_from_menu)} paths missing from menu classification")

    # ---- Check 3: Routes in files but NOT in route_catalog.py ----
    print("\n" + "=" * 80)
    print("CHECK 3: Routes in route files but NOT in route_catalog.py")
    print("=" * 80)
    missing_from_catalog = []
    for base in sorted(route_base_paths):
        if any(base.startswith(p) for p in skip_prefixes):
            continue
        if base not in norm_catalog:
            for fname, line, orig in route_to_file.get(base, []):
                missing_from_catalog.append((base, orig, fname, line))

    if missing_from_catalog:
        for base, orig, fname, line in missing_from_catalog[:50]:
            print(f"  MISSING: {orig:55s} -> {fname}:{line}")
        if len(missing_from_catalog) > 50:
            print(f"  ... and {len(missing_from_catalog) - 50} more")
    else:
        print("  OK: All routes are in route_catalog.py")
    print(f"  Total: {len(missing_from_catalog)} routes missing from catalog")

    # ---- Check 4: Template url_for references to non-existent endpoints ----
    print("\n" + "=" * 80)
    print("CHECK 4: Template url_for() references to endpoints")
    print("=" * 80)
    # Check which endpoints exist in flask
    missing_endpoints = []
    for ep, locations in sorted(template_refs.items()):
        if ep not in flask_endpoints:
            missing_endpoints.append((ep, locations))

    if missing_endpoints:
        for ep, locations in missing_endpoints[:30]:
            files_str = ', '.join(f"{f}:{l}" for f, l in locations[:3])
            print(f"  MISSING endpoint: {ep:40s} referenced in: {files_str}")
        if len(missing_endpoints) > 30:
            print(f"  ... and {len(missing_endpoints) - 30} more")
    else:
        print("  OK: All template url_for() endpoints exist")
    print(f"  Total: {len(missing_endpoints)} missing endpoints")

    # ---- Check 5: Document entry vs list separation ----
    print("\n" + "=" * 80)
    print("CHECK 5: Document entry/list separation (AGENTS.md rule)")
    print("=" * 80)
    # Check if /new routes exist alongside list routes
    doc_entry_patterns = []
    list_routes_with_new_in_menu = []

    # Check MENU_ROLLOUT_CLASSIFICATION.md for document list pages that have /new buttons
    menu_file = r'c:\erp\MENU_ROLLOUT_CLASSIFICATION.md'
    with open(menu_file, 'r', encoding='utf-8') as f:
        menu_content = f.read()

    # Check templates for "new" buttons on list pages
    templates_dir = r'c:\erp\templates'
    list_page_new_buttons = []
    for root, dirs, files in os.walk(templates_dir):
        for fname in files:
            if not fname.endswith('.html'):
                continue
            # Skip if it's a form/detail/new page itself
            if any(x in fname for x in ['_add', '_form', '_new', '_detail', '_edit', 'form.html']):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            # Check if this list page has a "new" button linking to a /new route
            if re.search(r'url_for.*?/new', content) or re.search(r'href=["\'].*?/new["\']', content):
                # Check if this is a list page (has table/list indicators)
                if 'table' in content.lower() or 'list' in fname.lower():
                    list_page_new_buttons.append(fname)

    if list_page_new_buttons:
        for f in list_page_new_buttons[:20]:
            print(f"  WARNING: List page may expose new button: {f}")
    else:
        print("  OK: No obvious new-button violations in list pages")

    # ---- Check 6: URL naming convention issues ----
    print("\n" + "=" * 80)
    print("CHECK 6: URL naming convention issues")
    print("=" * 80)
    # Check for inconsistent naming (snake_case vs kebab-case mixing)
    inconsistent_names = []
    for base in sorted(route_base_paths):
        if any(base.startswith(p) for p in skip_prefixes):
            continue
        parts = base.strip('/').split('/')
        for part in parts:
            if '_' in part and '-' in part:
                inconsistent_names.append((base, part))
                break

    if inconsistent_names:
        for base, part in inconsistent_names[:20]:
            print(f"  MIXED naming: {base:50s} segment '{part}' has both _ and -")
    else:
        print("  OK: No mixed naming conventions detected")

    # ---- Check 7: Duplicate route paths ----
    print("\n" + "=" * 80)
    print("CHECK 7: Duplicate route paths in route files")
    print("=" * 80)
    path_count = {}
    for fname, entries in route_files.items():
        for path, line in entries:
            if path not in path_count:
                path_count[path] = []
            path_count[path].append((fname, line))

    duplicates = {p: locs for p, locs in path_count.items() if len(locs) > 1}
    if duplicates:
        for path, locs in sorted(duplicates.items())[:20]:
            locs_str = ', '.join(f"{f}:{l}" for f, l in locs)
            print(f"  DUPLICATE: {path:50s} defined in: {locs_str}")
    else:
        print("  OK: No duplicate routes detected")

    # ---- Summary ----
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"  Total route definitions in files: {sum(len(v) for v in route_files.values())}")
    print(f"  Unique base paths in route files: {len(route_base_paths)}")
    print(f"  Paths in pilot_permissions.py:    {len(norm_perm)}")
    print(f"  Paths in MENU_ROLLOUT_CLASSIFICATION.md: {len(norm_menu)}")
    print(f"  Paths in route_catalog.py:        {len(norm_catalog)}")
    print(f"  Routes missing from permissions:  {len(missing_from_perm)}")
    print(f"  Paths missing from menu classification: {len(missing_from_menu)}")
    print(f"  Routes missing from catalog:      {len(missing_from_catalog)}")
    print(f"  Template endpoints not found:     {len(missing_endpoints)}")
    print(f"  Duplicate routes:                 {len(duplicates)}")


if __name__ == '__main__':
    main()
