<template>
  <div class="cc-page" :class="{ 'sidebar-collapsed': sidebarCollapsed }">

    <!-- 左侧会话历史 -->
    <aside class="cc-sidebar">
      <div class="cc-sidebar-header">
        <div class="cc-brand">
          <span class="cc-brand-icon">◈</span>
          <span class="cc-brand-name">Claude</span>
        </div>
        <button class="cc-collapse-btn" @click="sidebarCollapsed = !sidebarCollapsed" title="折叠侧栏">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
      </div>

      <button class="cc-new-btn" @click="newConversation">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新建对话
      </button>

      <div class="cc-conv-list">
        <div
          v-for="conv in conversations"
          :key="conv.conv_id"
          class="cc-conv-item"
          :class="{ active: activeConvId === conv.conv_id }"
          @click="loadConversation(conv)"
        >
          <div class="cc-conv-icon">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
          </div>
          <div class="cc-conv-info">
            <div class="cc-conv-title">{{ conv.title || '新对话' }}</div>
            <div class="cc-conv-date">{{ fmtDate(conv.updated_at) }}</div>
          </div>
          <button class="cc-conv-del" @click.stop="deleteConversation(conv.conv_id)" title="删除">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div v-if="!conversations.length" class="cc-conv-empty">暂无历史对话</div>
      </div>
    </aside>

    <!-- 侧栏折叠时展开按钮 -->
    <button v-if="sidebarCollapsed" class="cc-expand-btn" @click="sidebarCollapsed = false" title="展开侧栏">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
    </button>

    <!-- 主体区域 -->
    <main class="cc-main">

      <!-- 顶栏 -->
      <header class="cc-topbar">
        <div class="cc-session-title">
          <span class="cc-session-icon">◈</span>
          <span>{{ currentTitle || 'Claude Code' }}</span>
        </div>
        <div class="cc-topbar-right">
          <div class="cc-model-badge" v-if="activeModel">
            <span class="cc-model-dot"></span>
            {{ activeModel }}
          </div>
          <div class="cc-status-indicator" :class="statusClass">
            <span class="cc-status-dot-anim" v-if="streaming"></span>
            {{ statusText }}
          </div>
          <button v-if="streaming" class="cc-stop-btn" @click="stopStream">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="6" y="6" width="12" height="12"/></svg>
            停止
          </button>
        </div>
      </header>

      <!-- 消息区 -->
      <div class="cc-messages" ref="messagesEl">

        <!-- 空状态 -->
        <div v-if="!messages.length && !streaming" class="cc-empty">
          <div class="cc-empty-icon">◈</div>
          <div class="cc-empty-title">AIOps 智能运维助手</div>
          <div class="cc-empty-sub">基于 Claude Code 引擎，支持日志分析、故障诊断、根因定位</div>
          <div class="cc-quick-grid">
            <button v-for="q in QUICK_PROMPTS" :key="q" class="cc-quick-btn" @click="sendQuick(q)">{{ q }}</button>
          </div>
        </div>

        <!-- 消息列表 -->
        <template v-for="(msg, idx) in messages" :key="idx">

          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" class="cc-msg cc-msg-user">
            <div class="cc-msg-bubble cc-msg-bubble-user">
              <div class="cc-msg-text">{{ msg.content }}</div>
            </div>
            <div class="cc-msg-avatar cc-msg-avatar-user">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
            </div>
          </div>

          <!-- 助手消息 -->
          <div v-else-if="msg.role === 'assistant'" class="cc-msg cc-msg-assistant">
            <div class="cc-msg-avatar cc-msg-avatar-ai">◈</div>
            <div class="cc-msg-body">

              <!-- 文本内容 -->
              <div v-if="msg.content" class="cc-msg-bubble cc-msg-bubble-ai">
                <div class="cc-msg-text" v-html="renderMd(msg.content)"></div>
                <div v-if="msg.usage" class="cc-msg-usage">
                  <span>输入 {{ msg.usage.input_tokens || 0 }}</span>
                  <span>输出 {{ msg.usage.output_tokens || 0 }}</span>
                  <span v-if="msg.cost">${{ msg.cost.toFixed(4) }}</span>
                </div>
              </div>

              <!-- 工具调用 -->
              <div v-for="(tool, ti) in msg.tools" :key="ti" class="cc-tool-card" :class="{ 'tool-done': tool.done, 'tool-running': !tool.done }">
                <div class="cc-tool-header" @click="tool._open = !tool._open">
                  <div class="cc-tool-icon-wrap">
                    <span class="cc-tool-spinner" v-if="!tool.done"></span>
                    <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  </div>
                  <div class="cc-tool-name">{{ TOOL_LABELS[tool.name] || tool.name }}</div>
                  <div class="cc-tool-sub" v-if="tool.input">{{ fmtToolInput(tool.input) }}</div>
                  <div class="cc-tool-toggle">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :style="{ transform: tool._open ? 'rotate(180deg)' : '' }"><polyline points="6 9 12 15 18 9"/></svg>
                  </div>
                </div>
                <div class="cc-tool-body" v-show="tool._open">
                  <div v-if="tool.input && Object.keys(tool.input).length" class="cc-tool-section">
                    <div class="cc-tool-section-label">输入</div>
                    <pre class="cc-tool-code">{{ JSON.stringify(tool.input, null, 2) }}</pre>
                  </div>
                  <div v-if="tool.output" class="cc-tool-section">
                    <div class="cc-tool-section-label">输出</div>
                    <pre class="cc-tool-code cc-tool-output">{{ tool.output }}</pre>
                  </div>
                </div>
              </div>

            </div>
          </div>

          <!-- 错误消息 -->
          <div v-else-if="msg.role === 'error'" class="cc-msg cc-msg-error">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            {{ msg.content }}
          </div>

        </template>

        <!-- 流式输出中的当前消息 -->
        <div v-if="streaming && streamingMsg" class="cc-msg cc-msg-assistant">
          <div class="cc-msg-avatar cc-msg-avatar-ai">◈</div>
          <div class="cc-msg-body">
            <div v-if="streamingMsg.content" class="cc-msg-bubble cc-msg-bubble-ai">
              <div class="cc-msg-text" v-html="renderMd(streamingMsg.content)"></div>
              <span class="cc-cursor">▋</span>
            </div>
            <div v-for="(tool, ti) in streamingMsg.tools" :key="ti" class="cc-tool-card" :class="{ 'tool-done': tool.done, 'tool-running': !tool.done }">
              <div class="cc-tool-header" @click="tool._open = !tool._open">
                <div class="cc-tool-icon-wrap">
                  <span class="cc-tool-spinner" v-if="!tool.done"></span>
                  <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
                <div class="cc-tool-name">{{ TOOL_LABELS[tool.name] || tool.name }}</div>
                <div class="cc-tool-sub" v-if="tool.input">{{ fmtToolInput(tool.input) }}</div>
                <div class="cc-tool-toggle">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :style="{ transform: tool._open ? 'rotate(180deg)' : '' }"><polyline points="6 9 12 15 18 9"/></svg>
                </div>
              </div>
              <div class="cc-tool-body" v-show="tool._open">
                <div v-if="tool.input && Object.keys(tool.input).length" class="cc-tool-section">
                  <div class="cc-tool-section-label">输入</div>
                  <pre class="cc-tool-code">{{ JSON.stringify(tool.input, null, 2) }}</pre>
                </div>
                <div v-if="tool.output" class="cc-tool-section">
                  <div class="cc-tool-section-label">输出</div>
                  <pre class="cc-tool-code cc-tool-output">{{ tool.output }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div><!-- /cc-messages -->

      <!-- 输入区 -->
      <div class="cc-input-area">

        <!-- 斜杠命令提示 -->
        <div v-if="showSlashMenu" class="cc-slash-menu">
          <div
            v-for="(cmd, i) in filteredCmds"
            :key="cmd.cmd"
            class="cc-slash-item"
            :class="{ selected: i === slashIdx }"
            @click="applySlashCmd(cmd)"
          >
            <span class="cc-slash-cmd">{{ cmd.cmd }}</span>
            <span class="cc-slash-desc">{{ cmd.desc }}</span>
          </div>
        </div>

        <div class="cc-input-shell">
          <div class="cc-input-prompt">
            <span class="cc-prompt-char">❯</span>
          </div>
          <textarea
            ref="inputEl"
            v-model="inputText"
            class="cc-textarea"
            :placeholder="inputPlaceholder"
            :disabled="streaming"
            @keydown="onKeydown"
            @input="onInput"
            rows="1"
          ></textarea>
          <button class="cc-send-btn" :disabled="!inputText.trim() || streaming" @click="sendMessage">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          </button>
        </div>

        <div class="cc-input-hints">
          <span>Enter 发送 · Shift+Enter 换行</span>
          <span v-if="streaming" class="cc-hint-stop">Ctrl+C 停止生成</span>
          <span class="cc-hint-slash">/ 命令</span>
        </div>

      </div>
    </main>

  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { safeRandomUUID } from '../utils/uuid.js'
import { api } from '../api/index.js'

// ── 常量 ─────────────────────────────────────────────────────────────────────

const QUICK_PROMPTS = [
  '分析最近的系统告警，找出高频问题',
  '检查 Loki 中最近 30 分钟的错误日志',
  '帮我做一次根因分析，从告警到 Trace 链路',
  '当前哪些服务响应延迟异常？',
]

const TOOL_LABELS = {
  loki_query:       '🔍 查询日志',
  prometheus_query: '📊 查询指标',
  skywalking_query: '🔗 查询 Trace',
  list_alerts:      '🚨 获取告警',
  analyze_log:      '🧠 分析日志',
  bash:             '💻 执行命令',
  read_file:        '📄 读取文件',
  write_file:       '✏️  写入文件',
  web_search:       '🌐 搜索网络',
  Bash:             '💻 执行命令',
  Read:             '📄 读取文件',
  Write:            '✏️  写入文件',
  Edit:             '✏️  编辑文件',
  Glob:             '📂 文件搜索',
  Grep:             '🔍 内容搜索',
  WebFetch:         '🌐 抓取网页',
  WebSearch:        '🌐 搜索网络',
  Task:             '📋 创建任务',
  TodoWrite:        '📋 更新任务',
}

const SLASH_COMMANDS = [
  { cmd: '/clear',  desc: '清空当前对话' },
  { cmd: '/new',    desc: '新建对话' },
  { cmd: '/help',   desc: '查看帮助信息' },
  { cmd: '/log',    desc: '分析最近错误日志' },
  { cmd: '/alert',  desc: '查看当前告警' },
  { cmd: '/trace',  desc: '查询最近慢 Trace' },
  { cmd: '/rca',    desc: '根因分析' },
]

// ── 状态 ─────────────────────────────────────────────────────────────────────

const sidebarCollapsed = ref(false)
const conversations    = ref([])
const activeConvId     = ref('')
const currentTitle     = ref('')
const activeModel      = ref('')
const messages         = ref([])   // { role, content, tools?, usage?, cost? }
const streaming        = ref(false)
const streamingMsg     = reactive({ content: '', tools: [] })
const inputText        = ref('')
const inputEl          = ref(null)
const messagesEl       = ref(null)
const showSlashMenu    = ref(false)
const slashIdx         = ref(0)
const slashFilter      = ref('')

let   _abortCtrl       = null
let   _saveTimer       = null

// ── 计算属性 ─────────────────────────────────────────────────────────────────

const statusClass = computed(() => streaming.value ? 'status-running' : 'status-idle')
const statusText  = computed(() => streaming.value ? '生成中...' : '就绪')

const filteredCmds = computed(() =>
  SLASH_COMMANDS.filter(c => c.cmd.startsWith(slashFilter.value || '/'))
)

const inputPlaceholder = computed(() =>
  streaming.value ? '生成中，请稍候...' : '输入消息，/ 触发命令'
)

// ── 生命周期 ─────────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadConversations()
  await loadActiveModel()
  newConversation()
})

