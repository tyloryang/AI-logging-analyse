<template>
  <div class="page fault-dashboard">
    <!-- 页头 -->
    <div class="page-header">
      <h1>故障大盘</h1>
      <span class="subtitle">实时告警态势 · 服务健康总览</span>
      <div class="env-selector-bar">
        <label class="env-label">环境</label>
        <button v-for="e in ENV_OPTIONS" :key="e.value"
          class="env-btn"
          :class="{ active: envFilter === e.value }"
          @click="envFilter = e.value; refresh()">
          {{ e.label }}
        </button>
        <select v-if="nsOptions.length" v-model="nsFilter" @change="refresh" class="ns-select" title="Namespace">
          <option value="">全部 Namespace</option>
          <option v-for="ns in nsOptions" :key="ns" :value="ns">{{ ns }}</option>
        </select>
      </div>
      <button class="btn btn-outline btn-sm" style="margin-left:8px" @click="refresh" :disabled="loading">
        {{ loading ? '刷新中...' : '刷新' }}
      </button>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-row">
      <div class="stat-card p0">
        <div class="stat-num">{{ statsData.p0 ?? '--' }}</div>
        <div class="stat-label">P0 紧急告警</div>
      </div>
      <div class="stat-card p1">
        <div class="stat-num">{{ statsData.p1 ?? '--' }}</div>
        <div class="stat-label">P1 警告</div>
      </div>
      <div class="stat-card active">
        <div class="stat-num">{{ statsData.active ?? '--' }}</div>
        <div class="stat-label">活跃告警组</div>
      </div>
      <div class="stat-card resolved">
        <div class="stat-num">{{ statsData.resolved ?? '--' }}</div>
        <div class="stat-label">今日已解决</div>
      </div>
      <div class="stat-card suppressed">
        <div class="stat-num">{{ statsData.suppressed ?? '--' }}</div>
        <div class="stat-label">已抑制</div>
      </div>
    </div>

    <!-- 告警列表 -->
    <div class="card" style="margin-top:16px">
      <div class="card-header">
        <h3>活跃告警组</h3>
        <div class="filter-row">
          <select v-model="severityFilter" class="filter-select">
            <option value="">全部严重度</option>
            <option value="critical">Critical</option>
            <option value="error">Error</option>
            <option value="warning">Warning</option>
          </select>
          <span v-if="envFilter || nsFilter" class="env-badge-active">
            {{ [envFilter, nsFilter].filter(Boolean).join(' / ') }}
            <button @click="envFilter=''; nsFilter=''; refresh()" class="clear-env-btn">✕</button>
          </span>
        </div>
      </div>

      <div v-if="loading" class="empty-state"><div class="spinner"></div></div>
      <div v-else-if="!filteredGroups.length" class="empty-state">
        <div class="icon">✅</div>
        <div>当前无活跃告警</div>
      </div>
      <table v-else>
        <thead>
          <tr>
            <th style="width:90px">严重度</th>
            <th>告警名称</th>
            <th>服务</th>
            <th style="width:60px">触发次数</th>
            <th style="width:160px">首次告警</th>
            <th style="width:160px">最近更新</th>
            <th style="width:120px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in filteredGroups" :key="g.id" class="alert-row" @click="openDetail(g)">
            <td><span class="sev-badge" :class="g.severity">{{ g.severity }}</span></td>
            <td class="alert-name">{{ g.alertname }}</td>
            <td class="mono">{{ g.service }}</td>
            <td class="mono" style="text-align:center">{{ g.count }}</td>
            <td class="mono time">{{ fmtTime(g.first_at) }}</td>
            <td class="mono time">{{ fmtTime(g.last_at) }}</td>
            <td @click.stop>
              <div class="action-btns">
                <button class="btn btn-sm btn-outline" @click="resolve(g)">解决</button>
                <button class="btn btn-sm btn-ghost" @click="suppress(g)">抑制</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 详情抽屉 -->
    <Transition name="slide">
      <div v-if="detail" class="detail-drawer">
        <div class="drawer-header">
          <span class="sev-badge" :class="detail.severity">{{ detail.severity }}</span>
          <span class="drawer-title">{{ detail.alertname }}</span>
          <button class="drawer-close" @click="detail = null">×</button>
        </div>
        <div class="drawer-body">
          <div class="detail-row"><label>服务</label><span class="mono">{{ detail.service }}</span></div>
          <div class="detail-row"><label>触发次数</label><span>{{ detail.count }} 次</span></div>
          <div class="detail-row"><label>首次告警</label><span class="mono">{{ fmtTime(detail.first_at) }}</span></div>
          <div class="detail-row"><label>最近更新</label><span class="mono">{{ fmtTime(detail.last_at) }}</span></div>
          <div class="detail-row"><label>摘要</label><span>{{ detail.summary || '—' }}</span></div>
          <div class="detail-row" v-if="detail.description"><label>描述</label><span>{{ detail.description }}</span></div>

          <div class="drawer-section">原始告警（最近 {{ detail.raw_alerts?.length || 0 }} 条）</div>
          <div v-for="(a, i) in (detail.raw_alerts || [])" :key="i" class="raw-alert-item">
            <div class="raw-labels">
              <span v-for="(v, k) in a.labels" :key="k" class="label-chip">{{ k }}=<b>{{ v }}</b></span>
            </div>
            <div class="raw-time mono">{{ fmtTime(a.startsAt) }}</div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api/index.js'

const ENV_OPTIONS = [
  { label: '全部', value: '' },
  { label: '生产', value: 'production' },
  { label: '预发', value: 'staging' },
  { label: '开发', value: 'development' },
  { label: '测试', value: 'testing' },
]

