# Engineering Laws

Project-agnostic laws for all agentic engineering work. These are non-negotiable and apply to every repo that uses Claude Code or equivalent AI-assisted development tooling. A project's own instructions may add rules but never relax these. Sections explicitly marked as patterns (Resource Lifecycle) are the exception: each project overrides them with its own rules.

Tooling names (Plane for tickets, `/code-review`, `/session-close`) are the ones these laws were written against; substitute your own. What matters is the content each requires.

---

## Record Laws

Context that isn't written down doesn't exist for the next session.

### Work Creation

Two modes — pick the right one:

**Planned work** (features, multi-session initiatives, architecture changes): A Plane ticket must exist with problem, rationale, acceptance criteria, and a link to `docs/designs/FEATURE-NAME.md` for anything touching architecture or data schema. The ticket description is the agent brief — if incomplete, ask, and put the answer in the ticket.

**Reactive work** (prod bugs, user-reported issues, quick fixes): No Plane ticket required. Log the outcome in `docs/feedback/YYYY-MM-DD-slug.md` when done.

### Session End

Before a session closes:
- **Decisions or constraints** not obvious from the code → `docs/sessions/YYYY-MM-DD-slug.md`
- **User complaints that drove a fix** → `docs/feedback/YYYY-MM-DD-slug.md` (one paragraph: what was reported, what was done, what was deferred)
- Plane ticket state updated
- Audit `git worktree list`. Remove only clean worktrees whose exact branch HEAD is verified merged; preserve dirty, unmerged, or changed worktrees, then run `git worktree prune`.

Run `/session-close` to walk through this checklist interactively.

### Adversarial Review

Before moving any ticket from In Progress → Blocked/In Review, run `/code-review medium` and post findings as a Plane comment. Hotfixes may skip both this review and the cold verifier (see Cold Review) only if production is degraded and the fix cannot wait for a review (minutes, not hours) — document that it was skipped and why.

**`/code-review medium` is the permanent ceiling. Never use `high`, `max`, or `ultra` — they spawn multiple parallel cloud agents and consume more tokens than the work itself.**

### Cold Review

The adversarial review above must be cold. An author's context biases their judgment of their own work, so:

- **Different context**: the reviewer is a separate agent or session. The author never reviews their own diff.
- **Minimal input**: the reviewer receives only the diff and the acceptance criteria. Never the author's plan, reasoning, or session history.
- **Read-only**: the reviewer reports; it does not edit or fix.
- **Fixed output**: one line per acceptance criterion (`PASS`, `FAIL`, or `UNVERIFIABLE`) with `path:line` evidence, then one line per finding. `UNVERIFIABLE` names the command or manual check that would prove it.
- **Disputes are settled by evidence**: if the author disagrees with a finding, they cite `path:line`, not argument.

Two reviews, one gate. `/code-review medium` hunts defects in the diff; the cold verifier checks the acceptance criteria. Both must be cold, both run before In Review, and both outputs are posted as a ticket comment. `/code-review` reads the repo, so for it cold means a fresh session that was not given the author's plan; treat that as best-effort. The verifier's input is strictly the diff and the criteria. The cost ceiling above applies to each: one reviewer, no parallel fan-out. A verifier without a shell cannot run commands, so any criterion that needs one comes back `UNVERIFIABLE` and the author runs the named command.

### Provenance

When claiming "this works because X" or "we decided Y", cite a doc. If no doc exists, write one before implementing.

Before relying on how a library, API, or tool behaves, read its official docs or source and cite what you read. When requirements are unclear, ask instead of inventing scope.

### Strategic Execution

1. State the objective, constraints, and rationale before editing code, in the ticket or PR description. This is not input to a cold reviewer (see Cold Review).
2. Work in bounded increments: implement, verify, reassess.
3. End with an outcome audit in the PR description or ticket: what was delivered, what was deferred, and the next step.

---

## Code Quality Laws

### Code Claims Require Code Reads

Before stating anything about how code behaves — what a function does, what a field contains, what a query returns, how two components interact — read that code first. Every behavioral claim must be backed by a file and line number that was actually read in the current session.