onBeforeUnmount(() => {
  _abortCtrl?.abort()
  clearTimeout(_saveTimer)
})

// ── 会话管理 ─────────────────────────────────────────────────────────────────

async function loadConversations() {
  try {
    const r = await api.listConversations()
    conversations.value = Array.isArray(r) ? r : (r?.data || [])
  } catch { /* ignore */ }
}

async function loadActiveModel() {
  try {
    const r = await api.listAgentModels()
    const models = r?.data || []
    const active = models.find(m => m.active)
    if (active) activeModel.value = active.name || active.runtime_model || ''
  } catch { /* ignore */ }
}

function newConversation() {
  _abortCtrl?.abort()
  activeConvId.value = safeRandomUUID()
  currentTitle.value = ''
  messages.value = []
  streaming.value = false
  streamingMsg.content = ''
  streamingMsg.tools = []
  inputText.value = ''
  nextTick(scrollBottom)
}

async function loadConversation(conv) {
  if (conv.conv_id === activeConvId.value) return
  _abortCtrl?.abort()
  activeConvId.value = conv.conv_id
  currentTitle.value = conv.title || ''
  streaming.value = false
  streamingMsg.content = ''
  streamingMsg.tools = []
  try {
    const r = await api.getConversation(conv.conv_id)
    const raw = (r?.messages || r?.data?.messages || [])
    messages.value = raw.map(m => ({
      role:    m.role,
      content: m.content,
      tools:   (m.tools || []).map(t => ({ ...t, _open: false })),
      usage:   m.usage || null,
      cost:    m.cost  || null,
    }))
  } catch {
    messages.value = []
  }
  await nextTick(scrollBottom)
}

