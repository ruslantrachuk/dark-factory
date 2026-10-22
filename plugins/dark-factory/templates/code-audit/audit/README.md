# Audit of <system> — method

> The `audit/` directory holds the factory's conclusions about the <system> code. Code clones live in `app/` (gitignored) and are
> not committed here. Only maps, ledgers, cards, reports and raw runs live here. The method is the `code-audit` skill.

## Main principle: everything is a hypothesis until proven

| Input | Default status |
|---|---|
| client's diagram/description ([hypothesis/baseline.md](hypothesis/baseline.md)) | hypothesis |
| repository READMEs and documentation | hypothesis |
| repository and service names, comments | hypothesis |
| audit agents' conclusions | accepted only with evidence and after spot-checking |

Tiers: **T1** — code · **T2** — deploy/CI · **RT** — runtime · **OWNER** — owner confirmation.
Statuses: ✅ `confirmed` · 🔧 `refined` · ❌ `refuted` · ❔ `not_found`.

## Sources

| Source | Status (active / secondary / dead) | Where | Note |
|---|---|---|---|
| `<…>` | | | |

The desired deploy state lives in: `<git / orchestrator stack / host — confirm with the owner>`.

## Artifacts

- `hypothesis/baseline.md` — client input verbatim (not edited)
- `hypothesis/verification-ledger.md` — the "hypothesis → fact" ledger
- `services/<unit>.md` — a card per unit
- `runs/<date>-<name>.json` — raw results of `scripts/audit-verify.wf.js` runs (with spot-checking)
- `report-<date>.md` — reports; a new one goes into a new file, the old one is marked historical
- `owner-qa-<date>.md` — questions to the owner and answers (question → answer → status → what it changes)

## Unit card stencil

Role (fact) · repositories and revisions · stack · storage and buses · external integrations · exposure · deploy ·
edges (outgoing and incoming, with evidence and tiers) · liveness · hypothesis check table ·
findings · secrets spotted (path and type, no value) · open questions.
