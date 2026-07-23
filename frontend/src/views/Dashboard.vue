<template>
  <div class="obs-page">
    <div class="obs-header">
      <div class="obs-header-left">
        <div class="obs-brand-icon">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
        </div>
        <div>
          <h1 class="obs-title">可观测<span class="obs-sep">|</span>平台总览</h1>
          <p class="obs-subtitle">告警、日志、追踪与看板统一汇总，实时感知系统健康状态</p>
        </div>
      </div>
      <div class="obs-header-right">
        <select class="time-select" v-model.number="windowMinutes" @change="onWindowChange">
          <option :value="1">最近 1 分钟</option>
          <option :value="10">最近 10 分钟</option>
          <option :value="30">最近 30 分钟</option>
          <option :value="60">最近 1 小时</option>
          <option :value="360">最近 6 小时</option>
          <option :value="1440">最近 24 小时</option>
        </select>
        <button class="btn-refresh" @click="forceRefresh" :disabled="refreshing" title="刷新">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" :class="{ spinning: refreshing }">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
        </button>
      </div>
    </div>

    <div class="stats-row">
      <div class="stat-card drillable" :class="{ 'stat-alert': hasPositive(overview.alert_count) }"
           @click="goAlerts" title="查看告警历史">
        <div class="stat-num" :class="{ 'num-alert': hasPositive(overview.alert_count), missing: !hasValue(overview.alert_count) }">
          {{ loading ? '--' : displayValue(overview.alert_count) }}
        </div>
        <div class="stat-label">告警触发 <span class="drill-arrow">→</span></div>
        <div class="stat-bar alert-bar"></div>
      </div>
      <div class="stat-card drillable" :class="{ 'stat-warn': typeof overview.error_count === 'number' && overview.error_count > 5 }"
           @click="goErrorLogs" title="按错误级别查询日志">
        <div class="stat-num" :class="{ 'num-warn': typeof overview.error_count === 'number' && overview.error_count > 5, missing: !hasValue(overview.error_count) }">
          {{ loading ? '--' : displayValue(overview.error_count) }}
        </div>
        <div class="stat-label">服务错误 <span class="drill-arrow">→</span></div>
        <div class="stat-bar error-bar"></div>
      </div>
      <div class="stat-card drillable" @click="goTraces" title="查看接口 RED 仪表盘">
        <div class="stat-num num-info" :class="{ missing: !hasValue(overview.trace_count) }">{{ loading ? '--' : displayValue(overview.trace_count) }}</div>
        <div class="stat-label">Trace 数 <span class="drill-arrow">→</span></div>
        <div class="stat-bar trace-bar"></div>
      </div>
      <div class="stat-card drillable" @click="goGrafana" title="打开 Grafana 看板列表">
        <div class="stat-num num-success" :class="{ missing: !hasValue(overview.grafana_count) }">{{ loading ? '--' : displayValue(overview.grafana_count) }}</div>
        <div class="stat-label">Grafana 看板 <span class="drill-arrow">→</span></div>
        <div class="stat-bar grafana-bar"></div>
      </div>
      <div class="stat-card drillable stat-resource" @click="goResources" title="查看 CMDB 与容器资源">
        <div class="stat-num num-resource" :class="{ missing: !hasValue(overview.resource_count) }">{{ loading ? '--' : displayValue(overview.resource_count) }}</div>
        <div class="stat-label">资源数量 <span class="drill-arrow">→</span></div>
        <div class="stat-sub">{{ displayValue(overview.resource_summary?.hosts) }} 主机 · {{ displayValue(overview.resource_summary?.containers) }} 容器资源</div>
        <div class="stat-bar resource-bar"></div>
      </div>
      <div class="stat-card drillable" :class="{ 'stat-alert': hasPositive(overview.host_abnormal_alert_count) }"
           @click="goHostAlerts" title="查看主机运行异常告警">
        <div class="stat-num" :class="{ 'num-alert': hasPositive(overview.host_abnormal_alert_count), 'num-host': isZero(overview.host_abnormal_alert_count), missing: !hasValue(overview.host_abnormal_alert_count) }">
          {{ loading ? '--' : displayValue(overview.host_abnormal_alert_count) }}
        </div>
        <div class="stat-label">主机异常告警 <span class="drill-arrow">→</span></div>
        <div class="stat-sub">活跃主机 / 节点类告警</div>
        <div class="stat-bar host-bar"></div>
      </div>
      <div class="stat-card drillable stat-container" :class="{ 'stat-warn': hasPositive(overview.container_resource_abnormal_count) }"
           @click="goContainerIssues" title="查看容器资源异常">
        <div class="stat-num" :class="{ 'num-warn': hasPositive(overview.container_resource_abnormal_count), 'num-container': isZero(overview.container_resource_abnormal_count), missing: !hasValue(overview.container_resource_abnormal_count) }">
          {{ loading ? '--' : displayValue(overview.container_resource_abnormal_count) }}
        </div>
        <div class="stat-label">容器资源异常 <span class="drill-arrow">→</span></div>
        <div class="stat-sub">Pod / Node / 工作负载</div>
        <div class="stat-bar container-bar"></div>
      </div>
    </div>

    <div class="ai-analyze-box card" :class="{ collapsed: aiBoxCollapsed }">
      <div class="ai-analyze-header" @click="aiBoxCollapsed = !aiBoxCollapsed" style="cursor: pointer">
        <span class="ai-icon-wrap">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="10" rx="2" />
            <path d="M9 11V7a3 3 0 016 0v4" />
            <circle cx="9" cy="16" r="1" fill="currentColor" />
            <circle cx="15" cy="16" r="1" fill="currentColor" />
          </svg>
        </span>
        <span class="ai-analyze-title">AI 分析</span>
        <span class="ai-model-badge">{{ aiModelName }}</span>
        <span v-if="analyzing" class="ai-analyzing-indicator">分析中...</span>
        <span class="ai-collapse-btn" :title="aiBoxCollapsed ? '展开' : '收起'">
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
            stroke-linecap="round"
            :style="{ transform: aiBoxCollapsed ? 'rotate(-90deg)' : 'rotate(0)', transition: 'transform .2s' }"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </span>
      </div>
      <div v-show="!aiBoxCollapsed" class="ai-analyze-body">
        <div class="ai-analyze-input-row">
          <input
            v-model="analyzeQuestion"
            class="ai-analyze-input"
            placeholder="描述问题或直接提问：当前最需要关注什么？"
            @keydown.enter="startAnalyze"
            :disabled="analyzing"
          />
          <button class="btn-analyze" @click="startAnalyze" :disabled="analyzing || !analyzeQuestion.trim()">
            <span v-if="analyzing" class="spinner-sm"></span>
            <span v-else>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </span>
            {{ analyzing ? '分析中...' : '分析' }}
          </button>
        </div>
        <div v-if="analyzeResult" class="ai-analyze-result">
          <div class="ai-analyze-content" v-html="renderAnalysis(analyzeResult)"></div>
          <span v-if="analyzing" class="cursor-blink"></span>
        </div>
      </div>
    </div>

    <div class="main-grid">
      <div class="left-col">
        <div class="section-card card">
          <div class="section-header">
            <span class="section-dot dot-alert"></span>
            <h2 class="section-title">根因中心</h2>
            <span class="section-count">{{ overview.problem_services?.length || 0 }} 个异常服务</span>
            <button class="section-link" @click="forceRefresh">刷新</button>
          </div>

          <div v-if="loading" class="section-loading">
            <div class="spinner"></div>
          </div>

          <div v-else-if="!overview.problem_services?.length" class="section-empty">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <span>当前无异常服务</span>
          </div>

          <div v-else class="rca-grid">
            <div
              v-for="svc in overview.problem_services"
              :key="svc.service"
              class="rca-card"
              :class="svc.severity"
            >
              <div class="rca-header">
                <span class="rca-severity-dot" :class="svc.severity"></span>
                <span class="rca-svc-name">{{ svc.service }}</span>
                <span class="rca-badge" v-if="svc.errors > 0">{{ svc.errors }} 错误</span>
                <span class="rca-badge alert-badge" v-if="svc.alerts > 0">{{ svc.alerts }} 告警</span>
              </div>
              <div class="rca-summary">{{ svc.summary || '存在异常，建议尽快排查。' }}</div>
              <div v-if="svc.summary_source === 'rca' || svc.rca_created_at" class="rca-summary-meta">
                <span v-if="svc.summary_source === 'rca'" class="rca-ai-badge">AI RCA</span>
                <span v-if="svc.rca_created_at" class="rca-summary-time">{{ fmtRcaTime(svc.rca_created_at) }}</span>
              </div>
              <div class="rca-actions">
                <RouterLink
                  v-if="svc.rca_id"
                  :to="{ path: '/aiops/rca', query: { rca_id: svc.rca_id } }"
                  class="rca-link"
                >
                  RCA 详情
                </RouterLink>
                <RouterLink :to="{ path: '/observability/logs', query: { service: svc.service } }" class="rca-link">日志分析</RouterLink>
                <RouterLink :to="{ path: '/observability/trace', query: { service: svc.service } }" class="rca-link">链路追踪</RouterLink>
                <button class="rca-link" @click="askAI(svc.service)">AI 分析</button>
              </div>
            </div>
          </div>
        </div>

        <div class="section-card card">
          <div class="section-header">
            <span class="section-dot dot-alert"></span>
            <h2 class="section-title">告警列表</h2>
            <RouterLink to="/alerts" class="section-link">查看全部 →</RouterLink>
          </div>

          <div v-if="loading" class="section-loading"><div class="spinner"></div></div>

          <div v-else-if="!sourceFetched('alerts')" class="section-empty">
            <span>告警数据未获取</span>
          </div>

          <div v-else-if="!overview.recent_alerts?.length" class="section-empty">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
            <span>暂无活动告警</span>
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

      <div class="right-col">
        <div class="section-card card">
          <div class="section-header">
            <span class="section-dot dot-trace"></span>
            <h2 class="section-title">服务拓扑</h2>
          </div>
          <div class="topo-grid">
            <RouterLink to="/skywalking" class="topo-card">
              <div class="topo-icon topo-trace">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="5" r="2" />
                  <circle cx="5" cy="19" r="2" />
                  <circle cx="19" cy="19" r="2" />
                  <line x1="12" y1="7" x2="5" y2="17" />
                  <line x1="12" y1="7" x2="19" y2="17" />
                  <line x1="5" y1="19" x2="19" y2="19" />
                </svg>
              </div>
              <div class="topo-info">
                <div class="topo-label">链路追踪</div>
                <div class="topo-sub">SkyWalking / OAP</div>
              </div>
              <div class="topo-count" :class="{ missing: !hasValue(overview.trace_count) }">{{ displayValue(overview.trace_count) }}</div>
            </RouterLink>

            <RouterLink to="/alerts" class="topo-card">
              <div class="topo-icon topo-alert">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
                  <path d="M13.73 21a2 2 0 01-3.46 0" />
                </svg>
              </div>
              <div class="topo-info">
                <div class="topo-label">告警中心</div>
                <div class="topo-sub">Prometheus / Alertmanager</div>
              </div>
              <div class="topo-count" :class="{ 'count-alert': hasPositive(overview.alert_count), missing: !hasValue(overview.alert_count) }">{{ displayValue(overview.alert_count) }}</div>
            </RouterLink>

            <RouterLink to="/metrics" class="topo-card">
              <div class="topo-icon topo-metric">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <div class="topo-info">
                <div class="topo-label">指标总览</div>
                <div class="topo-sub">Prometheus 指标</div>
              </div>
              <div class="topo-count" :class="{ missing: !hasValue(overview.trace_count) }">{{ displayValue(overview.trace_count) }}</div>
            </RouterLink>

            <div class="topo-card topo-grafana" @click="openGrafana">
              <div class="topo-icon topo-grafana-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                  <rect x="3" y="3" width="7" height="7" />
                  <rect x="14" y="3" width="7" height="7" />
                  <rect x="14" y="14" width="7" height="7" />
                  <rect x="3" y="14" width="7" height="7" />
                </svg>
              </div>
              <div class="topo-info">
                <div class="topo-label">Grafana 看板</div>
                <div class="topo-sub">{{ overview.grafana_boards?.length || 0 }} 个看板</div>
              </div>
              <div class="topo-count num-success" :class="{ missing: !hasValue(overview.grafana_count) }">{{ displayValue(overview.grafana_count) }}</div>
            </div>
          </div>

          <div v-if="overview.grafana_boards?.length" class="grafana-list">
            <div
              v-for="b in overview.grafana_boards"
              :key="b.id"
              class="grafana-item"
              @click="openBoard(b)"
              :class="{ clickable: b.url }"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="3" y="3" width="7" height="7" />
                <rect x="14" y="3" width="7" height="7" />
                <rect x="14" y="14" width="7" height="7" />
                <rect x="3" y="14" width="7" height="7" />
              </svg>
              <span>{{ b.title }}</span>
            </div>
          </div>
        </div>

        <div class="section-card card">
          <div class="section-header">
            <span class="section-dot dot-trace"></span>
            <h2 class="section-title">最近 Trace</h2>
            <RouterLink to="/skywalking" class="section-link">查看全部 →</RouterLink>
          </div>

          <div v-if="loading" class="section-loading"><div class="spinner"></div></div>

          <div v-else-if="!sourceFetched('skywalking')" class="section-empty">
            <span>Trace 数据未获取</span>
          </div>

          <div v-else-if="!overview.recent_traces?.length" class="section-empty">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="12" cy="5" r="2" />
              <circle cx="5" cy="19" r="2" />
              <circle cx="19" cy="19" r="2" />
              <line x1="12" y1="7" x2="5" y2="17" />
              <line x1="12" y1="7" x2="19" y2="17" />
            </svg>
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
                <td><span class="svc-tag">{{ displayValue(t.service) }}</span></td>
                <td class="text-muted" style="max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap">
                  {{ displayValue(t.endpoint || t.trace_id) }}
                </td>
                <td class="mono" :class="{ 'dur-slow': t.duration > 1000, 'dur-warn': t.duration > 500 && t.duration <= 1000 }">
                  {{ displayDuration(t.duration) }}
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
import { onBeforeUnmount, onMounted, reactive, ref, computed } from 'vue'
import { RouterLink, useRouter } from 'vue-router'

