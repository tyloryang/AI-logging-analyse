<template>
  <div class="kg-page">
    <div class="kg-toolbar">
      <div class="kg-brand">
        <div class="kg-brand-mark">
          <span class="kg-ring kg-ring-a"></span>
          <span class="kg-ring kg-ring-b"></span>
          <span class="kg-core"></span>
        </div>
        <div>
          <div class="kg-title">{{ graphTitle }}</div>
          <div class="kg-subtitle">{{ graphSubtitle }}</div>
        </div>
      </div>

      <div class="kg-toolbar-actions">
        <div class="kg-tabs">
          <button
            :class="['kg-tab', { active: mode === 'knowledge' }]"
            @click="switchMode('knowledge')"
          >
            知识关系
          </button>
          <button
            :class="['kg-tab', { active: mode === 'neo4j' }]"
            @click="switchMode('neo4j')"
          >
            Neo4j 关系
          </button>
          <button
            :class="['kg-tab', { active: mode === 'runtime' }]"
            @click="switchMode('runtime')"
          >
            运行关系
          </button>
        </div>

        <div class="kg-controls">
          <span v-if="pinnedId" class="kg-pin-hint" @click="clearPin" title="点击取消固定">📌 已固定 · 点此取消</span>
          <label class="kg-toggle">
            <input v-model="animOn" type="checkbox">
            <span>流动效果</span>
          </label>
          <label class="kg-toggle">
            <input v-model="showLabels" type="checkbox">
            <span>说明浮层</span>
          </label>
          <button
            v-if="mode === 'neo4j'"
            class="kg-btn kg-btn-primary"
            @click="syncNeo4j"
            :disabled="loading || syncing || !neo4jConfigured"
          >
            <span v-if="syncing" class="kg-spinner"></span>
            <span v-else>同步图谱</span>
          </button>
          <button
            v-if="mode === 'neo4j'"
            class="kg-btn"
            @click="openRelationDialog"
            :disabled="loading || !neo4jConnected || nodes.length < 2"
          >
            新增关系
          </button>
          <button
            v-if="mode === 'neo4j' && selectedEdge"
            class="kg-btn kg-btn-danger"
            @click="removeSelectedRelation"
            :disabled="relationSaving"
          >
            删除关系
          </button>
          <button class="kg-btn" @click="loadGraph" :disabled="loading">
            <span v-if="loading" class="kg-spinner"></span>
            <span v-else>刷新</span>
          </button>
          <button class="kg-btn" @click="fitView">Fit</button>
        </div>
      </div>
    </div>

    <div class="kg-meta">
      <div class="kg-chip-row">
        <span v-for="chip in statsChips" :key="chip.label" class="kg-chip">
          <strong>{{ chip.value }}</strong>
          <span>{{ chip.label }}</span>
        </span>
      </div>
      <div class="kg-source">{{ sourceLabel }}</div>
      <div v-if="actionMessage" class="kg-action-message">{{ actionMessage }}</div>
    </div>

    <div class="kg-legend">
      <span v-for="group in nodeGroups" :key="group.id" class="kg-legend-item">
        <span class="kg-dot" :style="{ background: group.color }"></span>
        {{ group.label }}
      </span>
      <span class="kg-legend-divider"></span>
      <span v-for="rel in relationLegend" :key="rel.id" class="kg-legend-item">
        <span class="kg-line" :style="{ background: rel.color }"></span>
        {{ rel.label }}
      </span>
    </div>

    <div class="kg-canvas">
      <svg
        ref="svgEl"
        class="kg-svg"
        :viewBox="vbStr"
        preserveAspectRatio="xMidYMid meet"
        :style="{ cursor: drag.active ? 'grabbing' : 'grab' }"
        @wheel.prevent="onWheel"
        @mousedown="onDragStart"
        @mousemove="onDragMove"
        @mouseup="onDragEnd"
        @mouseleave="onDragEnd"
      >
        <defs>
          <pattern id="kg-grid" width="48" height="48" patternUnits="userSpaceOnUse">
            <path d="M48,0 L0,0 L0,48" fill="none" stroke="rgba(126, 142, 171, 0.08)" stroke-width="1" />
          </pattern>

          <filter id="kg-glow">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter id="kg-glow-sm">
            <feGaussianBlur stdDeviation="2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <linearGradient id="kg-bg" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#081220" />
            <stop offset="58%" stop-color="#0d1117" />
            <stop offset="100%" stop-color="#10192b" />
          </linearGradient>

          <marker
            v-for="marker in edgeMarkers"
            :key="marker.id"
            :id="marker.id"
            markerWidth="8"
            markerHeight="8"
            refX="7"
            refY="3"
            orient="auto"
          >
            <path d="M0,0 L0,6 L8,3 z" :fill="marker.color" />
          </marker>
        </defs>

        <rect width="100%" height="100%" fill="url(#kg-bg)" @click="clearPin" />
        <rect width="100%" height="100%" fill="url(#kg-grid)" @click="clearPin" />

        <g class="kg-zones">
          <rect
            v-for="zone in zones"
            :key="zone.id"
            :x="zone.x"
            :y="zone.y"
            :width="zone.w"
            :height="zone.h"
            rx="24"
            :fill="withAlpha(zone.color, 0.08)"
            :stroke="withAlpha(zone.color, 0.5)"
            stroke-width="1.2"
            stroke-dasharray="10 6"
          />
          <text
            v-for="zone in zones"
            :key="`${zone.id}-label`"
            :x="zone.x + 18"
            :y="zone.y + 24"
            class="kg-zone-label"
            :fill="zone.color"
          >
            {{ zone.label }}
          </text>
        </g>

        <g class="kg-edges">
          <path
            v-for="edge in edges"
            :id="`kg-edge-${edge.id}`"
            :key="edge.id"
            :d="edge.d"
            fill="none"
            :stroke="hoveredId ? (isEdgeRelated(edge) ? edge.color : withAlpha(edge.color, 0.1)) : withAlpha(edge.color, 0.55)"
            :stroke-width="hoveredId && isEdgeRelated(edge) ? 2.5 : 1.5"
            :stroke-dasharray="edge.dash || null"
            :opacity="hoveredId ? (isEdgeRelated(edge) ? 1 : 0.12) : 1"
            :marker-end="`url(#${edge.markerId})`"
            :class="['kg-edge', { selected: selectedEdge?.id === edge.id }]"
            @click.stop="selectEdge(edge)"
          />

          <g v-if="hoveredId">
            <g v-for="edge in relatedEdges" :key="`label-${edge.id}`">
              <rect
                :x="edge.labelX - 34"
                :y="edge.labelY - 10"
                width="68"
                height="18"
                rx="5"
                :fill="withAlpha(edge.color, 0.16)"
                :stroke="withAlpha(edge.color, 0.55)"
                stroke-width="1"
              />
              <text
                :x="edge.labelX"
                :y="edge.labelY + 4"
                class="kg-edge-label"
                text-anchor="middle"
                :fill="edge.color"
              >
                {{ edge.label }}
              </text>
            </g>
          </g>
        </g>

        <g v-if="animOn" class="kg-particles">
          <g
            v-for="edge in edges"
            :key="`particle-${edge.id}`"
            :opacity="hoveredId ? (isEdgeRelated(edge) ? 1 : 0) : 1"
          >
            <circle
              v-for="particle in edge.packets"
              :key="particle.i"
              :r="hoveredId && isEdgeRelated(edge) ? particle.r * 1.45 : particle.r"
              :fill="edge.color"
              filter="url(#kg-glow-sm)"
            >
              <animateMotion
                :dur="`${hoveredId && isEdgeRelated(edge) ? particle.dur * 0.65 : particle.dur}s`"
                repeatCount="indefinite"
                :begin="`${particle.begin}s`"
              >
                <mpath :href="`#kg-edge-${edge.id}`" />
              </animateMotion>
            </circle>
          </g>
        </g>

        <g class="kg-nodes">
          <g
            v-for="node in nodes"
            :key="node.id"
            class="kg-node"
            :transform="`translate(${node.x},${node.y})`"
            :opacity="hoveredId && hoveredId !== node.id && !isNodeConnected(node.id) ? 0.16 : 1"
            :class="{ pinned: pinnedId === node.id }"
            @mouseenter="hoveredId = node.id"
            @mouseleave="hoveredId = pinnedId"
            @click.stop="togglePin(node.id)"
          >
            <circle
              v-if="node.pulse || hoveredId === node.id"
              cx="0"
              cy="0"
              :r="node.r + (hoveredId === node.id ? 14 : 10)"
              :fill="withAlpha(node.color, hoveredId === node.id ? 0.2 : 0.12)"
              :class="{ 'kg-pulse': hoveredId !== node.id }"
            />

            <circle
              v-if="pinnedId === node.id"
              cx="0"
              cy="0"
              :r="node.r + 6"
              fill="none"
              :stroke="node.color"
              stroke-width="1.6"
              stroke-dasharray="3 3"
            />

            <circle
              cx="0"
              cy="0"
              :r="node.r"
              :fill="node.fill"
              :stroke="hoveredId === node.id ? node.color : withAlpha(node.color, 0.65)"
              :stroke-width="hoveredId === node.id ? 2.8 : 1.8"
              filter="url(#kg-glow)"
            />

            <text x="0" y="-2" text-anchor="middle" class="kg-node-abbr">{{ node.abbr }}</text>
            <text x="0" :y="node.r + 16" text-anchor="middle" class="kg-node-name">{{ node.name }}</text>
            <text v-if="node.subtitle" x="0" :y="node.r + 30" text-anchor="middle" class="kg-node-subtitle">
              {{ node.subtitle }}
            </text>
          </g>
        </g>

        <g v-if="showLabels && hoveredNode" class="kg-tooltip">
          <g :transform="`translate(${tooltipPos.x}, ${tooltipPos.y})`">
            <rect
              x="0"
              y="0"
              :width="tooltipW"
              :height="tooltipHeight"
              rx="14"
              fill="rgba(9, 18, 36, 0.96)"
              stroke="rgba(126, 142, 171, 0.25)"
              stroke-width="1.2"
            />
            <text x="14" y="24" class="kg-tooltip-title" :fill="hoveredNode.color">
              {{ hoveredNode.name }}
            </text>
            <text x="14" y="42" class="kg-tooltip-sub">
              {{ hoveredNode.subtitle || hoveredNode.metadata?.kind || 'topology node' }}
            </text>
            <text
              v-for="(line, index) in tooltipLines"
              :key="`${hoveredNode.id}-tip-${index}`"
              x="14"
              :y="66 + index * 18"
              class="kg-tooltip-line"
            >
              {{ line }}
            </text>
          </g>
        </g>
      </svg>

      <div v-if="loadError" class="kg-overlay kg-overlay-error">
        <div class="kg-overlay-card">
          <div class="kg-overlay-title">拓扑加载失败</div>
          <div class="kg-overlay-text">{{ loadError }}</div>
        </div>
      </div>

      <div v-else-if="!loading && !nodes.length" class="kg-overlay">
        <div class="kg-overlay-card">
          <div class="kg-overlay-title">暂无拓扑数据</div>
          <div class="kg-overlay-text">{{ emptyMessage }}</div>
        </div>
      </div>
    </div>

    <div v-if="relationDialogOpen" class="kg-dialog-backdrop" @click.self="closeRelationDialog">
      <form class="kg-dialog" @submit.prevent="saveRelation">
        <div class="kg-dialog-head">
          <div>
            <div class="kg-dialog-title">新增 Neo4j 关系</div>
            <div class="kg-dialog-subtitle">在两个知识实体之间建立有向关系</div>
          </div>
          <button type="button" class="kg-dialog-close" title="关闭" @click="closeRelationDialog">×</button>
        </div>

        <label class="kg-field">
          <span>源节点</span>
          <select v-model="relationForm.source_id" required>
            <option v-for="node in nodes" :key="`src-${node.id}`" :value="node.id">
              {{ node.name }} · {{ node.metadata?.kind || node.id }}
            </option>
          </select>
        </label>
        <label class="kg-field">
          <span>目标节点</span>
          <select v-model="relationForm.target_id" required>
            <option v-for="node in nodes" :key="`dst-${node.id}`" :value="node.id">
              {{ node.name }} · {{ node.metadata?.kind || node.id }}
            </option>
          </select>
        </label>
        <label class="kg-field">
          <span>关系类型</span>
          <input
            v-model.trim="relationForm.relation"
            maxlength="64"
            pattern="[A-Za-z][A-Za-z0-9_]*"
            placeholder="例如 DEPENDS_ON"
            required
          >
        </label>
        <label class="kg-field">
          <span>关系属性（JSON）</span>
          <textarea v-model="relationForm.propsText" rows="4" spellcheck="false"></textarea>
        </label>
        <div v-if="relationFormError" class="kg-form-error">{{ relationFormError }}</div>
        <div class="kg-dialog-actions">
          <button type="button" class="kg-btn" @click="closeRelationDialog">取消</button>
          <button type="submit" class="kg-btn kg-btn-primary" :disabled="relationSaving">
            <span v-if="relationSaving" class="kg-spinner"></span>
            <span v-else>保存关系</span>
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api/index.js'

