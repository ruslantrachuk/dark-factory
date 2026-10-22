# observability — module manifest

> **Observability of a running system**: business metrics, dashboard as code, an alert catalog, investigation via logs.
> Installed **on top of base** once the project has a prod. The in-code minimum (structured logs,
> `correlation_id`, `llm.usage`, version in the startup log) is **not a module but a base standard** (CODING_STANDARDS,
> "Logging and LLM — mandatory minimum"): it is needed from the first line. Practice — `docs/practices/observability.md`.
>
> **Status: experimental.** The contents are contract documents; metric code is written in the project's stack, and the
> contracts are not yet checked against a second stack.

> **Seam:** hosting metrics and logs = your hosting's collection agent and CLI. To use another hosting, rewrite "Managed cloud variant" and the "question → log filter" table in `docs/deploy/monitoring.md`.

## Contents

| Artifact | What it does |
|---|---|
| `docs/deploy/monitoring.md` | the `/metrics/business` contract (loopback, always 200, self-diagnostics, explicit windows), metrics table, "question → log filter" table, log retention period (measured) |
| `docs/deploy/monitoring-alerts.md` | a catalog of nine alerts by meaning + rules: "silence is a signal", one push on an outage, flapping, windows, "no data" |

## Setup by /dark-factory:add observability

**Only the owner can (one list, up front):** log in to the hosting/cloud account where metrics and logs are collected
(the collection agent, the dashboard, console-only alerts and mutes), and say which alerts should reach whom.

**The agent:**

1. Copies `docs/deploy/monitoring.md` and `monitoring-alerts.md` (`add-module.sh observability`).
2. Writes the `/metrics/business` endpoint in the project's stack per the contract (loopback only, always 200, a
   `*_db_ok` self-check) with a test: 404 from outside, 200 with `*_db_ok=0` when the database is down.
3. Fills in the metrics table with the project prefix and measured thresholds, and the "question → filter" table with
   commands of the project's log storage; **measures the log retention** with the hosting CLI and records it in
   `monitoring.md` and in the sources of the `investigate` skill.
4. Drafts the dashboard as code (Terraform / the provider's format) and the alert list from the catalog for the owner to
   review; applying them to the cloud account is the owner's step.
5. Status check: the endpoint test passes and, after the owner connects the collection agent, the dashboard shows data.

## Managed cloud variant

A typical managed-cloud setup: the provider's collection agent pulls `/metrics/business` every 60 s and parses
JSON logs into structured fields; logs are read with the provider's CLI filtering on `correlation_id` (if large
`--since` windows sometimes silently return nothing — widen in steps, starting from 8h); the dashboard is a
Terraform resource of the provider; if alerts and mutes can only be set in the console, the catalog is the source
of truth and the console is reconciled against it.

## Abandon criterion

An alert that fired falsely more often than for a reason within a month — rework or remove it; the whole module — if
incidents within a month were found not by alerts but by user complaints.

## Design notes

- Metric names carry the project prefix; thresholds are placeholders set from measurements.
