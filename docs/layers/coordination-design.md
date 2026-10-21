# The Coordination layer — design (v0.1)

> Requirements — [coordination.md](coordination.md). Principle of choice: "choose the tool by an honest pilot, not by a preference for its interface".

## Comparison of candidates

**A. Linear** — a management board: Initiatives/Projects (target picture), Issues (umbrellas, claim = assignee), the GitHub App (linking branches/PRs), MCP for agents. Risks: one more tool; free-tier limits (not a problem at umbrella granularity); **a self-hosted GitLab behind a VPN cannot be integrated** (Linear supports only a publicly reachable GitLab instance) — there linking is done by hand or by an agent.

**B. GitHub Projects (v2)** — easy to underestimate: it has board/table/roadmap views, auto-add by filters, charts/burn-up, parent/sub-issue progress; **issues from any organisation can be added** (the limitation is subtler: org fields of foreign orgs are empty → project fields Owner/Client are needed). Free, git-native.

**The honest argument for Linear is behavioural only:** "two people will really open it every day". That is verified by a pilot, not by reasoning.

## Model

### 1. Card state machine (instead of "closed and done")
`Unclaimed → Claimed/In progress → Ready to ship → Shipped` (+ `Blocked`).
- PR automation (merge) moves a card at most to **Ready to ship**.
- **Shipped — only by an explicit closing transaction** (a human, or an agent on command): date, a link to the release/tag, proof of delivery/acceptance. "Done in code" ≠ "release created" ≠ "shipped to the client" — three different facts.
- **Magic words (`Fixes LIN-123`) on umbrellas are linking only, NOT closing**: one PR does not close "sprint 5" made of six changes.

### 2. Fixed-price progress: a baseline, not a card counter
% of closed cards ≠ % of commitments. Rule: the Project description holds an **immutable baseline matrix of the mandatory scope**; a card's weight is set by a human (or the convention "1 umbrella = 1 contractual deliverable"). The percentage is an indicator, not an acceptance criterion. A change request is an explicit, marked edit of the baseline.

### 3. One delivery record, not "both, roughly"
The human delivery log = **a milestone/closing on the board with links to git releases**. A GitHub Release is a per-repo technical artifact (auto-notes from readable commits), not the log itself: it covers neither a multi-repo delivery, nor GitLab repos, nor the fact of external acceptance.

### 4. Anti-beads rules (operationalised)
1. **One URL** — a single view "today: projects → umbrellas → who took what"; that is the "window".
2. **A limit on open cards** (around ≤ 5–7 per project) + regular cleanup of Unclaimed/Blocked.
3. **The agent does NOT create cards without an explicit human decision** (otherwise in a month it is beads with a nice UI).
4. **An SLA on a stale claim**: taken and not moving for N days → the card returns to the pool, visible to everyone.
5. Comments on a card — **only by an exception template**: blocked / decision needed / the next concrete step / a link to an artifact. No diary summaries (otherwise the devlog comes back under a new name).

### 5. Client facades: source of truth and direction
For every project, explicitly: who is the source (the client's contractual tracker OR our board), sync direction, the ID link, what must not be rewritten silently (creation/closing/scope). A common case: the client's tracker is the contractual source for the client, the board is internal; statuses are propagated one way, with an error log.

### 6. Workspace structure
A Team is an ACCESS boundary, not an org folder. While everyone may see everything — one team, with participants at the Project level (a Project has its own members/lead; different line-ups on different projects are normal). A separate team is created only when a person appears who must not see everything (and with it, possibly a paid tier: private teams/guests). Moving cards between teams is standard, so the decision is reversible — do not split in advance.

## Shipping transaction

"Done" (in master) and "Shipped" (the client will see it) are **two states with a gap of up to a week**; shipping is batched (a week of merges → one delivery). When the client looks at the dev stand directly, "on the dev stand" = "the client saw it" — one event; production is an attribute of the delivery, not a separate status.

Two transactions of different nature:

**Merge transaction** (frequent, cheap, automatable):
- PR/MR into master → card status **"In Master"** (type started, NOT completed).
- Where the tracker's GitHub integration works: automation "PR merged → status"; otherwise an agent or a human.
- An umbrella moves to "In Master" with its last PR closed — a human decision or an explicit rule.

**Ship transaction** (rare, batched, meaningful):
- Deploy to the client stand → all of the project's "In Master" cards → **"Shipped"** (Done).
- At the same time: a git tag + release notes from the commits since the previous delivery (the technical log is generated here); a link to the release on the cards; updating the client's facade where there is one.
- Started by a human ("shipping project X"), executed by an agent. By hand — one decision, not bookkeeping.

**Project progress (fixed-price %) is counted by "Shipped"** — a promise to the client is closed only by what the client can see. "In Master" is the internal truth and does not count toward the percentage (hence its status type is started).

Linear setup (UI, by hand): rename "In Review" → "In Master" (or add a started-type status); automation "PR merged → In Master" in the GitHub integration settings.

## Choosing the tool: a pilot with criteria set in advance
Pilot on one live project without a network perimeter. About 2 weeks. Success criteria, measured from facts:
- both people open the board ≥ N times a week without reminders;
- the share of work visible on the board before it starts (not post factum);
- the number of manual reconciliations/"what are you on" calls goes down;
- a project hand-over without a call — did it happen at least once.

GitHub Projects is the fallback: migration is cheap (there are few cards and they are umbrellas).

## Open questions
1. Card template: result/acceptance, owner, client, contract mode, links (code, external tracker, bd epic).
2. Rights: who creates/closes/reassigns umbrellas; what the agent may do.
3. Exact semantics of a claim: WIP limit, staleness period, hand-over on vacation/departure.
4. Baseline and change requests: where they are recorded, who changes them.
5. A report to the client from the board — without internal notes.
6. The fate of existing ROADMAP.md files (freeze → generate from the board?).
7. The shipping transaction: a step-by-step procedure (what the human presses, what the agent fills in).
