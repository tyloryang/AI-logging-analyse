<template>
  <div class="page alert-center">
    <div class="page-header">
      <h1>告警中心</h1>
      <span class="subtitle">聚合告警管理 · 降噪 · 抑制规则</span>
      <button class="btn btn-outline btn-sm" style="margin-left:auto" @click="load" :disabled="loading">
        {{ loading ? '刷新中...' : '刷新' }}
      </button>
    </div>

    <!-- 状态标签页 -->
    <div class="tab-bar">
      <button v-for="t in TABS" :key="t.key" class="tab" :class="{ active: tab === t.key }" @click="tab = t.key">
        {{ t.label }}
        <span v-if="t.key !== 'all'" class="tab-count">{{ countByStatus(t.key) }}</span>
      </button>
      <!-- 过滤器 -->
      <div class="alert-filters">
        <select v-model="filterNs" @change="load" class="filter-select" title="K8s Namespace">
          <option value="">全部 Namespace</option>
          <option v-for="ns in filterOptions.namespaces" :key="ns" :value="ns">{{ ns }}</option>
        </select>
        <select v-model="filterEnv" @change="load" class="filter-select" title="环境">
          <option value="">全部环境</option>
          <option v-for="e in filterOptions.envs" :key="e" :value="e">{{ e }}</option>
          <option value="production">生产</option>
          <option value="staging">预发</option>
          <option value="development">开发</option>
          <option value="testing">测试</option>
        </select>
        <input v-model="filterSvc" @input="load" class="filter-input" placeholder="服务名筛选..." />
      </div>
    </div>

    <!-- 模拟接入说明 -->
    <div class="webhook-tip">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
      AlertManager Webhook 地址：
      <code>{{ webhookUrl }}</code>
      <button class="copy-btn" @click="copyWebhook">{{ copied ? '已复制' : '复制' }}</button>
    </div>

    <div v-if="loading" class="empty-state"><div class="spinner"></div></div>
    <div v-else-if="!filtered.length" class="empty-state">
      <div class="icon">🔕</div>
      <div>该分类下暂无告警</div>
    </div>

    <div v-else class="groups-list">
      <div v-for="g in filtered" :key="g.id" class="group-card" :class="g.severity">
        <!-- 卡片头 -->
        <div class="group-head">
          <span class="sev-dot" :class="g.severity"></span>
          <span class="group-name">{{ g.alertname }}</span>
          <span class="group-svc mono">{{ g.service }}</span>
          <span class="group-count">{{ g.count }} 次</span>
          <span class="status-chip" :class="g.status">{{ STATUS_LABEL[g.status] || g.status }}</span>
          <div class="group-actions">
            <button v-if="g.status !== 'resolved'" class="btn btn-sm btn-outline" @click="resolve(g)">解决</button>
            <button v-if="!['suppressed','resolved'].includes(g.status)" class="btn btn-sm btn-ghost" @click="suppress(g)">抑制</button>
          </div>
        </div>

        <!-- 摘要 -->
        <div v-if="g.summary" class="group-summary">{{ g.summary }}</div>

        <!-- 时间线 -->
        <div class="group-meta">
          <span>首次：<span class="mono">{{ fmt(g.first_at) }}</span></span>
          <span>最近：<span class="mono">{{ fmt(g.last_at) }}</span></span>
          <span v-if="g.resolved_at">解决：<span class="mono">{{ fmt(g.resolved_at) }}</span></span>
        </div>

        <!-- 展开原始告警 -->
        <button class="expand-btn" @click="toggleExpand(g.id)">
          {{ expanded.has(g.id) ? '▲ 收起' : `▼ 展开 ${g.raw_alerts?.length || 0} 条原始告警` }}
        </button>
        <div v-if="expanded.has(g.id)" class="raw-list">
          <div v-for="(a, i) in g.raw_alerts" :key="i" class="raw-item">
            <div class="raw-labels">
              <span v-for="(v, k) in a.labels" :key="k" class="label-chip">{{ k }}=<b>{{ v }}</b></span>
            </div>
            <div v-if="a.annotations?.description" class="raw-desc">{{ a.annotations.description }}</div>
            <div class="raw-time mono">{{ fmt(a.startsAt) }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const TABS = [
  { key: 'all',        label: '全部' },
  { key: 'new',        label: '新建' },
  { key: 'grouped',    label: '已聚合' },
  { key: 'analyzing',  label: '分析中' },
  { key: 'suppressed', label: '已抑制' },
  { key: 'resolved',   label: '已解决' },
]

const STATUS_LABEL = {
  new:        '新建',
  grouped:    '已聚合',
  analyzing:  '分析中',
  suppressed: '已抑制',
  resolved:   '已解决',
}

const loading       = ref(false)
const groups        = ref([])
const tab           = ref('all')
const expanded      = ref(new Set())
const copied        = ref(false)
const filterNs      = ref('')
const filterEnv     = ref('')
const filterSvc     = ref('')
const filterOptions = ref({ namespaces: [], envs: [] })

const webhookUrl = computed(() => `${window.location.protocol}//${window.location.host}/api/alerts/webhook`)

const filtered = computed(() => {
  if (tab.value === 'all') return groups.value
  return groups.value.filter(g => g.status === tab.value)
})

function countByStatus(status) {
  return groups.value.filter(g => g.status === status).length
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filterNs.value)  params.namespace = filterNs.value
    if (filterEnv.value) params.env       = filterEnv.value
    if (filterSvc.value) params.service   = filterSvc.value
    const [r, fo] = await Promise.all([
      api.alertGroups(params),
      api.alertFilters().catch(() => ({ namespaces: [], envs: [] })),
    ])
    groups.value        = r.groups || []
    filterOptions.value = fo
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

function fmt(iso) {
  if (!iso) return '—'
  return iso.slice(0, 19).replace('T', ' ')
}

function toggleExpand(id) {
  const s = new Set(expanded.value)
  s.has(id) ? s.delete(id) : s.add(id)
  expanded.value = s
}

async function resolve(g) {
  await api.alertUpdateStatus(g.id, { status: 'resolved' })
  await load()
}

async function suppress(g) {
  await api.alertUpdateStatus(g.id, { status: 'suppressed' })
  await load()
}

async function copyWebhook() {
  try {
    await navigator.clipboard.writeText(webhookUrl.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {}
}

onMounted(load)
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

.groups-list { display: flex; flex-direction: column; gap: 10px; }

.group-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 14px 16px;
  border-left: 3px solid var(--border);
  display: flex; flex-direction: column; gap: 8px;
}
.group-card.critical, .group-card.error { border-left-color: var(--error); }
.group-card.warning { border-left-color: var(--warning); }
.group-card.info    { border-left-color: var(--accent); }

.group-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sev-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.sev-dot.critical, .sev-dot.error { background: var(--error); }
.sev-dot.warning { background: var(--warning); }
.sev-dot.info    { background: var(--accent); }
.group-name { font-weight: 600; font-size: 13px; }
.group-svc { font-size: 12px; color: var(--text-secondary); }
.group-count { font-size: 12px; color: var(--text-muted); margin-left: auto; }
.group-actions { display: flex; gap: 6px; }

.status-chip {
  font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 3px;
}
.status-chip.new        { background: var(--accent-dim); color: var(--accent); }
.status-chip.grouped    { background: rgba(154,103,0,.1); color: var(--warning); }
.status-chip.analyzing  { background: rgba(115,63,255,.1); color: #7c3aed; }
.status-chip.suppressed { background: var(--bg-surface); color: var(--text-muted); }
.status-chip.resolved   { background: rgba(26,127,55,.1); color: var(--success); }

.group-summary { font-size: 13px; color: var(--text-secondary); }
.group-meta { display: flex; gap: 16px; font-size: 11px; color: var(--text-muted); }

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
</style>
