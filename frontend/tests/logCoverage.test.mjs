import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildCoverageSummary,
  countLoadedPods,
  replacePodFilters,
} from '../src/utils/logCoverage.mjs'


test('coverage summary distinguishes matched rows from loaded rows', () => {
  const summary = buildCoverageSummary({
    totalLogs: 1056869,
    loadedCount: 200,
    loadedPods: 2,
    totalPods: 25,
    hasMore: true,
  })

  assert.equal(summary.text, '匹配 1,056,869 条 · 已加载 200 条 · 覆盖 2/25 个 Pod')
  assert.equal(summary.truncated, true)
})


test('loaded pod count uses the resolved Loki pod label', () => {
  const rows = [
    { labels: { pod_name: 'api-1' } },
    { labels: { pod_name: 'api-1' } },
    { labels: { pod_name: 'api-2' } },
    { labels: {} },
  ]

  assert.equal(countLoadedPods(rows, 'pod_name'), 2)
})


test('pod drill-down replaces stale namespace and pod filters', () => {
  const result = replacePodFilters(
    [
      { label: 'env', value: 'prod' },
      { label: 'namespace', value: 'old-ns' },
      { label: 'pod', value: 'old-pod' },
    ],
    {
      namespaceLabel: 'namespace',
      namespace: 'new-ns',
      podLabel: 'pod',
      pod: 'api-1',
    },
  )

  assert.deepEqual(result, [
    { label: 'env', value: 'prod' },
    { label: 'namespace', value: 'new-ns' },
    { label: 'pod', value: 'api-1' },
  ])
})
