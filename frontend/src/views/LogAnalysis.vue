<template>
  <div class="log-layout">
    <!-- 左侧服务过滤 -->
    <aside class="service-panel">
      <div class="panel-header">
        <span class="panel-title">服务列表</span>
        <!-- 时间模式切换 -->
        <div class="time-mode-tabs">
          <button class="tmode-btn" :class="{ active: timeMode === 'relative' }" @click="timeMode = 'relative'; onTimeModeChange()">快速</button>
          <button class="tmode-btn" :class="{ active: timeMode === 'custom' }" @click="timeMode = 'custom'">自定义</button>
        </div>
        <!-- 相对时间选择 -->
        <select v-if="timeMode === 'relative'" v-model="hours" class="time-select" @change="onParamChange">
          <option value="1">最近 1 小时</option>
          <option value="6">最近 6 小时</option>
          <option value="24">最近 24 小时</option>
          <option value="72">最近 3 天</option>
        </select>
        <!-- 自定义时间范围 -->
        <div v-else class="custom-time-wrap">
          <input type="datetime-local" v-model="customStart" class="dt-input" @change="onCustomTimeChange" title="开始时间" />
          <span class="dt-sep">→</span>
          <input type="datetime-local" v-model="customEnd"   class="dt-input" @change="onCustomTimeChange" title="结束时间" />
        </div>
      </div>

      <div class="svc-list-wrap">
        <div class="svc-item" :class="{ active: selectedService === '' }" @click="selectService('')">
          <span class="svc-dot all"></span>
          <span class="svc-label">全部服务</span>
          <span class="svc-badge">{{ totalErrors }}</span>
        </div>
        <div v-if="loadingSvcs" class="loading-row">
          <div class="spinner" style="width:14px;height:14px;border-width:2px"></div>
        </div>
        <div
          v-for="svc in services" :key="svc.name"
          class="svc-item"
          :class="{ active: selectedService === svc.name }"
          @click="selectService(svc.name)"
        >
          <span class="svc-dot" :class="svc.error_count > 0 ? 'error' : 'ok'"></span>
          <span class="svc-label">{{ svc.name }}</span>
          <span v-if="svc.error_count" class="svc-badge error">{{ svc.error_count }}</span>
        </div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <div class="log-panel">
      <!-- 工具栏 -->
      <div class="log-toolbar">
        <div class="toolbar-left">
          <!-- Tab 切换 -->
          <div class="tab-group">
            <button class="tab-btn" :class="{ active: activeTab === 'logs' }" @click="switchTab('logs')">
              📋 日志流
              <span class="tab-count">{{ logs.length }}</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'templates' }" @click="switchTab('templates')">
              🧩 模板聚合
              <span class="tab-count" v-if="templates.length">{{ templates.length }}</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'trace' }" @click="switchTab('trace')">
              ⏱ 耗时追踪
            </button>
          </div>
        </div>
        <div class="toolbar-right">
          <!-- 关键字搜索（日志流 / 模板聚合 tab 共用） -->
          <div v-if="activeTab !== 'trace'" class="keyword-wrap">
            <span class="kw-icon">🔍</span>
            <input
              v-model="keyword"
              class="kw-input"
              placeholder="关键字过滤..."
              @input="onKeywordInput"
              @keyup.enter="onParamChange"
            />
            <button v-if="keyword" class="kw-clear" @click="clearKeyword">✕</button>
          </div>

          <!-- 日志流专有控件 -->
          <template v-if="activeTab === 'logs'">
            <select v-model="levelFilter" class="time-select" @change="onLevelChange">
              <option value="">全部级别</option>
              <option value="error">ERROR</option>
              <option value="warn">WARN</option>
              <option value="info">INFO</option>
              <option value="debug">DEBUG</option>
            </select>
            <button
              class="btn"
              :class="incidentOnly ? 'btn-incident-active' : 'btn-outline'"
              @click="toggleIncident"
              title="仅显示 ERROR/WARN 及含 error/exception/timeout 等关键字的日志"
            >⚡ 仅事件</button>
            <button class="btn btn-outline" @click="loadLogs" :disabled="loadingLogs">
              <span v-if="loadingLogs" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🔄</span>查询
            </button>
            <button class="btn btn-primary" @click="startAIAnalysis" :disabled="analyzingAI">
              <span v-if="analyzingAI" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🤖</span>AI 分析
            </button>
          </template>
          <!-- 模板聚合专有控件 -->
          <template v-if="activeTab === 'templates'">
            <span class="meta-info" v-if="templateMeta.total_logs">
              采样 {{ templateMeta.total_logs }} 条 → {{ templates.length }} 个模板
            </span>
            <select v-model="tplLevelFilter" class="time-select" @change="loadTemplates">
              <option value="">全量日志</option>
              <option value="error">仅 ERROR</option>
              <option value="warn">仅 WARN</option>
            </select>
            <button class="btn btn-outline" @click="loadTemplates" :disabled="loadingTemplates">
              <span v-if="loadingTemplates" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🔄</span>重新聚类
            </button>
            <button class="btn btn-primary" @click="startTplAIAnalysis" :disabled="analyzingTplAI || loadingTemplates || !templates.length">
              <span v-if="analyzingTplAI" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🤖</span>AI 分析
            </button>
          </template>
        </div>
      </div>

      <!-- AI 分析面板（日志流 tab） -->
      <transition name="fade">
        <div v-if="(aiContent || analyzingAI) && activeTab === 'logs'" class="ai-panel">
          <div class="ai-panel-header">
            <span>🤖 AI 分析结果</span>
            <button class="btn btn-outline btn-xs" @click="aiContent = ''">关闭</button>
          </div>
          <div class="ai-content" v-html="renderedAI"></div>
          <div v-if="analyzingAI" class="ai-typing">
            <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
          </div>
        </div>
      </transition>
      <!-- AI 分析面板（模板聚合 tab） -->
      <transition name="fade">
        <div v-if="(tplAiContent || analyzingTplAI) && activeTab === 'templates'" class="ai-panel">
          <div class="ai-panel-header">
            <span>🤖 模板聚类 AI 分析</span>
            <button class="btn btn-outline btn-xs" @click="tplAiContent = ''">关闭</button>
          </div>
          <div class="ai-content" v-html="renderedTplAI"></div>
          <div v-if="analyzingTplAI" class="ai-typing">
            <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
          </div>
        </div>
      </transition>

      <!-- ── 日志流 ── -->
      <div v-show="activeTab === 'logs'" class="log-container">
        <div v-if="loadingLogs && !filteredLogs.length" class="empty-state">
          <div class="spinner"></div><p>加载日志中...</p>
        </div>
        <div v-else-if="!filteredLogs.length" class="empty-state">
          <span class="icon">📭</span><p>暂无日志数据</p>
        </div>
        <template v-else>
          <!-- 统计栏 -->
          <div class="log-stats-bar">
            <span class="log-stat-item">
              共 <strong>{{ filteredLogs.length }}</strong> 条
              <span v-if="filteredLogs.length !== logs.length" class="log-stat-filtered">（过滤后）</span>
            </span>
            <span class="log-stat-sep">·</span>
            <span v-for="(cnt, lvl) in levelStats" :key="lvl" class="log-stat-item">
              <span class="lvl-dot" :class="'lvl-' + lvl"></span>{{ lvl.toUpperCase() }} {{ cnt }}
            </span>
          </div>
          <!-- 表格 -->
          <div class="log-table-wrap">
            <table class="log-table">
              <colgroup>
                <col style="width:168px">
                <col style="width:72px">
                <col style="width:130px">
                <col>
              </colgroup>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>级别</th>
                  <th>服务</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(log, i) in pagedLogs" :key="i"
                  class="log-row" :class="logRowClass(log.line)"
                  @click="openDetail(log)"
                >
                  <td class="col-ts">{{ log.timestamp }}</td>
                  <td class="col-lvl">
                    <span class="lvl-badge" :class="'lvl-badge-' + extractLevel(log.line)">
                      {{ extractLevel(log.line).toUpperCase() }}
                    </span>
                  </td>
                  <td class="col-svc">{{ log.labels?.app || log.labels?.job || selectedService || '—' }}</td>
                  <td class="col-msg">{{ log.line }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- 分页 -->
          <div class="log-pagination">
            <span class="pg-info">第 {{ currentPage }} / {{ totalPages }} 页，每页 {{ pageSize }} 条</span>
            <div class="pg-btns">
              <button class="pg-btn" :disabled="currentPage <= 1" @click="currentPage = 1">«</button>
              <button class="pg-btn" :disabled="currentPage <= 1" @click="currentPage--">‹</button>
              <span
                v-for="p in pageNumbers" :key="p"
                class="pg-num" :class="{ active: p === currentPage, ellipsis: p === '…' }"
                @click="p !== '…' && (currentPage = p)"
              >{{ p }}</span>
              <button class="pg-btn" :disabled="currentPage >= totalPages" @click="currentPage++">›</button>
              <button class="pg-btn" :disabled="currentPage >= totalPages" @click="currentPage = totalPages">»</button>
            </div>
            <select class="pg-size-sel" v-model.number="pageSize" @change="currentPage = 1">
              <option :value="20">20 条/页</option>
              <option :value="50">50 条/页</option>
              <option :value="100">100 条/页</option>
            </select>
          </div>
        </template>
      </div>

      <!-- 日志详情抽屉 -->
      <transition name="drawer-slide">
        <div v-if="detailLog" class="log-detail-drawer" @click.self="detailLog = null">
          <div class="drawer-panel">
            <div class="drawer-header">
              <span>日志详情</span>
              <button class="drawer-close" @click="detailLog = null">✕</button>
            </div>
            <div class="drawer-body">
              <div class="drawer-row">
                <span class="drawer-label">时间</span>
                <span class="drawer-val">{{ detailLog.timestamp }}</span>
              </div>
              <div class="drawer-row">
                <span class="drawer-label">级别</span>
                <span class="lvl-badge" :class="'lvl-badge-' + extractLevel(detailLog.line)">
                  {{ extractLevel(detailLog.line).toUpperCase() }}
                </span>
              </div>
              <div class="drawer-row">
                <span class="drawer-label">服务</span>
                <span class="drawer-val">{{ detailLog.labels?.app || detailLog.labels?.job || selectedService || '—' }}</span>
              </div>
              <div v-if="detailLog.labels && Object.keys(detailLog.labels).length" class="drawer-row">
                <span class="drawer-label">标签</span>
                <div class="drawer-tags">
                  <span v-for="(v, k) in detailLog.labels" :key="k" class="drawer-tag">{{ k }}=<em>{{ v }}</em></span>
                </div>
              </div>
              <div class="drawer-row drawer-row-full">
                <span class="drawer-label">内容</span>
                <pre class="drawer-content">{{ detailLog.line }}</pre>
              </div>
            </div>
          </div>
        </div>
      </transition>

      <!-- ── 模板聚合 ── -->
      <div v-show="activeTab === 'templates'" class="template-container">
        <div v-if="loadingTemplates" class="empty-state">
          <div class="spinner"></div><p>Drain3 聚类中...</p>
        </div>
        <div v-else-if="tplError" class="empty-state">
          <span class="icon">⚠️</span>
          <p style="color:var(--error)">{{ tplError }}</p>
        </div>
        <div v-else-if="!templates.length" class="empty-state">
          <span class="icon">🧩</span>
          <p>当前条件下暂无日志可聚类<br><small style="color:var(--text-muted)">尝试切换「全量日志」或扩大时间范围</small></p>
        </div>
        <div v-else class="template-list">
          <div v-for="(tpl, i) in templates" :key="tpl.cluster_id" class="tpl-card">
            <!-- 头部：排名 + 计数 + 模板 -->
            <div class="tpl-header">
              <span class="tpl-rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
              <span class="tpl-count badge badge-error">{{ tpl.count }} 条</span>
              <span class="tpl-pct">{{ tplPct(tpl.count) }}%</span>
              <div class="tpl-bar-wrap">
                <div class="tpl-bar" :style="{ width: tplBarW(tpl.count) + '%' }"></div>
              </div>
            </div>
            <!-- 模板字符串 -->
            <div class="tpl-pattern" v-html="highlightWildcard(tpl.template)"></div>
            <!-- 服务分布 -->
            <div class="tpl-services" v-if="tpl.top_services.length">
              <span class="tpl-label">来源：</span>
              <span
                v-for="s in tpl.top_services" :key="s.name"
                class="svc-chip"
              >{{ s.name }}<em>{{ s.count }}</em></span>
            </div>
            <!-- 示例原文（可展开） -->
            <div class="tpl-example" v-if="tpl.example">
              <span class="tpl-label">示例：</span>
              <span class="tpl-example-text">
                <span class="tpl-example-ts">{{ tpl.example_ts }}</span>
                {{ tpl.example }}
              </span>
            </div>
          </div>
        </div>
      </div>
      <!-- ── 耗时追踪 Tab ── -->
      <div v-show="activeTab === 'trace'" class="trace-tab">
        <!-- 查询表单（单行紧凑工具栏） -->
        <div class="trace-form-bar">
          <!-- 追踪值输入 -->
          <div class="trace-input-wrap trace-input-grow">
            <span class="trace-input-icon">🔍</span>
            <input
              v-model="traceValue"
              class="trace-input"
              placeholder="追踪值：traceId、requestId、关键字..."
              @keyup.enter="runTrace"
            />
            <button v-if="traceValue" class="kw-clear" @click="traceValue = ''">✕</button>
          </div>
          <!-- 时间模式 -->
          <div class="time-mode-tabs" style="width:fit-content;flex-shrink:0">
            <button class="tmode-btn" :class="{ active: traceTimeMode === 'relative' }" @click="traceTimeMode = 'relative'">快速</button>
            <button class="tmode-btn" :class="{ active: traceTimeMode === 'custom' }" @click="switchTraceToCustom">自定义</button>
          </div>
          <select v-if="traceTimeMode === 'relative'" v-model="traceHours" class="time-select" style="width:120px;flex-shrink:0">
            <option value="1">最近 1 小时</option>
            <option value="6">最近 6 小时</option>
            <option value="24">最近 24 小时</option>
            <option value="72">最近 3 天</option>
            <option value="168">最近 7 天</option>
          </select>
          <template v-else>
            <input type="datetime-local" v-model="traceStart" class="dt-input" style="width:152px;flex-shrink:0" title="开始时间" />
            <span class="dt-sep" style="flex-shrink:0">→</span>
            <input type="datetime-local" v-model="traceEnd"   class="dt-input" style="width:152px;flex-shrink:0" title="结束时间" />
          </template>
          <!-- 当前服务提示 -->
          <span v-if="selectedService" class="trace-svc-hint" style="flex-shrink:0;font-size:12px;color:var(--text-muted);white-space:nowrap">
            服务: <em style="color:var(--primary)">{{ selectedService }}</em>
          </span>
          <!-- 分析按钮 -->
          <button
            class="btn btn-trace-primary"
            @click="runTrace"
            :disabled="!traceValue || tracingKeyword"
            style="flex-shrink:0"
          >
            <span v-if="tracingKeyword" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>⏱</span>
            开始分析
          </button>
        </div>

        <!-- 结果区 -->
        <div v-if="tracingKeyword" class="empty-state">
          <div class="spinner"></div>
          <p>正在全量扫描日志，计算首末耗时...</p>
          <small style="color:var(--text-muted)">最多扫描 50,000 条匹配日志</small>
        </div>
        <div v-else-if="traceResult" class="trace-result">
          <!-- 未找到 / 请求失败 -->
          <div v-if="!traceResult.found" class="trace-not-found">
            <span class="icon" style="font-size:28px">{{ traceResult._error ? '⚠️' : '🔍' }}</span>
            <p v-if="traceResult._error" style="color:var(--error);font-size:13px">
              请求失败：{{ traceResult._error }}
            </p>
            <p v-else>
              在指定时间范围内未找到包含 <em>{{ traceResult.keyword }}</em> 的日志
            </p>
            <small v-if="!traceResult._error" style="color:var(--text-muted)">
              请检查关键字拼写、时间范围或服务选择是否正确
            </small>
          </div>
          <!-- 找到了：子页签 -->
          <template v-else>
            <!-- 子页签切换栏 -->
            <div class="trace-sub-tabs">
              <button
                class="trace-sub-btn"
                :class="{ active: traceResultTab === 'overview' }"
                @click="traceResultTab = 'overview'"
              >
                ⏱ 耗时概览
              </button>
              <button
                class="trace-sub-btn"
                :class="{ active: traceResultTab === 'logs' }"
                @click="traceResultTab = 'logs'"
              >
                📋 匹配日志
                <span class="trace-sub-badge">
                  <span v-if="loadingTraceLogs" class="spinner" style="width:10px;height:10px;border-width:2px"></span>
                  <span v-else>{{ traceLogs.length }}</span>
                </span>
              </button>
            </div>

            <!-- ── 耗时概览页签 ── -->
            <div v-show="traceResultTab === 'overview'" class="trace-overview">
              <!-- 大耗时数字区 -->
              <div class="trace-hero">
                <div class="trace-hero-label">全链路耗时</div>
                <div class="trace-hero-duration">{{ traceResult.duration_str }}</div>
                <div class="trace-hero-meta">
                  关键字 <em>{{ traceResult.keyword }}</em>
                  · 共匹配 <strong>{{ traceResult.log_count }}</strong> 条日志
                  <span v-if="traceResult.log_count >= 50000" class="trace-limit-hint">（已达扫描上限）</span>
                </div>
              </div>
              <!-- 时间线 -->
              <div class="trace-timeline-card">
                <!-- 首次 -->
                <div class="trace-tl-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-dot dot-first"></div>
                    <div class="trace-tl-connector"></div>
                  </div>
                  <div class="trace-tl-body">
                    <div class="trace-tl-tag">首次出现</div>
                    <div class="trace-tl-ts">{{ traceResult.first_ts }}</div>
                    <span v-if="traceResult.first_service" class="trace-ep-svc">{{ traceResult.first_service }}</span>
                    <div class="trace-tl-log">{{ traceResult.first_log }}</div>
                  </div>
                </div>
                <!-- 耗时标注 -->
                <div class="trace-tl-row dur-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-line"></div>
                  </div>
                  <div class="trace-tl-dur-badge">{{ traceResult.duration_str }}</div>
                </div>
                <!-- 末次 -->
                <div class="trace-tl-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-dot dot-last"></div>
                  </div>
                  <div class="trace-tl-body">
                    <div class="trace-tl-tag">末次出现</div>
                    <div class="trace-tl-ts">{{ traceResult.last_ts }}</div>
                    <span v-if="traceResult.last_service" class="trace-ep-svc">{{ traceResult.last_service }}</span>
                    <div class="trace-tl-log">{{ traceResult.last_log }}</div>
                  </div>
                </div>
              </div>

              <!-- 每条耗时列表 -->
              <div class="trace-spans-card">
                <div class="trace-spans-header">
                  <span>每次出现耗时</span>
                  <span v-if="loadingTraceLogs" class="spinner" style="width:11px;height:11px;border-width:2px;flex-shrink:0"></span>
                  <span v-else class="trace-logs-count">{{ traceLogs.length }} 条</span>
                </div>
                <div v-if="loadingTraceLogs && !traceLogs.length" class="empty-state" style="padding:20px">
                  <div class="spinner"></div><p style="font-size:12px">加载中...</p>
                </div>
                <div v-else class="trace-span-list">
                  <div
                    v-for="(log, i) in traceLogs" :key="i"
                    class="trace-span-row"
                    :class="[logClass(log.line), { expanded: expandedSpans.has(i) }]"
                    @click="toggleSpan(i)"
                  >
                    <div class="trace-span-idx">{{ i + 1 }}</div>
                    <div class="trace-span-elapsed">{{ spanElapsed(log) }}</div>
                    <div class="trace-span-bar-wrap">
                      <div class="trace-span-bar" :style="{ width: spanBarW(log) + '%' }"></div>
                    </div>
                    <div class="trace-span-ts">{{ log.timestamp }}</div>
                    <span v-if="log.labels.app || log.labels.job" class="trace-ep-svc">{{ log.labels.app || log.labels.job }}</span>
                    <div class="trace-span-line">{{ log.line }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- ── 匹配日志页签 ── -->
            <div v-show="traceResultTab === 'logs'" class="trace-log-panel">
              <div class="trace-logs-header">
                <span>匹配日志（按时间升序）</span>
                <span v-if="loadingTraceLogs" class="spinner" style="width:12px;height:12px;border-width:2px;flex-shrink:0"></span>
                <span v-else class="trace-logs-count">{{ traceLogs.length }} 条</span>
                <span v-if="traceLogs.length >= 2000" class="trace-limit-hint" style="margin-left:4px">（仅展示前 2000 条）</span>
              </div>
              <div class="trace-log-list">
                <div v-if="loadingTraceLogs && !traceLogs.length" class="empty-state" style="padding:24px">
                  <div class="spinner"></div><p style="font-size:12px">加载日志列表...</p>
                </div>
                <div
                  v-for="(log, i) in traceLogs" :key="i"
                  class="log-line" :class="logClass(log.line)"
                >
                  <span class="log-ts">{{ log.timestamp }}</span>
                  <span class="log-svc">{{ log.labels.app || log.labels.job || '?' }}</span>
                  <span class="log-text">{{ log.line }}</span>
                </div>
              </div>
            </div>
          </template>
        </div>
        <!-- 初始提示 -->
        <div v-else class="empty-state" style="flex:1">
          <span class="icon" style="font-size:36px">⏱</span>
          <p>输入追踪值并选择时间范围，分析关键字首次到末次出现的耗时</p>
          <small style="color:var(--text-muted)">支持 traceId、requestId、订单号等任意字符串</small>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, streamSSE } from '../api/index.js'

// ── 公共状态 ─────────────────────────────
const services       = ref([])
const selectedService = ref('')
const hours          = ref('1')
const loadingSvcs    = ref(false)
const activeTab      = ref('logs')

// 时间模式：relative（最近N小时） | custom（自定义时间段）
const timeMode    = ref('relative')
const customStart = ref('')
const customEnd   = ref('')

// 关键字搜索
const keyword      = ref('')
let   searchTimer  = null

const totalErrors = computed(() =>
  services.value.reduce((s, v) => s + v.error_count, 0)
)

// 返回今天 00:00 ~ 当前时刻的本地时间字符串（datetime-local 格式）
function todayRange() {
  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  return {
    start: `${date}T00:00`,
    end:   `${date}T${pad(now.getHours())}:${pad(now.getMinutes())}`,
  }
}

// datetime-local 返回本地时间字符串，转成 UTC ISO 再发给后端
function toUtcStr(localStr) {
  if (!localStr) return ''
  return new Date(localStr).toISOString().slice(0, 16)   // "2025-03-25T02:00"
}

// 构建时间参数（relative 或 custom）
function timeParams() {
  if (timeMode.value === 'custom' && customStart.value && customEnd.value) {
    return { start_time: toUtcStr(customStart.value), end_time: toUtcStr(customEnd.value) }
  }
  return { hours: hours.value }
}

// ── 日志流 ───────────────────────────────
const logs         = ref([])
const levelFilter  = ref('')
const loadingLogs  = ref(false)
const analyzingAI  = ref(false)
const aiContent    = ref('')

// 仅事件过滤
const incidentOnly = ref(false)
const INCIDENT_KEYWORDS = ['error', 'exception', 'fail', 'timeout', 'refused', 'panic', 'oom', 'fatal', 'traceback']

// 分页
const currentPage = ref(1)
const pageSize    = ref(50)

// 详情抽屉
const detailLog   = ref(null)

// 提取日志级别
function extractLevel(line) {
  const l = (line || '').toLowerCase()
  if (/\berror\b|exception|fatal|panic|traceback/.test(l)) return 'error'
  if (/\bwarn(ing)?\b/.test(l))                            return 'warn'
  if (/\binfo\b/.test(l))                                  return 'info'
  if (/\bdebug\b/.test(l))                                 return 'debug'
  return 'other'
}

function logRowClass(line) {
  const lvl = extractLevel(line)
  if (lvl === 'error') return 'row-error'
  if (lvl === 'warn')  return 'row-warn'
  return ''
}

const filteredLogs = computed(() => {
  let list = logs.value
  // 前端 incidentOnly 过滤（已从后端拿全量，在前端二次过滤）
  if (incidentOnly.value) {
    list = list.filter(log => {
      const l = (log.line || '').toLowerCase()
      return /\berror\b|exception|fatal|panic|\bwarn\b/.test(l) ||
             INCIDENT_KEYWORDS.some(kw => l.includes(kw))
    })
  }
  return list
})

const levelStats = computed(() => {
  const stats = {}
  for (const log of filteredLogs.value) {
    const lvl = extractLevel(log.line)
    stats[lvl] = (stats[lvl] || 0) + 1
  }
  return stats
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredLogs.value.length / pageSize.value)))

