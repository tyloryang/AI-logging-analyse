import test from 'node:test'
import assert from 'node:assert/strict'

import {
  CONTEXT_INITIAL_SIDE,
  CONTEXT_MAX_SIDE,
  CONTEXT_PAGE_STEP,
  nextContextCount,
} from '../src/utils/logLoading.mjs'


test('context loads a small first window and grows progressively', () => {
  assert.equal(CONTEXT_INITIAL_SIDE, 20)
  assert.equal(CONTEXT_PAGE_STEP, 50)
  assert.equal(CONTEXT_MAX_SIDE, 500)
  assert.equal(nextContextCount(20), 70)
  assert.equal(nextContextCount(480), 500)
})
