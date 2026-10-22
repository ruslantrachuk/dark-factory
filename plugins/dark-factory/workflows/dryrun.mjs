// Stub run of workflow scripts: syntax + control flow with fake agents, no tokens spent.
// Usage: node dryrun.mjs <script name, e.g. feature-auto.js> '<args-json>' ['{"<label>": <answer>}']
// Exits 1 when the run's agentsUsed differs from the stub's count, passes args.maxAgents, or misses DRYRUN_EXPECT_ERROR.
// A nested workflow('dark-factory:<name>') resolves to <name>.js next to this file, as the plugin registers it.
import fs from 'node:fs'
// Scripts are loaded from next to dryrun.mjs: run from a worktree, it checks that worktree's version, not the main checkout's.
const WF = new URL('.', import.meta.url).pathname
function load(name) {
  let src = fs.readFileSync(WF + name, 'utf8').replace(/^export const meta/m, 'const meta')
  return new Function('args', 'agent', 'parallel', 'pipeline', 'log', 'phase', 'workflow', 'budget', 'return (async () => {' + src + '\n})()')
}
const calls = []
function mkEnv(name, canned, depth) {
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
    // workflow('dark-factory:feature-core') — the plugin's registered name; {scriptPath} — a project's own copy.
    const child = typeof ref === 'string'
      ? (ref.startsWith('dark-factory:') ? ref.slice('dark-factory:'.length) + '.js' : (() => { throw new Error(`unknown workflow name ${ref}`) })())
      : ref.scriptPath.split('/').pop()
    // The Workflow tool nests one level only: a script launched by workflow() cannot call workflow() itself.
    if (depth > 0) throw new Error(`${name} is a child workflow and calls workflow(${child}) — nesting is one level only`)
    console.log(`  [${name}] ▸ workflow ${child} args=${JSON.stringify(a)}`)
    return run(child, a, depth + 1)
  }
  // DRYRUN_BUDGET=<n>: a token target of n with every agent call counted as 1000 tokens — exercises 'budget exhausted'.
  const target = process.env.DRYRUN_BUDGET ? Number(process.env.DRYRUN_BUDGET) : null
  const budget = { total: target, spent: () => calls.length * 1000, remaining: () => (target == null ? Infinity : target - calls.length * 1000) }
  return { log, phase, agent, parallel, pipeline, workflow, budget }
}
const CANNED = {
  'feature-core.js': [
    [/^plan$/, { tasks: [
      { id: "proj-x.1", title: "migration+repository", status: "closed", files: ['alembic/versions/x.py', 'src/app/repositories/outbound.py', 'tests/integration/db/test_outbound.py'], testPlan: 'db', acceptance: 'a', blockedBy: [] },
      { id: "proj-x.2", title: "service", status: "in_progress", files: ['src/app/services/outbound/journal.py', 'tests/unit/test_journal.py'], testPlan: 'unit', acceptance: 'b', blockedBy: ['proj-x.1'] },
      { id: "proj-x.3", title: "reaction", status: "in_progress", files: ['src/app/api/webhook.py', 'tests/unit/test_reacted.py'], testPlan: 'unit', acceptance: 'c', blockedBy: [] },
    ] }],
    [/^impl:/, (p, o) => ({ bdId: o.label.slice(5), status: 'done', filesChanged: ['f'], testFiles: ['t'], testsAdded: 3, assumptions: ['a1'], summary: 's' })],
    [/^review/, { dimension: 'combined', findings: [{ file: 'f', summary: 'x', severity: 'major', fix: 'y' }, { file: 'g', summary: 'z', severity: 'minor' }] }],
  ],
  'feature-auto.js': [
    [/^repo-root$/, { ok: true, summary: '/home/dev/app' }],
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
  'feature-lite.js': [[/^lite-build$/, { ok: true, branch: 'b', filesChanged: ['a'], testsAdded: 1, gatesPassed: true, assumptions: [], summary: 's' }]],
}
async function run(name, args, depth = 0) {
  const fn = load(name)
  const env = mkEnv(name, CANNED[name] || [], depth)
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
// The agent cap holds across nesting: the run's own count matches the stub's, and never passes args.maxAgents.
console.log(`ERROR: ${res && res.error}; agents ${calls.length}, reported ${res && res.agentsUsed} of ${res && res.maxAgents}`)
const fail = (m) => { console.error('DRYRUN FAIL: ' + m); process.exit(1) }
if (!res || res.agentsUsed !== calls.length) fail(`agentsUsed ${res && res.agentsUsed} != ${calls.length} agent calls`)
if (args.maxAgents && calls.length > args.maxAgents) fail(`${calls.length} agent calls over maxAgents ${args.maxAgents}`)
// DRYRUN_EXPECT_ERROR=<text>: the run must stop with an error containing it ('null' — must succeed).
const expect = process.env.DRYRUN_EXPECT_ERROR
if (expect === 'null' && res.error !== null) fail(`expected error null, got ${res.error}`)
if (expect && expect !== 'null' && !String(res.error).includes(expect)) fail(`expected error containing "${expect}", got ${res.error}`)