const pagedLogs = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredLogs.value.slice(start, start + pageSize.value)
})

const pageNumbers = computed(() => {
  const total = totalPages.value
  const cur   = currentPage.value
  const pages = []
  if (total <= 7) {
    for (let i = 1; i <= total; i++) pages.push(i)
  } else {
    pages.push(1)
    if (cur > 3)          pages.push('…')
    for (let i = Math.max(2, cur - 1); i <= Math.min(total - 1, cur + 1); i++) pages.push(i)
    if (cur < total - 2)  pages.push('…')
    pages.push(total)
  }
  return pages
})

function toggleIncident() {
  incidentOnly.value = !incidentOnly.value
  currentPage.value = 1
}

function openDetail(log) {
  detailLog.value = log
}

function onLevelChange() {
  currentPage.value = 1
  loadLogs()
}

// ── 模板聚合 AI ───────────────────────────
const tplAiContent  = ref('')
const analyzingTplAI = ref(false)

// ── 耗时追踪 Tab ──────────────────────────
const traceValue     = ref('')
const traceTimeMode  = ref('relative')   // 默认快速模式，避免空 custom 字段误导
const traceHours     = ref('24')
const traceStart     = ref('')
const traceEnd       = ref('')
const traceResult      = ref(null)
const traceLogs        = ref([])
const tracingKeyword   = ref(false)   // trace API 请求中
const loadingTraceLogs = ref(false)   // 日志列表加载中（独立状态）
const traceResultTab   = ref('overview')  // 结果子页签：overview | logs
const expandedSpans    = ref(new Set())   // 已展开的行索引