const router = useRouter()
const MISSING_TEXT = '未获取'

function hasValue(value) {
  return value !== null && value !== undefined && value !== ''
}

function hasPositive(value) {
  return typeof value === 'number' && value > 0
}

function isZero(value) {
  return value === 0
}

function displayValue(value) {
  return hasValue(value) ? value : MISSING_TEXT
}

function displayDuration(value) {
  return hasValue(value) ? `${value} ms` : MISSING_TEXT
}

function sourceFetched(key) {
  return overview.fetch_status?.[key] !== false
}

// ── KPI 钻取 ──────────────────────────────────────────────────────────────
function goAlerts()    { router.push('/observability/alerts') }
function goErrorLogs() { router.push({ path: '/observability/logs', query: { level: 'error' } }) }
function goTraces()    { router.push('/observability/api-red') }
function goGrafana()   { router.push('/observability/grafana') }
function goResources() { router.push('/cmdb') }
function goHostAlerts() { router.push('/observability/alerts') }
function goContainerIssues() { router.push('/containers') }
function goServiceLogs(service) { router.push({ path: '/observability/logs', query: { service } }) }
import { api } from '../api/index.js'
import { fetchHealthStatus, getAiModelShort } from '../composables/useHealthStatus.js'

const hasLoaded = ref(false)      // 是否已有可展示的数据（首次或缓存）
const refreshing = ref(false)     // 请求进行中（后台刷新不遮挡已有数据）
const loading = computed(() => refreshing.value && !hasLoaded.value)
const windowMinutes = ref(1)
const overview = reactive({
  alert_count: null,
  error_count: null,
  trace_count: null,
  grafana_count: null,
  resource_count: null,
  resource_summary: { total: null, hosts: null, containers: null, k8s_available: false },
  host_abnormal_alert_count: null,
  host_resource_summary: { total: null, abnormal_alerts: null, abnormal_status: null },
  container_resource_count: null,
  container_resource_abnormal_count: null,
  container_resource_summary: null,
  recent_alerts: [],
  recent_traces: [],
  problem_services: [],
  grafana_boards: [],
  fetch_status: {},
})

