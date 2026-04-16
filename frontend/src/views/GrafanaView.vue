<template>
  <div class="grafana-page">
    <!-- Header -->
    <div class="page-header">
      <div class="header-left">
        <h1>Grafana 监控</h1>
        <span class="subtitle">
          {{ grafanaUrl || '未配置 Grafana URL' }}
          <span v-if="discovered" class="discover-badge">自动发现 {{ boards.length }} 个</span>
          <span v-else-if="discoverError" class="discover-warn" :title="discoverError">配置模式</span>
        </span>
      </div>
      <div class="header-actions">
        <!-- 自动发现按钮 -->
        <button
          class="btn-icon btn-discover"
          :class="{ spinning: discovering }"
          title="从 Grafana 自动发现全部看板"
          @click="discoverBoards"
          :disabled="discovering || !grafanaUrl"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        </button>
        <select v-model="selectedBoard" class="board-select" @change="onBoardChange">
          <option v-for="b in boards" :key="b.id" :value="b.id">{{ b.title }}</option>
        </select>
        <button class="btn-icon" title="刷新画面" @click="reloadFrame">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
        </button>
        <a v-if="currentUrl" :href="currentUrl" target="_blank" class="btn-icon" title="在新标签打开">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/>
            <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </a>
      </div>
    </div>

    <!-- discover error hint -->
    <div v-if="discoverError && grafanaUrl" class="discover-hint">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      <span>自动发现失败：<b>{{ discoverError }}</b></span>
      <span class="hint-link" @click="runDiag">诊断</span>
      <span class="hint-sep">·</span>
      <span class="hint-link" @click="$router.push('/settings')">系统配置</span>
    </div>

    <!-- diag result -->
    <div v-if="diagResult" class="diag-panel">
      <div class="diag-row"><span class="diag-k">Grafana URL</span><span class="diag-v">{{ diagResult.grafana_url || '未设置' }}</span></div>
      <div class="diag-row"><span class="diag-k">API Key</span><span class="diag-v" :class="diagResult.api_key_set ? 'ok' : 'warn'">{{ diagResult.api_key_set ? '已配置' : '未配置' }}</span></div>
      <div class="diag-row"><span class="diag-k">健康检查</span><span class="diag-v" :class="diagResult.health_ok ? 'ok' : 'err'">{{ diagResult.health_ok ? '正常' : diagResult.health_error }}</span></div>
      <div class="diag-row"><span class="diag-k">看板搜索</span><span class="diag-v" :class="diagResult.search_ok ? 'ok' : 'err'">{{ diagResult.search_ok ? `正常（${diagResult.search_count} 个看板）` : diagResult.search_error }}</span></div>
      <button class="diag-close" @click="diagResult = null">×</button>
    </div>

    <!-- Tab bar -->
    <div class="tab-bar">
      <button
        v-for="b in boards"
        :key="b.id"
        class="tab-btn"
        :class="{ active: selectedBoard === b.id }"
        @click="selectedBoard = b.id; onBoardChange()"
      >
        <span class="tab-icon" v-html="GRAFANA_ICON"></span>
        {{ b.title }}
        <span v-if="b.folder && b.folder !== 'General'" class="tab-folder">{{ b.folder }}</span>
      </button>
      <button v-if="discovering" class="tab-btn tab-loading" disabled>
        <span class="mini-spinner"></span> 发现中...
      </button>
      <button class="tab-btn tab-add" title="前往系统配置管理看板" @click="$router.push('/settings')">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        配置
      </button>
    </div>

    <!-- Not configured -->
    <div v-if="!grafanaUrl" class="empty-grafana">
      <div class="empty-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
      </div>
      <h3>未配置 Grafana 地址</h3>
      <p>请前往系统配置页面填写 Grafana URL，然后刷新本页。</p>
      <button class="btn-primary" @click="$router.push('/settings')">前往系统配置</button>
    </div>

    <!-- iframe wrapper -->
    <div v-else class="iframe-wrap">
      <!-- Loading overlay -->
      <div v-if="frameLoading" class="frame-loading">
        <div class="spinner"></div>
        <span>加载中...</span>
      </div>

      <!-- Grafana iframe in kiosk mode -->
      <iframe
        v-if="currentUrl"
        :key="frameKey"
        :src="currentUrl"
        class="grafana-frame"
        allowfullscreen
        allow="fullscreen"
        @load="frameLoading = false"
        @error="onFrameError"
        referrerpolicy="no-referrer"
      ></iframe>

      <!-- Embed blocked notice -->
      <div v-if="embedBlocked" class="embed-blocked">
        <div class="blocked-icon">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
        </div>
        <h3>Grafana 拒绝了嵌入请求</h3>
        <p>Grafana 默认禁止 iframe 嵌入，需在 <code>grafana.ini</code> 中启用：</p>
        <pre class="config-block">[security]
