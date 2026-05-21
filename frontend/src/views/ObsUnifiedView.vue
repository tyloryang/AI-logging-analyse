<template>
  <div class="obs-layout">

    <!-- ══════════════ 顶栏：数据源·服务·时间·状态·数量 ══════════════ -->
    <div class="obs-topbar">
      <!-- 左侧过滤条 -->
      <div class="obs-topbar-filters">
        <!-- 数据源 -->
        <div class="obs-filter-chip">
          <span class="obs-fc-label">数据源</span>
          <select v-model="datasource" class="obs-fc-select" @change="onDatasourceChange">
            <option value="loki">Loki</option>
            <option value="prometheus">Prometheus</option>
            <option value="skywalking">SkyWalking</option>
            <option value="jenkins">Jenkins</option>
          </select>
        </div>
        <!-- 服务 -->
        <div class="obs-filter-chip">
          <span class="obs-fc-label">服务</span>
          <select v-model="selectedService" class="obs-fc-select" @change="onServiceChange">
            <option value="">全部</option>
            <option v-for="s in serviceOptions" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <!-- 时间 -->
        <div class="obs-filter-chip obs-filter-time" @click="toggleTimePicker">
          <span class="obs-fc-label">时间</span>
          <span class="obs-fc-val">{{ timeLabel }}</span>
          <span class="obs-fc-arrow">{{ showTimePicker ? '▲' : '▼' }}</span>
          <!-- 时间下拉 -->
          <div v-if="showTimePicker" class="obs-time-dropdown" @click.stop>
            <div class="obs-time-presets">
              <button v-for="p in TIME_PRESETS" :key="p.v"
                class="obs-tp-btn" :class="{ active: timePreset === p.v && !customTimeActive }"
                @click="applyPreset(p)">{{ p.label }}</button>
            </div>
            <div class="obs-time-custom">
              <input type="datetime-local" v-model="customStart" class="obs-time-input" />
              <span class="obs-time-sep">~</span>
              <input type="datetime-local" v-model="customEnd" class="obs-time-input" />
              <button class="obs-apply-btn" @click="applyCustomTime">应用</button>
            </div>
          </div>
        </div>
        <!-- 状态 -->
        <div class="obs-filter-chip">
          <span class="obs-fc-label">状态</span>
          <select v-model="statusFilter" class="obs-fc-select" @change="onFilterChange">
            <option value="">全部</option>
            <option value="error">ERROR</option>
            <option value="success">SUCCESS</option>
            <option value="running">RUNNING</option>
          </select>
        </div>
        <!-- 数量统计 -->
        <div class="obs-stat-chips">
          <span class="obs-stat-chip chip-total">总计 {{ totalCount }}</span>
          <span class="obs-stat-chip chip-err" v-if="errorCount">错误 {{ errorCount }}</span>
          <span class="obs-stat-chip chip-ok" v-if="successCount">成功 {{ successCount }}</span>
          <span class="obs-stat-chip chip-run" v-if="runningCount">运行中 {{ runningCount }}</span>
        </div>
      </div>
      <!-- 右侧 Tabs -->
      <div class="obs-tabs">
        <button v-for="tab in TABS" :key="tab.id"
          class="obs-tab-btn" :class="{ active: activeTab === tab.id }"
          @click="switchTab(tab.id)">
          {{ tab.icon }} {{ tab.label }}
        </button>
      </div>
    </div>

    <!-- ══════════════ 主体（左侧列表 + 右侧详情）══════════════ -->
    <div class="obs-body">

      <!-- ─────────── 查日志 ─────────── -->
      <template v-if="activeTab === 'logs'">
        <aside class="obs-sidebar">
          <div class="obs-sb-header">
            <span class="obs-sb-title">日志列表</span>
            <span class="obs-sb-count">{{ logLines.length }}</span>
            <button class="obs-sb-refresh" @click="loadLogs" :disabled="loadingLogs">↻</button>
          </div>
          <div class="obs-sb-search">
            <input v-model="logSearch" class="obs-sb-input" placeholder="搜索服务..." />
          </div>
          <div class="obs-sb-list">
            <div v-for="svc in filteredLogServices" :key="svc"
              class="obs-sb-item" :class="{ active: selectedLogSvc === svc }"
              @click="selectLogSvc(svc)">
              <span class="obs-sb-dot"></span>
              <span class="obs-sb-name">{{ svc }}</span>
              <span class="obs-sb-badge">{{ logServiceCount[svc] || 0 }}</span>
            </div>
          </div>
        </aside>
        <div class="obs-main">
          <div class="obs-main-header">
            <span class="obs-main-title">{{ selectedLogSvc || '全部服务' }}</span>
            <span class="obs-main-sub">共 {{ filteredLogs.length }} 条</span>
            <div class="obs-mh-spacer"></div>
            <input v-model="logKeyword" class="obs-search-input" placeholder="关键字过滤..." />
            <select v-model="logLevel" class="obs-fc-select obs-fc-select-sm" @change="loadLogs">
              <option value="">全部级别</option>
              <option value="error">ERROR</option>
              <option value="warn">WARN</option>
              <option value="info">INFO</option>
            </select>
          </div>
          <div class="obs-content-area">
            <div v-if="loadingLogs" class="obs-empty"><div class="spinner"></div><p>加载中...</p></div>
            <div v-else-if="!filteredLogs.length" class="obs-empty"><span>暂无日志数据</span></div>
            <div v-else class="obs-log-list">
              <div v-for="(log, i) in filteredLogs" :key="i"
                class="obs-log-row" :class="logRowClass(log)"
                @click="selectedLog = log">
                <span class="obs-log-lv" :class="logLvClass(log)">{{ logLvText(log) }}</span>
                <span class="obs-log-ts">{{ log.timestamp || '' }}</span>
                <span class="obs-log-svc" v-if="!selectedLogSvc">{{ log.labels?.app || log.labels?.service || log.labels?.job || '' }}</span>
                <span class="obs-log-body">{{ log.line || '' }}</span>
              </div>
            </div>
          </div>
          <!-- 日志详情抽屉 -->
          <transition name="slide-up">
            <div v-if="selectedLog" class="obs-detail-drawer">
              <div class="obs-dd-header">
                <span>日志详情</span>
                <button class="obs-close" @click="selectedLog = null">✕</button>
              </div>
              <pre class="obs-dd-pre">{{ typeof selectedLog === 'object' ? JSON.stringify(selectedLog, null, 2) : selectedLog }}</pre>
            </div>
          </transition>
        </div>
      </template>

      <!-- ─────────── 查高级 ─────────── -->
      <template v-if="activeTab === 'advanced'">
        <aside class="obs-sidebar">
          <div class="obs-sb-header"><span class="obs-sb-title">查询模板</span></div>
          <div class="obs-sb-list">
            <div v-for="tpl in QUERY_TPLS" :key="tpl.id"
              class="obs-sb-item" :class="{ active: activeTpl === tpl.id }"
              @click="applyTpl(tpl)">
              <span class="obs-sb-dot" :class="'dot-' + tpl.type"></span>
              <div class="obs-sb-info">
                <span class="obs-sb-name">{{ tpl.name }}</span>
                <span class="obs-sb-sub">{{ tpl.type }}</span>
              </div>
            </div>
          </div>
        </aside>
        <div class="obs-main">
          <div class="obs-main-header">
            <span class="obs-main-title">高级查询</span>
            <div class="obs-type-tabs">
              <button v-for="t in ['LogQL','PromQL']" :key="t"
                class="obs-type-tab" :class="{ active: queryType === t }"
                @click="queryType = t">{{ t }}</button>
            </div>
            <div class="obs-mh-spacer"></div>
            <button class="obs-run-btn" @click="runQuery" :disabled="queryRunning">
              <span v-if="queryRunning" class="spinner" style="width:10px;height:10px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:4px"></span>
              ▶ 执行
            </button>
          </div>
          <div class="obs-query-wrap">
            <textarea v-model="queryText" class="obs-query-editor"
              :placeholder="queryType === 'LogQL' ? '{app=~&quot;.+&quot;} |= &quot;error&quot; | json' : 'rate(http_requests_total[5m])'">
            </textarea>
          </div>
          <div class="obs-result-area">
            <div v-if="queryRunning" class="obs-empty"><div class="spinner"></div><p>查询中...</p></div>
            <div v-else-if="!queryResults.length" class="obs-empty obs-empty-hint">
              <span style="font-size:28px">🔍</span><p>执行查询以查看结果</p>
            </div>
            <div v-else class="obs-result-list">
              <div class="obs-result-header">
                <span>结果</span><span class="obs-result-count">{{ queryResults.length }} 条</span>
              </div>
              <div v-for="(r, i) in queryResults" :key="i" class="obs-result-row">
                <span class="obs-result-idx">{{ i + 1 }}</span>
                <span class="obs-result-ts">{{ r.ts }}</span>
                <span class="obs-result-val">{{ r.value ?? r.line }}</span>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- ─────────── 看发布 ─────────── -->
      <template v-if="activeTab === 'deploy'">
        <aside class="obs-sidebar">
          <div class="obs-sb-header">
            <span class="obs-sb-title">发布列表</span>
            <span class="obs-sb-count">{{ jenkinsJobs.length }}</span>
            <button class="obs-sb-refresh" @click="loadJobs" :disabled="loadingJobs">↻</button>
          </div>
          <div class="obs-sb-search">
            <select v-model="jenkinsInstId" class="obs-sb-input obs-sb-select" @change="loadJobs">
              <option value="">选择实例</option>
              <option v-for="inst in jenkinsInsts" :key="inst.id" :value="inst.id">{{ inst.name }}</option>
            </select>
          </div>
          <div class="obs-sb-list">
            <div v-if="loadingJobs" class="obs-sb-loading"><div class="spinner" style="width:14px;height:14px;border-width:2px"></div></div>
            <div v-for="job in filteredJobs" :key="job.name"
              class="obs-sb-item obs-sb-job" :class="{ active: selectedJob?.name === job.name }"
              @click="selectJob(job)">
              <span class="obs-sb-dot" :class="jobDotClass(job)"></span>
              <div class="obs-sb-info">
                <span class="obs-sb-name">{{ job.name.split('/').pop() }}</span>
                <span class="obs-sb-sub" v-if="job.name.includes('/')">{{ job.name.split('/').slice(0,-1).join('/') }}</span>
              </div>
              <span class="obs-job-dur" v-if="job.lastBuild?.duration">
                {{ Math.round(job.lastBuild.duration / 1000) }}s
              </span>
            </div>
          </div>
        </aside>
        <div class="obs-main">
          <div v-if="!selectedJob" class="obs-empty obs-empty-full">
            <span style="font-size:36px">🚀</span><p>选择左侧 Job 查看构建详情</p>
          </div>
          <template v-else>
            <!-- Trace 风格 Header -->
            <div class="obs-trace-header">
              <div class="obs-th-title-row">
                <span class="obs-th-brand">Jenkins</span>
                <span class="obs-th-ep">{{ selectedJob.name }}</span>
                <span class="obs-th-badge" :class="buildResultClass">{{ buildResultText }}</span>
                <button class="obs-outline-btn" style="margin-left:auto" @click="loadBuildHistory" :disabled="loadingHistory">↻ 刷新</button>
              </div>
              <div class="obs-th-meta">
                <span>实例: {{ jenkinsInstName }}</span>
                <span v-if="buildDetail">构建时间: {{ formatTs(buildDetail.timestamp) }}</span>
              </div>
              <!-- 统计卡片 -->
              <div class="obs-th-stats">
                <div class="obs-ths-item">
                  <span class="obs-ths-val">{{ buildDetail ? Math.round((buildDetail.duration||0)/1000) + 's' : '--' }}</span>
                  <span class="obs-ths-label">Duration</span>
                </div>
                <div class="obs-ths-div"></div>
                <div class="obs-ths-item">
                  <span class="obs-ths-val">#{{ buildDetail?.number ?? buildNum ?? '—' }}</span>
                  <span class="obs-ths-label">Build</span>
                </div>
                <div class="obs-ths-div"></div>
                <div class="obs-ths-item">
                  <span class="obs-ths-val">{{ buildHistory.length }}</span>
                  <span class="obs-ths-label">Records</span>
                </div>
                <div class="obs-ths-div"></div>
                <div class="obs-ths-item">
                  <span class="obs-ths-val" :class="buildDetail?.result === 'FAILURE' ? 'val-err' : buildDetail?.result === 'SUCCESS' ? 'val-ok' : ''">
                    {{ buildDetail?.result ?? '—' }}
                  </span>
                  <span class="obs-ths-label">Result</span>
                </div>
              </div>
            </div>

            <!-- 主体：左右分栏（构建列表 + 日志详情）-->
            <div class="obs-build-body">

              <!-- 左：最近构建列表（类比 Trace 列表） -->
              <div class="obs-build-list-panel">
                <div class="obs-wf-col-header">
                  <span class="obs-col-left">最近构建</span>
                  <span class="obs-col-right">{{ buildHistory.length }} 条</span>
                </div>
                <div v-if="loadingHistory" class="obs-empty-sm" style="padding:20px">
                  <div class="spinner" style="width:14px;height:14px;border-width:2px"></div>
                </div>
                <div v-else-if="!buildHistory.length" class="obs-empty" style="padding:20px;font-size:12px">
                  暂无构建记录
                </div>
                <div v-else class="obs-build-list">
                  <div v-for="b in buildHistory" :key="b.number"
                    class="obs-build-row"
                    :class="[buildRowClass(b), { active: buildNum === b.number }]"
                    @click="selectBuild(b)">
                    <!-- 左侧：状态 + 编号 -->
                    <div class="obs-br-info">
                      <span class="obs-br-dot" :class="buildDotClass(b)"></span>
                      <span class="obs-br-num">#{{ b.number }}</span>
                      <span class="obs-br-result" :class="buildBadgeClass(b)">{{ b.result || (b.building ? 'RUNNING' : '—') }}</span>
                    </div>
                    <!-- 中间：耗时瀑布条（类比 Span bar） -->
                    <div class="obs-br-timeline">
                      <div class="obs-br-bar" :class="buildDotClass(b)"
                        :style="{ width: buildBarWidth(b) + '%' }">
                      </div>
                      <span class="obs-br-dur">{{ b.duration ? Math.round(b.duration/1000) + 's' : '—' }}</span>
                    </div>
                    <!-- 右侧：时间 -->
                    <span class="obs-br-ts">{{ formatBuildTs(b.timestamp) }}</span>
                  </div>
                </div>
              </div>

              <!-- 右：构建日志 -->
              <div class="obs-build-log-panel">
                <div class="obs-wf-col-header">
                  <span class="obs-col-left">
                    {{ buildDetail ? 'Build #' + buildDetail.number + ' 控制台输出' : '控制台输出' }}
                  </span>
                  <span class="obs-col-right">{{ buildLog ? buildLog.split('\n').length + ' 行' : '' }}</span>
                  <button class="obs-icon-btn" style="margin-left:8px" @click="loadBuildLog" :disabled="!buildNum || loadingBuild">↻</button>
                </div>
                <div v-if="loadingBuild" class="obs-empty" style="flex:1">
                  <div class="spinner"></div><p>加载中...</p>
                </div>
                <div v-else-if="!buildNum" class="obs-empty obs-empty-hint" style="flex:1">
                  <span style="font-size:28px">📋</span><p>点击左侧构建记录查看日志</p>
                </div>
                <pre v-else class="obs-build-log">{{ buildLog || '暂无日志' }}</pre>
              </div>

            </div>
          </template>
        </div>
      </template>

      <!-- ─────────── 看监控 ─────────── -->
      <template v-if="activeTab === 'monitor'">
        <aside class="obs-sidebar">
          <div class="obs-sb-header">
            <span class="obs-sb-title">服务列表</span>
            <button class="obs-sb-refresh" @click="loadMonitorSvcs">↻</button>
          </div>
          <div class="obs-sb-search">
            <input v-model="monitorSearch" class="obs-sb-input" placeholder="搜索服务..." />
          </div>
          <div class="obs-sb-list">
            <div v-if="loadingMonitorSvcs" class="obs-sb-loading"><div class="spinner" style="width:14px;height:14px;border-width:2px"></div></div>
            <div v-for="svc in filteredMonitorSvcs" :key="svc.id"
              class="obs-sb-item" :class="{ active: selectedMonitorSvc?.id === svc.id }"
              @click="selectMonitorSvc(svc)">
              <span class="obs-sb-dot dot-svc"></span>
              <div class="obs-sb-info">
                <span class="obs-sb-name">{{ svc.name }}</span>
                <span class="obs-sb-sub">{{ svc.group || '默认' }}</span>
              </div>
            </div>
          </div>
        </aside>
        <div class="obs-main">
          <div v-if="!selectedMonitorSvc" class="obs-empty obs-empty-full">
            <span style="font-size:36px">📊</span><p>选择左侧服务查看指标</p>
          </div>
          <template v-else>
            <!-- 类 Trace header -->
            <div class="obs-trace-header">
              <div class="obs-th-title-row">
                <span class="obs-th-brand">SkyWalking</span>
                <span class="obs-th-ep">{{ selectedMonitorSvc.name }}</span>
              </div>
              <div class="obs-th-meta"><span>Group: {{ selectedMonitorSvc.group || '默认' }}</span></div>
              <div class="obs-th-stats">
                <div class="obs-ths-item">
                  <span class="obs-ths-val">{{ monAvgResp }}</span>
                  <span class="obs-ths-label">Avg ms</span>
                </div>
                <div class="obs-ths-div"></div>
                <div class="obs-ths-item">
                  <span class="obs-ths-val">{{ monAvgTp }}</span>
                  <span class="obs-ths-label">CPM</span>
                </div>
                <div class="obs-ths-div"></div>
                <div class="obs-ths-item">
                  <span class="obs-ths-val" :class="monAvgErr > 5 ? 'val-err' : ''">{{ monAvgErr }}%</span>
                  <span class="obs-ths-label">Error</span>
                </div>
              </div>
            </div>
            <div class="obs-content-area obs-metrics-area">
              <div v-if="loadingMetrics" class="obs-empty"><div class="spinner"></div></div>
              <div v-else class="obs-metrics-grid">
                <div class="obs-mc">
                  <div class="obs-mc-title">响应时间 (ms)</div>
                  <svg class="obs-chart" viewBox="0 0 300 60" preserveAspectRatio="none">
                    <polygon :points="chartArea(monitorMetrics?.resp_time, 300, 60)" fill="var(--accent)" opacity=".12"/>
                    <polyline :points="chartLine(monitorMetrics?.resp_time, 300, 60)" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
                  </svg>
                </div>
                <div class="obs-mc">
                  <div class="obs-mc-title">吞吐量 (CPM)</div>
                  <svg class="obs-chart" viewBox="0 0 300 60" preserveAspectRatio="none">
                    <polygon :points="chartArea(monitorMetrics?.throughput, 300, 60)" fill="#3fb950" opacity=".12"/>
                    <polyline :points="chartLine(monitorMetrics?.throughput, 300, 60)" fill="none" stroke="#3fb950" stroke-width="1.5"/>
                  </svg>
                </div>
                <div class="obs-mc">
                  <div class="obs-mc-title">错误率 (%)</div>
                  <svg class="obs-chart" viewBox="0 0 300 60" preserveAspectRatio="none">
                    <polygon :points="chartArea(monitorMetrics?.error_rate, 300, 60)" fill="var(--error)" opacity=".12"/>
                    <polyline :points="chartLine(monitorMetrics?.error_rate, 300, 60)" fill="none" stroke="var(--error)" stroke-width="1.5"/>
                  </svg>
                </div>
              </div>
              <!-- 慢接口 TopN（类比 Span 列表） -->
              <div class="obs-wf-col-header" style="margin-top:12px">
                <span class="obs-col-left">慢接口 Top 20</span>
                <button class="obs-icon-btn" @click="loadTopN" style="margin-left:auto">↻</button>
              </div>
              <div v-if="loadingTopN" class="obs-empty-sm"><div class="spinner" style="width:14px;height:14px;border-width:2px"></div></div>
              <table v-else-if="endpointTopN.length" class="obs-topn-table">
                <thead><tr><th>#</th><th>接口</th><th>平均耗时</th><th>成功率</th></tr></thead>
                <tbody>
                  <tr v-for="(ep, i) in endpointTopN" :key="ep.name">
                    <td class="obs-rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</td>
                    <td class="obs-ep-name">{{ ep.name }}</td>
                    <td :class="ep.avg_ms > 1000 ? 'val-err' : ep.avg_ms > 300 ? 'val-warn' : 'val-ok'">{{ ep.avg_ms }} ms</td>
                    <td :class="ep.sla < 90 ? 'val-err' : ep.sla < 99 ? 'val-warn' : 'val-ok'">{{ ep.sla }}%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </template>

      <!-- ─────────── 原生平台 ─────────── -->
      <template v-if="activeTab === 'native'">
        <div class="obs-native-wrap">
          <div class="obs-native-title">原生平台入口</div>
          <div class="obs-native-grid">
            <a v-for="p in nativePlatforms" :key="p.id"
              :href="p.url || '#'" :target="p.url ? '_blank' : ''"
              class="obs-native-card" :class="{ 'card-disabled': !p.url }">
              <div class="obs-nc-icon">{{ p.icon }}</div>
              <div class="obs-nc-name">{{ p.name }}</div>
              <div class="obs-nc-desc">{{ p.desc }}</div>
              <div class="obs-nc-url">{{ p.url || '未配置' }}</div>
              <div class="obs-nc-arrow" v-if="p.url">→ 打开</div>
              <div class="obs-nc-arrow obs-nc-config" v-else>⚙ 去配置</div>
            </a>
          </div>
        </div>
      </template>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api/index.js'