const renderedAI = computed(() =>
  aiContent.value
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
)
const renderedTplAI = computed(() =>
  tplAiContent.value
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
)

function logClass(line) {
  const l = line.toLowerCase()
  if (/\berror\b|exception|fatal|panic/.test(l)) return 'level-error'
  if (/\bwarn(ing)?\b/.test(l))                  return 'level-warn'
  return ''
}

// ── 模板聚合 ─────────────────────────────
const templates        = ref([])
const loadingTemplates = ref(false)
const templateMeta     = ref({ total_logs: 0, total_templates: 0 })
const tplLevelFilter   = ref('')
const tplError         = ref('')

const maxTplCount = computed(() =>
  templates.value[0]?.count || 1
)
const totalTplLogs = computed(() =>
  templates.value.reduce((s, t) => s + t.count, 0) || 1
)
function tplBarW(cnt) {
  return Math.round(cnt / maxTplCount.value * 100)
}
function tplPct(cnt) {
  return (cnt / totalTplLogs.value * 100).toFixed(1)
}
function highlightWildcard(tpl) {
  return tpl.replace(/<\*>/g, '<span class="wildcard">&lt;*&gt;</span>')
}

// ── 数据加载 ─────────────────────────────
async function loadServices() {
  loadingSvcs.value = true
  try {
    const r = await api.getServices()
    services.value = r.data
  } finally {
    loadingSvcs.value = false
  }
}

