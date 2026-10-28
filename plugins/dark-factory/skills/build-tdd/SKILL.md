---
name: build-tdd
description: >
  Build one planned slice by TDD — failing test first, then the code, then the refactor — following the project's
  standards and touching only the slice's files. Use when a planned slice or a bd subtask with FILES and TESTS is
  next ("build 3.2", "implement this subtask"), and as the rules of the feature pipeline's implementers.
  Next: integrate.
---

# Skill `build-tdd` — one slice, test first

> Part of the dark-factory plugin. The method is the Superpowers `test-driven-development` skill (use it when it is
> installed); this skill adds what is specific to the factory.

## Steps

1. **Read the slice:** `bd show <id>` — its FILES, TESTS, ACCEPTANCE and any critic remarks — and the source it
   belongs to (the OpenSpec change, the spec).
2. **Read the standards in full:** the project `CLAUDE.md` (with its list of known anti-patterns, if it has one) and
   `CODING_STANDARDS.md` (rule map by layer, general prohibitions, test pyramid, project language: layer
   responsibilities, where prompts, SQL, secrets and user-facing texts live, the language of logs, typed exceptions),
   and `naming.yaml` (the project map and glossary). Any user-facing text goes only through the project's message
   catalog.
3. **Read the actual code** around the slice: neighbouring modules, existing repositories, services, settings. Follow
   the neighbouring files; reuse what exists instead of writing a second one. Before a new component, style rule,
   helper or query, search for one with the same role (`grep` by class, function and key names) and extend it; a copy
   of an existing rule under a new name is the commonest review finding.
4. **RED → GREEN → REFACTOR.** A failing test first, then the code that makes it pass, then the refactor. Tests by the
   slice's TESTS, or, without one, happy, edge and error paths at the right pyramid level: unit for logic, service
   level with the boundaries mocked, db tests (`@pytest.mark.db`) only for a new hot path with a real database —
   written following their neighbours even when this machine cannot run them (CI does).
5. **Run only the slice's tests** as you go (`pytest <abs path of the test file> -q`). The full suite is
   `integrate`'s job.
6. **Stay in the slice's files.** A new file only next to them (the same package or test folder). Migrations only
   when the spec allows them: a revision following its neighbours, up and down both written; otherwise the slice
   stops as failed with the reason.
7. **Forks** not covered by the spec — KISS/YAGNI, and write each one down as an assumption: it goes into the PR
   description's `## Decisions`.
8. **Report:** files changed, test files, tests added, assumptions, and the status — done, partial (what is left),
   or failed (the missing precondition).

Comments and test descriptions are in the project language. Next: **`integrate`** — in a session right after each
slice; in a parallel wave the run's integrator does it for the whole wave.
