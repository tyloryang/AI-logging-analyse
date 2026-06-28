<template>
  <div class="ops-page">
    <header class="ops-header">
      <div>
        <h1>任务工作台</h1>
        <p>集中执行 SSH 运维命令，查看最近任务状态和主机输出。</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-outline" @click="refreshAll" :disabled="loading">
          <span v-if="loading" class="spinner-sm"></span>
          刷新
        </button>
        <button class="btn btn-primary" @click="submitRun" :disabled="running">
          <span v-if="running" class="spinner-sm"></span>
          执行任务
        </button>
      </div>
    </header>

    <section class="stat-grid">
      <div class="stat-card">
        <span>任务总数</span>
        <strong>{{ stats.total }}</strong>
      </div>
      <div class="stat-card">
        <span>运行中</span>
        <strong class="info">{{ stats.running }}</strong>
      </div>
      <div class="stat-card">
        <span>成功</span>
        <strong class="success">{{ stats.success }}</strong>
      </div>
      <div class="stat-card">
        <span>失败</span>
        <strong class="error">{{ stats.failed }}</strong>
      </div>
    </section>

    <div class="workbench-grid">
      <section class="panel run-panel">
        <div class="panel-head">
          <div>
            <h2>立即执行</h2>
            <span>选择目标主机或分组后执行命令</span>
          </div>
        </div>

        <div class="form-grid">
          <label>
            <span>任务名称</span>
            <input v-model.trim="runForm.name" placeholder="例如：检查磁盘空间" />
          </label>
          <label>
            <span>超时秒数</span>
            <input v-model.number="runForm.timeout" type="number" min="5" max="3600" />
          </label>
        </div>

        <label class="block-label">
          <span>执行命令</span>
          <textarea v-model="runForm.command" rows="5" spellcheck="false" placeholder="df -h"></textarea>
        </label>

        <div class="quick-section">
          <div class="quick-title">快捷命令</div>
          <div class="quick-list">
            <button
              v-for="tpl in commandTemplates"
              :key="tpl.name"
              class="quick-card"
              :class="{ active: runForm.command === tpl.command }"
              @click="applyTemplate(tpl)"
            >
              <strong>{{ tpl.name }}</strong>
              <code>{{ tpl.command }}</code>
            </button>
          </div>
        </div>

        <div class="target-box">
          <div class="target-tabs">
            <button :class="{ active: runForm.mode === 'group' }" @click="runForm.mode = 'group'">按分组</button>
            <button :class="{ active: runForm.mode === 'hosts' }" @click="runForm.mode = 'hosts'">指定主机</button>
          </div>

          <select v-if="runForm.mode === 'group'" v-model="runForm.host_group">
            <option value="">请选择主机分组</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">
              {{ g.name }}（{{ g.host_count || 0 }} 台）
            </option>
          </select>

          <div v-else class="host-picker">
            <input v-model.trim="hostSearch" placeholder="搜索主机名或 IP" />
            <div class="host-list">
              <label v-for="host in filteredHosts" :key="host.id" class="host-item">
                <input v-model="runForm.host_ids" type="checkbox" :value="host.id" />
                <span>{{ host.hostname || host.name || host.ip }}</span>
                <code>{{ host.ip }}</code>
              </label>
            </div>
          </div>
        </div>

        <p v-if="runError" class="error-box">{{ runError }}</p>
      </section>

      <section class="panel history-panel">
        <div class="panel-head">
          <div>
            <h2>最近任务</h2>
            <span>点击任务查看每台主机输出</span>
          </div>
          <select v-model="statusFilter">
            <option value="">全部状态</option>
            <option value="running">运行中</option>
            <option value="success">成功</option>
            <option value="partial">部分失败</option>
            <option value="failed">失败</option>
          </select>
        </div>

        <div v-if="loading && !tasks.length" class="empty-state">
          <span class="spinner"></span>
          <p>正在加载任务</p>
        </div>
        <div v-else-if="!visibleTasks.length" class="empty-state">
          <p>暂无任务记录</p>
        </div>
        <div v-else class="task-list">
          <button
            v-for="task in visibleTasks"
            :key="task.id"
            class="task-row"
            :class="{ active: detail?.id === task.id }"
            @click="openDetail(task.id)"
          >
            <span class="status-dot" :class="task.status"></span>
            <span class="task-main">
              <strong>{{ task.name }}</strong>
              <code>{{ task.command }}</code>
            </span>
            <span class="task-meta">
              <em>{{ task.target_count || 0 }} 台</em>
              <b :class="task.status">{{ statusText(task.status) }}</b>
              <small>{{ fmt(task.created_at) }}</small>
            </span>
          </button>
        </div>
      </section>
    </div>

    <section class="panel detail-panel">
      <div class="panel-head">
        <div>
          <h2>执行输出</h2>
          <span v-if="detail">{{ detail.name }} · {{ statusText(detail.status) }}</span>
          <span v-else>选择一个任务查看详情</span>
        </div>
        <button v-if="detail" class="btn btn-outline danger" @click="deleteCurrent">删除记录</button>
      </div>

      <div v-if="!detail" class="empty-state">
        <p>尚未选择任务</p>
      </div>
      <template v-else>
        <div class="detail-meta">
          <span><b>命令</b><code>{{ detail.command }}</code></span>
          <span><b>摘要</b>{{ detail.summary || '-' }}</span>
          <span><b>开始</b>{{ fmt(detail.started_at) }}</span>
          <span><b>结束</b>{{ fmt(detail.finished_at) }}</span>
        </div>
        <div class="result-grid">
          <article
            v-for="item in detail.host_results || []"
            :key="item.ip || item.hostname"
            class="result-card"
            :class="item.rc === 0 ? 'ok' : 'bad'"
          >
            <div class="result-head">
              <strong>{{ item.hostname || item.ip }}</strong>
              <code>{{ item.ip }}</code>
              <span>exit {{ item.rc }}</span>
            </div>
            <p v-if="item.error" class="host-error">{{ item.error }}</p>
            <pre v-if="item.stdout">{{ item.stdout }}</pre>
            <pre v-if="item.stderr" class="stderr">{{ item.stderr }}</pre>
          </article>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api/index.js'

