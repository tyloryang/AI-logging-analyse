import test from 'node:test'
import assert from 'node:assert/strict'

import {
  resolveDefaultLabelNames,
  toggleDefaultLabelName,
} from '../src/utils/logLabelPreferences.mjs'


test('saved default labels keep order and discard labels missing from Loki', () => {
  assert.deepEqual(
    resolveDefaultLabelNames(
      ['pod', 'namespace', 'pod', 'removed'],
      ['app', 'namespace', 'pod'],
      ['namespace'],
    ),
    ['pod', 'namespace'],
  )
})


test('catalog defaults are used when no preference has been saved', () => {
  assert.deepEqual(
    resolveDefaultLabelNames(null, ['app', 'namespace', 'pod'], ['namespace', 'app']),
    ['namespace', 'app'],
  )
})


test('an explicitly empty preference remains empty', () => {
  assert.deepEqual(
    resolveDefaultLabelNames([], ['app', 'namespace'], ['namespace']),
    [],
  )
})


test('toggling a default label adds and removes it', () => {
  assert.deepEqual(toggleDefaultLabelName(['namespace'], 'pod'), ['namespace', 'pod'])
  assert.deepEqual(toggleDefaultLabelName(['namespace', 'pod'], 'namespace'), ['pod'])
})
