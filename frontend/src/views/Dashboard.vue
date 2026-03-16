<template>
  <div class="dash">

    <!-- ── 头部 ──────────────────────────────────────────────── -->
    <div class="dash-header">
      <div class="dash-title">
        <h1>仪表盘</h1>
        <span class="subtitle">系统总览 · 最近 24 小时</span>
      </div>
    </div>

    <div v-if="loading" class="loading-full"><div class="spinner"></div><p>加载中...</p></div>

    <template v-else>

      <!-- ── 统计区（主机 + 日志 并排）───────────────────────── -->
      <div class="stats-row">

        <!-- 主机概览 -->
        <div class="stats-panel">
          <div class="section-label">
            <span class="section-dot prom"></span>主机概览
            <RouterLink to="/hosts" class="section-link">查看详情 →</RouterLink>
          </div>
          <div v-if="hostError" class="inline-warn">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            Prometheus 未连接，主机数据不可用
          </div>
          <div class="stat-grid" v-else>
            <div class="stat-card" v-for="s in hostStats" :key="s.label" :style="{ '--card-accent': s.color }">
              <div class="stat-value mono" :style="{ color: s.color }">{{ s.value }}</div>
              <div class="stat-label">{{ s.label }}</div>
              <div class="stat-bar"></div>
            </div>
          </div>
        </div>

        <!-- 日志分析 -->
        <div class="stats-panel">
          <div class="section-label">
            <span class="section-dot loki"></span>日志分析
            <RouterLink to="/logs" class="section-link">查看日志 →</RouterLink>
          </div>
          <div class="stat-grid">
            <div class="stat-card" v-for="s in logStats" :key="s.label" :style="{ '--card-accent': s.color }">
              <div class="stat-value mono" :style="{ color: s.color }">{{ s.value }}</div>
              <div class="stat-label">{{ s.label }}</div>
              <div class="stat-bar"></div>
            </div>
          </div>
        </div>

      </div>

      <!-- ── 下方面板（撑满剩余高度）──────────────────────────── -->
      <div class="lower-grid">

        <!-- 错误 Top 10 -->
        <div class="card panel-card">
          <div class="card-header">
            <h3>错误 Top 10 服务</h3>
          </div>
          <div class="error-list">
            <div v-if="!errorMetrics.length" class="empty-state" style="padding:24px">
              <span>暂无错误数据</span>
            </div>
            <div v-for="(item, i) in errorMetrics.slice(0,10)" :key="item.service" class="error-row">
              <span class="rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
              <span class="svc-name">{{ item.service }}</span>
              <div class="bar-wrap">
                <div class="bar" :style="{ width: barWidth(item.count) + '%' }"></div>
              </div>
              <span class="badge badge-error">{{ item.count }}</span>
            </div>
          </div>
        </div>

        <!-- 主机状态 / 服务状态 -->
        <div class="card panel-card">
          <div class="card-header">
            <h3>主机状态</h3>
            <div v-if="hosts.length" class="sort-btns">
              <button
                v-for="col in sortCols" :key="col.key"
                class="sort-btn" :class="{ active: sortKey === col.key }"
                @click="toggleSort(col.key)"
              >
                {{ col.label }}
                <span class="sort-arrow">{{ sortKey === col.key ? (sortAsc ? '↑' : '↓') : '↕' }}</span>
              </button>
            </div>
          </div>
          <div v-if="hosts.length" class="host-list">
            <div v-for="h in sortedHosts" :key="h.instance" class="host-row">
              <span class="host-dot" :class="h.state === 'up' ? 'ok' : 'err'"></span>
              <span class="host-name">{{ h.hostname || h.ip }}</span>
              <span class="host-ip mono">{{ h.ip }}</span>
              <div class="host-metrics">
                <span class="metric-tag" :class="cpuClass(h.metrics.cpu_usage)">
                  CPU {{ h.metrics.cpu_usage != null ? h.metrics.cpu_usage + '%' : '-' }}
                </span>
                <span class="metric-tag" :class="memClass(h.metrics.mem_usage)">
                  MEM {{ h.metrics.mem_usage != null ? h.metrics.mem_usage + '%' : '-' }}
                </span>
                <span class="metric-tag" :class="diskClass(maxDisk(h))">
                  DSK {{ maxDisk(h) != null ? maxDisk(h) + '%' : '-' }}
                </span>
              </div>
            </div>
          </div>
          <div v-else>
            <div class="service-grid">
              <div v-for="s in services" :key="s.name" class="svc-chip" :class="s.error_count > 0 ? 'has-error' : 'healthy'">
                <span class="svc-dot"></span>
                <span class="svc-chip-name">{{ s.name }}</span>
                <span v-if="s.error_count" class="svc-cnt">{{ s.error_count }}</span>
              </div>
            </div>
          </div>
        </div>

      </div>
    </template>
  </div>
</template>

<script>
export default { name: 'Dashboard' }
</script>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api/index.js'