const aiBoxCollapsed = ref(true)
const analyzeQuestion = ref('')
const analyzeResult = ref('')
const analyzing = ref(false)
const aiModelName = ref('AI')

let overviewAbortController = null
let overviewRequestId = 0
let dashboardMounted = true

function isRequestCanceled(error) {
  return error?.code === 'ERR_CANCELED' || error?.name === 'CanceledError' || error?.name === 'AbortError'
}

// ── sessionStorage 缓存：回到首页秒开，后台静默刷新 ──────────────────────
const OVERVIEW_CACHE_PREFIX = 'obs-overview:'

function readOverviewCache(minutes) {
  try {
    const raw = sessionStorage.getItem(OVERVIEW_CACHE_PREFIX + minutes)
    const parsed = raw ? JSON.parse(raw) : null
    return parsed && typeof parsed === 'object' ? parsed : null
  } catch {
    return null
  }
}

function writeOverviewCache(minutes, data) {
  try {
    sessionStorage.setItem(OVERVIEW_CACHE_PREFIX + minutes, JSON.stringify(data))
  } catch {
    // 存储满/隐私模式等，忽略
  }
}

function applyCachedOverview() {
  const cached = readOverviewCache(windowMinutes.value)
  if (cached) {
    Object.assign(overview, cached)
    hasLoaded.value = true
  } else {
    hasLoaded.value = false
  }
  return !!cached
}

