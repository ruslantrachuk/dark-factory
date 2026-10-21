---
name: board
description: >-
  Working with the factory's Linear board — "who took what" status, a quick note for triage, proposing a card, claim, merge and ship transactions. Use on any mention of the board, cards, Linear, "what's in progress", "note: …", "I'm taking this task", "I'm shipping the project".
---

# Skill `board` — the factory board in Linear

> Canonical template (templates/base). Deployed copies differ only in the Configuration section; carry generic improvements back here.

## Configuration (fill in on deployment)

- Workspace: `linear.app/<workspace>`; team: **<team>** (id `<uuid>`, prefix `<PREFIX>`)
- Linear project for this repository: **<project>** (id `<uuid>`); client: <client>; external tracker: <tracker or —, with the direction of status sync>.
- Access: Linear MCP. If the tools are not loaded — `ToolSearch` with the query `+linear` (needed: `list_issues`, `save_issue`, `list_projects`, `save_project`, `list_issue_statuses`, `save_comment`).
- In `save_issue`, pass the project and team as **UUIDs**, not names (more reliable; non-ASCII names can cause a Validation Error).

Work only with the project from the configuration; if in doubt whether a card belongs there, ask — do not pick a "default". (The global registry of all projects is the factory's own operations and is not part of a project copy.)

## Model (do not violate)

- **Card = umbrella**: a large chunk of work that people understand through an agreement ("client tasks for sprint 5"). NOT a micro-task, NOT an agent to-do.
- **The machine queue (beads/tasks.md) is not mirrored onto the board.** The link is a reference from the card to the epic/spec, not a sync.
- Card statuses: `Backlog` (not confirmed / "for triage") → `Todo` (free, can be taken) → `In Progress` (taken, assignee = who) → `In Master` (code merged, waiting for shipping) → `Shipped` (on the stand, the client sees it). `Canceled`/`Duplicate` — managed failure.
- **Project** statuses (Backlog/Planned/In Progress/Completed) — the lifecycle of the whole stage; do not confuse them with card statuses.
- Project progress is counted by `Shipped` — "done" ≠ "shipped".

## Iron rules (anti-beads)

1. **A card is created only by an explicit human decision.** "Note: …", "create a card …" — that is a decision, create it right away. "Propose a card" or your own initiative — only a text draft in the chat; create it after a "yes".
2. **Do not close umbrellas by automation.** A PR/merge moves a card at most to `In Master`. `Shipped` — only via the ship transaction on a human's command.
3. **Comments on a card are for exceptions only**: blocked / owner decision needed / next concrete step / link to an artifact (PR, release, spec). No diary summaries.
4. **Open card limit** ~5–7 per project: when exceeded — warn and propose a cleanup (merge/close/move to Backlog), do not add silently. Backlog notes (the project's `Backlog` cards) do not count toward the limit, but show their count in the status overview; if >10 have piled up — propose triage.
5. The card title is human-readable prose (not telegraphese, not file paths). Description: what / why / where it came from; acceptance — if known.

## Procedures

### "What's in progress?" (status overview)
`list_issues` **for the project from the configuration (project UUID)**, statuses Todo/In Progress/In Master, grouped by assignee. Answer: who has what, what is free (Todo without assignee), what is waiting for shipping (In Master), what is in triage (the project's Backlog). Across the whole team — only if explicitly asked "across all projects"; that is the factory's operations, not a project copy's.

**Note triage rule: "whoever opens the board first in the morning does the triage."** So in every status overview: show the project's Backlog notes with their age; if any is older than 3 days — explicitly remind: "this note is N days old, shall we triage it?". Blocked cards — on a separate line with reasons.

### Quick note ("note: look into X")
Create a card: team and **project from the configuration** — as UUIDs (a note without a project is invisible in the project status overview), status `Backlog`, title from the phrase, description — the context and source verbatim ("according to the owner, <date>"). Do not invent or polish anything — this is raw input for triage.

### Backlog triage ("triage the notes")
For each Backlog card of the project propose: turn it into an umbrella / fold it as a sub-issue into an existing umbrella / reject. Apply after human confirmation (a batch "yes" is acceptable).

### Claim ("I'm taking <PREFIX>-N" / "give it to <name>")
`save_issue`: assignee + status `In Progress`.
- **Blocked**: there is no separate status or label — a block is recorded with an exception comment (`blocked: reason + what is needed`); in the status overview blocked cards are picked out by these comments and shown on a separate line.
- **Stale claim**: In Progress with no movement (no commits/comments/status change) > 5 working days → in the status overview explicitly propose returning it to Todo. The return happens on a "yes" from any of the people (including someone who is not the card's assignee: the card is shared); the agent never removes a claim by itself.

### Merge transaction (PR merged)
Card → `In Master` + a comment linking to the PR. If the project has Linear's GitHub automation — do not duplicate it. An umbrella made of several PRs moves with the last PR — if not sure the umbrella is closed entirely, ask.

### Ship transaction ("I'm shipping <project>") — only on an explicit command
1. Collect the project's cards in `In Master` — show the list: "we're shipping these, correct?"
2. **Proof of delivery is a mandatory input**: `Shipped` means "the client can see it", so before the transition you need one of: a link/log of the deploy to the client stand, or an explicit human confirmation "it's on the stand". A git release by itself is NOT grounds for Shipped.
3. After "yes" + proof: in the project repo — `git tag` + release notes from **human-readable** commits since the previous tag (GitHub: `gh release create --generate-notes` + edit into a readable form).
4. Cards → `Shipped`, on each — a comment: link to the release + where/when it was deployed.
5. If the project has a client tracker — carry the statuses over there or remind someone to.
6. Do not deploy anything yourself — deployment is done by the project's procedure; the skill records the fact.

## What the skill does NOT do
- Does not create/move cards on its own initiative "to keep things tidy".
- Does not carry release history onto the board.
- Does not mirror agent queues.
- Does not increment the project's release/train numbers (that is the project's SSOT; a human increments them).
