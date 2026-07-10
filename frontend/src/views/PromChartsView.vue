<template>
  <div class="pc-page">
    <header class="pc-header">
      <div>
        <h1>指标图表</h1>
        <p>输入 PromQL 表达式生成折线图，自定义设计并保存你的指标面板。</p>
      </div>
      <div class="pc-toolbar">
        <select v-model.number="rangeMinutes" @change="onSettingChange">
          <option :value="15">最近 15 分钟</option>
          <option :value="60">最近 1 小时</option>
          <option :value="360">最近 6 小时</option>
          <option :value="1440">最近 24 小时</option>
          <option :value="4320">最近 3 天</option>
        </select>
        <select v-model.number="refreshSeconds" @change="onSettingChange">
          <option :value="0">不自动刷新</option>
          <option :value="30">每 30 秒</option>
          <option :value="60">每 1 分钟</option>
          <option :value="300">每 5 分钟</option>
        </select>
        <button class="btn btn-outline" @click="reloadAll" :disabled="loadingAll">
          <span v-if="loadingAll" class="spinner-sm"></span> 刷新
        </button>
        <button class="btn btn-outline" @click="openVariableEditor" :disabled="!activeDashboard">变量设置</button>
        <button class="btn btn-primary" @click="openEditor()">＋ 添加图表</button>
      </div>
    </header>

    <section class="pc-tabs">
      <div class="pc-tab-list">
        <button
          v-for="dashboard in dashboards"
          :key="dashboard.id"
          class="pc-tab"
          :class="{ active: dashboard.id === activeDashboardId }"
          @click="selectDashboard(dashboard.id)"
        >
          <span>{{ dashboard.name }}</span>
          <small>{{ dashboard.charts.length }}</small>
        </button>
        <button class="pc-tab add" @click="addDashboard">＋ 页签</button>
      </div>
      <div v-if="activeDashboard" class="pc-tab-actions">
        <button class="btn btn-outline" @click="renameDashboard(activeDashboard)">重命名</button>
        <button class="btn btn-outline danger-text" :disabled="dashboards.length <= 1" @click="removeDashboard(activeDashboard)">删除</button>
      </div>
    </section>

    <section v-if="activeVariables.length" class="pc-vars">
      <label v-for="variable in activeVariables" :key="variable.id" class="pc-var-filter">
        <span>{{ variable.label || variable.name }}</span>
        <select v-model="variable.value" @change="onVariableChange(variable)">
          <option value="">全部</option>
          <option v-for="value in variable.values" :key="value" :value="value">{{ value }}</option>
        </select>
        <button class="pc-icon-btn" title="刷新变量值" @click="refreshVariable(variable)" :disabled="variable.loading">
          <span v-if="variable.loading" class="spinner-sm"></span>
          <span v-else>↻</span>
        </button>
        <small v-if="variable.error">{{ variable.error }}</small>
      </label>
    </section>

    <div v-if="!charts.length" class="pc-empty">
      <p>还没有图表，点击「添加图表」输入 PromQL 表达式开始。</p>
    </div>

    <div class="pc-grid">
      <section
        v-for="chart in charts"
        :key="chart.id"
        class="pc-card"
        :class="{ full: chart.width === 'full' }"
      >
        <div class="pc-card-head">
          <div class="pc-card-title">
            <strong>{{ chart.title }}</strong>
            <code :title="displayQuery(chart)">{{ displayQuery(chart) }}</code>
          </div>
          <div class="pc-card-actions">
            <button title="编辑" @click="openEditor(chart)">✎</button>
            <button title="复制" @click="duplicateChart(chart)">⧉</button>
            <button title="半宽/全宽" @click="toggleWidth(chart)">⇔</button>
            <button title="删除" class="danger" @click="removeChart(chart)">✕</button>
          </div>
        </div>

        <div v-if="dataOf(chart.id).loading" class="pc-chart-empty"><span class="spinner"></span></div>
        <div v-else-if="dataOf(chart.id).error" class="pc-chart-empty error">{{ dataOf(chart.id).error }}</div>
        <div v-else-if="!dataOf(chart.id).series.length" class="pc-chart-empty">表达式无数据</div>

        <template v-else>
          <div class="pc-chart-wrap">
            <svg
              :viewBox="`0 0 ${W} ${H}`"
              class="pc-svg"
              preserveAspectRatio="none"
              @mousemove="onChartHover(chart, $event)"
              @mouseleave="clearHover(chart.id)"
            >
              <line v-for="g in 4" :key="'g'+g" :x1="PAD" :x2="W-8" :y1="gy(g)" :y2="gy(g)" class="grid" />
              <text v-for="g in 4" :key="'t'+g" :x="PAD-6" :y="gy(g)+4" class="axis-y">
                {{ fmtVal(gridValue(chart.id, g), chart.unit) }}
              </text>
              <polyline
                v-for="(s, i) in dataOf(chart.id).series"
                :key="s.key"
                :points="s.points"
                fill="none"
                :stroke="palette[i % palette.length]"
                stroke-width="1.6"
                stroke-linejoin="round"
              />
              <line
                v-if="isChartHover(chart.id)"
                :x1="hover.x"
                :x2="hover.x"
                y1="10"
                :y2="H-22"
                class="hover-line"
              />
              <template v-if="isChartHover(chart.id)">
                <circle
                  v-for="item in hover.items"
                  :key="item.key"
                  :cx="item.x"
                  :cy="item.y"
                  r="3.2"
                  :fill="item.color"
                  class="hover-dot"
                />
              </template>
              <text :x="PAD" :y="H-4" class="axis-x">{{ dataOf(chart.id).t0 }}</text>
              <text :x="W-8" :y="H-4" class="axis-x end">{{ dataOf(chart.id).t1 }}</text>
            </svg>
            <div v-if="isChartHover(chart.id)" class="pc-tooltip" :style="hoverTooltipStyle">
              <div class="pc-tooltip-time">{{ hover.time }}</div>
              <div v-for="item in hover.items" :key="item.key" class="pc-tooltip-row">
                <i :style="{ background: item.color }"></i>
                <span :title="item.name">{{ item.name }}</span>
                <b>{{ fmtVal(item.value, chart.unit) }}</b>
              </div>
            </div>
          </div>
          <div class="pc-legend">
            <span
              v-for="(s, i) in dataOf(chart.id).series.slice(0, 8)"
              :key="s.key"
              class="pc-legend-item"
              :title="s.name"
            >
              <i :style="{ background: palette[i % palette.length] }"></i>
              {{ s.name }} · <b>{{ fmtVal(s.last, chart.unit) }}</b>
            </span>
            <span v-if="dataOf(chart.id).series.length > 8" class="pc-legend-more">
              +{{ dataOf(chart.id).series.length - 8 }} 条
            </span>
          </div>
        </template>
      </section>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="editor.visible" class="pc-mask" @click.self="editor.visible = false">
      <div class="pc-modal">
        <div class="pc-modal-head">
          <span>{{ editor.id ? '编辑图表' : '添加图表' }}</span>
          <button @click="editor.visible = false">×</button>
        </div>
        <div class="pc-modal-body">
          <label><span>标题</span><input v-model.trim="editor.title" placeholder="例如：主机 CPU 使用率" /></label>
          <label>
            <span>PromQL 表达式</span>
            <textarea ref="queryInput" v-model="editor.query" rows="3" spellcheck="false"
                      placeholder='100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100'></textarea>
          </label>
          <div v-if="activeVariables.length" class="pc-variable-insert">
            <span>变量过滤</span>
            <button v-for="variable in activeVariables" :key="variable.id" @click="insertVariableFilter(variable)">
              {{ variable.label || variable.name }}=~{{ variable.name }}
            </button>
          </div>
          <div class="pc-form-grid">
            <label><span>单位</span><input v-model.trim="editor.unit" placeholder="% / ms / MB，可留空" /></label>
            <label>
              <span>宽度</span>
              <select v-model="editor.width">
                <option value="half">半宽</option>
                <option value="full">全宽</option>
              </select>
            </label>
          </div>
          <div class="pc-quick">
            <span>常用模板：</span>
            <button v-for="tpl in quickTemplates" :key="tpl.title" @click="applyTemplate(tpl)">{{ tpl.title }}</button>
          </div>
          <div class="pc-test">
            <button class="btn btn-outline" @click="testQuery" :disabled="editor.testing">
              <span v-if="editor.testing" class="spinner-sm"></span> 测试表达式
            </button>
            <span v-if="editor.testResult" :class="editor.testOk ? 'ok' : 'bad'">{{ editor.testResult }}</span>
          </div>
          <p v-if="editor.error" class="pc-error">{{ editor.error }}</p>
        </div>
        <div class="pc-modal-foot">
          <button class="btn btn-primary" @click="saveEditor">保存</button>
          <button class="btn btn-outline" @click="editor.visible = false">取消</button>
        </div>
      </div>
    </div>

    <!-- 变量设置弹窗 -->
    <div v-if="variableEditor.visible" class="pc-mask" @click.self="variableEditor.visible = false">
      <div class="pc-modal pc-modal-wide">
        <div class="pc-modal-head">
          <span>变量设置 · {{ activeDashboard?.name || '' }}</span>
          <button @click="variableEditor.visible = false">×</button>
        </div>
        <div class="pc-modal-body">
          <div class="pc-var-editor-head">
            <span>Prometheus 标签变量</span>
            <button class="btn btn-outline" @click="addVariableDraft">添加变量</button>
          </div>
          <div v-if="!variableDrafts.length" class="pc-empty-inline">未设置变量</div>
          <div v-for="(variable, index) in variableDrafts" :key="variable.id" class="pc-var-row">
            <div class="pc-var-row-main">
              <label><span>变量名</span><input v-model.trim="variable.name" placeholder="instance" /></label>
              <label><span>标签名</span><input v-model.trim="variable.label" placeholder="instance / job / namespace" /></label>
              <label><span>取值表达式</span><input v-model.trim="variable.query" placeholder="up 或 http_server_requests_seconds_count" /></label>
            </div>
            <div class="pc-var-row-sub">
              <select v-model="variable.value">
                <option value="">全部</option>
                <option v-for="value in variable.values" :key="value" :value="value">{{ value }}</option>
              </select>
              <button class="btn btn-outline" @click="loadVariableDraftValues(variable)" :disabled="variable.loading">
                <span v-if="variable.loading" class="spinner-sm"></span> 取值
              </button>
              <button class="btn btn-outline danger-text" @click="removeVariableDraft(index)">删除</button>
              <small v-if="variable.error">{{ variable.error }}</small>
            </div>
          </div>
          <p v-if="variableEditor.error" class="pc-error">{{ variableEditor.error }}</p>
        </div>
        <div class="pc-modal-foot">
          <button class="btn btn-primary" @click="saveVariables">保存</button>
          <button class="btn btn-outline" @click="variableEditor.visible = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api/index.js'

