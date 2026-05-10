<template>
  <div class="rr-page">
    <!-- 顶部工具栏 -->
    <div class="rr-toolbar">
      <div class="rr-brand">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="1.8">
          <circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/>
          <line x1="12" y1="7" x2="5" y2="17"/><line x1="12" y1="7" x2="19" y2="17"/>
          <line x1="7" y1="19" x2="17" y2="19"/>
        </svg>
        <span>K8s 资源关系图</span>
        <span class="rr-sub">Resource Dependency & Interaction Map</span>
      </div>
      <div class="rr-controls">
        <label class="toggle-pill">
          <input type="checkbox" v-model="animOn"/>
          <span class="pill-track"><span class="pill-thumb"></span></span>
          <span>流动动效</span>
        </label>
        <label class="toggle-pill">
          <input type="checkbox" v-model="showLabels"/>
          <span class="pill-track"><span class="pill-thumb"></span></span>
          <span>显示说明</span>
        </label>
        <div class="zoom-btns">
          <button class="ctrl-btn" @click="zoomIn">＋</button>
          <button class="ctrl-btn" @click="zoomOut">－</button>
          <button class="ctrl-btn" @click="fitView" style="font-size:11px">Fit</button>
        </div>
      </div>
    </div>

    <!-- 图例 -->
    <div class="rr-legend">
      <span v-for="g in NODE_GROUPS" :key="g.id" class="leg-item">
        <span class="leg-dot" :style="{background: g.color}"></span>{{ g.label }}
      </span>
      <span class="leg-sep">|</span>
      <span class="leg-item"><span class="leg-line" style="background:#38bdf8"></span>API 调用</span>
      <span class="leg-item"><span class="leg-line" style="background:#a78bfa"></span>控制/监听</span>
      <span class="leg-item"><span class="leg-line" style="background:#22c55e"></span>选择/关联</span>
      <span class="leg-item"><span class="leg-line" style="background:#fbbf24"></span>挂载/注入</span>
    </div>

    <!-- SVG 主画布 -->
    <div class="rr-canvas" ref="canvasEl">
      <svg class="rr-svg"
        :viewBox="vbStr"
        preserveAspectRatio="xMidYMid meet"
        :style="{ cursor: drag.active ? 'grabbing' : 'grab' }"
        @wheel.prevent="onWheel"
        @mousedown="onDragStart"
        @mousemove="onDragMove"
        @mouseup="onDragEnd"
        @mouseleave="onDragEnd"
        ref="svgEl"
      >
        <defs>
          <pattern id="rr-grid" width="44" height="44" patternUnits="userSpaceOnUse">
            <path d="M44,0 L0,0 L0,44" fill="none" stroke="rgba(56,189,248,0.06)" stroke-width="1"/>
          </pattern>
          <filter id="rr-glow">
            <feGaussianBlur stdDeviation="3" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <filter id="rr-glow-sm">
            <feGaussianBlur stdDeviation="2" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <!-- 箭头 -->
          <marker v-for="g in NODE_GROUPS" :key="'arr-'+g.id"
            :id="'arr-'+g.id" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
            <path d="M0,0 L0,6 L8,3 z" :fill="g.color"/>
          </marker>
          <!-- 渐变背景 -->
          <radialGradient id="rr-bg" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stop-color="#111827"/>
            <stop offset="100%" stop-color="#0d1117"/>
          </radialGradient>
        </defs>

        <rect width="100%" height="100%" fill="url(#rr-bg)"/>
        <rect width="100%" height="100%" fill="url(#rr-grid)"/>

        <!-- 分区背景框 -->
        <g class="rr-zones">
          <rect v-for="z in ZONES" :key="z.id"
            :x="z.x" :y="z.y" :width="z.w" :height="z.h" rx="18"
            fill="none" :stroke="z.color" stroke-width="1"
            stroke-dasharray="8 5" :fill-opacity="0.02"/>
          <text v-for="z in ZONES" :key="'zt'+z.id"
            :x="z.x + 14" :y="z.y + 18" class="zone-label" :fill="z.color">{{ z.label }}</text>
        </g>

        <!-- 关系连线 -->
        <g class="rr-edges">
          <path v-for="e in EDGES" :key="e.id"
            :id="'re-'+e.id" :d="e.d"
            fill="none"
            :stroke="hoveredId ? (isRelated(e) ? e.color : e.color+'18') : e.color+'55'"
            :stroke-width="hoveredId && isRelated(e) ? 2.2 : 1.4"
            :stroke-dasharray="e.dash || '6 4'"
            :opacity="hoveredId ? (isRelated(e) ? 1 : 0.1) : 1"
            :marker-end="'url(#arr-'+e.group+')'"
            class="rr-edge"
          />
          <!-- hover 时显示关系标签 -->
          <g v-if="hoveredId">
            <g v-for="e in EDGES.filter(e => isRelated(e))" :key="'el-'+e.id">
              <rect :x="edgeMid(e).x-30" :y="edgeMid(e).y-9" width="60" height="17" rx="4"
                :fill="e.color+'25'" :stroke="e.color+'70'" stroke-width="1"/>
              <text :x="edgeMid(e).x" :y="edgeMid(e).y+4" text-anchor="middle"
                class="edge-lbl" :fill="e.color">{{ e.label }}</text>
            </g>
          </g>
        </g>

        <!-- 流动粒子 -->
        <g v-if="animOn" class="rr-particles">
          <g v-for="e in EDGES" :key="'pk-'+e.id"
            :opacity="hoveredId ? (isRelated(e) ? 1 : 0) : 1">
            <circle v-for="pk in e.packets" :key="pk.i"
              :r="hoveredId && isRelated(e) ? pk.r * 1.5 : pk.r"
              :fill="e.color" filter="url(#rr-glow-sm)">
              <animateMotion :dur="(hoveredId && isRelated(e) ? pk.dur*0.65 : pk.dur)+'s'"
                repeatCount="indefinite" :begin="pk.begin+'s'">
                <mpath :href="'#re-'+e.id"/>
              </animateMotion>
            </circle>
          </g>
        </g>

        <!-- 节点 -->
        <g class="rr-nodes">
          <g v-for="nd in NODES" :key="nd.id"
            :transform="`translate(${nd.x},${nd.y})`"
            :opacity="hoveredId && hoveredId !== nd.id && !isConnected(nd.id) ? 0.15 : 1"
            style="transition: opacity .2s"
            class="rr-node"
            @mouseenter="hoveredId = nd.id"
            @mouseleave="hoveredId = null"
          >
            <!-- 光晕 -->
            <circle v-if="nd.pulse || hoveredId === nd.id" cx="0" cy="0"
              :r="nd.r + (hoveredId === nd.id ? 14 : 10)"
              :fill="nd.color+'20'"
              :class="hoveredId === nd.id ? '' : 'rr-pulse'"/>
            <!-- 主圆 -->
            <circle cx="0" cy="0" :r="nd.r"
              :fill="nd.fill"
              :stroke="hoveredId === nd.id ? nd.color : nd.color+'88'"
              :stroke-width="hoveredId === nd.id ? 2.5 : 1.8"
              filter="url(#rr-glow)"/>
            <!-- 图标 -->
            <text x="0" :y="-4" text-anchor="middle" :font-size="nd.iconSize || 16"
              dominant-baseline="middle">{{ nd.icon }}</text>
            <!-- 名称 -->
            <text x="0" :y="nd.r + 14" text-anchor="middle" class="nd-name">{{ nd.name }}</text>
            <!-- 副标题 -->
            <text v-if="nd.sub" x="0" :y="nd.r + 26" text-anchor="middle" class="nd-sub">{{ nd.sub }}</text>
          </g>
        </g>

        <!-- 说明文字浮层 -->
        <g v-if="showLabels && hoveredId" class="rr-tooltip">
          <g :transform="`translate(${tooltipPos.x}, ${tooltipPos.y})`">
            <rect x="0" y="0" :width="tooltipW" :height="tooltipLines.length*18+28"
              rx="10" fill="#161b22" stroke="#30363d" stroke-width="1.2"
              filter="url(#rr-glow)"/>
            <text x="12" y="20" class="tip-title" :fill="hoveredNode?.color">{{ hoveredNode?.name }}</text>
            <text v-for="(ln, i) in tooltipLines" :key="i"
              x="12" :y="38+i*18" class="tip-line">{{ ln }}</text>
          </g>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'

