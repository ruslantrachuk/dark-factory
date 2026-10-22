export const meta = {
  name: 'feature-lite',
  description:
    'SMALL PATH of the feature pipeline: a self-contained feature end to end with 2 agents, no openspec graph and no fan-out. (1) Build — one agent: branch r{N}/<type>-<slug>-<bd-id> (the full bd id <prefix>-<hash>; no id — plain r{N}/feat-lite-<stamp>) from a fresh base (main or the train integration branch) + implementation from a ready spec by TDD + FULL gates (fast pytest suite + ruff) + commit. (2) Wrap — one agent: bd tracing + charter document sync + devlog. (3) PR — optional (push + gh pr create; merge is done after a human "accepted" via scripts/merge-feature.sh <branch> --accepted-by "<name>"). One repository: code (<appSubdir>/src, <appSubdir>/tests; appSubdir defaults to app) and harness (.beads/, devlog.md, openspec/) in one tree.',
  phases: [{ title: 'Build' }, { title: 'Wrap' }, { title: 'PR' }],
}

// --- Input (args) ---
// { request, stamp (REQUIRED — Date.now is forbidden), slug?, releaseLine? (REQUIRED in practice — never guess the line),
//   specPath? (absolute path of a ready spec), stopBeforePR?=true, noFetch?=false, assignee?, appDir? (abs. path of the tree), bdId?,
//   baseBranch?='main' (train integration branch from openspec/INTEGRATION_BRANCH — passed by the caller),
//   venv? (abs. path of a venv with pytest/ruff; default <appDir>/.venv), branchReady?=false (branch already created by the caller — feature-auto),
//   root? (abs. path of the main checkout holding the bd Dolt store; differs from appDir when using a worktree),
//   allowMigrations?=false (a chunk of a split phase that needs a migration — allowed by the calling feature-auto),
//   skipWrap?=false (a chunk of a split phase: docs, devlog and the bd note are done once at the end by the caller),
//   appSubdir?='app' (where the code lives inside the tree: <tree>/<appSubdir>/src, /tests, /.venv — base keeps it in app/;
//     '' for code at the tree root) }
// Branch: with bdId — r{N}/feat-lite-<stamp>-<bdId> (bdId is the full bd id, <prefix>-<hash>[.N]); merge-feature.sh
// takes the id only when the branch ends in -<prefix>-<id>[.N], with the project's prefix (from .beads/issues.jsonl or
// .beads/config.yaml), and closes that task. Without bdId — plainly r{N}/feat-lite-<stamp>: the tail is not
// -<prefix>-<id>, so merge-feature.sh extracts no id and closes nothing (a stamp tail like "p3" is no longer taken for
// a task id; check with `scripts/merge-feature.sh <branch> --print-bd-id`). The task Wrap creates for such a branch is
// closed by hand after the merge.
// --- Result ---
// { error, path:'lite', branch, appDir, build, wrap, pr, note }. The harness status is almost always "completed";
// the outcome is `error`: null — the branch is committed (and the PR opened when stopBeforePR=false). Otherwise:
// 'no request' | 'no stamp' | 'no release line' | 'bad appSubdir' | 'build failed' | 'gates failed' | 'wrap failed' | 'PR not opened'.
function parseArgs(x) {
  if (typeof x === 'string') {
    try {
      return JSON.parse(x) || {}
    } catch (e) {
      return {}
    }
  }
  return x || {}
}
const a = parseArgs(args)
const TREE_CMD = (cmd, dir) => String(cmd).split('{tree}').join(dir)
const REQUEST = a.request || ''
const SPEC_PATH = a.specPath || null
const REL = a.releaseLine || null
const STAMP = a.stamp
const BD_ID = a.bdId || null
// No bd id → a plain slug: merge-feature.sh finds no -<prefix>-<id> tail in it and closes nothing (see above).
const SLUG = BD_ID ? a.slug || 'feat-lite-' + STAMP + '-' + BD_ID : a.slug || 'feat-lite-' + STAMP
const STOP_BEFORE_PR = a.stopBeforePR !== false // default true: the boundary is a local commit; push/PR/merge — the session after a human "yes"
const NO_FETCH = !!a.noFetch
const ASSIGNEE = a.assignee || null
// Working tree of the run: by default the repo root (git rev-parse); in parallel runs — the absolute worktree path.
const APP = a.appDir || null
const ROOT = a.root || null // main checkout with the bd Dolt store (differs from appDir when using a worktree)
const BASE = a.baseBranch || 'main'
const VENV = a.venv || null
const BRANCH_READY = !!a.branchReady
const ALLOW_MIGRATIONS = !!a.allowMigrations
const SKIP_WRAP = !!a.skipWrap
// Code subdirectory inside the tree (base layout: app/). S is the prefix of code paths from the tree root.
const SUB = String(a.appSubdir == null ? 'app' : a.appSubdir).replace(/^\/+|\/+$/g, '')
const S = SUB ? SUB + '/' : ''