async function deleteConversation(convId) {
  try {
    await api.deleteConversation(convId)
    conversations.value = conversations.value.filter(c => c.conv_id !== convId)
    if (activeConvId.value === convId) newConversation()
  } catch { /* ignore */ }
}

function scheduleSave() {
  clearTimeout(_saveTimer)
  _saveTimer = setTimeout(() => _saveConversation(), 1500)
}

async function _saveConversation() {
  if (!activeConvId.value || !messages.value.length) return
  const userMsgs = messages.value.filter(m => m.role === 'user')
  const title = currentTitle.value || userMsgs[0]?.content?.slice(0, 30) || '新对话'
  currentTitle.value = title
  const conv = conversations.value.find(c => c.conv_id === activeConvId.value)
  const payload = {
    mode:     'chat',
    title,
    messages: messages.value.map(m => ({
      role:    m.role,
      content: m.content,
      tools:   m.tools || [],
      usage:   m.usage  || null,
      cost:    m.cost   || null,
    })),
  }
  try {
    await api.saveConversation(activeConvId.value, payload)
    if (!conv) {
      conversations.value.unshift({
        conv_id:    activeConvId.value,
        title,
        updated_at: new Date().toISOString(),
      })
    } else {
      conv.title      = title
      conv.updated_at = new Date().toISOString()
    }
  } catch (e) { console.warn('[claude] save conv failed:', e) }
}