// ── 常量 ──────────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'logs',     icon: '📋', label: '查日志' },
  { id: 'advanced', icon: '🔍', label: '查高级' },
  { id: 'deploy',   icon: '🚀', label: '看发布' },
  { id: 'monitor',  icon: '📊', label: '看监控' },
  { id: 'native',   icon: '🔗', label: '原生平台' },
]

const TIME_PRESETS = [
  { label: '15分钟', v: 0.25 },
  { label: '1小时',  v: 1 },
  { label: '3小时',  v: 3 },
  { label: '6小时',  v: 6 },
  { label: '1天',    v: 24 },
  { label: '3天',    v: 72 },
  { label: '7天',    v: 168 },
]

const QUERY_TPLS = [
  { id: 1, name: '错误日志',      type: 'LogQL',   query: '{app=~".+"} |= "error" | json' },
  { id: 2, name: '慢请求',        type: 'LogQL',   query: '{app=~".+"} | json | duration > 1s' },
  { id: 3, name: '服务请求率',    type: 'PromQL',  query: 'rate(http_requests_total[5m])' },
  { id: 4, name: '接口错误率',    type: 'PromQL',  query: 'rate(http_requests_total{status=~"5.."}[5m])' },
  { id: 5, name: 'JVM 堆内存',   type: 'PromQL',  query: 'jvm_memory_used_bytes{area="heap"}' },
  { id: 6, name: 'DB 慢查询',    type: 'LogQL',   query: '{app=~".+"} |= "slow query" | json' },
]

