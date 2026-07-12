<template>
  <div class="page alert-center">
    <div class="page-header">
      <h1>告警中心</h1>
      <span class="subtitle">基建告警 · 运营数据告警 · 错误/异常日志告警 · Hook 驱动 RCA</span>
      <button class="btn btn-outline btn-sm" style="margin-left:auto" @click="load" :disabled="loading">
        {{ loading ? '刷新中...' : '刷新' }}
      </button>
    </div>

    <div class="tab-bar">
      <button
        v-for="t in TABS"
        :key="t.key"
        class="tab"
        :class="{ active: tab === t.key }"
        @click="switchTab(t.key)"
      >
        {{ t.label }}
        <span v-if="t.key !== 'all'" class="tab-count">{{ countByStatus(t.key) }}</span>
      </button>

      <div class="alert-filters">
        <select v-model="filterType" @change="applyFilters" class="filter-select" title="告警类型">
          <option value="">全部告警类型</option>
          <option v-for="type in filterOptions.alert_types" :key="type.key" :value="type.key">{{ type.label }}</option>
        </select>
        <select v-model="filterNs" @change="applyFilters" class="filter-select" title="K8s Namespace">
          <option value="">全部 Namespace</option>
          <option v-for="ns in filterOptions.namespaces" :key="ns" :value="ns">{{ ns }}</option>
        </select>
        <select v-model="filterEnv" @change="applyFilters" class="filter-select" title="环境">
          <option value="">全部环境</option>
          <option v-for="env in filterOptions.envs" :key="env" :value="env">{{ env }}</option>
        </select>
        <input v-model="filterSvc" @input="applyFilters" class="filter-input" placeholder="服务名过滤..." />
      </div>
    </div>

    <div class="webhook-tip">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 8v4m0 4h.01" />
      </svg>
      AlertManager Webhook：
      <code>{{ webhookUrl }}</code>
      <button class="copy-btn" @click="copyWebhook">{{ copied ? '已复制' : '复制' }}</button>
    </div>

    <div class="type-strip">
      <button
        v-for="type in alertTypeOptions"
        :key="type.key"
        class="type-card"
        :class="[`type-${type.key}`, { active: filterType === type.key }]"
        @click="switchType(type.key)"
      >
        <b>{{ countByType(type.key) }}</b>
        <span>{{ type.label }}</span>
      </button>
    </div>

    <div v-if="loading" class="empty-state"><div class="spinner"></div></div>
    <div v-else-if="!filtered.length" class="empty-state">
      <div class="icon">🔔</div>
      <div>当前筛选条件下暂无告警</div>
    </div>

    <div v-else class="alert-results">
      <div class="batch-toolbar">
        <label class="select-all">
          <input
            type="checkbox"
            :checked="allFilteredSelected"
            :indeterminate="partlyFilteredSelected"
            @change="toggleSelectAll"
          />
          <span>全选当前结果</span>
        </label>
        <span class="selected-count">已选 {{ selectedCount }} 条</span>
        <div class="batch-actions">
          <button
            class="btn btn-sm btn-outline"
            :disabled="!suppressibleCount || batchUpdating"
            @click="batchUpdate('suppressed')"
          >
            批量抑制<span v-if="suppressibleCount">（{{ suppressibleCount }}）</span>
          </button>
          <button
            class="btn btn-sm btn-primary"
            :disabled="!resolvableCount || batchUpdating"
            @click="batchUpdate('resolved')"
          >
            批量解决<span v-if="resolvableCount">（{{ resolvableCount }}）</span>
          </button>
          <button v-if="selectedCount" class="btn btn-sm btn-ghost" :disabled="batchUpdating" @click="clearSelection">
            取消选择
          </button>
        </div>
      </div>

      <div v-if="batchNotice.text" class="batch-notice" :class="batchNotice.type">{{ batchNotice.text }}</div>

      <div class="groups-list">
      <div
        v-for="group in filtered"
        :key="group.id"
        class="group-card"
        :class="[group.severity, { selected: selectedIds.has(group.id) }]"
      >
        <div class="group-head">
          <input
            class="group-select"
            type="checkbox"
            :checked="selectedIds.has(group.id)"
            :aria-label="`选择告警 ${group.alertname || group.id}`"
            @change="toggleSelection(group.id)"
          />
          <span class="sev-dot" :class="group.severity"></span>
          <span class="group-name">{{ group.alertname || 'Unknown Alert' }}</span>
          <span class="type-chip" :class="`type-${group.alert_type || 'infra'}`">
            {{ group.alert_type_label || TYPE_LABEL[group.alert_type] || '基建告警' }}
          </span>
          <span class="group-svc mono">{{ group.service || 'unknown' }}</span>
          <span class="group-count">{{ group.count }} 次</span>
          <span class="status-chip" :class="group.status">{{ STATUS_LABEL[group.status] || group.status }}</span>
          <div class="group-actions">
            <button class="btn btn-sm btn-primary" @click="openRca(group)">
              {{ group.rca_id ? '查看 RCA' : '进入 RCA' }}
            </button>
            <button v-if="group.status !== 'resolved'" class="btn btn-sm btn-outline" @click="resolve(group)">解决</button>
            <button v-if="!['suppressed', 'resolved'].includes(group.status)" class="btn btn-sm btn-ghost" @click="suppress(group)">抑制</button>
          </div>
        </div>

        <div v-if="group.summary" class="group-summary">{{ group.summary }}</div>

        <div v-if="group.analysis_hook" class="rca-progress">
          <span class="rca-progress-label">RCA：{{ rcaStatusLabel(group.analysis_hook.status) }}</span>
          <span v-if="group.analysis_hook.facts_ready_ms != null">事实 {{ group.analysis_hook.facts_ready_ms }}ms</span>
          <span v-if="group.analysis_hook.analysis_ready_ms != null">结论 {{ group.analysis_hook.analysis_ready_ms }}ms</span>
          <span v-if="group.analysis_hook.top_confidence" class="confidence-inline" :class="group.analysis_hook.top_confidence">
            {{ confidenceLabel(group.analysis_hook.top_confidence) }}
          </span>
        </div>

        <div class="group-meta">
          <span>首次：<span class="mono">{{ fmt(group.first_at) }}</span></span>
          <span>最近：<span class="mono">{{ fmt(group.last_at) }}</span></span>
          <span v-if="group.analysis_strategy">策略：{{ ANALYSIS_LABEL[group.analysis_strategy] || group.analysis_strategy }}</span>
          <span v-if="group.resolved_at">解决：<span class="mono">{{ fmt(group.resolved_at) }}</span></span>
        </div>

        <!-- AI 根因分析报告（aiops_router 派单结果） -->
        <div v-if="group.ai_report" class="ai-report-block">
          <button class="ai-report-toggle" @click="toggleAiReport(group.id)">
            <span class="ai-report-badge">🤖 AI 根因分析</span>
            <span class="ai-report-time mono" v-if="group.ai_report_at">{{ fmt(group.ai_report_at) }}</span>
            <span class="ai-report-arrow">{{ aiReportOpen.has(group.id) ? '▲' : '▼' }}</span>
          </button>
          <pre v-if="aiReportOpen.has(group.id)" class="ai-report-body">{{ group.ai_report }}</pre>
        </div>

        <div v-if="group.notify_targets?.length" class="group-routes">
          <span
            v-for="target in group.notify_targets"
            :key="target.group_id || target.group_name"
            class="route-chip"
          >
            推送到 {{ target.group_name }}
            <span v-if="target.matches?.length" class="route-match">· {{ formatMatches(target.matches) }}</span>
          </span>
        </div>
        <div v-else-if="group.notify_via_global_feishu" class="group-routes">
          <span class="route-chip fallback">未命中分组路由，走全局飞书告警</span>
        </div>

        <button class="expand-btn" @click="toggleExpand(group.id)">
          {{ expanded.has(group.id) ? '▲ 收起' : `▼ 展开 ${group.raw_alerts?.length || 0} 条原始告警` }}
        </button>

        <div v-if="expanded.has(group.id)" class="raw-list">
          <div v-for="(alert, idx) in group.raw_alerts" :key="idx" class="raw-item">
            <div class="raw-labels">
              <span v-for="(value, key) in alert.labels" :key="key" class="label-chip">{{ key }}=<b>{{ value }}</b></span>
            </div>
            <div v-if="alert.annotations?.description" class="raw-desc">{{ alert.annotations.description }}</div>
            <div class="raw-time mono">{{ fmt(alert.startsAt) }}</div>
          </div>
        </div>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'
