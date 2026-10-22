# Project templates

> The canon a factory project is deployed from: `base/` always, optional modules on top of it when the project has the
> problem a module solves.
>
> **Supported stack:** GitHub (code, PRs, CI), Linear (the board), Telegram through Claude Code Channels (the client
> chat), beads `bd` (the execution queue), Postgres (monitor snapshots), and your hosting through its CLI or MCP. One
> stack, no adapters and no tools config: each skill and module that depends on a tool names its **Seam**, the place to
> rewrite to use another one. The functions and their contracts: [docs/functions.md](../docs/functions.md#supported-stack).

## Rules

- `base/` holds the **canonical files** of the starter set, copied into a project at deployment. A factory's working
  instances live in its own private repository; improvements found there are carried back into the canon by hand during
  the review pass.
- **An instance differs from the canon only in its header, the "Configuration" section and a sanctioned overlay** —
  procedure text is identical, so reconciliation is a mechanical diff (`scripts/harness-diff.sh` in the project).
- Each module has a `MANIFEST.md`: contents, requirements, setup, design notes. A project learns about modules from the
  catalog [base/.harness/modules.md](base/.harness/modules.md), which ships with base; a new module or a change of its
  "when it is time" signal is a row in the catalog in the same commit.
- Modules are parts of the end-to-end practices in [docs/practices/](../docs/practices/README.md).
- The registry of deployed projects and their lag behind the canon is `registry.md` in the factory instance, created from
  [../registry.example.md](../registry.example.md).

## Install

0. The **dark-factory plugin** ([../plugins/dark-factory](../plugins/dark-factory/README.md)) is installed first: it
   carries the always-on hooks (the fence guard, the quota guard, git-hook repair) and the feature pipeline workflows.
   `base/.claude/settings.json` enables it for the project.
1. `scripts/deploy-base.sh <target> --dry-run`, then without `--dry-run` — copies `base/` without overwriting existing
   files, prints the template SHA and the remaining `<…>` placeholders.
2. The `deploy-project` skill ([../.claude/skills/deploy-project/SKILL.md](../.claude/skills/deploy-project/SKILL.md))
   asks the configuration questions, fills the placeholders, runs the smoke checks and writes the registry row. At the end
   it names the modules whose "time to install" signal is already present.
3. A module is installed by the owner's decision, following its `MANIFEST.md`.

## Contents

- **base** — the charter (`CLAUDE.md` with GATE), devlog, OpenSpec train, beads queue, git hooks (pre-commit queue guard,
  pre-push gate), CI (`quick` / `full` / `browser` / `secret-scan`), coding and documentation standards, test scaffolding
  with the layer meta-test, skills (board, ship, stand, investigate, code-audit, openspec, openspec-to-beads,
  transcript-intake, feature-sanity-check), the merge script. The guard hook and the subscription quota guard come from
  the dark-factory plugin ([quota-guard.md](../plugins/dark-factory/docs/quota-guard.md)), which base enables. Always installed.
- **feature-pipeline** — the project settings for the plugin's Workflow scripts the development session launches to take
  one bd task from a spec or an OpenSpec phase to a committed, reviewed branch; stops before the PR
  ([MANIFEST](feature-pipeline/MANIFEST.md)).
- **release-tag** — prod deploys only from a tag, for hostings that build prod from a branch
  ([MANIFEST](release-tag/MANIFEST.md)).
- **feedback-desk** — the On-call session holding the client's Telegram group: receives requests, forwards them to the
  development session, replies to the group ([MANIFEST](feedback-desk/MANIFEST.md)).
- **prod-monitor** — a model-free watchdog plus a read-only monitor agent that sends real outages to the On-call session
  ([MANIFEST](prod-monitor/MANIFEST.md)).
- **observability** — business metrics contract, dashboard as code, alert catalog, log-based investigation
  ([MANIFEST](observability/MANIFEST.md)).
- **code-audit** — fan-out audit of many repositories with evidence and spot checks ([MANIFEST](code-audit/MANIFEST.md)).

## Layout

```
templates/
├── README.md
├── base/
│   ├── CLAUDE.md, CODING_STANDARDS.md, DOCUMENTATION_STANDARDS.md, MANIFEST.md, devlog.md, naming.yaml
│   ├── .beads/README.md
│   ├── .claude/{settings.json, hooks/, skills/}
│   ├── .githooks/{pre-commit, pre-push, post-merge, post-checkout, _bd-autoimport.sh}
│   ├── .github/workflows/ci.yml
│   ├── .harness/{README.md, modules.md}
│   ├── .gitattributes
│   ├── app/tests/{conftest.py, README.md, api/, unit/, integration/, e2e/}
│   ├── docs/{feature-development-workflow.md, review-contract.md, user-guide/}
│   ├── openspec/{README.md, CURRENT_TRAIN}
│   └── scripts/{merge-feature.sh, bd-export.sh, bd-queue-guard.sh, beads-queue-line.sh, harness-diff.sh,
│                install-git-hooks.sh, fetch-openspec-docs.sh, check_doc_links.py, pyramid.py}
├── feature-pipeline/     MANIFEST.md, .claude/feature-pipeline.json (the workflows: ../plugins/dark-factory/workflows/)
├── release-tag/          MANIFEST.md, VERSION, .github/workflows/release.yml, scripts/release.sh, app/tests/
├── feedback-desk/        MANIFEST.md, .claude/{feedback-desk/, skills/feedback-desk/}, scripts/feedback-desk.sh
├── prod-monitor/         MANIFEST.md, .claude/{feedback-desk/ROLE.monitor.md, skills/prod-monitor/}, scripts/ops/prod_monitor/
├── observability/        MANIFEST.md, docs/deploy/{monitoring.md, monitoring-alerts.md}
└── code-audit/           MANIFEST.md, audit/, scripts/{audit-verify.wf.js, clone-group.sh}
```

## Prior art

The starter set draws on several production harnesses and on public prior art:
[molyanov-ai-dev](https://github.com/pavel-molyanov/molyanov-ai-dev) (MIT), OpenSpec, beads (`bd`), the Superpowers plugin,
Diátaxis (documentation standards), Claude Code / Agent SDK / Channels.
