<template>
  <div class="http-metrics-page">
    <header class="page-header">
      <div>
        <h1>接口指标监控</h1>
        <p>基于 Prometheus http_server_requests_seconds_count，按自定义标签过滤与分组生成接口指标图表。</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-outline" :disabled="loadingLabels" @click="loadLabels">刷新标签</button>
        <button class="btn btn-primary" :disabled="loading" @click="loadMetrics">
          <span v-if="loading" class="spinner-sm"></span>
          生成图表
        </button>
      </div>
    </header>

    <section class="panel config-panel">
      <div class="config-grid">
        <label>
          <span>指标名</span>
          <input v-model.trim="form.metric" placeholder="http_server_requests_seconds_count" />
        </label>
        <label>
          <span>时间范围</span>
          <select v-model.number="form.range_minutes">
            <option :value="5">最近 5 分钟</option>
            <option :value="15">最近 15 分钟</option>
            <option :value="30">最近 30 分钟</option>
            <option :value="60">最近 1 小时</option>
            <option :value="360">最近 6 小时</option>
            <option :value="1440">最近 24 小时</option>
          </select>
        </label>
        <label>
          <span>采样步长</span>
          <select v-model.number="form.step">
            <option :value="15">15 秒</option>
            <option :value="30">30 秒</option>
            <option :value="60">1 分钟</option>
            <option :value="300">5 分钟</option>
          </select>
        </label>
        <label>
          <span>Rate 窗口</span>
          <select v-model="form.rate_window">
            <option value="1m">1 分钟</option>
            <option value="5m">5 分钟</option>
            <option value="10m">10 分钟</option>
            <option value="15m">15 分钟</option>
          </select>
        </label>
        <label>
          <span>Top N</span>
          <select v-model.number="form.top_n">
            <option :value="10">Top 10</option>
            <option :value="20">Top 20</option>
            <option :value="50">Top 50</option>
            <option :value="100">Top 100</option>
          </select>
        </label>
      </div>

      <div class="subsection">
        <div class="subsection-head">
          <strong>分组标签</strong>
          <span>{{ form.group_by.join(', ') || '未选择' }}</span>
        </div>
        <div class="label-pills">
          <button
            v-for="label in suggestedLabels"
            :key="label"
            class="pill"
            :class="{ active: form.group_by.includes(label) }"
            @click="toggleGroup(label)"
          >{{ label }}</button>
        </div>
        <div class="custom-label-row">
          <input v-model.trim="customGroupLabel" placeholder="自定义分组标签，例如 endpoint / route / path" @keyup.enter="addGroupLabel" />
          <button class="btn btn-outline" @click="addGroupLabel">加入分组</button>
        </div>
      </div>

      <div class="subsection">
        <div class="subsection-head">
          <strong>标签过滤</strong>
          <button class="btn btn-outline btn-sm" @click="addFilter">添加过滤</button>
        </div>
        <div v-if="!form.filters.length" class="hint-line">未设置过滤，将查询该指标的全部序列。</div>
        <div v-for="(filter, index) in form.filters" :key="index" class="filter-row">
          <input v-model.trim="filter.label" list="http-labels" placeholder="标签名" />
          <select v-model="filter.op">
            <option value="=">=</option>
            <option value="!=">!=</option>
            <option value="=~">=~</option>
            <option value="!~">!~</option>
          </select>
          <input v-model.trim="filter.value" :list="`values-${filter.label}`" placeholder="标签值或正则" />
          <button class="icon-btn" title="删除" @click="removeFilter(index)">×</button>
          <datalist v-if="filter.label" :id="`values-${filter.label}`">
            <option v-for="value in valuesFor(filter.label)" :key="value" :value="value" />
          </datalist>
        </div>
        <datalist id="http-labels">
          <option v-for="label in suggestedLabels" :key="label" :value="label" />
        </datalist>
      </div>
    </section>

    <div v-if="error" class="error-box">{{ error }}</div>

    <section class="kpi-grid">
      <article class="kpi-card">
        <span>总请求速率</span>
        <strong>{{ fmt(totalRequestRate, 2) }}</strong>
        <small>rps</small>
      </article>
      <article class="kpi-card">
        <span>窗口请求量</span>
        <strong>{{ fmt(totalRequestCount, 0) }}</strong>
        <small>requests</small>
      </article>
      <article class="kpi-card" :class="maxErrorRatio > 5 ? 'danger' : maxErrorRatio > 1 ? 'warn' : ''">
        <span>最高错误率</span>
        <strong>{{ fmt(maxErrorRatio, 2) }}%</strong>
        <small>5xx</small>
      </article>
      <article class="kpi-card">
        <span>接口序列</span>
        <strong>{{ rows.length }}</strong>
        <small>series</small>
      </article>
    </section>

    <section v-if="loading" class="panel empty">
      <span class="spinner"></span>
      <p>正在查询 Prometheus 并生成接口图表...</p>
    </section>

    <template v-else>
      <section class="chart-grid">
        <article v-for="chart in visibleCharts" :key="chart.key" class="panel chart-panel">
          <div class="chart-head">
            <div>
              <h2>{{ chart.label }}</h2>
              <span>{{ chart.series_count }} 条序列 · {{ chart.unit }}</span>
            </div>
            <div class="chart-head-right">
              <span
                v-if="forecasts[chart.key]"
                class="trend-badge"
                :class="'tr-' + forecasts[chart.key].trend"
                :title="`基于最显著序列「${forecasts[chart.key].mainName}」线性回归外推`"
              >
                {{ trendIcon(forecasts[chart.key].trend) }} {{ trendText(forecasts[chart.key].trend) }} · 预计 {{ fmt(forecasts[chart.key].predEnd, 1) }}{{ chart.unit === '%' ? '%' : '' }}
              </span>
              <button class="query-toggle" @click="toggleQuery(chart.key)">{{ openedQueries.has(chart.key) ? '收起' : 'PromQL' }}</button>
            </div>
          </div>
          <div v-if="chart.series?.length" class="line-chart">
            <svg viewBox="0 0 920 260" preserveAspectRatio="none">
              <line x1="36" y1="232" x2="910" y2="232" class="axis" />
              <line x1="36" y1="18" x2="36" y2="232" class="axis" />
              <polyline
                v-for="line in chartLines(chart)"
                :key="line.id"
                :points="line.points"
                :stroke="line.color"
                fill="none"
                stroke-width="2"
              />
            </svg>
            <div class="legend">
              <span v-for="line in chartLines(chart)" :key="line.id">
                <i :style="{ background: line.color }"></i>{{ line.name }}
              </span>
            </div>
          </div>
          <div v-else class="chart-empty">暂无数据，可能缺少对应指标或标签过滤过窄。</div>
          <pre v-if="openedQueries.has(chart.key)" class="query-box">{{ chart.query }}</pre>
        </article>
      </section>

      <section class="panel table-panel">
        <div class="table-head">
          <div>
            <h2>接口明细</h2>
            <span>{{ result?.row_count || rows.length }} 条序列，按请求速率排序</span>
          </div>
          <input v-model.trim="search" placeholder="过滤接口、服务或标签值" />
        </div>
        <div v-if="!filteredRows.length" class="empty slim">暂无接口数据</div>
        <table v-else>
          <thead>
            <tr>
              <th>接口/分组</th>
              <th class="num">RPS</th>
              <th class="num">请求量</th>
              <th class="num">错误率</th>
              <th class="num">成功率</th>
              <th class="num">平均耗时</th>
              <th class="num">P95</th>
              <th class="num">P99</th>
              <th class="num">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredRows" :key="row.id" :class="{ 'row-error': Number(row.error_ratio) >= 1 }">
              <td>
                <div class="row-name">{{ row.name }}</div>
                <div class="row-labels">
                  <span v-for="(value, key) in row.labels" :key="key">{{ key }}={{ value || '-' }}</span>
                </div>
              </td>
              <td class="num mono">{{ fmt(row.request_rate, 3) }}</td>
              <td class="num mono">{{ fmt(row.request_count, 0) }}</td>
              <td class="num mono" :class="tone(row.error_ratio)">{{ fmt(row.error_ratio, 2) }}%</td>
              <td class="num mono">{{ fmt(row.success_rate, 2) }}%</td>
              <td class="num mono">{{ fmt(row.avg_latency, 1) }} ms</td>
              <td class="num mono">{{ fmt(row.p95_latency, 1) }} ms</td>
              <td class="num mono">{{ fmt(row.p99_latency, 1) }} ms</td>
              <td class="num">
                <button
                  class="drill-btn"
                  :class="{ hot: Number(row.error_ratio) >= 1 }"
                  title="按该接口的服务与时间窗，跳转到日志分析排查错误"
                  @click="drillToLogs(row)"
                >查日志</button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router = useRouter()

