<template>
  <div class="page anomaly-view">
    <div class="page-header">
      <h1>异常检测</h1>
      <span class="subtitle">3σ 动比 · 趋势检测 · 静态阈值 · 每5分钟自动执行</span>
      <div style="margin-left:auto;display:flex;gap:8px">
        <button class="btn btn-outline btn-sm" @click="load" :disabled="loading">刷新</button>
        <button class="btn btn-primary btn-sm" @click="detect" :disabled="detecting">
          {{ detecting ? '检测中...' : '▶ 立即检测' }}
        </button>
      </div>
    </div>

    <!-- 检测结果提示 -->
    <div v-if="detectResult" class="detect-result" :class="detectResult.detected ? 'warn' : 'ok'">
      <template v-if="detectResult.detected">
        本次检测发现 <b>{{ detectResult.detected }}</b> 个异常
        （P0: {{ detectResult.p0 }}，P1: {{ detectResult.p1 }}）
      </template>
      <template v-else>本次检测未发现异常</template>
    </div>

    <!-- 过滤 -->
    <div class="filter-bar">
      <button v-for="t in SEVERITY_TABS" :key="t.key" class="tab" :class="{ active: sevFilter === t.key }" @click="sevFilter = t.key">
        {{ t.label }} <span class="tab-count">{{ countBySev(t.key) }}</span>
      </button>
      <button v-for="t in TYPE_TABS" :key="t.key" class="tab type-tab" :class="{ active: typeFilter === t.key }" @click="typeFilter = t.key">
        {{ t.label }}
      </button>
    </div>

    <div v-if="loading" class="empty-state"><div class="spinner"></div></div>
    <div v-else-if="!filtered.length" class="empty-state">
      <div class="icon">✅</div>
      <div>该分类下暂无异常记录</div>
    </div>

    <div v-else class="anomaly-list">
      <div v-for="a in filtered" :key="a.detected_at + a.name" class="anomaly-card" :class="a.severity.toLowerCase()">
        <div class="anomaly-head">
          <span class="sev-badge" :class="a.severity.toLowerCase()">{{ a.severity }}</span>
          <span class="anomaly-name">{{ a.name }}</span>
          <span class="type-chip">{{ TYPE_LABEL[a.type] || a.type }}</span>
          <span class="anomaly-time mono">{{ fmt(a.detected_at) }}</span>
        </div>

        <div class="anomaly-detail">{{ a.detail }}</div>

        <!-- 数值对比 -->
        <div class="metrics-row">
          <div class="metric-item">
            <div class="metric-label">当前值</div>
            <div class="metric-value" :class="a.severity.toLowerCase()">
              {{ a.value }}{{ a.unit }}
            </div>
          </div>
          <template v-if="a.type === 'static'">
            <div class="metric-item">
              <div class="metric-label">阈值</div>
              <div class="metric-value muted">{{ a.threshold }}{{ a.unit }}</div>
            </div>
          </template>
          <template v-if="a.type === 'dynamic_3sigma'">
            <div class="metric-item">
              <div class="metric-label">7天均值</div>
              <div class="metric-value muted">{{ a.baseline }}{{ a.unit }}</div>
            </div>
            <div class="metric-item">
              <div class="metric-label">标准差 σ</div>
              <div class="metric-value muted">{{ a.sigma }}{{ a.unit }}</div>
            </div>
          </template>
        </div>

        <!-- 操作 -->
        <div class="anomaly-actions">
          <button class="btn btn-sm btn-outline" @click="triggerRCA(a)">
            🧠 触发 RCA 分析
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router   = useRouter()
const loading  = ref(false)
const detecting = ref(false)
const anomalies = ref([])
const detectResult = ref(null)
const sevFilter  = ref('all')
const typeFilter = ref('all')

const SEVERITY_TABS = [
  { key: 'all', label: '全部' },
  { key: 'p0',  label: 'P0 紧急' },
  { key: 'p1',  label: 'P1 警告' },
  { key: 'p2',  label: 'P2 预警' },
]
const TYPE_TABS = [
  { key: 'all',           label: '所有类型' },
  { key: 'static',        label: '静态阈值' },
  { key: 'dynamic_3sigma', label: '3σ 动比' },
  { key: 'trend',         label: '趋势检测' },
]
const TYPE_LABEL = {
  static:          '静态阈值',
  dynamic_3sigma:  '3σ 动比',
  trend:           '趋势上升',
}

