# Open questions and settled decisions

## 1. Open questions (decide here)

1. **Several projects on one server.** Development sessions, worktrees and port lanes should not conflict by
   design, but this has not been verified with several projects working at the same time (the shared quota,
   the dev stands, one On-call session serving more than one group).
2. **The hand-over of a run.** The pipeline result carries an `error` field and the development session reports in
   its own conversation, but there is no fixed, readable hand-over format. Per feature it would hold: the branch;
   what changed; the assumptions ("decisions the machine took for you"); where a failed run stopped and what the
   human must do; a link to the dev stand. Intake has its skills (`board`, `transcript-intake`); the
   output of the pipeline needs one too.
3. **An autonomy ladder for the developer agent.** Formalise it as A1→A3: the steps are proposing a diff →
   committing to a branch → opening a PR → merging. Moving up a step depends on measured acceptance, red lines and
   reversibility.
4. **toolchain.json, "five verbs"** (lint, format, test plus SAST, deps-audit) as a stack-neutral contract for base:
   hooks and routines read the verbs from `.claude/toolchain.json` instead of the hard-coded TEST_CMD placeholders in
   pre-push.
   - The argument for it: while the test command is hard-coded in the body of `pre-push`, a project rewrites the
     whole hook for its stack and loses fixes made in the canon (for example, push-range detection and the non-HEAD
     warning).
The open questions of the map and of individual layers live next to them: [map.md](map.md) §6, [layers/](layers/).

## 2. Settled decisions (do not revisit without a new episode)

