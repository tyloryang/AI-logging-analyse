<template>
  <div class="metrics-page">
    <header class="page-header">
      <div>
        <h1>指标查询</h1>
        <p>执行 PromQL 即时或区间查询，快速查看时序趋势和标签结果。</p>
      </div>
      <div class="actions">
        <button class="btn btn-outline" @click="loadMetricNames" :disabled="loadingMetrics">刷新指标名</button>
        <button class="btn btn-primary" @click="runQuery" :disabled="querying">
          <span v-if="querying" class="spinner-sm"></span>
          执行查询
        </button>
      </div>
    </header>

    <section class="panel result-panel">
      <div class="result-head">
        <div>
          <h2>查询结果</h2>
          <span>{{ resultMeta }}</span>
        </div>
        <div class="pill-row">
          <span>类型 {{ result?.result_type || '-' }}</span>
          <span>序列 {{ seriesRows.length }}</span>
          <span>步长 {{ result?.step || step }}s</span>
        </div>
      </div>

      <div v-if="error" class="error-box">{{ error }}</div>

      <div v-if="querying" class="empty">
        <span class="spinner"></span>
        <p>正在查询 Prometheus</p>
      </div>
      <div v-else-if="!seriesRows.length" class="empty">
        <p>暂无结果</p>
      </div>
      <template v-else>
        <div v-if="mode === 'range'" class="chart-card">
          <svg viewBox="0 0 920 240" preserveAspectRatio="none">
            <line x1="0" y1="220" x2="920" y2="220" class="axis" />
            <line x1="40" y1="0" x2="40" y2="240" class="axis" />
            <polyline
              v-for="line in chartLines"
              :key="line.id"
              :points="line.points"
              :stroke="line.color"
              fill="none"
              stroke-width="2"
            />
          </svg>
          <div class="legend">
            <span v-for="line in chartLines" :key="line.id">
              <i :style="{ background: line.color }"></i>{{ line.name }}
            </span>
          </div>
        </div>

        <div class="series-table-wrap">
          <table>
            <thead>
              <tr>
                <th class="metric-col">Metric</th>
                <th>Labels</th>
                <th>最新值</th>
                <th>点数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in seriesRows" :key="row.id" :class="{ expanded: isSeriesExpanded(row) }">
                <td class="metric-cell">
                  <button class="row-toggle" @click.stop="toggleSeriesRow(row)">
                    {{ isSeriesExpanded(row) ? '收起' : '展开' }}
                  </button>
                  <code class="metric-name" :title="row.metricFull">
                    {{ isSeriesExpanded(row) ? row.metricFull : row.metricName }}
                  </code>
                </td>
                <td class="labels-cell">
                  <template v-if="row.labelEntries.length">
                    <div class="label-chip-list" :class="{ expanded: isSeriesExpanded(row) }">
                      <span v-for="label in visibleLabels(row)" :key="`${row.id}-${label.key}`" class="label-chip">
                        <b>{{ label.key }}</b><code>{{ label.value }}</code>
                      </span>
                    </div>
                    <button
                      v-if="row.labelEntries.length > LABEL_COLLAPSE_LIMIT"
                      class="inline-toggle"
                      @click.stop="toggleSeriesRow(row)"
                    >
                      {{ isSeriesExpanded(row) ? '收起标签' : `还有 ${row.labelEntries.length - LABEL_COLLAPSE_LIMIT} 个` }}
                    </button>
                  </template>
                  <span v-else class="muted">-</span>
                </td>
                <td class="value-cell"><strong>{{ row.lastValue }}</strong></td>
                <td class="count-cell">{{ row.count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>

    <main class="accordion-stack">
      <section class="panel accordion-panel">
        <button class="accordion-head" @click="togglePanel('query')">
          <span class="accordion-title">
            <strong>PromQL 查询配置</strong>
            <small>{{ queryConfigSummary }}</small>
          </span>
          <span class="accordion-icon">{{ collapsed.query ? '展开' : '收起' }}</span>
        </button>
        <div v-show="!collapsed.query" class="accordion-body query-body">
          <textarea v-model="promql" rows="4" spellcheck="false" placeholder='up 或 sum(rate(http_requests_total[5m])) by (service)'></textarea>
          <div class="control-grid">
            <label>
              <span>查询类型</span>
              <div class="mode-toggle">
                <button :class="{ active: mode === 'range' }" @click="mode = 'range'">区间查询</button>
                <button :class="{ active: mode === 'instant' }" @click="mode = 'instant'">即时查询</button>
              </div>
            </label>
            <label>
              <span>时间范围</span>
              <select v-model="range" :disabled="mode === 'instant'">
                <option value="5m">最近 5 分钟</option>
                <option value="15m">最近 15 分钟</option>
                <option value="30m">最近 30 分钟</option>
                <option value="1h">最近 1 小时</option>
                <option value="6h">最近 6 小时</option>
                <option value="24h">最近 24 小时</option>
              </select>
            </label>
            <label>
              <span>步长</span>
              <select v-model.number="step" :disabled="mode === 'instant'">
                <option :value="15">15 秒</option>
                <option :value="30">30 秒</option>
                <option :value="60">1 分钟</option>
                <option :value="300">5 分钟</option>
              </select>
            </label>
          </div>
        </div>
      </section>

      <section class="panel accordion-panel">
        <button class="accordion-head" @click="togglePanel('templates')">
          <span class="accordion-title">
            <strong>常用 PromQL</strong>
            <small>{{ filteredTemplates.length }} 个模板，点击后写入查询语句</small>
          </span>
          <span class="accordion-icon">{{ collapsed.templates ? '展开' : '收起' }}</span>
        </button>
        <div v-show="!collapsed.templates" class="accordion-body">
          <div class="template-list">
            <button
              v-for="tpl in filteredTemplates"
              :key="tpl.name"
              class="template-card"
              @click="applyTemplate(tpl)"
            >
              <strong>{{ tpl.name }}</strong>
              <span>{{ tpl.desc }}</span>
              <code>{{ tpl.query }}</code>
            </button>
          </div>
        </div>
      </section>

      <section class="panel accordion-panel">
        <button class="accordion-head" @click="togglePanel('metrics')">
          <span class="accordion-title">
            <strong>指标检索</strong>
            <small>{{ metricNames.length }} 个指标名，可展开过滤选择</small>
          </span>
          <span class="accordion-icon">{{ collapsed.metrics ? '展开' : '收起' }}</span>
        </button>
        <div v-show="!collapsed.metrics" class="accordion-body metric-body">
          <input v-model.trim="metricSearch" placeholder="过滤指标名" />
          <div class="metric-list">
            <button v-for="name in visibleMetricNames" :key="name" @click="promql = name">
              {{ name }}
            </button>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/index.js'

const templates = [
  { name: '服务存活', desc: 'Prometheus target up 状态', query: 'up' },
  { name: 'CPU 使用率', desc: 'Node Exporter CPU 使用率', query: '100 - (avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)' },
  { name: '内存使用率', desc: '主机内存使用百分比', query: '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100' },
  { name: '磁盘使用率', desc: '文件系统使用百分比', query: '(1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"}) * 100' },
  { name: 'HTTP QPS', desc: '按服务统计 HTTP 请求速率', query: 'sum(rate(http_requests_total[5m])) by (service)' },
  { name: '错误率', desc: '按服务统计 5xx 错误率', query: 'sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)' },
]

const colors = ['#D97757', '#63825B', '#C58A46', '#4f83cc', '#9b6bcc', '#BD564F']
const promql = ref('up')
const mode = ref('range')
const range = ref('30m')
const step = ref(60)
const metricSearch = ref('')
const metricNames = ref([])
const loadingMetrics = ref(false)
const querying = ref(false)
const error = ref('')
const result = ref(null)
const expandedSeries = ref(new Set())
const collapsed = ref({
  query: true,
  templates: true,
  metrics: true,
})
const LABEL_COLLAPSE_LIMIT = 3

const filteredTemplates = computed(() => templates)
const visibleMetricNames = computed(() => {
  const q = metricSearch.value.toLowerCase()
  const names = q ? metricNames.value.filter(name => name.toLowerCase().includes(q)) : metricNames.value
  return names.slice(0, 200)
})

const seriesRows = computed(() => {
  const data = result.value?.data || []
  return data.map((item, index) => {
    const values = item.values || (item.value ? [item.value] : [])
    const last = values[values.length - 1] || []
    const metric = item.metric || {}
    const metricName = metric.__name__ || promql.value.split(/[({\s]/)[0] || `series_${index + 1}`
    const labelEntries = Object.entries(metric)
      .filter(([key]) => key !== '__name__')
      .map(([key, value]) => ({ key, value: String(value) }))
    const labels = labelEntries
      .map(({ key, value }) => `${key}="${value}"`)
      .join(', ')
    const metricFull = labels ? `${metricName}{${labels}}` : metricName
    return {
      id: `${metricName}-${index}`,
      metricName,
      metricFull,
      labelEntries,
      labels: labels || '-',
      values,
      lastValue: formatNumber(last[1]),
      count: values.length,
    }
  })
})

const chartLines = computed(() => {
  const rows = seriesRows.value.slice(0, 6)
  const allValues = rows.flatMap(row => row.values.map(point => Number(point[1])).filter(Number.isFinite))
  const min = Math.min(...allValues, 0)
  const max = Math.max(...allValues, 1)
  const span = max - min || 1
  return rows.map((row, index) => {
    const values = row.values
    const denom = Math.max(values.length - 1, 1)
    const points = values.map((point, i) => {
      const x = 40 + (i / denom) * 860
      const y = 220 - ((Number(point[1]) - min) / span) * 190
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
    return {
      id: row.id,
      name: row.metricName,
      color: colors[index % colors.length],
      points,
    }
  })
})

const resultMeta = computed(() => {
  if (!result.value) return '尚未执行查询'
  return `${result.value.query || promql.value} · ${mode.value === 'range' ? range.value : 'instant'}`
})

const queryConfigSummary = computed(() => {
  const query = promql.value.trim() || '未填写 PromQL'
  const modeText = mode.value === 'range' ? `区间 · ${range.value} · ${step.value}s` : '即时'
  return `${modeText} · ${query}`
})

function rangeSeconds(value) {
  const unit = value.slice(-1)
  const amount = Number(value.slice(0, -1)) || 1
  if (unit === 'm') return amount * 60
  if (unit === 'h') return amount * 3600
  return 1800
}

function formatNumber(value) {
  const num = Number(value)
  if (!Number.isFinite(num)) return value ?? '-'
  if (Math.abs(num) >= 1000) return num.toFixed(0)
  if (Math.abs(num) >= 10) return num.toFixed(2)
  return num.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

function applyTemplate(tpl) {
  promql.value = tpl.query
  collapsed.value.query = false
}

function togglePanel(key) {
  collapsed.value[key] = !collapsed.value[key]
}

function isSeriesExpanded(row) {
  return expandedSeries.value.has(row.id)
}

function toggleSeriesRow(row) {
  const next = new Set(expandedSeries.value)
  if (next.has(row.id)) next.delete(row.id)
  else next.add(row.id)
  expandedSeries.value = next
}

function visibleLabels(row) {
  return isSeriesExpanded(row) ? row.labelEntries : row.labelEntries.slice(0, LABEL_COLLAPSE_LIMIT)
}

async function loadMetricNames() {
  loadingMetrics.value = true
  try {
    const data = await api.prometheusLabelValues('__name__', { limit: 1000 })
    metricNames.value = data.data || []
  } catch {
    metricNames.value = []
  } finally {
    loadingMetrics.value = false
  }
}

async function runQuery() {
  error.value = ''
  if (!promql.value.trim()) {
    error.value = '请填写 PromQL'
    return
  }
  querying.value = true
  expandedSeries.value = new Set()
  try {
    if (mode.value === 'instant') {
      result.value = await api.prometheusQuery({ query: promql.value.trim() })
    } else {
      const end = Math.floor(Date.now() / 1000)
      const start = end - rangeSeconds(range.value)
      result.value = await api.prometheusQueryRange({
        query: promql.value.trim(),
        start,
        end,
        step: step.value,
      })
    }
  } catch (err) {
    error.value = String(err)
    result.value = null
  } finally {
    querying.value = false
  }
}

onMounted(() => {
  loadMetricNames()
  runQuery()
})
</script>

<style scoped>
.metrics-page {
  height: 100%;
  overflow: auto;
  padding: 24px;
  background: var(--bg-base);
  color: var(--text-primary);
}
.page-header,
.actions,
.result-head,
.pill-row,
.mode-toggle,
.legend {
  display: flex;
  gap: 10px;
}
.page-header {
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}
h1 {
  font-size: 26px;
  margin: 0 0 4px;
}
p,
.panel-head span,
.result-head span {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}
.btn {
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 8px 13px;
  background: var(--bg-card);
  color: var(--text-primary);
  cursor: pointer;
}
.btn:disabled {
  opacity: .55;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--accent);
  color: #fff;
}
.btn-outline {
  border-color: var(--border);
}
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.result-head {
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}
h2 {
  font-family: var(--font-sans);
  font-size: 16px;
  margin: 0 0 2px;
}
.mode-toggle {
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 3px;
  width: 100%;
}
.mode-toggle button {
  flex: 1;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-muted);
  padding: 5px 12px;
  cursor: pointer;
}
.mode-toggle button.active {
  color: #fff;
  background: var(--accent);
}
textarea,
input,
select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 9px 10px;
  outline: none;
}
select:disabled {
  opacity: .6;
  cursor: not-allowed;
}
textarea,
code {
  font-family: var(--font-mono);
}
.control-grid {
  display: grid;
  grid-template-columns: minmax(240px, 1.2fr) repeat(2, minmax(180px, .9fr));
  gap: 10px;
  margin-top: 10px;
}
label span,
.section-title {
  display: block;
  margin-bottom: 6px;
  color: var(--text-muted);
  font-size: 12px;
}
.error-box {
  margin-top: 10px;
  border: 1px solid rgba(var(--error-rgb), .24);
  background: rgba(var(--error-rgb), .08);
  color: var(--error);
  border-radius: 7px;
  padding: 8px 10px;
}
.template-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px;
}
.template-card {
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-base);
  color: var(--text-primary);
  padding: 10px;
  cursor: pointer;
}
.template-card:hover {
  border-color: var(--accent);
}
.template-card strong,
.template-card span,
.template-card code {
  display: block;
}
.template-card span {
  color: var(--text-muted);
  font-size: 12px;
  margin: 2px 0 6px;
}
.template-card code {
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.metric-list {
  max-height: 260px;
  overflow: auto;
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.metric-list button {
  text-align: left;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  padding: 6px 8px;
  cursor: pointer;
  font-family: var(--font-mono);
  font-size: 12px;
}
.metric-list button:hover {
  border-color: var(--border);
  background: var(--bg-hover);
  color: var(--text-primary);
}
.result-panel {
  margin-top: 0;
}
.accordion-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}
.accordion-panel {
  padding: 0;
  overflow: hidden;
}
.accordion-head {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  cursor: pointer;
  text-align: left;
}
.accordion-head:hover {
  background: var(--bg-hover);
}
.accordion-title {
  min-width: 0;
  display: grid;
  gap: 2px;
}
.accordion-title strong {
  font-size: 14px;
}
.accordion-title small {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.accordion-icon {
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 9px;
  color: var(--text-muted);
  font-size: 12px;
}
.accordion-body {
  border-top: 1px solid var(--border);
  padding: 12px 14px 14px;
}
.query-body textarea {
  min-height: 92px;
  resize: vertical;
}
.pill-row {
  flex-wrap: wrap;
  justify-content: flex-end;
}
.pill-row span {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 9px;
  color: var(--text-muted);
  font-size: 12px;
}
.empty {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-muted);
}
.chart-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  background: var(--bg-base);
  margin-bottom: 12px;
}
svg {
  width: 100%;
  height: 320px;
}
.axis {
  stroke: var(--border);
  stroke-width: 1;
}
.legend {
  flex-wrap: wrap;
  margin-top: 8px;
}
.legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  font-size: 12px;
}
.legend i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.series-table-wrap {
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  table-layout: fixed;
}
th,
td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
th {
  color: var(--text-muted);
  background: var(--bg-base);
  font-weight: 600;
}
.metric-col {
  width: 30%;
}
.metric-cell {
  min-width: 0;
}
.metric-cell,
.labels-cell {
  color: var(--text-secondary);
}
.metric-name {
  display: block;
  margin-top: 6px;
  max-width: 100%;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
tr.expanded .metric-name {
  white-space: normal;
  overflow: visible;
  word-break: break-all;
}
.row-toggle,
.inline-toggle {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-base);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
}
.row-toggle {
  padding: 4px 8px;
}
.inline-toggle {
  margin-top: 6px;
  padding: 3px 8px;
}
.row-toggle:hover,
.inline-toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.label-chip-list {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  max-width: 100%;
  overflow: hidden;
}
.label-chip-list.expanded {
  flex-wrap: wrap;
  overflow: visible;
}
.label-chip {
  min-width: 0;
  max-width: 220px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-base);
  padding: 3px 7px;
  color: var(--text-muted);
  font-size: 11px;
}
.label-chip b {
  flex-shrink: 0;
  color: var(--text-primary);
  font-weight: 600;
}
.label-chip code {
  min-width: 0;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.label-chip-list.expanded .label-chip {
  max-width: 100%;
}
.label-chip-list.expanded .label-chip code {
  white-space: normal;
  word-break: break-all;
}
.value-cell,
.count-cell {
  width: 96px;
  white-space: nowrap;
}
.muted {
  color: var(--text-muted);
}
.spinner,
.spinner-sm {
  display: inline-block;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .75s linear infinite;
}
.spinner { width: 22px; height: 22px; }
.spinner-sm { width: 14px; height: 14px; }
@keyframes spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 1050px) {
  .control-grid {
    grid-template-columns: 1fr;
  }
}
</style>
