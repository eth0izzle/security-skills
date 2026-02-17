"""
Query existing CrowdStrike Fusion workflow definitions.

Search by name, check for duplicates before importing, or list all workflows
with optional filtering. This script should be run BEFORE importing to avoid
creating duplicate workflow definitions.

Usage:
    python query_workflows.py --list                          # List all workflows
    python query_workflows.py --search "contain"              # Search by name substring
    python query_workflows.py --search "contain" --json       # Machine-readable
    python query_workflows.py --check-name "My Workflow"      # Exit 0 if exists, 1 if not
    python query_workflows.py --check-yaml workflow.yaml      # Extract name from YAML, check if exists
    python query_workflows.py --check-yaml *.yaml             # Check multiple files
"""

import argparse
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import load_env, api_get

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFINITIONS_COMBINED = "/workflows/combined/definitions/v1"


def fetch_all_definitions():
    """Fetch all workflow definitions with pagination."""
    load_env()
    all_defs = []
    offset = 0
    limit = 100
    while True:
        resp = api_get(DEFINITIONS_COMBINED, params={"limit": limit, "offset": offset})
        resources = resp.get("resources", [])
        if not resources:
            break
        all_defs.extend(resources)
        meta = resp.get("meta", {}).get("pagination", {})
        total = meta.get("total", 0)
        offset += len(resources)
        if offset >= total:
            break
    return all_defs


def search_definitions(term):
    """Fetch all definitions and filter by name substring (case-insensitive)."""
    defs = fetch_all_definitions()
    term_lower = term.lower()
    return [d for d in defs if term_lower in d.get("name", "").lower()]


def find_by_exact_name(name):
    """Find workflows with an exact name match (case-insensitive)."""
    defs = fetch_all_definitions()
    name_lower = name.lower()
    return [d for d in defs if d.get("name", "").lower() == name_lower]


def extract_name_from_yaml(file_path):
    """Extract the workflow name from a YAML file without requiring PyYAML."""
    if not os.path.isfile(file_path):
        print(f"  File not found: {file_path}", file=sys.stderr)
        return None

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            # Match top-level name: key (not indented)
            match = re.match(r"^name:\s*['\"]?(.+?)['\"]?\s*$", line)
            if match:
                return match.group(1)
    return None


def format_definition(d):
    """Format a definition for human display."""
    did = d.get("id", "?")
    name = d.get("name", "?")
    enabled = d.get("enabled", False)
    trigger_type = d.get("trigger", {}).get("type", "?")
    status = "enabled" if enabled else "disabled"
    last_modified = d.get("last_modified_timestamp", "?")
    return (
        f"  {name}\n"
        f"    ID       : {did}\n"
        f"    Trigger  : {trigger_type}\n"
        f"    Status   : {status}\n"
        f"    Modified : {last_modified}"
    )


def format_json(defs):
    """Format definitions as machine-readable JSON."""
    out = []
    for d in defs:
        out.append({
            "id": d.get("id", ""),
            "name": d.get("name", ""),
            "enabled": d.get("enabled", False),
            "trigger_type": d.get("trigger", {}).get("type", ""),
            "last_modified": d.get("last_modified_timestamp", ""),
        })
    return json.dumps(out, indent=2)


def main():
    parser = argparse.ArgumentParser(
        description="Query existing Fusion workflow definitions"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--list", "-l", action="store_true",
        help="List all workflow definitions"
    )
    group.add_argument(
        "--search", "-s", metavar="TERM",
        help="Search workflows by name (substring match)"
    )
    group.add_argument(
        "--check-name", metavar="NAME",
        help="Check if a workflow with this exact name exists"
    )
    group.add_argument(
        "--check-yaml", nargs="+", metavar="FILE",
        help="Extract name from YAML file(s) and check for duplicates"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Machine-readable JSON output"
    )
    args = parser.parse_args()

    if args.list:
        defs = fetch_all_definitions()
        if args.json:
            print(format_json(defs))
        else:
            print(f"\nWorkflow definitions ({len(defs)}):\n")
            for d in defs:
                print(format_definition(d))
                print()

    elif args.search:
        results = search_definitions(args.search)
        if args.json:
            print(format_json(results))
        else:
            print(f"\nSearch results for '{args.search}' ({len(results)} found):\n")
            if results:
                for d in results:
                    print(format_definition(d))
                    print()
            else:
                print("  No workflows found matching that search term.\n")

    elif args.check_name:
        matches = find_by_exact_name(args.check_name)
        if args.json:
            print(json.dumps({
                "name": args.check_name,
                "exists": len(matches) > 0,
                "count": len(matches),
                "matches": [{"id": d.get("id", ""), "name": d.get("name", "")} for d in matches],
            }, indent=2))
        else:
            if matches:
                print(f"\n  DUPLICATE FOUND: '{args.check_name}' already exists ({len(matches)} match(es)):\n")
                for d in matches:
                    print(f"    ID: {d.get('id', '?')}  Name: {d.get('name', '?')}")
                print()
            else:
                print(f"\n  OK: No existing workflow named '{args.check_name}'\n")
        # Exit 0 if exists (duplicate found), 1 if not found
        sys.exit(0 if matches else 1)

    elif args.check_yaml:
        # Fetch all definitions once for all file checks
        all_defs = fetch_all_definitions()
        all_names = {d.get("name", "").lower(): d for d in all_defs}

        duplicates = []
        clean = []

        for fp in args.check_yaml:
            basename = os.path.basename(fp)
            name = extract_name_from_yaml(fp)
            if name is None:
                print(f"  {basename}: Could not extract workflow name", file=sys.stderr)
                continue

            name_lower = name.lower()
            if name_lower in all_names:
                existing = all_names[name_lower]
                duplicates.append((basename, name, existing.get("id", "?")))
            else:
                clean.append((basename, name))

        if args.json:
            print(json.dumps({
                "duplicates": [
                    {"file": f, "name": n, "existing_id": eid}
                    for f, n, eid in duplicates
                ],
                "clean": [
                    {"file": f, "name": n}
                    for f, n in clean
                ],
            }, indent=2))
        else:
            if duplicates:
                print(f"\n  DUPLICATES FOUND ({len(duplicates)}):\n")
                for basename, name, eid in duplicates:
                    print(f"    {basename}")
                    print(f"      Name       : {name}")
                    print(f"      Existing ID: {eid}")
                    print()
            if clean:
                print(f"  No duplicates ({len(clean)}):\n")
                for basename, name in clean:
                    print(f"    {basename} — '{name}'")
                print()

        if duplicates:
            sys.exit(0)  # Duplicates found
        else:
            sys.exit(1)  # No duplicates — safe to import


if __name__ == "__main__":
    main()