if (!REQUEST) {
  log('feature-lite: empty args.request. Pass { request, stamp, releaseLine }.')
  return { error: 'no request' }
}
if (!STAMP) {
  log('feature-lite: args.stamp is required (unique suffix). Date.now() is forbidden in scripts.')
  return { error: 'no stamp' }
}
if (!REL) {
  log('feature-lite: args.releaseLine is required (r{N} from openspec/CURRENT_TRAIN) — never guess the line (CLAUDE.md, GATE Step 1).')
  return { error: 'no release line' }
}
if (!/^[A-Za-z0-9._/-]*$/.test(SUB) || SUB.split('/').includes('..')) {
  log(`feature-lite: appSubdir "${SUB}" is not a plain relative path (e.g. 'app', or '' for code at the tree root).`)
  return { error: 'bad appSubdir' }
}
const BRANCH = REL + '/' + SLUG

const STEP_SCHEMA = {
  type: 'object',
  required: ['ok', 'summary'],
  properties: { ok: { type: 'boolean' }, summary: { type: 'string' }, details: { type: 'string' } },
}
const BUILD_SCHEMA = {
  type: 'object',
  required: ['ok', 'branch', 'filesChanged', 'testsAdded', 'gatesPassed', 'summary'],
  properties: {
    ok: { type: 'boolean' },
    branch: { type: 'string' },
    filesChanged: { type: 'array', items: { type: 'string' } },
    testsAdded: { type: 'number' },
    gatesPassed: { type: 'boolean' },
    assumptions: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    details: { type: 'string' },
  },
}

// Human-readable style for commit/PR messages.
const MSG_STYLE =
  'Message style (commit and PR): the message is addressed to a reviewer and to a future reader of the history, not to a machine. The subject states the essence of the change (Conventional Commits, in the project language — CODING_STANDARDS.md §Project language, default English — ≤~70 characters). The body is coherent prose: what changes and why. Forbidden: chains like "A → B → C"; file paths and symbol names as the main text; JSON in the text; telegraphic style with slashes and semicolons. Supporting details (tests, assumptions) go in short bullet points. No Co-Authored-By.'
const STANDARDS =
  'Standards: the project CLAUDE.md (charter, test pyramid), CODING_STANDARDS.md (layer responsibilities, prohibitions, commit format, project language), naming.yaml (project map and glossary); idiomatic code following neighbouring files in the source tree; KISS/YAGNI/external-system-honesty; comments, test descriptions and UI strings in the project language; any user-facing text only through the project message catalog' + (a.i18nFile ? ' (' + a.i18nFile + ')' : '') + '.'
const MIGRATIONS_RULE = (allowed) =>
  allowed
    ? ' An Alembic migration is allowed by the caller: additive and reversible only (new nullable columns/tables), with a db test for upgrade/downgrade.'
    : ' The small path does not create alembic migrations: if the phase needs one, return ok:false — such work goes through the full path.'
