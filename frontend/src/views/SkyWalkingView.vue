<template>
  <div class="sw-layout">
    <!-- ── 左侧服务面板 ── -->
    <aside class="sw-service-panel">
      <div class="sw-panel-header">
        <span class="sw-panel-title">SkyWalking</span>
        <span class="sw-panel-sub">APM 追踪</span>
      </div>

      <!-- 时间范围 -->
      <div class="sw-time-row">
        <select v-model="hours" class="sw-select" @change="onHoursChange">
          <option value="1">1 小时</option>
          <option value="3">3 小时</option>
          <option value="6">6 小时</option>
          <option value="24">24 小时</option>
          <option value="72">3 天</option>
        </select>
        <button class="sw-refresh-btn" @click="reloadAll" :disabled="loadingSvcs" title="刷新">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
        </button>
      </div>

      <!-- 服务列表 -->
      <div class="sw-svc-list">
        <div
          class="sw-svc-item"
          :class="{ active: selectedSvc === null }"
          @click="selectService(null)"
        >
          <span class="sw-svc-dot all"></span>
          <span class="sw-svc-name">全部服务</span>
        </div>
        <div v-if="loadingSvcs" class="sw-loading-row">
          <div class="spinner" style="width:12px;height:12px;border-width:2px"></div>
        </div>
        <div v-else-if="svcError" class="sw-empty-svc">
          <span style="color:var(--error,#f87171);font-size:11px;line-height:1.5;display:block;padding:4px 0">⚠ {{ svcError }}</span>
        </div>
        <div v-else-if="!services.length" class="sw-empty-svc">
          <span style="color:var(--text-muted);font-size:12px">暂无服务（时间范围内无数据）</span>
        </div>
        <div
          v-for="svc in services" :key="svc.id"
          class="sw-svc-item"
          :class="{ active: selectedSvc?.id === svc.id }"
          @click="selectService(svc)"
        >
          <span class="sw-svc-dot svc"></span>
          <span class="sw-svc-name">{{ svc.name }}</span>
          <span v-if="svc.group" class="sw-svc-group">{{ svc.group }}</span>
        </div>
      </div>
    </aside>

    <!-- ── 右侧主区域 ── -->
    <div class="sw-main">
      <!-- Tab 栏 -->
      <div class="sw-tab-bar">
        <button
          v-for="t in TABS" :key="t.id"
          class="sw-tab-btn"
          :class="{ active: activeTab === t.id }"
          @click="switchTab(t.id)"
        >{{ t.label }}</button>
        <span class="sw-tab-svc" v-if="selectedSvc">
          · {{ selectedSvc.name }}
        </span>
      </div>

      <!-- ════════════════════ 链路追踪 Tab ════════════════════ -->
      <div v-show="activeTab === 'traces'" class="sw-tab-content">
        <!-- 过滤工具栏 -->
        <div class="sw-trace-toolbar">
          <div class="sw-search-wrap">
            <svg class="sw-search-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input
              v-model="traceIdSearch"
              class="sw-search-input"
              placeholder="按 TraceId 搜索..."
              @keyup.enter="searchTrace"
            />
            <button v-if="traceIdSearch" class="kw-clear" @click="traceIdSearch=''; loadTraces()">✕</button>
          </div>
          <label class="sw-check-label">
            <input type="checkbox" v-model="errorOnly" @change="loadTraces" />
            仅错误
          </label>
          <button class="sw-btn sw-btn-outline" @click="loadTraces" :disabled="loadingTraces">
            <span v-if="loadingTraces" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
            <span v-else>🔄</span> 查询
          </button>
          <span class="sw-total-hint" v-if="traceTotal">共 {{ traceTotal }} 条</span>
        </div>

        <!-- 追踪列表 + 详情（左右布局） -->
        <div class="sw-trace-area">
          <!-- 追踪列表 -->
          <div class="sw-trace-list-wrap" :class="{ narrow: !!selectedTrace }">
            <div v-if="loadingTraces && !traces.length" class="sw-empty">
              <div class="spinner"></div><p>查询中...</p>
            </div>
            <div v-else-if="!traces.length" class="sw-empty">
              <span style="font-size:28px">🔍</span>
              <p>暂无追踪数据</p>
              <small style="color:var(--text-muted)">请选择服务或调整时间范围</small>
            </div>
            <div v-else>
              <div
                v-for="tr in traces" :key="tr.segmentId"
                class="sw-trace-row"
                :class="[{ active: selectedTrace?.segmentId === tr.segmentId }, tr.isError ? 'row-err' : '']"
                @click="openTrace(tr)"
              >
                <div class="sw-trace-row-top">
                  <span class="sw-trace-ep">{{ tr.endpointNames?.[0] || '未知端点' }}</span>
                  <span class="sw-trace-dur" :class="tr.duration > 1000 ? 'dur-slow' : ''">
                    {{ tr.duration }} ms
                  </span>
                </div>
                <div class="sw-trace-row-bot">
                  <span class="sw-trace-id">{{ tr.traceIds?.[0]?.slice(0,20) }}...</span>
                  <span class="sw-trace-time">{{ formatTs(tr.start) }}</span>
                  <span v-if="tr.isError" class="sw-err-badge">ERROR</span>
                </div>
              </div>
              <!-- 分页 -->
              <div class="sw-pagination">
                <button class="sw-pg-btn" :disabled="tracePage <= 1" @click="tracePage--; loadTraces()">‹</button>
                <span class="sw-pg-info">第 {{ tracePage }} 页</span>
                <button class="sw-pg-btn" :disabled="traces.length < 20" @click="tracePage++; loadTraces()">›</button>
              </div>
            </div>
          </div>

          <!-- 追踪详情（瀑布图） -->
          <div v-if="selectedTrace" class="sw-waterfall-wrap">
            <div class="sw-wf-header">
              <div class="sw-wf-title">
                <span class="sw-wf-ep">{{ selectedTrace.endpointNames?.[0] }}</span>
                <span class="sw-wf-total">{{ selectedTrace.duration }} ms</span>
                <span v-if="selectedTrace.isError" class="sw-err-badge">ERROR</span>
              </div>
              <div class="sw-wf-meta">
                <span class="sw-wf-id">TraceId: {{ selectedTrace.traceIds?.[0] }}</span>
                <span class="sw-wf-time">{{ formatTs(selectedTrace.start) }}</span>
              </div>
              <button class="kw-clear" style="position:absolute;right:14px;top:14px" @click="selectedTrace=null; spanTree=[]">✕</button>
            </div>

            <div v-if="loadingSpans" class="sw-empty" style="flex:1">
              <div class="spinner"></div><p>加载 Span 列表...</p>
            </div>
            <div v-else-if="!spanTree.length" class="sw-empty" style="flex:1">
              <p>未找到 Span 数据</p>
            </div>
            <div v-else class="sw-waterfall">
              <!-- 列头 -->
              <div class="sw-wf-col-header">
                <div class="sw-wf-col-name">服务 / 端点</div>
                <div class="sw-wf-col-timeline">时间轴（总耗时 {{ selectedTrace.duration }} ms）</div>
              </div>
              <!-- Span 行 -->
              <div
                v-for="span in spanTree" :key="span._key"
                class="sw-span-row"
                :class="[span.isError ? 'span-err' : '', { expanded: expandedSpans.has(span._key) }]"
                @click="toggleSpan(span._key)"
              >
                <!-- 名称列 -->
                <div class="sw-span-name" :style="{ paddingLeft: (span._depth * 16 + 8) + 'px' }">
                  <span class="sw-span-type-dot" :class="spanTypeClass(span)"></span>
                  <span class="sw-span-svc">{{ span.serviceCode }}</span>
                  <span class="sw-span-sep">›</span>
                  <span class="sw-span-ep">{{ span.endpoint || span.peer || span.component || span.type }}</span>
                  <span v-if="span.isError" class="sw-span-err-dot"></span>
                </div>
                <!-- 时间轴列 -->
                <div class="sw-span-timeline">
                  <div
                    class="sw-span-bar"
                    :class="[spanTypeClass(span), span.isError ? 'bar-err' : '']"
                    :style="{
                      left:  spanOffset(span) + '%',
                      width: Math.max(spanWidth(span), 0.5) + '%',
                    }"
                  ></div>
                  <span
                    class="sw-span-dur-label"
                    :style="{ left: (spanOffset(span) + Math.max(spanWidth(span), 0.5) + 0.5) + '%' }"
                  >{{ spanDur(span) }} ms</span>
                </div>
              </div>
              <!-- 展开详情 -->
              <template v-for="span in spanTree" :key="'detail-' + span._key">
                <div v-if="expandedSpans.has(span._key)" class="sw-span-detail">
                  <div class="sw-span-detail-grid">
                    <div class="sw-sd-item" v-if="span.serviceInstanceName">
                      <span class="sw-sd-key">实例</span>
                      <span class="sw-sd-val">{{ span.serviceInstanceName }}</span>
                    </div>
                    <div class="sw-sd-item" v-if="span.peer">
                      <span class="sw-sd-key">Peer</span>
                      <span class="sw-sd-val">{{ span.peer }}</span>
                    </div>
                    <div class="sw-sd-item" v-if="span.component">
                      <span class="sw-sd-key">组件</span>
                      <span class="sw-sd-val">{{ span.component }}</span>
                    </div>
                    <div class="sw-sd-item">
                      <span class="sw-sd-key">类型</span>
                      <span class="sw-sd-val">{{ span.type }} / {{ span.layer }}</span>
                    </div>
                    <div class="sw-sd-item">
                      <span class="sw-sd-key">耗时</span>
                      <span class="sw-sd-val">{{ spanDur(span) }} ms</span>
                    </div>
                    <div class="sw-sd-item">
                      <span class="sw-sd-key">开始</span>
                      <span class="sw-sd-val">{{ formatTs(span.startTime) }}</span>
                    </div>
                    <template v-for="tag in (span.tags || [])" :key="tag.key">
                      <div class="sw-sd-item">
                        <span class="sw-sd-key">{{ tag.key }}</span>
                        <span class="sw-sd-val">{{ tag.value }}</span>
                      </div>
                    </template>
                  </div>
                  <div v-if="span.logs?.length" class="sw-span-logs">
                    <div class="sw-sd-key" style="margin-bottom:4px">日志事件</div>
                    <div v-for="(log, li) in span.logs" :key="li" class="sw-span-log-row">
                      <span class="sw-span-log-ts">{{ formatTs(log.time) }}</span>
                      <span v-for="d in log.data" :key="d.key" class="sw-span-log-kv">
                        <em>{{ d.key }}:</em> {{ d.value }}
                      </span>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- ════════════════════ 服务拓扑 Tab ════════════════════ -->
      <div v-show="activeTab === 'topology'" class="sw-tab-content">
        <div class="sw-topo-toolbar">
          <button class="sw-btn sw-btn-outline" @click="loadTopology" :disabled="loadingTopo">
            <span v-if="loadingTopo" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
            <span v-else>🔄</span> 刷新拓扑
          </button>
          <span class="sw-topo-hint">
            节点: {{ topoNodes.length }}  调用关系: {{ topoCalls.length }}
          </span>
          <div class="sw-topo-legend">
            <span class="sw-legend-item"><span class="sw-topo-dot dot-real"></span>真实服务</span>
            <span class="sw-legend-item"><span class="sw-topo-dot dot-virtual"></span>外部/虚拟</span>
          </div>
        </div>

        <div v-if="loadingTopo" class="sw-empty" style="flex:1">
          <div class="spinner"></div><p>加载拓扑...</p>
        </div>
        <div v-else-if="!topoNodes.length" class="sw-empty" style="flex:1">
          <span style="font-size:32px">🕸️</span>
          <p>暂无拓扑数据</p>
        </div>
        <div v-else class="sw-topo-area">
          <svg class="sw-topo-svg" :viewBox="`0 0 ${topoW} ${topoH}`" @wheel.prevent="topoZoom">
            <defs>
              <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
                <path d="M0,0 L0,6 L8,3 z" fill="var(--text-muted)" />
              </marker>
            </defs>
            <!-- 边 -->
            <g class="topo-edges">
              <line
                v-for="call in topoEdges" :key="call.id"
                :x1="call.sx" :y1="call.sy" :x2="call.tx" :y2="call.ty"
                class="topo-edge"
                :class="call.detectPoints?.includes('SERVER') ? 'edge-server' : 'edge-client'"
                marker-end="url(#arrow)"
              />
            </g>
            <!-- 节点 -->
            <g class="topo-nodes">
              <g
                v-for="n in positionedNodes" :key="n.id"
                class="topo-node"
                :class="[n.isReal ? 'node-real' : 'node-virtual', { 'node-selected': selectedSvc?.name === n.name }]"
                :transform="`translate(${n.x},${n.y})`"
                @click="selectNodeService(n)"
                style="cursor:pointer"
              >
                <circle r="28" class="node-circle" />
                <text class="node-icon" dominant-baseline="central" text-anchor="middle" dy="-8">
                  {{ nodeIcon(n) }}
                </text>
                <text class="node-label" text-anchor="middle" dy="22" dominant-baseline="auto">
                  {{ n.name.length > 14 ? n.name.slice(0,12) + '…' : n.name }}
                </text>
              </g>
            </g>
          </svg>
        </div>
      </div>

      <!-- ════════════════════ 性能指标 Tab ════════════════════ -->
      <div v-show="activeTab === 'metrics'" class="sw-tab-content" style="flex-direction:column;overflow-y:auto">
        <div class="sw-metrics-toolbar">
          <span v-if="!selectedSvc" class="sw-hint">← 请先选择服务</span>
          <template v-else>
            <span class="sw-metrics-svc">{{ selectedSvc.name }}</span>
            <button class="sw-btn sw-btn-outline" @click="loadMetrics" :disabled="loadingMetrics">
              <span v-if="loadingMetrics" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
              <span v-else>🔄</span> 刷新
            </button>
          </template>
        </div>

        <div v-if="loadingMetrics" class="sw-empty" style="flex:1">
          <div class="spinner"></div><p>加载指标...</p>
        </div>
        <div v-else-if="!selectedSvc" class="sw-empty" style="flex:1">
          <span style="font-size:32px">📊</span>
          <p>从左侧选择服务查看性能指标</p>
        </div>
        <div v-else-if="!metrics" class="sw-empty" style="flex:1">
          <span style="font-size:32px">📉</span>
          <p>暂无指标数据</p>
        </div>
        <div v-else class="sw-metrics-grid">
          <!-- 响应时间 -->
          <div class="sw-metric-card">
            <div class="sw-mc-header">
              <span class="sw-mc-title">平均响应时间</span>
              <span class="sw-mc-unit">ms</span>
            </div>
            <div class="sw-mc-stat" :class="avgRespTime > 1000 ? 'stat-warn' : ''">
              {{ avgRespTime }} ms
            </div>
            <div class="sw-mc-chart">
              <svg class="sw-line-chart" viewBox="0 0 400 80" preserveAspectRatio="none">
                <polyline
                  :points="linePoints(metrics.resp_time)"
                  fill="none" stroke="var(--accent)" stroke-width="1.5"
                />
                <polygon
                  :points="areaPoints(metrics.resp_time)"
                  fill="var(--accent)" opacity="0.12"
                />
              </svg>
            </div>
          </div>

          <!-- 吞吐量 -->
          <div class="sw-metric-card">
            <div class="sw-mc-header">
              <span class="sw-mc-title">吞吐量（CPM）</span>
              <span class="sw-mc-unit">次/分钟</span>
            </div>
            <div class="sw-mc-stat">{{ avgThroughput }}</div>
            <div class="sw-mc-chart">
              <svg class="sw-line-chart" viewBox="0 0 400 80" preserveAspectRatio="none">
                <polyline
                  :points="linePoints(metrics.throughput)"
                  fill="none" stroke="#3fb950" stroke-width="1.5"
                />
                <polygon
                  :points="areaPoints(metrics.throughput)"
                  fill="#3fb950" opacity="0.12"
                />
              </svg>
            </div>
          </div>

          <!-- 错误率 -->
          <div class="sw-metric-card">
            <div class="sw-mc-header">
              <span class="sw-mc-title">错误率</span>
              <span class="sw-mc-unit">%</span>
            </div>
            <div class="sw-mc-stat" :class="avgErrorRate > 5 ? 'stat-err' : avgErrorRate > 1 ? 'stat-warn' : ''">
              {{ avgErrorRate }} %
            </div>
            <div class="sw-mc-chart">
              <svg class="sw-line-chart" viewBox="0 0 400 80" preserveAspectRatio="none">
                <polyline
                  :points="linePoints(metrics.error_rate)"
                  fill="none" stroke="var(--error)" stroke-width="1.5"
                />
                <polygon
                  :points="areaPoints(metrics.error_rate)"
                  fill="var(--error)" opacity="0.12"
                />
              </svg>
            </div>
          </div>

          <!-- 实例列表 -->
          <div class="sw-metric-card sw-metric-card-wide">
            <div class="sw-mc-header">
              <span class="sw-mc-title">服务实例</span>
            </div>
            <div v-if="!instances.length" style="color:var(--text-muted);font-size:12px;padding:8px 0">
              无实例数据
            </div>
            <div v-else class="sw-instance-list">
              <div v-for="inst in instances" :key="inst.id" class="sw-instance-row">
                <span class="sw-inst-dot"></span>
                <span class="sw-inst-name">{{ inst.name }}</span>
                <div class="sw-inst-attrs">
                  <span v-for="attr in (inst.attributes||[]).slice(0,3)" :key="attr.name" class="sw-inst-attr">
                    {{ attr.name }}: {{ attr.value }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 接口耗时 TopN -->
        <div class="sw-endpoint-topn">
          <div class="sw-mc-header" style="padding:12px 16px 8px">
            <span class="sw-mc-title">接口耗时排行（全局 Top {{ endpointTopN.length }}）</span>
            <button class="sw-btn sw-btn-outline" style="margin-left:auto" @click="loadEndpointTopN" :disabled="loadingTopN">
              <span v-if="loadingTopN" class="spinner" style="width:10px;height:10px;border-width:2px"></span>
              <span v-else>🔄</span>
            </button>
          </div>
          <div v-if="loadingTopN" style="padding:12px;color:var(--text-muted);font-size:12px">加载中...</div>
          <div v-else-if="!endpointTopN.length" style="padding:12px;color:var(--text-muted);font-size:12px">暂无接口数据</div>
          <table v-else class="sw-topn-table">
            <thead>
              <tr>
                <th>#</th>
                <th>接口</th>
                <th>平均耗时</th>
                <th>成功率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(ep, i) in endpointTopN" :key="ep.name">
                <td class="sw-topn-rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</td>
                <td class="sw-topn-name">{{ ep.name }}</td>
                <td class="sw-topn-val" :class="ep.avg_ms > 1000 ? 'val-err' : ep.avg_ms > 300 ? 'val-warn' : 'val-ok'">
                  {{ ep.avg_ms }} ms
                </td>
                <td class="sw-topn-sla" :class="ep.sla < 90 ? 'val-err' : ep.sla < 99 ? 'val-warn' : 'val-ok'">
                  {{ ep.sla }}%
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
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api/index.js'

const TABS = [
  { id: 'traces',   label: '🔗 链路追踪' },
  { id: 'topology', label: '🕸️ 服务拓扑' },
  { id: 'metrics',  label: '📊 性能指标' },
]

// ── 公共状态 ─────────────────────────────────────────────────────────────────
const activeTab    = ref('traces')
const hours        = ref('24')
const services     = ref([])
const selectedSvc  = ref(null)
const loadingSvcs  = ref(false)
const svcError     = ref('')

// ── 追踪 ──────────────────────────────────────────────────────────────────────
const traces        = ref([])
const traceTotal    = ref(0)
const tracePage     = ref(1)
const loadingTraces = ref(false)
const errorOnly     = ref(false)
const traceIdSearch = ref('')
const selectedTrace = ref(null)
const spanTree      = ref([])
const loadingSpans  = ref(false)
const expandedSpans = ref(new Set())

// 追踪瀑布图计算
const traceStartNs = computed(() => {
  if (!spanTree.value.length) return 0
  return Math.min(...spanTree.value.map(s => s.startTime))
})
const traceDurMs = computed(() => {
  if (!selectedTrace.value) return 1
  return selectedTrace.value.duration || 1
})

function spanOffset(span) {
  const offset = span.startTime - traceStartNs.value
  return Math.max(0, (offset / traceDurMs.value) * 100)
}
function spanWidth(span) {
  const dur = span.endTime - span.startTime
  return Math.max(0.3, (dur / traceDurMs.value) * 100)
}
function spanDur(span) {
  return span.endTime - span.startTime
}
function spanTypeClass(span) {
  const t = (span.layer || '').toLowerCase()
  if (t === 'database' || t === 'db') return 'type-db'
  if (t === 'cache') return 'type-cache'
  if (t === 'mq')    return 'type-mq'
  const st = (span.type || '').toLowerCase()
  if (st === 'exit')  return 'type-exit'
  if (st === 'local') return 'type-local'
  return 'type-entry'
}
function toggleSpan(key) {
  const s = new Set(expandedSpans.value)
  s.has(key) ? s.delete(key) : s.add(key)
  expandedSpans.value = s
}
function nodeIcon(n) {
  const t = (n.type || '').toLowerCase()
  if (t.includes('database') || t.includes('db')) return '🗄'
  if (t.includes('cache') || t.includes('redis')) return '⚡'
  if (t.includes('mq') || t.includes('kafka') || t.includes('rabbit')) return '📨'
  if (t.includes('http') || t.includes('nginx')) return '🌐'
  return '⬡'
}

// ── 拓扑 ──────────────────────────────────────────────────────────────────────
const topology     = ref({ nodes: [], calls: [] })
const loadingTopo  = ref(false)
const topoW = 900
const topoH = 560

const topoNodes = computed(() => topology.value.nodes || [])
const topoCalls = computed(() => topology.value.calls || [])

const positionedNodes = computed(() => {
  const nodes = topoNodes.value
  if (!nodes.length) return []
  const cx = topoW / 2, cy = topoH / 2
  // Separate real vs virtual nodes
  const real    = nodes.filter(n => n.isReal !== false)
  const virtual = nodes.filter(n => n.isReal === false)
  const result = []
  // Real nodes: inner circle
  const ri = Math.min(180, 60 * real.length / (2 * Math.PI) + 60)
  real.forEach((n, i) => {
    const angle = (2 * Math.PI * i / real.length) - Math.PI / 2
    result.push({ ...n, x: cx + ri * Math.cos(angle), y: cy + ri * Math.sin(angle) })
  })
  // Virtual nodes: outer ring
  const ro = ri + 120
  virtual.forEach((n, i) => {
    const angle = (2 * Math.PI * i / (virtual.length || 1)) - Math.PI / 2
    result.push({ ...n, x: cx + ro * Math.cos(angle), y: cy + ro * Math.sin(angle) })
  })
  return result
})

const nodeMap = computed(() => {
  const m = {}
  positionedNodes.value.forEach(n => { m[n.id] = n })
  return m
})

const topoEdges = computed(() => {
  return topoCalls.value.map(call => {
    const src = nodeMap.value[call.source] || {}
    const tgt = nodeMap.value[call.target] || {}
    const sx = src.x || 0, sy = src.y || 0
    const tx = tgt.x || 0, ty = tgt.y || 0
    // Shorten line to stop at node border
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy) || 1
    const r = 29
    return {
      ...call,
      sx: sx + (dx / dist) * r,
      sy: sy + (dy / dist) * r,
      tx: tx - (dx / dist) * r,
      ty: ty - (dy / dist) * r,
    }
  }).filter(e => e.sx || e.tx)
})

