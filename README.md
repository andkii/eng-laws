# eng-laws

Source of truth for engineering laws that apply across all projects using AI-assisted development.

## What this is

These conventions govern how work is created, executed, reviewed, and recorded in any project where Claude Code (or equivalent agentic tools) are part of the development workflow. They are not tied to any specific stack, language, or codebase.

Each project's `CLAUDE.md` incorporates the laws from `ENGINEERING_LAWS.md` via Claude Code's native `@import` syntax, alongside project-specific overrides (verification commands, architecture notes, resource lifecycle rules, etc.).

## How to use in a project

Claude Code supports `@path/to/file.md` imports in `CLAUDE.md`. Add this repo as a git submodule at `.eng-laws/` and reference it at the top of the project's `CLAUDE.md`:

```markdown
@.eng-laws/ENGINEERING_LAWS.md

# Project-specific overrides below
```

Or, if both repos live under the same parent directory (e.g. `~/dev/`):

```markdown
@../eng-laws/ENGINEERING_LAWS.md
```

The laws are read through the import, not copied. A submodule or a pinned checkout stays on one version until you deliberately bump it, so updating is a conscious step.

## What goes here vs in project CLAUDE.md

| Here (`ENGINEERING_LAWS.md`) | Per-project `CLAUDE.md` |
|---|---|
| Record Laws (session close, work tracking) | Verification command (`./scripts/check`, `pytest`, etc.) |
| Worktree workflow | Resource lifecycle rules (Redis, DB, HTTP patterns) |
| Ticket discipline (Plane in the examples; any tracker works) | Architecture overview |
| Code quality laws (read-before-claim, declarative/imperative, debt-in-band) | Domain-specific key rules |
| Review gate rules | Project structure |

## Plugin

This repo is also a Claude Code plugin and a single-plugin marketplace (`.claude-plugin/`). It enforces mechanically what the laws state in prose.

| Component | Path | What it does |
|---|---|---|
| Bash guard hook | `hooks/guard-bash.sh` (wrapper) and `hooks/guard.py`, registered in `hooks/hooks.json` | Blocks `git revert`; `--no-verify` (including `commit -n`, `am -n`, abbreviations, `-c core.hooksPath`, and `git config core.hooksPath`); any push whose destination is `main`/`master`; and `git commit` while the branch is `main`/`master` |
| Verifier agent | `agents/verifier.md` | Read-only (`Read, Grep, Glob`) evaluator that checks acceptance criteria against the changed files with `file:line` evidence |
| Block log and report | `hooks/blocklog.py`, `hooks/rules.py`, `hooks/report.py` | Records each block (rule id, git subcommand, time, redacted command) so false positives can be counted per rule; see "Block log" below |
| Guard tests | `tests/test_guard.py` | Regression corpus of block and allow cases. Run `python3 -m unittest discover -s tests` |