const NOCD = ' Changing directory is FORBIDDEN: no `cd` at all — not bare, not in a subshell `(cd … && …)`, not `cd … &&` — it triggers permission prompts and breaks the CWD. Always use absolute paths: `git -C`, `bd -C`, `pytest <abs path>`, `ruff check <abs path>`, `grep -rn … <abs path>`, `rg`, `find <abs path>`, `sed -n … <abs path>`, `head <abs path>`.'
// Writes go only into appDir: a dirty main checkout (ROOT) blocks scripts/merge-feature.sh,
// which runs from it. The prohibition is stated explicitly and identically for both agents
// rather than relying on the feature request author to remember it.
const WRITE_SCOPE = (dir, root) =>
  root && root !== dir
    ? ` FILE WRITES (code, docs, devlog.md, tasks.md — anything via Write/Edit) — ONLY inside ${dir}. The main checkout ${root} is used EXCLUSIVELY for reading and for \`bd -C ${root} …\` (the bd Dolt store lives there); it is also the working tree of scripts/merge-feature.sh, and any file edit there (even the same devlog.md/tasks.md already written in ${dir}) leaves it dirty and blocks other merges. If a tool asks for a path — always ${dir}/…, never ${root}/….`
    : ` FILE WRITES — ONLY inside ${dir}.`
// A background run returns before its outcome is known — such a step counts as failed.
const SYNC = ' LONG COMMANDS (pytest, ruff, npm) — ONLY synchronously: background runs (run_in_background, `&`, nohup) are forbidden; do not return a result until the run has finished and you have read its outcome. Answering "waiting for a background run" is a failed step.'
const TOPO = (dir) =>
  `TOPOLOGY: one repository, the working tree of this run is ${dir} (code ${dir}/${S}src, ${dir}/${S}tests; harness .beads/, devlog.md, openspec/ — in the same tree). All git commands — \`git -C ${dir} …\`. bd commands — \`bd -C ${ROOT || dir} …\` (Dolt store in the main checkout).`+NOCD+SYNC+WRITE_SCOPE(dir, ROOT)
const PYBIN = (dir) => VENV ? `${VENV}/bin/python` : `$([ -x ${dir}/${S}.venv/bin/python ] && echo ${dir}/${S}.venv/bin/python || echo python)`
const RUFFBIN = (dir) => VENV ? `${VENV}/bin/ruff` : `${dir}/${S}.venv/bin/ruff`
const TEST_CMD = (dir) => a.testCmd ? TREE_CMD(a.testCmd, dir) : `${PYBIN(dir)} -m pytest ${dir}/${S}tests -q --tb=short`
// A frontend with its own CI lane (if the project has one) lives in frontendDir (arg, path from the tree root, e.g.
// app/frontend); without it there is no frontend lane. npm commands take the working directory via --prefix — no cd needed.
const FE = a.frontendDir ? String(a.frontendDir).replace(/^\/+|\/+$/g, '') : null
const FRONTEND_CMD = (dir) => `npm --prefix ${dir}/${FE} run typecheck && npm --prefix ${dir}/${FE} run lint && npm --prefix ${dir}/${FE} run test:run`
const LINT_CMD = (dir) => a.lintCmd ? TREE_CMD(a.lintCmd, dir) : `${RUFFBIN(dir)} check ${dir}/${S}src ${dir}/${S}tests && ${RUFFBIN(dir)} format --check ${dir}/${S}src ${dir}/${S}tests`

