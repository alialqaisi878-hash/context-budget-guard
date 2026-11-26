# Context Budget Guard

**Find what eats your Claude Code context before you type a word, and fix it.**

Claude Code loads every `CLAUDE.md`, every skill and subagent description, and every MCP tool schema into each session. Add a few plugins and MCP servers and you can burn 20–60k tokens before your first prompt, hit usage limits faster, and get skills that silently stop triggering because their descriptions overlap.

Context Budget Guard is a skill plus a zero-dependency Python script that:

- **Estimates the always-loaded tokens** from CLAUDE.md (including `@imports` and `.claude/rules`), skills, subagents, plugins and MCP servers.
- **Ranks the biggest consumers**, including a per-plugin breakdown so you know which plugin to disable.
- **Finds overlapping skills**: pairs whose trigger descriptions are so similar that Claude may pick the wrong one or ignore one.
- **Finds what you never use**: reads your local session transcripts to count how often each skill and subagent actually runs, and flags whole plugins you never touch.
- **Catches broken skills**: missing descriptions, duplicate names, descriptions over the 1024-char limit.
- **Gives a fix list** sorted by tokens saved.
- **Tracks changes**: save a baseline, fix things, and see the before/after diff.
- **Runs in CI** with `--fail-on`, `--max-tokens` and `--max-increase`, so a PR can't quietly bloat everyone's context.

See [examples/sample-report.md](examples/sample-report.md) for a full report.

## Install

As a Claude Code plugin:

```
/plugin marketplace add alialqaisi878-hash/context-budget-guard
/plugin install context-budget-guard@context-budget-guard
```

Or as a plain skill: copy `skills/context-budget-guard/` into `~/.claude/skills/` (all projects) or `.claude/skills/` (one project).

## Use

Ask Claude: *"Why is my context so full?"* or *"Audit my skills for conflicts."* The skill runs the audit and walks you through fixes.

Or run the script directly (Python 3.10+, no packages):

```bash
python3 skills/context-budget-guard/scripts/cbg.py --project . --out context-report.md
python3 skills/context-budget-guard/scripts/cbg.py --json          # machine-readable
python3 skills/context-budget-guard/scripts/cbg.py --fail-on high  # CI gate

# before/after
python3 skills/context-budget-guard/scripts/cbg.py --save-baseline base.json
# ...make fixes...
python3 skills/context-budget-guard/scripts/cbg.py --compare base.json
```

Usage stats read `~/.claude/projects/*/*.jsonl` (last 30 days by default) on your machine only. Use `--no-usage` to skip.

CI: see [examples/github-action.yml](examples/github-action.yml). It compares each PR against its target branch and fails if the context grows by more than 1,500 tokens.

## Development

```bash
python3 -m unittest discover -s tests -v
```

See [CHANGELOG.md](CHANGELOG.md).

## Accuracy

Token counts are estimates (±25%). MCP tool schemas are only known at runtime, so each server is counted at a flat `--mcp-estimate` (default 4,000). Run `/context` inside Claude Code for exact numbers. Overlap detection is lexical (TF-IDF cosine on descriptions).

The script is read-only. It never changes your files.

## Roadmap

- Exact MCP cost by querying each server's tool list
- Team dashboard: track context budget across repos over time *(Pro)*
- PR comments with before/after diff *(Pro)*

## License

MIT
