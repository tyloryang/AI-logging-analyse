<template>
  <div class="arch-page" ref="pageEl">
    <!-- 顶部控制栏 -->
    <div class="arch-toolbar">
      <div class="arch-brand">
        <svg class="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/>
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>
        </svg>
        <span>AIOps 系统架构</span>
        <span class="arch-subtitle">服务拓扑 & 调用关系</span>
      </div>
      <div class="arch-controls">
        <div class="view-tabs">
          <button :class="['vtab', { active: view === 'arch' }]" @click="view='arch'">系统架构图</button>
          <button :class="['vtab', { active: view === 'k8s' }]" @click="view='k8s'; loadK8s()">K8s 服务图</button>
        </div>
        <label class="toggle-pill">
          <input type="checkbox" v-model="animOn"/>
          <span class="pill-track"><span class="pill-thumb"></span></span>
          <span>流动动效</span>
        </label>
        <button class="ctrl-btn" @click="view==='k8s' ? loadK8s() : null" :disabled="loading">
          <span v-if="loading" class="spin-sm"></span>
          <span v-else>↺</span>
        </button>
      </div>
    </div>

    <!-- 系统架构图 -->
    <div v-show="view === 'arch'" class="canvas-wrap" ref="archWrap">
      <svg
        class="arch-svg"
        :viewBox="`0 0 ${SVG_W} ${SVG_H}`"
        preserveAspectRatio="xMidYMid meet"
        ref="archSvg"
        @mousemove="onMouseMove"
        @mouseleave="tooltip.show = false"
      >
        <defs>
          <!-- 背景网格 -->
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40,0 L0,0 L0,40" fill="none" stroke="rgba(99,132,255,0.12)" stroke-width="1"/>
          </pattern>
          <!-- 粒子发光 -->
          <filter id="glow-blue" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="glow-green" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.5" result="blur"/>
            <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="node-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="rgba(0,0,0,0.4)"/>
          </filter>
          <!-- 箭头 -->
          <marker id="arr-blue" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#3b82f6"/>
          </marker>
          <marker id="arr-green" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#22c55e"/>
          </marker>
          <marker id="arr-orange" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#f59e0b"/>
          </marker>
          <marker id="arr-purple" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" fill="#a855f7"/>
          </marker>
          <!-- 渐变 -->
          <linearGradient id="grad-blue" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#dbeafe" stop-opacity="1"/>
            <stop offset="100%" stop-color="#eff6ff" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-green" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#dcfce7" stop-opacity="1"/>
            <stop offset="100%" stop-color="#f0fdf4" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-orange" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#fef3c7" stop-opacity="1"/>
            <stop offset="100%" stop-color="#fffbeb" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-purple" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#f3e8ff" stop-opacity="1"/>
            <stop offset="100%" stop-color="#faf5ff" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-teal" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#ccfbf1" stop-opacity="1"/>
            <stop offset="100%" stop-color="#f0fdfa" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-red" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#fee2e2" stop-opacity="1"/>
            <stop offset="100%" stop-color="#fff5f5" stop-opacity="1"/>
          </linearGradient>
        </defs>

        <!-- 背景 -->
        <rect width="100%" height="100%" fill="#f8fafc"/>
        <rect width="100%" height="100%" fill="url(#grid)"/>

        <!-- 层标签 -->
        <g class="layer-labels">
          <text v-for="lbl in LAYER_LABELS" :key="lbl.id"
            :x="30" :y="lbl.y"
            class="layer-txt" text-anchor="start" dominant-baseline="middle">
            {{ lbl.text }}
          </text>
          <line v-for="lbl in LAYER_LABELS" :key="'l'+lbl.id"
            :x1="100" :y1="lbl.y" :x2="SVG_W - 20" :y2="lbl.y"
            stroke="rgba(99,132,255,0.08)" stroke-width="1" stroke-dasharray="4 8"/>
        </g>

        <!-- 连接线（先渲染在节点之下） -->
        <g class="edges">
          <path v-for="e in archEdges" :key="e.id"
            :id="'ae-' + e.id"
            :d="e.d"
            fill="none"
            :stroke="e.color + '55'"
            stroke-width="1.5"
            stroke-dasharray="6 5"
            class="edge-dash"
            :marker-end="'url(#arr-' + e.marker + ')'"
          />
        </g>

        <!-- 流动粒子 -->
        <g v-if="animOn" class="particles">
          <g v-for="e in archEdges" :key="'pk-'+e.id">
            <circle
              v-for="pk in e.packets" :key="pk.key"
              :r="pk.r"
              :fill="e.color"
              :filter="'url(#glow-' + (e.glowType || 'blue') + ')'"
            >
              <animateMotion :dur="pk.dur+'s'" repeatCount="indefinite" :begin="pk.begin+'s'" rotate="auto">
                <mpath :href="'#ae-'+e.id"/>
              </animateMotion>
            </circle>
          </g>
        </g>

        <!-- 节点 -->
        <g class="nodes" filter="url(#node-shadow)">
          <g v-for="nd in archNodes" :key="nd.id"
            class="arch-node"
            :class="{ hovered: hoveredNode === nd.id }"
            :transform="`translate(${nd.x},${nd.y})`"
            @mouseenter="hoveredNode=nd.id; showTooltip(nd, $event)"
            @mouseleave="hoveredNode=null; tooltip.show=false"
          >
            <!-- 光晕脉冲背景 -->
            <circle v-if="nd.pulse" cx="0" cy="0" :r="nd.w*0.6" :fill="nd.color+'15'" class="node-pulse"/>

            <!-- 节点背景 -->
            <rect :x="-nd.w/2" :y="-nd.h/2" :width="nd.w" :height="nd.h"
              rx="12" ry="12"
              :fill="'url(#grad-' + nd.grad + ')'"
              :stroke="nd.color + '80'"
              stroke-width="1.5"
            />
            <!-- 顶部彩条 -->
            <rect :x="-nd.w/2" :y="-nd.h/2" :width="nd.w" height="3"
              rx="12" :fill="nd.color"/>

            <!-- 图标 -->
            <text x="0" :y="-6" text-anchor="middle" dominant-baseline="middle"
              class="node-icon">{{ nd.icon }}</text>

            <!-- 主标签 -->
            <text x="0" y="10" text-anchor="middle" class="node-name">{{ nd.name }}</text>

            <!-- 端口/版本 -->
            <text v-if="nd.port" x="0" y="24" text-anchor="middle" class="node-port">{{ nd.port }}</text>

            <!-- 状态点 -->
            <circle :cx="nd.w/2-8" :cy="-nd.h/2+8" r="5"
              :fill="nd.status==='ok' ? '#22c55e' : nd.status==='warn' ? '#f59e0b' : '#6b7280'"
              :class="nd.status==='ok' ? 'status-pulse-ok' : ''"/>

            <!-- 选中高亮边框 -->
            <rect v-if="hoveredNode===nd.id"
              :x="-nd.w/2-2" :y="-nd.h/2-2" :width="nd.w+4" :height="nd.h+4"
              rx="13" fill="none" :stroke="nd.color" stroke-width="2"
              class="hover-ring"
            />
          </g>
        </g>

        <!-- 分组框（K8s Cluster、外部服务） -->
        <g class="group-boxes">
          <rect v-for="grp in GROUPS" :key="grp.id"
            :x="grp.x" :y="grp.y" :width="grp.w" :height="grp.h"
            rx="16" fill="none" :stroke="grp.color" stroke-width="1"
            stroke-dasharray="8 4" :fill-opacity="0.02"
          />
          <text v-for="grp in GROUPS" :key="'gt'+grp.id"
            :x="grp.x + 14" :y="grp.y + 16"
            class="grp-label" :fill="grp.color">{{ grp.label }}</text>
        </g>

      </svg>

      <!-- 悬浮工具提示 -->
      <div v-if="tooltip.show" class="node-tooltip"
        :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
        <div class="tip-header">
          <span class="tip-icon">{{ tooltip.icon }}</span>
          <span class="tip-name">{{ tooltip.name }}</span>
          <span class="tip-badge" :class="tooltip.status">{{ tooltip.statusText }}</span>
        </div>
        <div class="tip-rows">
          <div v-for="r in tooltip.rows" :key="r.k" class="tip-row">
            <span class="tip-key">{{ r.k }}</span>
            <span class="tip-val">{{ r.v }}</span>
          </div>
        </div>
        <div v-if="tooltip.calls?.length" class="tip-calls">
          <div class="tip-calls-title">调用关系</div>
          <div v-for="c in tooltip.calls" :key="c" class="tip-call-item">→ {{ c }}</div>
        </div>
      </div>

      <!-- 图例 -->
      <div class="arch-legend">
        <div class="leg-row"><span class="leg-line blue"></span>HTTP 调用</div>
        <div class="leg-row"><span class="leg-line green"></span>数据读写</div>
        <div class="leg-row"><span class="leg-line orange"></span>告警推送</div>
        <div class="leg-row"><span class="leg-line purple"></span>AI 推理</div>
        <div class="leg-sep"></div>
        <div class="leg-row"><span class="leg-dot ok"></span>健康</div>
        <div class="leg-row"><span class="leg-dot warn"></span>告警</div>
        <div class="leg-row"><span class="leg-dot gray"></span>未知</div>
      </div>
    </div>

    <!-- K8s 服务图 -->
    <div v-show="view === 'k8s'" class="k8s-wrap">
      <div v-if="loading" class="k8s-loading">
        <div class="spin-lg"></div><p>加载 K8s 集群数据...</p>
      </div>
      <div v-else-if="!k8sNodes.length" class="k8s-empty">
        <p>未获取到集群数据，请检查 K8s 配置</p>
      </div>
      <svg v-else
        class="k8s-svg"
        :viewBox="`0 0 ${K8S_W} ${k8sSvgH}`"
        preserveAspectRatio="xMidYMid meet"
        ref="k8sSvg"
      >
        <defs>
          <pattern id="k8s-grid" width="32" height="32" patternUnits="userSpaceOnUse">
            <path d="M32,0 L0,0 L0,32" fill="none" stroke="rgba(99,132,255,0.10)" stroke-width="1"/>
          </pattern>
          <filter id="k8s-glow">
            <feGaussianBlur stdDeviation="3" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <marker id="k8s-arr" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L7,3 z" fill="#3b82f680"/>
          </marker>
        </defs>

        <rect width="100%" height="100%" fill="#f8fafc"/>
        <rect width="100%" height="100%" fill="url(#k8s-grid)"/>

        <!-- Node 卡片行 -->
        <g v-for="(nd, ni) in k8sNodes" :key="nd.name">
          <!-- Node 背景 -->
          <rect :x="20" :y="ni*K8S_ROW_H + 20"
            width="200" :height="K8S_ROW_H - 24"
            rx="10" fill="#eff6ff" stroke="#93c5fd" stroke-width="1"/>
          <text :x="32" :y="ni*K8S_ROW_H + 42" class="k8s-node-name">{{ nd.name }}</text>
          <text :x="32" :y="ni*K8S_ROW_H + 58" class="k8s-node-role">{{ nd.roles }} · {{ nd.version }}</text>
          <circle :cx="196" :cy="ni*K8S_ROW_H + 42" r="6"
            :fill="nd.ready ? '#22c55e' : '#ef4444'"
            :class="nd.ready ? 'k8s-dot-pulse' : ''"/>

          <!-- Pod chips -->
          <g v-for="(pod, pi) in podsByNode(nd.name).slice(0, 8)" :key="pod.name">
            <rect
              :x="240 + (pi % 4) * 175"
              :y="ni*K8S_ROW_H + 20 + Math.floor(pi/4) * 44"
              width="165" height="36"
              rx="8"
              :fill="podColor(pod.phase) + '20'"
              :stroke="podColor(pod.phase) + '60'"
              stroke-width="1"
            />
            <circle
              :cx="252 + (pi % 4) * 175"
              :cy="ni*K8S_ROW_H + 38 + Math.floor(pi/4) * 44"
              r="5" :fill="podColor(pod.phase)"
              :class="pod.phase==='Running' ? 'k8s-dot-pulse' : ''"/>
            <text
              :x="263 + (pi % 4) * 175"
              :y="ni*K8S_ROW_H + 42 + Math.floor(pi/4) * 44"
              class="pod-name">{{ truncate(pod.name, 14) }}</text>
            <text
              :x="263 + (pi % 4) * 175"
              :y="ni*K8S_ROW_H + 52 + Math.floor(pi/4) * 44"
              class="pod-ns">{{ pod.namespace }}</text>
          </g>

          <!-- 连接线：Node → Pods -->
          <g v-if="animOn">
            <g v-for="(pod, pi) in podsByNode(nd.name).slice(0,8)" :key="'c'+pi">
              <path
                :id="`k8sp-${ni}-${pi}`"
                :d="`M220,${ni*K8S_ROW_H + 45} C230,${ni*K8S_ROW_H+45} 230,${ni*K8S_ROW_H + 38 + Math.floor(pi/4)*44} ${240+(pi%4)*175},${ni*K8S_ROW_H + 38 + Math.floor(pi/4)*44}`"
                fill="none" stroke="#3b82f630" stroke-width="1"/>
              <circle r="3" fill="#60a5fa80" filter="url(#k8s-glow)">
                <animateMotion :dur="(1.2 + pi*0.15)+'s'" repeatCount="indefinite" :begin="(pi*0.2)+'s'">
                  <mpath :href="`#k8sp-${ni}-${pi}`"/>
                </animateMotion>
              </circle>
            </g>
          </g>
        </g>

        <!-- 统计信息 -->
        <g :transform="`translate(20, ${k8sNodes.length * K8S_ROW_H + 28})`">
          <rect x="0" y="0" :width="K8S_W - 40" height="48" rx="10"
            fill="#eff6ff" stroke="#93c5fd" stroke-width="1"/>
          <text x="16" y="22" class="stat-label">集群概览</text>
          <text x="16" y="40" class="stat-val">节点 {{ k8sNodes.length }}</text>
          <text x="100" y="40" class="stat-val">Pods {{ k8sPods.length }}</text>
          <text x="200" y="40" class="stat-val">Running {{ k8sPods.filter(p=>p.phase==='Running').length }}</text>
          <text x="330" y="40" class="stat-val ok-text">{{ k8sPods.filter(p=>p.phase==='Running').length }} / {{ k8sPods.length }}</text>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '../api/index.js'

