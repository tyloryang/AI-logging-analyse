<template>
  <div class="cc-layout">

    <!-- 顶部标题栏 -->
    <div class="cc-titlebar">
      <div class="cc-brand">
        <span class="cc-logo">◈</span>
        <span class="cc-name">Claude Code 工作台</span>
        <span class="cc-powered">by cc-haha</span>
      </div>

      <!-- 服务状态 + 控制 -->
      <div class="cc-server-ctrl">
        <span class="cc-status-dot" :class="serverReachable ? 'dot-ok' : serverRunning ? 'dot-warn' : 'dot-off'"></span>
        <span class="cc-status-txt">{{ serverReachable ? '运行中' : serverRunning ? '启动中...' : '未启动' }}</span>
        <button v-if="!serverRunning" class="cc-btn cc-btn-start" @click="startServer" :disabled="starting">
          {{ starting ? '启动中...' : '▶ 启动服务' }}
        </button>
        <button v-else class="cc-btn cc-btn-stop" @click="stopServer">■ 停止</button>
        <button class="cc-btn cc-btn-settings" @click="showSetup = !showSetup">⚙</button>
      </div>

      <!-- Tab 栏 -->
      <div class="cc-tabs" v-if="sessions.length">
        <div v-for="s in sessions" :key="s.id"
          class="cc-tab" :class="{ active: activeSessionId === s.id }"
          @click="switchSession(s.id)">
          <span class="cc-tab-icon">{{ s.project ? '📁' : '💬' }}</span>
          <span class="cc-tab-title">{{ s.title || '新对话' }}</span>
          <span class="cc-tab-close" @click.stop="deleteSession(s.id)">✕</span>
        </div>
        <button class="cc-tab-new" @click="newSession" title="新建会话">＋</button>
      </div>
    </div>

    <!-- 配置提示 -->
    <div v-if="showSetup || !ccHahaDir" class="cc-setup-panel">
      <div class="cc-setup-title">⚙ 配置 cc-haha 路径</div>
      <div class="cc-setup-desc">
        cc-haha 是 Claude Code 桌面工作台，需要提前克隆项目并安装依赖。<br>
        <a href="https://github.com/NanmiCoder/cc-haha" target="_blank">github.com/NanmiCoder/cc-haha</a>
      </div>
      <div class="cc-setup-steps">
        <pre class="cc-setup-code">git clone https://github.com/NanmiCoder/cc-haha.git
