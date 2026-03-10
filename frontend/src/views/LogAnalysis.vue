<template>
  <div class="log-layout">
    <!-- 左侧服务过滤 -->
    <aside class="service-panel">
      <div class="panel-header">
        <span class="panel-title">服务列表</span>
        <!-- 时间模式切换 -->
        <div class="time-mode-tabs">
          <button class="tmode-btn" :class="{ active: timeMode === 'relative' }" @click="timeMode = 'relative'; onTimeModeChange()">快速</button>
          <button class="tmode-btn" :class="{ active: timeMode === 'custom' }" @click="timeMode = 'custom'">自定义</button>
        </div>
        <!-- 相对时间选择 -->
        <select v-if="timeMode === 'relative'" v-model="hours" class="time-select" @change="onParamChange">
          <option value="1">最近 1 小时</option>
          <option value="6">最近 6 小时</option>
          <option value="24">最近 24 小时</option>
          <option value="72">最近 3 天</option>
        </select>
        <!-- 自定义时间范围 -->
        <div v-else class="custom-time-wrap">
          <input type="datetime-local" v-model="customStart" class="dt-input" @change="onCustomTimeChange" title="开始时间" />
          <span class="dt-sep">→</span>
          <input type="datetime-local" v-model="customEnd"   class="dt-input" @change="onCustomTimeChange" title="结束时间" />
        </div>
      </div>

      <div class="svc-list-wrap">
        <div class="svc-item" :class="{ active: selectedService === '' }" @click="selectService('')">
          <span class="svc-dot all"></span>
          <span class="svc-label">全部服务</span>
          <span class="svc-badge">{{ totalErrors }}</span>
        </div>
        <div v-if="loadingSvcs" class="loading-row">
          <div class="spinner" style="width:14px;height:14px;border-width:2px"></div>
        </div>
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

    <!-- 右侧内容区 -->
    <div class="log-panel">
      <!-- 工具栏 -->
      <div class="log-toolbar">
        <div class="toolbar-left">
          <!-- Tab 切换 -->
          <div class="tab-group">
            <button class="tab-btn" :class="{ active: activeTab === 'logs' }" @click="switchTab('logs')">
              📋 日志流
              <span class="tab-count">{{ logs.length }}</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'templates' }" @click="switchTab('templates')">
              🧩 模板聚合
              <span class="tab-count" v-if="templates.length">{{ templates.length }}</span>
            </button>
          </div>
        </div>
        <div class="toolbar-right">
          <!-- 关键字搜索（两个 tab 共用） -->
          <div class="keyword-wrap">
            <span class="kw-icon">🔍</span>
            <input
              v-model="keyword"
              class="kw-input"
              placeholder="关键字过滤..."
              @input="onKeywordInput"
              @keyup.enter="onParamChange"
            />
            <button v-if="keyword" class="kw-clear" @click="clearKeyword">✕</button>
          </div>

          <!-- 日志流专有控件 -->
          <template v-if="activeTab === 'logs'">
            <select v-model="levelFilter" class="time-select" @change="loadLogs">
              <option value="">全部级别</option>
              <option value="error">ERROR</option>
              <option value="warn">WARN</option>
            </select>
            <button class="btn btn-outline" @click="loadLogs" :disabled="loadingLogs">
              <span v-if="loadingLogs" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🔄</span>实时查询
            </button>
            <button class="btn btn-primary" @click="startAIAnalysis" :disabled="analyzingAI">
              <span v-if="analyzingAI" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🤖</span>AI 分析
            </button>
          </template>
          <!-- 模板聚合专有控件 -->
          <template v-if="activeTab === 'templates'">
            <span class="meta-info" v-if="templateMeta.total_logs">
              采样 {{ templateMeta.total_logs }} 条 → {{ templates.length }} 个模板
            </span>
            <select v-model="tplLevelFilter" class="time-select" @change="loadTemplates">
              <option value="">全量日志</option>
              <option value="error">仅 ERROR</option>
              <option value="warn">仅 WARN</option>
            </select>
            <button class="btn btn-outline" @click="loadTemplates" :disabled="loadingTemplates">
              <span v-if="loadingTemplates" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🔄</span>重新聚类
            </button>
          </template>
        </div>
      </div>

      <!-- AI 分析面板（仅日志流 tab 显示） -->
      <transition name="fade">
        <div v-if="(aiContent || analyzingAI) && activeTab === 'logs'" class="ai-panel">
          <div class="ai-panel-header">
            <span>🤖 AI 分析结果</span>
            <button class="btn btn-outline btn-xs" @click="aiContent = ''">关闭</button>
          </div>
          <div class="ai-content" v-html="renderedAI"></div>
          <div v-if="analyzingAI" class="ai-typing">
            <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
          </div>
        </div>
      </transition>

      <!-- ── 日志流 ── -->
      <div v-show="activeTab === 'logs'" class="log-container">
        <div v-if="loadingLogs && !logs.length" class="empty-state">
          <div class="spinner"></div><p>加载日志中...</p>
        </div>
        <div v-else-if="!logs.length" class="empty-state">
          <span class="icon">📭</span><p>暂无日志数据</p>
        </div>
        <div v-else class="log-lines">
          <div
            v-for="(log, i) in logs" :key="i"
            class="log-line" :class="logClass(log.line)"
          >
            <span class="log-ts">{{ log.timestamp }}</span>
            <span class="log-svc" v-if="!selectedService">{{ log.labels.app || log.labels.job || '?' }}</span>
            <span class="log-text">{{ log.line }}</span>
          </div>
        </div>
      </div>

      <!-- ── 模板聚合 ── -->
      <div v-show="activeTab === 'templates'" class="template-container">
        <div v-if="loadingTemplates" class="empty-state">
          <div class="spinner"></div><p>Drain3 聚类中...</p>
        </div>
        <div v-else-if="tplError" class="empty-state">
          <span class="icon">⚠️</span>
          <p style="color:var(--error)">{{ tplError }}</p>
        </div>
        <div v-else-if="!templates.length" class="empty-state">
          <span class="icon">🧩</span>
          <p>当前条件下暂无日志可聚类<br><small style="color:var(--text-muted)">尝试切换「全量日志」或扩大时间范围</small></p>
        </div>
        <div v-else class="template-list">
          <div v-for="(tpl, i) in templates" :key="tpl.cluster_id" class="tpl-card">
            <!-- 头部：排名 + 计数 + 模板 -->
            <div class="tpl-header">
              <span class="tpl-rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
              <span class="tpl-count badge badge-error">{{ tpl.count }} 条</span>
              <span class="tpl-pct">{{ tplPct(tpl.count) }}%</span>
              <div class="tpl-bar-wrap">
                <div class="tpl-bar" :style="{ width: tplBarW(tpl.count) + '%' }"></div>
              </div>
            </div>
            <!-- 模板字符串 -->
            <div class="tpl-pattern" v-html="highlightWildcard(tpl.template)"></div>
            <!-- 服务分布 -->
            <div class="tpl-services" v-if="tpl.top_services.length">
              <span class="tpl-label">来源：</span>
              <span
                v-for="s in tpl.top_services" :key="s.name"
                class="svc-chip"
              >{{ s.name }}<em>{{ s.count }}</em></span>
            </div>
            <!-- 示例原文（可展开） -->
            <div class="tpl-example" v-if="tpl.example">
              <span class="tpl-label">示例：</span>
              <span class="tpl-example-text">
                <span class="tpl-example-ts">{{ tpl.example_ts }}</span>
                {{ tpl.example }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, streamSSE } from '../api/index.js'

