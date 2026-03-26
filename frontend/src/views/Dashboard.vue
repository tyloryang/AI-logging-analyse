<template>
  <div class="dash">

    <!-- ── 头部 ──────────────────────────────────────────────── -->
    <div class="dash-header">
      <div class="dash-title">
        <h1>仪表盘</h1>
        <span class="subtitle">系统总览 · 最近 24 小时</span>
      </div>
      <button class="btn-refresh" @click="reload" :disabled="loading" title="刷新数据">
        <span v-if="loading" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
        <span v-else>🔄</span>
      </button>
    </div>

    <div v-if="loading && !hosts.length" class="loading-full"><div class="spinner"></div><p>加载中...</p></div>

    <template v-else>

      <!-- ── 顶部 Stat 卡片区 ───────────────────────────────── -->
      <div class="stats-row">
        <!-- 主机概览 -->
        <div class="stats-panel">
          <div class="section-label">
            <span class="section-dot prom"></span>主机概览
            <RouterLink to="/hosts" class="section-link">进入 CMDB →</RouterLink>
          </div>
          <div v-if="hostError" class="inline-warn">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            Prometheus 未连接，主机数据不可用
          </div>
          <div class="stat-grid" v-else>
            <div
              v-for="s in hostStats" :key="s.label"
              class="stat-card"
              :class="{ 'stat-card-alert': s.alert }"
              :style="{ '--card-accent': s.color }"
              @click="s.to && router.push(s.to)"
              :style2="s.to ? 'cursor:pointer' : ''"
            >
              <div class="stat-value mono" :style="{ color: s.color }">{{ s.value }}</div>
              <div class="stat-label">{{ s.label }}</div>
              <div class="stat-bar"></div>
              <span v-if="s.alert && s.to" class="stat-link-hint">点击查看 →</span>
            </div>
          </div>
        </div>

        <!-- 日志告警概览 -->
        <div class="stats-panel">
          <div class="section-label">
            <span class="section-dot loki"></span>日志告警概览
            <RouterLink to="/logs" class="section-link">进入日志分析 →</RouterLink>
          </div>
          <div class="stat-grid">
            <div
              v-for="s in logStats" :key="s.label"
              class="stat-card"
              :class="{ 'stat-card-alert': s.alert }"
              :style="{ '--card-accent': s.color }"
              @click="s.to && router.push(s.to)"
            >
              <div class="stat-value mono" :style="{ color: s.color }">{{ s.value }}</div>
              <div class="stat-label">{{ s.label }}</div>
              <div class="stat-bar"></div>
              <span v-if="s.alert && s.to" class="stat-link-hint">点击查看 →</span>
            </div>
          </div>
        </div>
      </div>

      <!-- ── 下方三栏面板 ────────────────────────────────────── -->
      <div class="lower-grid">

        <!-- 主机告警 -->
        <div class="card panel-card">
          <div class="card-header">
            <h3>主机告警</h3>
            <span class="card-header-hint">综合评分 Top 10</span>
          </div>
          <div class="alert-list">
            <div v-if="hostError" class="empty-state" style="padding:20px">
              <span style="font-size:20px">⚠️</span><p style="font-size:12px">Prometheus 未连接</p>
            </div>
            <div v-else-if="!unhealthyHosts.length" class="empty-state" style="padding:20px">
              <span style="font-size:20px;color:var(--success)">✓</span>
              <p style="font-size:12px;color:var(--success)">所有主机运行正常</p>
            </div>
            <div
              v-for="(item, i) in unhealthyHosts" :key="item.instance"
              class="alert-row"
              :class="item.score >= 4 ? 'alert-crit' : 'alert-warn'"
              @click="router.push('/hosts')"
            >
              <span class="alert-rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
              <div class="alert-main">
                <div class="alert-hostname">{{ item.hostname || item.ip }}</div>
                <div class="alert-tags">
                  <span v-for="t in item.tags" :key="t.label" class="atag" :class="t.level">{{ t.label }}</span>
                </div>
              </div>
              <span class="alert-score" :class="item.score >= 4 ? 'score-crit' : 'score-warn'">{{ item.score }}分</span>
            </div>
          </div>
        </div>

        <!-- 日志服务告警 -->
        <div class="card panel-card">
          <div class="card-header">
            <h3>日志服务告警</h3>
            <span class="card-header-hint">24h 错误数排名</span>
          </div>
          <div class="alert-list">
            <div v-if="!services.length" class="empty-state" style="padding:20px">
              <div class="spinner" style="width:16px;height:16px;border-width:2px"></div>
              <p style="font-size:12px">加载日志数据...</p>
            </div>
            <div v-else-if="!alertServices.length" class="empty-state" style="padding:20px">
              <span style="font-size:20px;color:var(--success)">✓</span>
              <p style="font-size:12px;color:var(--success)">无服务错误日志</p>
            </div>
            <div
              v-for="(svc, i) in alertServices" :key="svc.name"
              class="alert-row svc-alert-row"
              @click="router.push({ path: '/logs', query: { service: svc.name } })"
            >
              <span class="alert-rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
              <div class="alert-main">
                <div class="alert-hostname">{{ svc.name }}</div>
                <div class="svc-bar-wrap">
                  <div class="svc-bar" :style="{ width: svcBarW(svc.error_count) + '%' }"></div>
                </div>
              </div>
              <span class="alert-score score-crit">{{ svc.error_count.toLocaleString() }}</span>
            </div>
            <!-- 正常服务 -->
            <div v-if="healthyServices.length" class="svc-healthy-row">
              <span class="dot-ok"></span>
              <span>{{ healthyServices.length }} 个服务正常</span>
              <span v-for="s in healthyServices.slice(0,4)" :key="s.name" class="svc-ok-chip" @click.stop="router.push({ path:'/logs', query:{service:s.name} })">{{ s.name }}</span>
              <span v-if="healthyServices.length > 4" class="svc-more">+{{ healthyServices.length - 4 }}</span>
            </div>
          </div>
        </div>

        <!-- 主机状态 -->
        <div class="card panel-card">
          <div class="card-header">
            <h3>主机状态</h3>
            <div v-if="groups.length" class="host-group-filter">
              <select v-model="groupFilter" class="host-group-select">
                <option value="">全部分组</option>
                <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
              </select>
            </div>
          </div>
          <div v-if="hosts.length" class="host-list">
            <!-- 表头 -->
            <div class="host-row host-list-header">
              <span class="host-state-badge col-hd" @click="toggleSort('state')">状态<em>{{ sortKey==='state'?(sortAsc?' ↑':' ↓'):'' }}</em></span>
              <span class="host-name col-hd" @click="toggleSort('hostname')">主机名<em>{{ sortKey==='hostname'?(sortAsc?' ↑':' ↓'):'' }}</em></span>
              <span class="host-ip col-hd">IP</span>
              <span v-if="groups.length" class="host-group col-hd" @click="toggleSort('group')">分组<em>{{ sortKey==='group'?(sortAsc?' ↑':' ↓'):'' }}</em></span>
              <div class="host-metrics">
                <span class="metric-tag col-hd" @click="toggleSort('cpu')">CPU<em>{{ sortKey==='cpu'?(sortAsc?'↑':'↓'):'' }}</em></span>
                <span class="metric-tag col-hd" @click="toggleSort('mem')">MEM<em>{{ sortKey==='mem'?(sortAsc?'↑':'↓'):'' }}</em></span>
                <span class="metric-tag col-hd" @click="toggleSort('disk')">磁盘<em>{{ sortKey==='disk'?(sortAsc?'↑':'↓'):'' }}</em></span>
                <span class="metric-tag col-hd" @click="toggleSort('tcp')">TCP<em>{{ sortKey==='tcp'?(sortAsc?'↑':'↓'):'' }}</em></span>
                <span class="metric-tag col-hd" @click="toggleSort('load')">负载<em>{{ sortKey==='load'?(sortAsc?'↑':'↓'):'' }}</em></span>
                <span class="metric-tag col-hd" @click="toggleSort('io')">IO<em>{{ sortKey==='io'?(sortAsc?'↑':'↓'):'' }}</em></span>
                <span class="metric-tag col-hd" @click="toggleSort('net')">NET<em>{{ sortKey==='net'?(sortAsc?'↑':'↓'):'' }}</em></span>
                <span class="metric-tag col-hd" @click="toggleSort('uptime')">运行<em>{{ sortKey==='uptime'?(sortAsc?'↑':'↓'):'' }}</em></span>
              </div>
            </div>
            <!-- 数据行 -->
            <div
              v-for="h in sortedHosts" :key="h.instance"
              class="host-row"
              :class="hostRowClass(h)"
              @click="router.push('/hosts')"
            >
              <span class="host-state-badge" :class="h.state==='up'?'ok':'err'">
                {{ h.state==='up'?'在线':'离线' }}
              </span>
              <span class="host-name">{{ h.hostname || h.ip }}</span>
              <span class="host-ip mono">{{ h.ip }}</span>
              <span v-if="groups.length" class="host-group">{{ groupMap[h.group] || '-' }}</span>
              <div class="host-metrics">
                <span class="metric-tag" :class="cpuClass(h.metrics.cpu_usage)">CPU {{ h.metrics.cpu_usage!=null?h.metrics.cpu_usage+'%':'-' }}</span>
                <span class="metric-tag" :class="memClass(h.metrics.mem_usage)">MEM {{ h.metrics.mem_usage!=null?h.metrics.mem_usage+'%':'-' }}</span>
                <span class="metric-tag" :class="diskClass(maxDisk(h))">DSK {{ maxDisk(h)!=null?maxDisk(h)+'%':'-' }}</span>
                <span class="metric-tag" :class="tcpClass(h.metrics.tcp_estab)">TCP {{ h.metrics.tcp_estab!=null?h.metrics.tcp_estab:'-' }}</span>
                <span class="metric-tag" :class="loadClass(h.metrics.load5)">LD {{ h.metrics.load5!=null?h.metrics.load5.toFixed(2):'-' }}</span>
                <span v-if="fmtIO(h.metrics)" class="metric-tag ok">IO {{ fmtIO(h.metrics) }}</span>
                <span v-if="fmtNet(h.metrics)" class="metric-tag ok">NET {{ fmtNet(h.metrics) }}</span>
                <span v-if="fmtUptime(h.metrics.uptime_seconds)" class="metric-tag ok">UP {{ fmtUptime(h.metrics.uptime_seconds) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-state" style="padding:24px">
            <span style="font-size:20px">🖥️</span>
            <p style="font-size:12px">{{ hostError ? 'Prometheus 未连接' : '暂无主机数据' }}</p>
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
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router    = useRouter()
const loading   = ref(true)
const services  = ref([])
const totalErrors = ref(0)
const hosts     = ref([])
const hostError = ref(false)
const groups    = ref([])
const groupFilter = ref('')

const groupMap = computed(() => Object.fromEntries((groups.value || []).map(g => [g.id, g.name])))

// ── 主机 stat 卡片 ───────────────────────────────────────────
const hostStats = computed(() => {
  const total    = hosts.value.length
  const online   = hosts.value.filter(h => h.state === 'up').length
  const offline  = total - online
  const cpuWarn  = hosts.value.filter(h => (h.metrics?.cpu_usage ?? 0) > 70).length
  const memWarn  = hosts.value.filter(h => (h.metrics?.mem_usage ?? 0) > 80).length
  const diskWarn = hosts.value.filter(h => (maxDisk(h) ?? 0) > 80).length
  const tcpWarn  = hosts.value.filter(h => (h.metrics?.tcp_estab ?? 0) > 5000).length
  return [
    { label: '主机总数',   value: total,    color: 'var(--accent)',   alert: false, to: '/hosts' },
    { label: '在线',       value: online,   color: 'var(--success)',  alert: false, to: '/hosts' },
    { label: '离线',       value: offline,  color: offline  ? 'var(--error)'   : 'var(--text-secondary)', alert: offline  > 0, to: '/hosts' },
    { label: 'CPU > 70%',  value: cpuWarn,  color: cpuWarn  ? 'var(--warning)' : 'var(--text-secondary)', alert: cpuWarn  > 0, to: '/hosts' },
    { label: '内存 > 80%', value: memWarn,  color: memWarn  ? 'var(--warning)' : 'var(--text-secondary)', alert: memWarn  > 0, to: '/hosts' },
    { label: '磁盘 > 80%', value: diskWarn, color: diskWarn ? 'var(--error)'   : 'var(--text-secondary)', alert: diskWarn > 0, to: '/hosts' },
    { label: 'TCP > 5000', value: tcpWarn,  color: tcpWarn  ? 'var(--warning)' : 'var(--text-secondary)', alert: tcpWarn  > 0, to: '/hosts' },
  ]
})

// ── 日志 stat 卡片 ───────────────────────────────────────────
const logStats = computed(() => {
  const total   = services.value.length
  const healthy = services.value.filter(s => !s.error_count).length
  const errSvcs = services.value.filter(s => s.error_count > 0).length
  return [
    { label: '服务总数',   value: total,                        color: 'var(--info)',    alert: false,       to: '/logs' },
    { label: '正常服务',   value: healthy,                      color: 'var(--success)', alert: false,       to: '/logs' },
    { label: '异常服务',   value: errSvcs,                      color: errSvcs  ? 'var(--error)'   : 'var(--text-secondary)', alert: errSvcs  > 0, to: '/logs' },
    { label: '错误总数',   value: totalErrors.value.toLocaleString(), color: totalErrors.value ? 'var(--error)' : 'var(--text-secondary)', alert: totalErrors.value > 0, to: '/logs' },
  ]
})

// ── 告警服务列表 ─────────────────────────────────────────────
const alertServices  = computed(() => services.value.filter(s => s.error_count > 0).sort((a, b) => b.error_count - a.error_count))
const healthyServices = computed(() => services.value.filter(s => !s.error_count))
const maxSvcErrors   = computed(() => Math.max(...alertServices.value.map(s => s.error_count), 1))
const svcBarW = (n) => Math.round(n / maxSvcErrors.value * 100)

// ── 综合不健康主机评分 ────────────────────────────────────────
function maxDisk(h) {
  const parts = h.partitions ?? []
  return parts.length ? Math.max(...parts.map(p => p.usage_pct ?? 0)) : null
}
function cpuClass(v)  { if (v == null) return ''; return v > 90 ? 'crit' : v > 70 ? 'warn' : 'ok' }
function memClass(v)  { if (v == null) return ''; return v > 90 ? 'crit' : v > 80 ? 'warn' : 'ok' }
function diskClass(v) { if (v == null) return ''; return v > 90 ? 'crit' : v > 80 ? 'warn' : 'ok' }
function tcpClass(v)  { if (v == null) return ''; return v > 10000 ? 'crit' : v > 5000 ? 'warn' : 'ok' }
function loadClass(v) { if (v == null) return ''; return v > 8 ? 'crit' : v > 4 ? 'warn' : 'ok' }
function fmtIO(m)     { return m.disk_read_mbps != null ? `${m.disk_read_mbps}/${m.disk_write_mbps}` : null }
function fmtNet(m)    { return m.net_recv_mbps  != null ? `${m.net_recv_mbps}/${m.net_send_mbps}`   : null }
function fmtUptime(s) { if (s == null) return null; const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600); return d > 0 ? `${d}天${h}时` : `${h}时` }

function hostRowClass(h) {
  const m = h.metrics ?? {}
  if (h.state !== 'up') return 'row-offline'
  const cpu = m.cpu_usage ?? 0, mem = m.mem_usage ?? 0, disk = maxDisk(h) ?? 0
  if (cpu > 90 || mem > 90 || disk > 90) return 'row-crit'
  if (cpu > 70 || mem > 80 || disk > 80) return 'row-warn'
  return ''
}

const unhealthyHosts = computed(() => {
  return hosts.value.map(h => {
    const m = h.metrics ?? {}
    const tags = []
    let score = 0
    if (h.state !== 'up') {
      tags.push({ label: '离线', level: 'crit' }); score += 3
    } else {
      const cpu = m.cpu_usage ?? 0, mem = m.mem_usage ?? 0
      const disk = maxDisk(h) ?? 0, tcp = m.tcp_estab ?? 0
      const load = m.load5 ?? 0, cores = h.cpu_cores ?? 4
      if (cpu > 90)        { tags.push({ label: `CPU ${cpu}%`,   level: 'crit' }); score += 2 }
      else if (cpu > 70)   { tags.push({ label: `CPU ${cpu}%`,   level: 'warn' }); score += 1 }
      if (mem > 90)        { tags.push({ label: `内存 ${mem}%`,  level: 'crit' }); score += 2 }
      else if (mem > 80)   { tags.push({ label: `内存 ${mem}%`,  level: 'warn' }); score += 1 }
      if (disk > 90)       { tags.push({ label: `磁盘 ${disk}%`, level: 'crit' }); score += 2 }
      else if (disk > 80)  { tags.push({ label: `磁盘 ${disk}%`, level: 'warn' }); score += 1 }
      if (tcp > 10000)     { tags.push({ label: `TCP ${tcp}`,    level: 'crit' }); score += 2 }
      else if (tcp > 5000) { tags.push({ label: `TCP ${tcp}`,    level: 'warn' }); score += 1 }
      const lw = cores, lc = cores * 2
      if (load > lc)       { tags.push({ label: `负载 ${load.toFixed(1)}`, level: 'crit' }); score += 2 }
      else if (load > lw)  { tags.push({ label: `负载 ${load.toFixed(1)}`, level: 'warn' }); score += 1 }
    }
    return { ...h, score, tags }
  }).filter(h => h.score > 0).sort((a, b) => b.score - a.score).slice(0, 10)
})

// ── 排序 ────────────────────────────────────────────────────
const sortKey = ref('state')
const sortAsc = ref(true)
function toggleSort(key) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = key === 'hostname' }
}
const sortedHosts = computed(() => {
  const base = groupFilter.value ? hosts.value.filter(h => h.group === groupFilter.value) : [...hosts.value]
  const dir = sortAsc.value ? 1 : -1
  return base.slice().sort((a, b) => {
    switch (sortKey.value) {
      case 'state':    return dir * ((a.state==='up'?0:1) - (b.state==='up'?0:1))
      case 'hostname': return dir * (a.hostname||a.ip).localeCompare(b.hostname||b.ip)
      case 'group':    return dir * (groupMap.value[a.group]||'').localeCompare(groupMap.value[b.group]||'')
      case 'cpu':      return dir * ((a.metrics?.cpu_usage??-1)-(b.metrics?.cpu_usage??-1))
      case 'mem':      return dir * ((a.metrics?.mem_usage??-1)-(b.metrics?.mem_usage??-1))
      case 'disk':     return dir * ((maxDisk(a)??-1)-(maxDisk(b)??-1))
      case 'tcp':      return dir * ((a.metrics?.tcp_estab??-1)-(b.metrics?.tcp_estab??-1))
      case 'load':     return dir * ((a.metrics?.load5??-1)-(b.metrics?.load5??-1))
      case 'io':       return dir * (((a.metrics?.disk_read_mbps??0)+(a.metrics?.disk_write_mbps??0))-((b.metrics?.disk_read_mbps??0)+(b.metrics?.disk_write_mbps??0)))
      case 'net':      return dir * (((a.metrics?.net_recv_mbps??0)+(a.metrics?.net_send_mbps??0))-((b.metrics?.net_recv_mbps??0)+(b.metrics?.net_send_mbps??0)))
      case 'uptime':   return dir * ((a.metrics?.uptime_seconds??-1)-(b.metrics?.uptime_seconds??-1))
      default:         return 0
    }
  })
})

