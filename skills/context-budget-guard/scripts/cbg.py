#!/usr/bin/env python3
"""Context Budget Guard: audit what a Claude Code setup loads into context.

Scans CLAUDE.md memory files, skills, subagents and MCP servers for a project,
estimates their always-loaded token cost, finds skills/agents whose trigger
descriptions overlap, and prints a prioritized fix list.

Standard library only. Token counts are estimates (no tokenizer is bundled).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field, asdict
from pathlib import Path

VERSION = "0.2.0"

# ---------------------------------------------------------------- tokens

_WORD = re.compile(r"\w+", re.UNICODE)


def est_tokens(text: str) -> int:
    """Rough token estimate. Mixes a char-based and a word-based heuristic so
    that code, prose and non-Latin scripts all land in a sensible range."""
    if not text:
        return 0
    chars = len(text)
    words = len(_WORD.findall(text))
    non_ascii = sum(1 for c in text if ord(c) > 127)
    # Non-Latin scripts (e.g. Arabic) tokenize far less efficiently.
    by_chars = chars / (4.0 if non_ascii < chars * 0.3 else 2.2)
    by_words = words * 1.33
    return int(round(max(by_chars, by_words)))


# ---------------------------------------------------------------- model


@dataclass
class Item:
    kind: str          # memory | skill | agent | command | mcp
    name: str
    path: str
    scope: str         # user | project | plugin | local
    always_tokens: int  # loaded into every session
    ondemand_tokens: int = 0  # loaded only when invoked
    description: str = ""
    plugin: str = ""
    uses: int | None = None   # invocations found in session transcripts (None = not measured)
    notes: list = field(default_factory=list)


@dataclass
class Finding:
    severity: str      # high | medium | low
    title: str
    detail: str
    fix: str
    tokens_at_stake: int = 0


# ---------------------------------------------------------------- parsing

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)


def split_frontmatter(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    meta: dict = {}
    key = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        kv = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
        if kv and not line.startswith((" ", "\t")):
            key = kv.group(1).strip()
            val = kv.group(2).strip()
            if val in ("|", ">", "|-", ">-"):
                val = ""
            meta[key] = val.strip("\"'")
        elif key:  # continuation of a multi-line value
            meta[key] = (meta[key] + " " + line.strip()).strip()
    return meta, text[m.end():]


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


_IMPORT = re.compile(r"(?:^|\s)@((?:~|\.{1,2})?/?[\w./-]+\.\w+)")


def expand_imports(path: Path, home: Path, seen: set, depth: int = 0) -> str:
    """CLAUDE.md supports `@path` imports (max depth 5). Inline them."""
    if depth > 5 or path in seen:
        return ""
    seen.add(path)
    text = read(path)
    out = [text]
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        for ref in _IMPORT.findall(line):
            target = Path(ref.replace("~", str(home), 1)) if ref.startswith("~") else (path.parent / ref)
            target = target.resolve()
            if target.is_file():
                out.append(expand_imports(target, home, seen, depth + 1))
    return "\n".join(out)


# ---------------------------------------------------------------- collectors


def collect_memory(project: Path, home: Path) -> list[Item]:
    items: list[Item] = []
    candidates: list[tuple[Path, str]] = [(home / ".claude" / "CLAUDE.md", "user")]
    # Claude Code walks up from cwd loading CLAUDE.md files.
    chain = [project, *project.parents]
    for d in reversed(chain):
        if d == home or d == home.parent:
            continue
        for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
            candidates.append((d / name, "local" if name.endswith("local.md") else "project"))
    rules = project / ".claude" / "rules"
    if rules.is_dir():
        candidates += [(p, "project") for p in sorted(rules.rglob("*.md"))]
    seen: set = set()
    for p, scope in candidates:
        if not p.is_file() or p.resolve() in seen:
            continue
        text = expand_imports(p.resolve(), home, seen)
        items.append(Item("memory", label(p, project, home), str(p), scope, est_tokens(text)))
        items[-1].notes.append(("sections", top_sections(text)))
    return items


def label(p: Path, project: Path, home: Path) -> str:
    for base, prefix in ((project, ""), (home, "~/")):
        try:
            return prefix + str(p.resolve().relative_to(base))
        except ValueError:
            pass
    return str(p)


def top_sections(text: str, n: int = 3) -> list[tuple[str, int]]:
    parts = re.split(r"^(#{1,3} .+)$", text, flags=re.M)
    sections = []
    for i in range(1, len(parts) - 1, 2):
        sections.append((parts[i].lstrip("# ").strip(), est_tokens(parts[i + 1])))
    return sorted(sections, key=lambda s: -s[1])[:n]


def skill_dirs(project: Path, home: Path) -> list[tuple[Path, str]]:
    dirs = [(home / ".claude" / "skills", "user"), (project / ".claude" / "skills", "project")]
    plug = home / ".claude" / "plugins"
    if plug.is_dir():
        for d in plug.rglob("skills"):
            if d.is_dir():
                dirs.append((d, "plugin"))
    return dirs


def collect_skills(project: Path, home: Path) -> list[Item]:
    items = []
    seen = set()
    for base, scope in skill_dirs(project, home):
        if not base.is_dir():
            continue
        for sk in sorted(base.glob("*/SKILL.md")):
            rp = sk.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            meta, body = split_frontmatter(read(sk))
            name = meta.get("name") or sk.parent.name
            desc = meta.get("description", "")
            it = Item("skill", name, str(sk), scope,
                      always_tokens=est_tokens(f"{name}: {desc}"),
                      ondemand_tokens=est_tokens(body), description=desc,
                      plugin=plugin_name(sk) if scope == "plugin" else "")
            items.append(it)
    return items


def collect_agents(project: Path, home: Path) -> list[Item]:
    items = []
    for base, scope in ((home / ".claude" / "agents", "user"), (project / ".claude" / "agents", "project")):
        if not base.is_dir():
            continue
        for f in sorted(base.glob("*.md")):
            meta, body = split_frontmatter(read(f))
            name = meta.get("name") or f.stem
            desc = meta.get("description", "")
            items.append(Item("agent", name, str(f), scope,
                              always_tokens=est_tokens(f"{name}: {desc}"),
                              ondemand_tokens=est_tokens(body), description=desc))
    return items


def _load_json(p: Path) -> dict:
    try:
        return json.loads(read(p) or "{}")
    except json.JSONDecodeError:
        return {}


def collect_mcp(project: Path, home: Path, per_server: int) -> list[Item]:
    servers: dict[str, tuple[str, str]] = {}
    pj = project / ".mcp.json"
    for n in _load_json(pj).get("mcpServers", {}) or {}:
        servers[n] = ("project", str(pj))
    cj = home / ".claude.json"
    data = _load_json(cj)
    for n in data.get("mcpServers", {}) or {}:
        servers.setdefault(n, ("user", str(cj)))
    proj_cfg = (data.get("projects", {}) or {}).get(str(project), {}) or {}
    for n in proj_cfg.get("mcpServers", {}) or {}:
        servers.setdefault(n, ("local", str(cj)))
    disabled = set(proj_cfg.get("disabledMcpjsonServers", []) or [])
    settings = _load_json(project / ".claude" / "settings.json")
    disabled |= set(settings.get("disabledMcpjsonServers", []) or [])
    items = []
    for n, (scope, path) in sorted(servers.items()):
        if n in disabled:
            continue
        it = Item("mcp", n, path, scope, always_tokens=per_server)
        it.notes.append(("estimated", True))
        items.append(it)
    return items


# ---------------------------------------------------------------- usage

_CMD = re.compile(r"<command-name>/?([\w:.-]+)</command-name>")


@dataclass
class Usage:
    sessions: int = 0
    days: int = 0
    skills: Counter = field(default_factory=Counter)
    agents: Counter = field(default_factory=Counter)


def project_slug(project: Path) -> str:
    """Claude Code stores transcripts under ~/.claude/projects/<path with non-alphanumerics as '-'>."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(project))


