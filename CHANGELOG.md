# Changelog

## 0.1.5

- Delegation law: add "Choose the delegate" (Claude or Codex, with a default split; a Claude subagent brief states `[claude: <reason>]` when Codex is installed).
- `hooks/delegate-codex.py` (new) and an `Agent` matcher in `hooks/hooks.json` enforce it; allows everything when Codex is not installed or on internal error. Tests: `tests/test_delegate_codex.py`.

## 0.1.4

Law text only; no hook or agent behavior change. The version bump lets projects pin a tag that includes this change.

- Remove two record-keeping requirements. Strategic Execution no longer requires a checkpoint comment after each major slice; the objective is still stated first and the outcome audit still records what was delivered, deferred and next, but there is no longer an explicit requirement to record gaps and risks. Delegation no longer requires project parameters to name the model and effort used per class of task; the PR still states what was delegated, to which agent, and that the output was verified, so model and effort are no longer recorded.

## 0.1.3

- Guard: expand variables assigned earlier in the same command when resolving `cd`, `git -C`, `env -C` and `git worktree add` targets. `D=/path; cd "$D" && git commit` was blocked as an unresolved directory even when `$D` was a feature checkout; a variable pointing at a protected checkout is now blocked as such. A variable with no assignment in the command still fails closed. `$PWD`, `$(pwd)` and the toplevel inside an assigned value are expanded at assignment time (previously they would have been resolved against whatever directory was current at use). `unset`, a `for` loop variable, `select` and `read` forget an earlier assignment. A value over 4,096 characters is dropped, which also stops a self-doubling `A=$A$A` chain from hanging or exhausting memory in the hook.
- Laws: add Smallest Sufficient Change (no unrequested additions, no speculative generality, reuse before writing, a replacement deletes what it replaces, no dead code, justified dependencies, net lines reported) and Delegation (the same laws bind delegated work; laws delivered through the delegate's own instruction file; same enforcement or read-only; isolated writes; output untrusted until cold review and CI).
- README: machine setup for delegating to Codex (pinned official plugin, global `AGENTS.md` linked to the pinned laws, instruction-size cap) and what is and is not verified.

## 0.1.2

Block log: every guard block is recorded so true blocks and false positives can be counted per rule. No change to what is blocked.

- `hooks/rules.py` (new): registry of rule ids (`git-revert`, `no-verify`, `hooks-path`, `push-protected`, `push-all`, `push-wildcard`, `push-unknown-branch`, `commit-protected`, `commit-unknown-branch`, `unparseable-git`, `unreadable-payload`). `guard.py` raises `Block(rule, detail)`; a test fails if a `Block` takes a bare string.
- `hooks/blocklog.py` (new): appends one JSON line per block to `${CLAUDE_PLUGIN_DATA}/blocks.jsonl` (outside any repository). Stores rule id, git subcommand, UTC timestamp, cwd basename, and only the blocked git invocation's words (at most 16, each redacted on its own and capped, 200 characters total); never the rest of the command line or the raw command. Logging fails open: an unset variable, an unwritable path, a FIFO or any error skips the log and never changes the decision or delays it.
- `hooks/report.py` (new): tolerates a missing or corrupt log; `summary` (blocks per rule and per day, with false-positive, true-block and open counts), `list [--unreviewed]`, and `mark ID [--verdict false-positive|true-block] [--note TEXT]`.
- Tests: `tests/test_blocklog.py`; the existing corpus passes unchanged and no longer writes to a real data directory.

## Unreleased

Law text only; no hook or agent behavior change, so no version bump.

- Add Regression Proof: failing test first, sanitized incident corpus, replay on change (with a threshold rule for nondeterministic systems), checkable acceptance criteria, no retry-until-green.
- Add Strategic Execution; add to Provenance "read the official docs or source and cite what you read; ask when requirements are unclear".
- Cold Review: state how it fits with `/code-review medium` (two reviews, one gate, one reviewer each, `/code-review` cold is best-effort); `UNVERIFIABLE` names a command or a manual check; a shell-less verifier returns `UNVERIFIABLE` for command-based criteria. The hotfix skip covers both reviews, and Plane Workflow now names both reviews.
- Add Code Claims partial-read examples. Branches reach the default branch only through merged PRs; no direct push to it unless the user explicitly requests it; no force-push.
- Say "default branch (`main` or `master`)"; mark tooling names and ticket states as substitutable; state that pattern sections (Resource Lifecycle) are the only overridable ones; define when a hotfix may skip review; Production Diligence notes that enforcement tooling may be stricter than the law.
- Testing: soften an uncited production claim ("can pass", not "have passed"); Resource Lifecycle likewise ("can cause"). Remove an incident-flavored sentence from No Silent Exit Paths.
- Minor wording: worktree and `--no-verify` clarifications.

## 0.1.1

Fixes from three cold reviews of 0.1.0 and of the rewrites. The first bypassed the guard in many ways and found false positives; the second found control-structure, redirect, heredoc and directory-tracking gaps; the third (realistic payloads only) found that the common `git commit -m "$(cat <<'EOF' ... EOF)"` form was blocked when the message held an apostrophe, plus unquoted `$(...)` handling and per-directory branch tracking.

- `hooks/guard.py` (new): replace the regex guard with a tokenizing evaluator that tracks the working directory and chained branch switches. Covers `git -C`/`-c`/`--git-dir`, absolute git path, `commit -n` and `am -n`, `-c core.hooksPath`, `bash -c`, `eval`, `find -exec`, `xargs`/`sudo`/`env`/`timeout` wrappers, `if`/`for`/`while`/`case` bodies, `{ }`, functions, subshell scope, `cd` options and variable targets, redirects, here-strings, ANSI-C quoting, refspec forms (`+main`, `HEAD:main`, `@`, `heads/main`, `--repo`, `--all`, wildcards). Quoted text, `echo`, comments and heredoc bodies (including heredocs inside `"$(...)"`, apostrophes in them or in comments) no longer trigger it. Unquoted `$(...)` and backticks stay part of their word, so they no longer split a command. Branch tracking is per directory and sees `git worktree add` earlier in the chain; `git push --tags` and `git push origin "$(git branch --show-current)"` are understood. A fourth review (realistic payloads, about 550 run) found no realistic bypass; its one realism-3 finding, a false positive on `BRANCH=x; git push origin "$BRANCH"`, is fixed by tracking top-level same-command variable assignments (a protected name reaching a push through one is still blocked; the README lists the forms not followed). A fifth, delta-only review (281 payloads) returned SHIP with nothing at realism 4 or above. Also: `cd -`, `mkdir x && cd x` under a repo, DWIM/`--track` checkouts, attached `-ccore.hooksPath=` and `--config-env=`, `git config core.hooksPath`, a protected `${VAR:-default}` push destination, and `git push --help`. Known friction is listed in the README.
- `hooks/guard-bash.sh`: thin wrapper that fails closed (missing `python3`, internal error). Drops the undocumented `jq` dependency, whose absence silently disabled the guard.
- Behavior change: any push whose destination is `main`/`master` is now blocked, not only forced ones. When the directory or branch is unknown, `git commit` and a refspec-less push are blocked.
- `tests/test_guard.py` (new): regression corpus from both reviews. Out-of-scope cases are listed in the README.
- `agents/verifier.md`: state that it has no git or shell, so runtime criteria are `UNVERIFIABLE` by design; allow a one-line fix on FAIL; `UNVERIFIABLE` names a command or a manual check, matching the laws.
- Manifests: remove the claim of "ticket workflow skills" that does not exist.

## 0.1.0

- Plugin scaffold: `.claude-plugin/plugin.json`, `marketplace.json`.
- `hooks/guard-bash.sh`: blocks `git revert`, `--no-verify`, force-push to main/master, commit/push on main/master.
- `agents/verifier.md`: read-only acceptance-criteria evaluator.
- Laws: add Cold Review, generalize the webhook example, add worktree audit to Session End, Operational Scripts section, align Testing with CI-owns-full-suite.