// ── 发送消息 ─────────────────────────────────────────────────────────────────

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return

  if (text.startsWith('/')) {
    if (handleSlashCmd(text)) { inputText.value = ''; return }
  }

  inputText.value = ''
  showSlashMenu.value = false
  resizeTextarea()

  messages.value.push({ role: 'user', content: text })
  await nextTick(scrollBottom)
  await doStream(text)
}

function sendQuick(prompt) {
  inputText.value = prompt
  sendMessage()
}

async function doStream(text) {
  streaming.value = true
  streamingMsg.content = ''
  streamingMsg.tools   = []

  _abortCtrl = new AbortController()

  let currentToolIdx = -1

  try {
    const resp = await fetch('/api/agent/chat', {
      method:      'POST',
      headers:     { 'Content-Type': 'application/json' },
      credentials: 'include',
      body:        JSON.stringify({
        message: text,
        conv_id: activeConvId.value,
      }),
      signal:  _abortCtrl.signal,
    })

    if (!resp.ok) {
      if (resp.status === 401) {
        window.location.href = '/#/login'
        throw new Error('登录已过期，请重新登录后再试')
      }

      let detail = ''
      try {
        const data = await resp.clone().json()
        detail = data?.detail || data?.message || data?.error || ''
      } catch {
        try { detail = await resp.text() } catch { detail = '' }
      }
      throw new Error(detail ? `HTTP ${resp.status}: ${detail}` : `HTTP ${resp.status}`)
    }

    const reader  = resp.body.getReader()
    const decoder = new TextDecoder()
    let   buf     = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw) continue
        let evt
        try { evt = JSON.parse(raw) } catch { continue }

        if (evt.type === 'token') {
          streamingMsg.content += evt.text
          scrollBottom()

        } else if (evt.type === 'tool_start') {
          streamingMsg.tools.push({
            name:   evt.tool,
            input:  evt.input || {},
            output: '',
            done:   false,
            _open:  true,
          })
          currentToolIdx = streamingMsg.tools.length - 1
          scrollBottom()

        } else if (evt.type === 'tool_end') {
          if (currentToolIdx >= 0 && streamingMsg.tools[currentToolIdx]) {
            streamingMsg.tools[currentToolIdx].output = evt.output || ''
            streamingMsg.tools[currentToolIdx].done   = true
          }

        } else if (evt.type === 'replace_content') {
          // 后端提取结构化数据后，用干净文本替换流式累积内容
          if (evt.text != null) streamingMsg.content = evt.text

        } else if (evt.type === 'done') {
          const finalMsg = {
            role:    'assistant',
            content: streamingMsg.content,
            tools:   streamingMsg.tools.map(t => ({ ...t, _open: false })),
            usage:   evt.usage || null,
            cost:    evt.cost  || null,
          }
          messages.value.push(finalMsg)
          streaming.value      = false
          streamingMsg.content = ''
          streamingMsg.tools   = []
          scheduleSave()
          await nextTick(scrollBottom)
          break

        } else if (evt.type === 'error') {
          messages.value.push({ role: 'error', content: evt.message || '发生错误' })
          streaming.value      = false
          streamingMsg.content = ''
          streamingMsg.tools   = []
          await nextTick(scrollBottom)
          break
        }
      }
    }
  } catch (e) {
    if (e?.name !== 'AbortError') {
      if (streamingMsg.content) {
        messages.value.push({
          role:    'assistant',
          content: streamingMsg.content,
          tools:   streamingMsg.tools.map(t => ({ ...t, _open: false })),
        })
        scheduleSave()
      }
      if (e?.name !== 'AbortError') {
        messages.value.push({ role: 'error', content: String(e) })
      }
    }
    streaming.value      = false
    streamingMsg.content = ''
    streamingMsg.tools   = []
    await nextTick(scrollBottom)
  }
}

