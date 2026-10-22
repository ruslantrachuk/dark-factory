# Known prod incidents of <project>

The monitor's catalogue: it checks against it on every pass, names an incident by name and suggests the step from here.
An entry is name, signs, verdict, step. A new incident type — add it here and run `prod-monitor.sh install`.
Known background (things that are always there and do not affect users) also goes here, otherwise the monitor will alarm the group.

- **<name>** — <signs in logs/data>. Verdict: <crit | warn | info>. Step: <what the developer does; what only the owner does>.

Illustrative example (a bot on a container hosting):
- **Hosting build fails** — `error building image … failed to get filesystem from image` while unpacking the base
  image. The code is not at fault, prod stays on the previous version. Step: rebuild up to 5 times in a row (developer alone); if that does not help — to the group.
- **Stuck scheduler** — no heartbeat in the logs for more than 3 minutes, deferred jobs pile up. Verdict: crit.
  Step: restart (developer alone, up to 5 times in a row, then ask the group).
- **Server network → hosting** — http_probe returns 000/timeout while the logs are alive. This is not prod. Verdict: info at most.
- **Background, not an alarm**: a single 403 "bot was blocked by the user"; hosting warnings while prod works.