cd cc-haha
bun install</pre>
      </div>
      <label class="cc-setup-field">
        <span>cc-haha 项目目录</span>
        <input v-model="ccHahaDirInput" class="cc-input" placeholder="/path/to/cc-haha 或 D:\cc-haha" />
        <button class="cc-btn cc-btn-primary" @click="saveCcHahaDir">保存</button>
      </label>
      <label class="cc-setup-field" style="margin-top:8px">
        <span>端口（默认 35729）</span>
        <input v-model.number="ccPort" type="number" class="cc-input" style="width:100px" />
      </label>
    </div>

    <!-- 主体：无服务提示 -->
    <div v-if="!serverReachable && !showSetup" class="cc-offline">
      <div class="cc-offline-icon">◈</div>
      <div class="cc-offline-title">cc-haha 服务未启动</div>
      <div class="cc-offline-sub">启动服务后即可使用真实的 Claude Code 对话引擎</div>
      <button class="cc-btn cc-btn-primary cc-btn-lg" @click="startServer" :disabled="starting">
        {{ starting ? '启动中...' : '▶ 启动 cc-haha 服务' }}
      </button>
      <div v-if="startError" class="cc-error">{{ startError }}</div>
    </div>

    <!-- 主体：左右分栏 -->
    <div v-else-if="serverReachable" class="cc-body">

      <!-- 左侧：会话列表 -->
      <aside class="cc-sidebar">
        <div class="cc-sb-header">
          <span class="cc-sb-title">对话历史</span>
          <button class="cc-sb-new" @click="newSession">＋ 新建</button>
        </div>
        <div class="cc-sb-list">
          <div v-if="!sessions.length" class="cc-sb-empty">暂无会话</div>
          <div v-for="s in sessions" :key="s.id"
            class="cc-sb-item" :class="{ active: activeSessionId === s.id }"
            @click="switchSession(s.id)">
            <div class="cc-sb-item-title">{{ s.title || '未命名' }}</div>
            <div class="cc-sb-item-meta">{{ formatTime(s.modifiedAt || s.createdAt) }}</div>
          </div>
        </div>
      </aside>

      <!-- 右侧：对话主区 -->
      <main class="cc-chat-area">
        <div v-if="!activeSessionId" class="cc-chat-empty">
          <div class="cc-chat-empty-icon">◈</div>
          <div>点击「＋ 新建」开始一个 Claude Code 对话</div>
        </div>

        <template v-else>
          <!-- 会话头部 -->
          <div class="cc-chat-header">
            <div class="cc-chat-title">{{ activeSession?.title || '未命名对话' }}</div>
            <div class="cc-chat-meta">
              <span v-if="connState === 'connected'" class="cc-conn-ok">● 已连接</span>
              <span v-else-if="connState === 'connecting'" class="cc-conn-warn">◌ 连接中...</span>
              <span v-else class="cc-conn-off">○ 未连接</span>
              <span v-if="tokenUsage.input_tokens || tokenUsage.output_tokens" class="cc-token">
                ↑{{ tokenUsage.input_tokens }} ↓{{ tokenUsage.output_tokens }}
              </span>
              <span v-if="elapsedSeconds > 0" class="cc-elapsed">{{ elapsedSeconds }}s</span>
            </div>
          </div>

          <!-- 消息列表 -->
          <div class="cc-messages" ref="msgListRef">
            <div v-for="(msg, i) in messages" :key="i" class="cc-msg" :class="'msg-' + msg.type">

              <!-- 用户消息 -->
              <div v-if="msg.type === 'user'" class="cc-msg-user">
                <span class="cc-msg-user-label">你</span>
                <div class="cc-msg-user-body">{{ msg.text }}</div>
              </div>

              <!-- AI 消息 -->
              <div v-else-if="msg.type === 'assistant'" class="cc-msg-ai">
                <span class="cc-msg-ai-label">Claude</span>
                <div class="cc-msg-ai-body" v-html="renderMd(msg.text)"></div>
              </div>

              <!-- 工具调用 -->
              <div v-else-if="msg.type === 'tool_use'" class="cc-tool-call">
                <div class="cc-tool-header" @click="msg._expanded = !msg._expanded">
                  <span class="cc-tool-icon">⚡</span>
                  <span class="cc-tool-name">{{ msg.toolName }}</span>
                  <span class="cc-tool-toggle">{{ msg._expanded ? '▴' : '▾' }}</span>
                </div>
                <div v-if="msg._expanded" class="cc-tool-body">
                  <pre class="cc-tool-input">{{ JSON.stringify(msg.input, null, 2) }}</pre>
                  <div v-if="msg.output" class="cc-tool-output">
                    <div class="cc-tool-output-label">结果</div>
                    <pre>{{ truncate(msg.output) }}</pre>
                  </div>
                </div>
              </div>

              <!-- Thinking -->
              <div v-else-if="msg.type === 'thinking'" class="cc-thinking">
                <span class="cc-thinking-icon">💭</span>
                <div class="cc-thinking-text">{{ truncate(msg.text, 200) }}</div>
              </div>
            </div>

            <!-- 流式输出 -->
            <div v-if="streamingText" class="cc-msg msg-assistant">
              <div class="cc-msg-ai">
                <span class="cc-msg-ai-label">Claude</span>
                <div class="cc-msg-ai-body" v-html="renderMd(streamingText)"></div>
                <span class="cc-stream-cursor">▌</span>
              </div>
            </div>

            <!-- 工具执行中 -->
            <div v-if="activeToolName" class="cc-tool-running">
              <div class="spinner" style="width:12px;height:12px;border-width:2px"></div>
              <span>{{ activeToolName }}{{ streamingToolInput ? ': ' + truncate(streamingToolInput, 60) : '' }}</span>
            </div>

            <!-- 状态动词 -->
            <div v-if="chatState === 'thinking' || chatState === 'generating'" class="cc-status-verb">
              <div class="cc-status-spinner"></div>
              <span>{{ statusVerb || (chatState === 'thinking' ? '思考中' : '生成中') }}...</span>
            </div>
          </div>

          <!-- 权限审批 -->
          <div v-if="pendingPermission" class="cc-permission-dialog">
            <div class="cc-perm-header">
              <span class="cc-perm-icon">⚠</span>
              <span>Claude Code 请求权限</span>
            </div>
            <div class="cc-perm-tool">工具: <strong>{{ pendingPermission.toolName }}</strong></div>
            <div class="cc-perm-desc">{{ pendingPermission.description }}</div>
            <pre v-if="pendingPermission.input" class="cc-perm-input">{{ JSON.stringify(pendingPermission.input, null, 2) }}</pre>
            <div class="cc-perm-actions">
              <button class="cc-btn cc-btn-deny" @click="replyPermission(false)">拒绝</button>
              <button class="cc-btn cc-btn-allow" @click="replyPermission(true)">允许一次</button>
              <button class="cc-btn cc-btn-allow-always" @click="replyPermission(true, true)">始终允许</button>
            </div>
          </div>

          <!-- 输入框 -->
          <div class="cc-composer">
            <div class="cc-composer-inner">
              <textarea
                v-model="inputText"
                class="cc-input-area"
                :placeholder="chatState !== 'idle' ? 'Claude 正在工作中...' : '发送消息给 Claude Code（支持 /slash 命令）'"
                :disabled="chatState !== 'idle'"
                rows="1"
                ref="inputRef"
                @keydown.enter.exact.prevent="sendMessage"
                @input="autoResize"
              ></textarea>
              <div class="cc-composer-actions">
                <button v-if="chatState !== 'idle'" class="cc-btn cc-btn-stop" @click="stopGeneration">⬛ 停止</button>
                <button v-else class="cc-btn cc-btn-send" :disabled="!inputText.trim()" @click="sendMessage">发送</button>
              </div>
            </div>
            <!-- Slash 命令提示 -->
            <div v-if="slashCommands.length && inputText.startsWith('/')" class="cc-slash-menu">
              <div v-for="cmd in filteredSlashCommands" :key="cmd.name"
                class="cc-slash-item" @click="insertSlash(cmd)">
                <span class="cc-slash-name">/{{ cmd.name }}</span>
                <span class="cc-slash-desc">{{ cmd.description }}</span>
              </div>
            </div>
          </div>
        </template>
      </main>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { api } from '../api/index.js'

