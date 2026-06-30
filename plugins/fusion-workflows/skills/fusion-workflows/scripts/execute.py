"""
Execute a CrowdStrike Fusion workflow and optionally poll for results.

Usage:
    python execute.py --id <def_id> --params '{"device_id":"abc123"}'
    python execute.py --id <def_id>                     # Interactive parameter prompt
    python execute.py --id <def_id> --params '{}' --wait --timeout 120
"""

import argparse
import json
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import get_client

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def get_workflow_params_schema(definition_id):
    """Fetch the parameter schema for a workflow definition."""
    try:
        client = get_client()
        resp = client.search_definitions(filter=f"id:'{definition_id}'")
        body = resp["body"]
        resources = body.get("resources", [])
        if not resources:
            return None
        trigger = resources[0].get("trigger", {})
        return trigger.get("parameters", {}).get("properties", {})
    except (ConnectionError, RuntimeError, OSError):
        return None


def prompt_for_params(schema):
    """Interactively prompt the user for each parameter."""
    params = {}
    if not schema:
        print("  No parameter schema found. Enter JSON manually:")
        raw = input("  > ")
        return json.loads(raw) if raw.strip() else {}

    print("\n  Enter parameter values (leave blank for optional fields):\n")
    for field_name, field_schema in schema.items():
        title = field_schema.get("title", field_name)
        ftype = field_schema.get("type", "string")
        desc = field_schema.get("description", "")
        prompt_text = f"  {title} ({ftype})"
        if desc:
            prompt_text += f" — {desc}"
        prompt_text += ": "

        value = input(prompt_text)
        if not value:
            continue

        # Type coercion
        if ftype == "integer":
            value = int(value)
        elif ftype == "boolean":
            value = value.lower() in ("true", "1", "yes")
        elif ftype == "array":
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                # Treat as comma-separated strings
                value = [v.strip() for v in value.split(",")]
        elif ftype == "object":
            value = json.loads(value)

        params[field_name] = value

    return params


def execute_workflow(definition_id, params, depth=1):
    """
    Execute a workflow. Returns (success, execution_id, response_body).
    """
    try:
        client = get_client()
        resp = client.execute(
            definition_id=[definition_id],
            depth=depth,
            body=params,
        )
        body = resp["body"]
        errors = body.get("errors", [])
        if errors:
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            return False, None, msg

        resources = body.get("resources", [])
        # The execute endpoint returns resources as a list of bare execution-ID
        # strings, not objects. Handle both shapes defensively.
        exec_id = None
        if resources:
            first = resources[0]
            exec_id = first if isinstance(first, str) else first.get("id")
        return True, exec_id, body
    except (ConnectionError, RuntimeError, OSError) as exc:
        return False, None, str(exc)


def poll_results(execution_id, timeout=120, interval=5):
    """
    Poll for execution results until complete or timeout.
    Returns the result body or None.
    """
    client = get_client()
    start = time.time()
    # Terminal statuses returned by the execution-results API (see
    # references/best-practices.md). The API returns capitalized values;
    # match case-insensitively to be safe. "ActionRequired" is terminal for
    # polling purposes — it waits on human input and won't progress on its own.
    terminal = {"succeeded", "failed", "canceled", "nonrecoverable", "actionrequired"}
    print(f"\n  Polling for results (timeout: {timeout}s)...")
    while time.time() - start < timeout:
        try:
            resp = client.execution_results(ids=execution_id)
            body = resp["body"]
            resources = body.get("resources", [])
            if resources:
                result = resources[0]
                status = result.get("status", "")
                if status.lower() in terminal:
                    return result
                print(f"    Status: {status} ({int(time.time() - start)}s elapsed)")
        except (ConnectionError, RuntimeError, OSError) as exc:
            print(f"    Poll error: {exc}")
        time.sleep(interval)

    print(f"  Timeout after {timeout}s — execution may still be running.")
    return None


def main():
    """CLI entry point for workflow execution."""
    parser = argparse.ArgumentParser(description="Execute a Fusion workflow")
    parser.add_argument("--id", required=True, metavar="DEF_ID", help="Workflow definition ID")
    parser.add_argument("--params", metavar="JSON", help="Execution parameters as JSON string")
    parser.add_argument("--wait", action="store_true", help="Poll for execution results")
    parser.add_argument("--timeout", type=int, default=120, help="Poll timeout in seconds (default: 120)")
    parser.add_argument("--json", action="store_true", help="Machine-readable JSON output")
    args = parser.parse_args()

    # Get parameters
    if args.params:
        params = json.loads(args.params)
    else:
        # Interactive mode
        schema = get_workflow_params_schema(args.id)
        params = prompt_for_params(schema)

    print(f"\n  Executing workflow {args.id}")
    print(f"  Parameters: {json.dumps(params, indent=2)}")

    ok, exec_id, resp = execute_workflow(args.id, params)

    if not ok:
        print(f"\n  Execution FAILED: {resp}")
        sys.exit(1)

    print(f"  Execution ID: {exec_id}")

    if args.json and not args.wait:
        print(json.dumps(resp, indent=2))
        return

    # Poll for results
    if args.wait and exec_id:
        result = poll_results(exec_id, timeout=args.timeout)
        if result:
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                status = result.get("status", "?")
                print(f"\n  Execution {status}")
                output = result.get("output", {})
                if output:
                    print(f"  Output:\n{json.dumps(output, indent=4)}")
        else:
            print("  No results returned within timeout.")
            sys.exit(1)
    elif not args.wait:
        print("\n  Execution submitted. Use --wait to poll for results.")


if __name__ == "__main__":
    main()