**The rule in one line: read the code, then state what it does. Never state then read.**

This applies even when the answer seems obvious from a name or pattern. If the read contradicts the assumption, the read wins. Partial reads (finding one writer of a field without checking all writers, finding one call site without checking the callee) do not count — trace the full path before claiming to understand it.

### Declarative Before Imperative

Before writing a third instance of any repeating imperative pattern (hardcoded labels, scattered conditionals, parallel if/else blocks for variants), stop and define an abstraction: a registry entry, a dataclass, a dispatch table. The threshold is **3 instances** — not "many". Write the abstraction in the design doc first; only then implement. Features built without a declared structure accrue immediate tech debt and will require a structural refactor before they can grow.

### Clear Debt In-Band

When a code review or inspection surfaces a finding that is **directly related to the current change** (touches files already in the diff) and the fix is **bounded in scope** (small and self-contained), fix it in the same PR — do not defer it. "We'll clean this up later" is how debt accumulates and never gets paid.

The test: if the debt lives in a file the current PR already touches, and the fix is ≤ ~20 lines, do it now. Only defer when the fix would require a separate design decision, a new migration, or pulls in files entirely outside the current change's scope.

### Smallest Sufficient Change

Build what was asked, and leave no dead weight behind. The goal is explicit, readable code, not fewer lines. A shared abstraction that needs flags or special cases to tell its callers apart is the symptom of over-compression; keep the explicit copies instead.

