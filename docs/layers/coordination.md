# The Coordination layer

> **Stages:** all six. Coordination runs alongside every stage rather than being one of them, and it carries the
> factory's Observe job. See the Coordination row in [process.md](../process.md).
>
> This page holds the requirements for the layer (the typical starting state, the pains, the target picture) and its
> design: the board for people, and the execution queue as the execution state for the machine. The contracts of
> both, and the tools the reference implementation uses, are in [functions.md](../functions.md); the working
> procedures are in the base `board` skill.

## Typical starting state

- **Parallel work exists only at the project level**: once a week a call decides who runs which project that week.
  Within the week, everyone works alone.
- **Weekly project ownership is a crutch, not a design**: it follows from not being able to work together; nobody
  chose it as a goal.
- **Handing a project over**: unfinished work and new tasks get dropped into a mix of places (the client's tracker
  if there is one, otherwise the agents' task queue or a roadmap), plus a phone call.
- **A session log file** carries context only from "me yesterday" to "me today" on one machine. Between people or machines it
  is useless: a local file, invisible without git discipline, with no incentive to update it. A scheduled cloud job
  that summarises upstream commits only works around the problem.
- **The machine queue (beads, in this experience) does not work between people**, for four reasons:
  1. it is invisible: not in front of you, and "if you did not query the CLI, it does not exist";
  2. it is not present in every project;
  3. it is fragile: hard to install, and it breaks across versions;
  4. **it gets cluttered, because agents dump debts and trivia into it**. The machine queue and the human list of
     intents are mixed in one object, so people stop opening it.

## What hurts

1. **No view of the portfolio**: nobody sees the total volume of tasks across projects.
2. **A project's context lives in one person's head**: progress is invisible, there is nothing to discuss, and it
   is unclear what is done.
3. **A bus factor of 1 per project**: one vacation stalls the project.
4. **No target picture, so the factory builds the wrong thing.** Where the roadmap lives in the client's tracker, it
   is a progress reference that drifts; where there is none, the team builds extras outside the mandatory scope.
   This is the most expensive pain: a week of work that misses the commitments.

## The four parts of the layer

| Part | What it is | Without a coordination layer |
|---|---|---|
| **Target picture** | "where we are going, what is mandatory": a reference for measuring progress and checking priority | exists only if the client set it up |
| **List of intents** | "what we do, who took it": the thing people claim | does not exist (gap G1) |
| **State hand-over** | "what is done, where I stopped" | inside one head (a session log); between people, a phone call |
| **Delivery log** | "what was shipped and when": summaries for the client, the memory of what we shipped and why | needed and important; exists only where the client has a tracker |

**The delivery log has two levels:**
- **Git level (technical, assembled).** Git is always there, so a technical "what's new" is assembled from the
  commit log, provided commits are written as readable text, not as terse LLM notes. At this level a milestone or
  release marks each delivery. This is why the rule "commit messages are readable prose, not terse notes" matters to
  the factory and is not a matter of taste.
- **Ticket level (managerial).** Deliveries are marked by closing umbrella cards or milestones on the board. This is
  what people discuss and show the client.

Consequence: the technical level is generated from git, not kept by hand, and the managerial level is a simple
transaction on the board. The state hand-over at shipping is a release or milestone, not a retelling.

## Target picture

Open the board on any day and see: **a list of projects → a list of tasks in each → who took what**. For a
fixed-price project, the share of the mandatory scope that is implemented; for time and materials (T&M), a list of
near-term tasks. From that, see **what I can take on** (details agreed with a colleague on the spot) and what is
already taken by a partner.

Purpose: move work from weekly project ownership to a **pull model**, where the board itself is the claiming
mechanism that turns sequential work into parallel work.

Clarifications:
- **A human card can be coarse**, down to an umbrella like "client task for sprint 5". People understand the card
  through an agreement ("one person closes this whole sprint"); it does not need to mirror machine-level detail.
- **People may keep the board current by hand** (closing cards, recording a delivery): that is a meaningful action,
  not busywork, as long as it stays **simple and clear**. The agent helps with the bookkeeping; it does not have to
  own it.
- **The internal tail of shipping**: without this layer, the fact of a delivery is scattered over four or five
  places in the harness repository (ROADMAP, SHIPPED, PR descriptions, the queue). In the target picture, shipping ends with one
  clear transaction in the coordination layer.

## Hard constraints

1. **It is a web page**, a live view. Digests are only a supplement: a digest is a snapshot, and between snapshots
   you are blind.
2. **Nothing home-grown.** Only existing tools.
3. The human list and the machine queue are **different objects with different granularity**. This is the lesson of
   the machine queue failing as a channel between people; likewise, a line in tasks.md does not translate into an issue.

## Desirable, not mandatory

- The progress view takes the **project's contract type** into account (fixed-price: the share of mandatory scope;
  T&M: the near-term queue). This is not a hard requirement, because there are **hybrids** (mixed fixed-price and
  T&M), so a strict either-or would be wrong.

## Design: the board and the queue

