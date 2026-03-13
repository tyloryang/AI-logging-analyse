<template>
  <div class="page">
    <div class="page-header">
      <h1>分析报告</h1>
    </div>

    <!-- 错误提示 -->
    <transition name="fade">
      <div v-if="errorMsg" class="error-toast">
        ❌ {{ errorMsg }}
        <button class="toast-close" @click="errorMsg = ''">✕</button>
      </div>
    </transition>
    <!-- 成功提示 -->
    <transition name="fade">
      <div v-if="successMsg" class="success-toast">
        ✅ {{ successMsg }}
        <button class="toast-close" @click="successMsg = ''">✕</button>
      </div>
    </transition>

    <div class="report-layout">
      <!-- 左侧报告列表 -->
      <aside class="report-list-panel">
        <div class="panel-top">
          <select v-model="reportType" class="time-select">
            <option value="daily">运维日报</option>
            <option value="inspect">主机巡检日报</option>
          </select>
          <button class="btn btn-primary btn-full" @click="generateReport" :disabled="generating">
            <span v-if="generating" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>▶</span>
            {{ generating ? 'AI 分析中...' : reportType === 'inspect' ? '立即生成巡检日报' : '立即生成日报' }}
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
              <span>{{ formatDate(r.created_at) }}</span>
              <span class="badge" :class="healthBadge(r.health_score)">{{ r.health_score }}/100</span>
            </div>
          </div>
          <div v-if="!loadingList && !reportList.length" class="empty-state" style="padding:30px">
            <span class="icon" style="font-size:28px">📋</span>
            <p>暂无历史报告</p>
          </div>
        </div>
      </aside>

      <!-- 右侧报告详情 -->
      <div class="report-detail">

        <!-- 生成中（无报告） -->
        <div v-if="generating && !currentReport" class="empty-state" style="height:100%">
          <div class="spinner" style="width:36px;height:36px;border-width:3px"></div>
          <p style="margin-top:12px;color:var(--text-secondary)">正在采集数据并生成日报...</p>
        </div>

        <!-- 无报告 -->
        <div v-else-if="!currentReport" class="empty-state" style="height:100%">
          <span class="icon">📋</span>
          <p>请点击「立即生成日报」或选择历史报告</p>
        </div>

        <!-- 报告内容 -->
        <div v-else class="report-content">

          <!-- 标题栏 -->
          <div class="report-title-bar">
            <div>
              <h2>{{ currentReport.title }}</h2>
              <p class="report-date">报告时间：{{ formatDate(currentReport.created_at) }}</p>
            </div>
            <div style="display:flex;align-items:center;gap:12px">
              <button
                v-if="!generating"
                class="btn btn-outline"
                @click="generateReport"
                title="重新生成"
              >🔄 重新生成</button>
              <!-- 通知按钮 -->
              <button
                v-if="currentReport?.id && !generating"
                class="btn btn-notify feishu"
                :disabled="notifying.feishu"
                @click="sendNotify('feishu')"
                title="发送到飞书"
              >
                <span v-if="notifying.feishu" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                <span v-else>🔔</span> 飞书
              </button>
              <button
                v-if="currentReport?.id && !generating"
                class="btn btn-notify dingtalk"
                :disabled="notifying.dingtalk"
                @click="sendNotify('dingtalk')"
                title="发送到钉钉"
              >
                <span v-if="notifying.dingtalk" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                <span v-else>🔔</span> 钉钉
              </button>
              <div class="health-circle" :class="healthClass(currentReport.health_score)">
                <div class="health-num">{{ currentReport.health_score }}</div>
                <div class="health-label">整体健康评分 /100</div>
              </div>
            </div>
          </div>

          <!-- 运维日报指标 -->
          <template v-if="currentReport.type !== 'inspect'">
            <div class="metrics-row">
              <div class="metric-card">
                <div class="metric-icon">📋</div>
                <div class="metric-val">{{ fmtNum(currentReport.total_logs) }}</div>
                <div class="metric-label">总日志条数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">❌</div>
                <div class="metric-val" style="color:var(--error)">{{ fmtNum(currentReport.total_errors) }}</div>
                <div class="metric-label">错误总数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🔧</div>
                <div class="metric-val">{{ currentReport.service_count }}</div>
                <div class="metric-label">涉及服务数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🖥️</div>
                <div class="metric-val" style="font-size:15px">
                  <span style="color:var(--success)">{{ currentReport.node_status?.normal ?? 0 }} 正常</span>
                  <span style="color:var(--text-muted);font-size:11px;margin:0 4px">/</span>
                  <span style="color:var(--error)">{{ currentReport.node_status?.abnormal ?? 0 }} 异常</span>
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
            <div class="section" v-if="currentReport.top10_errors?.length">
              <h3 class="section-title">🔥 错误 Top 10 服务</h3>
              <div class="top10-list">
                <div v-for="(item, i) in currentReport.top10_errors" :key="item.service" class="top10-row">
                  <span class="rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
                  <span class="top10-svc" :title="item.service">{{ item.service }}</span>
                  <div class="bar-wrap">
                    <div class="bar" :style="{ width: topBarWidth(item.count) + '%' }"></div>
                  </div>
                  <span class="badge badge-error" style="white-space:nowrap">{{ fmtNum(item.count) }} 条</span>
                </div>
              </div>
            </div>
          </template>

          <!-- 主机巡检日报指标 -->
          <template v-else>
            <div class="metrics-row">
              <div class="metric-card">
                <div class="metric-icon">🖥️</div>
                <div class="metric-val">{{ currentReport.host_summary?.total ?? 0 }}</div>
                <div class="metric-label">巡检主机总数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">✅</div>
                <div class="metric-val" style="color:var(--success)">{{ currentReport.host_summary?.normal ?? 0 }}</div>
                <div class="metric-label">正常主机</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">⚠️</div>
                <div class="metric-val" style="color:var(--warning)">{{ currentReport.host_summary?.warning ?? 0 }}</div>
                <div class="metric-label">警告主机</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🔴</div>
                <div class="metric-val" style="color:var(--error)">{{ currentReport.host_summary?.critical ?? 0 }}</div>
                <div class="metric-label">严重主机</div>
              </div>
            </div>
            <!-- 高频异常项 -->
            <div class="section" v-if="currentReport.top_issues?.length">
              <h3 class="section-title">🔥 高频异常项 Top 10</h3>
              <div class="top10-list">
                <div v-for="(item, i) in currentReport.top_issues" :key="item.item" class="top10-row">
                  <span class="rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
                  <span class="top10-svc" :title="item.item">{{ item.item }}</span>
                  <div class="bar-wrap">
                    <div class="bar" :style="{ width: issueBarWidth(item.count) + '%' }"></div>
                  </div>
                  <span class="badge badge-error" style="white-space:nowrap">{{ item.count }} 台</span>
                </div>
              </div>
            </div>
            <!-- 异常主机列表 -->
            <div class="section" v-if="currentReport.abnormal_hosts?.length">
              <h3 class="section-title">⚠️ 异常主机列表</h3>
              <div class="abnormal-list">
                <div v-for="h in currentReport.abnormal_hosts" :key="h.instance" class="abnormal-row" :class="'row-' + h.overall">
                  <span class="abnormal-dot" :class="h.overall"></span>
                  <span class="abnormal-host">{{ h.hostname || h.instance }}</span>
                  <span class="abnormal-ip">{{ h.ip }}</span>
                  <div class="abnormal-checks">
                    <span v-for="c in h.checks.filter(c => c.status !== 'normal').slice(0, 3)" :key="c.item" class="check-tag" :class="c.status">
                      {{ c.item }}: {{ c.value }}
                    </span>
                  </div>
                  <span class="badge" :class="h.overall === 'critical' ? 'badge-error' : 'badge-warn'">{{ h.overall }}</span>
                </div>
              </div>
            </div>
          </template>

          <!-- AI 分析 -->
          <div class="section">
            <div class="section-title-row">
              <h3 class="section-title">🤖 AI 分析</h3>
              <span v-if="generating" class="analyzing-badge">
                <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
                分析中
              </span>
            </div>
            <div class="ai-analysis-box">
              <!-- 流式生成中 -->
              <div v-if="aiStreamContent" class="ai-text" v-html="renderText(aiStreamContent)"></div>
              <!-- 历史报告已有内容 -->
              <div v-else-if="currentReport.ai_analysis" class="ai-text" v-html="renderText(currentReport.ai_analysis)"></div>
              <!-- 生成中但还没有内容 -->
              <div v-else-if="generating" class="ai-placeholder">
                <div class="spinner" style="width:20px;height:20px;border-width:2px"></div>
                <span>等待 AI 响应...</span>
              </div>
              <!-- 无内容 -->
              <div v-else class="empty-state" style="padding:24px">
                <p>AI 分析尚未生成，请点击「重新生成」</p>
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