const colors = ['#60a5fa', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6']
const defaultLabels = ['application', 'service', 'app', 'job', 'uri', 'method', 'status', 'outcome', 'exception', 'instance']

const form = reactive({
  metric: 'http_server_requests_seconds_count',
  range_minutes: 30,
  step: 60,
  rate_window: '5m',
  top_n: 20,
  group_by: ['application', 'uri', 'method'],
  filters: [],
})

const loading = ref(false)
const loadingLabels = ref(false)
const error = ref('')
const result = ref(null)
const labelInventory = ref([])
const customGroupLabel = ref('')
const search = ref('')
const openedQueries = ref(new Set())

const suggestedLabels = computed(() => {
  const remote = labelInventory.value.map(item => item.label)
  return Array.from(new Set([...remote, ...defaultLabels]))
})

const labelValueMap = computed(() => {
  const map = {}
  for (const item of labelInventory.value) map[item.label] = item.values || []
  return map
})

const charts = computed(() => result.value?.charts || [])
const visibleCharts = computed(() => charts.value.filter(chart => [
  'request_rate',
  'request_count',
  'error_ratio',
  'success_rate',
  'avg_latency',
  'p95_latency',
  'p99_latency',
].includes(chart.key)))
const rows = computed(() => result.value?.rows || [])
const filteredRows = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return rows.value
  return rows.value.filter(row => {
    const labels = Object.entries(row.labels || {}).map(([k, v]) => `${k}=${v}`).join(' ')
    return `${row.name} ${labels}`.toLowerCase().includes(q)
  })
})
const totalRequestRate = computed(() => rows.value.reduce((sum, row) => sum + Number(row.request_rate || 0), 0))
const totalRequestCount = computed(() => rows.value.reduce((sum, row) => sum + Number(row.request_count || 0), 0))
const maxErrorRatio = computed(() => Math.max(0, ...rows.value.map(row => Number(row.error_ratio || 0))))

