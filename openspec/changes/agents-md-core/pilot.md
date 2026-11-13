# Pilot — a live project moved to the AGENTS.md layout

2026-11-13, a Linux server. A private project on the base template (plugin pinned to v18, the v23-era layout:
`CLAUDE.md` importing `.claude/canon/CLAUDE.md`, 10 project skills including a module's `feedback-desk`, the two
header scripts filled in). Done in a throwaway clone of its repository on a branch: nothing pushed, nothing merged,
the project's checkout, its development session and its stand untouched. The agents ran with their own config
directories and no dark-factory plugin installed.

## Migration (`migrate_agents_md.py`)

- Dry run: the full plan — `AGENTS.md` from `CLAUDE.md` with the canon block where the import was, `CLAUDE.md` →
  `@AGENTS.md`, the old canon file removed, 10 skills moved behind the `.claude/skills` link, the header scripts moved,
  `session-start.sh` added, and the `.claude/settings.json` SessionStart change printed for the permission dialog.
- The project's own `CLAUDE.md` intro (Russian, from an older template) was not the v23 text: the script left it and
  named it for the owner, as designed. Reworded by hand.
- The project's SessionStart held only the three old commands — nothing of its own was lost.
- After `--apply` and the settings edit: a second run says "nothing to do"; the canon block is current; git sees 13
  renames; the project's sections (its rules, principles, constraints, maintenance) are all outside the block; the new
  header runs.
- `AGENTS.md` came out at 27,936 bytes — under Codex's 32 KiB but close: the project's own part is about 8 KB of
  Russian text. **Fixed in the branch:** `canon_block.py check` and the migration now say so past 28 KiB.

## Agents on the migrated project

| Question | Claude Code | Codex 0.169 |
|---|---|---|
| May the project go into the factory registry or onto the board? (the project's own section) | No — private, outside the factory | No — private; links `AGENTS.md` |
| The project's skills | all 10, `feedback-desk` included | the same 10, plus Codex's system skills |
| How to merge a work branch into main (the canon) | `scripts/merge-feature.sh <branch> [title]`; a bare `gh pr merge` is denied | `scripts/merge-feature.sh <branch> "<PR title>"` |

Both agents read the project's own rules and the canon from `AGENTS.md`, and the same project skills.

## Not covered by this pilot

- The upgrade across releases (v18 → v24 with each release's notes and `copier update`): the pilot moved the layout
  only. That run belongs to `/dark-factory:upgrade` once v24 is released.
- Projects whose `AGENTS.md` already has text of its own (two on this server): the migration stops there by design;
  each needs the owner's merge of the two texts.