const W = 600
const H = 200
const PAD = 46

const palette = ['#d97757', '#388bfd', '#3fb950', '#d29922', '#bc8cff', '#f85149', '#39c5cf', '#e3b341']

const dashboards = ref([])
const activeDashboardId = ref('')
const rangeMinutes = ref(60)
const refreshSeconds = ref(0)
const step = ref(60)
const loadingAll = ref(false)
const chartData = reactive({})   // id -> { loading, error, series, min, max, t0, t1 }
const queryInput = ref(null)

const activeDashboard = computed(() => (
  dashboards.value.find(item => item.id === activeDashboardId.value) || dashboards.value[0] || null
))

const charts = computed({
  get() {
    return activeDashboard.value?.charts || []
  },
  set(next) {
    if (activeDashboard.value) activeDashboard.value.charts = next
  },
})

const activeVariables = computed(() => activeDashboard.value?.variables || [])

const quickTemplates = [
  { title: 'CPU 使用率', unit: '%', query: '100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100' },
  { title: '内存使用率', unit: '%', query: '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100' },
  { title: '磁盘使用率', unit: '%', query: '100 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100' },
  { title: '网络接收', unit: 'MB/s', query: 'sum by (instance) (rate(node_network_receive_bytes_total[5m])) / 1024 / 1024' },
  { title: '接口 QPS', unit: 'rps', query: 'sum by (uri) (rate(http_server_requests_seconds_count[5m]))' },
  { title: '采集目标 up', unit: '', query: 'sum by (job) (up)' },
]