// ── 常量 ──────────────────────────────────────────────────────────────
const SVG_W = 1440
const SVG_H = 920
const K8S_W = 960
const K8S_ROW_H = 100

// ── 状态 ──────────────────────────────────────────────────────────────
const view     = ref('arch')
const animOn   = ref(true)
const loading  = ref(false)
const hoveredNode = ref(null)
const pageEl   = ref(null)
const archWrap = ref(null)
const k8sNodes = ref([])
const k8sPods  = ref([])

const k8sSvgH = computed(() =>
  Math.max(400, k8sNodes.value.length * K8S_ROW_H + 100)
)

const tooltip = ref({
  show: false, x: 0, y: 0,
  icon: '', name: '', status: '', statusText: '',
  rows: [], calls: [],
})

// ── 层标签 ────────────────────────────────────────────────────────────
const LAYER_LABELS = [
  { id: 0, y:  92, text: '用户入口' },
  { id: 1, y: 228, text: '前端层' },
  { id: 2, y: 378, text: '应用层' },
  { id: 3, y: 518, text: '数据/中间件层' },
  { id: 4, y: 668, text: '可观测性 & 外部服务' },
]

// ── 分组框 ────────────────────────────────────────────────────────────
const GROUPS = [
  { id: 'k8s', x: 90, y: 148, w: 1320, h: 490, color: '#3b82f6', label: 'Kubernetes Cluster (192.168.9.221)' },
  { id: 'ext', x: 90, y: 640, w: 1320, h: 115, color: '#a855f7', label: '可观测性 & 外部 AI & 通知服务' },
]

