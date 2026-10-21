# Third-party notices

This repository includes material adapted from the projects below. Each keeps its own license;
the license text travels with the copied files.

| Component | Path in this repo | Upstream | License |
|---|---|---|---|
| OpenSpec spec-driven schema and artifact templates | `templates/base/.claude/skills/openspec/schemas/` | [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | MIT, © 2024 OpenSpec Contributors — [LICENSE](templates/base/.claude/skills/openspec/schemas/LICENSE) |
| OpenSpec documentation (fetched at deploy time, not stored here) | `.claude/skills/openspec/docs/` in a deployed project, via `templates/base/scripts/fetch-openspec-docs.sh` | [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | MIT — the script copies upstream `LICENSE` next to the docs |

Ideas (not copied text or code) were also borrowed from
[pavel-molyanov/molyanov-ai-dev](https://github.com/pavel-molyanov/molyanov-ai-dev) (MIT), and the
`openspec-to-beads` skill is inspired by the skill of the same name in
[lucastamoios/celeiro](https://github.com/lucastamoios/celeiro) (rewritten from scratch; no text copied).
Tools the templates depend on but do not include: [beads](https://github.com/steveyegge/beads),
[Superpowers](https://github.com/obra/superpowers), [Claude Code](https://code.claude.com).
