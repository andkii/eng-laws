# Unattended runner: ticket in, reviewed PR out

Status: DRAFT 2 (after a `/code-review medium` of draft 1), awaiting plan approval (human gate 1). Design only; no runner code exists yet.

## 1. Problem

The owner wants to hand over a ticket (later a set of tickets, later a roadmap) and get a pull request back, with human gates only at plan approval and PR review. The owner does not watch sessions live; they review PRs and outputs and supply missing information. Today every session is started and steered by hand, and the Delegation law bans automatic review loops between agents "unless a human is watching", so an unattended run cannot be lawful as written.

The runner must also handle open-ended work (research, investigation, audits), not only code changes with checkable criteria.

## 2. Decisions this design makes

| # | Decision | Why |
|---|---|---|
| D1 | The runner lives in this repo, project-agnostic, next to the Delegation law and the guard it enforces. No project, tracker-vendor or repository names in code or docs. | The runner is not specific to one project, and this repo already ships hooks, tests and an agent as a plugin. |
| D2 | The runner is a Python standard-library script. It starts `claude -p` sessions; it does not call a model API itself. | The owner is on a subscription, so there are no API dollars to meter; Claude Code print mode is the supported non-interactive entry point. |
| D3 | State lives in the tracker (task text, plan, outcome comments) and in the branch and PR. The runner keeps only a local run log, never a source of truth. | Each session starts with a fresh context window ("Each Claude Code session begins with a fresh context window", memory docs); only what is written down carries over (Record Laws). |
| D4 | The tracker is reached through three configured commands (fetch, comment, set state), not a built-in client. | Keeps vendor code out of this repo. A project supplies the three commands for its tracker. A `local` file tracker ships for tests. |
| D5 | Two task kinds: `deliver` (code change, checkable criteria) and `investigate` (open-ended; output is a report committed on a branch). Both end at an open PR. | Open-ended work must stay possible. Its bound is the caps and a stated question, not mechanical criteria. |
| D6 | Caps are turns and wall-clock time, per session and per run. No USD cap. The runner removes `ANTHROPIC_API_KEY` from the sessions' environment so billing is not silently moved to an API key (precaution; its effect is not verified, [U]). | Subscription plan. `--max-turns` is documented (print mode only) and was observed to enforce (`claude -p ... --max-turns 1` ended with `subtype: error_max_turns`, Claude Code 2.1.318), although `claude --help` in that version does not list it. The wall-clock timeout is enforced by the runner. |
| D7 | The runner never merges, never pushes to the default branch, never closes a ticket. Enforced by three mechanisms, none of them instructions: the guard hook (extended here) for Bash; permission deny rules for `Write`/`Edit` on `.git/` and hook configuration; and no tracker access in any session (`--strict-mcp-config` with no MCP servers, so only the runner talks to the tracker, and it only sends the configured in-review state). | "Permission rules are enforced by Claude Code, not by the model" (permissions docs). The guard sees only Bash calls, so file-edit tools need their own rules. |
| D8 | The author, reviewer and checker agents are Claude Code sessions. Codex is not used by the runner until the guard is shown to apply to it. | The README states Codex hook coverage is not verified, and the Delegation law then limits Codex to read-only work. |

## 3. Data model

All instances conform to these dataclasses (module `runner/model.py`). Nothing else carries state between stages.

```python
@dataclass(frozen=True)
class Caps:                   # from runner.toml, fixed before the run starts
    session_turns: int        # --max-turns for each session
    session_seconds: int      # wall-clock timeout for each session
    run_turns: int            # sum over all sessions of one run
    run_seconds: int          # wall clock for the whole run

@dataclass(frozen=True)
class Task:
    id: str               # tracker id, opaque to the runner
    kind: Literal["deliver", "investigate"]
    title: str
    brief: str            # problem, rationale, constraints (from the tracker)
    plan: str             # the plan the owner approved at gate 1; given to the author
    criteria: list[str]   # deliver: checkable, one per line. investigate: the questions to answer
    plan_approved: bool   # set by the tracker command; runner refuses to start if false

@dataclass(frozen=True)
class StageResult:
    stage: Literal["author", "defect_review", "criteria_check", "fix", "final_check"]
    session_id: str | None
    turns: int | None
    seconds: float
    exit_code: int
    capped: bool          # stopped at a turn or time cap (`error_max_turns` or timeout)
    output: str           # reviewer/checker text, posted verbatim by the runner

Outcome = Literal["review_ready", "needs_input", "capped", "failed"]

@dataclass
class RunRecord:
    task_id: str
    branch: str
    worktree: str             # absolute path; the cwd of every stage
    pr_url: str | None
    outcome: Outcome
    stages: list[StageResult]
    deferred: list[str]       # work not done, from the final check
    unverifiable: list[str]   # criteria the reviewers could not check, each with the command to run
    questions: list[str]      # only for needs_input
```