// ── 服务状态 ───────────────────────────────────────────────────────────────────
const serverRunning   = ref(false)
const serverReachable = ref(false)
const starting        = ref(false)
const startError      = ref('')
const showSetup       = ref(false)
const ccHahaDir       = ref(localStorage.getItem('cc_haha_dir') || '')
const ccHahaDirInput  = ref(ccHahaDir.value)
const ccPort          = ref(Number(localStorage.getItem('cc_haha_port') || '35729'))

function saveCcHahaDir() {
  ccHahaDir.value = ccHahaDirInput.value
  localStorage.setItem('cc_haha_dir', ccHahaDir.value)
  localStorage.setItem('cc_haha_port', String(ccPort.value))
  showSetup.value = false
}

async function checkStatus() {
  try {
    const r = await api.ccHahaStatus()
    serverRunning.value   = r.running
    serverReachable.value = r.reachable
  } catch {}
}

async function startServer() {
  if (!ccHahaDir.value) { showSetup.value = true; return }
  starting.value = true; startError.value = ''
  try {
    await api.ccHahaStart()
    await checkStatus()
    if (serverReachable.value) await loadSessions()
  } catch (e) { startError.value = String(e) }
  finally { starting.value = false }
}

async function stopServer() {
  try { await api.ccHahaStop() } catch {}
  serverRunning.value = false; serverReachable.value = false
  disconnectWs()
}

// ── 会话管理 ───────────────────────────────────────────────────────────────────
const sessions       = ref([])
const activeSessionId = ref('')

const activeSession = computed(() => sessions.value.find(s => s.id === activeSessionId.value) || null)

async function loadSessions() {
  try {
    const r = await api.ccHahaProxy('GET', 'sessions')
    sessions.value = r?.sessions || r || []
  } catch {}
}

