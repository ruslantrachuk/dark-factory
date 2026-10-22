# Claude subscription quota watchdog

> **Agents do not hit 100% of the Claude subscription quota.** New work does not start near the limit, work in progress
> gets saved before the cut-off, and an autonomous session pauses until the window resets and then continues on its own.
> **A mandatory part of base.**

## Why

The subscription quota (5h and 7d windows) is shared per account: every session, project, subagent and machine spends it.
At 100% Claude Code cuts work off mid-sentence — edits are not committed, the devlog is not written. Telling the
agent "watch the quota" does not work: it cannot see the quota. The watchdog is a fence built on hooks: the percentage comes from the
server, and a script makes the decision.

## Contents

| Artifact | What it does |
|---|---|
| `scripts/quota.py` | stdlib, no dependencies. Source — the `rate_limit_event` event from `claude -p … --output-format stream-json --verbose` (a short haiku request, ~6 s; no tokens are read) or the status-line input (`rate_limits.*`). Per-machine cache `~/.cache/claude-quota.json`, TTL 10 min, one probe per machine under `flock`, a failed one no more often than once per TTL; measurement log `claude-quota.log`; subagent accounting across all projects `claude-quota-agents.json`. Modes for humans: `status`, `check` (exit 1 from the "no new work" tier), `refresh` |
| `scripts/test_quota.py` | `unittest` tests: source parsing, tiers, resume time, hook decisions (including writes disguised as "saving"), fail-closed, subagent accounting, probe retry. `python3 scripts/test_quota.py` |
| `scripts/guard.py` | the fence guard; `quota.py` reuses its shell reader for the ceiling (quoted text and heredoc bodies are data; `$(…)`, backticks, `bash -c` are commands). Without it the ceiling denies every Bash line |
| `.claude/settings.json` | SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, SubagentStart, SubagentStop hooks — via `$CLAUDE_PROJECT_DIR/scripts/quota.py` (a relative path from a foreign cwd would give exit 2, which is a PreToolUse block) |

## Tiers (worst of the windows; the same thresholds for 5h and 7d)

| Quota | Session | Subagent |
|---|---|---|
| 5h ≥ 60% | no more than 2 concurrent subagents per machine | — |
| ≥ 80% | `Agent`/`Task`/`Workflow` and `bd update … --claim` are denied | same |
| ≥ 85% | after an action — a one-time instruction: WIP commit, devlog, state in bd, start no new steps | a one-time instruction to return a report to the parent |
| ≥ 90% | ceiling: read-only; Bash lines where every command (including `$(…)`, backticks, `bash -c`) is `bd`, a saving/reading `git` subcommand — `add`, `commit`, `status`, `diff`, `log`, `show`, `stash` (save/list/show), `rev-parse`, `ls-files`, `branch` (listing only: no `-d`/`-D`/`-m`, no new branch), `worktree list`, `remote -v` — or a read-only filter (`cat`, `grep`, `head`, `wc`, `jq`, `sort` without `-o`, `uniq` without an output file…), with `VAR=…`/`env -C` prefixes and `cd` steps; output redirections only to `/dev/null` or between descriptors (`2>&1`, `>&2`) — `cat > src/x <<EOF`, `jq . a > x.json`, `sort -o`, `git diff --output=` are writes and are denied; no `push`, `reset`, `checkout`, `switch`, `clean`; editing `devlog.md`/`devlog/` and `.beads/`; scheduling and cancelling a continuation (`CronCreate`/`CronDelete`, `send_later`, scheduled-task create/update/delete, `ScheduleWakeup`, `TodoWrite`) | read-only |

The quota line is shown at session start and with every human message. No data — no blocking, unless
`QUOTA_FAIL_CLOSED=1`: then no data counts as the "no new work" tier (subagents, Workflow, `bd … --claim` are denied;
everything else goes on). Recommended for unattended sessions (`vps`), where nobody watches the quota line; set it in
`.claude/fences.env` (the environment wins when set).
Settings (env): `QUOTA_5H`, `QUOTA_7D` (`"80,85,90"`), `QUOTA_FAN` (`"60,2"`), `QUOTA_TTL`, `QUOTA_TZ` (default `UTC`),
`CLAUDE_QUOTA_DIR`, `QUOTA_FAIL_CLOSED`. Bypass is for humans only: `QUOTA_GUARD=off claude`.