// ── 顶栏状态 ──────────────────────────────────────────────────────────────────
const activeTab      = ref('logs')
const datasource     = ref('loki')
const selectedService= ref('')
const serviceOptions = ref([])
const statusFilter   = ref('')
const timePreset     = ref(1)
const customStart    = ref('')
const customEnd      = ref('')
const showTimePicker = ref(false)
const customTimeActive = ref(false)

const totalCount   = computed(() => {
  if (activeTab.value === 'logs')   return logLines.value.length
  if (activeTab.value === 'deploy') return jenkinsJobs.value.length
  if (activeTab.value === 'monitor') return monitorSvcs.value.length
  return 0
})
const errorCount   = computed(() => {
  if (activeTab.value === 'logs')   return logLines.value.filter(l => isErrorLog(l)).length
  if (activeTab.value === 'deploy') return jenkinsJobs.value.filter(j => j.lastBuild?.result === 'FAILURE').length
  return 0
})
const successCount = computed(() => {
  if (activeTab.value === 'deploy') return jenkinsJobs.value.filter(j => j.lastBuild?.result === 'SUCCESS').length
  return 0
})
const runningCount = computed(() => {
  if (activeTab.value === 'deploy') return jenkinsJobs.value.filter(j => j.color === 'blue_anime' || j.lastBuild?.building).length
  return 0
})

