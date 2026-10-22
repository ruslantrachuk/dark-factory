# The Operation layer

> **Stages:** Monitoring, and the production side of Support and feedback (phase 10 of [map.md](../map.md):
> "accepted feature → enabled, observed, closed").
>
> The layer is built from two practices, [Observability](../practices/observability.md) and
> [Incident investigation](../practices/incidents.md); its input from the client comes through the practice
> [Client feedback](../practices/feedback.md).

## Job of the layer
A shipped feature works for real users, not only in the preview environment: a failure is visible before anyone
complains, an investigation relies on facts, and every incident makes the next one cheaper.

| Input | Output (the transition artifact) |
|---|---|
| a feature in production (layer 4) | metrics and alerts for it; the release version in the startup log |
| an alert, a complaint, a finding | an investigation report → a bug task (layer 1) |
| an investigated incident | a "rule + episode" entry in the project; a recurring one becomes a candidate for the canon |

## What the canon already has
- the "Logging and LLM" code standard (base), from the first line of code, because without it there is nothing to
  investigate with;
- the `investigate` skill (base); the `observability` module (metrics, alerts, log-based investigation);
- the `prod-monitor` module: a cron watchdog without a model wakes a read-only agent only on a real anomaly; its
  verdict reaches the On-call session (`feedback-desk`) as a channel event and goes on to the client group and to the
  development session, which investigates;
- a regular production review ("review production every morning"), which a session books itself as a scheduled
  task;
- the `release-tag` module: a version and rollback by tag when production is built from a branch;
- not yet supported, although map.md calls for them: a feature flag and counter-metrics after 2–3 days do not exist
  as a procedure yet.
