# The Operation layer — phase 10 of the map

> Phase 10 of [map.md](../map.md) ("accepted feature → enabled, observed, closed"). The layer is assembled from the practices
> [Observability](../practices/observability.md) and [Incident investigation](../practices/incidents.md); the input from the client is the practice
> [Client feedback](../practices/feedback.md).

## Job of the layer
A shipped feature works for people, not only on the stand: a failure is visible before a complaint, investigation relies on facts,
and every incident makes the next one cheaper.

| Input | Output (= transition artifact) |
|---|---|
| feature in production (layer 4) | metrics and alerts for it; release version in the startup log |
| alert, complaint, finding | investigation report → bug task (layer 1) |
| an investigated incident | a "rule + episode" entry in the project; a recurring one — a candidate for the canon |

## What the canon already has
- the code standard "Logging and LLM" (base) — from the first line, otherwise there is nothing to investigate with;
- the `investigate` skill (base); the `observability` module (metrics, alerts, log-based investigation);
- the `prod-monitor` module: a model-free cron watchdog wakes a read-only agent only on a real anomaly; its verdict arrives in the On-call session (`feedback-desk`) as a channel event and goes to the client group and the development session, which investigates;
- a regular production review ("every morning review production") is booked by a session itself as a scheduled task;
- the `release-tag` module — version and rollback by tag when production is built from a branch;
- still without support from map.md: a feature flag and counter-metrics after 2–3 days do not exist as a procedure yet.