// ── 动效开关 ──────────────────────────────────────────────────────────
const animOn     = ref(true)
const showLabels = ref(true)
const hoveredId  = ref(null)
const svgEl      = ref(null)
const canvasEl   = ref(null)

// ── 画布尺寸 ──────────────────────────────────────────────────────────
const W = 1400, H = 900

// ── ViewBox 缩放/拖拽 ─────────────────────────────────────────────────
const vb   = reactive({ x: 0, y: 0, w: W, h: H })
const drag = reactive({ active: false, sx: 0, sy: 0, vbx0: 0, vby0: 0 })
const vbStr = computed(() => `${vb.x} ${vb.y} ${vb.w} ${vb.h}`)

function zoomAt(f, cx, cy) {
  const nw = Math.max(400, Math.min(W*3, vb.w / f))
  const nh = nw * H / W
  vb.x = cx - (cx - vb.x) * (nw / vb.w); vb.y = cy - (cy - vb.y) * (nh / vb.h)
  vb.w = nw; vb.h = nh
}
function zoomIn()  { zoomAt(1.2,  vb.x + vb.w/2, vb.y + vb.h/2) }
function zoomOut() { zoomAt(0.83, vb.x + vb.w/2, vb.y + vb.h/2) }
function fitView() { vb.x=0; vb.y=0; vb.w=W; vb.h=H }
function onWheel(e) {
  const rect = svgEl.value.getBoundingClientRect()
  const mx = (e.clientX - rect.left) / rect.width  * vb.w + vb.x
  const my = (e.clientY - rect.top)  / rect.height * vb.h + vb.y
  zoomAt(e.deltaY < 0 ? 1.15 : 0.87, mx, my)
}
function onDragStart(e) {
  if (e.button !== 0) return
  drag.active = true; drag.sx = e.clientX; drag.sy = e.clientY
  drag.vbx0 = vb.x; drag.vby0 = vb.y
}
function onDragMove(e) {
  if (!drag.active) return
  const rect = svgEl.value.getBoundingClientRect()
  const sx = vb.w / rect.width, sy = vb.h / rect.height
  vb.x = drag.vbx0 - (e.clientX - drag.sx) * sx
  vb.y = drag.vby0 - (e.clientY - drag.sy) * sy
}
function onDragEnd() { drag.active = false }

