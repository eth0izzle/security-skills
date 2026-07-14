"""
Search and inspect CrowdStrike Fusion workflow actions via the live API.

Usage:
    python action_search.py --search "contain"        # Search by name
    python action_search.py --details <action_id>     # Full schema for one action
    python action_search.py --list --limit 50         # Browse paginated
    python action_search.py --vendors                 # List all vendors/integrations
    python action_search.py --vendor "Okta" --list    # Filter to a specific vendor
    python action_search.py --use-case "Identity"     # Filter by use case
    python action_search.py --search "contain" --json # Machine-readable output
    python action_search.py --clear-cache             # Clear the local action cache
"""

import argparse
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import get_client

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Cache settings — full catalog is cached locally to avoid repeated full scans.
# The cache is only used for operations that must scan all actions (--vendors,
# --use-case).  Targeted searches use server-side FQL filtering and skip the cache.
_CACHE_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILE = os.path.join(_CACHE_DIR, ".action_cache.json")
_CACHE_TTL = 3600  # 1 hour


# ── Server-side FQL filtering ──────────────────────────────────────────────
# The Combined Activities endpoint supports FQL `filter` with these fields:
#   name:'keyword'          — substring match on action name
#   vendor:'VendorName'     — exact vendor match
# Combined with `+`:  vendor:'CrowdStrike'+name:'email'


def _usable_body(resp):
    """Return the response body if it carries usable resources, else None.

    The search_activities API returns a top-level 404 when the result set
    includes an action whose backing artifact is missing (an orphaned catalog
    entry), even though it still returns every action it could resolve. Keying
    success off the aggregate status_code therefore throws away valid data and
    makes common searches (email, query event, LLM) look like connection
    failures. Treat any response that carries resources as usable, regardless of
    the aggregate status; only a non-200 with no resources is a real failure.
    """
    body = resp.get("body") or {}
    if resp.get("status_code") == 200:
        return body
    if body.get("resources"):
        return body  # partial failure (e.g. orphaned artifact) — data still usable
    return None


def _fql_search(query, vendor_filter=None, limit=200):
    """Search actions using server-side FQL filter.  Returns (results, total).

    Falls back to None on FQL error so the caller can retry client-side.
    """
    parts = []
    if vendor_filter:
        parts.append(f"vendor:'{vendor_filter}'")
    if query:
        parts.append(f"name:'{query}'")
    fql = "+".join(parts)

    client = get_client()
    results = []
    offset = 0
    total = None
    while True:
        try:
            resp = client.search_activities(filter=fql, limit=limit, offset=offset)
            body = _usable_body(resp)
            if body is None:
                return None
        except (ConnectionError, RuntimeError, OSError):
            return None  # FQL not supported / transient error — caller retries
        resources = body.get("resources", [])
        if not resources:
            break
        if total is None:
            total = body.get("meta", {}).get("pagination", {}).get("total", 0)
        results.extend(resources)
        offset += len(resources)
        if offset >= total:
            break
    return results


def _fql_vendor(vendor, limit=200):
    """Return all actions for a vendor using server-side FQL filter."""
    return _fql_search(query=None, vendor_filter=vendor, limit=limit)


# ── Local cache for full-catalog operations ────────────────────────────────


def _load_cache():
    """Load cached catalog if fresh, else return None."""
    if not os.path.isfile(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("ts", 0) < _CACHE_TTL:
            return data["resources"]
    except (json.JSONDecodeError, KeyError, OSError):
        pass
    return None


def _save_cache(resources):
    """Persist catalog to local cache file."""
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "resources": resources}, f)
    except OSError:
        pass  # non-fatal — next run will just re-fetch


def _clear_cache():
    """Delete the local cache file."""
    try:
        os.remove(_CACHE_FILE)
        return True
    except FileNotFoundError:
        return False


def _fetch_page_with_retry(client, offset, max_retries=3, progress=False):
    """Fetch a single page of activities with retry logic. Returns body dict or None."""
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.search_activities(limit=200, offset=offset)
            body = _usable_body(resp)
            if body is None:
                raise RuntimeError(f"API returned {resp['status_code']} with no resources")
            return body
        except (ConnectionError, RuntimeError, OSError):
            if attempt < max_retries:
                if progress:
                    print(f"\n  Connection error, retrying ({attempt}/{max_retries})...", flush=True)
                time.sleep(2 * attempt)
            else:
                if progress:
                    print(f"\n  Failed after {max_retries} retries at offset {offset}.")
                return None
    return None