// ── 公共状态 ─────────────────────────────
const services       = ref([])
const selectedService = ref('')
const hours          = ref('24')
const loadingSvcs    = ref(false)
const activeTab      = ref('logs')

// 时间模式：relative（最近N小时） | custom（自定义时间段）
const timeMode    = ref('relative')
const customStart = ref('')
const customEnd   = ref('')

// 关键字搜索
const keyword      = ref('')
let   searchTimer  = null

const totalErrors = computed(() =>
  services.value.reduce((s, v) => s + v.error_count, 0)
)

// 构建时间参数（relative 或 custom）
function timeParams() {
  if (timeMode.value === 'custom' && customStart.value && customEnd.value) {
    return { start_time: customStart.value, end_time: customEnd.value }
  }
  return { hours: hours.value }
}

// ── 日志流 ───────────────────────────────
const logs         = ref([])
const levelFilter  = ref('')
const loadingLogs  = ref(false)
const analyzingAI  = ref(false)
const aiContent    = ref('')

const renderedAI = computed(() =>
  aiContent.value
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
)

function logClass(line) {
  const l = line.toLowerCase()
  if (/\berror\b|exception|fatal|panic/.test(l)) return 'level-error'
  if (/\bwarn(ing)?\b/.test(l))                  return 'level-warn'
  return ''
}

// ── 模板聚合 ─────────────────────────────
const templates        = ref([])
const loadingTemplates = ref(false)
const templateMeta     = ref({ total_logs: 0, total_templates: 0 })
const tplLevelFilter   = ref('')
const tplError         = ref('')

