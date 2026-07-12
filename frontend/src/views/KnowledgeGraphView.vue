<template>
  <div class="kgraph-page">
    <header class="kgraph-header">
      <div class="kgraph-head-left">
        <h1>运维知识图谱</h1>
        <p>CMDB 主机 · K8s 拓扑 · 服务调用链的实体关系图，用于根因分析与影响面评估（Neo4j）。</p>
      </div>
      <div class="kgraph-actions">
        <span class="neo4j-pill" :class="statusClass" :title="statusHint">
          <span class="neo4j-dot"></span>{{ statusText }}
        </span>
        <button class="btn btn-outline" @click="loadGraph" :disabled="loading">
          <span v-if="loading" class="spinner-sm"></span> 刷新
        </button>
        <button class="btn btn-primary" @click="rebuild" :disabled="rebuilding">
          <span v-if="rebuilding" class="spinner-sm"></span>
          {{ rebuilding ? '重建中…' : '重建图谱' }}
        </button>
      </div>
    </header>

    <div class="kgraph-toolbar">
      <div class="kg-search">
        <input v-model.trim="searchText" placeholder="搜索实体（服务/Pod/主机/IP），回车定位并高亮" @keyup.enter="locateEntity" />
        <button v-if="searchText" class="kg-search-clear" @click="clearSearch">✕</button>
      </div>
      <div class="kg-legend">
        <button
          v-for="k in kindLegend"
          :key="k.kind"
          class="kg-legend-chip"
          :class="{ dimmed: hiddenKinds.has(k.kind) }"
          @click="toggleKind(k.kind)"
          :title="hiddenKinds.has(k.kind) ? '点击显示' : '点击隐藏'"
        >
          <i :style="{ background: k.color }"></i>{{ kindLabel(k.kind) }}<b>{{ k.count }}</b>
        </button>
      </div>
      <span class="kg-count">{{ visibleNodes.length }} 节点 · {{ visibleEdges.length }} 关系</span>
    </div>

    <div class="kgraph-body">
      <div class="kgraph-canvas" ref="canvasRef">
        <div v-if="loading" class="kg-overlay"><span class="spinner"></span> 加载图谱…</div>
        <div v-else-if="!connected" class="kg-overlay error">
          <p>{{ statusHint || 'Neo4j 未连接' }}</p>
          <p class="kg-overlay-sub">配置 NEO4J_URI/USERNAME/PASSWORD 后点「重建图谱」同步，或图谱仍可用 SQLite 兜底。</p>
        </div>
        <div v-else-if="!nodes.length" class="kg-overlay">
          <p>图谱为空</p>
          <p class="kg-overlay-sub">点击右上角「重建图谱」，从 CMDB + K8s + SkyWalking 拓扑采集实体关系。</p>
        </div>

        <svg
          v-show="!loading && nodes.length"
          :viewBox="`0 0 ${W} ${H}`"
          class="kg-svg"
          @wheel.prevent="onWheel"
          @mousedown="onCanvasDown"
          @mousemove="onCanvasMove"
          @mouseup="onCanvasUp"
          @mouseleave="onCanvasUp"
        >
          <g :transform="`translate(${pan.x},${pan.y}) scale(${zoom})`">
            <!-- 边 -->
            <g class="kg-edges">
              <line
                v-for="e in visibleEdges"
                :key="e.id"
                :x1="pos(e.source).x" :y1="pos(e.source).y"
                :x2="pos(e.target).x" :y2="pos(e.target).y"
                :class="{ highlight: isEdgeActive(e), fade: activeId && !isEdgeActive(e) }"
                :stroke="relColor(e.relation)"
              />
            </g>
            <!-- 关系标签（仅高亮时显示，避免拥挤） -->
            <g v-if="activeId" class="kg-edge-labels">
              <text
                v-for="e in activeEdges"
                :key="'l'+e.id"
                :x="(pos(e.source).x + pos(e.target).x) / 2"
                :y="(pos(e.source).y + pos(e.target).y) / 2 - 2"
              >{{ e.relation }}</text>
            </g>
            <!-- 节点 -->
            <g
              v-for="n in visibleNodes"
              :key="n.id"
              class="kg-node"
              :class="{ active: n.id === activeId, neighbor: neighborIds.has(n.id), fade: activeId && n.id !== activeId && !neighborIds.has(n.id) }"
              :transform="`translate(${n.x},${n.y})`"
              @mousedown.stop="onNodeDown(n, $event)"
              @click.stop="selectNode(n)"
            >
              <circle :r="nodeR(n)" :fill="kindColor(n.kind)" />
              <text class="kg-node-abbr" dy="0.32em">{{ n.abbr }}</text>
              <text class="kg-node-label" :y="nodeR(n) + 12">{{ shortName(n.name) }}</text>
            </g>
          </g>
        </svg>

        <div class="kg-zoom-ctrl" v-show="nodes.length">
          <button @click="zoomBy(1.2)">＋</button>
          <button @click="zoomBy(0.83)">－</button>
          <button @click="resetView" title="复位">⟲</button>
        </div>
      </div>

      <!-- 详情侧栏 -->
      <aside v-if="selected" class="kgraph-detail">
        <div class="kg-detail-head">
          <span class="kg-detail-kind" :style="{ background: kindColor(selected.kind) }">{{ kindLabel(selected.kind) }}</span>
          <button class="kg-detail-close" @click="clearSelection">✕</button>
        </div>
        <h3 :title="selected.name">{{ selected.name }}</h3>
        <div v-if="selected.env" class="kg-detail-env">环境：{{ selected.env }}</div>

        <div v-if="Object.keys(selected.props || {}).length" class="kg-detail-section">
          <div class="kg-detail-title">属性</div>
          <div v-for="(v, k) in selected.props" :key="k" class="kg-detail-prop">
            <span>{{ k }}</span><b>{{ v }}</b>
          </div>
        </div>

        <div class="kg-detail-section">
          <div class="kg-detail-title">关系（{{ selectedRelations.length }}）</div>
          <div v-if="!selectedRelations.length" class="kg-detail-empty">无直接关系</div>
          <button
            v-for="r in selectedRelations"
            :key="r.id"
            class="kg-detail-rel"
            @click="selectNodeById(r.otherId)"
          >
            <span class="kg-rel-tag" :style="{ borderColor: relColor(r.relation) }">{{ r.relation }}</span>
            <span class="kg-rel-dir">{{ r.dir }}</span>
            <span class="kg-rel-other" :title="r.otherName">{{ shortName(r.otherName) }}</span>
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api/index.js'

