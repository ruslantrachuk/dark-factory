# The factory process on one page

> This page is the top-level model of the process. The detailed map, with phases and transitions, is
> [map.md](map.md), an appendix to this page.

## The lifecycle

The pipeline has six lifecycle stages; they are the primary vocabulary.

| Stage | What the factory puts in place | The human decides |
|---|---|---|
| **Requirements** | A request becomes a card on the board. A card becomes an OpenSpec change: a proposal with the confirmed user-facing surfaces, a design, phased tasks. An approved change becomes a task graph in the queue | what to build; approves the spec |
| **Development** | The operating contract in `CLAUDE.md`; one task card = one branch = one PR; the feature pipeline; the PR description as the record of work (`## Done` / `## Decisions` / `## Open questions`, written into the merge commit), read back with the tasks in progress at the start of every session | scope |
| **Testing** | The enforced test pyramid; pre-push gates; CI tiers (quick on every push, full + browser before a release); secret scanning; a review contract that demands evidence for every finding; the dev stand (it runs main) | accepts the result on the dev stand |
| **Release** | The merge transaction (merge = onto the dev stand, not acceptance). The acceptance mark on the PR (`accepted`), checked when a release is cut. Optionally, production only from tags: `vYYYY.MM.DD.N`, a forward-only `release` branch, generated notes, rollback by tag; a release takes all of main | "ship it" (the owner), or the requester's "ship?" in the On-call chat |
| **Monitoring** | From day one: structured logs with `correlation_id`, LLM usage, the version in the startup log. Then a business health endpoint, an alert catalogue and the model-free watchdog | — |
| **Support and feedback** | The On-call session in the client chat; incident investigation from logs. Every client reply returns to Requirements as a new card | what a reply becomes |

**Humans at the edges, the machine in the middle.** People own four jobs, and one person can hold all of them:
the **Product owner** (what to build, and the client relationship), the **Spec writer** (turns a request into a
spec the agent can execute), the **Reviewer** (accepts, merges and ships) and the **Operator** (the server, the
sessions and production).

## Lifecycle stages and layers

This page splits the same pipeline into layers, and [map.md](map.md) splits the layers into phases 0–10. The table maps one to the
other:

| Lifecycle stage | Layer (phases in [map.md](map.md)) | Transition artifact |
|---|---|---|
| **Requirements** | 1. Relations and 2. Preparation (phases 1–4) | a card on the board → an OpenSpec change → a task graph in the queue |
| **Development** | 3. Production: execution (phase 5) | a feature branch with a local commit |
| **Testing** | 3. Production: machine verification (phase 6); 4. Acceptance: the human check on the dev stand (phase 7) | "green" or an explicit failure; a verdict, or a return with a stated reason |
| **Release** | 4. Acceptance and release (phase 8) | a feature merged onto the dev stand and accepted; a release tag; a shipped card |
| **Monitoring** | Operation (phase 10) | metrics, alerts, a monitor verdict |
| **Support and feedback** | 5. Value and Operation, back to 1 (phases 9–10) | a client reply or an investigation report → a new card |

Above the per-project pipeline, the factory itself does three jobs. It **provisions** projects from the template and
the server with its sessions (phase 0). It **observes**: the registry, each project's drift from the template, and
the live status of each project (the Coordination layer). It **improves**: review pass → decision in `docs/` →
change in `plugins/dark-factory/templates/` → rollout ([methodology.md](methodology.md) §5).

| Job | What it does | Tooling |
|---|---|---|
| **Provision** | Creates a new project from the template. Sets up the server it runs on, so every project's sessions restart after a reboot | `/dark-factory:add base` (`deploy-base.sh`); `/dark-factory:provision-server` (`fleet.py provision`) |
| **Observe** | Keeps one registry of projects. Shows how far each project is behind the plugin release it is pinned to, plus live status: sessions, On-call login, monitor, quota, queue | `registry.md` in [your own factory](your-factory.md); the pin in each project and `harness-diff.sh`; `/dark-factory:factory-status` (`fleet.py status`) |
| **Improve** | Runs the review pass: what went wrong in a project becomes a decision in `docs/`, then a change in `plugins/dark-factory/templates/`, then a rollout back to the projects | `docs/`, `plugins/dark-factory/templates/` |

