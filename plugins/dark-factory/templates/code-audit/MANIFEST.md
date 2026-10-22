# code-audit — module manifest

> **Fan-out code audit across many repositories** with evidence and spot-checking of that evidence. For
> audit projects (someone else's system, due diligence, presales) and for a full review of your own system.
> Installed **on top of base**; the method is the `code-audit` skill in base (mode 2), the practice is `docs/practices/code-analysis.md`.
>
> **Status: experimental.** The fan-out is sized for one audit shape (about 25 agents over about 30 repositories in
> three passes); larger or smaller audits are not yet proven.

> **Seam:** code host = a GitLab group (GitHub through the `gh` one-liner in the script's header). To use another host, rewrite `scripts/clone-group.sh`.

## Contents

| Artifact | What it does |
|---|---|
| `scripts/audit-verify.wf.js` | Workflow: an agent per unit (Verify) → a separate agent checks evidence addresses (SpotCheck: all `refuted` + a share of `confirmed`). Units, hypotheses, revisions, domain — as arguments |
| `scripts/clone-group.sh` | clones all repositories of a GitLab group into `app/`; the token goes only in a header, never into the remote; for GitHub — a `gh` one-liner in the header comment |
| `audit/README.md` | the method: everything is a hypothesis, tiers, statuses, sources, artifacts, unit card stencil |
| `audit/hypothesis/{baseline,verification-ledger}.md` | client input verbatim; the "hypothesis → fact" ledger |
| `audit/{services,runs}/` | unit cards; raw run results |

## Design notes

- **Spot-checking evidence** is a separate phase: `file:line` addresses produced by agents must be re-checked, because agent conclusions are sometimes false (manual review regularly overturns a large share of agent reclassifications).
- **Raw results are saved** (`audit/runs/`): otherwise a pass is not reproducible and a repeated audit has nothing to compare against.
- **A revision in every conclusion and reading without checkout** (`git show <ref>:path`): "read what is deployed, not HEAD"; meaningful code is sometimes not on the default branch.
- **A schema without source-system specifics** (reverse proxy → `exposure`, message bus → `messaging`), with tiers on edges and deploy, `liveness`, findings in the `docs/review-contract.md` format, secrets as "path and type, no value".
- **The model by full id** for every agent.

## Setup by /dark-factory:add code-audit

**Only the owner can (one list, up front):** create a private repository for the audit HQ (the maps contain open
vulnerabilities) and put the code-access token in `.claude/secrets.env` (gitignored) themselves; the agent never prints
it. Provide the client's input verbatim.

**The agent:**

1. Copies `audit/` and `scripts/` (`<plugin root>/scripts/add-module.sh code-audit`); adds `app/` and `.claude/secrets.env` to `.gitignore`.
2. Fills in `audit/README.md` (the system, the sources, where the desired deploy state lives) and puts the client input
   into `audit/hypothesis/baseline.md`.
3. Clones the group's repositories with `scripts/clone-group.sh` once the owner has put the token in place.
4. Status check: one unit as a trial run per the `code-audit` skill, mode 2, before the first big run.

## Abandon criterion

If spot-checking rejects more than a quarter of the checked evidence two runs in a row — the fan-out with this
prompt and model is not fit as a source of facts: narrow the units, change the model, or switch to manual review.
