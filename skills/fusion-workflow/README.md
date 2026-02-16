# CrowdStrike Falcon Fusion SOAR Workflow Skill

A Claude Code skill for building, validating, and deploying [CrowdStrike Falcon Fusion SOAR](https://www.crowdstrike.com/platform/next-gen-siem/soar/) workflows entirely from natural language. Describe what you want to automate and Claude will discover the right actions, author valid YAML, validate against the CrowdStrike API, and import into your environment.

## What It Does

- **Discovers actions** from the live CrowdStrike action catalog (5,000+ actions across 100+ vendors)
- **Authors workflow YAML** with correct schema, data references, CEL expressions, and loop/conditional patterns
- **Validates** workflows against the CrowdStrike API before import (catches schema errors, invalid action IDs, bad references)
- **Imports** validated workflows into your CrowdStrike CID
- **Executes** on-demand workflows with parameters and monitors results
- **Exports** existing workflows from your environment to YAML

## Prerequisites

- Python 3.8+ with `requests` installed
- CrowdStrike API credentials with Falcon Fusion SOAR permissions
- Access to a CrowdStrike CID with Fusion SOAR enabled

### Required API Scopes

Your CrowdStrike API client needs these scopes:

| Scope | Permission | Used For |
|-------|------------|----------|
| Workflow | Read, Write | All operations (discover, validate, import, execute, export) |

## Setup

### 1. Install the skill

Follow the [main setup instructions](../../README.md#setup) to install all skills.

### 2. Configure CrowdStrike credentials

Create a `.env` file in your working directory (the directory where you run Claude Code) or set these variables manually:

```
CS_CLIENT_ID=your_client_id_here
CS_CLIENT_SECRET=your_client_secret_here
CS_BASE_URL=https://api.crowdstrike.com
```

The `CS_BASE_URL` varies by CrowdStrike cloud:

| Cloud | Base URL |
|-------|----------|
| US-1 | `https://api.crowdstrike.com` |
| US-2 | `https://api.us-2.crowdstrike.com` |
| EU-1 | `https://api.eu-1.crowdstrike.com` |
| US-GOV-1 | `https://api.laggar.gcw.crowdstrike.com` |

### 3. Verify credentials

```bash
python scripts/cs_auth.py
```

This will confirm your API client can authenticate and display a masked token.

## Usage with Claude Code

Start Claude Code in any directory with the `.env` file configured, then describe what you want:

```
> Create a workflow that network-contains a device by ID with a case reference note
> Build an on-demand workflow that takes a list of SHA256 hashes, looks each up on VirusTotal, and blocks any with 5+ detections
> Create a phishing response playbook that revokes user sessions in Okta and Entra, then force-resets their password
```

Claude will automatically:
1. Search the action catalog to find the right action IDs and input schemas
2. Choose the appropriate trigger type and workflow pattern
3. Author the YAML with correct data references and CEL expressions
4. Run validation to catch errors
5. Import into your CrowdStrike environment (with your approval)

### Tips

- Use `/plan` mode for complex multi-step workflows so Claude can research the action catalog before writing
- Provide CrowdStrike-specific details when possible (e.g., "use Okta to revoke sessions" vs "revoke sessions")
- For plugin actions (Okta, Entra, ServiceNow, Slack, etc.), you'll need to provide the `config_id` from your CrowdStrike Store integrations

## Standalone Script Usage

All scripts can be used independently without Claude Code.

### Discover actions

```bash
# Search by name
python scripts/action_search.py --search "contain"

# Browse a vendor's actions
python scripts/action_search.py --vendor "Okta" --list

# Get full schema for an action (input/output fields, types, class info)
python scripts/action_search.py --details <action_id>

# List all vendors/integrations
python scripts/action_search.py --vendors

# Filter by use case
python scripts/action_search.py --use-case "Identity"

# Machine-readable output
python scripts/action_search.py --search "contain" --json
```

### Discover trigger types

```bash
# List all trigger types
python scripts/trigger_search.py --list

# Get YAML structure for a specific trigger
python scripts/trigger_search.py --type "On demand"
```

### Validate

```bash
# Full validation (preflight structure check + API dry-run)
python scripts/validate.py workflow.yaml

# Preflight only (no API call, checks structure and PLACEHOLDER markers)
python scripts/validate.py --preflight workflow.yaml

# Validate multiple files
python scripts/validate.py *.yaml
```

### Import

```bash
# Validate and import
python scripts/import_workflow.py workflow.yaml

# Skip validation (if already validated)
python scripts/import_workflow.py --skip-validate workflow.yaml
```

### Execute

```bash
# Run with parameters
python scripts/execute.py --id <definition_id> --params '{"device_id":"abc123"}'

# Run and wait for results
python scripts/execute.py --id <definition_id> --params '{"key":"val"}' --wait --timeout 120

# Interactive parameter prompt
python scripts/execute.py --id <definition_id>
```

### Export

```bash
# Export a workflow to YAML
python scripts/export.py --id <workflow_id> --output workflow.yaml

# List all workflow definitions in your CID
python scripts/export.py --list
```