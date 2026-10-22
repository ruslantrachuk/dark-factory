# Project templates

> The canon a project is set up from, shipped inside the dark-factory plugin (`<plugin root>/templates/`):
> `base/` always, optional modules on top of it when the project has the problem a module solves. A user installs the
> plugin and runs `/dark-factory:add <module>`; no checkout of the repository is involved.
>
> **Supported stack:** GitHub (code, PRs, CI), Linear (the board), Telegram through Claude Code Channels (the client
> chat), beads `bd` (the execution queue), Postgres (monitor snapshots), and your hosting through its CLI or MCP. One
> stack, no adapters and no tools config: each skill and module that depends on a tool names its **Seam**, the place to
> rewrite to use another one. The functions and their contracts: [docs/functions.md](https://github.com/ruslantrachuk/dark-factory/blob/main/docs/functions.md#supported-stack).

## Rules

- `base/` holds the **canonical files** of the starter set, copied into a project at deployment; `solo/` the few
  files `/dark-factory:init` adds for level 0 (the merge script itself is `base/scripts/merge-feature.sh`). A factory's working
  instances live in its own private repository; improvements found there are carried back into the canon by hand during
  the review pass.
- **An instance differs from the canon only in its header, the "Configuration" section and a sanctioned overlay** —
  procedure text is identical, so reconciliation is a mechanical diff (`scripts/harness-diff.sh` in the project).
- Each module has a `MANIFEST.md`: contents, requirements, setup, design notes. A project learns about modules from the
  catalog [base/.harness/modules.md](base/.harness/modules.md), which ships with base; a new module or a change of its
  "when it is time" signal is a row in the catalog in the same commit.
- Modules are parts of the end-to-end practices in [docs/practices/](https://github.com/ruslantrachuk/dark-factory/blob/main/docs/practices/README.md).
- The registry of deployed projects and their lag behind the canon is `registry.md` in the factory instance, created from
  [../registry.example.md](https://github.com/ruslantrachuk/dark-factory/blob/main/registry.example.md).

## Install

0. The **dark-factory plugin** ([../README.md](../README.md)) is installed first: it carries the always-on hooks (the
   fence guard, the quota guard, git-hook repair), the feature pipeline workflows and these templates.
   `base/.claude/settings.json` enables it for the project.
1. `/dark-factory:add base` in the project: `deploy-base.sh <target> --dry-run`, then without `--dry-run` — copies
   `base/` without overwriting existing files, prints the template ref and the remaining `<…>` placeholders. It asks
   the configuration questions, fills the placeholders, runs the smoke checks, writes the registry row if you keep one,
   and installs `release-tag` too when the project has production. At the end it names the modules whose "time to
   install" signal is already present.
2. A module is installed by the owner's decision, with `/dark-factory:add <module>`: it follows the module's
   `MANIFEST.md` section "Setup by /dark-factory:add <module>" — the owner's own steps first, then the files, the
   filling in, the tests, the server units and a status check.

## Contents

- **base** — the project rules (`CLAUDE.md` for the project's own sections, importing the canon part `.claude/canon/CLAUDE.md` with the GATE), OpenSpec change folders, beads queue (a local store per
  checkout), the pre-push gate, CI (`quick` / `full` / `browser` / `secret-scan`), coding and documentation standards, test scaffolding
  with the layer meta-test, skills (board, ship, save, dev-stand, investigate, code-audit, openspec, openspec-to-beads,
  transcript-intake, feature-sanity-check), the merge script. The guard hook and the subscription quota guard come from
  the dark-factory plugin ([quota-guard.md](../docs/quota-guard.md)), which base enables. Always installed.
- **feature-pipeline** (`add feature-pipeline`) — the project settings for the plugin's Workflow scripts the development session launches to take
  one bd task from a spec or an OpenSpec phase to a committed, reviewed branch; stops before the PR
  ([MANIFEST](feature-pipeline/MANIFEST.md)).
- **release-tag** (`add release`) — production deploys only from a `vYYYY.MM.DD.N` tag; part of base when the project
  has production ([MANIFEST](release-tag/MANIFEST.md)).
- **feedback-desk** (`add on-call`) — the On-call session holding the client's Telegram group: receives requests, forwards them to the
  development session, replies to the group ([MANIFEST](feedback-desk/MANIFEST.md)).
- **prod-monitor** (`add monitor`) — a model-free watchdog plus a read-only monitor agent that sends real outages to the On-call session
  ([MANIFEST](prod-monitor/MANIFEST.md)).
- **observability** — business metrics contract, dashboard as code, alert catalog, log-based investigation
  ([MANIFEST](observability/MANIFEST.md)).
- **code-audit** — fan-out audit of many repositories with evidence and spot checks ([MANIFEST](code-audit/MANIFEST.md)).

## Layout

```
templates/                 (plugins/dark-factory/templates/)
├── README.md
├── solo/                 CLAUDE.md (contract block), .claude/{fences.env, settings.json}, .githooks/pre-push — for /dark-factory:init
├── base/
│   ├── CLAUDE.md (project part), CODING_STANDARDS.md, DOCUMENTATION_STANDARDS.md, MANIFEST.md, naming.yaml
│   ├── .beads/README.md
│   ├── .claude/{canon/CLAUDE.md, settings.json, hooks/, skills/}
│   ├── .githooks/pre-push
│   ├── .github/workflows/ci.yml
│   ├── .harness/{README.md, modules.md}
│   ├── app/tests/{conftest.py, README.md, api/, unit/, integration/, e2e/}
│   ├── docs/{feature-development-workflow.md, review-contract.md, user-guide/}
│   ├── openspec/README.md
│   └── scripts/{merge-feature.sh, harness-diff.sh, install-git-hooks.sh,
│                check_doc_links.py, pyramid.py}
├── feature-pipeline/     MANIFEST.md, .claude/feature-pipeline.json (the workflows: ../workflows/)
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
