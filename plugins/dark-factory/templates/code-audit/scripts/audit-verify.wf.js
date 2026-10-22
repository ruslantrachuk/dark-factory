export const meta = {
  name: 'audit-verify',
  description: 'Fan-out verification of hypotheses against code and deploy: an agent per unit (repository/group/investigation), then spot-checking of evidence',
  phases: [
    { title: 'Verify', detail: 'an agent per unit: code + deploy config, hypotheses with statuses and evidence' },
    { title: 'SpotCheck', detail: 'a separate agent opens evidence addresses: all refuted and a sample of confirmed' },
  ],
}

// Factory module code-audit.
// Run: the Workflow tool by scriptPath (inside the session directory), args as an object:
// { appDir: '<abs path to the clones>', preamble: '<system domain in one paragraph>',
//   units: [{ label, repos: ['repo-a', 'repo-b'], ref?: 'v1.2.3' | 'origin/master', hypotheses: ['…', '…'], hints?: '…' }],
//   spotCheckRatio?: 0.2, model?: 'claude-sonnet-5-5' }
// Result: { units: [...per schema], spotCheck: [...] } — the caller saves it to audit/runs/<date>-<name>.json.
// Date.now is forbidden (breaks resume) — the caller writes the date.

const a = typeof args === 'string' ? JSON.parse(args) : (args || {})
const APP = a.appDir
const UNITS = a.units || []
if (!APP || !UNITS.length) return { error: 'appDir and units are required' }
const MODEL = a.model || 'claude-sonnet-5-5' // pin the full model id; an alias can resolve to a different model than you expect
const RATIO = typeof a.spotCheckRatio === 'number' ? a.spotCheckRatio : 0.2

const EVIDENCE = { type: 'array', items: { type: 'string' } }
const TIER = { type: 'string', enum: ['T1', 'T2', 'none'] }
const EDGE = (peer) => ({
  type: 'array',
  items: {
    type: 'object', additionalProperties: false,
    properties: { [peer]: { type: 'string' }, mechanism: { type: 'string' }, evidence: EVIDENCE, tier: TIER },
    required: [peer, 'mechanism', 'evidence', 'tier'],
  },
})

const SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    unit: { type: 'string' },
    repos: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: { name: { type: 'string' }, ref: { type: 'string' }, last_commit_date: { type: 'string' }, exists: { type: 'boolean' } },
        required: ['name', 'ref', 'exists'],
      },
    },
    language: { type: 'string' },
    framework: { type: 'string' },
    storage: { type: 'array', items: { type: 'string' } },
    messaging: { type: 'array', items: { type: 'string' } },
    external_integrations: { type: 'array', items: { type: 'string' } },
    exposure: {
      type: 'object', additionalProperties: false,
      properties: { public: { type: 'boolean' }, detail: { type: 'string' }, tier: TIER },
      required: ['public', 'detail', 'tier'],
    },
    deploy: {
      type: 'object', additionalProperties: false,
      properties: { how: { type: 'string' }, where: { type: 'string' }, tier: TIER },
      required: ['how', 'where', 'tier'],
    },
    edges_out: EDGE('peer'),
    edges_in: EDGE('peer'),
    role_actual: { type: 'string' },
    liveness: {
      type: 'object', additionalProperties: false,
      properties: { active: { type: 'boolean' }, evidence: EVIDENCE },
      required: ['active', 'evidence'],
    },
    hypothesis_checks: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          claim: { type: 'string' },
          source: { type: 'string' },
          status: { type: 'string', enum: ['confirmed', 'refined', 'refuted', 'not_found'] },
          evidence: EVIDENCE,
          tier: TIER,
        },
        required: ['claim', 'status', 'evidence', 'tier'],
      },
    },
    findings: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          location: { type: 'string' }, evidence: { type: 'string' }, risk: { type: 'string' },
          conditions: { type: 'string' }, impact: { type: 'string' },
          severity: { type: 'string', enum: ['critical', 'major', 'minor'] },
        },
        required: ['location', 'evidence', 'risk', 'impact', 'severity'],
      },
    },
    secrets_spotted: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: { path: { type: 'string' }, kind: { type: 'string' } },
        required: ['path', 'kind'],
      },
    },
    open_questions: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
  required: ['unit', 'repos', 'role_actual', 'deploy', 'hypothesis_checks', 'findings', 'secrets_spotted'],
}

