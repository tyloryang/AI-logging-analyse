<template>
  <div class="page task-center">
    <header class="page-header">
      <div>
        <h1>任务中心</h1>
        <p class="subtitle">巡检 · 部署 · 命令草稿 — 看待确认动作，看执行结果，看审计回放</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-outline btn-sm" :disabled="loading" @click="reload">⟳ 刷新</button>
      </div>
    </header>

    <!-- KPI -->
    <div class="kpi-row">
      <div class="kpi"><span>总任务</span><strong>{{ stats.total }}</strong></div>
      <div class="kpi warn"><span>待确认</span><strong>{{ stats.pending }}</strong></div>
      <div class="kpi"><span>执行中</span><strong>{{ stats.running }}</strong></div>
      <div class="kpi ok"><span>已完成</span><strong>{{ stats.done }}</strong></div>
      <div class="kpi danger"><span>失败</span><strong>{{ stats.failed }}</strong></div>
      <div class="kpi"><span>平均耗时</span><strong>{{ stats.avgCost }}</strong></div>
    </div>

    <div class="tc-tabs">
      <button v-for="t in TABS" :key="t.id" class="tc-tab" :class="{ active: tab === t.id }" @click="tab = t.id">
        {{ t.label }} <span class="tab-count" :class="{ warn: t.id === 'pending' && counts.pending > 0 }">{{ counts[t.id] || 0 }}</span>
      </button>
    </div>

    <div v-if="loading" class="empty-state"><div class="spinner"></div><p>加载中...</p></div>
    <div v-else-if="!visibleTasks.length" class="empty-state"><span class="icon">📋</span><p>{{ tab === 'pending' ? '暂无待确认动作' : '无任务记录' }}</p></div>
    <div v-else class="task-list">
      <div v-for="t in visibleTasks" :key="t._key" class="task-row" :class="'st-' + (t._statusTone || 'info')">
        <div class="tr-type">
          <span class="type-badge" :class="t._typeClass">{{ t._typeLabel }}</span>
        </div>
        <div class="tr-body">
          <div class="tr-title">{{ t._title }}</div>
          <div class="tr-meta">
            <span class="tr-meta-item">⏱ {{ fmtTime(t._time) }}</span>
            <span v-if="t._target" class="tr-meta-item">🎯 {{ t._target }}</span>
            <span v-if="t._actor" class="tr-meta-item">👤 {{ t._actor }}</span>
            <span v-if="t._cost != null" class="tr-meta-item">⏳ {{ t._cost }}s</span>
          </div>
        </div>
        <div class="tr-status">
          <span class="status-badge" :class="t._statusTone">{{ t._statusLabel }}</span>
        </div>
        <div class="tr-actions">
          <button v-if="tab === 'pending' || t._status === 'pending'" class="btn btn-primary btn-xs"
                  @click="confirmTask(t)" :disabled="confirming === t._key">
            <span v-if="confirming === t._key" class="spinner-mini"></span>
            ✓ 确认执行
          </button>
          <button v-if="t._link" class="btn btn-outline btn-xs" @click="goLink(t._link)">→ 详情</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/index.js'

const route = useRoute()
const router = useRouter()
const tab = ref(route.query.tab || 'all')
const loading = ref(false)
const confirming = ref('')

const tickets = ref([])      // 工单视为部署/SQL 任务
const hostTasks = ref([])    // 主机巡检/命令任务
const pendingActions = ref([])  // AIOps 待确认动作（暂时空，等 P3.2 接通）

const TABS = [
  { id: 'all', label: '全部' },
  { id: 'pending', label: '待确认' },
  { id: 'running', label: '执行中' },
  { id: 'done', label: '已完成' },
  { id: 'failed', label: '失败' },
]

watch(() => route.query.tab, (v) => { if (v) tab.value = v })
watch(tab, (v) => router.replace({ query: { ...route.query, tab: v === 'all' ? undefined : v } }))

