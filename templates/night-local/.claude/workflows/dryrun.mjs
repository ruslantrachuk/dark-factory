// Stub run of workflow scripts: syntax + control flow with fake agents.
import fs from 'node:fs'
// Scripts are loaded from next to dryrun.mjs: run from a worktree, it checks that worktree's version, not the main checkout's.
const WF = new URL('.', import.meta.url).pathname
function load(name) {
  let src = fs.readFileSync(WF + name, 'utf8').replace(/^export const meta/m, 'const meta')
  return new Function('args', 'agent', 'parallel', 'pipeline', 'log', 'phase', 'workflow', 'budget', 'return (async () => {' + src + '\n})()')
}
const calls = []
function mkEnv(name, canned) {
  const log = (m) => console.log(`  [${name}] ${m}`)
  const phase = (t) => console.log(`  [${name}] == ${t}`)
  const agent = async (prompt, opts = {}) => {
    const label = opts.label || '?'
    calls.push(`${name}:${label}`)
    for (const [re, fn] of canned) if (re.test(label)) return typeof fn === 'function' ? fn(prompt, opts) : fn
    return { ok: true, summary: 'stub ' + label, details: '' }
  }
  const parallel = async (thunks) => Promise.all(thunks.map((t) => t().catch(() => null)))
  const pipeline = async (items, ...stages) => Promise.all(items.map(async (it, i) => { let r = it; for (const s of stages) r = await s(r, it, i); return r }))
  const workflow = async (ref, a) => {
    const child = ref.scriptPath.split('/').pop()
    console.log(`  [${name}] ▸ workflow ${child} args=${JSON.stringify(a)}`)
    return run(child, a)
  }
  const budget = { total: null, spent: () => 0, remaining: () => Infinity }
  return { log, phase, agent, parallel, pipeline, workflow, budget }
}
const CANNED = {
  'feature-core.ts': [
    [/^plan$/, { tasks: [
      { id: "proj-x.1", title: "migration+repository", status: "closed", files: ['alembic/versions/x.py', 'src/<project>/repositories/outbound.py', 'tests/integration/db/test_outbound.py'], testPlan: 'db', acceptance: 'a', blockedBy: [] },
      { id: "proj-x.2", title: "service", status: "in_progress", files: ['src/<project>/services/outbound/journal.py', 'tests/unit/test_journal.py'], testPlan: 'unit', acceptance: 'b', blockedBy: ['proj-x.1'] },
      { id: "proj-x.3", title: "reaction", status: "in_progress", files: ['src/<project>/api/webhook.py', 'tests/unit/test_reacted.py'], testPlan: 'unit', acceptance: 'c', blockedBy: [] },
    ] }],
    [/^impl:/, (p, o) => ({ bdId: o.label.slice(5), status: 'done', filesChanged: ['f'], testFiles: ['t'], testsAdded: 3, assumptions: ['a1'], summary: 's' })],
    [/^review/, { dimension: 'combined', findings: [{ file: 'f', summary: 'x', severity: 'major', fix: 'y' }, { file: 'g', summary: 'z', severity: 'minor' }] }],
  ],
  'feature-auto.ts': [
    [/^repo-root$/, { ok: true, summary: '~/<project>' }],
    [/^triage$/, { ok: true, summary: 'full', details: 'migration' }],
    [/^plan$/, { title: 'Delivery log', tasks: [
      { key: '3.1', title: 'a', files: ['x'], testPlan: 't', acceptance: 'c', blockedBy: [] },
      { key: '3.2', title: 'b', files: ['y'], testPlan: 't', acceptance: 'c', blockedBy: ['3.1'] },
      { key: '3.3', title: 'c', files: ['z'], testPlan: 't', acceptance: 'c', blockedBy: [] },
    ], assumptions: ['A', 'B', 'C', 'D'], requirementMap: [{ requirement: 'R1', tasks: ['3.1'] }], migrationNeeded: true }],
    [/^critic$/, { approved: false, issues: ['R2 not covered'] }],
    [/^replan$/, { title: 'Delivery log v2', tasks: [{ key: '3.1', title: 'a', files: ['x'], testPlan: 't', acceptance: 'c', blockedBy: [] }, { key: '3.2', title: 'b', files: ['y'], testPlan: 't', acceptance: 'c', blockedBy: ['3.1'] }], assumptions: ['A'], requirementMap: [], migrationNeeded: true }],
    [/^critic:recheck$/, { approved: true, issues: [] }],
    [/^bridge$/, { ok: true, summary: 'ok', ids: ['proj-x.1', 'proj-x.2'] }],
  ],
  'feature-lite.ts': [[/^lite-build$/, { ok: true, branch: 'b', filesChanged: ['a'], testsAdded: 1, gatesPassed: true, assumptions: [], summary: 's' }]],
  'night-dispatch.ts': [
    [/^repo-root$/, { ok: true, summary: '~/<project>\t12\tdevelop' }],
    [/^pick$/, { items: [{ id: 'proj-t4sk.3', type: 'feature', title: 'phase 3', scale: 'auto', changeDir: 'openspec/changes/r12-example-change', phase: '3' }] }],
    [/^test:/, { ran: true, ok: true, passed: 10, failed: 0, summary: 'ok' }],
    [/^guard:/, { docsOnly: false, hasCode: true, hasTests: true, summary: '' }],
  ],
}
async function run(name, args) {
  const fn = load(name)
  const env = mkEnv(name, CANNED[name] || [])
  return fn(args, env.agent, env.parallel, env.pipeline, env.log, env.phase, env.workflow, env.budget)
}
const which = process.argv[2]
const args = JSON.parse(process.argv[3] || '{}')
// Optional: {"<label>": <answer>} — override agent answers to exercise rare branches (split, failed chunk).
const OVERRIDES = JSON.parse(process.argv[4] || '{}')
for (const [label, resp] of Object.entries(OVERRIDES)) for (const k of Object.keys(CANNED)) CANNED[k].unshift([new RegExp('^' + label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'), resp])
console.log(`=== ${which} ${JSON.stringify(args)}`)
const res = await run(which, args)
console.log('RESULT:', JSON.stringify(res, null, 1).slice(0, 1500))
console.log('AGENTS:', calls.join(', '))
