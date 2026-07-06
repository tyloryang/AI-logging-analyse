<template>
  <div ref="rootRef" class="bigscreen" :class="{ 'has-critical': criticalCount > 0 }">
    <!-- 粒子背景 -->
    <canvas ref="canvasRef" class="particles"></canvas>

    <div class="bs-inner">
      <!-- 顶栏 -->
      <header class="bs-header">
        <div class="bs-title">
          <span class="bs-logo">◈</span>
          <span>AIOps 智能运维监控大屏</span>
        </div>
        <div class="bs-clock">
          <span class="bs-date">{{ clock.date }}</span>
          <span class="bs-time">{{ clock.time }}</span>
        </div>
        <div class="bs-actions">
          <span class="bs-live"><i class="dot"></i>{{ loading ? '刷新中' : '实时' }}</span>
          <button class="bs-btn" @click="toggleFullscreen" :title="isFullscreen ? '退出全屏' : '全屏'">
            {{ isFullscreen ? '⤡' : '⤢' }}
          </button>
          <button class="bs-btn" @click="goBack" title="返回">✕</button>
        </div>
      </header>

      <!-- 严重告警横幅 -->
      <transition name="fade">
        <div v-if="criticalCount > 0" class="bs-critical-banner">
          <span class="cb-icon">🔔</span>
          <span>当前有 <b>{{ criticalCount }}</b> 个严重级别告警需要处理</span>
          <button class="cb-btn" @click="goAlerts">立即查看 ›</button>
        </div>
      </transition>

      <!-- KPI 行 -->
      <section class="bs-kpis">
        <div class="kpi-card" v-for="k in kpis" :key="k.label" :style="{ '--c': k.color }" @click="k.to && router.push(k.to)">
          <div class="kpi-icon">{{ k.icon }}</div>
          <div class="kpi-body">
            <div class="kpi-value">{{ k.value }}</div>
            <div class="kpi-label">{{ k.label }}</div>
          </div>
        </div>
      </section>

      <!-- 主体三列 -->
      <section class="bs-main">
        <!-- 左：告警严重度环形 + 分布 -->
        <div class="bs-panel">
          <div class="panel-title">告警严重度分布</div>
          <div class="ring-wrap">
            <svg viewBox="0 0 120 120" class="ring">
              <circle cx="60" cy="60" r="50" class="ring-bg" />
              <circle
                cx="60" cy="60" r="50" class="ring-fg"
                :stroke-dasharray="ringDash" stroke-dashoffset="0"
                :style="{ stroke: healthColor }"
              />
              <text x="60" y="54" class="ring-num">{{ healthScore }}</text>
              <text x="60" y="72" class="ring-unit">健康度</text>
            </svg>
          </div>
          <ul class="sev-list">
            <li v-for="s in sevBreakdown" :key="s.label">
              <span class="sev-dot" :style="{ background: s.color }"></span>
              <span class="sev-name">{{ s.label }}</span>
              <span class="sev-val">{{ s.value }}</span>
            </li>
          </ul>
        </div>

        <!-- 中：服务错误 top 柱状 -->
        <div class="bs-panel bs-panel-wide">
          <div class="panel-title">服务错误 TOP（近 {{ windowText }}）</div>
          <div class="bars">
            <div v-if="!errorBars.length" class="empty-hint">暂无错误数据</div>
            <div v-for="b in errorBars" :key="b.name" class="bar-row">
              <span class="bar-name" :title="b.name">{{ b.name }}</span>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: b.pct + '%', background: b.color }"></div>
              </div>
              <span class="bar-val">{{ b.value }}</span>
            </div>
          </div>
          <div class="panel-title" style="margin-top:16px">问题服务</div>
          <div class="svc-chips">
            <span v-if="!problemServices.length" class="empty-hint">全部正常 ✓</span>
            <span v-for="(s, i) in problemServices.slice(0, 12)" :key="i" class="svc-chip">
              {{ s.name }}<em v-if="s.err">×{{ s.err }}</em>
            </span>
          </div>
        </div>

        <!-- 右：实时告警滚动 -->
        <div class="bs-panel">
          <div class="panel-title">实时告警流</div>
          <div class="alert-stream">
            <div v-if="!recentAlerts.length" class="empty-hint">暂无告警</div>
            <div v-for="(a, i) in recentAlerts.slice(0, 12)" :key="i" class="alert-item" :class="sevClass(a.severity)">
              <span class="ai-dot"></span>
              <div class="ai-body">
                <div class="ai-name">{{ a.alertname || a.name || '告警' }}</div>
                <div class="ai-meta">{{ a.service || a.instance || '-' }} · {{ a.severity || 'warning' }}</div>
              </div>
              <span class="ai-time">{{ fmtTime(a.last_at || a.startsAt || a.timestamp) }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- 底部状态条 -->
      <footer class="bs-footer">
        <span :class="footerColor"><i class="dot"></i>{{ footerText }}</span>
        <span>资源 {{ overview.grafana_count ?? 0 }} 看板 · Trace {{ overview.trace_count ?? 0 }} · 错误 {{ overview.error_count ?? 0 }}</span>
        <span>数据每 15s 自动刷新 · {{ clock.time }}</span>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router = useRouter()
const rootRef = ref(null)
const canvasRef = ref(null)

const loading = ref(false)
const overview = ref({})
const stats = ref({})
const clock = reactive({ date: '', time: '' })
const isFullscreen = ref(false)

let pollTimer = null
let clockTimer = null
let particleRAF = null

// ── 数据加载 ──────────────────────────────────
async function load() {
  loading.value = true
  try {
    const [ov, st] = await Promise.allSettled([
      api.observabilityOverview({ minutes: 60 }),
      api.alertStats(),
    ])
    if (ov.status === 'fulfilled') overview.value = ov.value || {}
    if (st.status === 'fulfilled') stats.value = st.value || {}
  } catch { /* 大屏容错：出错保留旧数据 */ }
  finally { loading.value = false }
}

// ── 派生数据 ──────────────────────────────────
const windowText = computed(() => overview.value.window_text || overview.value.window_label || '1 小时')

const kpis = computed(() => [
  { label: '活跃告警', value: overview.value.alert_count ?? stats.value.active ?? 0, icon: '🔔', color: '#f87171', to: '/observability/alerts' },
  { label: '错误数',   value: overview.value.error_count ?? 0, icon: '⚠️', color: '#fbbf24', to: '/observability/logs' },
  { label: 'Trace 量', value: overview.value.trace_count ?? 0, icon: '🔗', color: '#38bdf8', to: '/observability/trace' },
  { label: '问题服务', value: problemServices.value.length, icon: '🧩', color: '#a78bfa', to: '/observability/api-red' },
])

const criticalCount = computed(() => Number(stats.value.p0 ?? 0))

const problemServices = computed(() => (overview.value.problem_services || []).map(s =>
  typeof s === 'string'
    ? { name: s, err: 0 }
    : { name: s.service || s.name || s.app || s.job || '未知服务', err: s.errors || s.error_count || 0 }
))
const recentAlerts = computed(() => overview.value.recent_alerts || [])

// 健康度：100 - 加权告警惩罚（p0×10 + p1×3 + active×1，封顶）
const healthScore = computed(() => {
  const p0 = Number(stats.value.p0 || 0)
  const p1 = Number(stats.value.p1 || 0)
  const active = Number(stats.value.active || overview.value.alert_count || 0)
  const penalty = Math.min(100, p0 * 10 + p1 * 3 + active * 1)
  return Math.max(0, 100 - penalty)
})
const healthColor = computed(() => healthScore.value >= 80 ? '#34d399' : healthScore.value >= 50 ? '#fbbf24' : '#f87171')
const ringDash = computed(() => {
  const circ = 2 * Math.PI * 50
  return `${(healthScore.value / 100) * circ} ${circ}`
})

const sevBreakdown = computed(() => [
  { label: '严重 P0', value: Number(stats.value.p0 || 0), color: '#f87171' },
  { label: '高 P1',   value: Number(stats.value.p1 || 0), color: '#fbbf24' },
  { label: '活跃',    value: Number(stats.value.active || 0), color: '#38bdf8' },
  { label: '已解决',  value: Number(stats.value.resolved || 0), color: '#34d399' },
])

const errorBars = computed(() => {
  const bd = overview.value.error_breakdown || []
  const list = (Array.isArray(bd) ? bd : Object.entries(bd).map(([name, value]) => ({ name, value })))
    .map(x => ({ name: x.name || x.service || x.label || '?', value: Number(x.value ?? x.count ?? 0) }))
    .filter(x => x.value > 0)
    .sort((a, b) => b.value - a.value)
    .slice(0, 8)
  const max = Math.max(1, ...list.map(x => x.value))
  const palette = ['#f87171', '#fb923c', '#fbbf24', '#a3e635', '#34d399', '#38bdf8', '#818cf8', '#c084fc']
  return list.map((x, i) => ({ ...x, pct: Math.round((x.value / max) * 100), color: palette[i % palette.length] }))
})

const footerText = computed(() => {
  if (criticalCount.value > 0) return '严重告警中'
  if (Number(stats.value.active || 0) > 0) return '存在活跃告警'
  return '系统运行正常'
})
const footerColor = computed(() => criticalCount.value > 0 ? 'foot-red' : Number(stats.value.active || 0) > 0 ? 'foot-yellow' : 'foot-green')

function sevClass(sev) {
  const s = (sev || '').toLowerCase()
  if (s === 'critical' || s === 'p0') return 'sev-critical'
  if (s === 'high' || s === 'warning' || s === 'p1') return 'sev-high'
  return 'sev-info'
}
function fmtTime(t) {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d)) return '-'
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// ── 时钟 ──────────────────────────────────────
function tick() {
  const d = new Date()
  clock.date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} 周${'日一二三四五六'[d.getDay()]}`
  clock.time = d.toLocaleTimeString('zh-CN', { hour12: false })
}

// ── 全屏 ──────────────────────────────────────
function toggleFullscreen() {
  const el = rootRef.value
  if (!document.fullscreenElement) el?.requestFullscreen?.().catch(() => {})
  else document.exitFullscreen?.()
}
function onFsChange() { isFullscreen.value = !!document.fullscreenElement }

function goBack() { router.push('/observability/overview') }
function goAlerts() { router.push('/observability/alerts') }

// ── 粒子背景 ──────────────────────────────────
function initParticles() {
  const canvas = canvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  let w, h, particles
  function resize() {
    w = canvas.width = canvas.offsetWidth
    h = canvas.height = canvas.offsetHeight
    particles = Array.from({ length: Math.min(70, Math.floor(w * h / 22000)) }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4,
      r: Math.random() * 1.6 + 0.4,
    }))
  }
  resize()
  window.addEventListener('resize', resize)
  canvas._resize = resize
  function draw() {
    ctx.clearRect(0, 0, w, h)
    for (const p of particles) {
      p.x += p.vx; p.y += p.vy
      if (p.x < 0 || p.x > w) p.vx *= -1
      if (p.y < 0 || p.y > h) p.vy *= -1
      ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(56,189,248,0.5)'; ctx.fill()
    }
    // 连线
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i], b = particles[j]
        const dist = Math.hypot(a.x - b.x, a.y - b.y)
        if (dist < 110) {
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y)
          ctx.strokeStyle = `rgba(56,189,248,${0.12 * (1 - dist / 110)})`; ctx.stroke()
        }
      }
    }
    particleRAF = requestAnimationFrame(draw)
  }
  draw()
}

onMounted(() => {
  tick(); clockTimer = setInterval(tick, 1000)
  load(); pollTimer = setInterval(load, 15000)
  initParticles()
  document.addEventListener('fullscreenchange', onFsChange)
})
onBeforeUnmount(() => {
  clearInterval(pollTimer); clearInterval(clockTimer)
  cancelAnimationFrame(particleRAF)
  if (canvasRef.value?._resize) window.removeEventListener('resize', canvasRef.value._resize)
  document.removeEventListener('fullscreenchange', onFsChange)
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {})
})
</script>

<style scoped>
.bigscreen {
  position: relative;
  width: 100%; height: 100vh;
  overflow: hidden;
  background: radial-gradient(ellipse at top, #0b1a33 0%, #050b18 55%, #03060d 100%);
  color: #e2e8f0;
  font-family: 'Cascadia Code', 'Consolas', system-ui, sans-serif;
}
.bigscreen.has-critical::before {
  content: ''; position: absolute; inset: 0; z-index: 5; pointer-events: none;
  border: 4px solid rgba(248, 81, 73, 0.45); border-radius: 8px;
  animation: pulseBorder 1.4s ease-in-out infinite;
}
@keyframes pulseBorder { 0%,100% { opacity: .3 } 50% { opacity: 1 } }

.particles { position: absolute; inset: 0; width: 100%; height: 100%; z-index: 1; }
.bs-inner { position: relative; z-index: 10; display: flex; flex-direction: column; height: 100%; padding: 16px 20px; gap: 12px; }

.bs-header { display: flex; align-items: center; justify-content: space-between; }
.bs-title { display: flex; align-items: center; gap: 10px; font-size: 22px; font-weight: 700; letter-spacing: .1em;
  background: linear-gradient(90deg, #38bdf8, #818cf8); -webkit-background-clip: text; background-clip: text; color: transparent; }
.bs-logo { color: #38bdf8; -webkit-text-fill-color: #38bdf8; }
.bs-clock { display: flex; flex-direction: column; align-items: center; }
.bs-date { font-size: 12px; color: #64748b; }
.bs-time { font-size: 20px; font-weight: 700; color: #e2e8f0; letter-spacing: .08em; }
.bs-actions { display: flex; align-items: center; gap: 10px; }
.bs-live { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: #34d399; }
.bs-live .dot, .foot-red .dot, .foot-yellow .dot, .foot-green .dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; background: currentColor; box-shadow: 0 0 8px currentColor; animation: blink 1.5s infinite; }
@keyframes blink { 0%,100% { opacity: 1 } 50% { opacity: .35 } }
.bs-btn { width: 30px; height: 30px; border-radius: 7px; border: 1px solid rgba(148,163,184,.3); background: rgba(30,41,59,.5);
  color: #cbd5e1; cursor: pointer; font-size: 14px; transition: all .15s; }
.bs-btn:hover { border-color: #38bdf8; color: #38bdf8; }

.bs-critical-banner { display: flex; align-items: center; gap: 12px; padding: 10px 16px;
  background: linear-gradient(90deg, rgba(127,29,29,.6), rgba(153,27,27,.6)); border: 1px solid rgba(248,113,113,.5);
  border-radius: 10px; animation: pulseBorder 1.4s infinite; }
.cb-icon { font-size: 20px; }
.bs-critical-banner b { color: #fca5a5; font-size: 18px; padding: 0 3px; }
.cb-btn { margin-left: auto; padding: 5px 14px; background: rgba(248,113,113,.25); border: 1px solid rgba(248,113,113,.5);
  border-radius: 7px; color: #fecaca; cursor: pointer; font-size: 13px; }

.bs-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.kpi-card { display: flex; align-items: center; gap: 14px; padding: 16px 18px; cursor: pointer;
  background: rgba(15,23,42,.5); backdrop-filter: blur(8px); border: 1px solid rgba(148,163,184,.15);
  border-radius: 14px; border-left: 3px solid var(--c); transition: all .15s; }
.kpi-card:hover { border-color: var(--c); transform: translateY(-2px); }
.kpi-icon { font-size: 26px; }
.kpi-value { font-size: 30px; font-weight: 800; color: #f1f5f9; line-height: 1; }
.kpi-label { font-size: 12px; color: #94a3b8; margin-top: 5px; }

.bs-main { flex: 1; display: grid; grid-template-columns: 1fr 1.6fr 1fr; gap: 12px; min-height: 0; }
.bs-panel { background: rgba(15,23,42,.45); backdrop-filter: blur(8px); border: 1px solid rgba(148,163,184,.15);
  border-radius: 14px; padding: 16px; display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.panel-title { font-size: 13px; font-weight: 600; color: #7dd3fc; margin-bottom: 12px; padding-left: 8px; border-left: 3px solid #38bdf8; }

.ring-wrap { display: flex; justify-content: center; }
.ring { width: 150px; height: 150px; transform: rotate(-90deg); }
.ring-bg { fill: none; stroke: rgba(148,163,184,.15); stroke-width: 9; }
.ring-fg { fill: none; stroke-width: 9; stroke-linecap: round; transition: stroke-dasharray .6s ease, stroke .3s; }
.ring-num { transform: rotate(90deg); transform-origin: 60px 60px; font-size: 26px; font-weight: 800; fill: #f1f5f9; text-anchor: middle; }
.ring-unit { transform: rotate(90deg); transform-origin: 60px 60px; font-size: 10px; fill: #94a3b8; text-anchor: middle; }
.sev-list { list-style: none; margin: 16px 0 0; padding: 0; display: flex; flex-direction: column; gap: 9px; }
.sev-list li { display: flex; align-items: center; gap: 9px; font-size: 13px; }
.sev-dot { width: 9px; height: 9px; border-radius: 50%; }
.sev-name { color: #cbd5e1; }
.sev-val { margin-left: auto; font-weight: 700; color: #f1f5f9; }

.bars { display: flex; flex-direction: column; gap: 9px; }
.bar-row { display: flex; align-items: center; gap: 10px; }
.bar-name { width: 130px; font-size: 12px; color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-track { flex: 1; height: 14px; background: rgba(148,163,184,.1); border-radius: 7px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 7px; transition: width .6s ease; }
.bar-val { width: 42px; text-align: right; font-size: 12px; font-weight: 700; color: #f1f5f9; }
.svc-chips { display: flex; flex-wrap: wrap; gap: 7px; overflow-y: auto; }
.svc-chip { padding: 4px 10px; font-size: 12px; background: rgba(129,140,248,.14); border: 1px solid rgba(129,140,248,.3);
  border-radius: 999px; color: #c7d2fe; }
.svc-chip em { color: #fca5a5; font-style: normal; margin-left: 4px; }

.alert-stream { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.alert-item { display: flex; align-items: center; gap: 10px; padding: 9px 11px; border-radius: 9px;
  background: rgba(30,41,59,.4); border-left: 3px solid #64748b; }
.alert-item.sev-critical { border-left-color: #f87171; background: rgba(127,29,29,.25); }
.alert-item.sev-high { border-left-color: #fbbf24; background: rgba(120,53,15,.2); }
.ai-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
.sev-critical .ai-dot { background: #f87171; box-shadow: 0 0 8px #f87171; }
.sev-high .ai-dot { background: #fbbf24; }
.sev-info .ai-dot { background: #38bdf8; }
.ai-body { flex: 1; min-width: 0; }
.ai-name { font-size: 13px; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ai-meta { font-size: 11px; color: #94a3b8; }
.ai-time { font-size: 11px; color: #64748b; }

.empty-hint { font-size: 12px; color: #64748b; padding: 10px; text-align: center; }

.bs-footer { display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: #64748b;
  padding: 8px 4px 0; border-top: 1px solid rgba(148,163,184,.1); }
.foot-red { color: #f87171; } .foot-yellow { color: #fbbf24; } .foot-green { color: #34d399; }
.bs-footer span { display: inline-flex; align-items: center; gap: 6px; }

.fade-enter-active, .fade-leave-active { transition: opacity .3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
