<template>
  <div class="java-diag-view">
    <div class="page-header">
      <div>
        <h1>Java 进程诊断</h1>
        <p class="subtitle">基于 SSH 远程执行 Arthas 和火焰图采样，适用于 Linux 主机上的 Java 进程分析。</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-outline" :disabled="hostLoading" @click="loadHosts">刷新主机</button>
        <button class="btn btn-outline" :disabled="!selectedHostId || procLoading" @click="loadProcesses">刷新进程</button>
      </div>
    </div>

    <div class="notice-grid">
      <div class="notice-card">
        <strong>Arthas</strong>
        <span>支持 `dashboard`、`jvm`、`thread`、`memory` 和自定义命令。</span>
      </div>
      <div class="notice-card">
        <strong>火焰图</strong>
        <span>对 Java 进程使用 async-profiler 生成 HTML 火焰图，并返回下载链接。</span>
      </div>
      <div class="notice-card">
        <strong>前置条件</strong>
        <span>主机需配置 SSH 凭证，远端建议具备 `curl` 或 `wget` 下载工具。</span>
      </div>
    </div>

    <div class="layout-grid">
      <section class="panel controls-panel">
        <div class="panel-title">目标主机</div>
        <label class="field">
          <span>主机</span>
          <select v-model="selectedHostId" class="form-input" :disabled="hostLoading">
            <option value="">请选择主机</option>
            <option v-for="host in hosts" :key="host.id" :value="host.id">
              {{ host.hostname }} / {{ host.ip }}{{ host.ssh_saved ? '' : '（未配置 SSH）' }}
            </option>
          </select>
        </label>
        <div v-if="selectedHost" class="host-meta">
          <div><span>平台</span><b>{{ selectedHost.platform || '-' }}</b></div>
          <div><span>系统</span><b>{{ selectedHost.os_version || '-' }}</b></div>
          <div><span>SSH</span><b>{{ selectedHost.ssh_saved ? '已配置' : '未配置' }}</b></div>
        </div>
        <div v-if="hostError" class="status-msg err">{{ hostError }}</div>
        <div v-if="procError" class="status-msg err">{{ procError }}</div>
      </section>

      <section class="panel process-panel">
        <div class="panel-head">
          <div class="panel-title">Java 进程</div>
          <span class="count-badge">{{ javaProcesses.length }} 个</span>
        </div>

        <div v-if="procLoading" class="empty-state">
          <div class="spinner"></div>
          <span>正在获取进程...</span>
        </div>
        <div v-else-if="!selectedHostId" class="empty-state">
          <span>请选择主机后再加载 Java 进程。</span>
        </div>
        <div v-else-if="!selectedHost?.ssh_saved" class="empty-state">
          <span>该主机未配置 SSH 凭证，无法执行 Java 诊断。</span>
        </div>
        <div v-else-if="!javaProcesses.length" class="empty-state">
          <span>未发现 Java 进程。</span>
        </div>
        <div v-else class="process-list">
          <button
            v-for="proc in javaProcesses"
            :key="proc.pid"
            type="button"
            class="process-card"
            :class="{ active: selectedPid === proc.pid }"
            @click="selectedPid = proc.pid"
          >
            <div class="process-top">
              <strong>{{ proc.comm || 'java' }}</strong>
              <span class="pid-badge">PID {{ proc.pid }}</span>
            </div>
            <div class="process-metrics">
              <span>CPU {{ proc.cpu.toFixed(1) }}%</span>
              <span>MEM {{ proc.mem.toFixed(1) }}%</span>
              <span>{{ proc.rss_mb }} MB</span>
            </div>
            <div class="process-args" :title="proc.args">{{ proc.args }}</div>
          </button>
        </div>
      </section>

      <section class="panel action-panel">
        <div class="panel-title">诊断操作</div>
        <div v-if="!selectedProcess" class="empty-state compact">
          <span>先选择一个 Java 进程。</span>
        </div>
        <template v-else>
          <div class="selected-proc">
            <div><span>当前进程</span><b>PID {{ selectedProcess.pid }}</b></div>
            <div><span>用户</span><b>{{ selectedProcess.user }}</b></div>
            <div><span>命令</span><b class="mono">{{ selectedProcess.comm }}</b></div>
          </div>

          <div class="action-tabs">
            <button class="tab-btn" :class="{ active: activeTool === 'arthas' }" @click="activeTool = 'arthas'">Arthas</button>
            <button class="tab-btn" :class="{ active: activeTool === 'flamegraph' }" @click="activeTool = 'flamegraph'">火焰图</button>
          </div>

          <div v-if="activeTool === 'arthas'" class="tool-form">
            <label class="field">
              <span>预设命令</span>
              <select v-model="arthasForm.preset" class="form-input">
                <option value="dashboard">dashboard</option>
                <option value="jvm">jvm</option>
                <option value="thread_top">thread -n 5</option>
                <option value="thread_blocked">thread -b</option>
                <option value="memory">memory</option>
                <option value="custom">自定义</option>
              </select>
            </label>
            <label v-if="arthasForm.preset === 'custom'" class="field">
              <span>自定义命令</span>
              <input v-model="arthasForm.command" class="form-input mono" placeholder="例如：thread -n 10" />
            </label>
            <button class="btn btn-primary" :disabled="arthasRunning" @click="runArthas">
              {{ arthasRunning ? '执行中...' : '执行 Arthas' }}
            </button>
          </div>

          <div v-else class="tool-form">
            <label class="field">
              <span>事件类型</span>
              <select v-model="flameForm.event" class="form-input">
                <option value="cpu">CPU</option>
                <option value="alloc">Alloc</option>
                <option value="lock">Lock</option>
                <option value="wall">Wall</option>
              </select>
            </label>
            <label class="field">
              <span>采样时长（秒）</span>
              <input v-model.number="flameForm.seconds" type="number" min="10" max="300" class="form-input" />
            </label>
            <button class="btn btn-primary" :disabled="flameRunning" @click="runFlamegraph">
              {{ flameRunning ? '采样中...' : '生成火焰图' }}
            </button>
          </div>
        </template>
      </section>
    </div>

    <section class="panel result-panel">
      <div class="panel-head">
        <div class="panel-title">结果</div>
        <button v-if="result?.download_url" class="btn btn-outline btn-sm" @click="openArtifact(result.download_url)">打开结果文件</button>
      </div>

      <div v-if="resultError" class="status-msg err">{{ resultError }}</div>
      <div v-else-if="result?.tool === 'arthas'" class="result-box">
        <div class="result-meta">
          <span>Arthas</span>
          <span>PID {{ result.pid }}</span>
          <span>{{ result.command }}</span>
        </div>
        <pre class="result-pre">{{ result.stdout || result.stderr || '(无输出)' }}</pre>
      </div>
      <div v-else-if="result?.tool === 'flamegraph'" class="result-box">
        <div class="result-meta">
          <span>火焰图</span>
          <span>PID {{ result.pid }}</span>
          <span>{{ result.event }} / {{ result.seconds }}s</span>
          <span>{{ humanSize(result.size_bytes) }}</span>
        </div>
        <div class="artifact-card">
          <div>火焰图已生成，可直接在浏览器打开或下载保存。</div>
          <button class="btn btn-primary btn-sm" @click="openArtifact(result.download_url)">打开火焰图</button>
        </div>
        <pre v-if="result.stdout" class="result-pre compact">{{ result.stdout }}</pre>
      </div>
      <div v-else class="empty-state compact">
        <span>选择进程并执行工具后，这里会显示结果。</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api/index.js'