function valuesFor(label) {
  return labelValueMap.value[label] || []
}

function toggleGroup(label) {
  const index = form.group_by.indexOf(label)
  if (index >= 0) form.group_by.splice(index, 1)
  else if (form.group_by.length < 8) form.group_by.push(label)
}

function addGroupLabel() {
  const label = customGroupLabel.value.trim()
  if (!label || form.group_by.includes(label)) return
  if (form.group_by.length < 8) form.group_by.push(label)
  customGroupLabel.value = ''
}

function addFilter() {
  form.filters.push({ label: 'application', op: '=', value: '' })
}

function removeFilter(index) {
  form.filters.splice(index, 1)
}

function toggleQuery(key) {
  const next = new Set(openedQueries.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openedQueries.value = next
}

function fmt(value, digits = 2) {
  const num = Number(value)
  if (!Number.isFinite(num)) return '-'
  return num.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

function tone(value) {
  const num = Number(value || 0)
  if (num >= 5) return 'danger'
  if (num >= 1) return 'warn'
  return 'ok'
}

// ── 趋势预测：对图表最显著序列做最小二乘线性回归，外推未来值 + 判定方向 ──
function forecast(chart) {
  const series = chart.series || []
  if (!series.length) return null
  // 选末值最大的序列作为主序列（最值得关注）
  let main = series[0]
  let maxLast = -Infinity
  for (const s of series) {
    const vs = s.values || []
    const last = vs.length ? Number(vs[vs.length - 1][1]) : 0
    if (Number.isFinite(last) && last > maxLast) { maxLast = last; main = s }
  }
  const ys = (main.values || []).map(p => Number(p[1])).filter(Number.isFinite)
  if (ys.length < 4) return null
  const n = ys.length
  let sx = 0, sy = 0, sxx = 0, sxy = 0
  ys.forEach((y, x) => { sx += x; sy += y; sxx += x * x; sxy += x * y })
  const denom = n * sxx - sx * sx || 1
  const b = (n * sxy - sx * sy) / denom      // 斜率
  const a = (sy - b * sx) / n                 // 截距
  const future = Math.max(2, Math.round(n * 0.5))
  const predEnd = Math.max(0, a + b * (n - 1 + future))
  const mean = Math.abs(sy / n) || 1
  const change = (b * n) / mean               // 整段变化占均值比例
  let trend = 'flat'
  if (change > 0.15) trend = 'up'
  else if (change < -0.15) trend = 'down'
  return { trend, predEnd, mainName: main.name }
}

const forecasts = computed(() => {
  const map = {}
  for (const c of visibleCharts.value) map[c.key] = forecast(c)
  return map
})

function trendIcon(t) { return t === 'up' ? '↑' : t === 'down' ? '↓' : '→' }
function trendText(t) { return t === 'up' ? '上升趋势' : t === 'down' ? '下降趋势' : '基本平稳' }

// ── 关联日志排查：从接口异常钻取到对应服务的错误日志 ──
function drillToLogs(row) {
  const labels = row.labels || {}
  const service = labels.application || labels.service || labels.app || labels.job || ''
  const query = {
    hours: (form.range_minutes / 60).toFixed(4),
    level: 'error',
  }
  if (service) query.service = service
  if (labels.uri) query.q = labels.uri
  router.push({ path: '/observability/logs', query })
}

function chartLines(chart) {
  const series = (chart.series || []).slice(0, 6)
  const values = series.flatMap(item => (item.values || []).map(point => Number(point[1])).filter(Number.isFinite))
  const min = Math.min(...values, 0)
  const max = Math.max(...values, 1)
  const span = max - min || 1
  return series.map((item, index) => {
    const points = (item.values || []).map((point, i, arr) => {
      const denom = Math.max(arr.length - 1, 1)
      const x = 36 + (i / denom) * 874
      const y = 232 - ((Number(point[1]) - min) / span) * 204
      return `${x.toFixed(1)},${y.toFixed(1)}`
    }).join(' ')
    return {
      id: item.id || `${chart.key}-${index}`,
      name: item.name || `series-${index + 1}`,
      color: colors[index % colors.length],
      points,
    }
  })
}

async function loadLabels() {
  loadingLabels.value = true
  try {
    const data = await api.httpServerMetricLabels({ metric: form.metric, limit: 80 })
    labelInventory.value = data.labels || []
  } catch {
    labelInventory.value = []
  } finally {
    loadingLabels.value = false
  }
}

async function loadMetrics() {
  loading.value = true
  error.value = ''
  try {
    result.value = await api.httpServerMetrics({
      metric: form.metric,
      filters: form.filters.filter(item => item.label && item.value),
      group_by: form.group_by,
      range_minutes: form.range_minutes,
      step: form.step,
      rate_window: form.rate_window,
      top_n: form.top_n,
    })
  } catch (err) {
    error.value = String(err)
    result.value = null
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadLabels()
  await loadMetrics()
})
</script>

<style scoped>
.http-metrics-page {
  height: 100%;
  overflow: auto;
  padding: 24px;
  background: var(--bg-base);
  color: var(--text-primary);
}
.page-header,
.header-actions,
.subsection-head,
.chart-head,
.table-head,
.legend {
  display: flex;
  gap: 10px;
}
.page-header {
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}
.chart-head { align-items: flex-start; justify-content: space-between; }
.chart-head-right { display: flex; align-items: center; gap: 8px; }
.trend-badge {
  font-size: 12px;
  padding: 3px 9px;
  border-radius: 999px;
  white-space: nowrap;
  border: 1px solid transparent;
}
.trend-badge.tr-up   { background: rgba(245,158,11,.14); color: #f59e0b; border-color: rgba(245,158,11,.3); }
.trend-badge.tr-down { background: rgba(34,197,94,.14);  color: #22c55e; border-color: rgba(34,197,94,.3); }
.trend-badge.tr-flat { background: var(--bg-hover); color: var(--text-muted); border-color: var(--border); }
.drill-btn {
  padding: 3px 10px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  cursor: pointer;
  white-space: nowrap;
  transition: all .12s;
}
.drill-btn:hover { border-color: var(--accent); color: var(--accent); }
.drill-btn.hot { border-color: rgba(239,68,68,.4); color: #ef4444; background: rgba(239,68,68,.06); }
.drill-btn.hot:hover { background: rgba(239,68,68,.14); }
tr.row-error td { background: rgba(239,68,68,.04); }
h1 {
  margin: 0 0 4px;
  font-size: 26px;
}
p,
.subsection-head span,
.chart-head span,
.table-head span,
.hint-line {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}
.btn,
.icon-btn,
.query-toggle,
.pill {
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-primary);
  cursor: pointer;
}
.btn {
  padding: 8px 13px;
}
.btn-sm {
  padding: 5px 9px;
  font-size: 12px;
}
.btn-primary {
  border-color: var(--accent);
  background: var(--accent);
  color: #fff;
}
.btn:disabled {
  opacity: .55;
  cursor: not-allowed;
}
.panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  padding: 16px;
}
.config-panel {
  margin-bottom: 16px;
}
.config-grid {
  display: grid;
  grid-template-columns: minmax(240px, 1.4fr) repeat(4, minmax(130px, .7fr));
  gap: 10px;
}
label span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-muted);
  font-size: 12px;
}
input,
select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 8px 10px;
  outline: none;
}
.subsection {
  margin-top: 16px;
}
.subsection-head {
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.label-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pill {
  padding: 5px 9px;
  font-size: 12px;
}
.pill.active {
  border-color: var(--accent);
  background: var(--accent-dim);
  color: var(--accent);
}
.custom-label-row,
.filter-row {
  display: grid;
  gap: 8px;
  margin-top: 8px;
}
.custom-label-row {
  grid-template-columns: minmax(240px, 1fr) 110px;
}
.filter-row {
  grid-template-columns: minmax(120px, .8fr) 78px minmax(180px, 1.3fr) 36px;
}
.icon-btn {
  height: 36px;
  font-size: 18px;
}
.error-box {
  margin-bottom: 16px;
  border: 1px solid rgba(239,68,68,.28);
  border-radius: 8px;
  background: rgba(239,68,68,.08);
  color: var(--error);
  padding: 10px 12px;
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.kpi-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  padding: 14px;
}
.kpi-card span,
.kpi-card small {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}
.kpi-card strong {
  display: block;
  margin: 5px 0 2px;
  font-size: 24px;
}
.kpi-card.warn strong { color: var(--warning); }
.kpi-card.danger strong { color: var(--error); }
.chart-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.chart-panel h2,
.table-panel h2 {
  margin: 0 0 2px;
  font-size: 16px;
}
.chart-head,
.table-head {
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
}
.query-toggle {
  padding: 5px 9px;
  font-size: 12px;
}
.line-chart {
  min-height: 250px;
}
svg {
  width: 100%;
  height: 220px;
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
  max-width: 220px;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.legend i {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 5px;
  border-radius: 50%;
}
.chart-empty,
.empty {
  min-height: 160px;
  display: grid;
  place-items: center;
  color: var(--text-muted);
  font-size: 13px;
}
.empty.slim {
  min-height: 80px;
}
.query-box {
  max-height: 110px;
  overflow: auto;
  margin: 10px 0 0;
  border: 1px dashed var(--border);
  border-radius: 7px;
  background: var(--bg-base);
  color: var(--text-secondary);
  padding: 8px;
  white-space: pre-wrap;
}
.table-panel {
  margin-top: 12px;
}
.table-head input {
  max-width: 280px;
}
table {
  width: 100%;
  border-collapse: collapse;
}
th,
td {
  border-bottom: 1px solid var(--border);
  padding: 10px 8px;
  text-align: left;
  font-size: 12px;
}
th {
  color: var(--text-muted);
  font-weight: 600;
}
.num {
  text-align: right;
}
.mono {
  font-family: var(--font-mono);
}
.row-name {
  font-weight: 600;
}
.row-labels {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.row-labels span {
  border-radius: 4px;
  background: var(--bg-surface);
  color: var(--text-muted);
  padding: 1px 5px;
  font-size: 11px;
}
.ok { color: var(--success); }
.warn { color: var(--warning); }
.danger { color: var(--error); }

@media (max-width: 980px) {
  .config-grid,
  .kpi-grid,
  .chart-grid {
    grid-template-columns: 1fr;
  }
  .page-header,
  .table-head {
    flex-direction: column;
  }
}
</style>
