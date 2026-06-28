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

    <main class="query-grid">
      <section class="panel query-panel">
        <div class="panel-head">
          <div>
            <h2>PromQL</h2>
            <span>支持区间查询和即时查询</span>
          </div>
          <div class="mode-toggle">
            <button :class="{ active: mode === 'range' }" @click="mode = 'range'">区间</button>
            <button :class="{ active: mode === 'instant' }" @click="mode = 'instant'">即时</button>
          </div>
        </div>

        <textarea v-model="promql" rows="5" spellcheck="false" placeholder='up 或 sum(rate(http_requests_total[5m])) by (service)'></textarea>

        <div class="control-grid">
          <label>
            <span>时间范围</span>
            <select v-model="range">
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
            <select v-model.number="step">
              <option :value="15">15 秒</option>
              <option :value="30">30 秒</option>
              <option :value="60">1 分钟</option>
              <option :value="300">5 分钟</option>
            </select>
          </label>
        </div>

        <div v-if="error" class="error-box">{{ error }}</div>

        <div class="template-section">
          <div class="section-title">常用 PromQL</div>
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

      <aside class="panel explorer-panel">
        <div class="panel-head">
          <div>
            <h2>指标检索</h2>
            <span>{{ metricNames.length }} 个指标名</span>
          </div>
        </div>
        <input v-model.trim="metricSearch" placeholder="过滤指标名" />
        <div class="metric-list">
          <button v-for="name in visibleMetricNames" :key="name" @click="promql = name">
            {{ name }}
          </button>
        </div>
      </aside>
    </main>

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
                <th>Metric</th>
                <th>Labels</th>
                <th>最新值</th>
                <th>点数</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in seriesRows" :key="row.id">
                <td>{{ row.metricName }}</td>
                <td><code>{{ row.labels }}</code></td>
                <td><strong>{{ row.lastValue }}</strong></td>
                <td>{{ row.count }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>
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
    const labels = Object.entries(metric)
      .filter(([key]) => key !== '__name__')
      .map(([key, value]) => `${key}="${value}"`)
      .join(', ')
    return {
      id: `${metricName}-${index}`,
      metricName,
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
.panel-head,
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
.query-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 14px;
}
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.panel-head,
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
}
.mode-toggle button {
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
textarea,
code {
  font-family: var(--font-mono);
}
.control-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
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
.template-section {
  margin-top: 14px;
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
.explorer-panel {
  min-height: 430px;
  display: flex;
  flex-direction: column;
}
.metric-list {
  flex: 1;
  min-height: 0;
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
  margin-top: 14px;
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
  height: 240px;
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
td code {
  color: var(--text-secondary);
  word-break: break-all;
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
  .query-grid,
  .control-grid {
    grid-template-columns: 1fr;
  }
}
</style>
