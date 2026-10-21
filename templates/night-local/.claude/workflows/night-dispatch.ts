export const meta = {
  name: 'night-dispatch',
  description:
    'Night orchestrator for <project> (local night on one machine, one repository): takes bd ready, routes by the scale tier (lite → feature-lite; bug/auto → feature-auto; core → feature-core; in the pilot only lite by default — pilotLiteOnly), isolates runs (assignee scope; worktree when N>1), the night gate is pytest (fast suite, as in pre-push) with a bounded fix loop, stopBeforePR: ship is NEVER called, the task is NOT closed (label night-done — picked up by a human in the morning). Runaway protection: anomalous per-run cut-off + soft reserve between tasks + telemetry; wall-clock — outside (night-guard timeout / systemd).',
  phases: [{ title: 'Resolve' }, { title: 'Pick' }, { title: 'Run' }],
}

// --- Input (args) ---
// { stamp: string (REQUIRED — Date.now() is forbidden), maxParallel?: number=1,
//   maxFeaturesPerNight?: number (night volume; default=maxParallel), stopBeforePR?: boolean=true,
//   releaseLine?: string (e.g. "r12"; otherwise openspec/CURRENT_TRAIN; neither — error),
//   scale?: 'auto'|'core'|'lite' (run argument; a per-task scale:* label overrides it),
//   pilotLiteOnly?: boolean=true (pilot: take ONLY scale:lite; enable auto/core/bug with pilotLiteOnly=false after a green lite),
//   baseBranch?: string (branch base: otherwise openspec/INTEGRATION_BRANCH, otherwise main),
//   (all orchestrator agents — Sonnet: mechanics, test gate, night fix; heavy stages live in the tiers)
//   tokenBudget?: number, perRunReserve?: number=1_300_000, maxPerRun?: number=3_000_000, maxTestFix?: number=2 }
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
const STAMP = a.stamp
const MAX_PARALLEL = a.maxParallel || 1
const MAX_FEATURES = a.maxFeaturesPerNight || MAX_PARALLEL
const STOP_BEFORE_PR = a.stopBeforePR !== false // default true: the night NEVER reaches ship
const REL_ARG = a.releaseLine || null
const SCALE = (typeof a.scale === 'string' ? a.scale.toLowerCase() : '') || null
const PILOT_LITE_ONLY = a.pilotLiteOnly !== false // pilot: lite only until lite is green
const BASE_ARG = a.baseBranch || null

// === Runaway protection (runbook §4) ===
// Three levels: (1) runtime ceiling budget.total; (2) anomalous per-run cut-off — one run costing more than maxPerRun ⇒
//   probable loop ⇒ stop the whole night; (3) soft reserve between tasks. Wall-clock — OUTSIDE (night-guard timeout),
//   Date.now() is forbidden in the script (breaks resume).
const SOFT_BUDGET = a.tokenBudget || budget.total
const PER_RUN_RESERVE = a.perRunReserve || 1_300_000
const MAX_PER_RUN = a.maxPerRun || 3_000_000
const TOKENS_LEFT = () => (SOFT_BUDGET == null ? Infinity : Math.max(0, SOFT_BUDGET - budget.spent()))

if (!STAMP) {
  log('night-dispatch: args.stamp is required (unique suffix — a date like "20260101-2300"). Date.now() is forbidden in scripts.')
  return { error: 'no stamp' }
}
if (SOFT_BUDGET == null) {
  log('night-dispatch: ⚠ running WITHOUT a token budget → no soft spending ceiling (pilot measurement mode, runbook §4.7).')
}

