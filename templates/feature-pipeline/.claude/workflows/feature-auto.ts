export const meta = {
  name: 'feature-auto',
  description:
    'Automated development for <project> from a ready requirements source to a committed branch (optionally an open PR). Source: a phase of an approved OpenSpec change (changeDir + phase), a ready spec (specPath) or a bd bug (task description). Setup (branch r{N}/<type>-<slug>-<bd-id> from the base — main or the train integration branch from openspec/INTEGRATION_BRANCH; a git worktree when appDir ≠ root) → Plan (decomposition into bd subtasks with files[]/testPlan) → Critic → Bridge (subtasks as children of the bd task, claimed by the owner) → Build (feature-core: waves → integrate → review → fix) → Integrate (merge the base, FULL pytest+ruff gates, charter document sync, devlog, bd close of subtasks, bd export) → PR (optional; merge is done by a human via scripts/merge-feature.sh). Forks → automatic defaults + assumptions. A small feature → delegated to feature-lite. One repository, GitHub.',
  phases: [
    { title: 'Setup' },
    { title: 'Plan' },
    { title: 'Split', detail: 'phase wider than the threshold or not agreed — split into end-to-end slices' },
    { title: 'Chunks', detail: 'split chunks via the small path on one branch; review once' },
    { title: 'Critic' },
    { title: 'Bridge' },
    { title: 'Build' },
    { title: 'Integrate' },
    { title: 'PR' },
  ],
}

// --- Input (args) ---
// { request (REQUIRED), stamp (REQUIRED — Date.now is forbidden), releaseLine (REQUIRED — r{N}, never guess),
//   bdId (REQUIRED — the run's parent bd task: a phase task or a bug; subtasks are created as its children; the branch
//   ends with this id — merge-feature.sh closes by it), slug? (default: <type>-auto-<stamp>-<bdId>),
//   type?='feat'|'fix', baseBranch?='main' (train integration branch — from openspec/INTEGRATION_BRANCH; passed by
//   the caller), appDir? (default: <session dir>/.claude/worktrees/fab-<slug> — git worktree add; ONLY inside
//   the session dir, a path outside → error: external directories cause a permission prompt on every file;
//   equal to the session dir → checkout -b in it), venv? (abs. path of the
//   venv; default <root>/.venv), changeDir?+phase? (OpenSpec change from the repo root + tasks.md phase number) | specPath?
//   (abs. path of the spec) | (neither → bug/task from the bd description), stopBeforePR?=true, noFetch?=false,
//   assignee? (owner scope; default auto-<stamp>), path?='lite'|'full', dbTests?=false, allowMigrations?=false,
//   dbShards? (db lane paths from the tree root, default ['tests/integration/db']; a lane longer than 600 s — split into shards,
//     e.g. ['<test shard glob 1>', '<test shard glob 2>']),
//   root? (abs. path of the main checkout — bd Dolt store; otherwise git rev-parse), maxRounds?, coreScript?, liteScript?
//   (default — <session dir>/.claude/workflows/: Workflow runs scripts only from the session dir),
//   ignoreSizeGate? (do not measure scope — the phase has already been split by the caller),
//   manualChunks?=false (on a split, return the proposal to the caller instead of running the chunks itself),
//   allowOverlap?=false (do not stop if the plan's files are being edited by another unmerged branch),
//   reviewDims? (which review lenses to run: 'tests' | 'invariants' | 'simplify'; all three by default.
//     On intermediate chunks of a split phase ['tests','invariants'] is reasonable — simplify looks at the shape
//     of the code, which is not final until the last chunk; it runs once, on the last chunk) }
// --- Result ---
// The harness status of a run is almost always "completed"; the outcome is the `error` field of the returned object.
// error: null — the branch is committed (and the PR opened when stopBeforePR=false). Any other value is a failure or
// an incomplete run: 'no request' | 'no stamp' | 'no release line' | 'no bdId' | 'no phase' | 'repo-root resolve failed' |
// 'appDir outside session dir' | 'setup failed' | 'plan failed' | 'migration required but not allowed' |
// 'overlaps in-flight branch' | 'phase too large — split proposed' | 'decomposition rejected by critic' |
// 'decomposition rejected — split proposed' | 'replan failed' | 'bridge failed' | 'core failed: …' | 'chunk <key> failed' |
// 'integrate failed' | 'incomplete: …' (subtasks not implemented, review blockers left, PR not opened). The small path
// returns the result of feature-lite, which follows the same contract.
// IMPORTANT: the Workflow tool passes args as a JSON STRING — parse it if it is a string.
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
const REQUEST = a.request || ''
const STAMP = a.stamp
const REL = a.releaseLine || null
const BD_ID = a.bdId || null
const TYPE = a.type === 'fix' ? 'fix' : 'feat'
const SLUG = a.slug || `${TYPE}-auto-${STAMP}-${String(BD_ID || '').replace(/[^a-z0-9.]+/gi, '-').toLowerCase()}`
const BASE = a.baseBranch || 'main'
const APP_ARG = a.appDir || null
const VENV_ARG = a.venv || null
const CHANGE_DIR = a.changeDir || null
const PHASE = a.phase != null ? String(a.phase) : null
const SPEC_PATH = a.specPath || null
const STOP_BEFORE_PR = a.stopBeforePR !== false // default true: the boundary is a local commit; push/PR/merge — a human
const NO_FETCH = !!a.noFetch
const FORCE_PATH = a.path || null
const DB_TESTS = !!a.dbTests
const DB_SHARDS = Array.isArray(a.dbShards) && a.dbShards.length ? a.dbShards : ['tests/integration/db']
const ALLOW_MIGRATIONS = !!a.allowMigrations
const MAX_ROUNDS = a.maxRounds || 20
// run scope: subtasks are assigned to OWNER, the core takes the children of BD_ID (not everything in_progress) — nothing foreign leaks in.
const OWNER = a.assignee || 'auto-' + STAMP

