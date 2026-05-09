<template>
  <div class="topo-page">
    <!-- 顶部工具栏 -->
    <div class="topo-toolbar">
      <div class="topo-title">
        <span class="topo-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v4M8.5 17.5L12 11M15.5 17.5L12 11"/></svg>
        </span>
        K8s 拓扑流图
      </div>
      <div class="topo-controls">
        <select v-model="selectedNs" class="ns-select" @change="loadData">
          <option value="">全部命名空间</option>
          <option v-for="ns in namespaces" :key="ns" :value="ns">{{ ns }}</option>
        </select>
        <label class="anim-toggle" title="切换流动动效">
          <input type="checkbox" v-model="animEnabled" />
          <span>流动动效</span>
        </label>
        <button class="ctrl-btn" @click="loadData" :disabled="loading">
          <span v-if="loading" class="spin"></span>
          <span v-else>↺</span> 刷新
        </button>
        <button class="ctrl-btn" :class="{ active: viewMode==='pipeline' }" @click="viewMode='pipeline'">部署流程</button>
        <button class="ctrl-btn" :class="{ active: viewMode==='cluster' }"  @click="viewMode='cluster'">集群拓扑</button>
      </div>
    </div>

    <!-- 图例 -->
    <div class="legend-bar">
      <span class="leg-item"><i class="leg-dot ok"></i>Running</span>
      <span class="leg-item"><i class="leg-dot warn"></i>Pending</span>
      <span class="leg-item"><i class="leg-dot err"></i>Failed</span>
      <span class="leg-item"><i class="leg-dot unknown"></i>Unknown</span>
      <span class="leg-sep">|</span>
      <span class="leg-item"><i class="leg-line flow"></i>数据流</span>
      <span class="leg-info" v-if="summary">
        节点 {{ summary.node_count }} &nbsp;·&nbsp;
        Pod {{ summary.pod_count }} &nbsp;·&nbsp;
        Deployment {{ summary.deployment_count }}
      </span>
    </div>

    <!-- 部署流程视图 -->
    <div v-if="viewMode === 'pipeline'" class="pipeline-wrap">
      <svg class="pipeline-svg" :width="pipelineSvgW" :height="pipelineSvgH" ref="pipelineSvg">
        <defs>
          <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="var(--flow-color, #3b82f6)" />
          </marker>
          <!-- 发光滤镜 -->
          <filter id="glow">
            <feGaussianBlur stdDeviation="2.5" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
        </defs>

        <!-- 连接路径 -->
        <g class="edges">
          <path
            v-for="e in pipelineEdges" :key="e.id"
            :id="'ep-' + e.id"
            :d="e.d"
            fill="none"
            :stroke="e.color"
            stroke-width="1.5"
            stroke-dasharray="6 4"
            class="edge-path"
          />
        </g>

        <!-- 流动粒子 -->
        <g v-if="animEnabled" class="packets">
          <g v-for="e in pipelineEdges" :key="'pk-' + e.id">
            <circle
              v-for="(pk, pi) in e.packets"
              :key="pi"
              :r="pk.r"
              :fill="e.color"
              filter="url(#glow)"
              class="packet"
            >
              <animateMotion
                :dur="pk.dur + 's'"
                repeatCount="indefinite"
                :begin="pk.begin + 's'"
              >
                <mpath :href="'#ep-' + e.id" />
              </animateMotion>
            </circle>
          </g>
        </g>

        <!-- 节点 -->
        <g class="nodes">
          <g
            v-for="node in pipelineNodes"
            :key="node.id"
            :transform="`translate(${node.x}, ${node.y})`"
            class="pnode"
            :class="{ selected: selectedNode?.id === node.id }"
            @click="selectedNode = node"
          >
            <!-- 节点卡片背景 -->
            <rect
              :x="-node.w/2" :y="-node.h/2"
              :width="node.w" :height="node.h"
              rx="10" ry="10"
              :class="['node-rect', node.status]"
            />
            <!-- 顶部色条 -->
            <rect
              :x="-node.w/2" :y="-node.h/2"
              :width="node.w" height="4"
              rx="4" ry="4"
              :class="['node-top', node.status]"
            />
            <!-- 图标 -->
            <text :y="-8" text-anchor="middle" class="node-icon">{{ node.icon }}</text>
            <!-- 标签 -->
            <text y="10" text-anchor="middle" class="node-label">{{ node.label }}</text>
            <!-- 副标签 -->
            <text y="24" text-anchor="middle" class="node-sublabel">{{ node.sublabel }}</text>
            <!-- 状态点 -->
            <circle
              :cx="node.w/2 - 8" :cy="-node.h/2 + 8" r="5"
              :class="['status-dot', node.status]"
            />
          </g>
        </g>
      </svg>

      <!-- 节点详情面板 -->
      <transition name="slide-in">
        <div v-if="selectedNode" class="node-detail-panel">
          <div class="ndp-header">
            <span class="ndp-icon">{{ selectedNode.icon }}</span>
            <div>
              <div class="ndp-title">{{ selectedNode.label }}</div>
              <div class="ndp-sub">{{ selectedNode.sublabel }}</div>
            </div>
            <button class="ndp-close" @click="selectedNode = null">✕</button>
          </div>
          <div class="ndp-body">
            <div v-for="(v, k) in selectedNode.detail" :key="k" class="ndp-row">
              <span class="ndp-key">{{ k }}</span>
              <span class="ndp-val" :class="{ ok: v === 'Running' || v === 'Active', err: v === 'Failed' || v === 'Error' }">{{ v }}</span>
            </div>
          </div>
        </div>
      </transition>
    </div>

    <!-- 集群拓扑视图 -->
    <div v-else class="cluster-wrap">
      <div v-if="loading" class="topo-loading">
        <div class="spin-lg"></div>
        <p>加载集群数据...</p>
      </div>
      <div v-else-if="!nodes.length && !pods.length" class="topo-empty">
        <p>暂无集群数据，请检查 K8s 配置</p>
      </div>
      <div v-else class="cluster-layout">
        <!-- 节点列 -->
        <div class="node-col">
          <div class="col-title">集群节点 ({{ nodes.length }})</div>
          <div
            v-for="n in nodes" :key="n.name"
            class="k8s-node-card"
            :class="{ selected: selectedClusterNode === n.name }"
            @click="selectedClusterNode = selectedClusterNode === n.name ? null : n.name"
          >
            <div class="knc-header">
              <span class="knc-dot" :class="n.ready ? 'ok' : 'err'"></span>
              <span class="knc-name">{{ n.name }}</span>
              <span class="knc-role">{{ n.roles }}</span>
            </div>
            <div class="knc-stats">
              <span>CPU: {{ n.cpu || '-' }}</span>
              <span>MEM: {{ n.memory || '-' }}</span>
              <span class="knc-ver">{{ n.version }}</span>
            </div>
            <div class="knc-pods">
              <span>Pods: {{ podsByNode(n.name).length }}</span>
              <span class="knc-pod-ok">{{ podsByNode(n.name).filter(p=>p.phase==='Running').length }} Running</span>
            </div>
          </div>
        </div>

        <!-- SVG 连接线 -->
        <svg class="cluster-svg" ref="clusterSvg" :height="clusterSvgH">
          <defs>
            <marker id="arr2" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L0,6 L6,3 z" fill="#3b82f680"/>
            </marker>
          </defs>
          <g v-for="edge in clusterEdges" :key="edge.id">
            <path
              :id="'ce-'+edge.id"
              :d="edge.d"
              fill="none" stroke="#3b82f640" stroke-width="1.5"
              marker-end="url(#arr2)"
            />
            <g v-if="animEnabled">
              <circle
                v-for="i in 2" :key="i"
                r="3" fill="#60a5fa80"
              >
                <animateMotion :dur="(1.5 + i*0.4)+'s'" repeatCount="indefinite" :begin="(i*0.6)+'s'">
                  <mpath :href="'#ce-'+edge.id"/>
                </animateMotion>
              </circle>
            </g>
          </g>
        </svg>

        <!-- Pod 列 -->
        <div class="pod-col">
          <div class="col-title">
            Pods ({{ filteredPods.length }})
            <span v-if="selectedClusterNode" class="filter-hint">
              · 节点 {{ selectedClusterNode }}
              <button class="clear-filter" @click="selectedClusterNode = null">×</button>
            </span>
          </div>
          <div class="pod-grid">
            <div
              v-for="p in filteredPods.slice(0, 60)" :key="p.name"
              class="pod-chip"
              :class="podPhaseClass(p.phase)"
              :title="`${p.namespace}/${p.name}\n状态: ${p.phase}\n节点: ${p.node_name}`"
            >
              <span class="pod-chip-dot"></span>
              <span class="pod-chip-name">{{ p.name }}</span>
              <span class="pod-chip-ns">{{ p.namespace }}</span>
            </div>
            <div v-if="filteredPods.length > 60" class="pod-more">+{{ filteredPods.length - 60 }} 更多</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { api } from '../api/index.js'