async function fetchAiModel() {
  try {
    const result = await fetchHealthStatus()
    if (!dashboardMounted) return
    aiModelName.value = getAiModelShort(result.ai_provider || '')
  } catch {
    // ignore
  }
}

async function loadAll(options = {}) {
  const force = options === true || options?.force === true
  const requestId = ++overviewRequestId
  overviewAbortController?.abort()
  const controller = new AbortController()
  overviewAbortController = controller
  refreshing.value = true

  try {
    const params = { minutes: windowMinutes.value }
    if (force) params.refresh = true
    const data = await api.observabilityOverview(params, { signal: controller.signal })
    if (!dashboardMounted || requestId !== overviewRequestId) return
    Object.assign(overview, data)
    hasLoaded.value = true
    writeOverviewCache(windowMinutes.value, data)
    // 命中后端 stale 数据时，稍后自动拉一次新鲜结果（后端已在后台重建）
    if (data?.stale && !force) {
      setTimeout(() => {
        if (dashboardMounted && requestId === overviewRequestId) loadAll()
      }, 3000)
    }
  } catch (error) {
    if (isRequestCanceled(error)) return
    console.warn('[obs] 加载总览失败:', error)
  } finally {
    if (requestId === overviewRequestId) {
      refreshing.value = false
    }
    if (overviewAbortController === controller) {
      overviewAbortController = null
    }
  }
}

