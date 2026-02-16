"""
Import CrowdStrike Fusion workflow YAML files via the API.

Validates first (unless --skip-validate), then imports.
Prints the workflow definition ID on success.

Usage:
    python import_workflow.py workflow.yaml                  # Validate + import
    python import_workflow.py --skip-validate workflow.yaml  # Skip validation
    python import_workflow.py *.yaml                         # Multiple files
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import load_env, api_post_multipart
from validate import validate_file

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IMPORT_ENDPOINT = "/workflows/entities/definitions/import/v1"


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
    args = parser.parse_args()

    results = []

    for fp in args.files:
        basename = os.path.basename(fp)
        print(f"\n  {basename}")

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
    failed = [r for r in results if "FAILED" in r[1]]

    if imported:
        print(f"  Imported ({len(imported)}):")
        for name, _, wf_id in imported:
            print(f"    {name} → {wf_id}")

    if failed:
        print(f"  Failed ({len(failed)}):")
        for name, status, _ in failed:
            print(f"    {name}: {status}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