allow_embedding = true</pre>
        <p>或通过环境变量：<code>GF_SECURITY_ALLOW_EMBEDDING=true</code></p>
        <a :href="currentUrl" target="_blank" class="btn-primary">在新标签中打开 Grafana</a>
      </div>
    </div>

    <!-- Time range toolbar -->
    <div v-if="grafanaUrl" class="time-toolbar">
      <span class="toolbar-label">时间范围</span>
      <div class="time-presets">
        <button
          v-for="t in TIME_PRESETS"
          :key="t.value"
          class="preset-btn"
          :class="{ active: timeRange === t.value }"
          @click="timeRange = t.value; rebuildUrl()"
        >{{ t.label }}</button>
      </div>
      <label class="kiosk-toggle">
        <input type="checkbox" v-model="kioskMode" @change="rebuildUrl()">
        <span>Kiosk 模式</span>
      </label>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api/index.js'

// ── 状态 ──────────────────────────────────────────────────────────────────
const boards        = ref([])
const grafanaUrl    = ref('')
const selectedBoard = ref('')
const currentUrl    = ref('')
const frameKey      = ref(0)
const frameLoading  = ref(false)
const embedBlocked  = ref(false)
const timeRange     = ref('1h')
const kioskMode     = ref(true)
const discovering   = ref(false)
const discoverError = ref('')
const discovered    = ref(false)   // true = boards came from Grafana API
const diagResult    = ref(null)

const TIME_PRESETS = [
  { label: '30m', value: '30m' },
  { label: '1h',  value: '1h'  },
  { label: '3h',  value: '3h'  },
  { label: '6h',  value: '6h'  },
  { label: '12h', value: '12h' },
  { label: '24h', value: '24h' },
  { label: '3d',  value: '3d'  },
  { label: '7d',  value: '7d'  },
]