function forceRefresh() {
  return loadAll({ force: true })
}

function onWindowChange() {
  applyCachedOverview()
  loadAll()
}

function fmtRcaTime(iso) {
  if (!iso) return ''
  return String(iso).slice(0, 16).replace('T', ' ')
}

async function startAnalyze() {
  const question = analyzeQuestion.value.trim()
  if (!question || analyzing.value) return

  aiBoxCollapsed.value = false
  analyzing.value = true
  analyzeResult.value = ''

  try {
    const response = await fetch('/api/observability/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ question, minutes: windowMinutes.value }),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      let chunkIndex = buffer.indexOf('\n\n')

      while (chunkIndex !== -1) {
        const chunk = buffer.slice(0, chunkIndex)
        buffer = buffer.slice(chunkIndex + 2)

        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.type === 'token') analyzeResult.value += event.text || ''
            if (event.type === 'done') analyzing.value = false
            if (event.type === 'error') {
              analyzeResult.value += `\n错误：${event.message}`
              analyzing.value = false
            }
          } catch {
            // ignore malformed SSE chunks
          }
        }

        chunkIndex = buffer.indexOf('\n\n')
      }
    }
  } catch (error) {
    analyzeResult.value = `错误：分析失败，${error.message}`
  } finally {
    analyzing.value = false
  }
}

function askAI(service) {
  analyzeQuestion.value = `分析 ${service} 服务当前异常，给出根因和处理建议`
  aiBoxCollapsed.value = false
  startAnalyze()
}