const W = 1480
const H = 940

const RUNTIME_GROUPS = [
  { id: 'entry', label: '入口流量', color: '#38bdf8' },
  { id: 'service', label: '微服务', color: '#22c55e' },
  { id: 'dependency', label: '外部依赖', color: '#fbbf24' },
]

const RUNTIME_RELATIONS = [
  { id: 'call', label: '实时调用', color: '#38bdf8' },
  { id: 'dependency', label: '外部依赖', color: '#fbbf24' },
]

const GRAPH_PALETTE = ['#38bdf8', '#22c55e', '#f59e0b', '#f87171', '#a78bfa', '#14b8a6', '#94a3b8', '#e879f9']

const mode = ref('knowledge')
const loading = ref(false)
const syncing = ref(false)
const relationSaving = ref(false)
const loadError = ref('')
const actionMessage = ref('')
const animOn = ref(true)
const showLabels = ref(true)
const hoveredId = ref(null)
const pinnedId = ref(null)
const selectedEdge = ref(null)
const relationDialogOpen = ref(false)
const relationFormError = ref('')
const graph = ref(emptyGraph())
const svgEl = ref(null)

const relationForm = reactive({
  source_id: '',
  target_id: '',
  relation: 'DEPENDS_ON',
  propsText: '{}',
})