// === 1. Build — ONE agent builds the whole feature by TDD ===
phase('Build')
const build = await agent(
  [
    APP ? `Working tree of the run: ${APP} (absolute path).` : 'STEP -1: determine the repo root: `git rev-parse --show-toplevel` — from now on this is ${DIR}; all commands use the absolute path.',
    SPEC_PATH
      ? `The feature spec is READY and is a PRECONDITION (written by a human BEFORE the run). Read it by the ABSOLUTE path ${SPEC_PATH}. Your job is IMPLEMENTATION strictly per the spec, by TDD (code+tests). Do NOT rewrite and do NOT commit the spec. Forks not covered by the spec → KISS/YAGNI, record them in assumptions[]. If there is NO file at the spec path — do NOT invent a design: return ok:false (the task is not ready for implementation).`
      : 'Implement the feature ENTIRELY on your own, by TDD, like an experienced developer: a short brainstorm-lite on safe defaults (forks → KISS/YAGNI, record them in assumptions[]), then code+tests.',
    TOPO(APP || '${DIR}'),
    `Request: "${REQUEST}".${BD_ID ? ` bd task: ${BD_ID}.` : ''}`,
    BRANCH_READY
      ? `STEP 0 — branch ${BRANCH} has ALREADY been created by the caller in tree ${APP || '${DIR}'}: make sure \`git -C ${APP || '${DIR}'} rev-parse --abbrev-ref HEAD\` = ${BRANCH} and the tree is clean. Do not branch again.`
      : `STEP 0 — branch: ${NO_FETCH ? `WITHOUT fetch (branch from the local origin/${BASE}): ` : `git fetch origin ${BASE}; then `}git checkout -b ${BRANCH} origin/${BASE} (in tree ${APP || '${DIR}'}; base — ${BASE}, the train integration branch from openspec/INTEGRATION_BRANCH or main). Make sure: HEAD is on ${BRANCH}, the tree is clean. If the branch already exists — ok:false with an explanation.`,
    `IMPLEMENTATION by TDD (RED→GREEN→REFACTOR): tests first, then code. Test pyramid per CODING_STANDARDS.md §Test pyramid: unit tests in ${S}tests/unit/ for logic; service-level tests in ${S}tests/integration/service/ with boundaries mocked; add db tests (@pytest.mark.db) only if the phase is a new hot path with a real DB; they are not part of the fast suite (deselected), a separate db lane and CI run them. Check the ACTUAL state of the code, not a stub. Run scoped tests as you go: \`${PYBIN(APP || '${DIR}')} -m pytest <abs path of test file> -q\`.`,
    STANDARDS + MIGRATIONS_RULE(ALLOW_MIGRATIONS),
    `FINAL — FULL gates: \`${TEST_CMD(APP || '${DIR}')}\` (fast suite, as in pre-push) + \`${LINT_CMD(APP || '${DIR}')}\`. ` + (FE ? `IF you touched the frontend (${FE}) — additionally run the frontend lane: \`${FRONTEND_CMD(APP || '${DIR}')}\` (if node_modules is missing, first \`npm --prefix ${APP || '${DIR}'}/${FE} ci\`); return the frontend test counters in details. ` : '') + `If green — commit to the branch (git add + commit). NO push, NO PR. Commit ONLY code/tests/code docs — .beads/ and devlog.md are handled by the next step.`,
    MSG_STYLE,
    'Return {ok, branch, filesChanged, testsAdded, gatesPassed, assumptions, summary, details: test counters from the real run}.',
  ].join('\n'),
  { label: 'lite-build', phase: 'Build', schema: BUILD_SCHEMA, model: 'claude-sonnet-5-5' },
)
if (!build || !build.ok) return { error: 'build failed', branch: BRANCH, build }
log(`Build: ${(build.filesChanged || []).length} files, +${build.testsAdded || 0} tests, gates ${build.gatesPassed ? 'green' : 'RED'}`)
if (!build.gatesPassed) return { error: 'gates failed', branch: BRANCH, build }
if (SKIP_WRAP) {
  log('skipWrap: the caller does the wrap-up (docs, devlog, bd) — this is a chunk of a split phase.')
  return { error: null, path: 'lite', branch: BRANCH, appDir: APP, build, wrap: null, pr: null }
}

