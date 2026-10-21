# base — deployment manifest

> What is copied into a new project and what to fill in. Use the `deploy-project` skill or follow this procedure by hand; after deployment — a row in the deploying factory's registry (`registry.example.md` in this repo is the template) with the commit SHA of `templates/`.

## Dependencies

- **Claude Code**; the **Superpowers** plugin is recommended (GATE step 0 names its skills)
- **beads** (`brew install beads`) — task queue
- **gh** CLI (for `merge-feature.sh`; two-repository projects override it)
- **jq** — normalization and the beads queue guard (`bd-export.sh`, `bd-queue-guard.sh`, the pre-commit hook), the closed-task line in `merge-feature.sh` (`beads-queue-line.sh`)
- **pytest-playwright** + Chromium (`playwright install chromium`) — the e2e layer and user-guide screenshots; installed into the project's test group
- Linear MCP — for the `board` skill

## Questions at deployment (answers go into the registry, column "Contents/Deviations")

1. **Sandbox**: do we enable `sandbox` + `permissions.deny`? Default "yes"; "no" → remove the blocks.
2. **Pyramid profile**: unit-first or contract-first? Default **unit-first**; contract-first when the risk is at the seams with a live dependency (see CODING_STANDARDS §Test pyramid). The answer is written by the first `scripts/pyramid.py --write-baseline --profile <…>` and into the project's CODING_STANDARDS.
3. **User guide**: is there a user UI for people? Default "yes" for an SPA/screens; "no" (bot, library, own help packaging) → remove `docs/user-guide/` and `app/tests/unit/test_user_guide.py`, mark GATE step 3 in CLAUDE.md as "does not apply".

## Contents and placeholders