const neo4jConfigured = computed(() => Boolean(graph.value.configured))
const neo4jConnected = computed(() => Boolean(graph.value.connected))

const vb = reactive({ x: 0, y: 0, w: W, h: H })
const drag = reactive({ active: false, sx: 0, sy: 0, vbx0: 0, vby0: 0 })
const vbStr = computed(() => `${vb.x} ${vb.y} ${vb.w} ${vb.h}`)

function emptyGraph() {
  return {
    graph_id: '',
    title: '知识拓扑图',
    subtitle: '',
    source: '',
    groups: [],
    relation_legend: [],
    zones: [],
    nodes: [],
    edges: [],
    stats: {},
  }
}

function safeArray(value) {
  return Array.isArray(value) ? value : []
}

function buildKnowledgeFallbackGraph(reason = '') {
  const groups = [
    { id: 'control', label: 'Control', color: '#38bdf8' },
    { id: 'workload', label: 'Workload', color: '#a78bfa' },
    { id: 'traffic', label: 'Traffic', color: '#22c55e' },
    { id: 'observe', label: 'Observe', color: '#14b8a6' },
    { id: 'aiops', label: 'AIOps', color: '#f87171' },
  ]
  const relationLegend = [
    { id: 'operate', label: 'operate', color: '#38bdf8' },
    { id: 'route', label: 'route', color: '#22c55e' },
    { id: 'observe', label: 'observe', color: '#14b8a6' },
    { id: 'analyze', label: 'analyze', color: '#f87171' },
  ]
  const zones = [
    { id: 'control', label: 'Control Plane', x: 40, y: 70, w: 350, h: 220, color: '#38bdf8' },
    { id: 'workload', label: 'Workloads', x: 40, y: 350, w: 350, h: 250, color: '#a78bfa' },
    { id: 'traffic', label: 'Traffic', x: 450, y: 70, w: 340, h: 220, color: '#22c55e' },
    { id: 'observe', label: 'Observability', x: 850, y: 70, w: 360, h: 220, color: '#14b8a6' },
    { id: 'aiops', label: 'AIOps', x: 850, y: 350, w: 360, h: 250, color: '#f87171' },
  ]
  const nodes = [
    {
      id: 'kubectl',
      name: 'kubectl',
      subtitle: 'CLI / GitOps',
      abbr: 'CLI',
      group: 'control',
      zone: 'control',
      x: 120,
      y: 170,
      size: 28,
      summary: ['Cluster operation entrypoint', 'Submits resource changes to API Server'],
      metadata: { kind: 'client', scope: 'k8s' },
    },
    {
      id: 'apiserver',
      name: 'API Server',
      subtitle: 'REST / Watch',
      abbr: 'API',
      group: 'control',
      zone: 'control',
      x: 245,
      y: 170,
      size: 34,
      summary: ['Unified Kubernetes control-plane entrypoint', 'Serves CRUD and watch traffic'],
      metadata: { kind: 'control-plane', scope: 'k8s' },
    },
    {
      id: 'controller',
      name: 'Controller',
      subtitle: 'Reconcile Loop',
      abbr: 'CTL',
      group: 'control',
      zone: 'control',
      x: 340,
      y: 170,
      size: 28,
      summary: ['Continuously reconciles desired state', 'Drives workload rollout and healing'],
      metadata: { kind: 'controller-manager', scope: 'k8s' },
    },
    {
      id: 'deployment',
      name: 'Deployment',
      subtitle: 'Stateless App',
      abbr: 'DEP',
      group: 'workload',
      zone: 'workload',
      x: 130,
      y: 445,
      size: 30,
      summary: ['Manages stateless replicas', 'Owns rollout strategy for app pods'],
      metadata: { kind: 'workload', scope: 'k8s' },
    },
    {
      id: 'pod',
      name: 'Pod',
      subtitle: 'Runtime Unit',
      abbr: 'POD',
      group: 'workload',
      zone: 'workload',
      x: 255,
      y: 520,
      size: 36,
      summary: ['Smallest runtime scheduling unit', 'Emits logs, metrics, and traces'],
      metadata: { kind: 'workload', scope: 'k8s' },
    },
    {
      id: 'service',
      name: 'Service',
      subtitle: 'Stable Endpoint',
      abbr: 'SVC',
      group: 'traffic',
      zone: 'traffic',
      x: 560,
      y: 160,
      size: 32,
      summary: ['Provides stable endpoint for pods', 'Selects backends by labels'],
      metadata: { kind: 'network', scope: 'k8s' },
    },
    {
      id: 'ingress',
      name: 'Ingress',
      subtitle: 'North-South',
      abbr: 'ING',
      group: 'traffic',
      zone: 'traffic',
      x: 690,
      y: 160,
      size: 30,
      summary: ['Routes external requests into services', 'Carries host/path/TLS rules'],
      metadata: { kind: 'network', scope: 'k8s' },
    },
    {
      id: 'loki',
      name: 'Loki',
      subtitle: 'Logs',
      abbr: 'LOG',
      group: 'observe',
      zone: 'observe',
      x: 965,
      y: 145,
      size: 30,
      summary: ['Collects and queries pod logs', 'Feeds troubleshooting and RCA context'],
      metadata: { kind: 'observability', scope: 'platform' },
    },
    {
      id: 'skywalking',
      name: 'SkyWalking',
      subtitle: 'Tracing',
      abbr: 'APM',
      group: 'observe',
      zone: 'observe',
      x: 1100,
      y: 145,
      size: 30,
      summary: ['Builds service topology and traces', 'Correlates requests across services'],
      metadata: { kind: 'observability', scope: 'platform' },
    },
    {
      id: 'aiops',
      name: 'AI RCA',
      subtitle: 'Diagnosis',
      abbr: 'RCA',
      group: 'aiops',
      zone: 'aiops',
      x: 1035,
      y: 470,
      size: 34,
      pulse: true,
      summary: reason
        ? [`Fallback graph enabled: ${reason}`, 'Backend graph returned empty or failed temporarily']
        : ['Correlates logs, traces, and K8s context', 'Outputs root-cause hints and next actions'],
      metadata: { kind: 'aiops', scope: 'analysis' },
    },
  ]
  const edges = [
    { id: 'kubectl-api', source: 'kubectl', target: 'apiserver', category: 'operate', relation: 'operate', label: 'apply' },
    { id: 'api-controller', source: 'apiserver', target: 'controller', category: 'operate', relation: 'operate', label: 'watch' },
    { id: 'controller-deployment', source: 'controller', target: 'deployment', category: 'operate', relation: 'operate', label: 'reconcile' },
    { id: 'deployment-pod', source: 'deployment', target: 'pod', category: 'operate', relation: 'operate', label: 'owns' },
    { id: 'service-pod', source: 'service', target: 'pod', category: 'route', relation: 'route', label: 'selects' },
    { id: 'ingress-service', source: 'ingress', target: 'service', category: 'route', relation: 'route', label: 'routes' },
    { id: 'pod-loki', source: 'pod', target: 'loki', category: 'observe', relation: 'observe', label: 'logs' },
    { id: 'pod-sw', source: 'pod', target: 'skywalking', category: 'observe', relation: 'observe', label: 'traces' },
    { id: 'loki-aiops', source: 'loki', target: 'aiops', category: 'analyze', relation: 'analyze', label: 'analyzes' },
    { id: 'sw-aiops', source: 'skywalking', target: 'aiops', category: 'analyze', relation: 'analyze', label: 'correlates' },
  ]

  return {
    graph_id: 'knowledge-fallback',
    title: 'K8s Knowledge Topology',
    subtitle: reason ? `Frontend fallback graph · ${reason}` : 'Frontend fallback graph',
    source: 'knowledge-fallback',
    groups,
    relation_legend: relationLegend,
    zones,
    nodes,
    edges,
    stats: {
      groups: groups.length,
      zones: zones.length,
      nodes: nodes.length,
      edges: edges.length,
      details: [
        { label: 'Mode', value: 'Fallback' },
        { label: 'Nodes', value: nodes.length },
        { label: 'Edges', value: edges.length },
      ],
    },
  }
}