Config (file `runner.toml`, parsed with `tomllib`):

```toml
default_branch = "main"
agent = "claude"              # only value in v1
report_dir = "docs"           # where an `investigate` report is written
caps = { session_turns = 0, session_seconds = 0, run_turns = 0, run_seconds = 0 }   # the owner sets these; 0 is rejected
tracker = { fetch = "...", comment = "...", set_state = "..." }   # commands, see 5
states = { in_progress = "...", in_review = "..." }               # every run ends in in_review; the comment carries the outcome
author_allowed_tools = ["Read", "Edit", "Write", "Bash(git add:*)", "Bash(git commit:*)", "Bash(git push:*)", "Bash(git status:*)", "Bash(git diff:*)", "Bash(gh pr create:*)", "Bash(gh pr view:*)"]
reviewer_allowed_tools = ["Read", "Grep", "Glob", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)"]
denied_tools = ["Write(.git/**)", "Edit(.git/**)", "Write(.claude/**)", "Edit(.claude/**)", "Write(hooks/**)", "Edit(hooks/**)"]   # [U] pattern syntax checked in selftest
```
Allowlists exclude interpreters and `git branch`, `git config`, `git worktree`, `git reset`; project test commands are added per project.

## 4. Flow

One run is one task. The runner is a state machine over the stages in `StageResult.stage`. Each stage is a fresh `claude -p` session. The first four steps and the last are runner code, not model work.

1. **Gate 1 check.** Fetch the task. Refuse unless `plan_approved` is true, the selftest marker (section 6) is current, all four caps are set, and `git fetch origin` succeeds.
2. **Claim and worktree.** Set the tracker state to in progress. The runner creates the worktree itself (`git worktree add .claude/worktrees/<slug> -b <branch> origin/<default_branch>`, or reuses the existing branch on a re-run) and records its absolute path. Every stage below is started with that path as its working directory, so every session's cwd is the worktree (Isolate writes). No stage uses `claude --worktree`.
3. **author.** `claude -p` with `--allowedTools` (`author_allowed_tools`), `--disallowedTools` (`denied_tools`), `--strict-mcp-config`, `--permission-prompts none`, `--max-turns`, `--output-format json`, under the wall-clock timeout. Never `--bare`: it skips hooks and CLAUDE.md, so the guard and the laws would not load (`claude --help`, 2.1.318: "Minimal mode: skip hooks"). A test fails if any stage command contains it. The brief carries the objective, constraints, criteria, the worktree path, and "write down questions instead of guessing". `deliver`: implement, add tests, run targeted checks, push the branch, open the PR. `investigate`: write the report under the project's docs path, cite a source for every claim, mark unsourced claims, push, open the PR.
4. **defect_review.** Fresh session with `reviewer_allowed_tools` (read-only; it runs `git diff` itself) and the prompt `/code-review medium`. `/code-review` runs in `-p` mode: observed on 2026-11-05 in a scratch repository (Claude Code 2.1.318), where it reported two seeded defects; on a trivial diff it returned "(none)". The reviewer is cold on a best-effort basis, as the laws say of `/code-review`. One reviewer, no fan-out. Empty output from a diff that has changes is treated as a failed stage, not as "no findings". The runner posts its output.
5. **criteria_check.** Fresh read-only session (`Read`, `Grep`, `Glob` only) given only the diff text, inlined in the prompt by the runner (`git diff origin/<default_branch>...HEAD`; a diff over the size limit in `runner.toml` stops the run as `failed`), and `criteria`. One line per criterion: `PASS`, `FAIL` or `UNVERIFIABLE` with `path:line` evidence. For `investigate` the criteria are the questions, and the check is that each is answered with a cited source. The runner posts it.
6. **fix.** At most one. A fresh session that gets the two review outputs, the diff and the `UNVERIFIABLE` commands, with the author tool set and the same denies. It runs those commands itself under the guard. The runner never executes a command taken from model output.
7. **final_check.** Repeat step 5 once. No second fix round. A criterion still `UNVERIFIABLE` is listed for the owner with its command and does not block `review_ready`.
8. **Record.** The runner computes the outcome with this precedence: `failed` (non-zero exit, empty review, oversize diff, tracker or guard error) over `capped` (any stage stopped at a session cap, or a run cap was reached; a capped run never counts as `review_ready` even if no `FAIL` was seen) over `needs_input` (the author wrote questions) over `review_ready` (the final check ran, has no `FAIL` and at least one `PASS`). It writes the delegation record into the PR description (what was delegated, to which agent, that the output passed both reviews and the final check, net lines, anything added that was not asked for), posts the summary with the outcome, turns and seconds per stage, deferred items and unverifiable commands, and sets the tracker state to `in_review`. If the tracker is unreachable, the record goes to the local log only.

