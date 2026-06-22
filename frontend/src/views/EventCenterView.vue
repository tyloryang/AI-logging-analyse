<template>
  <div class="page event-center">
    <header class="page-header">
      <div>
        <h1>事件中心</h1>
        <p class="subtitle">最终执行结果 · 关键写操作 · 失败定位 — 聚合告警、工单与运维事件</p>
      </div>
      <div class="header-actions">
        <select v-model="filter.system" class="filter" @change="reload">
          <option value="">全部系统</option>
          <option v-for="s in systemOptions" :key="s" :value="s">{{ s }}</option>
        </select>
        <select v-model="filter.env" class="filter" @change="reload">
          <option value="">全部环境</option>
          <option value="production">生产</option>
          <option value="staging">预发</option>
          <option value="testing">测试</option>
        </select>
        <select v-model="filter.status" class="filter" @change="reload">
          <option value="">全部状态</option>
          <option value="failed">仅失败</option>
          <option value="success">仅成功</option>
        </select>
        <button class="btn btn-outline btn-sm" :disabled="loading" @click="reload">⟳ 刷新</button>
      </div>
    </header>

    <!-- KPI 行 -->
    <div class="kpi-row">
      <div class="kpi"><span>总事件</span><strong>{{ stats.total }}</strong></div>
      <div class="kpi danger"><span>失败</span><strong>{{ stats.failed }}</strong></div>
      <div class="kpi warn"><span>审批中</span><strong>{{ stats.pending }}</strong></div>
      <div class="kpi ok"><span>成功</span><strong>{{ stats.success }}</strong></div>
      <div class="kpi"><span>告警 (24h)</span><strong>{{ stats.alerts }}</strong></div>
      <div class="kpi"><span>关键写操作</span><strong>{{ stats.writes }}</strong></div>
    </div>

    <!-- 按 source 分 tab -->
    <div class="ec-tabs">
      <button v-for="t in TABS" :key="t.id" class="ec-tab" :class="{ active: tab === t.id }" @click="tab = t.id">
        {{ t.label }} <span class="tab-count">{{ counts[t.id] || 0 }}</span>
      </button>
    </div>

    <!-- 事件列表 -->
    <div v-if="loading" class="empty-state"><div class="spinner"></div><p>加载中...</p></div>
    <div v-else-if="!visibleEvents.length" class="empty-state"><span class="icon">📭</span><p>无事件</p></div>
    <div v-else class="event-list">
      <div v-for="ev in visibleEvents" :key="ev._key" class="event-row" :class="'tone-' + (ev._tone || 'info')">
        <div class="ev-tone-bar"></div>
        <div class="ev-meta">
          <span class="ev-type" :class="ev._source">{{ ev._sourceLabel }}</span>
          <span class="ev-time mono">{{ fmtTime(ev._time) }}</span>
        </div>
        <div class="ev-body">
          <div class="ev-title">{{ ev._title }}</div>
          <div class="ev-detail">{{ ev._detail }}</div>
          <div class="ev-tags">
            <span v-if="ev._system" class="ev-tag">系统: {{ ev._system }}</span>
            <span v-if="ev._env" class="ev-tag">环境: {{ ev._env }}</span>
            <span v-if="ev._actor" class="ev-tag">操作人: {{ ev._actor }}</span>
            <span v-if="ev._status" class="ev-tag" :class="'st-' + ev._status">{{ ev._statusLabel || ev._status }}</span>
          </div>
        </div>
        <div class="ev-actions">
          <button v-if="ev._link" class="btn btn-outline btn-xs" @click="goLink(ev._link)">→ 详情</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router = useRouter()
const loading = ref(false)
const alerts = ref([])
const tickets = ref([])
const events = ref([])   // /api/events 数据

const filter = reactive({ system: '', env: '', status: '' })
const tab = ref('all')

const TABS = [
  { id: 'all', label: '全部' },
  { id: 'alerts', label: '告警' },
  { id: 'tickets', label: '工单' },
  { id: 'events', label: '事件墙' },
]