function stopStream() {
  _abortCtrl?.abort()
}

// ── 斜杠命令 ─────────────────────────────────────────────────────────────────

function handleSlashCmd(text) {
  const cmd = text.split(' ')[0].toLowerCase()
  if (cmd === '/clear')  { messages.value = []; return true }
  if (cmd === '/new')    { newConversation(); return true }
  if (cmd === '/help')   {
    messages.value.push({ role: 'assistant', content: SLASH_COMMANDS.map(c => `**${c.cmd}** — ${c.desc}`).join('\n') })
    return true
  }
  if (cmd === '/log')    { inputText.value = '分析最近 30 分钟的错误日志，找出高频异常'; return false }
  if (cmd === '/alert')  { inputText.value = '列出当前所有告警，按严重程度排序'; return false }
  if (cmd === '/trace')  { inputText.value = '查询最近慢 Trace（>500ms），定位瓶颈服务'; return false }
  if (cmd === '/rca')    { inputText.value = '进行一次完整根因分析：从告警 → 日志 → Trace'; return false }
  return false
}

function onInput() {
  resizeTextarea()
  const val = inputText.value
  if (val.startsWith('/')) {
    slashFilter.value  = val.split(' ')[0]
    showSlashMenu.value = filteredCmds.value.length > 0
    slashIdx.value      = 0
  } else {
    showSlashMenu.value = false
  }
}

function onKeydown(e) {
  if (showSlashMenu.value) {
    if (e.key === 'ArrowDown')  { e.preventDefault(); slashIdx.value = (slashIdx.value + 1) % filteredCmds.value.length; return }
    if (e.key === 'ArrowUp')    { e.preventDefault(); slashIdx.value = (slashIdx.value - 1 + filteredCmds.value.length) % filteredCmds.value.length; return }
    if (e.key === 'Tab' || e.key === 'Enter') { e.preventDefault(); applySlashCmd(filteredCmds.value[slashIdx.value]); return }
    if (e.key === 'Escape')     { showSlashMenu.value = false; return }
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); return }
  if (e.key === 'c' && e.ctrlKey && streaming.value) { stopStream(); return }
}

function applySlashCmd(cmd) {
  if (!cmd) return
  inputText.value     = cmd.cmd + ' '
  showSlashMenu.value = false
  inputEl.value?.focus()
  if (handleSlashCmd(cmd.cmd)) {
    inputText.value = ''
  }
}

// ── 辅助 ─────────────────────────────────────────────────────────────────────

function resizeTextarea() {
  const el = inputEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
}

