---
name: feature
description: Launch the feature pipeline for one task with the project's saved settings — reads .claude/feature-pipeline.json, fills in the run's own arguments (branch type and slug, tracker ID, bd task, requirements source, stamp) and calls the Workflow dark-factory:feature-auto (or dark-factory:feature-lite with --lite). Stops at a committed branch; never merges. Invoked by the human as /dark-factory:feature.
argument-hint: "[--lite] [--mode session|pipeline] <task: bd id, OpenSpec change + phase, spec path or a sentence>"
disable-model-invocation: true
---

# /dark-factory:feature — one task through the feature pipeline

The workflows ship with this plugin (`dark-factory:feature-auto`, `dark-factory:feature-core`,
`dark-factory:feature-lite`); the project keeps its settings in `.claude/feature-pipeline.json` (the
`feature-pipeline` module). This command joins the two so the settings are never re-typed. The run rules and the
argument table are in the module's `MANIFEST.md` and the plugin's `workflows/README.md`.

## Rules

1. **The file is the project's settings; the task is the run.** Pass every key of `.claude/feature-pipeline.json`
   as it is (`appSubdir`, `testCmd`, `lintCmd`, `frontendDir`, `i18nFile`, `invariantsDoc`, `surfaces`, `models`,
   `maxAgents`, …). Do not invent values for keys the file leaves out — the workflows have defaults. A key whose value
   still holds a `<placeholder>` is left out, and you tell the human it is unfilled.
2. **Never guess the run's required arguments.** `bdId` comes from the task or the human, `slug` and `trackerId` from the
   change (`openspec/changes/<slug>/`, its proposal header), the source from the task. Missing and not derivable — ask one short question.
3. **`args` is an object** of JSON values, never a JSON-encoded string.
4. **The run stops at a committed branch.** Merging is `scripts/merge-feature.sh <branch>` once CI is green, outside
   this command.

## Steps

1. Read `.claude/feature-pipeline.json`. No file → tell the human the `feature-pipeline` module is not set up
   (its `MANIFEST.md` §Setup) and stop.
2. Build the run's arguments from `$ARGUMENTS` and the repository:
   - `request` — the task in one or two sentences (the bd task's title when only an id is given: `bd show <id>`).
   - `bdId` — the full bd id `<prefix>-<hash>[.N]`; required by `feature-auto`.
   - the source: `changeDir` + `phase` (an approved OpenSpec change and its `tasks.md` phase), or `specPath`
     (absolute path of a ready spec), or neither (the bd task's description is the source).
   - `slug` — the change slug (`openspec/changes/<slug>/`; a phase of a spec without sub-cards: `<slug>-p<K>`);
     `trackerId` — the tracker ID of the change when there is one (it goes into the branch name); `type` —
     `feat|fix|ui|refactor|chore|docs`.
   - `stamp` — a unique suffix the scripts cannot make themselves: `date +%Y%m%d-%H%M` plus a short tag
     (e.g. `20261021-1430-p3`). Keep it for a resume.
3. Show the human the call in short — workflow name, the run's arguments, the settings taken from the file — and
   launch after their "yes":
   ```
   Workflow({ name: "dark-factory:feature-auto", args: { ...settings from the file, request, stamp, slug, trackerId, bdId, ... } })
   ```
   `--lite` in `$ARGUMENTS` → `dark-factory:feature-lite` with the same settings (`bdId` optional there).
   `--mode session|pipeline` sets `buildMode` for this run over the file's value (how `feature-core` builds the
   subtasks; `feature-lite` has a single builder either way).
4. Read the result's `error`, not the harness status. `null` — show the branch, the assumptions and the PR description (`prBody`; the branch's PR gets it: `gh pr create --draft --body-file -`)
   and ask for the owner's acceptance. Anything else — show the error, the `stage` it stopped at and `agentsUsed` /
   `maxAgents`; a stop on `budget exhausted` or `agent limit reached` is resumed with `resumeFromRunId`, the same
   args and the same `stamp` (with a larger `maxAgents` for the second one, after the human agrees).