const stats = computed(() => ({
  total: allEvents.value.length,
  failed: allEvents.value.filter(e => e._tone === 'danger' || e._status === 'failed' || e._status === 'rejected').length,
  pending: allEvents.value.filter(e => e._status === 'pending' || e._status === 'in_progress').length,
  success: allEvents.value.filter(e => e._status === 'success' || e._status === 'done' || e._status === 'approved').length,
  alerts: alerts.value.length,
  writes: tickets.value.filter(t => ['deploy', 'sql'].includes(t.type)).length,
}))

const counts = computed(() => ({
  all: allEvents.value.length,
  alerts: alerts.value.length,
  tickets: tickets.value.length,
  events: events.value.length,
}))

const systemOptions = computed(() => {
  const set = new Set()
  for (const e of allEvents.value) if (e._system) set.add(e._system)
  return [...set].sort()
})

// 统一规范化各类事件到通用结构
function normalizeAlert(a) {
  return {
    _key: 'alert-' + (a.id ?? a.time + a.service),
    _source: 'alert', _sourceLabel: '告警',
    _time: a.time || new Date().toISOString(),
    _title: a.service + ' 异常告警',
    _detail: a.description || `${a.service} 检测到 ${a.count} 条错误日志`,
    _tone: a.level === 'critical' ? 'danger' : a.level === 'warning' ? 'warn' : 'info',
    _system: a.service,
    _status: 'failed',
    _statusLabel: a.level?.toUpperCase(),
    _link: '/observability/alerts',
  }
}

function normalizeTicket(t) {
  const TYPE_LABELS = { deploy: '应用发布', sql: 'SQL 审计', incident: '事务工单', approval: '审批流' }
  const STATUS_LABELS = { pending: '待审批', approved: '已批准', rejected: '已拒绝', in_progress: '执行中', done: '已完成', cancelled: '已取消' }
  const tone = ({ rejected: 'danger', pending: 'warn', in_progress: 'warn', done: 'ok', approved: 'ok' })[t.status] || 'info'
  return {
    _key: 'ticket-' + t.id,
    _source: 'ticket', _sourceLabel: TYPE_LABELS[t.type] || '工单',
    _time: t.updated_at || t.created_at,
    _title: `${t.no || ''} ${t.title || ''}`.trim(),
    _detail: t.description || '',
    _tone: tone,
    _system: t.extra?.system || t.extra?.service || '',
    _env: t.extra?.env || '',
    _actor: t.assignee || '',
    _status: t.status,
    _statusLabel: STATUS_LABELS[t.status] || t.status,
    _link: `/tickets/${t.type}`,
  }
}

function normalizeEvent(e) {
  return {
    _key: 'evt-' + (e.id ?? e.time + e.title),
    _source: 'event', _sourceLabel: '事件',
    _time: e.time || new Date().toISOString(),
    _title: e.title || '事件',
    _detail: e.message || '',
    _tone: e.severity === 'critical' || e.severity === 'error' ? 'danger' : e.severity === 'warning' ? 'warn' : 'info',
    _system: e.service || '',
    _status: e.status || '',
    _link: '/events',
  }
}

const allEvents = computed(() => {
  let list = []
  if (tab.value === 'all' || tab.value === 'alerts') list = list.concat(alerts.value.map(normalizeAlert))
  if (tab.value === 'all' || tab.value === 'tickets') list = list.concat(tickets.value.map(normalizeTicket))
  if (tab.value === 'all' || tab.value === 'events') list = list.concat(events.value.map(normalizeEvent))
  return list
})

const visibleEvents = computed(() => {
  return allEvents.value.filter(e => {
    if (filter.system && e._system !== filter.system) return false
    if (filter.env && e._env !== filter.env) return false
    if (filter.status === 'failed' && e._tone !== 'danger') return false
    if (filter.status === 'success' && !['ok'].includes(e._tone)) return false
    return true
  }).sort((a, b) => (b._time || '').localeCompare(a._time || ''))
})

