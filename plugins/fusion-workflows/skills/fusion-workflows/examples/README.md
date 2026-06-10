# Workflow Examples

Real Fusion SOAR playbooks exported from the CrowdStrike Content Library. These are
production workflows with real action IDs that demonstrate common automation patterns.

## How to use these examples

These JSON files can be imported directly via the Fusion SOAR API:

```bash
python scripts/import_workflow.py example-file.json
```

The import logic detects non-global actions (third-party integrations like Slack, Zscaler,
PAN NGFW) and prompts you to either configure the integration or replace it with an action
available in your CID.

CrowdStrike-native actions (Create variable, Send email, Contain device, etc.) use universal
IDs that work across all clouds (us-1, us-2, eu-1).

## Categories

### threat-intel/
IOC enrichment workflows using VirusTotal and Zscaler.

- **enrich-url-on-demand-with-virustotal-and-add-to-zscaler-blocklist.json** — Simple
  on-demand URL enrichment + block (3 activities, 1 gateway)
- **domain-enrichment-virustotal.json** — Full domain enrichment with comment building
  and DNS resolution (15 activities, 12 gateways, 3 loops)

### identity-response/
Identity detection response and phishing remediation.

- **identity-detection-auto-resolution-recent-password-change.json** — Auto-resolves
  brute force detections when user recently changed password (3 activities)
- **email-phishing-playbook-with-identity-threat-protection-actions.json** — Enriches
  and remediates phishing with Identity Threat Protection actions (8 activities, 4 loops)

### notifications/
Alert routing and incident response with stakeholder notifications.

- **slack-send-message-to-channel.json** — Simplest possible workflow: one trigger,
  one action (1 activity)
- **network-contain-endpoint-on-detection.json** — Auto-contain with human approval
  gates and stakeholder email notifications (24 activities)

### ngsiem/
Falcon Next-Gen SIEM detection management.

- **close-duplicate-next-gen-siem-detections-automatically.json** — Auto-closes duplicate
  detections by querying for previous alerts with matching event types (6 activities)

### response-actions/
Palo Alto Networks NGFW integration for network-level response.

- **pan-ngfw-register-ip-to-tag-dag.json** — Register IP to Dynamic Address Group tag
- **pan-ngfw-unregister-ip-from-tag-dag.json** — Remove IP from DAG tag
- **pan-ngfw-blocklist-to-edl-and-force-refresh.json** — Add to External Dynamic List blocklist
- **pan-ngfw-allowlist-add-to-edl-exception-list.json** — Add to EDL exception list
- **pan-ngfw-get-all-edls.json** — List all EDLs
- **pan-ngfw-monitor-dynamic-address-group-members.json** — Monitor DAG membership

### tutorials/
"Introduction to..." playbooks that teach specific Fusion SOAR concepts.

- **introduction-to-cases-how-to-add-an-event-to-a-case.json** — Case management basics
- **introduction-to-data-transforms-how-to-use-a-ternary-operator.json** — CEL ternary expressions
- **introduction-to-error-handling.json** — Error handling patterns
- **introduction-to-lookup-file-actions.json** — Create/overwrite lookup files
- **introduction-to-receive-email-trigger-how-to-create-a-lookup-file-from-an-email-.json** — Email trigger + lookup file creation
- **introduction-to-variables-how-to-append-to-an-array.json** — Variable manipulation with arrays