async function newSession() {
  try {
    const r = await api.ccHahaProxy('POST', 'sessions', { title: '新对话' })
    await loadSessions()
    if (r?.id) switchSession(r.id)
  } catch {}
}

async function deleteSession(id) {
  if (!confirm('删除此会话？')) return
  try {
    await api.ccHahaProxy('DELETE', `sessions/${id}`)
    await loadSessions()
    if (activeSessionId.value === id) {
      activeSessionId.value = sessions.value[0]?.id || ''
      if (activeSessionId.value) connectWs(activeSessionId.value)
    }
  } catch {}
}

function switchSession(id) {
  if (activeSessionId.value === id) return
  disconnectWs()
  activeSessionId.value = id
  resetChatState()
  connectWs(id)
  loadHistoryMessages(id)
}

async function loadHistoryMessages(sessionId) {
  try {
    const r = await api.ccHahaProxy('GET', `sessions/${sessionId}/messages`)
    const msgs = r?.messages || r || []
    messages.value = msgs.map(m => ({
      type: m.role === 'user' ? 'user' : 'assistant',
      text: Array.isArray(m.content)
        ? m.content.filter(c => c.type === 'text').map(c => c.text).join('')
        : String(m.content || ''),
      _expanded: false,
    }))
    scrollToBottom()
  } catch {}
}

// ── WebSocket 连接 ─────────────────────────────────────────────────────────────
const connState        = ref('disconnected')
const messages         = ref([])
const streamingText    = ref('')
const streamingToolInput = ref('')
const activeToolName   = ref('')
const chatState        = ref('idle')
const statusVerb       = ref('')
const tokenUsage       = ref({ input_tokens: 0, output_tokens: 0 })
const elapsedSeconds   = ref(0)
const pendingPermission = ref(null)
const slashCommands    = ref([])

let _ws = null
let _elapsed = null

function connectWs(sessionId) {
  disconnectWs()
  connState.value = 'connecting'
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  _ws = new WebSocket(`${proto}://${location.host}/api/cc-haha/ws/${sessionId}`)

  _ws.onopen = () => {
    connState.value = 'connected'
  }
  _ws.onclose = () => {
    connState.value = 'disconnected'
    _ws = null
  }
  _ws.onerror = () => {
    connState.value = 'disconnected'
  }
  _ws.onmessage = (ev) => {
    try { handleWsMessage(JSON.parse(ev.data)) } catch {}
  }
}

function disconnectWs() {
  if (_ws) { _ws.close(); _ws = null }
  clearInterval(_elapsed); _elapsed = null
  connState.value = 'disconnected'
}

function resetChatState() {
  messages.value = []
  streamingText.value = ''
  streamingToolInput.value = ''
  activeToolName.value = ''
  chatState.value = 'idle'
  statusVerb.value = ''
  pendingPermission.value = null
  elapsedSeconds.value = 0
  clearInterval(_elapsed)
}