function withAlpha(hex, alpha) {
  const raw = String(hex || '').trim()
  if (/^#([0-9a-f]{6})$/i.test(raw)) {
    const value = raw.slice(1)
    const r = parseInt(value.slice(0, 2), 16)
    const g = parseInt(value.slice(2, 4), 16)
    const b = parseInt(value.slice(4, 6), 16)
    return `rgba(${r}, ${g}, ${b}, ${alpha})`
  }
  if (/^rgb/i.test(raw)) return raw
  return `rgba(56, 189, 248, ${alpha})`
}

function deriveNodeAbbr(name) {
  const words = String(name || '')
    .replace(/[^A-Za-z0-9\s/-]/g, ' ')
    .split(/[\s/-]+/)
    .filter(Boolean)
  if (!words.length) return 'N'
  return words.slice(0, 3).map((part) => part[0]).join('').toUpperCase()
}

function sanitizeId(value) {
  return String(value || 'id').replace(/[^a-zA-Z0-9_-]+/g, '-')
}

function makePackets(count = 2, baseDur = 1.8) {
  return Array.from({ length: Math.max(1, count) }, (_, index) => ({
    i: index,
    r: 3 + (count - index) * 0.35,
    dur: baseDur + index * 0.24,
    begin: index * (baseDur / Math.max(count, 1)),
  }))
}

function zoomAt(factor, cx, cy) {
  const nextW = Math.max(460, Math.min(W * 3, vb.w / factor))
  const nextH = nextW * H / W
  vb.x = cx - (cx - vb.x) * (nextW / vb.w)
  vb.y = cy - (cy - vb.y) * (nextH / vb.h)
  vb.w = nextW
  vb.h = nextH
}

function fitView() {
  vb.x = 0
  vb.y = 0
  vb.w = W
  vb.h = H
}

function onWheel(event) {
  if (!svgEl.value) return
  const rect = svgEl.value.getBoundingClientRect()
  const mx = ((event.clientX - rect.left) / rect.width) * vb.w + vb.x
  const my = ((event.clientY - rect.top) / rect.height) * vb.h + vb.y
  zoomAt(event.deltaY < 0 ? 1.12 : 0.88, mx, my)
}

function onDragStart(event) {
  if (event.button !== 0) return
  drag.active = true
  drag.sx = event.clientX
  drag.sy = event.clientY
  drag.vbx0 = vb.x
  drag.vby0 = vb.y
}

function onDragMove(event) {
  if (!drag.active || !svgEl.value) return
  const rect = svgEl.value.getBoundingClientRect()
  const sx = vb.w / rect.width
  const sy = vb.h / rect.height
  vb.x = drag.vbx0 - (event.clientX - drag.sx) * sx
  vb.y = drag.vby0 - (event.clientY - drag.sy) * sy
}

function onDragEnd() {
  drag.active = false
}

function switchMode(nextMode) {
  if (mode.value === nextMode) return
  mode.value = nextMode
  selectedEdge.value = null
  pinnedId.value = null
  actionMessage.value = ''
  closeRelationDialog()
  loadGraph()
}

// 点击固定节点：高亮与提示常驻，再次点击或点空白取消
function togglePin(nodeId) {
  pinnedId.value = pinnedId.value === nodeId ? null : nodeId
  hoveredId.value = pinnedId.value
}
function clearPin() {
  pinnedId.value = null
  hoveredId.value = null
}

function classifyRuntimeNode(node) {
  const name = String(node?.name || '').toLowerCase()
  const type = String(node?.type || '').toLowerCase()
  if (node?.isReal === false) return 'dependency'
  if (type.includes('database') || type.includes('cache') || type.includes('mq')) return 'dependency'
  if (name.includes('gateway') || name.includes('ingress') || name.includes('nginx') || name.includes('edge')) return 'entry'
  return 'service'
}

function runtimeNodeSummary(node, group) {
  const type = String(node?.type || '').trim() || 'Unknown'
  const lines = []
  if (group === 'entry') {
    lines.push('作为入口或网关类服务被 SkyWalking 发现。')
  } else if (group === 'dependency') {
    lines.push('作为外部依赖或虚拟节点存在于运行时调用链中。')
  } else {
    lines.push('作为业务微服务存在于运行时真实调用拓扑中。')
  }
  lines.push(`SkyWalking 类型: ${type}`)
  lines.push(node?.isReal === false ? '节点来源: 虚拟依赖 / 外部组件' : '节点来源: 真实服务实例')
  return lines
}

