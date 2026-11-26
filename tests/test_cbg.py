"""Tests for Context Budget Guard. Run: python3 -m unittest discover -s tests"""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cbg", ROOT / "skills/context-budget-guard/scripts/cbg.py")
cbg = importlib.util.module_from_spec(spec)
sys.modules["cbg"] = cbg
spec.loader.exec_module(cbg)


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def skill(base: Path, folder: str, name: str, desc: str | None) -> None:
    fm = f"name: {name}\n" + (f"description: {desc}\n" if desc is not None else "")
    write(base / folder / "SKILL.md", f"---\n{fm}---\nBody of {name}.\n")


class Fixture:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home, self.proj = root / "home", root / "proj"
        self.proj.mkdir(parents=True)
        self.home.mkdir(parents=True)

    def run(self, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cbg.main(["--project", str(self.proj), "--home", str(self.home), "--json", *extra])
        return code, json.loads(buf.getvalue())

    def close(self):
        self.tmp.cleanup()


class TestTokens(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(cbg.est_tokens(""), 0)

    def test_english_roughly_quarter_of_chars(self):
        text = "The quick brown fox jumps over the lazy dog. " * 20
        self.assertTrue(len(text) / 6 < cbg.est_tokens(text) < len(text) / 2)

    def test_arabic_costs_more_per_char(self):
        ar = "هذا نص عربي للتجربة " * 20
        en = "this is english text " * 20
        self.assertGreater(cbg.est_tokens(ar) / len(ar), cbg.est_tokens(en) / len(en))


class TestFrontmatter(unittest.TestCase):
    def test_parses_folded_description(self):
        meta, body = cbg.split_frontmatter("---\nname: x\ndescription: >\n  line one\n  line two\n---\nbody")
        self.assertEqual(meta["name"], "x")
        self.assertEqual(meta["description"], "line one line two")
        self.assertEqual(body, "body")

    def test_no_frontmatter(self):
        self.assertEqual(cbg.split_frontmatter("hello"), ({}, "hello"))


class TestAudit(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def titles(self, data):
        return [x["title"] for x in data["findings"]]

    def test_clean_setup_has_no_findings(self):
        skill(self.f.home / ".claude/skills", "a", "pdf-tools", "Extract text from PDF files.")
        skill(self.f.home / ".claude/skills", "b", "commit-msg", "Write git commit messages from staged diffs.")
        code, data = self.f.run("--fail-on", "low")
        self.assertEqual(data["findings"], [])
        self.assertEqual(code, 0)

    def test_big_claude_md_and_imports(self):
        write(self.f.proj / "docs/extra.md", "extra words here " * 800)
        write(self.f.proj / "CLAUDE.md", "# Rules\nBe nice.\n# Reference\n" + "api detail " * 1500 + "\n@docs/extra.md\n")
        _, data = self.f.run()
        mem = [i for i in data["items"] if i["kind"] == "memory"][0]
        self.assertGreater(mem["always_tokens"], 4000, "import should be counted")
        self.assertTrue(any("CLAUDE.md" in t for t in self.titles(data)))

    def test_missing_description_and_duplicates(self):
        skill(self.f.home / ".claude/skills", "a", "dup", "Does one thing.")
        skill(self.f.proj / ".claude/skills", "b", "dup", "Does another thing entirely.")
        skill(self.f.home / ".claude/skills", "c", "nodesc", None)
        code, data = self.f.run("--fail-on", "high")
        t = self.titles(data)
        self.assertTrue(any("named 'dup'" in x for x in t))
        self.assertTrue(any("'nodesc' has no description" in x for x in t))
        self.assertEqual(code, 1)

    def test_overlap_detected_and_distinct_not(self):
        s = self.f.home / ".claude/skills"
        skill(s, "a", "pdf-tools", "Extract text and tables from PDF files, merge PDF documents.")
        skill(s, "b", "pdf-reader", "Read PDF documents and extract tables and text from PDF files.")
        skill(s, "c", "deploy", "Deploy the web app to production with Docker and Kubernetes.")
        _, data = self.f.run()
        overl = [x for x in self.titles(data) if "overlapping" in x]
        self.assertEqual(len(overl), 1)
        self.assertIn("pdf", overl[0])

    def test_mcp_servers_and_disabled(self):
        write(self.f.proj / ".mcp.json", json.dumps({"mcpServers": {k: {} for k in "abcde"}}))
        write(self.f.proj / ".claude/settings.json", json.dumps({"disabledMcpjsonServers": ["e"]}))
        _, data = self.f.run("--mcp-estimate", "1000")
        mcps = [i for i in data["items"] if i["kind"] == "mcp"]
        self.assertEqual(sorted(i["name"] for i in mcps), list("abcd"))
        self.assertTrue(any("4 MCP servers" in t for t in self.titles(data)))

    def test_plugin_name_from_manifest(self):
        plug = self.f.home / ".claude/plugins/cache/abc123"
        write(plug / ".claude-plugin/plugin.json", json.dumps({"name": "nice-plugin"}))
        skill(plug / "skills", "x", "x-skill", "Does x.")
        _, data = self.f.run()
        it = [i for i in data["items"] if i["name"] == "x-skill"][0]
        self.assertEqual(it["plugin"], "nice-plugin")
        self.assertEqual(it["scope"], "plugin")

    def test_max_tokens_gate(self):
        write(self.f.proj / "CLAUDE.md", "word " * 500)
        self.assertEqual(self.f.run("--max-tokens", "100")[0], 1)
        self.assertEqual(self.f.run("--max-tokens", "100000")[0], 0)


class TestUsage(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        s = self.f.home / ".claude/skills"
        skill(s, "a", "used-skill", "Format SQL queries.")
        skill(s, "b", "idle-skill", "Draw ASCII diagrams of architectures.")
        plug = self.f.home / ".claude/plugins/p1"
        write(plug / ".claude-plugin/plugin.json", json.dumps({"name": "idle-plugin"}))
        skill(plug / "skills", "c", "plug-skill", "Generate marketing slogans for products.")
        tdir = self.f.home / ".claude/projects" / cbg.project_slug(self.f.proj)
        for n in range(6):
            lines = [{"message": {"role": "user", "content": "hi"}}]
            if n == 0:
                lines.append({"message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "used-skill"}}]}})
            write(tdir / f"s{n}.jsonl", "\n".join(json.dumps(x) for x in lines) + "\n")

    def tearDown(self):
        self.f.close()

    def test_counts_and_findings(self):
        _, data = self.f.run()
        uses = {i["name"]: i["uses"] for i in data["items"]}
        self.assertEqual(uses["used-skill"], 1)
        self.assertEqual(uses["idle-skill"], 0)
        self.assertEqual(data["usage"]["sessions"], 6)
        t = [x["title"] for x in data["findings"]]
        self.assertTrue(any("Plugin 'idle-plugin' was never used" in x for x in t))
        self.assertTrue(any("1 skills/agents were never used" in x for x in t))

    def test_slash_command_counts_as_use(self):
        tdir = self.f.home / ".claude/projects" / cbg.project_slug(self.f.proj)
        write(tdir / "cmd.jsonl", json.dumps({"message": {"role": "user",
              "content": "<command-name>/idle-skill</command-name>"}}) + "\n")
        _, data = self.f.run()
        self.assertEqual({i["name"]: i["uses"] for i in data["items"]}["idle-skill"], 1)

    def test_too_few_sessions_no_usage_findings(self):
        _, data = self.f.run("--min-sessions", "50")
        self.assertFalse(any("never used" in x["title"] for x in data["findings"]))

    def test_no_usage_flag(self):
        _, data = self.f.run("--no-usage")
        self.assertIsNone(data["usage"])


class TestBaseline(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def tearDown(self):
        self.f.close()

    def test_compare_and_max_increase(self):
        base = Path(self.f.tmp.name) / "base.json"
        write(self.f.proj / "CLAUDE.md", "small file")
        self.f.run("--save-baseline", str(base))
        write(self.f.proj / "CLAUDE.md", "much bigger file " * 400)
        code, data = self.f.run("--compare", str(base), "--max-increase", "100")
        self.assertGreater(data["delta_tokens"], 100)
        self.assertEqual(code, 1)
        code, _ = self.f.run("--compare", str(base), "--max-increase", "100000")
        self.assertEqual(code, 0)

    def test_markdown_diff_section(self):
        base = Path(self.f.tmp.name) / "base.json"
        self.f.run("--save-baseline", str(base))
        skill(self.f.proj / ".claude/skills", "n", "new-skill", "Brand new helper for release notes.")
        out = Path(self.f.tmp.name) / "r.md"
        cbg.main(["--project", str(self.f.proj), "--home", str(self.f.home), "--compare", str(base), "--out", str(out)])
        md = out.read_text()
        self.assertIn("## Change since baseline", md)
        self.assertIn("| new-skill | skill | added |", md)


class TestBundleAndEmpty(unittest.TestCase):
    def test_empty_setup_explains_itself(self):
        f = Fixture()
        try:
            out = Path(f.tmp.name) / "r.md"
            cbg.main(["--project", str(f.proj), "--home", str(f.home), "--out", str(out)])
            self.assertIn("Nothing to audit here", out.read_text())
        finally:
            f.close()

    def test_bundle_zip_and_unsafe_paths(self):
        import zipfile
        with tempfile.TemporaryDirectory() as t:
            z = Path(t) / "cfg.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("my-app/CLAUDE.md", "word " * 3000)
                zf.writestr("my-app/.claude/skills/a/SKILL.md", "---\nname: a\ndescription: Does a.\n---\n")
                zf.writestr("my-app/.claude/agents/r.md", "---\nname: r\ndescription: Reviews.\n---\n")
                zf.writestr("../evil.txt", "nope")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cbg.main(["--bundle", str(z), "--json", "--no-usage"])
            data = json.loads(buf.getvalue())
            kinds = sorted(i["kind"] for i in data["items"])
            self.assertEqual(kinds, ["agent", "memory", "skill"])
            self.assertFalse((Path(t).parent / "evil.txt").exists())


if __name__ == "__main__":
    unittest.main()
