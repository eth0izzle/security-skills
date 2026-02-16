"""
Import CrowdStrike Fusion workflow YAML files via the API.

Validates first (unless --skip-validate), checks for duplicate names
(unless --skip-duplicate-check), then imports.
Prints the workflow definition ID on success.

Usage:
    python import_workflow.py workflow.yaml                         # Validate + dup check + import
    python import_workflow.py --skip-validate workflow.yaml         # Skip validation
    python import_workflow.py --skip-duplicate-check workflow.yaml  # Skip duplicate check
    python import_workflow.py *.yaml                                # Multiple files
"""

import argparse
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import load_env, api_post_multipart
from validate import validate_file
from query_workflows import fetch_all_definitions

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IMPORT_ENDPOINT = "/workflows/entities/definitions/import/v1"


def extract_name_from_yaml(file_path):
    """Extract the workflow name from a YAML file."""
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            match = re.match(r"^name:\s*['\"]?(.+?)['\"]?\s*$", line)
            if match:
                return match.group(1)
    return None


def check_duplicate(name, existing_names):
    """
    Check if a workflow name already exists.
    Returns the existing definition ID if found, None otherwise.
    """
    name_lower = name.lower()
    match = existing_names.get(name_lower)
    if match:
        return match.get("id", "?")
    return None


def import_file(file_path):
    """
    Import a single YAML file. Returns (success, message, workflow_id).
    """
    try:
        result = api_post_multipart(IMPORT_ENDPOINT, file_path)
        errors = result.get("errors", [])
        if errors:
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            return False, msg, None

        resources = result.get("resources", [])
        wf_id = resources[0].get("id") if resources else None
        return True, "OK", wf_id
    except Exception as e:
        error_text = str(e)
        if hasattr(e, "response") and e.response is not None:
            try:
                err_json = e.response.json()
                errs = err_json.get("errors", [])
                if errs:
                    error_text = "; ".join(item.get("message", str(item)) for item in errs)
            except Exception:
                error_text = e.response.text[:500] if e.response.text else str(e)
        return False, error_text, None


def main():
    parser = argparse.ArgumentParser(description="Import Fusion workflow YAML files")
    parser.add_argument("files", nargs="+", metavar="FILE", help="YAML file(s) to import")
    parser.add_argument("--skip-validate", action="store_true", help="Skip pre-import validation")
    parser.add_argument("--skip-duplicate-check", action="store_true", help="Skip duplicate name check")
    args = parser.parse_args()

    # Pre-fetch existing workflow names for duplicate checking
    existing_names = {}
    if not args.skip_duplicate_check:
        print("\n  Checking for duplicate workflow names...")
        try:
            all_defs = fetch_all_definitions()
            existing_names = {d.get("name", "").lower(): d for d in all_defs}
            print(f"    Found {len(all_defs)} existing workflow(s)")
        except Exception as e:
            print(f"    WARNING: Could not fetch existing workflows: {e}", file=sys.stderr)
            print("    Skipping duplicate check — use --skip-duplicate-check to suppress")

    results = []

    for fp in args.files:
        basename = os.path.basename(fp)
        print(f"\n  {basename}")

        # Check for duplicate name
        if existing_names:
            wf_name = extract_name_from_yaml(fp)
            if wf_name:
                dup_id = check_duplicate(wf_name, existing_names)
                if dup_id:
                    print(f"    DUPLICATE: '{wf_name}' already exists (ID: {dup_id})")
                    print(f"    Skipping — delete or rename the existing workflow first")
                    results.append((basename, "DUPLICATE", None))
                    continue

        # Validate first
        if not args.skip_validate:
            passed, messages = validate_file(fp)
            for m in messages:
                print(f"    {m}")
            if not passed:
                results.append((basename, "VALIDATION FAILED", None))
                continue

        # Import
        ok, msg, wf_id = import_file(fp)
        if ok:
            print(f"    Imported — ID: {wf_id}")
            results.append((basename, "IMPORTED", wf_id))
        else:
            print(f"    IMPORT FAILED: {msg}")
            results.append((basename, "IMPORT FAILED", None))

    # Summary
    print(f"\n{'─' * 50}")
    imported = [r for r in results if r[1] == "IMPORTED"]
    duplicates = [r for r in results if r[1] == "DUPLICATE"]
    failed = [r for r in results if "FAILED" in r[1]]

    if imported:
        print(f"  Imported ({len(imported)}):")
        for name, _, wf_id in imported:
            print(f"    {name} → {wf_id}")

    if duplicates:
        print(f"  Skipped — duplicate ({len(duplicates)}):")
        for name, _, _ in duplicates:
            print(f"    {name}")

    if failed:
        print(f"  Failed ({len(failed)}):")
        for name, status, _ in failed:
            print(f"    {name}: {status}")

    if failed or duplicates:
        sys.exit(1)


if __name__ == "__main__":
    main()