// ── 节点分组 / 颜色 ───────────────────────────────────────────────────
const NODE_GROUPS = [
  { id:'ctrl',   color:'#38bdf8', label:'控制平面' },
  { id:'wrkld',  color:'#a78bfa', label:'工作负载' },
  { id:'net',    color:'#22c55e', label:'网络/服务' },
  { id:'stor',   color:'#fbbf24', label:'存储/配置' },
  { id:'sec',    color:'#f87171', label:'安全/权限' },
  { id:'client', color:'#fb923c', label:'客户端' },
]

// ── 分区框 ────────────────────────────────────────────────────────────
const ZONES = [
  { id:'plane', x:30,  y:30,  w:480, h:280, color:'#38bdf8', label:'Control Plane' },
  { id:'wrkld', x:30,  y:350, w:480, h:510, color:'#a78bfa', label:'Workload Objects' },
  { id:'net',   x:550, y:30,  w:440, h:510, color:'#22c55e', label:'Networking' },
  { id:'cfg',   x:550, y:570, w:440, h:290, color:'#fbbf24', label:'Config & Storage' },
  { id:'sec',   x:1020,y:30,  w:350, h:510, color:'#f87171', label:'Security & RBAC' },
]

// ── 节点定义 ──────────────────────────────────────────────────────────
const NODES = [
  // 控制平面
  { id:'apisvr',  name:'API Server', sub:':6443', icon:'⚙️', iconSize:20, r:38, x:200, y:140,
    color:'#38bdf8', fill:'#0c2038', pulse:true, group:'ctrl',
    desc:['集群唯一入口，所有资源操作经过它','提供 REST API + Watch 机制','负责认证/授权/准入控制','所有组件只与 API Server 通信'] },
  { id:'etcd',    name:'etcd', sub:':2379', icon:'🗄️', iconSize:18, r:30, x:100, y:260,
    color:'#38bdf8', fill:'#0c1a30', group:'ctrl',
    desc:['分布式 K-V 存储，保存所有集群状态','只有 API Server 直接访问','支持 Watch 实现事件驱动','多副本 Raft 共识保证一致性'] },
  { id:'sched',   name:'Scheduler', sub:'Pod 调度', icon:'📅', iconSize:16, r:30, x:300, y:260,
    color:'#38bdf8', fill:'#0c1a30', group:'ctrl',
    desc:['监听未调度 Pod','根据资源/亲和性选择 Node','写回 Pod.spec.nodeName','可替换为自定义调度器'] },
  { id:'ctrlmgr', name:'Controller\nManager', sub:'控制循环', icon:'🔄', iconSize:16, r:30, x:420, y:260,
    color:'#38bdf8', fill:'#0c1a30', group:'ctrl',
    desc:['内置多个控制器的集合','Deployment/ReplicaSet/Node 控制器','持续比对 spec vs status','驱动资源向期望状态收敛'] },

  // 工作负载
  { id:'deploy',  name:'Deployment', sub:'无状态应用', icon:'🚀', iconSize:18, r:34, x:120, y:480,
    color:'#a78bfa', fill:'#160d29', pulse:true, group:'wrkld',
    desc:['声明无状态应用期望状态','管理 ReplicaSet 生命周期','支持滚动更新/回滚','HPA 通过它扩缩容'] },
  { id:'sts',     name:'StatefulSet', sub:'有状态应用', icon:'🗃️', iconSize:16, r:28, x:250, y:560,
    color:'#a78bfa', fill:'#160d29', group:'wrkld',
    desc:['管理有状态应用（DB/MQ）','Pod 有固定名称和存储','有序部署/删除','需要 Headless Service'] },
  { id:'ds',      name:'DaemonSet', sub:'节点守护', icon:'👁️', iconSize:16, r:28, x:380, y:480,
    color:'#a78bfa', fill:'#160d29', group:'wrkld',
    desc:['每个节点运行一个 Pod','常用于日志/监控/网络插件','节点加入时自动部署'] },
  { id:'rs',      name:'ReplicaSet', sub:'副本控制', icon:'📋', iconSize:16, r:28, x:120, y:640,
    color:'#a78bfa', fill:'#160d29', group:'wrkld',
    desc:['维护指定数量的 Pod 副本','通常不直接使用，由 Deployment 管理','通过 labelSelector 选择 Pod'] },
  { id:'pod',     name:'Pod', sub:'最小调度单元', icon:'🟢', iconSize:18, r:36, x:250, y:750,
    color:'#a78bfa', fill:'#1a1030', pulse:true, group:'wrkld',
    desc:['包含一个或多个 Container','共享 Network Namespace','最小调度/运行单元','通过 Service 暴露访问'] },
  { id:'job',     name:'Job/CronJob', sub:'批处理任务', icon:'⏰', iconSize:16, r:26, x:430, y:640,
    color:'#a78bfa', fill:'#160d29', group:'wrkld',
    desc:['Job：运行完成即结束','CronJob：定时触发 Job','常用于数据迁移/定时清理'] },

  // 网络服务
  { id:'ingress', name:'Ingress', sub:'HTTP 入口', icon:'🌐', iconSize:18, r:32, x:660, y:120,
    color:'#22c55e', fill:'#0a1f15', pulse:true, group:'net',
    desc:['HTTP/HTTPS 路由规则','域名/路径 → Service 映射','需要 Ingress Controller','支持 TLS 终止'] },
  { id:'svc',     name:'Service', sub:'稳定访问入口', icon:'🔌', iconSize:18, r:34, x:680, y:280,
    color:'#22c55e', fill:'#0a1f15', group:'net',
    desc:['为 Pod 提供稳定的 DNS 名和 IP','ClusterIP/NodePort/LoadBalancer','通过 labelSelector 关联 Pod','kube-proxy 实现负载均衡'] },
  { id:'ep',      name:'Endpoints', sub:'后端 IP 列表', icon:'📍', iconSize:14, r:24, x:820, y:200,
    color:'#22c55e', fill:'#071a10', group:'net',
    desc:['记录 Service 对应的 Pod IP:Port','Service 自动维护','ExternalEndpoints 可指向外部'] },
  { id:'netsvc',  name:'NetworkPolicy', sub:'流量控制', icon:'🛡️', iconSize:16, r:26, x:840, y:340,
    color:'#22c55e', fill:'#071a10', group:'net',
    desc:['控制 Pod 间网络访问','基于 labelSelector 定义规则','需要 CNI 插件支持','默认全通，加策略后按需放行'] },
  { id:'hpa',     name:'HPA', sub:'水平自动扩缩', icon:'📈', iconSize:16, r:26, x:660, y:440,
    color:'#22c55e', fill:'#071a10', group:'net',
    desc:['根据 CPU/内存/自定义指标','自动调整 Deployment 副本数','依赖 Metrics Server'] },

  // 配置存储
  { id:'cm',      name:'ConfigMap', sub:'配置数据', icon:'📝', iconSize:16, r:28, x:620, y:660,
    color:'#fbbf24', fill:'#1a1300', group:'stor',
    desc:['存储非敏感配置数据','可作为环境变量/Volume 挂载','更新后 Pod 可动态感知（Volume）'] },
  { id:'secret',  name:'Secret', sub:'敏感数据', icon:'🔐', iconSize:16, r:28, x:750, y:660,
    color:'#fbbf24', fill:'#1a1300', group:'stor',
    desc:['存储敏感信息（密码/Token/证书）','Base64 编码（非加密）','可配合 Vault 增强安全性'] },
  { id:'pvc',     name:'PVC/PV', sub:'持久化存储', icon:'💾', iconSize:16, r:28, x:880, y:660,
    color:'#fbbf24', fill:'#1a1300', group:'stor',
    desc:['PVC：用户声明存储需求','PV：管理员提供存储资源','StorageClass 动态供给','支持 ReadWriteOnce/Many'] },
  { id:'ns',      name:'Namespace', sub:'资源隔离', icon:'📦', iconSize:16, r:26, x:660, y:800,
    color:'#fbbf24', fill:'#1a1300', group:'stor',
    desc:['逻辑隔离多租户/环境','ResourceQuota 限制用量','NetworkPolicy 在 NS 内生效','默认 NS: default/kube-system'] },

  // 安全 RBAC
  { id:'sa',      name:'ServiceAccount', sub:'Pod 身份', icon:'👤', iconSize:16, r:28, x:1090, y:130,
    color:'#f87171', fill:'#200c0c', group:'sec',
    desc:['Pod 访问 API Server 的身份','每个 NS 默认有 default SA','Token 自动挂载到 Pod'] },
  { id:'role',    name:'Role/ClusterRole', sub:'权限定义', icon:'📜', iconSize:14, r:26, x:1230, y:200,
    color:'#f87171', fill:'#200c0c', group:'sec',
    desc:['Role：NS 级别权限','ClusterRole：集群级别权限','定义对资源的 verbs（get/list/watch）'] },
  { id:'rb',      name:'RoleBinding', sub:'权限绑定', icon:'🔗', iconSize:14, r:26, x:1150, y:340,
    color:'#f87171', fill:'#200c0c', group:'sec',
    desc:['将 Role 绑定到 Subject','Subject：User/Group/ServiceAccount','ClusterRoleBinding 全局绑定'] },
  { id:'admit',   name:'Admission\nWebhook', sub:'准入控制', icon:'🚦', iconSize:14, r:26, x:1270, y:380,
    color:'#f87171', fill:'#200c0c', group:'sec',
    desc:['ValidatingWebhook：验证请求','MutatingWebhook：修改请求','OPA/Kyverno 基于此实现策略'] },

  // 客户端
  { id:'kubectl', name:'kubectl', sub:'CLI 工具', icon:'💻', iconSize:16, r:28, x:700, y:860,
    color:'#fb923c', fill:'#1a0f00', pulse:true, group:'client',
    desc:['K8s 命令行客户端','通过 kubeconfig 访问 API Server','常用命令: apply/get/describe/logs'] },
]

