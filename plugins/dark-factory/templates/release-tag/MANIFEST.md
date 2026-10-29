# release-tag — module manifest

> **Prod deploys only from a tag, not from a merge into main.** For projects whose hosting builds prod from a
> branch (hostings where every push to the tracked branch rebuilds prod).
> Installed with **base** when the project has production (`/dark-factory:add base` asks), or later by
> `/dark-factory:add release`.
>
> **Status: experimental.** The parameterisation is not yet checked on a second project and a second hosting.

> **Seam:** code host = GitHub Releases and Actions; hosting = one that builds production from the `release` branch. To use another tool, rewrite `scripts/release.sh`, `.github/workflows/release.yml` and the hosting step of the setup.

## Why

The base rule "accompanying changes (SHIPPED, an ADR) ride in the feature branch, not as a
tail commit in main" works around a symptom: the hosting rebuilds prod on every push to main. The module removes
the cause: the hosting watches the `release` branch, and only a verified release moves it. A merge into main does
not go to prod; heavy tests run once — on the tag, not on every PR.

## Contents

| Artifact | What it does |
|---|---|
| `scripts/release.sh` | no arguments — tag `vYYYY.MM.DD.N` on `origin/<main>` **only if every merge since the last `v*` tag is accepted** (the PR carries the label `accepted`; otherwise it refuses and names each unaccepted feature with its title); `--owner-accepts` — the owner accepts everything listed (labels each PR, then tags); `--include-unaccepted "<who allowed>"` — ships without the mark, the name goes into the annotated tag and the release notes; `--list-unaccepted` — only lists them; `--publish <tag>` — `release` = tag + a `VERSION` commit, GitHub Release with auto-generated notes; `--manual --reason "<why>" --by "<human name>"` — emergency release without Actions (`manual` mark in `VERSION`, reason and name in the annotated tag and the notes), refused at `FENCE_LEVEL=team` |
| `.github/workflows/release.yml` | on a `v*` tag: base release gate (`ci.yml` — tiers `full` + `browser`), green → `release.sh --publish` in the `production` environment; read-only token except the publish job, actions pinned to a commit SHA |
| `app/tests/integration/test_release_script.py` | Tests of the script against a temporary bare repo, `gh` is a stub |
| `VERSION` | `dev` on the main branch; the release tag is written only by `--publish` on the `release` branch |

## Acceptance (the check in the normal release)

A release takes all of main, so it first lists every first-parent commit since the last `v*` tag (`git log
<tag>..origin/<main> --first-parent`, a merge, a squash and a rebase alike; before the first release, since the root),
takes the PR number from the subject (`(#N)` or `Merge pull request #N`) and reads each PR once (`gh pr view N --json
labels`, through `RELEASE_GH`). A PR without the label
`accepted` stops the release; the message lists it with its title, so whoever releases can ask again. A commit without a PR number (a direct push, a
rebase merge) is not a PR: it is listed and needs an override. Overrides, both recorded: `--owner-accepts` (labels each PR `accepted`, comments
"accepted by the owner, permission dialog", then tags) and `--include-unaccepted "<who allowed>"` (comments on each PR;
the annotated tag and, through `--publish`, the GitHub Release notes carry "Shipped without acceptance, allowed by …").
`--manual` (emergency) and `--publish` (CI, after the tag) do not check. If `gh` cannot read a PR the release stops:
an unverifiable merge is not an accepted one. The guard asks before any of these runs (`docs/layers/acceptance.md`).

## Properties (do not change without a reason)

- **`release` grows forward, push without `--force`.** A release commit is a descendant of the previous release (first parent) and of the tag (second parent); its content is exactly the tag + `VERSION`. Some hostings do not build the branch as is but merge it into their own master: recreating `release` from scratch caused a conflict on `VERSION` at the second release.
- **Fetch tags with `--force`.** `actions/checkout` on a tag creates a local lightweight tag, and `git fetch --tags` without `--force` refuses to replace it with the annotated one — the publish step then fails with exit code 1 and no message.
- **Failure is not silent:** `trap ERR` prints the line and the command.
- **Retry is safe:** a repeated `--publish` of the same tag is a no-op (detected via `VERSION`) and adds a missing GitHub Release. A GitHub Release failure is a warning, not a failure: `release` has already been pushed by then.
- **Version comes from the file, not from git:** `.git` does not get into the image, so a git-derived version in the container is always `unknown`.
- **Tests get an isolated git environment:** the pre-push hook runs pytest with `GIT_DIR`/`GIT_INDEX_FILE` of the real repo; inherited, they redirect the test into the real `.git/config`.

## Setup by /dark-factory:add release

Part of `/dark-factory:add base` when the owner says the project has production; `/dark-factory:add release` later
otherwise. Project releases are tagged `vYYYY.MM.DD.N`.

**Only the owner can (one list, up front):**

1. **Hosting:** switch the production build from the main branch to the `release` branch (the hosting's GitHub/branch
   binding settings). Do it just before the first release, not earlier.
2. **GitHub, as a repository admin** (the guard denies rulesets and environments to the agent; the agent prints the
   commands, `add base`'s question 11 holds the ruleset JSON): a tag ruleset on `v*` (create for admins only; no update,
   deletion or force) and the `production` environment with required reviewers, so a person approves each publish.
   Without the ruleset anyone with write access cuts a production release; without reviewers a green gate deploys
   unattended.

**The agent:**

1. Copies the files (`<plugin root>/scripts/add-module.sh release`): `scripts/release.sh`, `.github/workflows/release.yml`, `VERSION`,
   `app/tests/integration/test_release_script.py`; fills `MAIN_BRANCH` (from the project), `RELEASE_TZ` (asks, default
   `UTC`), the bot name and environment name in `release.yml`.
2. Adds `workflow_call:` to the `on:` of base's `ci.yml` (without it `release.yml` cannot call the gate).
3. Makes the image take its version from the file (`COPY VERSION ./VERSION` instead of `git rev-parse`) and print it in
   the startup log.
4. Writes who cuts a release and who marks features accepted (the label `accepted`, created on first use), the emergency path (`--manual --reason --by`, refused at `team`) and where the version
   shows into the project's deploy document.
5. Runs `python -m pytest app/tests/integration/test_release_script.py`.
6. Status check, after the owner's two steps: `scripts/release.sh` (the first tag), `release.yml` green, the version in
   the startup log. Nothing here needs a server unit.

## Design notes

- Separate unit / heavy workflows are not part of the module — in base these are the `quick`/`full` tiers in one `ci.yml`. A nightly run of the heavy tier is a `schedule:` in `ci.yml`, at the project's discretion.
- The hosting-specific deploy document is per project.
- Main branch and timezone are parameters (overridable from the environment for tests).

## Abandon criterion

The module is removed from a project if, within a month, a release went around `release.sh` at least once (a
direct push to `release`, a manual rebuild from main) or the emergency `--manual` became the main path — that
means the tag gate hinders more than it protects.