## Pause and self-continuation

Every watchdog message to the main session (a denial, an instruction to wrap up, the quota line at a tier)
states **when work resumes**: in the `QUOTA_TZ` zone, in UTC (`2026-10-21T17:50:00Z`) and as "in 1h 23min".
This is the latest reset among the windows holding the tier: if both 5h and 7d are exhausted, the 7d reset is given.
Instruction to the model: save the state, schedule its own continuation for that time and end the turn;
without autonomy — tell the human the time. After a reset, an expired window counts as zero even from an old cache,
so a session that wakes up is not throttled by a stale percentage.

## Properties (do not change without a reason)

- **The percentage comes from the server.** Different projects and machines see the same number and slow down identically; no dispatcher is needed.
- **No tokens are read.** The unofficial `api.anthropic.com/api/oauth/usage` requires an OAuth token — we do not use it.
- **The probe runs outside the project directory and without user settings** (`cwd` = tmp, `CLAUDE_QUOTA_PROBE=1`,
  `--no-session-persistence`, `--setting-sources local`, `--strict-mcp-config` with an empty list): project hooks
  do not fire, there is no recursion, probe sessions do not pile up, the user's plugins do not start. Without the last part the probe
  would start the user's plugins — e.g. a Telegram channel plugin sharing a state directory, which on startup kicks the bot reader
  out of a running On-call agent.
- **A regular action reads only the cache.** The probe runs when new work starts and after an action once per TTL;
  a failed probe (no `claude`, API-key login without a subscription) is not retried before the TTL.
- **The instruction to wrap up is given once** per session, agent, tier and window (`claude-quota-notices.json`).
- **Subagents are visible to hooks:** PreToolUse/PostToolUse fire inside a subagent with `agent_id` — so the
  session and the subagent get different instructions.

## Setup (at deployment and when reconciling older projects)

1. Copy `scripts/quota.py` and `scripts/test_quota.py`, run the test.
2. The hooks ship in base's `.claude/settings.json`. For a project with its own `settings.json` — add the hook groups to
   the existing events, do not replace them.
3. "Save" paths at the 90% tier — `devlog.md`, `devlog/`, `.beads/` (base layout). For a different layout,
   adjust `SAVE_PATH_RE`.
4. **Recommended:** the status-line feed in `~/.claude/settings.json` (a user file, set by a human):
   `"statusLine": {"type": "command", "command": "python3 <path>/scripts/quota.py statusline"}` — fresh data
   after every model response with no probe at all (no `claude -p` request, no 6 s wait, nothing to fail).
   The probe stays the fallback for sessions without a status line (headless, scheduled). With `QUOTA_FAIL_CLOSED=1`
   the feed matters even more: no data is a denial, and the status line keeps the data coming.
5. Scheduled runs ("run it tonight"): the booked prompt starts with `scripts/quota.py check`; on denial the
   session books itself again for the reset time. A session dedicated to scheduled work can run with lower
   thresholds (`QUOTA_5H="60,70,80"`), leaving the quota to the sessions people are working in.
6. Check: a new session prints "📊 subscription quota: …"; a subagent denial at a low threshold:
   `echo '{"tool_name":"Agent","tool_input":{}}' | QUOTA_5H=1,85,90 python3 scripts/quota.py pretool`
   returns `deny` with "Work resumes … Z".

## Not covered

- Fan-out accounting is per machine, not per account: two machines together can run up to 4 subagents.
- A subagent whose `SubagentStop` never arrived (the session was killed) counts as alive for 2 hours (`AGENT_TTL`) and occupies a fan-out slot.
- No "the session a person is working in beats scheduled work" priority — only lowered thresholds for the latter.
- No forecast of "this task will push us to 100%" — thresholds are fixed; the measurement log accumulates for estimation.

## Review criterion

The watchdog is reconsidered if within a month a session was cut off at 100% even once with the watchdog running (the fence does not hold)
or the owner regularly bypasses it with `QUOTA_GUARD=off` (the thresholds get in the way more than they protect).

## Open questions

- [ ] verify live that `Workflow` agents go through SubagentStart and PreToolUse;