function scrollBottom() {
  const el = messagesEl.value
  if (el) el.scrollTop = el.scrollHeight
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function fmtToolInput(input) {
  if (!input) return ''
  const first = Object.values(input)[0]
  if (typeof first === 'string') return first.slice(0, 60)
  return ''
}

function renderMd(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) =>
      `<pre class="md-code" data-lang="${lang}"><code>${code.trim()}</code></pre>`)
    .replace(/`([^`]+)`/g, '<code class="md-inline">$1</code>')
    .replace(/^\s*#{3}\s+(.+)$/gm, '<h4 class="md-h4">$1</h4>')
    .replace(/^\s*#{2}\s+(.+)$/gm, '<h3 class="md-h3">$1</h3>')
    .replace(/^\s*#{1}\s+(.+)$/gm, '<h2 class="md-h2">$1</h2>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^\s*[-*+]\s+(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
    .replace(/^\s*\d+\.\s+(.+)$/gm, '<li>$1</li>')
    .replace(/\n/g, '<br>')
}
</script>

<style scoped>
/* ── 布局 ── */
.cc-page {
  display: flex;
  height: 100%;
  background: #0d1117;
  color: #e6edf3;
  font-family: 'Cascadia Code', 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  overflow: hidden;
  position: relative;
}

/* ── 侧栏 ── */
.cc-sidebar {
  width: 220px;
  min-width: 220px;
  background: #0a0e14;
  border-right: 1px solid #21262d;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width .2s, min-width .2s;
}
.cc-page.sidebar-collapsed .cc-sidebar { width: 0; min-width: 0; }

.cc-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 10px;
  border-bottom: 1px solid #21262d;
  flex-shrink: 0;
}
.cc-brand { display: flex; align-items: center; gap: 7px; }
.cc-brand-icon { color: #00d084; font-size: 16px; }
.cc-brand-name { font-weight: 700; font-size: 14px; color: #e6edf3; letter-spacing: .03em; }
.cc-collapse-btn {
  background: none; border: none; color: #484f58;
  cursor: pointer; padding: 3px; border-radius: 4px;
  transition: color .15s, background .15s;
}
.cc-collapse-btn:hover { color: #e6edf3; background: #21262d; }

.cc-new-btn {
  display: flex; align-items: center; gap: 7px;
  margin: 10px 10px 4px;
  padding: 8px 12px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #8b949e;
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
  font-family: inherit;
}
.cc-new-btn:hover { background: #21262d; color: #e6edf3; border-color: #484f58; }

.cc-conv-list { flex: 1; overflow-y: auto; padding: 4px 6px; scrollbar-width: thin; scrollbar-color: #21262d transparent; }
.cc-conv-item {
  display: flex; align-items: center; gap: 7px;
  padding: 7px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background .12s;
  position: relative;
}
.cc-conv-item:hover { background: #161b22; }
.cc-conv-item.active { background: #1c2128; }
.cc-conv-icon { color: #484f58; flex-shrink: 0; }
.cc-conv-info { flex: 1; min-width: 0; }
.cc-conv-title { font-size: 12px; color: #c9d1d9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cc-conv-date { font-size: 10px; color: #484f58; margin-top: 1px; }
.cc-conv-del {
  display: none; background: none; border: none; color: #484f58;
  cursor: pointer; padding: 2px; border-radius: 3px;
  transition: color .12s, background .12s;
}
.cc-conv-item:hover .cc-conv-del { display: flex; }
.cc-conv-del:hover { color: #f85149; background: rgba(248,81,73,.12); }
.cc-conv-empty { padding: 16px 8px; font-size: 11px; color: #484f58; text-align: center; }

.cc-expand-btn {
  position: absolute;
  left: 4px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 4px;
  color: #8b949e;
  cursor: pointer;
  padding: 4px;
  transition: all .15s;
}
.cc-expand-btn:hover { background: #21262d; color: #e6edf3; }

/* ── 主体 ── */
.cc-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

/* ── 顶栏 ── */
.cc-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  height: 44px;
  background: #0a0e14;
  border-bottom: 1px solid #21262d;
  flex-shrink: 0;
}
.cc-session-title {
  display: flex; align-items: center; gap: 8px;
  font-weight: 600; font-size: 13px; color: #e6edf3;
}
.cc-session-icon { color: #00d084; }
.cc-topbar-right { display: flex; align-items: center; gap: 10px; }
.cc-model-badge {
  display: flex; align-items: center; gap: 5px;
  padding: 3px 9px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 20px;
  font-size: 11px;
  color: #8b949e;
}
.cc-model-dot { width: 6px; height: 6px; border-radius: 50%; background: #00d084; }
.cc-status-indicator { font-size: 11px; color: #484f58; display: flex; align-items: center; gap: 5px; }
.status-running { color: #00d084; }
.cc-status-dot-anim {
  width: 6px; height: 6px; border-radius: 50%; background: #00d084;
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
.cc-stop-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px;
  background: rgba(248,81,73,.1);
  border: 1px solid rgba(248,81,73,.3);
  border-radius: 5px;
  color: #f85149;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  transition: all .12s;
}
.cc-stop-btn:hover { background: rgba(248,81,73,.2); }

/* ── 消息区 ── */
.cc-messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
  scrollbar-width: thin;
  scrollbar-color: #21262d transparent;
}
.cc-messages::-webkit-scrollbar { width: 4px; }
.cc-messages::-webkit-scrollbar-thumb { background: #21262d; border-radius: 2px; }

/* ── 空状态 ── */
.cc-empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center;
  padding: 60px 32px;
  text-align: center;
  min-height: 300px;
}
.cc-empty-icon { font-size: 40px; color: #00d084; margin-bottom: 16px; opacity: .8; }
.cc-empty-title { font-size: 18px; font-weight: 700; color: #e6edf3; margin-bottom: 8px; }
.cc-empty-sub { font-size: 13px; color: #8b949e; margin-bottom: 28px; line-height: 1.6; max-width: 400px; }
.cc-quick-grid {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 10px; width: 100%; max-width: 560px;
}
.cc-quick-btn {
  padding: 12px 16px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  color: #8b949e;
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  line-height: 1.4;
  transition: all .15s;
  font-family: inherit;
}
.cc-quick-btn:hover { background: #1c2128; border-color: #00d084; color: #e6edf3; }

/* ── 消息气泡 ── */
.cc-msg {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 6px 24px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}
.cc-msg-user { flex-direction: row-reverse; }

.cc-msg-avatar {
  width: 28px; height: 28px;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px;
  flex-shrink: 0;
  margin-top: 2px;
}
.cc-msg-avatar-user { background: #1f6feb; color: #fff; }
.cc-msg-avatar-ai   { background: #0a3622; color: #00d084; border: 1px solid #1a7f4a; }

.cc-msg-body { display: flex; flex-direction: column; gap: 8px; flex: 1; min-width: 0; }

.cc-msg-bubble {
  border-radius: 8px;
  padding: 12px 16px;
  max-width: 100%;
  line-height: 1.65;
  word-break: break-word;
  position: relative;
}
.cc-msg-bubble-user {
  background: #1f6feb;
  color: #fff;
  border-radius: 8px 2px 8px 8px;
  max-width: 70%;
}
.cc-msg-bubble-ai {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 2px 8px 8px 8px;
}

.cc-msg-text { font-size: 13px; }
.cc-msg-usage {
  display: flex; gap: 12px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #21262d;
  font-size: 10.5px;
  color: #484f58;
}

.cc-cursor {
  display: inline-block;
  color: #00d084;
  animation: blink .8s steps(1) infinite;
  margin-left: 1px;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

/* ── 错误消息 ── */
.cc-msg-error {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 24px;
  max-width: 900px; margin: 0 auto; width: 100%; box-sizing: border-box;
  color: #f85149;
  font-size: 12.5px;
  background: rgba(248,81,73,.06);
  border-left: 3px solid #f85149;
}

/* ── 工具调用卡片 ── */
.cc-tool-card {
  border-radius: 6px;
  border: 1px solid #21262d;
  overflow: hidden;
  background: #0d1117;
  font-size: 12px;
}
.tool-running { border-color: #1a7f4a; }
.tool-done    { border-color: #21262d; }

.cc-tool-header {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 12px;
  cursor: pointer;
  background: #161b22;
  transition: background .12s;
  user-select: none;
}
.cc-tool-header:hover { background: #1c2128; }
.cc-tool-icon-wrap {
  width: 18px; height: 18px;
  border-radius: 4px;
  background: #0a3622;
  border: 1px solid #1a7f4a;
  display: flex; align-items: center; justify-content: center;
  color: #00d084;
  flex-shrink: 0;
}
.tool-done .cc-tool-icon-wrap { background: #0a3622; }
.cc-tool-spinner {
  width: 8px; height: 8px;
  border: 1.5px solid #1a7f4a;
  border-top-color: #00d084;
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.cc-tool-name { font-weight: 600; color: #c9d1d9; flex-shrink: 0; }
.cc-tool-sub  { flex: 1; color: #484f58; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.cc-tool-toggle { margin-left: auto; color: #484f58; transition: color .12s; flex-shrink: 0; }
.cc-tool-toggle svg { transition: transform .2s; }

.cc-tool-body { padding: 0; }
.cc-tool-section { border-top: 1px solid #21262d; }
.cc-tool-section-label {
  padding: 4px 12px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: #484f58;
  background: #0a0e14;
}
.cc-tool-code {
  margin: 0;
  padding: 10px 14px;
  font-size: 11.5px;
  font-family: inherit;
  color: #8b949e;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
  scrollbar-width: thin;
}
.cc-tool-output { color: #7ee787; }

/* ── 输入区 ── */
.cc-input-area {
  flex-shrink: 0;
  padding: 12px 18px 16px;
  background: #0a0e14;
  border-top: 1px solid #21262d;
  position: relative;
}
.cc-slash-menu {
  position: absolute;
  bottom: calc(100% + 4px);
  left: 18px; right: 18px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0,0,0,.5);
  z-index: 50;
}
.cc-slash-item {
  display: flex; align-items: center; gap: 12px;
  padding: 9px 14px;
  cursor: pointer;
  transition: background .1s;
}
.cc-slash-item:hover, .cc-slash-item.selected { background: #1c2128; }
.cc-slash-cmd { font-weight: 600; color: #00d084; min-width: 80px; font-size: 12px; }
.cc-slash-desc { color: #8b949e; font-size: 12px; }

.cc-input-shell {
  display: flex; align-items: flex-end; gap: 8px;
  padding: 10px 12px;
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 10px;
  transition: border-color .15s;
}
.cc-input-shell:focus-within { border-color: #00d084; }

.cc-input-prompt { display: flex; align-items: center; padding-bottom: 2px; }
.cc-prompt-char { color: #00d084; font-size: 15px; font-weight: 700; line-height: 1; }

.cc-textarea {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: #e6edf3;
  font-size: 13px;
  font-family: inherit;
  resize: none;
  line-height: 1.55;
  min-height: 22px;
  max-height: 200px;
  scrollbar-width: thin;
}
.cc-textarea::placeholder { color: #484f58; }
.cc-textarea:disabled { opacity: .5; cursor: not-allowed; }

.cc-send-btn {
  width: 32px; height: 32px;
  border-radius: 7px;
  background: #00d084;
  border: none;
  color: #0d1117;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all .15s;
  flex-shrink: 0;
}
.cc-send-btn:hover:not(:disabled) { background: #26e09a; }
.cc-send-btn:disabled { background: #21262d; color: #484f58; cursor: not-allowed; }

.cc-input-hints {
  display: flex; align-items: center; gap: 14px;
  margin-top: 7px;
  font-size: 10.5px;
  color: #484f58;
}
.cc-hint-stop { color: #f85149; }
.cc-hint-slash { color: #00d084; }

/* ── Markdown 样式 ── */
:deep(.md-code) {
  background: #0a0e14;
  border: 1px solid #21262d;
  border-radius: 6px;
  padding: 12px 14px;
  margin: 8px 0;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre;
  color: #7ee787;
}
:deep(.md-inline) {
  background: #21262d;
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 12px;
  color: #ff7b72;
}
:deep(.md-h2) { font-size: 15px; font-weight: 700; color: #e6edf3; margin: 12px 0 6px; }
:deep(.md-h3) { font-size: 14px; font-weight: 600; color: #c9d1d9; margin: 10px 0 4px; }
:deep(.md-h4) { font-size: 13px; font-weight: 600; color: #c9d1d9; margin: 8px 0 4px; }
:deep(ul) { padding-left: 20px; margin: 4px 0; }
:deep(li) { margin: 2px 0; color: #c9d1d9; }
:deep(strong) { color: #e6edf3; font-weight: 700; }
</style>