import { confidenceLabel, rcaStatusLabel, shouldPollAlertGroups } from '../utils/rcaPresentation.mjs'

const router = useRouter()

// AI 报告展开状态（按 group.id）
const aiReportOpen = ref(new Set())
function toggleAiReport(id) {
  const next = new Set(aiReportOpen.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  aiReportOpen.value = next
}

const TABS = [
  { key: 'all', label: '全部' },
  { key: 'new', label: '新建' },
  { key: 'grouped', label: '已聚合' },
  { key: 'analyzing', label: '分析中' },
  { key: 'suppressed', label: '已抑制' },
  { key: 'resolved', label: '已解决' },
]

const STATUS_LABEL = {
  new: '新建',
  grouped: '已聚合',
  analyzing: '分析中',
  suppressed: '已抑制',
  resolved: '已解决',
}

const TYPE_LABEL = {
  infra: '基建告警',
  business: '运营数据告警',
  log_exception: '错误/异常日志告警',
}

const ANALYSIS_LABEL = {
  infra_first: '基建优先',
  metric_trace_first: '指标/Trace 优先',
  logs_context_code_first: '日志上下文/源码优先',
}

const loading = ref(false)
const groups = ref([])
const tab = ref('all')
const expanded = ref(new Set())
const copied = ref(false)
const filterType = ref('')
const filterNs = ref('')
const filterEnv = ref('')
const filterSvc = ref('')
const filterOptions = ref({ namespaces: [], envs: [], alert_types: [] })
const typeStats = ref({})
const selectedIds = ref(new Set())
const batchUpdating = ref(false)
const batchNotice = ref({ type: '', text: '' })
let pollTimer = null

const webhookUrl = computed(() => `${window.location.protocol}//${window.location.host}/api/alerts/webhook`)
const alertTypeOptions = computed(() => {
  const remote = filterOptions.value.alert_types || []
  if (remote.length) return remote
  return Object.entries(TYPE_LABEL).map(([key, label]) => ({ key, label }))
})

const filtered = computed(() => {
  if (tab.value === 'all') return groups.value
  return groups.value.filter(group => group.status === tab.value)
})
const selectedGroups = computed(() => groups.value.filter(group => selectedIds.value.has(group.id)))
const selectedCount = computed(() => selectedIds.value.size)
const allFilteredSelected = computed(() => (
  filtered.value.length > 0 && filtered.value.every(group => selectedIds.value.has(group.id))
))
const partlyFilteredSelected = computed(() => (
  !allFilteredSelected.value && filtered.value.some(group => selectedIds.value.has(group.id))
))
const suppressibleCount = computed(() => selectedGroups.value.filter(
  group => !['suppressed', 'resolved'].includes(group.status),
).length)
const resolvableCount = computed(() => selectedGroups.value.filter(group => group.status !== 'resolved').length)

function countByStatus(status) {
  return groups.value.filter(group => group.status === status).length
}

function countByType(type) {
  if (typeof typeStats.value[type] === 'number') return typeStats.value[type]
  return groups.value.filter(group => (group.alert_type || 'infra') === type).length
}

async function switchType(type) {
  filterType.value = filterType.value === type ? '' : type
  clearSelection()
  await load()
}

function switchTab(nextTab) {
  tab.value = nextTab
  clearSelection()
}

async function applyFilters() {
  clearSelection()
  await load()
}

function clearSelection() {
  selectedIds.value = new Set()
}

function toggleSelection(id) {
  const next = new Set(selectedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedIds.value = next
}

function toggleSelectAll() {
  const next = new Set(selectedIds.value)
  if (allFilteredSelected.value) {
    filtered.value.forEach(group => next.delete(group.id))
  } else {
    filtered.value.forEach(group => next.add(group.id))
  }
  selectedIds.value = next
}

function fmt(iso) {
  if (!iso) return '--'
  return iso.slice(0, 19).replace('T', ' ')
}

function formatMatches(matches = []) {
  return matches.map(item => `${item.label}=${item.actual || item.value || '*'}`).join('，')
}

function toggleExpand(id) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expanded.value = next
}

async function load() {
  if (pollTimer) clearTimeout(pollTimer)
  loading.value = true
  try {
    const params = {}
    if (filterType.value) params.alert_type = filterType.value
    if (filterNs.value) params.namespace = filterNs.value
    if (filterEnv.value) params.env = filterEnv.value
    if (filterSvc.value) params.service = filterSvc.value
    const [result, options, stats] = await Promise.all([
      api.alertGroups(params),
      api.alertFilters().catch(() => ({ namespaces: [], envs: [] })),
      api.alertStats().catch(() => ({ by_type: {} })),
    ])
    groups.value = result.groups || []
    const visibleIds = new Set(groups.value.map(group => group.id))
    selectedIds.value = new Set([...selectedIds.value].filter(id => visibleIds.has(id)))
    filterOptions.value = options
    typeStats.value = stats.by_type || {}
  } catch (error) {
    console.error(error)
  } finally {
    loading.value = false
    if (shouldPollAlertGroups(groups.value)) {
      pollTimer = setTimeout(load, 2500)
    }
  }
}

async function resolve(group) {
  await api.alertUpdateStatus(group.id, { status: 'resolved' })
  await load()
}

async function suppress(group) {
  await api.alertUpdateStatus(group.id, { status: 'suppressed' })
  await load()
}

async function batchUpdate(status) {
  const isSuppress = status === 'suppressed'
  const targetGroups = selectedGroups.value.filter(group => (
    isSuppress ? !['suppressed', 'resolved'].includes(group.status) : group.status !== 'resolved'
  ))
  if (!targetGroups.length) return

  const actionLabel = isSuppress ? '抑制' : '解决'
  if (!window.confirm(`确认批量${actionLabel}已选中的 ${targetGroups.length} 条告警吗？`)) return

  batchUpdating.value = true
  batchNotice.value = { type: '', text: '' }
  try {
    const result = await api.alertBatchUpdateStatus({
      group_ids: targetGroups.map(group => group.id),
      status,
    })
    const updated = result.updated?.length || 0
    const skipped = result.skipped?.length || 0
    const missing = result.missing?.length || 0
    batchNotice.value = {
      type: missing ? 'warning' : 'success',
      text: `批量${actionLabel}完成：成功 ${updated} 条，跳过 ${skipped} 条${missing ? `，未找到 ${missing} 条` : ''}`,
    }
    clearSelection()
    await load()
  } catch (error) {
    const detail = error?.response?.data?.detail || error?.message || '请求失败'
    batchNotice.value = { type: 'error', text: `批量${actionLabel}失败：${detail}` }
  } finally {
    batchUpdating.value = false
  }
}

async function openRca(group) {
  if (group.rca_id) {
    router.push({ path: '/aiops/rca', query: { rca_id: group.rca_id } })
    return
  }
  const result = await api.alertTriggerRca(group.id)
  if (result?.rca_id) {
    router.push({ path: '/aiops/rca', query: { rca_id: result.rca_id } })
  }
}

async function copyWebhook() {
  try {
    await navigator.clipboard.writeText(webhookUrl.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}

onMounted(load)
onBeforeUnmount(() => {
  if (pollTimer) clearTimeout(pollTimer)
})
</script>

<style scoped>
.tab-bar { display: flex; gap: 2px; margin-bottom: 16px; border-bottom: 1px solid var(--border-light); flex-wrap: wrap; align-items: flex-end; }
.alert-filters { display: flex; gap: 6px; margin-left: auto; padding-bottom: 4px; }
.filter-select { padding: 4px 8px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 12px; }
.filter-input { padding: 4px 8px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 12px; width: 140px; }
.tab {
  padding: 8px 16px; font-size: 13px; border: none; background: none;
  cursor: pointer; color: var(--text-secondary); border-bottom: 2px solid transparent;
  margin-bottom: -1px; transition: all .12s;
}
.tab:hover { color: var(--text-primary); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 500; }
.tab-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 18px; height: 18px; padding: 0 5px;
  border-radius: 9px; font-size: 10px; font-weight: 600;
  background: var(--bg-surface); color: var(--text-muted); margin-left: 5px;
}

.webhook-tip {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 12px; background: var(--accent-dim); border: 1px solid var(--border-accent);
  border-radius: var(--radius); font-size: 12px; color: var(--text-secondary);
  margin-bottom: 16px;
}
.webhook-tip code {
  font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px;
  color: var(--accent); background: none; border: none; padding: 0;
}
.copy-btn {
  padding: 2px 8px; font-size: 11px; border-radius: 3px;
  border: 1px solid var(--border-accent); background: none;
  color: var(--accent); cursor: pointer;
}

.type-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.type-card {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 54px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
}
.type-card:hover,
.type-card.active {
  border-color: var(--accent);
  background: var(--accent-dim);
}
.type-card b {
  font-size: 20px;
  line-height: 1;
  color: var(--text-primary);
}
.type-card span {
  font-size: 12px;
  font-weight: 600;
}
.type-card.type-infra b { color: var(--warning); }
.type-card.type-business b { color: var(--success); }
.type-card.type-log_exception b { color: var(--error); }

.groups-list { display: flex; flex-direction: column; gap: 10px; }
.alert-results { display: flex; flex-direction: column; gap: 10px; }
.batch-toolbar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg-card); position: sticky; top: 0; z-index: 5;
}
.select-all { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; cursor: pointer; }
.select-all input, .group-select { accent-color: var(--accent); cursor: pointer; }
.selected-count { font-size: 12px; color: var(--text-muted); }
.batch-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; flex-wrap: wrap; }
.batch-notice { padding: 8px 12px; border-radius: var(--radius); font-size: 12px; }
.batch-notice.success { background: rgba(26,127,55,.1); color: var(--success); }
.batch-notice.warning { background: rgba(245,158,11,.12); color: var(--warning); }
.batch-notice.error { background: rgba(239,68,68,.12); color: var(--error); }

