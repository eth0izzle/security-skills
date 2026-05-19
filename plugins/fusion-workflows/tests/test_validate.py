"""Tests for validate.py — preflight and structural checks (no API calls needed)."""

import validate


VALID_WORKFLOW = """\
# Created by https://github.com/eth0izzle/security-skills/
name: Test Workflow
trigger:
  type: On demand
  name: On demand
  next:
    - ContainHost
  parameters:
    $schema: https://json-schema.org/draft-07/schema
    properties:
      device_id:
        type: string
    required:
      - device_id
    type: object
actions:
  ContainHost:
    id: aabbccdd11223344aabbccdd11223344
    name: Contain device
    properties:
      device_id: ${data['device_id']}
output_fields: []
"""


class TestPreflightCheck:
    """Test local YAML validation checks."""

    def test_valid_yaml(self, tmp_path):
        f = tmp_path / "good.yaml"
        f.write_text("# Header comment\nname: Test Workflow\ntrigger:\n  type: On demand\n")
        issues = validate.preflight_check(str(f))
        assert issues == []

    def test_missing_header_comment(self, tmp_path):
        f = tmp_path / "no_header.yaml"
        f.write_text("name: Test\ntrigger:\n  type: On demand\n")
        issues = validate.preflight_check(str(f))
        assert any("header comment" in i for i in issues)

    def test_missing_name_key(self, tmp_path):
        f = tmp_path / "no_name.yaml"
        f.write_text("# Header\ntrigger:\n  type: On demand\n")
        issues = validate.preflight_check(str(f))
        assert any("'name'" in i for i in issues)

    def test_missing_trigger_key(self, tmp_path):
        f = tmp_path / "no_trigger.yaml"
        f.write_text("# Header\nname: Test\n")
        issues = validate.preflight_check(str(f))
        assert any("'trigger'" in i for i in issues)

    def test_placeholder_markers_detected(self, tmp_path):
        f = tmp_path / "placeholders.yaml"
        f.write_text("# Header\nname: Test\ntrigger:\n  type: On demand\nactions:\n  MyAction:\n    id: PLACEHOLDER_ACTION_ID\n")
        issues = validate.preflight_check(str(f))
        assert any("PLACEHOLDER" in i for i in issues)

    def test_file_not_found(self):
        issues = validate.preflight_check("/nonexistent/file.yaml")
        assert any("not found" in i.lower() for i in issues)

    def test_multiple_placeholders_listed(self, tmp_path):
        f = tmp_path / "multi.yaml"
        f.write_text("# Header\nname: Test\ntrigger:\n  type: On demand\nactions:\n  A:\n    id: PLACEHOLDER_ACTION_ID\n  B:\n    id: PLACEHOLDER_TRIGGER_ID\n")
        issues = validate.preflight_check(str(f))
        placeholder_issues = [i for i in issues if "PLACEHOLDER" in i]
        assert len(placeholder_issues) == 1  # Single message listing all
        assert "PLACEHOLDER_ACTION_ID" in placeholder_issues[0]
        assert "PLACEHOLDER_TRIGGER_ID" in placeholder_issues[0]


