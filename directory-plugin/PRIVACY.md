# Privacy policy: Context Budget Guard

Last updated: 2026-11-28

Context Budget Guard is a skill that runs inside Claude on the user's own computer or in the user's own Claude session. It has no server, no analytics, and no network calls of its own.

## What it reads
- Claude Code configuration files: `CLAUDE.md` files, skill and subagent files, plugin manifests, and MCP server names from `.mcp.json` and `~/.claude.json`.
- Optionally, and only if the user agrees: local Claude Code session logs in `~/.claude/projects/`, to count how often each skill was used. Only counts are reported. Log contents are never quoted.
- On claude.ai: only a zip the user chooses to upload.

These files can contain personal data, such as names or email addresses written in a `CLAUDE.md`. The skill does not look for personal data and does not extract it.

## What it never reads
`.credentials.json`, `.env` files, API keys, or tokens. The skill tells Claude not to open them.

## What it stores
Nothing outside the user's own machine. The only file it may write is `context-report.md` in the user's project, which the user controls.

## What it sends
Nothing. The skill sends no data to the author or any third party. Data is processed by Claude under the user's existing agreement with Anthropic.

## Changes it makes
None without the user's explicit approval.

## Contact
Open an issue at https://github.com/alialqaisi878-hash/context-budget-guard/issues