.group-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-left: 4px solid var(--border-strong);
  border-radius: var(--radius-card);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: box-shadow .15s;
}
.group-card:hover { box-shadow: var(--shadow-sm); }
.group-card.selected { box-shadow: 0 0 0 1px var(--accent); background: var(--accent-dim); }
.group-card.critical { border-left-color: var(--error); }
.group-card.warning { border-left-color: var(--warning); }
.group-card.info { border-left-color: var(--accent); }

.group-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.group-select { width: 15px; height: 15px; flex-shrink: 0; }
.sev-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.sev-dot.critical, .sev-dot.error { background: var(--error); }
.sev-dot.warning { background: var(--warning); }
.sev-dot.info { background: var(--accent); }
.group-name { font-weight: 600; font-size: 13px; }
.type-chip {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 3px;
  white-space: nowrap;
}
.type-chip.type-infra { background: rgba(245,158,11,.14); color: var(--warning); }
.type-chip.type-business { background: rgba(26,127,55,.12); color: var(--success); }
.type-chip.type-log_exception { background: rgba(239,68,68,.12); color: var(--error); }
.group-svc { font-size: 12px; color: var(--text-secondary); }
.group-count { font-size: 12px; color: var(--text-muted); margin-left: auto; }
.group-actions { display: flex; gap: 6px; }

