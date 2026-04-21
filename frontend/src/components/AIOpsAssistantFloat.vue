<template>
  <teleport to="body">
    <transition name="ai-fade">
      <button v-if="open" class="ai-mask" type="button" @click="open = false"></button>
    </transition>

    <transition name="ai-pop">
      <section v-if="open" class="ai-panel">
        <header class="ai-head">
          <div class="ai-head-main">
            <span class="ai-icon" v-html="AGENT_ICON"></span>
            <div class="ai-head-copy">
              <div class="ai-title-row">
                <h2>AIOps 智能助手</h2>
                <span class="ai-pill blue">{{ aiModelShort }}</span>
                <span class="ai-pill amber">{{ streaming ? '执行中' : '执行需确认' }}</span>
              </div>
              <p>{{ description }}</p>
            </div>
          </div>
          <div class="ai-head-actions">
            <button type="button" :disabled="streaming" @click="newConversation">新会话</button>
            <button type="button" @click="open = false">收起</button>
          </div>
        </header>

        <div class="ai-body">
          <aside class="ai-side">
            <div class="ai-side-title">
              <span>会话历史</span>
              <em>{{ filteredHistory.length }}</em>
            </div>
            <div v-if="filteredHistory.length" class="ai-history">
              <button
                v-for="item in filteredHistory"
                :key="item.conv_id"
                class="ai-history-item"
                :class="{ active: item.conv_id === convId }"
                type="button"
                @click="loadConversation(item)"
              >
                <strong>{{ item.title || '新会话' }}</strong>
                <span>{{ fmtHistoryDate(item.updated_at) }}</span>
              </button>
            </div>
            <div v-else class="ai-empty">还没有历史会话</div>

            <div class="ai-side-title sub">
              <span>快捷问题</span>
            </div>
            <div class="ai-prompts">
              <button
                v-for="prompt in prompts"
                :key="prompt"
                type="button"
                :disabled="streaming"
                @click="sendMessage(prompt)"
              >
                {{ prompt }}
              </button>
            </div>
          </aside>

          <div class="ai-chat">
            <div class="ai-scroll">
              <div v-if="!messages.length" class="ai-welcome">
                <span class="ai-welcome-icon" v-html="AGENT_ICON"></span>
                <h3>你好，我是你的 AIOps 智能助手</h3>
                <p>我可以结合当前页面上下文查询资源、分析告警、梳理日志，并生成执行建议。</p>
                <div class="ai-chips">
                  <button
                    v-for="prompt in prompts.slice(0, 4)"
                    :key="prompt"
                    type="button"
                    :disabled="streaming"
                    @click="sendMessage(prompt)"
                  >
                    {{ prompt }}
                  </button>
                </div>
              </div>

              <template v-else>
                <div v-for="msg in messages" :key="msg.id" class="ai-row" :class="msg.role">
                  <div v-if="msg.role === 'user'" class="ai-user">{{ msg.content }}</div>
                  <div v-else class="ai-assistant">
                    <span class="ai-avatar" v-html="AGENT_ICON"></span>
                    <div class="ai-assistant-body">
                      <div
                        v-for="tc in msg.toolCalls || []"
                        :key="tc.id"
                        class="ai-tool"
                        :class="{ pending: tc.pending }"
                      >
                        <button class="ai-tool-head" type="button" @click="tc.expanded = !tc.expanded">
                          <span class="ai-dot" :class="{ pending: tc.pending }"></span>
                          <strong>{{ TOOL_LABELS[tc.tool] || tc.tool }}</strong>
                          <span class="ai-tool-input">{{ formatInput(tc.input) }}</span>
                          <span>{{ tc.expanded ? '收起' : '展开' }}</span>
                        </button>
                        <pre v-if="tc.expanded && tc.output">{{ tc.output }}</pre>
                      </div>

                      <div v-if="msg.content || msg.streaming" class="ai-bubble">
                        <div class="ai-content" v-html="renderContent(msg.content)"></div>
                        <span v-if="msg.streaming" class="ai-cursor"></span>
                      </div>
                    </div>
                  </div>
                </div>
                <div ref="bottomRef"></div>
              </template>
            </div>

            <footer class="ai-input-wrap">
              <div class="ai-input-box">
                <textarea
                  ref="inputRef"
                  v-model="inputText"
                  class="ai-input"
                  :placeholder="placeholder"
                  :disabled="streaming"
                  rows="1"
                  @keydown.enter.exact.prevent="onSend"
                  @keydown.esc.stop="open = false"
                  @input="autoResize"
                ></textarea>
                <button class="ai-send" type="button" :disabled="streaming || !inputText.trim()" @click="onSend">
                  <span v-if="streaming" class="ai-spin"></span>
                  <span v-else v-html="SEND_ICON"></span>
                </button>
              </div>
              <div class="ai-foot">
                <span>Enter 发送，Shift + Enter 换行，Esc 收起</span>
                <button v-if="messages.length" type="button" :disabled="streaming" @click="clearChat">清空</button>
              </div>
            </footer>
          </div>
        </div>
      </section>
    </transition>

    <button class="ai-launcher" :class="{ active: open, streaming, docked: !open }" type="button" @click="toggleOpen">
      <span class="ai-launcher-icon" v-html="AGENT_ICON"></span>
      <span class="ai-launcher-text">
        <strong>AIOps</strong>
        <small>智能助手</small>
      </span>
      <span class="ai-status-dot"></span>
    </button>
  </teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const AGENT_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M9 11V7a3 3 0 0 1 6 0v4"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/><path d="M12 3v2"/></svg>`
