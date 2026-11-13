# The plugin's operator commands work under Codex

## Why

The plugin's skills are visible in Codex unchanged (stage 0.5 of the plan), but they are written in Claude Code's
terms:
- commands named `/dark-factory:x`;
- commands built on `${CLAUDE_PLUGIN_ROOT}`, which Claude Code substitutes into a skill's text;
- tools that only Claude Code has (Workflow, AskUserQuestion, SendMessage, Remote Control).

A Codex session reading them would run a command with an empty plugin path, or call a tool it does not have.

## What changes

- **`AGENTS.md`** (canon block) gets one paragraph, "The plugin's commands under Codex":
  - `/dark-factory:x` is `$dark-factory:x`;
  - the plugin-root variable is the folder two levels above the skill's `SKILL.md`;
  - each Claude-only tool has its Codex path: a Workflow run → the same stages in this session by the stage skills; a
    question → plain text; another session → the role broker; remote → `codex remote-control`.

  It is one rule for every skill, hook message and doc, instead of a second copy of each text.
- **`feature`**: under Codex there is no Workflow tool. The command offers the same task in this session (session
  mode: plan → build-tdd → integrate → one review → wrap) with the file's settings, after the human's yes. A Codex
  pipeline runner is stage 4 of the plan.
- **`statusline`**: Claude Code only. Under Codex the quota comes from `codex app-server` at no cost, so there is
  nothing to wire, and the skill says so.

The other operator skills (`add`, `init`, `level`, `upgrade`, `provision-server`, `factory-status`, `vulns`) use only
shell commands and the plugin path, which the rule covers.

## Decisions

- **No second set of skill texts.** Codex reads `AGENTS.md` directly. One translation rule there costs less than
  forking every skill, and it stays true as skills change.
- **The plugin-root variable is not rewritten in the skills.** Claude Code substitutes it, and the repository test
  requires that it appears only in `SKILL.md` bodies.

## Acceptance

- WHEN a Codex session runs a plugin skill whose command uses the plugin-root variable THEN `AGENTS.md` tells it how
  to resolve the path from the skill's location.
- WHEN `/dark-factory:feature` is invoked under Codex THEN the skill offers the run in this session instead of calling
  Workflow.
- WHEN `/dark-factory:statusline` is invoked under Codex THEN the skill says there is nothing to wire and stops.

Not checked live: a Codex model turn running a skill. The sandbox has no Codex login, because copying `auth.json` was
refused.
