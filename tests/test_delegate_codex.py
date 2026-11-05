"""Cases for hooks/delegate-codex.py. Run: python3 -m unittest discover -s tests -v"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HOOK = os.path.join(os.path.dirname(__file__), "..", "hooks", "delegate-codex.py")


def run(subagent, prompt="do a thing", plugins=("codex@openai-codex",), raw=None):
    with tempfile.TemporaryDirectory() as d:
        reg = os.path.join(d, "installed_plugins.json")
        with open(reg, "w") as f:
            json.dump({"version": 2, "plugins": {p: [] for p in plugins}}, f)
        payload = raw if raw is not None else json.dumps(
            {"tool_name": "Agent", "tool_input": {"subagent_type": subagent, "prompt": prompt}}
        )
        env = dict(os.environ, ENG_LAWS_INSTALLED_PLUGINS=reg)
        return subprocess.run([sys.executable, HOOK], input=payload, text=True, capture_output=True, env=env)


class DelegateCodex(unittest.TestCase):
    def test_blocks_claude_subagents_when_codex_installed(self):
        for kind in ("Explore", "general-purpose", "eng-laws:verifier", "fork", "", None):
            r = run(kind)
            self.assertEqual(r.returncode, 2, kind)
            self.assertIn("codex:codex-rescue", r.stderr)

    def test_allows_codex_agent(self):
        for kind in ("codex:codex-rescue", "codex:other"):
            self.assertEqual(run(kind).returncode, 0, kind)

    def test_allows_claude_only_agents(self):
        for kind in ("web-fetch", "claude-code-guide", "statusline-setup"):
            self.assertEqual(run(kind).returncode, 0, kind)

    def test_marker_with_reason_allows(self):
        self.assertEqual(run("Explore", "[claude: needs Plane MCP] list tickets").returncode, 0)

    def test_marker_without_reason_does_not_allow(self):
        self.assertEqual(run("Explore", "[claude: ] list").returncode, 2)

    def test_allows_when_codex_not_installed(self):
        self.assertEqual(run("Explore", plugins=("caveman@caveman",)).returncode, 0)

    def test_fails_open_on_bad_payload(self):
        r = run("Explore", raw="not json")
        self.assertEqual(r.returncode, 0)
        self.assertIn("internal error", r.stderr)


if __name__ == "__main__":
    unittest.main()