.status-chip {
  font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 3px;
}
.status-chip.new { background: var(--accent-dim); color: var(--accent); }
.status-chip.grouped { background: rgba(154,103,0,.1); color: var(--warning); }
.status-chip.analyzing { background: rgba(56,139,253,.12); color: var(--accent); }
.status-chip.suppressed { background: var(--bg-surface); color: var(--text-muted); }
.status-chip.resolved { background: rgba(26,127,55,.1); color: var(--success); }

.group-summary { font-size: 13px; color: var(--text-secondary); }
.rca-progress {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 7px 10px; border: 1px solid var(--border-accent);
  border-radius: 7px; background: var(--accent-dim);
  font-size: 11px; color: var(--text-secondary);
}
.rca-progress-label { color: var(--accent); font-weight: 700; }
.confidence-inline { padding: 2px 7px; border-radius: 999px; font-weight: 700; }
.confidence-inline.high { color: var(--success); background: rgba(26,127,55,.12); }
.confidence-inline.medium { color: var(--warning); background: rgba(210,153,34,.12); }
.confidence-inline.low { color: var(--error); background: rgba(248,81,73,.12); }
.group-meta { display: flex; gap: 16px; font-size: 11px; color: var(--text-muted); }
.group-routes { display: flex; flex-wrap: wrap; gap: 6px; }