const SEND_ICON = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`
const TOOL_LABELS = { query_error_logs: '查询错误日志', count_errors_by_service: '统计服务错误数', get_services_list: '获取服务列表', get_host_metrics: '获取主机指标', inspect_all_hosts: '全量巡检', query_recent_logs: '查询最近日志' }
const PROMPTS = {
  'obs-logs': ['帮我分析最近 30 分钟错误日志热点', '最近哪个服务报错最多', '帮我定位一个典型异常链路', '总结日志里的高风险问题'],
  'obs-grafana': ['解释当前看板最异常的波动', '最近 1 小时有哪些高优先级告警', '从 CPU/内存看当前风险', '给我一个排查顺序'],
  'obs-trace': ['帮我分析最近最慢的调用链', '有哪些服务间调用明显异常', 'Trace 里最值得优先处理的问题', '给我一段链路追踪排障建议'],
  containers: ['检查 K8s 集群是否有异常 Pod', '最近哪些 Deployment 失败', '帮我看看节点资源瓶颈', '总结容器平台当前风险点'],
  default: ['当前未确认的严重告警有哪些', '分析生产核心链路最近异常', '帮我总结今天平台运行风险', '生成一份值班巡检建议'],
}

const open = ref(typeof window !== 'undefined' && window.localStorage.getItem('aiops-assistant-open') === '1')
const aiModelShort = ref('AI')
const convId = ref(genUUID())
const historyList = ref([])
const messages = ref([])
const inputText = ref('')
const streaming = ref(false)
const inputRef = ref(null)
const bottomRef = ref(null)
let msgId = 0

const prompts = computed(() => PROMPTS[route.name] || PROMPTS.default)
const filteredHistory = computed(() => historyList.value.filter((item) => item.mode === 'chat'))
const description = computed(() => `你好，我可以基于 ${routeLabel(route.name)} 帮你查询资源、分析告警、生成执行建议。`)
const placeholder = computed(() => `围绕 ${routeLabel(route.name)} 提问，或直接输入你的运维问题...`)

function genUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => ((Math.random() * 16 | 0) & (c === 'x' ? 15 : 3) | (c === 'y' ? 8 : 0)).toString(16))
}

function routeLabel(name) {
  return {
    dashboard: '平台总览',
    'obs-logs': '日志中心',
    'obs-grafana': '监控看板',
    'obs-trace': '链路追踪',
    containers: '容器管理',
    middleware: '中间件',
    settings: '系统配置',
    'aiops-config': '智能体配置',
  }[name] || '当前页面'
}

function fmtHistoryDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86400000)
  if (diffDays === 0) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (diffDays < 7) return `${diffDays}天前`
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function formatInput(input) {
  if (!input || typeof input !== 'object') return ''
  return Object.entries(input).filter(([, v]) => v !== '' && v !== null && v !== undefined).slice(0, 3).map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`).join(' · ')
}