if (!REQUEST) {
  log('feature-auto: empty args.request.')
  return { error: 'no request' }
}
if (!STAMP) {
  log('feature-auto: args.stamp is required (unique suffix). Date.now() is forbidden in scripts.')
  return { error: 'no stamp' }
}
if (!REL) {
  log('feature-auto: args.releaseLine is required (r{N} from openspec/CURRENT_TRAIN) — never guess (CLAUDE.md, GATE Step 1).')
  return { error: 'no release line' }
}
if (!BD_ID) {
  log('feature-auto: args.bdId is required — the run\'s parent bd task (branch r{N}/<type>-<slug>-<bd-id>, merge-feature.sh closes by the tail).')
  return { error: 'no bdId' }
}
if (CHANGE_DIR && !PHASE) {
  log('feature-auto: changeDir requires phase (the tasks.md phase number).')
  return { error: 'no phase' }
}

const BRANCH = REL + '/' + SLUG
const STEP_SCHEMA = {
  type: 'object',
  required: ['ok', 'summary'],
  properties: { ok: { type: 'boolean' }, summary: { type: 'string' }, details: { type: 'string' } },
}
const PLAN_SCHEMA = {
  type: 'object',
  required: ['title', 'tasks', 'assumptions', 'requirementMap', 'migrationNeeded'],
  properties: {
    title: { type: 'string' },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['key', 'title', 'files', 'testPlan', 'acceptance', 'blockedBy'],
        properties: {
          key: { type: 'string' }, // local key (e.g. "3.1") — for blockedBy before bd ids exist
          title: { type: 'string' },
          description: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          testPlan: { type: 'string' },
          acceptance: { type: 'string' },
          blockedBy: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    assumptions: { type: 'array', items: { type: 'string' } },
    requirementMap: {
      type: 'array',
      items: {
        type: 'object',
        required: ['requirement', 'tasks'],
        properties: { requirement: { type: 'string' }, tasks: { type: 'array', items: { type: 'string' } } },
      },
    },
    migrationNeeded: { type: 'boolean' },
    details: { type: 'string' },
  },
}
const CRITIC_SCHEMA = {
  type: 'object',
  required: ['approved', 'issues'],
  properties: { approved: { type: 'boolean' }, issues: { type: 'array', items: { type: 'string' } } },
}
const BRIDGE_SCHEMA = {
  type: 'object',
  required: ['ok', 'summary', 'ids'],
  properties: { ok: { type: 'boolean' }, summary: { type: 'string' }, ids: { type: 'array', items: { type: 'string' } }, details: { type: 'string' } },
}

// Model layout is a project decision: the main session model is NOT inherited by subagents. Mechanics (root, branch,
// triage, bd writes) — Sonnet/medium; plan and critic — Opus (architectural decisions, fresh context); final
// integration (merge, gates, devlog) — Sonnet. Models ONLY by full id: an alias can resolve to an older model.
// A project may put every role on Sonnet to save tokens.
const SIMPLE = { model: 'claude-sonnet-5-5', effort: 'medium' }
const WORKER = { model: 'claude-sonnet-5-5' }
const ARCHITECT = { model: 'claude-opus-5-5' }
const MSG_STYLE =
  'Message style (commit and PR): addressed to a reviewer and a future reader of the history, not to a machine. Subject — the essence of the change (Conventional Commits, in the project language — CODING_STANDARDS.md §Project language, default English — ≤~70 characters). Body — coherent prose: what changes and why. Forbidden: chains "A → B → C"; file paths and symbol names as the main text; JSON in the text; telegraphic style. Details (tests, assumptions) — short bullet points. No Co-Authored-By.'

// === 0. Setup: repo root → working tree → branch from a fresh base ===
phase('Setup')
// The session directory (its cwd) is the only zone where agents work without permission prompts and where Workflow
// runs nested scripts. feature-core/feature-lite are taken from it and the run's working tree is created in it.
const topStep = await agent(
  'Run `git rev-parse --show-toplevel` (no cd) and return {ok:true, summary: absolute path of the repository root}.',
  { label: 'repo-root', phase: 'Setup', schema: STEP_SCHEMA, ...SIMPLE },
)
if (!topStep || !topStep.ok) return { error: 'repo-root resolve failed' }
const SESSION_TOP = topStep.summary.trim().replace(/\/+$/, '')
const ROOT = (a.root || SESSION_TOP).replace(/\/+$/, '')
const APP = (APP_ARG || `${SESSION_TOP}/.claude/worktrees/fab-${SLUG}`).replace(/\/+$/, '')
if (APP !== SESSION_TOP && !APP.startsWith(SESSION_TOP + '/')) {
  log(`feature-auto: appDir ${APP} is outside the session dir ${SESSION_TOP} — agents would get a permission prompt on every file. Do not pass appDir (default ${SESSION_TOP}/.claude/worktrees/fab-<slug>) or give a path inside the session.`)
  return { error: 'appDir outside session dir', appDir: APP, sessionDir: SESSION_TOP }
}
const USE_WORKTREE = APP !== ROOT && APP !== SESSION_TOP
const VENV = VENV_ARG || `${ROOT}/.venv`
const CHANGE_ABS = CHANGE_DIR ? `${ROOT}/${String(CHANGE_DIR).replace(/^\/+/, '').replace(/\/+$/, '')}` : null
const CORE_SCRIPT = a.coreScript || `${SESSION_TOP}/.claude/workflows/feature-core.ts`
const LITE_SCRIPT = a.liteScript || `${SESSION_TOP}/.claude/workflows/feature-lite.ts`

const NOCD = ' Changing directory is FORBIDDEN: no `cd` at all — not bare, not in a subshell `(cd … && …)`, not `cd … &&` — it triggers permission prompts and breaks the CWD. Always use absolute paths: `git -C`, `bd -C`, `pytest <abs path>`, `ruff check <abs path>`, `grep -rn … <abs path>`, `rg`, `find <abs path>`, `sed -n … <abs path>`, `head <abs path>`.'
// A background run returns before its outcome is known — such a step counts as failed.
const SYNC = ' LONG COMMANDS (pytest, ruff, npm) — ONLY synchronously: background runs (run_in_background, `&`, nohup) are forbidden; do not return a result until the run has finished and you have read its outcome. Answering "waiting for a background run" is a failed step.'
const TOPO = `TOPOLOGY: one repository. The run's working tree is ${APP} (code src/, tests/, alembic/; harness .beads/, devlog.md, openspec/ — in the same tree). git — \`git -C ${APP} …\`, tests — \`${VENV}/bin/python -m pytest ${APP}/tests/… -q\`. bd — \`bd -C ${ROOT} …\`.`+NOCD+SYNC
// A user-visible feature covers every project surface, not only the one the request came from.
// The surface completeness gate is openspec/README.md §0.
// The list of surfaces is per project (<project surfaces>) and is filled in at deployment.
const SURFACES = ' SURFACES: a user-visible feature must have an "Interaction surfaces" section in proposal.md — for each project surface (<project surfaces: e.g. chat with the bot, mini app, web version, outbound messages from the bot>) the entry point, action and result, or an explicit "not here", confirmed by the requester or the owner; and a "Transition tree" in design.md. No section or no confirmation — STOP with the error "no decision on interaction surfaces"; do not plan and do not fill in the gaps.'
const SOURCE = CHANGE_ABS
  ? `REQUIREMENTS SOURCE — the approved OpenSpec change ${CHANGE_ABS}: proposal.md, design.md (decisions, state model, as-is with file:line), specs/*/spec.md (MUST requirements with scenarios), tasks.md — section "Phase ${PHASE}" (items ${PHASE}.1, ${PHASE}.2, …). ONLY this phase is implemented; do not touch other phases. Do NOT rewrite the spec.`+SURFACES
  : SPEC_PATH
    ? `REQUIREMENTS SOURCE — the ready spec ${SPEC_PATH} (written by a human BEFORE the run; a precondition). If the file does not exist — return an error, do not invent a design.`+SURFACES
    : `REQUIREMENTS SOURCE — the description of bd task ${BD_ID} (\`bd -C ${ROOT} show ${BD_ID}\`): a bug/task with evidence and repro; there is no spec. For a bug — systematic-debugging: reproduce with a test (RED), find the root cause, fix.`

const setupGit = USE_WORKTREE
  ? `${NO_FETCH ? '' : `git -C ${SESSION_TOP} fetch origin ${BASE}; then `}create a SEPARATE git worktree: \`git -C ${SESSION_TOP} worktree add -b ${BRANCH} ${APP} origin/${BASE}\`. Make sure: HEAD in ${APP} is on ${BRANCH}, the tree is clean (\`git -C ${APP} status --porcelain\` is empty, except gitignored files).`
  : `${NO_FETCH ? '' : `git -C ${APP} fetch origin ${BASE}; then `}\`git -C ${APP} checkout -b ${BRANCH} origin/${BASE}\`. Make sure: HEAD is on ${BRANCH}, the tree is clean.`
const setup = await agent(
  [
    `Create feature branch ${BRANCH} from the fresh base origin/${BASE} (CLAUDE.md canon: r{N}/<type>-<slug>-<bd-id>; the bd id at the tail is mandatory).`,
    setupGit,
    `IDEMPOTENCY (run resume): if branch ${BRANCH} already exists AND tree ${APP} is already on it (\`git -C ${APP} rev-parse --abbrev-ref HEAD\`) AND the tree is clean — this is a repeated Setup: create nothing, return ok:true.`,
    // A tree left over from the previous chunk of the train is normal, not a breakage: after
    // the merge it is switched to detached on the base branch and reused.
    `TREE REUSE: if path ${APP} is already registered as a worktree, branch ${BRANCH} does not exist yet, and the tree is CLEAN (\`git -C ${APP} status --porcelain\` is empty) and sits on a detached HEAD or on the base branch — do NOT delete it and do not ask for another path: just create the branch in place, \`git -C ${APP} switch -c ${BRANCH} origin/${BASE}\`. This is a normal case: the tree is left over from the previous chunk of the same train.`,
    `ok:false with an explanation — only if the tree is DIRTY, or is occupied by SOMEONE ELSE'S feature branch (neither ${BRANCH} nor the base), or branch ${BRANCH} exists but the tree is on a different branch. No cd — only git -C.`,
    `Return {ok, summary, details: branch name, base SHA, tree path}.`,
  ].join('\n'),
  { label: 'setup', phase: 'Setup', schema: STEP_SCHEMA, ...SIMPLE },
)
if (!setup || !setup.ok) return { error: 'setup failed', branch: BRANCH, setup }
log(`Setup: branch ${BRANCH} from origin/${BASE}, tree ${APP}${USE_WORKTREE ? ' (worktree)' : ''}`)

// === 0b. Scale gating: a small self-contained task → feature-lite (the small path is ~5× cheaper). An explicit path skips triage. ===
if (FORCE_PATH !== 'full') {
  let route = FORCE_PATH
  if (!route) {
    const triage = await agent(
      [
        `Classify the work: "small path" (lite) or "full" (orchestration). Request: "${REQUEST}". ${SOURCE}`,
        `Look at the ACTUAL code in ${APP}/src and estimate: how many files it will really touch; is there a contract change (DB migration / API / user flow / new service); does it split into several parallel tasks with disjoint files.`,
        'Rule: lite — if ALL are "yes": ≤~5 files (with tests), no migration and no contract change, does not split into parallel tasks. Otherwise full.',
        'Return {ok:true, summary:"lite" OR "full", details: justification}. No cd — absolute paths.',
      ].join('\n'),
      { label: 'triage', phase: 'Setup', schema: STEP_SCHEMA, ...SIMPLE },
    )
    route = triage && /^\s*lite\b/i.test(triage.summary) ? 'lite' : 'full'
    log('Scale gating: path "' + route + '"' + (triage && triage.details ? ' — ' + triage.details : ''))
  }
  if (route === 'lite') {
    log('Delegating to feature-lite (small path) — the branch already exists, feature-lite reuses it (branchReady).')
    const lite = await workflow(
      { scriptPath: LITE_SCRIPT },
      {
        request: REQUEST + (CHANGE_ABS ? ` (OpenSpec ${CHANGE_ABS}, phase ${PHASE})` : ''),
        stamp: STAMP,
        slug: SLUG,
        releaseLine: REL,
        baseBranch: BASE,
        specPath: SPEC_PATH || (CHANGE_ABS ? `${CHANGE_ABS}/tasks.md` : null),
        stopBeforePR: STOP_BEFORE_PR,
        noFetch: true,
        branchReady: true,
        assignee: OWNER,
        appDir: APP,
        root: ROOT,
        venv: VENV,
        bdId: BD_ID,
      },
    )
    return lite || { error: 'feature-lite returned no result', branch: BRANCH }
  }
}

// === 1. Plan — decompose the source into run subtasks (files[] disjoint within a wave, TDD pairs test+code) ===
phase('Plan')
const plan = await agent(
  [
    `Plan the implementation of "${REQUEST}" (bd task ${BD_ID}) as a graph of subtasks for parallel agents. Read CLAUDE.md and CODING_STANDARDS.md (${APP}), then the source. ${SOURCE}`,
    TOPO,
    `Check the ACTUAL state of the code in ${APP}/src (existing repositories, services, dispatchers, settings in config, scheduled jobs, alembic/versions) — plan edits to real files, not imagined ones. Cross-check with the design.md "as-is" (file:line), if present.`,
    'GRANULARITY: fewer, file-coherent tasks. A task = test file(s) + code file(s) that are always edited together (a TDD pair). Split ONLY along real boundaries: different files (disjointness for parallelism) or a dependency (migration+repository are needed by the service; the service is needed by the dispatchers). Within one wave files[] do NOT overlap; express overlap via blockedBy. Do not breed micro-tasks of 1 file where they are inseparable. A file edited by two tasks goes into one of them, the other is blockedBy.',
    'Each task: key (e.g. "3.1"), title (in the project language, ≤70), description (what exactly to do, grounded in the spec requirements — requirement id/name), files[] (paths from the repo root, including NEW files and test files), testPlan (test pyramid levels per CODING_STANDARDS.md §Test pyramid: unit / service with boundaries mocked / db @pytest.mark.db for a hot path with a real DB — what exactly is verified), acceptance (verifiable criteria), blockedBy[] (keys).',
    // Test paths written from memory and method names that do not exist in the code are the
    // commonest critic remarks. The check is mandatory and cheap.
    `VERIFICATION BEFORE RETURNING (mandatory, otherwise the plan will be rejected): check every existing-file path in files[] on disk (\`ls\` by absolute path from ${APP}); look up test files via \`find ${APP}/tests -name "<name>"\` — suites live both in tests/unit and in tests/integration/service, and mixing them up means creating a duplicate instead of extending. Find every method, field and function named in description or acceptance in the code (\`grep -rn "def <name>" ${APP}/src\`) — if the method does not exist, name the existing one or create a task to add it. Every message catalog key a consumer task will need must be introduced by a task that edits the message catalog (<i18n file>): the list of keys must cover ALL snapshots and branches named in the source.`,
    'SINGLE EDIT NODE: if the edit has to be made on a path reached by several entry points (a shared dispatcher, a ladder of branches, a handler after disambiguation), name the shared node in the description, not the individual branches, and pin the behaviour at every entry point with a separate test case.',
    'At ANY fork — a safe default (KISS/YAGNI; train flags default to false, the old path is kept behind the flag) and record it in assumptions[]. Do NOT ask — this is automatic mode. Do NOT write code and do NOT commit.',
    `migrationNeeded=true if an alembic migration is needed. ${ALLOW_MIGRATIONS ? 'Migrations are allowed (per the spec).' : 'Migrations are FORBIDDEN in this run — if it cannot be done without one, still return the plan with migrationNeeded=true (the orchestrator will stop).'}`,
    'requirementMap: requirement (a MUST from the spec / a tasks.md item / a bug acceptance criterion) → keys of the tasks that close it. Return {title, tasks, assumptions, requirementMap, migrationNeeded, details}.',
  ].join('\n'),
  { label: 'plan', phase: 'Plan', schema: PLAN_SCHEMA, ...ARCHITECT },
)
if (!plan || !plan.tasks || plan.tasks.length === 0) return { error: 'plan failed', branch: BRANCH, plan }
log(`Plan: "${plan.title}", ${plan.tasks.length} tasks, ${plan.requirementMap.length} requirements, ${plan.assumptions.length} assumptions${plan.migrationNeeded ? ', migration needed' : ''}`)
if (plan.migrationNeeded && !ALLOW_MIGRATIONS) {
  log('feature-auto: the plan needs an alembic migration while allowMigrations=false — stop; rerun with allowMigrations:true if the spec allows a migration.')
  return { error: 'migration required but not allowed', branch: BRANCH, plan }
}

// === 1a. Overlap with parallel work. ===
// Two features built at the same time on shared code introduce the same schema or helper twice —
// a merge conflict and manual cleanup of duplicates. The shared layer is built first, the second
// feature builds on top of it. We compare code (src/, tests/, alembic/), not docs: devlog,
// naming, the message catalog and openspec merge normally.
const OVERLAP_SCHEMA = {
  type: 'object',
  required: ['overlaps'],
  properties: {
    overlaps: {
      type: 'array',
      items: { type: 'object', required: ['branch', 'files'], properties: { branch: { type: 'string' }, files: { type: 'array', items: { type: 'string' } } } },
    },
  },
}
const PLAN_CODE_FILES = [...new Set(plan.tasks.flatMap((t) => t.files || []))].filter((f) => /^(app\/)?(src|tests|alembic)\//.test(f) && !/resources\/messages\//.test(f))
if (!a.allowOverlap && PLAN_CODE_FILES.length) {
  const ov = await agent(
    [
      `Find local branches NOT merged into origin/${BASE}, other than ${BRANCH}: \`git -C ${APP} for-each-ref --format='%(refname:short)' refs/heads/\` and for each one \`git -C ${APP} merge-base --is-ancestor <branch> origin/${BASE}\` (exit code 0 — already in the base, skip) and \`git -C ${APP} merge-base --is-ancestor <branch> HEAD\` (exit code 0 — already merged into this branch, skip).`,
      `For each unmerged one: \`git -C ${APP} diff --name-only origin/${BASE}...<branch>\` and its intersection with the plan files: ${JSON.stringify(PLAN_CODE_FILES)}.`,
      'Return {overlaps:[{branch, files: intersection}]} only for branches with a non-empty intersection; none — {overlaps:[]}. Change nothing.' + NOCD,
    ].join('\n'),
    { label: 'overlap', phase: 'Plan', schema: OVERLAP_SCHEMA, ...SIMPLE },
  )
  const overlaps = (ov && ov.overlaps) || []
  if (overlaps.length) {
    log(`Overlap with unmerged work: ${overlaps.map((o) => `${o.branch} (${o.files.join(', ')})`).join('; ')} — merge that branch first (or merge it into this one), then restart; to continue deliberately — allowOverlap:true`)
    return { error: 'overlaps in-flight branch', branch: BRANCH, overlaps, plan }
  }
}

// === 1b. Phase size. ===
// The critic can say "the plan is bad" but not "the task is the wrong size": on a wide phase
// every round finds a NEW behaviour branch, and no plan lists them all in one go. So the scope
// is measured before the critic and, if the phase is too wide, the phase is split.
const SPLIT_SCHEMA = {
  type: 'object',
  required: ['chunks'],
  properties: {
    chunks: {
      type: 'array',
      items: {
        type: 'object',
        required: ['key', 'title', 'request', 'files'],
        properties: {
          key: { type: 'string' },
          title: { type: 'string' },
          request: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          dependsOn: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    rationale: { type: 'string' },
  },
}
const planFiles = new Set()
for (const t of plan.tasks) for (const f of t.files || []) planFiles.add(f)
// Only the amount of work is measured — tasks and files. The number of requirements is not a size:
// a small chunk can close many requirements with a few tasks.
const OVERSIZED = plan.tasks.length > 8 || planFiles.size > 25
if (OVERSIZED && !a.ignoreSizeGate) {
  phase('Split')
  log(`Phase size: ${plan.tasks.length} tasks, ${planFiles.size} files, ${(plan.requirementMap || []).length} requirements — above the threshold, proposing a split`)
  const split = await agent(
    [
      `Phase "${plan.title}" for "${REQUEST}" is too wide for one run: ${plan.tasks.length} tasks, ${planFiles.size} files, ${(plan.requirementMap || []).length} requirements. ${SOURCE}`,
      TOPO,
      'Plan: ' + JSON.stringify({ tasks: plan.tasks, requirementMap: plan.requirementMap }),
      'Split the phase into 2–4 SEQUENTIAL chunks on one branch. A good split is thin END-TO-END slices: each chunk, after its commit, works from the entry point (webhook, route, dispatcher) to the result for at least its own scenario and is covered by a test at the entry level; the first chunk is the narrowest working scenario in full (with the migration, if one is needed), the following ones extend it. A bad split is by layers (data → sending → wizard → dispatcher) or "all tests first, then code": between chunks the feature is not wired up, and a dead path passes all tests.',
      'For each chunk: key (e.g. "5a"), title (in the project language), request (the full request text for a separate run — self-contained, with the source requirements this chunk closes), files[] (which files it touches), dependsOn[] (keys of chunks that must be merged earlier).',
      'Chunk boundaries by file should overlap minimally: a file edited by two chunks goes to the earlier one. Return {chunks, rationale}.',
    ].join('\n'),
    { label: 'split', phase: 'Split', schema: SPLIT_SCHEMA, ...ARCHITECT },
  )
  if (split && split.chunks && split.chunks.length > 1) {
    if (a.manualChunks) {
      log(`Split: ${split.chunks.map((c) => c.key).join(', ')} — manualChunks: the caller starts the runs one by one`)
      return { error: 'phase too large — split proposed', branch: BRANCH, plan, split }
    }
    return await runChunks(split.chunks, 'phase wider than the threshold')
  }
  log('Split failed — going to the critic as is')
}

// === 2. Critic — replaces the human approval of the breakdown. Small plan (≤2 tasks, ≤3 assumptions, no migration) → skip. ===
phase('Critic')
const SMALL_PLAN = plan.tasks.length <= 2 && plan.assumptions.length <= 3 && !plan.migrationNeeded
let critic = SMALL_PLAN ? { approved: true, issues: [] } : null
if (SMALL_PLAN) log(`Critic: small plan (${plan.tasks.length} tasks, ${plan.assumptions.length} assumptions) → critic skipped`)
let planFinal = plan
// Three rounds: the critic finds something new on every pass, and one re-plan is rarely enough.
const CRITIC_ROUNDS = 3
for (let attempt = 0; !SMALL_PLAN && attempt < CRITIC_ROUNDS; attempt++) {
  critic = await agent(
    [
      `Independent review of the plan "${planFinal.title}" for "${REQUEST}" (replaces a human approval). ${SOURCE}`,
      TOPO,
      'Plan: ' + JSON.stringify({ tasks: planFinal.tasks, requirementMap: planFinal.requirementMap, assumptions: planFinal.assumptions }),
      'Check: (1) COVERAGE — every MUST requirement of the phase/spec and every tasks.md item of the phase is closed by a task; the acceptance criteria of the bd task (`bd show`) are covered by testPlan; (2) GRANULARITY — no monoliths and no empty tasks, TDD pairs test+code in one task; (3) FILES — within a wave (tasks without mutual blockedBy) files[] do not overlap, paths are real (existing files exist, new ones are in the right layer); (4) DEPENDENCIES are correct and acyclic; (5) PREMISE — the plan does not contradict the actual code and the anti-patterns of CLAUDE.md / CODING_STANDARDS.md, flags default to false, the old path is kept; (6) assumptions do not override decisions already made in design.md/proposal; (7) SWITCH-OFF AND REUSE — for every endpoint and every piece of stored user data, the behaviour with the flag off/on rollback is defined (revoking and deleting what the user saved — secrets, connections — works regardless of the flag); for limiters, clients, helpers the plan uses the ones that already exist in the code (find them by search) rather than writing its own; (8)' + SURFACES + ' A plan that covers only part of the surfaces in the section — do not approve.',
      'Return {approved, issues[]}. approved=false on any substantial problem (issues — concretely, what to fix and how).',
    ].join('\n'),
    { label: attempt ? 'critic:recheck' : 'critic', phase: 'Critic', schema: CRITIC_SCHEMA, ...ARCHITECT },
  )
  if (!critic || critic.approved) break
  if (attempt === CRITIC_ROUNDS - 1) {
    // The critic used up its rounds and found something NEW every time — a sign not of a bad plan
    // but of a task that is too wide. Return a split to the caller instead of a bare refusal.
    phase('Split')
    log('The critic did not accept the plan within the allotted rounds — proposing a phase split')
    const rescue = await agent(
      [
        `Phase "${planFinal.title}" for "${REQUEST}" was not agreed in ${CRITIC_ROUNDS} rounds: the critic kept finding new unaccounted behaviour branches. ${SOURCE}`,
        TOPO,
        'Last plan: ' + JSON.stringify({ tasks: planFinal.tasks, requirementMap: planFinal.requirementMap }),
        'Remarks of the last round: ' + JSON.stringify(critic.issues),
        'Split the phase into 2–4 SEQUENTIAL chunks on one branch. A good split is thin END-TO-END slices: each chunk, after its commit, works from the entry point (webhook, route, dispatcher) to the result for at least its own scenario and is covered by a test at the entry level; the first chunk is the narrowest working scenario in full (with the migration, if one is needed), the following ones extend it. A bad split is by layers (data → sending → wizard → dispatcher) or "all tests first, then code": between chunks the feature is not wired up, and a dead path passes all tests. Distribute the critic\'s remarks verbatim to the chunks they concern.',
        'For each chunk: key, title (in the project language), request (the full self-contained request text for a separate run, including the critic remarks relevant to the chunk), files[], dependsOn[]. Return {chunks, rationale}.',
      ].join('\n'),
      { label: 'split:rescue', phase: 'Split', schema: SPLIT_SCHEMA, ...ARCHITECT },
    )
    if (rescue && rescue.chunks && rescue.chunks.length > 1 && !a.manualChunks) return await runChunks(rescue.chunks, 'the critic did not accept the plan as a whole')
    return {
      error: rescue && rescue.chunks && rescue.chunks.length > 1 ? 'decomposition rejected — split proposed' : 'decomposition rejected by critic',
      branch: BRANCH,
      issues: critic.issues,
      split: rescue || null,
    }
  }
  log(`Critic rejected (round ${attempt + 1} of ${CRITIC_ROUNDS - 1}): ${JSON.stringify(critic.issues)}`)
  const replan = await agent(
    [
      `Rework the plan according to the critic's remarks: ${JSON.stringify(critic.issues)}. ${SOURCE}`,
      TOPO,
      'Current plan: ' + JSON.stringify(planFinal),
      `Same rules (granularity, disjoint waves, TDD pairs, assumptions, requirementMap). Before returning, re-check on disk every path in files[] (\`ls\`, \`find ${APP}/tests -name "<name>"\`) and every method or field name (\`grep -rn\` over ${APP}/src) — critic remarks about non-existent paths and methods must not repeat. If the problem is in the premise (it cannot be implemented) — return tasks:[] and explain in details. Do NOT write code.`,
    ].join('\n'),
    { label: 'replan', phase: 'Critic', schema: PLAN_SCHEMA, ...ARCHITECT },
  )
  if (!replan || !replan.tasks || replan.tasks.length === 0) return { error: 'replan failed', branch: BRANCH, issues: critic.issues, replan }
  planFinal = replan
}

// Critic remarks with approved=true (non-critical, "take into account during implementation") are not lost: into subtask notes and the devlog.
const CRITIC_NOTES = (critic && critic.approved && critic.issues) || []
function notesFor(key) {
  // the key is mentioned inside square brackets at the start of a remark: "[3.1 testPlan]", "[3.4/3.6, …]"
  return CRITIC_NOTES.filter((n) => new RegExp('^\\[[^\\]]*(?<![0-9.])' + key.replace('.', '\\.') + '(?![0-9.])[^\\]]*\\]').test(n))
}

// === 3. Bridge — plan → bd subtasks (children of BD_ID) with dependencies, claimed by OWNER ===
phase('Bridge')
const bridge = await agent(
  [
    `Create the run's subtasks in bd as CHILDREN of task ${BD_ID}. All bd commands — \`bd -C ${ROOT} …\` (no cd). Do NOT close or reassign the parent.`,
    `IDEMPOTENCY (run resume): FIRST \`bd -C ${ROOT} list --parent ${BD_ID} --status open,in_progress,closed --json\` (without --status bd shows only open ones). If children with the auto-run label already exist and their design contains "key: <key>" for the plan keys — do NOT create duplicates: return the existing ids (in the order of the plan keys, in any status), and create the missing keys. If there are no children — create them all.`,
    'For EACH plan task: `bd -C ' + ROOT + ' create --parent=' + BD_ID + ' --type=task --priority=1 --title="<title>" --description="<description>\\n\\nFILES: <comma-separated files>\\nTESTS: <testPlan>" --acceptance="<acceptance>" --design="key: <key>" --labels=auto-run` — then `bd -C ' + ROOT + ' update <new-id> --assignee=' + OWNER + ' --claim` (status in_progress, run scope). Creation order — by key.',
    'Dependencies: for each blockedBy — `bd -C ' + ROOT + ' dep add <task id> <dependency id>` (the task depends on the dependency).',
    'Plan: ' + JSON.stringify(planFinal.tasks.map((t) => ({ key: t.key, title: t.title, description: t.description || '', files: t.files, testPlan: t.testPlan, acceptance: t.acceptance, blockedBy: t.blockedBy, criticNotes: notesFor(t.key) }))),
    'If a task has criticNotes — add them to the description as a block "CRITIC REMARKS (take into account during implementation):".',
    `Check: \`bd -C ${ROOT} list --parent ${BD_ID} --status in_progress\` shows all the created ones. Do NOT commit .beads/.`,
    'Return {ok, summary, ids: [created ids in key order], details: key → id mapping}.',
  ].join('\n'),
  { label: 'bridge', phase: 'Bridge', schema: BRIDGE_SCHEMA, ...SIMPLE },
)
if (!bridge || !bridge.ok) return { error: 'bridge failed', branch: BRANCH, bridge }
log(`Bridge: ${(bridge.ids || []).length} subtasks under ${BD_ID}`)

// === 4. Build — feature-core (children of BD_ID → waves → integrate → review → fix) ===
phase('Build')
const core = await workflow(
  { scriptPath: CORE_SCRIPT },
  {
    appDir: APP,
    root: ROOT,
    baseBranch: BASE,
    venv: VENV,
    parentId: BD_ID,
    assignee: OWNER,
    changeDir: CHANGE_ABS,
    specPath: SPEC_PATH,
    skipExport: true,
    skipFinalGates: true,
    dbTests: DB_TESTS,
    dbShards: DB_SHARDS,
    allowMigrations: ALLOW_MIGRATIONS,
    maxRounds: MAX_ROUNDS,
    reviewDims: a.reviewDims,
  },
)
const blockers = (core && core.blockersRemaining) || []
const coreImplemented = (core && core.implemented) || []
const assumptions = [...planFinal.assumptions, ...((core && core.assumptions) || [])]
log(`Build: ${coreImplemented.length} of ${planFinal.tasks.length} implemented, ${blockers.length} blockers remaining`)
if (coreImplemented.length === 0) {
  if (core && core.error) return { error: 'core failed: ' + core.error, branch: BRANCH, core }
  return { error: 'core failed: zero implemented tasks — check the bd graph and the feature-core logs', branch: BRANCH, core }
}

return await finish({
  planFinal,
  coreImplemented,
  blockers,
  assumptions,
  CRITIC_NOTES,
  subtasks: bridge.ids || [],
  criticApproved: !critic || critic.approved,
  chunks: null,
  incomplete: (core && core.error) || null,
})

// === 1c. Split phase — chunks in sequence on ONE branch, via the small path; review once ===
// A full run per chunk (plan, critic, bridge, review each time) costs several times more tokens.
// The split is made by the architect and the chunks are self-contained, so each one is built by
// feature-lite (build + full gates, no wrap-up), and review and integration run once over the
// whole branch — which also catches defects that no single chunk shows.
async function runChunks(chunks, why) {
  phase('Chunks')
  log(`Split (${why}): ${chunks.map((c) => c.key).join(', ')} — chunks via the small path on branch ${BRANCH}, review once over the whole branch`)
  const done = []
  for (const c of chunks) {
    const r = await workflow(
      { scriptPath: LITE_SCRIPT },
      {
        request: `${c.request}\n\nCHUNK ${c.key} (${done.length + 1} of ${chunks.length}) of phase "${plan.title}". Already committed to this branch: ${done.map((d) => d.key).join(', ') || 'nothing'} — build on them, do not duplicate.`,
        stamp: `${STAMP}-${c.key}`,
        slug: SLUG,
        releaseLine: REL,
        baseBranch: BASE,
        specPath: SPEC_PATH || (CHANGE_ABS ? `${CHANGE_ABS}/tasks.md` : null),
        stopBeforePR: true,
        noFetch: true,
        branchReady: true,
        skipWrap: true,
        allowMigrations: ALLOW_MIGRATIONS,
        assignee: OWNER,
        appDir: APP,
        root: ROOT,
        venv: VENV,
        bdId: BD_ID,
      },
    )
    if (!r || r.error || !r.build || !r.build.ok || !r.build.gatesPassed) {
      log(`Chunk ${c.key} did not build — stop; finished chunks: ${done.map((d) => d.key).join(', ') || 'none'}`)
      return { error: `chunk ${c.key} failed`, branch: BRANCH, chunk: c, result: r, chunksDone: done.map((d) => d.key) }
    }
    done.push({ key: c.key, title: c.title, build: r.build })
  }
  phase('Build')
  // reviewOnly without parentId/assignee makes feature-core exit without a review — pass both.
  const core = await workflow(
    { scriptPath: CORE_SCRIPT },
    {
      appDir: APP,
      root: ROOT,
      baseBranch: BASE,
      venv: VENV,
      parentId: BD_ID,
      assignee: OWNER,
      reviewOnly: true,
      changeDir: CHANGE_ABS,
      specPath: SPEC_PATH,
      skipExport: true,
      skipFinalGates: true,
      dbTests: DB_TESTS,
      dbShards: DB_SHARDS,
      allowMigrations: ALLOW_MIGRATIONS,
      reviewDims: a.reviewDims,
    },
  )
  if (!core || core.error) log(`Branch review: ${core ? core.error : 'no result'} — integrating anyway; the run result carries it as incomplete`)
  return await finish({
    planFinal: plan,
    coreImplemented: done.map((d) => ({ bdId: `${BD_ID}:${d.key}`, title: d.title, status: 'done', filesChanged: d.build.filesChanged, testsAdded: d.build.testsAdded, assumptions: d.build.assumptions || [], summary: d.build.summary })),
    blockers: (core && core.blockersRemaining) || [],
    assumptions: [...(plan.assumptions || []), ...done.flatMap((d) => d.build.assumptions || [])],
    CRITIC_NOTES: [],
    subtasks: [],
    criticApproved: true,
    chunks: done.map((d) => d.key),
    incomplete: !core ? 'branch review did not run' : core.error || null,
  })
}

// === 5. Integrate — fresh base, FULL gates, charter docs, devlog, bd ===
// A function: called both by the normal path (after feature-core) and by the split phase (after the chunks).
async function finish({ planFinal, coreImplemented, blockers, assumptions, CRITIC_NOTES, subtasks, criticApproved, chunks, incomplete }) {
phase('Integrate')
const TEST_FAST = `${VENV}/bin/python -m pytest ${APP}/tests -q --tb=short`
// The limit of one agent command is 600 s. A longer lane is cut off and the run repeats —
// split it into shards with the dbShards argument (paths from the tree root), each as its own command.
const TEST_DB = DB_SHARDS.map((s) => `\`${VENV}/bin/python -m pytest ${APP}/${s} -m db -q --tb=short\``).join(', ') + (DB_SHARDS.length > 1 ? ' — db lane shards, EACH as a separate synchronous command' : '')
const LINT = `${VENV}/bin/ruff check ${APP}/src ${APP}/tests && ${VENV}/bin/ruff format --check ${APP}/src ${APP}/tests`
const integrate = await agent(
  [
    `Final integration of "${planFinal.title}" (branch ${BRANCH}, tree ${APP}, base ${BASE}).`,
    TOPO,
    (NO_FETCH ? '' : `git -C ${APP} fetch origin ${BASE}; `) + `git -C ${APP} merge origin/${BASE} --no-edit. Resolve code conflicts by meaning; .beads/issues.jsonl and devlog.md — auto-merge, check integrity.`,
    `FULL gates (mandatory, a real run): \`${TEST_FAST}\`, \`${LINT}\`` + (DB_TESTS ? `, ${TEST_DB} (Docker/testcontainers).` : '. The db lane (@pytest.mark.db) is not run here — CI will run it; note this in the devlog.') + ' Red → fix (root cause, not adjusting) and commit the fix.',
    `bd: the run's subtasks (\`timeout 60 bd -C ${ROOT} list --parent ${BD_ID}\`; all bd commands — with \`timeout 60\`: bd can hang on a database lock; on timeout — retry once, then skip with a note in the devlog) — close the done ones (\`bd -C ${ROOT} close <id> --reason\`), leave the undone ones open with a note (\`bd -C ${ROOT} update <id> --notes\`). Do NOT close the parent ${BD_ID} (scripts/merge-feature.sh closes it at merge). Then \`timeout 120 ${ROOT}/scripts/bd-export.sh\` — do NOT commit .beads/issues.jsonl (merge-feature.sh carries it).`,
    'SYNC the charter documents (CLAUDE.md §Finishing a feature; ONLY if the feature touched them): ARCHITECTURE.md (layers/model/endpoints), naming.yaml (new entities/terms), CODING_STANDARDS.md (new rules), README.md (quickstart/settings). Test counters — from the real run. Not touched — an explicit note in the devlog.',
    `devlog.md (in ${APP}): an entry at the TOP following the project template (HTML comment at the end of the file): Done / Decisions (including assumptions — "decisions the machine made for you": ${JSON.stringify(assumptions)}; critic remarks accepted as known consequences: ${JSON.stringify(CRITIC_NOTES)}) / Open questions (unimplemented subtasks, remaining review blockers: ${JSON.stringify(blockers.map((b) => b.summary))}) / Next session (review the branch → push → "accepted" → scripts/merge-feature.sh ${BRANCH}). This item is mandatory: the pre-push gate requires a devlog entry when code is touched. Make the entry a self-contained block and end it with a \`---\` separator line: the file is combined with a union merge (.gitattributes), and without its own separator the entries of two branches stick together.` +
      (CHANGE_ABS ? ` In ${CHANGE_ABS}/tasks.md mark [x] the completed items of phase ${PHASE}.` : ''),
    `Commit docs/devlog/openspec as a separate commit on ${BRANCH} (\`git -C ${APP} commit\`). NO push, NO PR. ` + MSG_STYLE,
    'Return {ok, summary, details: test counters (fast/db/ruff), closed subtasks, touched docs}.',
  ].join('\n'),
  { label: 'integrate', phase: 'Integrate', schema: STEP_SCHEMA, ...WORKER },
)
if (!integrate || !integrate.ok) return { error: 'integrate failed', branch: BRANCH, integrate, blockers, implemented: coreImplemented, chunks }

// === 6. PR — optional (boundary: open PR into the base; merge is done by a human via scripts/merge-feature.sh after "accepted") ===
let pr = null
if (!STOP_BEFORE_PR) {
  phase('PR')
  pr = await agent(
    [
      `Push the branch (\`git -C ${APP} push -u origin ${BRANCH}\`) and open a PR into ${BASE}: \`gh pr create --base ${BASE} --head ${BRANCH} --title "<title>" --body "<description>"\`. Do NOT merge (merge is done by a human, scripts/merge-feature.sh).`,
      `Title and description in human-readable prose: a paragraph "what changes and why"; bullet points — tests with actual counters (${integrate.details || ''}), assumptions in plain language (${JSON.stringify(assumptions)}), "Closes ${BD_ID}".`,
      MSG_STYLE,
      'Return {ok, summary, details: link to the PR}.',
    ].join('\n'),
    { label: 'pr', phase: 'PR', schema: STEP_SCHEMA, ...WORKER },
  )
} else {
  log('stopBeforePR: PR skipped — branch ' + BRANCH + ' is committed locally; push → PR → merge is done by a human.')
}

const problems = [...new Set([
  ...(incomplete ? String(incomplete).split('; ') : []),
  blockers.length ? `${blockers.length} critical review blocker(s) remain` : null,
  !STOP_BEFORE_PR && (!pr || !pr.ok) ? 'PR not opened' : null,
].filter(Boolean))]

return {
  error: problems.length ? 'incomplete: ' + problems.join('; ') : null,
  path: 'full',
  title: planFinal.title,
  branch: BRANCH,
  appDir: APP,
  bdId: BD_ID,
  subtasks,
  chunks,
  assumptions,
  criticApproved,
  implemented: coreImplemented,
  blockers,
  integrate,
  pr,
  note:
    'Automatic boundary — ' +
    (STOP_BEFORE_PR ? 'local commit' : 'open PR') +
    ' on branch ' +
    BRANCH +
    ' (tree ' +
    APP +
    '). Before merge, for the human: review the assumptions and the devlog, green CI (full db/e2e matrix) → "accepted" → scripts/merge-feature.sh ' +
    BRANCH +
    ' (closes ' +
    BD_ID +
    ', carries .beads/issues.jsonl).' +
    (USE_WORKTREE ? ` After the merge remove the worktree: git -C ${SESSION_TOP} worktree remove ${APP}.` : ''),
}
}