function normalizeKnowledgeGraph(data) {
  const normalized = {
    ...emptyGraph(),
    ...data,
    groups: safeArray(data?.groups),
    relation_legend: safeArray(data?.relation_legend),
    zones: safeArray(data?.zones),
    nodes: safeArray(data?.nodes),
    edges: safeArray(data?.edges),
  }
  if (!normalized.nodes.length) {
    return buildKnowledgeFallbackGraph('no nodes from /api/topology/knowledge')
  }
  normalized.stats = {
    ...(normalized.stats || {}),
    nodes: normalized.stats?.nodes ?? normalized.nodes.length,
    edges: normalized.stats?.edges ?? normalized.edges.length,
    zones: normalized.stats?.zones ?? normalized.zones.length,
    groups: normalized.stats?.groups ?? normalized.groups.length,
  }
  return normalized
}

function normalizeNeo4jGraph(raw) {
  const rawNodes = safeArray(raw?.nodes)
  const rawEdges = safeArray(raw?.edges)
  const kindNames = [...new Set(rawNodes.map((node) => String(node?.kind || 'entity')))]
  const kindIndex = Object.fromEntries(kindNames.map((kind, index) => [kind, index]))
  const groups = kindNames.map((kind, index) => ({
    id: sanitizeId(kind),
    kind,
    label: kind,
    color: GRAPH_PALETTE[index % GRAPH_PALETTE.length],
  }))
  const groupByKind = Object.fromEntries(groups.map((group) => [group.kind, group]))
  const groupedNodes = Object.fromEntries(kindNames.map((kind) => [kind, []]))
  rawNodes.forEach((node) => {
    const kind = String(node?.kind || 'entity')
    if (!groupedNodes[kind]) groupedNodes[kind] = []
    groupedNodes[kind].push(node)
  })

  const columnCount = Math.min(3, Math.max(1, groups.length))
  const rowCount = Math.max(1, Math.ceil(groups.length / columnCount))
  const gapX = 24
  const gapY = 28
  const marginX = 42
  const marginY = 58
  const zoneW = (W - marginX * 2 - gapX * (columnCount - 1)) / columnCount
  const zoneH = (H - marginY * 2 - gapY * (rowCount - 1)) / rowCount

  const zones = groups.map((group, index) => ({
    id: group.id,
    label: group.label,
    color: group.color,
    x: marginX + (index % columnCount) * (zoneW + gapX),
    y: marginY + Math.floor(index / columnCount) * (zoneH + gapY),
    w: zoneW,
    h: zoneH,
  }))
  const zoneByKind = Object.fromEntries(groups.map((group, index) => [group.kind, zones[index]]))

  const positionedNodes = []
  kindNames.forEach((kind) => {
    const items = groupedNodes[kind] || []
    const zone = zoneByKind[kind]
    if (!zone) return
    const columns = Math.max(1, Math.ceil(Math.sqrt(items.length * Math.max(zone.w / zone.h, 1))))
    const rows = Math.max(1, Math.ceil(items.length / columns))
    const cellW = (zone.w - 48) / columns
    const cellH = (zone.h - 62) / rows
    const radius = Math.max(16, Math.min(28, Math.min(cellW, cellH) * 0.28))
    items.forEach((node, index) => {
      const props = node?.props && typeof node.props === 'object' ? node.props : {}
      const summary = []
      if (node?.env) summary.push(`环境: ${node.env}`)
      Object.entries(props).slice(0, 4).forEach(([key, value]) => summary.push(`${key}: ${String(value)}`))
      positionedNodes.push({
        id: String(node.id),
        name: String(node.name || node.id),
        subtitle: kind,
        abbr: deriveNodeAbbr(node.name || node.id),
        group: groupByKind[kind]?.id || sanitizeId(kind),
        zone: groupByKind[kind]?.id || sanitizeId(kind),
        x: zone.x + 24 + cellW * (index % columns + 0.5),
        y: zone.y + 42 + cellH * (Math.floor(index / columns) + 0.5),
        size: radius,
        summary,
        metadata: { kind, scope: node.source || 'neo4j', env: node.env || '' },
      })
    })
  })

  const relationNames = [...new Set(rawEdges.map((edge) => String(edge?.relation || 'RELATED_TO')))]
  const relationLegend = relationNames.map((relation, index) => ({
    id: sanitizeId(relation),
    relation,
    label: relation,
    color: GRAPH_PALETTE[(index + 2) % GRAPH_PALETTE.length],
  }))
  const relationByName = Object.fromEntries(relationLegend.map((item) => [item.relation, item]))
  const edges = rawEdges.map((edge, index) => {
    const relation = String(edge?.relation || 'RELATED_TO')
    return {
      ...edge,
      id: String(edge?.id || `neo4j-edge-${index}`),
      source: String(edge?.source || ''),
      target: String(edge?.target || ''),
      label: relation,
      relation,
      category: relationByName[relation]?.id || sanitizeId(relation),
      metadata: edge?.props || {},
    }
  })

  return {
    graph_id: 'neo4j-knowledge-graph',
    title: 'Neo4j 知识图谱',
    subtitle: raw?.connected
      ? `数据库 ${raw?.database || 'neo4j'} · 可管理实体关系`
      : (raw?.message || raw?.error || 'Neo4j 未连接'),
    source: 'neo4j',
    configured: Boolean(raw?.configured),
    connected: Boolean(raw?.connected),
    error: raw?.error || '',
    groups,
    relation_legend: relationLegend,
    zones,
    nodes: positionedNodes,
    edges,
    stats: {
      nodes: positionedNodes.length,
      edges: edges.length,
      zones: zones.length,
      groups: groups.length,
      details: [
        { label: '连接', value: raw?.connected ? '正常' : (raw?.configured ? '失败' : '未配置') },
        { label: '数据库', value: raw?.database || '-' },
      ],
    },
  }
}

