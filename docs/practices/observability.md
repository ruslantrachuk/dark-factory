# Practice: Observability (logging and LLM)

> The standard belongs to layer 3 (Production): what the code writes from the first line. The modules belong to
> phase 10 (Operation): metrics, dashboard, alerts. Stages: Development and Monitoring. Standard: base
> CODING_STANDARDS, "Logging and LLM — mandatory minimum". Modules:
> [templates/observability](../../templates/observability/MANIFEST.md) and
> [templates/prod-monitor](../../templates/prod-monitor/MANIFEST.md).

## Why
What is not in the log from day one will not be there for the production investigation. Adding an end-to-end
identifier and structure to a live project is expensive, especially where the log is the only audit trail. An LLM
adds its own blind spots: spend is not measured, a stuck call hangs for half an hour, and a strict schema breaks the
fallback.

## Interfaces
| Takes | Gives |
|---|---|
| — (the code standard) | events with `event`, `correlation_id`, `user_id` → [Incident investigation](incidents.md) |
| LLM calls | traces with `correlation_id`, an `llm.usage` event → a spend metric |
| business slices and counters | `/metrics/business` → dashboard and alerts |
| an alert | the input to an investigation (before the client complains) |

## Where it is in the canon
- Standard (base): structured logs, `event` in ASCII, an end-to-end `correlation_id`, levels, secrets and personal
  data, logging configuration under test, the version in the startup log; prompts in files, models in settings by
  full id, a single client factory with a timeout based on measurement, a lenient schema with coercion,
  `llm.usage`, traces, documents in a prompt treated as data, tests without a live model, evals kept separate.
- The `prod-monitor` module: a watchdog without a model that runs every minute, plus a read-only agent on the
  Claude Agent SDK. Its verdict on a real failure reaches the On-call session as a channel event and goes on to the
  group and the development session. It keeps a catalogue of known incidents and background noise.
- The `observability` module: the `/metrics/business` contract, a catalogue of alerts and rules (silence is a
  signal; one push per failure), and a variant for `<your hosting>` monitoring.

## Settled conflicts
- **Log language:** `event`, fields and reason codes are ASCII (they are for machines); `message` is in the project
  language; search only by fields.
- **Live keys:** never in tests. An eval gate for LLM quality may use one, run by hand before shipping, with the key
  from CI secrets.
- **Timeouts:** not a fixed number but a principle: the measured p95 plus a margin; the worst case is recorded.

## Open questions
- A rule about raw user text in logs and tables: a project placeholder for now; there is no general rule yet.
- A cache for LLM calls keyed by a fingerprint of prompt and model: a candidate for the standard once a second
  project needs it.
