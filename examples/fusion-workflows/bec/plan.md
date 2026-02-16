&nbsp;BEC Investigation \& Response Workflows — CrowdStrike Fusion



&nbsp;Context



&nbsp;CrowdStrike Fusion SOAR workflows are needed to handle Business Email Compromise (BEC) cases following PwC's 10-step BEC investigation guide

&nbsp;(examples/PwC-Business\_Email\_Compromise-Guide.pdf). The workflows will automate investigation and response actions, using CrowdStrike-native actions where possible and HTTP

&nbsp;actions to call Microsoft Graph API for M365-specific investigation steps.



&nbsp;Outcome: 8 YAML workflow files (7 functional + 1 orchestrator) placed in examples/.claude/skills/fusion-workflow/workflows/bec/, covering the full BEC investigation lifecycle.



&nbsp;---

&nbsp;Workflow Summary



&nbsp;┌─────┬──────────────────────────────────┬───────────────┬─────────────────────────┬──────────────────────────────────────────────────────┐

&nbsp;│  #  │               File               │   PwC Steps   │         Pattern         │                       Actions                        │

&nbsp;├─────┼──────────────────────────────────┼───────────────┼─────────────────────────┼──────────────────────────────────────────────────────┤

&nbsp;│ W1  │ bec-investigation-kickoff.yaml   │ 1             │ single-action (chained) │ Print data (native)                                  │

&nbsp;├─────┼──────────────────────────────────┼───────────────┼─────────────────────────┼──────────────────────────────────────────────────────┤

&nbsp;│ W2  │ bec-login-analysis.yaml          │ 4             │ loop                    │ HTTP → Graph API sign-in logs                        │

&nbsp;├─────┼──────────────────────────────────┼───────────────┼─────────────────────────┼──────────────────────────────────────────────────────┤

&nbsp;│ W3  │ bec-forwarding-rules.yaml        │ 3             │ loop + conditional      │ HTTP → Graph API inbox rules                         │

&nbsp;├─────┼──────────────────────────────────┼───────────────┼─────────────────────────┼──────────────────────────────────────────────────────┤

&nbsp;│ W4  │ bec-permission-oauth-review.yaml │ 5, 6          │ loop                    │ HTTP → Graph API directory/OAuth                     │

&nbsp;├─────┼──────────────────────────────────┼───────────────┼─────────────────────────┼──────────────────────────────────────────────────────┤

&nbsp;│ W5  │ bec-ioc-enrichment-blocking.yaml │ 9             │ loop-conditional        │ Native: ThreatGraph + IOC mgmt                       │

&nbsp;├─────┼──────────────────────────────────┼───────────────┼─────────────────────────┼──────────────────────────────────────────────────────┤

&nbsp;│ W6  │ bec-identity-response.yaml       │ 10 (identity) │ loop + conditional      │ Plugin: Okta/Entra ID session revoke, password reset │

&nbsp;├─────┼──────────────────────────────────┼───────────────┼─────────────────────────┼──────────────────────────────────────────────────────┤

&nbsp;│ W7  │ bec-endpoint-containment.yaml    │ 10 (endpoint) │ loop                    │ Native: contain device                               │

&nbsp;├─────┼──────────────────────────────────┼───────────────┼─────────────────────────┼──────────────────────────────────────────────────────┤

&nbsp;│ W8  │ bec-orchestrator.yaml            │ All           │ sequential chain        │ Native: Execute Workflow actions                     │

&nbsp;└─────┴──────────────────────────────────┴───────────────┴─────────────────────────┴──────────────────────────────────────────────────────┘



&nbsp;---

&nbsp;Common YAML Conventions (all workflows)



&nbsp;- Header: # Created by https://github.com/eth0izzle/security-skills/

&nbsp;- Trigger: On demand with JSON Schema parameters

&nbsp;- Fixed IDs: CreateVariable 702d15788dbbffdf0b68d8e2f3599aa4, UpdateVariable 6c6eab39063fa3b72d98c82af60deb8a, Print data aadbf530e35fc452a032f5f8acaaac2a

&nbsp;- Class-based actions: class + version\_constraint: ~1

&nbsp;- Plugin actions: config\_id as PLACEHOLDER\_CONFIG\_ID with lookup instructions