Never reached by the runner: merge, push to the default branch, Done.

`needs_input`: the author session stops when it cannot proceed. The runner posts the questions and ends the run. The owner answers in the tracker and starts the run again; the new session reads the task and comments. This is the "provide missing information" path.

Re-runs are new runs on the same task. The runner reuses the existing branch and PR if present.

## 5. Tracker commands

Each is a command line from config, run without a shell. The runner passes JSON on stdin and reads JSON from stdout.

| Command | stdin | stdout |
|---|---|---|
| fetch | `{"id": "..."}` | the `Task` fields above except `caps` |
| comment | `{"id": "...", "body": "..."}` | none |
| set_state | `{"id": "...", "state": "..."}` | none |

A non-zero exit is a tracker failure. The run then stops with outcome `failed` and writes the record to the local log, because the tracker is unavailable.

## 6. Guard and selftest

- **Extend the guard** (`hooks/guard.py`, `hooks/rules.py`): add rules `gh-pr-merge` and `gh-api` to the registry and block those `gh` invocations at command position, in the same places the guard already looks (chains, `bash -c`, `eval`, wrappers). The guard already blocks pushes to `main`/`master`, `git commit` on them, and `core.hooksPath` changes. Cases go in `tests/test_guard.py`, including allow cases (`gh pr create`, `gh pr view`).
- **Selftest.** `runner selftest` attempts the blocked actions through a real `claude -p` session built by the same stage-command builder the runner uses, in a scratch repository: a push to the default branch of a local bare remote, `gh pr merge`, a `Write` to `.git/config`. It requires, for each, the guard's or the deny rule's own reason in the session output (the rule id, for example `gh-pr-merge`, so a command that merely failed does not count) and an unchanged remote. It also requires that every flag the runner uses is accepted by the installed CLI (`--max-turns`, `--permission-prompts`, `--strict-mcp-config`, `--allowedTools`, `--disallowedTools`) and that `/code-review` returns non-empty output on a seeded defect. On success it writes a marker keyed by the Claude Code version, the plugin version and a hash of the effective `runner.toml` allowlists and denies. The runner refuses to start without a current marker. This satisfies "Apply means tested" in the Delegation law and repeats whenever any of the three changes.
- **Fail closed.** The runner treats any guard, hook or tracker error as a stop. A crashing hook must exit 2, not 1 (a non-2 exit does not block).
- Out of scope, stated: commands run through other interpreters (`python -c`) are not parsed by the guard, so the allowlists exclude interpreters. `git push` of a feature branch (including a forced one) and deletion of feature branches are not blocked; the branch is the owner's to review and discard.

## 7. Law change

Delegation, "No unattended loops". Current text: "No automatic review loops between agents (for example a stop-time gate that re-invokes another agent) unless a human is watching." Proposed replacement:

