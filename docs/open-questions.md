# Forks and open questions

## 1. Open forks (decide here)

1. **Tracker facade**: ROADMAP.md vs Linear (one workable mapping: Project = stage, Issue = release, sub-issues = blockers, Cycles rejected) — develop a common rule or decide per project?
2. **Several projects on one VPS** — by construction there are no conflicts (port lanes), but this is not verified in practice.
3. **Morning report** — the output of the line (a human-readable digest of the night) is described but not built as a script; intake has its skills (`board`, `transcript-intake`). The factory needs both the input and the output of the line.
4. **Usage-watchdog calibration** — a pilot night measuring "JSONL sum → % of the 5-hour window" against the provider's console; until then the thresholds are stubs.
5. **ADR "autonomous night development"** — write it here as a normative factory document: what exactly may be pushed without supervision (harness state only).
6. **Autonomy ladder for the developer agent** — formalise along A1→A3 (steps: proposes a diff → commits to a branch → opens a PR → merges; transitions by measured acceptance; red lines; reversibility).
7. **Agent-level guarantees for base** — Claude Code hooks (PreToolUse, argv parsing) can close exactly the holes that `.githooks/pre-push` documents as bypasses: `--no-verify`, force-push, a code commit to main before the command runs; plus the permissions/sandbox perimeter in settings.json (denyRead for secrets, a network allowlist) and `disable-model-invocation: true` on skills with side effects (`board`/`ship` currently state the same rule in prose). Related: **a plugin as the rollout channel** for the skill-and-hook half of base ("bump the version → the whole team has it") versus manual reconciliation during the review pass. Run it through the filter in methodology §5, pilot on one project.
   - **First cheap step**: a candidate-diff check (CI/hook verifies it works on the tree it thinks it does: clean tree, base SHA is an ancestor) — the same class of problem as a hooks path silently pointing elsewhere; plus `disable-model-invocation: true` for `ship`/`board`.
8. **toolchain.json — "five verbs"** (lint · format · test + SAST · deps-audit) as a stack-neutral contract for base: hooks and rituals read the verbs from `.claude/toolchain.json` instead of hard-coded TEST_CMD placeholders in pre-push.
   - Argument for it: while the test command is hard-coded in the body of `pre-push`, a project rewrites the whole hook for its stack and loses fixes made in the canon (e.g. push-range detection and the non-HEAD warning).
9. **Devlog grep contract** — fixed class-A tokens (`## YYYY-MM-DD`, `problem:`, `correction:`, release id): mechanics grep instead of reading the whole file (a long-lived devlog grows to hundreds of kilobytes); `problem:` entries are consolidated into the proposal's "Implementation summary" when shipped; `correction:` tags → a proposal for a new rule on repetition, only with approval. Changes the session loop of live projects — only through a pilot under the §5 filter.
10. **Evidence gates: a principle with a limiter.** The idea "a gate is executable code, not a statement" is adopted in a limited form: a gate checks a **process invariant** (links, secrets, test layering, GATE checkboxes), not a one-off fact of a release; a one-off release gate is allowed only with mandatory archiving no later than the next release. Without the limiter, gate scripts can outgrow the application itself. Anti-pattern: versioned JSON contracts v1…v7 with no "current".
11. **`.claude/workflows/*` when deploying base.** Night-loop workflows belong to the `night-local` module; `deploy-project` must not copy them without the module, and projects that already have stale copies should remove or replace them.
12. **Pyramid profiles** — unit-first by default when the project is silent, contract-first by declaration (§2). Revisit the default if the ratchet on unit-first projects gives false rejections or the unit share does not grow over a train; revisit "the machinery lives in base" if a project not on the Python/`app/` topology asks for it as a module.

## 2. Resolved forks (do not revisit without a reason)