function renderContent(text) {
  if (!text) return ''
  let safe = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  safe = safe.replace(/^(\d+)\.\s+(.+)$/gm, '<div class="ai-li"><span class="ai-li-num">$1</span>$2</div>')
  safe = safe.replace(/^[-•]\s+(.+)$/gm, '<div class="ai-li"><span class="ai-li-dot">•</span>$1</div>')
  safe = safe.replace(/`([^`]+)`/g, '<code class="ai-code">$1</code>')
  safe = safe.replace(/## (.+?)(\n|$)/g, '<div class="ai-section-title">$1</div>')
  return safe.replace(/\n/g, '<br>')
}

function scrollBottom(behavior = 'smooth') {
  nextTick(() => bottomRef.value?.scrollIntoView({ behavior }))
}

function focusInput() {
  nextTick(() => inputRef.value?.focus())
}

function autoResize(event) {
  const el = event.target
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

function clearChat() {
  messages.value = []
  inputText.value = ''
  streaming.value = false
  convId.value = genUUID()
  if (inputRef.value) inputRef.value.style.height = 'auto'
}

function newConversation() {
  clearChat()
  focusInput()
}

function toggleOpen() {
  open.value = !open.value
  if (open.value) {
    focusInput()
    loadHistoryList()
  }
}

async function fetchAiModel() {
  try {
    const resp = await fetch('/api/health', { credentials: 'include' })
    if (!resp.ok) return
    const data = await resp.json()
    const provider = data.ai_provider || ''
    const match = provider.match(/\((.+)\)/)
    aiModelShort.value = provider.startsWith('Anthropic') ? 'Claude' : (match ? match[1].slice(0, 10) : (provider.slice(0, 10) || 'AI'))
  } catch {}
}

async function loadHistoryList() {
  try {
    const resp = await fetch('/api/agent/conversations', { credentials: 'include' })
    if (resp.ok) historyList.value = await resp.json()
  } catch {}
}

async function saveConversation() {
  if (!messages.value.length || streaming.value) return
  const title = messages.value.find((item) => item.role === 'user')?.content?.slice(0, 60) || '新会话'
  const plain = messages.value.map((item) => ({ id: item.id, role: item.role, content: item.content, toolCalls: item.role === 'assistant' ? (item.toolCalls || []).map((tc) => ({ id: tc.id, tool: tc.tool, input: tc.input, output: tc.output, pending: false, expanded: false })) : [], streaming: false, done: true }))
  try {
    await fetch(`/api/agent/conversations/${convId.value}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ mode: 'chat', title, messages: plain }) })
    await loadHistoryList()
  } catch {}
}

async function loadConversation(item) {
  if (streaming.value) return
  try {
    const resp = await fetch(`/api/agent/conversations/${item.conv_id}`, { credentials: 'include' })
    if (!resp.ok) return
    const data = await resp.json()
    convId.value = item.conv_id
    messages.value = (data.messages || []).map((message) => reactive({ ...message, toolCalls: (message.toolCalls || []).map((tc) => reactive({ ...tc })) }))
    open.value = true
    scrollBottom('auto')
  } catch {}
}

function onSend() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return
  sendMessage(text)
  inputText.value = ''
  if (inputRef.value) inputRef.value.style.height = 'auto'
}

async function sendMessage(text) {
  if (!text || streaming.value) return
  open.value = true
  messages.value.push({ id: ++msgId, role: 'user', content: text })
  const assistant = reactive({ id: ++msgId, role: 'assistant', content: '', toolCalls: [], streaming: true, done: false })
  messages.value.push(assistant)
  streaming.value = true
  scrollBottom()

  try {
    const resp = await fetch('/api/agent/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ message: text, conv_id: convId.value }) })
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
        chunk.split('\n').forEach((line) => {
          if (!line.startsWith('data: ')) return
          try { handleEvent(JSON.parse(line.slice(6)), assistant) } catch {}
        })
      }
    }
  } catch (error) {
    assistant.content += `${assistant.content ? '\n\n' : ''}❌ 请求失败：${error.message}`
    assistant.streaming = false
    assistant.done = true
    streaming.value = false
  }
}