// ── 状态 ──────────────────────────────────────────────────────────────
const viewMode    = ref('pipeline')
const animEnabled = ref(true)
const loading     = ref(false)
const selectedNs  = ref('')
const namespaces  = ref([])
const summary     = ref(null)
const nodes       = ref([])
const pods        = ref([])
const selectedNode        = ref(null)
const selectedClusterNode = ref(null)
const pipelineSvg = ref(null)
const clusterSvg  = ref(null)

// ── 流程视图布局常量 ──────────────────────────────────────────────────
const PIPE_COLS  = 7   // 每行节点数
const NODE_W     = 110
const NODE_H     = 70
const COL_GAP    = 60
const ROW_GAP    = 80
const PAD_X      = 60
const PAD_Y      = 60

const pipelineSvgW = computed(() => PIPE_COLS * (NODE_W + COL_GAP) + PAD_X * 2 - COL_GAP)
const pipelineSvgH = computed(() => Math.ceil(PIPELINE_STAGES.length / PIPE_COLS) * (NODE_H + ROW_GAP) + PAD_Y * 2)

// ── K8s 部署流程阶段定义 ──────────────────────────────────────────────
const PIPELINE_STAGES = [
  { id: 'code',     label: 'Code Push',   sublabel: 'Git Repository', icon: '📝', color: '#6366f1', detail: { 平台: 'GitHub/GitLab', 分支: 'main', 触发: '自动' } },
  { id: 'ci',       label: 'CI Build',    sublabel: 'Jenkins/Actions', icon: '⚙️', color: '#8b5cf6', detail: { 工具: 'Jenkins', 步骤: 'Build & Test', 耗时: '~3min' } },
  { id: 'image',    label: 'Image Build', sublabel: 'Docker Build',   icon: '🐳', color: '#3b82f6', detail: { 基础镜像: 'python:3.11', 仓库: 'Registry', 缓存: '启用' } },
  { id: 'registry', label: 'Registry',    sublabel: 'Image Push',     icon: '📦', color: '#0ea5e9', detail: { 地址: '192.168.9.221:5000', 认证: '已配置', Tag: 'latest' } },
  { id: 'deploy',   label: 'K8s Deploy',  sublabel: 'kubectl apply',  icon: '🚀', color: '#10b981', detail: { 命名空间: 'aiops', 策略: 'RollingUpdate', 副本: '1' } },
  { id: 'rs',       label: 'ReplicaSet',  sublabel: 'Pod Template',   icon: '📋', color: '#14b8a6', detail: { 期望副本: '1', 当前副本: '1', 就绪: '1' } },
  { id: 'pod',      label: 'Pod',         sublabel: 'Running',        icon: '🟢', color: '#22c55e', detail: { 状态: 'Running', 重启次数: '0', IP: '动态分配' } },
  { id: 'svc',      label: 'Service',     sublabel: 'ClusterIP',      icon: '🔌', color: '#f59e0b', detail: { 类型: 'NodePort', 端口: '8000→30800', 协议: 'TCP' } },
  { id: 'ingress',  label: 'Ingress',     sublabel: 'HTTP Route',     icon: '🌐', color: '#ef4444', detail: { 控制器: 'nginx', TLS: '未启用', 路由: '/' } },
  { id: 'user',     label: '用户访问',    sublabel: 'End User',       icon: '👤', color: '#ec4899', detail: { 协议: 'HTTP', 端口: '30090', 响应: '200 OK' } },
]

