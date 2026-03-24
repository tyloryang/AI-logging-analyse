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

        <!-- 综合不健康主机 Top 10 -->
        <div class="card panel-card">
          <div class="card-header">
            <h3>综合不健康主机 Top 10</h3>
            <span class="card-header-hint">多维阈值综合评分</span>
          </div>
          <div class="error-list">
            <div v-if="hostError" class="empty-state" style="padding:24px">
              <span>Prometheus 未连接</span>
            </div>
            <div v-else-if="!unhealthyHosts.length" class="empty-state" style="padding:24px">
              <span style="color:var(--success)">✓ 所有主机运行正常</span>
            </div>
            <div v-for="(item, i) in unhealthyHosts" :key="item.instance" class="error-row unhealthy-row">
              <span class="rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
              <span class="svc-name">{{ item.hostname || item.ip }}</span>
              <div class="unhealthy-tags">
                <span v-for="t in item.tags" :key="t.label" class="unhealthy-tag" :class="t.level">
                  {{ t.label }}
                </span>
              </div>
              <span class="badge" :class="item.score >= 4 ? 'badge-error' : item.score >= 2 ? 'badge-warn' : 'badge-info'">
                {{ item.score }}分
              </span>
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
              <span class="host-state-badge" :class="h.state === 'up' ? 'ok' : 'err'">
                {{ h.state === 'up' ? '在线' : '离线' }}
              </span>
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
                <span class="metric-tag" :class="tcpClass(h.metrics.tcp_estab)">
                  TCP {{ h.metrics.tcp_estab != null ? h.metrics.tcp_estab : '-' }}
                </span>
                <span class="metric-tag" :class="loadClass(h.metrics.load5)">
                  LD {{ h.metrics.load5 != null ? h.metrics.load5.toFixed(2) : '-' }}
                </span>
                <span v-if="fmtIO(h.metrics)" class="metric-tag ok">
                  IO {{ fmtIO(h.metrics) }}
                </span>
                <span v-if="fmtNet(h.metrics)" class="metric-tag ok">
                  NET {{ fmtNet(h.metrics) }}
                </span>
                <span v-if="fmtUptime(h.metrics.uptime_seconds)" class="metric-tag ok">
                  UP {{ fmtUptime(h.metrics.uptime_seconds) }}
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
  const offline  = total - online
  const cpuWarn  = hosts.value.filter(h => (h.metrics?.cpu_usage ?? 0) > 70).length
  const memWarn  = hosts.value.filter(h => (h.metrics?.mem_usage ?? 0) > 80).length
  const diskWarn = hosts.value.filter(h => (maxDisk(h) ?? 0) > 80).length
  const tcpWarn  = hosts.value.filter(h => (h.metrics?.tcp_estab ?? 0) > 5000).length
  return [
    { label: '主机总数',      value: total,    color: 'var(--accent)'   },
    { label: '在线',          value: online,   color: 'var(--success)'  },
    { label: '离线',          value: offline,  color: offline  ? 'var(--error)'   : 'var(--text-secondary)' },
    { label: 'CPU > 70%',     value: cpuWarn,  color: cpuWarn  ? 'var(--warning)' : 'var(--text-secondary)' },
    { label: '内存 > 80%',    value: memWarn,  color: memWarn  ? 'var(--warning)' : 'var(--text-secondary)' },
    { label: '磁盘 > 80%',    value: diskWarn, color: diskWarn ? 'var(--error)'   : 'var(--text-secondary)' },
    { label: 'TCP > 5000',    value: tcpWarn,  color: tcpWarn  ? 'var(--warning)' : 'var(--text-secondary)' },
  ]
})

// ── 日志汇总指标 ────────────────────────────────────────────────────────
const logStats = computed(() => [
  { label: '涉及服务数',  value: services.value.length,                                         color: 'var(--info)'     },
  { label: '健康服务数',  value: services.value.filter(s => !s.error_count).length,              color: 'var(--success)'  },
  { label: '错误总数',    value: totalErrors.value.toLocaleString(),                             color: 'var(--error)'    },
  { label: '异常服务数',  value: services.value.filter(s => s.error_count > 0).length,           color: 'var(--warning)'  },
])

function cpuClass(v)   { if (v == null) return ''; return v > 90 ? 'crit' : v > 70 ? 'warn' : 'ok' }
function memClass(v)   { if (v == null) return ''; return v > 90 ? 'crit' : v > 80 ? 'warn' : 'ok' }
function diskClass(v)  { if (v == null) return ''; return v > 90 ? 'crit' : v > 80 ? 'warn' : 'ok' }
function tcpClass(v)   { if (v == null) return ''; return v > 10000 ? 'crit' : v > 5000 ? 'warn' : 'ok' }
function loadClass(v)  { if (v == null) return ''; return v > 8 ? 'crit' : v > 4 ? 'warn' : 'ok' }
// 取主机所有分区中使用率最高的
function maxDisk(h) {
  const parts = h.partitions ?? []
  if (!parts.length) return null
  return Math.max(...parts.map(p => p.usage_pct ?? 0))
}
function fmtIO(m) {
  if (m.disk_read_mbps == null) return null
  return `${m.disk_read_mbps}/${m.disk_write_mbps}`
}
function fmtNet(m) {
  if (m.net_recv_mbps == null) return null
  return `${m.net_recv_mbps}/${m.net_send_mbps}`
}
function fmtUptime(sec) {
  if (sec == null) return null
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  return d > 0 ? `${d}天${h}时` : `${h}时`
}

