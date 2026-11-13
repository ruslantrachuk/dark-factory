# The fences hold under Codex: apply_patch, no "ask", the Codex layer, execpolicy rules

## Why

After agent-codex the plugin's guard runs under Codex and denies a shell `git commit --no-verify`. Three gaps stayed,
all from how Codex differs from Claude Code (Codex hook documentation, release behaviour, Codex CLI 0.169):

- **File edits.** Codex edits files with one tool, `apply_patch`: PreToolUse gets `tool_name: "apply_patch"` and the
  whole patch in `tool_input.command`. The guard knew Edit, Write, MultiEdit and NotebookEdit only, so a patch to
  `.githooks/pre-push`, `.claude/settings.json`, `.claude/fences.env` or `.git/hooks/` passed unchecked.
- **"ask" lets the call through.** Under Claude Code a fence change is asked in the permission dialog. Codex parses a
  PreToolUse `permissionDecision: "ask"` but does not support it: it marks the hook run failed **and runs the call**.
  Every fence change the guard would ask about was open under Codex.
- **The Codex layer is not a fence.** `.codex/hooks.json`, `.codex/config.toml` and `.codex/rules/` decide whether the
  hooks run (a changed hook is skipped until re-approved) and what the permission profile denies; nothing fenced them.

## What changes

- **The guard reads `apply_patch`.** Each file a patch adds, updates, deletes or moves (both ends of a move) gets the
  checks of an Edit/Write: the installed plugin, `.git/hooks` and `.git/config`, settings that switch the hooks or the
  plugin off (the patched text is computed from the hunks when it can be), `fences.env` (raising the level passes,
  lowering it or an untellable result is a fence change, deleting it is too), and the fence files at standard and team.
  A patch the guard cannot read is judged by the fence names it mentions.
- **Under Codex the guard never asks.** A Codex session (its transcript under `<CODEX_HOME>/sessions/`, as in the
  quota guard) is treated like a launched agent: what would be asked is denied, with "leave it to the human".
- **`.codex/hooks.json`, `.codex/config.toml`, `.codex/rules/…` are fence files** for every agent, from the shell and
  from edit tools.
- **The hook matcher names `apply_patch`** explicitly (Codex also matches it by its `Edit`/`Write` aliases).
- **`.codex/rules/dark-factory.rules` in the agent-codex module**: execpolicy `forbidden` for the plain forms of a force
  push, `--no-verify` on commit/push/merge/rebase/am/cherry-pick, `git config core.hooksPath`/`--unset`, and
  `gh pr merge` — a second line for the plain forms; the guard reads the whole line.
- **Branch protection** stays the last line on any agent; the manifest says so.

## Acceptance

- WHEN a Codex `apply_patch` updates `.githooks/pre-push` at standard THEN the guard returns a fence change; at solo it
  passes; a move of any file onto a fence path is the same.
- WHEN a patch adds `.git/hooks/pre-commit` or writes `hooksPath` into `.git/config` THEN it is denied as a hook bypass.
- WHEN a patch switches the plugin off in `.claude/settings.json`, or adds `disableAllHooks` THEN it is denied as
  settings off.
- WHEN a patch raises the level in `fences.env` THEN it passes; lowering it is a fence lowering; a hunk that is not in the
  file, or deleting the file, is a fence change.
- WHEN the guard would ask in a Codex session THEN it denies and the reason names Codex; under Claude Code the same edit
  is still asked.
- WHEN a shell command writes `.codex/hooks.json` at standard THEN it is a fence change.
- WHEN `codex execpolicy check` runs the rules on `git push --force origin main`, `git commit --no-verify`,
  `git config core.hooksPath x`, `gh pr merge 12` THEN each is `forbidden`; `git push origin feat/x`, `git commit -m x`,
  `gh pr view 12` match no rule.