Two objects with different granularity, never mirrored into each other:

| Object | What it holds | Who writes |
|---|---|---|
| **The board** (for example, Linear) | the target picture (Projects), the list of intents (umbrella cards), claims (assignee), the delivery log (Shipped cards with links to releases) | people, and the agent on an explicit human command (the `board` skill) |
| **The execution queue** (for example, beads) | the execution state: the task graph of a change (`openspec-to-beads`), claims of subtasks, statuses inside a feature run | the development session and the feature pipeline; one local store per project, not committed (the record of what was done is the PR and the merge history) |

A card refers to its spec and its queue epic; the link is a pointer, not a sync.

### Card state machine
`Backlog` (a note waiting for triage) → `Todo` (free) → `In Progress` (claimed; the assignee is who took it) →
`Merged` (merged, waiting to ship) → `Shipped` (deployed where the client can see it).
`Canceled` and `Duplicate` are managed failures. Blocked is an exception comment ("blocked: reason + what is
needed"), not a status.
- "Done in code", "release created" and "shipped to the client" are three different facts.
- **Magic words (`Fixes LIN-123`) on umbrella cards only link, they do NOT close**: one PR does not close a
  "sprint 5" made of six changes.

### Single-writer rules
1. **A card is created only by an explicit human decision.** "Note: …" is such a decision; anything the agent
   proposes on its own is a text draft until someone says "yes".
2. **A merge moves a card no further than `Merged`.** Only the ship transaction, on a human command and with proof
   of delivery, moves it to `Shipped`.
3. **Nobody removes a claim silently.** A claim with no movement for more than 5 working days is proposed for return
   to `Todo` in the status overview; it returns on a "yes" from anyone.
4. **Inside a feature run, one integrator writes to git and the execution queue**; implementation agents write code and tests and do
   not commit. The run closes only its own subtasks; `merge-feature.sh` closes the parent task at merge (found from the
   branch name: tracker ID or slug) and also carries the queue state.
5. **Release numbers (CalVer tags) are cut only by the release script or a human.**
6. **Coordination state is not kept in free-form files**: ROADMAP-style files are reports, not the place where
   tasks live.

### Merge and ship transactions
"Done" (merged to main) and "Shipped" (the client will see it) are **two states up to a week apart**, because
shipping is batched. Acceptance happens on the dev stand (the environment that runs main) before the release, so "Merged" is "on the dev stand" and
"Shipped" is "released to production"; production is an attribute of the delivery, not a separate status.

- **Merge transaction** (frequent, cheap): a PR into main → the card moves to `Merged`, with a link to the PR.
  Where the board's integration with the code host works, its "PR merged → Merged" automation does this; otherwise the
  agent does. An umbrella made of several PRs moves with the last one; when in doubt, a human decides.
- **Ship transaction** (rare, batched, meaningful): a human starts it ("shipping project X") and the agent carries
  it out. The project's `Merged` cards are confirmed; proof of delivery is required (a deploy log, or a human
  saying "it's live for the client"); then a git tag and release notes from readable commits; the cards move
  to `Shipped` with a link to the release; and the client's tracker is updated where there is one. The agent does not
  deploy; it records the fact.

### Progress and the delivery record
- **Fixed-price progress is measured against a baseline, not by counting cards.** The Project description holds a
  fixed baseline matrix of the mandatory scope; a human sets each card's weight (or uses "1 umbrella = 1 contractual
  deliverable"). Progress counts `Shipped` cards only. A change request is an explicit, marked edit of the baseline.
- **One delivery record**: a milestone or closing on the board, with links to git releases. A release on the code host is a
  technical artifact of one repository, not the log itself: it covers neither a delivery across several repositories
  nor the fact of the client's acceptance.

### Keeping the board alive
1. **One URL**: a single view of "today: projects → umbrellas → who took what".
2. **A limit on open cards** (about 5–7 per project) and regular cleanup; whoever opens the board first in the
   morning triages the Backlog notes.
3. **Comments only from an exception template**: blocked, decision needed, the next concrete step, or a link to an
   artifact. No diary-style summaries.

### Client facades and workspace
- For every project, state explicitly: which side is the source (the client's contractual tracker or our board),
  the sync direction, the ID link, and what must not be changed silently (creation, closing, scope). Typically the
  client's tracker is the contractual source for the client and the board is internal; statuses flow one way, with
  an error log.
- A team on the board is an access boundary, not an org-chart folder: use one team while everyone may see everything, and
  add participants at the Project level; create a separate team only when someone must not see everything.

## Open questions

1. A card template: result and acceptance, owner, client, contract type, links (code, external tracker, queue epic).
2. Rights: who creates, closes and reassigns umbrellas beyond the rules above; what the agent may do on its own.
3. The baseline and change requests: where they are recorded, and who changes them.
4. A report to the client generated from the board, without internal notes.
5. What happens to existing ROADMAP.md files (freeze them, then generate them from the board?).
6. How the four parts connect: target picture ↔ tasks ↔ state hand-over (and what replaces the phone call).