// ── 综合不健康主机评分 ───────────────────────────────────────────────────
// 规则：每违反一项阈值加分；critical=2分，warning=1分；离线直接3分
const unhealthyHosts = computed(() => {
  const scored = hosts.value.map(h => {
    const m = h.metrics ?? {}
    const tags = []
    let score = 0

    if (h.state !== 'up') {
      tags.push({ label: '离线', level: 'crit' })
      score += 3
    } else {
      const cpu  = m.cpu_usage  ?? 0
      const mem  = m.mem_usage  ?? 0
      const disk = maxDisk(h)   ?? 0
      const tcp  = m.tcp_estab  ?? 0
      const load = m.load5      ?? 0
      const cores = h.cpu_cores ?? 4

      if (cpu > 90)        { tags.push({ label: `CPU ${cpu}%`,   level: 'crit' }); score += 2 }
      else if (cpu > 70)   { tags.push({ label: `CPU ${cpu}%`,   level: 'warn' }); score += 1 }

      if (mem > 90)        { tags.push({ label: `内存 ${mem}%`,  level: 'crit' }); score += 2 }
      else if (mem > 80)   { tags.push({ label: `内存 ${mem}%`,  level: 'warn' }); score += 1 }

      if (disk > 90)       { tags.push({ label: `磁盘 ${disk}%`, level: 'crit' }); score += 2 }
      else if (disk > 80)  { tags.push({ label: `磁盘 ${disk}%`, level: 'warn' }); score += 1 }

      if (tcp > 10000)     { tags.push({ label: `TCP ${tcp}`,    level: 'crit' }); score += 2 }
      else if (tcp > 5000) { tags.push({ label: `TCP ${tcp}`,    level: 'warn' }); score += 1 }

      const loadWarn = cores, loadCrit = cores * 2
      if (load > loadCrit)      { tags.push({ label: `负载 ${load.toFixed(1)}`, level: 'crit' }); score += 2 }
      else if (load > loadWarn) { tags.push({ label: `负载 ${load.toFixed(1)}`, level: 'warn' }); score += 1 }
    }

    return { ...h, score, tags }
  })
  return scored
    .filter(h => h.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 10)
})

// ── 主机列表排序 ─────────────────────────────────────────────────────────
const sortKey = ref('state')   // 默认：状态（离线排前面）
const sortAsc = ref(true)
const sortCols = [
  { key: 'state',     label: '状态' },
  { key: 'hostname',  label: '主机名' },
  { key: 'cpu',       label: 'CPU' },
  { key: 'mem',       label: 'MEM' },
  { key: 'disk',      label: '磁盘' },
  { key: 'tcp',       label: 'TCP' },
  { key: 'load',      label: '负载' },
  { key: 'uptime',    label: '运行时长' },
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
      case 'tcp':      return dir * ((a.metrics?.tcp_estab ?? -1) - (b.metrics?.tcp_estab ?? -1))
      case 'load':     return dir * ((a.metrics?.load5 ?? -1) - (b.metrics?.load5 ?? -1))
      case 'uptime':   return dir * ((a.metrics?.uptime_seconds ?? -1) - (b.metrics?.uptime_seconds ?? -1))
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
.error-row { display: flex; align-items: center; gap: 8px; padding: 7px 0; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
.error-row:last-child { border-bottom: none; }
.rank { width: 18px; text-align: center; font-size: 11px; font-weight: 600; font-family: 'JetBrains Mono', monospace; color: var(--text-muted); flex-shrink: 0; }
.rank-top { color: var(--warning); }
.svc-name { width: 90px; flex-shrink: 0; font-size: 12px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-wrap { width: 80px; height: 3px; background: var(--bg-surface); border-radius: 2px; overflow: hidden; flex-shrink: 0; }
.bar { height: 100%; background: var(--error); border-radius: 2px; transition: width .4s ease; opacity: .8; }
/* 综合不健康 Top10 */
.card-header-hint { font-size: 11px; color: var(--text-muted); margin-left: 6px; }
.unhealthy-row .svc-name { width: 80px; }
.unhealthy-tags { flex: 1; display: flex; flex-wrap: wrap; gap: 3px; min-width: 0; }
.unhealthy-tag {
  font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: 500;
  font-family: 'JetBrains Mono', monospace; white-space: nowrap;
}
.unhealthy-tag.warn { background: rgba(210,153,34,.12); color: var(--warning); }
.unhealthy-tag.crit { background: rgba(248,81,73,.12);  color: var(--error);   }
.badge { font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 600; font-family: 'JetBrains Mono', monospace; flex-shrink: 0; }
.badge-error { background: rgba(248,81,73,.12); color: var(--error); }
.badge-warn  { background: rgba(210,153,34,.12); color: var(--warning); }
.badge-info  { background: rgba(82,130,255,.12); color: var(--accent); }

/* Host list */
.host-list { display: flex; flex-direction: column; }
.host-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 7px 0; border-bottom: 1px solid var(--border-light);
  font-size: 12px; flex-shrink: 0; flex-wrap: wrap;
}
.host-row:last-child { border-bottom: none; }
/* 状态徽章（替代原小圆点） */
.host-state-badge {
  flex-shrink: 0;
  font-size: 10px; font-weight: 600; font-family: 'JetBrains Mono', monospace;
  padding: 1px 5px; border-radius: 3px; letter-spacing: .02em;
}
.host-state-badge.ok  { background: rgba(63,185,80,.12);  color: var(--success); }
.host-state-badge.err { background: rgba(248,81,73,.12);  color: var(--error);   }
.host-name { flex: 1; min-width: 80px; max-width: 140px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.host-ip   { width: 100px; flex-shrink: 0; color: var(--text-muted); font-size: 11px; }
.host-metrics { display: flex; gap: 4px; flex: 2; flex-wrap: wrap; }
.metric-tag { font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: 500; font-family: 'JetBrains Mono', monospace; white-space: nowrap; }
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