// ── 数据加载 ────────────────────────────────────────────────
async function reload() {
  loading.value = true
  const hostsRes = await api.getHosts().catch(() => null)
  if (hostsRes) { hosts.value = hostsRes.data ?? []; hostError.value = false }
  else hostError.value = true
  loading.value = false
}

onMounted(async () => {
  const hostsRes = await api.getHosts().catch(() => null)
  if (hostsRes) hosts.value = hostsRes.data ?? []
  else hostError.value = true
  loading.value = false

  api.listGroups().then(r => { groups.value = r.data ?? [] }).catch(() => {})
  api.getServices().then(r => { services.value = r.data ?? [] }).catch(() => {})
  api.getErrorMetrics(24).then(r => { totalErrors.value = r.total_errors ?? 0 }).catch(() => {})
})
</script>

<style scoped>
.dash {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  gap: 12px; padding: 14px 18px; overflow: hidden;
}
.loading-full {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; color: var(--text-muted); font-size: 13px;
}

/* 头部 */
.dash-header { display: flex; align-items: center; gap: 10px; }
.dash-title h1 { font-size: 18px; font-weight: 600; color: var(--text-primary); margin: 0; }
.dash-title .subtitle { color: var(--text-muted); font-size: 12px; margin-left: 8px; }
.btn-refresh {
  margin-left: auto; background: none; border: 1px solid var(--border);
  color: var(--text-muted); border-radius: 6px; padding: 4px 10px;
  cursor: pointer; font-size: 13px; transition: all .12s;
}
.btn-refresh:hover { color: var(--text-primary); border-color: var(--accent); }