// ── 节点定义（1440 画布，均匀分布，消除重叠）────────────────────────
// x 为节点中心，y 为节点中心
const archNodes = ref([

  // ─── 层 0 y=92 · 用户入口（三节点均匀分布）────────────
  { id:'user',       name:'用户浏览器', icon:'🌐', port:':30090',
    x:230, y:92, w:136, h:72, grad:'blue',   color:'#3b82f6', status:'ok', pulse:true,
    detail:{ 协议:'HTTP/HTTPS', 端口:'30090', 路由:'Vue Router Hash' }, calls:['Frontend'] },
  { id:'feishu_in',  name:'飞书机器人', icon:'💬', port:'Webhook',
    x:620, y:92, w:130, h:72, grad:'teal',   color:'#14b8a6', status:'ok', pulse:false,
    detail:{ 触发:'关键词@机器人', 协议:'HTTPS Webhook', 通知:'双向' }, calls:['Feishu Bot'] },
  { id:'jenkins_in', name:'Jenkins CI',  icon:'⚙️', port:':8080',
    x:1010,y:92, w:130, h:72, grad:'orange', color:'#f59e0b', status:'ok', pulse:false,
    detail:{ 版本:'Jenkins 2.x', 连接:'Multi-instance', 视图:'分Views管理' }, calls:['Backend API'] },

  // ─── 层 1 y=228 · 前端层 ─────────────────────────────
  { id:'frontend',   name:'Frontend',   icon:'⚡', port:'Vue 3.5.13',
    x:230, y:228, w:140, h:72, grad:'teal',  color:'#14b8a6', status:'ok', pulse:true,
    detail:{ 框架:'Vue 3.5.13+Vite', 端口:'30090(NodePort)', 镜像:'aiops-frontend' }, calls:['Backend API'] },
  { id:'feishu_bot', name:'Feishu Bot', icon:'🤖', port:':30801',
    x:620, y:228, w:140, h:72, grad:'teal',  color:'#14b8a6', status:'ok', pulse:false,
    detail:{ 框架:'FastAPI', 端口:'30801(NodePort)', 功能:'AI消息处理' }, calls:['Backend API'] },

  // ─── 层 2 y=378 · 应用层（Backend 居中）─────────────
  { id:'backend', name:'Backend API', icon:'🚀', port:'FastAPI :30800',
    x:660, y:378, w:172, h:82, grad:'blue', color:'#3b82f6', status:'ok', pulse:true,
    detail:{ 框架:'Python FastAPI', 端口:'30800(NodePort)', 镜像:'aiops-backend', AI引擎:'LangGraph ReAct' },
    calls:['Loki','Prometheus','Redis','Elasticsearch','AlertManager','Claude API','SkyWalking','飞书Open API'] },

  // ─── 层 3 y=518 · 数据/中间件（6节点等间距）────────
  { id:'loki',         name:'Loki',          icon:'📋', port:':27478',
    x:120, y:518, w:116, h:66, grad:'orange', color:'#f59e0b', status:'ok', pulse:false,
    detail:{ 类型:'日志聚合', 地址:'192.168.9.221:27478', 认证:'无' }, calls:[] },
  { id:'prometheus',   name:'Prometheus',    icon:'📈', port:':24404',
    x:308, y:518, w:130, h:66, grad:'orange', color:'#f59e0b', status:'ok', pulse:false,
    detail:{ 类型:'指标监控', 地址:'192.168.9.221:24404', 采集:'15s/次' }, calls:[] },
  { id:'redis',        name:'Redis',         icon:'⚡', port:':6379',
    x:504, y:518, w:116, h:66, grad:'red',    color:'#ef4444', status:'ok', pulse:false,
    detail:{ 类型:'缓存/消息队列', 版本:'7.x', 用途:'Session & Queue' }, calls:[] },
  { id:'es',           name:'Elasticsearch', icon:'🔍', port:':9200',
    x:710, y:518, w:152, h:66, grad:'green',  color:'#22c55e', status:'ok', pulse:false,
    detail:{ 类型:'搜索 & 分析', 节点:'3 nodes', 用途:'日志/报告索引' }, calls:[] },
  { id:'alertmanager', name:'AlertManager',  icon:'🔔', port:':30093',
    x:920, y:518, w:148, h:66, grad:'red',    color:'#ef4444', status:'ok', pulse:false,
    detail:{ 类型:'告警路由', 地址:'192.168.9.221:30093', 接收器:'AIOps Webhook' }, calls:['Backend API'] },
  { id:'grafana',      name:'Grafana',       icon:'📊', port:':30300',
    x:1140,y:518, w:128, h:66, grad:'orange', color:'#f59e0b', status:'ok', pulse:false,
    detail:{ 类型:'可视化大盘', 端口:'30300', 数据源:'Prometheus+Loki' }, calls:[] },

  // ─── 层 4 y=668 · 可观测性 & 外部（4节点等间距）────
  { id:'skywalking',  name:'SkyWalking',   icon:'🔭', port:'APM',
    x:220, y:668, w:138, h:64, grad:'purple', color:'#a855f7', status:'ok', pulse:false,
    detail:{ 类型:'APM链路追踪', 协议:'gRPC/HTTP', 用途:'Trace & Span' }, calls:[] },
  { id:'claude',      name:'Claude API',   icon:'🧠', port:'Anthropic',
    x:570, y:668, w:134, h:64, grad:'purple', color:'#a855f7', status:'ok', pulse:true,
    detail:{ 模型:'claude-opus-4-6', 方式:'SSE流式', 功能:'LangGraph Agent' }, calls:[] },
  { id:'qwen',        name:'Qwen / OpenAI',icon:'🤖', port:'OpenAI兼容',
    x:780, y:668, w:142, h:64, grad:'purple', color:'#a855f7', status:'ok', pulse:false,
    detail:{ 接口:'OpenAI兼容协议', 配置:'AI_BASE_URL', 用途:'本地/私有LLM' }, calls:[] },
  { id:'feishu_svc',  name:'飞书 Open API',icon:'🪶', port:'HTTPS',
    x:1020,y:668, w:148, h:64, grad:'teal',   color:'#14b8a6', status:'ok', pulse:false,
    detail:{ 端点:'open.feishu.cn', 功能:'卡片消息/Webhook', 触发:'告警 & 日报' }, calls:[] },
])

