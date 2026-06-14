<template>
  <div class="red-page">
    <div class="page-header">
      <div>
        <h1>接口 RED 仪表盘</h1>
        <span class="subtitle">Rate · Errors · Duration · 微服务接口实时健康（数据源 SkyWalking）</span>
      </div>
      <div class="header-actions">
        <select v-model.number="hours" class="filter">
          <option :value="1">最近 1 小时</option>
          <option :value="6">最近 6 小时</option>
          <option :value="24">最近 24 小时</option>
          <option :value="72">最近 3 天</option>
        </select>
        <select v-model.number="topN" class="filter">
          <option :value="10">Top 10</option>
          <option :value="20">Top 20</option>
          <option :value="50">Top 50</option>
        </select>
        <button class="btn btn-outline btn-sm" :disabled="loading" @click="load">⟳ 刷新</button>
      </div>
    </div>

    <!-- KPI -->
    <div class="kpi-row">
      <div class="kpi"><span>接口总数</span><strong>{{ endpoints.length }}</strong></div>
      <div class="kpi ok"><span>健康</span><strong>{{ stats.ok }}</strong></div>
      <div class="kpi warn"><span>告警</span><strong>{{ stats.warn }}</strong></div>
      <div class="kpi danger"><span>危险</span><strong>{{ stats.danger }}</strong></div>
      <div class="kpi"><span>总 QPS</span><strong>{{ totalQps }}</strong></div>
      <div class="kpi"><span>平均错误率</span><strong>{{ avgErrorRate }}%</strong></div>
    </div>

    <!-- Grafana 风格 4 张时序图（实时聚合，10s 轮询）-->
    <div class="grafana-grid">
      <div class="g-panel">
        <div class="g-title"><span class="g-dot" style="background:#60a5fa"></span>QPS 总量 · Rate</div>
        <Sparkline :values="series.qps" :tone="'#60a5fa'" :height="92" unit=" rps"
          :fmt="v => v == null ? '—' : v.toFixed(1)" />
      </div>
      <div class="g-panel">
        <div class="g-title"><span class="g-dot" style="background:#BD564F"></span>错误率 · Errors</div>
        <Sparkline :values="series.err" :tone="'#BD564F'" :height="92" unit="%"
          :fmt="v => v == null ? '—' : v.toFixed(2)" />
      </div>
      <div class="g-panel">
        <div class="g-title"><span class="g-dot" style="background:#C58A46"></span>p95 延迟 · Duration</div>
        <Sparkline :values="series.p95" :tone="'#C58A46'" :height="92" unit=" ms"
          :fmt="v => v == null ? '—' : Math.round(v)" />
      </div>
      <div class="g-panel">
        <div class="g-title"><span class="g-dot" style="background:#D97757"></span>p99 延迟</div>
        <Sparkline :values="series.p99" :tone="'#D97757'" :height="92" unit=" ms"
          :fmt="v => v == null ? '—' : Math.round(v)" />
      </div>
    </div>

    <!-- 排序与过滤 -->
    <div class="filter-bar">
      <input v-model="search" class="search" placeholder="按接口名 / 服务名过滤" />
      <span class="sep"></span>
      <span class="sort-label">排序：</span>
      <button v-for="opt in SORT_OPTIONS" :key="opt.key" class="sort-btn"
        :class="{ active: sortBy === opt.key }" @click="setSort(opt.key)">
        {{ opt.label }}
        <span v-if="sortBy === opt.key" class="sort-arrow">↓</span>
      </button>
    </div>

    <!-- 数据表 -->
    <div v-if="loading" class="empty-state"><div class="spinner"></div><p>加载接口数据…</p></div>
    <div v-else-if="!endpoints.length" class="empty-state"><span class="icon">📊</span><p>无接口数据</p></div>
    <table v-else class="red-table">
      <thead>
        <tr>
          <th>状态</th>
          <th>接口</th>
          <th class="num">QPS<br/><small>Rate</small></th>
          <th class="num">错误率<br/><small>Errors</small></th>
          <th class="num">avg<br/><small>ms</small></th>
          <th class="num">p95<br/><small>ms</small></th>
          <th class="num">p99<br/><small>ms</small></th>
          <th class="num">SLA<br/><small>%</small></th>
          <th style="width:140px">QPS 趋势</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="ep in visibleEndpoints" :key="ep.name">
          <td>
            <span class="tone-dot" :class="ep.red_tone || 'ok'" :title="toneTip(ep)"></span>
          </td>
          <td class="ep-cell">
            <div class="ep-name">{{ ep._endpoint }}</div>
            <div class="ep-svc">{{ ep._service }}</div>
          </td>
          <td class="num mono">{{ ep.qps?.toFixed(2) ?? '-' }}</td>
          <td class="num mono" :class="errorTone(ep.error_rate)">{{ ep.error_rate?.toFixed(2) ?? '-' }}%</td>
          <td class="num mono">{{ ep.avg_ms ?? '-' }}</td>
          <td class="num mono" :class="latencyTone(ep.p95)">{{ ep.p95 ?? '-' }}</td>
          <td class="num mono" :class="latencyTone(ep.p99)">{{ ep.p99 ?? '-' }}</td>
          <td class="num mono">{{ ep.sla?.toFixed(1) ?? '-' }}</td>
          <td class="ep-spark">
            <Sparkline
              :values="epSeries[ep.name] || []"
              :height="28" :show-grid="false" :show-labels="false"
              :tone="errorTone(ep.error_rate) === 'danger' ? '#BD564F' : '#60a5fa'"
            />
          </td>
          <td>
            <button class="link" @click="jumpLogs(ep)" title="跳到日志中心，按服务过滤">日志 →</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'