/* AI 根因分析报告块 */
.ai-report-block {
  border: 1px solid rgba(129,140,248,.3);
  border-radius: 8px;
  background: rgba(129,140,248,.05);
  overflow: hidden;
}
.ai-report-toggle {
  display: flex; align-items: center; gap: 8px;
  width: 100%;
  background: transparent; border: 0;
  padding: 8px 12px;
  cursor: pointer;
  text-align: left;
}
.ai-report-badge {
  font-size: 12px; font-weight: 600;
  color: var(--accent, #818cf8);
}
.ai-report-time { font-size: 11px; color: var(--text-muted); }
.ai-report-arrow { margin-left: auto; font-size: 10px; color: var(--text-muted); }
.ai-report-body {
  margin: 0;
  padding: 10px 14px;
  border-top: 1px dashed rgba(129,140,248,.25);
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 420px;
  overflow-y: auto;
  font-family: inherit;
}
.route-chip {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: rgba(56,139,253,.12); color: var(--accent);
}
.route-chip.fallback { background: var(--bg-surface); color: var(--text-muted); }
.route-match { color: inherit; opacity: .9; }

.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
.btn-ghost:hover { border-color: var(--warning); color: var(--warning); }

.expand-btn {
  align-self: flex-start; font-size: 11px; color: var(--accent);
  background: none; border: none; cursor: pointer; padding: 0;
}
.expand-btn:hover { text-decoration: underline; }

.raw-list { display: flex; flex-direction: column; gap: 6px; padding-top: 4px; }
.raw-item {
  background: var(--bg-surface); border-radius: var(--radius);
  padding: 8px 10px; display: flex; flex-direction: column; gap: 4px;
}
.raw-labels { display: flex; flex-wrap: wrap; gap: 4px; }
.label-chip {
  font-size: 11px; background: var(--accent-dim); color: var(--accent);
  padding: 1px 6px; border-radius: 3px; font-family: 'Cascadia Code', 'Consolas', monospace;
}
.raw-desc { font-size: 12px; color: var(--text-secondary); }
.raw-time { font-size: 11px; color: var(--text-muted); }

@media (max-width: 720px) {
  .type-strip { grid-template-columns: 1fr; }
  .alert-filters { width: 100%; margin-left: 0; flex-wrap: wrap; }
  .batch-actions { width: 100%; margin-left: 0; }
}
</style>
