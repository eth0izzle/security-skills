"""
Upload a new CrowdStrike Falcon Next-Gen SIEM lookup file.

Usage:
    python create_lookup.py --file data.csv                         # Upload (filename from path)
    python create_lookup.py --file data.csv --name "blocklist.csv"  # Custom remote name
    python create_lookup.py --file data.csv --json                  # Machine-readable

The file is uploaded to the global namespace so CQL match() can resolve it by
filename in a search. A view-scoped ("search_domain") upload would make the file
invisible to match(), which defeats the purpose of a lookup file.
"""

import argparse
import json
import sys
import os

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


def create_lookup(file_path, filename=None):
    """
    Upload a new lookup file to the global namespace. Returns (success, message).

    No search_domain is sent, so the file is resolvable by CQL match() in a
    search. Scoping to a view would hide it from match().
    """
    if filename is None:
        filename = os.path.basename(file_path)

    client = get_client()
    with open(file_path, "rb") as f:
        resp = client.create_lookup_file(filename=filename, file=f.read())

    body = resp["body"] if isinstance(resp, dict) else resp
    if isinstance(body, dict):
        errors = body.get("errors", [])
        if errors:
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            return False, msg

    status_code = resp.get("status_code", 0) if isinstance(resp, dict) else 0
    if status_code not in (200, 201):
        return False, f"API returned status {status_code}"

    return True, f"Lookup file '{filename}' created successfully"


def main():
    """CLI entry point for creating a lookup file."""
    parser = argparse.ArgumentParser(
        description="Upload a new Falcon Next-Gen SIEM lookup file"
    )
    parser.add_argument(
        "--file", "-f", required=True, metavar="FILE",
        help="Local file to upload"
    )
    parser.add_argument(
        "--name", "-n", metavar="FILENAME",
        help="Remote filename (defaults to local filename)"
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

    remote_name = args.name or os.path.basename(args.file)
    success, message = create_lookup(args.file, filename=remote_name)

    if args.json:
        print(json.dumps({
            "success": success,
            "filename": remote_name,
            "message": message,
        }, indent=2))
    else:
        if success:
            print(f"\n  {message}")
            print(f"    Filename : {remote_name}")
            print("\n  Note: Rate limit is 5 file uploads per 30 seconds.\n")
        else:
            print(f"  FAILED: {message}", file=sys.stderr)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