function handleEvent(data, msg) {
  if (data.type === 'token') msg.content += data.text || ''
  if (data.type === 'tool_start') msg.toolCalls.push(reactive({ id: ++msgId, tool: data.tool || '', input: data.input || {}, output: '', pending: true, expanded: false }))
  if (data.type === 'tool_end') {
    const tc = [...msg.toolCalls].reverse().find((item) => item.tool === data.tool && item.pending)
    if (tc) { tc.output = data.output || ''; tc.pending = false }
  }
  if (data.type === 'replace_content') msg.content = data.text || ''
  if (data.type === 'done' || data.type === 'error') {
    if (data.type === 'error') msg.content += `${msg.content ? '\n\n' : ''}❌ ${data.message || '未知错误'}`
    msg.streaming = false
    msg.done = true
    streaming.value = false
    saveConversation()
  }
  scrollBottom()
}

watch(open, (value) => {
  if (typeof window !== 'undefined') window.localStorage.setItem('aiops-assistant-open', value ? '1' : '0')
  if (value) focusInput()
})

watch(() => route.fullPath, () => {
  if (route.name === 'aiops-assistant') open.value = false
})

onMounted(() => {
  fetchAiModel()
  loadHistoryList()
  window.addEventListener('keydown', onEsc)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onEsc)
  if (!streaming.value && messages.value.length) saveConversation()
})

function onEsc(event) {
  if (event.key === 'Escape' && open.value) open.value = false
}
</script>

