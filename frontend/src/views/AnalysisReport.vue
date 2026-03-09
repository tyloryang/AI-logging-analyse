<template>
  <div class="page">
    <div class="page-header">
      <h1>分析报告</h1>
    </div>

    <div class="report-layout">
      <!-- 左侧报告列表 -->
      <aside class="report-list-panel">
        <div class="panel-top">
          <select v-model="reportType" class="time-select">
            <option value="daily">每日日报</option>
          </select>
          <button class="btn btn-primary btn-full" @click="generateReport" :disabled="generating">
            <span v-if="generating" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>▶</span>
            立即生成日报
          </button>
        </div>

        <div class="history-list">
          <div v-if="loadingList" class="empty-state" style="padding:30px">
            <div class="spinner"></div>
          </div>
          <div
            v-for="r in reportList" :key="r.id"
            class="history-item"
            :class="{ active: currentReport?.id === r.id }"
            @click="loadReport(r.id)"
          >
            <div class="history-title">{{ r.title }}</div>
            <div class="history-meta">
              {{ formatDate(r.created_at) }}
              <span class="badge" :class="healthBadge(r.health_score)">{{ r.health_score }}/100</span>
            </div>
          </div>
          <div v-if="!loadingList && !reportList.length" class="empty-state" style="padding:30px">
            <p>暂无历史报告</p>
          </div>
        </div>
      </aside>

      <!-- 右侧报告详情 -->
      <div class="report-detail">
        <!-- 生成中 -->
        <div v-if="generating && !currentReport" class="empty-state" style="height:400px">
          <div class="spinner" style="width:32px;height:32px;border-width:3px"></div>
          <p>正在生成日报，AI 分析中...</p>
        </div>

        <!-- 无报告 -->
        <div v-else-if="!currentReport" class="empty-state" style="height:400px">
          <span class="icon">📋</span>
          <p>请选择或生成一份报告</p>
        </div>

        <!-- 报告内容 -->
        <div v-else class="report-content">
          <div class="report-title-bar">
            <div>
              <h2>{{ currentReport.title }}</h2>
              <p class="report-date">{{ formatDate(currentReport.created_at) }}</p>
            </div>
            <div class="health-circle" :class="healthClass(currentReport.health_score)">
              <div class="health-num">{{ currentReport.health_score }}</div>
              <div class="health-label">整体健康评分</div>
            </div>
          </div>

          <!-- 基础指标 -->
          <div class="metrics-row">
            <div class="metric-card">
              <div class="metric-icon">📋</div>
              <div class="metric-val">{{ currentReport.total_logs?.toLocaleString() }}</div>
              <div class="metric-label">总健康日志数</div>
            </div>
            <div class="metric-card">
              <div class="metric-icon">🔧</div>
              <div class="metric-val">{{ currentReport.service_count }}</div>
              <div class="metric-label">涉及服务数</div>
            </div>
            <div class="metric-card">
              <div class="metric-icon">🖥️</div>
              <div class="metric-val">
                <span style="color:var(--success)">{{ currentReport.node_status?.normal || 0 }} 正常</span>
                <span style="color:var(--text-muted);font-size:12px"> / </span>
                <span style="color:var(--error)">{{ currentReport.node_status?.abnormal || 0 }} 异常</span>
              </div>
              <div class="metric-label">节点状态</div>
            </div>
            <div class="metric-card">
              <div class="metric-icon">🔔</div>
              <div class="metric-val" :style="{ color: currentReport.active_alerts > 0 ? 'var(--error)' : 'var(--success)' }">
                {{ currentReport.active_alerts }}
              </div>
              <div class="metric-label">活跃告警</div>
            </div>
          </div>

          <!-- 错误 Top 10 -->
          <div class="section">
            <h3 class="section-title">🔥 错误 Top 10 服务</h3>
            <div class="top10-list">
              <div v-for="(item, i) in currentReport.top10_errors" :key="item.service" class="top10-row">
                <span class="rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
                <span class="top10-svc">{{ item.service }}</span>
                <div class="bar-wrap">
                  <div class="bar" :style="{ width: topBarWidth(item.count, i) + '%' }"></div>
                </div>
                <span class="badge badge-error">{{ item.count }} 条错误</span>
              </div>
            </div>
          </div>

          <!-- AI 分析 -->
          <div class="section">
            <h3 class="section-title">🤖 AI 分析</h3>
            <div class="ai-analysis-box">
              <div v-if="aiStreamContent || generating" class="ai-text" v-html="renderedAI"></div>
              <div v-if="generating" class="ai-typing">
                <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
              </div>
              <div v-else-if="!aiStreamContent && currentReport.ai_analysis" class="ai-text" v-html="renderText(currentReport.ai_analysis)"></div>
              <div v-else-if="!aiStreamContent && !currentReport.ai_analysis" class="empty-state" style="padding:20px">
                <p>AI 分析内容未生成</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, streamSSE } from '../api/index.js'

const reportType = ref('daily')
const reportList = ref([])
const currentReport = ref(null)
const generating = ref(false)
const loadingList = ref(false)
const aiStreamContent = ref('')

