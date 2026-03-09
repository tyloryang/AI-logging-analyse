<template>
  <div class="log-layout">
    <!-- 左侧服务过滤 -->
    <aside class="service-panel">
      <div class="panel-header">
        <span class="panel-title">服务列表</span>
        <select v-model="hours" class="time-select" @change="loadLogs">
          <option value="1">最近 1 小时</option>
          <option value="6">最近 6 小时</option>
          <option value="24">最近 24 小时</option>
          <option value="72">最近 3 天</option>
        </select>
      </div>

      <div class="svc-list-wrap">
        <div
          class="svc-item"
          :class="{ active: selectedService === '' }"
          @click="selectService('')"
        >
          <span class="svc-dot all"></span>
          <span class="svc-label">全部服务</span>
          <span class="svc-badge">{{ totalErrors }}</span>
        </div>
        <div v-if="loadingSvcs" class="loading-row"><div class="spinner" style="width:14px;height:14px;border-width:2px"></div></div>
        <div
          v-for="svc in services" :key="svc.name"
          class="svc-item"
          :class="{ active: selectedService === svc.name }"
          @click="selectService(svc.name)"
        >
          <span class="svc-dot" :class="svc.error_count > 0 ? 'error' : 'ok'"></span>
          <span class="svc-label">{{ svc.name }}</span>
          <span v-if="svc.error_count" class="svc-badge error">{{ svc.error_count }}</span>
        </div>
      </div>
    </aside>

    <!-- 右侧日志区 -->
    <div class="log-panel">
      <div class="log-toolbar">
        <div class="toolbar-left">
          <span class="log-title">
            管道日志总条数
            <span class="log-count">{{ logs.length.toLocaleString() }}</span>
          </span>
        </div>
        <div class="toolbar-right">
          <select v-model="levelFilter" class="time-select" @change="loadLogs">
            <option value="">全部级别</option>
            <option value="error">ERROR</option>
            <option value="warn">WARN</option>
          </select>
          <button class="btn btn-outline" @click="loadLogs" :disabled="loadingLogs">
            <span v-if="loadingLogs" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>🔄</span>
            实时查询
          </button>
          <button class="btn btn-primary" @click="startAIAnalysis" :disabled="analyzingAI">
            <span v-if="analyzingAI" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>🤖</span>
            AI 分析
          </button>
        </div>
      </div>

      <!-- AI 分析面板 -->
      <transition name="fade">
        <div v-if="aiContent || analyzingAI" class="ai-panel">
          <div class="ai-panel-header">
            <span>🤖 AI 分析结果</span>
            <button class="btn btn-outline btn-xs" @click="aiContent = ''">关闭</button>
          </div>
          <div class="ai-content" v-html="renderedAI"></div>
          <div v-if="analyzingAI" class="ai-typing"><span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span></div>
        </div>
      </transition>

      <!-- 日志列表 -->
      <div class="log-container" ref="logContainer">
        <div v-if="loadingLogs && !logs.length" class="empty-state">
          <div class="spinner"></div><p>加载日志中...</p>
        </div>
        <div v-else-if="!logs.length" class="empty-state">
          <span class="icon">📭</span><p>暂无日志数据</p>
        </div>
        <div v-else class="log-lines">
          <div
            v-for="(log, i) in logs" :key="i"
            class="log-line"
            :class="logClass(log.line)"
          >
            <span class="log-ts">{{ log.timestamp }}</span>
            <span class="log-svc" v-if="!selectedService">{{ log.labels.app || log.labels.job || '?' }}</span>
            <span class="log-text">{{ log.line }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, streamSSE } from '../api/index.js'

const services = ref([])
const logs = ref([])
const selectedService = ref('')
const hours = ref('24')
const levelFilter = ref('')
const loadingSvcs = ref(false)
const loadingLogs = ref(false)
const analyzingAI = ref(false)
const aiContent = ref('')
const logContainer = ref(null)
const totalErrors = computed(() => services.value.reduce((s, v) => s + v.error_count, 0))

const renderedAI = computed(() =>
  aiContent.value
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
)

function logClass(line) {
  const l = line.toLowerCase()
  if (/\berror\b|exception|fatal|panic/.test(l)) return 'level-error'
  if (/\bwarn(ing)?\b/.test(l)) return 'level-warn'
  return ''
}

