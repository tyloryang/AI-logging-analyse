<template>
  <div class="visual-page">
    <header class="visual-header">
      <div>
        <h1>可视化</h1>
        <p>集中管理 Grafana 看板，支持发现、诊断和内嵌预览。</p>
      </div>
      <div class="actions">
        <button class="btn btn-outline" @click="testConnection" :disabled="testing">诊断</button>
        <button class="btn btn-outline" @click="discover" :disabled="discovering">发现看板</button>
        <button class="btn btn-primary" @click="loadBoards" :disabled="loading">刷新</button>
      </div>
    </header>

    <section class="summary-strip">
      <div>
        <span>Grafana URL</span>
        <strong>{{ grafanaUrl || '未配置' }}</strong>
      </div>
      <div>
        <span>看板数量</span>
        <strong>{{ boards.length }}</strong>
      </div>
      <div>
        <span>当前看板</span>
        <strong>{{ currentBoard?.title || '-' }}</strong>
      </div>
      <div>
        <span>时间范围</span>
        <strong>{{ rangeLabel }}</strong>
      </div>
    </section>

    <div v-if="message" class="message" :class="messageType">{{ message }}</div>

    <section v-if="diag" class="diag-panel">
      <div><span>健康检查</span><strong :class="diag.health_ok ? 'ok' : 'bad'">{{ diag.health_ok ? '正常' : diag.health_error || '异常' }}</strong></div>
      <div><span>API Key</span><strong>{{ diag.api_key_set ? '已配置' : '未配置' }}</strong></div>
      <div><span>看板搜索</span><strong :class="diag.search_ok ? 'ok' : 'bad'">{{ diag.search_ok ? `${diag.search_count || 0} 个` : diag.search_error || '异常' }}</strong></div>
      <button @click="diag = null">关闭</button>
    </section>

    <main class="visual-grid">
      <aside class="board-panel">
        <div class="panel-head">
          <h2>看板列表</h2>
          <span>{{ sourceLabel }}</span>
        </div>
        <div class="board-tools">
          <input v-model.trim="search" placeholder="搜索看板" />
          <select v-model="timeRange" @change="rebuildUrl">
            <option value="5m">最近 5 分钟</option>
            <option value="15m">最近 15 分钟</option>
            <option value="30m">最近 30 分钟</option>
            <option value="1h">最近 1 小时</option>
            <option value="6h">最近 6 小时</option>
            <option value="24h">最近 24 小时</option>
          </select>
        </div>

        <div v-if="loading && !boards.length" class="empty">
          <span class="spinner"></span>
          <p>正在加载看板</p>
        </div>
        <div v-else-if="!filteredBoards.length" class="empty">
          <p>暂无看板</p>
        </div>
        <div v-else class="board-list">
          <button
            v-for="board in filteredBoards"
            :key="board.id || board.uid || board.url"
            class="board-item"
            :class="{ active: selectedId === boardKey(board) }"
            @click="selectBoard(board)"
          >
            <span class="board-icon">▦</span>
            <span class="board-text">
              <strong>{{ board.title || board.id }}</strong>
              <small>{{ board.folder || (board.custom ? 'Custom' : 'Built-in') }}</small>
            </span>
            <a v-if="board.url" :href="board.url" target="_blank" @click.stop>打开</a>
          </button>
        </div>

        <form class="add-form" @submit.prevent="addBoard">
          <h3>添加自定义看板</h3>
          <input v-model.trim="newBoard.title" placeholder="看板标题" />
          <input v-model.trim="newBoard.uid" placeholder="Grafana UID，可选" />
          <input v-model.trim="newBoard.url" placeholder="完整 URL，可选" />
          <button class="btn btn-primary" :disabled="adding">添加</button>
        </form>
      </aside>

      <section class="preview-panel">
        <div class="preview-head">
          <div>
            <h2>{{ currentBoard?.title || '看板预览' }}</h2>
            <span>{{ currentBoard?.url || '选择一个看板开始预览' }}</span>
          </div>
          <div class="preview-actions">
            <label>
              <input v-model="kiosk" type="checkbox" @change="rebuildUrl" />
              Kiosk
            </label>
            <button class="btn btn-outline" @click="reloadFrame" :disabled="!frameUrl">重载</button>
          </div>
        </div>

        <div v-if="!grafanaUrl" class="preview-empty">
          <h3>未配置 Grafana</h3>
          <p>请先到系统配置中填写 Grafana URL 和 API Key。</p>
        </div>
        <div v-else-if="!frameUrl" class="preview-empty">
          <h3>未选择看板</h3>
          <p>从左侧选择一个看板进行预览。</p>
        </div>
        <div v-else class="frame-wrap">
          <div v-if="frameLoading" class="frame-loading">
            <span class="spinner"></span>
            <p>正在加载 Grafana</p>
          </div>
          <iframe
            :key="frameKey"
            :src="frameUrl"
            class="grafana-frame"
            allowfullscreen
            referrerpolicy="no-referrer"
            @load="frameLoading = false"
          ></iframe>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api/index.js'

