"""
Export CrowdStrike Fusion workflow definitions as YAML or list all definitions.

Usage:
    python export.py --id <wf_id>                      # Print YAML to stdout
    python export.py --id <wf_id> --output file.yaml   # Save to file
    python export.py --list                             # List all definitions
    python export.py --list --json                      # Machine-readable
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import load_env, api_get

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXPORT_ENDPOINT = "/workflows/entities/definitions/export/v1"
DEFINITIONS_COMBINED = "/workflows/combined/definitions/v1"


def export_workflow(workflow_id):
    """
    Export a workflow as YAML. Returns the raw YAML string.
    Note: the export endpoint returns YAML directly, not JSON.
    """
    import requests as req_lib

    load_env()
    from cs_auth import _base_url, _headers

    url = f"{_base_url()}{EXPORT_ENDPOINT}"
    resp = req_lib.get(url, headers=_headers(), params={"id": workflow_id})
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "")
    if "yaml" in content_type or "text" in content_type:
        return resp.text
    # If JSON response, it might contain errors
    try:
        body = resp.json()
        errors = body.get("errors", [])
        if errors:
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            print(f"  Export error: {msg}", file=sys.stderr)
            sys.exit(1)
    except Exception:
        pass
    return resp.text


def list_definitions(limit=100, offset=0):
    """List all workflow definitions."""
    all_defs = []
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


def format_definition(d):
    """Format a definition for human display."""
    did = d.get("id", "?")
    name = d.get("name", "?")
    enabled = d.get("enabled", False)
    trigger_type = d.get("trigger", {}).get("type", "?")
    status = "enabled" if enabled else "disabled"
    return f"  {name}\n    ID      : {did}\n    Trigger : {trigger_type}\n    Status  : {status}"


def main():
    parser = argparse.ArgumentParser(description="Export Fusion workflow definitions")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--id", metavar="WF_ID", help="Workflow definition ID to export")
    group.add_argument("--list", "-l", action="store_true", help="List all definitions")
    parser.add_argument("--output", "-o", metavar="FILE", help="Save exported YAML to file")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args()

    if args.id:
        yaml_content = export_workflow(args.id)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(yaml_content)
            print(f"  Exported to {args.output}")
        else:
            print(yaml_content)

    elif args.list:
        defs = list_definitions()
        if args.json:
            out = []
            for d in defs:
                out.append({
                    "id": d.get("id", ""),
                    "name": d.get("name", ""),
                    "enabled": d.get("enabled", False),
                    "trigger_type": d.get("trigger", {}).get("type", ""),
                })
            print(json.dumps(out, indent=2))
        else:
            print(f"\nWorkflow definitions ({len(defs)}):\n")
            for d in defs:
                print(format_definition(d))
                print()


if __name__ == "__main__":
    main()