const W = 1000
const H = 640

const PALETTE = ['#d97757', '#388bfd', '#3fb950', '#d29922', '#bc8cff', '#39c5cf', '#f85149', '#e3b341', '#7ee787']
const KIND_LABELS = {
  host: '主机', service: '服务', pod: 'Pod', cluster: '集群',
  k8s_node: 'K8s 节点', workload: '工作负载', k8s_service: 'K8s Service', entity: '实体',
}
const REL_LABELS = {
  CALLS: '调用', RUNS_ON: '运行于', SCHEDULED_ON: '调度到', OWNS: '拥有',
  SAME_MACHINE: '同机', MANAGES: '管理',
}

const loading = ref(false)
const rebuilding = ref(false)
const nodes = ref([])
const edges = ref([])
const graphMeta = reactive({ configured: false, connected: false, source: '', message: '' })
const searchText = ref('')
const hiddenKinds = ref(new Set())
const activeId = ref('')
const selected = ref(null)

const canvasRef = ref(null)
const zoom = ref(1)
const pan = reactive({ x: 0, y: 0 })

const nodeMap = computed(() => Object.fromEntries(nodes.value.map(n => [n.id, n])))

// ── 图例 / 颜色 ────────────────────────────────────────────────────
const kindColorMap = computed(() => {
  const kinds = [...new Set(nodes.value.map(n => n.kind))]
  return Object.fromEntries(kinds.map((k, i) => [k, PALETTE[i % PALETTE.length]]))
})
function kindColor(kind) { return kindColorMap.value[kind] || '#888' }
function kindLabel(kind) { return KIND_LABELS[kind] || kind }

