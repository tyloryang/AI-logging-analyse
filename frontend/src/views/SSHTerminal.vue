<template>
  <div class="ssh-page" :class="{ 'is-fullscreen': fullscreen }">

    <!-- Page header (hidden in fullscreen) -->
    <div class="ssh-header">
      <div class="ssh-header-left">
        <h1>SSH 终端</h1>
        <span class="subtitle">Web Terminal · 多会话</span>
      </div>
      <div class="ssh-header-right">
        <button class="btn btn-outline btn-sm" @click="showCredModal = true">凭证管理</button>
      </div>
    </div>

    <!-- Session tabs bar -->
    <div class="session-bar">
      <div
        v-for="s in sessions" :key="s.id"
        class="session-tab"
        :class="{ active: activeId === s.id, connected: s.connected, connecting: s.connecting }"
        @click="switchSession(s.id)"
      >
        <span class="tab-dot" :class="s.connected ? 'ok' : s.connecting ? 'ing' : 'off'"></span>
        <span class="tab-label">{{ s.label }}</span>
        <span class="tab-close" @click.stop="closeSession(s.id)">×</span>
      </div>
      <button class="btn-new-session" @click="showConnForm = !showConnForm">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新建
      </button>
      <div class="session-bar-right">
        <button class="btn btn-outline btn-sm" @click="toggleFullscreen">
          {{ fullscreen ? '退出全屏' : '全屏' }}
        </button>
      </div>
    </div>

    <!-- Connection form (collapsible) -->
    <transition name="slide-down">
      <div v-show="showConnForm" class="conn-form">
        <select class="ssh-input" @change="onSelectHost($event.target.value)" :value="form.instance">
          <option value="">选择主机...</option>
          <option v-for="h in hosts" :key="h.instance" :value="h.instance">
            {{ h.hostname || h.ip }} ({{ h.ip }}){{ (h.ssh_saved || h.credential_id) ? ' ✓' : '' }}
          </option>
        </select>
        <select class="ssh-input" v-model="form.credentialId" @change="onSelectCredential">
          <option value="">手动输入凭证</option>
          <option v-for="c in credentials" :key="c.id" :value="c.id">{{ c.name }} ({{ c.username }})</option>
        </select>
        <input v-model="form.host"     class="ssh-input host-input" placeholder="IP / 主机名" :disabled="!!form.instance" />
        <input v-model.number="form.port" class="ssh-input port-input" type="number" placeholder="22" :disabled="form.useSaved || !!form.credentialId" />
        <input v-model="form.username" class="ssh-input user-input" placeholder="用户名" :disabled="form.useSaved || !!form.credentialId" />
        <input v-model="form.password" class="ssh-input" type="password"
          :placeholder="form.useSaved || form.credentialId ? '已保存凭证' : '密码'"
          :disabled="form.useSaved || !!form.credentialId" />
        <span v-if="form.useSaved || form.credentialId" class="saved-badge">已保存</span>
        <button class="btn btn-primary btn-sm" @click="doConnect">连接</button>
      </div>
    </transition>

    <!-- Terminal area -->
    <div class="term-area">
      <!-- Welcome / empty state -->
      <div v-if="!sessions.length" class="welcome-panel">
        <div class="welcome-card">
          <div class="welcome-icon">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/>
            </svg>
          </div>
          <div class="welcome-title">SSH 终端</div>
          <div class="welcome-sub">支持多会话并行 · 凭证库快速连接</div>

          <div class="welcome-form">
            <div class="wf-row">
              <label>主机</label>
              <select class="ssh-input" @change="onSelectHost($event.target.value)" :value="form.instance">
                <option value="">选择主机...</option>
                <option v-for="h in hosts" :key="h.instance" :value="h.instance">
                  {{ h.hostname || h.ip }} ({{ h.ip }}){{ (h.ssh_saved || h.credential_id) ? ' ✓' : '' }}
                </option>
              </select>
            </div>
            <div class="wf-row">
              <label>凭证</label>
              <select class="ssh-input" v-model="form.credentialId" @change="onSelectCredential">
                <option value="">手动输入</option>
                <option v-for="c in credentials" :key="c.id" :value="c.id">{{ c.name }} ({{ c.username }})</option>
              </select>
            </div>
            <div class="wf-row">
              <label>主机 IP</label>
              <input v-model="form.host" class="ssh-input" placeholder="192.168.x.x" :disabled="!!form.instance" />
            </div>
            <div class="wf-row">
              <label>端口</label>
              <input v-model.number="form.port" class="ssh-input" placeholder="22" :disabled="form.useSaved || !!form.credentialId" />
            </div>
            <div class="wf-row">
              <label>用户名</label>
              <input v-model="form.username" class="ssh-input" placeholder="root" :disabled="form.useSaved || !!form.credentialId" />
            </div>
            <div class="wf-row">
              <label>密码</label>
              <input v-model="form.password" class="ssh-input" type="password"
                :placeholder="form.useSaved || form.credentialId ? '已保存凭证' : '输入密码'"
                :disabled="form.useSaved || !!form.credentialId" />
            </div>
          </div>

          <div class="welcome-actions">
            <span v-if="form.useSaved || form.credentialId" class="saved-badge">已保存凭证</span>
            <button class="btn btn-primary" @click="doConnect">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg>
              建立连接
            </button>
          </div>
        </div>
      </div>

      <!-- xterm containers -->
      <div
        v-for="s in sessions" :key="s.id"
        v-show="activeId === s.id"
        :ref="el => setTermRef(s.id, el)"
        class="term-container"
      ></div>
    </div>

    <!-- Credentials management modal -->
    <transition name="fade">
      <div v-if="showCredModal" class="modal-overlay" @click.self="showCredModal = false">
        <div class="modal-box">
          <div class="modal-header">
            <span>凭证库管理</span>
            <button class="btn btn-outline btn-sm" @click="showCredModal = false">✕</button>
          </div>
          <div class="modal-body">
            <div class="cred-form">
              <div class="cred-form-title">{{ credEditId ? '编辑凭证' : '新建凭证' }}</div>
              <div class="cred-form-row">
                <input v-model="credForm.name" placeholder="凭证名称，如：生产环境root" class="ssh-input" style="flex:2" />
                <input v-model="credForm.username" placeholder="用户名" class="ssh-input" style="flex:1" />
                <input v-model="credForm.password" type="password" :placeholder="credEditId ? '留空不修改' : '密码'" class="ssh-input" style="flex:1" />
                <input v-model.number="credForm.port" type="number" placeholder="端口" class="ssh-input" style="width:70px" />
                <button class="btn btn-primary btn-sm" @click="saveCred" :disabled="credSaving">
                  {{ credEditId ? '更新' : '添加' }}
                </button>
                <button v-if="credEditId" class="btn btn-outline btn-sm" @click="resetCredForm">取消</button>
              </div>
            </div>
            <div class="cred-list">
              <div v-if="!credentials.length" class="empty-state" style="padding:20px">暂无凭证</div>
              <div v-for="c in credentials" :key="c.id" class="cred-item">
                <div class="cred-info">
                  <span class="cred-name">{{ c.name }}</span>
                  <span class="cred-detail">{{ c.username }} : {{ c.port }}</span>
                </div>
                <div class="cred-actions">
                  <button class="btn btn-outline btn-sm" @click="editCred(c)">编辑</button>
                  <button class="btn btn-outline btn-sm" style="border-color:var(--error);color:var(--error)" @click="deleteCred(c.id)">删除</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'
