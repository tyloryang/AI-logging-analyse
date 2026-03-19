<template>
  <div class="agent-page">

    <!-- 顶部标题 + 模式切换 -->
    <div class="agent-header">
      <div class="agent-title">
        <span class="agent-icon-wrap" v-html="AGENT_ICON"></span>
        <div>
          <h1>AI 智能体</h1>
          <span class="subtitle">由 LangGraph 驱动 · 自主推理 · 多工具协作</span>
        </div>
      </div>
      <div class="mode-tabs">
        <button
          v-for="m in MODES" :key="m.key"
          class="mode-tab" :class="{ active: mode === m.key }"
          @click="switchMode(m.key)"
        >
          <span class="mode-icon" v-html="m.icon"></span>
          {{ m.label }}
        </button>
      </div>
    </div>

    <!-- 聊天区域 -->
    <div class="chat-area" ref="chatAreaRef">

      <!-- 欢迎占位 -->
      <div v-if="!messages.length" class="welcome-state">
        <div class="welcome-icon" v-html="AGENT_ICON"></div>
        <div class="welcome-title">{{ currentMode.label }}</div>
        <div class="welcome-desc">{{ currentMode.desc }}</div>
        <div class="welcome-hints">
          <button
            v-for="hint in currentMode.hints" :key="hint"
            class="hint-btn" @click="sendMessage(hint)"
          >{{ hint }}</button>
        </div>
      </div>

      <!-- 消息列表 -->
      <template v-else>
        <div v-for="msg in messages" :key="msg.id" class="msg-wrapper" :class="msg.role">

          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" class="bubble user-bubble">
            {{ msg.content }}
          </div>

          <!-- AI 消息 -->
          <div v-else class="assistant-msg">
            <div class="assistant-avatar" v-html="AGENT_ICON"></div>
            <div class="assistant-body">

              <!-- 工具调用卡片 -->
              <div v-for="tc in msg.toolCalls" :key="tc.id" class="tool-card" :class="tc.pending ? 'pending' : 'done'">
                <div class="tool-header" @click="tc.expanded = !tc.expanded">
                  <span class="tool-status-dot" :class="tc.pending ? 'spin' : 'ok'"></span>
                  <span class="tool-name">{{ TOOL_LABELS[tc.tool] || tc.tool }}</span>
                  <span v-if="!tc.pending" class="tool-params">
                    {{ formatInput(tc.input) }}
                  </span>
                  <span v-if="tc.pending" class="tool-pending-text">执行中...</span>
                  <span v-if="!tc.pending && tc.output" class="tool-expand-btn">
                    {{ tc.expanded ? '▲ 收起' : '▼ 查看结果' }}
                  </span>
                </div>
                <div v-if="tc.expanded && tc.output" class="tool-output">
                  <pre>{{ tc.output }}</pre>
                </div>
              </div>

              <!-- AI 文本回复（流式） -->
              <div v-if="msg.content || msg.streaming" class="ai-text">
                <span class="ai-content">{{ msg.content }}</span>
                <span v-if="msg.streaming" class="cursor-blink"></span>
              </div>

            </div>
          </div>

        </div>

        <!-- 底部占位，用于自动滚动 -->
        <div ref="bottomRef"></div>
      </template>
    </div>

    <!-- 输入区 -->
    <div class="input-area">
      <div v-if="mode === 'inspect' && !messages.length" class="inspect-quick">
        <button class="btn-inspect" @click="startInspect" :disabled="streaming">
          <span v-if="streaming" class="spinner-sm"></span>
          <span v-else v-html="SCAN_ICON"></span>
          {{ streaming ? '巡检中...' : '一键开始巡检' }}
        </button>
        <span class="inspect-hint">将自动检查所有主机状态、日志异常并生成报告</span>
      </div>
      <div v-else class="input-row">
        <textarea
          ref="inputRef"
          v-model="inputText"
          class="chat-input"
          :placeholder="currentMode.placeholder"
          :disabled="streaming"
          rows="1"
          @keydown.enter.exact.prevent="onEnter"
          @input="autoResize"
        ></textarea>
        <button class="send-btn" :disabled="streaming || !inputText.trim()" @click="onSend">
          <span v-if="streaming" class="spinner-sm"></span>
          <span v-else v-html="SEND_ICON"></span>
        </button>
      </div>
      <div v-if="messages.length" class="input-actions">
        <button class="action-btn" @click="clearChat">清空对话</button>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, nextTick, reactive } from 'vue'