async function loadLogs() {
  loadingLogs.value = true
  logs.value = []
  currentPage.value = 1
  try {
    const r = await api.getLogs({
      service:  selectedService.value || undefined,
      level:    levelFilter.value || undefined,
      limit:    2000,
      keyword:  keyword.value || undefined,
      ...timeParams(),
    })
    logs.value = r.data
  } finally {
    loadingLogs.value = false
  }
}

async function loadTemplates() {
  loadingTemplates.value = true
  templates.value = []
  tplError.value = ''
  try {
    const r = await api.getTemplates({
      service:  selectedService.value || undefined,
      limit:    10000,
      top_n:    100,
      level:    tplLevelFilter.value || undefined,
      keyword:  keyword.value || undefined,
      ...timeParams(),
    })
    templates.value = r.data
    templateMeta.value = { total_logs: r.total_logs, total_templates: r.total_templates }
  } catch (e) {
    tplError.value = typeof e === 'string' ? e : (e?.message || '聚类请求失败，请检查后端连接')
  } finally {
    loadingTemplates.value = false
  }
}

function selectService(name) {
  selectedService.value = name
  if (activeTab.value === 'logs')           loadLogs()
  else if (activeTab.value === 'templates') loadTemplates()
  // trace tab: 不自动触发，由用户手动点击"开始分析"
}