const timeLabel = computed(() => {
  if (customTimeActive.value) return `${customStart.value.slice(0,16)} ~ ${customEnd.value.slice(0,16)}`
  const p = TIME_PRESETS.find(x => x.v === timePreset.value)
  return p ? `最近 ${p.label}` : '最近 1小时'
})

function toggleTimePicker() { showTimePicker.value = !showTimePicker.value }

function applyPreset(p) {
  timePreset.value = p.v
  customTimeActive.value = false
  showTimePicker.value = false
  onFilterChange()
}

function applyCustomTime() {
  if (!customStart.value || !customEnd.value) return
  customTimeActive.value = true
  showTimePicker.value = false
  onFilterChange()
}

const timeParams = computed(() => {
  if (customTimeActive.value) {
    return { start_time: customStart.value, end_time: customEnd.value }
  }
  return { hours: timePreset.value }
})

// ── 查日志 ────────────────────────────────────────────────────────────────────
const logLines       = ref([])
const loadingLogs    = ref(false)
const logSearch      = ref('')
const logKeyword     = ref('')
const logLevel       = ref('')
const selectedLogSvc = ref('')
const selectedLog    = ref(null)

const logServices = computed(() => {
  const set = new Set()
  logLines.value.forEach(l => {
    const s = l.labels?.app || l.labels?.service || l.labels?.job || ''
    if (s) set.add(s)
  })
  return [...set].sort()
})
const filteredLogServices = computed(() =>
  logSearch.value ? logServices.value.filter(s => s.includes(logSearch.value)) : logServices.value
)
const logServiceCount = computed(() => {
  const map = {}
  logLines.value.forEach(l => {
    const s = l.labels?.app || l.labels?.service || l.labels?.job || ''
    if (s) map[s] = (map[s] || 0) + 1
  })
  return map
})
const filteredLogs = computed(() => {
  let list = logLines.value
  if (selectedLogSvc.value)
    list = list.filter(l => (l.labels?.app || l.labels?.service || l.labels?.job || '') === selectedLogSvc.value)
  if (statusFilter.value === 'error')
    list = list.filter(l => isErrorLog(l))
  if (logKeyword.value)
    list = list.filter(l => (l.line || l.msg || l.message || '').toLowerCase().includes(logKeyword.value.toLowerCase()))
  return list
})

function isErrorLog(l) {
  const line = (l.line || '').toLowerCase()
  const lv   = (l.labels?.level || l.labels?.severity || '').toLowerCase()
  return lv === 'error' || line.includes('error') || line.includes('exception')
}
function logRowClass(l)  { return isErrorLog(l) ? 'row-err' : '' }
function logLvClass(l)   {
  const lv = (l.labels?.level || '').toLowerCase()
  if (lv === 'error' || isErrorLog(l)) return 'lv-err'
  if (lv === 'warn') return 'lv-warn'
  return 'lv-info'
}
function logLvText(l) {
  const lv = (l.labels?.level || l.labels?.severity || '').toUpperCase()
  if (lv) return lv.slice(0, 4)
  return isErrorLog(l) ? 'ERRO' : 'INFO'
}

async function loadLogs() {
  loadingLogs.value = true
  try {
    const params = {
      ...timeParams.value,
      limit: 500,
      ...(selectedService.value ? { service: selectedService.value } : {}),
      ...(logLevel.value ? { level: logLevel.value } : {}),
    }
    const r = await api.getLogs(params)
    // 后端返回 {data: [...], total, has_more}
    logLines.value = r?.data || []
  } catch {
    logLines.value = []
  } finally {
    loadingLogs.value = false
  }
  // 同步服务列表到顶栏过滤器
  if (!serviceOptions.value.length) {
    try {
      const svcs = await api.getServices()
      serviceOptions.value = (svcs || []).map(s => s.service || s.name || s).filter(Boolean)
    } catch {}
  }
}