/* 顶部 stat 区 */
.stats-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex-shrink: 0; }
.stats-panel { min-width: 0; }
.section-label {
  display: flex; align-items: center; gap: 7px;
  font-size: 11px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: .07em; margin-bottom: 8px;
}
.section-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.section-dot.prom { background: #e85d0f; }
.section-dot.loki { background: var(--warning); }
.section-link { margin-left: auto; font-size: 11px; color: var(--accent); text-decoration: none; text-transform: none; letter-spacing: 0; }
.section-link:hover { text-decoration: underline; }
.inline-warn {
  display: flex; align-items: center; gap: 7px; padding: 7px 10px;
  background: rgba(210,153,34,.08); border: 1px solid rgba(210,153,34,.25);
  border-radius: var(--radius); color: var(--warning); font-size: 12px;
}

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px,1fr)); gap: 7px; }
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-top: 2px solid var(--card-accent, var(--accent));
  border-radius: var(--radius-card);
  padding: 10px 12px 8px;
  position: relative; overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: box-shadow .15s, transform .12s;
  cursor: pointer;
}
.stat-card:hover { box-shadow: var(--shadow-accent); transform: translateY(-1px); }
.stat-card-alert {
  border-color: var(--card-accent, var(--accent));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--card-accent,var(--accent)) 30%, transparent);
}
.stat-value { font-size: 22px; font-weight: 700; line-height: 1; letter-spacing: -.02em; }
.stat-label { color: var(--text-muted); font-size: 10px; margin-top: 4px; text-transform: uppercase; letter-spacing: .06em; }
.stat-bar {
  position: absolute; bottom: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--card-accent,var(--accent)) 0%, transparent 100%); opacity: .35;
}
.stat-link-hint {
  position: absolute; bottom: 5px; right: 8px;
  font-size: 9px; color: var(--text-muted); letter-spacing: .03em;
}