const reportType    = ref('daily')
const reportList    = ref([])
const currentReport = ref(null)
const generating    = ref(false)
const loadingList   = ref(false)
const aiStreamContent = ref('')
const errorMsg      = ref('')
const successMsg    = ref('')
const notifying     = ref({ feishu: false, dingtalk: false })

// ── 工具函数 ──────────────────────────────
function fmtNum(n) { return n != null ? Number(n).toLocaleString() : '0' }

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

function renderText(t) {
  if (!t) return ''
  return t
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/⚠️/g, '<span class="ai-warn">⚠️</span>')
    .replace(/✅/g, '<span class="ai-ok">✅</span>')
    .replace(/\n/g, '<br>')
}

const maxTop = computed(() =>
  currentReport.value?.top10_errors?.[0]?.count || 1
)
function topBarWidth(cnt) {
  return Math.round((cnt / maxTop.value) * 100)
}

const maxIssue = computed(() =>
  currentReport.value?.top_issues?.[0]?.count || 1
)
function issueBarWidth(cnt) {
  return Math.round((cnt / maxIssue.value) * 100)
}

// ── 加载历史列表 ──────────────────────────
async function loadReportList() {
  loadingList.value = true
  try {
    const r = await api.listReports()
    reportList.value = r.data
  } catch (e) {
    errorMsg.value = '加载报告列表失败：' + e
  } finally {
    loadingList.value = false
  }
}

