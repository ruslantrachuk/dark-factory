# Forks and open questions

## 1. Open forks (decide here)

1. **Several projects on one server** — development sessions, worktrees and port lanes do not conflict by construction, but this is not verified with several projects working at the same time (shared quota, stands, the On-call session serving more than one group).
2. **The hand-over of a run** — the pipeline result carries an `error` field and the development session reports in its own conversation, but there is no fixed human-readable hand-over format (per feature: branch, what changed, assumptions — "decisions the machine took for you", where a failed run stopped and what the human must do, a link to the stand). Intake has its skills (`board`, `transcript-intake`); the output of the line needs one too.
3. **Autonomy ladder for the developer agent** — formalise along A1→A3 (steps: proposes a diff → commits to a branch → opens a PR → merges; transitions by measured acceptance; red lines; reversibility).
4. **Agent-level guarantees for base** — Claude Code hooks (PreToolUse, argv parsing) can close exactly the holes that `.githooks/pre-push` documents as bypasses: `--no-verify`, force-push, a code commit to main before the command runs; plus `disable-model-invocation: true` on skills with side effects (`board`/`ship` state the same rule in prose). Related: **a plugin as the rollout channel** for the skill-and-hook half of base ("bump the version → the whole team has it") versus manual reconciliation during the review pass. Run it through the filter in [methodology.md](methodology.md) §5.
   - **First cheap step**: a candidate-diff check (CI/hook verifies it works on the tree it thinks it does: clean tree, base SHA is an ancestor) — the same class of problem as a hooks path silently pointing elsewhere; plus `disable-model-invocation: true` for `ship`/`board`.
5. **toolchain.json — "five verbs"** (lint · format · test + SAST · deps-audit) as a stack-neutral contract for base: hooks and rituals read the verbs from `.claude/toolchain.json` instead of hard-coded TEST_CMD placeholders in pre-push.
   - Argument for it: while the test command is hard-coded in the body of `pre-push`, a project rewrites the whole hook for its stack and loses fixes made in the canon (e.g. push-range detection and the non-HEAD warning).
6. **Devlog grep contract** — fixed tokens (`## YYYY-MM-DD`, `problem:`, `correction:`, release id): mechanics grep instead of reading the whole file (a long-lived devlog grows to hundreds of kilobytes); `problem:` entries are consolidated into the proposal's "Implementation summary" when shipped; `correction:` tags → a proposal for a new rule on repetition, only with approval. Changes the session loop of live projects — only through a pilot under the [methodology.md](methodology.md) §5 filter.

Open questions of the map and of individual layers live next to them: [map.md](map.md) §6, [layers/](layers/).

## 2. Settled decisions (do not revisit without a new episode)

| Question | Decision |
|---|---|
| Where sessions run | a server you control with long-lived `claude remote-control` sessions; cloud sessions lack the chat channel, two-way messaging between sessions and local access to hosting tools, the dev environment and production read access |
| Unattended and scheduled work | booked by the session itself with native scheduling (`send_later`, `CronCreate`, scheduled tasks) |
| Coordination tools | the board in Linear for people (cards = umbrellas, claims, delivery); the bd queue for the machine; not mirrored into each other ([layers/coordination.md](layers/coordination.md)) |
| Release acceptance format (a separate HUMAN_GATES file?) | no separate file: release acceptance = the owner's "yes" + `SHIPPED.md` (header: date, PR, merge commit, card, bd epic → what actually shipped → what was postponed and why → found by review, moved out of the branch → retro). Format — `templates/base/openspec/README.md` |
| A fleet of reviewer agents as canonical files | not needed: the canonical [review-contract.md](../templates/base/docs/review-contract.md) is enough; two waves of read-only subagents catch critical issues; there is no third wave — the remaining findings go to bd |
| bd sync between machines | git-JSONL + auto-import by hooks, not `bd dolt push/pull`; conditions for return in base `.beads/README.md` |
| Auth: API key vs OAuth | OAuth under a subscription |
| A restricted database in an autonomous run | no: a CI gate + local access by a human |
| Wall-clock as a quota regulator | no: a dead-man switch; quota only via the quota guard, from the server's rate-limit data |
| The cheapest model / low effort for cheap stages | no: a mid-tier model at medium effort minimum |
| Live design check in the autonomous path | no: a live visual check is a human acceptance step |
| "The core builds the graph from the spec" | no: preparation builds the graph, the core is a consumer |
| Slimming the system brief | no: about −10% at a risk to quality |
| tasks.md into the tracker | no: a TDD micro-step lives for minutes, its consumer is the agent |
| `merge=union` | only for append-only files (the devlog); on files with line edits it is silent corruption |
| Splitting an epic across several branches | no: one epic = one branch/PR |
| Archiving openspec folders | no: they live forever as "why it was done this way" |
| Chat mode / streaming / open-ended intent | an idea graveyard with reasons |
| Three layers of the factory repository | methodology = `docs/`, template = `templates/` (canon), instance = your own `.claude/` + registry; the factory is project #0 deployed from its own template |
| Rolling template improvements out to live projects | reconciliation with `templates/` is a mandatory item of the review pass: `scripts/harness-diff.sh` + `.harness/base-sha` in base, a line in SessionStart, the registry's "Reconciliation" column filled from the script's output |
| Pyramid: unit or integration as the base | two named profiles, **the project declares its own at deployment** (question 2 of the base MANIFEST); silence = **unit-first** (unit 50–60 %); contract-first has integration as the base (seams such as DSN parsing, special characters in passwords, the wrong database driver — unit tests do not catch them). The machinery (layer = directory + auto-marker + meta-test, `pyramid.py`, e2e skeleton) stays in base, not in a module. The ratchet guards the base share of the declared profile. Revisit the default if the ratchet on unit-first projects gives false rejections or the unit share does not grow over a train; revisit "the machinery lives in base" if a project outside the Python/`app/` topology asks for it as a module |
| User guide: "later" or a gate | a gate for features with UI **in projects with a user-facing UI — a flag at deployment** (question 3 of the base MANIFEST, default "yes" for an SPA; "no" for a bot or a service with its own help packaging). Mechanics: GATE step 3 + "Finishing a feature", screenshots by a script from the e2e layer, a hash manifest, a meta-test (skipped without the folder). When the guide is not in the "Finishing a feature" list, it does not get written |
| E2E: "when a seam appears" or a skeleton from day one | a skeleton in base (`tests/e2e/conftest.py`, smoke, marker, a `browser` job on `workflow_dispatch` and on tag, pre-push on frontend paths). Without it, the browser layer does not run in CI at all |
| CI: the full matrix on every push or tiers | tiers `quick` (PR) / `full` and `browser` (`workflow_dispatch`, release tag) / `secret-scan` (PR, trufflehog) |
| deploy-project mechanics: wizard/generator vs skill | a skill ("nothing home-grown"); steps that have settled are made deterministic in scripts — "the skill is the frontier, the script is the sediment" |
| Sandbox | the built-in Claude Code sandbox (filesystem, network allowlist, secrets for Bash) + `permissions.deny` for Read/Edit, in base behind an explicit question at deployment ([methodology.md](methodology.md) §3); per-agent Docker or a microVM only for multi-tenancy |
| Evidence gates | a gate is executable code, in a limited form: it checks a **process invariant** (links, secrets, test layering, GATE checkboxes), not a one-off fact of a release; a one-off release gate is allowed only with mandatory archiving no later than the next release. Anti-pattern: versioned JSON contracts v1…v7 with no "current" |
