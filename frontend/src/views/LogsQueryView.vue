<template>
  <div class="logs-page">
    <header class="page-header">
      <div>
        <h1>日志中心</h1>
        <p>面向 Loki 的 LogQL 查询入口，支持标签选择、快速时间范围和日志展开。</p>
      </div>
      <div class="actions">
        <button class="btn btn-outline" @click="loadLabels" :disabled="loadingLabels">刷新标签</button>
        <button class="btn btn-primary" @click="runQuery" :disabled="querying">
          <span v-if="querying" class="spinner-sm"></span>
          查询日志
        </button>
      </div>
    </header>

    <main class="logs-grid">
      <section class="panel query-panel">
        <div class="panel-head">
          <div>
            <h2>查询条件</h2>
            <span>输入 LogQL 或通过标签构造查询</span>
          </div>
        </div>

        <textarea v-model="query" rows="4" spellcheck="false" placeholder='{app=~".+"} |= "error"'></textarea>

        <div class="control-grid">
          <label>
            <span>时间范围</span>
            <select v-model="hours">
              <option value="0.016667">最近 1 分钟</option>
              <option value="0.083333">最近 5 分钟</option>
              <option value="0.25">最近 15 分钟</option>
              <option value="0.5">最近 30 分钟</option>
              <option value="1">最近 1 小时</option>
              <option value="6">最近 6 小时</option>
              <option value="24">最近 24 小时</option>
            </select>
          </label>
          <label>
            <span>返回条数</span>
            <select v-model.number="limit">
              <option :value="100">100</option>
              <option :value="200">200</option>
              <option :value="500">500</option>
              <option :value="1000">1000</option>
            </select>
          </label>
          <label>
            <span>方向</span>
            <select v-model="direction">
              <option value="backward">最新优先</option>
              <option value="forward">最旧优先</option>
            </select>
          </label>
        </div>

        <div class="quick-row">
          <button v-for="tpl in queryTemplates" :key="tpl.name" @click="applyTemplate(tpl)">
            <strong>{{ tpl.name }}</strong>
            <code>{{ tpl.query }}</code>
          </button>
        </div>

        <div v-if="error" class="error-box">{{ error }}</div>
      </section>

      <aside class="panel label-panel">
        <div class="panel-head">
          <div>
            <h2>Loki 标签</h2>
            <span>{{ labels.length }} 个标签</span>
          </div>
        </div>
        <input v-model.trim="labelSearch" placeholder="搜索标签" />
        <div class="label-select-stack">
          <label>
            <span>标签名</span>
            <select v-model="activeLabel" @change="onLabelSelectChange">
              <option value="">请选择 Loki 标签</option>
              <option v-for="label in visibleLabels" :key="label.name" :value="label.name">
                {{ label.name }} · {{ label.role }}
              </option>
            </select>
          </label>
          <label>
            <span>标签值</span>
            <select v-model="activeLabelValue" :disabled="!activeLabel || loadingValues" @change="onLabelValueSelectChange">
              <option value="">{{ loadingValues ? '加载中...' : '请选择标签值' }}</option>
              <option v-for="value in labelValues" :key="value" :value="value">{{ value }}</option>
            </select>
          </label>
          <button
            class="label-apply"
            :disabled="!activeLabel || !activeLabelValue"
            @click="applyLabelFilter(activeLabel, activeLabelValue)"
          >
            加入查询
          </button>
          <div v-if="activeLabel && !loadingValues && !labelValues.length" class="mini-state">当前标签暂无样例值</div>
        </div>
      </aside>
    </main>

    <section class="panel result-panel">
      <div class="result-head">
        <div>
          <h2>查询结果</h2>
          <span>{{ resultSummary }}</span>
        </div>
        <div class="pill-row">
          <span>总数 {{ logs.length }}</span>
          <span>范围 {{ rangeText }}</span>
          <span>查询 {{ lastQuery || '-' }}</span>
        </div>
      </div>

      <div v-if="querying" class="empty">
        <span class="spinner"></span>
        <p>正在查询 Loki</p>
      </div>
      <div v-else-if="!logs.length" class="empty">
        <p>暂无日志结果</p>
      </div>
      <div v-else class="log-list">
        <article
          v-for="(log, index) in logs"
          :key="`${log.timestamp_ns}-${index}`"
          class="log-card"
          :class="levelOf(log.line)"
        >
          <button class="log-line" @click="toggle(index)">
            <span class="ts">{{ log.timestamp }}</span>
            <span class="level" :class="levelOf(log.line)">{{ levelOf(log.line).toUpperCase() }}</span>
            <span class="svc">{{ serviceName(log) }}</span>
            <span class="msg">{{ log.line }}</span>
          </button>
          <div v-if="expanded.has(index)" class="log-detail">
            <div class="label-chips">
              <button
                v-for="(value, key) in log.labels || {}"
                :key="key"
                @click.stop="applyLabelFilter(key, value)"
              >
                {{ key }}={{ value }}
              </button>
            </div>
            <pre>{{ log.line }}</pre>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/index.js'