const editor = reactive({
  visible: false, id: '', title: '', query: '', unit: '', width: 'half',
  error: '', testing: false, testResult: '', testOk: false,
})

const variableEditor = reactive({ visible: false, error: '' })
const variableDrafts = ref([])

const hover = reactive({
  chartId: '',
  x: 0,
  tooltipX: 0,
  tooltipY: 0,
  time: '',
  items: [],
})

const hoverTooltipStyle = computed(() => ({
  left: `${hover.tooltipX}px`,
  top: `${hover.tooltipY}px`,
}))

let refreshTimer = null
let saveTimer = null

function newId(prefix) {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function sanitizeVariableName(value) {
  const cleaned = String(value || '').trim().replace(/[^a-zA-Z0-9_]/g, '_').replace(/^[^a-zA-Z_]+/, '')
  return cleaned || ''
}

function normalizeChart(item = {}, index = 0) {
  return {
    id: String(item.id || `chart-${index}-${Date.now().toString(36)}`),
    title: String(item.title || 'PromQL 图表'),
    query: String(item.query || '').trim(),
    unit: String(item.unit || ''),
    width: item.width === 'full' ? 'full' : 'half',
  }
}

function normalizeVariable(item = {}, index = 0) {
  const label = String(item.label || item.name || '').trim()
  const name = sanitizeVariableName(item.name || label || `var${index + 1}`) || `var${index + 1}`
  const values = Array.isArray(item.values) ? item.values.map(value => String(value)).filter(Boolean) : []
  return {
    id: String(item.id || newId('var')),
    name,
    label,
    query: String(item.query || ''),
    value: String(item.value || ''),
    values,
    loading: false,
    error: '',
  }
}

function normalizeDashboard(item = {}, index = 0, fallbackCharts = []) {
  const rawCharts = Array.isArray(item.charts) ? item.charts : fallbackCharts
  const rawVariables = Array.isArray(item.variables) ? item.variables : []
  const normalizedCharts = rawCharts.map((chart, chartIndex) => normalizeChart(chart, chartIndex)).filter(chart => chart.query)
  const normalizedVariables = rawVariables.map((variable, varIndex) => normalizeVariable(variable, varIndex)).filter(variable => variable.name && variable.label)
  return {
    id: String(item.id || (index === 0 ? 'default' : newId('dashboard'))),
    name: String(item.name || (index === 0 ? '默认' : `页签 ${index + 1}`)),
    variables: normalizedVariables,
    charts: normalizedCharts,
  }
}

function normalizeSavedPanels(saved = {}) {
  const rawDashboards = Array.isArray(saved.dashboards) ? saved.dashboards : []
  const rawCharts = Array.isArray(saved.charts) ? saved.charts : []
  const list = rawDashboards.length
    ? rawDashboards.map((dashboard, index) => normalizeDashboard(dashboard, index)).filter(Boolean)
    : [normalizeDashboard({ id: 'default', name: '默认', charts: rawCharts }, 0, rawCharts)]
  dashboards.value = list.length ? list : [normalizeDashboard({ id: 'default', name: '默认', charts: [] })]
  activeDashboardId.value = dashboards.value.some(item => item.id === saved.active_dashboard_id)
    ? saved.active_dashboard_id
    : dashboards.value[0].id
}

function chartPayload(chart) {
  return {
    id: chart.id,
    title: chart.title,
    query: chart.query,
    unit: chart.unit,
    width: chart.width,
  }
}

function variablePayload(variable) {
  return {
    id: variable.id,
    name: variable.name,
    label: variable.label,
    query: variable.query,
    value: variable.value,
    values: variable.values || [],
  }
}

function dashboardPayload(dashboard) {
  return {
    id: dashboard.id,
    name: dashboard.name,
    variables: (dashboard.variables || []).map(variablePayload),
    charts: (dashboard.charts || []).map(chartPayload),
  }
}

function dataOf(id) {
  return chartData[id] || { loading: true, error: '', series: [], min: 0, max: 1, t0: '', t1: '', start: 0, end: 0 }
}

function fmtVal(value, unit) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-'
  const abs = Math.abs(value)
  let text
  if (abs >= 1e6) text = (value / 1e6).toFixed(1) + 'M'
  else if (abs >= 1e4) text = (value / 1e3).toFixed(1) + 'k'
  else if (abs >= 100) text = value.toFixed(0)
  else if (abs >= 1) text = value.toFixed(1)
  else text = value.toFixed(2)
  return unit ? `${text}${unit}` : text
}