// ── 计算节点坐标 ─────────────────────────────────────────────────────
const pipelineNodes = computed(() => {
  return PIPELINE_STAGES.map((s, i) => {
    const col = i % PIPE_COLS
    const row = Math.floor(i / PIPE_COLS)
    // 偶数行从左到右，奇数行从右到左（蛇形布局）
    const actualCol = row % 2 === 0 ? col : (PIPE_COLS - 1 - col)
    return {
      ...s,
      w: NODE_W, h: NODE_H,
      x: PAD_X + actualCol * (NODE_W + COL_GAP) + NODE_W / 2,
      y: PAD_Y + row * (NODE_H + ROW_GAP) + NODE_H / 2,
      status: 'ok',
    }
  })
})

// ── 生成边（贝塞尔曲线）──────────────────────────────────────────────
const FLOW_COLORS = ['#6366f1','#3b82f6','#0ea5e9','#10b981','#22c55e','#f59e0b','#ef4444','#ec4899','#8b5cf6']

const pipelineEdges = computed(() => {
  const ns = pipelineNodes.value
  const edges = []
  for (let i = 0; i < ns.length - 1; i++) {
    const a = ns[i], b = ns[i + 1]
    const sameRow = Math.floor(i / PIPE_COLS) === Math.floor((i + 1) / PIPE_COLS)
    let d
    if (sameRow) {
      // 同行：水平S型曲线
      const mx = (a.x + b.x) / 2
      d = `M${a.x + a.w/2},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x - b.w/2},${b.y}`
    } else {
      // 换行：垂直U型曲线（蛇形转弯）
      const row = Math.floor(i / PIPE_COLS)
      const isEvenRow = row % 2 === 0
      const edgeX = isEvenRow ? a.x + a.w/2 + 30 : a.x - a.w/2 - 30
      d = [
        `M${a.x + (isEvenRow ? a.w/2 : -a.w/2)},${a.y}`,
        `C${edgeX},${a.y} ${edgeX},${b.y} ${b.x + (isEvenRow ? -b.w/2 : b.w/2)},${b.y}`,
      ].join(' ')
    }
    // 每条边 2~3 个粒子，不同延迟
    const packets = [
      { r: 4, dur: 2.2, begin: 0 },
      { r: 3, dur: 2.2, begin: 0.8 },
      { r: 2.5, dur: 2.2, begin: 1.5 },
    ]
    edges.push({
      id: `${i}to${i+1}`,
      d,
      color: FLOW_COLORS[i % FLOW_COLORS.length],
      packets,
    })
  }
  return edges
})

