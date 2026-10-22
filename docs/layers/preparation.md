# The Preparation layer

> **Stages:** the second half of Requirements (phases 3–4 of [map.md](../map.md): discovery, spec, plan and tier).
> Layer 2 of [process.md](../process.md): "turn intent into something the machine can execute". Input: a ticket
> from the board. Output: a package for the machine. Same format as [intake.md](intake.md).

## Typical state

- How long preparation takes depends on the task; there is no single answer:
  - simple tasks go to an agent straight away;
  - when someone already has the setup in their head, it takes about 15 minutes to type up the assignment;
  - broad or unexplored tasks need iterative work with the agent. A typical failure: a whole day of attempts because
    the constraints of the domain model were not visible. The breakthrough comes from going back to basics and
    spelling out what the user actually does, step by step.
- The result of expensive preparation ends up **in specs at the project level**, which is where it belongs.
- The input to the process is tickets on the board, usually high-level ("add user documentation", "do load
  testing").
- Nobody knows in advance whether the full set of preparation documents is actually used further down the line; it
  has to be measured.

## Decisions

1. **The essence before the details.** Iterative work starts from a high-level "what we want, and what the user does
   step by step"; details come only once the essence is settled. Agents tend to dive into details early, and a lost
   day is the typical price.
2. **Specs live in the project repository; the board holds a pointer.** A card is an umbrella, and the details sit
   behind a link to the spec (a rule of the `board` skill, confirmed from this side).
3. **A package = spec + plan + clearance.** The "tier" from [process.md](../process.md) is refined and split into
   two dimensions:
   - *how much preparation is needed*: a property of the preparation process, not part of the package;
   - *clearance*: the risk class in the package, which sets the maximum allowed autonomy and the mandatory gates.
     **The executor chooses the execution mode** (attended in a session, or unattended and booked for later) within
     the clearance: a well-prepared task may still run attended, and a task whose clearance does not allow
     unattended work is not booked for later.
4. **Preparation is pair work, a human with an agent.** The agent does not need its own identity on the board for
   this. Keep three agent roles apart: preparation in the development session (exists); note triage (a candidate:
   the tracker's catalogue agents); an executor that claims tasks (gated by the autonomy ladder).
5. **Do not cut the document set blindly; measure.** Add this to the review pass: which package artifacts the
   executing agents actually read (from session logs). An artifact nobody opens for N releases is a candidate for
   removal from the template. Cut based on data.
6. **There is no simple, explicit classification of routes.** The way to prepare a ticket is neither computed from
   it nor picked from a closed menu. It comes from **talking with a human, using a vocabulary of commands** ("work
   out the idea at a high level", "work out the implementation", "make a first version, show the forks", …). The
   human says it and the agent must be able to carry out the command; the card records the command **verbatim**,
   not as a route code.
7. **Preparation ends with an explicit human confirmation** ("ready, send it"). The one exception is an explicit "do
   it yourself" when the ticket is taken: that is a confirmation given in advance, and the agent completes the
   package and goes into execution without asking again. Silence, the existence of artifacts, or "I think we
   discussed everything" are not confirmations. This is how the rule "the hand-over to the machine is explicit"
   from [process.md](../process.md) works in practice: the human's word is the hand-over.

## The preparation command vocabulary (an open list, not a classification)

The first step of preparation: whoever took the ticket tells the agent what to do. There are four commands, in
decreasing order of human involvement. They are a scale of "how much of me goes into the preparation", chosen in the
moment, not a classification of the ticket:

| Command | What the agent does | Output |
|---|---|---|
| "work out the idea at a high level" | a pair session, the essence before details: what we want, what the user does step by step; stays out of the implementation | the agreed essence |
| "work out the implementation" | works on its own from the essence until it reaches the forks; the first artifact (a draft spec or a first prototype) depends on the task | the forks, for the human |
| "research and report" | a spike or a comparison; the report is accepted as a whole or part by part (that is a way of accepting, not a separate command) | a report; the decision stays with the human |
| "do it yourself" | full delegation, with confirmation given in advance (decision 7) | the package → straight into execution |

"Postpone until X" is not a preparation command. It is a coordination action (a blocked comment with a condition for
coming back, plus a link) and follows the board's rules.

The list grows as real commands are observed. Commands that stop changing become skills in the template, the same way
stable skill steps become scripts (see the deploy-project row in [open-questions.md](../open-questions.md) §2).

## Open questions

- **Layer design**: how commands turn into artifacts and skills, and which command becomes a template skill first
  (candidate: "a draft spec with forks" for commands 1 and 2).
- **Clearance**: the scale and the class names (lite, core or something else) are decided in the Production layer
  ([production.md](production.md)).
- **Measuring artifact usage** (decision 5): the mechanics (which logs, how to count) are set at the first review
  pass.
- The harness and the project code may live in separate repositories; check how that affects the package (where
  the spec goes when there are two repositories).