def _short(name: str) -> str:
    return name.split(":")[-1].strip().lower()


def collect_usage(project: Path, home: Path, days: int, scope: str) -> Usage:
    """Count Skill and subagent invocations in Claude Code session transcripts (*.jsonl)."""
    import time
    root = home / ".claude" / "projects"
    u = Usage(days=days)
    if not root.is_dir():
        return u
    dirs = [root / project_slug(project)] if scope == "project" else [d for d in root.iterdir() if d.is_dir()]
    cutoff = time.time() - days * 86400
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.glob("*.jsonl"):
            try:
                if f.stat().st_mtime < cutoff:
                    continue
                fh = f.open(encoding="utf-8", errors="replace")
            except OSError:
                continue
            u.sessions += 1
            with fh:
                for line in fh:
                    if '"Skill"' not in line and "command-name" not in line and "subagent_type" not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    content = (rec.get("message") or {}).get("content")
                    if isinstance(content, str):
                        for m in _CMD.findall(content):
                            u.skills[_short(m)] += 1
                        continue
                    if not isinstance(content, list):
                        continue
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "tool_use":
                            inp = b.get("input") or {}
                            if b.get("name") == "Skill" and inp.get("skill"):
                                u.skills[_short(str(inp["skill"]))] += 1
                            elif b.get("name") in ("Agent", "Task") and inp.get("subagent_type"):
                                u.agents[_short(str(inp["subagent_type"]))] += 1
                        elif b.get("type") == "text":
                            for m in _CMD.findall(b.get("text") or ""):
                                u.skills[_short(m)] += 1
    return u