function gy(g) {
  // 4 条网格线：g=1 顶部（max）… g=4 底部（min）
  return 14 + ((g - 1) / 3) * (H - 40)
}

function gridValue(id, g) {
  const d = dataOf(id)
  return d.max - ((g - 1) / 3) * (d.max - d.min)
}

function seriesName(metric) {
  const entries = Object.entries(metric || {}).filter(([k]) => k !== '__name__')
  if (!entries.length) return metric?.__name__ || 'value'
  return entries.map(([k, v]) => `${k}=${v}`).join(', ')
}

function pad2(value) {
  return String(value).padStart(2, '0')
}

function fmtAxisTime(ts) {
  return new Date(ts * 1000).toTimeString().slice(0, 5)
}

function fmtHoverTime(ts) {
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())} ${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
}

function escapePromValue(value) {
  return String(value || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n')
}

function escapeRegexValue(value) {
  return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function renderPromQL(query, variables = activeVariables.value, excludedVariableId = '') {
  const source = Array.isArray(variables) ? variables : []
  const variableMap = new Map()
  for (const variable of source) {
    if (!variable || variable.id === excludedVariableId) continue
    const name = sanitizeVariableName(variable.name)
    if (name) variableMap.set(name, variable)
  }
  const resolve = (match, name, mode = '') => {
    const variable = variableMap.get(name)
    if (!variable) return match
    const raw = String(variable.value || '')
    if (mode === 'raw') return raw
    if (mode === 'regex') return raw ? escapePromValue(escapeRegexValue(raw)) : '.*'
    return escapePromValue(raw)
  }
  return String(query || '')
    .replace(/\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)(?::(regex|raw))?\s*\}\}/g, resolve)
    .replace(/\$\{([a-zA-Z_][a-zA-Z0-9_]*)(?::(regex|raw))?\}/g, resolve)
    .replace(/\$([a-zA-Z_][a-zA-Z0-9_]*)/g, resolve)
}

function displayQuery(chart) {
  return renderPromQL(chart.query)
}

function variableSnippet(variable) {
  const label = String(variable.label || variable.name || '').trim()
  const name = sanitizeVariableName(variable.name || label)
  return `${label}=~"` + '${' + `${name}:regex` + '}"'
}

