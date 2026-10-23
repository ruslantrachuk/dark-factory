# .harness/ — binding the project to the harness canon

Service files by which the project is reconciled with the canon, the dark-factory plugin's `templates/base`,
learns about the canon's modules and keeps the shape of the test pyramid. All files are **versioned** (committed to git):
without them reconciliation and the ratchet do not work on another machine or in CI.

| File | What it is | Who writes it |
|---|---|---|
| `base-sha` | The canon ref the project was deployed from or last synced with: the plugin's release tag (`v<N>`, e.g. `v1`), or a commit SHA when deployed from a canon checkout. One line. | `/dark-factory:add base` at deployment; `copier update` rewrites it; by hand — after a manual sync with the canon |
| `../.copier-answers.yml` (at the project root) | The same ref and the template's address, for `copier update`. | `/dark-factory:add base` at deployment; `copier update` |
| `modules.md` | Catalog of canon modules: what each gives, when it is time to install it, how to install it. A canon file, the project does not edit it; updated together with the base sync. | dark-factory canon |
| `pyramid-baseline.json` | The project's pyramid profile (`profile`: unit-first / contract-first), the base layer (`layer`) and its share in `<main>` (`share`) — the ratchet's reference point. | `scripts/pyramid.py --write-baseline --profile …` at deployment and on merge into `<main>` |

## Who reads them

- `copier update` — reads `.copier-answers.yml` and updates the canon files (below).
- `scripts/harness-diff.sh` — takes `base-sha` as the common base and shows for each
  canon file: identical / project moved ahead / canon moved ahead / both diverged. A report, it applies nothing.
- `.claude/hooks/env-context.sh` — prints `base-sha` at the start of the session.
- `.githooks/pre-push` and CI (`quick`) — `scripts/pyramid.py --ratchet` compares the current
  share of the profile's base layer with `pyramid-baseline.json` and blocks the push/PR if the share dropped.
  No baseline — a warning, not a block.

## Updating to a new canon version

`/dark-factory:upgrade` does all of this, and the steps from each release's "How to upgrade" notes. By hand, on a
work branch, with a clean working tree:

```bash
uvx copier update --defaults --conflict inline --vcs-ref v<N>
git grep -nE '^(<<<<<<<|>>>>>>>) (before|after) updating'
```

Copier takes the canon file at the project's version, the canon file at `v<N>` and the project's file, and merges
them: a change of the canon in a place the project did not touch is applied; a change where the project has its own
text (a filled Configuration section, a translated document) is left in the file between `<<<<<<< before updating`
(the project's text) and `>>>>>>> after updating` (the canon's). Resolve each one: keep the project's configuration,
take the canon's procedure text, and carry the meaning of the canon's change into text the project rewrote. No marker
may remain in the commit. Files the project owns after setup (`CLAUDE.md`, `naming.yaml`, `docs/user-guide/`,
`app/tests/`) are never touched. Another canon file the project deleted comes back only if the canon changed it —
delete it again in the same branch. A file the project moved gets no update — check it by hand against the release notes. A
conflict on `.harness/base-sha` (a project set up from a canon checkout records a commit) resolves to `v<N>`. Then run
the project's checks and merge as usual. The plugin pin (`"ref"` in `.claude/settings.json`) comes with the update; if
it conflicts, resolve it to `v<N>`.

Without `uvx`: `pipx run copier …` or `pip install copier`. A project without `.copier-answers.yml` (set up before
Copier was adopted) syncs once with `scripts/harness-diff.sh`, then adds the file with `_commit: v<N>` and
`_src_path: gh:ruslantrachuk/dark-factory`.

## Rules

- Update `base-sha` only together with an actual sync of the canon files —
  otherwise reconciliation shows "identical" where the project has fallen behind.
- Do not edit `pyramid-baseline.json` by hand: raise the bar with `--write-baseline`
  after a merge; lowering it or changing the profile is a conscious decision recorded in the PR description (`## Decisions`).