// === 2. Wrap — ONE agent: tracing (bd) + doc sync + devlog ===
phase('Wrap')
const wrap = await agent(
  [
    `Do the process wrap-up of the finished feature (the code is already on branch ${BRANCH}, gates are green). Everything goes into the SAME branch, in the same tree (one repository).`,
    TOPO(APP || '<repo root, git rev-parse --show-toplevel>'),
    `Feature request: "${REQUEST}". What was done: ${build.summary}. Files: ${JSON.stringify(build.filesChanged)}. Assumptions: ${JSON.stringify(build.assumptions || [])}.`,
    BD_ID || ASSIGNEE
      ? `1) bd TRACING: task ${BD_ID || '(see assignee ' + ASSIGNEE + ')'} has already been claimed by the caller. Do NOT create a duplicate and do NOT close the task: scripts/merge-feature.sh closes it at merge by the full bd id at the tail of the branch name (-<prefix>-<id>). Leave it in_progress and add a note about what was done (\`bd -C ${ROOT || APP || '${DIR}'} update <id> --notes "…"\`). Do NOT commit .beads/ — merge-feature.sh carries the export.`
      : `1) bd TRACING: create ONE bd task for the feature (\`bd -C ${ROOT || APP || '${DIR}'} create --type=feature --acceptance="…"\`) — do NOT close it; leave it in_progress with a note (bd update <id> --notes). Branch ${BRANCH} carries NO bd id, so scripts/merge-feature.sh will not close this task: put its id first in details — the session closes it by hand after the merge. Then \`scripts/bd-export.sh\` — do NOT commit .beads/issues.jsonl (merge-feature.sh carries it).`,
    `2) SYNC the charter documents (ONLY if the phase touched them, per CLAUDE.md §Finishing a feature): ARCHITECTURE.md (layers, model, endpoints), naming.yaml (entities and terms), CODING_STANDARDS.md (new rules), README.md (quickstart). Separately and always: tick the completed items in the release tasks.md. Test counters — from the REAL run, not "by analogy". Not touched — state explicitly "charter documents need no changes".`,
    '3) devlog.md: an entry at the top following the project template (Done / Decisions / Open questions / Next session; an assumptions section — "decisions the machine made for you"). This item is mandatory: the pre-push gate requires a devlog entry when code is touched. Make the entry a self-contained block and end it with a `---` separator line: the file is combined with a union merge (.gitattributes), and without its own separator the entries of two branches stick together.',
    'Commit the wrap-up (docs, devlog) as a separate commit on the same branch. Do NOT commit .beads/. NO push, NO PR.',
    MSG_STYLE,
    'Return {ok, summary, details: bd task id + which docs were touched + test counters}.',
  ].join('\n'),
  { label: 'lite-wrap', phase: 'Wrap', schema: STEP_SCHEMA, model: 'claude-sonnet-5-5' },
)
if (!wrap || !wrap.ok) return { error: 'wrap failed', path: 'lite', branch: BRANCH, appDir: APP, build, wrap }

// === 3. PR — optional (boundary: open PR; merge after a human "accepted" via scripts/merge-feature.sh <branch> --accepted-by "<name>") ===
let pr = null
if (!STOP_BEFORE_PR) {
  phase('PR')
  pr = await agent(
    [
      `Push branch ${BRANCH} (git -C ${APP || '${DIR}'} push -u origin ${BRANCH}) and open a PR into ${BASE}: \`gh pr create --base ${BASE} --head ${BRANCH} --title "<title>" --body "<description>"\`. Do NOT merge (merge happens after a human "accepted": scripts/merge-feature.sh ${BRANCH} --accepted-by "<name>").`,
      'Title and description in human-readable prose: a paragraph "what changes and why" + short bullet points (tests with actual counters; assumptions — rephrase them in plain language: ' + JSON.stringify(build.assumptions || []) + '). In the description, reference the board umbrella card `Part of <umbrella card id>` if it is known from the bd task.',
      MSG_STYLE,
      'Return {ok, summary, details: link to the PR}.',
    ].join('\n'),
    { label: 'lite-pr', phase: 'PR', schema: STEP_SCHEMA, model: 'claude-sonnet-5-5' },
  )
} else {
  log('stopBeforePR: PR skipped — branch ' + BRANCH + ' is committed locally; push → PR → merge is done by a human.')
}

return {
  error: !STOP_BEFORE_PR && (!pr || !pr.ok) ? 'PR not opened' : null,
  path: 'lite',
  branch: BRANCH,
  bdId: BD_ID,
  appDir: APP,
  build,
  wrap,
  pr,
  note:
    'Small path (feature-lite): feature on branch ' +
    BRANCH +
    '. Boundary — ' +
    (STOP_BEFORE_PR ? 'local commit (no push)' : 'open PR') +
    '. Before merge, for the human: review the assumptions, green CI (full db/e2e matrix on CI) → "accepted" → scripts/merge-feature.sh ' +
    BRANCH +
    ' --accepted-by "<name of the human who said accepted>"' +
    (BD_ID ? ' (closes ' + BD_ID + ').' : '. The branch carries no bd id: merge-feature.sh closes nothing — close the task Wrap created (its id is in wrap.details) by hand after the merge.') +
    ' If CI cannot run (Actions disabled: billing, limits, an incident), the human may add --skip-ci "<reason>": the local gate runs instead and the merge is marked as made without CI (refused at FENCE_LEVEL=team).',
}