def _paginate_all(progress=False):
    """Return the full action catalog, using cache when available."""
    cached = _load_cache()
    if cached is not None:
        if progress:
            print(f"  Using cached catalog ({len(cached)} actions, < 1 hr old)")
        return cached

    client = get_client()
    resources = []
    offset = 0
    total = None
    while True:
        body = _fetch_page_with_retry(client, offset, progress=progress)
        if body is None:
            if resources:
                _save_cache(resources)
            return resources
        page = body.get("resources", [])
        if not page:
            break
        if total is None:
            total = body.get("meta", {}).get("pagination", {}).get("total", 0)
        resources.extend(page)
        offset += len(page)
        if progress and total:
            print(f"\r  Scanning actions... ({min(offset, total)}/{total})", end="", flush=True)
        if offset >= total:
            break
    if progress:
        print()

    _save_cache(resources)
    return resources


# ── Search / filter helpers ────────────────────────────────────────────────


def list_vendors():
    """Aggregate all actions by vendor. Returns {vendor: {count, use_cases, has_permission}}."""
    vendors = {}
    for r in _paginate_all(progress=True):
        v = r.get("vendor", "Unknown")
        if v not in vendors:
            vendors[v] = {"count": 0, "use_cases": set(), "has_permission": True}
        vendors[v]["count"] += 1
        for uc in r.get("use_cases", []):
            vendors[v]["use_cases"].add(uc)
        if not r.get("has_permission", True):
            vendors[v]["has_permission"] = False
    return vendors


def _client_side_search(query, vendor_filter=None):
    """Scan the cached catalog for actions matching *query* (substring, case-insensitive)."""
    all_actions = _paginate_all(progress=True)
    out = []
    ql = query.lower()
    for r in all_actions:
        if vendor_filter and r.get("vendor", "").lower() != vendor_filter.lower():
            continue
        if ql in r.get("name", "").lower():
            out.append(r)
    return out


def search_actions(query, vendor_filter=None):
    """Search activities by name.  Uses FQL server-side filter first, then
    falls back to a smart client-side filter.

    FQL handles single-word queries well but returns 0 for multi-word
    substrings (e.g. "detection details").  For multi-word queries we:
      1. FQL-search the longest single word (returns a small result set fast)
      2. Client-side filter that small set for the full multi-word query
    This avoids the slow full-catalog scan entirely.
    """
    # Fast path — server-side FQL with the full query
    results = _fql_search(query, vendor_filter=vendor_filter)
    if results is not None and len(results) > 0:
        return results

    # FQL returned 0 or failed.  For multi-word queries, narrow via the
    # longest single word, then filter client-side on that small set.
    words = query.split()
    if len(words) > 1:
        longest = max(words, key=len)
        fql_results = _fql_search(longest, vendor_filter=vendor_filter)
        if fql_results is not None and len(fql_results) > 0:
            ql = query.lower()
            return [r for r in fql_results if ql in r.get("name", "").lower()]

    # Last resort — full catalog scan (single-word query that FQL missed,
    # or FQL error).  Uses cache if available.
    return _client_side_search(query, vendor_filter=vendor_filter)


def search_by_vendor(vendor):
    """Return all actions for a specific vendor."""
    # Fast path — server-side FQL
    results = _fql_vendor(vendor)
    if results is not None:
        return results

    # Fallback — client-side scan
    return [r for r in _paginate_all(progress=True)
            if r.get("vendor", "").lower() == vendor.lower()]


def search_by_use_case(use_case):
    """Return all actions matching a use case substring (client-side, uses cache)."""
    ucl = use_case.lower()
    results = []
    for r in _paginate_all(progress=True):
        for uc in r.get("use_cases", []):
            if ucl in uc.lower():
                results.append(r)
                break
    return results


def list_actions(limit=25, offset=0, vendor_filter=None):
    """List activities with pagination."""
    if vendor_filter:
        all_for_vendor = search_by_vendor(vendor_filter)
        page = all_for_vendor[offset:offset + limit]
        return page, len(all_for_vendor)
    client = get_client()
    resp = client.search_activities(limit=limit, offset=offset)
    body = _usable_body(resp) or {}
    resources = body.get("resources", [])
    total = body.get("meta", {}).get("pagination", {}).get("total", 0)
    return resources, total


