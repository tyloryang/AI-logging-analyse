const RUNNING_STATES = new Set(['pending', 'running', 'facts_ready', 'evidence_ready'])

const STATUS_LABELS = {
  queued: '排队中',
  pending: '等待中',
  running: '采集中',
  facts_ready: '事实已就绪',
  evidence_ready: '证据已就绪',
  awaiting_confirmation: '待确认',
  confirmed: '已确认',
  needs_review: '待复核',
  error: '失败',
}

const CONFIDENCE_LABELS = {
  high: '高置信度',
  medium: '中置信度',
  low: '低置信度',
}

const COLLECTOR_STATUS_LABELS = {
  collecting: '采集中',
  completed: '完成',
  timeout: '超时',
  unavailable: '不可用',
  unconfigured: '未配置',
}

export function isRcaRunning(status) {
  return RUNNING_STATES.has(status)
}

export function rcaStatusLabel(status) {
  return STATUS_LABELS[status] || status || '--'
}

export function confidenceLabel(confidence) {
  return CONFIDENCE_LABELS[confidence] || '低置信度'
}

export function collectorStatusLabel(status) {
  return COLLECTOR_STATUS_LABELS[status] || status || '--'
}

export function shouldPollAlertGroups(groups) {
  return (groups || []).some(group => (
    group?.status === 'analyzing'
    && group?.analysis_hook?.status !== 'analysis_ready'
  ))
}

export function dependencyValidationError(form) {
  if (!String(form?.service || '').trim()) return '服务名不能为空'
  if (!String(form?.target || '').trim()) return 'MySQL 依赖目标不能为空'
  if (!String(form?.slowlog_config_id || '').trim()) return '请选择慢日志配置'
  return ''
}

export function buildDependencyPayload(form) {
  const clean = value => String(value || '').trim()
  const keywords = clean(form?.sql_keywords_text)
    .split(/[,\n]/)
    .map(value => value.trim())
    .filter(Boolean)
  return {
    id: clean(form?.id),
    cluster: clean(form?.cluster),
    namespace: clean(form?.namespace),
    service: clean(form?.service),
    dependency_type: 'mysql',
    target: clean(form?.target),
    source: clean(form?.source) || 'cmdb',
    slowlog_config_id: clean(form?.slowlog_config_id),
    source_host: clean(form?.source_host),
    db_user: clean(form?.db_user),
    sql_keywords: keywords,
  }
}

export function clusterNameWarning(cluster, clusters) {
  const value = String(cluster || '').trim()
  if (!value) return ''
  const matched = (clusters || []).some(item => value === String(item?.id || '') || value === String(item?.name || ''))
  return matched ? '' : `集群 ${value} 尚未在容器管理中配置`
}
