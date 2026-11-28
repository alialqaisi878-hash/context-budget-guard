---
name: context-budget-guard
description: Audit what a Claude Code setup loads before the first message (CLAUDE.md, skills, subagents, plugins, MCP servers), estimate the token cost, and find overlapping, duplicate or never-used skills. Use when usage limits run out fast, context feels full, or the user wants to clean up skills, plugins or MCP servers.
---

# Context Budget Guard

Find what fills the context window before any work starts, and fix it. You do the audit yourself with your normal file tools. Nothing is installed and nothing is changed without the user's approval.

## When to use

- The user says limits run out fast, sessions feel slow, or `/context` looks full.
- The user has many skills, plugins or MCP servers and wants a cleanup.
- A skill "stopped working", or Claude picks the wrong skill (often overlapping descriptions).
- Before committing changes to `CLAUDE.md`, `.claude/skills`, `.claude/agents` or `.mcp.json`.

## Step 0: check what you can see

- **In Claude Code:** you can read the user's files. Continue with step 1.
- **On claude.ai, Claude apps or Cowork:** you can't see the user's Claude Code setup. Say so plainly, don't report an empty all-clear. Offer two options:
  1. Run this skill inside Claude Code instead.
  2. Upload a zip of their project folder and their `~/.claude` folder. Tell them to leave out `.credentials.json`, `.env` files and anything with secrets. Then audit the unzipped files the same way.
- If they can't upload files, ask them to paste their `CLAUDE.md` and the output of `/context`, and estimate from that.

Never open or print `.credentials.json`, `.env`, or token values. From `~/.claude.json`, read only the `mcpServers` keys and `projects.<path>.mcpServers` / `disabledMcpjsonServers` keys, and only their names.

## Step 1: collect what loads every session

Look in these places (project = current working directory, home = `~`):

| Source | Where | What loads every session |
|---|---|---|
| Memory | `~/.claude/CLAUDE.md`, `CLAUDE.md` and `.claude/CLAUDE.md` in the project and each parent folder, `CLAUDE.local.md`, `.claude/rules/**/*.md`, plus any `@path` imports inside them | The whole file |
| Skills | `~/.claude/skills/*/SKILL.md`, `.claude/skills/*/SKILL.md`, and `~/.claude/plugins/**/skills/*/SKILL.md` | Only `name` + `description` from the frontmatter. The body loads when the skill is used. |
| Subagents | `~/.claude/agents/*.md`, `.claude/agents/*.md` | `name` + `description` |
| MCP servers | `.mcp.json` (`mcpServers`), `~/.claude.json` (`mcpServers` and `projects.<project path>.mcpServers`), minus names in `disabledMcpjsonServers` in `.claude/settings.json` | Every tool schema of every enabled server |

For plugin skills, find the plugin name in the nearest `.claude-plugin/plugin.json` above the skill.

## Step 2: estimate tokens

- Text: about **1 token per 4 characters** of English or code, about **1 per 2.2 characters** for Arabic and other non-Latin scripts. Use `wc -c` or the file length.
- Skills and subagents: count only the `name: description` text.
- MCP servers: tool schemas are only known at runtime. Count about **4,000 tokens per server** and tell the user to run `/context` for the real number.
- Say clearly that these are estimates (about ±25%).

## Step 3: find problems

Check each of these and note the tokens you could save:

1. **Big CLAUDE.md:** over ~2,000 tokens. Name its largest `#` sections.
2. **Missing description:** a skill or agent with no `description` will rarely or never trigger.
3. **Duplicate names:** two skills or two agents with the same `name`. Only one wins.
4. **Overlapping triggers:** compare descriptions pairwise. Flag pairs that share most of their key words or describe the same situation (for example "extract text from PDF files" and "read PDF documents and extract text"). Claude may pick the wrong one or quietly stop using one.
5. **Long descriptions:** over ~150 tokens, or over 1,024 characters (may be cut off). Aim for ~80 tokens.
6. **Many MCP servers:** 4 or more enabled for this project.
7. **Never-used skills (optional):** if the user agrees, search their session logs in `~/.claude/projects/*/*.jsonl` from the last 30 days for `"name":"Skill"` tool calls with `"skill":"<name>"`, and for `<command-name>/<name></command-name>`. A skill or whole plugin with zero uses over 5+ sessions is a candidate to disable. Only count; never quote log contents back to the user.

## Step 4: report

Write `context-report.md` in the project (or show it in chat on claude.ai) with:

1. **Total always-loaded estimate**, and a table by source: CLAUDE.md, skills, subagents, MCP.
2. **By plugin:** skills and tokens per plugin, biggest first.
3. **Top 10 biggest items.**
4. **Findings**, most severe first, each with: what's wrong, where, the fix, and tokens saved.

Lead your chat answer with the total and the top 3 fixes by tokens saved.

## Step 5: fix, only with approval

Offer fixes and apply them only after the user agrees:

- **Big CLAUDE.md:** move long reference sections into a new project skill so they load on demand.
- **Overlapping skills:** rewrite each description to name a distinct situation (file type, input, stage of work), or merge them.
- **Duplicates:** rename or remove one.
- **Unused plugins or MCP servers:** disable them for this project (`/plugin`, `/mcp`, or `disabledMcpjsonServers` in `.claude/settings.json`). Prefer disabling to deleting.
- **Long descriptions:** shorten to one or two sentences.

Never delete a user's skill, plugin or CLAUDE.md content without explicit approval. Before fixing, note the totals; after fixing, re-estimate and report before → after.

## Want CI checks and exact usage stats?

The open-source command-line version adds a CI gate that fails pull requests which grow the context, baselines with before/after diffs, and exact usage counts: https://github.com/alialqaisi878-hash/context-budget-guard