import { useTimeRangeStore } from '../stores/timeRange.js'
import Sparkline from '../components/Sparkline.vue'

// 时序缓冲：60 个数据点；10 秒一个 = 10 分钟历史
const MAX_POINTS = 60
const series = reactive({ qps: [], err: [], p95: [], p99: [] })
const epSeries = reactive({})   // { endpointName: [number] }

function pushSeries(arr, v) {
  arr.push(Number.isFinite(v) ? v : null)
  if (arr.length > MAX_POINTS) arr.shift()
}

const router = useRouter()
const timeStore = useTimeRangeStore()
// hours 与全局 store 双向绑定（也保留本地 select 可独立改）
const hours = computed({
  get: () => timeStore.hours,
  set: (v) => timeStore.set(v),
})
const topN  = ref(20)
const loading = ref(false)
const endpoints = ref([])
const search = ref('')
const sortBy = ref('qps')   // qps / error_rate / p95 / p99 / avg_ms

const SORT_OPTIONS = [
  { key: 'qps', label: 'QPS' },
  { key: 'error_rate', label: '错误率' },
  { key: 'p95', label: 'p95' },
  { key: 'p99', label: 'p99' },
  { key: 'avg_ms', label: '平均耗时' },
]

async function load() {
  loading.value = true
  try {
    const data = await api.swEndpointTopN(hours.value, topN.value)
    endpoints.value = (Array.isArray(data) ? data : []).map(ep => {
      const parts = String(ep.name || '').split(':')
      const svc = parts[0]?.trim() || ''
      const path = parts.slice(1).join(':').trim() || ep.name
      return { ...ep, _service: svc, _endpoint: path }
    })
    // 聚合时序：所有接口求总和/均值
    if (endpoints.value.length) {
      const totalQps = endpoints.value.reduce((s, e) => s + (e.qps || 0), 0)
      const avgErr = endpoints.value.reduce((s, e) => s + (e.error_rate || 0), 0) / endpoints.value.length
      const maxP95 = Math.max(...endpoints.value.map(e => e.p95 || 0))
      const maxP99 = Math.max(...endpoints.value.map(e => e.p99 || 0))
      // 首次加载预填 3 点形成短曲线，避免「单点不画」
      const seed = (arr, v) => {
        if (arr.length === 0) { arr.push(v, v); }
        pushSeries(arr, v)
      }
      seed(series.qps, totalQps)
      seed(series.err, avgErr)
      seed(series.p95, maxP95)
      seed(series.p99, maxP99)
    }
    // 每接口 sparkline 缓冲
    for (const ep of endpoints.value) {
      if (!epSeries[ep.name]) epSeries[ep.name] = [ep.qps || 0, ep.qps || 0]
      pushSeries(epSeries[ep.name], ep.qps || 0)
    }
  } catch (e) { endpoints.value = [] }
  finally { loading.value = false }
}

watch([hours, topN], load)

let pollTimer = null
onMounted(() => {
  // 兼容旧 localStorage 中的非整数小时（如 Dashboard 写入的 0.5）：
  // 若当前不在本页 select 候选内，回退到 1 小时
  const allowed = [1, 6, 24, 72]
  if (!allowed.includes(timeStore.hours)) timeStore.set(1)
  load()
  pollTimer = setInterval(load, 10000)   // 10s 轮询积累时序
})
onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer) })

const stats = computed(() => {
  const acc = { ok: 0, warn: 0, danger: 0 }
  for (const ep of endpoints.value) acc[ep.red_tone || 'ok']++
  return acc
})

const totalQps = computed(() =>
  endpoints.value.reduce((s, e) => s + (e.qps || 0), 0).toFixed(1))

const avgErrorRate = computed(() => {
  if (!endpoints.value.length) return '0.00'
  const total = endpoints.value.reduce((s, e) => s + (e.error_rate || 0), 0)
  return (total / endpoints.value.length).toFixed(2)
})

