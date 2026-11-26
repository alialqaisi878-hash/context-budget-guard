# Context Budget Report

Project: `~/my-app`  ·  Context Budget Guard v0.1.0

**Estimated always-loaded context: ~28,201 tokens** (before your first message; excludes Claude Code's own system prompt).

| Source | Count | ~Tokens every session |
|---|---:|---:|
| CLAUDE.md / rules | 1 | 8,118 |
| Skill descriptions | 4 | 65 |
| Subagent descriptions | 1 | 18 |
| MCP servers (estimate) | 5 | 20,000 |

## Biggest consumers

| # | Item | Kind | Scope | ~Tokens |
|---:|---|---|---|---:|
| 1 | CLAUDE.md | memory | project | 8,118 |
| 2 | github | mcp | project | 4,000 |
| 3 | linear | mcp | project | 4,000 |
| 4 | notion | mcp | project | 4,000 |
| 5 | sentry | mcp | project | 4,000 |
| 6 | slack | mcp | project | 4,000 |
| 7 | pdf-tools | skill | user | 30 |
| 8 | pdf-reader | skill | user | 18 |
| 9 | reviewer | agent | project | 18 |
| 10 | pdf-tools | skill | project | 14 |

## Findings (6)

### 1. 🔴 CLAUDE.md is ~8118 tokens, loaded every session · saves ~6,118 tokens

Largest sections: 'API reference' (~8106), 'Project rules' (~5).

**Fix:** Move reference material (long how-tos, API notes, style guides) into a skill so it loads only when relevant; keep CLAUDE.md to rules that apply to every task.

### 2. 🔴 skill 'commit-msg' has no description

~/.claude/skills/commit-msg/SKILL.md

**Fix:** Without a description Claude cannot decide when to use it. Add one sentence: what it does + when to use it.

### 3. 🔴 2 skills are named 'pdf-tools'

~/.claude/skills/pdf-tools/SKILL.md; .claude/skills/review/SKILL.md

**Fix:** Only one will win. Remove or rename the duplicates.

### 4. 🔴 'pdf-tools' and 'reviewer' have overlapping triggers (71% similar)

Shared terms: style, pull, request, issue, review, bugs. .claude/skills/review/SKILL.md vs .claude/agents/reviewer.md

**Fix:** Claude may pick the wrong one or silently stop using one. Make each description name a distinct situation (input type, file type, stage of work), or merge them.

### 5. 🟠 5 MCP servers enabled for this project · saves ~10,000 tokens

Every tool schema from every server is loaded up front. Servers: github, linear, notion, sentry, slack

**Fix:** Disable servers this project does not use (`/mcp` or `disabledMcpjsonServers` in .claude/settings.json), and run `/context` to see their real cost.

### 6. 🟠 'pdf-reader' and 'pdf-tools' have overlapping triggers (52% similar)

Shared terms: pdf, document, file, extract, text, table. ~/.claude/skills/pdf-reader/SKILL.md vs ~/.claude/skills/pdf-tools/SKILL.md

**Fix:** Claude may pick the wrong one or silently stop using one. Make each description name a distinct situation (input type, file type, stage of work), or merge them.

---

Token counts are estimates (±25%). MCP servers are counted at ~4,000 tokens each because their tool schemas are only known at runtime; run `/context` inside Claude Code for exact numbers.
