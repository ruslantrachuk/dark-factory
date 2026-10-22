# Dark factory: methodology

A "dark factory" (lights-out manufacturing, applied to software) is one where agents produce features with
minimal human presence. Humans keep four roles: the **Product owner** (what to build), the **Spec writer** (spec,
decomposition, tier label), the **Reviewer** (review, merge, release) and the **Operator** (the server, the sessions
and production). The machine does everything else.

The same approach can run at different levels of maturity:

| | Interactive | Autonomous feature run | Unattended work in remote sessions |
|---|---|---|---|
| Mode | the owner in the session, plus one-off "do it without me" instructions | the feature pipeline in its own worktree, stopping before the PR | long-lived sessions on the server work through booked runs, client requests and monitor events while nobody watches |
| Unit of work | release = session | a feature: one task card = one branch | a task card: one branch, named by its change key |
| Acceptance | "I'll come back for the final review" | a release record and a review hand-over | green CI and the agent's own review, then `merge-feature.sh`; the human gate is the release |

The method speaks in functions (the board, the execution queue, the client chat, the code host, and so on). Their
contracts, and the tools the reference implementation uses for them, are in [functions.md](functions.md).

---

## 1. Process core

### 1.1 Harness and product: two layers of the repository
The product (`app/`) is separate from the agent harness (the root: `CLAUDE.md`, openspec, workflows, hooks,
scripts). The boundary is strict: nothing in `app/` refers to anything outside it, so the product can be separated
mechanically and handed to the client. `app/` may be a folder in the same repository or a git submodule that points
to a separate one.

### 1.2 CLAUDE.md: the operating contract, with a blocking GATE
Every project uses the same skeleton:
- **Operating contract and constraints**: 5–7 rules that are never broken, at the top of the root `CLAUDE.md`.
  Claude Code loads that file into every session and reloads it after compaction. The reasoning: put the canon
  where it is guaranteed to be read, because a file nobody opens does not cure forgetting. Hard rules are also
  enforced by hooks and scripts, not by text alone (§1.9 lists what holds which rule).
- **GATE before any code**, three blocking steps: (0) sizing by the `size-task` skill (trivial, small or large, with the owner's ok); (1) skills by task type (brainstorming → writing-plans → TDD;
  systematic-debugging for bugs; verification-before-completion for any commit); (2) a work branch
  `<type>/<ID>-<slug>` (`<type>/<slug>` without a tracker; code on main is forbidden, docs are allowed); (3) read CODING_STANDARDS, the standard
  for the layer and `naming.yaml`.
- **Engineering principles stated explicitly, addressed to the model**: without explicit principles the model
  over-engineers (KISS, YAGNI, MVP, fail fast, spec-driven in proportion).
- `AGENTS.md`: a thin `@CLAUDE.md` alias for other coding agents.

### 1.3 Continuity: the state of work lives in git, the PR, the queue and memory
A session forgets everything at a context reset. What it must find again is kept where it already belongs, not in a
separate log file:

| What | Where |
|---|---|
| what a change does, its decisions, its open questions | the PR description: `## Done` / `## Decisions` / `## Open questions` |
| the project's history | the merge commits of the main branch: the merge script writes the PR description into the merge commit message, so the merge history reads as the log |
| a decision that shapes the architecture | an ADR in the branch |
| a follow-up, and where a task stopped | the feature execution queue: a new task, or a note on the claimed one |
| a rule or preference the human stated, an environment fact | the agent's memory |

- **Open a draft PR when work on a branch starts**, so the record has a place from the first commit.
- **Opening is deterministic**: a session-start hook prints the branch, its PR with the description, the tasks in
  progress with their notes and the latest merges (on the main branch also the active changes). The PR's open
  questions and the task notes are the continuation points.
- **Closing is a save step** (a `save` skill): commit, rewrite the PR description as the current state, note the
  claimed task, write to memory what is not in git. The same step runs before a context reset and at the quota ceiling.
- **Enforced mechanically**: the merge script refuses a PR whose description lacks the three sections. Anything that
  is in none of the four places is lost at the next reset; the rule is "not in git → memory or the queue".
