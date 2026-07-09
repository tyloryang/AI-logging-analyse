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
        <button class="btn btn-primary" @click="openEditor()">＋ 添加图表</button>
      </div>
    </header>

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
            <code :title="chart.query">{{ chart.query }}</code>
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
          <svg :viewBox="`0 0 ${W} ${H}`" class="pc-svg" preserveAspectRatio="none">
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
            <text :x="PAD" :y="H-4" class="axis-x">{{ dataOf(chart.id).t0 }}</text>
            <text :x="W-8" :y="H-4" class="axis-x end">{{ dataOf(chart.id).t1 }}</text>
          </svg>
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
            <textarea v-model="editor.query" rows="3" spellcheck="false"
                      placeholder='100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100'></textarea>
          </label>
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
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api/index.js'

const W = 600
const H = 200
const PAD = 46

const palette = ['#d97757', '#388bfd', '#3fb950', '#d29922', '#bc8cff', '#f85149', '#39c5cf', '#e3b341']

const charts = ref([])
const rangeMinutes = ref(60)
const refreshSeconds = ref(0)
const step = ref(60)
const loadingAll = ref(false)
const chartData = reactive({})   // id -> { loading, error, series, min, max, t0, t1 }

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

let refreshTimer = null
let saveTimer = null

function dataOf(id) {
  return chartData[id] || { loading: true, error: '', series: [], min: 0, max: 1, t0: '', t1: '' }
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

async function loadChart(chart) {
  chartData[chart.id] = { ...dataOf(chart.id), loading: true, error: '' }
  const end = Math.floor(Date.now() / 1000)
  const start = end - rangeMinutes.value * 60
  const stepValue = Math.max(15, Math.floor(rangeMinutes.value * 60 / 240))
  try {
    const result = await api.prometheusQueryRange({ query: chart.query, start, end, step: stepValue })
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
      chartData[chart.id] = { loading: false, error: '', series: [], min: 0, max: 1, t0: '', t1: '' }
      return
    }
    if (min === max) { min -= 1; max += 1 }
    const pad = (max - min) * 0.05
    min -= pad; max += pad
    for (const s of parsed) {
      s.points = s.values.map(([ts, v]) => {
        const x = PAD + ((ts - start) / (end - start)) * (W - PAD - 8)
        const y = 14 + (1 - (v - min) / (max - min)) * (H - 40)
        return `${x.toFixed(1)},${y.toFixed(1)}`
      }).join(' ')
    }
    const fmt = ts => new Date(ts * 1000).toTimeString().slice(0, 5)
    chartData[chart.id] = {
      loading: false, error: '', series: parsed, min, max,
      t0: fmt(start), t1: fmt(end),
    }
  } catch (error) {
    chartData[chart.id] = {
      loading: false, series: [], min: 0, max: 1, t0: '', t1: '',
      error: error?.response?.data?.detail || 'Prometheus 查询失败',
    }
  }
}

async function reloadAll() {
  loadingAll.value = true
  try {
    await Promise.all(charts.value.map(loadChart))
  } finally {
    loadingAll.value = false
  }
}

function schedulePersist() {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(persist, 400)
}

async function persist() {
  try {
    await api.saveMetricPanels({
      charts: charts.value,
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
  if (!editor.query.trim()) { editor.testResult = '请先填写表达式'; editor.testOk = false; return }
  editor.testing = true
  editor.testResult = ''
  try {
    const result = await api.prometheusQuery({ query: editor.query.trim() })
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
    const chart = { id: `chart-${Date.now().toString(36)}`, ...payload }
    charts.value.push(chart)
  }
  editor.visible = false
  schedulePersist()
  const target = charts.value.find(item => item.id === (editor.id || charts.value[charts.value.length - 1].id))
  if (target) loadChart(target)
}

function duplicateChart(chart) {
  const copy = { ...chart, id: `chart-${Date.now().toString(36)}`, title: `${chart.title} 副本` }
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
  schedulePersist()
}

onMounted(async () => {
  try {
    const saved = await api.getMetricPanels()
    charts.value = saved.charts || []
    rangeMinutes.value = saved.range_minutes || 60
    step.value = saved.step || 60
    refreshSeconds.value = saved.refresh_seconds || 0
  } catch { /* 使用空面板 */ }
  setupRefreshTimer()
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
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.pc-header h1 { font-size: 20px; margin: 0 0 4px; }
.pc-header p { margin: 0; color: var(--text-muted); font-size: 13px; }
.pc-toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.pc-toolbar select,
.pc-modal input, .pc-modal textarea, .pc-modal select {
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 7px 10px;
  font-size: 13px;
  outline: none;
}
.pc-modal input:focus, .pc-modal textarea:focus { border-color: var(--accent); }
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
.pc-svg { width: 100%; height: 200px; display: block; }
.grid { stroke: var(--border); stroke-width: .5; opacity: .6; }
.axis-y { font-size: 9px; fill: var(--text-muted); text-anchor: end; }
.axis-x { font-size: 9px; fill: var(--text-muted); }
.axis-x.end { text-anchor: end; }
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
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}
.pc-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 16px;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}
.pc-modal-head button { background: none; border: none; color: var(--text-muted); font-size: 18px; cursor: pointer; }
.pc-modal-body { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.pc-modal-body label { display: flex; flex-direction: column; gap: 5px; }
.pc-modal-body label span { font-size: 12px; color: var(--text-muted); }
.pc-modal-body textarea { font-family: var(--font-mono); resize: vertical; }
.pc-form-grid { display: grid; grid-template-columns: 1fr 130px; gap: 10px; }
.pc-quick { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; color: var(--text-muted); }
.pc-quick button {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-base);
  color: var(--text-secondary);
  padding: 3px 10px;
  font-size: 11px;
  cursor: pointer;
}
.pc-quick button:hover { border-color: var(--accent); color: var(--accent); }
.pc-test { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.pc-test .ok { color: var(--success); }
.pc-test .bad { color: var(--error); }
.pc-error { color: var(--error); font-size: 12px; margin: 0; }
.pc-modal-foot { display: flex; gap: 8px; padding: 13px 16px; border-top: 1px solid var(--border); }

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
}
</style>