// ── 关系边定义 ────────────────────────────────────────────────────────
function nd(id) { return NODES.find(n => n.id === id) }

function arc(a, b, bend = 0) {
  if (!a || !b) return ''
  const dx = b.x - a.x, dy = b.y - a.y
  const mx = (a.x + b.x) / 2 + (bend ? -dy * bend : 0)
  const my = (a.y + b.y) / 2 + (bend ? dx * bend : 0)
  const ra = a.r + 4, rb = b.r + 4
  const len = Math.sqrt(dx*dx + dy*dy)
  const ux = dx/len, uy = dy/len
  return `M${a.x + ux*ra},${a.y + uy*ra} Q${mx},${my} ${b.x - ux*rb},${b.y - uy*rb}`
}

function pkts(n, dur) {
  return Array.from({length: n}, (_, i) => ({ i, r: 3 + (n-i)*0.4, dur, begin: i * dur/n }))
}

const EDGES = [
  // API Server ↔ etcd
  { id:'api-etc', from:'apisvr', to:'etcd',    group:'ctrl', color:'#38bdf8', label:'读写状态',   packets: pkts(2,1.8) },
  { id:'etc-api', from:'etcd',   to:'apisvr',  group:'ctrl', color:'#38bdf8', label:'Watch事件',  packets: pkts(1,2.5), dash:'4 3' },
  // 控制器监听 API Server
  { id:'sch-api', from:'sched',   to:'apisvr', group:'ctrl', color:'#38bdf8', label:'Watch Pod',  packets: pkts(2,2.2) },
  { id:'cm-api',  from:'ctrlmgr', to:'apisvr', group:'ctrl', color:'#38bdf8', label:'Watch资源',  packets: pkts(2,2.0) },
  // 工作负载层级
  { id:'dep-rs',  from:'deploy', to:'rs',      group:'wrkld', color:'#a78bfa', label:'owns',       packets: pkts(2,1.6) },
  { id:'rs-pod',  from:'rs',     to:'pod',     group:'wrkld', color:'#a78bfa', label:'creates',    packets: pkts(3,1.4) },
  { id:'sts-pod', from:'sts',    to:'pod',     group:'wrkld', color:'#a78bfa', label:'manages',    packets: pkts(2,1.8) },
  { id:'ds-pod',  from:'ds',     to:'pod',     group:'wrkld', color:'#a78bfa', label:'per-node',   packets: pkts(2,2.0) },
  { id:'job-pod', from:'job',    to:'pod',     group:'wrkld', color:'#a78bfa', label:'run once',   packets: pkts(1,2.4) },
  // 调度器绑定 Pod → Node
  { id:'sch-pod', from:'sched',  to:'pod',     group:'ctrl',  color:'#38bdf8', label:'bind Node',  packets: pkts(2,2.5) },
  // 网络服务
  { id:'ing-svc', from:'ingress', to:'svc',    group:'net',   color:'#22c55e', label:'→ Service',  packets: pkts(3,1.5) },
  { id:'svc-pod', from:'svc',     to:'pod',    group:'net',   color:'#22c55e', label:'selector',   packets: pkts(3,1.4) },
  { id:'svc-ep',  from:'svc',     to:'ep',     group:'net',   color:'#22c55e', label:'维护 EP',    packets: pkts(1,2.0) },
  { id:'hpa-dep', from:'hpa',     to:'deploy', group:'net',   color:'#22c55e', label:'扩缩容',      packets: pkts(2,2.2) },
  // 配置注入到 Pod
  { id:'cm-pod',  from:'cm',   to:'pod',       group:'stor',  color:'#fbbf24', label:'env/vol',    packets: pkts(2,1.8) },
  { id:'sec-pod', from:'secret', to:'pod',     group:'stor',  color:'#fbbf24', label:'env/vol',    packets: pkts(2,2.0) },
  { id:'pvc-pod', from:'pvc',   to:'pod',      group:'stor',  color:'#fbbf24', label:'挂载',        packets: pkts(2,1.9) },
  // 安全
  { id:'sa-pod',  from:'sa',   to:'pod',       group:'sec',   color:'#f87171', label:'identity',   packets: pkts(2,2.4) },
  { id:'rb-sa',   from:'rb',   to:'sa',        group:'sec',   color:'#f87171', label:'binds',      packets: pkts(1,2.8) },
  { id:'role-rb', from:'role', to:'rb',        group:'sec',   color:'#f87171', label:'ref',        packets: pkts(1,3.0) },
  { id:'adm-api', from:'admit', to:'apisvr',   group:'sec',   color:'#f87171', label:'intercept',  packets: pkts(2,1.6) },
  // 客户端
  { id:'kube-api', from:'kubectl', to:'apisvr', group:'client', color:'#fb923c', label:'REST',      packets: pkts(3,1.4) },
  { id:'kube-dep', from:'kubectl', to:'deploy', group:'client', color:'#fb923c', label:'apply',     packets: pkts(2,2.0), dash:'4 3' },
].map(e => ({
  ...e,
  d: arc(nd(e.from), nd(e.to), e.bend || 0),
}))

