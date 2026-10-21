# The Preparation layer — understanding

> Format — as in [intake.md](intake.md).
> Layer 2 of the [process.md](../process.md) frame: "turn intent into something the machine can execute"; input — a ticket from the board, output — a package for the machine.

## Typical state

- Preparation time depends on the task; there is no straight answer to "how long":
  - simple tasks are delegated to an agent right away;
  - when the setup is already in someone's head — about 15 minutes to type up the assignment;
  - general/unexplored tasks — iterative work with the agent. A typical failure mode: a whole day of attempts because the constraints of the domain model were not visible; the breakthrough comes from returning to the essence and spelling out "what the user actually does, step by step".
- The result of expensive preparation settles **in specs at the project level** — and that is right.
- The process input is tickets on the board, most often high-level ("add user documentation", "do load testing").
- Whether the full set of preparation documents is actually used further down the line is not known in advance — it has to be measured.

## Layer decisions

1. **Essence before details.** Iterative work starts from a high-level "what we want / what the user does step by step"; details only after the essence is fixed. (Agents tend to dive into details early — a day lost to that is a typical price.)
2. **Specs live in the project repo; the board is a pointer.** A card = an umbrella, the details are behind a link to the spec (the `board` skill's rule, confirmed from this side).
3. **Package = spec + plan + clearance.** The frame's "tier" is refined and split into two dimensions:
   - *how much preparation is needed* — a property of the preparation process, not part of the package;
   - *clearance* — the risk class in the package: the maximum allowed autonomy and the mandatory gates. **The execution mode (attended in the session / unattended, booked for later) is the executor's choice** within the clearance: a well-prepared task may also run attended; a task whose clearance does not allow unattended work is not booked for later.
4. **Preparation is pair work, human + agent.** The agent does not need its own identity on the board for this. Do not mix three agent roles: preparation in the development session (exists) / note triage (candidate — the tracker's catalogue agents) / an executor with a claim (gated by the autonomy ladder).
5. **Do not cut the document set blindly — measure.** Into the review-pass loop: which package artifacts the executing agents actually read (from session logs); not opened for N releases — a candidate for removal from the template. Cut by data.
6. **There is no simple explicit classification of routes.** The way of preparing is neither computed from the ticket nor picked from a closed menu — there is **interaction with a human and a command vocabulary** ("work out the idea at a high level", "work out the implementation", "make a first version, show the forks", …). The human says it — the agent must be able to execute the command; on the card the command is recorded **verbatim**, not as a route code.
7. **The output of preparation is an explicit human confirmation** ("ready, send it"). One exception: an explicit "do it yourself" when taking the ticket — a confirmation given in advance; the agent then completes the package and goes into execution without a second touch. Silence, the existence of artifacts, "I think we discussed everything" are not confirmations. (The joint with the frame's "hand-over to the machine is explicit": the human's word does the hand-over.)

## Preparation command vocabulary (an open list, not a classification)

The first step of preparation: whoever took the ticket tells the agent what to do. Four commands, in decreasing order of human involvement — a scale of "how much of me is in the preparation", chosen in the moment, not a classification of the ticket:

| Command | What the agent does | Output |
|---|---|---|
| "work out the idea at a high level" | a pair session, essence before details: what we want, what the user does step by step; stay out of implementation | the fixed essence |
| "work out the implementation" | from the essence — on its own up to the forks; the form of the first artifact (a draft spec / a first prototype version) depends on the nature of the task | forks for the human |
| "research and report" | a spike / a comparative layout; the report is accepted as a whole or by zones (an acceptance mode, not a separate command) | a report; the decision stays with the human |
| "do it yourself" | full delegation; confirmation given in advance (decision 7) | package → straight into execution |

Not a preparation command: "postpone until X" is a coordination action (a blocked comment with a return condition + a link) and lives in the board's rules.

The list grows as real commands are observed; settled commands sediment into skills in the template (the same logic as "the skill is the frontier, the script is the sediment").

## Open ends

- **Layer design**: how routes turn into artifacts/skills — which command becomes a template skill first (candidate: "a draft spec with forks" for commands 1/2).
- **Clearance**: the scale and the class names (lite/core or otherwise) — decided in the Production layer ([production.md](production.md)).
- **Measuring artifact usage** (decision 5): the mechanics — which logs, how to count — set at the first review pass.
- The harness and the project code may live in separate repos — check how that affects the package (where the spec goes when there are two repos).
