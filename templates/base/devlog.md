# <Project> — Devlog

> Session-by-session progress log. Goal: recover context within 30 seconds when returning to the project.
> **New entries go on top** (reverse chronological order).

## Rules (mandatory)

Mirrors the SESSION LOOP from [CLAUDE.md](CLAUDE.md).

**Opening a session:**
- Before any action, read the **latest entry** below — the `Open questions` and `Next session` blocks give an explicit continuation point
- If the open questions conflict with the user's request, raise it before work starts

**Closing a session:**
- Add a new entry **on top** using the template (see the HTML comment at the end of the file)
- The entry is mandatory. Without it the session is not considered finished (part of `verification-before-completion`); enforced by the pre-push hook
- File the session's open questions in bd immediately (otherwise they are invisible in `bd ready` — a proven gap)
- If something release-level shipped, also update `ROADMAP.md` and/or create `openspec/changes/r{N}-{name}/SHIPPED.md`
- Secrets (stand passwords, tokens, account details) never go into the devlog — git history does not forget them

---

## <YYYY-MM-DD> — Project deployed from the factory template

### Done
- [x] Project deployed from dark-factory `templates/base/` (see the factory registry)

### Next session
- <first steps of the project>

---

<!--
ENTRY TEMPLATE (copy as a whole, insert ON TOP under the "Rules" heading)

## YYYY-MM-DD — short title (one line describing the session)

### Done
- [x] concrete action 1

### Decisions
- Chose X over Y — because Z. Architectural → also an ADR

### Checks
- pytest N passed (revision abc1234) · ruff clean · e2e N (if run) · pyramid unit X % — numbers, not "all green"

### Delivery status
- committed / pushed / PR #N opened / merged / deployed to the stand (smoke: …) — exactly where we stopped

### Open questions
- [ ] what is unresolved / blocked / needed from the user (and file it in bd!)

### Next session
- A concrete first step when returning (not "continue work" but "open file X, finish Y per tasks.md phase N")

### Harness changes (if any)
- ROADMAP.md — status of rN changed
- openspec/changes/rN-name/SHIPPED.md — created

---
-->