function openGrafana() {
  const url = overview.grafana_boards?.[0]?.url
  window.open(url || 'http://localhost:3000', '_blank')
}

function openBoard(board) {
  if (board.url) window.open(board.url, '_blank')
}

function renderAnalysis(text) {
  if (!text) return ''

  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^## (.+)$/gm, '<div class="analysis-title">$1</div>')
    .replace(/^(\d+)\.\s+(.+)$/gm, '<div class="analysis-li"><span class="li-num">$1</span><span>$2</span></div>')
    .replace(/^[-*]\s+(.+)$/gm, '<div class="analysis-li"><span class="li-dot">•</span><span>$1</span></div>')
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
    .replace(/\n/g, '<br>')
}

onMounted(() => {
  applyCachedOverview() // 有缓存则立即渲染，避免整页 spinner
  loadAll()
  fetchAiModel()
})

onBeforeUnmount(() => {
  dashboardMounted = false
  overviewAbortController?.abort()
  overviewAbortController = null
})
</script>

<style scoped>
.obs-page {
  padding: 24px clamp(18px, 2.4vw, 30px);
  height: 100%;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  background:
    radial-gradient(900px circle at 100% 0%, rgba(var(--accent-rgb), 0.05), transparent 34%),
    radial-gradient(700px circle at 0% 0%, rgba(99, 130, 91, 0.04), transparent 30%);
}

.obs-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border-light);
}

.obs-header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.obs-brand-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.18), rgba(var(--accent-rgb), 0.08));
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: inset 0 0 0 1px rgba(var(--accent-rgb), 0.12);
}

.obs-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.015em;
}

.obs-sep {
  color: var(--text-muted);
  margin: 0 4px;
}

.obs-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 4px 0 0;
  max-width: 760px;
}

.obs-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.time-select {
  padding: 8px 12px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-input);
  color: var(--text-primary);
  cursor: pointer;
  min-height: 34px;
}

.btn-refresh {
  width: 36px;
  height: 36px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-card);
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all .15s;
}

.btn-refresh:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-refresh:disabled {
  opacity: .4;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.spinning {
  animation: spin .8s linear infinite;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 14px;
}

.stat-card.drillable { cursor: pointer; transition: transform .15s, border-color .15s, box-shadow .15s; }
.stat-card.drillable:hover { transform: translateY(-2px); border-color: var(--accent); box-shadow: var(--shadow-md); }
.drill-arrow { color: var(--accent); opacity: 0; margin-left: 4px; transition: opacity .15s, transform .15s; display: inline-block; }
.stat-card.drillable:hover .drill-arrow { opacity: 1; transform: translateX(2px); }
.stat-card {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(255, 253, 249, 0.98)),
    var(--bg-card);
  border: 1px solid var(--border);
  border-left: 3px solid var(--border-strong);
  border-radius: 20px;
  padding: 20px 18px 16px;
  position: relative;
  overflow: hidden;
  transition: border-color .15s, box-shadow .15s, transform .15s;
}

.stat-card:hover {
  box-shadow: var(--shadow);
}

.stat-card.stat-alert {
  border-left-color: var(--error);
  background: linear-gradient(135deg, rgba(203, 59, 48, 0.03) 0%, transparent 60%);
}

.stat-card.stat-warn {
  border-left-color: var(--warning);
  background: linear-gradient(135deg, rgba(181, 112, 22, 0.03) 0%, transparent 60%);
}

.stat-card:not(.stat-alert):not(.stat-warn) {
  border-left-color: var(--accent);
}

.stat-card.stat-resource {
  border-left-color: var(--success);
  background: linear-gradient(135deg, rgba(63, 185, 80, 0.03) 0%, transparent 60%);
}

.stat-card.stat-container:not(.stat-warn) {
  border-left-color: var(--accent);
}

.stat-num {
  font-size: 34px;
  font-weight: 700;
  font-family: 'Cascadia Code', 'Consolas', 'SF Mono', monospace;
  color: var(--text-primary);
  line-height: 1;
  letter-spacing: 0;
}

.stat-num.missing {
  font-size: 22px;
  color: var(--text-muted);
  letter-spacing: 0;
}