const relColorMap = computed(() => {
  const rels = [...new Set(edges.value.map(e => e.relation))]
  return Object.fromEntries(rels.map((r, i) => [r, PALETTE[(i + 3) % PALETTE.length]]))
})
function relColor(rel) { return relColorMap.value[rel] || '#5a6270' }

const kindLegend = computed(() => {
  const counts = {}
  nodes.value.forEach(n => { counts[n.kind] = (counts[n.kind] || 0) + 1 })
  return Object.keys(counts).map(kind => ({ kind, count: counts[kind], color: kindColor(kind) }))
})

// ── 可见性过滤 ────────────────────────────────────────────────────
const visibleNodes = computed(() => nodes.value.filter(n => !hiddenKinds.value.has(n.kind)))
const visibleNodeIds = computed(() => new Set(visibleNodes.value.map(n => n.id)))
const visibleEdges = computed(() =>
  edges.value.filter(e => visibleNodeIds.value.has(e.source) && visibleNodeIds.value.has(e.target))
)

function toggleKind(kind) {
  const next = new Set(hiddenKinds.value)
  next.has(kind) ? next.delete(kind) : next.add(kind)
  hiddenKinds.value = next
}

// ── 状态 ──────────────────────────────────────────────────────────
const connected = computed(() => graphMeta.connected || (graphMeta.source === 'sqlite' && nodes.value.length > 0))
const statusText = computed(() => {
  if (graphMeta.connected) return `Neo4j 已连接 · ${graphMeta.source || 'neo4j'}`
  if (graphMeta.configured) return 'Neo4j 未连接'
  return nodes.value.length ? 'SQLite 兜底' : '未配置'
})
const statusClass = computed(() => graphMeta.connected ? 'ok' : (graphMeta.configured ? 'warn' : 'muted'))
const statusHint = computed(() => graphMeta.message || graphMeta.error || '')

// ── 位置访问（供边使用）──────────────────────────────────────────
function pos(id) { return nodeMap.value[id] || { x: W / 2, y: H / 2 } }
function nodeR(n) { return n.kind === 'cluster' ? 22 : (n.kind === 'host' || n.kind === 'k8s_node' ? 17 : 13) }
function shortName(name) {
  const s = String(name || '')
  return s.length > 22 ? s.slice(0, 21) + '…' : s
}
function deriveAbbr(name) {
  const s = String(name || '').replace(/^[a-z_]+:/, '')
  const tail = s.includes('/') ? s.split('/').pop() : s
  return (tail || s).slice(0, 3).toUpperCase()
}

// ── 高亮 / 选择 ────────────────────────────────────────────────────
const neighborIds = computed(() => {
  const ids = new Set()
  if (!activeId.value) return ids
  edges.value.forEach(e => {
    if (e.source === activeId.value) ids.add(e.target)
    if (e.target === activeId.value) ids.add(e.source)
  })
  return ids
})
const activeEdges = computed(() =>
  visibleEdges.value.filter(e => e.source === activeId.value || e.target === activeId.value)
)
function isEdgeActive(e) {
  return activeId.value && (e.source === activeId.value || e.target === activeId.value)
}

const selectedRelations = computed(() => {
  if (!selected.value) return []
  const id = selected.value.id
  const out = []
  edges.value.forEach(e => {
    if (e.source === id) out.push({ id: e.id, relation: e.relation, dir: '→', otherId: e.target, otherName: nodeMap.value[e.target]?.name || e.target })
    else if (e.target === id) out.push({ id: e.id, relation: e.relation, dir: '←', otherId: e.source, otherName: nodeMap.value[e.source]?.name || e.source })
  })
  return out
})

function selectNode(n) {
  selected.value = n
  activeId.value = n.id
}
function selectNodeById(id) {
  const n = nodeMap.value[id]
  if (n) selectNode(n)
}
function clearSelection() {
  selected.value = null
  activeId.value = ''
}