import { api } from '../api/index.js'

const route = useRoute()

// ── State ─────────────────────────────────────────────────────────────────────
const hosts       = ref([])
const credentials = ref([])
const sessions    = ref([])   // [{ id, label, host, port, username, password, instance, useSaved, credentialId, connected, connecting }]
const activeId    = ref('')
const fullscreen  = ref(false)
const showConnForm = ref(true)

const form = reactive({ host: '', port: 22, username: 'root', password: '', instance: '', useSaved: false, credentialId: '' })

const showCredModal = ref(false)
const credForm      = reactive({ name: '', username: 'root', password: '', port: 22 })
const credEditId    = ref('')
const credSaving    = ref(false)

const _meta    = {}  // { [id]: { term, fitAddon, ws, resizeObserver } }
const _termEls = {}  // { [id]: HTMLElement }

// ── Helpers ───────────────────────────────────────────────────────────────────
function setTermRef(id, el) {
  if (el) _termEls[id] = el
  else delete _termEls[id]
}

function _makeTerminal() {
  return new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: '"JetBrains Mono", "Cascadia Code", "Fira Code", "Microsoft YaHei UI", "PingFang SC", "Noto Sans Mono CJK SC", Menlo, Monaco, monospace',
    theme: {
      background: '#0d1117', foreground: '#c9d1d9', cursor: '#58a6ff',
      selectionBackground: '#264f78',
      black: '#0d1117', red: '#ff7b72', green: '#7ee787', yellow: '#d29922',
      blue: '#58a6ff', magenta: '#bc8cff', cyan: '#76e3ea', white: '#c9d1d9',
    },
    scrollback: 5000,
  })
}