function normalizeTicket(t) {
  const TYPE = { deploy: { label: '应用发布', cls: 'deploy' }, sql: { label: 'SQL', cls: 'sql' },
                 incident: { label: '事务', cls: 'incident' }, approval: { label: '审批', cls: 'approval' } }
  const ST = { pending: { label: '待审批', tone: 'warn' }, approved: { label: '已批准', tone: 'ok' },
               in_progress: { label: '执行中', tone: 'warn' }, done: { label: '已完成', tone: 'ok' },
               rejected: { label: '已拒绝', tone: 'danger' }, cancelled: { label: '已取消', tone: 'info' } }
  const ty = TYPE[t.type] || { label: '工单', cls: 'other' }
  const st = ST[t.status] || { label: t.status, tone: 'info' }
  return {
    _key: 'ticket-' + t.id,
    _type: 'ticket', _typeLabel: ty.label, _typeClass: ty.cls,
    _title: `${t.no || ''} ${t.title || ''}`.trim(),
    _time: t.updated_at || t.created_at,
    _target: t.extra?.target || '',
    _actor: t.assignee || '',
    _cost: null,
    _status: t.status,
    _statusLabel: st.label,
    _statusTone: st.tone,
    _link: `/tickets/${t.type}`,
  }
}

function normalizeHostTask(h) {
  const ST = { running: { label: '执行中', tone: 'warn' }, success: { label: '成功', tone: 'ok' },
               failed: { label: '失败', tone: 'danger' }, pending: { label: '待执行', tone: 'info' } }
  const st = ST[h.status] || { label: h.status || '-', tone: 'info' }
  return {
    _key: 'host-' + (h.id || h.created_at),
    _type: 'host', _typeLabel: '主机任务', _typeClass: 'host',
    _title: h.name || h.command || '主机任务',
    _time: h.updated_at || h.created_at,
    _target: h.target_ip || (h.hosts || []).join(', '),
    _actor: h.creator || '',
    _cost: h.duration_sec ?? null,
    _status: h.status,
    _statusLabel: st.label,
    _statusTone: st.tone,
    _link: '/hosts/tasks',
  }
}

function normalizePending(p) {
  return {
    _key: 'pending-' + p.id,
    _type: 'pending', _typeLabel: 'AIOps 草稿', _typeClass: 'aiops',
    _title: p.title || p.action || 'AI 待确认动作',
    _time: p.created_at,
    _target: p.target || '',
    _actor: p.requested_by || 'AIOps',
    _cost: null,
    _status: 'pending',
    _statusLabel: '待确认',
    _statusTone: 'warn',
    _link: null,
    _rawPending: p,
  }
}

const allTasks = computed(() => [
  ...pendingActions.value.map(normalizePending),
  ...tickets.value.map(normalizeTicket),
  ...hostTasks.value.map(normalizeHostTask),
])

const counts = computed(() => ({
  all: allTasks.value.length,
  pending: allTasks.value.filter(t => t._status === 'pending').length,
  running: allTasks.value.filter(t => t._status === 'in_progress' || t._status === 'running').length,
  done: allTasks.value.filter(t => t._status === 'done' || t._status === 'success' || t._status === 'approved').length,
  failed: allTasks.value.filter(t => t._status === 'failed' || t._status === 'rejected').length,
}))

const stats = computed(() => {
  const costs = allTasks.value.filter(t => t._cost != null).map(t => t._cost)
  const avg = costs.length ? (costs.reduce((a, b) => a + b, 0) / costs.length) : 0
  return {
    total: counts.value.all,
    pending: counts.value.pending,
    running: counts.value.running,
    done: counts.value.done,
    failed: counts.value.failed,
    avgCost: avg ? `${avg.toFixed(1)}s` : '—',
  }
})

const visibleTasks = computed(() => {
  let list = allTasks.value
  if (tab.value === 'pending') list = list.filter(t => t._status === 'pending')
  else if (tab.value === 'running') list = list.filter(t => t._status === 'in_progress' || t._status === 'running')
  else if (tab.value === 'done') list = list.filter(t => ['done', 'success', 'approved'].includes(t._status))
  else if (tab.value === 'failed') list = list.filter(t => ['failed', 'rejected'].includes(t._status))
  return [...list].sort((a, b) => (b._time || '').localeCompare(a._time || ''))
})

async function reload() {
  loading.value = true
  try {
    const [t, h, p] = await Promise.allSettled([
      api.listTickets({ limit: 200 }),
      fetch('/api/host-tasks?limit=100', { credentials: 'include' }).then(r => r.ok ? r.json() : { data: [] }),
      fetch('/api/aiops/pending-actions', { credentials: 'include' }).then(r => r.ok ? r.json() : { data: [] }).catch(() => ({ data: [] })),
    ])
    tickets.value = t.status === 'fulfilled' ? (Array.isArray(t.value) ? t.value : (t.value?.data || [])) : []
    hostTasks.value = h.status === 'fulfilled' ? (h.value?.data || h.value || []) : []
    pendingActions.value = p.status === 'fulfilled' ? (p.value?.data || []) : []
  } finally {
    loading.value = false
  }
}