const hosts = ref([])
const hostLoading = ref(false)
const hostError = ref('')
const selectedHostId = ref('')

const procLoading = ref(false)
const procError = ref('')
const allProcesses = ref([])
const selectedPid = ref(null)

const activeTool = ref('arthas')
const arthasRunning = ref(false)
const flameRunning = ref(false)
const result = ref(null)
const resultError = ref('')

const arthasForm = reactive({
  preset: 'dashboard',
  command: '',
})

const flameForm = reactive({
  event: 'cpu',
  seconds: 30,
})

const selectedHost = computed(() => hosts.value.find((item) => item.id === selectedHostId.value) || null)
const javaProcesses = computed(() => (
  allProcesses.value.filter((item) => item.service === 'Java' || /(^|\/)java$/i.test(item.comm || '') || /\bjava\b/i.test(item.args || ''))
))
const selectedProcess = computed(() => javaProcesses.value.find((item) => item.pid === selectedPid.value) || null)

async function loadHosts() {
  hostLoading.value = true
  hostError.value = ''
  try {
    const res = await api.getHosts()
    hosts.value = res.data || []
    if (!selectedHostId.value && hosts.value.length) selectedHostId.value = hosts.value[0].id
  } catch (e) {
    hostError.value = typeof e === 'string' ? e : '获取主机列表失败'
  } finally {
    hostLoading.value = false
  }
}

async function loadProcesses() {
  resultError.value = ''
  result.value = null
  procError.value = ''
  allProcesses.value = []
  selectedPid.value = null
  if (!selectedHostId.value) return
  if (!selectedHost.value?.ssh_saved) {
    procError.value = '该主机未配置 SSH 凭证'
    return
  }
  procLoading.value = true
  try {
    const res = await api.getHostProcesses(selectedHostId.value)
    allProcesses.value = res.data || []
    if (javaProcesses.value.length) selectedPid.value = javaProcesses.value[0].pid
  } catch (e) {
    procError.value = typeof e === 'string' ? e : '获取进程失败'
  } finally {
    procLoading.value = false
  }
}

async function runArthas() {
  resultError.value = ''
  result.value = null
  if (!selectedProcess.value) {
    resultError.value = '请先选择 Java 进程'
    return
  }
  if (arthasForm.preset === 'custom' && !String(arthasForm.command || '').trim()) {
    resultError.value = '自定义 Arthas 命令不能为空'
    return
  }
  arthasRunning.value = true
  try {
    result.value = await api.javaDiagArthas(selectedHostId.value, {
      pid: selectedProcess.value.pid,
      preset: arthasForm.preset,
      command: arthasForm.command,
    })
  } catch (e) {
    resultError.value = typeof e === 'string' ? e : 'Arthas 执行失败'
  } finally {
    arthasRunning.value = false
  }
}