.num-alert {
  color: var(--error);
}

.num-warn {
  color: var(--warning);
}

.num-info {
  color: var(--accent);
}

.num-success {
  color: var(--success);
}

.num-resource {
  color: var(--success);
}

.num-host,
.num-container {
  color: var(--accent);
}

.stat-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  margin-top: 8px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.stat-sub {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stat-bar {
  display: none;
}

.ai-analyze-box {
  padding: 16px 18px;
  transition: padding .2s, box-shadow .2s;
  box-shadow: var(--shadow-sm);
}

.ai-analyze-box.collapsed {
  padding: 10px 18px;
}

.ai-analyze-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 0;
  user-select: none;
}

.ai-analyze-body {
  margin-top: 12px;
}

.ai-collapse-btn {
  margin-left: auto;
  color: var(--text-muted);
  display: flex;
  align-items: center;
}

.ai-analyzing-indicator {
  font-size: 11px;
  color: var(--accent);
  margin-left: 4px;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: .4;
  }
}

.ai-icon-wrap {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: var(--accent-dim);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
}

.ai-analyze-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.ai-model-badge {
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
  background: var(--accent-dim);
  color: var(--accent);
  border: 1px solid rgba(56, 139, 253, 0.25);
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.ai-analyze-input-row {
  display: flex;
  gap: 8px;
}

.ai-analyze-input {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  outline: none;
}

.ai-analyze-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim);
}

.ai-analyze-input:disabled {
  opacity: .5;
}

.btn-analyze {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  border-radius: 12px;
  border: none;
  background: var(--accent);
  color: #fff;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: opacity .15s;
  white-space: nowrap;
}

.btn-analyze:hover:not(:disabled) {
  opacity: .85;
}

.btn-analyze:disabled {
  opacity: .45;
  cursor: not-allowed;
}

.ai-analyze-result {
  margin-top: 12px;
  padding: 14px 16px;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-primary);
}

.ai-analyze-result :deep(.analysis-title) {
  font-weight: 700;
  color: var(--accent);
  margin: 10px 0 5px;
  padding-left: 8px;
  border-left: 3px solid var(--accent);
}

.ai-analyze-result :deep(.analysis-li) {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin: 3px 0;
}

.ai-analyze-result :deep(.li-num) {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ai-analyze-result :deep(.li-dot) {
  color: var(--accent);
  font-weight: 700;
}

.ai-analyze-result :deep(.inline-code) {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px;
  padding: 1px 5px;
  background: var(--bg-card);
  border-radius: 3px;
  color: var(--accent);
}

.cursor-blink {
  display: inline-block;
  width: 2px;
  height: 13px;
  background: var(--accent);
  margin-left: 2px;
  vertical-align: middle;
  animation: blink .9s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  gap: 18px;
  align-items: start;
}

.left-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.right-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card {
  padding: 0;
  overflow: hidden;
  border-radius: 20px;
  box-shadow: var(--shadow-sm);
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(180deg, rgba(255,255,255,0.58), transparent);
}

.section-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-alert {
  background: var(--error);
  box-shadow: 0 0 6px rgba(248, 81, 73, .4);
}

.dot-trace {
  background: var(--accent);
  box-shadow: 0 0 6px rgba(56, 139, 253, .4);
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.section-count {
  font-size: 12px;
  color: var(--text-muted);
}

.section-link {
  font-size: 12px;
  color: var(--accent);
  text-decoration: none;
  background: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
  padding: 0;
}

.section-link:hover {
  opacity: .8;
}

.section-loading {
  display: flex;
  justify-content: center;
  padding: 32px;
}

.section-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 36px 20px;
  color: var(--success);
  font-size: 13px;
}

.section-empty svg {
  opacity: .6;
}

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

.rca-card.error {
  border-color: rgba(248, 81, 73, 0.3);
}

.rca-card.warning {
  border-color: rgba(210, 153, 34, 0.3);
}

.rca-card:hover {
  box-shadow: var(--shadow-sm);
}

.rca-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 5px;
}

.rca-severity-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.rca-severity-dot.error {
  background: var(--error);
}

.rca-severity-dot.warning {
  background: var(--warning);
}

