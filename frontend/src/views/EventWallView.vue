<template>
  <div class="event-wall">
    <div class="page-header">
      <div class="header-left">
        <h1>事件墙</h1>
        <span class="subtitle">Prometheus 告警 + Loki 错误日志实时聚合</span>
      </div>
      <div class="header-right">
        <select v-model="filterSev" class="filter-select">
          <option value="">全部级别</option>
          <option value="critical">Critical</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <select v-model="filterSource" class="filter-select">
          <option value="">全部来源</option>
          <option value="prometheus">Prometheus</option>
          <option value="loki">Loki</option>
        </select>
        <select v-model="hours" class="filter-select">
          <option :value="1">最近 1h</option>
          <option :value="6">最近 6h</option>
          <option :value="24">最近 24h</option>
          <option :value="72">最近 3d</option>
        </select>
        <button class="btn-ghost" @click="fetchEvents" :disabled="loading">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
          刷新
        </button>
      </div>
    </div>

    <!-- Stats bar -->
    <div class="stats-bar">
      <div v-for="s in SEVERITIES" :key="s.key" class="stat-pill" :class="s.key">
        <span class="pill-dot"></span>
        <span>{{ s.label }}</span>
        <span class="pill-count">{{ statCount(s.key) }}</span>
      </div>
      <span class="stat-total">共 {{ events.length }} 条事件</span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-row"><div class="spinner"></div> 加载中…</div>

    <!-- Event list -->
    <div v-else class="event-list">
      <div v-if="!events.length" class="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" opacity=".3"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
        <p>当前没有事件</p>
      </div>
      <div v-for="ev in filteredEvents" :key="ev.id" class="event-card" :class="ev.severity" @click="activeEvent = ev">
        <div class="ev-left">
          <span class="sev-badge" :class="ev.severity">{{ SEV_LABEL[ev.severity] || ev.severity }}</span>
        </div>
        <div class="ev-body">
          <div class="ev-title">{{ ev.title }}</div>
          <div class="ev-msg">{{ ev.message }}</div>
          <div class="ev-meta">
            <span class="source-tag" :class="ev.source">{{ SOURCE_LABEL[ev.source] || ev.source }}</span>
            <span v-if="ev.service" class="service-tag">{{ ev.service }}</span>
            <span class="time-tag">{{ fmtTime(ev.time) }}</span>
          </div>
        </div>
        <div class="ev-status">
          <span class="status-dot" :class="ev.status === 'firing' ? 'firing' : 'active'"></span>
        </div>
      </div>
    </div>

    <!-- Detail drawer -->
    <div v-if="activeEvent" class="modal-overlay" @click.self="activeEvent = null">
      <div class="detail-panel">
        <div class="detail-header">
          <span class="sev-badge" :class="activeEvent.severity">{{ SEV_LABEL[activeEvent.severity] }}</span>
          <span class="detail-title">{{ activeEvent.title }}</span>
          <button class="close-btn" @click="activeEvent = null">✕</button>
        </div>
        <div class="detail-body">
          <div class="detail-section">
            <label>消息</label>
            <pre class="detail-pre">{{ activeEvent.message || '（无详情）' }}</pre>
          </div>
          <div class="detail-section">
            <label>来源</label>
            <p>{{ SOURCE_LABEL[activeEvent.source] }} · {{ activeEvent.service || activeEvent.instance || '—' }}</p>
          </div>
          <div class="detail-section">
            <label>时间</label>
            <p>{{ activeEvent.time }}</p>
          </div>
          <div v-if="activeEvent.labels && Object.keys(activeEvent.labels).length" class="detail-section">
            <label>标签</label>
            <div class="label-grid">
              <template v-for="(v, k) in activeEvent.labels" :key="k">
                <span class="label-key">{{ k }}</span>
                <span class="label-val">{{ v }}</span>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { api } from '../api/index.js'

const SEVERITIES = [
  { key: 'critical', label: 'Critical' },
  { key: 'error',    label: 'Error' },
  { key: 'warning',  label: 'Warning' },
  { key: 'info',     label: 'Info' },
]
const SEV_LABEL    = { critical: '严重', error: '错误', warning: '警告', info: '信息' }
const SOURCE_LABEL = { prometheus: 'Prometheus', loki: 'Loki' }