// ── 加载单个报告 ──────────────────────────
async function loadReport(id) {
  aiStreamContent.value = ''
  errorMsg.value = ''
  try {
    currentReport.value = await api.getReport(id)
  } catch (e) {
    errorMsg.value = '加载报告失败：' + e
  }
}

// ── 生成日报（SSE GET） ──────────────────
function generateReport() {
  if (generating.value) return
  generating.value = true
  aiStreamContent.value = ''
  errorMsg.value = ''
  const prevReport = currentReport.value
  currentReport.value = prevReport

  const url = reportType.value === 'inspect'
    ? '/api/report/inspect/generate'
    : '/api/report/generate'

  const stop = streamSSE(
    url,
    (raw) => {
      // __META__ 前缀判断必须在 JSON.parse 前
      if (raw.startsWith('__META__')) {
        try {
          currentReport.value = JSON.parse(raw.slice(8))
          aiStreamContent.value = ''
        } catch (e) {
          console.error('META parse error', e)
        }
        return
      }
      // 普通 AI 文本 chunk（已被后端 JSON.stringify 包裹）
      try {
        aiStreamContent.value += JSON.parse(raw)
      } catch {
        aiStreamContent.value += raw
      }
    },
    async () => {
      generating.value = false
      await loadReportList()
      // 刷新当前报告（取完整 ai_analysis 字段）
      if (currentReport.value?.id) {
        try {
          currentReport.value = await api.getReport(currentReport.value.id)
        } catch {}
      }
    },
    (err) => {
      generating.value = false
      errorMsg.value = '生成失败，请检查后端连接和 AI 配置'
      console.error('SSE error', err)
    },
  )
}

