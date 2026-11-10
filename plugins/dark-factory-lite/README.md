# Dark Factory Lite

The working method of the [dark-factory](https://github.com/ruslantrachuk/dark-factory) plugin as plain skills and
roles for Claude Code: size a request before any code, plan it in end-to-end slices, build each slice test first,
commit only after its tests, and leave the pull request as the record of the work. No hooks, no scripts, nothing that
runs on its own: every step is text Claude reads, and every command it runs goes through your usual permission prompt.

Install it from the Claude plugin directory, or from this repository's marketplace (`dark-factory-lite` in the
`ruslantrachuk/dark-factory` marketplace).

## What is inside

| Skill | Use when |
|---|---|
| `size-task` | a request starts new work: says trivial, small or large, names the branch and phases, waits for your ok |
| `wsjf` | scoring or ranking work by WSJF: business value, time criticality, risk reduction over job size |
| `plan` | an approved change is about to be built: slices with their files, tests, acceptance and dependencies |
| `build-tdd` | a planned slice is next: a failing test first, then the code, then the refactor |
| `integrate` | built code is about to be committed: its tests and lint first, one commit per slice |
| `wrap` | the branch is done: the pull request description in `## Done`, `## Decisions`, `## Open questions` |

| Role (agent) | What it does |
|---|---|
| `tech-lead` | sizes and shapes work, critiques a plan against the code, scores job size; read-only |
| `product-owner` | judges a task from the product side, writes WHEN/THEN acceptance scenarios, scores value; read-only |
| `reviewer` | a fresh-context review of a diff or branch through one lens at a time; never edits |
| `builder` | builds a planned slice by `build-tdd`, commits it by `integrate`, wraps up by `wrap` |

The skills work in any git repository. When the project has more of the factory — a bd task queue, OpenSpec change
folders, `scripts/merge-feature.sh` — they use it; without it they say what to do instead.

## How it is checked

Each skill has cases for `claude plugin eval` in the [dark-factory repository](https://github.com/ruslantrachuk/dark-factory/tree/main/plugins/dark-factory/evals)
(they are not shipped here): a plain request it must answer, a near-miss it must leave alone, and its behaviour — no code before the ok, a test run before the code changes, tests before a commit, the three
sections of the description, no secret from a local `.env` in an answer. They run in CI on every change to a skill.

## What it does not do

The light edition only asks. The full [dark-factory](https://github.com/ruslantrachuk/dark-factory) plugin holds the
same rules with hooks (no force push or push to main, merges only on green CI, a subscription quota guard) and adds a
feature pipeline, releases of accepted work only, and an on-call agent. Install one or the other in a project, not
both: the full plugin carries the same skills.

## Data

The plugin sends nothing anywhere and stores nothing; it reads the files of the repository you open it in, as Claude
does. Privacy: [PRIVACY.md](https://github.com/ruslantrachuk/dark-factory/blob/main/PRIVACY.md).