function topoZoom(e) {
  // Placeholder - pure SVG viewBox zoom could be added
}
function selectNodeService(n) {
  const svc = services.value.find(s => s.name === n.name)
  if (svc) selectService(svc)
}

// ── 指标 ──────────────────────────────────────────────────────────────────────
const metrics        = ref(null)
const instances      = ref([])
const loadingMetrics = ref(false)
const endpointTopN   = ref([])
const loadingTopN    = ref(false)

const avgRespTime  = computed(() => avg(metrics.value?.resp_time  || []))
const avgThroughput= computed(() => avg(metrics.value?.throughput || []))
const avgErrorRate = computed(() => avg(metrics.value?.error_rate || []))

function avg(arr) {
  const vals = (arr || []).map(v => typeof v === 'object' ? v.value : v).filter(v => v != null)
  if (!vals.length) return 0
  return +(vals.reduce((s, v) => s + v, 0) / vals.length).toFixed(2)
}

function linePoints(arr) {
  const vals = (arr || []).map(v => typeof v === 'object' ? v.value : v)
  if (!vals.length) return ''
  const max = Math.max(...vals, 1)
  const w = 400, h = 80, pad = 4
  return vals.map((v, i) => {
    const x = (i / Math.max(vals.length - 1, 1)) * w
    const y = h - pad - ((v / max) * (h - pad * 2))
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

function areaPoints(arr) {
  const vals = (arr || []).map(v => typeof v === 'object' ? v.value : v)
  if (!vals.length) return ''
  const max = Math.max(...vals, 1)
  const w = 400, h = 80, pad = 4
  const top = vals.map((v, i) => {
    const x = (i / Math.max(vals.length - 1, 1)) * w
    const y = h - pad - ((v / max) * (h - pad * 2))
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  return `0,${h} ${top} ${w},${h}`
}

// ── 工具函数 ─────────────────────────────────────────────────────────────────
function formatTs(ts) {
  if (!ts) return ''
  const n = Number(ts)
  if (!n) return ts
  const d = new Date(n)
  if (isNaN(d)) return ts
  const pad = x => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// ── 数据加载 ─────────────────────────────────────────────────────────────────
async function loadServices() {
  loadingSvcs.value = true
  svcError.value = ''
  try {
    services.value = await api.swGetServices(Number(hours.value))
  } catch (e) {
    services.value = []
    svcError.value = e?.message || '连接 OAP 失败'
    // Try to get more detail from diagnostic endpoint
    try {
      const diag = await api.swTest()
      if (diag?.error) svcError.value = diag.error
    } catch {}
  } finally {
    loadingSvcs.value = false
  }
}

async function loadTraces() {
  loadingTraces.value = true
  selectedTrace.value = null
  spanTree.value = []
  tracePage.value = Math.max(1, tracePage.value)
  try {
    const r = await api.swGetTraces({
      service_id:  selectedSvc.value?.id,
      trace_id:    traceIdSearch.value || undefined,
      hours:       Number(hours.value),
      error_only:  errorOnly.value,
      page:        tracePage.value,
      page_size:   20,
    })
    traces.value = r.traces || []
    traceTotal.value = r.total || 0
  } catch {
    traces.value = []
    traceTotal.value = 0
  } finally {
    loadingTraces.value = false
  }
}

function searchTrace() {
  tracePage.value = 1
  loadTraces()
}

async function openTrace(tr) {
  selectedTrace.value = tr
  expandedSpans.value = new Set()
  spanTree.value = []
  loadingSpans.value = true
  try {
    const tid = tr.traceIds?.[0]
    if (!tid) return
    const r = await api.swGetTraceDetail(tid)
    spanTree.value = buildSpanTree(r.spans || [])
  } catch {
    spanTree.value = []
  } finally {
    loadingSpans.value = false
  }
}

function buildSpanTree(spans) {
  if (!spans.length) return []
  const map = {}
  spans.forEach(s => {
    const key = `${s.segmentId}:${s.spanId}`
    map[key] = { ...s, _key: key, _children: [], _depth: 0 }
  })
  // Link
  spans.forEach(s => {
    const key = `${s.segmentId}:${s.spanId}`
    const node = map[key]
    // Cross-segment ref (takes priority)
    if (s.refs?.length) {
      const ref = s.refs[0]
      const pk = `${ref.parentSegmentId}:${ref.parentSpanId}`
      if (map[pk]) { map[pk]._children.push(node); return }
    }
    // Same-segment parent
    if (s.parentSpanId >= 0) {
      const pk = `${s.segmentId}:${s.parentSpanId}`
      if (map[pk]) { map[pk]._children.push(node); return }
    }
    // Else: root (mark with special key)
    node._root = true
  })
  // DFS flatten
  const flat = []
  function dfs(node, depth) {
    node._depth = depth
    flat.push(node)
    node._children.sort((a, b) => a.startTime - b.startTime)
    node._children.forEach(c => dfs(c, depth + 1))
  }
  const roots = Object.values(map).filter(n => n._root)
  roots.sort((a, b) => a.startTime - b.startTime)
  roots.forEach(r => dfs(r, 0))
  // If no roots found (bad refs), just show all flat
  if (!flat.length) {
    const all = Object.values(map).sort((a, b) => a.startTime - b.startTime)
    all.forEach((n, i) => { n._depth = 0; flat.push(n) })
  }
  return flat
}

async function loadTopology() {
  loadingTopo.value = true
  try {
    topology.value = await api.swGetTopology({
      hours:      Number(hours.value),
      service_id: selectedSvc.value?.id,
    })
  } catch {
    topology.value = { nodes: [], calls: [] }
  } finally {
    loadingTopo.value = false
  }
}

async function loadMetrics() {
  if (!selectedSvc.value) return
  loadingMetrics.value = true
  try {
    metrics.value = await api.swGetMetrics({
      service_name: selectedSvc.value.name,
      hours:        Number(hours.value),
    })
  } catch {
    metrics.value = null
  } finally {
    loadingMetrics.value = false
  }
}

async function loadInstances() {
  if (!selectedSvc.value) { instances.value = []; return }
  try {
    instances.value = await api.swGetInstances({
      service_id: selectedSvc.value.id,
      hours:      Number(hours.value),
    })
  } catch {
    instances.value = []
  }
}

async function loadEndpointTopN() {
  loadingTopN.value = true
  try {
    endpointTopN.value = await api.swGetEndpointTopN({ hours: Number(hours.value), top_n: 20 })
  } catch {
    endpointTopN.value = []
  } finally {
    loadingTopN.value = false
  }
}

function selectService(svc) {
  selectedSvc.value = svc
  selectedTrace.value = null
  spanTree.value = []
  tracePage.value = 1
  if (activeTab.value === 'traces')   loadTraces()
  if (activeTab.value === 'topology') loadTopology()
  if (activeTab.value === 'metrics')  { loadMetrics(); loadInstances(); loadEndpointTopN() }
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'traces')    loadTraces()
  if (tab === 'topology')  loadTopology()
  if (tab === 'metrics')   { loadEndpointTopN(); if (selectedSvc.value) { loadMetrics(); loadInstances() } }
}

function onHoursChange() {
  reloadAll()
}

async function reloadAll() {
  await loadServices()
  loadTraces()
  if (activeTab.value === 'topology') loadTopology()
  if (activeTab.value === 'metrics')  { loadEndpointTopN(); if (selectedSvc.value) { loadMetrics(); loadInstances() } }
}

onMounted(() => {
  loadServices()
  loadTraces()
})
</script>

<style scoped>
.sw-layout {
  display: flex; height: 100%; overflow: hidden;
  background: var(--bg-base);
}

/* ── 左侧服务面板 ── */
.sw-service-panel {
  width: 210px; min-width: 210px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
.sw-panel-header {
  padding: 14px 16px 8px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.sw-panel-title {
  display: block; font-size: 13px; font-weight: 600;
  color: var(--text-primary); letter-spacing: .03em;
}
.sw-panel-sub {
  display: block; font-size: 11px; color: var(--text-muted); margin-top: 1px;
}
.sw-time-row {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.sw-select {
  flex: 1; height: 28px; padding: 0 6px;
  background: var(--bg-input); border: 1px solid var(--border);
  color: var(--text-primary); border-radius: 4px; font-size: 12px;
}
.sw-refresh-btn {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  background: var(--bg-input); border: 1px solid var(--border);
  color: var(--text-secondary); border-radius: 4px; cursor: pointer;
  transition: background .12s;
}
.sw-refresh-btn:hover { background: var(--border); }
.sw-svc-list { flex: 1; overflow-y: auto; padding: 4px 0; }
.sw-svc-item {
  display: flex; align-items: center; gap: 7px;
  padding: 8px 14px; cursor: pointer; font-size: 12px;
  color: var(--text-secondary); transition: background .1s, color .1s;
  border-left: 2px solid transparent;
}
.sw-svc-item:hover { background: var(--sidebar-hover); color: var(--text-primary); }
.sw-svc-item.active { background: var(--sidebar-active); color: var(--text-primary); border-left-color: var(--accent); }
.sw-svc-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.sw-svc-dot.all  { background: var(--text-muted); }
.sw-svc-dot.svc  { background: var(--accent); }
.sw-svc-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sw-svc-group { font-size: 10px; color: var(--text-muted); background: var(--bg-input); padding: 1px 4px; border-radius: 3px; }
.sw-loading-row { display: flex; justify-content: center; padding: 12px; }
.sw-empty-svc { padding: 12px 16px; text-align: center; }

/* ── 主区域 ── */
.sw-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.sw-tab-bar {
  display: flex; align-items: center; gap: 2px;
  padding: 0 16px; background: var(--bg-card);
  border-bottom: 1px solid var(--border); flex-shrink: 0; height: 42px;
}
.sw-tab-btn {
  padding: 6px 14px; border-radius: 4px; font-size: 13px;
  border: none; background: transparent; color: var(--text-secondary);
  cursor: pointer; transition: background .1s, color .1s;
}
.sw-tab-btn:hover { color: var(--text-primary); background: var(--sidebar-hover); }
.sw-tab-btn.active { color: var(--accent); font-weight: 500; background: rgba(56,139,253,.1); }
.sw-tab-svc { margin-left: 8px; font-size: 12px; color: var(--text-muted); }
.sw-tab-content { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* ── 追踪工具栏 ── */
.sw-trace-toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  background: var(--bg-card);
}
.sw-search-wrap {
  display: flex; align-items: center;
  background: var(--bg-input); border: 1px solid var(--border); border-radius: 5px;
  padding: 0 8px; height: 30px; min-width: 220px;
}
.sw-search-icon { color: var(--text-muted); flex-shrink: 0; }
.sw-search-input {
  flex: 1; background: transparent; border: none; outline: none;
  color: var(--text-primary); font-size: 12px; padding: 0 6px;
}
.sw-check-label { display: flex; align-items: center; gap: 5px; font-size: 12px; color: var(--text-secondary); cursor: pointer; }
.sw-btn { padding: 5px 12px; border-radius: 4px; font-size: 12px; cursor: pointer; border: 1px solid transparent; display: flex; align-items: center; gap: 5px; }
.sw-btn-outline { background: transparent; border-color: var(--border); color: var(--text-secondary); }
.sw-btn-outline:hover { color: var(--text-primary); border-color: var(--text-muted); }
.sw-btn:disabled { opacity: .5; cursor: not-allowed; }
.sw-total-hint { font-size: 11px; color: var(--text-muted); }

/* ── 追踪区域 ── */
.sw-trace-area { flex: 1; display: flex; overflow: hidden; }
.sw-trace-list-wrap { width: 340px; min-width: 260px; border-right: 1px solid var(--border); overflow-y: auto; flex-shrink: 0; }
.sw-trace-list-wrap.narrow { width: 280px; min-width: 220px; }
.sw-trace-row {
  padding: 10px 14px; border-bottom: 1px solid var(--border);
  cursor: pointer; transition: background .1s;
}
.sw-trace-row:hover { background: var(--sidebar-hover); }
.sw-trace-row.active { background: var(--sidebar-active); border-left: 2px solid var(--accent); }
.sw-trace-row.row-err { border-left: 2px solid var(--error); }
.sw-trace-row-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.sw-trace-ep { font-size: 12px; color: var(--text-primary); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px; }
.sw-trace-dur { font-size: 12px; color: var(--accent); font-weight: 600; white-space: nowrap; }
.sw-trace-dur.dur-slow { color: var(--warning, #d29922); }
.sw-trace-row-bot { display: flex; align-items: center; gap: 6px; }
.sw-trace-id { font-size: 11px; color: var(--text-muted); font-family: monospace; overflow: hidden; text-overflow: ellipsis; flex: 1; }
.sw-trace-time { font-size: 10px; color: var(--text-muted); white-space: nowrap; }
.sw-err-badge { font-size: 10px; background: rgba(248,81,73,.15); color: var(--error); padding: 1px 5px; border-radius: 3px; font-weight: 600; }
.sw-pagination { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 10px; }
.sw-pg-btn { width: 28px; height: 28px; border-radius: 4px; border: 1px solid var(--border); background: transparent; color: var(--text-secondary); cursor: pointer; font-size: 16px; }
.sw-pg-btn:disabled { opacity: .4; cursor: not-allowed; }
.sw-pg-info { font-size: 12px; color: var(--text-muted); }

/* ── 瀑布图 ── */
.sw-waterfall-wrap {
  flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative;
}
.sw-wf-header {
  padding: 12px 14px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  background: var(--bg-card);
}
.sw-wf-title { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.sw-wf-ep { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.sw-wf-total { font-size: 13px; color: var(--accent); font-weight: 700; }
.sw-wf-meta { display: flex; gap: 12px; }
.sw-wf-id { font-size: 11px; color: var(--text-muted); font-family: monospace; }
.sw-wf-time { font-size: 11px; color: var(--text-muted); }

.sw-waterfall { flex: 1; overflow-y: auto; }
.sw-wf-col-header {
  display: flex; position: sticky; top: 0; z-index: 2;
  background: var(--bg-card); border-bottom: 1px solid var(--border);
  font-size: 11px; color: var(--text-muted); padding: 0;
}
.sw-wf-col-name { width: 320px; min-width: 200px; padding: 6px 12px; border-right: 1px solid var(--border); flex-shrink: 0; }
.sw-wf-col-timeline { flex: 1; padding: 6px 12px; }

.sw-span-row {
  display: flex; align-items: center;
  border-bottom: 1px solid rgba(255,255,255,0.03);
  cursor: pointer; transition: background .08s; min-height: 32px;
}
.sw-span-row:hover { background: var(--sidebar-hover); }
.sw-span-row.span-err { background: rgba(248,81,73,.04); }
.sw-span-row.expanded { background: rgba(56,139,253,.06); }
.sw-span-name {
  width: 320px; min-width: 200px; display: flex; align-items: center; gap: 5px;
  padding: 4px 6px 4px 8px; border-right: 1px solid var(--border); flex-shrink: 0;
  overflow: hidden;
}
.sw-span-type-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.type-entry  .sw-span-type-dot, .sw-span-type-dot.type-entry  { background: var(--accent); }
.type-exit   .sw-span-type-dot, .sw-span-type-dot.type-exit   { background: #3fb950; }
.type-local  .sw-span-type-dot, .sw-span-type-dot.type-local  { background: var(--text-muted); }
.type-db     .sw-span-type-dot, .sw-span-type-dot.type-db     { background: #d29922; }
.type-cache  .sw-span-type-dot, .sw-span-type-dot.type-cache  { background: #e3b341; }
.type-mq     .sw-span-type-dot, .sw-span-type-dot.type-mq     { background: #a371f7; }
.sw-span-svc { font-size: 11px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 80px; flex-shrink: 0; }
.sw-span-sep { color: var(--text-muted); font-size: 11px; flex-shrink: 0; }
.sw-span-ep  { font-size: 12px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.sw-span-err-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--error); flex-shrink: 0; }

.sw-span-timeline {
  flex: 1; position: relative; height: 32px; overflow: hidden; padding: 0 8px;
}
.sw-span-bar {
  position: absolute; top: 50%; transform: translateY(-50%);
  height: 10px; border-radius: 3px; min-width: 2px;
  background: var(--accent); opacity: .8;
}
.sw-span-bar.type-exit  { background: #3fb950; }
.sw-span-bar.type-local { background: var(--text-muted); }
.sw-span-bar.type-db    { background: #d29922; }
.sw-span-bar.type-cache { background: #e3b341; }
.sw-span-bar.type-mq    { background: #a371f7; }
.sw-span-bar.bar-err    { background: var(--error); }
.sw-span-dur-label {
  position: absolute; top: 50%; transform: translateY(-50%);
  font-size: 10px; color: var(--text-muted); white-space: nowrap;
}

/* Span 详情 */
.sw-span-detail {
  background: var(--bg-input); border-bottom: 1px solid var(--border);
  padding: 10px 12px 10px 24px;
}
.sw-span-detail-grid {
  display: flex; flex-wrap: wrap; gap: 6px 20px;
}
.sw-sd-item { display: flex; gap: 6px; align-items: baseline; }
.sw-sd-key { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.sw-sd-val { font-size: 11px; color: var(--text-primary); word-break: break-all; }
.sw-span-logs { margin-top: 8px; }
.sw-span-log-row { display: flex; gap: 10px; font-size: 11px; padding: 2px 0; }
.sw-span-log-ts  { color: var(--text-muted); white-space: nowrap; }
.sw-span-log-kv  { color: var(--text-secondary); }

/* ── 拓扑 ── */
.sw-topo-toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  background: var(--bg-card);
}
.sw-topo-hint { font-size: 12px; color: var(--text-muted); }
.sw-topo-legend { display: flex; gap: 12px; margin-left: auto; }
.sw-legend-item { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-muted); }
.sw-topo-dot { width: 10px; height: 10px; border-radius: 50%; }
.dot-real    { background: var(--accent); }
.dot-virtual { background: var(--text-muted); }
.sw-topo-area { flex: 1; overflow: hidden; display: flex; }
.sw-topo-svg { width: 100%; height: 100%; }

/* SVG topology styles */
.topo-edge { stroke: var(--border); stroke-width: 1.5; }
.edge-server { stroke: var(--accent); opacity: .6; }
.edge-client { stroke: var(--text-muted); opacity: .4; }
.node-circle { fill: var(--bg-card); stroke: var(--text-muted); stroke-width: 1.5; }
.node-real .node-circle { stroke: var(--accent); stroke-width: 2; }
.node-selected .node-circle { stroke: var(--accent); stroke-width: 3; fill: rgba(56,139,253,.12); }
.node-icon  { font-size: 16px; fill: var(--text-primary); }
.node-label { font-size: 10px; fill: var(--text-secondary); }

/* ── 指标 ── */
.sw-metrics-toolbar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  background: var(--bg-card);
}
.sw-metrics-svc { font-size: 13px; color: var(--text-primary); font-weight: 500; }
.sw-hint { font-size: 12px; color: var(--text-muted); }
.sw-metrics-grid {
  padding: 14px;
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;
}
.sw-metric-card {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
  padding: 14px; display: flex; flex-direction: column; gap: 8px;
}
.sw-metric-card-wide { grid-column: 1 / -1; }
.sw-mc-header { display: flex; justify-content: space-between; align-items: center; }
.sw-mc-title { font-size: 12px; color: var(--text-secondary); }
.sw-mc-unit  { font-size: 11px; color: var(--text-muted); }
.sw-mc-stat  { font-size: 28px; font-weight: 700; color: var(--text-primary); }
.sw-mc-stat.stat-warn { color: var(--warning, #d29922); }
.sw-mc-stat.stat-err  { color: var(--error); }
.sw-mc-chart { height: 60px; overflow: hidden; }
.sw-line-chart { width: 100%; height: 100%; }

.sw-instance-list { display: flex; flex-direction: column; gap: 6px; max-height: 160px; overflow-y: auto; }
.sw-instance-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--border); }
.sw-inst-dot { width: 7px; height: 7px; border-radius: 50%; background: #3fb950; flex-shrink: 0; }
.sw-inst-name { font-size: 12px; color: var(--text-primary); min-width: 120px; }
.sw-inst-attrs { display: flex; gap: 8px; flex-wrap: wrap; }
.sw-inst-attr { font-size: 11px; color: var(--text-muted); background: var(--bg-input); padding: 1px 5px; border-radius: 3px; }

/* 接口耗时 TopN */
.sw-endpoint-topn {
  margin: 0 14px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.sw-topn-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.sw-topn-table th {
  padding: 7px 12px; background: var(--bg-input);
  color: var(--text-muted); font-weight: 500; text-align: left;
  border-bottom: 1px solid var(--border);
}
.sw-topn-table td { padding: 7px 12px; border-bottom: 1px solid var(--border); }
.sw-topn-table tr:last-child td { border-bottom: none; }
.sw-topn-rank { width: 32px; color: var(--text-muted); font-weight: 600; }
.sw-topn-rank.rank-top { color: var(--accent); }
.sw-topn-name { color: var(--text-primary); max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sw-topn-val, .sw-topn-sla { font-weight: 600; width: 90px; }
.val-ok   { color: #3fb950; }
.val-warn { color: #e3b341; }
.val-err  { color: var(--error, #f85149); }

/* 通用 */
.sw-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; padding: 40px 20px; color: var(--text-muted); font-size: 13px;
}
.kw-clear {
  background: none; border: none; color: var(--text-muted); cursor: pointer;
  font-size: 14px; padding: 2px 4px; border-radius: 3px; line-height: 1;
}
.kw-clear:hover { color: var(--text-primary); }
.spinner {
  width: 20px; height: 20px; border: 2px solid var(--border);
  border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
