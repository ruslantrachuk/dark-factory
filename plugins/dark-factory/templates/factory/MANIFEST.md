# factory — module manifest

> **The skeleton of your own factory**: a small, usually private repository that holds only what is yours — which
> projects you run, how each machine is set up, your pin of the dark-factory plugin, your own roles and your notes.
> The public dark-factory repository is the template; this repository holds no copy of the method, the templates or the
> plugin. The full description is [docs/your-factory.md](https://github.com/ruslantrachuk/dark-factory/blob/main/docs/your-factory.md).
> Installed into an **empty repository** (not into a project: a project has `/dark-factory:add base`).

## Contents

| File | What it holds |
|---|---|
| `registry.md` | the projects: what, repository, level, modules, client, machine; no paths |
| `machines/README.md`, `machines/<host>.md` | how each machine is set up (a VPS with systemd through `/dark-factory:provision-server`, or a Mac by hand); not a second list of project paths |
| `.claude/settings.json` | the dark-factory plugin enabled and pinned to a release (`"ref": "v<N>"`) for sessions opened in this repository |
| `.claude/agents/` | your own roles; created when you need one (see below) |
| `notes/README.md`, `notes/` | your own decisions, any language |

## Setup by /dark-factory:add factory

Owner's own steps first: create an empty repository (private is usual) and clone it; nothing else needs a secret.

1. `/dark-factory:add factory` in the empty clone: the files above are copied, none overwritten.
2. In `registry.md` delete the example row. Add a row per project you run (`/dark-factory:add base` and
   `/dark-factory:init` offer to do it at the end).
3. For each machine, create `machines/<host>.md` from the template in `machines/README.md`.
4. Check `.claude/settings.json`: the `ref` is the release you installed from; keep it until you choose to move.
5. Commit; open Claude Code in the repository; `/dark-factory:factory-status` on a provisioned machine shows the
   projects in `~/.config/dark-factory/projects`.

Roles: put `.claude/agents/<name>.md` (same name as a plugin role, e.g. `reviewer.md`) in **a project's own**
`.claude/agents/` to override that role in that project's workflow runs, or in `~/.claude/agents/` for a role you call by
hand by its bare name. The factory repository's own `.claude/agents/` applies to sessions opened in the factory
repository only; it does not reach the projects.

## Abandon criterion

You run one project, or none of your projects needs a machine file: keep the pin in the project's own settings and
delete this repository.