function handleWsMessage(msg) {
  switch (msg.type) {
    case 'connected':
      if (msg.slashCommands) slashCommands.value = msg.slashCommands
      break

    case 'status':
      chatState.value = msg.state || chatState.value
      if (msg.state === 'thinking' || msg.state === 'generating') startElapsed()
      if (msg.state === 'idle') stopElapsed()
      break

    case 'content_start':
      chatState.value = 'generating'
      streamingText.value = ''
      break

    case 'content_delta':
      if (msg.delta?.type === 'text_delta') {
        streamingText.value += msg.delta.text || ''
        scrollToBottom()
      }
      break

    case 'thinking':
      messages.value.push({ type: 'thinking', text: msg.thinking || '', _expanded: false })
      break

    case 'tool_use_start':
      activeToolName.value = msg.name || 'tool'
      streamingToolInput.value = ''
      chatState.value = 'generating'
      break

    case 'tool_input_delta':
      streamingToolInput.value += msg.delta || ''
      break

    case 'tool_use_complete': {
      const toolMsg = {
        type: 'tool_use',
        toolName: msg.name || activeToolName.value,
        input: msg.input || {},
        output: '',
        _expanded: false,
      }
      messages.value.push(toolMsg)
      activeToolName.value = ''
      streamingToolInput.value = ''
      break
    }

    case 'tool_result': {
      const last = [...messages.value].reverse().find(m => m.type === 'tool_use' && m.toolName === msg.name)
      if (last) last.output = typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content)
      break
    }

    case 'message_complete':
      if (streamingText.value) {
        messages.value.push({ type: 'assistant', text: streamingText.value, _expanded: false })
        streamingText.value = ''
      }
      if (msg.usage) tokenUsage.value = msg.usage
      chatState.value = 'idle'
      stopElapsed()
      scrollToBottom()
      // 更新会话标题
      if (msg.sessionTitle) {
        const s = sessions.value.find(s => s.id === activeSessionId.value)
        if (s) s.title = msg.sessionTitle
      }
      break

    case 'session_title_updated':
      if (msg.sessionId === activeSessionId.value) {
        const s = sessions.value.find(s => s.id === msg.sessionId)
        if (s) s.title = msg.title
      }
      break

    case 'permission_request':
      pendingPermission.value = {
        requestId: msg.requestId,
        toolName: msg.toolName,
        toolUseId: msg.toolUseId,
        input: msg.input,
        description: msg.description,
      }
      break

    case 'error':
      chatState.value = 'idle'
      stopElapsed()
      messages.value.push({
        type: 'assistant',
        text: `❌ 错误：${msg.message || '未知错误'}`,
        _expanded: false,
      })
      break
  }
}

function startElapsed() {
  if (_elapsed) return
  const start = Date.now()
  _elapsed = setInterval(() => {
    elapsedSeconds.value = Math.floor((Date.now() - start) / 1000)
  }, 1000)
}
function stopElapsed() {
  clearInterval(_elapsed); _elapsed = null
}

// ── 发送消息 ───────────────────────────────────────────────────────────────────
const inputText = ref('')
const inputRef  = ref(null)
const msgListRef = ref(null)

function sendMessage() {
  const text = inputText.value.trim()
  if (!text || chatState.value !== 'idle' || !_ws) return
  messages.value.push({ type: 'user', text, _expanded: false })
  inputText.value = ''
  if (inputRef.value) inputRef.value.style.height = 'auto'
  _ws.send(JSON.stringify({ type: 'user_message', content: text }))
  chatState.value = 'thinking'
  startElapsed()
  scrollToBottom()
}

function stopGeneration() {
  if (_ws) _ws.send(JSON.stringify({ type: 'stop_generation' }))
  chatState.value = 'idle'
  stopElapsed()
}

function replyPermission(allowed, always = false) {
  if (!_ws || !pendingPermission.value) return
  _ws.send(JSON.stringify({
    type: 'permission_response',
    requestId: pendingPermission.value.requestId,
    allowed,
    rule: always ? 'allow_always' : 'allow_once',
  }))
  pendingPermission.value = null
}

// ── Slash 命令 ─────────────────────────────────────────────────────────────────
const filteredSlashCommands = computed(() => {
  const q = inputText.value.slice(1).toLowerCase()
  return slashCommands.value.filter(c => c.name.startsWith(q)).slice(0, 6)
})

function insertSlash(cmd) {
  inputText.value = `/${cmd.name} `
  nextTick(() => inputRef.value?.focus())
}