.rca-svc-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.rca-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(248, 81, 73, .1);
  color: var(--error);
}

.alert-badge {
  background: rgba(210, 153, 34, .1);
  color: var(--warning);
}

.rca-summary {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  line-height: 1.4;
}

.rca-summary-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.rca-ai-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(56, 139, 253, .12);
  color: var(--accent);
  font-weight: 600;
}

.rca-summary-time {
  font-size: 10px;
  color: var(--text-muted);
}

.rca-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.rca-link {
  font-size: 11px;
  color: var(--accent);
  text-decoration: none;
  background: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
  padding: 0;
  transition: opacity .12s;
}

.rca-link:hover {
  opacity: .75;
}

.obs-table {
  width: 100%;
  border-collapse: collapse;
}

.obs-table th {
  padding: 8px 14px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--text-muted);
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  text-align: left;
}

.obs-table td {
  padding: 9px 14px;
  font-size: 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border-light);
}

.obs-table tbody tr:hover td {
  background: var(--bg-hover);
}

.text-muted {
  color: var(--text-muted) !important;
}

.mono {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 11px !important;
}

.svc-tag {
  font-size: 11px;
  padding: 2px 7px;
  background: var(--accent-dim);
  color: var(--accent);
  border-radius: 3px;
  font-weight: 500;
}

.severity-badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 3px;
  font-weight: 600;
  text-transform: uppercase;
}

.severity-badge.critical {
  background: rgba(248, 81, 73, .15);
  color: var(--error);
}

.severity-badge.warning {
  background: rgba(210, 153, 34, .15);
  color: var(--warning);
}

.severity-badge.info {
  background: rgba(56, 139, 253, .12);
  color: var(--accent);
}

.trace-status {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 3px;
  font-weight: 600;
}

.trace-status.ok {
  background: rgba(63, 185, 80, .12);
  color: var(--success);
}

.trace-status.error {
  background: rgba(248, 81, 73, .12);
  color: var(--error);
}

.dur-slow {
  color: var(--error) !important;
}

.dur-warn {
  color: var(--warning) !important;
}

.topo-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 14px 18px 6px;
}

.topo-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 13px;
  border: 1px solid var(--border);
  border-radius: 16px;
  text-decoration: none;
  cursor: pointer;
  transition: border-color .12s, background .12s, transform .12s, box-shadow .12s;
  background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(255,253,249,0.95));
}

.topo-card:hover {
  border-color: var(--accent);
  background: var(--accent-dim);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.topo-icon {
  width: 32px;
  height: 32px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.topo-trace {
  background: rgba(56, 139, 253, .12);
  color: var(--accent);
}

.topo-alert {
  background: rgba(248, 81, 73, .1);
  color: var(--error);
}

.topo-metric {
  background: rgba(63, 185, 80, .1);
  color: var(--success);
}

.topo-grafana-icon {
  background: rgba(210, 153, 34, .1);
  color: var(--warning);
}

.topo-info {
  flex: 1;
  min-width: 0;
}

.topo-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.topo-sub {
  font-size: 10px;
  color: var(--text-muted);
}

.topo-count {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-secondary);
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.topo-count.missing {
  font-size: 13px;
  color: var(--text-muted);
}

.count-alert {
  color: var(--error);
}

.grafana-list {
  padding: 4px 18px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.grafana-item {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: var(--text-muted);
  padding: 3px 0;
}

.grafana-item.clickable {
  cursor: pointer;
  transition: color .15s;
}

.grafana-item.clickable:hover {
  color: var(--accent);
}

.spinner {
  width: 20px;
  height: 20px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin .8s linear infinite;
}

.spinner-sm {
  display: inline-block;
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255, 255, 255, .3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}

@media (max-width: 1280px) {
  .main-grid {
    grid-template-columns: 1fr;
  }

  .right-col {
    order: 2;
  }
}

@media (max-width: 900px) {
  .obs-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .obs-header-right {
    width: 100%;
    justify-content: flex-start;
  }

  .stats-row {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  }

  .topo-grid {
    grid-template-columns: 1fr;
  }

  .ai-analyze-input-row {
    flex-direction: column;
  }

  .btn-analyze {
    width: 100%;
    justify-content: center;
  }
}
</style>
