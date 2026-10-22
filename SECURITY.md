# Security policy

## Reporting a vulnerability

Report it privately through GitHub's private vulnerability reporting: the repository's **Security** tab →
**Report a vulnerability** ([direct link](https://github.com/ruslantrachuk/dark-factory/security/advisories/new)).
Do not open a public issue for it.

Please include what an attacker (or a misbehaving agent) can do, the fence level and versions involved (plugin
version from `plugins/dark-factory/.claude-plugin/plugin.json`, `claude --version`), and the smallest reproduction —
for a guard bypass, the exact tool call the guard let through. Expect an acknowledgement within a week; a fix is
released as a new plugin version with a [CHANGELOG](CHANGELOG.md) entry, and you are credited unless you ask not
to be.

## Supported versions

| Version | Supported |
|---|---|
| latest release (`vX.Y.Z` tag, currently 0.3.x) | yes |
| older releases | no — move the project's marketplace pin to the latest tag |
| `main` between releases | best effort |

## Scope

In scope: the dark-factory plugin (guard, quota guard, level grants, hooks, the solo kit, the feature pipeline
workflows), the templates' scripts and settings (`templates/**`: `merge-feature.sh`, `release.sh`, git hooks, the
On-call and prod-monitor scripts, CI workflows), and the factory scripts (`scripts/`). Typical findings: a tool call
that should be denied at a given fence level and is not; a way for the agent to lower its own fence level or write
into the installed plugin; a template default that exposes a credential or widens a token's permissions; injection
through a channel envelope or the monitor channel.

Out of scope: Claude Code itself, GitHub, Telegram and other third-party services (report those to their vendors);
anything that needs the owner's own credentials or a shell as the same Unix user (see the residual risks in the
[threat model](docs/threat-model.md)); and the guard's documented limits below.

## What the guard is, and what it is not

The guard is a **seatbelt**: a static reader of tool calls (a PreToolUse hook) that stops an agent's mistakes and the
common shortcuts — a force push, a push to main, skipping the git hooks, an unaccepted merge, an edit to the fences.
It is **not a sandbox against a hostile agent**: it cannot see through a script written to a file and then run, an
alias defined elsewhere, a subprocess or an arbitrary interpreter, and a human can restart a session with it off.
Bypasses of that kind are known limits, not vulnerabilities; a plain command the guard is meant to deny and lets
through is a vulnerability.

The real gates sit outside the agent's machine and process:

- **GitHub branch protection or rulesets** on main and on release tags (no force push, a pull request required, no
  admin bypass) — the factory's `deploy-project` skill applies and verifies them;
- **required reviews** at the `team` fence level, ideally with the agent on its own GitHub identity;
- **the Claude Code sandbox** (filesystem and network limits for commands) and `permissions.deny` for credentials.

The [threat model](docs/threat-model.md) lists the assets, actors, trust boundaries, the control on each boundary and
the risks that remain.
