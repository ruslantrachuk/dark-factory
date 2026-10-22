# .harness/ — binding the project to the harness canon

Service files by which the project is reconciled with the canon `dark-factory/templates/base`,
learns about the canon's modules and keeps the shape of the test pyramid. All files are **versioned** (committed to git):
without them reconciliation and the ratchet do not work on another machine or in CI.

| File | What it is | Who writes it |
|---|---|---|
| `base-sha` | SHA of the dark-factory canon's `templates/` commit the project was deployed from or last synced with. One line. | `deploy-project` at deployment; by hand — after a manual sync with the canon |
| `modules.md` | Catalog of canon modules: what each gives, when it is time to install it, how to install it. A canon file, the project does not edit it; updated together with the base sync. | dark-factory canon |
| `pyramid-baseline.json` | The project's pyramid profile (`profile`: unit-first / contract-first), the base layer (`layer`) and its share in `<main>` (`share`) — the ratchet's reference point. | `scripts/pyramid.py --write-baseline --profile …` at deployment and on merge into `<main>` |

## Who reads them

- `scripts/harness-diff.sh` — takes `base-sha` as the common base and shows for each
  canon file: identical / project moved ahead / canon moved ahead / both diverged.
- `.claude/hooks/env-context.sh` — prints `base-sha` at the start of the session.
- `.githooks/pre-push` and CI (`quick`) — `scripts/pyramid.py --ratchet` compares the current
  share of the profile's base layer with `pyramid-baseline.json` and blocks the push/PR if the share dropped.
  No baseline — a warning, not a block.

## Rules

- Update `base-sha` only together with an actual sync of the canon files —
  otherwise reconciliation shows "identical" where the project has fallen behind.
- Do not edit `pyramid-baseline.json` by hand: raise the bar with `--write-baseline`
  after a merge; lowering it or changing the profile is a conscious decision recorded in the PR description (`## Decisions`).
