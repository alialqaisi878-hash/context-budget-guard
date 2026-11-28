# Context Budget Guard

Instruction-only edition of [Context Budget Guard](https://github.com/alialqaisi878-hash/context-budget-guard) for the Claude plugin directory.

Claude audits what your Claude Code setup loads before your first message (CLAUDE.md, skills, subagents, plugins, MCP servers), estimates the token cost, finds overlapping, duplicate and never-used skills, and offers fixes sorted by tokens saved. It changes nothing without your approval.

## Install

```
/plugin install context-budget-guard --marketplace alialqaisi878-hash/context-budget-guard
```

Then ask Claude: "Why is my Claude Code context so full?"

This edition ships no scripts. For CI checks, baselines and exact usage counts, use the command-line version in the main repository.

Privacy: see [PRIVACY.md](PRIVACY.md). No data leaves your machine.

License: MIT