const visibleEndpoints = computed(() => {
  const kw = search.value.trim().toLowerCase()
  let list = endpoints.value
  if (kw) list = list.filter(e => (e.name || '').toLowerCase().includes(kw))
  return [...list].sort((a, b) => (b[sortBy.value] || 0) - (a[sortBy.value] || 0))
})

function setSort(k) { sortBy.value = k }

function errorTone(er) {
  if (er == null) return ''
  if (er > 5) return 'danger'
  if (er > 1) return 'warn'
  return 'ok'
}
function latencyTone(ms) {
  if (ms == null) return ''
  if (ms > 1000) return 'danger'
  if (ms > 500) return 'warn'
  return ''
}
function toneTip(ep) {
  const er = ep.error_rate, p = ep.p95
  if (ep.red_tone === 'danger') return `危险：错误率 ${er}%、p95 ${p}ms`
  if (ep.red_tone === 'warn') return `告警：错误率 ${er}%、p95 ${p}ms`
  return `健康：错误率 ${er}%、p95 ${p}ms`
}
function jumpLogs(ep) {
  // 跳到日志中心，预填服务名 + 当前时间窗
  router.push({ path: '/observability/logs', query: { service: ep._service, hours: hours.value } })
}
</script>

<style scoped>
.red-page { padding: 24px 28px; overflow-y: auto; }
.page-header { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 18px; gap: 12px; }
.page-header h1 { font-family: var(--font-serif); font-size: 26px; font-weight: 500; letter-spacing: -0.015em; }
.page-header .subtitle { color: var(--text-secondary); font-size: 13px; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.filter { background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; font-size: 12.5px; min-width: 110px; }

.grafana-grid {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 12px; margin-bottom: 16px;
}
.g-panel {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
  padding: 12px 14px 14px; min-width: 0;
}
.g-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--text-secondary); font-weight: 600;
  margin-bottom: 8px;
}
.g-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

.ep-spark { padding: 4px 8px !important; min-width: 130px; vertical-align: middle; }

@media (max-width: 1200px) { .grafana-grid { grid-template-columns: repeat(2, 1fr); } }

.kpi-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 14px; }
.kpi { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 10px 14px; display: flex; flex-direction: column; gap: 2px; }
.kpi span { font-size: 11px; color: var(--text-muted); }
.kpi strong { font-size: 20px; font-weight: 600; }
.kpi.ok strong { color: var(--success); }
.kpi.warn strong { color: var(--warning); }
.kpi.danger strong { color: var(--error); }

.filter-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.search { background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; font-size: 12.5px; width: 260px; }
.sep { width: 1px; height: 18px; background: var(--border); }
.sort-label { font-size: 12px; color: var(--text-muted); }
.sort-btn { background: transparent; border: 1px solid var(--border); border-radius: 8px; padding: 4px 10px; font-size: 12px; color: var(--text-secondary); cursor: pointer; }
.sort-btn:hover { color: var(--text-primary); border-color: var(--border-strong); }
.sort-btn.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); font-weight: 600; }
.sort-arrow { margin-left: 4px; }

.red-table { width: 100%; border-collapse: collapse; background: var(--bg-card); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.red-table th { padding: 10px 14px; font-size: 11px; color: var(--text-muted); border-bottom: 1px solid var(--border); text-align: left; background: var(--bg-surface); font-weight: 500; }
.red-table th.num { text-align: right; }
.red-table th small { color: var(--text-muted); opacity: .7; font-weight: 400; }
.red-table td { padding: 11px 14px; border-bottom: 1px solid var(--border-light); font-size: 12.5px; }
.red-table td.num { text-align: right; }
.red-table tr:last-child td { border-bottom: none; }
.red-table tbody tr:hover td { background: var(--bg-hover); }

.tone-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; }
.tone-dot.ok { background: var(--success); box-shadow: 0 0 0 3px rgba(99,130,91,.18); }
.tone-dot.warn { background: var(--warning); box-shadow: 0 0 0 3px rgba(197,138,70,.18); }
.tone-dot.danger { background: var(--error); box-shadow: 0 0 0 3px rgba(189,86,79,.18); }

.ep-cell { max-width: 360px; }
.ep-name { font-weight: 500; word-break: break-all; }
.ep-svc { font-size: 11px; color: var(--text-muted); margin-top: 2px; font-family: var(--font-mono); }

.mono { font-family: var(--font-mono); }
.mono.warn { color: var(--warning); font-weight: 600; }
.mono.danger { color: var(--error); font-weight: 600; }
.mono.ok { color: var(--success); }

.link { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 12px; padding: 0; }
.link:hover { text-decoration: underline; }

.empty-state { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 60px; color: var(--text-muted); }
.empty-state .icon { font-size: 36px; opacity: .6; }
</style>