&nbsp;- Non-fixed action IDs: PLACEHOLDER\_\* with comments specifying which action\_search.py command to run

&nbsp;- Sequential loops (sequential: true) for all bulk operations

&nbsp;- Data refs: ${data\['param']}, ${data\['arr.#.field']}, ${data\['Action.Field']}



&nbsp;HTTP Action Pattern for Graph API



&nbsp;Workflows W2-W4 use HTTP actions to call Microsoft Graph API. Each requires:

&nbsp;- Parameters: tenant\_id, client\_id, client\_secret (Azure AD app credentials)

&nbsp;- Step 1: HTTP POST to https://login.microsoftonline.com/{tenant\_id}/oauth2/v2.0/token to get access token

&nbsp;- Step 2: HTTP GET/POST to Graph API endpoint with Authorization: Bearer {token}

&nbsp;- Azure AD App Permissions needed: AuditLog.Read.All, MailboxSettings.Read, Directory.Read.All, Application.Read.All



&nbsp;---

&nbsp;W1: BEC - Investigation Kickoff



&nbsp;File: bec-investigation-kickoff.yaml

&nbsp;Template basis: assets/single-action.yaml (extended to chain Print data actions)



&nbsp;Parameters: case\_id (string, required), compromised\_users (array of strings, required), incident\_date (string, required), incident\_summary (string, required), priority (enum:

&nbsp;Critical/High/Medium/Low)



&nbsp;Flow:

&nbsp;trigger → PrintCaseHeader → PrintChecklist → PrintUserList



&nbsp;- PrintCaseHeader: Print case ID, date, summary, priority, user list

&nbsp;- PrintChecklist: Print PwC 10-step checklist with automation status markers:

&nbsp;  - Steps 1,3,4,5,6,9,10 → "Automated via CrowdStrike Fusion"

&nbsp;  - Steps 2,7,8 → "Partially automated via Graph API HTTP actions"

&nbsp;- PrintUserList: Print each compromised user UPN for downstream workflows



&nbsp;Output: PrintCaseHeader.output



&nbsp;---

&nbsp;W2: BEC - Suspicious Login Analysis



&nbsp;File: bec-login-analysis.yaml

&nbsp;Template basis: assets/loop.yaml



&nbsp;Parameters: user\_upns (array, required), tenant\_id, client\_id, client\_secret (strings, required for Graph API), lookback\_days (integer, default 30)



&nbsp;Flow:

&nbsp;trigger → GetGraphToken (HTTP action) → Loop(user\_upns)

&nbsp;  → CreateVariable(user\_upn, suspicious\_logins, mfa\_failures, brute\_force\_detected, findings)

&nbsp;  → QuerySignInLogs (HTTP GET: /auditLogs/signIns?$filter=userPrincipalName eq '{upn}')

&nbsp;  → UpdateVariable(parse results: flag suspicious IPs, MFA errors, brute force patterns)



&nbsp;Graph API endpoints:

&nbsp;- GET https://graph.microsoft.com/v1.0/auditLogs/signIns?$filter=userPrincipalName eq '{upn}' and createdDateTime ge {start\_date}



&nbsp;Detection logic (mapped from PwC Step 4):

&nbsp;- Suspicious logins: non-corporate IPs, unusual geolocations, odd UserAgent strings

&nbsp;- MFA errors: status.errorCode matching MFA failure codes

&nbsp;- Brute force: high volume of UserLoginFailed in short timeframe



&nbsp;Output: WorkflowCustomVariable.user\_upn, .suspicious\_logins, .mfa\_failures, .brute\_force\_detected, .findings



&nbsp;---

&nbsp;W3: BEC - Forwarding Rule Audit



&nbsp;File: bec-forwarding-rules.yaml

&nbsp;Template basis: assets/conditional.yaml



&nbsp;Parameters: user\_upns (array, required), tenant\_id, client\_id, client\_secret (strings, required), external\_domains\_watchlist (string, optional - comma-separated suspicious

&nbsp;domains)



&nbsp;Flow:

&nbsp;trigger → GetGraphToken → Loop(user\_upns)

&nbsp;  → CreateVariable(user\_upn, rules\_found, suspicious\_rules, rule\_details)

&nbsp;  → QueryInboxRules (HTTP GET: /users/{upn}/mailFolders/inbox/messageRules)

