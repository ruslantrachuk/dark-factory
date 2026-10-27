# Tasks: one command to release, one to roll it out

Spec: `proposal.md` in this directory.

- [x] **1. `scripts/release.sh`.** Checks (version on origin/main, tag new, previous exists), notes, "y", tag + push,
  `gh release`, `release` branch. Checked by hand: a wrong version, a bad argument and no answer each stop before
  the tag.
- [x] **2. `fleet.py upgrade`.** `pin_of`, `set_pin`, `move_checkout`, `upgrade`; `--dry-run`. Tests: bad or missing
  tag, pin moved with other settings kept, step order with the new plugin's `provision`, sessions only on "y" and
  never without a terminal, dry run changes nothing, older project pin named, missing new plugin stops.
- [x] **3. Docs.** CONTRIBUTING "Versioning", the `provision-server` skill, the `fleet.py` usage.
