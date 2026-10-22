# The Value layer

> **Stages:** Support and feedback (phase 9 of [map.md](../map.md): client acceptance).
> Layer 5 of [process.md](../process.md). Input: the feature accepted on the dev stand and released to production. Output: feedback, which become the input of layer 1.

## Typical state

Everything happens on calls, and delivery comes in releases or waves. The problem "the client did not notice what
was shipped" usually does not come up: on the call there is either an "ok" or a request for rework.

## Decisions

1. **The layer lives on calls; nothing new is built.** The feedback loop is closed with what exists: call →
   `transcript-intake` (the difference against the board, draft cards). Rework from a call is an ordinary feature
   that goes through intake, not a special path.
2. **Client acceptance happens in the client's tracker.** The ship transaction moves the client's ticket (to Done or
   "to verify"), and the client closes it; their closing is the confirmation. Our board does not duplicate someone
   else's bookkeeping, so there is no status after Shipped (such as Accepted). The condition for revisiting this: a
   project where "nobody noticed what was shipped" becomes a real pain. Client tickets left open are an agenda item
   for the next call.