// ── 连接线定义（自动计算贝塞尔曲线） ─────────────────────────────────
function nodeById(id) {
  return archNodes.value.find(n => n.id === id)
}

function edgePath(fromId, toId) {
  const a = nodeById(fromId)
  const b = nodeById(toId)
  if (!a || !b) return ''
  // 从源节点底部中心 → 目标节点顶部中心
  // 使用"L形弯"：先垂直到层间中点，再水平，再垂直到目标
  // 这样路径始终走层间空白区，不穿过其他节点
  const ax = a.x, ay = a.y + a.h / 2
  const bx = b.x, by = b.y - b.h / 2
  const midY = (ay + by) / 2
  return `M${ax},${ay} C${ax},${midY} ${bx},${midY} ${bx},${by}`
}

function makePackets(count, baseDur, color) {
  return Array.from({ length: count }, (_, i) => ({
    key: i,
    r: 3.5 - i * 0.4,
    dur: baseDur + i * 0.3,
    begin: i * (baseDur / count),
  }))
}

const archEdges = computed(() => [
  // 用户 → 前端
  { id:'u-fe',  fromId:'user',     toId:'frontend',    color:'#3b82f6', marker:'blue',   glowType:'blue',   packets: makePackets(3,2.0) },
  // 飞书 → Feishu Bot
  { id:'fs-fb', fromId:'feishu_in',toId:'feishu_bot',  color:'#14b8a6', marker:'blue',   glowType:'blue',   packets: makePackets(2,2.5) },
  // Jenkins → Backend
  { id:'jk-be', fromId:'jenkins_in',toId:'backend',    color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(2,2.8) },
  // 前端 → Backend
  { id:'fe-be', fromId:'frontend', toId:'backend',     color:'#3b82f6', marker:'blue',   glowType:'blue',   packets: makePackets(3,1.8) },
  // Feishu Bot → Backend
  { id:'fb-be', fromId:'feishu_bot',toId:'backend',    color:'#14b8a6', marker:'blue',   glowType:'blue',   packets: makePackets(2,2.2) },
  // Backend → Loki
  { id:'be-lk', fromId:'backend',  toId:'loki',        color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(3,1.6) },
  // Backend → Prometheus
  { id:'be-pm', fromId:'backend',  toId:'prometheus',  color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(3,1.8) },
  // Backend → Redis
  { id:'be-rd', fromId:'backend',  toId:'redis',       color:'#ef4444', marker:'blue',   glowType:'blue',   packets: makePackets(2,1.4) },
  // Backend → ES
  { id:'be-es', fromId:'backend',  toId:'es',          color:'#22c55e', marker:'green',  glowType:'green',  packets: makePackets(2,2.0) },
  // Backend → AlertManager
  { id:'be-am', fromId:'backend',  toId:'alertmanager',color:'#ef4444', marker:'orange', glowType:'blue',   packets: makePackets(2,3.0) },
  // AlertManager → Backend (回调)
  { id:'am-be', fromId:'alertmanager',toId:'backend',  color:'#ef4444', marker:'orange', glowType:'blue',   packets: makePackets(1,2.5) },
  // Loki → Grafana
  { id:'lk-gf', fromId:'loki',     toId:'grafana',     color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(2,2.2) },
  // Prometheus → Grafana
  { id:'pm-gf', fromId:'prometheus',toId:'grafana',    color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(2,2.0) },
  // Backend → Claude
  { id:'be-cl', fromId:'backend',  toId:'claude',      color:'#a855f7', marker:'purple', glowType:'blue',   packets: makePackets(3,1.5) },
  // Backend → Qwen
  { id:'be-qw', fromId:'backend',  toId:'qwen',        color:'#a855f7', marker:'purple', glowType:'blue',   packets: makePackets(2,2.0) },
  // Backend → 飞书服务
  { id:'be-fs', fromId:'backend',  toId:'feishu_svc',  color:'#14b8a6', marker:'blue',   glowType:'blue',   packets: makePackets(2,3.5) },
  // Backend → SkyWalking
  { id:'be-sw', fromId:'backend',  toId:'skywalking',  color:'#a855f7', marker:'purple', glowType:'blue',   packets: makePackets(2,2.4) },
].map(e => ({
  ...e,
  d: edgePath(e.fromId, e.toId),
})))

