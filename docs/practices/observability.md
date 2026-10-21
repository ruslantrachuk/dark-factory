# Practice "Observability" (logging and LLM)

> Standard — layer 3 (Production): what the code writes from the first line. Modules — phase 10 (Operation):
> metrics, dashboard, alerts. Standard: base CODING_STANDARDS, "Logging and LLM — mandatory minimum"; modules —
> [templates/observability](../../templates/observability/MANIFEST.md) and [templates/prod-monitor](../../templates/prod-monitor/MANIFEST.md).

## Why
What is not in the log from day one is not in the production investigation. Adding an end-to-end identifier and structure to a live
project is expensive — especially where the log is the only audit trail. An LLM adds its own blind spots: spend is not measured, a hung call hangs for half an hour,
a strict schema kills the fallback.

## Joints
| Takes | Gives |
|---|---|
| — (code standard) | events with `event`, `correlation_id`, `user_id` → [Incident investigation](incidents.md) |
| LLM calls | traces with `correlation_id`, an `llm.usage` event → a spend metric |
| business slices and counters | `/metrics/business` → dashboard and alerts |
| an alert | input to an investigation (ahead of the client's complaint) |

## Where it is in the canon
- Standard (base): structured logs, `event` in ASCII, an end-to-end `correlation_id`, levels, secrets and personal data, logging configuration under test, the version in the startup log; prompts in files, models in settings by full id, a single client factory with a timeout based on measurement, a lenient schema + coercion, `llm.usage`, traces, documents in a prompt are data, tests without a live model, evals separately.
- The `prod-monitor` module: a model-free watchdog every minute + an agent on the Claude Agent SDK that only reads and, through the On-call agent, tells the group about a real failure; a catalogue of known incidents and background noise.
- The `observability` module: the `/metrics/business` contract, a catalogue of alerts and rules (silence is a signal, one push on failure), a variant for `<your hosting>` monitoring.

## Resolved contradictions
- **Log language:** `event`, fields, reason codes — ASCII (machine code); `message` — in the project language; search only by fields.
- **Live keys:** tests — never; an LLM-quality eval gate — allowed, by hand before shipping, with the key from CI secrets.
- **Timeouts:** not a number but a principle — by measured p95 with a margin; the worst case is recorded.

## Open
- A rule about raw user text in logs and tables — a project placeholder; there is no general rule yet.
- An LLM call cache keyed by a fingerprint of prompt and model — a candidate for the standard once a second project needs it.
