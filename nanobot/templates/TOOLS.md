# Tool Usage Notes

Tool signatures are provided automatically via function calling.
This file documents non-obvious constraints and usage patterns.

## Prompt File Maintenance

- Keep `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, and `HEARTBEAT.md` in English.
- Keep user-facing conversation in Chinese by default.
- When updating prompt files, prefer small, targeted edits with clear reasons.
- Do not write unconfirmed assumptions as persistent rules.

## Personalization Workflow

- Use observed repeated behavior to propose durable rules.
- Ask for explicit confirmation before writing long-term preference changes.
- Write confirmed user preferences to `USER.md`.
- Write confirmed assistant identity/relationship style to `SOUL.md`.
- Write durable execution constraints to `AGENTS.md` or `TOOLS.md`.

## exec — Safety Limits

- Commands have a configurable timeout (default 60s)
- Dangerous commands are blocked (`rm -rf`, format, `dd`, `shutdown`, etc.)
- Output is truncated at 10,000 characters
- `restrictToWorkspace` config can limit file access to the workspace

## cron — Scheduled Reminders

- Refer to the cron skill for usage and best practices.
