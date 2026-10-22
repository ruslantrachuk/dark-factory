# <project> — Documentation standard

> Project documents are read by **people** (users and developers) and by AI. They must be
> clear, consistent and easy to scan. This guide sets a single bar for
> every `*.md` in the repository. At deployment, fill in the "Where we keep it" table, the roles
> in §6 and the tone examples in §3 for the project's domain.

## 1. Principle: one document — one job (Diátaxis)

Each document answers **one** type of question. Do not mix "how to do it" and "why it is so".

| Type | Reader's question | Where we keep it |
|-----|-----------------|-----------|
| **How-to / Tutorial** | "how do I do this?" | `README.md`, <`docs/user-guide/`, …> |
| **Explanation** | "how does it work and why?" | `ARCHITECTURE.md`, `docs/decisions/adr/`, <…> |
| **Reference** | "what are the exact facts and contracts?" | `CODING_STANDARDS.md`, `docs/standards/`, <`naming.yaml`, …> |
| **Status** | "what is done and what is next?" | `ROADMAP.md`, `openspec/changes/*/SHIPPED.md`, the PR descriptions (`git log --merges` of the main branch) |

**Consequence:** the README is short (run it + where to go next). Do not duplicate the same thing in
two places — link to it.

## 2. Document structure

- **One H1 per file**, at the top.
- **Purpose in the first lines** — one or two sentences "what it is and for whom", or a `TL;DR`.
  The reader knows within 5 seconds whether they are in the right place.
- **Heading hierarchy without gaps:** H1 → H2 → H3, never skip a level.
- **Short sections** with meaningful names. Longer than a screen — split it.
- **Long docs** (> ~150 lines) start with a table of contents or a map table.

## 3. Tone and text

- **Active voice, present tense:** "the service builds the report", not "the report will be built".
- **Concise.** Remove filler ("it should be noted that…"). One thought — one sentence.
- **Real prose, not clipped notes.** Write connected sentences, not fragments joined by dashes.
  - ⛔ "Export — cron, fetched, done."
  - ✅ "When the nightly export finishes, the dashboard switches to the fresh data — the timestamp in the header updates automatically."
  - <replace a couple of examples with the project's domain>
- **Form of address:** informal and direct to the developer (technical docs); polite and direct to the user (in the user guide).
- **No unexplained jargon.** Expand an abbreviation on first use
  (except well-known ones from the project glossary).

## 4. Formatting (Markdown)

- **Callouts — GitHub Alerts**, uniformly:
  ```markdown
  > [!NOTE] neutral context
  > [!IMPORTANT] something that must not be missed
  > [!TIP] advice / shortcut
  > [!WARNING] risk / breaking behaviour
  ```
- **Code in fenced blocks with a language** (` ```bash `, ` ```python `). Commands are copy-pasted as is.
- **Tables for comparisons and "parameter → value"**, not for prose.
- **Links are relative and clickable:** `[ARCHITECTURE.md](ARCHITECTURE.md)`. No bare paths in the text.
- **Lists** for enumerations; numbered ones only for sequential steps.

## 5. Honesty and freshness

- **"How it is now" and "where we are going" are clearly separated.** README and the user guide describe what
  works; goals live in specs, ADRs and the ROADMAP.
- **No links to non-existent files.** Check paths before committing
  (with the project's script, if there is one).
- **Numbers and facts come from the code**, not from memory (number of tests, screens, versions).
- **Dates are absolute** (`2026-08-26`), not "yesterday".

## 6. User guide (a feature gate, not "later")

This section applies to projects with a user UI (flag "user guide: yes" at deployment); a bot, a library or a project with its own help packaging marks "no", and has no `docs/user-guide/` folder.

The guide is read by **<the project's user roles>**. It lives in `docs/user-guide/`:
`README.md` — the index, task pages, `images/` — screenshots, `screenshot-manifest.json` —
screenshot hashes and the data policy. A feature that changes the UI or user behaviour is not closed
without updating the guide (CLAUDE.md, GATE step 3 and "Finishing a feature").

- **The user's language, not the developer's.** Terms come from the project glossary, in the project language.
  No routes, database tables, service names.
- **One document — one user task:** "How to sign in", "How to build a report".
  The heading is the task. A numeric prefix in the file name sets the order in the index.
- **Every screen has a screenshot.** Screenshots are taken by the script `python -m tests.e2e.make_screenshots`
  against the e2e preview, never by hand. When the screen changes, rerun the script: the hash in the manifest
  changes, and the meta-test `tests/unit/test_user_guide.py` forces an update.
- **Data in screenshots is only synthetic or masked** (`data_policy` in the manifest).
  Real client names, account details or amounts never appear in a screenshot.
- **Every page is in the index** `README.md`, otherwise nobody finds it; links — `scripts/check_doc_links.py`.
- **Address the user politely.** Steps as a numbered list, important points in a callout.

## 7. Checklist before committing a doc

- [ ] One H1, purpose visible in the first lines
- [ ] No skipped heading levels
- [ ] Code in blocks with a language, commands work
- [ ] Links are relative and point to existing files
- [ ] "Now" is not confused with "goal"
- [ ] Facts and numbers checked against the code
- [ ] User guide: the user's language, one document — one task, page in the index
- [ ] User guide: screenshots taken by the script, manifest updated, data synthetic

## Related documents

- [CODING_STANDARDS.md](CODING_STANDARDS.md) — code rules (including the project language)
