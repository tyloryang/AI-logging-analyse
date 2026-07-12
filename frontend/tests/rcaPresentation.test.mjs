import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildDependencyPayload,
  clusterNameWarning,
  collectorStatusLabel,
  confidenceLabel,
  dependencyValidationError,
  isRcaRunning,
  rcaStatusLabel,
  shouldPollAlertGroups,
} from '../src/utils/rcaPresentation.mjs'


test('two-stage RCA states continue polling until analysis is ready', () => {
  assert.equal(isRcaRunning('pending'), true)
  assert.equal(isRcaRunning('facts_ready'), true)
  assert.equal(isRcaRunning('evidence_ready'), true)
  assert.equal(isRcaRunning('awaiting_confirmation'), false)
})

test('alert center polls only while a structured RCA is active', () => {
  assert.equal(shouldPollAlertGroups([{ status: 'analyzing', analysis_hook: { status: 'facts_ready' } }]), true)
  assert.equal(shouldPollAlertGroups([{ status: 'resolved', analysis_hook: { status: 'analysis_ready' } }]), false)
})

test('RCA confidence and collector states have explicit Chinese labels', () => {
  assert.equal(confidenceLabel('high'), '高置信度')
  assert.equal(confidenceLabel('medium'), '中置信度')
  assert.equal(confidenceLabel('low'), '低置信度')
  assert.equal(collectorStatusLabel('unconfigured'), '未配置')
  assert.equal(collectorStatusLabel('timeout'), '超时')
  assert.equal(rcaStatusLabel('facts_ready'), '事实已就绪')
})

test('service dependency form is normalized and warns on unknown cluster names', () => {
  const form = {
    cluster: ' z1 ',
    namespace: ' analyse ',
    service: ' analyse ',
    target: ' mysql-analyse ',
    source: 'cmdb',
    slowlog_config_id: 'slow-1',
    sql_keywords_text: 'large_object, analyse_payload\nselect payload',
  }

  const payload = buildDependencyPayload(form)

  assert.equal(dependencyValidationError(form), '')
  assert.deepEqual(payload.sql_keywords, ['large_object', 'analyse_payload', 'select payload'])
  assert.equal(clusterNameWarning(form.cluster, [{ id: 'c1', name: 'k8s-direct' }]), '集群 z1 尚未在容器管理中配置')
  assert.equal(clusterNameWarning('c1', [{ id: 'c1', name: 'k8s-direct' }]), '')
})