const boards = ref([])
const grafanaUrl = ref('')
const selectedId = ref('')
const frameUrl = ref('')
const frameKey = ref(0)
const frameLoading = ref(false)
const loading = ref(false)
const discovering = ref(false)
const discovered = ref(false)
const testing = ref(false)
const adding = ref(false)
const search = ref('')
const timeRange = ref('1h')
const kiosk = ref(true)
const message = ref('')
const messageType = ref('info')
const diag = ref(null)
const newBoard = reactive({ title: '', uid: '', url: '' })

const currentBoard = computed(() => boards.value.find(board => boardKey(board) === selectedId.value) || null)
const sourceLabel = computed(() => discovered.value ? '来自 Grafana 自动发现' : '来自本地配置')
const rangeLabel = computed(() => ({
  '5m': '最近 5 分钟',
  '15m': '最近 15 分钟',
  '30m': '最近 30 分钟',
  '1h': '最近 1 小时',
  '6h': '最近 6 小时',
  '24h': '最近 24 小时',
}[timeRange.value] || timeRange.value))

const filteredBoards = computed(() => {
  const q = search.value.toLowerCase()
  if (!q) return boards.value
  return boards.value.filter(board => `${board.title || ''} ${board.folder || ''} ${board.uid || ''}`.toLowerCase().includes(q))
})

function boardKey(board) {
  return board.id || board.uid || board.url || board.title
}

function setMessage(text, type = 'info') {
  message.value = text
  messageType.value = type
  if (text) setTimeout(() => {
    if (message.value === text) message.value = ''
  }, 4500)
}

function rangeMs(range) {
  const unit = range.slice(-1)
  const value = Number(range.slice(0, -1)) || 1
  if (unit === 'm') return value * 60 * 1000
  if (unit === 'h') return value * 3600 * 1000
  return 3600 * 1000
}

function proxyUrl(rawUrl) {
  if (!rawUrl) return ''
  try {
    const url = new URL(rawUrl)
    return `/api/observability/grafana-proxy${url.pathname}`
  } catch {
    return rawUrl
  }
}

function rebuildUrl() {
  const board = currentBoard.value
  if (!board?.url) {
    frameUrl.value = ''
    return
  }
  const now = Date.now()
  const url = new URL(proxyUrl(board.url), window.location.origin)
  url.searchParams.set('from', String(now - rangeMs(timeRange.value)))
  url.searchParams.set('to', String(now))
  url.searchParams.set('refresh', '30s')
  if (kiosk.value) url.searchParams.set('kiosk', 'tv')
  frameUrl.value = url.toString()
  frameLoading.value = true
  frameKey.value += 1
}

function selectBoard(board) {
  selectedId.value = boardKey(board)
  rebuildUrl()
}

function selectFirst() {
  if (!boards.value.length) return
  const exists = boards.value.some(board => boardKey(board) === selectedId.value)
  if (!exists) selectedId.value = boardKey(boards.value[0])
  rebuildUrl()
}

function reloadFrame() {
  if (!frameUrl.value) return
  frameLoading.value = true
  frameKey.value += 1
}

async function loadBoards() {
  loading.value = true
  try {
    const data = await api.observabilityGrafanaBoards()
    boards.value = data.boards || []
    grafanaUrl.value = data.grafana_url || ''
    discovered.value = false
    selectFirst()
  } catch (error) {
    setMessage(String(error), 'error')
  } finally {
    loading.value = false
  }
}

async function discover() {
  discovering.value = true
  try {
    const data = await api.discoverGrafanaBoards()
    if (data.boards?.length) {
      boards.value = data.boards
      grafanaUrl.value = data.grafana_url || grafanaUrl.value
      discovered.value = true
      setMessage(`发现 ${data.boards.length} 个看板`, 'success')
      selectFirst()
    } else {
      setMessage(data.error || 'Grafana 未返回可用看板', 'warning')
      await loadBoards()
    }
  } catch (error) {
    setMessage(String(error), 'error')
  } finally {
    discovering.value = false
  }
}

async function testConnection() {
  testing.value = true
  try {
    diag.value = await api.testGrafanaConnection()
  } catch (error) {
    setMessage(String(error), 'error')
  } finally {
    testing.value = false
  }
}