function locateEntity() {
  const q = searchText.value.trim().toLowerCase()
  if (!q) return
  const hit = nodes.value.find(n =>
    n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
  if (hit) {
    selectNode(hit)
    // 居中到该节点
    pan.x = W / 2 - hit.x * zoom.value
    pan.y = H / 2 - hit.y * zoom.value
  }
}
function clearSearch() { searchText.value = ''; clearSelection() }

// ── 缩放 / 平移 ────────────────────────────────────────────────────
function zoomBy(f) { zoom.value = Math.max(0.3, Math.min(3, zoom.value * f)) }
function onWheel(e) { zoomBy(e.deltaY < 0 ? 1.1 : 0.9) }
function resetView() { zoom.value = 1; pan.x = 0; pan.y = 0 }

let panning = false
let panStart = null
let draggingNode = null
function onCanvasDown(e) {
  if (draggingNode) return
  panning = true
  panStart = { x: e.clientX - pan.x, y: e.clientY - pan.y }
}
function onCanvasMove(e) {
  if (draggingNode) {
    const rect = canvasRef.value.getBoundingClientRect()
    const scaleX = W / rect.width
    draggingNode.x = (e.clientX - rect.left) * scaleX / zoom.value - pan.x / zoom.value
    draggingNode.y = (e.clientY - rect.top) * scaleX / zoom.value - pan.y / zoom.value
    draggingNode.fixed = true
    return
  }
  if (panning && panStart) { pan.x = e.clientX - panStart.x; pan.y = e.clientY - panStart.y }
}
function onCanvasUp() { panning = false; panStart = null; draggingNode = null }
function onNodeDown(n) { draggingNode = n }

// ── 力导向布局（简易 Verlet：斥力 + 弹簧 + 向心）─────────────────
let animHandle = null
function runLayout() {
  cancelAnimationFrame(animHandle)
  const list = nodes.value
  if (!list.length) return
  // 初始随机分布
  list.forEach((n, i) => {
    if (n.x == null) {
      const angle = (i / list.length) * Math.PI * 2
      n.x = W / 2 + Math.cos(angle) * 200 + (Math.random() - 0.5) * 60
      n.y = H / 2 + Math.sin(angle) * 160 + (Math.random() - 0.5) * 60
      n.vx = 0; n.vy = 0
    }
  })
  const idx = Object.fromEntries(list.map((n, i) => [n.id, i]))
  const links = edges.value
    .map(e => ({ s: idx[e.source], t: idx[e.target] }))
    .filter(l => l.s != null && l.t != null)

  let ticks = 0
  const MAX_TICKS = 260
  function step() {
    const k = 0.045
    // 斥力（O(n^2)，图谱节点数受后端限量，规模可控）
    for (let i = 0; i < list.length; i++) {
      const a = list[i]
      for (let j = i + 1; j < list.length; j++) {
        const b = list[j]
        let dx = a.x - b.x, dy = a.y - b.y
        let d2 = dx * dx + dy * dy || 0.01
        const rep = 2600 / d2
        const d = Math.sqrt(d2)
        const fx = (dx / d) * rep, fy = (dy / d) * rep
        a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy
      }
    }
    // 弹簧
    links.forEach(l => {
      const a = list[l.s], b = list[l.t]
      let dx = b.x - a.x, dy = b.y - a.y
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01
      const f = (d - 110) * 0.02
      const fx = (dx / d) * f, fy = (dy / d) * f
      a.vx += fx; a.vy += fy; b.vx -= fx; b.vy -= fy
    })
    // 向心 + 阻尼 + 位移
    list.forEach(n => {
      if (n.fixed) { n.vx = 0; n.vy = 0; return }
      n.vx += (W / 2 - n.x) * 0.006
      n.vy += (H / 2 - n.y) * 0.006
      n.vx *= 0.86; n.vy *= 0.86
      n.x += n.vx * k * 20
      n.y += n.vy * k * 20
      n.x = Math.max(30, Math.min(W - 30, n.x))
      n.y = Math.max(30, Math.min(H - 30, n.y))
    })
    ticks++
    if (ticks < MAX_TICKS) animHandle = requestAnimationFrame(step)
  }
  step()
}

// ── 数据加载 ──────────────────────────────────────────────────────
function normalize(raw) {
  const rawNodes = Array.isArray(raw?.nodes) ? raw.nodes : []
  const rawEdges = Array.isArray(raw?.edges) ? raw.edges : []
  nodes.value = rawNodes.map(n => ({
    id: String(n.id),
    name: String(n.name || n.id),
    kind: String(n.kind || 'entity'),
    env: n.env || '',
    props: (n.props && typeof n.props === 'object') ? n.props : {},
    abbr: deriveAbbr(n.name || n.id),
    x: null, y: null, vx: 0, vy: 0, fixed: false,
  }))
  edges.value = rawEdges.map((e, i) => ({
    id: String(e.id || `e${i}`),
    source: String(e.source || ''),
    target: String(e.target || ''),
    relation: String(e.relation || 'RELATED_TO'),
  })).filter(e => e.source && e.target)
  graphMeta.configured = Boolean(raw?.configured)
  graphMeta.connected = Boolean(raw?.connected)
  graphMeta.source = raw?.source || ''
  graphMeta.message = raw?.message || ''
  graphMeta.error = raw?.error || ''
}

async function loadGraph() {
  loading.value = true
  try {
    const raw = await api.kgGraph({ limit: 300 })
    normalize(raw)
    clearSelection()
    resetView()
    runLayout()
  } catch (e) {
    graphMeta.message = String(e?.message || e)
  } finally {
    loading.value = false
  }
}

async function rebuild() {
  rebuilding.value = true
  try {
    await api.kgBuild()
    await loadGraph()
  } catch (e) {
    graphMeta.message = `重建失败：${e?.message || e}`
  } finally {
    rebuilding.value = false
  }
}

onMounted(loadGraph)
onBeforeUnmount(() => cancelAnimationFrame(animHandle))
</script>

<style scoped>
.kgraph-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; background: var(--bg-base); color: var(--text-primary); }
.kgraph-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 18px 22px 10px; }
.kgraph-header h1 { font-size: 20px; margin: 0 0 4px; }
.kgraph-header p { margin: 0; font-size: 13px; color: var(--text-muted); }
.kgraph-actions { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
.btn { border: 1px solid transparent; border-radius: 7px; padding: 7px 14px; cursor: pointer; font-size: 13px; display: inline-flex; align-items: center; gap: 6px; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-outline { background: var(--bg-card); border-color: var(--border); color: var(--text-primary); }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.neo4j-pill { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; padding: 5px 11px; border-radius: 999px; border: 1px solid var(--border); background: var(--bg-card); }
.neo4j-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-muted); }
.neo4j-pill.ok { color: var(--success); border-color: rgba(63,185,80,.35); }
.neo4j-pill.ok .neo4j-dot { background: var(--success); }
.neo4j-pill.warn { color: var(--warning); }
.neo4j-pill.warn .neo4j-dot { background: var(--warning); }

