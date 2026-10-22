---
name: size-task
description: >
  The tech lead's first step when a new piece of work starts — a request like "add", "fix", "make",
  "change", a new ask from the owner or a customer, before any code or spec. Reads the request and the
  code, answers in one line how big the work is (trivial / small / large) for the owner's ok, and
  proposes the branch type, slug, tracker ID and end-to-end phases. Use at the start of every new task.
---

# Skill `size-task` — how big is this, and how do we name it

> Canonical template (templates/base). Needs no configuration.

> **Seam:** the tracker ID. One pattern recognises it in a branch name, and the same pattern is in
> `scripts/merge-feature.sh` (`TRACKER_ID_RE`). **To swap the tracker, change this pattern in both places:**
> `[A-Z][A-Z0-9]+-[0-9]+|[0-9]+` (default: Linear/Jira style `DMP-123`, or a GitHub issue number `123`).

You are the tech lead. Before any code, size the work and agree it with the owner in one line. No code,
no branch, no spec until the owner says ok.

## Steps

1. **Read** the request (and the tracker card, if there is one) and the code it touches: entry points,
   tests, `ROADMAP.md`, open PRs and `openspec/changes/` for overlap. Surfaces of a user-visible
   feature are asked first (`CLAUDE.md` rule 7).
2. **Verdict**, one line, with the reason:

   | Verdict | When | What exists |
   |---|---|---|
   | `trivial` | one clear spot, no contract change, nothing to decide: a typo, a string, a one-line fix, a config value | no spec: a branch and a PR |
   | `small` | one behaviour or a few, within the existing model and API | `openspec/changes/<slug>/` with a short `proposal.md` (including WHEN/THEN acceptance scenarios) and `tasks.md` |
   | `large` | the data model, an API contract or a user flow changes, or a ROADMAP milestone ships | the same plus `design.md`: the delta and the transition tree |

3. **Propose**, in the same message:
   - **type**: `feat | fix | ui | refactor | chore | docs`;
   - **slug**: lowercase words with hyphens, unique — taken if `openspec/changes/<slug>/` exists (check it);
   - **tracker ID**, if the work has a card (`DMP-123`; GitHub Issues: the number, and `Fixes #123` goes in the PR);
   - **branch**: `<type>/<ID>-<slug>` with a tracker, `<type>/<slug>` without (`feat/DMP-123-voice-input`);
     the PR title carries the ID so the tracker links the PR and moves the card;
   - **phases** for `small` and `large` when there is more than one: each phase works **end to end**,
     from the entry point (webhook, route, command) to the result, and has an entry-level test. Never
     slice by layers ("data", then "API", then "UI"). Each phase is its own branch and PR: its own
     sub-card with its own ID (preferred), or `-p<K>` after the slug when there is no tracker.
4. **Wait for the owner's ok.** A change of verdict, name or phases is cheap now and expensive after the
   first commit.
5. After the ok: `trivial` — branch and PR. `small`/`large` — write `openspec/changes/<slug>/` with the
   `openspec` skill (superpowers skills such as brainstorming and writing-plans may help, but they write
   into that folder), then `openspec-to-beads` for the queue.

## Output shape

```
Verdict: small — one behaviour in the existing bot flow, no model change.
Name: feat/DMP-123-voice-input (slug voice-input, tracker DMP-123)
Phases: 1) voice message → transcript reply, 2) length limit and error reply (sub-cards DMP-124, DMP-125)
Ok?
```

## Don'ts

- Don't start code, a branch or a folder before the ok.
- Don't inflate: a typo is `trivial`; a spec for it is waste.
- Don't deflate: a changed contract is `large` even if the diff is small.
- Don't reuse a taken slug or the name of an older change folder.