const GRAFANA_ICON = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`

// ── Grafana kiosk URL 构建 ────────────────────────────────────────────────
function buildKioskUrl(boardUrl) {
  if (!boardUrl) return ''
  const now  = Date.now()
  const from = now - rangeMs(timeRange.value)
  const url  = new URL(boardUrl)
  url.searchParams.set('from', String(from))
  url.searchParams.set('to',   String(now))
  url.searchParams.set('refresh', '30s')
  if (kioskMode.value) {
    url.searchParams.set('kiosk', 'tv')
  } else {
    url.searchParams.delete('kiosk')
  }
  return url.toString()
}

function rangeMs(range) {
  const map = { '30m': 30*60e3, '1h': 3600e3, '3h': 3*3600e3,
                '6h': 6*3600e3, '12h': 12*3600e3, '24h': 24*3600e3,
                '3d': 3*24*3600e3, '7d': 7*24*3600e3 }
  return map[range] || 3600e3
}

function rebuildUrl() {
  const board = boards.value.find(b => b.id === selectedBoard.value)
  if (!board) return
  currentUrl.value  = buildKioskUrl(board.url)
  frameLoading.value = true
  embedBlocked.value = false
  frameKey.value++
}

function onBoardChange() {
  rebuildUrl()
}

function reloadFrame() {
  frameLoading.value = true
  embedBlocked.value = false
  frameKey.value++
}

function onFrameError() {
  frameLoading.value = false
  embedBlocked.value = true
}

// ── 加载看板：先尝试 Grafana API 自动发现，失败则用配置的默认看板 ────────
async function loadBoards() {
  // 1. 先从 overview 拿 grafana_url
  try {
    const data = await api.observabilityOverview()
    grafanaUrl.value = data.grafana_url || ''
  } catch (_) {}

  // 2. 尝试自动发现
  await discoverBoards()
}

async function discoverBoards() {
  discovering.value   = true
  discoverError.value = ''
  try {
    const data = await api.discoverGrafanaBoards()
    if (data.boards && data.boards.length > 0) {
      boards.value   = data.boards
      grafanaUrl.value = data.grafana_url || grafanaUrl.value
      discovered.value = true
      discoverError.value = ''
    } else {
      // Grafana 可达但没有看板，或有错误，回退到配置的默认看板
      discoverError.value = data.error || ''
      await _loadFallbackBoards()
    }
  } catch (e) {
    discoverError.value = typeof e === 'string' ? e : (e?.message || '自动发现失败')
    await _loadFallbackBoards()
  } finally {
    discovering.value = false
  }
  // 选中第一个
  if (boards.value.length && !selectedBoard.value) {
    selectedBoard.value = boards.value[0].id
    rebuildUrl()
  }
}

async function _loadFallbackBoards() {
  try {
    const data = await api.observabilityGrafanaBoards()
    boards.value     = data.boards || []
    grafanaUrl.value = data.grafana_url || grafanaUrl.value
    discovered.value = false
  } catch (e) {
    console.error('Failed to load fallback boards', e)
  }
}

// 嵌入检测：超时后若 frame 还在 loading 则尝试用 X-Frame-Options 判断
let _loadTimer = null
watch(frameKey, () => {
  clearTimeout(_loadTimer)
  if (!currentUrl.value) return
  // 15s 超时后显示 blocked 提示
  _loadTimer = setTimeout(() => {
    if (frameLoading.value) {
      frameLoading.value = false
      embedBlocked.value = true
    }
  }, 15000)
})

async function runDiag() {
  diagResult.value = null
  try {
    diagResult.value = await api.testGrafanaConnection()
  } catch (e) {
    diagResult.value = { grafana_url: grafanaUrl.value, health_ok: false, search_ok: false,
      health_error: String(e), search_error: '', api_key_set: false }
  }
}

onMounted(loadBoards)
</script>

<style scoped>
.grafana-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 0 14px 0;
  flex-shrink: 0;
}
.header-left h1 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 2px;
}
.subtitle {
  font-size: 11px;
  color: var(--text-tertiary);
  font-family: var(--font-mono);
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.board-select {
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  outline: none;
}
.board-select:focus { border-color: var(--accent); }
.btn-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-secondary);
  cursor: pointer;
  text-decoration: none;
  transition: all 0.15s;
}
.btn-icon:hover { border-color: var(--accent); color: var(--accent); }
.btn-discover.spinning svg { animation: spin 0.8s linear infinite; }
.btn-discover:disabled { opacity: 0.5; cursor: not-allowed; }

/* discover badge / hint */
.discover-badge {
  display: inline-block; margin-left: 6px;
  padding: 1px 7px; border-radius: 10px; font-size: 10px;
  background: rgba(56,200,100,.12); color: var(--success);
  border: 1px solid rgba(56,200,100,.25);
}
.discover-warn {
  display: inline-block; margin-left: 6px;
  padding: 1px 7px; border-radius: 10px; font-size: 10px;
  background: rgba(210,153,34,.1); color: var(--warning);
  border: 1px solid rgba(210,153,34,.25); cursor: default;
}
.discover-hint {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 12px; margin-bottom: 4px; border-radius: 6px;
  background: rgba(210,153,34,.08); border: 1px solid rgba(210,153,34,.2);
  font-size: 12px; color: var(--text-secondary); flex-shrink: 0;
}
.hint-link { color: var(--accent); cursor: pointer; text-decoration: underline; }
.hint-sep { color: var(--text-tertiary); }

/* diag panel */
.diag-panel {
  position: relative;
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 36px 12px 14px;
  margin-bottom: 4px; flex-shrink: 0;
  display: flex; flex-direction: column; gap: 6px;
}
.diag-row { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.diag-k { color: var(--text-tertiary); width: 80px; flex-shrink: 0; }
.diag-v { color: var(--text-primary); }
.diag-v.ok  { color: var(--success); }
.diag-v.warn { color: var(--warning); }
.diag-v.err  { color: var(--error); }
.diag-close {
  position: absolute; top: 8px; right: 10px;
  background: none; border: none; color: var(--text-tertiary);
  font-size: 16px; cursor: pointer; line-height: 1;
}
.diag-close:hover { color: var(--text-primary); }

/* ── Tab bar ── */
.tab-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
  margin-bottom: 0;
}
.tab-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-add { color: var(--text-tertiary); margin-left: auto; }
.tab-add:hover { color: var(--accent); }
.tab-icon { opacity: 0.7; }
.tab-folder {
  font-size: 10px; color: var(--text-tertiary);
  background: var(--surface-1); border-radius: 3px;
  padding: 1px 4px; margin-left: 2px;
}
.tab-loading { color: var(--text-tertiary); cursor: default; }
.mini-spinner {
  display: inline-block; width: 10px; height: 10px;
  border: 1.5px solid var(--border); border-top-color: var(--accent);
  border-radius: 50%; animation: spin 0.6s linear infinite;
}

/* ── iframe wrap ── */
.iframe-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--surface-1);
}
.grafana-frame {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}
.frame-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  background: var(--surface-1);
  z-index: 5;
  color: var(--text-secondary);
  font-size: 13px;
}
.spinner {
  width: 28px;
  height: 28px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Empty / Blocked ── */
.empty-grafana, .embed-blocked {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  flex: 1;
  text-align: center;
  padding: 40px 24px;
  color: var(--text-secondary);
}
.empty-icon, .blocked-icon {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  background: var(--surface-2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
}
.empty-grafana h3, .embed-blocked h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.empty-grafana p, .embed-blocked p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
  max-width: 460px;
}
code {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--accent);
}
.config-block {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-primary);
  text-align: left;
  white-space: pre;
  margin: 0;
}
.btn-primary {
  padding: 8px 18px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition: opacity 0.15s;
}
.btn-primary:hover { opacity: 0.85; }

/* ── Time toolbar ── */
.time-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 0 0 0;
  flex-shrink: 0;
  border-top: 1px solid var(--border);
}
.toolbar-label {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
}
.time-presets {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
}
.preset-btn {
  padding: 3px 10px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-secondary);
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.12s;
}
.preset-btn:hover { border-color: var(--accent); color: var(--accent); }
.preset-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.kiosk-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  margin-left: auto;
  user-select: none;
}
.kiosk-toggle input { cursor: pointer; accent-color: var(--accent); }
</style>