/* 下方三栏 */
.lower-grid {
  flex: 1; display: grid;
  grid-template-columns: 260px 260px 1fr;
  gap: 12px; min-height: 0;
}
.panel-card { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }

/* 卡片头 */
.card-header {
  padding: 10px 14px 8px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px; flex-shrink: 0;
}
.card-header h3 { font-size: 13px; font-weight: 600; color: var(--text-primary); margin: 0; }
.card-header-hint { font-size: 11px; color: var(--text-muted); }
.host-group-filter { margin-left: auto; }
.host-group-select {
  height: 26px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--bg-card); color: var(--text-secondary);
  font-size: 11px; padding: 0 8px; outline: none; cursor: pointer;
}

/* 告警列表（主机/服务共用） */
.alert-list { flex: 1; overflow-y: auto; min-height: 0; }
.alert-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 8px 12px; border-bottom: 1px solid var(--border-light);
  cursor: pointer; transition: background .1s;
}
.alert-row:last-child { border-bottom: none; }
.alert-row:hover { background: var(--bg-hover); }
.alert-crit { border-left: 3px solid var(--error); }
.alert-warn { border-left: 3px solid var(--warning); }
.alert-rank {
  width: 16px; flex-shrink: 0; text-align: center;
  font-size: 11px; font-weight: 700; color: var(--text-muted);
  font-family: 'JetBrains Mono', monospace; margin-top: 2px;
}
.rank-top { color: var(--warning); }
.alert-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.alert-hostname { font-size: 12px; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.alert-tags { display: flex; flex-wrap: wrap; gap: 3px; }
.atag {
  font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: 500;
  font-family: 'JetBrains Mono', monospace; white-space: nowrap;
}
.atag.crit { background: rgba(248,81,73,.12);  color: var(--error); }
.atag.warn { background: rgba(210,153,34,.12); color: var(--warning); }
.alert-score {
  flex-shrink: 0; font-size: 11px; font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  padding: 1px 6px; border-radius: 4px; margin-top: 2px;
}
.score-crit { background: rgba(248,81,73,.12); color: var(--error); }
.score-warn { background: rgba(210,153,34,.12); color: var(--warning); }

/* 服务告警专用 */
.svc-alert-row { align-items: center; }
.svc-bar-wrap { width: 100%; height: 4px; background: rgba(255,255,255,.07); border-radius: 2px; overflow: hidden; margin-top: 4px; }
.svc-bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 2px; min-width: 2px; }
.svc-healthy-row {
  display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
  padding: 8px 12px; font-size: 11px; color: var(--text-muted);
  border-top: 1px solid var(--border);
}
.dot-ok { width: 6px; height: 6px; border-radius: 50%; background: var(--success); flex-shrink: 0; }
.svc-ok-chip {
  font-size: 10px; padding: 1px 7px; border-radius: 9999px;
  background: rgba(63,185,80,.1); color: var(--success);
  border: 1px solid rgba(63,185,80,.2); cursor: pointer;
}
.svc-ok-chip:hover { background: rgba(63,185,80,.2); }
.svc-more { font-size: 10px; color: var(--text-muted); }