**Guard requirements and limits.**
- Requires `python3` (standard library only). It fails closed: a missing `python3`, an unreadable payload, or an unparseable git command blocks the call with a message instead of silently allowing it.
- It tokenizes the command and judges only what sits at command position, so quoted text, `echo` arguments, comments and heredoc bodies never trigger it. It looks inside `if`/`for`/`while`/`case` bodies, `{ }` groups, functions, `$(...)`, backticks, `bash -c`, `eval`, `find -exec`, and wrappers such as `sudo`, `env`, `timeout`, `xargs`.
- It tracks the working directory through `cd`, `pushd`/`popd`, `( )` subshell scope, `git -C`, `env -C`, and a fixed set of expansions: `$PWD`, `$HOME`, `$(pwd)`, `$(git rev-parse --show-toplevel)`, quoted or not. A command substitution never splits the command it sits in.
- It tracks a branch moved by a `git switch`/`checkout` earlier in the same command, for the directory where the switch ran (path checkouts, `--detach` and `checkout -` are handled), and a worktree created by `git worktree add` earlier in the same command. `git push origin "$(git branch --show-current)"` resolves to the current branch.
- It follows simple shell variables assigned at the top level of the same command (`BRANCH=feat/x; git push origin "$BRANCH"`, also `export`/`declare`/`readonly`/`local`) in push destinations and in `cd`, `pushd`, `git -C`, `env -C` and `git worktree add` targets, a `${VAR:-main}` default in a push destination (in a `cd` or `-C` target a `${VAR:-x}` fails closed), `cd -`, and a `mkdir x && cd x` target under an existing repository. `$PWD`, `$(pwd)` and the toplevel inside a value mean the directory at the moment of assignment, not the directory current when the variable is used. `unset NAME`, a `for NAME in` loop, `select NAME in` and `read NAME` forget an earlier assignment (the variable then counts as unassigned). A `for` loop over a literal path is therefore blocked for `git commit` (fails closed), and a push to a loop variable is allowed because an unassigned variable is out of scope. A value longer than 4,096 characters is dropped, so a self-doubling chain such as `A=$A$A` cannot exhaust memory; the variable then fails closed.
- Not followed: an assignment inside an `if`/`for`/`{ }`/function body, which means the guard silently keeps using the earlier top-level value (or none), `+=`, an empty value (`D=` is not treated as `cd` to home), the `env --chdir=` spelling, a literal loop list (`for b in main master`), a value holding `refs/heads/...` or `HEAD:...`, and `$(...)` values other than the current-branch queries. A checkout that creates a local branch from `origin/<name>` (DWIM or `--track`) counts as a switch.
- When the directory or branch cannot be determined, `git commit` and a push without a refspec are blocked with a message asking for a literal branch name and an absolute path. Known friction: a bare command substitution as a push destination (`git push origin $(some-command)`), any `$VAR` with no assignment in the same command, or any other `$(...)`, in a `cd`/`-C` target, and `git init x && cd x && git commit` outside a repository (the new repository does not exist yet when the guard runs). Inside a repository, `git init x`/`git clone … x` followed by `cd x && git commit` is judged against the parent repository's branch, not the new one. A variable with no assignment in the same command (loop variable, value from the environment) is not judged: it is variable indirection, out of scope below.
- It is a guard against mistakes, not a sandbox. Out of scope: other variable indirection (`g=git; $g revert`), aliases, scripts, `ssh`/`watch`/`parallel`/`env -S` wrappers, `GIT_*` environment overrides, and deliberate obfuscation. Edits made through tools other than Bash are not covered.
- It blocks `--no-verify` unconditionally, which is stricter than the law's "unless the user explicitly requests it". If the user requests it, the user runs the command themselves (the `!` prefix) or disables the plugin for that session.

A plugin-root `CLAUDE.md` is not loaded as context, so the laws still reach a project through the `@import` above; the plugin adds enforcement only.

Install: `claude plugin marketplace add andkii/eng-laws#<tag>` then `claude plugin install eng-laws@eng-laws`.

### Block log

Every block appends one JSON line to `${CLAUDE_PLUGIN_DATA}/blocks.jsonl`. Claude Code exports `CLAUDE_PLUGIN_DATA` to hook processes (hooks reference, "Command hook fields"); it resolves to `~/.claude/plugins/data/<id>/` (for this plugin, `~/.claude/plugins/data/eng-laws-eng-laws/`), is kept across plugin updates, and is deleted when the plugin is uninstalled from its last location. It is outside every repository. If the variable is unset or the write fails, logging is skipped silently and the block still happens.

Each entry holds: `id` (8 hex chars, used to mark it), `ts` (UTC), `rule` (an id from `hooks/rules.py`), `sub` (git subcommand, `null` when unknown), `cwd` (basename only), and `cmd`. `cmd` is only the blocked git invocation's own words (at most 16), never the rest of the command line, so a secret in a chained `curl`, `docker login` or `export` cannot reach the log. For a command that would not parse (`unparseable-git`) it is the first 4 words from the first `git`; for an unreadable payload it is `null`. Each word is redacted on its own: a word containing whitespace (a commit message, a header value) becomes `<text>`, URL userinfo, values of `name=value` words whose name contains `pass`, `token`, `secret`, `key`, `auth` or `credential`, well-known token prefixes, and any 32+ character token-like string become `<redacted>`, `$HOME` becomes `~`, and the whole is capped at 200 characters. This is best effort: a secret passed as a bare git argument (`git commit -m hunter2`), or in an option whose name carries no secret word (`--push-option=secret=abc`), survives, and other absolute paths (for example `-C /path`) are kept, so treat the file as sensitive (it is created mode 0600). Long hex strings such as commit SHAs are redacted too. There is no rotation; delete the file to reset it.

