# Dark factory: methodology

"Dark factory" (lights-out manufacturing for software development) — features produced by agents with minimal human presence. The human stays in three roles: **client** (what to do), **preparer** (spec, decomposition, tier label) and **acceptor** (review, merge, production). Everything else is the machine.

The same approach can be run at different maturity levels:

| | Interactive | Autonomous feature run | Unattended work in remote sessions |
|---|---|---|---|
| Mode | the owner in the session + one-off "do it without me" directives | the feature pipeline in its own worktree, stopping before the PR | long-lived sessions on the server work through booked runs, client requests and monitor events while nobody watches |
| Unit of work | release = session | a feature: one epic = one branch | a release **train** (`r{N}` ≠ release) |
| Acceptance | "I'll come for the final review" | a release record + review hand-over | a human "yes" per branch (assumptions ∧ live check ∧ CI), then `merge-feature` |

---

## 1. Process core

### 1.1 Harness / product — two layers of the repository
The product (`app/`) is separated from the agent harness (root: CLAUDE.md, devlog, openspec, workflows, hooks, scripts). The boundary is hard: "nothing in `app/` references the outside", so the product can be mechanically separated and handed to the client. `app/` may be a folder in the same repo or a git submodule pointing to a separate repository.

### 1.2 CLAUDE.md — a charter with a blocking GATE
The same skeleton in every project:
- **Operating contract / Constraints** — 5–7 inviolable rules at the top of the root `CLAUDE.md`, which Claude Code loads into every session and reloads after compaction ("canon goes to places that are guaranteed to be read; an unopened file does not cure forgetting"); hard rules are additionally held by hooks and scripts, not by text.
- **GATE before any code** (3 blocking steps): skills by task type (brainstorming → writing-plans → TDD; systematic-debugging for bugs; verification-before-completion for any commit) → feature branch `r{N}/{type}-{description}` (code in main is forbidden, docs are allowed) → read CODING_STANDARDS + the per-layer standard + naming.yaml.
- **Engineering Principles stated explicitly, addressed to the model**: "without explicit principles the model builds spaceships" (KISS/YAGNI/MVP/Fail Fast/OpenSpec-driven).
- `AGENTS.md` — a thin `@CLAUDE.md` alias for other coding agents.

### 1.3 Devlog — the agent's persistent memory between sessions
- Reverse chronology; the entry template sits as an HTML comment at the end of the file: `Done / Decisions / Open questions / Next session / Harness changes`.
- **The session loop is blocking**: on opening — read the latest entry BEFORE any action; on closing — write a new one. "Next session" is a concrete first step, not "continue working".
- **Mechanical enforcement**: `.githooks/pre-push` blocks pushing code without a devlog update (docs-only pushes pass).
- `merge=union` in .gitattributes — only for the devlog (an append-only log); for files with line edits, union = "silent corruption instead of a loud signal".
- Known gap: the devlog's "Open questions" do not reach the tracker and are invisible in the queue → rule: file them in bd immediately.