// ── 集群拓扑 ─────────────────────────────────────────────────────────
const filteredPods = computed(() => {
  if (!selectedClusterNode.value) return pods.value
  return pods.value.filter(p => p.node_name === selectedClusterNode.value)
})

const clusterSvgH = computed(() => Math.max(300, nodes.value.length * 88))

const clusterEdges = computed(() => {
  const edges = []
  nodes.value.forEach((n, ni) => {
    const nodePods = podsByNode(n.name)
    nodePods.slice(0, 5).forEach((p, pi) => {
      const y1 = ni * 88 + 40
      const y2 = pi * 52 + 26
      edges.push({
        id: `${ni}-${pi}`,
        d: `M5,${y1} C50,${y1} 50,${y2} 95,${y2}`,
      })
    })
  })
  return edges
})

function podsByNode(nodeName) {
  return pods.value.filter(p => p.node_name === nodeName)
}

function podPhaseClass(phase) {
  if (phase === 'Running')   return 'ok'
  if (phase === 'Pending')   return 'warn'
  if (phase === 'Succeeded') return 'ok'
  if (phase === 'Failed')    return 'err'
  return 'unknown'
}

// ── 数据加载 ─────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    const [sumRes, nodeRes, podRes, nsRes] = await Promise.allSettled([
      api.k8sSummary(),
      api.k8sNodes(),
      api.k8sPods(null, selectedNs.value || undefined),
      api.k8sNamespaces(),
    ])
    if (sumRes.status === 'fulfilled') summary.value = sumRes.value?.data ?? sumRes.value
    if (nodeRes.status === 'fulfilled') nodes.value = nodeRes.value?.data ?? nodeRes.value ?? []
    if (podRes.status === 'fulfilled')  pods.value  = podRes.value?.data  ?? podRes.value  ?? []
    if (nsRes.status === 'fulfilled')   namespaces.value = nsRes.value?.data ?? nsRes.value ?? []

    // 用真实数据更新流程节点状态
    await updatePipelineStatus()
  } catch (e) {
    console.error('K8s topology load error:', e)
  } finally {
    loading.value = false
  }
}