| Question | Decision |
|---|---|
| Where sessions run | a server you control, with long-lived `claude remote-control` sessions. Cloud sessions lack the chat channel, two-way messaging between sessions, and local access to hosting tools, the dev stand environment and read-only production data |
| Unattended and scheduled work | the session books it itself with native scheduling (`send_later`, `CronCreate`, scheduled tasks) |
| Coordination tools | the board for people (cards are umbrellas, claims, delivery); the execution queue for the machine; the two are not mirrored into each other ([layers/coordination.md](layers/coordination.md); the reference tools are in [functions.md](functions.md)) |
| Release acceptance format (a separate HUMAN_GATES file?) | no separate file. Release acceptance is the owner's "yes" plus `SHIPPED.md`: a header (date, PR, merge commit, card, queue epic) → what actually shipped → what was postponed and why → what review found and moved out of the branch → a retro. The format is in `plugins/dark-factory/templates/base/openspec/README.md` |
| A fleet of reviewer agents as canonical files | not needed: the canonical [review-contract.md](../plugins/dark-factory/templates/base/docs/review-contract.md) is enough. Two waves of read-only subagents catch the critical issues; there is no third wave, and the remaining findings go to the execution queue |
| Syncing the execution queue between machines | not synced: one local store per project, outside git; the record of what was done is the PR description and the merge history, and work people share is on the board (base `.beads/README.md`) |
| Auth: API key or OAuth | OAuth under a subscription |
| A restricted database in an autonomous run | no: a CI gate plus local access by a human |
| Wall-clock time as a quota regulator | no: it is a dead-man switch. The quota is handled only by the quota guard, from the server's rate-limit data |
| The cheapest model or low effort for cheap stages | no: a mid-tier model at medium effort at least |
| A live design check in the autonomous path | no: a hands-on visual check is a human acceptance step |
| "The core builds the graph from the spec" | no: preparation builds the graph; the core consumes it |
| Slimming the system brief | no: it saves about 10% at a risk to quality |
| tasks.md items in the tracker | no: a TDD micro-step lives for minutes, and its consumer is the agent |
| `merge=union` | not used: on files with line edits it causes silent corruption instead of a loud conflict |
| Splitting an epic across several branches | no: one epic = one branch and one PR |
| Archiving openspec folders | no: they stay forever as the record of why it was done this way |
| Chat mode, streaming, open-ended intent | parked ideas, with reasons |
| Layers of the factory | the method is `docs/`, the template is `plugins/dark-factory/templates/` inside the plugin (together, the public canon), your factory is a repository of your own with the registry, the machine notes and the plugin pin ([your-factory.md](your-factory.md)) |
| Rolling template improvements out to live projects | a project pins a plugin release (`"ref": "v<N>"`); `/dark-factory:factory-status` shows who is behind, and reconciling a project's files with the template (`scripts/harness-diff.sh`, base `.harness/base-sha`) is an item of the review pass |
| Pyramid: unit or integration as the base | two named profiles; **the project declares its own at deployment** (question 2 of the base MANIFEST). No answer means **unit-first** (unit tests 50–60%). Contract-first puts integration at the base, because unit tests do not catch seams such as DSN parsing, special characters in passwords or the wrong database driver. The machinery (layer = directory + auto-marker + meta-test, `pyramid.py`, the e2e skeleton) stays in base, not in a module. The ratchet guards the base share of the declared profile. Revisit the default if the ratchet gives false rejections on unit-first projects or the unit share does not grow over a series of changes; revisit "the machinery lives in base" if a project outside the Python/`app/` layout asks for it as a module |
| User guide: "later" or a gate | a gate for features with UI, **in projects with a user-facing UI, set by a flag at deployment** (question 3 of the base MANIFEST; default "yes" for an SPA, "no" for a bot or a service that packages its own help). Mechanics: GATE step 3 and "Finishing a feature", screenshots taken by a script from the e2e layer, a hash manifest, a meta-test (skipped when the folder is missing). If the guide is not on the "Finishing a feature" list, it does not get written |
| E2E: "when a seam appears", or a skeleton from day one | a skeleton in base (`tests/e2e/conftest.py`, a smoke test, a marker, a `browser` job on `workflow_dispatch` and on tags, pre-push on frontend paths). Without it, the browser layer does not run in CI at all |
| CI: the full matrix on every push, or tiers | tiers: `quick` (PR), `full` and `browser` (`workflow_dispatch`, release tag), `secret-scan` (PR, trufflehog) |
| `/dark-factory:add` mechanics: a wizard or generator, or a skill | a skill ("nothing home-grown"). Steps that have stabilised move into deterministic scripts: a procedure starts as a skill and becomes a script once it stops changing |
| Agent-level guarantees: PreToolUse guards against `--no-verify`, force-push and merge | yes, in the dark-factory plugin, which base enables. Its `guard.py` (PreToolUse) denies force push, a push to main, `--no-verify` and other ways around the git hooks, release-tag pushes outside `scripts/release.sh`, and, at the `standard` and `team` fence levels, a direct merge on the code host (`gh pr merge`) outside `merge-feature.sh`; a change to the fences runs only with a human's yes in the permission dialog and is denied to launched agents. `merge-feature.sh` merges only on green CI; `pre-push` holds the tests, and the merge script requires the PR description sections; `board` carries `disable-model-invocation: true`. The level is a deployment question (`.claude/fences.env`). Limits that stay: the guard is a seatbelt, not a sandbox; a static reader of tool calls cannot see through scripts written and then run, aliases defined elsewhere, subprocesses or arbitrary interpreters. Branch protection or rulesets on main at the code host and required reviews are the real gates ([methodology.md](methodology.md) §1.9, [threat-model.md](threat-model.md)) |
| Sandbox | the built-in Claude Code sandbox (filesystem, network allowlist, secrets for Bash) plus `permissions.deny` for Read and Edit, in base behind an explicit question at deployment ([methodology.md](methodology.md) §3); per-agent Docker or a microVM only for multi-tenancy |
| Evidence gates | a gate is executable code, in a limited form: it checks a **process invariant** (links, secrets, test layering, GATE checkboxes), not a one-off fact about a release. A one-off release gate is allowed only if it is archived no later than the next release. |
