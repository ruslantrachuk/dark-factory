# Project setup templates — assembly plan

> What goes into the starter set of a new factory project, and how the template layer is organised.

## Layer structure and rules

- `base/` — **canonical files** of the starter set, copied into a project at deployment. The canon lives here; your factory's working instances live in your own private factory repository (the factory itself is project #0 as a consumer of base; its global operations are a control-plane overlay). Improvements found in instances and projects are carried over into the canon **by hand during the review pass**.
- `night-local/`, `release-tag/`, `feedback-desk/`, `observability/`, `code-audit/`, `prod-monitor/` — **optional modules** on top of base, each with its own `MANIFEST.md` (contents, setup, design notes). `release-tag` — prod only from a tag, for hostings that build from a branch; `feedback-desk` — an On-call agent for the client's Telegram group on Claude Code Channels, set up by the module's skill; `observability` — metrics, dashboard, alert catalog; `code-audit` — fan-out audit of many repositories; `prod-monitor` — a prod monitor agent on the Claude Agent SDK on top of the On-call agent. The Claude subscription quota watchdog is not a module but a mandatory part of base ([base/docs/quota-guard.md](base/docs/quota-guard.md)). Modules are parts of the end-to-end cycle practices: [docs/practices/](../docs/practices/README.md). **A project learns about modules from the catalog [base/.harness/modules.md](base/.harness/modules.md)** — it ships with base and is updated via `harness-diff.sh`; a new module or a change of its "when it is time" signal is a row in the catalog in the same commit.
- **An instance differs from the canon only in its header, the "Configuration" section and a sanctioned overlay** — procedure text is identical, so reconciliation is a mechanical diff.
- Deployment is done by the `deploy-project` skill: the agent copies modules, asks for configuration, fills placeholders. **Steps that have settled are made deterministic in scripts** ([scripts/deploy-base.sh](../scripts/deploy-base.sh)); the skill stays a thin layer of questions and non-standard cases. The skill's contract: an input contract (what to ask the human), a deployment log = a row in the registry with the commit SHA of `templates/`, and a dry-run ("show what you will copy and what you will ask", no writes).
- Once more than one module exists as files with overlapping paths, modules need a machine-readable manifest: owned paths, requires/conflicts, overlay order, merge/overwrite strategy (premature for now).
- The registry of deployed projects and their lag behind the canon is `registry.md` in your factory instance, created from [../registry.example.md](../registry.example.md) (SSOT; the auto-diff threshold is defined there too).

## Starter set contents (target)

```
<project>/                        # harness (GitHub)
├── CLAUDE.md                     # charter: contract → onboarding → SESSION LOOP → GATE → principles → constraints
├── AGENTS.md                     # @CLAUDE.md
├── devlog.md                     # rules + entry template as an HTML comment
├── ROADMAP.md
├── app/                          # product (a folder or a submodule)
│   ├── CODING_STANDARDS.md + docs/standards/{api,services,…}.md
│   ├── naming.yaml
│   ├── ARCHITECTURE.md, docs/decisions/adr/
│   ├── DOCUMENTATION_STANDARDS.md
│   └── tests/{conftest.py, unit/test_layers.py, unit/test_user_guide.py, e2e/{conftest.py, test_smoke.py, make_screenshots.py}}  # ✅ in base
├── docs/user-guide/{README.md, images/, screenshot-manifest.json}   # ✅ in base — the gate for a feature with UI
├── openspec/{README.md, CURRENT_TRAIN, changes/}
├── docs/{inputs/, vision/, decisions/adr/, superpowers/{specs,plans}/,
│        feature-development-workflow.md, night-dev-runbook.md, project-audit-prompt.md}
├── .beads/ + .githooks/{pre-commit, pre-push, post-merge, post-checkout} + scripts/install-git-hooks.sh
├── .harness/{base-sha, pyramid-baseline.json}   # ✅ in base — reconciliation with the canon, test pyramid ratchet
├── .claude/{settings.json, hooks/, workflows/, skills/, commands/}
├── .gitattributes                # devlog merge=union — ✅ in base
├── .github/workflows/ci.yml      # tiers quick / full / browser / secret-scan — ✅ in base
└── scripts/{harness-diff.sh, pyramid.py, bd-export.sh, bd-queue-guard.sh, check_doc_links.py, merge-feature.sh, vps-provision.sh}
```

## Prior art

The starter set was assembled from several mature production harnesses and from public prior art:
[molyanov-ai-dev](https://github.com/pavel-molyanov/molyanov-ai-dev) (MIT), OpenSpec, beads (`bd`), the Superpowers plugin,
Diátaxis (documentation standards), Claude Code / Agent SDK / Channels.

## What to write from scratch (gaps)

1. **ADR "autonomous night dev"** — what is allowed unattended (harness state only).
2. **HUMAN_GATES.md for the night loop** — collected in one place.
3. **intake-mirror / morning-report** — the pipeline's input and output.
4. **An autonomy ladder for the developer agent** (A1 → A3).
5. Calibrated watchdog thresholds (after a pilot night).

## Module "coordination / intake"

Intake: only the OUTPUT is universal — a "card proposal" on the board (a draft umbrella: what / why / where from) confirmed by a human. Inputs are per-project adapters. The project starter set includes:

1. **An explicit note about the board in CLAUDE.md** — that a board exists (your tracker/board, if any: workspace, team), it is the SSOT of human intentions; rules: cards = umbrellas, only humans create them (the agent proposes), statuses Todo → In Progress → In Master → Shipped, the machine queue (beads) is not mirrored to the board.
2. **A ready-made board skill** — ✅ done: canon [base/.claude/skills/board/SKILL.md](base/.claude/skills/board/SKILL.md) (fill in the "Configuration" section at deployment).
3. **A transcript triage skill** — ✅ done: canon [base/.claude/skills/transcript-intake/SKILL.md](base/.claude/skills/transcript-intake/SKILL.md) ("what is new for us": a diff against the board/baseline, buckets, quotes mandatory). For projects with an external tracker — a paired "tracker mirror" adapter (not done).

The "from the head" channel (verbal bugs, thoughts on the go — every project has them, none has a carrier): the drop point is the nearest agent session of any project; the `board` skill makes capture cheap ("propose a card: …" → a draft on the board in seconds).

## Modules (not every project needs all of them)

- **base** — charter, devlog, openspec, beads, hooks, CI, standards. Always.
- **night-local** — the night loop on a Mac/VPS without a perimeter (night-dispatch + lite/core/auto + night-guard + the night-dev operator CLI + runbook). Default. **Assembled** ([night-local/MANIFEST.md](night-local/MANIFEST.md)): workflows moved here from base; not yet adapted per project — the parameter map and pilot order are in the manifest.
- **night-ci** — an e2e-autofix loop in GitHub Actions. Cheap, recommended.
- **corp-perimeter** — relay, mirror, environment matrix, ship, corporate VPN provisioning. Only for clients with a closed perimeter.
- **fork-upstream** — sync-upstream + rules for working through a partner's fork.