- An open question is a task in the queue, not a line in a document: a document line is invisible in the queue.

### 1.4 OpenSpec: the change register
`openspec/changes/<slug>/` holds: proposal (always, with WHEN/THEN acceptance scenarios), design (a delta and a
transition tree, only for large changes) and tasks (always); SHIPPED for a milestone. The `size-task` skill decides
which of them a piece of work needs: none (trivial), proposal and tasks (small), plus design (large). One spec
system: working tools such as the Superpowers brainstorming and planning skills write into the change folder, not
into a separate specs or plans folder, so the subagent works to a contract in one place. Full OpenSpec (a living
spec and its CLI) is an option for larger projects and is not used here.

Conventions: the folder name is a unique slug, the tracker ID goes in the proposal header; no date in the name (git
log has it); the folder stays forever as the record of why it was done this way; code is the source of truth and a
spec is only a delta; a hotfix gets no folder. Phases are cut end to end, and each is its own branch and card. The
proposal has a **"Decisions (taken, do not revisit)"** section, so the agent does not reopen them, and a **scope
fallback**: closing a change green after a risky item fails is a valid outcome, not a failure. Branch, spec folder,
queue epic label and tracker card all derive from one change key.

### 1.5 The feature execution queue: one local store per project
The queue holds the work in progress only; the record of what was done is the PR and the merge history (§1.3). So the
queue is not committed and not synced through git: one local store per project, in the main working copy, which
every worktree of that copy uses (the reference tool, beads, finds it from a worktree, and the session-start hook
names it explicitly). Nothing has to travel in a branch, be exported, imported or merged. External trackers (client
trackers, the code host's issues, the board) are facades. Pitfall of the reference tool: beads may take over
`core.hooksPath` on setup, so it is set up without its hooks and `install-git-hooks.sh` checks for it and reports.

### 1.6 Execution: subagents and an orchestrator
- **Model roles**: mid-tier subagents write the code; the main agent, on the strongest model, orchestrates and
  reviews. The cheapest models and low effort are not used for production stages.
- **The core is not delegated**: financial math, layer contracts and migrations stay with the orchestrator; the
  periphery is delegated.
- **Parallel work is split by disjoint file zones**, checked deterministically (`pairwiseDisjoint(files)`) **in
  code, not by an LLM**.
- **One integrator agent is the only writer to git and the execution queue**, which removes `index.lock` races. Implementation
  agents only write code and tests, and do not commit.
- Plans carry the header "For agentic workers: REQUIRED SUB-SKILL: superpowers:subagent-driven-development".

### 1.7 Review: several layers, and each makes mistakes
- A two-stage review (spec, then quality) per task or phase plus a final review of the whole; or, on a large diff,
  a fan-out by dimension (design, tests, simplify).
- A multi-agent code review before merge, from several independent angles.
- **The 360 review** is read-only: N parallel agents, one per axis (code, frontend, tests, completeness against the
  client's requirements, coherence between idea and implementation, production readiness). Its result is only a
  diagnosis and a prioritised plan of fix releases.
- **Review findings are verified, and may be rejected with a justification.**
- **An external, independent reviewer (another model or vendor) catches what your own tests miss.**
- **The finding format and the triage rules are canonical**:
  [templates/base/docs/review-contract.md](../templates/base/docs/review-contract.md). It defines five mandatory
  elements of a finding; `clean_check` (a "clean" verdict also has to be proven); `user_decision_required`; a limit
  on review waves (2 for an implementation, 3 for a spec); and a spec skeptic. Prior art: molyanov-ai-dev.

### 1.8 Quality gates
- The test pyramid is a policy: the project's profile chooses the main layer of trust; E2E is a release gate, not a
  per-PR check; the project states explicitly what it does NOT test and keeps a catalogue of anti-patterns.
- The standard report line: `lint ✓ · tests N ✓ · build ✓ · doc-links ✓ · hands-on check in the preview environment ✓`.
- pre-commit is empty or fast; the full suite runs on pre-push (once per push) and in CI.
- EVALS with a baseline for everything an LLM makes nondeterministic. A deviation is not a hard failure, but it must
  be explained; each eval runs three times for stability.
- FOUND_BUGS and an xfail quarantine: a bug that tests find in a branch is NOT fixed in that branch (that leads to
  an uncontrolled refactor). A separate fix branch removes the xfail.
- A "silent fake success" is a distinct class of defect that can be caught. Rule: **a loud signal beats silent
  corruption**.

### 1.9 Human acceptance
- **The release record**: a release is accepted by the owner's "yes" plus `SHIPPED.md`; the release is the human gate. Its sections: a header
  (date, PR, merge commit, card, queue epic) → what actually shipped → what was postponed and why → what review found
  and moved out of the branch → a retro. The format is in `templates/base/openspec/README.md`. Gates that can be
  listed explicitly: review (the diff invariant), evals (a threshold), migration (with rollback), smoke (numbered
  scenarios with a data check), flag (switched off, the release behaves exactly like the previous one),
  counter-metrics (a query after 2–3 days), push.
- **REVIEW.md, the shift hand-over**: a TL;DR, "How to review (15 minutes)", **"Decisions taken for you"** (what
  was chosen | why | the alternative), and "If you want it differently" (what it costs to roll back each decision).
- **Autonomy fuses**: no push, merge or deploy without an explicit "yes" (the merge and everything that reaches
  main are fenced, see below; a feature-branch push rests on the rule); an emergency flag `APP_{FEATURE}_ENABLED`
  per feature, with proof that "off" behaves exactly like the previous release; caps on loops (turns, number of PRs,
  maximum rounds, and a stop when there is no progress).
- **What holds the hard rules.** The fence level (`solo` / `standard` / `team`) is chosen at deployment in
  `.claude/fences.env`.
  - The guard (`guard.py` of the dark-factory plugin, a PreToolUse hook) denies force push, a push to main, `--no-verify` and other
    ways around the git hooks, release-tag pushes outside `scripts/release.sh`, and, at `standard` and `team`,
    a direct merge on the code host (`gh pr merge`) outside the merge script and edits to the fence files.
  - `scripts/merge-feature.sh` merges on green CI, after the agent's own review. At `team` it also needs an approval on the code host. `--skip-ci "<reason>"` is for CI that cannot run
    at all, on the owner's word.
  - `.githooks/pre-push`: the tests.
  - The merge script refuses a PR without `## Done` / `## Decisions` / `## Open questions` in its description.
  - The quota guard: no new work near the subscription limit.
  - The sandbox: filesystem and network limits for commands.

  The guard is a seatbelt, not a sandbox: it reads tool calls, so it cannot see through scripts written and then
  run, aliases defined elsewhere, subprocesses or arbitrary interpreters, and it does not stop a determined or
  hostile agent. Below `team` no person approves a merge. **Branch protection or rulesets on main at
  the code host** (no force pushes, a PR required, reviews at `team`) are the real gate; deployment proposes them.
  The fence level itself changes only on the human's own `/dark-factory:level <target>`, and lowering it takes
  effect only once merged into main ([levels.md](levels.md), [threat-model.md](threat-model.md)).
- **A user instruction grants the autonomy mode**, and the PR description quotes it: "work autonomously, I'll come back for
  the final review", "do it without me", or a hands-on review mode without tests that records the debt.

---

## 2. Unattended work in remote sessions

The standard scope: **one feature at a time per development session, with a mandatory verification gate**. More
features in parallel, or more projects, come only after one has been proven in real use.

Key elements:
1. **Topology**: a server you control; one long-lived `claude remote-control` development session per project, each
   in its own git worktree; the owner drives the sessions from claude.ai on the web or the phone. Code and harness
   live in one tree (code in `app/`), with ordinary `git push` and `git pull` to the git host.
2. **Sessions talk to each other by name.** The On-call session (`feedback-desk`) holds the client chat channel,
   acknowledges a request, forwards it verbatim to the development session and posts the answer back. The production
   monitor (`prod-monitor`) is a cron watchdog without a model that wakes a read-only agent only on a real anomaly;
   its verdict reaches the On-call session as a channel event and goes on to the group and the development session.
3. **Feature work**: the development session launches the feature pipeline (Workflow scripts of the dark-factory
   plugin, `feature-auto` → `feature-core` or `feature-lite`; the `feature-pipeline` module holds the project settings): plan → test-first chunks → integration in its own
   worktree → local commit, stopping before the PR. **The real outcome is in the result's `error` field**, not in
   its status. The merge happens once CI is green (`scripts/merge-feature.sh <branch>`).
4. **Execution tiers** follow the `scale` label, which a human sets: auto, core (an epic graph) or lite; the default
   is lite. For a small feature most of the cost is the orchestration itself, so the lite path is several times
   cheaper.
5. **Unattended work is booked by the session itself.** For "run it tonight" or "review production every morning",
   the session schedules the run with native scheduling (`send_later`, `CronCreate`, scheduled tasks in the server
   environment).
6. **Quota guard** (the dark-factory plugin, enabled by base): near the subscription limit, hooks stop new work (80%); ask the agent to wrap up with a
   WIP commit, the PR description and the task notes (85%); and allow only saving work and scheduling a continuation (90%).
   The session books its own continuation after the reset. The quota comes from the server's rate-limit data,
   measured outside the agent.
7. **Environment awareness**: an environment marker (`.claude/env`), a capability block printed at session start,
   and **structural backstops** (what the environment physically allows, guard hooks that deny the call — the fence
   guard and the quota guard, `stopBeforePR` in the pipeline code, the sandbox), not the agent's conscience.
8. **Runs are isolated along three axes**: tasks (assignee scope), files (worktree), ports.
9. **Gates**: a docs-only guard (against a false "done") and a functional verification gate with a fix cycle (two
   attempts, then an explicit failure). An autonomous run closes only its own subtasks; `merge-feature.sh` closes
   the parent task at merge (found from the branch name: tracker ID or slug).
10. **Protection model**: three things to fear: a hang, a runaway loop and an irreversible action. Irreversible
    actions are excluded structurally (the run stops before the PR; merge and deploy need a human). A loop is told
    apart by progress against spend. Wall-clock time is a dead-man switch, not a regulator. A worktree is not a
    sandbox (§3).
11. **Human acceptance is the main value of the pipeline**: an autonomous feature can be "green" and still have a UX
    defect that only a hands-on review catches.
12. **Final statuses and contract checks live in the pipeline code, not in an instruction to the agent.** An agent
    keeps breaking "set a label instead of closing the task in the queue" until the rule is in code.

---

## 3. Infrastructure and setup

- **The server**: one machine you control runs the long-lived sessions (a development session per project, the
  On-call session) and the monitor watchdog, and all of them come back after a reboot. Cloud sessions are not used:
  they lack the chat channel, two-way messaging with other sessions, and local access to hosting tools, the preview
  environment and read-only production data.
- **Provisioning in three layers**: (1) a one-off bootstrap as root: the personal environment and the Claude CLI;
  (2) an unprivileged user for the sessions; (3) the project's provisioning script, which adds only the toolchain
  the project needs on top. Every step is idempotent and runs on a single "go". **The agent never runs as root**,
  and refuses to skip permissions as root on its own.
- Secrets are either generated or typed in by the owner (`read -s`), so the agent never sees the value. A ship
  token comes from the OS keychain, outside the agent's context.
- Host specifics (ports, addresses) stay out of the repository: CLI flags and a local `launch.json`.
- Claude auth: OAuth under a subscription, not an API key.
- Access only through a private network (a tailnet); public SSH is closed.
- **Sandbox**: a worktree isolates files and git, not commands. Base enables the built-in Claude Code sandbox
  (filesystem writes limited to the working directory, a network domain allowlist, secrets denied or masked for
  Bash) plus `permissions.deny` for the Read and Edit tools. Enabling it is an explicit question at deployment; a
  "no" is recorded as a deviation in the registry. The fence level (`.claude/fences.env`) is a deployment question
  too, and deployment recommends branch protection on main at the code host as the backstop (§1.9).
- No state on the server beyond git (JSONL in git plus the git host), so losing the machine costs only uncommitted
  worktree changes, and rebuilding it takes minutes.

---

## 4. Cross-cutting principles

1. **Structural fences instead of instructions.** Everything critical ("do not push", "do not leave the perimeter",
   "do not close tasks") is enforced by what the environment physically allows, by guard hooks and by orchestrator
   code, not by prompt text. An agent breaks instructions far more easily than fences. Fences in hooks are still a
   seatbelt, not a sandbox: a static guard misses scripts written and then run, aliases and subprocesses, so the
   last line of defence is outside the agent's machine (branch protection, required reviews) and the sandbox
   ([threat-model.md](threat-model.md)).
2. **The human Reviewer is permanent, not a temporary crutch.** A hands-on review catches defects that automated
   tests and static checks cannot reach.
3. **Autonomy is granted in steps, on measured acceptance**: a ladder A1→A3→…, red lines, counter-metrics, and every
   action reversible.
4. **Memory is git, the PR, the queue and the agent's memory.** The PR description and the merge history hold what was
   done and why, the execution queue holds the work in progress, memory holds what is not in git; the merge script
   enforces the record, and nothing important lives only in the session's head.
5. **Preparation is separate from execution.** A human with the development session prepares the spec, the task
   graph and the scale label; the feature pipeline consumes them and chooses neither scope nor tier.
6. **Cost is standing context, not generation.** Rule of thumb: cost ≈ the number of agents × the standing context
   each one loads. Take the small path by default, orchestrate only when the feature is worth it, and have a human
   confirm the choice of path explicitly.
7. **A loud signal beats silent corruption.** A fake-green sync, a docs-only "done", a union merge, a false-green
   E2E: each was caught and turned into a guard.
8. **Do not trust agents' self-reports**: commit messages, "✓" ticks, verdicts of review agents. Verify by running,
   by grepping, or by a human. The canonical format is
   [templates/base/docs/review-contract.md](../templates/base/docs/review-contract.md).
9. **Every closed door comes with the conditions for reopening it.** Rejected alternatives are recorded with reasons
   (parked ideas, ADRs that note reversibility).
10. **The status of an artifact is stated, not implied**: "✅ exists / 🟡 template, not activated / 🔜 needed",
    right in the runbook and in SKILL.md.
11. **Prove N=1 in real use, then scale.** Building for N=2 before N=1 is proven is premature.
12. **One project language, set per project (English by default); English is the language of the tooling.** Agent
    messages are readable prose, not terse notes.
13. **Choose the layer by the strength of the guarantee and the cost of context.** A guarantee → a hook or a
    permission (deterministic code that does not rely on the model remembering a rule). A procedure → a skill (loaded only when invoked).
    Knowledge → a rule or standard loaded on demand. The always-on context holds only what must be true on every
    turn. Every addition to the harness is paid for in tokens on every turn, so count the cost before adopting it.

---

## 5. Filter for adopting harness changes (checklist)

> The entry filter of the improvement loop: review pass → decision → change in `templates/` → rollout.
> Check in order and stop at the first "no".

0. **A problem, not a tool.** Name an episode from recent project work that this change solves. No episode → it
   goes to the backlog, not into work.
1. **Already covered?** By the existing canon; by what Claude Code has built in (check the current docs, not an
   article); by installed plugins.
2. **The layer by strength of guarantee** (principle 13). If it needs always-on context, the answer is almost
   always no.
3. **Cost of ownership.** Tokens per turn or per invocation; lines of code and config to maintain; external
   dependencies.
4. **One source of truth.** Does it create a second home for an existing fact? If it replaces one, the old home is
   removed in the same change.
5. **Portability.** It works on every machine and project of the factory, does not codify one person's habits, and
   rolls out through the existing channel (canon → review pass → registry).
6. **A pilot with an abandon criterion written down in advance.** One project, a fixed time box; what counts as
   failure is decided before the start.
7. **Record the outcome either way**: a row in [open-questions.md](open-questions.md) (§1 if open, §2 if settled or
   rejected, with the condition for reopening). If accepted, the change goes into `templates/` and rolls out during
   the review pass.