Read it (the path defaults to the data directory when `CLAUDE_PLUGIN_DATA` is set; otherwise pass `--file`):

```sh
python3 hooks/report.py --file ~/.claude/plugins/data/eng-laws-eng-laws/blocks.jsonl summary
python3 hooks/report.py --file ... list --unreviewed
python3 hooks/report.py --file ... mark <id> --note "dry run, not a real revert"          # false positive (default)
python3 hooks/report.py --file ... mark <id> --verdict true-block
```

`summary` prints blocks, false positives (`fp`), confirmed true blocks (`true`) and unreviewed (`open`) per rule and per day. Marks are appended to the same file and the last mark for an id wins.

### Delegating to Codex (machine setup)

The laws reach Claude Code through the `@import` above and Codex through its own global instruction file. See the Delegation law for the policy. One-time setup per machine:

1. **Install the official plugin, pinned.** `claude plugin marketplace add openai/codex-plugin-cc#v1.0.6 --scope user`, then `claude plugin install codex@openai-codex --scope user`, then `/codex:setup` (and `codex login` if it asks). Do not run `/codex:setup --enable-review-gate`: it makes two agents review each other in a loop and can drain usage quickly.
2. **Give Codex the same laws.** `ln -s ~/.claude/eng-laws/ENGINEERING_LAWS.md ~/.codex/AGENTS.md`. Codex reads `~/.codex/AGENTS.md` first and then each project `AGENTS.md` from the repository root down. Checked on 2026-10-27 with a read-only `codex exec` in a scratch repository whose `AGENTS.md` held a marker: Codex quoted the marker and the Cold Review law, so it followed the symlink and merged both files. Bumping the pinned checkout updates Claude and Codex together.
3. **Raise the instruction cap.** The Codex docs say it stops adding instruction files once their combined size reaches `project_doc_max_bytes` (32 KiB by default). Files load global first and then from the repository root down, so the project's files are the last added and the first to be cut. The laws alone are about 19 KB (19,304 bytes at this version). Set `project_doc_max_bytes = 65536` in `~/.codex/config.toml`; the cap and the cut order come from the docs and were not exercised.
4. **Keep a project's `AGENTS.md` to project parameters.** Do not copy the laws into it; two copies drift.

The eng-laws plugin also registers a `PreToolUse` hook on the `Agent` tool (`hooks/delegate-codex.py`). When `codex@...` appears in `~/.claude/plugins/installed_plugins.json`, it blocks any subagent that is not `codex:*`, except `web-fetch`, `claude-code-guide`, `statusline-setup`, and briefs containing `[claude: <reason>]`. The reasons stay in the transcript, so Codex and Claude delegations can be counted later. It allows everything when Codex is not installed and when it hits an internal error. The registry file path was observed on a working install; it is not in the Claude Code documentation.

What the plugin does: `/codex:review` and `/codex:adversarial-review` are read-only; `/codex:rescue` hands a task to Codex, by default with a `workspace-write` sandbox and no approval prompts, in the git root of the session's working directory. It may tighten the wording of your task with its own prompting skill, but it adds no laws, so the laws arrive only through the files above. Its result comes back unreviewed. The rescue agent adds `--write` by default; to keep a rescue read-only, say so in the request (diagnosis or research only, no edits), which the agent's instructions treat as a reason to omit `--write`. The command has no working-directory option, so write delegation needs a Claude session started inside the worktree.

Not verified: whether the guard in this repository can be registered as a Codex `PreToolUse` hook (the Codex docs describe such an event with the same stdin JSON and exit-2 contract), whether Codex rules cover commands run inside its sandbox, and whether a worktree under a trusted project inherits the project's trust. Until those are verified, use Codex for read-only work only, per the Delegation law.

### Versioning

`version` in `.claude-plugin/plugin.json` is the pin: installed repos stay on it until it changes. Every change that alters hook or agent behavior bumps `version` and gets a `CHANGELOG.md` entry. Add the marketplace at a tag (`#v0.1.0`) so adopters move only when they choose to.

## Repos using these conventions

Adoption status is tracked in each adopting project, not here.