function selectLogSvc(svc) {
  selectedLogSvc.value = selectedLogSvc.value === svc ? '' : svc
}

// ── 查高级 ────────────────────────────────────────────────────────────────────
const queryType    = ref('LogQL')
const queryText    = ref('')
const queryRunning = ref(false)
const queryResults = ref([])
const activeTpl    = ref(null)

function applyTpl(tpl) {
  activeTpl.value  = tpl.id
  queryType.value  = tpl.type
  queryText.value  = tpl.query
}

async function runQuery() {
  if (!queryText.value.trim()) return
  queryRunning.value = true
  queryResults.value = []
  try {
    const r = await api.getLogs({ keyword: queryText.value, limit: 200, ...timeParams.value })
    const raw = r?.data || []
    queryResults.value = raw.map(l => ({
      ts:   l.timestamp || '',
      line: l.line || '',
    }))
  } catch (e) {
    queryResults.value = [{ ts: '', line: '查询失败: ' + (e?.message || e) }]
  } finally {
    queryRunning.value = false
  }
}

// ── 看发布 ────────────────────────────────────────────────────────────────────
const jenkinsInsts   = ref([])
const jenkinsInstId  = ref('')
const jenkinsJobs    = ref([])
const loadingJobs    = ref(false)
const selectedJob    = ref(null)
const buildNum       = ref(null)
const buildDetail    = ref(null)
const buildLog       = ref('')
const loadingBuild   = ref(false)
const buildHistory   = ref([])
const loadingHistory = ref(false)

const jenkinsInstName = computed(() =>
  jenkinsInsts.value.find(i => i.id === jenkinsInstId.value)?.name || ''
)
const filteredJobs = computed(() => {
  let list = jenkinsJobs.value
  if (statusFilter.value === 'error')   list = list.filter(j => j.lastBuild?.result === 'FAILURE')
  if (statusFilter.value === 'success') list = list.filter(j => j.lastBuild?.result === 'SUCCESS')
  if (statusFilter.value === 'running') list = list.filter(j => j.lastBuild?.building)
  return list
})
const buildResultClass = computed(() => {
  const r = buildDetail.value?.result
  if (!r) return ''
  return r === 'SUCCESS' ? 'badge-ok' : r === 'FAILURE' ? 'badge-err' : 'badge-run'
})
const buildResultText = computed(() => buildDetail.value?.result || (buildDetail.value ? 'RUNNING' : ''))

function jobDotClass(job) {
  const r = job.lastBuild?.result
  const c = job.color || ''
  if (c.includes('_anime') || job.lastBuild?.building) return 'dot-run'
  if (r === 'SUCCESS' || c === 'blue') return 'dot-ok'
  if (r === 'FAILURE' || c === 'red')  return 'dot-err'
  return 'dot-none'
}
function jobStatusText(job) {
  const r = job.lastBuild?.result
  if (!r) return job.color?.includes('_anime') ? 'RUNNING' : 'NONE'
  return r
}

async function loadJenkinsInsts() {
  try {
    const r = await api.jenkinsListInstances()
    jenkinsInsts.value = r?.data || []
    if (!jenkinsInstId.value && jenkinsInsts.value.length)
      jenkinsInstId.value = jenkinsInsts.value[0].id
    await loadJobs()
  } catch { jenkinsInsts.value = [] }
}

async function loadJobs() {
  if (!jenkinsInstId.value) return
  loadingJobs.value = true
  try {
    const r = await api.jenkinsGetJobs(jenkinsInstId.value)
    jenkinsJobs.value = r?.data || []
  } catch { jenkinsJobs.value = [] }
  finally { loadingJobs.value = false }
}

const maxBuildDuration = computed(() =>
  Math.max(...buildHistory.value.map(b => b.duration || 0), 1)
)

