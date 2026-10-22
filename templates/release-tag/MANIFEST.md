# release-tag — module manifest

> **Prod deploys only from a tag, not from a merge into main.** For projects whose hosting builds prod from a
> branch (hostings where every push to the tracked branch rebuilds prod).
> Installed **on top of base**.
>
> **Status: experimental.** The parameterisation is not yet checked on a second project and a second hosting.

> **Seam:** code host = GitHub Releases and Actions; hosting = one that builds production from the `release` branch. To use another tool, rewrite `scripts/release.sh`, `.github/workflows/release.yml` and the hosting step of Setup.

## Why

The base rule "accompanying changes (devlog, beads queue, ROADMAP/SHIPPED) ride in the feature branch, not as a
tail commit in main" works around a symptom: the hosting rebuilds prod on every push to main. The module removes
the cause: the hosting watches the `release` branch, and only a verified release moves it. A merge into main does
not go to prod; heavy tests run once — on the tag, not on every PR.

## Contents

| Artifact | What it does |
|---|---|
| `scripts/release.sh` | no arguments — tag `vYYYY.MM.DD.N` on `origin/<main>`; `--publish <tag>` — `release` = tag + a `VERSION` commit, GitHub Release with auto-generated notes; `--manual` — emergency release without Actions (`manual` mark in `VERSION` and in the notes) |
| `.github/workflows/release.yml` | on a `v*` tag: base release gate (`ci.yml` — tiers `full` + `browser`), green → `release.sh --publish` |
| `app/tests/integration/test_release_script.py` | 16 tests of the script against a temporary bare repo, `gh` is a stub |
| `VERSION` | `dev` on the main branch; the release tag is written only by `--publish` on the `release` branch |

## Properties (do not change without a reason)

- **`release` grows forward, push without `--force`.** A release commit is a descendant of the previous release (first parent) and of the tag (second parent); its content is exactly the tag + `VERSION`. Some hostings do not build the branch as is but merge it into their own master: recreating `release` from scratch caused a conflict on `VERSION` at the second release.
- **Fetch tags with `--force`.** `actions/checkout` on a tag creates a local lightweight tag, and `git fetch --tags` without `--force` refuses to replace it with the annotated one — the publish step then fails with exit code 1 and no message.
- **Failure is not silent:** `trap ERR` prints the line and the command.
- **Retry is safe:** a repeated `--publish` of the same tag is a no-op (detected via `VERSION`) and adds a missing GitHub Release. A GitHub Release failure is a warning, not a failure: `release` has already been pushed by then.
- **Version comes from the file, not from git:** `.git` does not get into the image, so a git-derived version in the container is always `unknown`.
- **Tests get an isolated git environment:** the pre-push hook runs pytest with `GIT_DIR`/`GIT_INDEX_FILE` of the real repo; inherited, they redirect the test into the real `.git/config`.

## Setup

1. Copy the contents on top of base. Fill in `release.sh`: `MAIN_BRANCH`, `RELEASE_TZ` (timezone of the tag date, default `UTC`); in `release.yml` — the bot name.
2. **base `ci.yml`:** add a `workflow_call:` line to `on:` — without it `release.yml` cannot call the gate.
3. **Image:** take the version from the file (`COPY VERSION ./VERSION` in the Dockerfile instead of `git rev-parse`), print it in the startup log.
4. **Hosting:** switch the prod build to the `release` branch (in `<your hosting>` — its GitHub/branch binding settings). First release — `scripts/release.sh`; check that `release.yml` is green and the version appears in the startup log.
5. Project deploy document: who cuts a release (any participant), the emergency path (`--manual`), where to see the version.
6. A line about the module goes into your factory's registry (see `registry.example.md`, column "Composition & deviations").

**A base rule the module weakens but does not cancel:** "accompanying changes ride in the feature branch"
stays — an extra commit in main no longer rebuilds prod, but it clutters history and bypasses review.

## Design notes

- Separate unit / heavy workflows are not part of the module — in base these are the `quick`/`full` tiers in one `ci.yml`. A nightly run of the heavy tier is a `schedule:` in `ci.yml`, at the project's discretion.
- The hosting-specific deploy document is per project.
- Main branch and timezone are parameters (overridable from the environment for tests).

## Abandon criterion

The module is removed from a project if, within a month, a release went around `release.sh` at least once (a
direct push to `release`, a manual rebuild from main) or the emergency `--manual` became the main path — that
means the tag gate hinders more than it protects.