// ── 通知推送 ──────────────────────────────
async function sendNotify(channel) {
  if (!currentReport.value?.id) return
  notifying.value[channel] = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    const r = await api.notifyReport(currentReport.value.id, [channel])
    const res = r.results?.[channel]
    if (res?.ok) {
      const label = channel === 'feishu' ? '飞书' : '钉钉'
      successMsg.value = `已成功发送到${label}`
      setTimeout(() => { successMsg.value = '' }, 4000)
    } else {
      errorMsg.value = `发送失败：${res?.msg || '未知错误'}`
    }
  } catch (e) {
    errorMsg.value = `发送失败：${e}`
  } finally {
    notifying.value[channel] = false
  }
}

onMounted(loadReportList)
</script>

<style scoped>
.page {
  padding: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}
.page-header { margin-bottom: 16px; flex-shrink: 0; }
.page-header h1 { font-size: 22px; font-weight: 700; }

/* 错误提示 */
.error-toast {
  position: absolute;
  top: 16px; right: 16px;
  background: rgba(239,68,68,.15);
  border: 1px solid rgba(239,68,68,.4);
  color: #fca5a5;
  padding: 10px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 100;
}
.toast-close {
  background: none; border: none; color: inherit;
  cursor: pointer; font-size: 14px; opacity: .7;
}
.toast-close:hover { opacity: 1; }

/* 布局 */
.report-layout { flex: 1; display: flex; gap: 16px; overflow: hidden; min-height: 0; }

/* 左侧 */
.report-list-panel {
  width: 240px; min-width: 240px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.panel-top {
  padding: 12px;
  border-bottom: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 10px;
  flex-shrink: 0;
}
.time-select {
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-primary);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.btn-full { width: 100%; justify-content: center; }

.history-list { flex: 1; overflow-y: auto; padding: 8px; }
.history-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background .12s;
}
.history-item:hover { background: var(--bg-hover); }
.history-item.active { background: var(--accent-dim); color: var(--accent); }
.history-title {
  font-size: 13px; font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 5px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.history-meta {
  display: flex; align-items: center;
  justify-content: space-between;
  font-size: 11px; color: var(--text-muted);
}

/* 右侧 */
.report-detail {
  flex: 1;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow-y: auto;
  min-height: 0;
}
.report-content { padding: 24px; }

/* 标题栏 */
.report-title-bar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
  gap: 16px;
}
.report-title-bar h2 { font-size: 20px; font-weight: 700; }
.report-date { color: var(--text-muted); font-size: 13px; margin-top: 4px; }

.health-circle {
  text-align: center;
  padding: 14px 18px;
  border-radius: var(--radius);
  border: 2px solid;
  min-width: 100px;
  flex-shrink: 0;
}
.health-circle.health-good { border-color: var(--success); color: var(--success); background: rgba(63,185,80,.08); }
.health-circle.health-mid  { border-color: var(--warning); color: var(--warning); background: rgba(210,153,34,.08); }
.health-circle.health-bad  { border-color: var(--error);   color: var(--error);   background: rgba(248,81,73,.08); }
.health-num   { font-size: 30px; font-weight: 800; line-height: 1; }
.health-label { font-size: 10px; margin-top: 4px; opacity: .8; }