async function addBoard() {
  if (!newBoard.title.trim()) {
    setMessage('请填写看板标题', 'warning')
    return
  }
  adding.value = true
  try {
    await api.addGrafanaBoard({ ...newBoard })
    newBoard.title = ''
    newBoard.uid = ''
    newBoard.url = ''
    await loadBoards()
    setMessage('看板已添加', 'success')
  } catch (error) {
    setMessage(String(error), 'error')
  } finally {
    adding.value = false
  }
}

onMounted(loadBoards)
</script>

<style scoped>
.visual-page {
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 22px;
  gap: 12px;
  background: var(--bg-base);
  color: var(--text-primary);
}
.visual-header,
.summary-strip,
.diag-panel,
.visual-grid,
.preview-head,
.panel-head,
.actions,
.preview-actions {
  display: flex;
  gap: 10px;
}
.visual-header {
  align-items: flex-start;
  justify-content: space-between;
}
h1 {
  font-size: 26px;
  margin: 0 0 4px;
}
p {
  margin: 0;
  color: var(--text-muted);
}
.actions {
  align-items: center;
}
.btn {
  border: 1px solid transparent;
  border-radius: 7px;
  padding: 7px 13px;
  cursor: pointer;
  background: var(--bg-card);
  color: var(--text-primary);
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
.summary-strip {
  display: grid;
  grid-template-columns: 2fr repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.summary-strip div,
.diag-panel,
.board-panel,
.preview-panel {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.summary-strip div {
  padding: 12px;
  min-width: 0;
}
.summary-strip span,
.panel-head span,
.preview-head span {
  display: block;
  color: var(--text-muted);
  font-size: 12px;
}
.summary-strip strong {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.message {
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 13px;
}
.message.success { background: rgba(var(--success-rgb), .1); color: var(--success); }
.message.warning { background: rgba(var(--warning-rgb), .1); color: var(--warning); }
.message.error { background: rgba(var(--error-rgb), .1); color: var(--error); }
.diag-panel {
  align-items: center;
  padding: 10px 12px;
}
.diag-panel div {
  display: flex;
  gap: 8px;
}
.diag-panel span {
  color: var(--text-muted);
}
.diag-panel .ok { color: var(--success); }
.diag-panel .bad { color: var(--error); }
.diag-panel button {
  margin-left: auto;
  border: 0;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
}
.visual-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
}
.board-panel,
.preview-panel {
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.board-panel {
  padding: 14px;
}
.panel-head,
.preview-head {
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}
h2 {
  font-family: var(--font-sans);
  font-size: 16px;
  margin: 0 0 2px;
}
.board-tools {
  display: grid;
  grid-template-columns: 1fr 132px;
  gap: 8px;
  margin-bottom: 10px;
}
input,
select {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-input);
  color: var(--text-primary);
  padding: 8px 9px;
  outline: none;
}
.board-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.board-item {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  gap: 9px;
  align-items: center;
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-primary);
  border-radius: 8px;
  padding: 9px;
  text-align: left;
  cursor: pointer;
}
.board-item:hover,
.board-item.active {
  border-color: var(--accent);
}
.board-icon {
  color: var(--accent);
}
.board-text {
  min-width: 0;
}
.board-text strong,
.board-text small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.board-text small {
  color: var(--text-muted);
}
.board-item a {
  color: var(--accent);
  font-size: 12px;
  text-decoration: none;
}
.add-form {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: grid;
  gap: 8px;
}
.add-form h3 {
  font-family: var(--font-sans);
  font-size: 13px;
  margin: 0;
}
.preview-panel {
  position: relative;
}
.preview-head {
  padding: 14px 16px 0;
  flex-shrink: 0;
}
.preview-actions {
  align-items: center;
}
.preview-actions label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 12px;
}
.preview-actions input {
  width: auto;
}
.frame-wrap {
  flex: 1;
  min-height: 0;
  position: relative;
  background: var(--bg-base);
  margin-top: 10px;
}
.grafana-frame {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}
.preview-empty,
.empty,
.frame-loading {
  flex: 1;
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 8px;
  color: var(--text-muted);
}
.frame-loading {
  position: absolute;
  inset: 0;
  background: var(--bg-base);
  z-index: 2;
}
.spinner {
  width: 22px;
  height: 22px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .75s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
@media (max-width: 1100px) {
  .visual-page {
    overflow: auto;
  }
  .visual-grid,
  .summary-strip {
    grid-template-columns: 1fr;
  }
  .preview-panel {
    min-height: 620px;
  }
}
</style>
