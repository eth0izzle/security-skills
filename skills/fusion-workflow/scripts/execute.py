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
from cs_auth import load_env, api_get, api_post

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXECUTE_ENDPOINT = "/workflows/entities/execute/v1"
RESULTS_ENDPOINT = "/workflows/entities/execution-results/v1"
DEFINITIONS_ENDPOINT = "/workflows/entities/definitions/v1"


def get_workflow_params_schema(definition_id):
    """Fetch the parameter schema for a workflow definition."""
    try:
        resp = api_get(DEFINITIONS_ENDPOINT, params={"ids": definition_id})
        resources = resp.get("resources", [])
        if not resources:
            return None
        trigger = resources[0].get("trigger", {})
        return trigger.get("parameters", {}).get("properties", {})
    except Exception:
        return None


def prompt_for_params(schema):
    """Interactively prompt the user for each parameter."""
    params = {}
    if not schema:
        print("  No parameter schema found. Enter JSON manually:")
        raw = input("  > ")
        return json.loads(raw) if raw.strip() else {}

    required = set()
    # Get required fields from parent schema if available
    for field_name, field_schema in schema.items():
        pass  # We'll mark required below

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
    body = {
        "definition_id": [definition_id],
        **params,
    }
    try:
        # The execution API expects parameters at the top level alongside definition_id
        resp = api_post(EXECUTE_ENDPOINT, json_body=body, params={"depth": depth})
        errors = resp.get("errors", [])
        if errors:
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            return False, None, msg

        resources = resp.get("resources", [])
        exec_id = resources[0].get("id") if resources else None
        return True, exec_id, resp
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
        return False, None, error_text


def poll_results(execution_id, timeout=120, interval=5):
    """
    Poll for execution results until complete or timeout.
    Returns the result body or None.
    """
    start = time.time()
    print(f"\n  Polling for results (timeout: {timeout}s)...")
    while time.time() - start < timeout:
        try:
            resp = api_get(RESULTS_ENDPOINT, params={"ids": execution_id})
            resources = resp.get("resources", [])
            if resources:
                result = resources[0]
                status = result.get("status", "")
                if status in ("completed", "failed", "error"):
                    return result
                print(f"    Status: {status} ({int(time.time() - start)}s elapsed)")
        except Exception as e:
            print(f"    Poll error: {e}")
        time.sleep(interval)

    print(f"  Timeout after {timeout}s — execution may still be running.")
    return None


def main():
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