// ── 图标 ──────────────────────────────────────────────────────────────
const AGENT_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M9 11V7a3 3 0 0 1 6 0v4"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/><path d="M12 3v2"/></svg>`
const SEND_ICON  = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`
const SCAN_ICON  = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h1m18 0h1M12 2v1m0 18v1M4.93 4.93l.7.7m12.74 12.74.7.7M4.93 19.07l.7-.7m12.74-12.74.7-.7"/><circle cx="12" cy="12" r="4"/></svg>`

// ── 模式配置 ──────────────────────────────────────────────────────────
const MODES = [
  {
    key: 'rca',
    label: '根因分析',
    desc: '描述你遇到的问题，AI 将自动查询日志和指标，给出根因分析报告',
    placeholder: '描述问题，例如：用户反馈支付服务响应慢，请分析原因...',
    hints: ['分析最近的服务错误', '为什么响应变慢了', '哪个服务出现了异常'],
    icon: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  },
  {
    key: 'inspect',
    label: '自主巡检',
    desc: '一键触发全量巡检，AI 自主检查所有主机和服务，输出结构化报告',
    placeholder: '可以指定巡检重点，或直接点击"一键开始巡检"...',
    hints: ['重点检查磁盘空间', '检查高负载主机', '查看最近出错的服务'],
    icon: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`,
  },
  {
    key: 'chat',
    label: '智能对话',
    desc: '自由提问，AI 按需调用工具查询日志、指标、主机状态',
    placeholder: '有什么想了解的？例如：查一下 nginx 最近的错误...',
    hints: ['查看所有服务的错误情况', '哪台主机 CPU 最高', '最近 1 小时有什么异常'],
    icon: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  },
]

// 工具友好名称
const TOOL_LABELS = {
  query_error_logs:       '查询错误日志',
  count_errors_by_service:'统计各服务错误数',
  get_services_list:      '获取服务列表',
  get_host_metrics:       '获取主机指标',
  inspect_all_hosts:      '全量主机巡检',
  query_recent_logs:      '查询最近日志',
}

// ── 状态 ──────────────────────────────────────────────────────────────
const mode       = ref('chat')
const messages   = ref([])
const inputText  = ref('')
const streaming  = ref(false)
const chatAreaRef = ref(null)
const bottomRef   = ref(null)
const inputRef    = ref(null)

let msgIdCounter = 0
let currentAssistantMsg = null

// 每种模式独立的会话 ID，用于后端多轮历史隔离
const convIds = ref({
  rca:     crypto.randomUUID(),
  inspect: crypto.randomUUID(),
  chat:    crypto.randomUUID(),
})

const currentMode = computed(() => MODES.find(m => m.key === mode.value) || MODES[2])

// ── 工具函数 ──────────────────────────────────────────────────────────
function formatInput(input) {
  if (!input || typeof input !== 'object') return ''
  const parts = Object.entries(input)
    .filter(([, v]) => v !== '' && v !== null && v !== undefined && v !== 0)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
  return parts.length ? '(' + parts.join(', ') + ')' : ''
}

function scrollToBottom() {
  nextTick(() => {
    bottomRef.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

function autoResize(e) {
  const el = e.target
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}

// ── 模式切换 ──────────────────────────────────────────────────────────
function switchMode(key) {
  if (streaming.value) return
  mode.value = key
  clearChat()
}

function clearChat() {
  messages.value = []
  currentAssistantMsg = null
  streaming.value = false
  inputText.value = ''
  // 重置会话 ID，后端历史同步清空
  convIds.value[mode.value] = crypto.randomUUID()
  if (inputRef.value) inputRef.value.style.height = 'auto'
}

// ── 发送消息 ──────────────────────────────────────────────────────────
function onEnter() { onSend() }

function onSend() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return
  sendMessage(text)
  inputText.value = ''
  if (inputRef.value) inputRef.value.style.height = 'auto'
}

function startInspect() {
  sendMessage('请执行全面系统巡检，检查所有主机状态和日志异常，生成完整巡检报告。')
}

async function sendMessage(text) {
  if (streaming.value) return

  // 添加用户消息
  messages.value.push({ id: ++msgIdCounter, role: 'user', content: text })
  scrollToBottom()

  // 准备 AI 消息（立即显示思考状态）
  const assistantMsg = reactive({
    id: ++msgIdCounter,
    role: 'assistant',
    content: '',
    toolCalls: [],
    streaming: true,
    done: false,
  })
  messages.value.push(assistantMsg)
  currentAssistantMsg = assistantMsg
  streaming.value = true

  const endpoint = `/api/agent/${mode.value}`

  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ message: text, conv_id: convIds.value[mode.value] }),
    })

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const chunk = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              handleEvent(JSON.parse(line.slice(6)), assistantMsg)
            } catch { /* ignore parse errors */ }
          }
        }
      }
    }
  } catch (e) {
    assistantMsg.content += `\n\n❌ 请求失败：${e.message}`
    assistantMsg.streaming = false
    assistantMsg.done = true
    streaming.value = false
    currentAssistantMsg = null
  }
}

function handleEvent(data, msg) {
  switch (data.type) {
    case 'token':
      msg.content += data.text || ''
      scrollToBottom()
      break

    case 'tool_start':
      msg.toolCalls.push(reactive({
        id: ++msgIdCounter,
        tool: data.tool || '',
        input: data.input || {},
        output: null,
        pending: true,
        expanded: false,
      }))
      scrollToBottom()
      break

    case 'tool_end': {
      // 找最后一个同名且 pending 的工具调用
      const tc = [...msg.toolCalls].reverse().find(t => t.tool === data.tool && t.pending)
      if (tc) {
        tc.output = data.output || ''
        tc.pending = false
      }
      scrollToBottom()
      break
    }

    case 'done':
      msg.streaming = false
      msg.done = true
      streaming.value = false
      currentAssistantMsg = null
      scrollToBottom()
      break

    case 'error':
      msg.content += (msg.content ? '\n\n' : '') + `❌ ${data.message || '未知错误'}`
      msg.streaming = false
      msg.done = true
      streaming.value = false
      currentAssistantMsg = null
      scrollToBottom()
      break
  }
}
</script>

<style scoped>
/* ── 页面整体 ──────────────────────────────────────────────── */
.agent-page {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

/* ── 顶部 ──────────────────────────────────────────────────── */
.agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 16px;
  flex-wrap: wrap;
}
.agent-title {
  display: flex;
  align-items: center;
  gap: 10px;
}
.agent-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px; height: 34px;
  border-radius: 8px;
  background: var(--accent-dim, rgba(99,102,241,.12));
  color: var(--accent);
  flex-shrink: 0;
}
.agent-title h1 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.subtitle {
  font-size: 11px;
  color: var(--text-muted);
  display: block;
  margin-top: 1px;
}

/* ── 模式标签 ──────────────────────────────────────────────── */
.mode-tabs {
  display: flex;
  gap: 6px;
}
.mode-tab {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  font-size: 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
  transition: all .15s;
}
.mode-tab:hover { border-color: var(--accent); color: var(--text-primary); }
.mode-tab.active { border-color: var(--accent); background: var(--accent-dim); color: var(--accent); font-weight: 500; }
.mode-icon { display: flex; align-items: center; }

/* ── 聊天区域 ──────────────────────────────────────────────── */
.chat-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── 欢迎状态 ──────────────────────────────────────────────── */
.welcome-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
  text-align: center;
}
.welcome-icon {
  width: 52px; height: 52px;
  border-radius: 14px;
  background: var(--accent-dim, rgba(99,102,241,.12));
  color: var(--accent);
  display: flex; align-items: center; justify-content: center;
}
.welcome-icon :deep(svg) { width: 26px; height: 26px; }
.welcome-title { font-size: 18px; font-weight: 600; color: var(--text-primary); }
.welcome-desc  { font-size: 13px; color: var(--text-muted); max-width: 420px; line-height: 1.6; }
.welcome-hints { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 8px; }
.hint-btn {
  padding: 7px 14px;
  font-size: 12px;
  border-radius: 20px;
  border: 1px solid var(--border-accent, var(--border));
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
  transition: all .15s;
}
.hint-btn:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }

/* ── 消息行 ──────────────────────────────────────────────── */
.msg-wrapper { display: flex; }
.msg-wrapper.user { justify-content: flex-end; }
.msg-wrapper.assistant { justify-content: flex-start; }

/* 用户气泡 */
.user-bubble {
  max-width: 72%;
  padding: 10px 14px;
  border-radius: 14px 14px 2px 14px;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

/* AI 消息 */
.assistant-msg {
  display: flex;
  gap: 10px;
  max-width: 88%;
}
.assistant-avatar {
  width: 28px; height: 28px;
  border-radius: 7px;
  background: var(--accent-dim, rgba(99,102,241,.12));
  color: var(--accent);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}
.assistant-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

/* ── 工具调用卡片 ─────────────────────────────────────────── */
.tool-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-surface, var(--bg-card));
  font-size: 12px;
}
.tool-card.pending { border-color: rgba(210,153,34,.3); }
.tool-card.done    { border-color: rgba(63,185,80,.2); }

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  cursor: pointer;
  user-select: none;
  flex-wrap: wrap;
}
.tool-header:hover { background: var(--bg-hover, rgba(255,255,255,.03)); }

.tool-status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.tool-status-dot.ok   { background: var(--success); }
.tool-status-dot.spin {
  border: 2px solid rgba(210,153,34,.3);
  border-top-color: var(--warning);
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.tool-name { font-weight: 600; color: var(--text-primary); }
.tool-params { color: var(--text-muted); font-family: 'JetBrains Mono', monospace; font-size: 11px; }
.tool-pending-text { color: var(--warning); font-style: italic; }
.tool-expand-btn { margin-left: auto; color: var(--text-muted); font-size: 11px; }

.tool-output {
  border-top: 1px solid var(--border);
  padding: 8px 10px;
  background: var(--bg-base, #0f1117);
}
.tool-output pre {
  margin: 0;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 240px;
  overflow-y: auto;
  line-height: 1.5;
}

/* ── AI 文本回复 ──────────────────────────────────────────── */
.ai-text {
  padding: 10px 14px;
  border-radius: 2px 14px 14px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.cursor-blink {
  display: inline-block;
  width: 2px; height: 14px;
  background: var(--accent);
  margin-left: 2px;
  vertical-align: middle;
  animation: blink .9s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }

/* ── 输入区 ──────────────────────────────────────────────── */
.input-area {
  flex-shrink: 0;
  padding: 10px 20px 14px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* 一键巡检 */
.inspect-quick {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.btn-inspect {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 22px;
  border-radius: 8px;
  border: 1px solid var(--accent);
  background: var(--accent-dim, rgba(99,102,241,.12));
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: all .15s;
}
.btn-inspect:hover:not(:disabled) { background: var(--accent); color: #fff; }
.btn-inspect:disabled { opacity: .5; cursor: not-allowed; }
.inspect-hint { font-size: 12px; color: var(--text-muted); }

/* 文本输入行 */
.input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.chat-input {
  flex: 1;
  min-height: 38px;
  max-height: 160px;
  padding: 9px 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--bg-surface, var(--bg-card));
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  resize: none;
  line-height: 1.5;
  outline: none;
  transition: border-color .15s;
}
.chat-input:focus { border-color: var(--accent); }
.chat-input:disabled { opacity: .5; cursor: not-allowed; }
.chat-input::placeholder { color: var(--text-muted); }

.send-btn {
  width: 38px; height: 38px;
  border-radius: 8px;
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: all .15s;
}
.send-btn:hover:not(:disabled) { opacity: .85; }
.send-btn:disabled { opacity: .4; cursor: not-allowed; }

/* 清空按钮 */
.input-actions { display: flex; gap: 8px; }
.action-btn {
  font-size: 11px;
  color: var(--text-muted);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0 2px;
  font-family: inherit;
}
.action-btn:hover { color: var(--text-secondary); }

/* 小 spinner */
.spinner-sm {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .8s linear infinite;
  display: inline-block;
}
</style>