async function reload() {
  loading.value = true
  try {
    const [a, t, e] = await Promise.allSettled([
      api.getErrorMetrics(24).then(r => (r?.data || []).map((item, i) => ({
        id: i, service: item.service, count: item.count, time: new Date(Date.now() - i * 120000).toISOString(),
        level: item.count >= 100 ? 'critical' : item.count >= 10 ? 'warning' : 'info',
      }))),
      api.listTickets({ limit: 200 }),
      fetch('/api/events?hours=24&limit=200', { credentials: 'include' }).then(r => r.json()),
    ])
    alerts.value = a.status === 'fulfilled' ? a.value : []
    tickets.value = t.status === 'fulfilled' ? (Array.isArray(t.value) ? t.value : (t.value?.data || [])) : []
    events.value = e.status === 'fulfilled' ? (Array.isArray(e.value) ? e.value : []) : []
  } finally {
    loading.value = false
  }
}

function fmtTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

function goLink(link) {
  if (link?.startsWith('http')) window.open(link, '_blank')
  else router.push(link)
}

onMounted(reload)
</script>

<style scoped>
.page-header { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 18px; gap: 12px; }
.page-header h1 { font-family: var(--font-serif); font-size: 28px; font-weight: 500; letter-spacing: -0.015em; }
.page-header .subtitle { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }
.header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.filter { background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; font-size: 12.5px; min-width: 110px; color: inherit; }

.kpi-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 16px; }
.kpi { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 10px 14px; display: flex; flex-direction: column; gap: 2px; }
.kpi span { font-size: 11px; color: var(--text-muted); }
.kpi strong { font-size: 20px; font-weight: 600; }
.kpi.ok strong { color: var(--success); }
.kpi.warn strong { color: var(--warning); }
.kpi.danger strong { color: var(--error); }

.ec-tabs { display: flex; gap: 4px; margin-bottom: 14px; border-bottom: 1px solid var(--border); }
.ec-tab { background: none; border: none; padding: 8px 14px; border-bottom: 2px solid transparent;
  font-size: 13.5px; color: var(--text-secondary); cursor: pointer; font-family: inherit; }
.ec-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.ec-tab .tab-count { background: var(--bg-surface); color: var(--text-muted); padding: 1px 7px; border-radius: 99px; font-size: 11px; margin-left: 4px; }
.ec-tab.active .tab-count { background: var(--accent-soft); color: var(--accent); }

.event-list { display: flex; flex-direction: column; gap: 8px; }
.event-row {
  display: grid; grid-template-columns: 4px 130px 1fr auto; gap: 14px;
  align-items: center;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 14px; padding-left: 0;
  transition: border-color .15s;
}
.event-row:hover { border-color: var(--border-strong); }
.ev-tone-bar { width: 4px; align-self: stretch; border-radius: 4px 0 0 4px; }
.event-row.tone-danger .ev-tone-bar { background: var(--error); }
.event-row.tone-warn .ev-tone-bar { background: var(--warning); }
.event-row.tone-ok .ev-tone-bar { background: var(--success); }
.event-row.tone-info .ev-tone-bar { background: var(--text-muted); opacity: .4; }

.ev-meta { display: flex; flex-direction: column; gap: 4px; font-size: 11.5px; padding-left: 14px; }
.ev-type {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 1px 8px; border-radius: 99px; font-size: 11px; font-weight: 600; width: fit-content;
}
.ev-type.alert { background: rgba(189,86,79,.12); color: var(--error); }
.ev-type.ticket { background: rgba(96,165,250,.14); color: #60a5fa; }
.ev-type.event { background: rgba(197,138,70,.14); color: var(--warning); }
.ev-time { color: var(--text-muted); }

.ev-body { min-width: 0; }
.ev-title { font-weight: 600; font-size: 13.5px; color: var(--text-primary); margin-bottom: 3px; }
.ev-detail { color: var(--text-secondary); font-size: 12.5px; line-height: 1.5; margin-bottom: 6px; }
.ev-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.ev-tag { font-size: 10.5px; padding: 1px 8px; border-radius: 99px;
  background: var(--bg-surface); color: var(--text-secondary); }
.ev-tag.st-rejected { background: rgba(189,86,79,.14); color: var(--error); }
.ev-tag.st-pending,
.ev-tag.st-in_progress { background: rgba(197,138,70,.14); color: var(--warning); }
.ev-tag.st-done,
.ev-tag.st-approved { background: rgba(99,130,91,.14); color: var(--success); }

.spinner { width: 22px; height: 22px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.empty-state { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 60px; color: var(--text-muted); }
.empty-state .icon { font-size: 36px; opacity: .6; }
</style>
