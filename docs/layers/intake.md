# The Relations layer: intake

> **Stages:** the start of Requirements (phases 1–2 of [map.md](../map.md)); it is also where Support and feedback
> returns to the line. Layer 1 of [process.md](../process.md).
>
> The output of intake is a card proposal for the board (see [coordination.md](coordination.md)).

## Typical input channels

| Channel | Typical state |
|---|---|
| **External tracker** (the client's) | defines the sprint and is the most reliable channel, but verbal bug reports bypass it |
| **Meeting transcripts** | the meeting platform produces a recording or transcript, which **usually lies untriaged**; now and then someone copies it into `docs/inputs/` by hand |
| **"From memory"** (verbal bugs, thoughts on the go) | there is nowhere to put them; someone "may file it right after the meeting", or may not |

## What people want
- "One place that works wherever Claude is": **tell an LLM to save something quickly**, a note like "look into
  this", and it appears on the board for triage; the project's workflow may offer to do the triage itself.
- Not everything can be covered in one universal way; **project instructions and skills plus one automatic path
  cover most cases**.

## Target design

**Only the output is universal:** a card proposal (what, why, where it came from) plus a human's confirmation. The
inputs are per-project adapters.

1. **Quick capture, for the "from memory" channel**: any Claude session (desktop, phone, voice) with the Linear
   connector → the phrase "note: …" → a card in the team's **Triage** (an inbox for triage; if Triage is not
   available on the plan, Backlog without a project). This keeps the rule "people create cards": the phrase is an
   explicit decision, and the agent only saves the clicks. It works for every team member who has their own Claude
   and connector.
2. **The transcript adapter** (`transcript-intake`): not just a summary, but **"triage it and list what is new for
   us"**. It compares the transcript with the project's current state (board, target picture, baseline): new
   agreements become card proposals; changes in commitments become a note against the baseline (a change request);
   contradictions with open umbrellas are raised explicitly. What is already known is filtered out, so the human sees
   only the difference.
3. **The tracker mirror adapter**: for projects with an external tracker, pre-triage of the sprint's tickets and
   sending statuses back.

A human does the triage, with the agent's help (the agent proposes the project, the umbrella, and whether to merge
or reject).

## Operational requirements (settle before scaling)

- **An owner for intake.** Rule: **"whoever opens the board first in the morning does the triage; the agent reminds
  you when a note is older than 3 days"**. This is built into the `board` skill (the status overview shows notes
  with their age).
- **Idempotency.** One transcript may arrive by email, through another tool and as a file, so processing needs a
  trace (the meeting date and a "triaged, see report X" mark in `inputs/` or on the card) to avoid duplicate
  proposals.
- **A project registry** (Linear project ↔ repository ↔ client ↔ external tracker ↔ sync direction), kept in the
  `board` skill's configuration and kept current.
- Failures and privacy (an empty attachment, an unreachable mailbox, other people's personal data in a transcript):
  rules will be added as the practice matures.

## Open questions
- **Transcript delivery.** The trigger usually exists already: the meeting platform sends an email after the
  meeting. The factory adapter is a bridge: the transcript (from an existing mail or ingest tool, or by email) → the
  "what is new for us" skill → proposals in Triage. Which end to connect (an existing ingest tool, forwarding to a
  mailbox Claude can read, or a file by hand) is decided per project.
- How and where each team member records meetings: clarify when they are onboarded to the board.
- The Triage rhythm (daily? at the start of each session?): settle on a simple rule in practice.
