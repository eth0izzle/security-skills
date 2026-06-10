"""
Validate CrowdStrike Fusion workflow YAML files.

Performs three levels of validation:
  1. Pre-flight: checks header comment, required top-level keys, PLACEHOLDER markers
  2. Structural: parses YAML and validates schema rules (action IDs, trigger types, etc.)
  3. API: dry-run import via POST /workflows/entities/definitions/import/v1?validate_only=true

Usage:
    python validate.py workflow.yaml                    # Validate one file
    python validate.py *.yaml                           # Validate multiple files
    python validate.py --preflight-only workflow.yaml   # Skip API call (runs pre-flight + structural)
"""

import argparse
import re
import sys
import os

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cs_auth import get_client

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REQUIRED_KEYS = {"name", "trigger"}
PLACEHOLDER_PATTERN = re.compile(r"PLACEHOLDER_[A-Z_]+")
ACTION_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
DATA_REF_PATTERN = re.compile(r"\$\{data\[")
VALID_TRIGGER_TYPES = {"On demand", "Signal", "Scheduled", "SubModel"}


def preflight_check(file_path):
    """
    Local checks before hitting the API. Returns list of warning/error strings.
    Empty list means all pre-flight checks passed.
    """
    issues = []

    if not os.path.isfile(file_path):
        return [f"File not found: {file_path}"]

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines()

    # Check header comment
    if not lines or not lines[0].startswith("#"):
        issues.append("WARNING: Missing header comment (first line should start with #)")

    # Check for required top-level keys (simple text scan — not a full YAML parser)
    for key in REQUIRED_KEYS:
        # Match key at start of line (top-level) followed by colon
        if not re.search(rf"^{key}\s*:", content, re.MULTILINE):
            issues.append(f"ERROR: Missing required top-level key '{key}'")

    # Check for PLACEHOLDER markers
    placeholders = PLACEHOLDER_PATTERN.findall(content)
    if placeholders:
        unique = sorted(set(placeholders))
        issues.append(f"ERROR: Found PLACEHOLDER markers that must be replaced: {', '.join(unique)}")

    return issues


def _collect_node_labels(data):
    """Collect all defined node labels from actions, loops, and conditions."""
    labels = set()
    for key in ("actions", "loops", "conditions"):
        section = data.get(key, {})
        if isinstance(section, dict):
            labels.update(section.keys())
    for loop_name, loop_def in data.get("loops", {}).items():
        if not isinstance(loop_def, dict):
            continue
        labels.add(loop_name)
        for key in ("actions", "conditions"):
            section = loop_def.get(key, {})
            if isinstance(section, dict):
                labels.update(section.keys())
    return labels


def _validate_action(label, action, issues):
    """Validate a single action dict."""
    if not isinstance(action, dict):
        return
    if "id" not in action:
        issues.append(f"ERROR: Action '{label}' missing required 'id' field")
    elif not ACTION_ID_PATTERN.match(str(action["id"])):
        issues.append(
            f"ERROR: Action '{label}' has invalid id '{action['id']}' "
            f"(must be 32-char hex)"
        )
    if "name" not in action:
        issues.append(f"ERROR: Action '{label}' missing required 'name' field")
    if "class" in action and "version_constraint" not in action:
        issues.append(
            f"ERROR: Action '{label}' has 'class' but missing "
            f"'version_constraint' (add: version_constraint: ~1)"
        )


def _validate_next_refs(label, action, all_labels, issues):
    """Check that next references point to defined labels."""
    if not isinstance(action, dict):
        return
    next_refs = action.get("next", [])
    if isinstance(next_refs, list):
        for ref in next_refs:
            if ref not in all_labels:
                issues.append(
                    f"WARNING: Action '{label}' references '{ref}' in 'next' "
                    f"but no action/loop/condition with that name exists"
                )


def _validate_loops(data, trigger, all_labels, issues):
    """Validate loop definitions and their actions."""
    loops = data.get("loops", {})
    if not isinstance(loops, dict):
        return
    for loop_name, loop_def in loops.items():
        if not isinstance(loop_def, dict):
            continue
        loop_actions = loop_def.get("actions", {})
        if isinstance(loop_actions, dict):
            for label, action in loop_actions.items():
                _validate_action(label, action, issues)
                _validate_next_refs(label, action, all_labels, issues)

        loop_for = loop_def.get("for", {})
        if not isinstance(loop_for, dict):
            continue
        loop_input = loop_for.get("input")
        if not loop_input or not isinstance(trigger, dict):
            continue
        params = trigger.get("parameters", {})
        if not isinstance(params, dict):
            continue
        props = params.get("properties", {})
        if isinstance(props, dict) and loop_input not in props:
            issues.append(
                f"WARNING: Loop '{loop_name}' references "
                f"'{loop_input}' in for.input but it is not "
                f"defined in trigger.parameters.properties"
            )


