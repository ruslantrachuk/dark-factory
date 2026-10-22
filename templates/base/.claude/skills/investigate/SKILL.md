---
name: investigate
description: Investigate an incident in prod or on the stand — by correlation_id, a user complaint (who + when), the request text, an alert name or "something broke". Collects logs, the DB (read-only), LLM traces and metrics, builds a timeline, names the root cause with evidence. Use for "figure out why…", "the bot didn't answer", "an alert fired", "a user is complaining", "investigate", and when the On-call agent of a group forwarded a complaint.
---

# Skill `investigate` — incident investigation

> Skeleton of the dark factory canon (the "Incident investigation" practice, `docs/practices/incidents.md`).
> The order and rules are generic (distilled from many analysed incidents across projects);
> the "Project sources" section is filled in by the project and verified by a live run.

> **Seam:** hosting logs and metrics, the production DB and the LLM tracer = the project's own tools. To use another tool, rewrite the "Project sources" section.

**An investigation is diagnosis, not permission to make changes** (CLAUDE.md, rule 6). The result is a report
and a proposal; the fix goes the usual feature path (bd task → branch → TDD).

## Rules (generic, do not change)

1. **Prod is read-only.** DB — via a separate read-only role or a SELECT-only script; write-capable hosting tools and MCPs are forbidden during an investigation. Changing prod (migration, restart, rollback) — by the owner's hands.
2. **Do not print secrets; personal data stays out of the report:** in the report use `user_id`/`correlation_id`, not names and not users' texts verbatim, if you can do without them.
3. **Evidence goes to the tracker before deletion** (a bd task with an excerpt), if something will have to be cleaned up.
4. **A missing source does not block** — the analysis continues, the gap goes into "What was missing".
5. **Facts about sources are verified, not postulated.** Log retention, delivery delay, trace coverage — are measured in preflight (a skill once claimed 30 days of retention when it was really 3 — only a blind-spot audit revealed it).
6. **Several matches — list them and ask, do not choose yourself.** Matching by time without a key — mark it "approximate".
7. **"Not our code" is proven** by the code and environment being unchanged along the request path (`git log` of the path, a config diff) — e.g. an external API tightened its format.
8. **Check the way the user goes** (through the proxy/load balancer, with the same headers), not around it (a live check that bypasses nginx proves nothing).

## Project sources (fill in; verify with preflight)

| Source | How to read | Search key | Retention (measured) | If no access |
|---|---|---|---|---|
| logs | `<cloud CLI / files / docker logs>` | `correlation_id`, `event`, `user_id` | `<…>` | `<fallback: file export>` |
| DB (read-only) | `<scripts/ops/investigate_db.py or psql with a ro role>` | `<tables with correlation_id>` | — | `<…>` |
| LLM traces | `<tracer / none>` | `correlation_id` in metadata | `<…>` | — |
| metrics and alerts | `<dashboard>`; alert catalogue — `<docs/deploy/monitoring-alerts.md>` | alert name → metric | `<…>` | — |
| release version | startup log (`version`) | incident time | — | — |
| `<project-specific: queue, diagnostics page, hosting>` | | | | |

## Order

### 0. Preflight
One line per source: is it reachable, is it authorized, what is the real retention. Red — a hint on how to fix it, and continue without it.

### 1. Input → key
| Given | Action |
|---|---|
| `correlation_id` | straight to collection |
| user + approximate time | logs/DB by `user_id` in the window → `correlation_id` |
| request text | search the project's input table or logs → `correlation_id` |
| alert name | alert catalogue → metric → window → ERROR events in the window → `correlation_id` |
| "something broke" | ERRORs and anomalous metrics for the window → list of candidates → ask |

Widen the time windows in steps (with some CLIs a large window silently returns nothing).

### 2. Collection
All sources by the same key. Raw excerpts — in working notes, not in the report in full.

### 3. Timeline
Steps from input to answer (input → routing → LLM/external API calls → write → answer/delivery), each marked: normal / anomaly / error. Release version at the time of the incident.

### 4. Root cause
Class: `<project classes: prompt / data / retrieval / …>` + the mandatory `code`, `infra`, `external`, `config`. Hypotheses are cut off by facts, not by plausibility. Root cause not found — code analysis (skill `code-audit`, mode "figure it out") along the timeline.

### 5. Report
```
## Incident: <correlation_id or short name>, <date>
What happened: <1–2 sentences, what the user saw>
Root cause: <class> — <explanation>
Evidence:
- <source>: <fact>
Release version: <…>
Recommendation: <what to fix: the root, not the symptom; where to degrade instead of failing>
What a human must do: <token rotation, manual migration, … — if any>
What was missing: <sources that were unavailable and what that risks for the next analysis>
```

### 6. Handing over to work (after the owner's "yes")
1. A bd task (bug) with the report; significant ones — a card on the board (skill `board`).
2. Fix along the feature path: reproduce with a failing test that "fails exactly like prod" (`systematic-debugging` → TDD), fix the root; the regression test — one level lower (push-tests-down); in the commit — why the existing tests did not catch it.
3. Record the analysis in the devlog: date, symptom, how it was found, `correlation_id`, root cause, fix, remaining human actions.
4. A rule, if the incident suggested one, — into the project (CLAUDE.md/CODING_STANDARDS "rule + episode"); one that recurs in two projects — a canon candidate at the next collection.
5. The skill lied (source, retention, command) — fix this file in the same PR.
6. The complaint came from a feedback group — answer in the group through the On-call agent (skill `feedback-desk`): what was found and when the fix will land, without internal details.