def get_action_details(action_id):
    """Get full details for a specific action by ID."""
    client = get_client()
    resp = client.search_activities(filter=f"id:'{action_id}'")
    body = _usable_body(resp) or {}
    resources = body.get("resources", [])
    return resources[0] if resources else None


# ── Formatting ─────────────────────────────────────────────────────────────


def format_action_summary(action):
    """Format an action for human display."""
    aid = action.get("id", "?")
    name = action.get("name", "?")
    desc = action.get("description", "")
    category = action.get("category", "")
    vendor = action.get("vendor", "")
    vendor_tag = f" [{vendor}]" if vendor and vendor != "CrowdStrike" else ""
    lines = [f"  {name}{vendor_tag}"]
    lines.append(f"    ID       : {aid}")
    if category:
        lines.append(f"    Category : {category}")
    if desc:
        lines.append(f"    Desc     : {desc[:120]}")
    return "\n".join(lines)


def format_action_details(action):
    """Format full action details including input fields."""
    lines = []
    lines.append(f"  Name        : {action.get('name', '?')}")
    lines.append(f"  ID          : {action.get('id', '?')}")
    lines.append(f"  Category    : {action.get('category', '')}")
    lines.append(f"  Description : {action.get('description', '')}")

    vendor = action.get("vendor", "")
    ns = action.get("namespace", "")
    use_cases = action.get("use_cases", [])
    has_perm = action.get("has_permission", True)
    is_plugin = "plugin" in ns or vendor not in ("CrowdStrike", "Unknown", "")

    lines.append(f"  Vendor      : {vendor}")
    if use_cases:
        lines.append(f"  Use cases   : {', '.join(use_cases)}")
    if ns:
        lines.append(f"  Namespace   : {ns}")
    if not has_perm:
        lines.append("  Permission  : NOT AVAILABLE (install app from CrowdStrike Store)")
    if is_plugin:
        lines.append("  Plugin      : Yes \u2014 requires config_id in workflow YAML")

    # Show input fields / properties schema
    props = action.get("properties", {})
    if props:
        lines.append(f"\n  Input fields ({len(props)}):")
        for pname, pschema in props.items():
            ptype = pschema.get("type", "?")
            pdesc = pschema.get("description", "")
            required = pschema.get("required", False)
            req_mark = " (required)" if required else ""
            lines.append(f"    {pname} [{ptype}]{req_mark}")
            if pdesc:
                lines.append(f"      {pdesc[:120]}")

    # Show if class/version_constraint needed
    cls = action.get("class", "")
    if cls:
        lines.append(f"\n  Class              : {cls}")
        lines.append("  version_constraint : ~1  (typically required for class-based actions)")

    return "\n".join(lines)


def format_vendors_table(vendors):
    """Format the vendors listing as a table."""
    total_actions = sum(v["count"] for v in vendors.values())
    total_vendors = len(vendors)
    lines = []
    lines.append(f"\nAvailable integrations ({total_vendors} vendors, {total_actions} actions):\n")
    lines.append(f"  {'Vendor':<35} {'Actions':>7}  Use Cases")
    lines.append(f"  {'\u2500' * 75}")

    # Sort by action count descending
    for name, info in sorted(vendors.items(), key=lambda x: x[1]["count"], reverse=True):
        use_cases_str = ", ".join(sorted(info["use_cases"])) if info["use_cases"] else ""
        perm_flag = "" if info["has_permission"] else " *"
        lines.append(f"  {name:<35} {info['count']:>7}  {use_cases_str}{perm_flag}")

    lines.append("")
    lines.append('Use --vendor "NAME" to see all actions for a specific vendor.')
    lines.append("* = not all actions available (app may need installation)")
    return "\n".join(lines)


# ── CLI handlers ──────────────────────────────────────────────────────────


def _print_results(results, label, as_json=False):
    """Print a list of action results in summary or JSON format."""
    if as_json:
        print(json.dumps(results, indent=2))
    elif not results:
        print(f"No actions matching {label}.")
    else:
        print(f"\nFound {len(results)} action(s) matching {label}:\n")
        for r in results:
            print(format_action_summary(r))
            print()