/* 指标卡片 */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
  margin-bottom: 24px;
}
.metric-card {
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 10px;
  text-align: center;
}
.metric-icon  { font-size: 20px; margin-bottom: 6px; }
.metric-val   { font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.metric-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

/* 区块 */
.section { margin-bottom: 24px; }
.section-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.section-title { font-size: 15px; font-weight: 600; }

.analyzing-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--accent-hover);
  background: rgba(99,102,241,.12);
  border: 1px solid rgba(99,102,241,.25);
  padding: 2px 10px;
  border-radius: 9999px;
}
.analyzing-badge span {
  animation: pulse 1.2s ease-in-out infinite;
}
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }

/* Top10 */
.top10-list { display: flex; flex-direction: column; gap: 10px; }
.top10-row  { display: flex; align-items: center; gap: 12px; }
.rank { width: 22px; text-align: center; font-size: 12px; color: var(--text-muted); font-weight: 700; flex-shrink: 0; }
.rank-top { color: var(--warning); }
.top10-svc {
  width: 180px; font-size: 13px; color: var(--text-primary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0;
}
.bar-wrap { flex: 1; height: 8px; background: var(--bg-hover); border-radius: 4px; overflow: hidden; }
.bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 4px; transition: width .4s ease; }

/* AI 分析框 */
.ai-analysis-box {
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  min-height: 80px;
}
.ai-text {
  font-size: 13px;
  line-height: 2;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}
:deep(.ai-warn) { color: var(--warning); }
:deep(.ai-ok)   { color: var(--success); }
:deep(strong)   { color: var(--text-primary); font-weight: 600; }

.ai-placeholder {
  display: flex; align-items: center; gap: 10px;
  color: var(--text-muted); font-size: 13px;
  padding: 8px 0;
}

/* 通知按钮 */
.btn-notify {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: 6px; border: 1px solid;
  font-size: 12px; font-weight: 500; cursor: pointer;
  transition: opacity .15s;
}
.btn-notify:disabled { opacity: .5; cursor: not-allowed; }
.btn-notify.feishu {
  background: rgba(0, 195, 155, .1);
  border-color: rgba(0, 195, 155, .4);
  color: #00c39b;
}
.btn-notify.feishu:hover:not(:disabled) { background: rgba(0, 195, 155, .2); }
.btn-notify.dingtalk {
  background: rgba(255, 106, 0, .1);
  border-color: rgba(255, 106, 0, .4);
  color: #ff6a00;
}
.btn-notify.dingtalk:hover:not(:disabled) { background: rgba(255, 106, 0, .2); }
/* 成功提示 */
.success-toast {
  position: absolute;
  top: 16px; right: 16px;
  background: rgba(34,197,94,.15);
  border: 1px solid rgba(34,197,94,.4);
  color: #86efac;
  padding: 10px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 100;
}

@keyframes pulse { 0%,80%,100%{opacity:.2} 40%{opacity:1} }

/* 异常主机列表 */
.abnormal-list { display: flex; flex-direction: column; gap: 6px; }
.abnormal-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: var(--radius);
  border: 1px solid var(--border); background: var(--bg-card);
  font-size: 12px;
}
.abnormal-row.row-critical { border-left: 3px solid var(--error); }
.abnormal-row.row-warning  { border-left: 3px solid var(--warning); }
.abnormal-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.abnormal-dot.critical { background: var(--error); }
.abnormal-dot.warning  { background: var(--warning); }
.abnormal-host { font-weight: 600; color: var(--text-primary); min-width: 120px; }
.abnormal-ip   { color: var(--text-muted); min-width: 110px; }
.abnormal-checks { flex: 1; display: flex; flex-wrap: wrap; gap: 4px; }
.check-tag {
  padding: 1px 7px; border-radius: 2px; font-size: 11px;
  background: var(--bg-hover); color: var(--text-secondary); border: 1px solid var(--border);
}
.check-tag.warning  { background: rgba(255,156,1,.1);  color: var(--warning); border-color: rgba(255,156,1,.3); }
.check-tag.critical { background: rgba(234,54,54,.1);  color: var(--error);   border-color: rgba(234,54,54,.3); }
</style>
