# Claude subscription quota watchdog

> **Agents do not hit 100% of the Claude subscription quota.** New work does not start near the limit, work in progress
> gets saved before the cut-off, and an autonomous session pauses until the window resets and then continues on its own.
> **Part of the dark-factory plugin**; every project that uses the plugin (base, or the solo kit of
> `/dark-factory:init`) has it. Paths below are relative to the plugin root.

## Why

The subscription quota (5h and 7d windows) is shared per account: every session, project, subagent and machine spends it.
At 100% Claude Code cuts work off mid-sentence — edits are not committed, the PR description is not updated. Telling the
agent "watch the quota" does not work: it cannot see the quota. The watchdog is a fence built on hooks: the percentage comes from the
server, and a script makes the decision.

## Contents

| Artifact | What it does |
|---|---|
| `scripts/quota.py` | stdlib, no dependencies. Source — the `rate_limit_event` event from `claude -p … --output-format stream-json --verbose` (a short haiku request, ~6 s; no tokens are read) or the status-line input (`rate_limits.*`). Per-machine cache `~/.cache/claude-quota.json`, TTL 10 min, one probe per machine under `flock`, a failed one no more often than once per TTL; never inline after an action or on a prompt (a detached background refresh instead); measurement log `claude-quota.log`; subagent accounting across all projects `claude-quota-agents.json`. Modes for humans: `status`, `check` (exit 1 from the "no new work" tier), `refresh` |
| `scripts/statusline.py` | the status-line installer behind `/dark-factory:statusline`: a stable wrapper `~/.claude/dark-factory/statusline.sh` in `~/.claude/settings.json` that feeds the newest installed plugin version and keeps the previous status line; dry run by default, `--apply`, `--uninstall` |
| `scripts/test_quota.py` | `unittest` tests: source parsing, tiers, resume time, hook decisions (including writes disguised as "saving", git config and environment, abbreviated options, `..` and symlinked paths), scheduling only after the reset, `QUOTA_ROLE=desk`, fail-closed (one fences parser with the guard), a crash, the hot path with a slow probe, the project and its opt-in, subagent accounting, probe retry, the status-line installer against a temporary HOME. `python3 plugins/dark-factory/scripts/test_quota.py` from the canon |
| `scripts/guard.py` | the fence guard; `quota.py` reuses its shell reader for the ceiling (quoted text and heredoc bodies are data; `$(…)`, backticks, `bash -c` are commands). Without it the ceiling denies every Bash line |
| `hooks/hooks.json` | SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, SubagentStart, SubagentStop hooks — via `<plugin root>/scripts/quota.py` (an absolute path: a relative one from a foreign cwd would give exit 2, which is a PreToolUse block) |