def _print_paginated(items, total, offset, as_json=False):
    """Print a paginated list of actions."""
    if as_json:
        print(json.dumps({"resources": items, "total": total}, indent=2))
    else:
        print(f"\nActions (showing {len(items)} of {total}):\n")
        for a in items:
            print(format_action_summary(a))
            print()
        if offset + len(items) < total:
            print(f"  ... use --offset {offset + len(items)} to see more")


def _handle_vendors(args):
    """Handle --vendors command."""
    vendors = list_vendors()
    if args.use_case:
        vendors = {
            name: info for name, info in vendors.items()
            if any(args.use_case.lower() in uc.lower() for uc in info["use_cases"])
        }
    if args.json:
        out = {k: {"count": v["count"], "use_cases": sorted(v["use_cases"]),
                    "has_permission": v["has_permission"]} for k, v in vendors.items()}
        print(json.dumps(out, indent=2))
    else:
        print(format_vendors_table(vendors))


def _handle_search(args):
    """Handle --search command."""
    results = search_actions(args.search, vendor_filter=args.vendor)
    if args.use_case:
        results = [r for r in results if any(
            args.use_case.lower() in uc.lower() for uc in r.get("use_cases", [])
        )]
    _print_results(results, f"'{args.search}'", as_json=args.json)


def _handle_details(args):
    """Handle --details command."""
    action = get_action_details(args.details)
    if args.json:
        print(json.dumps(action, indent=2))
    elif not action:
        print(f"Action '{args.details}' not found.")
        sys.exit(1)
    else:
        print("\nAction details:\n")
        print(format_action_details(action))
        print()


def _handle_list(args):
    """Handle --list command."""
    if args.use_case:
        results = search_by_use_case(args.use_case)
        if args.vendor:
            results = [r for r in results if r.get("vendor", "").lower() == args.vendor.lower()]
        page = results[args.offset:args.offset + args.limit]
        _print_paginated(page, len(results), args.offset, as_json=args.json)
    else:
        actions, total = list_actions(limit=args.limit, offset=args.offset,
                                      vendor_filter=args.vendor)
        _print_paginated(actions, total, args.offset, as_json=args.json)


def _handle_use_case(args):
    """Handle --use-case (standalone) command."""
    results = search_by_use_case(args.use_case)
    if args.vendor:
        results = [r for r in results if r.get("vendor", "").lower() == args.vendor.lower()]
    _print_results(results, f"use case '{args.use_case}'", as_json=args.json)


def _handle_vendor(args):
    """Handle --vendor (standalone) command."""
    results = search_by_vendor(args.vendor)
    _print_results(results, f"vendor '{args.vendor}'", as_json=args.json)


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    """CLI entry point for action search."""
    parser = argparse.ArgumentParser(description="Search CrowdStrike Fusion actions")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--search", "-s", metavar="QUERY", help="Search actions by name")
    group.add_argument("--details", "-d", metavar="ID", help="Show full details for an action ID")
    group.add_argument("--list", "-l", action="store_true", help="List actions (paginated)")
    group.add_argument("--vendors", action="store_true", help="List all available vendors/integrations")
    group.add_argument("--clear-cache", action="store_true", help="Clear the local action cache")
    parser.add_argument("--vendor", metavar="NAME", help="Filter to a specific vendor")
    parser.add_argument("--use-case", metavar="TERM", help="Filter by use case")
    parser.add_argument("--limit", type=int, default=25, help="Results per page (default: 25)")
    parser.add_argument("--offset", type=int, default=0, help="Pagination offset")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args()

    if not any([args.search, args.details, args.list, args.vendors, args.vendor,
                args.use_case, args.clear_cache]):
        parser.error("one of --search, --details, --list, --vendors, --vendor, "
                     "--use-case, or --clear-cache is required")

    if args.clear_cache:
        print("Cache cleared." if _clear_cache() else "No cache file found.")
    elif args.vendors:
        _handle_vendors(args)
    elif args.use_case and not args.search and not args.list:
        _handle_use_case(args)
    elif args.vendor and not args.search and not args.list:
        _handle_vendor(args)
    elif args.search:
        _handle_search(args)
    elif args.details:
        _handle_details(args)
    elif args.list:
        _handle_list(args)


if __name__ == "__main__":
    main()
