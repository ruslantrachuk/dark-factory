# base — deployment manifest

> What is copied into a new project and what to fill in. Use the `deploy-project` skill or follow this procedure by hand; after deployment — a row in the deploying factory's registry (`registry.example.md` in this repo is the template) with the commit SHA of `templates/`.

> **Seams** of the [supported stack](../../docs/functions.md#supported-stack). To use another tool for a function, rewrite what its line names:
> - board = Linear: the skills `board` and `transcript-intake`;
> - execution queue = beads (`bd`, a local store per checkout, outside git): `.beads/README.md`, the `.gitignore` lines, `BEADS_DIR` in `.claude/hooks/env-context.sh`, the task lines of `.claude/hooks/session-context.sh`, the closing step of `scripts/merge-feature.sh`, the skills `openspec-to-beads`, `feature-sanity-check` and `save`;
> - code host = GitHub (`gh`): `scripts/merge-feature.sh`, the skill `ship`;
> - CI = GitHub Actions: `.github/workflows/ci.yml`;
> - hosting, production data and the LLM tracer = the project's tools: the skill `investigate` ("Project sources").

## Dependencies

- **Claude Code** with the **dark-factory plugin**, installed first (`/plugin marketplace add ruslantrachuk/dark-factory`,
  `/plugin install dark-factory@dark-factory`; [plugins/dark-factory/README.md](../../plugins/dark-factory/README.md)).
  It carries the always-on hooks: the fence guard, the quota guard and git-hook repair. `.claude/settings.json` enables
  it for the project (`enabledPlugins`) and names its marketplace (`extraKnownMarketplaces`), so every collaborator is
  offered it. Python 3.11+ for its hooks
- the **Superpowers** plugin is recommended (GATE step 0 names its skills)
- **beads** (`brew install beads`) — the execution queue, a local store per checkout (`.beads/README.md`)
- **gh** CLI (for `merge-feature.sh`; two-repository projects override it)
- **pytest-playwright** + Chromium (`playwright install chromium`) — the e2e layer and user-guide screenshots; installed into the project's test group
- Linear MCP — for the `board` skill

## Questions at deployment (answers go into the registry, column "Contents/Deviations")

1. **Sandbox**: do we enable `sandbox` + `permissions.deny`? Default "yes"; "no" → remove the blocks.
2. **Pyramid profile**: unit-first or contract-first? Default **unit-first**; contract-first when the risk is at the seams with a live dependency (see CODING_STANDARDS §Test pyramid). The answer is written by the first `scripts/pyramid.py --write-baseline --profile <…>` and into the project's CODING_STANDARDS.
3. **User guide**: is there a user UI for people? Default "yes" for an SPA/screens; "no" (bot, library, own help packaging) → remove `docs/user-guide/` and `app/tests/unit/test_user_guide.py`, mark GATE step 3 in CLAUDE.md as "does not apply".
4. **Fence level** (`.claude/fences.env` → `FENCE_LEVEL`): `solo` / `standard` / `team`? Default **standard**. `solo` — one owner who wants only the destructive things fenced (force push, push to main, hooks bypass, release-tag pushes; `merge-feature.sh --accepted-by` stays); for `solo` also remove from `.claude/settings.json` the `Edit(…)` fence-file rules and `Bash(gh pr merge:*)` from `permissions.deny` and set `sandbox.allowUnsandboxedCommands` to `true`. `team` — several people: a GitHub approval before every merge, `--skip-ci` refused. Unattended sessions (`vps`): ask about `QUOTA_FAIL_CLOSED=1` in the same file. At every level recommend GitHub branch protection on the main branch — block force pushes, require a PR with 0 approvals (a solo owner satisfies it); `team`: 1 approval and no admin bypass. It is the backstop the guard cannot be (the factory's `deploy-project` skill asks these four questions as its questions 8–11 and holds the details).

## Contents and placeholders

| Artifact | Fill in |
|---|---|
| `CLAUDE.md` | Overview/stack, language, branch, project principles and prohibitions |
| `CODING_STANDARDS.md` | layers, prohibitions, "what we do not test", project language; in "Logging and LLM" — the rule on user text in logs, the prompts directory, the tracer |
| `DOCUMENTATION_STANDARDS.md` | the "Where we keep it" table, user-guide roles (§6), tone examples (§3) |
| `naming.yaml` | glossary and domain units; **mandatory** — GATE step 2 requires reading it before any code |
| `README.md` | **created at deployment** — CLAUDE.md onboarding starts with it: what it is and how to run it |
| `.claude/settings.json` | the dark-factory marketplace in `extraKnownMarketplaces` (`ruslantrachuk/dark-factory`; change it only if you publish your own fork); network allowlist of the `sandbox` block (stack and project domains; GitHub API domains for `gh` are already there), the project secrets directory in `denyRead` and `Read(…)` (e.g. `~/.config/<project>`) — enabling the sandbox is confirmed by an explicit question at deployment; with "no" the `sandbox` block and the `Read(…)` rules are removed, the fence rules stay. `permissions.deny` also holds the fences: no reading `gh`/Claude credentials, no `Edit` of the fence files, `git push --force`/`-f` and `gh pr merge` (defence in depth behind the guard). `allowUnsandboxedCommands: false` — a command cannot ask to leave the sandbox. The file is a fence file: after deployment the human edits it |
| `.claude/fences.env` | `FENCE_LEVEL` (question 4), `QUOTA_FAIL_CLOSED`. Read by the dark-factory plugin (guard, quota guard) and `merge-feature.sh`; its presence opts the project in to the plugin's guards; a fence file — the human changes it |
| the dark-factory plugin (not copied: installed, enabled in `.claude/settings.json`) | — the fence guard (`guard.py`, PreToolUse on `Bash\|Edit\|Write\|MultiEdit\|NotebookEdit`; reads the level from `.claude/fences.env`, the main branch from `scripts/merge-feature.sh`; human bypass `GUARD=off claude`; CLAUDE.md "Fences"), the subscription quota guard (`quota.py`; thresholds and bypass via env, fail-closed via `QUOTA_FAIL_CLOSED`; the plugin's [docs/quota-guard.md](../../plugins/dark-factory/docs/quota-guard.md)), `ensure-git-hooks.sh` (self-healing of `core.hooksPath` at session start). Mandatory |
| `.claude/hooks/env-context.sh` | capability block texts |
| `.claude/hooks/session-context.sh` | — (session header: branch and uncommitted files, the branch's PR with its description, tasks in progress with notes, the latest merges of the main branch; on the main branch the active OpenSpec changes) |
| `.claude/skills/feature-sanity-check/SKILL.md` | bd prefix, product direction document, project hot paths |
| `.claude/skills/investigate/SKILL.md` | the "Project sources" table (commands, keys, **measured** retention), project root-cause classes; verify with a live preflight run |
| `.claude/skills/code-audit/SKILL.md` | — (the method is generic; fan-out across many repositories — the `code-audit` module) |
| `.claude/skills/preview/SKILL.md` | **filled in from the first live run of the preview environment**: topology, commands to start, smoke-test and clean up; do not change the preview rules. A project without a preview deletes the skill |
| `.claude/skills/board/SKILL.md` | Linear workspace/team/project, the client's tracker. `disable-model-invocation: true` — the human invokes it (`/board`) |
| `.claude/skills/transcript-intake/SKILL.md` | — (needs no configuration) |
| `.claude/skills/openspec/*` | — (needs no configuration; cycle reference + artifact templates). The `docs/` folder is absent from the template — populate it at deployment: `scripts/fetch-openspec-docs.sh`, commit the snapshot |
| `.claude/skills/openspec-to-beads/*` | — (needs no configuration) |
| `.claude/skills/save/SKILL.md` | — (saving the state before `/clear`: the PR description, the task notes, memory) |
| `.claude/skills/ship/SKILL.md` | branch, merge strategy, exceptions, one/two repos. `disable-model-invocation: true` — the human invokes it (`/ship`) |
| `.claude/workflows/*` | not in base — the feature pipeline workflows ship in the dark-factory plugin (`dark-factory:feature-auto`); their project settings are the `templates/feature-pipeline/` module |
| `.githooks/pre-push` | TRIGGER/CODE_PATTERNS, the test command; `E2E_GATE=1` + `E2E_PATTERNS` — once a frontend appears. The main branch is taken from `merge-feature.sh` (`MAIN_BRANCH`). Bypass (`--no-verify`) is a human's only; the guard denies it to the agent |
| `.gitignore` | — (`.beads/*` except its README: the queue store stays on the machine); a project with its own `.gitignore` merges the lines |
| `.harness/base-sha` | **created at deployment**: SHA of the canon's `templates/` (`git -C <canon> rev-parse HEAD`); read by `scripts/harness-diff.sh` and `env-context.sh` |
| `.harness/modules.md` | — (catalog of canon modules; at deployment go through it and ask the owner about modules whose "time to install" sign is already present) |
| `.harness/pyramid-baseline.json` | created by the first `scripts/pyramid.py --write-baseline --profile <unit-first\|contract-first>` once tests exist; ratchet on the share of the profile's base layer |
| `app/tests/integration/test_merge_feature.py` | — (tests `merge-feature.sh` on a temporary repo with gh/bd stubs: the PR description sections and the merge commit body, closing the task after the merge, the task id from the branch name, `--accepted-by` (comment + trailer), team mode, `--skip-ci`, no CI) |
| `app/tests/{conftest.py, README.md, unit/test_layers.py, unit/test_user_guide.py, e2e/*}` | project fixtures in `conftest.py`, `FORBIDDEN_IN_UNIT` in the meta-test, `PREVIEW_COMMAND` and `<Project>` in e2e; the `app/` topology is the same as for pre-push. In `app/pyproject.toml`: `[tool.pytest.ini_options] addopts = ["-m", "not e2e"]`, otherwise e2e gets into the regular run; markers are registered by conftest |
| `docs/user-guide/{README.md, images/, screenshot-manifest.json}` | only with "user guide: yes" (question 3): index for the project's roles; the sample page is replaced by the first real one; screenshot scenes go into `tests/e2e/make_screenshots.py` |
| `.beads/README.md` | project name, the task id prefix |
| `openspec/README.md` | project name, layers in design.md |
| `openspec/CURRENT_TRAIN` | leave `1` |
| `.github/workflows/ci.yml` | stack steps in the `quick`/`full`/`browser` jobs, main branch name; `secret-scan` without configuration. Every stub step fails (`::error::` + `exit 1`) until replaced; the token is read-only (`permissions: contents: read`); actions are pinned to commit SHAs — pin new ones the same way |
| `docs/feature-development-workflow.md` | stack specifics of the phases (mockups, previews) |
| `docs/review-contract.md` | — |
| `scripts/*` | merge-feature.sh: MAIN_BRANCH, MERGE_FLAG (also read by the guard and pre-push), optionally REQUIRE_REVIEW and LOCAL_GATE_CMD (the gate of `--skip-ci`; empty = pre-push over the branch range). Usage: `merge-feature.sh <branch> [title] --accepted-by "<name>" [--skip-ci "<reason>"]`; the bd id is taken only from a branch ending in the full id (`…-<prefix>-<id>`); `harness-diff.sh`/`pyramid.py`/`check_doc_links.py` — no configuration (pyramid.py: the Vitest part is enabled by the presence of `app/frontend/package.json`) |

## Order

1. Copy the contents into the project root; `chmod +x` the scripts and hooks.
2. Fill in the placeholders (grep for `<`).
3. `./scripts/install-git-hooks.sh`; `bd init --non-interactive --skip-agents --skip-hooks --role maintainer -p <prefix>` in the main checkout (`.beads/README.md`).
4. Smoke: `claude plugin list` shows `dark-factory@dark-factory` enabled; a Claude session sees the contract echo + the env block (with "🛡️ fences: level …") and the line "📊 subscription quota: …"; the guard answers `deny` (ask the session to run `git push --force`, or feed it by hand: `echo '{"tool_name":"Bash","tool_input":{"command":"git push --force"},"cwd":"."}' | CLAUDE_PROJECT_DIR="$PWD" python3 <plugin dir>/scripts/guard.py`, the plugin dir as `claude plugin list` prints it); `bd ready` works; pre-push is checked **without a real push** — feed ranges to the hook on stdin:
   ```bash
   # docs-only range → exit 0 without tests; code range → the test gate
   printf 'refs/heads/main %s refs/heads/main %s\n' "$(git rev-parse HEAD)" "$(git rev-parse HEAD~10)" | .githooks/pre-push
   ```
   Separately: TEST_CMD must actually run **on every operator's machine** (a broken environment = a gate that is always red, "No module named pytest" etc.) — run the test command by hand at deployment.
5. `.harness/base-sha` is written by `scripts/deploy-base.sh` (full SHA of the canon `templates/` commit); after the first tests — `python scripts/pyramid.py --write-baseline --profile <answer to question 2>`.
6. A row in the factory's registry (`registry.example.md` layout): project, date, SHA of `templates/`, contents. Further reconciliation — `scripts/harness-diff.sh` during a review pass (result in the "Reconciliation" column).