// ── 工具提示 ──────────────────────────────────────────────────────────
function showTooltip(nd, evt) {
  const wrap = archWrap.value
  if (!wrap) return
  const rect = wrap.getBoundingClientRect()
  tooltip.value = {
    show: true,
    x: evt.clientX - rect.left + 14,
    y: evt.clientY - rect.top - 10,
    icon: nd.icon,
    name: nd.name,
    status: nd.status,
    statusText: nd.status === 'ok' ? '正常' : nd.status === 'warn' ? '告警' : '未知',
    rows: Object.entries(nd.detail || {}).map(([k, v]) => ({ k, v })),
    calls: nd.calls || [],
  }
}

function onMouseMove(evt) {
  if (!tooltip.value.show) return
  const wrap = archWrap.value
  if (!wrap) return
  const rect = wrap.getBoundingClientRect()
  tooltip.value.x = evt.clientX - rect.left + 14
  tooltip.value.y = evt.clientY - rect.top - 10
}

// ── K8s 数据 ──────────────────────────────────────────────────────────
async function loadK8s() {
  loading.value = true
  try {
    const [nr, pr] = await Promise.allSettled([api.k8sNodes(), api.k8sPods()])
    k8sNodes.value = (nr.status === 'fulfilled' ? (nr.value?.data ?? nr.value ?? []) : [])
    k8sPods.value  = (pr.status === 'fulfilled' ? (pr.value?.data ?? pr.value ?? []) : [])
  } finally {
    loading.value = false
  }
}