// ── 工具函数 ───────────────────────────────────────────────────────────────────
function renderMd(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```([\s\S]*?)```/g, '<pre class="cc-code-block">$1</pre>')
    .replace(/`([^`]+)`/g, '<code class="cc-inline-code">$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

function truncate(text, max = 500) {
  const s = String(text || '')
  return s.length > max ? s.slice(0, max) + '…' : s
}

function formatTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return isNaN(d) ? '' : d.toLocaleDateString() + ' ' + d.toLocaleTimeString().slice(0, 5)
}

function scrollToBottom() {
  nextTick(() => {
    if (msgListRef.value) msgListRef.value.scrollTop = msgListRef.value.scrollHeight
  })
}

function autoResize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// ── 生命周期 ───────────────────────────────────────────────────────────────────
let _statusTimer = null
onMounted(async () => {
  await checkStatus()
  if (serverReachable.value) await loadSessions()
  _statusTimer = setInterval(checkStatus, 10000)
})
onUnmounted(() => {
  disconnectWs()
  clearInterval(_statusTimer)
})
</script>

<style scoped>
.cc-layout { display: flex; flex-direction: column; height: 100%; overflow: hidden; background: #0d1117; color: #c9d1d9; font-size: 13px; }

/* Titlebar */
.cc-titlebar { display: flex; align-items: center; gap: 14px; padding: 0 14px; height: 48px; flex-shrink: 0; background: #161b22; border-bottom: 1px solid #30363d; flex-wrap: wrap; }
.cc-brand    { display: flex; align-items: center; gap: 7px; }
.cc-logo     { font-size: 18px; color: #58a6ff; }
.cc-name     { font-size: 14px; font-weight: 700; color: #e6edf3; }
.cc-powered  { font-size: 10px; color: #484f58; padding: 1px 6px; background: #21262d; border-radius: 4px; }

/* Server ctrl */
.cc-server-ctrl { display: flex; align-items: center; gap: 7px; margin-left: auto; }
.cc-status-dot   { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-ok  { background: #3fb950; }
.dot-warn { background: #f0883e; animation: pulse 1s infinite; }
.dot-off { background: #484f58; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.cc-status-txt { font-size: 12px; color: #8b949e; }

/* Tabs */
.cc-tabs    { display: flex; align-items: stretch; gap: 0; overflow-x: auto; flex: 1; }
.cc-tab     { display: flex; align-items: center; gap: 6px; padding: 0 12px; min-width: 120px; cursor: pointer; border-bottom: 2px solid transparent; color: #8b949e; font-size: 12px; transition: .12s; }
.cc-tab:hover { background: #21262d; color: #c9d1d9; }
.cc-tab.active { border-bottom-color: #58a6ff; color: #c9d1d9; }
.cc-tab-icon  { font-size: 13px; }
.cc-tab-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cc-tab-close { opacity: 0; font-size: 11px; padding: 1px 3px; }
.cc-tab:hover .cc-tab-close { opacity: 1; }
.cc-tab-close:hover { color: #f85149; }
.cc-tab-new { padding: 0 12px; cursor: pointer; color: #484f58; font-size: 18px; border: none; background: transparent; }
.cc-tab-new:hover { color: #58a6ff; }

/* Buttons */
.cc-btn { padding: 4px 12px; border-radius: 6px; border: 1px solid; cursor: pointer; font-size: 12px; font-weight: 600; transition: .12s; }
.cc-btn-start { border-color: #238636; background: rgba(35,134,54,.15); color: #3fb950; }
.cc-btn-start:hover { background: rgba(35,134,54,.3); }
.cc-btn-stop  { border-color: rgba(248,81,73,.3); background: rgba(248,81,73,.1); color: #f85149; }
.cc-btn-stop:hover { background: rgba(248,81,73,.2); }
.cc-btn-settings { border-color: #30363d; background: transparent; color: #8b949e; }
.cc-btn-settings:hover { border-color: #58a6ff; color: #58a6ff; }
.cc-btn-primary { border-color: #58a6ff; background: rgba(88,166,255,.15); color: #58a6ff; }
.cc-btn-primary:hover { background: rgba(88,166,255,.25); }
.cc-btn-lg { padding: 10px 28px; font-size: 14px; }
.cc-btn-send  { border-color: #58a6ff; background: rgba(88,166,255,.15); color: #58a6ff; }
.cc-btn-send:hover:not(:disabled) { background: rgba(88,166,255,.3); }
.cc-btn-send:disabled { opacity: .4; cursor: not-allowed; }
.cc-btn-allow { border-color: #238636; background: rgba(35,134,54,.15); color: #3fb950; }
.cc-btn-allow-always { border-color: #1f6feb; background: rgba(31,111,235,.15); color: #58a6ff; }
.cc-btn-deny  { border-color: #f85149; background: rgba(248,81,73,.1); color: #f85149; }

/* Setup panel */
.cc-setup-panel { background: #161b22; border-bottom: 1px solid #30363d; padding: 14px 18px; flex-shrink: 0; }
.cc-setup-title { font-size: 13px; font-weight: 700; color: #e6edf3; margin-bottom: 5px; }
.cc-setup-desc  { font-size: 12px; color: #8b949e; margin-bottom: 10px; }
.cc-setup-desc a { color: #58a6ff; }
.cc-setup-code  { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 8px 12px; font-family: monospace; font-size: 12px; color: #c9d1d9; margin-bottom: 10px; }
.cc-setup-field { display: flex; align-items: center; gap: 8px; }
.cc-setup-field span { font-size: 12px; color: #8b949e; white-space: nowrap; }
.cc-input { padding: 5px 9px; border-radius: 5px; border: 1px solid #30363d; background: #0d1117; color: #c9d1d9; font-size: 12px; flex: 1; }
.cc-input:focus { outline: none; border-color: #58a6ff; }

/* Offline */
.cc-offline { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; }
.cc-offline-icon  { font-size: 48px; color: #30363d; }
.cc-offline-title { font-size: 20px; font-weight: 700; color: #8b949e; }
.cc-offline-sub   { font-size: 13px; color: #484f58; }
.cc-error { font-size: 12px; color: #f85149; max-width: 400px; text-align: center; }

/* Body */
.cc-body { flex: 1; display: flex; overflow: hidden; min-height: 0; }

/* Sidebar */
.cc-sidebar { width: 220px; flex-shrink: 0; border-right: 1px solid #30363d; background: #161b22; display: flex; flex-direction: column; overflow: hidden; }
.cc-sb-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border-bottom: 1px solid #30363d; flex-shrink: 0; }
.cc-sb-title  { font-size: 11px; font-weight: 700; color: #8b949e; text-transform: uppercase; letter-spacing: .05em; }
.cc-sb-new    { padding: 2px 8px; border-radius: 4px; border: 1px solid #30363d; background: transparent; color: #8b949e; cursor: pointer; font-size: 12px; }
.cc-sb-new:hover { border-color: #58a6ff; color: #58a6ff; }
.cc-sb-list  { flex: 1; overflow-y: auto; }
.cc-sb-empty { font-size: 12px; color: #484f58; padding: 16px 12px; text-align: center; }
.cc-sb-item  { padding: 10px 12px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,.04); }
.cc-sb-item:hover { background: #21262d; }
.cc-sb-item.active { background: rgba(88,166,255,.1); }
.cc-sb-item-title { font-size: 13px; color: #c9d1d9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 3px; }
.cc-sb-item-meta  { font-size: 10px; color: #484f58; }

/* Chat area */
.cc-chat-area   { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.cc-chat-empty  { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10px; color: #484f58; }
.cc-chat-empty-icon { font-size: 40px; }
.cc-chat-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; border-bottom: 1px solid #30363d; background: #161b22; flex-shrink: 0; }
.cc-chat-title  { font-size: 14px; font-weight: 600; color: #e6edf3; }
.cc-chat-meta   { display: flex; align-items: center; gap: 10px; font-size: 11px; }
.cc-conn-ok   { color: #3fb950; } .cc-conn-warn { color: #f0883e; } .cc-conn-off { color: #484f58; }
.cc-token  { color: #8b949e; font-family: monospace; }
.cc-elapsed { color: #8b949e; }

/* Messages */
.cc-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.cc-messages::-webkit-scrollbar { width: 5px; }
.cc-messages::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

.cc-msg-user { display: flex; flex-direction: column; align-items: flex-end; }
.cc-msg-user-label { font-size: 10px; color: #484f58; margin-bottom: 3px; }
.cc-msg-user-body  { background: #1f6feb; color: #fff; border-radius: 12px 12px 2px 12px; padding: 8px 12px; max-width: 70%; font-size: 13px; line-height: 1.6; word-break: break-word; }

.cc-msg-ai { display: flex; flex-direction: column; }
.cc-msg-ai-label { font-size: 10px; color: #484f58; margin-bottom: 3px; }
.cc-msg-ai-body  { background: #161b22; border: 1px solid #30363d; border-radius: 2px 12px 12px 12px; padding: 10px 14px; max-width: 90%; font-size: 13px; line-height: 1.7; color: #c9d1d9; word-break: break-word; }
.cc-msg-ai-body :deep(.cc-code-block) { background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 10px; overflow-x: auto; font-family: monospace; font-size: 12px; color: #c9d1d9; margin: 8px 0; }
.cc-msg-ai-body :deep(.cc-inline-code) { background: #21262d; padding: 1px 5px; border-radius: 3px; font-family: monospace; font-size: 12px; }
.cc-stream-cursor { color: #58a6ff; animation: blink .8s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

.cc-tool-call    { background: #161b22; border: 1px solid #30363d; border-left: 3px solid #e3b341; border-radius: 6px; overflow: hidden; }
.cc-tool-header  { display: flex; align-items: center; gap: 8px; padding: 7px 12px; cursor: pointer; }
.cc-tool-icon    { color: #e3b341; }
.cc-tool-name    { color: #c9d1d9; font-weight: 600; font-size: 12px; flex: 1; }
.cc-tool-toggle  { color: #484f58; font-size: 11px; }
.cc-tool-body    { padding: 8px 12px; border-top: 1px solid #30363d; }
.cc-tool-input   { font-family: monospace; font-size: 11px; color: #8b949e; margin: 0; white-space: pre-wrap; word-break: break-all; }
.cc-tool-output  { margin-top: 8px; }
.cc-tool-output-label { font-size: 10px; color: #484f58; margin-bottom: 3px; }
.cc-tool-output pre  { font-family: monospace; font-size: 11px; color: #3fb950; margin: 0; white-space: pre-wrap; word-break: break-all; }

.cc-thinking     { display: flex; gap: 8px; align-items: flex-start; background: rgba(88,166,255,.05); border-radius: 6px; padding: 7px 10px; }
.cc-thinking-icon { flex-shrink: 0; }
.cc-thinking-text { font-size: 12px; color: #484f58; font-style: italic; }

.cc-tool-running { display: flex; align-items: center; gap: 8px; padding: 6px 10px; color: #8b949e; font-size: 12px; }
.cc-status-verb  { display: flex; align-items: center; gap: 8px; padding: 6px 10px; color: #8b949e; font-size: 12px; }
.cc-status-spinner { width: 12px; height: 12px; border: 2px solid #30363d; border-top-color: #58a6ff; border-radius: 50%; animation: spin .8s linear infinite; flex-shrink: 0; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Permission dialog */
.cc-permission-dialog { margin: 0 16px 12px; background: #161b22; border: 1px solid #f0883e; border-radius: 10px; padding: 12px 14px; flex-shrink: 0; }
.cc-perm-header { display: flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 700; color: #f0883e; margin-bottom: 8px; }
.cc-perm-tool   { font-size: 12px; color: #8b949e; margin-bottom: 5px; }
.cc-perm-desc   { font-size: 12px; color: #c9d1d9; margin-bottom: 8px; }
.cc-perm-input  { font-family: monospace; font-size: 11px; color: #8b949e; background: #0d1117; border-radius: 4px; padding: 6px 8px; margin-bottom: 10px; white-space: pre-wrap; word-break: break-all; }
.cc-perm-actions { display: flex; gap: 8px; }

/* Composer */
.cc-composer       { padding: 10px 14px; border-top: 1px solid #30363d; background: #161b22; flex-shrink: 0; position: relative; }
.cc-composer-inner { display: flex; gap: 8px; align-items: flex-end; }
.cc-input-area     { flex: 1; background: #0d1117; border: 1px solid #30363d; border-radius: 8px; color: #e6edf3; font-family: inherit; font-size: 13px; padding: 8px 12px; resize: none; outline: none; max-height: 160px; line-height: 1.5; }
.cc-input-area:focus { border-color: #58a6ff; }
.cc-input-area:disabled { opacity: .5; cursor: not-allowed; }
.cc-input-area::placeholder { color: #484f58; }

/* Slash commands */
.cc-slash-menu  { position: absolute; bottom: 100%; left: 14px; right: 14px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; margin-bottom: 4px; }
.cc-slash-item  { display: flex; gap: 10px; align-items: baseline; padding: 7px 12px; cursor: pointer; font-size: 12px; }
.cc-slash-item:hover { background: #21262d; }
.cc-slash-name  { font-weight: 700; color: #58a6ff; font-family: monospace; }
.cc-slash-desc  { color: #8b949e; }
</style>
