# The Value layer — understanding

> Layer 5 of [process.md](../process.md): input — a feature on the stand, output — client acceptance + feedback → input of layer 1.

## Typical state

Everything happens on calls; delivery is in releases/waves. The problem "the client did not notice what was shipped" usually does not arise: on the call there is either an "ok" or a comment asking for rework.

## Decisions

1. **The layer lives on calls; nothing new is built.** The feedback loop is closed by what exists: call → `transcript-intake` (diff, draft cards); rework from a call is an ordinary feature through intake, not a special path.
2. **Client acceptance happens in the client's tracker.** The ship transaction moves the client's ticket (Done / "to verify"), and the client closes it themselves — their closing is the confirmation. Our board does not duplicate someone else's bookkeeping: no status after Shipped (Accepted); the condition for return is a project where "nobody noticed what was shipped" becomes a pain. Client tickets left hanging open are an agenda item for the call.
