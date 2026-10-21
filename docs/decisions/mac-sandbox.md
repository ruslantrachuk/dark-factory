# Agent sandbox on macOS — decision record

> Status: **accepted** — tier 1 is materialised in `templates/base`
> (a `sandbox` + `permissions.deny` block in settings.json, enabled through an explicit question
> in the deploy-project questionnaire). Decisions on the original questions:
> (1) yes, tier 1 goes into base; (2) a strict sandbox + permissions for autonomous runs, a devcontainer only with night-local;
> (3) the default network allowlist is the git host + the stack's and the project's domains from the questionnaire. Facts about Claude Code
> are checked against the current official docs (links below), per filter item 1 in [methodology.md](../methodology.md) §5: "check against the docs,
> not an article". Where the problem was first recorded: [layers/production.md](../layers/production.md);
> background principle: "a worktree ≠ a sandbox".

## Problem (filter item 0 — an episode, not a tool)

On a VPS a sandbox is free: a disposable offline box — a machine without secrets, wiped and
re-provisioned. On a Mac an autonomous agent works with the user's full rights next to
`~/` (home), the Keychain and corporate VPNs — while executing untrusted input: task descriptions from
trackers, mirrored bug reports, npm dependencies (postinstall scripts). A worktree isolates
files/git, but not commands.

## Main finding (filter item 1 — "already covered by something built in?")

**Yes, for the most part.** Claude Code has a built-in OS sandbox on macOS (Seatbelt):
filesystem and network isolation of Bash subprocesses, configured in `settings.json`,
with no external dependencies. That fits "nothing home-grown" exactly: only the
config is custom. The cheap Linux step (cgroup limits / bwrap) does not exist on a Mac; Docker
around a run is not needed as a base layer.

What the built-in sandbox gives:

- **Filesystem**: writes only to the working directory + the session's temp; `sandbox.filesystem.denyRead`
  blocks reading secrets **for Bash subprocesses** (which `permissions.deny` does not cover).
- **Network**: a domain allowlist (`sandbox.network.allowedDomains`); by default nothing is
  allowed — the first access asks.
- **Secrets**: `sandbox.credentials.files` / `envVars` — deny or mask for `~/.ssh`,
  `~/.aws/credentials`, tokens in env.
- Restrictions are inherited by all Bash child processes; subagents inherit the parent's sandbox.

What it does **not** close (honest gaps):

| Gap | What closes it |
|---|---|
| Read/Edit/Write tools run outside the sandbox | `permissions.deny`: `Read(~/.ssh)`, `Read(.env)` etc. — the permissions layer works precisely for tools |
| MCP servers run outside the sandbox | the MCP perimeter: in an autonomous run, do not connect servers with access to secrets/network |
| Escape hatch: a command that failed in the sandbox may be retried without it | `sandbox.allowUnsandboxedCommands: false` for autonomous runs |
| Keychain / corporate VPN are system-level, not files | the sandbox cuts the network by domain (VPN hosts are not on the allowlist) and does not allow running `security` tooling outside the filesystem perimeter; a full guarantee is only tier 2 |

## Decision: two tiers (by principle 13 — layer by strength of guarantee)

### Tier 1 — in `templates/base` (the base layer, for supervised and semi-autonomous work)

A block in the template's `.claude/settings.json` (placeholders filled by the deploy-project mechanics):

```json
{
  "sandbox": {
    "enabled": true,
    "filesystem": { "denyRead": ["~/.ssh", "~/.aws", "~/.config/gh", "~/Library/Keychains"] },
    "network": { "allowedDomains": ["github.com", "api.anthropic.com", "<project domains>"] },
    "credentials": {
      "files": [{ "path": "~/.ssh", "mode": "deny" }, { "path": "~/.aws/credentials", "mode": "deny" }],
      "envVars": [{ "name": "<PROJECT_TOKEN>", "mode": "mask" }]
    },
    "allowUnsandboxedCommands": true
  },
  "permissions": { "deny": ["Read(~/.ssh/**)", "Read(~/.aws/**)", "Read(./.env*)"] }
}
```

- `allowUnsandboxedCommands: true` during the day (a human is nearby, false blocks do not paralyse work),
  **false in the autonomous-run profile** (the night queue sets it at start).
- Cost of ownership: ~25 lines of config, 0 tokens per turn, 0 external dependencies. It is the same
  perimeter as agent-level guarantees in [open-questions.md](../open-questions.md) §1 (denyRead for secrets + a network allowlist) —
  one layer, one source of truth: the template's settings.json.

### Tier 2 — devcontainer (only if/when `--dangerously-skip-permissions` is wanted at night on a Mac)

The official reference `anthropics/claude-code` `.devcontainer/` (image + `init-firewall.sh`,
an egress allowlist at the iptables level). The documented pattern for unattended runs:
the container is the boundary; inside, skip-permissions is acceptable. Requires Docker or an equivalent on the Mac — a weight
taken on only with a real night queue on a Mac, not in advance (principle 11, "N=1 first").

### Rejected (with conditions for return — principle 9)

- **bwrap / cgroup limits** — Linux mechanisms, absent on a Mac. Return: not foreseen.
- **Docker around every run as the base layer** — duplicates the built-in sandbox at the cost of
  starting environments (the very "morning tax" pain). Return: as tier 2 for nights on a Mac.
- **A separate macOS user for the agent** — protects home/Keychain but not the network/VPN, and
  breaks access to working checkouts and caches; worse than the built-in sandbox on every axis except
  "we do not trust Seatbelt". Return: if practice shows Seatbelt bypasses.
- **microVM** — per the already resolved fork ([open-questions.md](../open-questions.md) §2): only for multi-tenancy.

## Pilot and abandon criterion (filter item 6 — recorded before the start)

- **Where**: the factory itself (project #0) + one live project; enable tier 1 and work for a week
  as usual.
- **Abandon if**: (a) more than 3 episodes a week where the sandbox blocks a legitimate command and
  the config has to be edited by hand "in the moment"; (b) an observed bypass of the perimeter (the agent read
  a denyRead path or reached a domain outside the allowlist); (c) a noticeable slowdown of runs.
- **Outcome either way** → a row in [open-questions.md](../open-questions.md) §2, and if accepted — the block
  is materialised in `templates/base/.claude/settings.json` and becomes a reconciliation item when reviewing live projects.

## References

- Sandbox: https://code.claude.com/docs/en/sandboxing.md
- Permissions: https://code.claude.com/docs/en/permissions.md
- Devcontainer: https://code.claude.com/docs/en/devcontainer.md
- Headless: https://code.claude.com/docs/en/headless.md