function onParamChange() {
  if (activeTab.value === 'logs')      loadLogs()
  else                                 loadTemplates()
}

function onTimeModeChange() {
  if (timeMode.value === 'relative') {
    customStart.value = ''
    customEnd.value   = ''
    onParamChange()
  } else {
    const r = todayRange()
    if (!customStart.value) customStart.value = r.start
    if (!customEnd.value)   customEnd.value   = r.end
  }
}

function onCustomTimeChange() {
  if (customStart.value && customEnd.value) onParamChange()
}

function onKeywordInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(onParamChange, 500)
}

function clearKeyword() {
  keyword.value = ''
  onParamChange()
}

function traceTimeParams() {
  if (traceTimeMode.value === 'custom' && traceStart.value && traceEnd.value) {
    if (traceEnd.value < traceStart.value) {
      alert('结束时间不能早于开始时间')
      throw new Error('invalid time range')
    }
    // 本地时间 → UTC，避免服务端按 UTC 错误解析
    return { start_time: toUtcStr(traceStart.value), end_time: toUtcStr(traceEnd.value) }
  }
  return { hours: traceHours.value }
}

async function runTrace() {
  if (!traceValue.value) return

  // 验证自定义时间范围
  if (traceTimeMode.value === 'custom' && (!traceStart.value || !traceEnd.value)) {
    alert('请填写完整的开始时间和结束时间')
    return
  }

  tracingKeyword.value = true
  loadingTraceLogs.value = false
  traceResult.value = null
  traceLogs.value = []
  traceResultTab.value = 'overview'
  expandedSpans.value = new Set()

  let tp
  try { tp = traceTimeParams() } catch { tracingKeyword.value = false; return }

  // ── 第一步：计算首末耗时 ──────────────────
  let traceData = null
  try {
    traceData = await api.traceKeyword({
      keyword: traceValue.value,
      service: selectedService.value || undefined,
      ...tp,
    })
    traceResult.value = traceData
  } catch (e) {
    traceResult.value = { found: false, keyword: traceValue.value, log_count: 0, _error: String(e) }
    tracingKeyword.value = false
    return
  }
  tracingKeyword.value = false   // 耗时计算完成，立即解除主加载状态

  // ── 第二步：加载匹配日志列表（独立加载，不影响结果展示）──
  if (traceData.found) {
    loadingTraceLogs.value = true
    try {
      const logsR = await api.getLogs({
        keyword: traceValue.value,
        service: selectedService.value || undefined,
        limit: 2000,
        ...tp,
      })
      traceLogs.value = [...(logsR.data || [])].reverse()  // 升序展示
    } catch {
      traceLogs.value = []  // 日志列表加载失败不影响耗时结果
    } finally {
      loadingTraceLogs.value = false
    }
  }
}

function switchTraceToCustom() {
  traceTimeMode.value = 'custom'
  const r = todayRange()
  if (!traceStart.value) traceStart.value = r.start
  if (!traceEnd.value)   traceEnd.value   = r.end
}

function toggleSpan(i) {
  const s = new Set(expandedSpans.value)
  s.has(i) ? s.delete(i) : s.add(i)
  expandedSpans.value = s
}

function spanElapsed(log) {
  const firstNs = traceResult.value?.first_ts_ns
  if (!firstNs) return ''
  const ms = (parseInt(log.timestamp_ns) - firstNs) / 1_000_000
  if (ms <= 0) return '+0'
  if (ms < 1)       return `+${(ms * 1000).toFixed(0)} µs`
  if (ms < 1000)    return `+${ms.toFixed(1)} ms`
  if (ms < 60000)   return `+${(ms / 1000).toFixed(3)} s`
  return `+${Math.floor(ms / 60000)}m ${((ms % 60000) / 1000).toFixed(1)}s`
}

function spanBarW(log) {
  const firstNs = traceResult.value?.first_ts_ns
  const totalMs = traceResult.value?.duration_ms
  if (!firstNs || !totalMs) return 0
  const ms = (parseInt(log.timestamp_ns) - firstNs) / 1_000_000
  return Math.min(100, Math.max(0, (ms / totalMs) * 100))
}

function startTplAIAnalysis() {
  if (analyzingTplAI.value) return
  tplAiContent.value = ''
  analyzingTplAI.value = true
  const params = new URLSearchParams({
    ...(selectedService.value ? { service: selectedService.value } : {}),
    ...(tplLevelFilter.value ? { level: tplLevelFilter.value } : {}),
    ...(keyword.value ? { keyword: keyword.value } : {}),
  })
  if (timeMode.value === 'custom' && customStart.value && customEnd.value) {
    params.set('start_time', toUtcStr(customStart.value))
    params.set('end_time',   toUtcStr(customEnd.value))
  } else {
    params.set('hours', hours.value)
  }
  streamSSE(
    `/api/analyze/templates/stream?${params}`,
    chunk => { try { tplAiContent.value += JSON.parse(chunk) } catch { tplAiContent.value += chunk } },
    () => { analyzingTplAI.value = false },
    () => { analyzingTplAI.value = false },
  )
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'templates' && !templates.value.length) loadTemplates()
  // trace tab 不自动加载，等用户输入后手动触发
}

function startAIAnalysis() {
  aiContent.value = ''
  analyzingAI.value = true
  const params = new URLSearchParams({
    ...timeParams(),
    ...(selectedService.value ? { service: selectedService.value } : {}),
    ...(levelFilter.value     ? { level:   levelFilter.value     } : {}),
    ...(keyword.value         ? { keyword: keyword.value         } : {}),
  })
  streamSSE(
    `/api/analyze/stream?${params}`,
    (chunk) => { try { aiContent.value += JSON.parse(chunk) } catch { aiContent.value += chunk } },
    () => { analyzingAI.value = false },
    () => { analyzingAI.value = false },
  )
}

onMounted(() => {
  loadServices()
  loadLogs()
})
</script>

<style scoped>
.log-layout { display: flex; height: 100%; overflow: hidden; }