function normalizeRuntimeGraph(raw) {
  const rawNodes = safeArray(raw?.nodes)
  const rawCalls = safeArray(raw?.calls)
  const degree = {}

  rawCalls.forEach((call) => {
    degree[call.source] = (degree[call.source] || 0) + 1
    degree[call.target] = (degree[call.target] || 0) + 1
  })

  const grouped = { entry: [], service: [], dependency: [] }
  rawNodes.forEach((node) => {
    const group = classifyRuntimeNode(node)
    grouped[group].push({ ...node, group, degree: degree[node.id] || 0 })
  })

  Object.values(grouped).forEach((items) => {
    items.sort((a, b) => b.degree - a.degree || String(a.name).localeCompare(String(b.name)))
  })

  const columns = [
    { id: 'entry', x: 220, y: 110, h: 700, w: 300, label: 'Entry / Gateway' },
    { id: 'service', x: 560, y: 70, h: 780, w: 380, label: 'Service Mesh' },
    { id: 'dependency', x: 990, y: 110, h: 700, w: 320, label: 'Dependencies' },
  ]

  const positionedNodes = []
  columns.forEach((column) => {
    const items = grouped[column.id]
    const gap = column.id === 'service' ? 98 : 112
    const totalHeight = Math.max((items.length - 1) * gap, 0)
    const startY = column.y + column.h / 2 - totalHeight / 2
    items.forEach((node, index) => {
      positionedNodes.push({
        id: node.id,
        name: node.name,
        subtitle: node.type || (node.isReal === false ? 'Virtual Node' : 'Service'),
        abbr: deriveNodeAbbr(node.name),
        group: column.id,
        zone: column.id,
        x: column.x + column.w / 2,
        y: startY + index * gap,
        size: column.id === 'service' ? 34 : 30,
        pulse: column.id === 'service',
        summary: runtimeNodeSummary(node, column.id),
        metadata: {
          kind: node.type || 'runtime',
          scope: node.isReal === false ? 'dependency' : 'service',
        },
      })
    })
  })

  const nodeIndex = Object.fromEntries(positionedNodes.map((node) => [node.id, node]))
  const zones = columns.map((column, index) => ({
    id: column.id,
    label: column.label,
    x: column.x,
    y: column.y,
    w: column.w,
    h: column.h,
    color: RUNTIME_GROUPS[index]?.color || '#38bdf8',
  }))

  const edges = rawCalls.map((call, index) => {
    const target = nodeIndex[call.target]
    const isDependency = target?.group === 'dependency'
    return {
      id: call.id || `call-${index}`,
      source: call.source,
      target: call.target,
      label: isDependency ? 'external call' : 'service call',
      relation: 'calls',
      category: isDependency ? 'dependency' : 'call',
      style: isDependency ? 'dash' : '',
      metadata: {
        detect_points: safeArray(call.detectPoints).join(' / '),
      },
    }
  })

  return {
    graph_id: 'runtime-skywalking',
    title: '运行拓扑图',
    subtitle: 'SkyWalking 实时调用关系',
    source: 'skywalking',
    groups: RUNTIME_GROUPS,
    relation_legend: RUNTIME_RELATIONS,
    zones,
    nodes: positionedNodes,
    edges,
    stats: {
      groups: RUNTIME_GROUPS.length,
      zones: zones.length,
      nodes: positionedNodes.length,
      edges: edges.length,
    },
  }
}

function getErrorMessage(error) {
  return String(error?.response?.data?.detail || error?.message || error || '未知错误')
}

function selectEdge(edge) {
  if (mode.value !== 'neo4j') return
  selectedEdge.value = selectedEdge.value?.id === edge.id ? null : edge
}

function openRelationDialog() {
  if (nodes.value.length < 2) return
  relationForm.source_id = selectedEdge.value?.source || nodes.value[0].id
  relationForm.target_id = selectedEdge.value?.target || nodes.value.find((node) => node.id !== relationForm.source_id)?.id || ''
  relationForm.relation = selectedEdge.value?.relation || 'DEPENDS_ON'
  relationForm.propsText = '{}'
  relationFormError.value = ''
  relationDialogOpen.value = true
}

function closeRelationDialog() {
  relationDialogOpen.value = false
  relationFormError.value = ''
}

async function saveRelation() {
  relationFormError.value = ''
  if (relationForm.source_id === relationForm.target_id) {
    relationFormError.value = '源节点和目标节点不能相同'
    return
  }
  let props = {}
  try {
    props = JSON.parse(relationForm.propsText || '{}')
    if (!props || Array.isArray(props) || typeof props !== 'object') throw new Error('invalid object')
  } catch {
    relationFormError.value = '关系属性必须是 JSON 对象'
    return
  }

  relationSaving.value = true
  try {
    await api.kgUpsertRelation({
      source_id: relationForm.source_id,
      target_id: relationForm.target_id,
      relation: relationForm.relation.toUpperCase(),
      props,
    })
    closeRelationDialog()
    actionMessage.value = 'Neo4j 关系已保存'
    await loadGraph()
  } catch (error) {
    relationFormError.value = getErrorMessage(error)
  } finally {
    relationSaving.value = false
  }
}

async function removeSelectedRelation() {
  const edge = selectedEdge.value
  if (!edge) return
  if (!confirm(`确认删除关系 ${edge.source} -[${edge.relation}]-> ${edge.target}？`)) return
  relationSaving.value = true
  try {
    await api.kgDeleteRelation(edge.source, edge.target, edge.relation)
    selectedEdge.value = null
    actionMessage.value = 'Neo4j 关系已删除'
    await loadGraph()
  } catch (error) {
    actionMessage.value = `删除失败：${getErrorMessage(error)}`
  } finally {
    relationSaving.value = false
  }
}

async function syncNeo4j() {
  syncing.value = true
  actionMessage.value = ''
  try {
    const result = await api.kgBuild()
    if (result?.neo4j?.error) throw new Error(result.neo4j.error)
    actionMessage.value = `同步完成：${result?.nodes || 0} 个节点，${result?.edges || 0} 条关系`
    await loadGraph()
  } catch (error) {
    actionMessage.value = `同步失败：${getErrorMessage(error)}`
  } finally {
    syncing.value = false
  }
}

async function loadGraph() {
  loading.value = true
  loadError.value = ''
  hoveredId.value = null
  selectedEdge.value = null

  try {
    if (mode.value === 'knowledge') {
      graph.value = normalizeKnowledgeGraph(await api.topologyKnowledge())
    } else if (mode.value === 'neo4j') {
      graph.value = normalizeNeo4jGraph(await api.kgGraph({ limit: 240 }))
      if (graph.value.error) loadError.value = graph.value.error
    } else {
      graph.value = normalizeRuntimeGraph(await api.swGetTopology({ hours: 1 }))
    }
    fitView()
  } catch (error) {
    const message = getErrorMessage(error)
    loadError.value = message
    graph.value = mode.value === 'knowledge'
      ? buildKnowledgeFallbackGraph(message)
      : emptyGraph()
    if (mode.value === 'knowledge') fitView()
  } finally {
    loading.value = false
  }
}

const graphTitle = computed(() => {
  if (graph.value.title) return graph.value.title
  if (mode.value === 'neo4j') return 'Neo4j 知识图谱'
  return mode.value === 'knowledge' ? '知识拓扑图' : '运行拓扑图'
})
const graphSubtitle = computed(() => graph.value.subtitle || '')
const sourceLabel = computed(() => {
  if (graph.value.source === 'knowledge-fallback') return 'Source: frontend fallback graph'
  if (mode.value === 'knowledge') return 'Source: backend /api/topology/knowledge'
  if (mode.value === 'neo4j') return `Source: Neo4j / ${graph.value.connected ? 'connected' : 'disconnected'}`
  return 'Source: SkyWalking /api/sw/topology'
})

const emptyMessage = computed(() => {
  if (mode.value !== 'neo4j') return '当前模式没有可展示的节点或关系。'
  if (!graph.value.configured) return '尚未配置 Neo4j 连接，请先设置后端环境变量。'
  if (!graph.value.connected) return graph.value.error || 'Neo4j 当前无法连接。'
  return 'Neo4j 中暂无节点，请点击“同步图谱”。'
})