> **Bounded unattended runs.** No automatic review loops between agents unless a human is watching, except a run that meets all of: (1) bounded: per unit of work, the two reviews these laws require (a defect review and a criteria check), at most one fix round, and one final verification, then stop; (2) capped: turn and wall-clock limits set before the run starts and enforced by the tool; (3) gated: it ends at a human gate (an open pull request) and cannot merge, push to the default branch or close the ticket, enforced by hooks or permission rules shown to block before the first run; (4) recorded: the run posts its outcome, turns used per stage and deferred work to the ticket.

Other laws are satisfied as written (worktree isolation, laws delivered via the project instruction file, cold reviewers with one reviewer each, `/code-review medium` ceiling, delegated output untrusted until verified).

## 8. Files added

| Path | Purpose |
|---|---|
| `runner/model.py` | dataclasses in section 3 |
| `runner/config.py` | parse `runner.toml` |
| `runner/stages.py` | build each `claude -p` command line; run with timeout; parse JSON output |
| `runner/tracker.py` | run the three commands; `local` file tracker for tests |
| `runner/run.py` | state machine and outcome computation; CLI: `run <id>`, `selftest` |
| `tests/test_runner.py` | non-model logic with a fake `claude` executable |
| `hooks/rules.py`, `hooks/guard.py` | two new rules |
| `ENGINEERING_LAWS.md`, `README.md`, `CHANGELOG.md` | law text, usage, release note |

## 9. Tests

- **Logic tests with a fake `claude`.** A stub executable that records its arguments and prints canned JSON. Cover: refuses without plan approval or a current marker; caps passed to every session; reviewers get read-only tools; one fix round maximum; outcome for each of `review_ready`, `needs_input`, `capped`, `failed`; tracker failure stops the run; no stage receives a merge-capable tool.
- **Guard corpus** for the two new rules.
- **Live selftest** in a scratch repository, run once by the owner after install. It uses subscription usage, small by design.
- The real end-to-end pilot (a real ticket) is not a test here; it is the first use.

## 10. Not decided or not verified

- [U] Exact `--allowedTools` pattern syntax for `Bash(...)` entries; the selftest is where it is checked.
- [U] Whether a tracker's API offers what the three commands need; each project writes its own commands.
- [U] A way to cap a run's share of subscription usage; none found in the Claude Code docs read. Turns and time (per session and per run) are the only bounds.
- [U] Whether removing `ANTHROPIC_API_KEY` from the environment is enough to keep billing on the subscription.
- [U] `--disallowedTools` pattern syntax for `Write`/`Edit` path rules; checked by the selftest.
- [U] Codex as a runner agent; blocked on guard coverage (README).
- Parallel runs of several tasks and roadmap intake are later stages and are not designed here.

## 11. Acceptance criteria

1. `ENGINEERING_LAWS.md` Delegation carries the text in section 7; `CHANGELOG.md` and `README.md` describe the runner and the new guard rules.
2. `python3 -m unittest discover -s tests` passes, including new guard cases (`gh pr merge`, `gh api` blocked in plain, chained, `bash -c` and wrapper forms; `gh pr create`, `gh pr view` allowed).
3. `tests/test_runner.py` passes and covers each bullet in section 9.
4. `runner selftest` on a scratch repository prints a block for the default-branch push and for `gh pr merge`, leaves the remote unchanged, and writes the marker.
5. Manual, needs a live model session (so not in CI): `python3 -m runner run T1 --config <scratch>/runner.toml` against the `local` tracker and a scratch repository with a local bare remote. Observable: the run log JSON has `outcome` set, `gh pr view` (or the remote branch for a local remote) shows the PR or branch with the delegation record, and the local tracker file shows state `in_review` and the posted comments.
6. Manual, same command with one `deliver` task file and one `investigate` task file: both reach an `outcome` through the same state machine.
7. `git diff origin/main...HEAD | grep -ci fightbot` prints `0`.
8. `tests/test_runner.py` asserts no stage command contains `--bare`, every stage sets `--max-turns` and a wall-clock timeout, and the author and reviewer tool lists contain no `gh pr merge`, `gh api` or interpreter entry.
