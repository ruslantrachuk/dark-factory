# Factory project registry (SSOT)

> Copy this file to `registry.md` in your own private factory repository and keep it there; this public file is
> only the template.
>
> **The single registry of projects**: which board project belongs to whom, what was deployed from the template,
> when it was last reconciled. Consumers (the `board` skill and others) refer here and keep no copies of the table.
> **Single writer**: a human (or an agent on an explicit command) writes it; transitions are rare — deployment, review
> pass, client onboarding. Once it gets crowded (2+ writers, frequent transitions) — move it to a structured store
> and keep the markdown as a view.
>
> **Template improvements are rolled out by hand: reconciliation with `templates/` is a mandatory review-pass item**,
> its result goes into the "Reconciliation" column. In "From template" record the commit SHA of `templates/` (the lag
> = `git log templates/` since that SHA). Build an auto-diff once a threshold is reached: 3+ projects from the
> template in the registry OR 2 skipped reconciliations in a row.

| Project | Tracker id | Repository | Client | External tracker | From template (SHA/date) | Composition & deviations | Reconciliation |
|---|---|---|---|---|---|---|---|
| _Example (delete this row):_ Photo-booth control panel | `proj-a1b` | `~/photobooth-panel` (github.com/<owner>/photobooth-panel) | Example Client Ltd | — | `abc1234` (2026-01-15) | base in full, code in `app/`; modules: release-tag. **Deviations:** no user guide yet (no UI); sandbox: yes | 2026-01-15 |

Donor projects that were not deployed from the template are listed with "—" in the template columns; fill them
in if/when their artifacts are moved onto the template.