const STEP_SCHEMA = {
  type: 'object',
  required: ['ok', 'summary'],
  properties: { ok: { type: 'boolean' }, summary: { type: 'string' }, details: { type: 'string' } },
}
const PICK_SCHEMA = {
  type: 'object',
  required: ['items'],
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'type'],
        properties: { id: { type: 'string' }, type: { type: 'string' }, title: { type: 'string' }, scale: { type: 'string' }, releaseLine: { type: 'string' }, specPath: { type: 'string' }, changeDir: { type: 'string' }, phase: { type: 'string' } },
      },
    },
  },
}
// Night test gate: result of the fast pytest suite (the same as in pre-push; db/e2e/live are excluded by addopts).
const TEST_SCHEMA = {
  type: 'object',
  required: ['ran', 'ok'],
  properties: {
    ran: { type: 'boolean' },
    ok: { type: 'boolean' },
    passed: { type: 'number' },
    failed: { type: 'number' },
    summary: { type: 'string' },
    failing: { type: 'string' }, // names/output of failed tests — input for the fix agent
  },
}
const MAX_TEST_FIX = a.maxTestFix != null ? a.maxTestFix : 2
// Docs-only guard: an implement feature that boiled down to docs only = a false done.
const GUARD_SCHEMA = {
  type: 'object',
  required: ['docsOnly'],
  properties: {
    docsOnly: { type: 'boolean' },
    hasCode: { type: 'boolean' },
    hasTests: { type: 'boolean' },
    summary: { type: 'string' },
  },
}
// Fast suite command — exactly like TEST_CMD in .githooks/pre-push.
const TEST_CMD = (dir) => `$([ -x ${dir}/.venv/bin/python ] && echo ${dir}/.venv/bin/python || echo ${ROOT_HINT(dir)}/.venv/bin/python) -m pytest ${dir}/tests -q --tb=short`
// a worktree without .venv → python of the main checkout (ROOT is known after Resolve; before that — dir itself)
let ROOT_FOR_VENV = null
const ROOT_HINT = (dir) => ROOT_FOR_VENV || dir

// === 0. Resolve: repo root + release line ===
phase('Resolve')
const rootStep = await agent(
  'Run (no cd) `git rev-parse --show-toplevel` (absolute root path), `head -1 <root>/openspec/CURRENT_TRAIN` (number of the current release train, e.g. 12) and `head -1 <root>/openspec/INTEGRATION_BRANCH` (train integration branch, e.g. develop). ' +
    'Return {ok:true, summary: "<absolute-root-path>\\t<train-number>\\t<integration-branch>"} — three tab-separated fields. If a file is missing — the field is empty ("-"); this is NOT an error.',
  { model: 'claude-sonnet-5-5', label: 'repo-root', phase: 'Resolve', schema: STEP_SCHEMA },
)
if (!rootStep || !rootStep.ok) return { error: 'repo-root resolve failed' }
const [ROOT, TRAIN_RAW_0, BASE_RAW_0] = rootStep.summary.trim().split(/\t| +/)
ROOT_FOR_VENV = ROOT
const TRAIN_RAW = TRAIN_RAW_0 && TRAIN_RAW_0 !== '-' ? TRAIN_RAW_0 : ''
const BASE = BASE_ARG || (BASE_RAW_0 && BASE_RAW_0 !== '-' ? BASE_RAW_0 : 'main')
// Line priority: task label rel:<line> ▸ args.releaseLine ▸ openspec/CURRENT_TRAIN. Guessing is forbidden (CLAUDE.md).
const REL = REL_ARG || (TRAIN_RAW ? `r${String(TRAIN_RAW).replace(/^r/i, '').trim()}` : null)
if (!REL) {
  log('night-dispatch: release line unknown — neither args.releaseLine (PROJ_NIGHT_REL) nor openspec/CURRENT_TRAIN. Guessing is not allowed (CLAUDE.md, GATE Step 1). Stop.')
  return { error: 'no release line' }
}
log(`night-dispatch: release line (default) = ${REL} (arg=${REL_ARG || '—'}, CURRENT_TRAIN=${TRAIN_RAW || '—'}); branch base = ${BASE}`)
const FEATURE_AUTO = a.featureAutoScript || ROOT + '/.claude/workflows/feature-auto.ts'
const FEATURE_LITE = a.featureLiteScript || ROOT + '/.claude/workflows/feature-lite.ts'
const FEATURE_CORE = a.featureCoreScript || ROOT + '/.claude/workflows/feature-core.ts'