- **Do what was asked.** No unrequested features, refactors, files, flags, config options, or dependencies. Anything not in the request becomes its own ticket, except what Clear Debt In-Band allows: small related fixes and refactors in files already in the diff.
- **No speculative generality.** An abstraction, parameter, option, hook, or extension point needs a caller in the same change. "We might need it" is not a caller. When an abstraction is justified, Declarative Before Imperative decides its shape.
- **Reuse before writing.** Search for an existing implementation before adding one. A second copy of the same logic is tolerable and is named in the PR; before writing a third, define the abstraction (Declarative Before Imperative). Do not merge code that only looks alike.
- **A replacement deletes what it replaces.** A change that adds a new version, variant, or path (a `_v2`, a second implementation, a new flow) removes the old one in the same change, or states in the PR why it stays and when it goes.
- **Leave no dead code.** Remove what your change makes unused: imports, variables, helpers, parameters, flags, branches, scripts, config. Code with no caller is deleted, not commented out; version control remembers it. Before adding a symbol, know its caller; before finishing, search for a caller of each symbol you added (a grep, or the project's unused-code check).
- **A new dependency needs a reason.** The PR states what it does that the standard library or an existing dependency does not.
- **Report it.** The PR description gives net lines added and removed and lists anything added that was not asked for. A cold reviewer maps every changed hunk to a requirement, and a hunk that maps to none is a finding.

### No Silent Exit Paths

Every exit path from a handler, background job, or event callback must produce a log line. A `return` with no preceding log in a non-nominal path is always a bug.

This applies especially to:
- **Null checks**: subscription not found, event ID missing, record lookup returned None
- **Early returns from state guards**: duplicate event, stale event, terminal-status block
- **Worker error paths**: per-cycle failures caught and swallowed without capture

A silent 200 OK from a webhook that took no action is diagnosed by the absence of logs — which is no basis for diagnosis.

### Design Docs Must Specify the Data Model

For any feature involving a repeated pattern (N insight types, N notification templates, N scoring rules), the design doc must include the **concrete struct/dataclass/schema** that all instances conform to — not just prose describing intent. If the design doc lacks this, the ticket is incomplete. Stop and ask before implementing.

This is the upstream gate for the Declarative Before Imperative law. The abstraction must exist on paper before any instance is written in code.

---

## Delegation

Work handed to another agent (another vendor's coding agent, a subagent, a background job) falls under the same laws as work done directly. The delegating agent stays responsible for it.

- **Default to the available delegate.** When the Codex plugin is installed, work that would go to a Claude subagent (investigation, search, implementation, refactor, review) goes to Codex instead, to spread usage across vendors. Stay on Claude only for work that needs Claude-only tools (MCP servers, web fetch, Claude Code documentation); the plugin exempts web fetch, Claude Code documentation and status line agents automatically; for anything else say why in the brief with `[claude-only: <reason>]`. The plugin's `Agent` hook enforces this. The conditions below still apply to every delegation.
- **Deliver the laws; do not hope for them.** The delegate must load these laws through its own instruction mechanism before it writes code, for example a global instruction file that points at the same pinned laws. Task text alone is not a delivery mechanism. If the delegate cannot load them, it does read-only work only.
- **Same enforcement, or less access.** Guards that protect the default branch (hooks, git hooks) must apply to the delegate too. "Apply" means tested: attempt a blocked action through the delegate in a scratch repository and observe the block. Until that is shown, give the delegate read-only tasks (review, investigation), not write tasks.
- **Isolate writes.** Write delegation runs in a worktree on its own branch, started from a session whose working directory is that worktree, because delegates work in the git root of the delegating session's directory. A session in the default-branch checkout cannot delegate writes.
- **Brief it checkably.** The delegate gets the objective, constraints, checkable acceptance criteria, and the absolute worktree path.
- **Delegated reviewers.** A delegate acting as a cold reviewer gets only the diff and the criteria where its tool allows (see Cold Review). A reviewer that reads the repository itself is cold on a best-effort basis, as with `/code-review`. The cost ceiling applies to delegated reviews: one reviewer per review, no fan-out.
- **Delegated output is untrusted until verified.** It passes the same cold review and the project's CI as direct work. Do not report it as done before that.
- **No unattended loops.** No automatic review loops between agents (for example a stop-time gate that re-invokes another agent) unless a human is watching.
- **Record it.** The PR states which parts were delegated, to which agent, and that the output was verified.

---

## Worktrees — Mandatory for All Code Changes

**Every code change must be made in a worktree on its own branch. Never commit to the default branch (`main` or `master`) directly.**

This is non-negotiable. The reason: the user may switch the main checkout to any worktree branch at any time to review or test work. If changes land on the default branch, they break that workflow and contaminate it with unreviewed code.

- **Reactive fixes**: still need a worktree. Create one, make the change, open a PR.
- **No exceptions**: not for one-liners, not for "obvious" fixes, not for hotfixes unless the user explicitly says to push to the default branch.

### Convention

Examples use `main`; substitute `master` if that is your default branch.

```bash
# Fetch first — always branch from remote origin/main, not local main (local may be stale)
git fetch origin

# Create a worktree on a new branch from remote main
git worktree add .claude/worktrees/<slug> -b <branch-name> origin/main

# Create a worktree on an existing branch
git worktree add .claude/worktrees/<slug> <branch-name>

# List all active worktrees
git worktree list

# Remove when done (after merging)
git worktree remove .claude/worktrees/<slug>
git branch -d <branch-name>
```

- **Location**: always under `.claude/worktrees/<slug>/` — this directory should be gitignored.
- **Each worktree is an independent working tree**: separate `git status`, separate checkout, runs project verification independently.
- **Never `cd` into a worktree for long-running work** — spawn an agent pointing at that directory instead, so the main session stays on its branch.
- **Agents working in a worktree** must be briefed with the absolute path as their working root.

### Typical flow

```
main checkout (main — read-only for agents)
  └── agent A → .claude/worktrees/fix-foo/  [fix/foo branch → PR]
  └── agent B → .claude/worktrees/feat-bar/ [feat/bar branch → PR]
```

Both agents commit, push, and open PRs independently. Branches reach the default branch only through merged PRs.

---

## Plane Workflow

Ticket states and the `docs/` paths are conventions; map them onto your own tracker and repository layout.

- **Planned work**: Plane ticket required before starting (problem, rationale, AC, design doc link for arch changes).
- **Reactive work**: no ticket required — log outcome in `docs/feedback/YYYY-MM-DD-slug.md`.
- Session start: read the ticket description and any linked design docs before touching code.
- Move to **In Progress** when starting. Run both reviews (Adversarial Review and Cold Review, including the hotfix exception stated there) and post findings before moving to **Blocked/In Review**.
- Never move to **Done** — reserved for user approval.
- Commit format: `<type>(<scope>): <description> [PLANE-###]`

---

## Testing

- **Test real behavior at real system boundaries.** Don't mock the database — mocked tests can pass while real migrations fail in production. Integration tests must hit a real DB.
- **New behavior gets a test in the same commit.** Not "we'll add tests later." If you add a code path, cover it.
- **Run the full test suite sparingly** — never in parallel, never as a development loop. Prefer targeted checks proportional to risk (single file or test, lint, build, smoke). Run the full local suite only on request or for broad/high-risk changes; pull-request CI owns the full matrix. Report the checks run and any relevant check that could not run.
- **Type checking and test suites verify code correctness, not feature correctness.** Passing tests do not mean the feature works end-to-end. Test the golden path and edge cases manually for any UI or behavioral change.

### Regression Proof

A fix is not done until a test proves it, and the proof comes from real failures, not imagined ones.

- **Failing test first.** A bug fix starts with a test built from the real failing input (captured from production, a log, or the report). Run it and watch it fail for the reported reason, then fix, then watch it pass. Report both runs in the PR description.
- **Every incident adds a case.** The input that caused the failure becomes a permanent fixture in the repo, sanitized of secrets and personal data before it is committed (especially in a public repo). The fixture set is the project's regression corpus.
- **Replay the corpus when the system under test changes**: a dependency upgrade, a refactor, a model or prompt change for anything LLM-driven. A replay is a targeted check, not the full suite: run it on such a change, and in CI on every PR when it fits the project's stated CI time budget (recorded in the README or CI config). Prompt or LLM scaffolding whose removal fails no corpus case is a candidate for deletion after review; this does not apply to safety rules a corpus does not cover (for example Resource Lifecycle).
- **Nondeterministic systems** (any system whose output varies across identical runs; LLM-driven ones are the usual case) replay each case N times, with N and the pass threshold recorded in the project's test config or README. "No retry-until-green" below does not apply to a recorded threshold, only to rerunning until one run passes.
- **Acceptance criteria are checkable.** Each criterion names a command, query, or observable whose result decides pass or fail. A criterion that cannot be checked mechanically is marked `UNVERIFIABLE` and names the manual check, as in Cold Review.
- **No retry-until-green.** A test that passes on rerun is a failing test. Quarantining a flaky test means skipping it while keeping it listed (a skip marker plus a link to a tracked issue, in the same PR). Deleting it silently is not allowed.

---

## Operational Scripts

One-shot scripts (backfills, migrations, data fixes) must let an operator tell at a glance that work is happening and how much is left:

- **Periodic count output**: print a running tally every N rows (e.g. every 10,000). Silent scripts that only print on completion are unacceptable for anything that takes more than a few seconds.
- **Final summary line**: always print total rows changed and total elapsed time on exit.
- **Structured output**: `print(f"[{i}/{total}] ...")` or similar so progress is unambiguous.

---

## Production Diligence

- Zero tolerance for sloppy commits — every commit in a production-tracked repo deploys immediately or is one merge away from deploying.
- For prod incidents, deliver structural fixes that make the failure impossible, not manual intervention or band-aids.
- Never skip pre-commit hooks (`--no-verify`) or bypass signing unless the user explicitly requests it.
- Never use `git revert` — use `git reset` to undo commits.
- Never push directly to the default branch unless the user explicitly requests it; it otherwise changes only through merged PRs. Never force-push to it.

Enforcement tooling may be stricter than any rule above (for example, a hook that blocks `--no-verify` or any push to the default branch unconditionally). When the user has explicitly requested a blocked action, the user runs the command themselves.

---

## Resource Lifecycle

These are patterns, not law — each project overrides with its own rules. The principle is: **always use the project's established context managers and singletons. Never instantiate raw clients or sessions.**

Leaked connections and unclosed resources can cause production outages. Any new resource type (HTTP client, cache client, queue connection) must have an explicit lifecycle defined before it's used in more than one place.