def _validate_data_refs(file_path, issues):
    """Check data reference syntax for unclosed expressions."""
    with open(file_path, encoding="utf-8") as f:
        content = f.read()
    for match in DATA_REF_PATTERN.finditer(content):
        start = match.start()
        rest = content[start:]
        if "${data['" not in rest[:10] and '${data["' not in rest[:10]:
            continue
        bracket_count = 0
        closed = False
        for ch in rest:
            if ch == "{":
                bracket_count += 1
            elif ch == "}":
                bracket_count -= 1
                if bracket_count == 0:
                    closed = True
                    break
        if not closed:
            line_num = content[:start].count("\n") + 1
            issues.append(
                f"WARNING: Unclosed data reference at line {line_num}"
            )


def structural_check(file_path):
    """
    Validate YAML structure against workflow schema rules.
    Returns list of issue strings. Empty list means all checks passed.
    """
    issues = []

    try:
        with open(file_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        return [f"ERROR: YAML parse error: {exc}"]

    if not isinstance(data, dict):
        return ["ERROR: YAML did not parse as a dictionary"]

    trigger = data.get("trigger", {})
    if isinstance(trigger, dict):
        trigger_type = trigger.get("type")
        if trigger_type and trigger_type not in VALID_TRIGGER_TYPES:
            issues.append(
                f"ERROR: Invalid trigger type '{trigger_type}'. "
                f"Must be one of: {', '.join(sorted(VALID_TRIGGER_TYPES))}"
            )

    all_labels = _collect_node_labels(data)

    actions = data.get("actions", {})
    if isinstance(actions, dict):
        for label, action in actions.items():
            _validate_action(label, action, issues)
            _validate_next_refs(label, action, all_labels, issues)

    _validate_loops(data, trigger, all_labels, issues)
    _validate_data_refs(file_path, issues)

    return issues


def api_validate(file_path):
    """
    Validate via the CrowdStrike import API with validate_only=true.
    Returns (success: bool, message: str).
    """
    try:
        client = get_client()
        resp = client.import_definition(data_file=file_path, validate_only=True)
        body = resp["body"]
        errors = body.get("errors", [])
        if errors:
            msg = "; ".join(e.get("message", str(e)) for e in errors)
            return False, msg
        if resp["status_code"] not in (200, 201):
            return False, f"API returned status {resp['status_code']}"
        return True, "OK"
    except (ConnectionError, RuntimeError, OSError) as exc:
        return False, str(exc)


def validate_file(file_path, preflight_only=False):
    """
    Validate a single file. Returns (passed: bool, messages: list[str]).
    """
    messages = []

    # Pre-flight
    issues = preflight_check(file_path)
    has_errors = any(i.startswith("ERROR") for i in issues)
    messages.extend(issues)

    if has_errors:
        messages.append("Pre-flight FAILED — fix errors above before structural validation")
        return False, messages

    if not issues:
        messages.append("Pre-flight passed")

    # Structural validation
    struct_issues = structural_check(file_path)
    struct_errors = any(i.startswith("ERROR") for i in struct_issues)
    messages.extend(struct_issues)

    if struct_errors:
        messages.append("Structural validation FAILED — fix errors above before API validation")
        return False, messages

    if not struct_issues:
        messages.append("Structural validation passed")

    if preflight_only:
        return True, messages

    # API validation
    ok, msg = api_validate(file_path)
    if ok:
        messages.append("API validation passed")
    else:
        messages.append(f"API validation FAILED: {msg}")

    return ok, messages


def main():
    """CLI entry point for workflow validation."""
    parser = argparse.ArgumentParser(description="Validate Fusion workflow YAML files")
    parser.add_argument("files", nargs="+", metavar="FILE", help="YAML file(s) to validate")
    parser.add_argument("--preflight-only", action="store_true", help="Skip API validation")
    args = parser.parse_args()

    all_passed = True
    for fp in args.files:
        print(f"\n  {os.path.basename(fp)}")
        passed, messages = validate_file(fp, preflight_only=args.preflight_only)
        for m in messages:
            prefix = "    \u2713" if not m.startswith(("ERROR", "WARNING")) and "FAILED" not in m else "    \u2717"
            print(f"{prefix} {m}")
        if not passed:
            all_passed = False
        print()

    if all_passed:
        print("All files passed validation.")
    else:
        print("Some files failed validation.")
        sys.exit(1)


if __name__ == "__main__":
    main()