async function runFlamegraph() {
  resultError.value = ''
  result.value = null
  if (!selectedProcess.value) {
    resultError.value = '请先选择 Java 进程'
    return
  }
  flameRunning.value = true
  try {
    result.value = await api.javaDiagFlamegraph(selectedHostId.value, {
      pid: selectedProcess.value.pid,
      event: flameForm.event,
      seconds: flameForm.seconds,
    })
  } catch (e) {
    resultError.value = typeof e === 'string' ? e : '火焰图生成失败'
  } finally {
    flameRunning.value = false
  }
}

function openArtifact(url) {
  if (!url) return
  window.open(url, '_blank', 'noopener')
}

function humanSize(size) {
  const value = Number(size || 0)
  if (!value) return '-'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

watch(selectedHostId, async () => {
  allProcesses.value = []
  selectedPid.value = null
  result.value = null
  resultError.value = ''
  procError.value = ''
  if (selectedHostId.value) await loadProcesses()
})

watch(selectedPid, () => {
  result.value = null
  resultError.value = ''
})

onMounted(loadHosts)
</script>

<style scoped>
.java-diag-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px;
  min-height: 100%;
  background: var(--bg-base);
  color: var(--text-primary);
}
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
.page-header h1 {
  margin: 0;
  font-size: 20px;
}
.subtitle {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 13px;
  line-height: 1.6;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.notice-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.notice-card,
.panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
}
.notice-card {
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.notice-card strong {
  font-size: 13px;
}
.notice-card span {
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}
.layout-grid {
  display: grid;
  grid-template-columns: 280px minmax(320px, 1fr) minmax(320px, 420px);
  gap: 16px;
  min-height: 420px;
}
.panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.panel-title {
  font-size: 14px;
  font-weight: 700;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.field span {
  color: var(--text-muted);
  font-size: 12px;
}
.form-input {
  width: 100%;
  box-sizing: border-box;
  min-height: 38px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--bg-input, var(--bg-base));
  color: var(--text-primary);
}
.host-meta,
.selected-proc {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 12px;
  border-radius: 12px;
  background: var(--bg-hover);
}
.host-meta div,
.selected-proc div {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.host-meta span,
.selected-proc span {
  color: var(--text-muted);
  font-size: 11px;
}
.host-meta b,
.selected-proc b {
  font-size: 13px;
}
.process-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: auto;
  padding-right: 4px;
}
.process-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  text-align: left;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-primary);
  cursor: pointer;
}
.process-card.active {
  border-color: rgba(56, 139, 253, 0.55);
  box-shadow: inset 0 0 0 1px rgba(56, 139, 253, 0.35);
}
.process-top,
.process-metrics,
.result-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.pid-badge,
.count-badge {
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(56, 139, 253, 0.12);
  color: var(--accent);
  font-size: 11px;
}
.process-metrics {
  color: var(--text-muted);
  font-size: 12px;
}
.process-args,
.mono {
  font-family: 'Cascadia Code', 'Consolas', monospace;
}
.process-args {
  color: var(--text-muted);
  font-size: 11.5px;
  line-height: 1.6;
  word-break: break-all;
}
.action-tabs {
  display: flex;
  gap: 8px;
}
.tab-btn,
.btn {
  border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer;
}
.tab-btn {
  padding: 8px 12px;
  background: var(--bg-base);
  color: var(--text-muted);
}
.tab-btn.active {
  color: var(--accent);
  border-color: rgba(56, 139, 253, 0.3);
  background: rgba(56, 139, 253, 0.08);
}
.tool-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 38px;
  padding: 0 14px;
}
.btn-primary {
  background: var(--accent);
  color: #fff;
}
.btn-outline {
  border-color: var(--border);
  background: transparent;
  color: var(--text-primary);
}
.btn-sm {
  min-height: 32px;
  padding: 0 12px;
  font-size: 12px;
}
.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.result-panel {
  min-height: 220px;
}
.result-box {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.result-meta {
  color: var(--text-muted);
  font-size: 12px;
}
.result-pre {
  margin: 0;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 420px;
  overflow: auto;
}
.result-pre.compact {
  max-height: 160px;
}
.artifact-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px;
  border-radius: 12px;
  border: 1px dashed rgba(56, 139, 253, 0.35);
  background: rgba(56, 139, 253, 0.05);
}
.status-msg {
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 12px;
}
.status-msg.err {
  background: rgba(248, 81, 73, 0.08);
  color: var(--error);
  border: 1px solid rgba(248, 81, 73, 0.2);
}
.empty-state {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-muted);
  text-align: center;
}
.empty-state.compact {
  min-height: 120px;
}
.spinner {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid rgba(56, 139, 253, 0.18);
  border-top-color: var(--accent);
  animation: spin .7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 1180px) {
  .notice-grid,
  .layout-grid {
    grid-template-columns: 1fr;
  }
}
</style>