// === 1. Pick: up to MAX_FEATURES tasks from bd ready ===
phase('Pick')
const pick = await agent(
  [
    `Pick up to ${MAX_FEATURES} tasks from \`bd ready --json\` for a NIGHT autonomous run (no human; tests — the fast pytest suite without db/e2e/live).`,
    'SKIP tasks with the night-skip label (a human marked them as unfit for the night: they need secrets, the prod DB, external services, alembic migrations). Check labels via bd show when in doubt.',
    'For each, return {id, type, title}: type="bug" if issue_type=bug, otherwise "feature". Do NOT take epics (label epic).',
    'If the task has an EXPLICIT scale:auto / scale:core / scale:lite label — return scale accordingly. Do NOT guess yourself (the tier is set by a human during setup) — no label, do not return scale.',
    'If there is a rel:<line> label (e.g. rel:r12) — return releaseLine="r12". None — do not return it.',
    'If the description contains "SPEC: <path>" (a ready design document, relative to the repo root) — return specPath EXACTLY as in the description. None — do not return it. If it contains "OPENSPEC: <change dir path>" and "PHASE: <N>" — return changeDir and phase.',
    PILOT_LITE_ONLY
      ? 'PILOT: ONLY a task with scale:lite AND "SPEC:" qualifies. Do NOT take the others (bug, auto, core, no scale, no spec). None qualify — return {items: []} (a human will prepare them).'
      : 'READINESS: bug — qualifies (no spec needed); scale:auto with "SPEC:" OR with "OPENSPEC: <changeDir> PHASE: <N>" in the description — qualifies; scale:core — a parent task with child subtasks already created (FILES:/TESTS: in the children\'s descriptions); scale:lite with "SPEC:" — a single task. No scale (except bug) or no source — do not take. None qualify — {items: []}.',
  ].join('\n'),
  { model: 'claude-sonnet-5-5', label: 'pick', phase: 'Pick', schema: PICK_SCHEMA },
)
const items = (pick && pick.items) || []
if (items.length === 0) {
  log('night-dispatch: no suitable tasks in bd ready (empty, night-skip or not prepared: scale:lite + "SPEC:" are required).')
  return { stamp: STAMP, picked: [], note: 'nothing to do' }
}
log(`night-dispatch: picked ${items.length} tasks (maxFeaturesPerNight=${MAX_FEATURES}, maxParallel=${MAX_PARALLEL}, stopBeforePR=${STOP_BEFORE_PR}, pilotLiteOnly=${PILOT_LITE_ONLY})`)

