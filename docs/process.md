# Factory process — one page

> This page is the top-level model of the process.
> The detailed map with phases and edges is [map.md](map.md) (an appendix to this document).

## Layers (top level)

| Layer | Job of the layer | Input | Output (= transition artifact) |
|---|---|---|---|
| **1. Relations** (client ↔ factory) | turn pain into a commitment | raw signal: meetings, tickets, factory findings | **a task in the queue** |
| **2. Preparation** (human + co-pilot) | turn intent into something the machine can execute | a task from the queue | **a package for the machine**: spec + plan + tier |
| **3. Production** (machine) | turn the package into verified code | package | **branch + handoff** ("green" or an honest fail) |
| **4. Acceptance and release** (human) | verdict and delivery | branch + handoff | **feature on the stand** (or a typed return downstream) |
| **5. Value** (client) | confirm the hit, harvest feedback | feature on the stand | **acceptance + feedback** → input of layer 1 |
| **Coordination** (load-bearing, outside the flow) | queue, numbers, "who took what", infrastructure | — | — |

Boundary properties:
- **Every transition is one explicit artifact.** Without an artifact a layer "leaks" into its neighbour (typical symptoms: preparation lives in someone's head, a partner's acceptance is visible only in merge commits).
- **Backward transitions are typed only**: from acceptance — code defect / test defect / understanding defect (each to its own layer); from value — feedback as a new input, never a direct edit.
- The absence of a load-bearing Coordination layer produces both gaps G1/G2 (below).

Layers broken into phases (0–10) — [map.md](map.md). Phase 10 "Operation" — [layers/operation.md](layers/operation.md).

**Practices across layers** — client feedback, code analysis, observability, incident investigation: a standard in base + a skill + a module + joints — [practices/README.md](practices/README.md).

## The path (phases within layers)

client onboarding → **(input)** signal/ticket → intake → spec → plan+tier → execution → machine verification → human acceptance → release to the stand → client acceptance → operation → **(feedback — back to the input)**

## Five load-bearing claims

1. **Humans at the edges, the machine in the middle.** Autonomy lives in execution and machine verification; understanding the client and acceptance are human on purpose.
2. **Four human roles**: Producer (client, promises), Technologist (raw input → executable), Acceptor (review, merge), Operator (infrastructure). One person can hold all of them; the roles are named so they can be handed out.
3. **Hand-over to the machine is explicit**: spec + tier. The machine guesses neither scope nor release number.
4. **Return from the machine is typed**: green / honest fail / handback with a reason; failure is a managed exit, not something "hanging red".
5. **Coordination state does not live in free-form md files.** ROADMAP and the like are reports generated from the queue, not the place where tasks are kept.

## Two gaps this frame closes

### G1. There is no input
Without a dedicated object "task/intent before work starts", the line effectively begins with a spec in the owner's head; ROADMAP-style files degrade into a post-factum log of what was done, and the list of future work exists nowhere.

### G2. People can only work sequentially — and that is bad
Parallel work by two people is structurally unsafe without a coordination layer: there is no "who took what", release numbers `r{N}` collide, coordination files produce merge conflicts, and you learn about a partner's work from merge commits. Hence serialisation.

**Key observation:** for agents this problem is already solved. The agent parallelism mechanisms transfer to people:

| Mechanism (proven on agents) | Transfer to people |
|---|---|
| claiming a task in the queue (assignee scope) | a shared list of intents, "taken — visible to everyone" |
| disjoint zones (`pairwiseDisjoint(files)`) | splitting work by area before starting |
| single source of truth for the train number (CURRENT_TRAIN, incremented by one party) | release numbers/names issued by a single point |
| a single writer of coordination state | nobody edits coordination files by hand — they are generated |
| worktree isolation | people already have it (git branches) — the gap is not in code but in the coordination layer |
