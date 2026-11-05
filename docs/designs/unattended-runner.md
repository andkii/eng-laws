# Unattended runner: ticket in, reviewed PR out

Status: DRAFT 1, awaiting plan approval (human gate 1). Design only; no runner code exists yet.

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
| D6 | Caps are turns and wall-clock time. No USD cap. | Subscription plan. `--max-turns` is documented (print mode only); a wall-clock timeout is enforced by the runner. |
| D7 | The runner never merges, never pushes to the default branch, never closes a ticket. Enforced by the guard hook (extended here), not by instruction. | "Permission rules are enforced by Claude Code, not by the model" (permissions docs). |
| D8 | The author, reviewer and checker agents are Claude Code sessions. Codex is not used by the runner until the guard is shown to apply to it. | The README states Codex hook coverage is not verified, and the Delegation law then limits Codex to read-only work. |

## 3. Data model

All instances conform to these dataclasses (module `runner/model.py`). Nothing else carries state between stages.

```python
@dataclass(frozen=True)
class Caps:
    turns: int            # --max-turns for each session
    seconds: int          # wall-clock timeout for each session

@dataclass(frozen=True)
class Task:
    id: str               # tracker id, opaque to the runner
    kind: Literal["deliver", "investigate"]
    title: str
    brief: str            # problem, rationale, constraints (from the tracker)
    criteria: list[str]   # deliver: checkable, one per line. investigate: the questions to answer
    plan_approved: bool   # set by the tracker command; runner refuses to start if false
    caps: Caps

@dataclass(frozen=True)
class StageResult:
    stage: Literal["author", "defect_review", "criteria_check", "fix", "final_check"]
    session_id: str | None
    turns: int | None
    seconds: float
    exit_code: int
    capped: bool          # stopped at turns or seconds
    output: str           # reviewer/checker text, posted verbatim by the runner

Outcome = Literal["review_ready", "needs_input", "capped", "failed"]

@dataclass
class RunRecord:
    task_id: str
    branch: str
    pr_url: str | None
    outcome: Outcome
    stages: list[StageResult]
    deferred: list[str]       # work not done, from the final check
    questions: list[str]      # only for needs_input
```

Config (file `runner.toml`, parsed with `tomllib`):

```toml
default_branch = "main"
agent = "claude"              # only value in v1
tracker = { fetch = "...", comment = "...", set_state = "..." }   # commands, see 5
author_allowed_tools = ["Read", "Edit", "Write", "Bash(git:*)", "Bash(gh pr create:*)", "Bash(gh pr view:*)"]  # [U] syntax checked in selftest
reviewer_allowed_tools = ["Read", "Grep", "Glob"]
states = { in_progress = "...", in_review = "..." }
```

## 4. Flow

One run is one task. The runner is a state machine over the stages in `StageResult.stage`. Each stage is a fresh `claude -p` session. The first four steps and the last are runner code, not model work.

1. **Gate 1 check.** Fetch the task. Refuse unless `plan_approved` is true, the selftest marker (section 6) is current, the work tree is clean and the default branch is fetched.
2. **Claim.** Set the tracker state to in progress.
3. **author.** `claude -p --worktree <slug>` with `author_allowed_tools`, `--permission-prompts none`, `--max-turns`, JSON output, under the wall-clock timeout. The brief carries the objective, constraints, criteria, the worktree path, and "write down questions instead of guessing". `deliver`: implement, add tests, run targeted checks, push the branch, open the PR. `investigate`: write the report under the project's docs path, cite a source for every claim, mark unsourced claims, push, open the PR.
4. **defect_review.** Fresh read-only session given only the diff (`/code-review medium`, which runs in `-p` mode: tested in a scratch repository). One reviewer, no fan-out. The runner posts its output.
5. **criteria_check.** Fresh read-only session given only the diff and `criteria`. One line per criterion: `PASS`, `FAIL` or `UNVERIFIABLE` with `path:line` evidence. For `investigate` the criteria are the questions, and the check is that each is answered with a cited source. The runner posts it.
6. **fix.** At most one. A fresh session that gets the two review outputs and the diff, with `author_allowed_tools`.
7. **final_check.** Repeat step 5 once. No second fix round.
8. **Record.** Runner computes the outcome: `review_ready` if no `FAIL` remains, `needs_input` if the author wrote questions, `capped` if any stage hit a cap, `failed` on a non-zero exit. It writes the delegation record into the PR description (what was delegated, to which agent, that the output passed both reviews and the final check, net lines, anything added that was not asked for), posts the summary, and sets the tracker state to in review. `UNVERIFIABLE` criteria that name a command are run by the runner, not by a reviewer.

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
- **Selftest.** `runner selftest` attempts the blocked actions through a real `claude -p` session in a scratch repository (a push to the default branch of a local bare remote, `gh pr merge`) and requires the block and an unchanged remote. On success it writes a marker keyed by the Claude Code version and the plugin version. The runner refuses to start without a current marker. This satisfies "Apply means tested" in the Delegation law and is repeated whenever either version changes.
- **Fail closed.** The runner treats any guard, hook or tracker error as a stop. A crashing hook must exit 2, not 1 (a non-2 exit does not block).
- Out of scope, stated: commands run through other interpreters (`python -c`) are not parsed by the guard, so the allowlists exclude interpreters.

## 7. Law change

Delegation, "No unattended loops". Current text: "No automatic review loops between agents (for example a stop-time gate that re-invokes another agent) unless a human is watching." Proposed replacement:

> **Bounded unattended runs.** No automatic review loops between agents unless a human is watching, except a run that meets all of: (1) bounded: at most one review pass, one fix round and one final verification per unit of work; (2) capped: turn and wall-clock limits set before the run starts and enforced by the tool; (3) gated: it ends at a human gate (an open pull request) and cannot merge, push to the default branch or close the ticket, enforced by hooks or permission rules shown to block before the first run; (4) recorded: the run posts its outcome, turns used and deferred work to the ticket.

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
- [U] A way to cap a run's share of subscription usage; none found in the Claude Code docs read. Turns and time are the only bounds.
- [U] Codex as a runner agent; blocked on guard coverage (README).
- Parallel runs of several tasks and roadmap intake are later stages and are not designed here.

## 11. Acceptance criteria

1. `ENGINEERING_LAWS.md` Delegation carries the text in section 7; `CHANGELOG.md` and `README.md` describe the runner and the new guard rules.
2. `python3 -m unittest discover -s tests` passes, including new guard cases (`gh pr merge`, `gh api` blocked in plain, chained, `bash -c` and wrapper forms; `gh pr create`, `gh pr view` allowed).
3. `tests/test_runner.py` passes and covers each bullet in section 9.
4. `runner selftest` on a scratch repository prints a block for the default-branch push and for `gh pr merge`, leaves the remote unchanged, and writes the marker.
5. `runner run` against the `local` tracker and a scratch repository ends at an open PR (or its local-remote equivalent) with the delegation record, outcome recorded, tracker state in review.
6. An `investigate` task and a `deliver` task both complete through the same state machine.
7. No project-specific names appear in the repository diff.