| Fork | Decision |
|---|---|
| Canonical night loop variant | "local night": one machine, ordinary git, no relay (see [layers/production.md](layers/production.md)); e2e-autofix in CI enters the template only after it is debugged; the full VPS + relay setup is an unfinished delegation mechanism, not the canonical answer to a network perimeter |
| Release acceptance format (a separate HUMAN_GATES file?) | no separate file: release acceptance = the owner's "yes" + `SHIPPED.md` (header: date, PR, merge commit, card, bd epic → what actually shipped → what was postponed and why → found by review, moved out of the branch → retro). Format — `templates/base/openspec/README.md` |
| A fleet of reviewer agents as canonical files | not needed: the canonical [review-contract.md](../templates/base/docs/review-contract.md) is enough; two waves of read-only subagents catch critical issues; there is no third wave — the remaining findings go to bd |
| Night engine: a hosted agent platform vs own workflow | own workflow (a cloud platform cannot reach a closed perimeter; weak in git/MCP) |
| Dolt federation for bd vs git-JSONL | git-JSONL + auto-import by hooks; conditions for return recorded |
| Auth: API key vs OAuth | OAuth under a subscription |
| A restricted database at night on the VPS | no: a CI gate + local access on a workstation |
| Wall-clock as a quota regulator | no: a dead-man switch; quota only via a usage watchdog from outside |
| The cheapest model / low effort for cheap stages | no: a mid-tier model at medium effort minimum |
| Live design check in the autonomous path | no: a live visual check is a human morning step |
| "The core builds the graph from the spec" | no: preparation builds the graph, the core is a consumer |
| Slimming the system brief | no: about −10% at a risk to quality |
| Per-agent Docker on the VPS; microVM | no: a disposable offline box is the sandbox; microVM — only for multi-tenancy |
| Relay harness for a project without a perimeter | do not transfer: the VPS is equal to the workstation |
| Full mapping into Linear (release = Project, task = Issue) | collapsed: Project = stage, Issue = release, sub-issues = blockers; Cycles rejected |
| tasks.md into the tracker | no: a TDD micro-step lives for minutes, its consumer is the agent |
| `merge=union` for ROADMAP | reverted: union only for append-only files |
| CI action for summaries | a Claude routine (subscription without API keys) |
| Splitting an epic across several branches | no: one epic = one branch/PR |
| Archiving openspec folders | no: they live forever as "why it was done this way" |
| Chat mode / streaming / open-ended intent | an idea graveyard with reasons |
| Three layers of the factory repository | methodology = `docs/`, template = `templates/` (canon), instance = your own `.claude/` + registry; the factory is project #0 deployed from its own template |
| Rolling template improvements out to live projects | manually: reconciliation with `templates/` is a mandatory item of the review pass, the result goes to the registry; switch to an automatic diff at 3+ projects from the template or 2 missed reconciliations |
| Canon rollout: the automatic-diff threshold reached | once several projects run from base and reconciliations get skipped, projects keep fixing what the canon already fixed and borrow from each other directly. Decision: `scripts/harness-diff.sh` + `.harness/base-sha` in base, a line in SessionStart, the registry's "Reconciliation" column filled from the script's output |
| Pyramid: unit or integration as the base | two named profiles, **the project declares its own at deployment** (question 2 of the base MANIFEST); silence = **unit-first** (unit 50–60 %); contract-first has integration as the base (seams such as DSN parsing, special characters in passwords, the wrong database driver — unit tests do not catch them). The machinery (layer = directory + auto-marker + meta-test, `pyramid.py`, e2e skeleton) stays in base, not in a module: base is already Python/`app/`-shaped, and module rollout is exactly what does not work. The ratchet guards the base share of the declared profile, not unit unconditionally. Argument for unit-first: under "integration-heavy is fine", the unit share drifts down to about a third within a month |
| User guide: "later" or a gate | a gate for features with UI **in projects with a user-facing UI — a flag at deployment** (question 3 of the base MANIFEST, default "yes" for an SPA; "no" for a bot or a service with its own help packaging). Mechanics: GATE step 3 + "Finishing a feature", screenshots by a script from the e2e layer, a hash manifest, a meta-test (skipped without the folder). Reason: when the guide is not in the "Finishing a feature" list, it does not get written |
| E2E: "when a seam appears" or a skeleton from day one | a skeleton in base (`tests/e2e/conftest.py`, smoke, marker, a `browser` job on dispatch and on tag, pre-push on frontend paths). Without it, the browser layer does not run in CI at all |
| CI: the full matrix on every push or tiers | tiers `quick` (PR) / `full` and `browser` (dispatch, release tag) / `secret-scan` (PR, trufflehog) |
| deploy-project mechanics: wizard/generator vs skill | a skill ("nothing home-grown"); steps that have settled are made deterministic in scripts — "the skill is the frontier, the script is the sediment" |
| Sandbox on a workstation: Docker/bwrap vs built-in | the built-in Seatbelt sandbox of Claude Code (filesystem/network/secrets for Bash) + `permissions.deny` for Read/Edit; in base behind an explicit question at deployment; a devcontainer is tier 2, only for night-local ([decisions/mac-sandbox.md](decisions/mac-sandbox.md)) |