&nbsp;  → check\_external\_forwarding (condition: any rule forwards externally?)

&nbsp;      → \[Yes] → UpdateVariableSuspicious (record rule name, destination, folder)

&nbsp;      → \[No]  → UpdateVariableClean



&nbsp;Graph API endpoints:

&nbsp;- GET https://graph.microsoft.com/v1.0/users/{upn}/mailFolders/inbox/messageRules

&nbsp;- GET https://graph.microsoft.com/v1.0/users/{upn}/mailboxSettings (for ForwardingSmtpAddress)



&nbsp;Detection logic (mapped from PwC Step 3):

&nbsp;- Rules forwarding to external addresses (ForwardTo, BlindCopyTo, RedirectTo)

&nbsp;- Rules targeting suspicious folders: RSS, Archive, Junk Email, Conversation History

&nbsp;- Rules with keywords: "payment", "invoice", "wire", "bank"

&nbsp;- Transport rule modifications (New-TransportRule, Set-TransportRule)



&nbsp;Output: WorkflowCustomVariable.user\_upn, .rules\_found, .suspicious\_rules, .rule\_details



&nbsp;---

&nbsp;W4: BEC - Permission and OAuth Review



&nbsp;File: bec-permission-oauth-review.yaml

&nbsp;Template basis: assets/loop.yaml



&nbsp;Parameters: user\_upns (array, required), tenant\_id, client\_id, client\_secret (strings, required), check\_oauth\_apps (boolean, default true), check\_role\_assignments (boolean,

&nbsp;default true)



&nbsp;Flow:

&nbsp;trigger → GetGraphToken → Loop(user\_upns)

&nbsp;  → CreateVariable(user\_upn, permission\_changes, suspicious\_apps, role\_changes, findings)

&nbsp;  → QueryOAuthApps (HTTP GET: /users/{upn}/appRoleAssignments)

&nbsp;  → QueryRoleAssignments (HTTP GET: /users/{upn}/memberOf)

&nbsp;  → UpdateVariable(record findings)



&nbsp;Graph API endpoints:

&nbsp;- GET https://graph.microsoft.com/v1.0/users/{upn}/appRoleAssignments — OAuth apps

&nbsp;- GET https://graph.microsoft.com/v1.0/users/{upn}/oauth2PermissionGrants — delegated permissions

&nbsp;- GET https://graph.microsoft.com/v1.0/users/{upn}/memberOf — group/role membership

&nbsp;- GET https://graph.microsoft.com/v1.0/auditLogs/directoryAudits?$filter=category eq 'ApplicationManagement' — recent app consent events



&nbsp;Detection logic (mapped from PwC Steps 5-6):

&nbsp;- OAuth apps with Mail.Read, MailboxSettings.ReadWrite, Files.ReadWrite.All permissions

&nbsp;- Apps not in the standard M365 app list (PwC p.28 lists 26 default apps)

&nbsp;- Recent role additions to admin groups (Global, Exchange, Security admin)

&nbsp;- New user accounts (Add member to role/group events)



&nbsp;Output: WorkflowCustomVariable.user\_upn, .permission\_changes, .suspicious\_apps, .role\_changes, .findings



&nbsp;---

&nbsp;W5: BEC - IOC Enrichment and Blocking



&nbsp;File: bec-ioc-enrichment-blocking.yaml

&nbsp;Template basis: assets/loop-conditional.yaml (direct fit — this template was built for IOC type routing)



&nbsp;Parameters: iocs (array of objects: {ioc\_type, ioc\_value}, required; enum types: ip/domain/sha256/md5), auto\_block (boolean, default false), block\_policy (enum: detect/block,

&nbsp;default detect), case\_id (string, optional)



&nbsp;Flow:

&nbsp;trigger → Loop(iocs)

&nbsp;  → CreateVariable(ioc\_type, ioc\_value, devices\_found, enrichment\_result, blocked)

&nbsp;  → is\_ip (cel: data\['iocs.#.ioc\_type'] == 'ip')

&nbsp;      → GetDevicesIPv4 (PLACEHOLDER — action\_search.py --search "devices associated")

&nbsp;      → UpdateVariableIP

&nbsp;  → is\_domain (cel: data\['iocs.#.ioc\_type'] == 'domain')

