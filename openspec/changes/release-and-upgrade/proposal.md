# One command to release, one to roll it out

## Why

A release took four commands by hand (tag, notes, `gh release`, the `release` branch), and moving a server to it took
a one-off script written for that release: the owner's pin, the marketplace, every project's checkout and plugin,
`provision`, restarts. Each release added another script to the owner's home directory.

## What changes

- **`scripts/release.sh v<N>`** (the canon, the owner runs it; the guard is unchanged). It refuses unless origin/main
  is `<N>.0.0`, the tag is new and `v<N-1>` exists. It prints the notes and, on "y", tags, pushes, creates the GitHub
  release with the notes and moves `release`.
- **`fleet.py upgrade v<N> [--dry-run]`** (the plugin). It refuses a tag the repository does not have. Then:
  1. the owner's pin in `~/.claude/settings.json` and the marketplace move to the tag;
  2. each project's main checkout goes onto origin's default branch, by the stand updater's rules, and its plugin is
     updated; a project that still pins an older release is named;
  3. `provision` runs from the new plugin, and `df-fleet-serve` restarts;
  4. the sessions and On-calls restart only on the owner's "y". Without a terminal, it prints the command.

## Not in this change

- Projects following the `release` branch instead of a tag (owner: no).
- Opening the projects' pin PRs: `/dark-factory:upgrade` in each project still does that.

## Acceptance scenarios

- WHEN origin/main is not `<N>.0.0` THEN `release.sh v<N>` stops before anything is changed; WHEN the owner does not
  answer "y" THEN nothing is tagged.
- WHEN `fleet.py upgrade v<N>` runs for a tag that does not exist THEN nothing changes.
- WHEN it runs for a released tag THEN the pin is `v<N>` with the rest of the settings kept, and the units come from
  the `<N>.0.0` plugin; the sessions keep running unless the owner said "y".
- WHEN `--dry-run` is given THEN it prints the commands and changes nothing.