const commandTemplates = [
  { name: '磁盘空间', command: 'df -h' },
  { name: '内存使用', command: 'free -m' },
  { name: '系统负载', command: 'uptime && top -b -n 1 | head -20' },
  { name: '最近错误', command: 'journalctl -p err -n 50 --no-pager' },
  { name: '网络端口', command: 'ss -tulnp | head -50' },
]

const tasks = ref([])
const groups = ref([])
const hosts = ref([])
const detail = ref(null)
const loading = ref(false)
const running = ref(false)
const runError = ref('')
const hostSearch = ref('')
const statusFilter = ref('')
const runForm = reactive({
  name: '',
  command: '',
  mode: 'group',
  host_group: '',
  host_ids: [],
  timeout: 60,
})

let pollTimer = null

const stats = computed(() => {
  const result = { total: tasks.value.length, running: 0, success: 0, failed: 0 }
  for (const task of tasks.value) {
    if (task.status === 'running' || task.status === 'pending') result.running += 1
    if (task.status === 'success') result.success += 1
    if (task.status === 'failed' || task.status === 'partial') result.failed += 1
  }
  return result
})

const visibleTasks = computed(() => {
  if (!statusFilter.value) return tasks.value
  return tasks.value.filter(task => task.status === statusFilter.value)
})

const filteredHosts = computed(() => {
  const q = hostSearch.value.toLowerCase()
  if (!q) return hosts.value
  return hosts.value.filter(host => {
    const text = `${host.hostname || ''} ${host.name || ''} ${host.ip || ''}`.toLowerCase()
    return text.includes(q)
  })
})

function statusText(status) {
  return {
    pending: '等待',
    running: '运行中',
    success: '成功',
    failed: '失败',
    partial: '部分失败',
    cancelled: '已取消',
  }[status] || status || '-'
}

