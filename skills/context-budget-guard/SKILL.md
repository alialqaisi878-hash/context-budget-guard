---
name: context-budget-guard
description: Audit the tokens a Claude Code setup loads before the first message (CLAUDE.md, skills, subagents, plugins, MCP), find overlapping or never-used skills, and track changes. Use when limits run out fast, context feels full, or the user wants to clean up skills or plugins.
---

# Context Budget Guard

Find what is eating the context window before any work starts, and fix it.

## When to run

- The user says limits run out fast, sessions feel slow, or `/context` looks full.
- The user installed many skills, plugins or MCP servers and wants a cleanup.
- A skill "stopped working" or Claude picks the wrong skill (likely overlapping descriptions).
- Before committing changes to `CLAUDE.md`, `.claude/skills`, `.claude/agents` or `.mcp.json`.

## How to run

Run the bundled script from the project root. It is read-only and uses only the Python standard library.

```bash
python3 <this skill's directory>/scripts/cbg.py --project . --out context-report.md
```

Useful flags:

| Flag | Purpose |
|---|---|
| `--json` | Machine-readable output |
| `--similarity 0.35` | Overlap threshold between descriptions (raise to reduce noise) |
| `--memory-budget 2000` | Token budget for each CLAUDE.md before it is flagged |
| `--mcp-estimate 4000` | Assumed tokens per MCP server (real cost is only known at runtime) |
| `--fail-on high` | Exit 1 if any high finding (for CI) |
| `--max-tokens 20000` | Exit 1 if the always-loaded estimate exceeds this |
| `--usage-days 30` | How far back to read session transcripts for usage counts |
| `--no-usage` | Skip transcript scanning (e.g. in CI) |
| `--save-baseline cbg-baseline.json` | Save a snapshot before making fixes |
| `--compare cbg-baseline.json` | Show the before/after diff |
| `--max-increase 1500` | With `--compare`: exit 1 if tokens grew more than this |
| `--bundle config.zip` | Audit an uploaded zip of a project and/or `.claude` folder |

Usage counts come from local session transcripts in `~/.claude/projects/`. They never leave the machine. Usage findings need at least 5 sessions in the window (`--min-sessions`).

## Where this runs

- **Claude Code (terminal, desktop, IDE):** the full audit. The script reads `CLAUDE.md`, `.claude/`, `~/.claude/` and `.mcp.json` directly.
- **claude.ai, Claude apps, Cowork, or any sandbox without the user's config:** the script finds nothing and prints "Nothing to audit here". Do not report a clean bill of health. Instead:
  1. Tell the user this environment can't see their Claude Code setup.
  2. Offer two options: install the plugin in Claude Code (`/plugin marketplace add alialqaisi878-hash/context-budget-guard`), or upload a zip containing their project folder and/or their `~/.claude` folder. Remind them to leave out `.credentials.json` and any `.env` files.
  3. If they upload a zip, run `python3 <this skill's directory>/scripts/cbg.py --bundle <path-to-zip> --no-usage --out context-report.md`. Usage stats need session transcripts, so only include `~/.claude/projects` if they want usage counts (then drop `--no-usage`).
  4. If they can't upload files, ask them to paste their `CLAUDE.md` and the output of `/context` from Claude Code, and estimate from that by hand (about 4 characters per token).

## What to do with the report

0. Before suggesting fixes, save a baseline: add `--save-baseline cbg-baseline.json` to the first run.
1. Read `context-report.md`. Lead your answer with the total always-loaded estimate and the top 3 findings by tokens saved.
2. If MCP servers are listed, suggest the user run `/context` for exact numbers; the script only estimates them.
3. Offer concrete fixes, and apply them only after the user agrees:
   - **Big CLAUDE.md**: move the largest reference sections into a new project skill so they load on demand. Keep rules that apply to every task.
   - **Overlapping skills**: rewrite each description so it names a distinct situation (file type, input, stage of work), or merge the two skills.
   - **Duplicate names**: rename or remove one copy.
   - **Plugins or skills never used** (from usage stats): suggest disabling the plugin, or moving a project-only skill into that project's `.claude/skills`.
   - **Unused plugins or MCP servers**: disable them for this project (`/plugin` or `/mcp`, or `disabledMcpjsonServers` in `.claude/settings.json`).
   - **Long descriptions**: shorten to one or two sentences, about 80 tokens, and move detail into the skill body.
4. Never delete a user's skill, plugin or CLAUDE.md content without explicit approval. Prefer disabling over deleting.
5. After fixes, run again with `--compare cbg-baseline.json` and report the before/after total from the "Change since baseline" section.

## Limits

- Token counts are estimates (about ±25%); no tokenizer is bundled.
- MCP tool schemas are not fetched; each server is counted at a flat estimate.
- Overlap detection is lexical (TF-IDF on descriptions). It catches shared wording, not every semantic clash.