const loading        = ref(false)
const statsData      = ref({})
const groups         = ref([])
const detail         = ref(null)
const severityFilter = ref('')
const envFilter      = ref('')
const nsFilter       = ref('')
const nsOptions      = ref([])

const filteredGroups = computed(() => {
  let active = groups.value.filter(g => !['resolved', 'suppressed'].includes(g.status))
  if (severityFilter.value) active = active.filter(g => g.severity === severityFilter.value)
  return active
})

async function refresh() {
  loading.value = true
  try {
    const params = {}
    if (envFilter.value) params.env       = envFilter.value
    if (nsFilter.value)  params.namespace = nsFilter.value
    const [s, g, fo] = await Promise.all([
      api.alertStats(),
      api.alertGroups(params),
      api.alertFilters().catch(() => ({ namespaces: [] })),
    ])
    statsData.value = s
    groups.value    = g.groups || []
    nsOptions.value = fo.namespaces || []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function fmtTime(iso) {
  if (!iso) return '—'
  return iso.slice(0, 19).replace('T', ' ')
}

function openDetail(g) {
  detail.value = g
}

async function resolve(g) {
  await api.alertUpdateStatus(g.id, { status: 'resolved' })
  await refresh()
  if (detail.value?.id === g.id) detail.value = null
}

async function suppress(g) {
  await api.alertUpdateStatus(g.id, { status: 'suppressed' })
  await refresh()
  if (detail.value?.id === g.id) detail.value = null
}

let timer = null
onMounted(() => {
  refresh()
  timer = setInterval(refresh, 30000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.fault-dashboard { position: relative; }

.stat-row { display: flex; gap: 12px; flex-wrap: wrap; }
.stat-card {
  flex: 1; min-width: 120px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 16px 20px;
  border-left: 3px solid var(--border);
}
.stat-card.p0      { border-left-color: var(--error); }
.stat-card.p1      { border-left-color: var(--warning); }
.stat-card.active  { border-left-color: var(--accent); }
.stat-card.resolved  { border-left-color: var(--success); }
.stat-card.suppressed { border-left-color: var(--text-muted); }
.stat-num  { font-size: 28px; font-weight: 700; color: var(--text-primary); font-family: 'Cascadia Code', 'Consolas', monospace; }
.stat-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

.filter-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.env-selector-bar { display: flex; align-items: center; gap: 4px; margin-left: auto; }
.env-label { font-size: 12px; color: var(--text-muted); margin-right: 2px; }
.env-btn { padding: 3px 10px; border-radius: 12px; border: 1px solid var(--border); background: transparent; color: var(--text-secondary); font-size: 12px; cursor: pointer; transition: all .15s; }
.env-btn:hover { background: var(--bg-hover); }
.env-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.ns-select { padding: 3px 8px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 12px; }
.env-badge-active { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: rgba(56,139,253,.12); color: var(--accent); display: flex; align-items: center; gap: 4px; }
.clear-env-btn { background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 12px; padding: 0; }
.filter-select { padding: 4px 8px; font-size: 12px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary); }

.sev-badge {
  display: inline-flex; align-items: center; padding: 2px 8px;
  border-radius: 3px; font-size: 11px; font-weight: 600; font-family: 'Cascadia Code', 'Consolas', monospace;
}
.sev-badge.critical, .sev-badge.error { background: rgba(207,34,46,.1); color: var(--error); }
.sev-badge.warning { background: rgba(154,103,0,.1); color: var(--warning); }
.sev-badge.info    { background: var(--accent-dim); color: var(--accent); }

.alert-row { cursor: pointer; }
.alert-row:hover td { background: var(--bg-hover); }
.alert-name { font-weight: 500; color: var(--text-primary); }
.time { font-size: 12px; color: var(--text-muted); }

.action-btns { display: flex; gap: 4px; }
.btn-ghost { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
.btn-ghost:hover { border-color: var(--warning); color: var(--warning); }

/* 详情抽屉 */
.detail-drawer {
  position: fixed; top: 0; right: 0; bottom: 0; width: 420px;
  background: var(--bg-card); border-left: 1px solid var(--border);
  box-shadow: var(--shadow-md); z-index: 200;
  display: flex; flex-direction: column;
}
.drawer-header {
  display: flex; align-items: center; gap: 10px;
  padding: 16px 20px; border-bottom: 1px solid var(--border-light); flex-shrink: 0;
}
.drawer-title { font-size: 14px; font-weight: 600; flex: 1; }
.drawer-close { background: none; border: none; font-size: 20px; cursor: pointer; color: var(--text-muted); }
.drawer-body { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
.detail-row { display: flex; gap: 12px; align-items: flex-start; font-size: 13px; }
.detail-row label { width: 80px; flex-shrink: 0; color: var(--text-muted); font-size: 12px; padding-top: 1px; }
.drawer-section { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; margin-top: 6px; padding-top: 10px; border-top: 1px solid var(--border-light); }
.raw-alert-item { background: var(--bg-surface); border-radius: var(--radius); padding: 8px 10px; display: flex; flex-direction: column; gap: 4px; }
.raw-labels { display: flex; flex-wrap: wrap; gap: 4px; }
.label-chip { font-size: 11px; background: var(--accent-dim); color: var(--accent); padding: 1px 6px; border-radius: 3px; font-family: 'Cascadia Code', 'Consolas', monospace; }
.raw-time { font-size: 11px; color: var(--text-muted); }

.slide-enter-active, .slide-leave-active { transition: transform .2s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