const maxTplCount = computed(() =>
  templates.value[0]?.count || 1
)
const totalTplLogs = computed(() =>
  templates.value.reduce((s, t) => s + t.count, 0) || 1
)
function tplBarW(cnt) {
  return Math.round(cnt / maxTplCount.value * 100)
}
function tplPct(cnt) {
  return (cnt / totalTplLogs.value * 100).toFixed(1)
}
function highlightWildcard(tpl) {
  return tpl.replace(/<\*>/g, '<span class="wildcard">&lt;*&gt;</span>')
}

// ── 数据加载 ─────────────────────────────
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
      service:  selectedService.value || undefined,
      level:    levelFilter.value || undefined,
      limit:    2000,
      keyword:  keyword.value || undefined,
      ...timeParams(),
    })
    logs.value = r.data
  } finally {
    loadingLogs.value = false
  }
}

async function loadTemplates() {
  loadingTemplates.value = true
  templates.value = []
  tplError.value = ''
  try {
    const r = await api.getTemplates({
      service:  selectedService.value || undefined,
      limit:    10000,
      top_n:    100,
      level:    tplLevelFilter.value || undefined,
      keyword:  keyword.value || undefined,
      ...timeParams(),
    })
    templates.value = r.data
    templateMeta.value = { total_logs: r.total_logs, total_templates: r.total_templates }
  } catch (e) {
    tplError.value = typeof e === 'string' ? e : (e?.message || '聚类请求失败，请检查后端连接')
  } finally {
    loadingTemplates.value = false
  }
}

function selectService(name) {
  selectedService.value = name
  if (activeTab.value === 'logs')      loadLogs()
  else                                 loadTemplates()
}

function onParamChange() {
  if (activeTab.value === 'logs')      loadLogs()
  else                                 loadTemplates()
}

function onTimeModeChange() {
  if (timeMode.value === 'relative') {
    customStart.value = ''
    customEnd.value   = ''
    onParamChange()
  }
}

function onCustomTimeChange() {
  if (customStart.value && customEnd.value) onParamChange()
}

function onKeywordInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(onParamChange, 500)
}

function clearKeyword() {
  keyword.value = ''
  onParamChange()
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'templates' && !templates.value.length) loadTemplates()
}

function startAIAnalysis() {
  aiContent.value = ''
  analyzingAI.value = true
  const tp = timeParams()
  const params = new URLSearchParams(tp)
  if (selectedService.value) params.set('service', selectedService.value)
  streamSSE(
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
.service-panel {
  width: 220px; min-width: 220px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
.panel-header { padding: 16px 14px 12px; border-bottom: 1px solid var(--border); }
.panel-title {
  display: block; font-size: 12px; font-weight: 600;
  color: var(--text-muted); text-transform: uppercase;
  letter-spacing: .8px; margin-bottom: 8px;
}
.time-select {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 5px 8px; border-radius: 5px; font-size: 12px; cursor: pointer;
}
/* 时间模式切换 */
.time-mode-tabs {
  display: flex; margin-bottom: 6px;
  background: var(--bg-base); border-radius: 5px; padding: 2px;
}
.tmode-btn {
  flex: 1; padding: 3px 0; font-size: 11px; border: none;
  background: transparent; color: var(--text-muted);
  border-radius: 4px; cursor: pointer; transition: all .12s;
}
.tmode-btn.active { background: var(--bg-active); color: var(--text-primary); }

/* 自定义时间输入 */
.custom-time-wrap {
  display: flex; flex-direction: column; gap: 4px; margin-top: 2px;
}
.dt-input {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 4px 6px; border-radius: 5px; font-size: 11px;
  color-scheme: dark;
}
.dt-sep {
  text-align: center; font-size: 10px; color: var(--text-muted); line-height: 1;
}

/* 关键字搜索框 */
.keyword-wrap {
  display: flex; align-items: center;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px; padding: 0 8px; gap: 5px;
  min-width: 160px; max-width: 240px;
}
.kw-icon { font-size: 12px; flex-shrink: 0; }
.kw-input {
  flex: 1; background: transparent; border: none;
  color: var(--text-primary); font-size: 12px;
  padding: 5px 0; outline: none;
}
.kw-input::placeholder { color: var(--text-muted); }
.kw-clear {
  background: none; border: none; color: var(--text-muted);
  font-size: 11px; cursor: pointer; padding: 2px;
  line-height: 1; flex-shrink: 0;
}
.kw-clear:hover { color: var(--text-primary); }

.svc-list-wrap { flex: 1; overflow-y: auto; padding: 8px; }
.svc-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; border-radius: 6px;
  cursor: pointer; transition: background .12s;
}
.svc-item:hover  { background: var(--bg-hover); }
.svc-item.active { background: var(--bg-active); }
.svc-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.svc-dot.all   { background: var(--accent); }
.svc-dot.ok    { background: var(--success); }
.svc-dot.error { background: var(--error); }
.svc-label { flex: 1; font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.svc-badge { font-size: 10px; padding: 1px 6px; border-radius: 9999px; background: rgba(239,68,68,.15); color: var(--error); font-weight: 600; }
.loading-row { display: flex; justify-content: center; padding: 12px; }

/* 右侧 */
.log-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* 工具栏 */
.log-toolbar {
  padding: 10px 16px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  justify-content: space-between; gap: 12px;
  flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }

/* Tab */
.tab-group { display: flex; gap: 2px; background: var(--bg-base); padding: 3px; border-radius: 8px; }
.tab-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 14px; border-radius: 6px;
  border: none; background: transparent;
  color: var(--text-muted); font-size: 13px;
  cursor: pointer; transition: all .15s;
}
.tab-btn:hover  { color: var(--text-primary); }
.tab-btn.active { background: var(--bg-active); color: var(--text-primary); }
.tab-count {
  background: var(--bg-hover);
  color: var(--text-muted);
  font-size: 11px; padding: 0 6px;
  border-radius: 9999px; font-weight: 600;
}
.tab-btn.active .tab-count { background: rgba(99,102,241,.2); color: var(--accent-hover); }
.meta-info { font-size: 12px; color: var(--text-muted); }

/* AI 面板 */
.ai-panel {
  margin: 10px 14px; padding: 14px 16px;
  background: rgba(99,102,241,.07);
  border: 1px solid rgba(99,102,241,.25);
  border-radius: var(--radius);
  flex-shrink: 0;
}
.ai-panel-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; font-size: 13px; font-weight: 600;
  color: var(--accent-hover);
}
.btn-xs { padding: 2px 8px; font-size: 11px; }
.ai-content {
  font-size: 13px; line-height: 1.8; color: var(--text-secondary);
  max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
}
.ai-typing { display: flex; gap: 4px; margin-top: 8px; }
.ai-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }

/* 日志列表 */
.log-container { flex: 1; overflow-y: auto; }
.log-lines { font-family: 'Consolas', 'JetBrains Mono', monospace; font-size: 12px; }
.log-line {
  display: flex; gap: 10px; padding: 4px 16px;
  border-bottom: 1px solid rgba(46,49,80,.4);
  transition: background .1s;
}
.log-line:hover         { background: var(--bg-hover); }
.log-line.level-error   { background: var(--log-error); }
.log-line.level-warn    { background: var(--log-warn); }
.log-ts   { color: var(--text-muted); white-space: nowrap; flex-shrink: 0; }
.log-svc  { color: var(--accent-hover); white-space: nowrap; flex-shrink: 0; min-width: 140px; }
.log-text { color: var(--text-secondary); word-break: break-all; }
.level-error .log-text  { color: #fca5a5; }
.level-warn  .log-text  { color: #fcd34d; }

/* ── 模板聚合 ── */
.template-container { flex: 1; overflow-y: auto; padding: 12px 16px; }
.template-list { display: flex; flex-direction: column; gap: 10px; }

.tpl-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  transition: border-color .15s;
}
.tpl-card:hover { border-color: rgba(99,102,241,.4); }

.tpl-header {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px;
}
.tpl-rank {
  width: 22px; text-align: center;
  font-size: 12px; font-weight: 700;
  color: var(--text-muted); flex-shrink: 0;
}
.tpl-rank.rank-top { color: var(--warning); }
.tpl-count { flex-shrink: 0; }
.tpl-pct { font-size: 11px; color: var(--text-muted); flex-shrink: 0; width: 44px; }
.tpl-bar-wrap { flex: 1; height: 6px; background: var(--bg-hover); border-radius: 3px; overflow: hidden; }
.tpl-bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 3px; transition: width .4s; }

.tpl-pattern {
  font-family: 'Consolas', 'JetBrains Mono', monospace;
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 8px 12px;
  word-break: break-all;
  line-height: 1.7;
  margin-bottom: 10px;
}
:deep(.wildcard) {
  color: var(--accent-hover);
  background: rgba(99,102,241,.15);
  border-radius: 3px;
  padding: 0 3px;
  font-weight: 600;
}

.tpl-services { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tpl-label { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.svc-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; padding: 2px 8px;
  background: rgba(59,130,246,.1);
  border: 1px solid rgba(59,130,246,.25);
  color: var(--info); border-radius: 9999px;
}
.svc-chip em { font-style: normal; opacity: .7; }

.tpl-example {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: 11px;
}
.tpl-example-text {
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
  overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; flex: 1;
}
.tpl-example-ts { color: var(--text-muted); opacity: .6; margin-right: 6px; }

@keyframes pulse { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
</style>