function _fitSession(id = activeId.value) {
  if (!id) return
  const m = _meta[id]
  if (!m?.fitAddon) return
  m.fitAddon.fit()
  const dims = m.fitAddon.proposeDimensions?.()
  if (dims && m.ws?.readyState === WebSocket.OPEN) {
    m.ws.send(`\x1b[RESIZE:${dims.cols},${dims.rows}]`)
  }
}

function _scheduleFit(id = activeId.value, delay = 0) {
  if (!id) return
  const run = () => requestAnimationFrame(() => _fitSession(id))
  delay > 0 ? setTimeout(run, delay) : nextTick(run)
}

function toggleFullscreen(force) {
  fullscreen.value = typeof force === 'boolean' ? force : !fullscreen.value
}

function handleKeydown(e) {
  if (e.key === 'Escape' && fullscreen.value) toggleFullscreen(false)
}

async function initSessionTerm(id) {
  const el = _termEls[id]
  if (!el || _meta[id]?.term) return
  const m = _meta[id]
  m.term = _makeTerminal()
  m.fitAddon = new FitAddon()
  m.term.loadAddon(m.fitAddon)
  m.term.open(el)
  await nextTick()
  _fitSession(id)
  m.resizeObserver = new ResizeObserver(() => {
    if (activeId.value === id) requestAnimationFrame(() => _fitSession(id))
  })
  m.resizeObserver.observe(el)
}

function _buildAuthMsg(s) {
  if (s.credentialId)
    return { type: 'auth', credential_id: s.credentialId, instance: s.instance, host: s.host }
  if ((s.useSaved || s.credentialId) && s.instance)
    return { type: 'auth', use_saved: true, instance: s.instance, host: s.host, port: s.port }
  return { type: 'auth', host: s.host, port: s.port, username: s.username, password: s.password }
}

async function _doConnect(id) {
  const s = sessions.value.find(x => x.id === id)
  if (!s) return
  const m = _meta[id]
  const useSaved = (s.useSaved || s.credentialId) && s.instance
  if (!useSaved && (!s.host || !s.username || !s.password)) {
    m.term?.writeln('\x1b[31m请填写完整连接信息\x1b[0m')
    return
  }
  s.connecting = true
  await nextTick()
  await initSessionTerm(id)
  m.term.clear()
  m.term.writeln(`\x1b[36m正在连接 ${s.label} ...\x1b[0m\r\n`)

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  m.ws = new WebSocket(`${proto}://${location.host}/api/ws/ssh`)
  m.ws.onopen = () => {
    m.ws.send(JSON.stringify(_buildAuthMsg(s)))
    s.connected = true; s.connecting = false
    s.label = s.username + '@' + s.host
    _scheduleFit(id)
    _scheduleFit(id, 240)
  }
  m.ws.onmessage = (e) => m.term.write(e.data)
  m.ws.onclose = () => {
    s.connected = false; s.connecting = false
    m.term?.writeln('\r\n\x1b[90m连接已关闭\x1b[0m')
  }
  m.ws.onerror = () => {
    s.connected = false; s.connecting = false
    m.term?.writeln('\r\n\x1b[31mWebSocket 连接错误\x1b[0m')
  }
  m.term.onData((data) => {
    if (m.ws?.readyState === WebSocket.OPEN) m.ws.send(data)
  })
  m.term.onResize(({ cols, rows }) => {
    if (m.ws?.readyState === WebSocket.OPEN) m.ws.send(`\x1b[RESIZE:${cols},${rows}]`)
  })
}

// ── Session operations ────────────────────────────────────────────────────────
function switchSession(id) {
  activeId.value = id
  _scheduleFit(id)
  _scheduleFit(id, 180)
}

function closeSession(id) {
  const m = _meta[id]
  if (m) {
    m.ws?.close()
    m.resizeObserver?.disconnect()
    m.term?.dispose()
    delete _meta[id]
  }
  const idx = sessions.value.findIndex(s => s.id === id)
  if (idx !== -1) sessions.value.splice(idx, 1)
  if (activeId.value === id) {
    const next = sessions.value[Math.max(0, idx - 1)]
    activeId.value = next?.id || ''
    if (next) { _scheduleFit(next.id); _scheduleFit(next.id, 180) }
    else showConnForm.value = true
  }
}