const nodeGroups = computed(() => safeArray(graph.value.groups))
const groupMap = computed(() => Object.fromEntries(nodeGroups.value.map((group) => [group.id, group])))
const relationLegend = computed(() => {
  const items = safeArray(graph.value.relation_legend)
  if (items.length) return items
  return mode.value === 'runtime' ? RUNTIME_RELATIONS : []
})
const relationMap = computed(() => Object.fromEntries(relationLegend.value.map((item) => [item.id, item])))
const zones = computed(() => safeArray(graph.value.zones))

const nodes = computed(() => safeArray(graph.value.nodes).map((node) => {
  const group = groupMap.value[node.group] || {}
  const color = node.color || group.color || '#38bdf8'
  return {
    ...node,
    r: Number(node.size || node.r || 30),
    color,
    fill: node.fill || withAlpha(color, 0.14),
    abbr: String(node.abbr || deriveNodeAbbr(node.name)).slice(0, 4).toUpperCase(),
    pulse: Boolean(node.pulse) || node.group === 'aiops',
    summary: safeArray(node.summary),
  }
}))

const nodeMap = computed(() => Object.fromEntries(nodes.value.map((node) => [node.id, node])))

function arc(source, target, bend = 0) {
  if (!source || !target) return ''
  const dx = target.x - source.x
  const dy = target.y - source.y
  const len = Math.sqrt(dx * dx + dy * dy) || 1
  const mx = (source.x + target.x) / 2 + (bend ? -dy * bend : 0)
  const my = (source.y + target.y) / 2 + (bend ? dx * bend : 0)
  const ux = dx / len
  const uy = dy / len
  const ra = source.r + 4
  const rb = target.r + 4
  return `M${source.x + ux * ra},${source.y + uy * ra} Q${mx},${my} ${target.x - ux * rb},${target.y - uy * rb}`
}

function edgeMidpoint(source, target, bend = 0) {
  const dx = target.x - source.x
  const dy = target.y - source.y
  return {
    x: (source.x + target.x) / 2 + (bend ? -dy * bend : 0),
    y: (source.y + target.y) / 2 + (bend ? dx * bend : 0),
  }
}

const edges = computed(() => safeArray(graph.value.edges)
  .map((edge, index) => {
    const source = nodeMap.value[edge.source]
    const target = nodeMap.value[edge.target]
    if (!source || !target) return null
    const relation = relationMap.value[edge.category] || {}
    const color = edge.color || relation.color || groupMap.value[source.group]?.color || '#38bdf8'
    const markerId = `kg-marker-${sanitizeId(edge.category || edge.relation || index)}`
    const bend = Number(edge.bend || 0)
    const mid = edgeMidpoint(source, target, bend)
    return {
      ...edge,
      color,
      markerId,
      dash: edge.style === 'dash' ? '6 5' : edge.style === 'dotted' ? '2 5' : '',
      packets: makePackets(edge.category === 'analyze' ? 2 : 3, edge.category === 'analyze' ? 2.2 : 1.7),
      d: arc(source, target, bend),
      labelX: mid.x,
      labelY: mid.y,
    }
  })
  .filter(Boolean))

const edgeMarkers = computed(() => {
  const markers = new Map()
  edges.value.forEach((edge) => {
    if (!markers.has(edge.markerId)) markers.set(edge.markerId, edge.color)
  })
  return Array.from(markers.entries()).map(([id, color]) => ({ id, color }))
})

function isEdgeRelated(edge) {
  if (!hoveredId.value) return true
  return edge.source === hoveredId.value || edge.target === hoveredId.value
}

function isNodeConnected(nodeId) {
  if (!hoveredId.value) return true
  if (nodeId === hoveredId.value) return true
  return edges.value.some((edge) => (
    (edge.source === hoveredId.value || edge.target === hoveredId.value) &&
    (edge.source === nodeId || edge.target === nodeId)
  ))
}

const relatedEdges = computed(() => edges.value.filter((edge) => isEdgeRelated(edge)))
const hoveredNode = computed(() => nodeMap.value[hoveredId.value] || null)

const tooltipLines = computed(() => {
  const node = hoveredNode.value
  if (!node) return []
  const lines = [...safeArray(node.summary)]
  if (node.metadata?.kind) lines.push(`类型: ${node.metadata.kind}`)
  if (node.metadata?.scope) lines.push(`范围: ${node.metadata.scope}`)
  return lines.slice(0, 6)
})

const tooltipW = 292
const tooltipHeight = computed(() => 78 + tooltipLines.value.length * 18)
const tooltipPos = computed(() => {
  const node = hoveredNode.value
  if (!node) return { x: 0, y: 0 }
  let x = node.x + node.r + 18
  let y = node.y - 36
  if (x + tooltipW > W - 20) x = node.x - node.r - tooltipW - 18
  if (y + tooltipHeight.value > H - 18) y = H - tooltipHeight.value - 18
  if (y < 18) y = 18
  return { x, y }
})

const statsChips = computed(() => {
  const modeLabel = mode.value === 'knowledge' ? 'Knowledge' : mode.value === 'neo4j' ? 'Neo4j' : 'Runtime'
  const base = [
    { label: '节点', value: graph.value.stats?.nodes ?? nodes.value.length },
    { label: '关系', value: graph.value.stats?.edges ?? edges.value.length },
    { label: '分区', value: graph.value.stats?.zones ?? zones.value.length },
    { label: '模式', value: modeLabel },
  ]
  const details = safeArray(graph.value.stats?.details)
    .filter((item) => item && item.label != null && item.value != null)
    .slice(0, 4)
    .map((item) => ({ label: item.label, value: item.value }))
  return base.concat(details)
})

onMounted(() => {
  loadGraph()
})
</script>

<style scoped>
.kg-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 640px;
  background:
    radial-gradient(circle at top left, rgba(56, 189, 248, 0.08), transparent 28%),
    radial-gradient(circle at bottom right, rgba(34, 197, 94, 0.06), transparent 24%),
    var(--bg-base);
  color: var(--text-primary);
}

.kg-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 22px 12px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(9, 18, 36, 0.88), rgba(9, 18, 36, 0.68));
  backdrop-filter: blur(10px);
  flex-shrink: 0;
}

.kg-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.kg-brand-mark {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 14px;
  background: rgba(56, 189, 248, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.18);
  box-shadow: 0 10px 30px rgba(56, 189, 248, 0.12);
}

.kg-ring,
.kg-core {
  position: absolute;
  border-radius: 999px;
}

.kg-ring-a {
  inset: 8px;
  border: 1px solid rgba(56, 189, 248, 0.6);
}

.kg-ring-b {
  inset: 13px;
  border: 1px solid rgba(34, 197, 94, 0.55);
}