.kgraph-toolbar { display: flex; align-items: center; gap: 14px; padding: 4px 22px 12px; flex-wrap: wrap; }
.kg-search { position: relative; }
.kg-search input { width: 300px; max-width: 42vw; border: 1px solid var(--border); border-radius: 7px; background: var(--bg-input); color: var(--text-primary); padding: 7px 28px 7px 10px; font-size: 13px; outline: none; }
.kg-search input:focus { border-color: var(--accent); }
.kg-search-clear { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); border: none; background: none; color: var(--text-muted); cursor: pointer; }
.kg-legend { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.kg-legend-chip { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; padding: 3px 9px; border: 1px solid var(--border); border-radius: 999px; background: var(--bg-card); color: var(--text-secondary); cursor: pointer; }
.kg-legend-chip.dimmed { opacity: .4; }
.kg-legend-chip i { width: 9px; height: 9px; border-radius: 50%; }
.kg-legend-chip b { color: var(--text-primary); }
.kg-count { margin-left: auto; font-size: 12px; color: var(--text-muted); }

.kgraph-body { flex: 1; display: flex; min-height: 0; padding: 0 22px 18px; gap: 14px; }
.kgraph-canvas { position: relative; flex: 1; min-width: 0; border: 1px solid var(--border); border-radius: 12px; background: var(--bg-card); overflow: hidden; }
.kg-svg { width: 100%; height: 100%; display: block; cursor: grab; }
.kg-svg:active { cursor: grabbing; }
.kg-edges line { stroke-width: 1.2; opacity: .5; }
.kg-edges line.highlight { stroke-width: 2.2; opacity: 1; }
.kg-edges line.fade { opacity: .12; }
.kg-edge-labels text { font-size: 9px; fill: var(--text-secondary); text-anchor: middle; paint-order: stroke; }
.kg-node { cursor: pointer; }
.kg-node circle { stroke: var(--bg-card); stroke-width: 2; transition: opacity .15s; }
.kg-node.active circle { stroke: #fff; stroke-width: 3; }
.kg-node.fade { opacity: .22; }
.kg-node-abbr { font-size: 9px; fill: #fff; text-anchor: middle; font-weight: 700; pointer-events: none; }
.kg-node-label { font-size: 10px; fill: var(--text-secondary); text-anchor: middle; pointer-events: none; }
.kg-node.active .kg-node-label { fill: var(--text-primary); font-weight: 600; }

.kg-overlay { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--text-muted); font-size: 13px; text-align: center; padding: 20px; }
.kg-overlay.error { color: var(--warning); }
.kg-overlay-sub { font-size: 12px; color: var(--text-muted); max-width: 460px; }
.kg-zoom-ctrl { position: absolute; right: 12px; bottom: 12px; display: flex; flex-direction: column; gap: 4px; }
.kg-zoom-ctrl button { width: 28px; height: 28px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-base); color: var(--text-secondary); cursor: pointer; font-size: 14px; }
.kg-zoom-ctrl button:hover { border-color: var(--accent); color: var(--accent); }

.kgraph-detail { width: 300px; flex-shrink: 0; border: 1px solid var(--border); border-radius: 12px; background: var(--bg-card); padding: 14px 16px; overflow-y: auto; }
.kg-detail-head { display: flex; align-items: center; justify-content: space-between; }
.kg-detail-kind { font-size: 11px; color: #fff; padding: 2px 8px; border-radius: 6px; }
.kg-detail-close { border: none; background: none; color: var(--text-muted); cursor: pointer; font-size: 15px; }
.kgraph-detail h3 { margin: 10px 0 4px; font-size: 15px; word-break: break-all; }
.kg-detail-env { font-size: 12px; color: var(--text-muted); margin-bottom: 10px; }
.kg-detail-section { margin-top: 14px; }
.kg-detail-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 7px; }
.kg-detail-prop { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; padding: 3px 0; border-bottom: 1px solid var(--border-light, var(--border)); }
.kg-detail-prop span { color: var(--text-muted); }
.kg-detail-prop b { color: var(--text-primary); word-break: break-all; text-align: right; }
.kg-detail-empty { font-size: 12px; color: var(--text-muted); }
.kg-detail-rel { display: flex; align-items: center; gap: 7px; width: 100%; text-align: left; border: 1px solid var(--border); border-radius: 7px; background: var(--bg-base); color: var(--text-primary); padding: 6px 8px; margin-bottom: 5px; cursor: pointer; }
.kg-detail-rel:hover { border-color: var(--accent); }
.kg-rel-tag { font-size: 10px; padding: 1px 6px; border-radius: 4px; border: 1px solid; background: transparent; flex-shrink: 0; }
.kg-rel-dir { color: var(--text-muted); }
.kg-rel-other { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.spinner, .spinner-sm { display: inline-block; border-radius: 50%; border: 2px solid var(--border); border-top-color: var(--accent); animation: kgspin .7s linear infinite; }
.spinner { width: 22px; height: 22px; }
.spinner-sm { width: 13px; height: 13px; }
@keyframes kgspin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .kgraph-detail { display: none; }
}
</style>