function buildBarWidth(b) {
  return Math.max(3, ((b.duration || 0) / maxBuildDuration.value) * 100)
}
function buildDotClass(b) {
  if (b.building)              return 'dot-run'
  if (b.result === 'SUCCESS')  return 'dot-ok'
  if (b.result === 'FAILURE')  return 'dot-err'
  return 'dot-none'
}
function buildRowClass(b) {
  if (b.result === 'FAILURE') return 'row-err'
  if (b.building)             return 'row-run'
  return ''
}
function buildBadgeClass(b) {
  if (b.building)              return 'badge-run'
  if (b.result === 'SUCCESS')  return 'badge-ok'
  if (b.result === 'FAILURE')  return 'badge-err'
  return ''
}
function formatBuildTs(ts) {
  if (!ts) return ''
  const d = new Date(Number(ts))
  const pad = x => String(x).padStart(2, '0')
  return `${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function selectBuild(b) {
  buildNum.value = b.number
  loadBuildDetail()
}

async function loadBuildHistory() {
  if (!selectedJob.value || !jenkinsInstId.value) return
  loadingHistory.value = true
  try {
    const r = await api.jenkinsGetJobBuilds(jenkinsInstId.value, selectedJob.value.name, 20)
    buildHistory.value = r?.data || []
  } catch {
    buildHistory.value = []
  } finally {
    loadingHistory.value = false
  }
}

function selectJob(job) {
  selectedJob.value = job
  buildDetail.value = null
  buildLog.value    = ''
  buildNum.value    = null
  buildHistory.value = []
  loadBuildHistory()
}

async function loadBuildDetail() {
  if (!selectedJob.value || !buildNum.value) return
  loadingBuild.value = true
  try {
    buildDetail.value = await api.jenkinsGetBuildInfo(jenkinsInstId.value, selectedJob.value.name, buildNum.value)
    await loadBuildLog()
  } catch { buildDetail.value = null }
  finally { loadingBuild.value = false }
}

async function loadBuildLog() {
  if (!selectedJob.value || !buildNum.value) return
  try {
    const r = await api.jenkinsGetBuildLogs(jenkinsInstId.value, selectedJob.value.name, buildNum.value, 300)
    buildLog.value = r?.log || ''
  } catch { buildLog.value = '' }
}

// ── 看监控 ────────────────────────────────────────────────────────────────────
const monitorSvcs        = ref([])
const loadingMonitorSvcs = ref(false)
const monitorSearch      = ref('')
const selectedMonitorSvc = ref(null)
const monitorMetrics     = ref(null)
const loadingMetrics     = ref(false)
const endpointTopN       = ref([])
const loadingTopN        = ref(false)

const filteredMonitorSvcs = computed(() =>
  monitorSearch.value
    ? monitorSvcs.value.filter(s => s.name.toLowerCase().includes(monitorSearch.value.toLowerCase()))
    : monitorSvcs.value
)

function metricAvg(arr) {
  const vals = (arr || []).map(v => typeof v === 'object' ? (v.value ?? 0) : v).filter(v => v != null)
  if (!vals.length) return 0
  return +(vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(1)
}
const monAvgResp = computed(() => metricAvg(monitorMetrics.value?.resp_time))
const monAvgTp   = computed(() => metricAvg(monitorMetrics.value?.throughput))
const monAvgErr  = computed(() => metricAvg(monitorMetrics.value?.error_rate))

function chartLine(arr, w, h) {
  const vals = (arr || []).map(v => typeof v === 'object' ? (v.value ?? 0) : v)
  if (vals.length < 2) return ''
  const max = Math.max(...vals, 1)
  const pad = 4
  return vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * w
    const y = h - pad - ((v / max) * (h - pad * 2))
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}
function chartArea(arr, w, h) {
  const line = chartLine(arr, w, h)
  if (!line) return ''
  return `0,${h} ${line} ${w},${h}`
}

async function loadMonitorSvcs() {
  loadingMonitorSvcs.value = true
  try {
    monitorSvcs.value = await api.swGetServices(timeParams.value)
  } catch { monitorSvcs.value = [] }
  finally { loadingMonitorSvcs.value = false }
}

async function selectMonitorSvc(svc) {
  selectedMonitorSvc.value = svc
  loadingMetrics.value = true
  try {
    monitorMetrics.value = await api.swGetMetrics({ service_name: svc.name, ...timeParams.value })
  } catch { monitorMetrics.value = null }
  finally { loadingMetrics.value = false }
  loadTopN()
}

async function loadTopN() {
  loadingTopN.value = true
  try {
    endpointTopN.value = await api.swGetEndpointTopN({ ...timeParams.value, top_n: 20 })
  } catch { endpointTopN.value = [] }
  finally { loadingTopN.value = false }
}

// ── 原生平台 ──────────────────────────────────────────────────────────────────
const nativePlatforms = ref([
  { id: 'skywalking', icon: '🔭', name: 'SkyWalking',  desc: 'APM 链路追踪', url: '' },
  { id: 'grafana',    icon: '📈', name: 'Grafana',     desc: '指标可视化',   url: '' },
  { id: 'loki',       icon: '📋', name: 'Loki',        desc: '日志聚合',     url: '' },
  { id: 'prometheus', icon: '🔥', name: 'Prometheus',  desc: '指标采集',     url: '' },
  { id: 'jenkins',    icon: '⚙️', name: 'Jenkins',     desc: 'CI/CD 发布',   url: '' },
  { id: 'k8s',        icon: '☸️', name: 'Kubernetes',  desc: '容器编排',     url: '' },
])

async function loadNativePlatformUrls() {
  try {
    const s = await api.getSettings()
    // settings 接口返回扁平对象
    const mapping = {
      skywalking: s?.skywalking_oap_url || '',
      grafana:    s?.grafana_url        || '',
      loki:       s?.loki_url           || '',
      prometheus: s?.prometheus_url     || '',
    }
    nativePlatforms.value = nativePlatforms.value.map(p => ({
      ...p, url: mapping[p.id] || p.url,
    }))
  } catch {}
  // Jenkins URL 从已加载实例取
  if (!jenkinsInsts.value.length) {
    try {
      const r = await api.jenkinsListInstances()
      jenkinsInsts.value = r?.data || []
    } catch {}
  }
  if (jenkinsInsts.value.length) {
    const def = jenkinsInsts.value.find(i => i.default) || jenkinsInsts.value[0]
    nativePlatforms.value = nativePlatforms.value.map(p =>
      p.id === 'jenkins' ? { ...p, url: def?.url || '' } : p
    )
  }
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function formatTs(ts) {
  if (!ts) return ''
  const n = Number(ts)
  const d = new Date(n || ts)
  if (isNaN(d)) return String(ts)
  const pad = x => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function onDatasourceChange() { onFilterChange() }
function onServiceChange()    { onFilterChange() }
function onFilterChange() {
  if (activeTab.value === 'logs')    loadLogs()
  if (activeTab.value === 'monitor') loadMonitorSvcs()
  if (activeTab.value === 'deploy')  loadJobs()
}

function switchTab(id) {
  activeTab.value = id
  if (id === 'logs'    && !logLines.value.length)      loadLogs()
  if (id === 'deploy'  && !jenkinsInsts.value.length)  loadJenkinsInsts()
  if (id === 'monitor' && !monitorSvcs.value.length)   loadMonitorSvcs()
  if (id === 'native')                                 loadNativePlatformUrls()
}

// ── 初始化 ────────────────────────────────────────────────────────────────────
onMounted(async () => {
  await loadLogs()
  await loadJenkinsInsts()
})
</script>

<style scoped>
/* ══ 布局 ══ */
.obs-layout {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
  background: var(--bg-base);
}

/* ══ 顶栏 ══ */
.obs-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 14px;
  height: 46px; flex-shrink: 0;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  gap: 12px; overflow: hidden;
}
.obs-topbar-filters {
  display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; overflow: hidden;
}

/* 过滤 chip */
.obs-filter-chip {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 5px;
  background: var(--bg-input); border: 1px solid var(--border);
  font-size: 12px; cursor: pointer; white-space: nowrap; flex-shrink: 0;
  position: relative;
}
.obs-fc-label { color: var(--text-muted); font-size: 11px; }
.obs-fc-val   { color: var(--text-primary); }
.obs-fc-arrow { color: var(--text-muted); font-size: 10px; }
.obs-fc-select {
  background: transparent; border: none; outline: none;
  color: var(--text-primary); font-size: 12px; cursor: pointer;
  padding: 0; max-width: 90px;
}
.obs-fc-select-sm { max-width: 80px; }
.obs-filter-time { cursor: pointer; }

/* 时间下拉 */
.obs-time-dropdown {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 200;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px; width: 320px;
  box-shadow: 0 6px 24px rgba(0,0,0,.4);
}
.obs-time-presets { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.obs-tp-btn {
  padding: 3px 8px; font-size: 11px; border-radius: 4px; cursor: pointer;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-secondary); transition: all .1s;
}
.obs-tp-btn:hover, .obs-tp-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.obs-time-custom { display: flex; align-items: center; gap: 6px; }
.obs-time-input {
  flex: 1; padding: 4px 6px; font-size: 11px; border-radius: 4px;
  border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary);
}
.obs-time-sep { color: var(--text-muted); font-size: 11px; }
.obs-apply-btn {
  padding: 4px 10px; font-size: 11px; border-radius: 4px; cursor: pointer;
  background: var(--accent); border: none; color: #fff;
}

/* 统计 chips */
.obs-stat-chips { display: flex; gap: 5px; align-items: center; }
.obs-stat-chip {
  padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600;
}
.chip-total { background: rgba(56,139,253,.12); color: var(--accent); }
.chip-err   { background: rgba(248,81,73,.12);  color: var(--error); }
.chip-ok    { background: rgba(63,185,80,.12);  color: #3fb950; }
.chip-run   { background: rgba(210,153,34,.12); color: var(--warning); }

/* Tab 按钮 */
.obs-tabs { display: flex; gap: 2px; flex-shrink: 0; }
.obs-tab-btn {
  padding: 5px 14px; font-size: 12px; border-radius: 5px; cursor: pointer;
  border: 1px solid transparent; background: transparent;
  color: var(--text-secondary); transition: all .1s; white-space: nowrap;
}
.obs-tab-btn:hover { background: var(--sidebar-hover); color: var(--text-primary); }
.obs-tab-btn.active {
  background: rgba(56,139,253,.12); border-color: rgba(56,139,253,.3);
  color: var(--accent); font-weight: 600;
}

/* ══ 主体 ══ */
.obs-body {
  flex: 1; display: flex; overflow: hidden; min-height: 0;
}

/* ══ 左侧面板 ══ */
.obs-sidebar {
  width: 220px; min-width: 180px; flex-shrink: 0;
  background: var(--bg-card); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
.obs-sb-header {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 12px 6px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.obs-sb-title  { font-size: 12px; font-weight: 600; color: var(--text-secondary); flex: 1; }
.obs-sb-count  { font-size: 11px; color: var(--text-muted); background: var(--bg-input); padding: 1px 6px; border-radius: 8px; }
.obs-sb-refresh {
  padding: 2px 6px; font-size: 12px; border-radius: 4px; cursor: pointer;
  border: 1px solid var(--border); background: transparent; color: var(--text-muted);
}
.obs-sb-refresh:hover { color: var(--text-primary); }
.obs-sb-search { padding: 6px 8px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.obs-sb-input {
  width: 100%; padding: 4px 8px; font-size: 12px; border-radius: 4px;
  border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary);
  box-sizing: border-box;
}
.obs-sb-select { appearance: auto; }
.obs-sb-list   { flex: 1; overflow-y: auto; padding: 4px 0; }
.obs-sb-item {
  display: flex; align-items: center; gap: 7px;
  padding: 6px 12px; cursor: pointer; font-size: 12px;
  transition: background .08s; border-left: 2px solid transparent;
}
.obs-sb-item:hover  { background: var(--sidebar-hover); }
.obs-sb-item.active { background: rgba(56,139,253,.08); border-left-color: var(--accent); }
.obs-sb-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
  background: var(--text-muted);
}
.obs-sb-name  { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary); }
.obs-sb-sub   { font-size: 10px; color: var(--text-muted); }
.obs-sb-badge {
  font-size: 10px; color: var(--text-muted);
  background: var(--bg-input); padding: 1px 5px; border-radius: 8px; flex-shrink: 0;
}
.obs-sb-info  { flex: 1; overflow: hidden; }
.obs-sb-loading { display: flex; justify-content: center; padding: 16px; }
.obs-job-dur  { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }

/* 状态点 */
.dot-ok   { background: #3fb950; }
.dot-err  { background: var(--error); }
.dot-run  { background: var(--warning); animation: pulse 1s infinite; }
.dot-none { background: var(--text-muted); }
.dot-svc  { background: var(--accent); }
.dot-LogQL   { background: var(--accent); }
.dot-PromQL  { background: #3fb950; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

/* ══ 主内容区 ══ */
.obs-main {
  flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0;
}
.obs-main-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 14px; border-bottom: 1px solid var(--border);
  background: var(--bg-card); flex-shrink: 0; flex-wrap: wrap;
}
.obs-main-title { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.obs-main-sub   { font-size: 11px; color: var(--text-muted); }
.obs-mh-spacer  { flex: 1; }
.obs-search-input {
  padding: 4px 10px; font-size: 12px; border-radius: 4px;
  border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary);
  width: 160px;
}
.obs-content-area { flex: 1; overflow-y: auto; }

/* Trace-style 详情 header */
.obs-trace-header {
  padding: 10px 14px 8px; border-bottom: 1px solid var(--border);
  background: var(--bg-card); flex-shrink: 0;
}
.obs-th-title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.obs-th-brand {
  font-size: 11px; font-weight: 600; color: var(--accent);
  background: rgba(56,139,253,.1); border: 1px solid rgba(56,139,253,.2);
  border-radius: 3px; padding: 1px 7px; flex-shrink: 0;
}
.obs-th-ep    { font-size: 13px; font-weight: 600; color: var(--text-primary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.obs-th-badge {
  font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; flex-shrink: 0;
}
.badge-ok  { background: rgba(63,185,80,.15);  color: #3fb950; }
.badge-err { background: rgba(248,81,73,.15);  color: var(--error); }
.badge-run { background: rgba(210,153,34,.15); color: var(--warning); }
.obs-th-meta {
  display: flex; gap: 12px; font-size: 11px; color: var(--text-muted); margin-bottom: 8px;
}
.obs-th-stats {
  display: flex; align-items: center;
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: 6px; width: fit-content; overflow: hidden; margin-bottom: 8px;
}
.obs-ths-item {
  display: flex; flex-direction: column; align-items: center;
  padding: 5px 16px; gap: 1px;
}
.obs-ths-val   { font-size: 15px; font-weight: 700; color: var(--text-primary); line-height: 1; }
.obs-ths-label { font-size: 10px; color: var(--text-muted); white-space: nowrap; }
.obs-ths-div   { width: 1px; height: 32px; background: var(--border); }
.obs-th-actions { display: flex; align-items: center; gap: 8px; }
.obs-build-input {
  width: 90px; padding: 4px 8px; font-size: 12px; border-radius: 4px;
  border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary);
}
.obs-run-btn {
  padding: 4px 12px; font-size: 12px; border-radius: 4px; cursor: pointer;
  background: var(--accent); border: none; color: #fff; font-weight: 600;
}
.obs-run-btn:disabled { opacity: .5; cursor: not-allowed; }
.obs-outline-btn {
  padding: 4px 10px; font-size: 12px; border-radius: 4px; cursor: pointer;
  background: transparent; border: 1px solid var(--border); color: var(--text-secondary);
}
.obs-outline-btn:hover { background: var(--sidebar-hover); }

/* ══ 日志列表 ══ */
.obs-log-list { padding: 0; }
.obs-log-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 5px 14px; border-bottom: 1px solid rgba(255,255,255,.03);
  cursor: pointer; transition: background .06s; font-size: 12px;
}
.obs-log-row:hover { background: var(--sidebar-hover); }
.obs-log-row.row-err { background: rgba(248,81,73,.04); }
.obs-log-lv {
  font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px;
  flex-shrink: 0; width: 34px; text-align: center;
}
.lv-err  { background: rgba(248,81,73,.2);  color: var(--error); }
.lv-warn { background: rgba(210,153,34,.2); color: var(--warning); }
.lv-info { background: rgba(56,139,253,.1); color: var(--text-muted); }
.obs-log-ts  { color: var(--text-muted); font-size: 11px; white-space: nowrap; flex-shrink: 0; }
.obs-log-svc { color: var(--accent); font-size: 11px; flex-shrink: 0; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.obs-log-body { flex: 1; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 日志详情抽屉 */
.obs-detail-drawer {
  flex-shrink: 0; max-height: 280px;
  border-top: 1px solid var(--border); background: var(--bg-input);
  display: flex; flex-direction: column;
}
.obs-dd-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 12px; border-bottom: 1px solid var(--border);
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
}
.obs-close { background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 14px; }
.obs-dd-pre {
  flex: 1; overflow-y: auto; padding: 10px 14px;
  font-size: 11px; color: var(--text-primary); font-family: monospace;
  white-space: pre-wrap; word-break: break-all; margin: 0;
}
.slide-up-enter-active, .slide-up-leave-active { transition: max-height .2s ease; }
.slide-up-enter-from, .slide-up-leave-to { max-height: 0; }

/* ══ 高级查询 ══ */
.obs-type-tabs { display: flex; gap: 2px; }
.obs-type-tab {
  padding: 3px 10px; font-size: 11px; border-radius: 4px; cursor: pointer;
  border: 1px solid var(--border); background: transparent; color: var(--text-secondary);
}
.obs-type-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.obs-query-wrap { padding: 10px 14px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.obs-query-editor {
  width: 100%; height: 90px; padding: 8px 10px; font-size: 12px;
  border-radius: 6px; border: 1px solid var(--border);
  background: var(--bg-input); color: var(--text-primary);
  font-family: monospace; resize: vertical; box-sizing: border-box;
}
.obs-result-area { flex: 1; overflow-y: auto; }
.obs-result-header {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 14px; border-bottom: 1px solid var(--border);
  font-size: 12px; color: var(--text-secondary);
}
.obs-result-count { font-size: 11px; color: var(--text-muted); }
.obs-result-row {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 5px 14px; border-bottom: 1px solid rgba(255,255,255,.03); font-size: 12px;
}
.obs-result-idx { color: var(--text-muted); font-size: 11px; width: 24px; flex-shrink: 0; text-align: right; }
.obs-result-ts  { color: var(--text-muted); font-size: 11px; flex-shrink: 0; white-space: nowrap; }
.obs-result-val { flex: 1; color: var(--text-primary); word-break: break-all; }

/* ══ 构建主体（构建列表 + 日志，左右分栏）══ */
.obs-build-body {
  flex: 1; display: flex; overflow: hidden; min-height: 0;
}
.obs-build-list-panel {
  width: 280px; min-width: 220px; flex-shrink: 0;
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
.obs-build-list { flex: 1; overflow-y: auto; }

/* 构建行（类比 Trace 行） */
.obs-build-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; cursor: pointer;
  border-bottom: 1px solid rgba(255,255,255,.03);
  transition: background .07s;
}
.obs-build-row:hover  { background: var(--sidebar-hover); }
.obs-build-row.active { background: rgba(56,139,253,.08); border-left: 2px solid var(--accent); padding-left: 8px; }
.obs-build-row.row-err { background: rgba(248,81,73,.04); }
.obs-build-row.row-run { background: rgba(210,153,34,.03); }

.obs-br-info {
  display: flex; align-items: center; gap: 5px; flex-shrink: 0; width: 110px;
}
.obs-br-dot  { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.obs-br-num  { font-size: 12px; color: var(--text-primary); font-weight: 600; white-space: nowrap; }
.obs-br-result {
  font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px; flex-shrink: 0;
}
.obs-br-timeline {
  flex: 1; position: relative; height: 18px; overflow: hidden;
}
.obs-br-bar {
  position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  height: 6px; border-radius: 2px; min-width: 3px;
  background: var(--text-muted); transition: width .2s;
}
.obs-br-bar.dot-ok  { background: #3fb950; }
.obs-br-bar.dot-err { background: var(--error); }
.obs-br-bar.dot-run { background: var(--warning); }
.obs-br-dur {
  position: absolute; right: 0; top: 50%; transform: translateY(-50%);
  font-size: 10px; color: var(--text-muted); white-space: nowrap;
}
.obs-br-ts   { font-size: 10px; color: var(--text-muted); white-space: nowrap; flex-shrink: 0; }

.obs-build-log-panel {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}

/* ══ 构建日志（瀑布图风格）══ */
.obs-build-log-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.obs-wf-col-header {
  display: flex; align-items: center;
  padding: 5px 14px; background: var(--bg-card);
  border-bottom: 1px solid var(--border); flex-shrink: 0;
  font-size: 11px; color: var(--text-muted);
}
.obs-col-left  { font-weight: 600; color: var(--text-secondary); }
.obs-col-right { margin-left: auto; }
.obs-build-log {
  flex: 1; overflow-y: auto; padding: 10px 16px;
  font-size: 11px; color: var(--text-primary); font-family: monospace;
  white-space: pre-wrap; word-break: break-all; margin: 0;
  background: var(--bg-base); line-height: 1.6;
}
.obs-icon-btn {
  padding: 2px 7px; font-size: 11px; border-radius: 4px; cursor: pointer;
  border: 1px solid var(--border); background: transparent; color: var(--text-muted);
}
.obs-icon-btn:hover { color: var(--text-primary); }

/* ══ 监控指标 ══ */
.obs-metrics-area { display: flex; flex-direction: column; }
.obs-metrics-grid { display: flex; gap: 10px; padding: 12px 14px; flex-wrap: wrap; }
.obs-mc {
  flex: 1; min-width: 180px; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px;
}
.obs-mc-title { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; }
.obs-chart    { width: 100%; height: 60px; display: block; }
.obs-endpoint-section { padding: 0 14px 14px; }
.obs-section-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); padding: 10px 0 6px; }
.obs-empty-sm { display: flex; justify-content: center; padding: 16px; }
.obs-topn-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.obs-topn-table th {
  text-align: left; padding: 5px 10px; border-bottom: 1px solid var(--border);
  font-size: 11px; color: var(--text-muted); font-weight: 500;
}
.obs-topn-table td { padding: 5px 10px; border-bottom: 1px solid rgba(255,255,255,.04); }
.obs-rank     { color: var(--text-muted); font-size: 11px; width: 28px; }
.rank-top     { color: var(--warning); font-weight: 700; }
.obs-ep-name  { color: var(--text-primary); max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.val-ok   { color: #3fb950; }
.val-warn { color: var(--warning); }
.val-err  { color: var(--error); }

/* ══ 原生平台 ══ */
.obs-native-wrap  { flex: 1; overflow-y: auto; padding: 24px; }
.obs-native-title { font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 16px; }
.obs-native-grid  { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.obs-native-card {
  display: flex; flex-direction: column; gap: 4px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; padding: 18px 16px;
  text-decoration: none; color: inherit;
  transition: border-color .15s, box-shadow .15s; cursor: pointer;
  position: relative;
}
.obs-native-card:hover:not(.card-disabled) {
  border-color: var(--accent); box-shadow: 0 0 0 1px rgba(56,139,253,.2);
}
.card-disabled { opacity: .5; cursor: default; }
.obs-nc-icon { font-size: 28px; margin-bottom: 4px; }
.obs-nc-name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.obs-nc-desc { font-size: 12px; color: var(--text-muted); }
.obs-nc-url  { font-size: 10px; color: var(--accent); font-family: monospace; margin-top: 4px; word-break: break-all; }
.obs-nc-arrow{ position: absolute; bottom: 14px; right: 16px; font-size: 12px; color: var(--accent); }
.obs-nc-config { color: var(--text-muted); }

/* ══ 通用 ══ */
.obs-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; padding: 40px; color: var(--text-muted); font-size: 13px;
}
.obs-empty-full { flex: 1; }
.obs-empty-hint { opacity: .6; }
</style>
