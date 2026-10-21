# The Coordination layer

> Requirements for the layer (the typical starting state, the pains, the target picture) and its design: the board in Linear for people,
> the bd queue as the execution state for the machine. The working procedures are in the base `board` skill.

## Typical starting state

- **Parallelism exists only at the project level**: once a week a call decides who runs which project this week. Within the week everyone works solo.
- **Weekly project ownership is not a design but a crutch**: a consequence of being unable to work together, not a goal.
- **Handing a project over**: unfinished work and new tasks are dropped into a heterogeneous "somewhere" (the client's tracker if there is one; otherwise beads or a roadmap) + a phone call.
- **The devlog** carries context only from "me yesterday" to "me today" on one machine. Between people/machines it is dead: a local file, invisible without git discipline, with no incentive to update it. A cloud routine summarising upstream commits is a prosthesis for that blindness.
- **Beads does not work between people**, for four reasons:
  1. invisibility — not in front of your eyes; "if you did not query the CLI, it does not exist";
  2. not present in every project;
  3. fragility — hard to install, breaks across versions;
  4. **clutter — agents dump debts and trivia into it**; the machine queue and the human list of intents are mixed in one object → people stop opening it.

## What hurts

1. **No portfolio visibility**: nobody sees the total volume of tasks across projects.
2. **Project context = one person's head**: progress is invisible, there is nothing to discuss, "what is done" is unclear.
3. **Bus factor = 1 per project**: a vacation stalls the project.
4. **No target picture → the factory builds the wrong thing.** Where the roadmap lives in the client's tracker, it is a (drifting) progress reference; where there is none, the team ends up building extras outside the mandatory scope. The most expensive pain: a week of work that misses the commitments.

## Four floors of the layer

| Floor | What it is | Without a coordination layer |
|---|---|---|
| **Target picture** | "where we are going, what is mandatory" — a reference for measuring progress and checking priority | exists only if the client set it up |
| **List of intents** | "what we do, who took it" — the object of claiming | does not exist (gap G1) |
| **State hand-over** | "what is done, where I stopped" | inside one head (devlog); between people — a phone call |
| **Delivery log** | "what was shipped and when" — summaries for the client, memory of "what and why we shipped" | needed and important; exists only where the client's tracker exists |

**The delivery log has two levels:**
- **Git level (technical, assembled):** git is always there; a technical what's-new is assembled from the commit log — provided the commits are written in human-readable text, not terse LLM telegraphese. The fixation is a milestone/release at the git level. This makes the "human-readable prose, not telegraphese" commit-message rule load-bearing for the factory, not a matter of taste.
- **Ticket level (managerial):** fixation in "tickets" — closing umbrella cards/milestones on the board. This is what people discuss and show the client.

Consequence: the technical level is generated from git (not kept by hand); the managerial level is a simple transaction on the board. "State hand-over" at shipping is a release/milestone, not a retelling.

## Target picture

Open it any day and see: **list of projects → in each, a list of tasks → who took what**. For fixed-price — the percentage of the mandatory scope implemented; for T&M — a list of near-term tasks. From this, understand **what I can take on** (details clarified with a colleague on the spot), and what is already taken and will be done by a partner.

Purpose: switch work from "weekly project ownership" to a **pull model** — the board itself is the claiming mechanism that turns sequential work into parallel work.

Clarifications:
- **The granularity of a human card can be coarse** — down to an umbrella "client task for sprint 5". The card is understood by people through an agreement ("this sprint is entirely closed by one person"); it does not need to mirror machine-level detail.
- **People's hands may take part** in keeping the board current (closing, recording the fact of delivery) — this is a meaningful action, not mechanics. Condition: it must be **simple and clear**. The agent is a helper in the bookkeeping, not a mandatory monopolist.
- **The internal tail of shipping** — without this layer the fact of delivery is scattered over 4–5 places in the harness repo (ROADMAP, SHIPPED, devlog, bd); in the target picture, shipping ends with one clear transaction in the coordination layer.

## Constraints (hard)

1. **The form is the web**, a live window. Digests are only a supplement (a digest is a snapshot; between snapshots you are blind).
2. **Nothing home-grown.** Only existing tools.
3. The human list and the machine queue are **different objects with different granularity** (the lesson of beads dying as a channel between people; likewise, "a tasks.md line does not translate into an issue").

## Desirable (not mandatory)

- Accounting for the **project's contract type** in the progress view (fixed-price: % of mandatory scope; T&M: the near-term queue). This is desirable, not a hard requirement — there are **hybrids** (mixed fixed-price/T&M), so a strict either-or typing would be wrong.

## Design: the board and the queue

Two objects with different granularity, never mirrored into each other:

| Object | What it holds | Who writes |
|---|---|---|
| **The board** (Linear) | the target picture (Projects), the list of intents (umbrella cards), claims (assignee), the delivery log (Shipped cards with links to releases) | people, and the agent on an explicit human command (`board` skill) |
| **The bd queue** | the execution state: the task graph of a change (`openspec-to-beads`), claims of subtasks, statuses inside a feature run | the development session and the feature pipeline; committed as `.beads/issues.jsonl` in the same PR as the code |

A card references its spec and bd epic; the link is a pointer, not a sync.

### Card state machine
`Backlog` (a note for triage) → `Todo` (free) → `In Progress` (claimed, assignee = who) → `In Master` (merged, waiting for shipping) → `Shipped` (on the stand, the client sees it); `Canceled`/`Duplicate` — managed failure. Blocked is an exception comment ("blocked: reason + what is needed"), not a status.
- "Done in code" ≠ "release created" ≠ "shipped to the client" — three different facts.
- **Magic words (`Fixes LIN-123`) on umbrellas are linking only, NOT closing**: one PR does not close "sprint 5" made of six changes.

### Single-writer rules
1. **A card is created only by an explicit human decision.** "Note: …" is such a decision; anything the agent proposes on its own is a text draft until a "yes".
2. **A merge moves a card at most to `In Master`.** `Shipped` — only by the ship transaction on a human command, with proof of delivery.
3. **Nobody removes a claim silently.** A claim with no movement for more than 5 working days is proposed for return to `Todo` in the status overview; the return happens on a "yes" from any person.
4. **Inside a feature run one integrator writes git and bd**; implementation agents write code and tests and do not commit. The run closes only its own subtasks; the parent task is closed by `merge-feature.sh` at merge, which also carries the queue state.
5. **The train number** (`openspec/CURRENT_TRAIN`) and release numbers are incremented only by a human.
6. **Coordination state is not kept in free-form files**: ROADMAP-style files are reports, not the place where tasks live.

### Merge and ship transactions
"Done" (in master) and "Shipped" (the client will see it) are **two states with a gap of up to a week**; shipping is batched. When the client looks at the dev stand directly, "on the dev stand" = "the client saw it" — one event; production is an attribute of the delivery, not a separate status.

- **Merge transaction** (frequent, cheap): PR into master → card `In Master` + a link to the PR. Where the tracker's GitHub integration works, the automation "PR merged → In Master" does it; otherwise the agent. An umbrella made of several PRs moves with the last one — a human decision when in doubt.
- **Ship transaction** (rare, batched, meaningful): started by a human ("shipping project X"), executed by the agent: the project's `In Master` cards are confirmed, proof of delivery is required (a deploy log or a human "it's on the stand"), then a git tag + release notes from human-readable commits, cards → `Shipped` with a link to the release, the client's tracker updated where there is one. The agent does not deploy; it records the fact.

### Progress and the delivery record
- **Fixed-price progress is a baseline, not a card counter.** The Project description holds an immutable baseline matrix of the mandatory scope; a card's weight is set by a human (or "1 umbrella = 1 contractual deliverable"). Progress is counted by `Shipped` only. A change request is an explicit, marked edit of the baseline.
- **One delivery record**: a milestone/closing on the board with links to git releases. A GitHub Release is a per-repo technical artifact, not the log itself: it covers neither a multi-repo delivery nor the fact of external acceptance.

### Keeping the board alive
1. **One URL** — a single view "today: projects → umbrellas → who took what".
2. **A limit on open cards** (about 5–7 per project) + regular cleanup; Backlog notes are triaged by whoever opens the board first in the morning.
3. **Comments only by an exception template**: blocked / decision needed / the next concrete step / a link to an artifact. No diary summaries.

### Client facades and workspace
- For every project, explicitly: who is the source (the client's contractual tracker or our board), sync direction, the ID link, what must not be rewritten silently (creation/closing/scope). Typically the client's tracker is the contractual source for the client, the board is internal; statuses go one way, with an error log.
- A Team is an access boundary, not an org folder: one team while everyone may see everything, participants at the Project level; a separate team only when someone must not see everything.

## Open questions

1. Card template: result/acceptance, owner, client, contract mode, links (code, external tracker, bd epic).
2. Rights: who creates/closes/reassigns umbrellas beyond the rules above; what the agent may do on its own.
3. Baseline and change requests: where they are recorded, who changes them.
4. A report to the client from the board — without internal notes.
5. The fate of existing ROADMAP.md files (freeze → generate from the board?).
6. How the floors connect: target picture ↔ tasks ↔ state hand-over (and what replaces the phone call).