const loading      = ref(true)
const services     = ref([])
const errorMetrics = ref([])
const totalErrors  = ref(0)
const hosts        = ref([])
const hostError    = ref(false)

const maxCount = computed(() => Math.max(...errorMetrics.value.map(e => e.count), 1))
const barWidth = (n) => Math.round(n / maxCount.value * 100)

// ── 主机汇总指标 ────────────────────────────────────────────────────────
const hostStats = computed(() => {
  const total    = hosts.value.length
  const online   = hosts.value.filter(h => h.state === 'up').length
  const cpuWarn  = hosts.value.filter(h => (h.metrics?.cpu_usage ?? 0) > 70).length
  const memWarn  = hosts.value.filter(h => (h.metrics?.mem_usage ?? 0) > 80).length
  const diskWarn = hosts.value.filter(h => (maxDisk(h) ?? 0) > 80).length
  return [
    { label: '主机总数',   value: total,   color: 'var(--accent)'   },
    { label: '在线',       value: online,  color: 'var(--success)'  },
    { label: 'CPU > 70%',  value: cpuWarn, color: cpuWarn  ? 'var(--warning)' : 'var(--text-secondary)' },
    { label: '内存 > 80%', value: memWarn, color: memWarn  ? 'var(--warning)' : 'var(--text-secondary)' },
    { label: '磁盘 > 80%', value: diskWarn,color: diskWarn ? 'var(--error)'   : 'var(--text-secondary)' },
  ]
})

// ── 日志汇总指标 ────────────────────────────────────────────────────────
const logStats = computed(() => [
  { label: '涉及服务数',  value: services.value.length,                                         color: 'var(--info)'     },
  { label: '健康服务数',  value: services.value.filter(s => !s.error_count).length,              color: 'var(--success)'  },
  { label: '错误总数',    value: totalErrors.value.toLocaleString(),                             color: 'var(--error)'    },
  { label: '异常服务数',  value: services.value.filter(s => s.error_count > 0).length,           color: 'var(--warning)'  },
])

function cpuClass(v)  { if (v == null) return ''; return v > 90 ? 'crit' : v > 70 ? 'warn' : 'ok' }
function memClass(v)  { if (v == null) return ''; return v > 90 ? 'crit' : v > 80 ? 'warn' : 'ok' }
function diskClass(v) { if (v == null) return ''; return v > 90 ? 'crit' : v > 80 ? 'warn' : 'ok' }
// 取主机所有分区中使用率最高的
function maxDisk(h) {
  const parts = h.partitions ?? []
  if (!parts.length) return null
  return Math.max(...parts.map(p => p.usage_pct ?? 0))
}

// ── 主机列表排序 ─────────────────────────────────────────────────────────
const sortKey = ref('state')   // 默认：状态（离线排前面）
const sortAsc = ref(true)
const sortCols = [
  { key: 'state',     label: '状态' },
  { key: 'hostname',  label: '主机名' },
  { key: 'cpu',       label: 'CPU' },
  { key: 'mem',       label: 'MEM' },
  { key: 'disk',      label: '磁盘' },
]

function toggleSort(key) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = key === 'hostname' }
}

const sortedHosts = computed(() => {
  const list = [...hosts.value]
  const dir = sortAsc.value ? 1 : -1
  list.sort((a, b) => {
    switch (sortKey.value) {
      case 'state':    return dir * ((a.state === 'up' ? 0 : 1) - (b.state === 'up' ? 0 : 1))
      case 'hostname': return dir * (a.hostname || a.ip).localeCompare(b.hostname || b.ip)
      case 'cpu':      return dir * ((a.metrics?.cpu_usage  ?? -1) - (b.metrics?.cpu_usage  ?? -1))
      case 'mem':      return dir * ((a.metrics?.mem_usage  ?? -1) - (b.metrics?.mem_usage  ?? -1))
      case 'disk':     return dir * ((maxDisk(a) ?? -1) - (maxDisk(b) ?? -1))
      default:         return 0
    }
  })
  return list
})

onMounted(async () => {
  // hosts 很快（<1s），先加载完就显示，不等 Loki
  const hostsRes = await api.getHosts().catch(() => null)
  if (hostsRes) hosts.value = hostsRes.data ?? []
  else hostError.value = true
  loading.value = false   // ← 立即显示，不再 loading

  // Loki 数据慢（~10s），后台继续加载，填入后 Vue 自动更新
  api.getServices().then(r => {
    services.value = r.data ?? []
  }).catch(() => {})

  api.getErrorMetrics(24).then(r => {
    errorMetrics.value = r.data ?? []
    totalErrors.value  = r.total_errors ?? 0
  }).catch(() => {})
})
</script>

<style scoped>
/* ── 整页 Grid 布局，撑满视口不滚动 ─────────────────────────── */
.dash {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 20px;
  overflow: hidden;
}
.loading-full {
  flex: 1;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; color: var(--text-muted); font-size: 13px;
}