**The project** is `$CLAUDE_PROJECT_DIR` (else the git top level of the hook's cwd): `.claude/fences.env` is read from
it. A project **opts in** with that file (base ships it, `/dark-factory:init` writes it). Without it the hooks stay
silent apart from a one-line hint at session start, so a plugin installed for the user does not throttle unrelated
projects. The subagent registry counts every project on the machine either way.

## Tiers (worst of the windows; the same thresholds for 5h and 7d)

| Quota | Session | Subagent |
|---|---|---|
| 5h ≥ 60% | no more than 2 concurrent subagents per machine | — |
| ≥ 80% | `Agent`/`Task`/`Workflow` and `bd update … --claim` are denied | same |
| ≥ 85% | after an action — a one-time instruction: WIP commit, the PR description and the task notes in bd (the `save` skill), start no new steps | a one-time instruction to return a report to the parent |
| ≥ 90% | ceiling: read-only; Bash lines where every command (including `$(…)`, backticks, `bash -c`) is `bd` (all of it, `bd sync` included: it commits and pushes the queue, which is saving), a saving/reading `git` subcommand — `add`, `commit`, `status`, `diff`, `log`, `show`, `stash` (save/list/show), `rev-parse`, `ls-files`, `branch` (listing only: no `-d`/`-D`/`-m`, no new branch), `worktree list`, `remote -v` — or a read-only filter (`cat`, `grep`, `head`, `wc`, `jq`, `sort` without `-o`, `uniq` without an output file…), with `env -C`/`git -C` and `cd` steps; output redirections only to `/dev/null` or between descriptors (`2>&1`, `>&2`) — `cat > src/x <<EOF`, `jq . a > x.json`, `sort -o`, `git diff --output=` are writes and are denied; a long option also matches by its abbreviation (`sort --out=`, `sort --compress-prog=`); no `push`, `reset`, `checkout`, `switch`, `clean`; no git option that runs a program — `-c`, `--config-env`, `--exec-path`, `--git-dir`, `--work-tree` (only `-C`, `--no-pager` and the pathspec flags pass) — and no `VAR=…`/`env VAR=…` prefix except `BEADS_DIR`, `BEADS_DB`, `BD_ACTOR`, `LANG`, `LC_ALL`, `TZ`, `NO_COLOR` (`GIT_EXTERNAL_DIFF=…`, `GIT_PAGER`, `EDITOR`, `LD_PRELOAD`, `PATH` are denied); the PR as the record of work — `gh pr view`/`list`/`status`/`diff`/`checks`, `gh pr edit` of the title and description only (`--title`, `--body`, `--body-file -` from stdin), `gh pr create --draft` (no `--fill`, `--web`, `--editor`, `--repo`; no merge, review, comment or close), every `gh` word literal (no `$…` expansion, so no file's contents and no extra option reach GitHub); editing this project's Claude Code memory (`<config dir>/projects/<project>/memory/`, `<project>` being this checkout or, from a worktree, the main checkout, the config dir being `$CLAUDE_CONFIG_DIR` or `~/.claude`), checked after `..` and symlinks are resolved, never a `.git/` path, `HEAD` or `config` there; listing and cancelling scheduled runs (`CronList`/`CronDelete`, scheduled-task list/get/delete, `TodoWrite`) and **booking a continuation for the reset time or later** — see below | read-only |

The quota line is shown at session start and with every human message. No data — no blocking, unless
`QUOTA_FAIL_CLOSED=1`: then no data counts as the "no new work" tier (subagents, Workflow, `bd … --claim` are denied;
everything else goes on). Recommended for unattended sessions (`vps`), where nobody watches the quota line; set it in
`.claude/fences.env` (the environment wins when set; the file is read by the guard's parser, so a later line wins
for both). A crash of the watchdog itself counts as no data: a warning, or with `QUOTA_FAIL_CLOSED=1` new work is
blocked (exit 2 on PreToolUse); it never passes silently.

**`QUOTA_ROLE=desk`** — set in the environment of the On-call session (the restricted session in the client chat,
started by the feedback-desk module): answering the client is never cut off. Chat tools ending in `__reply`,
`__react`, `__edit_message`, `__download_attachment`, and `SendMessage`, `ListAgents`, `ToolSearch`, `Read` pass at
every tier; everything else is tiered as usual, the quota line and warnings still show, prompts are never blocked.

Settings (env): `QUOTA_5H`, `QUOTA_7D` (`"80,85,90"`), `QUOTA_FAN` (`"60,2"`), `QUOTA_TTL`, `QUOTA_TZ` (default `UTC`),
`QUOTA_STALE_MAX` (default 18000 s: an older cache counts as no data), `CLAUDE_QUOTA_DIR`, `QUOTA_FAIL_CLOSED`, `QUOTA_ROLE`. Bypass is for humans only: `QUOTA_GUARD=off claude`.

## Pause and self-continuation

Every watchdog message to the main session (a denial, an instruction to wrap up, the quota line at a tier)
states **when work resumes**: in the `QUOTA_TZ` zone, in UTC (`2026-10-21T17:50:00Z`) and as "in 1h 23min".
This is the latest reset among the windows holding the tier: if both 5h and 7d are exhausted, the 7d reset is given.
Instruction to the model: save the state, schedule its own continuation for that time and end the turn;
without autonomy — tell the human the time.

At the ceiling a booking passes only if it starts **at the reset minute or later**: `send_later` (`at`,
`delay_minutes`), a scheduled task (`run_once_at`, `cron_expression` in UTC or with `CRON_TZ=`), `CronCreate`
(`cron`, local time), `ScheduleWakeup` (`delaySeconds` — so only when the reset is within its reach),
`RemoteTrigger` create/update (the same fields in `body`). A run sooner would start new work on the quota that is
running out; running a scheduled task now (`RemoteTrigger` run, `fire_trigger`) is denied, and a booking whose
time the watchdog cannot read (no time, `@daily`, day names) is denied with the reset time in the message.
Updating a scheduled task without a new time (rename, prompt, disable) passes. After a reset, an expired window counts as zero even from an old cache,
so a session that wakes up is not throttled by a stale percentage.

## Properties (do not change without a reason)

- **The percentage comes from the server.** Different projects and machines see the same number and slow down identically; no dispatcher is needed.
- **No tokens are read.** The unofficial `api.anthropic.com/api/oauth/usage` requires an OAuth token — we do not use it.
- **The probe runs outside the project directory and without user settings** (`cwd` = tmp, `CLAUDE_QUOTA_PROBE=1`,
  `--no-session-persistence`, `--setting-sources local`, `--strict-mcp-config` with an empty list): project hooks
  do not fire, there is no recursion, probe sessions do not pile up, the user's plugins do not start. Without the last part the probe
  would start the user's plugins — e.g. a Telegram channel plugin sharing a state directory, which on startup kicks the bot reader
  out of a running On-call agent.
- **A regular action reads only the cache; the hot path never probes.** The probe runs inline only when new work
  starts (PreToolUse) or a session starts, and then waits at most 3 s for another process's probe before using the
  stale cache. After an action (PostToolUse) and on a prompt (UserPromptSubmit) a stale cache starts one detached
  background refresh (`quota.py bg-refresh`, skipped while a probe holds the lock) and the stale value is used:
  those hooks take a fraction of a second even when `claude -p` hangs, and their timeouts are 15 s. A failed
  probe (no `claude`, API-key login without a subscription) is not retried before the TTL.
- **The instruction to wrap up is given once** per session, agent, tier and window (`claude-quota-notices.json`).
- **Subagents are visible to hooks:** PreToolUse/PostToolUse fire inside a subagent with `agent_id` — so the
  session and the subagent get different instructions.

## Setup (at deployment and when reconciling older projects)

1. Install the dark-factory plugin (the repository README); base's `.claude/settings.json` enables it for the project
   (`enabledPlugins`, `extraKnownMarketplaces`). The hooks come with the plugin — nothing to copy.
2. The project has `.claude/fences.env` (base ships it; the solo kit writes it). Older projects that carried
   `scripts/quota.py`, `scripts/guard.py` and their hook groups in `.claude/settings.json`: remove both, or the
   hooks run twice.
3. "Save" paths at the 90% tier — Claude Code's project memory, `<config dir>/projects/<project>/memory/`, matched
   after the path is resolved. Everything else that saves work is a command: git, bd, `gh pr edit`.
4. **Recommended:** the status-line feed — the human runs `/dark-factory:statusline` (dry run, then `--apply`). It
   sets `statusLine` in `~/.claude/settings.json` to a stable wrapper, `~/.claude/dark-factory/statusline.sh`, which
   finds the newest installed plugin version under `~/.claude/plugins/cache/` at run time (so plugin updates need
   no rerun), feeds `quota.py statusline`, and runs the status line the human had before (saved by the installer;
   its output comes first, the quota line after it, or none with `--feed-only`). `--uninstall` restores it. Fresh
   data after every model response with no probe at all (no `claude -p` request, no 6 s wait, nothing to fail).
   The probe stays the fallback for sessions without a status line (headless, scheduled). With `QUOTA_FAIL_CLOSED=1`
   the feed matters even more: no data is a denial, and the status line keeps the data coming.
5. Scheduled runs ("run it tonight"): the booked prompt starts with `python3 <path>/scripts/quota.py check`; on denial the
   session books itself again for the reset time. A session dedicated to scheduled work can run with lower
   thresholds (`QUOTA_5H="60,70,80"`), leaving the quota to the sessions people are working in.
6. The On-call session of the feedback-desk module runs with `QUOTA_ROLE=desk` (its launcher sets it), so it can
   answer the client at the ceiling.
7. Check: a new session prints "📊 subscription quota: …"; a subagent denial at a low threshold:
   `echo '{"tool_name":"Agent","tool_input":{}}' | QUOTA_5H=1,85,90 CLAUDE_PROJECT_DIR=<project> python3 <path>/scripts/quota.py pretool`
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
