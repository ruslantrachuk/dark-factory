# Menu bar status: the factory at a glance on the owner's Mac

## Why

The factory runs on a server; the owner works on a Mac. To know whether anything is working right now — which
projects have agents running, which wait for quota, whether the On-call and the production watchdog are on — the owner
has to open a session and ask for `factory-status`, or read the quota line's "subagents: <project> N" without the rest.
There is no single place to glance at.

## What changes

- **Server: a status feed.** `fleet.py feed` writes one `status.json` for every project of the server every 15 minutes
  (a `df-fleet-feed.timer`), built from the same checks as `fleet.py status` plus three new facts per project: whether
  work is running now (and how many agents), when the On-call last wrote, when the project last worked. Read-only, no
  model, no quota spent.
- **Server: a private endpoint.** `fleet.py serve` serves that one file over HTTP on a private-network address only
  (Tailscale on the reference setup). Written as a user unit by `fleet.py provision` when `fleet.env` names the
  address.
- **Mac: a small native app** (`macos/FactoryBar/`), built by the owner in Xcode with a free Apple ID:
  - a **menu bar icon** with three states — live and working, live and idle, no data;
  - a **drop-down** under the icon and a **large desktop widget** with the same content: projects working now, idle
    projects, the On-call and watchdog icons, status line, last update;
  - a click on a project opens that project's development session in Claude.
- Interface text in English.

## Not in this change

- Trends over time (the "dynamics" view). The weekly analytics change covers history; the widget is "now".
- iPhone widget, notifications, sounds.
- Any action from the Mac (restart, claim, release). The app only reads.
- An endpoint reachable from the internet, or authentication beyond the private network.

## Acceptance scenarios

- WHEN a project has agents running THEN the icon is the filled "working" glyph with the number of running agents,
  and the project is listed under "Working now" as "Building · N agents".
- WHEN a session of a project is in the middle of a turn, with no agents THEN the project is under "Working now" as
  "Building" and the icon is "working"; WHEN that session finishes the turn and waits at its prompt THEN it no longer
  counts as working.
- WHEN no project has work running and the feed is fresh THEN the icon is the outlined "idle" glyph.
- WHEN quota blocks new work and a project has ready tasks THEN that project is under "Working now" as
  "Waiting for quota until HH:MM · N queued".
- WHEN the Mac cannot reach the endpoint, or the feed's `generated_at` is older than 45 minutes THEN the icon shows
  "no data" (red outline with "?"), and the drop-down says why and when the last good feed was.
- WHEN a project has the On-call module THEN its headset icon is colored if the On-call is running and grey if not;
  the same for the production watchdog (shield). A project without the module shows no icon for it.
- WHEN the On-call wrote in the last hour THEN the project row shows "On-call wrote N min ago"; otherwise no such line.
- WHEN a project is idle THEN its row shows "Last worked <when>".
- WHEN the owner clicks a project in the drop-down or in the widget THEN its development session opens in Claude; if
  the feed has no session link for it, the click does nothing and the row has no link style.
- WHEN `fleet.env` names no feed address THEN `fleet.py provision` writes no feed units and nothing listens.