/* ── 头部 ──────────────────────────────────────────────────── */
.dash-header { display: flex; align-items: baseline; gap: 10px; }
.dash-header h1 { font-size: 18px; font-weight: 600; color: var(--text-primary); }
.dash-header .subtitle { color: var(--text-muted); font-size: 12px; }

/* ── 统计区：主机 + 日志 左右并排 ──────────────────────────── */
.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  flex-shrink: 0;
}
.stats-panel { min-width: 0; }

/* Section labels */
.section-label {
  display: flex; align-items: center; gap: 7px;
  font-size: 11px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: .07em;
  margin-bottom: 8px;
}
.section-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.section-dot.prom { background: #e85d0f; }
.section-dot.loki { background: var(--warning); }
.section-link { margin-left: auto; font-size: 11px; color: var(--accent); text-decoration: none; text-transform: none; letter-spacing: 0; }
.section-link:hover { text-decoration: underline; }

/* Inline warning */
.inline-warn {
  display: flex; align-items: center; gap: 7px;
  padding: 7px 10px;
  background: rgba(210,153,34,.08); border: 1px solid rgba(210,153,34,.25);
  border-radius: var(--radius); color: var(--warning); font-size: 12px;
}

/* Stat cards */
.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px,1fr)); gap: 8px; }
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-top: 2px solid var(--card-accent, var(--accent));
  border-radius: var(--radius-card);
  padding: 12px 14px 10px;
  position: relative; overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: box-shadow .15s;
}
.stat-card:hover { box-shadow: var(--shadow-accent); }
.stat-value { font-size: 24px; font-weight: 600; line-height: 1; letter-spacing: -.02em; }
.stat-label { color: var(--text-muted); font-size: 10px; margin-top: 4px; text-transform: uppercase; letter-spacing: .06em; }
.stat-bar {
  position: absolute; bottom: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--card-accent, var(--accent)) 0%, transparent 100%);
  opacity: .3;
}

/* ── 下方面板（撑满剩余高度）──────────────────────────────── */
.lower-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 14px;
  min-height: 0;
}
.panel-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.panel-card .error-list,
.panel-card .host-list,
.panel-card > div:last-child {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

/* Error list */
.error-list { display: flex; flex-direction: column; }
.error-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
.error-row:last-child { border-bottom: none; }
.rank { width: 20px; text-align: center; font-size: 11px; font-weight: 600; font-family: 'JetBrains Mono', monospace; color: var(--text-muted); }
.rank-top { color: var(--warning); }
.svc-name { flex: 1; font-size: 12px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-wrap { width: 80px; height: 3px; background: var(--bg-surface); border-radius: 2px; overflow: hidden; flex-shrink: 0; }
.bar { height: 100%; background: var(--error); border-radius: 2px; transition: width .4s ease; opacity: .8; }

/* Host list */
.host-list { display: flex; flex-direction: column; }
.host-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0; border-bottom: 1px solid var(--border-light);
  font-size: 12px; flex-shrink: 0;
}
.host-row:last-child { border-bottom: none; }
.host-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.host-dot.ok  { background: var(--success); }
.host-dot.err { background: var(--error); }
.host-name { width: 110px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.host-ip   { width: 90px; color: var(--text-muted); font-size: 11px; }
.host-metrics { display: flex; gap: 5px; margin-left: auto; }
.metric-tag { font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 500; font-family: 'JetBrains Mono', monospace; }
.metric-tag.ok   { background: rgba(63,185,80,.1);  color: var(--success); }
.metric-tag.warn { background: rgba(210,153,34,.12); color: var(--warning); }
.metric-tag.crit { background: rgba(248,81,73,.12);  color: var(--error);   }

/* Service chips fallback */
.service-grid { display: flex; flex-wrap: wrap; gap: 6px; padding: 4px 0; }
.svc-chip { display: flex; align-items: center; gap: 5px; padding: 3px 9px; border-radius: 3px; font-size: 12px; border: 1px solid; }
.svc-chip.healthy   { border-color: var(--border); color: var(--text-secondary); }
.svc-chip.has-error { border-color: rgba(248,81,73,.25); background: rgba(248,81,73,.06); color: var(--error); }
.svc-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.svc-chip-name { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.svc-cnt { font-size: 11px; font-weight: 700; font-family: 'JetBrains Mono', monospace; }

/* 排序按钮 */
.sort-btns { display: flex; gap: 4px; margin-left: auto; }
.sort-btn {
  display: flex; align-items: center; gap: 3px;
  padding: 2px 7px; font-size: 11px; border-radius: 3px;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); cursor: pointer;
  font-family: inherit; transition: all .12s;
}
.sort-btn:hover { color: var(--text-primary); border-color: var(--border-accent); }
.sort-btn.active { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }
.sort-arrow { font-size: 10px; opacity: .7; }

@media (max-width: 900px) {
  .stats-row  { grid-template-columns: 1fr; }
  .lower-grid { grid-template-columns: 1fr; flex: none; }
  .dash { overflow-y: auto; }
}
</style>