/* 左侧服务面板 */
.service-panel {
  width: 220px; min-width: 220px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
.panel-header { padding: 12px 12px 10px; border-bottom: 1px solid var(--border); }
.panel-title {
  display: block; font-size: 12px; font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.time-select {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 5px 8px; border-radius: 5px; font-size: 12px; cursor: pointer;
}
/* 时间模式切换 */
.time-mode-tabs {
  display: flex; margin-bottom: 6px;
  background: var(--bg-base); border-radius: 5px; padding: 2px;
}
.tmode-btn {
  flex: 1; padding: 3px 0; font-size: 11px; border: none;
  background: transparent; color: var(--text-muted);
  border-radius: 4px; cursor: pointer; transition: all .12s;
}
.tmode-btn.active { background: var(--bg-active); color: var(--text-primary); }

/* 自定义时间输入 */
.custom-time-wrap {
  display: flex; flex-direction: column; gap: 4px; margin-top: 2px;
}
.dt-input {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 4px 6px; border-radius: 5px; font-size: 11px;
}
.dt-sep {
  text-align: center; font-size: 10px; color: var(--text-muted); line-height: 1;
}

/* 关键字搜索框 */
.keyword-wrap {
  display: flex; align-items: center;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px; padding: 0 8px; gap: 5px;
  min-width: 160px; max-width: 240px;
}
.kw-icon { font-size: 12px; flex-shrink: 0; }
.kw-input {
  flex: 1; background: transparent; border: none;
  color: var(--text-primary); font-size: 12px;
  padding: 5px 0; outline: none;
}
.kw-input::placeholder { color: var(--text-muted); }
.kw-clear {
  background: none; border: none; color: var(--text-muted);
  font-size: 11px; cursor: pointer; padding: 2px;
  line-height: 1; flex-shrink: 0;
}
.kw-clear:hover { color: var(--text-primary); }

.svc-list-wrap { flex: 1; overflow-y: auto; padding: 8px; }
.svc-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; border-radius: 6px;
  cursor: pointer; transition: background .12s;
}
.svc-item:hover  { background: var(--bg-hover); }
.svc-item.active { background: var(--accent-dim); color: var(--accent); }
.svc-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.svc-dot.all   { background: var(--accent); }
.svc-dot.ok    { background: var(--success); }
.svc-dot.error { background: var(--error); }
.svc-label { flex: 1; font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.svc-badge { font-size: 10px; padding: 1px 6px; border-radius: 9999px; background: rgba(239,68,68,.15); color: var(--error); font-weight: 600; }
.loading-row { display: flex; justify-content: center; padding: 12px; }

/* 右侧 */
.log-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* 工具栏 */
.log-toolbar {
  padding: 8px 14px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  justify-content: space-between; gap: 12px;
  flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }

/* Tab */
.tab-group { display: flex; gap: 2px; background: var(--bg-base); padding: 3px; border-radius: 8px; }
.tab-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 14px; border-radius: 6px;
  border: none; background: transparent;
  color: var(--text-muted); font-size: 13px;
  cursor: pointer; transition: all .15s;
}
.tab-btn:hover  { color: var(--text-primary); }
.tab-btn.active { background: var(--bg-active); color: var(--text-primary); }
.tab-count {
  background: var(--bg-hover);
  color: var(--text-muted);
  font-size: 11px; padding: 0 6px;
  border-radius: 9999px; font-weight: 600;
}
.tab-btn.active .tab-count { background: var(--accent-dim); color: var(--accent); }
.meta-info { font-size: 12px; color: var(--text-muted); }

/* AI 面板 */
.ai-panel {
  margin: 10px 14px; padding: 14px 16px;
  background: rgba(99,102,241,.07);
  border: 1px solid rgba(99,102,241,.25);
  border-radius: var(--radius);
  flex-shrink: 0;
}
.ai-panel-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; font-size: 13px; font-weight: 600;
  color: var(--accent-hover);
}
.btn-xs { padding: 2px 8px; font-size: 11px; }
.ai-content {
  font-size: 13px; line-height: 1.8; color: var(--text-secondary);
  max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
}
.ai-typing { display: flex; gap: 4px; margin-top: 8px; }
.ai-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }

