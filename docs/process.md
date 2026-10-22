# The factory process on one page

> This page is the top-level model of the process. The detailed map, with phases and transitions, is
> [map.md](map.md), an appendix to this page.

## Lifecycle stages and layers

The [README](../README.md) describes the line in six lifecycle stages; those are the primary vocabulary. This page
splits the same line into layers, and [map.md](map.md) splits the layers into phases 0–10. The table maps one to the
other:

| Lifecycle stage | Layer (phases in [map.md](map.md)) | Transition artifact |
|---|---|---|
| **Requirements** | 1. Relations and 2. Preparation (phases 1–4) | a card on the board → an OpenSpec change → a task graph in the queue |
| **Development** | 3. Production: execution (phase 5) | a feature branch with a local commit |
| **Testing** | 3. Production: machine verification (phase 6); 4. Acceptance: the human check in the preview environment (phase 7) | "green" or an explicit failure; a verdict, or a return with a stated reason |
| **Release** | 4. Acceptance and release (phase 8) | a feature merged and in the preview environment; a shipped card |
| **Monitoring** | Operation (phase 10) | metrics, alerts, a monitor verdict |
| **Support and feedback** | 5. Value and Operation, back to 1 (phases 9–10) | a client reply or an investigation report → a new card |

Above the per-project line, the factory itself does three jobs. It **provisions** projects from the template and
the server with its sessions (phase 0). It **observes**: the registry, each project's drift from the template, and
the live status of each project (the Coordination layer). It **improves**: review pass → decision in `docs/` →
change in `templates/` → rollout ([methodology.md](methodology.md) §5).

## Layers

| Layer | Job of the layer | Input | Output (the transition artifact) |
|---|---|---|---|
| **1. Relations** (client ↔ factory) | turn a client's problem into a commitment | raw signal: meetings, tickets, the factory's own findings | **a task in the queue** |
| **2. Preparation** (human and development session) | turn intent into something the machine can execute | a task from the queue | **a package for the machine**: spec, plan and tier |
| **3. Production** (machine) | turn the package into verified code | the package | **a branch and a hand-over** ("green" or an explicit failure) |
| **4. Acceptance and release** (human) | give a verdict and deliver | the branch and the hand-over | **the feature in the preview environment**, or a return with a stated reason |
| **5. Value** (client) | confirm that the feature solves the client's problem, and collect feedback | the feature in the preview environment | **acceptance and feedback**, the input of layer 1 |
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

**Functions the line relies on** (the board, the execution queue, the client chat, the code host, CI, hosting, the
production data snapshot, the scheduler, the agent runtime) are contracts, not products: [functions.md](functions.md)
defines each one and names the tool the reference implementation uses.

## The path through the phases

client onboarding → **(input)** signal or ticket → intake → spec → plan and tier → execution → machine verification
→ human acceptance → release to the preview environment → client acceptance → operation → **(feedback goes back to
the input)**

## Who runs each layer

The layers above describe work in the flow. This table says what actually does that work (see "How it runs day to
day" in the [README](../README.md#how-it-runs-day-to-day)).

| Layer | Done by | Runs where | Module |
|---|---|---|---|
| 1. Relations | the On-call session: chat → acknowledgement → verbatim forward to the development session; a human turns it into a card | a persistent session on the server | `feedback-desk` |
| 2. Preparation | a human with the development session: an OpenSpec change, then the session builds the task graph in the execution queue (`openspec-to-beads`) | the development session (the owner on the web or phone) | base |
| 3. Production | the feature pipeline inside the development session, one worktree per feature; the result carries an explicit `error` field, not just a status | the development session | `feature-pipeline` |
| 4. Acceptance and release | a human verdict, then `merge-feature.sh --accepted-by "<name>"` or `ship` run by the session | the development session | base, `release-tag` |
| 5. Value | the client replies in the chat group; the reply goes back through On-call to layer 1 | the On-call session | `feedback-desk` |
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
5. **Coordination state does not live in free-form Markdown files.** ROADMAP and similar files are reports generated
   from the queue, not the place where tasks are kept.

## Two gaps this model closes

### G1. There is no input
Without a dedicated object for "a task or intent before work starts", the line effectively begins with a spec in
the owner's head. ROADMAP-style files turn into an after-the-fact log of what was done, and the list of future work
exists nowhere.

### G2. People can only work one after another
Without a coordination layer, two people cannot safely work in parallel: there is no "who took what", release
numbers `r{N}` collide, coordination files cause merge conflicts, and you learn about a partner's work from merge
commits. So people take turns.

**Key observation:** agents already have this problem solved, and their mechanisms carry over to people:

| Mechanism (proven with agents) | The same for people |
|---|---|
| claiming a task in the queue (assignee scope) | a shared list of intents: "taken", visible to everyone |
| disjoint zones (`pairwiseDisjoint(files)`) | splitting work by area before starting |
| the train number lives in one file (`CURRENT_TRAIN`) and only one party increments it | release numbers and names issued from a single point |
| a single writer of coordination state | nobody edits coordination files by hand; they are generated |
| worktree isolation | people already have it (git branches); the gap is in the coordination layer, not in the code |