const renderedAI = computed(() => renderText(aiStreamContent.value))

function renderText(t) {
  if (!t) return ''
  return t.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>')
}

function formatDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { hour12: false })
}

function healthBadge(score) {
  if (score >= 80) return 'badge-success'
  if (score >= 60) return 'badge-warn'
  return 'badge-error'
}

function healthClass(score) {
  if (score >= 80) return 'health-good'
  if (score >= 60) return 'health-mid'
  return 'health-bad'
}

const maxTop = computed(() => {
  if (!currentReport.value?.top10_errors?.length) return 1
  return currentReport.value.top10_errors[0].count
})

function topBarWidth(cnt) {
  return Math.round(cnt / maxTop.value * 100)
}

async function loadReportList() {
  loadingList.value = true
  try {
    const r = await api.listReports()
    reportList.value = r.data
  } finally {
    loadingList.value = false
  }
}

async function loadReport(id) {
  aiStreamContent.value = ''
  const r = await api.getReport(id)
  currentReport.value = r
}

function generateReport() {
  generating.value = true
  aiStreamContent.value = ''
  currentReport.value = null

  const stop = streamSSE(
    '/api/report/generate',
    (chunk) => {
      try {
        const text = JSON.parse(chunk)
        if (typeof text === 'string' && text.startsWith('__META__')) {
          currentReport.value = JSON.parse(text.slice(8))
        } else {
          aiStreamContent.value += text
        }
      } catch {
        aiStreamContent.value += chunk
      }
    },
    async () => {
      generating.value = false
      await loadReportList()
      if (currentReport.value?.id) {
        const r = await api.getReport(currentReport.value.id)
        currentReport.value = r
      }
    },
    () => { generating.value = false },
  )
}

onMounted(loadReportList)
</script>

<style scoped>
.page { padding: 24px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
.page-header { margin-bottom: 20px; flex-shrink: 0; }
.page-header h1 { font-size: 22px; font-weight: 700; }

.report-layout { flex: 1; display: flex; gap: 20px; overflow: hidden; }

/* 左侧 */
.report-list-panel { width: 240px; min-width: 240px; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); display: flex; flex-direction: column; overflow: hidden; }
.panel-top { padding: 16px; border-bottom: 1px solid var(--border); display: flex; flex-direction: column; gap: 10px; }
.time-select { background: var(--bg-hover); border: 1px solid var(--border); color: var(--text-primary); padding: 6px 10px; border-radius: 6px; font-size: 13px; cursor: pointer; }
.btn-full { width: 100%; justify-content: center; }

.history-list { flex: 1; overflow-y: auto; padding: 8px; }
.history-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; transition: background .12s; }
.history-item:hover { background: var(--bg-hover); }
.history-item.active { background: var(--bg-active); }
.history-title { font-size: 13px; font-weight: 500; color: var(--text-primary); margin-bottom: 4px; }
.history-meta { display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--text-muted); }

/* 右侧 */
.report-detail { flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); overflow-y: auto; }
.report-content { padding: 24px; }

.report-title-bar { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.report-title-bar h2 { font-size: 20px; font-weight: 700; }
.report-date { color: var(--text-muted); font-size: 13px; margin-top: 4px; }

.health-circle { text-align: center; padding: 16px 20px; border-radius: var(--radius); border: 2px solid; }
.health-circle.health-good { border-color: var(--success); color: var(--success); background: rgba(34,197,94,.08); }
.health-circle.health-mid  { border-color: var(--warning); color: var(--warning); background: rgba(245,158,11,.08); }
.health-circle.health-bad  { border-color: var(--error);   color: var(--error);   background: rgba(239,68,68,.08); }
.health-num { font-size: 32px; font-weight: 800; line-height: 1; }
.health-label { font-size: 11px; margin-top: 4px; opacity: .8; }

.metrics-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }
.metric-card { background: var(--bg-base); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; text-align: center; }
.metric-icon { font-size: 22px; margin-bottom: 6px; }
.metric-val { font-size: 18px; font-weight: 700; color: var(--text-primary); line-height: 1.3; }
.metric-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

.section { margin-bottom: 24px; }
.section-title { font-size: 15px; font-weight: 600; margin-bottom: 14px; }

.top10-list { display: flex; flex-direction: column; gap: 8px; }
.top10-row { display: flex; align-items: center; gap: 12px; }
.rank { width: 22px; text-align: center; font-size: 12px; color: var(--text-muted); font-weight: 600; flex-shrink: 0; }
.rank-top { color: var(--warning); }
.top10-svc { width: 200px; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.bar-wrap { flex: 1; height: 6px; background: var(--bg-hover); border-radius: 3px; overflow: hidden; }
.bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 3px; }

.ai-analysis-box { background: var(--bg-base); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; }
.ai-text { font-size: 13px; line-height: 1.9; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; }
.ai-typing { display: flex; gap: 4px; margin-top: 10px; }
.ai-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }
@keyframes pulse { 0%,80%,100%{opacity:.2}40%{opacity:1} }
</style>
