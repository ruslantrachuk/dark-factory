# Tasks: codex-quota

## Phase 1 — the Codex source

- [x] `quota.py`: `use_agent` (per-agent cache, log, notices, title), `codex_probe` through `codex app-server`,
      `parse_codex` (windows by length, label, `ordinaryUsageAllowed` → denied)
- [x] `stage` / `reopen_at` / `format_line` read the window's own label and the denied entry; the Codex resume hint
- [x] `spawn_agent` is new work; `--agent codex` / `QUOTA_AGENT` for the human modes; the background refresh keeps the agent
- [x] the agent-codex silence removed; the module's manifest says how Codex is measured
- [x] tests: `CodexQuotaTest` (Plus, free, denied, hint, a fake app-server), the Codex session in `ProjectTest`
- [x] live: `quota.py status --agent codex` on this server's Codex login
