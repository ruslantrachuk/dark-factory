# The Relations layer / intake — understanding

> The output of intake is a card proposal for the board (see [coordination.md](coordination.md)).

## Typical input channels

| Channel | Typical state |
|---|---|
| **External tracker** (the client's) | defines the sprint; the most reliable. But verbal bug reports bypass it |
| **Meeting transcripts** | the meeting platform produces a recording/transcript → **more often it lies untriaged**; it reaches `docs/inputs/` by hand, now and then |
| **"From the head"** (verbal bugs, thoughts on the go) | there is no carrier; someone "may file it right after the meeting" — as luck would have it |

## What is wanted
- "A universal place that works wherever Claude is": **talk to an LLM just to save something quickly** — a note "look into this" → it appears on the board "for triage"; the project workflow may offer the triage itself.
- Not everything can be covered universally — **project instructions/skills + an automatic path cover most cases**.

## Target design

**Only the output is universal:** a "card proposal" (what / why / where from) + confirmation by a human. Inputs are per-project adapters.

1. **Quick capture, the "from the head" channel**: any Claude session (desktop, phone, voice) + the Linear connector → the phrase "note: …" → a card in the team's **Triage** (an inbox "for triage"; if Triage is not available on the tier — Backlog without a project). The rule "cards are created by people" is not broken: the phrase is an explicit decision; the agent only removes the clicks. Works for every team member with their own Claude + connector.
2. **The "transcript" adapter** (`transcript-intake`): not just a summary but **"triage it and build what is new for us"** — a diff of the transcript against the project's current state (board, target picture, baseline): new agreements → card proposals; changes in commitments → a note against the baseline (change request); contradictions with open umbrellas → raised explicitly. What is known is filtered out — the human sees only the delta.
3. **The "tracker mirror" adapter**: for projects with an external tracker — pre-triage of the sprint's tickets, propagating statuses back.

Triage is done by a human with the agent's help (the agent proposes: project, umbrella, merge/reject).

## Operational requirements (decide before scaling)

- **Owner of the intake process** — rule: **"whoever opens the board first in the morning does the triage; the agent reminds if a note is older than 3 days"**. Built into the `board` skill (the status overview shows notes with their age).
- **Idempotency**: one transcript may arrive by email, through another tool and as a file → a processing trace is needed (meeting date + a mark "triaged, report such-and-such" in `inputs/` or on the card) so that duplicate proposals are not produced.
- **Project registry** (Linear project ↔ repo ↔ client ↔ external tracker ↔ sync direction) — kept in the `board` skill's configuration; keep it current.
- Failures and privacy (empty attachment, unreachable mailbox, other people's personal data in a transcript) — rules to be added as the practice matures.

## Open ends
- **Transcript delivery** — the trigger usually exists: the meeting platform sends an email after the meeting. The factory adapter is a bridge: transcript (from an existing mail/ingest tool, or by email) → the "what is new for us" skill → proposals in Triage. Which end to connect (an existing ingest tool / forwarding to a mailbox Claude can read / a file by hand) — decide per project.
- How each team member records meetings and where — clarify at their onboarding to the board.
- The Triage rhythm (daily? at session start?) — set a simple rule in practice.