&nbsp;      → GetDevicesDomain (PLACEHOLDER)

&nbsp;      → UpdateVariableDomain

&nbsp;  → is\_hash (cel: data\['iocs.#.ioc\_type'] == 'sha256' || ... == 'md5')

&nbsp;      → GetDevicesHash (PLACEHOLDER)

&nbsp;      → UpdateVariableHash



&nbsp;Reuses: CEL IOC type detection patterns from references/cel-expressions.md lines 169-191; cs.cidr.valid() for IP detection, cs.string.find() for SHA256 detection.



&nbsp;Output: WorkflowCustomVariable.ioc\_type, .ioc\_value, .devices\_found, .enrichment\_result, .blocked



&nbsp;---

&nbsp;W6: BEC - Identity Response



&nbsp;File: bec-identity-response.yaml

&nbsp;Template basis: assets/conditional.yaml (skip-group pattern from PHI-010)



&nbsp;Parameters: user\_upns (array, required), revoke\_sessions (boolean, default true), force\_password\_reset (boolean, default true), disable\_account (boolean, default false),

&nbsp;identity\_provider (enum: entra\_id/okta, default entra\_id), case\_id (string, optional)



&nbsp;Flow:

&nbsp;trigger → Loop(user\_upns)

&nbsp;  → CreateVariable(user\_upn, sessions\_revoked, password\_reset, account\_disabled)

&nbsp;  → GetUserIdentityContext (PLACEHOLDER — Identity Protection lookup)

&nbsp;  → check\_skip\_group (FQL expression: Groups:!\['SkipCrowdStrikeWorkflows'])

&nbsp;      → \[Proceed] → check\_provider (cel: data\['identity\_provider'] == 'entra\_id')

&nbsp;          → \[Entra ID] → EntraRevokeSessions → EntraPasswordReset → UpdateVariableEntra

&nbsp;          → \[Okta]     → OktaRevokeSessions  → OktaPasswordReset  → UpdateVariableOkta

&nbsp;      → \[Skip] → UpdateVariableSkipped



&nbsp;Plugin actions (all need PLACEHOLDER\_CONFIG\_ID):

&nbsp;- Okta: action\_search.py --vendor "Okta" --search "revoke", --search "password"

&nbsp;- Entra ID: action\_search.py --vendor "Microsoft" --search "revoke", --search "password"



&nbsp;Output: WorkflowCustomVariable.user\_upn, .sessions\_revoked, .password\_reset, .account\_disabled



&nbsp;---

&nbsp;W7: BEC - Endpoint Containment



&nbsp;File: bec-endpoint-containment.yaml

&nbsp;Template basis: assets/loop.yaml (direct fit — based on RAN-006/RAN-021)



&nbsp;Parameters: device\_ids (array, required), containment\_note (string, required), case\_id (string, optional)



&nbsp;Flow:

&nbsp;trigger → Loop(device\_ids)

&nbsp;  → CreateVariable(device\_id, contained, error)

&nbsp;  → ContainDevice (PLACEHOLDER — action\_search.py --search "contain")

&nbsp;  → UpdateVariable(record result)



&nbsp;Output: WorkflowCustomVariable.device\_id, .contained, .error



&nbsp;---

&nbsp;W8: BEC - Investigation Orchestrator



&nbsp;File: bec-orchestrator.yaml

&nbsp;Template basis: Custom sequential chain (no template match)



&nbsp;Parameters: case\_id, compromised\_users, incident\_date, incident\_summary, priority (same as W1), plus: tenant\_id, client\_id, client\_secret (for Graph API workflows), iocs

&nbsp;(optional array), auto\_block\_iocs (boolean, default false), auto\_remediate\_identity (boolean, default false), device\_ids\_to\_contain (optional array), identity\_provider (enum)



&nbsp;Flow:

&nbsp;trigger

&nbsp;  → ExecuteKickoff (Execute W1 — always runs)

&nbsp;  → ExecuteLoginAnalysis (Execute W2 — always runs)

&nbsp;  → ExecuteForwardingRules (Execute W3 — always runs)

&nbsp;  → ExecutePermissionOAuth (Execute W4 — always runs)

&nbsp;  → check\_iocs (cel: has(data\['iocs']) \&\& size(data\['iocs']) > 0)