const query = ref('{app=~".+"}')
const serviceLabel = ref('app')
const hours = ref('0.016667')
const limit = ref(200)
const direction = ref('backward')
const labels = ref([])
const labelValues = ref([])
const labelSearch = ref('')
const activeLabel = ref('')
const activeLabelValue = ref('')
const logs = ref([])
const lastQuery = ref('')
const loadingLabels = ref(false)
const loadingValues = ref(false)
const querying = ref(false)
const error = ref('')
const expanded = ref(new Set())

const visibleLabels = computed(() => {
  const q = labelSearch.value.toLowerCase()
  const items = q ? labels.value.filter(label => label.name.toLowerCase().includes(q)) : labels.value
  return items.slice(0, 120)
})

const queryTemplates = computed(() => [
  { name: '全部服务', query: `{${serviceLabel.value}=~".+"}` },
  { name: '错误日志', query: `{${serviceLabel.value}=~".+"} |~ "(?i)(error|exception|fatal|panic)"` },
  { name: '告警日志', query: `{${serviceLabel.value}=~".+"} |~ "(?i)(warn|warning)"` },
  { name: '容器日志', query: '{container=~".+"}' },
])

const rangeText = computed(() => ({
  '0.016667': '最近 1 分钟',
  '0.083333': '最近 5 分钟',
  '0.25': '最近 15 分钟',
  '0.5': '最近 30 分钟',
  '1': '最近 1 小时',
  '6': '最近 6 小时',
  '24': '最近 24 小时',
}[String(hours.value)] || `${hours.value} 小时`))

const resultSummary = computed(() => {
  if (!lastQuery.value) return '尚未执行查询'
  return `${lastQuery.value} · ${rangeText.value}`
})

function applyTemplate(tpl) {
  query.value = tpl.query
}

