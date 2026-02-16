# Security Skills for Claude Code

A collection of [Claude Code skills](https://docs.anthropic.com/en/docs/claude-code/skills) that automate security operations. Each skill teaches Claude how to work with a specific security platform — discovering available APIs, authoring configurations in the correct schema, validating against live environments, and deploying to production.

Skills are designed to be composable: use one skill to build a single automation, or combine several to implement end-to-end playbooks across your security stack.

## Available Skills

| Skill | Platform | What It Does |
|-------|----------|--------------|
| [fusion-workflow](skills/fusion-workflow/) | CrowdStrike Falcon Fusion SOAR | Create, validate, import, execute, and export Fusion SOAR workflows. Discovers actions via the live API, authors YAML with correct schema and data references, handles CEL expressions, loop/conditional patterns, and manages the full workflow lifecycle. |

## Getting Started

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) (or Skills compatible) CLI installed

### Setup

1. Clone the repository:

```bash
git clone https://github.com/eth0izzle/security-skills.git
cd security-skills
mv skills ~/.claude
```

2. (Optionally) Some skills may require configuration. For example, the CrowdStrike Fusion workflow can understand your live environment and optimise your workflows.

3. Start Claude Code in the project directory:

```bash
claude
```

4. Ask Claude to build something:

```
/plan
> Create a workflow that contains a device and sends a Slack notification
> Create multiple workflows based on the attached BEC Playbook
> What CrowdStrike actions are available to help with forensics capture?
```

Claude will automatically use the appropriate skill based on your request.

### Using a Skill Directly

Each skill lives under `.claude/skills/<skill-name>/` and includes:

- `SKILL.md` — the skill definition that Claude loads automatically
- `scripts/` — CLI tools for interacting with the platform API
- `references/` — schema docs, expression syntax, best practices
- `assets/` — templates and starter files

You can also use the scripts standalone without Claude Code:

```bash
# Example: search for actions in the CrowdStrike catalog
python .claude/skills/fusion-workflow/scripts/action_search.py --search "contain"

# Example: validate a workflow file
python .claude/skills/fusion-workflow/scripts/validate.py workflow.yaml
```

## Contributing

To add a new security skill:

1. Create a directory under `skills/<skill-name>/`
2. Write a `SKILL.md` that describes the skill's capabilities, prerequisites, and step-by-step workflow
3. Add scripts for API interaction, validation, and deployment
4. Add reference docs for schema, syntax, and best practices
5. Add template assets for common patterns
6. Submit a pull request

See the [fusion-workflow skill](skills/fusion-workflow/SKILL.md) as a reference implementation.

## License

MIT
