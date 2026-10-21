# observability — module manifest

> **Observability of a running system**: business metrics, dashboard as code, an alert catalog, investigation via logs.
> Installed **on top of base** once the project has a prod. The in-code minimum (structured logs,
> `correlation_id`, `llm.usage`, version in the startup log) is **not a module but a base standard** (CODING_STANDARDS,
> "Logging and LLM — mandatory minimum"): it is needed from the first line. Practice — `docs/practices/observability.md`.
>
> **Tier B: a single source.** The contents are contract documents; metric code is written in the project's stack.

## Contents

| Artifact | What it does |
|---|---|
| `docs/deploy/monitoring.md` | the `/metrics/business` contract (loopback, always 200, self-diagnostics, explicit windows), metrics table, "question → log filter" table, log retention period (measured) |
| `docs/deploy/monitoring-alerts.md` | a catalog of nine alerts by meaning + rules: "silence is a signal", one push on an outage, flapping, windows, "no data" |

## Setup

1. The `/metrics/business` endpoint in the project's stack per the contract; test: 404 from outside, with the DB unavailable — 200 and `*_db_ok=0`.
2. The hosting/cloud metrics and logs collection agent (typically: a metrics pull from the endpoint + JSON parsing for logs).
3. Dashboard as code (Terraform / the cloud provider), if the provider supports it; alerts — per the catalog, by hand or as code.
4. **Measure the log retention period** and record it in `monitoring.md` and in the sources of the `investigate` skill.
5. Fill in the "question → filter" table with commands of your log storage.

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
