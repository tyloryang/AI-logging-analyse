<template>
  <div class="cp-page">
    <div class="cp-head">
      <div>
        <h2 class="cp-title">🛡️ 服务器安全合规检查</h2>
        <p class="cp-sub">等保 / CIS 风格基线检查：访问控制 · 账户安全 · 文件权限 · 网络安全 · 审计日志</p>
      </div>
    </div>

    <!-- 主机选择 + 跑检查 -->
    <div class="cp-toolbar">
      <select v-model="selectedHost" class="cp-select">
        <option value="">选择主机…</option>
        <option v-for="h in hosts" :key="h.id" :value="h.id">
          {{ h.hostname || h.ip }} ({{ h.ip }})
        </option>
      </select>
      <button class="btn btn-primary" :disabled="!selectedHost || running" @click="run">
        <span v-if="running" class="spin"></span>{{ running ? '检查中…' : '▶ 开始检查' }}
      </button>
      <span class="cp-checkcount">共 {{ checkCount }} 项基线</span>
    </div>

    <div v-if="err" class="cp-error">{{ err }}</div>

    <!-- 结果 -->
    <div v-if="result" class="cp-result">
      <!-- 评分卡 -->
      <div class="cp-scorecard">
        <svg viewBox="0 0 120 120" class="score-ring">
          <circle cx="60" cy="60" r="50" class="sr-bg" />
          <circle cx="60" cy="60" r="50" class="sr-fg" :stroke-dasharray="scoreDash" :style="{ stroke: scoreColor }" />
          <text x="60" y="56" class="sr-num" :style="{ fill: scoreColor }">{{ result.score }}</text>
          <text x="60" y="74" class="sr-unit">合规分</text>
        </svg>
        <div class="sc-stats">
          <div class="sc-stat pass"><b>{{ result.summary.pass }}</b><span>通过</span></div>
          <div class="sc-stat warn"><b>{{ result.summary.warn }}</b><span>警告</span></div>
          <div class="sc-stat fail"><b>{{ result.summary.fail }}</b><span>不合规</span></div>
        </div>
        <div class="sc-meta">
          <div>{{ result.hostname }} · {{ result.ip }}</div>
          <div>{{ fmtTime(result.checked_at) }}</div>
        </div>
      </div>

      <!-- 检查项列表（按状态排序，fail 在前） -->
      <div class="cp-checks">
        <div v-for="r in sortedResults" :key="r.id" class="check-row" :class="'st-' + r.status">
          <span class="ck-badge">{{ statusLabel(r.status) }}</span>
          <div class="ck-main">
            <div class="ck-name">{{ r.name }}<span class="ck-cat">{{ r.category }}</span><span class="ck-sev" :class="'sev-' + r.severity">{{ sevLabel(r.severity) }}</span></div>
            <div class="ck-reason">{{ r.reason }}<code v-if="r.actual" class="ck-actual">{{ r.actual }}</code></div>
          </div>
        </div>
      </div>
    </div>

    <div v-else-if="!running" class="cp-empty">
      <span class="e-icon">🛡️</span>
      <p>选择一台主机开始安全合规检查<br><small>检查通过 SSH 执行只读基线命令，不修改系统</small></p>
    </div>

    <!-- 历史 -->
    <div v-if="history.length" class="cp-history">
      <div class="hist-title">评分历史</div>
      <div class="hist-bars">
        <div v-for="(h, i) in history.slice(0, 15).reverse()" :key="i" class="hist-bar"
          :style="{ height: (h.score * 0.7 + 10) + '%', background: barColor(h.score) }"
          :title="`${h.score} 分 · ${fmtTime(h.checked_at)}`">
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api/index.js'

const hosts = ref([])
const selectedHost = ref('')
const running = ref(false)
const result = ref(null)
const history = ref([])
const checkCount = ref(10)
const err = ref('')

const scoreColor = computed(() => {
  const s = result.value?.score ?? 0
  return s >= 80 ? '#22c55e' : s >= 60 ? '#fbbf24' : '#f87171'
})
const scoreDash = computed(() => {
  const circ = 2 * Math.PI * 50
  return `${((result.value?.score ?? 0) / 100) * circ} ${circ}`
})
const sortedResults = computed(() => {
  const order = { fail: 0, error: 0, warn: 1, pass: 2 }
  return [...(result.value?.results || [])].sort((a, b) => (order[a.status] ?? 3) - (order[b.status] ?? 3))
})

async function loadHosts() {
  try {
    const r = await api.getHosts()
    const data = r?.data ?? r
    hosts.value = Array.isArray(data) ? data : (data?.hosts || [])
  } catch { hosts.value = [] }
}

async function loadChecks() {
  try { const r = await api.complianceChecks(); checkCount.value = r.total ?? 10 } catch { /* ignore */ }
}

async function run() {
  if (!selectedHost.value) return
  running.value = true; err.value = ''; result.value = null
  try {
    result.value = await api.complianceRun(selectedHost.value)
    await loadHistory()
  } catch (e) {
    err.value = 'SSH 检查失败：' + (typeof e === 'string' ? e : (e?.message || '未知错误'))
  } finally { running.value = false }
}