function insertVariableFilter(variable) {
  const snippet = variableSnippet(variable)
  const el = queryInput.value
  if (!el) {
    editor.query = `${editor.query || ''}${snippet}`
    return
  }
  const start = el.selectionStart ?? editor.query.length
  const end = el.selectionEnd ?? editor.query.length
  editor.query = `${editor.query.slice(0, start)}${snippet}${editor.query.slice(end)}`
  nextTick(() => {
    el.focus()
    const cursor = start + snippet.length
    el.setSelectionRange(cursor, cursor)
  })
}

async function loadChart(chart) {
  const query = renderPromQL(chart.query)
  chartData[chart.id] = { ...dataOf(chart.id), loading: true, error: '' }
  const end = Math.floor(Date.now() / 1000)
  const start = end - rangeMinutes.value * 60
  const stepValue = Math.max(15, Math.floor(rangeMinutes.value * 60 / 240))
  try {
    const result = await api.prometheusQueryRange({ query, start, end, step: stepValue })
    const raw = (result.data || []).slice(0, 20)
    let min = Infinity, max = -Infinity
    const parsed = raw.map((item, index) => {
      const values = (item.values || [])
        .map(([ts, v]) => [Number(ts), Number(v)])
        .filter(([, v]) => Number.isFinite(v))
      for (const [, v] of values) { if (v < min) min = v; if (v > max) max = v }
      return { key: `${chart.id}-${index}`, name: seriesName(item.metric), values, last: values.length ? values[values.length - 1][1] : null }
    }).filter(s => s.values.length)
    if (!parsed.length) {
      chartData[chart.id] = { loading: false, error: '', series: [], min: 0, max: 1, t0: '', t1: '', start, end }
      return
    }
    if (min === max) { min -= 1; max += 1 }
    const pad = (max - min) * 0.05
    min -= pad; max += pad
    for (const s of parsed) {
      s.samples = s.values.map(([ts, v]) => {
        const x = PAD + ((ts - start) / (end - start)) * (W - PAD - 8)
        const y = 14 + (1 - (v - min) / (max - min)) * (H - 40)
        return { ts, value: v, x, y }
      })
      s.points = s.samples.map(point => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(' ')
    }
    chartData[chart.id] = {
      loading: false, error: '', series: parsed, min, max,
      t0: fmtAxisTime(start), t1: fmtAxisTime(end), start, end,
    }
  } catch (error) {
    chartData[chart.id] = {
      loading: false, series: [], min: 0, max: 1, t0: '', t1: '', start, end,
      error: error?.response?.data?.detail || 'Prometheus 查询失败',
    }
  }
}

async function reloadAll() {
  loadingAll.value = true
  clearHover()
  try {
    await Promise.all(charts.value.map(loadChart))
  } finally {
    loadingAll.value = false
  }
}

function nearestSample(samples, targetTs) {
  let nearest = null
  let nearestDiff = Infinity
  for (const sample of samples || []) {
    const diff = Math.abs(sample.ts - targetTs)
    if (diff < nearestDiff) {
      nearest = sample
      nearestDiff = diff
    }
  }
  return nearest
}

function onChartHover(chart, event) {
  const data = dataOf(chart.id)
  if (!data.series.length || !data.start || !data.end) return
  const rect = event.currentTarget.getBoundingClientRect()
  const mouseX = event.clientX - rect.left
  const mouseY = event.clientY - rect.top
  const svgX = (mouseX / rect.width) * W
  const clampedX = Math.max(PAD, Math.min(W - 8, svgX))
  const targetTs = data.start + ((clampedX - PAD) / (W - PAD - 8)) * (data.end - data.start)
  const items = data.series.map((series, index) => {
    const sample = nearestSample(series.samples, targetTs)
    if (!sample) return null
    return {
      key: series.key,
      name: series.name,
      value: sample.value,
      ts: sample.ts,
      x: sample.x,
      y: sample.y,
      color: palette[index % palette.length],
    }
  }).filter(Boolean)
  if (!items.length) return
  const focus = items[0]
  const tooltipWidth = 260
  const maxLeft = Math.max(8, rect.width - tooltipWidth - 8)
  hover.chartId = chart.id
  hover.x = focus.x
  hover.time = fmtHoverTime(focus.ts)
  hover.items = items.slice(0, 10)
  hover.tooltipX = Math.min(maxLeft, Math.max(8, mouseX + 12))
  hover.tooltipY = mouseY > rect.height / 2 ? Math.max(8, mouseY - 122) : Math.max(8, mouseY + 12)
}

function isChartHover(id) {
  return hover.chartId === id && hover.items.length > 0
}

function clearHover(id = '') {
  if (id && hover.chartId !== id) return
  hover.chartId = ''
  hover.items = []
}

function schedulePersist() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(persist, 400)
}

