# The Coordination layer — understanding

> Requirements for the layer: the typical starting state, the pains and the target picture.
> Design and tool choice — [coordination-design.md](coordination-design.md).

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

## Open design questions

- Tool choice under the constraints (candidates: Linear — a ready mapping "Project = stage, Issue = release"; GitHub Projects — next to the code; the client's tracker where there is one).
- How the factory board and the clients' trackers coexist (facades? one board on top?).
- Who/what fills and updates the board (people's hands alone will not do it — an agent synchroniser is needed; link with intake).
- How the floors connect: target picture ↔ tasks ↔ state hand-over (and what replaces the phone call).