function escapeLabel(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

function addLabelFilter(label, value) {
  const matcher = `${label}="${escapeLabel(value)}"`
  const text = query.value.trim()
  if (!text.startsWith('{')) {
    query.value = `{${matcher}}`
    return
  }
  const close = text.indexOf('}')
  if (close < 0) {
    query.value = `{${matcher}}`
    return
  }
  const inner = text.slice(1, close).trim()
  const suffix = text.slice(close + 1)
  const parts = inner ? inner.split(/\s*,\s*/).filter(Boolean) : []
  const existing = parts.findIndex(part => new RegExp(`^${label}\\s*(=|=~|!=|!~)`).test(part))
  if (existing >= 0) {
    parts[existing] = matcher
  } else {
    parts.push(matcher)
  }
  query.value = `{${parts.join(',')}}${suffix}`
}

async function applyLabelFilter(label, value) {
  activeLabel.value = label
  activeLabelValue.value = value
  addLabelFilter(label, value)
  await runQuery()
}

function levelOf(line = '') {
  const lower = line.toLowerCase()
  if (/(error|exception|fatal|panic)/.test(lower)) return 'error'
  if (/(warn|warning)/.test(lower)) return 'warn'
  if (/debug/.test(lower)) return 'debug'
  return 'info'
}

function serviceName(log) {
  const labels = log.labels || {}
  return labels.app || labels.service || labels.job || labels.container || '-'
}

function toggle(index) {
  const next = new Set(expanded.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  expanded.value = next
}

async function loadLabels() {
  loadingLabels.value = true
  try {
    const data = await api.getLogLabels()
    labels.value = data.data || []
    const detectedServiceLabel = data.service_label || labels.value[0]?.name || 'app'
    serviceLabel.value = detectedServiceLabel
    if (query.value === '{app=~".+"}' && detectedServiceLabel !== 'app') {
      query.value = `{${detectedServiceLabel}=~".+"}`
    }
    if (detectedServiceLabel && !activeLabel.value) await selectLabel(detectedServiceLabel)
  } catch {
    labels.value = []
  } finally {
    loadingLabels.value = false
  }
}

async function selectLabel(label) {
  activeLabel.value = label
  activeLabelValue.value = ''
  loadingValues.value = true
  try {
    const data = await api.getLogLabelValues(label, { limit: 100 })
    labelValues.value = data.data || []
  } catch {
    labelValues.value = []
  } finally {
    loadingValues.value = false
  }
}

async function onLabelSelectChange() {
  activeLabelValue.value = ''
  if (!activeLabel.value) {
    labelValues.value = []
    return
  }
  await selectLabel(activeLabel.value)
}

async function onLabelValueSelectChange() {
  if (activeLabel.value && activeLabelValue.value) {
    await applyLabelFilter(activeLabel.value, activeLabelValue.value)
  }
}

async function runQuery() {
  error.value = ''
  if (!query.value.trim()) {
    error.value = '请填写 LogQL'
    return
  }
  querying.value = true
  expanded.value = new Set()
  try {
    const data = await api.queryLokiRange({
      query: query.value.trim(),
      hours: hours.value,
      limit: limit.value,
      direction: direction.value,
    })
    logs.value = data.data || []
    lastQuery.value = data.query || query.value.trim()
  } catch (err) {
    logs.value = []
    error.value = String(err)
  } finally {
    querying.value = false
  }
}

onMounted(async () => {
  await loadLabels()
  await runQuery()
})
</script>

<style scoped>
.logs-page {
  height: 100%;
  overflow: auto;
  padding: 24px;
  background: var(--bg-base);
  color: var(--text-primary);
}
.page-header,
.actions,
.panel-head,
.result-head,
.pill-row {
  display: flex;
  gap: 10px;
}
.page-header,
.result-head,
.panel-head {
  align-items: flex-start;
  justify-content: space-between;
}
.page-header {
  margin-bottom: 16px;
}
h1 {
  font-size: 26px;
  margin: 0 0 4px;
}
p,
.panel-head span,
.result-head span {
  margin: 0;
  color: var(--text-muted);
  font-size: 13px;
}
.btn {
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 8px 13px;
  background: var(--bg-card);
  color: var(--text-primary);
  cursor: pointer;
}
.btn:disabled {
  opacity: .55;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--accent);
  color: #fff;
}
.btn-outline {
  border-color: var(--border);
}
.logs-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: 14px;
}
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.panel-head {
  margin-bottom: 12px;
}
h2 {
  font-family: var(--font-sans);
  font-size: 16px;
  margin: 0 0 2px;
}
textarea,
input,
select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 9px 10px;
  outline: none;
}
textarea,
code,
pre {
  font-family: var(--font-mono);
}
.control-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}
label span {
  display: block;
  margin-bottom: 6px;
  color: var(--text-muted);
  font-size: 12px;
}
.quick-row {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 8px;
}
.quick-row button {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-base);
  color: var(--text-primary);
  text-align: left;
  padding: 10px;
  cursor: pointer;
}
.quick-row button:hover {
  border-color: var(--accent);
}
.quick-row strong,
.quick-row code {
  display: block;
}
.quick-row code {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.error-box {
  margin-top: 10px;
  border: 1px solid rgba(var(--error-rgb), .24);
  background: rgba(var(--error-rgb), .08);
  color: var(--error);
  border-radius: 7px;
  padding: 8px 10px;
}
.label-panel {
  min-height: 420px;
  display: flex;
  flex-direction: column;
}
.label-select-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
}
.label-select-stack label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: var(--text-muted);
  font-size: 12px;
}
.label-select-stack select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-base);
  color: var(--text-primary);
  padding: 8px 9px;
  font-size: 13px;
}
.label-apply {
  border: 1px solid var(--accent);
  border-radius: 7px;
  background: rgba(var(--accent-rgb), .12);
  color: var(--accent);
  padding: 8px 9px;
  cursor: pointer;
  font-size: 13px;
}
.label-apply:disabled {
  opacity: .5;
  cursor: not-allowed;
}
.label-list {
  margin-top: 10px;
  max-height: 230px;
  overflow: auto;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.label-list button,
.value-chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-base);
  color: var(--text-secondary);
  padding: 5px 9px;
  cursor: pointer;
  font-size: 12px;
}
.label-list button.active,
.label-list button:hover,
.value-chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.label-list small {
  margin-left: 4px;
  color: var(--text-muted);
}
.value-box {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.value-box h3 {
  flex-basis: 100%;
  margin: 0;
  font-family: var(--font-sans);
  font-size: 13px;
}
.mini-state {
  color: var(--text-muted);
  font-size: 12px;
}
.result-panel {
  margin-top: 14px;
}
.pill-row {
  flex-wrap: wrap;
  justify-content: flex-end;
}
.pill-row span {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 9px;
  color: var(--text-muted);
  font-size: 12px;
}
.empty {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-muted);
}
.log-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.log-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-base);
}
.log-card.error {
  border-color: rgba(var(--error-rgb), .25);
}
.log-card.warn {
  border-color: rgba(var(--warning-rgb), .25);
}
.log-line {
  width: 100%;
  display: grid;
  grid-template-columns: 158px 70px 140px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  padding: 9px 11px;
  cursor: pointer;
  text-align: left;
}
.ts,
.svc {
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.level {
  width: fit-content;
  border-radius: 999px;
  padding: 2px 7px;
  font-size: 11px;
  font-weight: 700;
  background: var(--bg-card);
  color: var(--text-muted);
}
.level.error { color: var(--error); }
.level.warn { color: var(--warning); }
.level.info { color: var(--info); }
.msg {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-detail {
  border-top: 1px solid var(--border);
  padding: 10px 12px 12px;
}
.label-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 8px;
}
.label-chips button {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: transparent;
  padding: 2px 7px;
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
}
.label-chips button:hover {
  border-color: var(--accent);
  color: var(--accent);
}
pre {
  margin: 0;
  padding: 10px;
  border-radius: 7px;
  background: var(--bg-card);
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.55;
}
.spinner,
.spinner-sm {
  display: inline-block;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .75s linear infinite;
}
.spinner { width: 22px; height: 22px; }
.spinner-sm { width: 14px; height: 14px; }
@keyframes spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 1050px) {
  .logs-grid,
  .control-grid,
  .log-line {
    grid-template-columns: 1fr;
  }
}
</style>
