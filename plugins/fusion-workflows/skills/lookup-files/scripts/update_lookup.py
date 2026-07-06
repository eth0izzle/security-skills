"""
Replace the content of an existing CrowdStrike Falcon Next-Gen SIEM lookup file.

Usage:
    python update_lookup.py --name "blocklist.csv" --file updated-data.csv
    python update_lookup.py --name "blocklist.csv" --file updated-data.csv --json

The file is updated in the global namespace so CQL match() can resolve it, mirroring
create_lookup.py. See that script's note on why a view-scoped ("search_domain") upload
would hide the file from match().
"""

import argparse
import json
import sys
import os

# Import shared auth from this scripts directory, anchored to this file's own
# location (not the cwd) so the import works regardless of where it is launched.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import get_client

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def validate_file(file_path):
    """Validate the local file before upload. Returns (ok, message)."""
    if not os.path.isfile(file_path):
        return False, f"File not found: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in (".csv", ".json", ".txt"):
        return False, f"Unexpected file extension '{ext}' (expected .csv, .json, or .txt)"

    return True, "OK"


def update_lookup(file_path, filename):
    """
    Replace lookup file content in the global namespace. Returns (success, message).

    No search_domain is sent, matching create_lookup.py, so the file stays
    resolvable by CQL match().
    """
    client = get_client()
    with open(file_path, "rb") as f:
        resp = client.update_lookup_file(filename=filename, file=f.read())

    body = resp["body"] if isinstance(resp, dict) else resp
    if isinstance(body, dict):
        errors = body.get("errors", [])
        if errors:
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            return False, msg

    status_code = resp.get("status_code", 0) if isinstance(resp, dict) else 0
    if status_code not in (200, 201):
        return False, f"API returned status {status_code}"

    return True, f"Lookup file '{filename}' updated successfully"


def main():
    """CLI entry point for updating a lookup file."""
    parser = argparse.ArgumentParser(
        description="Update an existing Falcon Next-Gen SIEM lookup file"
    )
    parser.add_argument(
        "--name", "-n", required=True, metavar="FILENAME",
        help="Remote filename to update"
    )
    parser.add_argument(
        "--file", "-f", required=True, metavar="FILE",
        help="Local file with new content"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Machine-readable JSON output"
    )
    args = parser.parse_args()

    ok, msg = validate_file(args.file)
    if not ok:
        if args.json:
            print(json.dumps({"success": False, "error": msg}, indent=2))
        else:
            print(f"  ERROR: {msg}", file=sys.stderr)
        sys.exit(1)

    success, message = update_lookup(args.file, filename=args.name)

    if args.json:
        print(json.dumps({
            "success": success,
            "filename": args.name,
            "message": message,
        }, indent=2))
    else:
        if success:
            print(f"\n  {message}")
            print(f"    Filename : {args.name}\n")
        else:
            print(f"  FAILED: {message}", file=sys.stderr)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