Install the plugin; do not edit it. Put your own registry, machine notes and plugin pin in a private repository of your
own: [your own factory](your-factory.md).

## Layers

| Layer | Job of the layer | Input | Output (the transition artifact) |
|---|---|---|---|
| **1. Relations** (client ↔ factory) | turn a client's problem into a commitment | raw signal: meetings, tickets, the factory's own findings | **a task in the queue** |
| **2. Preparation** (human and development session) | turn intent into something the machine can execute | a task from the queue | **a package for the machine**: spec, plan and tier |
| **3. Production** (machine) | turn the package into verified code | the package | **a branch and a hand-over** ("green" or an explicit failure) |
| **4. Acceptance and release** (human) | give a verdict and deliver | the branch and the hand-over | **the feature on the dev stand, accepted** (the mark `accepted` on its PR), or a return with a stated reason |
| **5. Value** (client) | confirm that the feature solves the client's problem, and collect feedback | the feature in production, after the release | **feedback**, the input of layer 1 |
| **Coordination** (outside the flow, but every layer depends on it) | the queue, the numbers, "who took what", infrastructure | — | — |

Rules for the boundaries:
- **Every transition is one explicit artifact.** Without one, a layer leaks into its neighbour. Typical symptoms:
  preparation lives in someone's head; a partner's acceptance is visible only in merge commits.
- **Every backward transition states its reason.** From acceptance: a code defect, a test defect or an
  understanding defect, each returned to its own layer. From value: feedback comes back as a new input, never as a
  direct edit.
- Without a working Coordination layer, both gaps G1 and G2 (below) appear.

[map.md](map.md) breaks the layers into phases 0–10. Phase 10, Operation, has its own page:
[layers/operation.md](layers/operation.md).

**Practices that cross layers** (client feedback, code analysis, observability, incident investigation) each have a
standard in base, a skill, a module and defined interfaces with their neighbours: [practices/README.md](practices/README.md).

**Functions the pipeline relies on** (the board, the execution queue, the client chat, the code host, CI, hosting, the
production data snapshot, the scheduler, the agent runtime) are contracts, not products: [functions.md](functions.md)
defines each one and names the tool the reference implementation uses.

## The path through the phases

client onboarding → **(input)** signal or ticket → intake → spec → plan and tier → execution → machine verification
→ merge onto the dev stand (main) → acceptance there (the owner's "release", or the requester's "ship?") → release of all of main from a tag → operation → **(feedback goes back to
the input)**

## Who does the work

The layers above describe work in the flow. This section says what actually does that work.

### How it runs day to day

A few long-lived Claude Code sessions run on a small Linux server you control, alongside processes that use no
model:

```
client chat ──► On-call session ──message──► development session ──► PR ──► green CI ──► main ──► release ──► deploy
     ▲                ▲                           │  runs the feature pipeline in a worktree per feature
     └──── reply ─────┤                           │  near the quota limit: saves work, schedules its own continuation
                      │ event
        production monitor (cron watchdog → read-only agent)

scheduled runs ("tonight", "every morning") booked by a session itself ──► that session or another one
```