async function loadServices() {
  loadingSvcs.value = true
  try {
    const r = await api.getServices()
    services.value = r.data
  } finally {
    loadingSvcs.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  logs.value = []
  try {
    const r = await api.getLogs({
      service: selectedService.value || undefined,
      hours: hours.value,
      level: levelFilter.value || undefined,
      limit: 500,
    })
    logs.value = r.data
  } finally {
    loadingLogs.value = false
  }
}

function selectService(name) {
  selectedService.value = name
  loadLogs()
}

function startAIAnalysis() {
  aiContent.value = ''
  analyzingAI.value = true
  const params = new URLSearchParams({ hours: hours.value })
  if (selectedService.value) params.set('service', selectedService.value)
  const stop = streamSSE(
    `/api/analyze/stream?${params}`,
    (chunk) => { try { aiContent.value += JSON.parse(chunk) } catch { aiContent.value += chunk } },
    () => { analyzingAI.value = false },
    () => { analyzingAI.value = false },
  )
}

onMounted(() => {
  loadServices()
  loadLogs()
})
</script>

<style scoped>
.log-layout { display: flex; height: 100vh; overflow: hidden; }

/* 左侧服务面板 */
.service-panel { width: 220px; min-width: 220px; background: var(--bg-card); border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.panel-header { padding: 16px 14px 12px; border-bottom: 1px solid var(--border); }
.panel-title { display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .8px; margin-bottom: 8px; }
.time-select { width: 100%; background: var(--bg-hover); border: 1px solid var(--border); color: var(--text-primary); padding: 5px 8px; border-radius: 5px; font-size: 12px; cursor: pointer; }
.svc-list-wrap { flex: 1; overflow-y: auto; padding: 8px 8px; }
.svc-item { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 6px; cursor: pointer; transition: background .12s; }
.svc-item:hover { background: var(--bg-hover); }
.svc-item.active { background: var(--bg-active); }
.svc-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.svc-dot.all   { background: var(--accent); }
.svc-dot.ok    { background: var(--success); }
.svc-dot.error { background: var(--error); }
.svc-label { flex: 1; font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.svc-badge { font-size: 10px; padding: 1px 6px; border-radius: 9999px; background: rgba(239,68,68,.15); color: var(--error); font-weight: 600; }
.loading-row { display: flex; justify-content: center; padding: 12px; }

/* 右侧日志面板 */
.log-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.log-toolbar { padding: 12px 20px; background: var(--bg-card); border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-shrink: 0; }
.toolbar-left { display: flex; align-items: center; }
.log-title { font-size: 14px; font-weight: 600; }
.log-count { margin-left: 8px; background: rgba(99,102,241,.15); color: var(--accent-hover); padding: 2px 8px; border-radius: 9999px; font-size: 12px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }

/* AI 面板 */
.ai-panel { margin: 12px 16px; background: rgba(99,102,241,.07); border: 1px solid rgba(99,102,241,.25); border-radius: var(--radius); padding: 14px 16px; }
.ai-panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 13px; font-weight: 600; color: var(--accent-hover); }
.btn-xs { padding: 2px 8px; font-size: 11px; }
.ai-content { font-size: 13px; line-height: 1.8; color: var(--text-secondary); max-height: 220px; overflow-y: auto; white-space: pre-wrap; word-break: break-word; }
.ai-typing { display: flex; gap: 4px; margin-top: 8px; }
.ai-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }
@keyframes pulse { 0%,80%,100% { opacity:.2 } 40% { opacity:1 } }

/* 日志列表 */
.log-container { flex: 1; overflow-y: auto; }
.log-lines { font-family: 'Consolas', 'JetBrains Mono', monospace; font-size: 12px; }
.log-line { display: flex; gap: 10px; padding: 4px 16px; border-bottom: 1px solid rgba(46,49,80,.4); transition: background .1s; }
.log-line:hover { background: var(--bg-hover); }
.log-line.level-error { background: var(--log-error); }
.log-line.level-warn  { background: var(--log-warn);  }
.log-ts  { color: var(--text-muted); white-space: nowrap; flex-shrink: 0; }
.log-svc { color: var(--accent-hover); white-space: nowrap; flex-shrink: 0; min-width: 140px; }
.log-text { color: var(--text-secondary); word-break: break-all; }
.level-error .log-text { color: #fca5a5; }
.level-warn  .log-text { color: #fcd34d; }
</style>