const filtered = computed(() => {
  let list = anomalies.value
  if (sevFilter.value !== 'all')
    list = list.filter(a => a.severity.toLowerCase() === sevFilter.value)
  if (typeFilter.value !== 'all')
    list = list.filter(a => a.type === typeFilter.value)
  return list
})

function countBySev(key) {
  if (key === 'all') return anomalies.value.length
  return anomalies.value.filter(a => a.severity.toLowerCase() === key).length
}

function fmt(iso) {
  if (!iso) return '—'
  return iso.slice(0, 19).replace('T', ' ')
}

async function load() {
  loading.value = true
  try {
    const r = await api.rcaAnomalies(200)
    anomalies.value = r.anomalies || []
  } finally {
    loading.value = false
  }
}

async function detect() {
  detecting.value = true
  detectResult.value = null
  try {
    const r = await api.rcaDetect()
    detectResult.value = r
    await load()
  } finally {
    detecting.value = false
  }
}

async function triggerRCA(a) {
  await api.rcaTrigger({ alert_name: a.name, extra_context: a.detail, hours: 0.5 })
  router.push('/aiops/rca')
}

onMounted(load)
</script>

<style scoped>
.filter-bar { display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 16px; align-items: center; }
.tab {
  padding: 6px 14px; font-size: 12px; border: 1px solid var(--border);
  border-radius: var(--radius); background: none; cursor: pointer;
  color: var(--text-secondary); transition: all .12s;
}
.tab:hover { border-color: var(--accent); color: var(--accent); }
.tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); font-weight: 500; }
.type-tab { margin-left: 8px; }
.tab-count {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 16px; height: 16px; padding: 0 4px;
  background: var(--bg-surface); border-radius: 8px;
  font-size: 10px; font-weight: 600; color: var(--text-muted); margin-left: 4px;
}

.detect-result {
  padding: 10px 14px; border-radius: var(--radius); margin-bottom: 14px; font-size: 13px;
}
.detect-result.warn { background: rgba(154,103,0,.08); border: 1px solid rgba(154,103,0,.2); color: var(--warning); }
.detect-result.ok   { background: rgba(26,127,55,.08); border: 1px solid rgba(26,127,55,.2); color: var(--success); }

.anomaly-list { display: flex; flex-direction: column; gap: 10px; }
.anomaly-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 14px 16px;
  border-left: 3px solid var(--border);
  display: flex; flex-direction: column; gap: 8px;
}
.anomaly-card.p0 { border-left-color: var(--error); }
.anomaly-card.p1 { border-left-color: var(--warning); }
.anomaly-card.p2 { border-left-color: var(--accent); }

.anomaly-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sev-badge {
  font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 3px;
  font-family: 'Cascadia Code', 'Consolas', monospace;
}
.sev-badge.p0 { background: rgba(207,34,46,.1); color: var(--error); }
.sev-badge.p1 { background: rgba(154,103,0,.1); color: var(--warning); }
.sev-badge.p2 { background: var(--accent-dim); color: var(--accent); }
.anomaly-name { font-weight: 600; font-size: 13px; flex: 1; }
.type-chip {
  font-size: 10px; padding: 1px 6px; border-radius: 3px;
  background: var(--bg-surface); border: 1px solid var(--border); color: var(--text-muted);
}
.anomaly-time { font-size: 11px; color: var(--text-muted); }
.anomaly-detail { font-size: 13px; color: var(--text-secondary); }

.metrics-row { display: flex; gap: 20px; flex-wrap: wrap; }
.metric-item { display: flex; flex-direction: column; gap: 2px; }
.metric-label { font-size: 11px; color: var(--text-muted); }
.metric-value { font-size: 18px; font-weight: 700; font-family: 'Cascadia Code', 'Consolas', monospace; }
.metric-value.p0 { color: var(--error); }
.metric-value.p1 { color: var(--warning); }
.metric-value.p2 { color: var(--accent); }
.metric-value.muted { font-size: 15px; color: var(--text-secondary); }

.anomaly-actions { display: flex; gap: 8px; }
</style>
