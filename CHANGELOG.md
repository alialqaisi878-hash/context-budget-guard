# Changelog

## 0.3.0

- **Works on claude.ai and Claude apps.** When no Claude Code config is visible, the report explains why instead of showing an empty "all clear", and the skill walks the user through uploading a zip.
- `--bundle ZIP` audits an uploaded zip of a project and/or `.claude` folder (unsafe paths are skipped).
- Uploadable skill zip for claude.ai in `dist/`.
- Plugin icon and marketplace description; passes `claude plugin validate --strict`.

## 0.2.0

- **Usage stats.** Reads Claude Code session transcripts (`~/.claude/projects/*.jsonl`) to count how often each skill and subagent is actually invoked. Flags whole plugins and individual skills that were never used in the last 30 days, with the tokens you'd save. New flags: `--no-usage`, `--usage-days`, `--usage-scope`, `--min-sessions`.
- **Baselines.** `--save-baseline FILE` and `--compare FILE` show a before/after diff: total tokens, items added/removed/changed, new and fixed problems. `--max-increase N` fails CI when a change grows the context by more than N tokens.
- New "Uses" column in the biggest-consumers table.
- The CI example now compares each PR against its target branch.
- Test suite (18 tests) and GitHub Actions on Python 3.10, 3.12 and 3.13.

## 0.1.0

- First release: token estimates for CLAUDE.md (with `@imports`), skills, subagents, plugins and MCP servers; overlapping-trigger detection; duplicate and missing descriptions; per-plugin breakdown; `--fail-on` and `--max-tokens` for CI.