class TestValidateFile:
    """Test the combined validation flow."""

    def test_preflight_only_passes(self, tmp_path):
        f = tmp_path / "good.yaml"
        f.write_text("# Header\nname: Test\ntrigger:\n  type: On demand\n")
        passed, messages = validate.validate_file(str(f), preflight_only=True)
        assert passed is True
        assert any("passed" in m.lower() for m in messages)

    def test_preflight_only_fails_on_errors(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("# Header\ntrigger:\n  type: On demand\n")
        passed, messages = validate.validate_file(str(f), preflight_only=True)
        assert passed is False

    def test_preflight_errors_block_api_call(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("# Header\nname: PLACEHOLDER_NAME\ntrigger:\n  type: On demand\n")
        passed, messages = validate.validate_file(str(f), preflight_only=False)
        assert passed is False
        assert any("fix errors" in m.lower() for m in messages)


class TestStructuralCheck:
    """Test YAML structural validation rules."""

    def test_valid_workflow_passes(self, tmp_path):
        f = tmp_path / "good.yaml"
        f.write_text(VALID_WORKFLOW)
        issues = validate.structural_check(str(f))
        assert issues == []

    def test_invalid_action_id_not_hex(self, tmp_path):
        f = tmp_path / "bad_id.yaml"
        f.write_text(VALID_WORKFLOW.replace(
            "aabbccdd11223344aabbccdd11223344", "not-a-valid-hex-id-at-all!!"
        ))
        issues = validate.structural_check(str(f))
        assert any("invalid id" in i.lower() for i in issues)

    def test_invalid_action_id_wrong_length(self, tmp_path):
        f = tmp_path / "short_id.yaml"
        f.write_text(VALID_WORKFLOW.replace(
            "aabbccdd11223344aabbccdd11223344", "aabbccdd1122"
        ))
        issues = validate.structural_check(str(f))
        assert any("invalid id" in i.lower() for i in issues)

    def test_missing_action_id(self, tmp_path):
        f = tmp_path / "no_id.yaml"
        content = """\
# Header
name: Test
trigger:
  type: On demand
  next:
    - MyAction
actions:
  MyAction:
    name: Some action
    properties:
      key: value
"""
        f.write_text(content)
        issues = validate.structural_check(str(f))
        assert any("missing required 'id'" in i.lower() for i in issues)

    def test_missing_action_name(self, tmp_path):
        f = tmp_path / "no_name.yaml"
        content = """\
# Header
name: Test
trigger:
  type: On demand
  next:
    - MyAction
actions:
  MyAction:
    id: aabbccdd11223344aabbccdd11223344
    properties:
      key: value
"""
        f.write_text(content)
        issues = validate.structural_check(str(f))
        assert any("missing required 'name'" in i.lower() for i in issues)

    def test_missing_version_constraint(self, tmp_path):
        f = tmp_path / "no_vc.yaml"
        content = """\
# Header
name: Test
trigger:
  type: On demand
  next:
    - CreateVariable
actions:
  CreateVariable:
    id: 702d15788dbbffdf0b68d8e2f3599aa4
    class: CreateVariable
    name: Create variable
    properties:
      variable_schema:
        properties:
          item:
            type: string
        type: object
"""
        f.write_text(content)
        issues = validate.structural_check(str(f))
        assert any("version_constraint" in i for i in issues)

    def test_invalid_trigger_type(self, tmp_path):
        f = tmp_path / "bad_trigger.yaml"
        f.write_text(VALID_WORKFLOW.replace("type: On demand", "type: Invalid"))
        issues = validate.structural_check(str(f))
        assert any("invalid trigger type" in i.lower() for i in issues)

    def test_unresolved_next_reference(self, tmp_path):
        f = tmp_path / "bad_next.yaml"
        content = """\
# Header
name: Test
trigger:
  type: On demand
  next:
    - ContainHost
actions:
  ContainHost:
    id: aabbccdd11223344aabbccdd11223344
    name: Contain device
    next:
      - NonExistentAction
    properties:
      device_id: ${data['device_id']}
"""
        f.write_text(content)
        issues = validate.structural_check(str(f))
        assert any("NonExistentAction" in i for i in issues)

    def test_loop_input_references_param(self, tmp_path):
        f = tmp_path / "bad_loop.yaml"
        content = """\
# Header
name: Test
trigger:
  type: On demand
  next:
    - Loop
  parameters:
    $schema: https://json-schema.org/draft-07/schema
    properties:
      device_id:
        type: string
    required:
      - device_id
    type: object
loops:
  Loop:
    name: For each item
    for:
      input: nonexistent_param
      sequential: true
    trigger:
      next:
        - DoStuff
    actions:
      DoStuff:
        id: aabbccdd11223344aabbccdd11223344
        name: Do stuff
        properties:
          key: value
output_fields: []
"""
        f.write_text(content)
        issues = validate.structural_check(str(f))
        assert any("nonexistent_param" in i for i in issues)

    def test_yaml_parse_error(self, tmp_path):
        f = tmp_path / "invalid.yaml"
        f.write_text(":\n  - [\ninvalid yaml content {{{\n")
        issues = validate.structural_check(str(f))
        assert any("parse error" in i.lower() for i in issues)

    def test_structural_errors_block_api(self, tmp_path):
        f = tmp_path / "struct_bad.yaml"
        content = """\
# Header
name: Test
trigger:
  type: On demand
  next:
    - MyAction
actions:
  MyAction:
    name: Missing ID action
    properties:
      key: value
"""
        f.write_text(content)
        passed, messages = validate.validate_file(str(f), preflight_only=False)
        assert passed is False
        assert any("structural validation failed" in m.lower() for m in messages)