async function confirmTask(t) {
  if (t._type === 'ticket') {
    if (!confirm(`确认批准工单「${t._title}」？`)) return
    confirming.value = t._key
    try { await api.approveTicket(t._rawPending?.id || t._key.replace('ticket-', '')); await reload() }
    finally { confirming.value = '' }
  } else if (t._type === 'pending') {
    if (!confirm(`确认执行 AIOps 动作「${t._title}」？`)) return
    confirming.value = t._key
    try {
      await fetch(`/api/aiops/pending-actions/${t._rawPending.id}/approve`, { method: 'POST', credentials: 'include' })
      await reload()
    } catch (e) { alert('确认失败: ' + e) }
    finally { confirming.value = '' }
  }
}

function fmtTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN', { hour12: false })
}

function goLink(link) { router.push(link) }

onMounted(reload)
</script>

<style scoped>
.page-header { display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 18px; gap: 12px; }
.page-header h1 { font-family: var(--font-serif); font-size: 28px; font-weight: 500; letter-spacing: -0.015em; }
.page-header .subtitle { color: var(--text-secondary); font-size: 13px; margin-top: 4px; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.kpi-row { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; margin-bottom: 16px; }
.kpi { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 10px 14px;
  display: flex; flex-direction: column; gap: 2px; }
.kpi span { font-size: 11px; color: var(--text-muted); }
.kpi strong { font-size: 20px; font-weight: 600; }
.kpi.ok strong { color: var(--success); }
.kpi.warn strong { color: var(--warning); }
.kpi.danger strong { color: var(--error); }

.tc-tabs { display: flex; gap: 4px; margin-bottom: 14px; border-bottom: 1px solid var(--border); }
.tc-tab { background: none; border: none; padding: 8px 14px; border-bottom: 2px solid transparent;
  font-size: 13.5px; color: var(--text-secondary); cursor: pointer; font-family: inherit; }
.tc-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.tab-count { background: var(--bg-surface); color: var(--text-muted); padding: 1px 7px; border-radius: 99px; font-size: 11px; margin-left: 4px; }
.tc-tab.active .tab-count { background: var(--accent-soft); color: var(--accent); }
.tab-count.warn { background: rgba(189,86,79,.14); color: var(--error); font-weight: 600; }

.task-list { display: flex; flex-direction: column; gap: 8px; }
.task-row {
  display: grid; grid-template-columns: 110px 1fr 110px 180px; gap: 14px;
  align-items: center;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 16px;
  transition: border-color .15s;
}
.task-row:hover { border-color: var(--border-strong); }
.task-row.st-warn { border-left: 3px solid var(--warning); }
.task-row.st-danger { border-left: 3px solid var(--error); }
.task-row.st-ok { border-left: 3px solid var(--success); }

.type-badge {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 2px 10px; border-radius: 99px; font-size: 11.5px; font-weight: 600;
}
.type-badge.deploy { background: rgba(96,165,250,.14); color: #60a5fa; }
.type-badge.sql { background: rgba(197,138,70,.14); color: var(--warning); }
.type-badge.incident { background: rgba(189,86,79,.14); color: var(--error); }
.type-badge.approval { background: rgba(148,163,184,.16); color: var(--text-secondary); }
.type-badge.host { background: rgba(99,130,91,.16); color: var(--success); }
.type-badge.aiops { background: var(--accent-soft); color: var(--accent); }

.tr-body { min-width: 0; }
.tr-title { font-weight: 600; font-size: 13.5px; margin-bottom: 4px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tr-meta { display: flex; gap: 12px; flex-wrap: wrap; font-size: 11.5px; color: var(--text-muted); }
.tr-meta-item { white-space: nowrap; }

.status-badge {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 3px 10px; border-radius: 99px; font-size: 11.5px; font-weight: 600;
  background: var(--bg-surface); color: var(--text-secondary);
}
.status-badge.ok { background: rgba(99,130,91,.16); color: var(--success); }
.status-badge.warn { background: rgba(197,138,70,.16); color: var(--warning); }
.status-badge.danger { background: rgba(189,86,79,.14); color: var(--error); }

.tr-actions { display: flex; gap: 6px; justify-content: flex-end; }
.btn-xs { padding: 3px 10px; font-size: 11.5px; }

.spinner { width: 22px; height: 22px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; }
.spinner-mini { width: 10px; height: 10px; border: 1.5px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.empty-state { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 60px; color: var(--text-muted); }
.empty-state .icon { font-size: 36px; opacity: .6; }
</style>