.kg-core {
  inset: 17px;
  background: linear-gradient(135deg, #38bdf8, #22c55e);
  box-shadow: 0 0 18px rgba(56, 189, 248, 0.28);
}

.kg-title {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.kg-subtitle {
  color: var(--text-secondary);
  font-size: 12px;
  margin-top: 4px;
}

.kg-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.kg-tabs {
  display: inline-flex;
  padding: 3px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(126, 142, 171, 0.18);
}

.kg-tab,
.kg-btn {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: 0.18s ease;
}

.kg-tab {
  min-width: 86px;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
}

.kg-tab.active {
  color: #f8fbff;
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(18, 96, 255, 0.34));
  box-shadow: inset 0 0 0 1px rgba(125, 211, 252, 0.18), 0 10px 24px rgba(18, 96, 255, 0.14);
}

.kg-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.kg-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.kg-toggle input {
  accent-color: var(--accent);
}

.kg-pin-hint {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  color: #7ee0ff;
  background: rgba(56, 139, 253, 0.12);
  border: 1px solid rgba(56, 139, 253, 0.4);
  border-radius: 999px;
  padding: 3px 10px;
  cursor: pointer;
}

.kg-node { cursor: pointer; }
.kg-node.pinned { cursor: default; }

.kg-btn {
  min-width: 56px;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid rgba(126, 142, 171, 0.18);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12px;
  font-weight: 600;
}

.kg-btn:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: rgba(56, 189, 248, 0.28);
  background: rgba(56, 189, 248, 0.08);
}

.kg-btn:disabled {
  opacity: 0.7;
  cursor: wait;
}

.kg-btn-primary {
  color: #f8fbff;
  border-color: rgba(56, 189, 248, 0.42);
  background: rgba(14, 116, 144, 0.3);
}

.kg-btn-danger {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.36);
  background: rgba(127, 29, 29, 0.22);
}

.kg-spinner {
  width: 12px;
  height: 12px;
  display: inline-block;
  border: 2px solid rgba(255, 255, 255, 0.25);
  border-top-color: #7dd3fc;
  border-radius: 50%;
  animation: kgSpin 0.8s linear infinite;
}

.kg-meta,
.kg-legend {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 22px;
  flex-shrink: 0;
}

.kg-meta {
  border-bottom: 1px solid rgba(126, 142, 171, 0.1);
  background: rgba(9, 18, 36, 0.42);
}

.kg-chip-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.kg-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(126, 142, 171, 0.12);
  font-size: 12px;
  color: var(--text-secondary);
}

.kg-chip strong {
  color: var(--text-primary);
  font-size: 13px;
}

.kg-source {
  color: var(--text-muted);
  font-size: 12px;
}

.kg-action-message {
  color: #7dd3fc;
  font-size: 12px;
  flex-basis: 100%;
}

.kg-legend {
  justify-content: flex-start;
  gap: 14px;
  border-bottom: 1px solid rgba(126, 142, 171, 0.08);
  background: rgba(255, 255, 255, 0.02);
  font-size: 12px;
}

.kg-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
}

.kg-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  box-shadow: 0 0 12px rgba(255, 255, 255, 0.12);
}

.kg-line {
  width: 22px;
  height: 2px;
  border-radius: 999px;
}

.kg-legend-divider {
  width: 1px;
  height: 14px;
  background: rgba(126, 142, 171, 0.22);
}

.kg-canvas {
  position: relative;
  flex: 1;
  min-height: 520px;
  overflow: hidden;
}

.kg-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.kg-zone-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.kg-edge {
  animation: kgDash 9s linear infinite;
  cursor: pointer;
  pointer-events: stroke;
}

.kg-edge.selected {
  filter: drop-shadow(0 0 6px currentColor);
}

.kg-edge-label {
  font-size: 9.5px;
  font-weight: 700;
  pointer-events: none;
}

.kg-node {
  cursor: pointer;
  transition: opacity 0.18s ease;
}

.kg-node:hover {
  filter: brightness(1.08);
}

.kg-node-abbr {
  fill: #f8fbff;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.05em;
}

.kg-node-name {
  fill: var(--text-primary);
  font-size: 12px;
  font-weight: 700;
}

.kg-node-subtitle {
  fill: var(--text-muted);
  font-size: 10px;
}

.kg-pulse {
  animation: kgPulse 2.5s ease-in-out infinite;
}

.kg-tooltip-title {
  font-size: 13px;
  font-weight: 700;
}

.kg-tooltip-sub {
  fill: var(--text-secondary);
  font-size: 11px;
}

.kg-tooltip-line {
  fill: var(--text-primary);
  font-size: 11px;
}

.kg-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}

.kg-overlay-error {
  background: rgba(15, 23, 42, 0.15);
}

.kg-overlay-card {
  padding: 18px 20px;
  border-radius: 18px;
  background: rgba(9, 18, 36, 0.92);
  border: 1px solid rgba(248, 113, 113, 0.18);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.24);
  max-width: 420px;
}

.kg-overlay-title {
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 8px;
}

.kg-overlay-text {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.kg-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(3, 7, 18, 0.72);
}

.kg-dialog {
  width: min(520px, 100%);
  max-height: calc(100vh - 40px);
  overflow-y: auto;
  padding: 20px;
  border: 1px solid rgba(126, 142, 171, 0.24);
  border-radius: 8px;
  background: #0d1524;
  box-shadow: 0 24px 72px rgba(0, 0, 0, 0.42);
}

.kg-dialog-head,
.kg-dialog-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.kg-dialog-head {
  margin-bottom: 18px;
}

.kg-dialog-title {
  font-size: 16px;
  font-weight: 700;
}

.kg-dialog-subtitle {
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.kg-dialog-close {
  width: 32px;
  height: 32px;
  border: 1px solid rgba(126, 142, 171, 0.2);
  border-radius: 50%;
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
  font-size: 20px;
  line-height: 1;
}

.kg-field {
  display: grid;
  gap: 7px;
  margin-bottom: 14px;
  color: var(--text-secondary);
  font-size: 12px;
}

.kg-field input,
.kg-field select,
.kg-field textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid rgba(126, 142, 171, 0.24);
  border-radius: 6px;
  padding: 9px 10px;
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.04);
  font: inherit;
}

.kg-field textarea {
  resize: vertical;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
}

.kg-field input:focus,
.kg-field select:focus,
.kg-field textarea:focus {
  outline: none;
  border-color: rgba(56, 189, 248, 0.62);
}

.kg-form-error {
  margin: -4px 0 14px;
  color: #fca5a5;
  font-size: 12px;
}

.kg-dialog-actions {
  justify-content: flex-end;
  padding-top: 4px;
}

@keyframes kgDash {
  to {
    stroke-dashoffset: -42;
  }
}

@keyframes kgPulse {
  0%,
  100% {
    opacity: 0.18;
    transform: scale(1);
  }
  50% {
    opacity: 0.36;
    transform: scale(1.18);
  }
}

@keyframes kgSpin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1100px) {
  .kg-toolbar,
  .kg-meta,
  .kg-legend {
    padding-left: 16px;
    padding-right: 16px;
  }

  .kg-toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .kg-toolbar-actions {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