| Part | What it is | Set up by |
|---|---|---|
| Development session | `claude remote-control` in the project's checkout; you drive it from claude.ai or the mobile app | `/dark-factory:provision-server` |
| On-call session | holds the client chat with a restricted tool set; forwards requests and posts answers back | `/dark-factory:add on-call` |
| Production monitor | a cron watchdog without a model; a read-only agent only on a real anomaly | `/dark-factory:add monitor` |
| Feature pipeline | Workflow scripts for unattended runs (a big task booked overnight), built from the plugin's roles (`tech-lead`, `reviewer`); an interactive session uses the skills and roles directly | the plugin + `feature-pipeline` module |
| Quota guard and guard hook | hooks in every session | the `dark-factory` plugin |
| Scheduled runs | native Claude Code scheduling (`send_later`, `CronCreate`, scheduled tasks); the quota guard keeps these tools open | Claude Code |

Why your own server instead of cloud sessions: the sessions need the chat channel, two-way messaging between
sessions, and local access to hosting tools, the dev stand and read-only production data.

### Who runs each layer


| Layer | Done by | Runs where | Module |
|---|---|---|---|
| 1. Relations | the On-call session: chat → acknowledgement → verbatim forward to the development session; a human turns it into a card | a persistent session on the server | `feedback-desk` |
| 2. Preparation | a human with the development session: an OpenSpec change, then the session builds the task graph in the execution queue (`openspec-to-beads`) | the development session (the owner on the web or phone) | base |
| 3. Production | the development session itself, or, for a big task left to run alone, the feature pipeline (token-expensive; one worktree per feature; the result carries an explicit `error` field, not just a status) | the development session | `feature-pipeline` |
| 4. Acceptance and release | green CI and the agent's own review, then `merge-feature.sh` or `ship` run by the session (the merge puts the feature on the dev stand); the human gates are acceptance there and the release, which refuses while a merge since the last tag lacks the `accepted` mark | the development session | base, `release-tag` |
| 5. Value | the client answers the On-call's "ship?" in the chat group, and replies after the release; the reply goes back through On-call to layer 1 | the On-call session | `feedback-desk` |
| Operation | cron watchdog → read-only monitor agent → event to On-call → the group and the development session; a scheduled daily review | cron and the On-call session | `prod-monitor` |
| Coordination | the board and the execution queue; the quota guard pauses work and the session books its own continuation | every session | base |

## Five core claims

1. **Humans at the edges, the machine in the middle.** Autonomy lives in execution and machine verification.
   Understanding the client and accepting the result are human on purpose.
2. **Four human roles**: the Product owner (the client relationship and what we promise), the Spec writer (raw
   input → something executable), the Reviewer (review and merge) and the Operator (infrastructure). One person can
   hold all of them; the roles are named so they can be handed out.
3. **The hand-over to the machine is explicit**: a spec and a tier. The machine guesses neither the scope nor the
   release number.
4. **The machine's result always states its outcome**: green, an explicit failure, or a handback with a reason. A
   failure is a managed exit, not a red build left hanging.
5. **Coordination state does not live in free-form Markdown files.** What is next lives in the queue and
   `openspec/changes/`, what shipped in the merged PRs and the release tags; a hand-kept ROADMAP file is not part of
   the method.

## Two gaps this model closes

### G1. There is no input
Without a dedicated object for "a task or intent before work starts", the pipeline effectively begins with a spec in
the owner's head. ROADMAP-style files turn into an after-the-fact log of what was done, and the list of future work
exists nowhere.

### G2. People can only work one after another
Without a coordination layer, two people cannot safely work in parallel: there is no "who took what", branch
and release names collide, coordination files cause merge conflicts, and you learn about a partner's work from merge
commits. So people take turns.

**Key observation:** agents already have this problem solved, and their mechanisms carry over to people:

| Mechanism (proven with agents) | The same for people |
|---|---|
| claiming a task in the queue (assignee scope) | a shared list of intents: "taken", visible to everyone |
| disjoint zones (`pairwiseDisjoint(files)`) | splitting work by area before starting |
| the branch name is the change key (`<type>/<ID>-<slug>`) | names and IDs issued by the tracker, one point |
| a single writer of coordination state | nobody edits coordination files by hand; they are generated |
| worktree isolation | people already have it (git branches); the gap is in the coordination layer, not in the code |