function fmt(value) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : '-'
}

function applyTemplate(tpl) {
  runForm.name = tpl.name
  runForm.command = tpl.command
}

async function loadTasks() {
  tasks.value = await api.ansibleTasks().catch(() => [])
}

async function refreshAll() {
  loading.value = true
  try {
    const [taskList, groupResult, hostResult] = await Promise.all([
      api.ansibleTasks().catch(() => []),
      api.listGroups().catch(() => ({ data: [] })),
      api.getHosts().catch(() => ({ data: [] })),
    ])
    tasks.value = taskList
    groups.value = groupResult.data || []
    hosts.value = hostResult.data || []
  } finally {
    loading.value = false
  }
}

async function openDetail(id) {
  detail.value = await api.ansibleGetTask(id).catch(() => null)
}

function validateRun() {
  if (!runForm.name.trim()) return '请填写任务名称'
  if (!runForm.command.trim()) return '请填写执行命令'
  if (runForm.mode === 'group' && !runForm.host_group) return '请选择目标分组'
  if (runForm.mode === 'hosts' && !runForm.host_ids.length) return '请选择至少一台目标主机'
  return ''
}

async function submitRun() {
  runError.value = validateRun()
  if (runError.value) return
  running.value = true
  try {
    const payload = {
      name: runForm.name,
      command: runForm.command,
      timeout: runForm.timeout || 60,
      host_group: runForm.mode === 'group' ? runForm.host_group : '',
      host_ids: runForm.mode === 'hosts' ? runForm.host_ids : [],
    }
    const task = await api.ansibleCreateTask(payload)
    await loadTasks()
    await openDetail(task.id)
  } catch (error) {
    runError.value = typeof error === 'string' ? error : '任务提交失败'
  } finally {
    running.value = false
  }
}

async function deleteCurrent() {
  if (!detail.value) return
  if (!confirm('确认删除该任务记录？')) return
  await api.ansibleDeleteTask(detail.value.id).catch(() => {})
  detail.value = null
  await loadTasks()
}

onMounted(async () => {
  await refreshAll()
  pollTimer = setInterval(async () => {
    if (tasks.value.some(task => task.status === 'running' || task.status === 'pending')) {
      await loadTasks()
      if (detail.value?.id) await openDetail(detail.value.id)
    }
  }, 2500)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.ops-page {
  height: 100%;
  overflow: auto;
  padding: 24px;
  background: var(--bg-base);
  color: var(--text-primary);
}
.ops-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.ops-header h1 {
  font-size: 26px;
  margin: 0 0 4px;
}
.ops-header p,
.panel-head span {
  color: var(--text-muted);
  font-size: 13px;
}
.header-actions,
.panel-head,
.target-tabs,
.quick-list {
  display: flex;
  align-items: center;
  gap: 8px;
}
.btn {
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 8px 14px;
  cursor: pointer;
  font-size: 13px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
  background: var(--bg-card);
  border-color: var(--border);
  color: var(--text-primary);
}
.btn-outline.danger {
  color: var(--error);
  border-color: rgba(var(--error-rgb), .28);
}
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}
.stat-card,
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.stat-card {
  padding: 15px;
}
.stat-card span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}
.stat-card strong {
  display: block;
  margin-top: 6px;
  font-size: 26px;
  line-height: 1;
}
.success { color: var(--success); }
.error { color: var(--error); }
.info { color: var(--info); }
.workbench-grid {
  display: grid;
  grid-template-columns: minmax(360px, 44%) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}