const COMMON = `
You are a codebase auditor. ${a.preamble || ''}
You work READ-ONLY: change nothing, do not commit, do not checkout — read revisions via
\`git -C <repo> show <ref>:<path>\` and \`git -C <repo> ls-tree -r <ref>\`. Do NOT print secrets, tokens, keys, passwords
or personal data: a spotted secret goes only as path and type into secrets_spotted.
Clones are in ${APP}/<repo>. Do not change directory (no cd) — only absolute paths and git -C.

PRINCIPLE: everything is a hypothesis until proven. Repository name, README, documentation, comments are hypotheses.
Evidence is only T1 (code, DB schema, application config) or T2 (Dockerfile, CI, deploy manifests).
Each piece of evidence is a line "<repo>/<path>:<line> — <quote no longer than one line>", or a CI stage,
or a dependency with its version. No evidence — status=not_found and tier=none; confirmed/refuted without
evidence are not allowed. A "docs vs code" discrepancy is resolved in favour of the code and itself goes into findings.
"Present in the code" does not mean "enabled" or "deployed": enablement is determined by the environment config.
In every repos[].ref state the revision you read; last_commit_date is the date of the last commit on it.

Determine as facts: language, framework, storage, buses/queues, external integrations, external exposure,
deploy (how and where), edges (edges_out — whom it calls; edges_in — who calls it; mechanism: REST, queue,
websocket, …), the actual role in one line, liveness (whether the code is active). In hypothesis_checks — every
hypothesis of the unit plus the claims made by the name and README. Findings (risks, discrepancies) go into findings.

Return STRICTLY an object per the schema. This is data, not a message to a human.
`

phase('Verify')
const unitPrompt = (u) => [
  COMMON,
  `=== UNIT: ${u.label} (repositories: ${(u.repos || []).join(', ')}) ===`,
  u.ref ? `Revision to read: ${u.ref} (if it does not exist in the repository — say so in notes and read the default branch).` : 'Revision: the default branch; if meaningful code is on another branch — find it and say so.',
  u.hints ? `Hints: ${u.hints}` : '',
  'Hypotheses to check:',
  ...(u.hypotheses || []).map((h, i) => `${i + 1}. ${h}`),
].filter(Boolean).join('\n')

const results = await parallel(UNITS.map((u) => () =>
  agent(unitPrompt(u), { label: `verify:${u.label}`, phase: 'Verify', schema: SCHEMA, model: MODEL })
))
const units = results.filter(Boolean)
log(`Verify: ${units.length} of ${UNITS.length} units returned data`)

// Sample to check: all refuted + a share of confirmed/refined (deterministic: every k-th).
phase('SpotCheck')
const picks = []
for (const u of units) {
  const checks = u.hypothesis_checks || []
  const positive = checks.filter((c) => c.status === 'confirmed' || c.status === 'refined')
  const step = RATIO > 0 ? Math.max(1, Math.round(1 / RATIO)) : Infinity
  checks.forEach((c) => {
    const k = positive.indexOf(c)
    if (c.status === 'refuted' || (k >= 0 && k % step === 0)) {
      picks.push({ unit: u.unit, claim: c.claim, status: c.status, evidence: c.evidence || [] })
    }
  })
}

const SPOT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  properties: {
    items: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          unit: { type: 'string' }, claim: { type: 'string' },
          valid: { type: 'boolean' }, why: { type: 'string' },
        },
        required: ['unit', 'claim', 'valid', 'why'],
      },
    },
  },
  required: ['items'],
}

const spot = picks.length
  ? await agent(
      [
        'Check the evidence addresses. Read-only, no cd, absolute paths and git -C; do not print secrets.',
        `Clones: ${APP}/<repo>. For each item open every address from evidence at the revision stated in it`,
        '(or the default branch) and decide: does the quote exist at the address and does it support the claim with its status.',
        'valid=false if the address does not exist, the quote does not match, or it does not prove the claim; why — in one line.',
        'Items:',
        JSON.stringify(picks, null, 1),
      ].join('\n'),
      { label: 'spot-check', phase: 'SpotCheck', schema: SPOT_SCHEMA, model: MODEL },
    )
  : { items: [] }

const invalid = ((spot && spot.items) || []).filter((i) => !i.valid)
log(`SpotCheck: checked ${picks.length}, not confirmed ${invalid.length} — their status on consolidation → not_found`)

return { units, spotCheck: (spot && spot.items) || [], invalid }
