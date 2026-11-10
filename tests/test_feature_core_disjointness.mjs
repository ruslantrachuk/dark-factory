import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'

// The workflow script is not an importable module, so the test runs the shipped helper itself: the code between the
// `// <pairwiseDisjoint>` and `// </pairwiseDisjoint>` marker lines in feature-core.js.
const source = readFileSync(new URL('../plugins/dark-factory/workflows/feature-core.js', import.meta.url), 'utf8')
const begin = source.indexOf('// <pairwiseDisjoint>\n')
const end = source.indexOf('// </pairwiseDisjoint>')
assert.ok(begin >= 0 && end > begin, 'feature-core.js must keep the pairwiseDisjoint marker lines')
const pairwiseDisjoint = runInNewContext(`${source.slice(begin, end)}\npairwiseDisjoint`)

test('distinct known file paths may run in parallel', () => {
  assert.equal(pairwiseDisjoint([['app/src/a.py'], ['app/src/b.py']]), true)
  assert.equal(pairwiseDisjoint([['app/src/a.py', 'app/tests/test_a.py'], ['app/src/b.py', 'app/tests/test_b.py']]), true)
})

test('exactly conflicting file paths must be serialized', () => {
  assert.equal(pairwiseDisjoint([['app/src/a.py'], ['app/src/a.py']]), false)
})

test('a path repeated inside one task is not an overlap', () => {
  assert.equal(pairwiseDisjoint([['app/src/a.py', './app/src/a.py'], ['app/src/b.py']]), true)
})

test('missing or empty file scope must fail closed to serial execution', () => {
  assert.equal(pairwiseDisjoint([['app/src/a.py'], []]), false)
  assert.equal(pairwiseDisjoint([['app/src/a.py'], null]), false)
  assert.equal(pairwiseDisjoint([['app/src/a.py'], ['  ']]), false)
})

test('lexical aliases cannot evade overlapping file admission', () => {
  assert.equal(pairwiseDisjoint([['app/src/./a.py'], ['app/src/a.py']]), false)
  assert.equal(pairwiseDisjoint([['app/src/sub/../a.py'], ['app/src/a.py']]), false)
  assert.equal(pairwiseDisjoint([['app\\src\\a.py'], ['app/src/a.py']]), false)
})

test('a directory overlaps the files under it, but not a sibling with a shared name prefix', () => {
  assert.equal(pairwiseDisjoint([['app/src'], ['app/src/a.py']]), false)
  assert.equal(pairwiseDisjoint([['app/src/a.py'], ['app/src/']]), false)
  assert.equal(pairwiseDisjoint([['app/src'], ['app/src2/a.py']]), true)
})

test('paths outside the declared repository-relative scope or globs fail closed', () => {
  assert.equal(pairwiseDisjoint([['../src/a.py'], ['app/src/b.py']]), false)
  assert.equal(pairwiseDisjoint([['/tmp/a.py'], ['app/src/b.py']]), false)
  assert.equal(pairwiseDisjoint([['app/src/*.py'], ['app/tests/b.py']]), false)
  assert.equal(pairwiseDisjoint([['app/src/[ab].py'], ['app/tests/b.py']]), false)
})