async function loadHistory() {
  if (!selectedHost.value) return
  try { const r = await api.complianceHistory(selectedHost.value); history.value = r.history || [] } catch { history.value = [] }
}

watch(selectedHost, () => { result.value = null; loadHistory() })

function statusLabel(s) { return { pass: '通过', warn: '警告', fail: '不合规', error: '异常' }[s] || s }
function sevLabel(s) { return { high: '高危', medium: '中危', low: '低危' }[s] || s }
function barColor(s) { return s >= 80 ? '#22c55e' : s >= 60 ? '#fbbf24' : '#f87171' }
function fmtTime(t) {
  if (!t) return '-'
  const d = new Date(t)
  return isNaN(d) ? '-' : d.toLocaleString('zh-CN', { hour12: false })
}

onMounted(() => { loadHosts(); loadChecks() })
</script>

<style scoped>
.cp-page { height: 100%; overflow-y: auto; padding: 20px 24px; background: var(--bg-base); }
.cp-title { font-size: 20px; font-weight: 600; color: var(--text-primary); }
.cp-sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

.cp-toolbar { display: flex; align-items: center; gap: 12px; margin: 18px 0; flex-wrap: wrap; }
.cp-select { min-width: 260px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--bg-card); color: var(--text-primary); font-size: 13px; }
.cp-checkcount { font-size: 12px; color: var(--text-muted); }
.spin { display: inline-block; width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.35); border-top-color: #fff;
  border-radius: 50%; animation: sp .7s linear infinite; margin-right: 6px; vertical-align: -1px; }
@keyframes sp { to { transform: rotate(360deg); } }

.cp-error { padding: 12px 16px; background: rgba(248,81,73,.1); border: 1px solid rgba(248,81,73,.3);
  border-radius: 8px; color: var(--error); font-size: 13px; margin-bottom: 16px; }
.cp-empty { text-align: center; padding: 70px 20px; color: var(--text-muted); }
.e-icon { font-size: 44px; display: block; margin-bottom: 14px; }

.cp-result { display: flex; flex-direction: column; gap: 18px; }
.cp-scorecard { display: flex; align-items: center; gap: 26px; padding: 20px 24px; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 14px; flex-wrap: wrap; }
.score-ring { width: 130px; height: 130px; transform: rotate(-90deg); flex-shrink: 0; }
.sr-bg { fill: none; stroke: var(--border); stroke-width: 9; }
.sr-fg { fill: none; stroke-width: 9; stroke-linecap: round; transition: stroke-dasharray .6s ease; }
.sr-num { transform: rotate(90deg); transform-origin: 60px 60px; font-size: 30px; font-weight: 800; text-anchor: middle; }
.sr-unit { transform: rotate(90deg); transform-origin: 60px 60px; font-size: 11px; fill: var(--text-muted); text-anchor: middle; }
.sc-stats { display: flex; gap: 24px; }
.sc-stat { display: flex; flex-direction: column; align-items: center; }
.sc-stat b { font-size: 26px; font-weight: 800; }
.sc-stat span { font-size: 12px; color: var(--text-muted); }
.sc-stat.pass b { color: #22c55e; } .sc-stat.warn b { color: #fbbf24; } .sc-stat.fail b { color: #f87171; }
.sc-meta { margin-left: auto; text-align: right; font-size: 12px; color: var(--text-muted); line-height: 1.8; }

.cp-checks { display: flex; flex-direction: column; gap: 8px; }
.check-row { display: flex; align-items: flex-start; gap: 12px; padding: 12px 16px; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 10px; border-left: 3px solid var(--border); }
.check-row.st-pass { border-left-color: #22c55e; }
.check-row.st-warn { border-left-color: #fbbf24; }
.check-row.st-fail, .check-row.st-error { border-left-color: #f87171; background: rgba(248,81,73,.04); }
.ck-badge { flex-shrink: 0; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; }
.st-pass .ck-badge { background: rgba(34,197,94,.15); color: #22c55e; }
.st-warn .ck-badge { background: rgba(251,191,36,.15); color: #d97706; }
.st-fail .ck-badge, .st-error .ck-badge { background: rgba(248,81,73,.15); color: #f87171; }
.ck-main { flex: 1; min-width: 0; }
.ck-name { font-size: 14px; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ck-cat { font-size: 11px; color: var(--text-muted); font-weight: 400; }
.ck-sev { font-size: 10px; padding: 1px 6px; border-radius: 4px; font-weight: 500; }
.sev-high { background: rgba(248,81,73,.15); color: #f87171; }
.sev-medium { background: rgba(251,191,36,.15); color: #d97706; }
.sev-low { background: rgba(148,163,184,.15); color: var(--text-muted); }
.ck-reason { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.ck-actual { display: block; margin-top: 4px; font-size: 11px; color: var(--text-muted); background: var(--bg-base);
  padding: 3px 8px; border-radius: 5px; font-family: 'Cascadia Code', monospace; word-break: break-all; }

.cp-history { margin-top: 22px; padding: 16px 20px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; }
.hist-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 12px; }
.hist-bars { display: flex; align-items: flex-end; gap: 6px; height: 80px; }
.hist-bar { flex: 1; max-width: 28px; border-radius: 4px 4px 0 0; min-height: 8px; transition: height .3s; }
</style>
