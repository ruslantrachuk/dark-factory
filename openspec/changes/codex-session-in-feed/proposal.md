# Who works on a project, and the way into its Codex session

## Why

The status page showed a "Codex" tag while Codex worked on a project and a link into the Claude development session,
but nothing to get into the Codex session itself, and nothing per project about the broker's roles. Codex has no web
link to one CLI session: a thread opens by `codex resume <thread id>` on the machine that holds it, through the
ChatGPT app's Remote list when remote control is on, or — Mac desktop app only, for threads it holds — by
`codex://threads/<id>` (openai/codex `codex-rs/tui/src/app/history_ui.rs`). `chatgpt.com/codex/tasks/<id>` is for
Codex Cloud tasks, not CLI threads.

## What changes — additive, the document stays `"version": 2`

- **`projects[].codex.session`**: the newest interactive Codex session of the project (a rollout whose
  `session_meta.source` is `cli`, the TUI; `codex exec` runs are not sessions), `null` when there is none in 14 days:
  `{"thread_id", "cwd", "working", "last_at"}`. `thread_id` is the id `codex resume` takes.
- **Status page, a project's screen:** a new **Agents** section — the Claude session (working or idle, the claude.ai
  link), running subagents, Codex (working, last worked), the Codex session as `codex resume <id>` copied on a tap with
  the ChatGPT-app hint, and the broker's roles of the project (`<project>/<role>`: agent, held, waiting, dead). The
  project row shows a "Claude" tag next to "Codex" when both work.

## Acceptance

- WHEN a project has a TUI Codex session and a newer `codex exec` run THEN `codex.session.thread_id` is the TUI
  session's id and `codex.last_worked_at` is the run's time.
- WHEN the owner taps the Codex session row THEN `codex resume <id>` is on the clipboard (selected, if the browser
  refuses the clipboard).
- WHEN the broker has roles `<project>/…` THEN the project's screen lists them with their agent.