.panel {
  padding: 16px;
}
.panel-head {
  justify-content: space-between;
  margin-bottom: 14px;
}
.panel-head h2 {
  margin: 0 0 2px;
  font-size: 16px;
  font-family: var(--font-sans);
}
input,
textarea,
select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 8px 10px;
  font-size: 13px;
  outline: none;
}
input:focus,
textarea:focus,
select:focus {
  border-color: var(--accent);
}
textarea,
code,
pre {
  font-family: var(--font-mono);
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 120px;
  gap: 10px;
}
label span,
.quick-title {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.block-label {
  display: block;
  margin-top: 12px;
}
.quick-section {
  margin-top: 12px;
}
.quick-list {
  align-items: stretch;
  flex-wrap: wrap;
}
.quick-card {
  flex: 1 1 140px;
  min-width: 130px;
  text-align: left;
  background: var(--bg-base);
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-radius: 7px;
  padding: 10px;
  cursor: pointer;
}
.quick-card.active {
  border-color: var(--accent);
  background: var(--accent-dim);
}
.quick-card strong,
.quick-card code {
  display: block;
}
.quick-card code {
  margin-top: 4px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.target-box {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-base);
}
.target-tabs {
  margin-bottom: 10px;
}
.target-tabs button {
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
  color: var(--text-secondary);
  padding: 5px 10px;
  cursor: pointer;
}
.target-tabs button.active {
  color: #fff;
  border-color: var(--accent);
  background: var(--accent);
}
.host-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.host-list {
  max-height: 210px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.host-item {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) 110px;
  gap: 8px;
  align-items: center;
  padding: 6px;
  border-radius: 6px;
}
.host-item:hover {
  background: var(--bg-hover);
}
.host-item input {
  width: auto;
}
.host-item code {
  color: var(--text-muted);
}
.error-box {
  margin-top: 10px;
  color: var(--error);
  background: rgba(var(--error-rgb), .08);
  border: 1px solid rgba(var(--error-rgb), .2);
  border-radius: 7px;
  padding: 8px 10px;
}
.history-panel {
  min-height: 560px;
}
.task-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  max-height: 508px;
  overflow: auto;
}
.task-row {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) 112px;
  gap: 10px;
  align-items: center;
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-base);
  color: var(--text-primary);
  padding: 10px;
  cursor: pointer;
}
.task-row.active,
.task-row:hover {
  border-color: var(--accent);
}
.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--text-muted);
}
.status-dot.running,
.status-dot.pending { background: var(--info); }
.status-dot.success { background: var(--success); }
.status-dot.failed,
.status-dot.partial { background: var(--error); }
.task-main {
  min-width: 0;
}
.task-main strong,
.task-main code,
.task-meta em,
.task-meta b,
.task-meta small {
  display: block;
}
.task-main strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-main code {
  color: var(--text-muted);
  margin-top: 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-meta {
  text-align: right;
  color: var(--text-muted);
}
.task-meta em {
  font-style: normal;
  font-size: 12px;
}
.task-meta b {
  font-size: 12px;
}
.task-meta small {
  font-size: 11px;
}
.detail-panel {
  margin-top: 14px;
}
.detail-meta {
  display: grid;
  grid-template-columns: 2fr repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.detail-meta span {
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 8px 10px;
  background: var(--bg-base);
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.detail-meta b {
  color: var(--text-muted);
  font-size: 11px;
  margin-right: 8px;
}
.result-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 10px;
}
.result-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-base);
}
.result-card.ok { border-color: rgba(var(--success-rgb), .28); }
.result-card.bad { border-color: rgba(var(--error-rgb), .28); }
.result-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 110px 70px;
  gap: 8px;
  padding: 9px 11px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
}
.result-head strong,
.result-head code {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.result-head span {
  text-align: right;
  color: var(--text-muted);
  font-size: 12px;
}
.host-error {
  color: var(--error);
  padding: 10px 12px 0;
}
pre {
  margin: 0;
  padding: 11px 12px;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.55;
}
pre.stderr {
  color: var(--warning);
}
.empty-state {
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  color: var(--text-muted);
}
.spinner,
.spinner-sm {
  display: inline-block;
  border-radius: 50%;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  animation: spin .75s linear infinite;
}
.spinner {
  width: 22px;
  height: 22px;
}
.spinner-sm {
  width: 14px;
  height: 14px;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 1100px) {
  .workbench-grid,
  .detail-meta,
  .stat-grid {
    grid-template-columns: 1fr;
  }
}
</style>
