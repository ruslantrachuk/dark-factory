# Factory analytics: weekly numbers of how the factory works

## Why

The factory claims that agents carry work from a request to a release with the owner stepping in less and less.
Nothing measures it. Every session already leaves what is needed on the server — transcripts with token counts,
roles and models, merged PRs, CI runs — and Claude Code deletes the transcripts after 30 days, so the history is lost
week by week.

Published numbers do two things: the owner sees where the tokens go and whether the friction falls, and a visitor of
the public repository sees a working factory instead of a claim.

## What changes

- A new plugin script, `plugins/dark-factory/scripts/analytics.py` (stdlib only, no model, no quota spent), that
  reads every project of the server and writes one week of numbers:
  1. who drove the work — the owner in a session, an unattended run (scheduled task, pipeline, review, monitor),
     the On-call for a client;
  2. a multi-agent pipeline against direct work in a session with skills;
  3. backend against frontend;
  4. the cost of tests (CI minutes, test runs inside sessions);
  5. the owner's friction: swearing, interrupts, rejected tool calls — counts only.
  Cost is in tokens only.
- The raw weekly numbers are kept on the server, so the series outlives the transcript cleanup.
- A weekly report into a target repository: `analytics/<YYYY>-W<ww>.md` per week and `analytics/SUMMARY.md` with
  the accumulated series. Projects are letters (A, B, C…); the letter map stays on the server.
- A weekly timer, `df-fleet-analytics.timer`, written by `fleet.py provision` when the server's `fleet.env` names a
  target repository. It collects, renders and opens a PR; the owner reviews and merges it.
- The first run fills in every week the server still has.
- For this repository: the owner's factory publishes its own numbers here, in `analytics/`, and the README says so in
  one line.

## Not in this change

- Recording the chain "client message → task → PR → release" in the On-call. Until it exists, the On-call share is
  derived from the sessions and is marked approximate. A separate change.
- Money. Subscriptions do not bill by token; no conversion to API prices.
- Message texts, branch names, PR titles, paths — never leave the server.
