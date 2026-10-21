# Dark factory: methodology

"Dark factory" (lights-out manufacturing for software development) — features produced by agents with minimal human presence. The human stays in three roles: **client** (what to do), **preparer** (spec, decomposition, tier label) and **acceptor** (morning review, merge, production). Everything else is the machine.

The same approach can be run at different maturity levels:

| | Interactive | Autonomous releases | Night loop |
|---|---|---|---|
| Mode | interactive sessions + one-off "do it without me" directives | autonomous releases in a worktree, optionally an e2e-autofix loop in CI | **a night loop** executing a prepared queue unattended |
| Unit of work | release = session | release `r{N}` | a release **train** (`r{N}` ≠ release) |
| Acceptance | "I'll come for the final review" | a release record + review hand-over | the morning ritual (assumptions ∧ live check ∧ CI) |

---

## 1. Process core

### 1.1 Harness / product — two layers of the repository
The product (`app/`) is separated from the agent harness (root: CLAUDE.md, devlog, openspec, workflows, hooks, scripts). The boundary is hard: "nothing in `app/` references the outside", so the product can be mechanically separated and handed to the client. `app/` may be a folder in the same repo or a git submodule pointing to a separate repository.

### 1.2 CLAUDE.md — a charter with a blocking GATE
The same skeleton in every project:
- **Operating contract / Constraints** — 5–7 inviolable rules at the top, duplicated in the SessionStart/PreCompact hooks ("canon goes to places that are guaranteed to be read; an unopened file does not cure forgetting").
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

**`r{N}` is a train, not a release**; the single source of truth for the number is the file `openspec/CURRENT_TRAIN`, incremented **only by a human** (the night does not guess N).

### 1.5 Queue — beads (bd), synced through git-JSONL
Dolt federation is rejected (version fragility, migration bugs, data outside git) — a "consciously closed door" with recorded conditions for return. Automatic `bd import` from post-merge/post-checkout git hooks. External trackers (client trackers, GitHub Issues, Linear) are facades. Pitfall: beads takes over `core.hooksPath` → install-git-hooks.sh with diagnostics. A conflict in issues.jsonl is resolved through the store, not line by line.

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

## 2. Night loop

Canonical scope: **1 feature per night on 1 project with a mandatory verification gate**. Scaling (N>1, multi-project) comes only after N=1 is proven live.

Key elements:
1. **Topology (canon: "local night")**: one machine (a workstation or a VPS), code and harness in one tree, code in `app/`. The night runs in tmux over ssh (or from a systemd unit) with ordinary `git push/pull`, no relay; it stops BEFORE ship; in the morning a human Acceptor takes over. A relay variant (a 24/7 VPS brain plus a machine inside a restricted network perimeter) is possible for projects whose code or data cannot leave a perimeter, but it is not part of the canon.
2. **Environment awareness**: an environment marker (`.claude/env`) + a capability matrix + **three structural backstops** (the physics of the environment, a guard hook with exit 2, `stopBeforePR` in code) — not "the agent's conscience".
3. **Execution tiers** by the `scale` label (set by a human): auto / core (epic graph) / lite; default lite. A cost audit shows that most of the orchestration cost of a small feature is the orchestration itself → the lite "small path" is several times cheaper.
4. **Run isolation along three axes**: tasks (assignee scope), files (worktree), ports.
5. **Night gates**: a docs-only guard (false done) + a functional verification gate with a fix cycle (2 attempts, then an honest fail). The night never closes tasks — it only sets a label (e.g. `night-done`).
6. **Protection model**: three fear modes (hang / runaway loop / the irreversible); the irreversible is excluded structurally; the loop discriminator is progress × spend; wall-clock is a dead-man switch, not a regulator; quota is measured from outside, from the transcript JSONL; a worktree ≠ a sandbox (a disposable offline box is a sandbox; on a workstation use a container or the built-in sandbox, see [decisions/mac-sandbox.md](decisions/mac-sandbox.md)).
7. **The morning ritual** is the main value of the loop: a "green" autonomous feature can have a UX defect that only a live review catches.
8. **Status finalisation and contract compliance live in orchestrator code, not in an instruction to the agent** (an agent will repeatedly break "set a label instead of `bd close`" until the rule moves into code).

Variant — **e2e-autofix in CI**: the nightly E2E fails → a CI agent triages from artifacts (ladder: infrastructure ≥80% → one issue; flaky → label, do not fix; rollup root cause → fix), files issues, opens PRs marked "DO NOT AUTO-MERGE", with caps on PRs and turns. A cheap lights-out loop without your own hardware; include it in a template only after it is debugged.

---

## 3. Infrastructure and setup

- **Three-layer provisioning**: (1) a one-off bootstrap (root) — personal environment + Claude CLI; (2) an unprivileged user for the loop; (3) the project's provisioning script — the minimal toolchain delta. Idempotent, "just say go". **The agent never runs as root** (and refuses skip-permissions as root by itself).
- Secrets: generated, or entered by the owner interactively (`read -s`) — "the agent never sees the value"; a ship token comes from the OS keychain into the container environment, outside the agent's context.
- Host specifics (ports, addresses) do not leak into the repository: CLI flags + a local launch.json.
- Claude auth — OAuth under a subscription, not an API key.
- Access only through a private network (tailnet); public SSH is closed.
- No state on the VPS (git-JSONL + the git host) → losing the machine costs only an uncommitted worktree; re-creation takes minutes.

---

## 4. Cross-cutting principles

1. **Structural fences instead of instructions.** Everything critical ("do not push", "do not leave the perimeter", "do not close tasks") is closed by the physics of the environment, guard hooks and orchestrator code, not by prompt text. An agent breaks instructions; it cannot break fences.
2. **The human is the Acceptor, and that is not a temporary crutch.** A live review catches a class of defects unreachable for automated tests and static checks.
3. **Autonomy is granted in steps by measured acceptance** (ladder A1→A3→…, red lines, counter-metrics, reversibility of every action).
4. **Memory = log + queue, both in git.** The devlog for context, beads for work; enforced by hooks; nothing important lives only in the session's head.
5. **Preparation is separated from execution.** A human (or a day session) prepares the spec/graph/tier label; the night only consumes. A dispatcher that splits a prepared graph is a bug.
6. **Cost is standing context, not generation.** Rule of thumb: cost ≈ number of agents × the standing context each one loads; the small path by default; orchestration only when the feature is worth it; the choice of path is confirmed by a human explicitly.
7. **A loud signal beats silent corruption** (a fake-green sync, a docs-only "done", union merge, a false-green E2E — each caught and turned into a guard).
8. **Do not trust agents' self-reports** — commit messages, "✓" ticks, verdicts of review agents; verify by running, grepping, or a human. Canonical format — [templates/base/docs/review-contract.md](../templates/base/docs/review-contract.md).
9. **Every closed door comes with conditions for return.** Rejected alternatives are recorded with reasons (idea graveyards, ADRs with reversibility).
10. **Honest artifact status**: "✅ exists / 🟡 template, not activated / 🔜 needed" — right in the runbook and SKILL.md ("Verification status (honest)").
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
7. **Record the outcome either way** — a row in [open-questions.md](open-questions.md) (§1 open or §2 resolved/rejected). Accepted → materialisation in `templates/`, rollout during the review pass.