async function persist() {
  try {
    await api.saveMetricPanels({
      charts: charts.value.map(chartPayload),
      dashboards: dashboards.value.map(dashboardPayload),
      active_dashboard_id: activeDashboardId.value,
      range_minutes: rangeMinutes.value,
      step: step.value,
      refresh_seconds: refreshSeconds.value,
    })
  } catch { /* 保存失败不阻塞展示 */ }
}

function setupRefreshTimer() {
  clearInterval(refreshTimer)
  if (refreshSeconds.value > 0) {
    refreshTimer = setInterval(reloadAll, refreshSeconds.value * 1000)
  }
}

function onSettingChange() {
  setupRefreshTimer()
  schedulePersist()
  reloadAll()
}

async function selectDashboard(id) {
  if (activeDashboardId.value === id) return
  activeDashboardId.value = id
  clearHover()
  schedulePersist()
  await loadActiveVariableValues()
  reloadAll()
}

function addDashboard() {
  const name = window.prompt('页签名称', `自定义 ${dashboards.value.length + 1}`)
  if (name === null) return
  const dashboard = {
    id: newId('dashboard'),
    name: name.trim() || `自定义 ${dashboards.value.length + 1}`,
    variables: [],
    charts: [],
  }
  dashboards.value.push(dashboard)
  activeDashboardId.value = dashboard.id
  clearHover()
  schedulePersist()
}

function renameDashboard(dashboard) {
  const name = window.prompt('页签名称', dashboard.name)
  if (name === null) return
  dashboard.name = name.trim() || dashboard.name
  schedulePersist()
}

function removeDashboard(dashboard) {
  if (dashboards.value.length <= 1) return
  if (!window.confirm(`删除页签「${dashboard.name}」？`)) return
  dashboards.value = dashboards.value.filter(item => item.id !== dashboard.id)
  if (activeDashboardId.value === dashboard.id) activeDashboardId.value = dashboards.value[0]?.id || ''
  clearHover()
  schedulePersist()
  reloadAll()
}

function openEditor(chart = null) {
  Object.assign(editor, {
    visible: true,
    id: chart?.id || '',
    title: chart?.title || '',
    query: chart?.query || '',
    unit: chart?.unit || '',
    width: chart?.width || 'half',
    error: '', testing: false, testResult: '', testOk: false,
  })
}

function applyTemplate(tpl) {
  editor.title = editor.title || tpl.title
  editor.query = tpl.query
  editor.unit = tpl.unit
}

async function testQuery() {
  const query = renderPromQL(editor.query.trim())
  if (!query) { editor.testResult = '请先填写表达式'; editor.testOk = false; return }
  editor.testing = true
  editor.testResult = ''
  try {
    const result = await api.prometheusQuery({ query })
    editor.testOk = true
    editor.testResult = `✓ 返回 ${result.series_count ?? (result.data || []).length} 条序列`
  } catch (error) {
    editor.testOk = false
    editor.testResult = `✗ ${error?.response?.data?.detail || '查询失败'}`
  } finally {
    editor.testing = false
  }
}

function saveEditor() {
  editor.error = ''
  if (!editor.query.trim()) { editor.error = '请填写 PromQL 表达式'; return }
  const payload = {
    title: editor.title.trim() || 'PromQL 图表',
    query: editor.query.trim(),
    unit: editor.unit.trim(),
    width: editor.width,
  }
  if (editor.id) {
    const chart = charts.value.find(item => item.id === editor.id)
    if (chart) Object.assign(chart, payload)
  } else {
    const chart = { id: newId('chart'), ...payload }
    charts.value.push(chart)
  }
  editor.visible = false
  schedulePersist()
  const target = charts.value.find(item => item.id === (editor.id || charts.value[charts.value.length - 1].id))
  if (target) loadChart(target)
}

function duplicateChart(chart) {
  const copy = { ...chart, id: newId('chart'), title: `${chart.title} 副本` }
  charts.value.push(copy)
  schedulePersist()
  loadChart(copy)
}

function toggleWidth(chart) {
  chart.width = chart.width === 'full' ? 'half' : 'full'
  schedulePersist()
}

function removeChart(chart) {
  if (!window.confirm(`删除图表「${chart.title}」？`)) return
  charts.value = charts.value.filter(item => item.id !== chart.id)
  delete chartData[chart.id]
  clearHover(chart.id)
  schedulePersist()
}

async function fetchVariableValues(variable, sourceVariables = activeVariables.value) {
  const label = String(variable.label || '').trim()
  if (!label) {
    variable.error = '标签名不能为空'
    return
  }
  variable.loading = true
  variable.error = ''
  try {
    const params = { limit: 1000 }
    const query = String(variable.query || '').trim()
    if (query) params.query = renderPromQL(query, sourceVariables, variable.id)
    const data = await api.prometheusLabelValues(label, params)
    const values = (data.data || []).map(value => String(value)).filter(Boolean)
    variable.values = values
    if (variable.value && !values.includes(variable.value)) variable.value = ''
  } catch (error) {
    variable.error = error?.response?.data?.detail || '取值失败'
    variable.values = []
  } finally {
    variable.loading = false
  }
}