// === 2. Run: claim (assignee scope) + isolation + route by tier ===
// One repository: code and harness (.beads/devlog/openspec) in one tree. A single run (N=1) writes to the main
//   tree (checkout -b from origin/<base> — like a human). N>1 → a separate git worktree per run
//   ${ROOT}/.night-worktrees/<owner> (NOT validated: .beads in a worktree is a copy of the JSONL, bd-export
//   in the worktree will diverge from the main one; parallelism — after a green pilot).
phase('Run')
const useWorktree = items.length > 1
if (useWorktree) log('night-dispatch: ⚠ N>1 → worktree isolation; not proven (shared .beads). maxFeaturesPerNight=1 is recommended.')
const results = []
const skippedForBudget = []
let anomaly = null
for (let i = 0; i < items.length; i++) {
  const it = items[i]
  const left = TOKENS_LEFT()
  if (left < PER_RUN_RESERVE) {
    const rest = items.slice(i).map((x) => x.id)
    skippedForBudget.push(...rest)
    log(`night-dispatch: token budget running out (~${Math.round(left / 1000)}k left < reserve ${Math.round(PER_RUN_RESERVE / 1000)}k) → not taking ${rest.length} tasks: ${JSON.stringify(rest)}`)
    break
  }
  const owner = `night-${STAMP}-${i}`
  const idSlug = String(it.id).replace(/[^a-z0-9]+/gi, '-').toLowerCase()
  // Branch canon: r{N}/<type>-<slug>-<bd-id> (the bd id at the tail is mandatory — merge-feature.sh closes by it).
  const typeSlug = it.type === 'bug' ? 'fix' : 'feat'
  const slug = `${typeSlug}-night-${STAMP}-${idSlug}`
  const rel = it.releaseLine || REL
  const branch = `${rel}/${slug}`
  const specAbs = it.specPath ? `${ROOT}/${String(it.specPath).replace(/^\/+/, '')}` : null
  // app topology: code in <repo>/app, venv in app/.venv, repo root (git/bd/beads) = ROOT.
  // N=1 (pilot): appDir = ROOT/app. N>1 worktree under app/ is NOT adapted (the worktree
  // is created at appDir, while the code here lives one level deeper) — see README/MANIFEST, after the pilot.
  const appDir = useWorktree ? `${ROOT}/.night-worktrees/${owner}` : `${ROOT}/app`
  const spentBefore = budget.spent()

  const scale = it.scale || SCALE
  const isCore = it.type !== 'bug' && scale === 'core'
  const route = it.type === 'bug' || scale === 'auto' ? 'feature-auto' : scale === 'core' ? 'feature-core' : 'feature-lite'

  if (PILOT_LITE_ONLY && route !== 'feature-lite') {
    results.push({ id: it.id, type: it.type, scale, route, ok: false, why: 'pilotLiteOnly: tier not enabled' })
    log(`night-dispatch: ${it.id} → tier ${route} is disabled in the pilot — skipping`)
    continue
  }

  // Claim the run scope: core → the whole graph of the epic's phase tasks; otherwise → a single task.
  const claim = isCore
    ? await agent(
        [
          `Task ${it.id} is the EPIC of a scale:core feature; the graph of phase tasks was built during setup, the tasks are open.`,
          `Find ALL open child phase tasks of the epic (\`bd show ${it.id}\`) and claim EACH one for ${owner}: \`bd update <child> --assignee=${owner} --claim\`. Do NOT claim the EPIC itself. Do not touch dependencies.`,
          `Return {ok, summary, details: list of claimed ids}. ok:false if the epic has no open phase tasks.`,
        ].join('\n'),
        { model: 'claude-sonnet-5-5', label: `graph:${it.id}`, phase: 'Run', schema: STEP_SCHEMA },
      )
    : await agent(
        `Claim bd task ${it.id} for assignee ${owner} (run scope): \`bd update ${it.id} --assignee=${owner} --claim\`. Return {ok, summary}.`,
        { model: 'claude-sonnet-5-5', label: `claim:${it.id}`, phase: 'Run', schema: STEP_SCHEMA },
      )
  if (!claim || !claim.ok) {
    results.push({ id: it.id, type: it.type, scale, owner, branch, appDir, ok: false, why: isCore ? 'graph claim failed' : 'claim failed' })
    log(`night-dispatch: ${it.id} — claim failed → skipping`)
    continue
  }

  const common = { request: it.title || 'bd ' + it.id, stamp: STAMP, slug, releaseLine: rel, baseBranch: BASE, stopBeforePR: STOP_BEFORE_PR, noFetch: false, assignee: owner, appDir, root: ROOT, specPath: specAbs, bdId: it.id, type: typeSlug, changeDir: it.changeDir || null, phase: it.phase || null, allowMigrations: false, dbTests: false }
  let r
  if (route === 'feature-auto') {
    r = await workflow({ scriptPath: FEATURE_AUTO }, common)
  } else if (route === 'feature-core') {
    const setup = await agent(
      [
        useWorktree
          ? `Create a SEPARATE git worktree for the run from origin/${BASE}: git -C ${ROOT} fetch origin ${BASE} && git -C ${ROOT} worktree add -b ${branch} ${appDir} origin/${BASE}. Make sure: HEAD in ${appDir} is on ${branch}, the tree is clean.`
          : `Create a branch from the fresh base ${BASE}: git -C ${ROOT} fetch origin ${BASE} && git -C ${ROOT} checkout -b ${branch} origin/${BASE}. Make sure: HEAD is on ${branch}, the tree is clean.`,
        'Do NOT change the session CWD (git -C). Return {ok, summary, details: branch and base SHA}.',
      ].join('\n'),
      { model: 'claude-sonnet-5-5', label: `setup:${it.id}`, phase: 'Run', schema: STEP_SCHEMA },
    )
    if (!setup || !setup.ok) {
      results.push({ id: it.id, type: it.type, scale, owner, branch, appDir, ok: false, why: 'setup failed' })
      log(`night-dispatch: ${it.id} (scale:core) → branch setup failed — skipping`)
      continue
    }
    r = await workflow({ scriptPath: FEATURE_CORE }, { parentId: it.id, assignee: owner, appDir, root: ROOT, baseBranch: BASE, specPath: specAbs, allowMigrations: false, dbTests: false })
  } else {
    r = await workflow({ scriptPath: FEATURE_LITE }, common)
  }

  // === Docs-only guard ===
  let guard = null
  if (r && !r.error && it.type !== 'bug') {
    guard = await agent(
      [
        `Classify the branch diff of task ${it.id}: \`git -C ${appDir} diff --name-only origin/${BASE}...HEAD\`.`,
        `Return {docsOnly, hasCode, hasTests, summary}. docsOnly=true ONLY if ALL changed files are documentation/process (*.md, docs/, openspec/, .beads/, devlog.md) and there is NO code (src/**, <frontend dir>/**, alembic/**, configs) and no tests (tests/**). Empty diff → docsOnly=true.`,
        `Do NOT change the CWD (git -C).`,
      ].join('\n'),
      { model: 'claude-sonnet-5-5', label: `guard:${it.id}`, phase: 'Run', schema: GUARD_SCHEMA },
    )
    if (guard && guard.docsOnly) {
      log(`night-dispatch: ${it.id} → docs-only diff for a feature = FALSE done → fail + task returned to work`)
      await agent(
        `Return task ${it.id} to work (the feature path may have closed it by mistake): \`bd update ${it.id} --status open --assignee=""\`. Return {ok, summary}.`,
        { model: 'claude-sonnet-5-5', label: `reopen:${it.id}`, phase: 'Run', schema: STEP_SCHEMA },
      )
    }
  }
  const guardOk = !(guard && guard.docsOnly)

  // === Night test gate (fast pytest suite) with a bounded fix loop ===
  // Red → a fix agent (systematic-debugging) fixes on the branch and commits, up to MAX_TEST_FIX attempts; still red →
  //   an HONEST fail (the task is not done). Fix tokens count into runSpent → the anomaly cut-off catches them.
  let gate = null
  if (r && !r.error && guardOk) {
    for (let attempt = 0; attempt <= MAX_TEST_FIX; attempt++) {
      const run = await agent(
        [
          `Night test gate, task ${it.id}, tree ${appDir} (attempt ${attempt}/${MAX_TEST_FIX}).`,
          `Run the fast suite (exactly like pre-push): \`${TEST_CMD(appDir)}\`. Then lint: \`${appDir}/.venv/bin/ruff check ${appDir}/src ${appDir}/tests && ${appDir}/.venv/bin/ruff format --check ${appDir}/src ${appDir}/tests\` (if ruff is not in .venv — \`ruff\` from PATH; not there either — note it in summary, lint does not block).`,
          `Return {ran:true, ok, passed, failed, summary, failing:"names/output of failed tests, if ok=false"}. ok=false if at least one test is red OR the suite did not start.`,
          `No cd (absolute paths). NO push, NO PR.`,
        ].join('\n'),
        { model: 'claude-sonnet-5-5', label: `test:${it.id}${attempt ? ':retry' + attempt : ''}`, phase: 'Run', schema: TEST_SCHEMA },
      )
      gate = run || { ran: false, ok: false, summary: 'test agent did not answer' }
      if (!gate.ran || gate.ok) break
      if (attempt === MAX_TEST_FIX) {
        log(`night-dispatch: ${it.id} → tests red after ${MAX_TEST_FIX} fix attempts → HONEST fail`)
        break
      }
      log(`night-dispatch: ${it.id} → tests red (attempt ${attempt}) → fix pass ${attempt + 1}/${MAX_TEST_FIX}`)
      await agent(
        [
          `Night test fix for ${it.id} in ${appDir}. Failed:`,
          gate.failing || gate.summary || '(output not saved — rerun the suite and look)',
          `systematic-debugging: find the ROOT cause (do not bend the test to the bug), fix the CODE (or the test, if the test is wrong). Commit the fix to the branch (git -C ${appDir} add+commit, message in the project language, no Co-Authored-By). NO push, NO PR. No cd — absolute paths, git -C.`,
          `Return {ok, summary: what was fixed}.`,
        ].join('\n'),
        { model: 'claude-sonnet-5-5', label: `test-fix:${it.id}:${attempt + 1}`, phase: 'Run', schema: STEP_SCHEMA },
      )
    }
  }
  const gateOk = !gate || gate.ok

  const runSpent = budget.spent() - spentBefore
  const ok = !!(r && !r.error) && gateOk && guardOk

  // === Status finalisation: the night does NOT close the task (final close — in the morning, merge-feature.sh closes by the bd id in the branch) ===
  // Green → label night-done (ready for the morning pickup); FAIL → open without the label. Defensive reopen.
  if (r && !r.error) {
    await agent(
      ok
        ? `Final status of ${it.id}: the gate is green, but the night does NOT close it (final close — in the morning after merge, scripts/merge-feature.sh). If the task was closed by the feature path — reopen it: \`bd update ${it.id} --status open\`. Add the ready-for-pickup label: \`bd label add ${it.id} night-done\`. Export: \`scripts/bd-export.sh\`. Return {ok, summary}.`
        : `Final status of ${it.id}: the run FAILED (tests red after fixes, or docs-only). The task must NOT be closed — if the feature path closed it, reopen it: \`bd update ${it.id} --status open\`. Do NOT add the night-done label. Export: \`scripts/bd-export.sh\`. Return {ok, summary}.`,
      { model: 'claude-sonnet-5-5', label: `finalize:${it.id}`, phase: 'Run', schema: STEP_SCHEMA },
    )
  }

  const guardNote = guard && guard.docsOnly ? ', ✗ DOCS-ONLY (false done — task returned)' : ''
  const gateNote = gate == null ? '' : gate.ok ? `, tests ✓ (${gate.passed != null ? gate.passed + ' passed' : 'green'})` : ', tests ✗ RED after fixes'
  results.push({ id: it.id, type: it.type, scale: scale || null, route, owner, branch, appDir, runSpent, ok, guard, gate, result: r })
  log(`night-dispatch: ${it.id} (${it.type}) → ${r && r.error ? 'ERROR: ' + r.error : `${ok ? 'done' : 'FAIL'} (branch ${branch}${appDir === ROOT ? '' : ', worktree ' + appDir}${guardNote}${gateNote}, no ship)`}`)
  log(`night-dispatch: run ~${Math.round(runSpent / 1000)}k; total ~${Math.round(budget.spent() / 1000)}k${SOFT_BUDGET == null ? '' : ` of ~${Math.round(SOFT_BUDGET / 1000)}k (~${Math.round(TOKENS_LEFT() / 1000)}k left)`}`)
  if (runSpent > MAX_PER_RUN) {
    anomaly = { id: it.id, runSpent }
    const rest = items.slice(i + 1).map((x) => x.id)
    skippedForBudget.push(...rest)
    log(`night-dispatch: ⚠ ANOMALY — run ${it.id} consumed ~${Math.round(runSpent / 1000)}k > threshold ${Math.round(MAX_PER_RUN / 1000)}k (probable loop) → night STOPPED. Not taking ${rest.length} tasks: ${JSON.stringify(rest)}`)
    break
  }
}

return {
  stamp: STAMP,
  stopBeforePR: STOP_BEFORE_PR,
  picked: results.map((x) => x.id),
  skippedForBudget,
  anomaly,
  tokenBudget: SOFT_BUDGET,
  tokensSpent: budget.spent(),
  results,
  note:
    'NIGHT mode: branches committed locally, ship was NOT called. In the morning: review the branches (night-dev status) → push → "accepted" → scripts/merge-feature.sh <branch> — by a human.' +
    (anomaly ? ` ⚠ the night was stopped early: ${anomaly.id} consumed ~${Math.round(anomaly.runSpent / 1000)}k (probable loop).` : '') +
    (skippedForBudget.length ? ` ${skippedForBudget.length} tasks postponed (budget/anomaly).` : ''),
}