&nbsp;      → \[Yes] ExecuteIOCEnrichment (Execute W5)

&nbsp;  → check\_remediate (cel: data\['auto\_remediate\_identity'] == true)

&nbsp;      → \[Yes] ExecuteIdentityResponse (Execute W6)

&nbsp;  → check\_containment (cel: has(data\['device\_ids\_to\_contain']) \&\& size(data\['device\_ids\_to\_contain']) > 0)

&nbsp;      → \[Yes] ExecuteContainment (Execute W7)

&nbsp;  → PrintSummary (consolidated results)



&nbsp;Investigation workflows (W1-W4) always run. Response workflows (W5-W7) are gated by parameters so the analyst must opt-in to remediation.



&nbsp;---

&nbsp;File Structure



&nbsp;examples/bec/

&nbsp;├── bec-investigation-kickoff.yaml        (W1)

&nbsp;├── bec-login-analysis.yaml               (W2)

&nbsp;├── bec-forwarding-rules.yaml             (W3)

&nbsp;├── bec-permission-oauth-review.yaml      (W4)

&nbsp;├── bec-ioc-enrichment-blocking.yaml      (W5)

&nbsp;├── bec-identity-response.yaml            (W6)

&nbsp;├── bec-endpoint-containment.yaml         (W7)

&nbsp;└── bec-orchestrator.yaml                 (W8)



&nbsp;Implementation Order



&nbsp;1. W1 (Kickoff) — zero external dependencies, Print data only

&nbsp;2. W7 (Containment) — native CrowdStrike, direct template match

&nbsp;3. W5 (IOC Enrichment) — native CrowdStrike, direct template match

&nbsp;4. W2 (Login Analysis) — HTTP action to Graph API

&nbsp;5. W3 (Forwarding Rules) — HTTP action to Graph API

&nbsp;6. W4 (Permission/OAuth) — HTTP action to Graph API

&nbsp;7. W6 (Identity Response) — plugin-dependent (Okta/Entra ID)

&nbsp;8. W8 (Orchestrator) — requires all sub-workflows



&nbsp;Key Reference Files



&nbsp;┌───────────────────────────────┬─────────────────────────────────────────────────────────┐

&nbsp;│             File              │                        Used For                         │

&nbsp;├───────────────────────────────┼─────────────────────────────────────────────────────────┤

&nbsp;│ assets/loop-conditional.yaml  │ Template for W5 (IOC type routing)                      │

&nbsp;├───────────────────────────────┼─────────────────────────────────────────────────────────┤

&nbsp;│ assets/conditional.yaml       │ Template for W3, W6 (condition branching)               │

&nbsp;├───────────────────────────────┼─────────────────────────────────────────────────────────┤

&nbsp;│ assets/loop.yaml              │ Template for W2, W4, W7 (bulk processing)               │

&nbsp;├───────────────────────────────┼─────────────────────────────────────────────────────────┤

&nbsp;│ assets/single-action.yaml     │ Template for W1 (chained actions)                       │

&nbsp;├───────────────────────────────┼─────────────────────────────────────────────────────────┤

&nbsp;│ references/yaml-schema.md     │ YAML field specs, data references, plugin format        │

&nbsp;├───────────────────────────────┼─────────────────────────────────────────────────────────┤

&nbsp;│ references/cel-expressions.md │ Condition logic, IOC detection patterns (lines 169-191) │

&nbsp;├───────────────────────────────┼─────────────────────────────────────────────────────────┤

&nbsp;│ references/best-practices.md  │ Loop patterns, version\_constraint rules, gotchas        │

&nbsp;├───────────────────────────────┼─────────────────────────────────────────────────────────┤

&nbsp;│ references/trigger-types.md   │ Trigger type YAML examples                              │

&nbsp;└───────────────────────────────┴─────────────────────────────────────────────────────────┘



&nbsp;Verification



&nbsp;For each workflow:

&nbsp;1. python scripts/validate.py --preflight-only <file>.yaml — check structure

&nbsp;2. python scripts/validate.py <file>.yaml — API schema validation

&nbsp;3. python scripts/import\_workflow.py <file>.yaml — import to CID

&nbsp;4. python scripts/execute.py --id <def\_id> --params '{...}' --wait — test execution