### 1.4 OpenSpec — the release register
`openspec/changes/r{N}-{name}/`: proposal (always) / design (delta, only for architectural changes) / specs/*/spec.md / tasks (always) / SHIPPED. Plus a second, "narrative" layer: `docs/superpowers/specs/*-design.md` (the brainstorming spec) and `plans/*.md` (a plan with the **full code** of the RED test and the implementation for every task — the subagent works to a contract, not to a description).

Conventions: name without a date (the date is in the git log); the folder lives forever as "why it was done this way"; after r1, code is the source of truth and the spec is only a delta; a hotfix gets no folder; the proposal has a **"Decisions (taken, do not revisit)"** section against re-discussion by the agent and a **scope fallback** ("closing a release green after a risky item fails is valid — not a failure").

**`r{N}` is a train, not a release**; the number lives only in the file `openspec/CURRENT_TRAIN`, incremented **only by a human** (no agent guesses N).

### 1.5 Queue — beads (bd), synced through git-JSONL
A local bd store per worktree; the queue travels between machines and people as `.beads/issues.jsonl` in git, not through `bd dolt push/pull` (conditions for return — in base `.beads/README.md`). Automatic `bd import` from post-merge/post-checkout git hooks. External trackers (client trackers, GitHub Issues, Linear) are facades. Pitfall: beads takes over `core.hooksPath` → install-git-hooks.sh with diagnostics. A conflict in issues.jsonl is resolved through the store, not line by line.

### 1.6 Execution: subagents + orchestrator
- **Model roles**: coding by mid-tier subagents; orchestration and review by the main agent on the strongest model. The cheapest models/low effort are rejected for production stages.
- **The core is not delegated**: financial math, layer contracts, migrations stay with the orchestrator; the periphery is delegated.
- **Parallelism by disjoint file zones** — checked deterministically (`pairwiseDisjoint(files)`) **in code, not by an LLM**.
- **One integrator agent = the only writer to git and bd** (removes index.lock races); implementation agents only write code + tests and do not commit.
- Plans carry the header "For agentic workers: REQUIRED SUB-SKILL: superpowers:subagent-driven-development".

### 1.7 Review — multi-layered, and it makes mistakes
- Two-stage review (spec + quality) per task/phase + a final holistic review, OR a fan-out by dimension (design / tests / simplify) on a large diff.
- Multi-agent code review before merge (several independent angles).
- **360 review** — a read-only genre: N parallel agents along axes (code, frontend, tests, completeness against the client's requirements, idea↔implementation coherence, production readiness); the result is only a diagnosis + a prioritised plan of fix releases.
- **Review findings are verified and may be rejected with a justification.**
- **An external independent reviewer (a different model/vendor) catches what your own tests miss.**
- **The finding format and triage rules are canonical**: [templates/base/docs/review-contract.md](../templates/base/docs/review-contract.md) — five mandatory elements of a finding, clean_check ("clean" also has to be proven), `user_decision_required`, a wave limit (2 for implementation / 3 for a spec), a spec skeptic. Prior art: molyanov-ai-dev.

### 1.8 Quality gates
- The test pyramid as policy: the main trust layer is chosen by the project's profile; E2E is a release gate, not per-PR; an explicit "what we do NOT test" + the project's anti-pattern catalogue.
- Standard report formula: `lint ✓ · tests N ✓ · build ✓ · doc-links ✓ · live check on the stand ✓`.
- pre-commit empty/fast; the full suite on pre-push (once per push) and in CI.
- EVALS with a baseline for everything LLM-nondeterministic (not a hard fail, but a deviation must be explained; ×3 runs for stability).
- FOUND_BUGS + xfail quarantine: a bug found by tests in a branch is NOT fixed in that branch (otherwise an uncontrolled refactor) — a separate fix branch removes the xfail.
- "Silent fake success" is a distinct, catchable class of defects; rule: **a loud signal beats silent corruption**.

### 1.9 Human acceptance
- **Release record**: acceptance of a release = the owner's "yes" + `SHIPPED.md` (header: date, PR, merge commit, card, bd epic → what actually shipped → what was postponed and why → found by review, moved out of the branch → retro). Format — `templates/base/openspec/README.md`. Gates that can be listed explicitly: review (diff invariant), evals (threshold), migration (+ rollback), smoke (numbered scenarios with a data check), flag (switch off → "previous release bit for bit"), counter-metrics ("a query after 2–3 days"), push.
- **REVIEW.md — the shift hand-over**: TL;DR, "How to review (15 minutes)", **"Decisions taken for you"** (What was chosen | Why | Alternative), "If you want it differently" (the rollback cost of each decision).
- **Autonomy fuses**: no push/merge/deploy without an explicit "yes" (repeated in several places, including hooks); an emergency flag `APP_{FEATURE}_ENABLED` per feature with proven "off = bit for bit"; caps on loops (turns, number of PRs, max rounds + stop on no progress).
- **The autonomy mode is granted by a user directive** and quoted in the devlog ("work autonomously, I'll come for the final review" / "do it without me" / a live-review mode without tests that records the DEBT).

---

## 2. Unattended work in remote sessions

Canonical scope: **one feature at a time per development session, with a mandatory verification gate**. More features in parallel or more projects come only after one is proven live.

Key elements:
1. **Topology**: a server you control; per project one long-lived `claude remote-control` development session, each in its own git worktree; the owner drives the sessions from claude.ai on the web or the phone. Code and harness live in one tree (code in `app/`); ordinary `git push/pull` to the git host.
2. **Sessions talk to each other by name.** The On-call session (`feedback-desk`) holds the client chat channel, acknowledges a request, forwards it verbatim to the development session and posts the answer back. The production monitor (`prod-monitor`) is a model-free cron watchdog that wakes a read-only agent only on a real anomaly; its verdict arrives in the On-call session as a channel event and goes to the group and the development session.
3. **Feature work** — the development session launches the feature pipeline (`feature-pipeline` module: Workflow scripts `feature-auto` → `feature-core` / `feature-lite`): plan → test-first chunks → integration in its own worktree → local commit, stopping before the PR. **The real outcome is in the result's `error` field**, not in its status. The merge happens after a human "yes" (`scripts/merge-feature.sh`).
4. **Execution tiers** by the `scale` label (set by a human): auto / core (epic graph) / lite; default lite. Most of the orchestration cost of a small feature is the orchestration itself, so the lite "small path" is several times cheaper.
5. **Unattended means booked by the session itself.** "Run it tonight" or "every morning review production" — the session schedules the run with native scheduling (`send_later`, `CronCreate`, scheduled tasks in the server environment).
6. **Quota guard** (base): near the subscription limit hooks stop new work (80%), ask to wrap up — WIP commit, devlog, queue state (85%), and allow only saving work and scheduling a continuation (90%); the session books its own continuation after the reset. The quota comes from the server's rate-limit data, measured outside the agent.
7. **Environment awareness**: an environment marker (`.claude/env`) + a capability block printed at session start + **structural backstops** (the physics of the environment, guard hooks with exit 2, `stopBeforePR` in the pipeline code, the sandbox) — not "the agent's conscience".
8. **Run isolation along three axes**: tasks (assignee scope), files (worktree), ports.
9. **Gates**: a docs-only guard (false done) + a functional verification gate with a fix cycle (2 attempts, then an honest fail). An autonomous run closes only its own subtasks; the parent task is closed by `merge-feature.sh` at merge.
10. **Protection model**: three fear modes (hang / runaway loop / the irreversible); the irreversible is excluded structurally (the run stops before the PR; merge and deploy need a human); the loop discriminator is progress × spend; wall-clock is a dead-man switch, not a regulator; a worktree ≠ a sandbox (§3).
11. **Human acceptance is the main value of the line**: a "green" autonomous feature can have a UX defect that only a live review catches.
12. **Status finalisation and contract compliance live in pipeline code, not in an instruction to the agent** — an agent breaks "set a label instead of `bd close`" until the rule is in code.

---

## 3. Infrastructure and setup

- **The server**: one machine you control runs the long-lived sessions (a development session per project, the On-call session) and the monitor watchdog; all of them come back after a reboot. Cloud sessions are not used: they lack the chat channel, two-way messaging with other sessions, and local access to hosting tools, the dev environment and production read access.
- **Three-layer provisioning**: (1) a one-off bootstrap (root) — personal environment + Claude CLI; (2) an unprivileged user for the sessions; (3) the project's provisioning script — the minimal toolchain delta. Idempotent, "just say go". **The agent never runs as root** (and refuses skip-permissions as root by itself).
- Secrets: generated, or entered by the owner interactively (`read -s`) — "the agent never sees the value"; a ship token comes from the OS keychain, outside the agent's context.
- Host specifics (ports, addresses) do not leak into the repository: CLI flags + a local launch.json.
- Claude auth — OAuth under a subscription, not an API key.
- Access only through a private network (tailnet); public SSH is closed.
- **Sandbox**: a worktree isolates files and git, not commands. Base enables the built-in Claude Code sandbox (filesystem writes limited to the working directory, a network domain allowlist, denied or masked secrets for Bash) plus `permissions.deny` for the Read/Edit tools; enabling it is an explicit question at deployment, a "no" is recorded as a deviation in the registry.
- No state on the server beyond git (git-JSONL + the git host) → losing the machine costs only an uncommitted worktree; re-creation takes minutes.

---

## 4. Cross-cutting principles

1. **Structural fences instead of instructions.** Everything critical ("do not push", "do not leave the perimeter", "do not close tasks") is closed by the physics of the environment, guard hooks and orchestrator code, not by prompt text. An agent breaks instructions; it cannot break fences.
2. **The human is the Acceptor, and that is not a temporary crutch.** A live review catches a class of defects unreachable for automated tests and static checks.
3. **Autonomy is granted in steps by measured acceptance** (ladder A1→A3→…, red lines, counter-metrics, reversibility of every action).
4. **Memory = log + queue, both in git.** The devlog for context, beads for work; enforced by hooks; nothing important lives only in the session's head.
5. **Preparation is separated from execution.** A human with the development session prepares the spec, the task graph and the scale label; the feature pipeline consumes them and chooses neither scope nor tier.
6. **Cost is standing context, not generation.** Rule of thumb: cost ≈ number of agents × the standing context each one loads; the small path by default; orchestration only when the feature is worth it; the choice of path is confirmed by a human explicitly.
7. **A loud signal beats silent corruption** (a fake-green sync, a docs-only "done", union merge, a false-green E2E — each caught and turned into a guard).
8. **Do not trust agents' self-reports** — commit messages, "✓" ticks, verdicts of review agents; verify by running, grepping, or a human. Canonical format — [templates/base/docs/review-contract.md](../templates/base/docs/review-contract.md).
9. **Every closed door comes with conditions for return.** Rejected alternatives are recorded with reasons (idea graveyards, ADRs with reversibility).
10. **Artifact status is stated, not implied**: "✅ exists / 🟡 template, not activated / 🔜 needed" — right in the runbook and SKILL.md.
11. **N=1 live first, then scale** — building N=2 before N=1 is proven is premature.
12. **One project language, set per project (default English); English is the language of the tooling.** Agent messages are human-readable prose, not telegraphese.
13. **Layer by strength of guarantee + cost of context**: a guarantee → a hook/permission (deterministic code the model cannot bypass); a procedure → a skill (loaded only when invoked); knowledge → a rule/standard loaded on demand; the always-on context holds only what must be true on every turn. Every harness addition is paid for in tokens per turn — the cost is counted before adoption.

---

## 5. Filter for adopting harness changes (checklist)

> The entry filter of the improvement loop "review pass → decision → materialisation → rollout".
> Check in order, stop at the first "no".

0. **A problem, not a tool.** Name an observed episode from recent project work that this solves. No episode → backlog, not work.
1. **Already covered?** By the existing canon; by what is built into Claude Code (check against current docs, not an article); by installed plugins.
2. **Layer by strength of guarantee** (principle 13). Needs always-on context → almost automatic rejection.
3. **Cost of ownership.** Tokens per turn/invocation; lines of code and config to maintain; external dependencies.
4. **One source of truth.** Does it create a second home for an existing fact; if it replaces one, the old home is removed in the same change.
5. **Portability.** Works on all machines and projects of the factory; does not codify one person's personal practice; rolls out through the existing channel (canon → review pass → registry).
6. **A pilot with an abandon criterion recorded in advance.** One project, time-boxed; what counts as failure is fixed before the start.
7. **Record the outcome either way** — a row in [open-questions.md](open-questions.md) (§1 open or §2 settled/rejected, with the condition for return). Accepted → materialisation in `templates/`, rollout during the review pass.