async function updatePipelineStatus() {
  // 根据 Pod 运行状态更新 pipeline 节点状态
  const hasRunning = pods.value.some(p => p.phase === 'Running')
  const hasFailed  = pods.value.some(p => p.phase === 'Failed')
  // 找 deploy/pod 节点更新状态
  const deployIdx = PIPELINE_STAGES.findIndex(s => s.id === 'deploy')
  const podIdx    = PIPELINE_STAGES.findIndex(s => s.id === 'pod')
  if (deployIdx >= 0 && pipelineNodes.value[deployIdx]) {
    pipelineNodes.value[deployIdx].status = hasRunning ? 'ok' : hasFailed ? 'err' : 'warn'
  }
  if (podIdx >= 0 && pipelineNodes.value[podIdx]) {
    const running = pods.value.filter(p => p.phase === 'Running').length
    PIPELINE_STAGES[podIdx].sublabel = `Running: ${running}`
    PIPELINE_STAGES[podIdx].detail['运行中'] = String(running)
    PIPELINE_STAGES[podIdx].detail['总数']   = String(pods.value.length)
  }
}

onMounted(loadData)
</script>

<style scoped>
/* ── 布局 ──────────────────────────────────────────────── */
.topo-page {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
  background: var(--bg-base); color: var(--text-primary);
}
.topo-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; border-bottom: 1px solid var(--border);
  background: var(--bg-card); flex-shrink: 0; flex-wrap: wrap; gap: 8px;
}
.topo-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 16px; font-weight: 700;
}
.topo-icon { width: 20px; height: 20px; color: var(--accent); }
.topo-icon svg { width: 20px; height: 20px; }
.topo-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ns-select {
  padding: 5px 10px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--bg-base); color: var(--text-primary); font-size: 12px;
}
.ctrl-btn {
  padding: 5px 12px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--bg-base); color: var(--text-primary); cursor: pointer;
  font-size: 12px; display: inline-flex; align-items: center; gap: 5px; transition: .15s;
}
.ctrl-btn:hover { background: var(--bg-hover); }
.ctrl-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.ctrl-btn:disabled { opacity: .5; cursor: not-allowed; }
.anim-toggle {
  display: flex; align-items: center; gap: 5px; cursor: pointer;
  font-size: 12px; color: var(--text-muted);
}