// ── hover 辅助函数 ────────────────────────────────────────────────────
function isRelated(edge) {
  if (!hoveredId.value) return true
  return edge.from === hoveredId.value || edge.to === hoveredId.value
}

function isConnected(nodeId) {
  if (!hoveredId.value) return true
  if (nodeId === hoveredId.value) return true
  return EDGES.some(e =>
    (e.from === hoveredId.value || e.to === hoveredId.value) &&
    (e.from === nodeId || e.to === nodeId)
  )
}

function edgeMid(edge) {
  const m = edge.d.match(/M([\d.]+),([\d.]+)\s+Q([\d.]+),([\d.]+)/)
  if (!m) return { x: 0, y: 0 }
  return { x: parseFloat(m[3]), y: parseFloat(m[4]) }
}

// ── tooltip 位置计算 ──────────────────────────────────────────────────
const tooltipW = 220
const hoveredNode = computed(() => NODES.find(n => n.id === hoveredId.value))
const tooltipLines = computed(() => hoveredNode.value?.desc || [])
const tooltipPos = computed(() => {
  const nd = hoveredNode.value
  if (!nd) return { x: 0, y: 0 }
  let tx = nd.x + nd.r + 16
  let ty = nd.y - 30
  if (tx + tooltipW > W - 20) tx = nd.x - nd.r - tooltipW - 16
  if (ty < 20) ty = 20
  return { x: tx, y: ty }
})

