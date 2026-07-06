"""
Delete a CrowdStrike Falcon Next-Gen SIEM lookup file.

Usage:
    python delete_lookup.py --name "blocklist.csv"                  # Interactive confirmation
    python delete_lookup.py --name "blocklist.csv" --confirm        # Skip confirmation
    python delete_lookup.py --name "blocklist.csv" --confirm --json # Machine-readable
"""

import argparse
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import get_client

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DOMAIN_CHOICES = ["all", "falcon", "third-party", "dashboards", "parsers-repository"]


def delete_lookup(filename, search_domain="all"):
    """
    Delete a lookup file. Returns (success, message).
    """
    client = get_client()
    resp = client.delete_lookup_file(filename=filename, search_domain=search_domain)

    body = resp["body"] if isinstance(resp, dict) else resp
    if isinstance(body, dict):
        errors = body.get("errors", [])
        if errors:
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            return False, msg

    status_code = resp.get("status_code", 0) if isinstance(resp, dict) else 0
    if status_code not in (200, 201, 204):
        return False, f"API returned status {status_code}"

    return True, f"Lookup file '{filename}' deleted successfully"


def main():
    """CLI entry point for deleting a lookup file."""
    parser = argparse.ArgumentParser(
        description="Delete a Falcon Next-Gen SIEM lookup file"
    )
    parser.add_argument(
        "--name", "-n", required=True, metavar="FILENAME",
        help="Lookup file name to delete"
    )
    parser.add_argument(
        "--domain", "-d", choices=DOMAIN_CHOICES, default="all",
        help="Search domain to delete from (default: all, which finds files in "
             "the global namespace where create_lookup.py uploads them)"
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Skip interactive confirmation"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Machine-readable JSON output"
    )
    args = parser.parse_args()

    # In JSON mode, require --confirm (non-interactive)
    if args.json and not args.confirm:
        print(json.dumps({
            "success": False,
            "error": "--confirm is required with --json (non-interactive mode)",
        }, indent=2))
        sys.exit(1)

    # Interactive confirmation
    if not args.confirm:
        answer = input(f"  Delete lookup file '{args.name}'? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("  Cancelled.")
            sys.exit(0)

    success, message = delete_lookup(args.name, search_domain=args.domain)

    if args.json:
        print(json.dumps({
            "success": success,
            "filename": args.name,
            "domain": args.domain,
            "message": message,
        }, indent=2))
    else:
        if success:
            print(f"\n  {message}\n")
        else:
            print(f"  FAILED: {message}", file=sys.stderr)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
