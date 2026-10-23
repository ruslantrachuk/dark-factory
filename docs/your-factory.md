# Your own factory

If you run more than one project, keep a small repository of your own for the factory. The public dark-factory
repository is the template: the method, the plugin, the templates. Your factory repository holds only what is yours, so
there is nothing to keep in step with the public one except a version number.

## What is in it

| Path | What it holds |
|---|---|
| `registry.md` | the projects you run: what each is, its repository, level, modules, client and machine. It describes; it holds no paths |
| `machines/<host>.md` | how each machine is set up: a VPS with systemd (through `/dark-factory:provision-server`) or a Mac by hand. It is not a second list of project paths: those live on the machine, in `~/.config/dark-factory/projects`, which `/dark-factory:factory-status` and `/dark-factory:provision-server` read |
| `.claude/settings.json` | the dark-factory plugin enabled and pinned to a release (`"ref": "v<N>"`) |
| `.claude/agents/` | your own roles (optional), see [Your own roles](#your-own-roles) |
| `notes/` | your own decisions and lessons, in any language |

No copy of the method, the templates or the plugin belongs in it. A copy goes stale; the pin does not.

## Steps

1. **Create the repository.** An empty, usually private, repository; clone it.
2. **Add the plugin and the skeleton.** In the clone, in Claude Code:

   ```
   /plugin marketplace add ruslantrachuk/dark-factory
   /plugin install dark-factory@dark-factory
   /dark-factory:add factory
   ```

   `add factory` copies the files above without overwriting anything, and pins the plugin to the release you installed.
3. **Add projects.** In each project run `/dark-factory:add base` (or `/dark-factory:init` for level 0). `add` ends by
   offering to add its row to `registry.md` (after `init`, add the row by hand); delete the example row.
4. **Set up each machine.** Write `machines/<host>.md` (a template is in `machines/README.md`).
   - *A VPS with systemd:* a non-root user with `loginctl enable-linger`; `claude` installed and logged in under the
     subscription; `gh` logged in; `git`, `tmux` and `bd` installed; the project checkouts listed in
     `~/.config/dark-factory/projects`, one path per line. Then run `/dark-factory:provision-server`: the development
     session (and On-call, where the project has it) of every listed project starts by itself and comes back after a
     reboot.
   - *A Mac:* nothing is provisioned. Start sessions by hand; they are gone after a restart. Write down what applies
     (logins, tools, ports) and say the machine is attended.
5. **Look at the state.** `/dark-factory:factory-status` on a provisioned machine: sessions, On-call, monitor, quota,
   queue and each project's lag behind the plugin.
6. **Keep current.** See below.

## Fences in the factory repository

The factory repository ships no `fences.env`, so it is unfenced by default: the guard still runs as part of the plugin,
but it holds no level for this repository. To fence it like a project, run `/dark-factory:init` in it.

## Keeping current

- **Move to a new release.** Read the release's notes
  ([releases](https://github.com/ruslantrachuk/dark-factory/releases); **How to upgrade** lists the steps beyond the
  file update), then change the `ref` in the factory's `.claude/settings.json` (a fence file: the change goes through
  the permission dialog and a reviewed merge). In each project run `/dark-factory:upgrade`: on a work branch it
  updates the template files with `copier update` (conflict markers where the project has its own text, resolved
  there), moves the pin, applies the project steps of the notes and lists the server steps for you in the PR.
- **See who is behind.** `/dark-factory:factory-status` compares each project's `.harness/base-sha` (`v<N>` when the project was set up by an installed plugin; a commit SHA
  when it was copied from a git checkout of the canon) with the installed plugin and says
  `template v1, the plugin is at v2`.
- **Give back.** A fix or improvement that is not specific to you goes to the public repository as a pull request;
  what is specific to you stays in `notes/` or in your own roles.

## Your own roles

The plugin ships three roles (`tech-lead`, `reviewer`, `product-owner`). To replace one, write an agent file with the
same name. Where it takes effect:

- In a **project's own `.claude/agents/`**: the feature-pipeline workflows look there at the start of a run and use the
  project's role in place of the plugin's. This is the only place the workflows detect.
- In **`~/.claude/agents/`** (your user): a role you call by hand by its bare name (`reviewer`) is yours. The workflows
  do not look there: they call `dark-factory:<name>` unless the project has its own file.
- The factory repository's own `.claude/agents/` applies to sessions opened in the factory repository, and does not
  reach the projects. To share one role across projects, put the file in each project (a symlink or a copy kept
  there) or in `~/.claude/agents/` on the machine for hand calls.

See the "Roles" section of [the workflows README](../plugins/dark-factory/workflows/README.md).

## Shared by everything on a machine

One subscription quota, the bots, the secrets and the ports are shared by all projects on a machine; the rules are in
[functions.md](functions.md#factory-level-functions).