/* ── 图例 ──────────────────────────────────────────────── */
.legend-bar {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 7px 20px; background: var(--bg-card);
  border-bottom: 1px solid var(--border); font-size: 12px; flex-shrink: 0;
}
.leg-item { display: flex; align-items: center; gap: 5px; color: var(--text-muted); }
.leg-dot  { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.leg-dot.ok      { background: #22c55e; }
.leg-dot.warn    { background: #f59e0b; }
.leg-dot.err     { background: #ef4444; }
.leg-dot.unknown { background: #94a3b8; }
.leg-line { display: inline-block; width: 24px; height: 2px; background: linear-gradient(90deg,#3b82f6,#60a5fa); border-radius: 1px; vertical-align: middle; }
.leg-line.flow { animation: legFlow 1.5s linear infinite; background-size: 200% 100%; }
@keyframes legFlow { from { background-position: 0 0; } to { background-position: -100% 0; } }
.leg-sep  { color: var(--border); }
.leg-info { margin-left: auto; color: var(--text-muted); font-size: 11px; }

/* ── 流程视图 ──────────────────────────────────────────── */
.pipeline-wrap {
  flex: 1; overflow: auto; position: relative; padding: 20px;
  display: flex; gap: 16px;
}
.pipeline-svg { flex-shrink: 0; }

/* 路径动效 */
.edge-path { animation: dashMove 8s linear infinite; }
@keyframes dashMove { to { stroke-dashoffset: -60; } }

/* 节点 */
.pnode { cursor: pointer; transition: filter .2s; }
.pnode:hover { filter: brightness(1.15); }
.pnode.selected .node-rect { filter: drop-shadow(0 0 8px #3b82f6); }

.node-rect {
  fill: var(--bg-card); stroke-width: 1.5;
  transition: all .2s;
}
.node-rect.ok      { stroke: #22c55e44; }
.node-rect.warn    { stroke: #f59e0b44; }
.node-rect.err     { stroke: #ef444444; }
.node-rect:hover   { fill: var(--bg-hover); }

.node-top.ok      { fill: #22c55e; }
.node-top.warn    { fill: #f59e0b; }
.node-top.err     { fill: #ef4444; }
.node-top         { fill: #3b82f6; }

.node-icon  { font-size: 20px; dominant-baseline: middle; }
.node-label { font-size: 11px; font-weight: 700; fill: var(--text-primary); }
.node-sublabel { font-size: 9.5px; fill: var(--text-muted); }

.status-dot { stroke: var(--bg-card); stroke-width: 1.5; }
.status-dot.ok      { fill: #22c55e; }
.status-dot.warn    { fill: #f59e0b; }
.status-dot.err     { fill: #ef4444; animation: pulse-err 1.5s ease-in-out infinite; }
@keyframes pulse-err { 0%,100% { r: 5; opacity: 1; } 50% { r: 7; opacity: .6; } }

/* 粒子流动 */
.packet { filter: url(#glow); }

/* ── 节点详情面板 ────────────────────────────────────────── */
.node-detail-panel {
  width: 220px; flex-shrink: 0; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 14px;
  overflow: hidden; align-self: flex-start; position: sticky; top: 0;
}
.ndp-header {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-hover);
}
.ndp-icon  { font-size: 24px; }
.ndp-title { font-size: 13px; font-weight: 700; }
.ndp-sub   { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.ndp-close { margin-left: auto; background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 16px; }
.ndp-body  { padding: 10px 14px; }
.ndp-row   { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid var(--border); font-size: 12px; }
.ndp-row:last-child { border-bottom: none; }
.ndp-key   { color: var(--text-muted); }
.ndp-val   { font-weight: 600; }
.ndp-val.ok  { color: #22c55e; }
.ndp-val.err { color: #ef4444; }

.slide-in-enter-active, .slide-in-leave-active { transition: all .2s; }
.slide-in-enter-from, .slide-in-leave-to { transform: translateX(20px); opacity: 0; }

/* ── 集群拓扑视图 ────────────────────────────────────────── */
.cluster-wrap {
  flex: 1; overflow: auto; padding: 20px;
}
.topo-loading, .topo-empty {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 200px; color: var(--text-muted); gap: 12px;
}
.cluster-layout {
  display: grid; grid-template-columns: 260px 100px 1fr; gap: 0; min-height: 400px;
}
.node-col, .pod-col {
  display: flex; flex-direction: column; gap: 10px;
}
.col-title {
  font-size: 13px; font-weight: 700; color: var(--text-muted);
  padding: 0 0 8px; border-bottom: 1px solid var(--border); margin-bottom: 4px;
  display: flex; align-items: center; gap: 6px;
}
.filter-hint { font-size: 11px; font-weight: 400; color: var(--accent); }
.clear-filter {
  background: none; border: none; cursor: pointer; color: var(--text-muted);
  font-size: 14px; padding: 0 2px;
}

/* K8s 节点卡片 */
.k8s-node-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; padding: 10px 12px; cursor: pointer; transition: .15s;
}
.k8s-node-card:hover { background: var(--bg-hover); }
.k8s-node-card.selected { border-color: var(--accent); box-shadow: 0 0 0 2px #3b82f630; }
.knc-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.knc-dot    { width: 7px; height: 7px; border-radius: 50%; }
.knc-dot.ok  { background: #22c55e; }
.knc-dot.err { background: #ef4444; animation: pulse-err 1.5s ease-in-out infinite; }
.knc-name   { font-size: 12px; font-weight: 700; flex: 1; }
.knc-role   { font-size: 10px; background: #3b82f615; color: var(--accent); padding: 1px 6px; border-radius: 4px; }
.knc-stats  { display: flex; gap: 8px; font-size: 11px; color: var(--text-muted); flex-wrap: wrap; }
.knc-ver    { margin-left: auto; font-size: 10px; color: var(--text-muted); }
.knc-pods   { display: flex; gap: 8px; font-size: 11px; margin-top: 4px; color: var(--text-muted); }
.knc-pod-ok { color: #22c55e; }

/* SVG 连接 */
.cluster-svg { overflow: visible; width: 100%; }

/* Pod chips */
.pod-grid {
  display: flex; flex-wrap: wrap; gap: 6px; align-content: flex-start;
}
.pod-chip {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 8px; border-radius: 6px; font-size: 11px;
  border: 1px solid transparent; cursor: default; max-width: 220px;
  overflow: hidden;
}
.pod-chip.ok      { background: #22c55e15; border-color: #22c55e30; }
.pod-chip.warn    { background: #f59e0b15; border-color: #f59e0b30; }
.pod-chip.err     { background: #ef444415; border-color: #ef444430; }
.pod-chip.unknown { background: var(--bg-hover); border-color: var(--border); }
.pod-chip-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
}
.ok .pod-chip-dot    { background: #22c55e; }
.warn .pod-chip-dot  { background: #f59e0b; }
.err .pod-chip-dot   { background: #ef4444; }
.unknown .pod-chip-dot { background: #94a3b8; }
.pod-chip-name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; }
.pod-chip-ns   { color: var(--text-muted); font-size: 10px; white-space: nowrap; flex-shrink: 0; }
.pod-more      { font-size: 11px; color: var(--text-muted); padding: 4px 8px; align-self: center; }

/* spinner */
.spin    { width: 13px; height: 13px; border-radius: 50%; border: 2px solid rgba(56,139,253,.2); border-top-color: var(--accent); animation: spin .7s linear infinite; display: inline-block; }
.spin-lg { width: 32px; height: 32px; border-radius: 50%; border: 3px solid rgba(56,139,253,.15); border-top-color: var(--accent); animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