async function loadActiveVariableValues() {
  const variables = activeVariables.value
  await Promise.all(variables.map(variable => fetchVariableValues(variable, variables)))
}

async function refreshVariable(variable) {
  await fetchVariableValues(variable, activeVariables.value)
  schedulePersist()
  reloadAll()
}

function onVariableChange() {
  schedulePersist()
  reloadAll()
}

function openVariableEditor() {
  variableEditor.error = ''
  variableDrafts.value = activeVariables.value.map((variable, index) => normalizeVariable(variable, index))
  variableEditor.visible = true
}

function addVariableDraft() {
  variableDrafts.value.push(normalizeVariable({ name: `var${variableDrafts.value.length + 1}`, label: 'instance', query: 'up' }, variableDrafts.value.length))
}

function removeVariableDraft(index) {
  variableDrafts.value.splice(index, 1)
}

async function loadVariableDraftValues(variable) {
  await fetchVariableValues(variable, variableDrafts.value)
}

async function saveVariables() {
  variableEditor.error = ''
  if (!activeDashboard.value) return
  const seen = new Set()
  const variables = []
  for (const draft of variableDrafts.value) {
    const name = sanitizeVariableName(draft.name)
    const label = String(draft.label || '').trim()
    if (!name && !label && !draft.query && !draft.value) continue
    if (!name || !label) {
      variableEditor.error = '变量名和标签名不能为空'
      return
    }
    if (seen.has(name)) {
      variableEditor.error = `变量名重复：${name}`
      return
    }
    seen.add(name)
    variables.push({
      ...normalizeVariable({ ...draft, name, label }, variables.length),
      values: Array.isArray(draft.values) ? draft.values : [],
    })
  }
  activeDashboard.value.variables = variables
  variableEditor.visible = false
  schedulePersist()
  await loadActiveVariableValues()
  schedulePersist()
  reloadAll()
}

onMounted(async () => {
  try {
    const saved = await api.getMetricPanels()
    normalizeSavedPanels(saved)
    rangeMinutes.value = saved.range_minutes || 60
    step.value = saved.step || 60
    refreshSeconds.value = saved.refresh_seconds || 0
  } catch {
    normalizeSavedPanels({ charts: [] })
  }
  setupRefreshTimer()
  await loadActiveVariableValues()
  reloadAll()
})

onBeforeUnmount(() => {
  clearInterval(refreshTimer)
  clearTimeout(saveTimer)
})
</script>