<style scoped>
.ai-mask{position:fixed;inset:0;border:none;background:rgba(148,163,184,.14);backdrop-filter:blur(8px);z-index:1090}
.ai-panel{position:fixed;right:24px;bottom:94px;width:min(980px,calc(100vw - 48px));height:min(78vh,760px);border-radius:28px;overflow:hidden;border:1px solid rgba(148,163,184,.22);background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(248,250,252,.94));box-shadow:0 28px 90px rgba(15,23,42,.18),0 8px 24px rgba(15,23,42,.08);z-index:1100}
.ai-head{display:flex;justify-content:space-between;gap:20px;padding:18px 20px 14px;border-bottom:1px solid rgba(226,232,240,.9);background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(255,247,237,.72))}
.ai-head-main{display:flex;gap:12px;min-width:0}.ai-icon,.ai-welcome-icon,.ai-avatar,.ai-launcher-icon{display:flex;align-items:center;justify-content:center;color:#1d9bf0;background:linear-gradient(135deg,rgba(14,165,233,.16),rgba(59,130,246,.1))}
.ai-icon{width:40px;height:40px;border-radius:14px;flex-shrink:0}.ai-title-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.ai-title-row h2{font-size:16px;font-weight:700;color:#111827}.ai-head-copy p{margin-top:6px;font-size:13px;color:#64748b}
.ai-pill{display:inline-flex;align-items:center;height:24px;padding:0 10px;border-radius:999px;font-size:11px;font-weight:600}.ai-pill.blue{background:rgba(14,165,233,.1);color:#0ea5e9}.ai-pill.amber{background:rgba(251,191,36,.14);color:#b45309}
.ai-head-actions{display:flex;gap:10px}.ai-head-actions button,.ai-foot button{border:none;background:transparent;color:#475569;font-size:13px;font-weight:600;cursor:pointer}.ai-head-actions button:disabled,.ai-foot button:disabled{opacity:.45;cursor:not-allowed}
.ai-body{display:flex;height:calc(100% - 73px);min-height:0}.ai-side{width:220px;flex-shrink:0;padding:14px 10px 14px 14px;border-right:1px solid rgba(226,232,240,.9);background:linear-gradient(180deg,rgba(248,250,252,.96),rgba(255,255,255,.8));display:flex;flex-direction:column;gap:10px}
.ai-side-title{display:flex;align-items:center;justify-content:space-between;font-size:13px;font-weight:700;color:#475569}.ai-side-title.sub{margin-top:4px}.ai-side-title em{min-width:24px;height:24px;padding:0 8px;border-radius:999px;background:rgba(59,130,246,.08);color:#64748b;font-size:12px;display:inline-flex;align-items:center;justify-content:center;font-style:normal}
.ai-history,.ai-prompts{display:flex;flex-direction:column;gap:8px;overflow-y:auto;padding-right:4px}.ai-history-item,.ai-prompts button,.ai-chips button{border:none;cursor:pointer}
.ai-history-item,.ai-prompts button{width:100%;padding:11px 12px;text-align:left;border-radius:14px;background:rgba(255,255,255,.9);box-shadow:inset 0 0 0 1px rgba(226,232,240,.95)}
.ai-history-item.active{box-shadow:inset 0 0 0 1px rgba(59,130,246,.28),0 10px 20px rgba(37,99,235,.08);background:linear-gradient(180deg,rgba(239,246,255,.96),rgba(255,255,255,.92))}
.ai-history-item strong,.ai-prompts button{display:block;font-size:13px;line-height:1.45;color:#334155}.ai-history-item span{display:block;margin-top:6px;font-size:12px;color:#94a3b8}.ai-empty{padding:8px 4px 2px;font-size:12px;color:#94a3b8}
.ai-chat{flex:1;min-width:0;display:flex;flex-direction:column;min-height:0}.ai-scroll{flex:1;overflow-y:auto;padding:14px 18px 8px;display:flex;flex-direction:column;gap:14px}
.ai-welcome{flex:1;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:12px;padding:12px 6px}.ai-welcome-icon{width:52px;height:52px;border-radius:16px}.ai-welcome h3{font-size:24px;font-weight:700;color:#0f172a}.ai-welcome p{max-width:620px;font-size:14px;line-height:1.7;color:#64748b}
.ai-chips{display:flex;flex-wrap:wrap;gap:10px}.ai-chips button{padding:9px 14px;border-radius:999px;background:rgba(239,246,255,.96);box-shadow:inset 0 0 0 1px rgba(125,211,252,.4);color:#0369a1;font-size:13px}
.ai-row{display:flex}.ai-row.user{justify-content:flex-end}.ai-user{max-width:min(72%,640px);padding:12px 16px;border-radius:18px 18px 6px 18px;background:linear-gradient(135deg,#60a5fa,#3b82f6);color:#fff;font-size:14px;line-height:1.65;box-shadow:0 14px 32px rgba(59,130,246,.18);white-space:pre-wrap;word-break:break-word}
.ai-assistant{display:flex;gap:10px;max-width:min(88%,760px)}.ai-avatar{width:30px;height:30px;border-radius:10px;flex-shrink:0;margin-top:2px}.ai-assistant-body{min-width:0;display:flex;flex-direction:column;gap:10px}
.ai-bubble{padding:14px 16px;border-radius:8px 18px 18px 18px;background:rgba(255,255,255,.92);box-shadow:inset 0 0 0 1px rgba(226,232,240,.95);color:#0f172a;font-size:14px;line-height:1.75}
.ai-cursor{display:inline-block;width:2px;height:14px;margin-left:2px;background:#2563eb;vertical-align:middle;animation:ai-blink .9s step-end infinite}
.ai-tool{background:rgba(255,255,255,.95);box-shadow:inset 0 0 0 1px rgba(226,232,240,.95);border-radius:16px;overflow:hidden}.ai-tool.pending{box-shadow:inset 0 0 0 1px rgba(251,191,36,.3)}
.ai-tool-head{width:100%;display:flex;align-items:center;gap:10px;padding:12px 14px;background:transparent;text-align:left}.ai-dot{width:10px;height:10px;border-radius:999px;background:#22c55e;flex-shrink:0}.ai-dot.pending{background:#f59e0b;box-shadow:0 0 0 4px rgba(245,158,11,.14)}
.ai-tool-head strong{font-size:13px;font-weight:700;color:#0f172a}.ai-tool-input{flex:1;font-size:12px;color:#64748b;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.ai-tool pre{margin:0 14px 14px;padding:10px 12px;border-radius:12px;background:#f8fafc;color:#475569;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;max-height:220px;overflow-y:auto}
.ai-input-wrap{padding:12px 18px 16px;border-top:1px solid rgba(226,232,240,.9);background:rgba(255,255,255,.92)}.ai-input-box{display:flex;align-items:flex-end;gap:10px}
.ai-input{flex:1;min-height:76px;max-height:160px;resize:none;border:none;outline:none;background:#fff;border-radius:16px;box-shadow:inset 0 0 0 1px rgba(59,130,246,.38);padding:14px 16px;font-size:14px;line-height:1.6;color:#0f172a;font-family:inherit}.ai-input::placeholder{color:#94a3b8}.ai-input:disabled{opacity:.6;cursor:not-allowed}
.ai-send{width:46px;height:46px;border:none;border-radius:14px;background:linear-gradient(135deg,#60a5fa,#3b82f6);color:#fff;display:inline-flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 12px 28px rgba(59,130,246,.22)}.ai-send:disabled{opacity:.45;cursor:not-allowed;box-shadow:none}
.ai-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:10px;font-size:12px;color:#94a3b8}
.ai-launcher{position:fixed;right:24px;bottom:22px;height:62px;min-width:134px;padding:8px 12px 8px 10px;border:none;border-radius:999px;background:rgba(255,255,255,.96);box-shadow:inset 0 0 0 1px rgba(59,130,246,.18),0 16px 42px rgba(37,99,235,.16);display:inline-flex;align-items:center;gap:10px;cursor:pointer;z-index:1110;transition:right .22s ease,transform .18s ease,box-shadow .18s ease,background .18s ease}.ai-launcher:not(.docked):hover{transform:translateY(-1px)}
.ai-launcher.docked{right:-118px;bottom:26px;min-width:158px;padding:8px 16px 8px 10px;border-radius:22px 0 0 22px;background:rgba(255,255,255,.98);box-shadow:inset 0 0 0 1px rgba(59,130,246,.22),0 18px 42px rgba(15,23,42,.14)}
.ai-launcher.docked:hover{right:-14px}
.ai-launcher.active{background:rgba(239,246,255,.98)}.ai-launcher-icon{width:42px;height:42px;border-radius:50%;flex-shrink:0}.ai-launcher-text{display:flex;flex-direction:column;align-items:flex-start;color:#334155;text-align:left}.ai-launcher.docked .ai-launcher-text{min-width:72px}.ai-launcher-text strong{font-size:14px;line-height:1.1;font-weight:700}.ai-launcher-text small{margin-top:2px;font-size:11px;line-height:1.1;color:#64748b}
.ai-status-dot{width:10px;height:10px;margin-left:auto;border-radius:999px;background:#22c55e;box-shadow:0 0 0 3px rgba(34,197,94,.16)}.ai-launcher.streaming .ai-status-dot{background:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,.16)}
.ai-spin{width:14px;height:14px;border-radius:999px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;animation:ai-rotate .8s linear infinite}
.ai-content :deep(.ai-section-title){margin:12px 0 6px;padding-left:10px;border-left:3px solid #3b82f6;color:#2563eb;font-weight:700}.ai-content :deep(.ai-li){display:flex;gap:8px;margin:4px 0}.ai-content :deep(.ai-li-num){width:18px;height:18px;flex-shrink:0;border-radius:999px;display:inline-flex;align-items:center;justify-content:center;background:#3b82f6;color:#fff;font-size:10px;font-weight:700}.ai-content :deep(.ai-li-dot){color:#3b82f6;font-weight:700}.ai-content :deep(.ai-code){padding:2px 6px;border-radius:6px;background:#eff6ff;color:#2563eb;font-family:'JetBrains Mono','Cascadia Code',monospace;font-size:12px}
.ai-fade-enter-active,.ai-fade-leave-active{transition:opacity .2s ease}.ai-fade-enter-from,.ai-fade-leave-to{opacity:0}.ai-pop-enter-active,.ai-pop-leave-active{transition:transform .22s ease,opacity .22s ease}.ai-pop-enter-from,.ai-pop-leave-to{opacity:0;transform:translateY(12px) scale(.98)}
@keyframes ai-rotate{to{transform:rotate(360deg)}}@keyframes ai-blink{50%{opacity:0}}
@media (max-width:1080px){.ai-panel{width:calc(100vw - 24px);right:12px;bottom:86px;height:min(82vh,760px)}.ai-side{width:196px}.ai-launcher:not(.docked){right:12px;bottom:14px}}
@media (max-width:860px){.ai-panel{width:calc(100vw - 16px);right:8px;height:calc(100vh - 88px);bottom:78px;border-radius:22px}.ai-side{display:none}.ai-head{padding:16px 16px 12px}.ai-scroll{padding:12px 14px 8px}.ai-input-wrap{padding:10px 14px 14px}.ai-user,.ai-assistant{max-width:100%}.ai-launcher.docked{right:12px;bottom:14px;min-width:134px;padding:8px 12px 8px 10px;border-radius:999px}.ai-launcher.docked:hover{right:12px}}
</style>