| Artifact | Fill in |
|---|---|
| `CLAUDE.md` | Overview/stack, language, branch, project principles and prohibitions |
| `devlog.md` | date of the first entry |
| `CODING_STANDARDS.md` | layers, prohibitions, "what we do not test", project language; in "Logging and LLM" — the rule on user text in logs, the prompts directory, the tracer |
| `DOCUMENTATION_STANDARDS.md` | the "Where we keep it" table, user-guide roles (§6), tone examples (§3) |
| `naming.yaml` | glossary and domain units; **mandatory** — GATE step 2 requires reading it before any code |
| `README.md` | **created at deployment** — CLAUDE.md onboarding starts with it: what it is and how to run it |
| `.claude/settings.json` | contract echo text; network allowlist of the `sandbox` block (stack and project domains) — enabling the sandbox is confirmed by an explicit question at deployment; with "no" the `sandbox`/`permissions.deny` blocks are removed |
| `.claude/hooks/env-context.sh` | capability block texts |
| `scripts/quota.py`, `scripts/test_quota.py` + quota hooks in `.claude/settings.json` | — (Claude subscription quota watchdog, mandatory; thresholds and bypass via env, the "save" path layout via `SAVE_PATH_RE`; [docs/quota-guard.md](docs/quota-guard.md)) |
| `.claude/hooks/ensure-git-hooks.sh` | — (self-healing of `core.hooksPath` at session start) |
| `.claude/hooks/session-context.sh` | — (session header: branch, latest devlog entry, main merges) |
| `.claude/skills/feature-sanity-check/SKILL.md` | bd prefix, product direction document, project hot paths |
| `.claude/skills/investigate/SKILL.md` | the "Project sources" table (commands, keys, **measured** retention), project root-cause classes; verify with a live preflight run |
| `.claude/skills/code-audit/SKILL.md` | — (the method is generic; fan-out across many repositories — the `code-audit` module) |
| `.claude/skills/stand/SKILL.md` | **filled in from the first live run of the stand**: topology, commands to bring up/smoke/clean up; do not change the stand rules. Project without a stand — delete the skill |
| `.claude/skills/board/SKILL.md` | Linear workspace/team/project, the client's tracker |
| `.claude/skills/transcript-intake/SKILL.md` | — (needs no configuration) |
| `.claude/skills/openspec/*` | — (needs no configuration; cycle reference + artifact templates). The `docs/` folder is absent from the template — populate it at deployment: `scripts/fetch-openspec-docs.sh`, commit the snapshot |
| `.claude/skills/openspec-to-beads/*` | — (needs no configuration) |
| `.claude/skills/ship/SKILL.md` | branch, merge strategy, exceptions, one/two repos |
| `.claude/workflows/*` | not in base — the feature pipeline is the `templates/feature-pipeline/` module |
| `.githooks/pre-push` | TRIGGER/CODE_PATTERNS, MAIN_REF, TEST_CMD; `E2E_GATE=1` + `E2E_PATTERNS` — once a frontend appears |
| `.githooks/pre-commit` | — (beads queue guard + normalization; requires jq) |
| `.gitattributes` | — (`devlog.md merge=union`); if the project has its own `.gitattributes`, append the line |
| `.gitignore` | append `/issues.jsonl` (the bd hook drops a duplicate export into the root) |
| `.harness/base-sha` | **created at deployment**: SHA of the canon's `templates/` (`git -C <canon> rev-parse HEAD`); read by `scripts/harness-diff.sh` and `env-context.sh` |
| `.harness/modules.md` | — (catalog of canon modules; at deployment go through it and ask the owner about modules whose "time to install" sign is already present) |
| `.harness/pyramid-baseline.json` | created by the first `scripts/pyramid.py --write-baseline --profile <unit-first\|contract-first>` once tests exist; ratchet on the share of the profile's base layer |
| `app/tests/integration/test_merge_feature_beads.py` | — (tests `beads-queue-line.sh` and task closing in `merge-feature.sh` on a temporary repo with gh/bd stubs; requires jq) |
| `app/tests/{conftest.py, README.md, unit/test_layers.py, unit/test_user_guide.py, e2e/*}` | project fixtures in `conftest.py`, `FORBIDDEN_IN_UNIT` in the meta-test, `STAND_COMMAND` and `<Project>` in e2e; the `app/` topology is the same as for pre-push. In `app/pyproject.toml`: `[tool.pytest.ini_options] addopts = ["-m", "not e2e"]`, otherwise e2e gets into the regular run; markers are registered by conftest |
| `docs/user-guide/{README.md, images/, screenshot-manifest.json}` | only with "user guide: yes" (question 3): index for the project's roles; the sample page is replaced by the first real one; screenshot scenes go into `tests/e2e/make_screenshots.py` |
| `.githooks/post-merge`, `post-checkout`, `_bd-autoimport.sh` | — |
| `.beads/README.md` | project name |
| `openspec/README.md` | project name, layers in design.md |
| `openspec/CURRENT_TRAIN` | leave `1` |
| `.github/workflows/ci.yml` | stack steps in the `quick`/`full`/`browser` jobs, main branch name; `secret-scan` without configuration |
| `docs/feature-development-workflow.md` | stack specifics of the phases (mockups, previews) |
| `docs/review-contract.md` | — |
| `scripts/*` | merge-feature.sh: MAIN_BRANCH, MERGE_FLAG; `beads-queue-line.sh` (builds the queue with a single closed-task line, called by merge-feature.sh)/`bd-export.sh`/`bd-queue-guard.sh`/`harness-diff.sh`/`pyramid.py`/`check_doc_links.py` — no configuration (pyramid.py: the Vitest part is enabled by the presence of `app/frontend/package.json`) |

## Order

1. Copy the contents into the project root; `chmod +x` the scripts and hooks.
2. Fill in the placeholders (grep for `<`).
3. `./scripts/install-git-hooks.sh`; `bd init … && bd import`.
4. Smoke: a Claude session sees the contract echo + the env block and the line "📊 subscription quota: …"; `python3 scripts/test_quota.py` is green; `bd ready` works; pre-push is checked **without a real push** — feed ranges to the hook on stdin:
   ```bash
   # docs-only range → exit 0 without tests; code range → tests + the "devlog.md not updated" block
   printf 'refs/heads/main %s refs/heads/main %s\n' "$(git rev-parse HEAD)" "$(git rev-parse HEAD~10)" | .githooks/pre-push
   ```
   Separately: TEST_CMD must actually run **on every operator's machine** (a broken environment = a gate that is always red, "No module named pytest" etc.) — run the test command by hand at deployment.
5. `.harness/base-sha` is written by `scripts/deploy-base.sh` (full SHA of the canon `templates/` commit); after the first tests — `python scripts/pyramid.py --write-baseline --profile <answer to question 2>`.
6. A row in the factory's registry (`registry.example.md` layout): project, date, SHA of `templates/`, contents. Further reconciliation — `scripts/harness-diff.sh` during a review pass (result in the "Reconciliation" column).