/* 主机状态表 */
.host-list { display: flex; flex-direction: column; flex: 1; overflow-y: auto; min-height: 0; }
.host-row {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-bottom: 1px solid var(--border-light);
  font-size: 12px; flex-shrink: 0; cursor: pointer; transition: background .1s;
}
.host-row:last-child { border-bottom: none; }
.host-row:hover { background: var(--bg-hover); }
.host-list-header { border-bottom: 1px solid var(--border) !important; cursor: default !important; }
.host-list-header:hover { background: transparent !important; }
.row-crit { background: rgba(239,68,68,.05); }
.row-warn { background: rgba(234,179,8,.04); }
.row-offline { background: rgba(239,68,68,.08); }
.col-hd {
  color: var(--text-muted) !important; font-size: 10px !important;
  font-weight: 500; letter-spacing: .3px; cursor: pointer; user-select: none;
  background: transparent !important;
}
.col-hd:hover { color: var(--text-primary) !important; }
.col-hd em { font-style: normal; color: var(--accent); }
.host-state-badge {
  flex-shrink: 0; width: 34px; text-align: center;
  font-size: 10px; font-weight: 600; padding: 1px 4px; border-radius: 3px;
}
.host-state-badge.ok  { background: rgba(63,185,80,.12);  color: var(--success); }
.host-state-badge.err { background: rgba(248,81,73,.12);  color: var(--error); }
.host-name { flex: 1; min-width: 70px; max-width: 130px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.host-ip   { width: 100px; flex-shrink: 0; color: var(--text-muted); font-size: 11px; font-family: 'Consolas', monospace; }
.host-group { width: 80px; flex-shrink: 0; color: var(--accent-hover); font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.host-metrics { display: flex; gap: 3px; flex-wrap: nowrap; }
.metric-tag {
  font-size: 10px; padding: 1px 4px; border-radius: 3px;
  font-weight: 500; font-family: 'JetBrains Mono', monospace;
  white-space: nowrap; min-width: 52px; text-align: center;
}
.metric-tag.ok   { background: rgba(63,185,80,.1);   color: var(--success); }
.metric-tag.warn { background: rgba(210,153,34,.12);  color: var(--warning); }
.metric-tag.crit { background: rgba(248,81,73,.12);   color: var(--error); }

.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: var(--text-muted); }

@media (max-width: 1100px) {
  .lower-grid { grid-template-columns: 240px 240px 1fr; }
}
@media (max-width: 900px) {
  .stats-row  { grid-template-columns: 1fr; }
  .lower-grid { grid-template-columns: 1fr; flex: none; }
  .dash { overflow-y: auto; }
}
</style>
