# Machines

One file per machine that runs this factory's sessions: `machines/<host>.md`. A machine file says **how the machine is
set up**, not which projects are on it: the checkout paths live on the machine itself, in
`~/.config/dark-factory/projects` (one path per line), which `/dark-factory:factory-status` and
`/dark-factory:provision-server` read.

## A Linux VPS with systemd (sessions come back after a reboot)

Record in `machines/<host>.md`:

- provider, size, region, how to log in (no secrets)
- the OS user the sessions run as (not root) and that `loginctl enable-linger <user>` is on
- `claude` installed and logged in under the subscription; `gh` logged in; `bd`, `tmux`, `git` installed
- where notifications go (`FLEET_NOTIFY=session` or `FLEET_NOTIFY_CMD` in `~/.config/dark-factory/fleet.env`)
- which ports and secrets directories are taken (see "Shared resources" in the method's functions page)
- the date `/dark-factory:provision-server` was last run

## A Mac (attended sessions, by hand)

Nothing is provisioned there: sessions are started by hand and are gone after a restart. Record the same facts
that apply (login, tools, ports, secrets) and say it is attended. `/dark-factory:factory-status` reads "not
provisioned" for the session on a machine like this, by design.

## Template

```markdown
# <host>

- Kind: VPS (systemd) | Mac (by hand)
- User: <os user>
- Set up: <date>, <who>
- Projects file: ~/.config/dark-factory/projects (paths are kept there)
- Notes: <anything the next person needs>
```