/* 日志列表容器 */
.log-container { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* 统计栏 */
.log-stats-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 6px 16px; font-size: 12px; color: var(--text-muted);
  background: var(--bg-base); border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.log-stat-sep { opacity: .4; }
.log-stat-filtered { color: var(--accent); margin-left: 3px; }
.log-stat-item { display: flex; align-items: center; gap: 4px; }
.lvl-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.lvl-error { background: #f87171; }
.lvl-warn  { background: #fb923c; }
.lvl-info  { background: #60a5fa; }
.lvl-debug { background: #6b7280; }
.lvl-other { background: #6b7280; }

/* 表格区 */
.log-table-wrap {
  flex: 1; overflow-y: auto;
  font-family: 'Consolas', 'JetBrains Mono', monospace; font-size: 12px;
}
.log-table {
  width: 100%; border-collapse: collapse; table-layout: fixed;
}
.log-table thead {
  position: sticky; top: 0; z-index: 1;
  background: var(--bg-card);
}
.log-table th {
  padding: 7px 12px; text-align: left;
  font-size: 11px; font-weight: 600; letter-spacing: .04em;
  color: var(--text-muted); border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.log-row {
  cursor: pointer; transition: background .1s;
  border-bottom: 1px solid rgba(46,49,80,.35);
}
.log-row:hover    { background: var(--bg-hover); }
.log-row.row-error { background: var(--log-error); }
.log-row.row-warn  { background: var(--log-warn); }
.log-row td { padding: 5px 12px; vertical-align: top; }
.col-ts  { color: var(--text-muted); white-space: nowrap; font-size: 11px; }
.col-svc { color: var(--accent-hover); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-msg { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-error .col-msg { color: #fca5a5; }
.row-warn  .col-msg { color: #fcd34d; }

/* 级别徽章 */
.lvl-badge {
  display: inline-block; padding: 1px 7px; border-radius: 4px;
  font-size: 10px; font-weight: 700; letter-spacing: .04em;
  white-space: nowrap;
}
.lvl-badge-error { background: rgba(248,113,113,.15); color: #f87171; border: 1px solid rgba(248,113,113,.3); }
.lvl-badge-warn  { background: rgba(251,146,60,.15);  color: #fb923c; border: 1px solid rgba(251,146,60,.3); }
.lvl-badge-info  { background: rgba(96,165,250,.15);  color: #60a5fa; border: 1px solid rgba(96,165,250,.3); }
.lvl-badge-debug { background: rgba(107,114,128,.15); color: #9ca3af; border: 1px solid rgba(107,114,128,.3); }
.lvl-badge-other { background: rgba(107,114,128,.12); color: #9ca3af; border: 1px solid rgba(107,114,128,.2); }

/* 仅事件按钮 */
.btn-incident-active {
  background: rgba(251,191,36,.15);
  border: 1px solid rgba(251,191,36,.5);
  color: #fbbf24;
  padding: 5px 12px; border-radius: 6px; font-size: 12px;
  cursor: pointer; display: inline-flex; align-items: center; gap: 5px;
}

/* 分页 */
.log-pagination {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 14px; border-top: 1px solid var(--border);
  background: var(--bg-card); flex-shrink: 0;
  font-size: 12px; color: var(--text-muted); flex-wrap: wrap;
}
.pg-info { flex: 1; min-width: 120px; }
.pg-btns { display: flex; align-items: center; gap: 2px; }
.pg-btn {
  width: 28px; height: 28px; border: 1px solid var(--border);
  background: var(--bg-base); color: var(--text-muted);
  border-radius: 5px; cursor: pointer; font-size: 13px;
  display: flex; align-items: center; justify-content: center;
  transition: all .12s;
}
.pg-btn:hover:not(:disabled) { background: var(--bg-hover); color: var(--text-primary); }
.pg-btn:disabled { opacity: .35; cursor: not-allowed; }
.pg-num {
  min-width: 28px; height: 28px; padding: 0 5px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid transparent; border-radius: 5px;
  font-size: 12px; cursor: pointer; color: var(--text-muted);
  transition: all .12s;
}
.pg-num:not(.ellipsis):hover { background: var(--bg-hover); color: var(--text-primary); }
.pg-num.active { background: var(--accent-dim); color: var(--accent); border-color: rgba(99,102,241,.3); font-weight: 600; }
.pg-num.ellipsis { cursor: default; }
.pg-size-sel {
  background: var(--bg-base); border: 1px solid var(--border);
  color: var(--text-muted); padding: 3px 6px; border-radius: 5px;
  font-size: 11px; cursor: pointer;
}

/* 日志详情抽屉 */
.log-detail-drawer {
  position: fixed; inset: 0; z-index: 300;
  background: rgba(0,0,0,.45); display: flex; justify-content: flex-end;
}
.drawer-panel {
  width: min(560px, 90vw); height: 100%;
  background: var(--bg-card);
  border-left: 1px solid var(--border);
  display: flex; flex-direction: column;
  box-shadow: -4px 0 24px rgba(0,0,0,.4);
}
.drawer-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  flex-shrink: 0;
}
.drawer-close {
  background: none; border: none; color: var(--text-muted);
  font-size: 14px; cursor: pointer; padding: 4px;
}
.drawer-close:hover { color: var(--text-primary); }
.drawer-body { flex: 1; overflow-y: auto; padding: 16px 18px; display: flex; flex-direction: column; gap: 14px; }
.drawer-row { display: flex; align-items: flex-start; gap: 12px; }
.drawer-row-full { flex-direction: column; gap: 6px; }
.drawer-label {
  width: 44px; flex-shrink: 0; font-size: 11px; font-weight: 600;
  color: var(--text-muted); padding-top: 2px; text-align: right;
}
.drawer-val { font-size: 13px; color: var(--text-primary); word-break: break-all; }
.drawer-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.drawer-tag {
  font-size: 11px; padding: 2px 8px;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 9999px; color: var(--text-muted);
}
.drawer-tag em { color: var(--accent-hover); font-style: normal; }
.drawer-content {
  margin: 0; padding: 12px 14px;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 6px; font-size: 12px; font-family: 'Consolas', monospace;
  color: var(--text-secondary); line-height: 1.7;
  word-break: break-all; white-space: pre-wrap;
  max-height: 60vh; overflow-y: auto;
}

/* 抽屉动画 */
.drawer-slide-enter-active, .drawer-slide-leave-active {
  transition: all .2s ease;
}
.drawer-slide-enter-from .drawer-panel, .drawer-slide-leave-to .drawer-panel {
  transform: translateX(100%);
}
.drawer-slide-enter-from, .drawer-slide-leave-to { background: transparent; }

/* ── 模板聚合 ── */
.template-container { flex: 1; overflow-y: auto; padding: 12px 16px; }
.template-list { display: flex; flex-direction: column; gap: 10px; }

.tpl-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  transition: border-color .15s;
}
.tpl-card:hover { border-color: rgba(99,102,241,.4); }

.tpl-header {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px;
}
.tpl-rank {
  width: 22px; text-align: center;
  font-size: 12px; font-weight: 700;
  color: var(--text-muted); flex-shrink: 0;
}
.tpl-rank.rank-top { color: var(--warning); }
.tpl-count { flex-shrink: 0; }
.tpl-pct { font-size: 11px; color: var(--text-muted); flex-shrink: 0; width: 44px; }
.tpl-bar-wrap { flex: 1; height: 6px; background: var(--bg-hover); border-radius: 3px; overflow: hidden; }
.tpl-bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 3px; transition: width .4s; }

.tpl-pattern {
  font-family: 'Consolas', 'JetBrains Mono', monospace;
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 8px 12px;
  word-break: break-all;
  line-height: 1.7;
  margin-bottom: 10px;
}
:deep(.wildcard) {
  color: var(--accent-hover);
  background: rgba(99,102,241,.15);
  border-radius: 3px;
  padding: 0 3px;
  font-weight: 600;
}

.tpl-services { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tpl-label { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.svc-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; padding: 2px 8px;
  background: rgba(59,130,246,.1);
  border: 1px solid rgba(59,130,246,.25);
  color: var(--info); border-radius: 9999px;
}
.svc-chip em { font-style: normal; opacity: .7; }

.tpl-example {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: 11px;
}
.tpl-example-text {
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
  overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; flex: 1;
}
.tpl-example-ts { color: var(--text-muted); opacity: .6; margin-right: 6px; }

@keyframes pulse { 0%,80%,100%{opacity:.2} 40%{opacity:1} }

/* ═══════════════════════════════════════
   耗时追踪 Tab
═══════════════════════════════════════ */
.trace-tab {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; padding: 10px 16px; gap: 10px;
}

/* 查询工具栏（单行） */
.trace-form-bar {
  display: flex; align-items: center; gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  flex-shrink: 0;
}
.trace-input-grow { flex: 1; min-width: 0; }
.trace-bar-select { width: 130px; flex-shrink: 0; }
.trace-input-wrap {
  display: flex; align-items: center;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px; padding: 0 10px; gap: 6px;
  transition: border-color .15s;
}
.trace-input-wrap:focus-within {
  border-color: rgba(234,179,8,.5);
  box-shadow: 0 0 0 2px rgba(234,179,8,.08);
}
.trace-input-icon { font-size: 13px; flex-shrink: 0; }
.trace-input {
  flex: 1; background: transparent; border: none;
  color: var(--text-primary); font-size: 13px;
  padding: 6px 0; outline: none;
}
.trace-input::placeholder { color: var(--text-muted); }

/* 开始分析按钮 */
.btn-trace-primary {
  background: linear-gradient(135deg, rgba(234,179,8,.2), rgba(234,179,8,.1));
  border: 1px solid rgba(234,179,8,.45);
  color: #fbbf24; padding: 7px 20px;
  border-radius: 6px; font-size: 13px; font-weight: 600;
  cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  transition: all .15s; white-space: nowrap;
}
.btn-trace-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(234,179,8,.3), rgba(234,179,8,.18));
  border-color: rgba(234,179,8,.7);
}
.btn-trace-primary:disabled { opacity: .4; cursor: not-allowed; }

/* 结果区域 */
.trace-result {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  min-height: 0;
}

/* 未找到 */
.trace-not-found {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 40px;
  color: var(--text-muted); font-size: 13px; gap: 8px;
}
.trace-not-found em { color: var(--text-primary); font-style: normal; font-weight: 500; }

/* ── 子页签切换栏 ── */
.trace-sub-tabs {
  display: flex; gap: 2px;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 8px; padding: 3px;
  flex-shrink: 0; margin-bottom: 10px;
  width: fit-content;
}
.trace-sub-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 16px; border-radius: 6px;
  border: none; background: transparent;
  color: var(--text-muted); font-size: 13px;
  cursor: pointer; transition: all .15s;
}
.trace-sub-btn:hover { color: var(--text-primary); }
.trace-sub-btn.active {
  background: var(--bg-active); color: var(--text-primary);
}
.trace-sub-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 20px; height: 18px; padding: 0 5px;
  background: var(--bg-hover); border-radius: 9999px;
  font-size: 11px; color: var(--text-muted); font-weight: 600;
}
.trace-sub-btn.active .trace-sub-badge {
  background: rgba(234,179,8,.15); color: #fbbf24;
}

/* ── 耗时概览页签 ── */
.trace-overview {
  flex: 1; overflow-y: auto;
  display: flex; flex-direction: column; gap: 16px;
}

/* 大数字英雄区 */
.trace-hero {
  background: var(--bg-card);
  border: 1px solid rgba(234,179,8,.3);
  border-radius: var(--radius);
  padding: 28px 32px;
  display: flex; flex-direction: column; gap: 6px;
  align-items: flex-start;
}
.trace-hero-label {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .6px; color: var(--text-muted);
}
.trace-hero-duration {
  font-size: 56px; font-weight: 700; color: #fbbf24;
  font-variant-numeric: tabular-nums; line-height: 1;
  letter-spacing: -2px;
}
.trace-hero-meta {
  font-size: 13px; color: var(--text-muted); margin-top: 4px;
}
.trace-hero-meta em { color: var(--text-primary); font-style: normal; font-weight: 500; }
.trace-hero-meta strong { color: var(--text-primary); }
.trace-limit-hint { font-size: 11px; color: var(--warning); }

/* 时间线卡片 */
.trace-timeline-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
}
.trace-tl-row {
  display: flex; align-items: stretch; gap: 16px;
}
.trace-tl-left {
  display: flex; flex-direction: column; align-items: center;
  width: 20px; flex-shrink: 0;
}
.trace-tl-dot {
  width: 14px; height: 14px; border-radius: 50%;
  flex-shrink: 0;
}
.dot-first { background: #34d399; box-shadow: 0 0 8px rgba(52,211,153,.6); }
.dot-last  { background: #f87171; box-shadow: 0 0 8px rgba(248,113,113,.6); }
.trace-tl-connector {
  flex: 1; width: 2px;
  background: repeating-linear-gradient(
    180deg, rgba(234,179,8,.4) 0 4px, transparent 4px 8px
  );
  margin: 4px 0;
}
.trace-tl-line {
  flex: 1; width: 2px;
  background: repeating-linear-gradient(
    180deg, rgba(234,179,8,.4) 0 4px, transparent 4px 8px
  );
}
.trace-tl-body {
  flex: 1; display: flex; flex-direction: column; gap: 4px;
  padding: 0 0 20px;
}
.dur-row .trace-tl-body { padding: 0; justify-content: center; }
.trace-tl-tag {
  font-size: 10px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .5px; color: var(--text-muted);
}
.trace-tl-ts {
  font-size: 15px; font-weight: 600; color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.trace-ep-svc {
  display: inline-block; font-size: 10px; padding: 1px 7px;
  background: rgba(99,102,241,.15); border: 1px solid rgba(99,102,241,.3);
  color: var(--accent-hover); border-radius: 9999px; width: fit-content;
}
.trace-tl-log {
  font-size: 12px; color: var(--text-muted);
  font-family: 'Consolas', monospace;
  word-break: break-all; line-height: 1.5;
}
.trace-tl-dur-badge {
  font-size: 13px; font-weight: 700; color: #fbbf24;
  background: rgba(234,179,8,.1);
  border: 1px solid rgba(234,179,8,.3);
  border-radius: 6px; padding: 3px 12px;
  font-variant-numeric: tabular-nums;
  align-self: flex-start;
}

/* ── 匹配日志页签 ── */
.trace-log-panel {
  flex: 1; display: flex; flex-direction: column; gap: 8px;
  overflow: hidden; min-height: 0;
}
.trace-logs-header {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; font-weight: 500; color: var(--text-muted);
  flex-shrink: 0;
}
.trace-logs-count {
  font-size: 11px; padding: 1px 7px;
  background: var(--bg-hover); border-radius: 9999px;
  color: var(--text-muted);
}
.trace-log-list {
  flex: 1; overflow-y: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-family: 'Consolas', 'JetBrains Mono', monospace;
  font-size: 12px;
}

/* ── 每条耗时列表 ── */
.trace-spans-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  flex-shrink: 0;
}
.trace-spans-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  font-size: 12px; font-weight: 500; color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  background: var(--bg-base);
}
.trace-span-list {
  max-height: 400px; overflow-y: auto;
  font-family: 'Consolas', 'JetBrains Mono', monospace; font-size: 11px;
}
.trace-span-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 5px 14px;
  border-bottom: 1px solid rgba(46,49,80,.35);
  transition: background .1s;
  cursor: pointer;
}
.trace-span-row:hover { background: var(--bg-hover); }
.trace-span-row.level-error { background: var(--log-error); }
.trace-span-row.level-warn  { background: var(--log-warn); }
.trace-span-idx {
  width: 30px; text-align: right; flex-shrink: 0;
  color: var(--text-muted); font-size: 10px;
}
.trace-span-elapsed {
  width: 90px; flex-shrink: 0;
  color: #fbbf24; font-weight: 600; font-size: 11px;
  font-variant-numeric: tabular-nums; text-align: right;
}
.trace-span-bar-wrap {
  width: 80px; flex-shrink: 0;
  height: 4px; background: rgba(255,255,255,.07);
  border-radius: 2px; overflow: hidden;
}
.trace-span-bar {
  height: 100%;
  background: linear-gradient(90deg, #34d399, #fbbf24);
  border-radius: 2px; transition: width .2s;
  min-width: 2px;
}
.trace-span-ts {
  width: 138px; flex-shrink: 0;
  color: var(--text-muted); font-size: 10px;
  white-space: nowrap;
}
.trace-span-line {
  flex: 1; color: var(--text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  line-height: 1.5; padding-top: 1px;
}
.trace-span-row.expanded .trace-span-line {
  white-space: pre-wrap; word-break: break-all;
  text-overflow: unset; overflow: visible;
}
.trace-span-idx,
.trace-span-elapsed,
.trace-span-bar-wrap,
.trace-span-ts,
.trace-ep-svc {
  flex-shrink: 0; margin-top: 2px;
}
</style>