async function doConnect() {
  const useSaved = (form.useSaved || form.credentialId) && form.instance
  if (!useSaved && (!form.host || !form.username || !form.password)) {
    alert('请填写完整连接信息（主机、用户名、密码）')
    return
  }
  const id = `sess_${Date.now()}`
  const h = hosts.value.find(x => x.instance === form.instance)
  const label = h ? (h.hostname || h.ip) : form.host
  sessions.value.push({
    id, label,
    host: form.host, port: form.port,
    username: form.username, password: form.password,
    instance: form.instance, useSaved: form.useSaved,
    credentialId: form.credentialId,
    connected: false, connecting: false,
  })
  _meta[id] = { term: null, fitAddon: null, ws: null, resizeObserver: null }
  activeId.value = id
  showConnForm.value = false
  await nextTick()
  await _doConnect(id)
}

// ── Form helpers ──────────────────────────────────────────────────────────────
function onSelectHost(instance) {
  const h = hosts.value.find(x => x.instance === instance)
  if (!h) { form.instance = ''; return }
  form.host         = h.ip
  form.port         = h.ssh_port || 22
  form.username     = h.ssh_user || 'root'
  form.password     = ''
  form.instance     = h.instance
  form.useSaved     = !!(h.ssh_saved || h.credential_id)
  form.credentialId = h.credential_id || ''
  if (h.credential_id) {
    const c = credentials.value.find(x => x.id === h.credential_id)
    if (c) { form.port = c.port; form.username = c.username }
  }
}

function onSelectCredential() {
  if (form.credentialId) {
    const c = credentials.value.find(x => x.id === form.credentialId)
    if (c) { form.port = c.port; form.username = c.username; form.password = ''; form.useSaved = false }
  }
}

// ── Credential CRUD ───────────────────────────────────────────────────────────
async function loadCredentials() {
  try {
    const r = await api.listCredentials()
    credentials.value = r.data
  } catch (e) { console.error('加载凭证失败', e) }
}

function resetCredForm() {
  credForm.name = ''; credForm.username = 'root'; credForm.password = ''; credForm.port = 22
  credEditId.value = ''
}

function editCred(c) {
  credEditId.value = c.id
  credForm.name = c.name; credForm.username = c.username
  credForm.password = ''; credForm.port = c.port
}

async function saveCred() {
  if (!credForm.name) return alert('请输入凭证名称')
  if (!credEditId.value && !credForm.password) return alert('请输入密码')
  credSaving.value = true
  try {
    const payload = { name: credForm.name, username: credForm.username || 'root', password: credForm.password || '', port: credForm.port || 22 }
    if (credEditId.value) {
      await api.updateCredential(credEditId.value, payload)
    } else {
      await api.createCredential(payload)
    }
    resetCredForm()
    await loadCredentials()
  } catch (e) {
    alert('保存凭证失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误'))
  } finally {
    credSaving.value = false
  }
}

async function deleteCred(id) {
  if (!confirm('确定删除此凭证？已绑定该凭证的主机将需要重新配置。')) return
  await api.deleteCredential(id)
  await loadCredentials()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  window.addEventListener('keydown', handleKeydown)
  try {
    const [hostsRes] = await Promise.all([
      api.getHosts(),
      loadCredentials(),
    ])
    hosts.value = hostsRes.data

    // Auto-connect if navigated from CMDB with ?instance=xxx
    const { instance, credential_id } = route.query
    if (instance) {
      onSelectHost(instance)
      if (credential_id) form.credentialId = credential_id
      const h = hosts.value.find(x => x.instance === instance)
      if (h && (h.ssh_saved || h.credential_id || credential_id)) {
        await nextTick()
        doConnect()
      }
    }
  } catch (e) {
    console.error('SSH 初始化失败', e)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
  for (const id of Object.keys(_meta)) closeSession(id)
})
</script>

<style scoped>
.ssh-page {
  display: flex; flex-direction: column; height: 100%;
  overflow: hidden; padding: 8px 12px; gap: 8px;
  background: var(--bg-base);
}
.ssh-page.is-fullscreen {
  position: fixed; inset: 0; z-index: 1200;
  padding: 6px 8px;
}
.ssh-page.is-fullscreen .ssh-header { display: none; }

/* Header */
.ssh-header {
  display: flex; align-items: center; justify-content: space-between;
  flex-shrink: 0;
}
.ssh-header-left { display: flex; align-items: baseline; gap: 10px; }
.ssh-header-left h1 { font-size: 15px; font-weight: 600; color: var(--text-primary); }
.ssh-header-left .subtitle { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }

/* Session bar */
.session-bar {
  display: flex; align-items: center; gap: 4px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 5px 8px;
  flex-shrink: 0; min-height: 38px; flex-wrap: wrap;
}
.session-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 10px 3px 8px; border-radius: 3px; cursor: pointer;
  font-size: 12px; color: var(--text-secondary);
  background: var(--bg-surface); border: 1px solid var(--border);
  transition: all .12s; user-select: none;
}
.session-tab:hover { border-color: var(--accent); color: var(--text-primary); }
.session-tab.active { background: var(--accent-dim); border-color: var(--accent); color: var(--text-primary); }
.tab-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.tab-dot.ok  { background: var(--success); }
.tab-dot.ing { background: var(--warning); animation: blink .8s step-start infinite; }
.tab-dot.off { background: var(--text-muted); }
@keyframes blink { 50% { opacity: 0; } }
.tab-label { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tab-close { color: var(--text-muted); font-size: 14px; line-height: 1; margin-left: 2px; padding: 0 2px; border-radius: 2px; }
.tab-close:hover { color: var(--error); background: rgba(248,81,73,.1); }
.btn-new-session {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 10px; border-radius: 3px;
  border: 1px dashed var(--border); background: transparent;
  color: var(--text-muted); font-size: 12px; cursor: pointer;
  font-family: inherit; transition: all .12s;
}
.btn-new-session:hover { border-color: var(--accent); color: var(--accent); }
.session-bar-right { margin-left: auto; }

/* Connection form */
.conn-form {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-card); padding: 10px 12px;
  flex-shrink: 0;
}
.ssh-input {
  background: var(--bg-input); border: 1px solid var(--border);
  color: var(--text-primary); border-radius: var(--radius);
  padding: 5px 9px; font-size: 13px; font-family: inherit;
  outline: none; transition: border-color .12s, box-shadow .12s;
}
.ssh-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.ssh-input:disabled { opacity: .5; cursor: not-allowed; }
.host-input { width: 160px; }
.port-input { width: 72px; }
.user-input { width: 110px; }
.saved-badge {
  display: inline-flex; align-items: center; padding: 2px 8px;
  background: rgba(63,185,80,.1); border: 1px solid rgba(63,185,80,.3);
  color: var(--success); border-radius: 3px; font-size: 11px; font-weight: 500;
}
.slide-down-enter-active, .slide-down-leave-active { transition: all .15s ease; max-height: 80px; overflow: hidden; }
.slide-down-enter-from, .slide-down-leave-to { max-height: 0; opacity: 0; }

/* Terminal area */
.term-area { flex: 1; min-height: 0; position: relative; overflow: hidden; }
.term-container { width: 100%; height: 100%; }

/* Welcome panel */
.welcome-panel {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-base);
}
.welcome-card {
  width: 420px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-lg); padding: 28px 28px 24px;
  box-shadow: var(--shadow-md);
}
.welcome-icon {
  width: 52px; height: 52px;
  background: var(--accent-dim); border: 1px solid var(--border-accent);
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  color: var(--accent); margin-bottom: 14px;
}
.welcome-title { font-size: 16px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; }
.welcome-sub { font-size: 12px; color: var(--text-muted); margin-bottom: 20px; }
.welcome-form { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.wf-row { display: flex; align-items: center; gap: 10px; }
.wf-row label { width: 52px; font-size: 12px; color: var(--text-secondary); text-align: right; flex-shrink: 0; }
.wf-row .ssh-input { flex: 1; }
.welcome-actions { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }

/* Modal */
.modal-overlay {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center;
}
.modal-box {
  width: 680px; max-width: 96vw;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-lg); overflow: hidden;
  box-shadow: var(--shadow-md);
}
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 20px; border-bottom: 1px solid var(--border);
  font-size: 14px; font-weight: 600; color: var(--text-primary);
}
.modal-body { padding: 16px 20px; max-height: 70vh; overflow-y: auto; }
.cred-form { margin-bottom: 16px; }
.cred-form-title { font-size: 12px; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase; letter-spacing: .05em; }
.cred-form-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.cred-list { display: flex; flex-direction: column; gap: 6px; }
.cred-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 12px; background: var(--bg-surface);
  border-radius: var(--radius); border: 1px solid var(--border-light);
}
.cred-info { display: flex; flex-direction: column; gap: 2px; }
.cred-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.cred-detail { font-size: 11px; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }
.cred-actions { display: flex; gap: 6px; }
</style>