onMounted(() => {})
</script>

<style scoped>
.rr-page {
  display: flex; flex-direction: column;
  height: 100%; background: #0d1117; color: #e6edf3; overflow: hidden;
}

/* ── 工具栏 ─────────────────────────────────────── */
.rr-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; background: #161b22;
  border-bottom: 1px solid rgba(48,54,61,.9); flex-shrink: 0; flex-wrap: wrap; gap: 8px;
}
.rr-brand { display: flex; align-items: center; gap: 10px; }
.rr-brand > span:first-of-type { font-size: 15px; font-weight: 700; color: #e6edf3; }
.rr-sub { font-size: 11px; color: #586069; margin-left: 4px; }
.rr-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.toggle-pill { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: #8d96a0; user-select: none; }
.toggle-pill input { display: none; }
.pill-track { width: 30px; height: 17px; background: rgba(48,54,61,.9); border-radius: 9px; position: relative; transition: background .2s; }
.toggle-pill input:checked ~ .pill-track { background: #38bdf8; }
.pill-thumb { position: absolute; top: 2px; left: 2px; width: 13px; height: 13px; background: #fff; border-radius: 50%; transition: left .2s; }
.toggle-pill input:checked ~ .pill-track .pill-thumb { left: 15px; }
.zoom-btns { display: flex; gap: 2px; }
.ctrl-btn { width: 30px; height: 30px; display: flex; align-items: center; justify-content: center;
  border: 1px solid rgba(48,54,61,.9); background: #161b22; color: #8d96a0;
  border-radius: 7px; cursor: pointer; font-size: 14px; transition: .15s; }
.ctrl-btn:hover { color: #38bdf8; border-color: rgba(56,189,248,.45); }

/* ── 图例 ───────────────────────────────────────── */
.rr-legend {
  display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  padding: 6px 20px; background: #0d1117;
  border-bottom: 1px solid rgba(48,54,61,.6); font-size: 11px; flex-shrink: 0;
}
.leg-item { display: flex; align-items: center; gap: 5px; color: #8d96a0; }
.leg-dot  { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.leg-line { display: inline-block; width: 20px; height: 2px; border-radius: 1px; }
.leg-sep  { color: rgba(48,54,61,.9); }

/* ── 画布 ───────────────────────────────────────── */
.rr-canvas { flex: 1; overflow: hidden; position: relative; }
.rr-svg    { width: 100%; height: 100%; display: block; }

/* ── SVG 文字 ───────────────────────────────────── */
.zone-label { font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; opacity: .7; }
.nd-name  { fill: #e6edf3; font-size: 11.5px; font-weight: 700; pointer-events: none; }
.nd-sub   { fill: #586069; font-size: 9.5px; pointer-events: none; }
.edge-lbl { font-size: 9.5px; font-weight: 600; pointer-events: none; }
.tip-title { font-size: 12px; font-weight: 700; }
.tip-line  { fill: #8d96a0; font-size: 10px; }

/* ── 动效 ───────────────────────────────────────── */
.rr-edge { animation: rrDash 8s linear infinite; }
@keyframes rrDash { to { stroke-dashoffset: -44; } }
.rr-pulse { animation: rrPulse 2.5s ease-in-out infinite; }
@keyframes rrPulse { 0%,100%{ opacity:.15; transform:scale(1); } 50%{ opacity:.35; transform:scale(1.25); } }
.rr-node  { cursor: pointer; transition: opacity .2s; }
.rr-node:hover { filter: brightness(1.2); }
</style>