function podsByNode(name) {
  return k8sPods.value.filter(p => p.node_name === name)
}

function podColor(phase) {
  return phase === 'Running' ? '#22c55e' : phase === 'Pending' ? '#f59e0b' : phase === 'Failed' ? '#ef4444' : '#6b7280'
}

function truncate(s, n) {
  return s && s.length > n ? s.slice(0, n) + '…' : (s || '')
}

onMounted(() => {})
</script>

<style scoped>
/* ── 页面布局 ────────────────────────────────────────────── */
.arch-page {
  display: flex; flex-direction: column;
  height: 100%; background: #f1f5f9; color: #1e293b; overflow: hidden;
}

/* ── 工具栏 ─────────────────────────────────────────────── */
.arch-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; background: #ffffff;
  border-bottom: 1px solid #e2e8f0; flex-shrink: 0; flex-wrap: wrap; gap: 8px;
}
.arch-brand { display: flex; align-items: center; gap: 10px; }
.brand-icon { width: 20px; height: 20px; stroke: #3b82f6; }
.arch-brand > span:first-of-type { font-size: 15px; font-weight: 700; color: #0f172a; }
.arch-subtitle { font-size: 11px; color: #64748b; margin-left: 4px; }
.arch-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.view-tabs { display: flex; background: #f1f5f9; border-radius: 8px; padding: 3px; gap: 2px; border: 1px solid #e2e8f0; }
.vtab { padding: 5px 14px; border-radius: 6px; border: none; background: transparent; color: #64748b; cursor: pointer; font-size: 12px; transition: .15s; }
.vtab.active { background: #3b82f6; color: #fff; }
.vtab:hover:not(.active) { color: #1e293b; background: #e2e8f0; }

.toggle-pill { display: flex; align-items: center; gap: 7px; cursor: pointer; font-size: 12px; color: #64748b; user-select: none; }
.toggle-pill input { display: none; }
.pill-track { width: 32px; height: 18px; background: #cbd5e1; border-radius: 9px; position: relative; transition: background .2s; }
.toggle-pill input:checked ~ .pill-track { background: #3b82f6; }
.pill-thumb { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; background: #fff; border-radius: 50%; transition: left .2s; }
.toggle-pill input:checked ~ .pill-track .pill-thumb { left: 16px; }

.ctrl-btn { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border: 1px solid #e2e8f0; background: #fff; color: #64748b; border-radius: 8px; cursor: pointer; font-size: 14px; transition: .15s; }
.ctrl-btn:hover { color: #1e293b; border-color: #3b82f6; }
.ctrl-btn:disabled { opacity: .4; cursor: not-allowed; }

/* ── 画布区域 ────────────────────────────────────────────── */
.canvas-wrap {
  flex: 1; overflow: auto; position: relative;
  display: flex; align-items: flex-start; justify-content: center;
  padding: 12px;
}
.arch-svg {
  width: 100%; max-width: 1300px;
  height: auto; min-height: 400px;
  display: block;
}

/* ── SVG 文本样式 ────────────────────────────────────────── */
.layer-txt { fill: #94a3b8; font-size: 10px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.node-icon { font-size: 18px; }
.node-name { fill: #1e293b; font-size: 11.5px; font-weight: 700; }
.node-port { fill: #64748b; font-size: 9.5px; }
.grp-label { font-size: 10px; font-weight: 600; opacity: 0.8; }

/* ── 节点动效 ────────────────────────────────────────────── */
.arch-node { cursor: pointer; transition: filter .2s; }
.arch-node:hover { filter: brightness(1.3); }

.node-pulse { animation: nodePulse 2.5s ease-in-out infinite; transform-origin: center; }
@keyframes nodePulse {
  0%, 100% { opacity: .15; transform: scale(1); }
  50%       { opacity: .35; transform: scale(1.3); }
}

.status-pulse-ok { animation: dotPulse 2s ease-in-out infinite; }
@keyframes dotPulse {
  0%, 100% { opacity: 1; r: 5; }
  50%       { opacity: .4; r: 7; }
}

.edge-dash { animation: dashFlow 6s linear infinite; }
@keyframes dashFlow { to { stroke-dashoffset: -44; } }

.hover-ring { animation: ringPulse .6s ease-in-out infinite alternate; }
@keyframes ringPulse { from { opacity: .5; } to { opacity: 1; } }

/* ── 工具提示 ────────────────────────────────────────────── */
.node-tooltip {
  position: absolute; z-index: 100; pointer-events: none;
  background: #ffffff; border: 1px solid #e2e8f0;
  border-radius: 12px; padding: 12px 14px; min-width: 200px; max-width: 280px;
  box-shadow: 0 8px 32px rgba(0,0,0,.12);
}
.tip-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.tip-icon { font-size: 18px; }
.tip-name { font-size: 13px; font-weight: 700; color: #0f172a; flex: 1; }
.tip-badge { padding: 2px 8px; border-radius: 999px; font-size: 10px; font-weight: 600; }
.tip-badge.ok   { background: #dcfce7; color: #16a34a; border: 1px solid #86efac; }
.tip-badge.warn { background: #fef3c7; color: #d97706; border: 1px solid #fcd34d; }
.tip-rows { display: flex; flex-direction: column; gap: 5px; }
.tip-row { display: flex; justify-content: space-between; font-size: 11px; }
.tip-key { color: #64748b; }
.tip-val { color: #1e293b; font-weight: 500; text-align: right; max-width: 160px; }
.tip-calls { margin-top: 8px; padding-top: 8px; border-top: 1px solid #e2e8f0; }
.tip-calls-title { font-size: 10px; color: #94a3b8; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .05em; }
.tip-call-item { font-size: 11px; color: #3b82f6; padding: 1px 0; }

/* ── 图例 ────────────────────────────────────────────────── */
.arch-legend {
  position: absolute; bottom: 20px; right: 20px;
  background: #ffffffee; border: 1px solid #e2e8f0;
  border-radius: 10px; padding: 10px 14px;
  display: flex; flex-direction: column; gap: 5px;
  font-size: 11px; backdrop-filter: blur(4px);
  box-shadow: 0 2px 12px rgba(0,0,0,.08);
}
.leg-row { display: flex; align-items: center; gap: 7px; color: #64748b; }
.leg-line { display: inline-block; width: 22px; height: 2px; border-radius: 1px; }
.leg-line.blue   { background: #3b82f6; }
.leg-line.green  { background: #22c55e; }
.leg-line.orange { background: #f59e0b; }
.leg-line.purple { background: #a855f7; }
.leg-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.leg-dot.ok   { background: #22c55e; }
.leg-dot.warn { background: #f59e0b; }
.leg-dot.gray { background: #6b7280; }
.leg-sep { height: 1px; background: #21262d; margin: 2px 0; }

/* ── K8s 服务图 ─────────────────────────────────────────── */
.k8s-wrap { flex: 1; overflow: auto; padding: 12px; display: flex; justify-content: center; }
.k8s-svg { width: 100%; max-width: 960px; height: auto; display: block; }
.k8s-loading, .k8s-empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 200px; color: #8b949e; gap: 12px;
}
.k8s-node-name { fill: #1e293b; font-size: 12px; font-weight: 700; }
.k8s-node-role { fill: #64748b; font-size: 10px; }
.pod-name { fill: #1e293b; font-size: 10.5px; font-weight: 600; dominant-baseline: middle; }
.pod-ns   { fill: #64748b; font-size: 9.5px; dominant-baseline: middle; }
.stat-label { fill: #94a3b8; font-size: 10px; text-transform: uppercase; letter-spacing: .05em; }
.stat-val   { fill: #1e293b; font-size: 12px; font-weight: 600; }
.ok-text    { fill: #16a34a; }

.k8s-dot-pulse { animation: dotPulse 2s ease-in-out infinite; }

/* ── 加载动画 ────────────────────────────────────────────── */
.spin-sm {
  width: 13px; height: 13px; border-radius: 50%;
  border: 2px solid #21262d; border-top-color: #58a6ff;
  animation: spin .7s linear infinite; display: inline-block;
}
.spin-lg {
  width: 36px; height: 36px; border-radius: 50%;
  border: 3px solid #21262d; border-top-color: #58a6ff;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
