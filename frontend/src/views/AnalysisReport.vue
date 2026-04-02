<template>
  <div class="page">
    <div class="page-header">
      <h1>分析报告</h1>
    </div>

    <!-- Toast -->
    <transition name="fade">
      <div v-if="errorMsg" class="error-toast">
        ❌ {{ errorMsg }}
        <button class="toast-close" @click="errorMsg = ''">✕</button>
      </div>
    </transition>
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
          <select v-model="reportType" class="time-select" @change="onTypeChange">
            <option value="daily">运维日报</option>
            <option value="inspect">主机巡检日报</option>
            <option value="slowlog">MySQL 慢日志报告</option>
          </select>
          <select v-if="reportType === 'inspect'" v-model="inspectGroupId" class="time-select">
            <option value="">全部主机</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
          <button class="btn btn-primary btn-full" @click="generateReport" :disabled="generating">
            <span v-if="generating" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>▶</span>
            {{ generating ? 'AI 分析中...' : genBtnLabel }}
          </button>
          <button
            v-if="reportType === 'inspect'"
            class="btn btn-outline btn-full"
            @click="generateAllGroups"
            :disabled="groupGenerating"
            title="为每个配置了飞书 webhook 的分组分别生成巡检报告并推送"
          >
            <span v-if="groupGenerating" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>📤</span>
            {{ groupGenerating ? '推送中...' : '按分组生成并推送' }}
          </button>
        </div>

        <div class="history-list">
          <div v-if="loadingList" class="empty-state" style="padding:30px">
            <div class="spinner"></div>
          </div>
          <div
            v-for="r in filteredList" :key="r.id"
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
          <div v-if="!loadingList && !filteredList.length" class="empty-state" style="padding:30px">
            <span class="icon" style="font-size:28px">📋</span>
            <p>暂无历史报告</p>
          </div>
        </div>
      </aside>

      <!-- 右侧：慢日志目标配置面板（仅 slowlog 类型时显示） -->
      <div v-if="reportType === 'slowlog'" class="slowlog-config-panel">
        <div class="slc-header" @click="slcOpen = !slcOpen">
          <span>⚙️ 慢日志报告目标配置</span>
          <span class="slc-saved" v-if="slcSaved">已保存 ✓</span>
          <svg class="chevron" :class="{ open: slcOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </div>

        <div v-if="slcOpen" class="slc-body">
          <!-- 全局参数 -->
          <div class="slc-row">
            <label class="slc-label">分析最近天数</label>
            <input v-model.number="slcConfig.date_days" type="number" min="1" max="30" class="inp-num" />
            <label class="slc-label" style="margin-left:16px">慢查询阈值(s)</label>
            <input v-model.number="slcConfig.threshold_sec" type="number" step="0.1" min="0.1" class="inp-num" />
            <label class="slc-label" style="margin-left:16px">告警阈值(s)</label>
            <input v-model.number="slcConfig.alert_sec" type="number" step="1" min="1" class="inp-num" />
          </div>
          <div class="slc-row" style="margin-top:6px">
            <label class="slc-label">定时推送</label>
            <label class="toggle-label">
              <input type="checkbox" v-model="slcConfig.enabled" />
              <span>{{ slcConfig.enabled ? '已启用（随定时日报一起推送）' : '未启用' }}</span>
            </label>
          </div>

          <!-- 目标主机列表 -->
          <div class="slc-targets-header">
            <span class="slc-label">目标主机</span>
            <button class="btn-xs" @click="addSlcTarget">+ 添加主机</button>
          </div>

          <div v-for="(t, i) in slcConfig.targets" :key="i" class="slc-target-row">
            <span class="slc-idx">{{ i + 1 }}</span>
            <input v-model="t.host_ip"   placeholder="IP 地址"    class="inp-s" />
            <input v-model="t.log_path"  placeholder="/mysqldata/.../mysql-slow.log" class="inp-path-s" />
            <select v-model="t.credential_id" class="inp-sel-s">
              <option value="">-- 凭证库 --</option>
              <option v-for="c in credList" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <span class="slc-or">或</span>
            <input v-model="t.ssh_user"     placeholder="用户名" class="inp-xs" />
            <input v-model="t.ssh_password" placeholder="密码"   class="inp-xs" type="password" />
            <input v-model.number="t.ssh_port" placeholder="22"  class="inp-port" type="number" />
            <button class="btn-remove-xs" @click="slcConfig.targets.splice(i, 1)" title="删除">✕</button>
          </div>

          <div v-if="!slcConfig.targets.length" class="slc-empty">暂无目标主机，点击「+ 添加主机」</div>

          <div class="slc-footer">
            <button class="btn btn-primary btn-sm" @click="saveSlcConfig" :disabled="slcSaving">
              {{ slcSaving ? '保存中...' : '保存配置' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 右侧报告详情 -->
      <div class="report-detail">

        <!-- 生成中（无报告） -->
        <div v-if="generating && !currentReport" class="empty-state" style="height:100%">
          <div class="spinner" style="width:36px;height:36px;border-width:3px"></div>
          <p style="margin-top:12px;color:var(--text-secondary)">正在采集数据并生成报告...</p>
        </div>

        <!-- 无报告 -->
        <div v-else-if="!currentReport" class="empty-state" style="height:100%">
          <span class="icon">📋</span>
          <p>
            <template v-if="reportType === 'slowlog'">请先配置目标主机，然后点击「立即生成慢日志报告」</template>
            <template v-else>请点击「立即生成日报」或选择历史报告</template>
          </p>
        </div>

        <!-- 报告内容 -->
        <div v-else class="report-content">

          <!-- 标题栏 -->
          <div class="report-title-bar">
            <div>
              <h2>{{ currentReport.title }}</h2>
              <p class="report-date">报告时间：{{ formatDate(currentReport.created_at) }}</p>
            </div>
            <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
              <button v-if="!generating" class="btn btn-outline" @click="generateReport" title="重新生成">
                🔄 重新生成
              </button>
              <button
                v-if="currentReport?.id && !generating"
                class="btn btn-notify feishu"
                :disabled="notifying.feishu"
                @click="sendNotify('feishu')"
              >
                <span v-if="notifying.feishu" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                <span v-else>🔔</span> 飞书
              </button>
              <button
                v-if="currentReport?.id && !generating"
                class="btn btn-notify dingtalk"
                :disabled="notifying.dingtalk"
                @click="sendNotify('dingtalk')"
              >
                <span v-if="notifying.dingtalk" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                <span v-else>🔔</span> 钉钉
              </button>
              <div class="health-circle" :class="healthClass(currentReport.health_score)">
                <div class="health-num">{{ currentReport.health_score }}</div>
                <div class="health-label">健康评分 /100</div>
              </div>
            </div>
          </div>

          <!-- ① 运维日报指标 -->
          <template v-if="!currentReport.type || currentReport.type === 'daily'">
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

          <!-- ② 主机巡检日报指标 -->
          <template v-else-if="currentReport.type === 'inspect'">
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

          <!-- ③ 慢日志报告指标 -->
          <template v-else-if="currentReport.type === 'slowlog'">
            <!-- 时间段 -->
            <div class="slowlog-date-range">
              📅 分析时段：<strong>{{ currentReport.date_from }}</strong> ~ <strong>{{ currentReport.date_to }}</strong>
            </div>
            <!-- 指标卡 -->
            <div class="metrics-row">
              <div class="metric-card">
                <div class="metric-icon">🖥️</div>
                <div class="metric-val">{{ currentReport.hosts_count ?? 0 }}</div>
                <div class="metric-label">分析主机数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🐌</div>
                <div class="metric-val">{{ fmtNum(currentReport.total_queries) }}</div>
                <div class="metric-label">慢查询总数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🔔</div>
                <div class="metric-val" :style="{ color: currentReport.alert_queries > 0 ? 'var(--error)' : 'var(--success)' }">
                  {{ fmtNum(currentReport.alert_queries) }}
                </div>
                <div class="metric-label">告警数（高耗时）</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">⏱️</div>
                <div class="metric-val" style="color:var(--warning)">{{ currentReport.avg_query_time }}s</div>
                <div class="metric-label">平均耗时</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🚨</div>
                <div class="metric-val" style="color:var(--error)">{{ currentReport.max_query_time }}s</div>
                <div class="metric-label">最大耗时</div>
              </div>
            </div>

            <!-- 各主机明细 -->
            <div class="section" v-if="currentReport.host_results?.length">
              <h3 class="section-title">🖥️ 各主机慢查询情况</h3>
              <table class="sl-table">
                <thead>
                  <tr>
                    <th>主机 IP</th><th>慢查询数</th><th>告警数</th>
                    <th>平均耗时(s)</th><th>最大耗时(s)</th><th>Top SQL 模板</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="h in currentReport.host_results" :key="h.host_ip">
                    <td class="mono">{{ h.host_ip }}</td>
                    <td>{{ h.total }}</td>
                    <td :style="{ color: h.alert_count > 0 ? 'var(--error)' : 'var(--success)' }">{{ h.alert_count }}</td>
                    <td>{{ h.avg_query_time }}</td>
                    <td>{{ h.max_query_time }}</td>
                    <td class="sl-clusters">
                      <span v-for="c in (h.top_clusters||[]).slice(0,2)" :key="c.rank" class="cluster-tag" :title="c.template">
                        ×{{ c.count }} {{ c.template.slice(0, 60) }}{{ c.template.length > 60 ? '...' : '' }}
                      </span>
                      <span v-if="!h.top_clusters?.length" class="muted">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Top 慢查询 -->
            <div class="section" v-if="currentReport.top_slow?.length">
              <h3 class="section-title">🐌 Top 10 最慢查询</h3>
              <div class="slowlog-list">
                <div v-for="(s, i) in currentReport.top_slow" :key="i" class="slowlog-row">
                  <span class="rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
                  <span class="sl-host mono">{{ s.host_ip }}</span>
                  <span class="sl-time" :class="s.query_time >= 10 ? 'sl-time-alert' : ''">{{ s.query_time }}s</span>
                  <span class="sl-rows">扫 {{ fmtNum(s.rows_examined) }} 行</span>
                  <span class="sl-sql" :title="s.sql_brief">{{ s.sql_brief }}</span>
                </div>
              </div>
            </div>

            <!-- SSH 错误提示 -->
            <div v-if="currentReport.errors?.length" class="section">
              <h3 class="section-title" style="color:var(--error)">⚠️ 采集失败的主机</h3>
              <div v-for="e in currentReport.errors" :key="e.host_ip" class="err-row">
                <span class="mono">{{ e.host_ip }}</span>：{{ e.error }}
              </div>
            </div>
          </template>

          <!-- AI 分析（通用） -->
          <div class="section">
            <div class="section-title-row">
              <h3 class="section-title">🤖 AI 分析</h3>
              <span v-if="generating" class="analyzing-badge">
                <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
                分析中
              </span>
            </div>
            <div class="ai-analysis-box">
              <div v-if="aiStreamContent" class="ai-text" v-html="renderText(aiStreamContent)"></div>
              <div v-else-if="currentReport.ai_analysis" class="ai-text" v-html="renderText(currentReport.ai_analysis)"></div>
              <div v-else-if="generating" class="ai-placeholder">
                <div class="spinner" style="width:20px;height:20px;border-width:2px"></div>
                <span>等待 AI 响应...</span>
              </div>
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
import { ref, computed, reactive, onMounted } from 'vue'
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
const credList      = ref([])
const groups        = ref([])
const inspectGroupId = ref('')
const groupGenerating = ref(false)

// ── 慢日志目标配置状态 ─────────────────────────────────────────────────
const slcOpen   = ref(true)
const slcSaved  = ref(false)
const slcSaving = ref(false)
const slcConfig = reactive({
  enabled: false, date_days: 1, threshold_sec: 1.0, alert_sec: 10.0, targets: [],
})

function addSlcTarget() {
  slcConfig.targets.push({
    host_ip: '', log_path: '/mysqldata/mysql/data/3306/mysql-slow.log',
    credential_id: '', ssh_user: '', ssh_password: '', ssh_port: 22,
  })
}

async function saveSlcConfig() {
  slcSaving.value = true
  try {
    await api.saveSlowlogTargets({ ...slcConfig, targets: [...slcConfig.targets] })
    slcSaved.value = true
    setTimeout(() => { slcSaved.value = false }, 3000)
  } catch (e) {
    errorMsg.value = '保存失败：' + e
  } finally {
    slcSaving.value = false
  }
}

async function loadSlcConfig() {
  try {
    const data = await api.getSlowlogTargets()
    Object.assign(slcConfig, data)
    if (!slcConfig.targets) slcConfig.targets = []
  } catch {}
}

// ── 工具函数 ───────────────────────────────────────────────────────────
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

const genBtnLabel = computed(() => {
  if (reportType.value === 'inspect') return '立即生成巡检日报'
  if (reportType.value === 'slowlog') return '立即生成慢日志报告'
  return '立即生成日报'
})

const filteredList = computed(() => {
  if (reportType.value === 'slowlog') return reportList.value.filter(r => r.type === 'slowlog')
  if (reportType.value === 'inspect') return reportList.value.filter(r => r.type === 'inspect')
  return reportList.value.filter(r => !r.type || r.type === 'daily')
})

const maxTop   = computed(() => currentReport.value?.top10_errors?.[0]?.count || 1)
const maxIssue = computed(() => currentReport.value?.top_issues?.[0]?.count || 1)
function topBarWidth(cnt)   { return Math.round((cnt / maxTop.value) * 100) }
function issueBarWidth(cnt) { return Math.round((cnt / maxIssue.value) * 100) }

// ── 列表 ───────────────────────────────────────────────────────────────
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

async function loadReport(id) {
  aiStreamContent.value = ''
  errorMsg.value = ''
  try {
    currentReport.value = await api.getReport(id)
  } catch (e) {
    errorMsg.value = '加载报告失败：' + e
  }
}

function onTypeChange() {
  currentReport.value = null
  aiStreamContent.value = ''
  inspectGroupId.value = ''
}

// ── 生成报告（SSE） ───────────────────────────────────────────────────
function generateReport() {
  if (generating.value) return
  generating.value   = true
  aiStreamContent.value = ''
  errorMsg.value     = ''

  const urlMap = {
    inspect: '/api/report/inspect/generate',
    slowlog: '/api/report/slowlog/generate',
    daily:   '/api/report/generate',
  }
  let url = urlMap[reportType.value] || urlMap.daily
  if (reportType.value === 'inspect' && inspectGroupId.value) {
    url += `?group_id=${encodeURIComponent(inspectGroupId.value)}`
  }

  streamSSE(
    url,
    (raw) => {
      if (raw.startsWith('__META__')) {
        try { currentReport.value = JSON.parse(raw.slice(8)); aiStreamContent.value = '' }
        catch (e) { console.error('META parse error', e) }
        return
      }
      try { aiStreamContent.value += JSON.parse(raw) }
      catch { aiStreamContent.value += raw }
    },
    async () => {
      generating.value = false
      await loadReportList()
      if (currentReport.value?.id) {
        try { currentReport.value = await api.getReport(currentReport.value.id) } catch {}
      }
    },
    (err) => {
      generating.value = false
      errorMsg.value   = '生成失败，请检查后端连接和配置'
      console.error('SSE error', err)
    },
  )
}

// ── 按分组生成并推送 ───────────────────────────────────────────────────
async function generateAllGroups() {
  if (groupGenerating.value) return
  groupGenerating.value = true
  errorMsg.value   = ''
  successMsg.value = ''
  try {
    const r = await fetch('/api/report/inspect/generate-groups', { method: 'POST' })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    const results = data.results || []
    const pushed  = results.filter(x => x.push?.ok).length
    const skipped = results.filter(x => x.skipped).length
    const failed  = results.filter(x => x.error || (x.push && !x.push.ok)).length
    successMsg.value = `分组推送完成：${pushed} 个成功，${skipped} 个跳过，${failed} 个失败`
    setTimeout(() => { successMsg.value = '' }, 6000)
    await loadReportList()
  } catch (e) {
    errorMsg.value = '按分组推送失败：' + e
  } finally {
    groupGenerating.value = false
  }
}

// ── 通知推送 ───────────────────────────────────────────────────────────
async function sendNotify(channel) {
  if (!currentReport.value?.id) return
  notifying.value[channel] = true
  errorMsg.value   = ''
  successMsg.value = ''
  try {
    const r   = await api.notifyReport(currentReport.value.id, [channel])
    const res = r.results?.[channel]
    if (res?.ok) {
      successMsg.value = `已成功发送到${channel === 'feishu' ? '飞书' : '钉钉'}`
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

onMounted(async () => {
  await loadReportList()
  try {
    const c = await api.listCredentials()
    credList.value = c.data || c
  } catch {}
  loadSlcConfig()
  try {
    const r = await fetch('/api/groups')
    if (r.ok) {
      const d = await r.json()
      groups.value = d.data || d
    }
  } catch {}
})
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

/* Toast */
.error-toast {
  position: absolute; top: 16px; right: 16px;
  background: rgba(239,68,68,.15); border: 1px solid rgba(239,68,68,.4);
  color: #fca5a5; padding: 10px 16px; border-radius: var(--radius);
  font-size: 13px; display: flex; align-items: center; gap: 10px; z-index: 100;
}
.success-toast {
  position: absolute; top: 16px; right: 16px;
  background: rgba(34,197,94,.15); border: 1px solid rgba(34,197,94,.4);
  color: #86efac; padding: 10px 16px; border-radius: var(--radius);
  font-size: 13px; display: flex; align-items: center; gap: 10px; z-index: 100;
}
.toast-close { background: none; border: none; color: inherit; cursor: pointer; font-size: 14px; opacity: .7; }
.toast-close:hover { opacity: 1; }

/* 布局 */
.report-layout { flex: 1; display: flex; gap: 16px; overflow: hidden; min-height: 0; }

/* 左侧 */
.report-list-panel {
  width: 240px; min-width: 240px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); display: flex; flex-direction: column; overflow: hidden;
}
.panel-top {
  padding: 12px; border-bottom: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 10px; flex-shrink: 0;
}
.time-select {
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-primary); padding: 6px 10px;
  border-radius: 6px; font-size: 13px; cursor: pointer;
}
.btn-full { width: 100%; justify-content: center; }
.history-list { flex: 1; overflow-y: auto; padding: 8px; }
.history-item {
  padding: 10px 12px; border-radius: 6px;
  cursor: pointer; margin-bottom: 4px; transition: background .12s;
}
.history-item:hover  { background: var(--bg-hover); }
.history-item.active { background: var(--accent-dim); color: var(--accent); }
.history-title {
  font-size: 13px; font-weight: 500; color: var(--text-primary);
  margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.history-meta { display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--text-muted); }

/* 慢日志配置面板 */
.slowlog-config-panel {
  width: 100%; flex-shrink: 0;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); margin-bottom: 0;
  /* 撑满剩余宽度的上部 - 通过 grid 布局实现，这里用独立面板 */
  max-width: 680px;
}
.slc-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; cursor: pointer; font-size: 13px; font-weight: 600;
  color: var(--text-primary); border-bottom: 1px solid transparent;
}
.slowlog-config-panel .slc-header:hover { background: var(--bg-hover); }
.slc-saved { font-size: 11px; color: var(--success); margin-left: auto; }
.chevron { transition: transform .2s; flex-shrink: 0; }
.chevron.open { transform: rotate(180deg); }
.slc-body { padding: 12px 16px 14px; border-top: 1px solid var(--border); }
.slc-row  { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.slc-label { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
.inp-num  { width: 64px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.inp-num:focus { border-color: var(--accent); }
.toggle-label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); cursor: pointer; }
.toggle-label input { accent-color: var(--accent); }
.slc-targets-header { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 6px; }
.btn-xs {
  padding: 3px 10px; background: var(--accent); color: #fff;
  border: none; border-radius: var(--radius); font-size: 11px; cursor: pointer;
}
.btn-xs:hover { opacity: .85; }
.slc-target-row {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 6px 8px; background: var(--bg-hover);
  border-radius: var(--radius); margin-bottom: 4px; border: 1px solid var(--border-light);
}
.slc-idx { font-size: 11px; color: var(--text-muted); width: 16px; text-align: center; flex-shrink: 0; }
.inp-s     { width: 120px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.inp-s:focus { border-color: var(--accent); }
.inp-path-s { flex: 1; min-width: 200px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.inp-sel-s { width: 130px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.slc-or { font-size: 11px; color: var(--text-muted); }
.inp-xs   { width: 90px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.inp-port { width: 50px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.btn-remove-xs { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 13px; padding: 2px 4px; }
.btn-remove-xs:hover { color: var(--error); }
.slc-empty { font-size: 12px; color: var(--text-muted); padding: 8px 0; }
.slc-footer { margin-top: 10px; display: flex; justify-content: flex-end; }
.btn-sm { padding: 5px 16px; font-size: 12px; }

/* 右侧 */
.report-detail {
  flex: 1;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); overflow-y: auto; min-height: 0;
}
.report-content { padding: 24px; }

/* 标题栏 */
.report-title-bar {
  display: flex; justify-content: space-between;
  align-items: flex-start; margin-bottom: 20px; gap: 16px;
}
.report-title-bar h2 { font-size: 20px; font-weight: 700; }
.report-date { color: var(--text-muted); font-size: 13px; margin-top: 4px; }

.health-circle {
  text-align: center; padding: 14px 18px;
  border-radius: var(--radius); border: 2px solid; min-width: 100px; flex-shrink: 0;
}
.health-circle.health-good { border-color: var(--success); color: var(--success); background: rgba(63,185,80,.08); }
.health-circle.health-mid  { border-color: var(--warning); color: var(--warning); background: rgba(210,153,34,.08); }
.health-circle.health-bad  { border-color: var(--error);   color: var(--error);   background: rgba(248,81,73,.08); }
.health-num   { font-size: 30px; font-weight: 800; line-height: 1; }
.health-label { font-size: 10px; margin-top: 4px; opacity: .8; }

/* 指标卡片 */
.metrics-row {
  display: grid; grid-template-columns: repeat(5, 1fr);
  gap: 10px; margin-bottom: 24px;
}
.metric-card {
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px 10px; text-align: center;
}
.metric-icon  { font-size: 20px; margin-bottom: 6px; }
.metric-val   { font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.metric-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

/* 区块 */
.section { margin-bottom: 24px; }
.section-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.section-title { font-size: 15px; font-weight: 600; margin-bottom: 14px; }

.analyzing-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--accent-hover);
  background: rgba(99,102,241,.12); border: 1px solid rgba(99,102,241,.25);
  padding: 2px 10px; border-radius: 9999px;
}
.analyzing-badge span { animation: pulse 1.2s ease-in-out infinite; }
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }

/* Top10 */
.top10-list { display: flex; flex-direction: column; gap: 10px; }
.top10-row  { display: flex; align-items: center; gap: 12px; }
.rank { width: 22px; text-align: center; font-size: 12px; color: var(--text-muted); font-weight: 700; flex-shrink: 0; }
.rank-top { color: var(--warning); }
.top10-svc { width: 180px; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.bar-wrap { flex: 1; height: 8px; background: var(--bg-hover); border-radius: 4px; overflow: hidden; }
.bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 4px; transition: width .4s ease; }

/* AI 分析框 */
.ai-analysis-box {
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px; min-height: 80px;
}
.ai-text { font-size: 13px; line-height: 2; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; }
:deep(.ai-warn) { color: var(--warning); }
:deep(.ai-ok)   { color: var(--success); }
:deep(strong)   { color: var(--text-primary); font-weight: 600; }
.ai-placeholder { display: flex; align-items: center; gap: 10px; color: var(--text-muted); font-size: 13px; padding: 8px 0; }

/* 通知按钮 */
.btn-notify { display: inline-flex; align-items: center; gap: 5px; padding: 5px 12px; border-radius: 6px; border: 1px solid; font-size: 12px; font-weight: 500; cursor: pointer; transition: opacity .15s; }
.btn-notify:disabled { opacity: .5; cursor: not-allowed; }
.btn-notify.feishu  { background: rgba(0,195,155,.1); border-color: rgba(0,195,155,.4); color: #00c39b; }
.btn-notify.feishu:hover:not(:disabled)   { background: rgba(0,195,155,.2); }
.btn-notify.dingtalk { background: rgba(255,106,0,.1); border-color: rgba(255,106,0,.4); color: #ff6a00; }
.btn-notify.dingtalk:hover:not(:disabled) { background: rgba(255,106,0,.2); }

/* 慢日志报告专用样式 */
.slowlog-date-range {
  font-size: 13px; color: var(--text-secondary);
  margin-bottom: 16px; padding: 8px 12px;
  background: var(--bg-hover); border-radius: var(--radius);
}
.sl-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.sl-table th { background: var(--bg-hover); padding: 7px 10px; text-align: left; font-weight: 600; border-bottom: 1px solid var(--border); color: var(--text-secondary); }
.sl-table td { padding: 8px 10px; border-bottom: 1px solid var(--border-light); vertical-align: top; color: var(--text-primary); }
.sl-table tr:last-child td { border-bottom: none; }
.sl-clusters { max-width: 300px; }
.cluster-tag { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.slowlog-list { display: flex; flex-direction: column; gap: 8px; }
.slowlog-row { display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px; background: var(--bg-hover); border-radius: var(--radius); border: 1px solid var(--border-light); }
.sl-host { font-size: 11px; color: var(--text-muted); width: 120px; flex-shrink: 0; }
.sl-time { font-size: 13px; font-weight: 700; width: 60px; flex-shrink: 0; color: var(--warning); }
.sl-time-alert { color: var(--error); }
.sl-rows { font-size: 11px; color: var(--text-muted); width: 90px; flex-shrink: 0; white-space: nowrap; }
.sl-sql { font-size: 12px; color: var(--text-secondary); font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.err-row { font-size: 12px; color: var(--error); padding: 4px 0; }
.muted { color: var(--text-muted); font-size: 12px; }
.mono { font-family: monospace; }

/* 异常主机 */
.abnormal-list { display: flex; flex-direction: column; gap: 6px; }
.abnormal-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: var(--radius);
  border: 1px solid var(--border); background: var(--bg-card); font-size: 12px;
}
.abnormal-row.row-critical { border-left: 3px solid var(--error); }
.abnormal-row.row-warning  { border-left: 3px solid var(--warning); }
.abnormal-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.abnormal-dot.critical { background: var(--error); }
.abnormal-dot.warning  { background: var(--warning); }
.abnormal-host { font-weight: 600; color: var(--text-primary); min-width: 120px; }
.abnormal-ip   { color: var(--text-muted); min-width: 110px; }
.abnormal-checks { flex: 1; display: flex; flex-wrap: wrap; gap: 4px; }
.check-tag { padding: 1px 7px; border-radius: 2px; font-size: 11px; background: var(--bg-hover); color: var(--text-secondary); border: 1px solid var(--border); }
.check-tag.warning  { background: rgba(255,156,1,.1);  color: var(--warning); border-color: rgba(255,156,1,.3); }
.check-tag.critical { background: rgba(234,54,54,.1);  color: var(--error);   border-color: rgba(234,54,54,.3); }

@keyframes pulse { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
.fade-enter-active, .fade-leave-active { transition: opacity .3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
