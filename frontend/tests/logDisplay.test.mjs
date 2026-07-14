import test from 'node:test'
import assert from 'node:assert/strict'

import { displayLogLine } from '../src/utils/logDisplay.mjs'


test('docker JSON log line displays only its actual log content', () => {
  const raw = JSON.stringify({
    log: 'Failed to make webhook request: context deadline exceeded\n',
    stream: 'stderr',
    time: '2026-07-12T04:38:53.086673Z',
  })

  assert.equal(displayLogLine(raw), 'Failed to make webhook request: context deadline exceeded')
})


test('structured application log prefers message fields over JSON', () => {
  assert.equal(
    displayLogLine('{"level":"error","message":"database timeout","trace_id":"abc"}'),
    'database timeout',
  )
})


test('nested JSON log content is unwrapped repeatedly', () => {
  const raw = JSON.stringify({ log: JSON.stringify({ msg: 'slow request' }) })
  assert.equal(displayLogLine(raw), 'slow request')
})


test('non-JSON log lines remain unchanged', () => {
  assert.equal(displayLogLine('plain text log'), 'plain text log')
})
