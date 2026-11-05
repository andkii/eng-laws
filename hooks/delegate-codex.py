#!/usr/bin/env python3
"""PreToolUse hook for the Agent tool: route subagent work to Codex when the
Codex plugin is installed (Delegation law, "Default to the available delegate").

Denies (exit 2, reason on stderr) any subagent whose type is not a Codex agent,
unless the type is in CLAUDE_ONLY, the brief carries the bypass marker, or the
Codex plugin is not installed. Fails open on any internal error: this is a
routing policy, not a safety guard.
"""
import json
import os
import re
import sys

# Subagents that need Claude-only capabilities (web fetch, Claude Code docs, status line settings).
CLAUDE_ONLY = {"web-fetch", "claude-code-guide", "statusline-setup"}
# A brief containing this marker, with a reason, is let through.
MARKER = re.compile(r"\[claude-only:\s*\S[^\]]*\]")
CODEX_PLUGIN_PREFIX = "codex@"


def codex_installed():
    path = os.environ.get("ENG_LAWS_INSTALLED_PLUGINS") or os.path.expanduser(
        "~/.claude/plugins/installed_plugins.json"
    )
    with open(path) as f:
        data = json.load(f)
    plugins = data.get("plugins", data)
    return any(name.startswith(CODEX_PLUGIN_PREFIX) for name in plugins)


def main():
    try:
        payload = json.load(sys.stdin)
        tool_input = payload.get("tool_input") or {}
        subagent = tool_input.get("subagent_type") or ""
        prompt = tool_input.get("prompt") or ""
        if subagent.startswith("codex:") or subagent in CLAUDE_ONLY:
            return 0
        if MARKER.search(prompt):
            return 0
        if not codex_installed():
            return 0
    except Exception as exc:  # noqa: BLE001 - fail open, but say so
        print(f"eng-laws delegate-codex: internal error ({exc!r}); allowing.", file=sys.stderr)
        return 0
    shown = subagent or "(default)"
    print(
        f"eng-laws: subagent '{shown}' blocked. The Codex plugin is installed, so subagent work "
        "goes to Codex: use subagent_type 'codex:codex-rescue' (read-only tasks: say so in the brief). "
        "If the task needs Claude-only tools, put '[claude-only: <reason>]' in the brief. "
        "See the Delegation law.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
