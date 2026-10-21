# <Project> monitoring

> Factory module observability. The in-code minimum (structured logs, `correlation_id`, `llm.usage`) — per
> CODING_STANDARDS, "Logging and LLM — mandatory minimum"; here — what is collected from the running system and where to look at it.
> This file is the source of truth: whatever is set up in the monitoring console matches it.

## How it works

```
app ──► counters (Redis/memory): logins, connections, ERRORs per process
business slices from the DB ──► GET /metrics/business (loopback only, always 200)
                          │ the hosting/cloud agent pulls every <60 s>
                          ▼
            <monitoring system>: dashboard (as code) + alerts (catalog — monitoring-alerts.md)
logs (JSON) ──► <log storage>, retention <measured: N days>
```

## The `/metrics/business` contract

- Format `<Prometheus text / other>`; **available only from loopback** (404 from outside) — business numbers are not public.
- **Always 200**: an unavailable source does not bring the endpoint down; instead self-diagnostic gauges `<proj>_business_db_ok`, `<proj>_business_counters_ok` = 0/1 — to tell "zero" from "could not read".
- Windows are explicit: `*_30m` are sliding, `*_today` is the calendar day in `<timezone, default UTC>`.
- Counters (`*_total`) start at deploy — record in the metric description what was before.

| Metric | Type | What |
|---|---|---|
| `<proj>_business_db_ok` | gauge | DB slices were read |
| `<proj>_requests_failed_30m` | gauge | failed user requests over 30 min |
| `<proj>_request_latency_ms_30m{quantile}` | gauge | latency (no requests — no metric) |
| `<proj>_stuck` | gauge | stuck operations |
| `<proj>_delivery_failed_30m` | gauge | undelivered outgoing messages |
| `<proj>_llm_tokens_today{direction}` | gauge | LLM tokens for the day (from `llm.usage`) |
| `<proj>_log_errors_total{process}` | counter | ERROR records per process |
| `<domain metrics>` | | |

## Investigating people and requests — logs

| Question | Filter |
|---|---|
| the full trace of one request | `correlation_id = "<id>"` |
| what a user did | `user_id = "<id>"` |
| all errors | `level >= ERROR` |
| an event of a given type | `event = "<domain.action>"` |
| the release version at a point in time | `event = "app.started"` (or the startup log) |

Read command: `<cloud CLI / docker logs / files>`. Retention — **measure and record it**, do not take it from the cloud documentation.

## Release version

The startup log prints the version and commit; see the release-tag module if prod deploys from a tag.