const events      = ref([])
const loading     = ref(false)
const filterSev   = ref('')
const filterSource = ref('')
const hours       = ref(24)
const activeEvent = ref(null)

const filteredEvents = computed(() => {
  let list = events.value
  if (filterSev.value)    list = list.filter(e => e.severity === filterSev.value)
  if (filterSource.value) list = list.filter(e => e.source   === filterSource.value)
  return list
})

function statCount(sev) {
  return events.value.filter(e => e.severity === sev).length
}

async function fetchEvents() {
  loading.value = true
  try {
    events.value = await api.listEvents({ hours: hours.value, limit: 300 })
  } catch { events.value = [] }
  finally { loading.value = false }
}

function fmtTime(ts) {
  if (!ts) return ''
  return ts.replace('T', ' ').replace('Z', '').slice(0, 16)
}

let _timer = null
watch(hours, fetchEvents)
onMounted(() => { fetchEvents(); _timer = setInterval(fetchEvents, 30000) })
onUnmounted(() => clearInterval(_timer))
</script>

<style scoped>
.event-wall {
  --eventwall-page-bg: #f6f8fb;
  --eventwall-surface: #ffffff;
  --eventwall-surface-soft: #f8fafc;
  --eventwall-border: #e5e7eb;
  --eventwall-border-strong: #d0d7de;
  --eventwall-text: #0f172a;
  --eventwall-text-muted: #64748b;
  --eventwall-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: var(--eventwall-page-bg);
  color: var(--eventwall-text);
}
.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 12px; border-bottom: 1px solid var(--eventwall-border); flex-shrink: 0; background: var(--eventwall-page-bg); }
.header-left h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; color: var(--eventwall-text); }
.subtitle { font-size: 12px; color: var(--eventwall-text-muted); }
.header-right { display: flex; align-items: center; gap: 8px; }
.filter-select {
  background: var(--eventwall-surface);
  border: 1px solid var(--eventwall-border-strong);
  border-radius: 8px;
  color: var(--eventwall-text);
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
}
.btn-ghost {
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--eventwall-surface);
  border: 1px solid var(--eventwall-border-strong);
  color: var(--eventwall-text);
  border-radius: 8px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: border-color .15s, background .15s, color .15s;
}
.btn-ghost:hover:not(:disabled) { border-color: var(--accent, #0969da); background: #eef5ff; color: var(--accent, #0969da); }
.btn-ghost:disabled { opacity: .6; cursor: not-allowed; }

.stats-bar { display: flex; align-items: center; gap: 12px; padding: 10px 20px; border-bottom: 1px solid var(--eventwall-border); flex-shrink: 0; background: rgba(255,255,255,0.72); }
.stat-pill { display: flex; align-items: center; gap: 5px; font-size: 11.5px; padding: 3px 10px; border-radius: 20px; }
.stat-pill.critical { background: rgba(248,81,73,0.1);  color: #f85149; border: 1px solid rgba(248,81,73,0.2); }
.stat-pill.error    { background: rgba(248,81,73,0.08); color: #ff7b72; border: 1px solid rgba(248,81,73,0.15); }
.stat-pill.warning  { background: rgba(210,153,34,0.1); color: #d29922; border: 1px solid rgba(210,153,34,0.2); }
.stat-pill.info     { background: rgba(56,139,253,0.1); color: #388bfd; border: 1px solid rgba(56,139,253,0.2); }
.pill-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pill-count { font-weight: 700; }
.stat-total { margin-left: auto; font-size: 11px; color: var(--eventwall-text-muted); }

.loading-row { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 40px; color: var(--eventwall-text-muted); }
.spinner { width: 16px; height: 16px; border: 2px solid rgba(148,163,184,0.22); border-top-color: var(--accent, #0969da); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.event-list { flex: 1; overflow-y: auto; padding: 10px 20px; display: flex; flex-direction: column; gap: 6px; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60px; color: var(--eventwall-text-muted); gap: 10px; font-size: 13px; }

.event-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  background: var(--eventwall-surface);
  border: 1px solid var(--eventwall-border);
  border-radius: 12px;
  padding: 12px 14px;
  cursor: pointer;
  transition: border-color .15s, background .15s, box-shadow .15s, transform .15s;
  box-shadow: var(--eventwall-shadow);
}
.event-card:hover { border-color: rgba(9,105,218,0.24); background: var(--eventwall-surface-soft); box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08); transform: translateY(-1px); }
.event-card.critical { border-left: 3px solid #f85149; }
.event-card.error    { border-left: 3px solid #ff7b72; }
.event-card.warning  { border-left: 3px solid #d29922; }
.event-card.info     { border-left: 3px solid #388bfd; }

.sev-badge { padding: 2px 8px; border-radius: 10px; font-size: 10.5px; font-weight: 600; white-space: nowrap; }
.sev-badge.critical { background: rgba(248,81,73,0.15);  color: #f85149; }
.sev-badge.error    { background: rgba(248,81,73,0.1);   color: #ff7b72; }
.sev-badge.warning  { background: rgba(210,153,34,0.15); color: #d29922; }
.sev-badge.info     { background: rgba(56,139,253,0.1);  color: #388bfd; }

.ev-body { flex: 1; min-width: 0; }
.ev-title { font-size: 13px; font-weight: 500; margin-bottom: 3px; color: var(--eventwall-text); }
.ev-msg   { font-size: 11.5px; color: var(--eventwall-text-muted); overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; line-height: 1.5; }
.ev-meta  { display: flex; gap: 8px; margin-top: 6px; align-items: center; flex-wrap: wrap; }
.source-tag  { font-size: 10px; padding: 1px 6px; border-radius: 8px; }
.source-tag.prometheus { background: rgba(232,108,0,0.12); color: #e86c00; border: 1px solid rgba(232,108,0,0.2); }
.source-tag.loki       { background: rgba(115,63,255,0.12); color: #8b5cf6; border: 1px solid rgba(115,63,255,0.2); }
.service-tag { font-size: 10px; color: var(--eventwall-text-muted); background: var(--eventwall-surface-soft); border: 1px solid var(--eventwall-border); padding: 1px 6px; border-radius: 8px; }
.time-tag    { font-size: 10px; color: var(--eventwall-text-muted); margin-left: auto; }
.ev-status { display: flex; align-items: center; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.firing { background: #f85149; animation: pulse 1.2s infinite; }
.status-dot.active { background: #d29922; }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.6;transform:scale(0.85)} }

/* Detail */
.modal-overlay { position: fixed; inset: 0; background: rgba(15,23,42,0.34); display: flex; align-items: center; justify-content: flex-end; z-index: 1000; backdrop-filter: blur(2px); }
.detail-panel { width: 480px; height: 100vh; background: var(--eventwall-surface); border-left: 1px solid var(--eventwall-border); display: flex; flex-direction: column; box-shadow: -18px 0 40px rgba(15, 23, 42, 0.12); }
.detail-header { display: flex; align-items: center; gap: 10px; padding: 16px; border-bottom: 1px solid var(--eventwall-border); }
.detail-title { font-size: 14px; font-weight: 600; flex: 1; color: var(--eventwall-text); }
.close-btn { background: none; border: none; color: var(--eventwall-text-muted); cursor: pointer; font-size: 16px; transition: color .15s; }
.close-btn:hover { color: var(--eventwall-text); }
.detail-body { flex: 1; overflow: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.detail-section label { display: block; font-size: 11px; font-weight: 600; color: var(--eventwall-text-muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 5px; }
.detail-section p { font-size: 12.5px; margin: 0; color: var(--eventwall-text); }
.detail-pre {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  line-height: 1.7;
  background: var(--eventwall-surface-soft);
  border: 1px solid var(--eventwall-border);
  border-radius: 8px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  color: #334155;
}
.label-grid { display: grid; grid-template-columns: auto 1fr; gap: 4px 12px; font-size: 11.5px; }
.label-key { color: var(--eventwall-text-muted); font-family: 'JetBrains Mono', monospace; }
.label-val { color: var(--eventwall-text); word-break: break-all; }
</style>