def apply_usage(items: list[Item], u: Usage) -> None:
    for it in items:
        if it.kind == "skill":
            it.uses = u.skills.get(it.name.lower(), 0)
        elif it.kind == "agent":
            it.uses = u.agents.get(it.name.lower(), 0)


# ---------------------------------------------------------------- overlap

_STOP = set("""a an the and or of to in on for with by from as at is are be this that
these those it its use used using when whenever user users ask asks asked wants want
any all also into via your you can will should do does skill skills claude code
task tasks help helps e g eg such like etc not only before after""".split())


def _terms(text: str) -> list[str]:
    out = []
    for w in _WORD.findall(text.lower()):
        if len(w) < 3 or w in _STOP or w.isdigit():
            continue
        for suf in ("ing", "ed", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[: -len(suf)]
                break
        out.append(w)
    return out


def overlaps(items: list[Item], threshold: float) -> list[tuple[Item, Item, float, list[str]]]:
    docs = [(it, Counter(_terms(it.description))) for it in items if it.description]
    n = len(docs)
    if n < 2:
        return []
    df = Counter()
    for _, c in docs:
        df.update(c.keys())
    vecs = []
    for it, c in docs:
        v = {t: (1 + math.log(f)) * math.log((n + 1) / (df[t] + 0.5)) for t, f in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append((it, {t: x / norm for t, x in v.items()}))
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            a, va = vecs[i]
            b, vb = vecs[j]
            shared = set(va) & set(vb)
            sim = sum(va[t] * vb[t] for t in shared)
            if sim >= threshold:
                top = sorted(shared, key=lambda t: -(va[t] * vb[t]))[:6]
                pairs.append((a, b, sim, top))
    return sorted(pairs, key=lambda p: -p[2])


# ---------------------------------------------------------------- analysis


def analyze(items: list[Item], pairs, args) -> list[Finding]:
    f: list[Finding] = []
    long_desc: list[Item] = []
    for it in items:
        if it.kind == "memory" and it.always_tokens > args.memory_budget:
            secs = dict(it.notes).get("sections", [])
            biggest = ", ".join(f"'{s}' (~{t})" for s, t in secs) or "n/a"
            f.append(Finding("high" if it.always_tokens > 2 * args.memory_budget else "medium",
                             f"{it.path} is ~{it.always_tokens} tokens, loaded every session",
                             f"Largest sections: {biggest}.",
                             "Move reference material (long how-tos, API notes, style guides) into a skill "
                             "so it loads only when relevant; keep CLAUDE.md to rules that apply to every task.",
                             it.always_tokens - args.memory_budget))
        if it.kind in ("skill", "agent"):
            if not it.description:
                f.append(Finding("high", f"{it.kind} '{it.name}' has no description",
                                 f"{it.path}", "Without a description Claude cannot decide when to use it. "
                                 "Add one sentence: what it does + when to use it.", 0))
            elif len(it.description) > 1024:
                f.append(Finding("medium", f"{it.kind} '{it.name}' description is {len(it.description)} chars",
                                 "Descriptions over 1024 chars may be truncated, and they are paid for in every session.",
                                 "Cut it to one or two sentences; move detail into the body.", it.always_tokens - 120))
            elif it.always_tokens > 150:
                long_desc.append(it)
    if long_desc:
        long_desc.sort(key=lambda i: -i.always_tokens)
        shown = ", ".join(f"{i.name} (~{i.always_tokens})" for i in long_desc[:8])
        more = f" and {len(long_desc) - 8} more" if len(long_desc) > 8 else ""
        f.append(Finding("low", f"{len(long_desc)} skill/agent descriptions are over 150 tokens",
                         f"These are loaded in every session even when never used: {shown}{more}.",
                         "Aim for under ~80 tokens each: trigger phrases + one-line purpose; move detail into the body.",
                         sum(i.always_tokens - 80 for i in long_desc)))
    names = Counter((it.kind, it.name) for it in items if it.kind in ("skill", "agent"))
    for (kind, name), c in names.items():
        if c > 1:
            paths = [it.path for it in items if it.kind == kind and it.name == name]
            f.append(Finding("high", f"{c} {kind}s are named '{name}'", "; ".join(paths),
                             "Only one will win. Remove or rename the duplicates.", 0))
    for a, b, sim, terms in pairs:
        sev = "high" if sim >= 0.6 else "medium"
        f.append(Finding(sev, f"'{a.name}' and '{b.name}' have overlapping triggers ({sim:.0%} similar)",
                         f"Shared terms: {', '.join(terms)}. {a.path} vs {b.path}",
                         "Claude may pick the wrong one or silently stop using one. Make each description name "
                         "a distinct situation (input type, file type, stage of work), or merge them.", 0))
    mcps = [it for it in items if it.kind == "mcp"]
    if len(mcps) >= args.mcp_warn:
        f.append(Finding("high" if len(mcps) >= 2 * args.mcp_warn else "medium",
                         f"{len(mcps)} MCP servers enabled for this project",
                         "Every tool schema from every server is loaded up front. Servers: " + ", ".join(m.name for m in mcps),
                         "Disable servers this project does not use (`/mcp` or `disabledMcpjsonServers` in "
                         ".claude/settings.json), and run `/context` to see their real cost.",
                         sum(m.always_tokens for m in mcps) // 2))
    f += usage_findings(items, args)
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(f, key=lambda x: (order[x.severity], -x.tokens_at_stake))


def usage_findings(items: list[Item], args) -> list[Finding]:
    u: Usage | None = getattr(args, "_usage", None)
    if not u or u.sessions < args.min_sessions:
        return []
    f: list[Finding] = []
    span = f"{u.sessions} session{'s' if u.sessions != 1 else ''} over the last {u.days} days"
    # Whole plugins that were never used: the biggest, simplest win.
    by_plugin: dict[str, list[Item]] = {}
    for it in items:
        if it.kind == "skill" and it.plugin:
            by_plugin.setdefault(it.plugin, []).append(it)
    idle_plugins = set()
    for name, sk in by_plugin.items():
        if all((i.uses or 0) == 0 for i in sk):
            idle_plugins.add(name)
            tok = sum(i.always_tokens for i in sk)
            f.append(Finding("high" if tok >= 2000 else "medium",
                             f"Plugin '{name}' was never used ({len(sk)} skills, ~{tok:,} tokens)",
                             f"None of its skills were invoked in {span}.",
                             f"Disable it with `/plugin` (or uninstall it) unless you need it; re-enable any time.", tok))
    idle = [i for i in items if i.kind in ("skill", "agent") and i.uses == 0 and i.plugin not in idle_plugins]
    if idle:
        idle.sort(key=lambda i: -i.always_tokens)
        shown = ", ".join(f"{i.name} (~{i.always_tokens})" for i in idle[:10])
        more = f" and {len(idle) - 10} more" if len(idle) > 10 else ""
        tok = sum(i.always_tokens for i in idle)
        f.append(Finding("medium" if tok >= 1000 else "low",
                         f"{len(idle)} skills/agents were never used (~{tok:,} tokens)",
                         f"Not invoked in {span}: {shown}{more}.",
                         "Remove the ones you don't need, or move project-specific ones into that project's "
                         ".claude/skills so they stop loading everywhere.", tok))
    return f


# ---------------------------------------------------------------- report


def plugin_name(skill_md: Path) -> str:
    """Name from the nearest plugin.json above the skill, else the folder above skills/."""
    d = skill_md.parent
    for _ in range(6):
        d = d.parent
        for cand in (d / ".claude-plugin" / "plugin.json", d / "plugin.json"):
            if cand.is_file():
                n = _load_json(cand).get("name")
                if n:
                    return n
        if d.name == "plugins":
            break
    parts = skill_md.parts
    return parts[parts.index("skills") - 1] if "skills" in parts else "?"


def render_md(project: Path, items: list[Item], findings: list[Finding], args) -> str:
    total = sum(i.always_tokens for i in items)
    by_kind = Counter()
    for i in items:
        by_kind[i.kind] += i.always_tokens
    L = [f"# Context Budget Report", "",
         f"Project: `{project}`  ·  Context Budget Guard v{VERSION}", "",
         f"**Estimated always-loaded context: ~{total:,} tokens** "
         f"(before your first message; excludes Claude Code's own system prompt).", "",
         "| Source | Count | ~Tokens every session |", "|---|---:|---:|"]
    labels = {"memory": "CLAUDE.md / rules", "skill": "Skill descriptions", "agent": "Subagent descriptions",
              "mcp": "MCP servers (estimate)"}
    for k in ("memory", "skill", "agent", "mcp"):
        cnt = sum(1 for i in items if i.kind == k)
        L.append(f"| {labels[k]} | {cnt} | {by_kind[k]:,} |")
    plugins = Counter()
    pcount = Counter()
    for i in items:
        if i.plugin:
            name = i.plugin
            plugins[name] += i.always_tokens
            pcount[name] += 1
    if plugins:
        L += ["", "## By plugin", "", "Disabling a plugin you don't use in this project removes all of its skills at once.", "",
              "| Plugin | Skills | ~Tokens every session |", "|---|---:|---:|"]
        for name, tok in plugins.most_common():
            L.append(f"| {name} | {pcount[name]} | {tok:,} |")
    u: Usage | None = getattr(args, "_usage", None)
    measured = bool(u and u.sessions >= args.min_sessions)
    if u:
        L += ["", f"Usage: scanned {u.sessions} session transcripts from the last {u.days} days"
              + ("." if measured else f" (need {args.min_sessions}+ for usage findings).")]
    L += ["", "## Biggest consumers", "", "| # | Item | Kind | Scope | ~Tokens | Uses |", "|---:|---|---|---|---:|---:|"]
    for n, it in enumerate(sorted(items, key=lambda i: -i.always_tokens)[: args.top], 1):
        uses = str(it.uses) if (measured and it.uses is not None) else "–"
        L.append(f"| {n} | {it.name} | {it.kind} | {it.scope} | {it.always_tokens:,} | {uses} |")
    L += ["", f"## Findings ({len(findings)})", ""]
    if not findings:
        L.append("No problems found. Nice and lean.")
    icon = {"high": "🔴", "medium": "🟠", "low": "🟡"}
    for n, fd in enumerate(findings, 1):
        save = f" · saves ~{fd.tokens_at_stake:,} tokens" if fd.tokens_at_stake > 0 else ""
        L += [f"### {n}. {icon[fd.severity]} {fd.title}{save}", "", fd.detail, "", f"**Fix:** {fd.fix}", ""]
    L += ["---", "",
          f"Token counts are estimates (±25%). MCP servers are counted at ~{args.mcp_estimate:,} tokens each "
          "because their tool schemas are only known at runtime; run `/context` inside Claude Code for exact numbers."]
    return "\n".join(L)


# ---------------------------------------------------------------- baseline


def snapshot(project: Path, items: list[Item], findings: list[Finding]) -> dict:
    return {"version": VERSION, "project": str(project),
            "always_loaded_tokens": sum(i.always_tokens for i in items),
            "items": {f"{i.kind}:{i.scope}:{i.name}": i.always_tokens for i in items},
            "findings": sorted({f.title for f in findings if f.severity != "low"})}


def render_diff(base: dict, cur: dict) -> tuple[str, int]:
    delta = cur["always_loaded_tokens"] - base["always_loaded_tokens"]
    sign = "+" if delta > 0 else ""
    L = ["## Change since baseline", "",
         f"**{base['always_loaded_tokens']:,} → {cur['always_loaded_tokens']:,} tokens ({sign}{delta:,})**", ""]
    bi, ci = base.get("items", {}), cur["items"]
    rows = []
    for k in sorted(set(bi) | set(ci)):
        a, b = bi.get(k), ci.get(k)
        if a == b:
            continue
        kind, _, name = k.split(":", 2)
        status = "added" if a is None else "removed" if b is None else "changed"
        d = (b or 0) - (a or 0)
        rows.append((abs(d), f"| {name} | {kind} | {status} | {'+' if d > 0 else ''}{d:,} |"))
    if rows:
        L += ["| Item | Kind | Change | Δ Tokens |", "|---|---|---|---:|"]
        L += [r for _, r in sorted(rows, key=lambda r: -r[0])[:25]]
        L.append("")
    new = [t for t in cur["findings"] if t not in set(base.get("findings", []))]
    fixed = [t for t in base.get("findings", []) if t not in set(cur["findings"])]
    if new:
        L += ["**New problems:**", *[f"- {t}" for t in new], ""]
    if fixed:
        L += ["**Fixed:**", *[f"- {t}" for t in fixed], ""]
    if not rows and not new and not fixed:
        L += ["No changes.", ""]
    return "\n".join(L), delta


# ---------------------------------------------------------------- main


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit the context budget of a Claude Code setup.")
    ap.add_argument("--project", default=os.getcwd(), help="project root (default: cwd)")
    ap.add_argument("--home", default=str(Path.home()), help="home dir holding ~/.claude (default: ~)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    ap.add_argument("--out", help="write the report to this file")
    ap.add_argument("--similarity", type=float, default=0.35, help="overlap threshold 0..1 (default 0.35)")
    ap.add_argument("--memory-budget", type=int, default=2000, help="CLAUDE.md token budget (default 2000)")
    ap.add_argument("--mcp-estimate", type=int, default=4000, help="assumed tokens per MCP server (default 4000)")
    ap.add_argument("--mcp-warn", type=int, default=4, help="warn at this many MCP servers (default 4)")
    ap.add_argument("--top", type=int, default=10, help="rows in the biggest-consumers table")
    ap.add_argument("--fail-on", choices=["high", "medium", "low", "never"], default="never",
                    help="exit 1 if any finding at or above this severity (for CI)")
    ap.add_argument("--max-tokens", type=int, default=0, help="exit 1 if always-loaded estimate exceeds this")
    ap.add_argument("--no-usage", action="store_true", help="skip scanning session transcripts")
    ap.add_argument("--usage-days", type=int, default=30, help="transcript window in days (default 30)")
    ap.add_argument("--usage-scope", choices=["all", "project"], default="all",
                    help="count usage across all projects (default) or only this one")
    ap.add_argument("--min-sessions", type=int, default=5, help="sessions needed before flagging unused items")
    ap.add_argument("--save-baseline", metavar="FILE", help="save a snapshot to compare against later")
    ap.add_argument("--compare", metavar="FILE", help="show changes since a saved baseline")
    ap.add_argument("--max-increase", type=int, default=0,
                    help="with --compare: exit 1 if always-loaded tokens grew by more than this")
    ap.add_argument("--version", action="version", version=VERSION)
    args = ap.parse_args(argv)

    project = Path(args.project).expanduser().resolve()
    home = Path(args.home).expanduser().resolve()
    items = (collect_memory(project, home) + collect_skills(project, home)
             + collect_agents(project, home) + collect_mcp(project, home, args.mcp_estimate))
    args._usage = None
    if not args.no_usage:
        args._usage = collect_usage(project, home, args.usage_days, args.usage_scope)
        apply_usage(items, args._usage)
    pairs = overlaps([i for i in items if i.kind in ("skill", "agent")], args.similarity)
    findings = analyze(items, pairs, args)
    total = sum(i.always_tokens for i in items)
    snap = snapshot(project, items, findings)
    diff_md, delta = "", 0
    if args.compare:
        base = _load_json(Path(args.compare))
        if base:
            diff_md, delta = render_diff(base, snap)
        else:
            print(f"warning: could not read baseline {args.compare}", file=sys.stderr)
    if args.save_baseline:
        Path(args.save_baseline).write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.json:
        out = json.dumps({"version": VERSION, "project": str(project), "always_loaded_tokens": total,
                          "items": [{k: v for k, v in asdict(i).items() if k != "notes"} for i in items],
                          "findings": [asdict(f) for f in findings],
                          "usage": ({"sessions": args._usage.sessions, "days": args._usage.days}
                                    if args._usage else None),
                          "delta_tokens": delta if args.compare else None}, indent=2, ensure_ascii=False)
    else:
        out = render_md(project, items, findings, args)
        if diff_md:
            head, sep, rest = out.partition("\n## ")
            out = head + diff_md + sep + rest
        out = out.replace(str(project) + os.sep, "").replace(str(home) + os.sep, "~/")
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
    else:
        print(out)

    rank = {"high": 0, "medium": 1, "low": 2, "never": -1}
    if args.fail_on != "never" and any(rank[f.severity] <= rank[args.fail_on] for f in findings):
        return 1
    if args.max_tokens and total > args.max_tokens:
        return 1
    if args.compare and args.max_increase and delta > args.max_increase:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
