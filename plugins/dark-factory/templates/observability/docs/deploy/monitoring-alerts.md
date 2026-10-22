# <project> alerts

> Factory module observability. The catalog is the source of truth: if alerts are created in the console by hand
> (many clouds have no API/Terraform for alerts), the console is reconciled against this table. Notification channel: `<…>`.

## Catalog (by meaning; thresholds — from measured project traffic)

| # | Name | Metric | Window / aggregation | Warning | Alarm | No data |
|---|---|---|---|---|---|---|
| 1 | Failing en masse | `*_requests_failed_30m` | 5 min, last | `>= <…>` | `>= <…>` | OK |
| 2 | Operations stuck | `*_stuck` | 5 min, minimum | `>= 1` | `>= <…>` | OK |
| 3 | Slow | `*_latency_ms_30m{p95}` | 10 min, minimum | `> <…>` | `> <…>` | OK (no requests — no metric) |
| 4 | Outgoing not delivered | `*_delivery_failed_30m` | 5 min, last | — | `>= <…>` | OK |
| 5 | DB unavailable | DB health | 5 min, maximum | — | `< 1` | do not send |
| 6 | External API unavailable | external API health | 5 min, maximum | — | `< 1` | do not send |
| 7 | **Monitoring went blind** | health/ready | 5 min, last | — | `< 1` | **Alarm** |
| 8 | Metrics incomplete | `*_business_db_ok`, `*_counters_ok` | 5 min, maximum | `< 1` | — | Alarm |
| 9 | Error spike | increase of `*_log_errors_total` | 15 min, sum | `> <…>` | — | OK |

## Rules (learned the hard way)

- **Silence is a signal too.** Alert 7 fires when there is no data: scheduled reports can silently stop arriving, and that is noticed only by their absence.
- **One push on an outage.** When the app is down, nobody has metrics — without protection all alerts fire at once. Dependent ones (1–4, 8, 9) are muted until 7 is OK; 5 and 6 are not muted but do not send on "no data" — they fire only on value 0 (the app is alive, the dependency is not).
- **Flap suppression** on 7: after a status change wait <5 min> and send the outcome — a one-minute restart does not wake people up.
- **The window is no shorter than 2–3× the data point period**: a 2-minute window with points every 30 s flapped OK ↔ Alarm.
- **"No points in the window" and "no metrics for the selector" are different settings**: the second fires on selector indexing delay, not on missing data; configure the first.
- A new alert goes as a row into this catalog in the same PR as the metric.
