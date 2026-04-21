<template>
  <div class="obs-page">

    <!-- ══ 页头 ══ -->
    <div class="obs-header">
      <div class="obs-header-left">
        <div class="obs-brand-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <div>
          <h1 class="obs-title">可观测性 <span class="obs-sep">|</span> 平台总览</h1>
          <p class="obs-subtitle">告警、日志、追踪、发布 — 实时感知系统健康状态</p>
        </div>
      </div>
      <div class="obs-header-right">
        <select class="time-select" v-model="hours" @change="loadAll">
          <option :value="1">最近 1 小时</option>
          <option :value="3">最近 3 小时</option>
          <option :value="6">最近 6 小时</option>
          <option :value="24">最近 24 小时</option>
        </select>
        <button class="btn-refresh" @click="loadAll" :disabled="loading" title="刷新">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ spinning: loading }">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- ══ 统计卡片行 ══ -->
    <div class="stats-row">
      <div class="stat-card" :class="{ 'stat-alert': overview.alert_count > 0 }">
        <div class="stat-num" :class="{ 'num-alert': overview.alert_count > 0 }">
          {{ loading ? '—' : overview.alert_count }}
        </div>
        <div class="stat-label">次告警触发</div>
        <div class="stat-bar alert-bar"></div>
      </div>
      <div class="stat-card" :class="{ 'stat-warn': overview.error_count > 5 }">
        <div class="stat-num" :class="{ 'num-warn': overview.error_count > 5 }">
          {{ loading ? '—' : overview.error_count }}
        </div>
        <div class="stat-label">服务错误</div>
        <div class="stat-bar error-bar"></div>
      </div>
      <div class="stat-card">
        <div class="stat-num num-info">{{ loading ? '—' : overview.trace_count }}</div>
        <div class="stat-label">Trace 量</div>
        <div class="stat-bar trace-bar"></div>
      </div>
      <div class="stat-card">
        <div class="stat-num num-success">{{ loading ? '—' : overview.grafana_count }}</div>
        <div class="stat-label">Grafana 看板</div>
        <div class="stat-bar grafana-bar"></div>
      </div>
    </div>

    <!-- ══ AI 分析输入 ══ -->
    <div class="ai-analyze-box card">
      <div class="ai-analyze-header">
        <span class="ai-icon-wrap">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M9 11V7a3 3 0 016 0v4"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/></svg>
        </span>
        <span class="ai-analyze-title">输入 AI 分析</span>
        <span class="ai-model-badge">{{ aiModelName }}</span>
      </div>
      <div class="ai-analyze-input-row">
        <input
          v-model="analyzeQuestion"
          class="ai-analyze-input"
          placeholder="描述问题或直接问：当前最需要关注什么？"
          @keydown.enter="startAnalyze"
          :disabled="analyzing"
        />
        <button class="btn-analyze" @click="startAnalyze" :disabled="analyzing || !analyzeQuestion.trim()">
          <span v-if="analyzing" class="spinner-sm"></span>
          <span v-else>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
          </span>
          {{ analyzing ? '分析中...' : '分析' }}
        </button>
      </div>
      <!-- AI 分析结果 -->
      <div v-if="analyzeResult" class="ai-analyze-result">
        <div class="ai-analyze-content" v-html="renderAnalysis(analyzeResult)"></div>
        <span v-if="analyzing" class="cursor-blink"></span>
      </div>
    </div>

    <div class="main-grid">
      <!-- ══ 左列：根因中心 + 告警列表 ══ -->
      <div class="left-col">

        <!-- 根因中心 -->
        <div class="section-card card">
          <div class="section-header">
            <span class="section-dot dot-alert"></span>
            <h2 class="section-title">根因中心</h2>
            <span class="section-count">{{ overview.problem_services?.length || 0 }} 个异常服务</span>
            <button class="section-link" @click="loadAll">刷新</button>
          </div>

          <div v-if="loading" class="section-loading">
            <div class="spinner"></div>
          </div>

          <div v-else-if="!overview.problem_services?.length" class="section-empty">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
            <span>当前无异常服务</span>
          </div>

          <div v-else class="rca-grid">
            <div
              v-for="svc in overview.problem_services" :key="svc.service"
              class="rca-card" :class="svc.severity"
            >
              <div class="rca-header">
                <span class="rca-severity-dot" :class="svc.severity"></span>
                <span class="rca-svc-name">{{ svc.service }}</span>
                <span class="rca-badge" v-if="svc.errors > 0">{{ svc.errors }} 错误</span>
                <span class="rca-badge alert-badge" v-if="svc.alerts > 0">{{ svc.alerts }} 告警</span>
              </div>
              <div class="rca-summary">{{ svc.summary || '存在异常，建议排查' }}</div>
              <div class="rca-actions">
                <RouterLink :to="`/logs?service=${svc.service}`" class="rca-link">日志分析</RouterLink>
                <RouterLink to="/skywalking" class="rca-link">链路追踪</RouterLink>
                <button class="rca-link" @click="askAI(svc.service)">AI 分析</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 告警列表 -->
        <div class="section-card card">
          <div class="section-header">
            <span class="section-dot dot-alert"></span>
            <h2 class="section-title">告警列表</h2>
            <RouterLink to="/alerts" class="section-link">查看全部 →</RouterLink>
          </div>

          <div v-if="loading" class="section-loading"><div class="spinner"></div></div>

          <div v-else-if="!overview.recent_alerts?.length" class="section-empty">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><polyline points="20 6 9 17 4 12"/></svg>
            <span>无活跃告警</span>
          </div>

          <table v-else class="obs-table">
            <thead>
              <tr>
                <th>服务</th>
                <th>告警名称</th>
                <th>级别</th>
                <th>命名空间</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in overview.recent_alerts" :key="a.name + a.service">
                <td>
                  <span class="svc-tag">{{ a.service }}</span>
                </td>
                <td>{{ a.name }}</td>
                <td>
                  <span class="severity-badge" :class="a.severity">{{ a.severity }}</span>
                </td>
                <td class="text-muted">{{ a.namespace || 'production' }}</td>
                <td class="text-muted mono">{{ a.time }}</td>
              </tr>
            </tbody>
          </table>
        </div>

      </div>

      <!-- ══ 右列：服务拓扑入口 + 最近 Trace ══ -->
      <div class="right-col">

        <!-- 服务拓扑快捷入口 -->
        <div class="section-card card">
          <div class="section-header">
            <span class="section-dot dot-trace"></span>
            <h2 class="section-title">服务拓扑</h2>
          </div>
          <div class="topo-grid">
            <RouterLink to="/skywalking" class="topo-card">
              <div class="topo-icon topo-trace">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><line x1="12" y1="7" x2="5" y2="17"/><line x1="12" y1="7" x2="19" y2="17"/><line x1="5" y1="19" x2="19" y2="19"/></svg>
              </div>
              <div class="topo-info">
                <div class="topo-label">链路追踪</div>
                <div class="topo-sub">SkyWalking · OAP</div>
              </div>
              <div class="topo-count">{{ overview.trace_count || 0 }}</div>
            </RouterLink>

            <RouterLink to="/alerts" class="topo-card">
              <div class="topo-icon topo-alert">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>
              </div>
              <div class="topo-info">
                <div class="topo-label">告警中心</div>
                <div class="topo-sub">Prometheus · AM</div>
              </div>
              <div class="topo-count" :class="{ 'count-alert': overview.alert_count > 0 }">{{ overview.alert_count || 0 }}</div>
            </RouterLink>

            <RouterLink to="/metrics" class="topo-card">
              <div class="topo-icon topo-metric">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
              </div>
              <div class="topo-info">
                <div class="topo-label">Trace 量</div>
                <div class="topo-sub">Prometheus · 指标</div>
              </div>
              <div class="topo-count">{{ overview.trace_count || 0 }}</div>
            </RouterLink>

            <div class="topo-card topo-grafana" @click="openGrafana">
              <div class="topo-icon topo-grafana-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              </div>
              <div class="topo-info">
                <div class="topo-label">Grafana 处理</div>
                <div class="topo-sub">{{ overview.grafana_boards?.length || 0 }} 个看板</div>
              </div>
              <div class="topo-count num-success">{{ overview.grafana_count || 0 }}</div>
            </div>
          </div>

          <!-- Grafana 看板列表 -->
          <div v-if="overview.grafana_boards?.length" class="grafana-list">
            <div v-for="b in overview.grafana_boards" :key="b.id" class="grafana-item"
                 @click="openBoard(b)"
                 :class="{ clickable: b.url }">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
              <span>{{ b.title }}</span>
            </div>
          </div>
        </div>

        <!-- 最近 Trace -->
        <div class="section-card card">
          <div class="section-header">
            <span class="section-dot dot-trace"></span>
            <h2 class="section-title">最近 Trace</h2>
            <RouterLink to="/skywalking" class="section-link">查看全部 →</RouterLink>
          </div>

          <div v-if="loading" class="section-loading"><div class="spinner"></div></div>

          <div v-else-if="!overview.recent_traces?.length" class="section-empty">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><line x1="12" y1="7" x2="5" y2="17"/><line x1="12" y1="7" x2="19" y2="17"/></svg>
            <span>暂无 Trace 数据</span>
          </div>

          <table v-else class="obs-table">
            <thead>
              <tr>
                <th>服务</th>
                <th>端点</th>
                <th>耗时</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in overview.recent_traces" :key="t.trace_id">
                <td><span class="svc-tag">{{ t.service || '—' }}</span></td>
                <td class="text-muted" style="max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  {{ t.endpoint || t.trace_id || '—' }}
                </td>
                <td class="mono" :class="{ 'dur-slow': t.duration > 1000, 'dur-warn': t.duration > 500 && t.duration <= 1000 }">
                  {{ t.duration ? t.duration + ' ms' : '—' }}
                </td>
                <td>
                  <span class="trace-status" :class="t.error ? 'error' : 'ok'">
                    {{ t.error ? '异常' : '正常' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router = useRouter()

// ── 状态 ─────────────────────────────────────────────────────────────
const loading  = ref(false)
const hours    = ref(1)
const overview = reactive({
  alert_count:      0,
  error_count:      0,
  trace_count:      0,
  grafana_count:    0,
  recent_alerts:    [],
  recent_traces:    [],
  problem_services: [],
  grafana_boards:   [],
})

// AI 分析状态
const analyzeQuestion = ref('')
const analyzeResult   = ref('')
const analyzing       = ref(false)
const aiModelName     = ref('AI')

// ── 读取 AI 模型名 ────────────────────────────────────────────────────
async function fetchAiModel() {
  try {
    const r = await api.healthCheck()
    const p = r.ai_provider || ''
    if (p.startsWith('Anthropic')) aiModelName.value = 'Claude'
    else {
      const m = p.match(/\((.+)\)/)
      aiModelName.value = m ? m[1].slice(0, 10) : (p.slice(0, 10) || 'AI')
    }
  } catch { /* ignore */ }
}

// ── 加载总览数据 ──────────────────────────────────────────────────────
async function loadAll() {
  loading.value = true
  try {
    const resp = await fetch(`/api/observability/overview?hours=${hours.value}`, {
      credentials: 'include',
    })
    if (resp.ok) {
      const data = await resp.json()
      Object.assign(overview, data)
    }
  } catch (e) {
    console.warn('[obs] 加载总览失败:', e)
  } finally {
    loading.value = false
  }
}

// ── AI 分析 ───────────────────────────────────────────────────────────
async function startAnalyze() {
  const q = analyzeQuestion.value.trim()
  if (!q || analyzing.value) return
  analyzing.value = true
  analyzeResult.value = ''

  try {
    const resp = await fetch('/api/observability/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ question: q, hours: hours.value }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    const reader = resp.body.getReader()
    const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const chunk = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        for (const line of chunk.split('\n')) {
          if (line.startsWith('data: ')) {
            try {
              const ev = JSON.parse(line.slice(6))
              if (ev.type === 'token') analyzeResult.value += ev.text || ''
              if (ev.type === 'done') analyzing.value = false
              if (ev.type === 'error') {
                analyzeResult.value += `\n❌ ${ev.message}`
                analyzing.value = false
              }
            } catch { /* ignore */ }
          }
        }
      }
    }
  } catch (e) {
    analyzeResult.value = `❌ 分析失败：${e.message}`
  } finally {
    analyzing.value = false
  }
}

// 点击服务卡片 → 预填问题
function askAI(service) {
  analyzeQuestion.value = `分析 ${service} 服务当前异常，给出根因和处理建议`
  startAnalyze()
}

function openGrafana() {
  const url = overview.grafana_boards?.[0]?.url
  window.open(url || 'http://localhost:3000', '_blank')
}

function openBoard(b) {
  if (b.url) window.open(b.url, '_blank')
}

// ── AI 分析文本渲染 ───────────────────────────────────────────────────
function renderAnalysis(text) {
  if (!text) return ''
  let t = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^## (.+)$/gm, '<div class="analysis-title">$1</div>')
    .replace(/^(\d+)\.\s+(.+)$/gm, '<div class="analysis-li"><span class="li-num">$1</span><span>$2</span></div>')
    .replace(/^[-•]\s+(.+)$/gm, '<div class="analysis-li"><span class="li-dot">•</span><span>$1</span></div>')
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    .replace(/\n/g, '<br>')
  return t
}

onMounted(() => {
  loadAll()
  fetchAiModel()
})
</script>

<style scoped>
/* ── 页面容器 ── */
.obs-page {
  padding: 20px 24px;
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── 页头 ── */
.obs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.obs-header-left { display: flex; align-items: center; gap: 12px; }
.obs-brand-icon {
  width: 36px; height: 36px;
  border-radius: 8px;
  background: var(--accent-dim);
  color: var(--accent);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.obs-title {
  font-size: 16px; font-weight: 600; color: var(--text-primary);
  margin: 0;
}
.obs-sep { color: var(--text-muted); margin: 0 4px; }
.obs-subtitle { font-size: 12px; color: var(--text-secondary); margin: 3px 0 0; }

.obs-header-right { display: flex; align-items: center; gap: 10px; }
.time-select {
  padding: 5px 10px; font-size: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-input); color: var(--text-primary);
  cursor: pointer;
}
.btn-refresh {
  width: 32px; height: 32px;
  border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg-card); color: var(--text-secondary);
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all .15s;
}
.btn-refresh:hover { border-color: var(--accent); color: var(--accent); }
.btn-refresh:disabled { opacity: .4; }
@keyframes spin { to { transform: rotate(360deg); } }
.spinning { animation: spin .8s linear infinite; }

/* ── 统计卡片行 ── */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.stat-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 16px 20px;
  position: relative;
  overflow: hidden;
  transition: border-color .15s;
}
.stat-card:hover { border-color: var(--border-accent); }
.stat-card.stat-alert { border-color: rgba(248,81,73,0.3); }
.stat-card.stat-warn  { border-color: rgba(210,153,34,0.3); }
.stat-num {
  font-size: 32px; font-weight: 700;
  font-family: 'Cascadia Code', 'Consolas', monospace;
  color: var(--text-primary); line-height: 1;
}
.num-alert   { color: var(--error); }
.num-warn    { color: var(--warning); }
.num-info    { color: var(--info, #58a6ff); }
.num-success { color: var(--success); }
.stat-label  { font-size: 12px; color: var(--text-secondary); margin-top: 6px; }
.stat-bar { position: absolute; bottom: 0; left: 0; right: 0; height: 3px; }
.alert-bar   { background: linear-gradient(90deg, var(--error) 0%, transparent 100%); }
.error-bar   { background: linear-gradient(90deg, var(--warning) 0%, transparent 100%); }
.trace-bar   { background: linear-gradient(90deg, var(--info,#58a6ff) 0%, transparent 100%); }
.grafana-bar { background: linear-gradient(90deg, var(--success) 0%, transparent 100%); }

/* ── AI 分析框 ── */
.ai-analyze-box { padding: 14px 18px; }
.ai-analyze-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 10px;
}
.ai-icon-wrap {
  width: 24px; height: 24px; border-radius: 6px;
  background: var(--accent-dim); color: var(--accent);
  display: flex; align-items: center; justify-content: center;
}
.ai-analyze-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.ai-model-badge {
  padding: 1px 8px; border-radius: 10px;
  font-size: 10px; font-weight: 600;
  background: var(--accent-dim);
  color: var(--accent);
  border: 1px solid rgba(56,139,253,0.25);
  font-family: 'Cascadia Code', 'Consolas', monospace;
}
.ai-analyze-input-row { display: flex; gap: 8px; }
.ai-analyze-input {
  flex: 1; padding: 8px 12px;
  border: 1px solid var(--border); border-radius: var(--radius);
  background: var(--bg-input); color: var(--text-primary);
  font-size: 13px; font-family: inherit; outline: none;
}
.ai-analyze-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.ai-analyze-input:disabled { opacity: .5; }
.btn-analyze {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: var(--radius);
  border: none; background: var(--accent); color: #fff;
  font-size: 13px; font-family: inherit; cursor: pointer;
  transition: opacity .15s; white-space: nowrap;
}
.btn-analyze:hover:not(:disabled) { opacity: .85; }
.btn-analyze:disabled { opacity: .45; cursor: not-allowed; }

.ai-analyze-result {
  margin-top: 12px;
  padding: 12px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  font-size: 13px; line-height: 1.75;
  color: var(--text-primary);
}
.ai-analyze-result :deep(.analysis-title) {
  font-weight: 700; color: var(--accent);
  margin: 10px 0 5px; padding-left: 8px;
  border-left: 3px solid var(--accent);
}
.ai-analyze-result :deep(.analysis-li) {
  display: flex; gap: 8px; align-items: baseline; margin: 3px 0;
}
.ai-analyze-result :deep(.li-num) {
  width: 18px; height: 18px; border-radius: 50%;
  background: var(--accent); color: #fff;
  font-size: 10px; font-weight: 700; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
}
.ai-analyze-result :deep(.li-dot) { color: var(--accent); font-weight: 700; }
.ai-analyze-result :deep(.inline-code) {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px; padding: 1px 5px;
  background: var(--bg-card); border-radius: 3px; color: var(--accent);
}
.cursor-blink {
  display: inline-block; width: 2px; height: 13px;
  background: var(--accent); margin-left: 2px;
  vertical-align: middle; animation: blink .9s step-end infinite;
}
@keyframes blink { 50% { opacity: 0; } }

/* ── 主内容网格 ── */
.main-grid {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 16px;
  align-items: start;
}
.left-col  { display: flex; flex-direction: column; gap: 16px; }
.right-col { display: flex; flex-direction: column; gap: 16px; }

/* ── 通用 section card ── */
.section-card { padding: 0; }
.section-header {
  display: flex; align-items: center; gap: 8px;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--border-light);
}
.section-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-alert  { background: var(--error); box-shadow: 0 0 6px rgba(248,81,73,.4); }
.dot-trace  { background: var(--accent); box-shadow: 0 0 6px rgba(56,139,253,.4); }
.section-title { font-size: 13px; font-weight: 600; color: var(--text-primary); flex: 1; }
.section-count { font-size: 12px; color: var(--text-muted); }
.section-link {
  font-size: 12px; color: var(--accent); text-decoration: none;
  background: none; border: none; cursor: pointer; font-family: inherit;
  padding: 0;
}
.section-link:hover { opacity: .8; }

.section-loading { display: flex; justify-content: center; padding: 32px; }
.section-empty {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 36px 20px; color: var(--success); font-size: 13px;
}
.section-empty svg { opacity: .6; }

/* ── 根因中心网格 ── */
.rca-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  padding: 12px 16px;
}
.rca-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 10px 12px;
  transition: border-color .15s;
}
.rca-card.error   { border-color: rgba(248,81,73,0.3); }
.rca-card.warning { border-color: rgba(210,153,34,0.3); }
.rca-card:hover   { box-shadow: var(--shadow-sm); }

.rca-header { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
.rca-severity-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.rca-severity-dot.error   { background: var(--error); }
.rca-severity-dot.warning { background: var(--warning); }
.rca-svc-name { font-size: 12px; font-weight: 600; color: var(--text-primary); flex: 1; }
.rca-badge { font-size: 10px; padding: 1px 6px; border-radius: 3px; background: rgba(248,81,73,.1); color: var(--error); }
.alert-badge { background: rgba(210,153,34,.1); color: var(--warning); }
.rca-summary { font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.4; }
.rca-actions { display: flex; gap: 8px; }
.rca-link {
  font-size: 11px; color: var(--accent); text-decoration: none;
  background: none; border: none; cursor: pointer; font-family: inherit;
  padding: 0; transition: opacity .12s;
}
.rca-link:hover { opacity: .75; }

/* ── 告警 / Trace 表格 ── */
.obs-table { width: 100%; border-collapse: collapse; }
.obs-table th {
  padding: 8px 14px;
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .06em; color: var(--text-muted);
  background: var(--bg-surface); border-bottom: 1px solid var(--border);
  white-space: nowrap; text-align: left;
}
.obs-table td {
  padding: 9px 14px;
  font-size: 12px; color: var(--text-secondary);
  border-bottom: 1px solid var(--border-light);
}
.obs-table tbody tr:hover td { background: var(--bg-hover); }
.text-muted { color: var(--text-muted) !important; }
.mono { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px !important; }

.svc-tag {
  font-size: 11px; padding: 2px 7px;
  background: var(--accent-dim); color: var(--accent);
  border-radius: 3px; font-weight: 500;
}
.severity-badge {
  font-size: 10px; padding: 2px 7px; border-radius: 3px;
  font-weight: 600; text-transform: uppercase;
}
.severity-badge.critical { background: rgba(248,81,73,.15); color: var(--error); }
.severity-badge.warning  { background: rgba(210,153,34,.15); color: var(--warning); }
.severity-badge.info     { background: rgba(56,139,253,.12); color: var(--accent); }

.trace-status { font-size: 10px; padding: 2px 7px; border-radius: 3px; font-weight: 600; }
.trace-status.ok    { background: rgba(63,185,80,.12);  color: var(--success); }
.trace-status.error { background: rgba(248,81,73,.12); color: var(--error); }

.dur-slow { color: var(--error) !important; }
.dur-warn { color: var(--warning) !important; }

/* ── 服务拓扑 ── */
.topo-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 12px 16px 4px; }
.topo-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border); border-radius: var(--radius-card);
  text-decoration: none; cursor: pointer;
  transition: border-color .12s, background .12s;
}
.topo-card:hover { border-color: var(--accent); background: var(--accent-dim); }
.topo-icon {
  width: 32px; height: 32px; border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.topo-trace       { background: rgba(56,139,253,.12); color: var(--accent); }
.topo-alert       { background: rgba(248,81,73,.1);   color: var(--error); }
.topo-metric      { background: rgba(63,185,80,.1);   color: var(--success); }
.topo-grafana-icon { background: rgba(210,153,34,.1); color: var(--warning); }
.topo-info { flex: 1; min-width: 0; }
.topo-label { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.topo-sub   { font-size: 10px; color: var(--text-muted); }
.topo-count {
  font-size: 18px; font-weight: 700; color: var(--text-secondary);
  font-family: 'Cascadia Code', 'Consolas', monospace;
}
.count-alert { color: var(--error); }

.grafana-list {
  padding: 4px 16px 12px;
  display: flex; flex-direction: column; gap: 4px;
}
.grafana-item {
  display: flex; align-items: center; gap: 7px;
  font-size: 11px; color: var(--text-muted);
  padding: 3px 0;
}
.grafana-item.clickable {
  cursor: pointer;
  transition: color .15s;
}
.grafana-item.clickable:hover { color: var(--accent); }

/* ── Spinner ── */
.spinner {
  width: 20px; height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
.spinner-sm {
  display: inline-block;
  width: 13px; height: 13px;
  border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}
</style>