<style scoped>
.pc-page {
  height: 100%;
  overflow: auto;
  padding: 20px 24px;
  background: var(--bg-base);
  color: var(--text-primary);
}
.pc-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.pc-header h1 { font-size: 20px; margin: 0 0 4px; }
.pc-header p { margin: 0; color: var(--text-muted); font-size: 13px; }
.pc-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pc-toolbar select,
.pc-vars select,
.pc-var-row select,
.pc-modal input, .pc-modal textarea, .pc-modal select {
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 7px 10px;
  font-size: 13px;
  outline: none;
}
.pc-modal input:focus, .pc-modal textarea:focus, .pc-vars select:focus { border-color: var(--accent); }
.btn {
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 7px 14px;
  cursor: pointer;
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.btn-primary { background: var(--accent); color: #fff; }
.btn-outline { background: var(--bg-card); border-color: var(--border); color: var(--text-primary); }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.danger-text { color: var(--error); }

.pc-tabs {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.pc-tab-list {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  overflow-x: auto;
}
.pc-tab {
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-card);
  color: var(--text-primary);
  padding: 7px 10px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
  cursor: pointer;
}
.pc-tab.active {
  border-color: var(--accent);
  background: var(--accent-dim);
  color: var(--accent);
}
.pc-tab.add { color: var(--text-secondary); }
.pc-tab small {
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  text-align: center;
  border-radius: 9px;
  background: var(--bg-base);
  color: var(--text-muted);
  font-size: 11px;
}
.pc-tab-actions { display: flex; gap: 8px; flex-shrink: 0; }

.pc-vars {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
}
.pc-var-filter {
  display: grid;
  grid-template-columns: auto minmax(160px, 260px) 30px;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.pc-var-filter span {
  color: var(--text-muted);
  font-size: 12px;
}
.pc-var-filter small {
  grid-column: 2 / 4;
  color: var(--error);
  font-size: 11px;
}
.pc-icon-btn {
  width: 30px;
  height: 30px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-base);
  color: var(--text-secondary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.pc-empty {
  border: 1px dashed var(--border);
  border-radius: 10px;
  padding: 60px 20px;
  text-align: center;
  color: var(--text-muted);
}
.pc-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.pc-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  min-width: 0;
}
.pc-card.full { grid-column: 1 / -1; }
.pc-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.pc-card-title { min-width: 0; }
.pc-card-title strong { display: block; font-size: 13px; }
.pc-card-title code {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.pc-card-actions { display: flex; gap: 4px; flex-shrink: 0; }
.pc-card-actions button {
  width: 26px; height: 26px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-base);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
}
.pc-card-actions button:hover { border-color: var(--accent); color: var(--accent); }
.pc-card-actions button.danger:hover { border-color: var(--error); color: var(--error); }
.pc-chart-wrap {
  position: relative;
  min-height: 200px;
}
.pc-svg { width: 100%; height: 200px; display: block; cursor: crosshair; }
.grid { stroke: var(--border); stroke-width: .5; opacity: .6; }
.axis-y { font-size: 9px; fill: var(--text-muted); text-anchor: end; }
.axis-x { font-size: 9px; fill: var(--text-muted); }
.axis-x.end { text-anchor: end; }
.hover-line {
  stroke: var(--accent);
  stroke-width: 1;
  stroke-dasharray: 4 3;
  opacity: .85;
}
.hover-dot {
  stroke: var(--bg-card);
  stroke-width: 1.4;
}
.pc-tooltip {
  position: absolute;
  z-index: 5;
  width: 260px;
  max-width: calc(100% - 16px);
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  box-shadow: 0 10px 28px rgba(0, 0, 0, .22);
  padding: 8px 9px;
  pointer-events: none;
}
.pc-tooltip-time {
  margin-bottom: 6px;
  color: var(--text-muted);
  font-size: 11px;
  font-family: var(--font-mono);
}
.pc-tooltip-row {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  line-height: 1.65;
}
.pc-tooltip-row i {
  width: 10px;
  height: 3px;
  border-radius: 2px;
}
.pc-tooltip-row span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}
.pc-tooltip-row b {
  color: var(--text-primary);
  font-family: var(--font-mono);
}
.pc-chart-empty {
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 12px;
}
.pc-chart-empty.error { color: var(--error); padding: 0 20px; text-align: center; }
.pc-legend { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 8px; }
.pc-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-secondary);
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pc-legend-item i { width: 10px; height: 3px; border-radius: 2px; flex-shrink: 0; }
.pc-legend-item b { color: var(--text-primary); }
.pc-legend-more { font-size: 11px; color: var(--text-muted); }

.pc-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, .45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 60;
}
.pc-modal {
  width: min(620px, 94vw);
  max-height: 88vh;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.pc-modal-wide { width: min(860px, 96vw); }
.pc-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 16px;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}
.pc-modal-head button { background: none; border: none; color: var(--text-muted); font-size: 18px; cursor: pointer; }
.pc-modal-body {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
}
.pc-modal-body label { display: flex; flex-direction: column; gap: 5px; }
.pc-modal-body label span { font-size: 12px; color: var(--text-muted); }
.pc-modal-body textarea { font-family: var(--font-mono); resize: vertical; }
.pc-form-grid { display: grid; grid-template-columns: 1fr 130px; gap: 10px; }
.pc-variable-insert {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: var(--text-muted);
  font-size: 12px;
}
.pc-variable-insert button,
.pc-quick button {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-base);
  color: var(--text-secondary);
  padding: 3px 10px;
  font-size: 11px;
  cursor: pointer;
}
.pc-variable-insert button:hover,
.pc-quick button:hover { border-color: var(--accent); color: var(--accent); }
.pc-quick { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; color: var(--text-muted); }
.pc-test { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.pc-test .ok { color: var(--success); }
.pc-test .bad { color: var(--error); }
.pc-error { color: var(--error); font-size: 12px; margin: 0; }
.pc-modal-foot { display: flex; gap: 8px; padding: 13px 16px; border-top: 1px solid var(--border); }

.pc-var-editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.pc-empty-inline {
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 18px;
  color: var(--text-muted);
  text-align: center;
  font-size: 13px;
}
.pc-var-row {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px;
  background: var(--bg-base);
}
.pc-var-row-main {
  display: grid;
  grid-template-columns: minmax(110px, .7fr) minmax(150px, .8fr) minmax(220px, 1.5fr);
  gap: 10px;
}
.pc-var-row-sub {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto auto minmax(120px, .5fr);
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.pc-var-row-sub small {
  color: var(--error);
  font-size: 11px;
}

.spinner, .spinner-sm {
  display: inline-block;
  border-radius: 50%;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  animation: pcspin .75s linear infinite;
}
.spinner { width: 22px; height: 22px; }
.spinner-sm { width: 13px; height: 13px; }
@keyframes pcspin { to { transform: rotate(360deg); } }

@media (max-width: 1000px) {
  .pc-grid { grid-template-columns: 1fr; }
  .pc-tabs { align-items: flex-start; flex-direction: column; }
  .pc-var-row-main,
  .pc-var-row-sub { grid-template-columns: 1fr; }
}
</style>
