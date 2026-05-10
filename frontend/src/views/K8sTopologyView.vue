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
        <!-- 系统架构子模式 -->
        <div v-if="view === 'arch'" class="view-tabs" style="margin-left:4px">
          <button :class="['vtab', { active: archMode === 'app' }]" @click="archMode='app'">应用架构</button>
          <button :class="['vtab', { active: archMode === 'deploy' }]" @click="archMode='deploy'">K8s 部署流程</button>
        </div>
        <!-- 缩放控制 -->
        <div v-if="view === 'arch'" class="zoom-btns">
          <button class="ctrl-btn" @click="zoomIn" title="放大 (+)">＋</button>
          <button class="ctrl-btn" @click="zoomOut" title="缩小 (-)">－</button>
          <button class="ctrl-btn" @click="fitView" title="适应窗口" style="font-size:11px">Fit</button>
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

      <!-- 应用架构 / K8s 部署流程 切换 -->
      <svg v-show="archMode === 'app'"
        class="arch-svg"
        :viewBox="vbStr"
        preserveAspectRatio="xMinYMin meet"
        ref="archSvg"
        :style="{ cursor: svgDrag.active ? 'grabbing' : 'grab' }"
        @wheel.prevent="onArchWheel"
        @mousedown="onArchDragStart"
        @mousemove="onArchDragMove($event); onMouseMove($event)"
        @mouseup="onArchDragEnd"
        @mouseleave="onArchDragEnd(); tooltip.show=false"
      >
        <defs>
          <!-- 背景网格 -->
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M40,0 L0,0 L0,40" fill="none" stroke="rgba(56,189,248,0.07)" stroke-width="1"/>
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
            <stop offset="0%" stop-color="#0c2038" stop-opacity="1"/>
            <stop offset="100%" stop-color="#0f2d52" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-green" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#0a1f15" stop-opacity="1"/>
            <stop offset="100%" stop-color="#0d2b1c" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-orange" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#1f1506" stop-opacity="1"/>
            <stop offset="100%" stop-color="#291c08" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-purple" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#160d29" stop-opacity="1"/>
            <stop offset="100%" stop-color="#1d1136" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-teal" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#071e1f" stop-opacity="1"/>
            <stop offset="100%" stop-color="#0a282a" stop-opacity="1"/>
          </linearGradient>
          <linearGradient id="grad-red" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#200c0c" stop-opacity="1"/>
            <stop offset="100%" stop-color="#2d0f0f" stop-opacity="1"/>
          </linearGradient>
        </defs>

        <!-- 背景 -->
        <rect width="100%" height="100%" fill="#0d1117"/>
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
            :stroke="hoveredNode ? (isEdgeActive(e) ? e.color : e.color+'14') : e.color+'55'"
            :stroke-width="hoveredNode && isEdgeActive(e) ? 2.5 : 1.5"
            :stroke-dasharray="hoveredNode && isEdgeActive(e) ? '8 4' : '6 5'"
            :opacity="hoveredNode ? (isEdgeActive(e) ? 1 : 0.12) : 1"
            :class="{ 'edge-dash': true, 'edge-active': hoveredNode && isEdgeActive(e) }"
            :marker-end="'url(#arr-' + e.marker + ')'"
          />
        </g>

        <!-- 流动粒子（hover 时只在关联边上显示，粒子更大更亮） -->
        <g v-if="animOn" class="particles">
          <g v-for="e in archEdges" :key="'pk-'+e.id"
            :opacity="hoveredNode ? (isEdgeActive(e) ? 1 : 0) : 1">
            <circle
              v-for="pk in e.packets" :key="pk.key"
              :r="hoveredNode && isEdgeActive(e) ? pk.r * 1.4 : pk.r"
              :fill="e.color"
              :filter="'url(#glow-' + (e.glowType || 'blue') + ')'"
            >
              <animateMotion :dur="hoveredNode && isEdgeActive(e) ? (pk.dur*0.7)+'s' : pk.dur+'s'"
                repeatCount="indefinite" :begin="pk.begin+'s'" rotate="auto">
                <mpath :href="'#ae-'+e.id"/>
              </animateMotion>
            </circle>
          </g>
        </g>

        <!-- hover 时在 active 边中点显示流量方向标签 -->
        <g v-if="hoveredNode" class="edge-labels">
          <g v-for="e in archEdges.filter(e => isEdgeActive(e))" :key="'el-'+e.id">
            <rect :x="edgeMid(e).x - 28" :y="edgeMid(e).y - 9"
              width="56" height="17" rx="4"
              :fill="e.color+'30'" :stroke="e.color+'80'" stroke-width="1"/>
            <text :x="edgeMid(e).x" :y="edgeMid(e).y + 4"
              text-anchor="middle" class="edge-label-txt" :fill="e.color">
              {{ e.label || '→' }}
            </text>
          </g>
        </g>

        <!-- 节点 -->
        <g class="nodes" filter="url(#node-shadow)">
          <g v-for="nd in archNodes" :key="nd.id"
            class="arch-node"
            :class="{ hovered: hoveredNode === nd.id }"
            :transform="`translate(${nd.x},${nd.y})`"
            :opacity="hoveredNode && hoveredNode !== nd.id && !isNodeConnected(nd.id) ? 0.18 : 1"
            :style="{ transition: 'opacity .2s' }"
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

      <!-- ─────── K8s 部署流程视图 ─────── -->
      <div v-show="archMode === 'deploy'" class="deploy-flow-wrap">
        <svg class="deploy-svg"
          :viewBox="`0 0 ${DSVG_W} ${DSVG_H}`"
          preserveAspectRatio="xMidYMid meet"
        >
          <defs>
            <pattern id="dg" width="40" height="40" patternUnits="userSpaceOnUse">
              <path d="M40,0 L0,0 L0,40" fill="none" stroke="rgba(56,189,248,0.07)" stroke-width="1"/>
            </pattern>
            <filter id="dglow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="2.5" result="b"/>
              <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <marker id="darr-blue"   markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#38bdf8"/></marker>
            <marker id="darr-orange" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#fbbf24"/></marker>
            <marker id="darr-green"  markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#22c55e"/></marker>
            <marker id="darr-purple" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto"><path d="M0,0 L0,6 L8,3 z" fill="#a78bfa"/></marker>
          </defs>
          <rect width="100%" height="100%" fill="#0d1117"/>
          <rect width="100%" height="100%" fill="url(#dg)"/>

          <!-- 区域标注 -->
          <rect x="20" y="20" width="560" height="720" rx="14"
            fill="none" stroke="#38bdf840" stroke-width="1" stroke-dasharray="8 4"/>
          <text x="32" y="38" class="d-zone-lbl" fill="#38bdf880">← YAML 部署流程</text>
          <rect x="620" y="20" width="560" height="720" rx="14"
            fill="none" stroke="#22c55e40" stroke-width="1" stroke-dasharray="8 4"/>
          <text x="632" y="38" class="d-zone-lbl" fill="#22c55e80">访问流量路由 →</text>
          <rect x="200" y="770" :width="DSVG_W-400" height="140" rx="14"
            fill="#161b22" stroke="#fbbf2440" stroke-width="1.5" stroke-dasharray="6 3"/>
          <text x="220" y="790" class="d-zone-lbl" fill="#fbbf2480">Worker Node</text>

          <!-- 部署流程连线 -->
          <g>
            <path v-for="e in deployEdges" :key="e.id"
              :id="'de-'+e.id" :d="e.d"
              fill="none" :stroke="e.color+'60'" stroke-width="1.5"
              stroke-dasharray="6 4" class="edge-dash"
              :marker-end="`url(#darr-${e.marker})`"/>
            <!-- 步骤序号标注 -->
            <g v-for="e in deployEdges.filter(e=>e.label)" :key="'el-'+e.id">
              <rect :x="e.lx-24" :y="e.ly-9" width="48" height="17" rx="4"
                :fill="e.color+'20'" :stroke="e.color+'50'" stroke-width="1"/>
              <text :x="e.lx" :y="e.ly+4" text-anchor="middle" class="d-edge-lbl" :fill="e.color">{{ e.label }}</text>
            </g>
          </g>

          <!-- 流动粒子 -->
          <g v-if="animOn">
            <g v-for="e in deployEdges" :key="'dp-'+e.id">
              <circle v-for="pk in e.packets" :key="pk.i"
                :r="pk.r" :fill="e.color" filter="url(#dglow)">
                <animateMotion :dur="pk.dur+'s'" repeatCount="indefinite" :begin="pk.begin+'s'">
                  <mpath :href="'#de-'+e.id"/>
                </animateMotion>
              </circle>
            </g>
          </g>

          <!-- 节点 -->
          <g v-for="nd in deployNodes" :key="nd.id">
            <!-- 节点卡片 -->
            <rect :x="nd.x-nd.w/2" :y="nd.y-nd.h/2" :width="nd.w" :height="nd.h"
              rx="10" :fill="nd.fill" :stroke="nd.stroke" stroke-width="1.5"/>
            <rect :x="nd.x-nd.w/2" :y="nd.y-nd.h/2" :width="nd.w" height="3"
              rx="3" :fill="nd.stroke"/>
            <!-- 步骤圆圈 -->
            <circle v-if="nd.step" :cx="nd.x-nd.w/2+14" :cy="nd.y-nd.h/2+14" r="10"
              :fill="nd.stroke" fill-opacity="0.25"/>
            <text v-if="nd.step" :x="nd.x-nd.w/2+14" :y="nd.y-nd.h/2+18"
              text-anchor="middle" class="d-step-num" :fill="nd.stroke">{{ nd.step }}</text>
            <!-- 图标 -->
            <text :x="nd.x" :y="nd.y - 6" text-anchor="middle" class="d-node-icon">{{ nd.icon }}</text>
            <!-- 名称 -->
            <text :x="nd.x" :y="nd.y + 10" text-anchor="middle" class="d-node-name">{{ nd.name }}</text>
            <!-- 副标题 -->
            <text v-if="nd.sub" :x="nd.x" :y="nd.y + 24" text-anchor="middle" class="d-node-sub">{{ nd.sub }}</text>
          </g>
        </svg>
      </div>
    </div>

    <!-- K8s 服务图：4层拓扑 Service→Deployment→Pod→Node -->
    <div v-show="view === 'k8s'" class="k8s-wrap">
      <!-- 顶部过滤 + 统计 -->
      <div class="k8s-topbar">
        <div class="k8s-topbar-stats">
          <span class="tstat"><span class="tstat-dot ok"></span>节点 {{ k8sNodes.length }}</span>
          <span class="tstat"><span class="tstat-dot blue"></span>服务 {{ k8sServices.length }}</span>
          <span class="tstat"><span class="tstat-dot purple"></span>Deployment {{ k8sDeployments.length }}</span>
          <span class="tstat"><span class="tstat-dot ok"></span>Running {{ k8sPods.filter(p=>p.status==='Running').length }}/{{ k8sPods.length }}</span>
          <span v-if="k8sPods.filter(p=>p.status==='Failed').length" class="tstat">
            <span class="tstat-dot err"></span>Failed {{ k8sPods.filter(p=>p.status==='Failed').length }}
          </span>
        </div>
        <div class="zoom-btns">
          <button class="ctrl-btn" @click="k8sZoomIn"  title="放大">＋</button>
          <button class="ctrl-btn" @click="k8sZoomOut" title="缩小">－</button>
          <button class="ctrl-btn" @click="k8sFitView" title="适应窗口" style="font-size:11px">Fit</button>
        </div>
        <button class="ctrl-btn" @click="loadK8s()" :disabled="loading">
          <span v-if="loading" class="spin-sm"></span><span v-else>↺</span>
        </button>
      </div>

      <div v-if="loading" class="k8s-loading">
        <div class="spin-lg"></div><p>加载 K8s 集群数据...</p>
      </div>
      <div v-else-if="!k8sNodes.length && !k8sServices.length" class="k8s-empty">
        <p>未获取到集群数据，请检查 K8s 配置</p>
      </div>
      <svg v-else ref="k8sSvgEl"
        class="k8s-topo-svg"
        :viewBox="k8sVbStr"
        :width="topoW"
        :height="topoH"
        preserveAspectRatio="xMinYMin meet"
        :style="{ cursor: k8sDrag.active ? 'grabbing' : 'grab' }"
        @wheel.prevent="onK8sWheel"
        @mousedown="onK8sDragStart"
        @mousemove="onK8sDragMove"
        @mouseup="onK8sDragEnd"
        @mouseleave="onK8sDragEnd"
      >
        <defs>
          <pattern id="tg" width="36" height="36" patternUnits="userSpaceOnUse">
            <path d="M36,0 L0,0 L0,36" fill="none" stroke="rgba(56,189,248,0.06)" stroke-width="1"/>
          </pattern>
          <filter id="tglow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="2.5" result="b"/>
            <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
          </filter>
          <marker id="tarr" markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto">
            <path d="M0,0 L0,6 L7,3 z" fill="#38bdf850"/>
          </marker>
        </defs>
        <rect width="100%" height="100%" fill="#0d1117"/>
        <rect width="100%" height="100%" fill="url(#tg)"/>

        <!-- 层标签 -->
        <g>
          <text v-for="lbl in TOPO_LAYERS" :key="lbl.id"
            x="16" :y="lbl.y - 4" class="topo-layer-txt">{{ lbl.label }}</text>
          <line v-for="lbl in TOPO_LAYERS" :key="'tl'+lbl.id"
            :x1="110" :y1="lbl.y - 4" :x2="topoW-16" :y2="lbl.y - 4"
            stroke="rgba(56,189,248,0.08)" stroke-width="1" stroke-dasharray="4 8"/>
        </g>

        <!-- 连接线（先渲染在节点之下） -->
        <g class="topo-edges">
          <path v-for="e in topoEdges" :key="e.id"
            :id="'te-'+e.id" :d="e.d"
            fill="none" :stroke="e.color+'40'" stroke-width="1.2"
            stroke-dasharray="5 4" class="topo-edge-dash"
            marker-end="url(#tarr)"/>
        </g>

        <!-- 流量粒子 -->
        <g v-if="animOn">
          <g v-for="e in topoEdges" :key="'tp-'+e.id">
            <circle v-for="pk in e.packets" :key="pk.i"
              :r="pk.r" :fill="e.color" filter="url(#tglow)">
              <animateMotion :dur="pk.dur+'s'" repeatCount="indefinite" :begin="pk.begin+'s'">
                <mpath :href="'#te-'+e.id"/>
              </animateMotion>
            </circle>
          </g>
        </g>

        <!-- Services 层 -->
        <g v-for="(svc, si) in topoSvcs" :key="'s'+si"
          :transform="`translate(${svc.x},${TOPO_Y.svc})`">
          <!-- 外框 -->
          <rect :x="-SVC_W/2" :y="-SVC_H/2" :width="SVC_W" :height="SVC_H"
            rx="10" :fill="svc.fill" :stroke="svc.stroke" stroke-width="1.5"/>
          <!-- 顶部色条 -->
          <rect :x="-SVC_W/2" :y="-SVC_H/2" :width="SVC_W" height="3"
            rx="3" :fill="svc.stroke"/>
          <!-- Service 类型 badge -->
          <rect :x="SVC_W/2-42" :y="-SVC_H/2+6" width="38" height="14" rx="3"
            :fill="svc.type==='NodePort'?'rgba(56,189,248,0.2)':'rgba(139,92,246,0.15)'"/>
          <text :x="SVC_W/2-23" :y="-SVC_H/2+16" text-anchor="middle" class="topo-badge-txt"
            :fill="svc.type==='NodePort'?'#38bdf8':'#a78bfa'">{{ svc.type }}</text>
          <!-- 名称 -->
          <text x="0" :y="-8" text-anchor="middle" class="topo-node-name">{{ truncate(svc.name,16) }}</text>
          <!-- 端口 -->
          <text x="0" y="9" text-anchor="middle" class="topo-node-sub">{{ svc.ports }}</text>
          <!-- 状态点 -->
          <circle :cx="SVC_W/2-7" :cy="-SVC_H/2+8" r="4.5" fill="#22c55e" class="k8s-dot-pulse"/>
          <!-- Namespace -->
          <text x="0" y="24" text-anchor="middle" class="topo-ns-txt">{{ svc.namespace }}</text>
        </g>

        <!-- Deployments 层 -->
        <g v-for="(dep, di) in topoDeployments" :key="'d'+di"
          :transform="`translate(${dep.x},${TOPO_Y.dep})`">
          <rect :x="-DEP_W/2" :y="-DEP_H/2" :width="DEP_W" :height="DEP_H"
            rx="10" :fill="dep.fill" :stroke="dep.stroke" stroke-width="1.5"/>
          <rect :x="-DEP_W/2" :y="-DEP_H/2" :width="DEP_W" height="3"
            rx="3" :fill="dep.stroke"/>
          <!-- 名称 -->
          <text x="0" y="-8" text-anchor="middle" class="topo-node-name">{{ truncate(dep.name,16) }}</text>
          <!-- 副本状态 -->
          <text x="0" y="9" text-anchor="middle" class="topo-node-sub">
            {{ dep.ready }}/{{ dep.desired }} 副本
          </text>
          <!-- 状态点 -->
          <circle :cx="DEP_W/2-7" :cy="-DEP_H/2+8" r="4.5"
            :fill="dep.ready===dep.desired && dep.desired>0 ? '#22c55e' : dep.ready>0 ? '#fbbf24' : '#f87171'"
            :class="dep.ready===dep.desired && dep.desired>0 ? 'k8s-dot-pulse' : ''"/>
          <!-- Namespace -->
          <text x="0" y="24" text-anchor="middle" class="topo-ns-txt">{{ dep.namespace }}</text>
        </g>

        <!-- Pods 层 -->
        <g v-for="(pod, pi) in topoPods" :key="'p'+pi"
          :transform="`translate(${pod.x},${TOPO_Y.pod})`">
          <rect :x="-POD_W/2" :y="-POD_H/2" :width="POD_W" :height="POD_H"
            rx="8" :fill="podColor(pod.status)+'18'" :stroke="podColor(pod.status)+'70'" stroke-width="1.2"/>
          <!-- 状态点 -->
          <circle :cx="-POD_W/2+10" cy="0" r="4"
            :fill="podColor(pod.status)"
            :class="pod.status==='Running'?'k8s-dot-pulse':''"/>
          <!-- Pod 名称 -->
          <text :x="-POD_W/2+20" y="-5" class="topo-pod-name">{{ truncate(pod.name,14) }}</text>
          <text :x="-POD_W/2+20" y="9" class="topo-pod-sub">{{ pod.status }}</text>
        </g>

        <!-- Nodes 层 -->
        <g v-for="(nd, ni) in topoNodes" :key="'n'+ni"
          :transform="`translate(${nd.x},${TOPO_Y.node})`">
          <rect :x="-NODE_W/2" :y="-NODE_H/2" :width="NODE_W" :height="NODE_H"
            rx="10" fill="#0f1e30" :stroke="isNodeReady(nd) ? '#22c55e55' : '#f8717155'" stroke-width="1.5"/>
          <rect :x="-NODE_W/2" :y="-NODE_H/2" :width="NODE_W" height="3"
            rx="3" :fill="isNodeReady(nd) ? '#22c55e' : '#f87171'"/>
          <!-- 名称 -->
          <text x="0" y="-14" text-anchor="middle" class="topo-node-name">{{ nd.name }}</text>
          <text x="0" y="2" text-anchor="middle" class="topo-node-sub">{{ nd.roles }}</text>
          <text x="0" y="17" text-anchor="middle" class="topo-ns-txt">{{ nd.version }}</text>
          <!-- 状态 -->
          <circle :cx="NODE_W/2-8" :cy="-NODE_H/2+8" r="5"
            :fill="isNodeReady(nd) ? '#22c55e' : '#f87171'"
            :class="isNodeReady(nd) ? 'k8s-dot-pulse' : ''"/>
          <!-- Pod 数 -->
          <text :x="NODE_W/2-8" :y="-NODE_H/2+28" text-anchor="middle" class="topo-badge-txt" fill="#38bdf8">
            {{ podsByNode(nd.name).length }}
          </text>
        </g>
      </svg>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch, onMounted, onUnmounted } from 'vue'
import { api } from '../api/index.js'

// ── 常量 ──────────────────────────────────────────────────────────────
const SVG_W = 1440
const SVG_H = 920

// K8s 拓扑图常量（节点尺寸）
const SVC_W  = 168, SVC_H  = 74
const DEP_W  = 162, DEP_H  = 70
const POD_W  = 138, POD_H  = 38
const NODE_W = 200, NODE_H = 76
const MIN_SPACING = 196   // 节点中心最小间距（px）
const PAD_X       = 60    // 左右内边距

// 各层中心 Y 坐标（去掉 Pod 层，Pod 折叠到 Deployment 卡片里）
const TOPO_Y = { svc: 110, dep: 290, pod: 460, node: 620 }

// 层标签
const TOPO_LAYERS = computed(() => [
  { id: 'svc',  y: TOPO_Y.svc  - SVC_H/2  - 12, label: 'SERVICE 层' },
  { id: 'dep',  y: TOPO_Y.dep  - DEP_H/2  - 12, label: 'DEPLOYMENT / WORKLOAD 层' },
  { id: 'pod',  y: TOPO_Y.pod  - POD_H/2  - 12, label: 'POD 层' },
  { id: 'node', y: TOPO_Y.node - NODE_H/2 - 12, label: 'NODE 层' },
])

// 画布总高
const topoH = computed(() => TOPO_Y.node + NODE_H/2 + 60)

// ── 部署流程 SVG 尺寸 ──────────────────────────────────────────────────
const DSVG_W = 1240
const DSVG_H = 960

// ── 状态 ──────────────────────────────────────────────────────────────
const view     = ref('arch')
const archMode = ref('app')   // 'app' | 'deploy'
const animOn   = ref(true)
const loading  = ref(false)
const hoveredNode = ref(null)
const pageEl   = ref(null)
const archWrap = ref(null)

// ── 缩放 / 拖拽状态 ────────────────────────────────────────────────────
const vb = reactive({ x: 0, y: 0, w: SVG_W, h: SVG_H })
const vbStr = computed(() => `${vb.x} ${vb.y} ${vb.w} ${vb.h}`)
const svgDrag = reactive({ active: false, sx: 0, sy: 0, vbx0: 0, vby0: 0 })

function zoomAt(factor, cx, cy) {
  const newW = Math.max(400, Math.min(SVG_W * 3.5, vb.w / factor))
  const newH = newW * SVG_H / SVG_W
  vb.x = cx - (cx - vb.x) * (newW / vb.w)
  vb.y = cy - (cy - vb.y) * (newH / vb.h)
  vb.w = newW; vb.h = newH
}
function zoomIn()  { zoomAt(1.25, vb.x + vb.w/2, vb.y + vb.h/2) }
function zoomOut() { zoomAt(0.80, vb.x + vb.w/2, vb.y + vb.h/2) }
function fitView() { vb.x=0; vb.y=0; vb.w=SVG_W; vb.h=SVG_H }

function onArchWheel(e) {
  const svg = archSvg.value; if (!svg) return
  const rect = svg.getBoundingClientRect()
  const mx = (e.clientX - rect.left) / rect.width  * vb.w + vb.x
  const my = (e.clientY - rect.top)  / rect.height * vb.h + vb.y
  zoomAt(e.deltaY < 0 ? 1.15 : 0.87, mx, my)
}
function onArchDragStart(e) {
  if (e.button !== 0 || e.target.closest('.arch-node')) return
  svgDrag.active = true
  svgDrag.sx = e.clientX; svgDrag.sy = e.clientY
  svgDrag.vbx0 = vb.x;    svgDrag.vby0 = vb.y
}
function onArchDragMove(e) {
  if (!svgDrag.active) return
  const svg = archSvg.value; if (!svg) return
  const rect = svg.getBoundingClientRect()
  const sx = vb.w / rect.width, sy = vb.h / rect.height
  vb.x = svgDrag.vbx0 - (e.clientX - svgDrag.sx) * sx
  vb.y = svgDrag.vby0 - (e.clientY - svgDrag.sy) * sy
}
function onArchDragEnd() { svgDrag.active = false }

// ── K8s 服务图 缩放/拖拽 ────────────────────────────────────────────
const k8sSvgEl = ref(null)
const k8sVb   = reactive({ x: 0, y: 0, w: 0, h: 0 })
const k8sVbStr = computed(() => {
  const w = k8sVb.w || topoW.value
  const h = k8sVb.h || topoH.value
  return `${k8sVb.x} ${k8sVb.y} ${w} ${h}`
})
const k8sDrag = reactive({ active: false, sx: 0, sy: 0, vbx0: 0, vby0: 0 })

// 当拓扑数据变化时重置 viewBox
watch([topoW, topoH], ([w, h]) => { k8sVb.w = w; k8sVb.h = h })

function k8sZoomAt(factor, cx, cy) {
  const curW = k8sVb.w || topoW.value
  const curH = k8sVb.h || topoH.value
  const newW = Math.max(400, Math.min(topoW.value * 3, curW / factor))
  const newH = newW * curH / curW
  k8sVb.x = cx - (cx - k8sVb.x) * (newW / curW)
  k8sVb.y = cy - (cy - k8sVb.y) * (newH / curH)
  k8sVb.w = newW; k8sVb.h = newH
}
function k8sZoomIn()  { k8sZoomAt(1.25, k8sVb.x + (k8sVb.w||topoW.value)/2, k8sVb.y + (k8sVb.h||topoH.value)/2) }
function k8sZoomOut() { k8sZoomAt(0.80, k8sVb.x + (k8sVb.w||topoW.value)/2, k8sVb.y + (k8sVb.h||topoH.value)/2) }
function k8sFitView() { k8sVb.x=0; k8sVb.y=0; k8sVb.w=topoW.value; k8sVb.h=topoH.value }

function onK8sWheel(e) {
  const svg = k8sSvgEl.value; if (!svg) return
  const rect = svg.getBoundingClientRect()
  const curW = k8sVb.w || topoW.value, curH = k8sVb.h || topoH.value
  const mx = (e.clientX - rect.left) / rect.width  * curW + k8sVb.x
  const my = (e.clientY - rect.top)  / rect.height * curH + k8sVb.y
  k8sZoomAt(e.deltaY < 0 ? 1.15 : 0.87, mx, my)
}
function onK8sDragStart(e) {
  if (e.button !== 0) return
  k8sDrag.active = true
  k8sDrag.sx = e.clientX; k8sDrag.sy = e.clientY
  k8sDrag.vbx0 = k8sVb.x; k8sDrag.vby0 = k8sVb.y
}
function onK8sDragMove(e) {
  if (!k8sDrag.active) return
  const svg = k8sSvgEl.value; if (!svg) return
  const rect = svg.getBoundingClientRect()
  const curW = k8sVb.w || topoW.value, curH = k8sVb.h || topoH.value
  const sx = curW / rect.width, sy = curH / rect.height
  k8sVb.x = k8sDrag.vbx0 - (e.clientX - k8sDrag.sx) * sx
  k8sVb.y = k8sDrag.vby0 - (e.clientY - k8sDrag.sy) * sy
}
function onK8sDragEnd() { k8sDrag.active = false }

const k8sNodes       = ref([])
const k8sPods        = ref([])
const k8sServices    = ref([])
const k8sDeployments = ref([])

// 动态画布宽度（必须在上面 4 个 ref 之后定义，避免 TDZ）
const topoW = computed(() => {
  const ns = Math.max(
    k8sServices.value.length    || 1,
    k8sDeployments.value.length || 1,
    topoPods.value.length       || 1,
    k8sNodes.value.length       || 1,
  )
  return Math.max(1280, ns * MIN_SPACING + PAD_X * 2)
})

function isNodeReady(nd) { return nd.status === 'Ready' }

const tooltip = ref({
  show: false, x: 0, y: 0,
  icon: '', name: '', status: '', statusText: '',
  rows: [], calls: [],
})

// ── 层标签（放在层间空白区，不与节点重叠）─────────────────────────
// 节点y: L0=92±36, L1=228±36, L2=378±41, L3=518±33, L4=668±32
// 间隔: L0底128→L1顶192→ 取160; L1底264→L2顶337→ 取300
//        L2底419→L3顶485→ 取452; L3底551→L4顶636→ 取593
const LAYER_LABELS = [
  { id: 0, y:  32, text: '用户入口' },
  { id: 1, y: 160, text: '前端层' },
  { id: 2, y: 300, text: '应用层' },
  { id: 3, y: 452, text: '数据 / 中间件层' },
  { id: 4, y: 593, text: '可观测性 & 外部服务' },
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
  { id:'u-fe',  fromId:'user',        toId:'frontend',    label:'HTTP:30090', color:'#3b82f6', marker:'blue',   glowType:'blue',   packets: makePackets(3,2.0) },
  { id:'fs-fb', fromId:'feishu_in',   toId:'feishu_bot',  label:'Webhook',    color:'#14b8a6', marker:'blue',   glowType:'blue',   packets: makePackets(2,2.5) },
  { id:'jk-be', fromId:'jenkins_in',  toId:'backend',     label:'API',        color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(2,2.8) },
  { id:'fe-be', fromId:'frontend',    toId:'backend',     label:'REST API',   color:'#3b82f6', marker:'blue',   glowType:'blue',   packets: makePackets(3,1.8) },
  { id:'fb-be', fromId:'feishu_bot',  toId:'backend',     label:'内部API',    color:'#14b8a6', marker:'blue',   glowType:'blue',   packets: makePackets(2,2.2) },
  { id:'be-lk', fromId:'backend',     toId:'loki',        label:'日志查询',   color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(3,1.6) },
  { id:'be-pm', fromId:'backend',     toId:'prometheus',  label:'指标查询',   color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(3,1.8) },
  { id:'be-rd', fromId:'backend',     toId:'redis',       label:'缓存R/W',    color:'#ef4444', marker:'blue',   glowType:'blue',   packets: makePackets(2,1.4) },
  { id:'be-es', fromId:'backend',     toId:'es',          label:'全文搜索',   color:'#22c55e', marker:'green',  glowType:'green',  packets: makePackets(2,2.0) },
  { id:'be-am', fromId:'backend',     toId:'alertmanager',label:'告警推送',   color:'#ef4444', marker:'orange', glowType:'blue',   packets: makePackets(2,3.0) },
  { id:'am-be', fromId:'alertmanager',toId:'backend',     label:'Webhook回调',color:'#ef4444', marker:'orange', glowType:'blue',   packets: makePackets(1,2.5) },
  { id:'lk-gf', fromId:'loki',        toId:'grafana',     label:'数据源',     color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(2,2.2) },
  { id:'pm-gf', fromId:'prometheus',  toId:'grafana',     label:'数据源',     color:'#f59e0b', marker:'orange', glowType:'blue',   packets: makePackets(2,2.0) },
  { id:'be-cl', fromId:'backend',     toId:'claude',      label:'AI推理SSE',  color:'#a855f7', marker:'purple', glowType:'blue',   packets: makePackets(3,1.5) },
  { id:'be-qw', fromId:'backend',     toId:'qwen',        label:'AI推理',     color:'#a855f7', marker:'purple', glowType:'blue',   packets: makePackets(2,2.0) },
  { id:'be-fs', fromId:'backend',     toId:'feishu_svc',  label:'消息推送',   color:'#14b8a6', marker:'blue',   glowType:'blue',   packets: makePackets(2,3.5) },
  { id:'be-sw', fromId:'backend',     toId:'skywalking',  label:'Trace上报',  color:'#a855f7', marker:'purple', glowType:'blue',   packets: makePackets(2,2.4) },
].map(e => ({
  ...e,
  d: edgePath(e.fromId, e.toId),
})))

// ── Hover 高亮辅助 ────────────────────────────────────────────────────
// 判断边是否与当前 hover 节点相关
function isEdgeActive(edge) {
  if (!hoveredNode.value) return true
  return edge.fromId === hoveredNode.value || edge.toId === hoveredNode.value
}

// 判断节点是否与 hover 节点有直接连线（含自身）
function isNodeConnected(nodeId) {
  if (!hoveredNode.value) return true
  if (nodeId === hoveredNode.value) return true
  return archEdges.value.some(e =>
    (e.fromId === hoveredNode.value || e.toId === hoveredNode.value) &&
    (e.fromId === nodeId || e.toId === nodeId)
  )
}

// 计算边路径中点（用于显示标签）
function edgeMid(edge) {
  // 用 d 路径中的控制点估算中点
  const m = edge.d.match(/M([\d.]+),([\d.]+).*?([\d.]+),([\d.]+)$/)
  if (!m) return { x: 0, y: 0 }
  return {
    x: (parseFloat(m[1]) + parseFloat(m[3])) / 2,
    y: (parseFloat(m[2]) + parseFloat(m[4])) / 2,
  }
}

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

// ── K8s 部署流程图节点 & 连线 ─────────────────────────────────────────
// 两列并排：左=YAML部署流程，右=流量访问路径，底部共享 Node/Pod
const DW = 168, DH = 72  // 部署流节点尺寸

// 辅助：生成粒子
function dPkts(n, dur, color) {
  return Array.from({length:n}, (_,i) => ({ i, r:3.5-i*0.5, dur:dur+i*0.3, begin:i*dur/n }))
}

const deployNodes = computed(() => {
  // 左列 x=310, 右列 x=930, 底部收敛 x=620
  const L = 310, R = 930, C = 620
  return [
    // ─ 左：YAML 部署流程 ─────────────────────────────────────
    { id:'ci',     step:1, icon:'👨‍💻', name:'Developer / CI',  sub:'kubectl apply',
      x:L, y:80,  w:DW, h:DH, fill:'#0c2038', stroke:'#38bdf8' },
    { id:'apisvr', step:2, icon:'⚙️',  name:'API Server',       sub:':6443  认证/准入',
      x:L, y:220, w:DW, h:DH, fill:'#0c2038', stroke:'#38bdf8' },
    { id:'etcd',   step:2, icon:'🗄️',  name:'etcd',             sub:':2379  持久化状态',
      x:L+230, y:220, w:DW, h:DH, fill:'#160d29', stroke:'#a78bfa' },
    { id:'ctrlmgr',step:3, icon:'🔄',  name:'Controller Manager', sub:'维护期望状态',
      x:L, y:370, w:DW, h:DH, fill:'#071e1f', stroke:'#22d3ee' },
    { id:'sched',  step:4, icon:'📅',  name:'Scheduler',        sub:'选择目标 Node',
      x:L, y:510, w:DW, h:DH, fill:'#0a1f15', stroke:'#22c55e' },
    { id:'kubelet',step:5, icon:'🤖',  name:'Kubelet',          sub:'Node Agent',
      x:C-80, y:750, w:DW, h:DH, fill:'#1f1506', stroke:'#fbbf24' },
    { id:'cri',    step:6, icon:'🐳',  name:'Container Runtime', sub:'containerd / CRI',
      x:C-80, y:880, w:DW+10, h:DH, fill:'#0c2038', stroke:'#38bdf8' },

    // ─ 右：流量访问路径 ──────────────────────────────────────
    { id:'ext',    step:1, icon:'🌐', name:'External User',    sub:'Internet / Browser',
      x:R, y:80,  w:DW, h:DH, fill:'#0c2038', stroke:'#38bdf8' },
    { id:'nodeport',step:2,icon:'🚪', name:'NodePort / Ingress',sub:':30090 / :30800',
      x:R, y:220, w:DW+10, h:DH, fill:'#0c2038', stroke:'#38bdf8' },
    { id:'kproxy', step:3, icon:'🔀', name:'kube-proxy',       sub:'IPVS / iptables',
      x:R, y:370, w:DW, h:DH, fill:'#160d29', stroke:'#a78bfa' },
    { id:'svc',    step:4, icon:'🔌', name:'Service',          sub:'ClusterIP 负载均衡',
      x:R, y:510, w:DW+10, h:DH, fill:'#071e1f', stroke:'#22d3ee' },

    // ─ 底部：Node / Pod（两列汇聚）────────────────────────────
    { id:'pod', step:7, icon:'🟢', name:'Pod (Running)',     sub:'应用容器 · 状态上报',
      x:C+60, y:880, w:DW+20, h:DH, fill:'#0a1f15', stroke:'#22c55e' },
  ]
})

// 边辅助：取节点坐标
function dn(id) { return deployNodes.value.find(n=>n.id===id) }
function dElbow(a, b) {
  if (!a||!b) return ''
  const ay=a.y+a.h/2, by=b.y-b.h/2, mid=(ay+by)/2
  return `M${a.x},${ay} C${a.x},${mid} ${b.x},${mid} ${b.x},${by}`
}
// 水平边（API Server ↔ etcd）
function dHoriz(a, b) {
  if (!a||!b) return `M${a?.x||0},${a?.y||0} L${b?.x||0},${b?.y||0}`
  const ax = a.x+a.w/2, bx = b.x-b.w/2, my = (a.y+b.y)/2
  return `M${ax},${a.y} C${ax+30},${a.y} ${bx-30},${b.y} ${bx},${b.y}`
}

const deployEdges = computed(() => {
  const nodes = deployNodes.value
  const edges = []
  const addE = (id, fromId, toId, color, marker, label, pkts=2, dur=1.8) => {
    const a=dn(fromId), b=dn(toId)
    if (!a||!b) return
    const d = fromId==='apisvr'&&toId==='etcd' ? dHoriz(a,b) : dElbow(a,b)
    // 标签位置：中点
    const pts = d.match(/\d+(\.\d+)?/g)?.map(Number) || []
    const lx = a.x+(b.x-a.x)*0.5, ly = a.y+(b.y-a.y)*0.5
    edges.push({ id, d, color, marker, label, lx, ly,
      packets: dPkts(pkts, dur, color) })
  }

  // 部署流程（左列）
  addE('ci-api',   'ci',    'apisvr',  '#38bdf8', 'blue',   '① apply',    3, 1.6)
  addE('api-etc',  'apisvr','etcd',    '#a78bfa', 'purple', '② persist',  2, 2.0)
  addE('etc-api',  'etcd',  'apisvr',  '#a78bfa', 'purple', '③ watch',    1, 2.5)
  addE('api-cm',   'apisvr','ctrlmgr', '#22d3ee', 'blue',   '④ notify',   2, 1.8)
  addE('cm-api',   'ctrlmgr','apisvr', '#22d3ee', 'blue',   null, 1, 2.2)
  addE('api-sch',  'apisvr','sched',   '#22c55e', 'green',  '⑤ schedule', 2, 1.9)
  addE('sch-kub',  'sched', 'kubelet', '#fbbf24', 'orange', '⑥ assign',   2, 1.7)
  addE('kub-cri',  'kubelet','cri',    '#38bdf8', 'blue',   '⑦ CRI',      2, 1.5)
  addE('cri-pod',  'cri',   'pod',     '#22c55e', 'green',  '⑧ create',   3, 1.4)

  // 流量路径（右列）
  addE('ext-np',   'ext',    'nodeport','#38bdf8', 'blue',   'HTTP req',   3, 1.5)
  addE('np-kp',    'nodeport','kproxy',  '#a78bfa', 'purple', 'route',      2, 1.8)
  addE('kp-svc',   'kproxy', 'svc',     '#22d3ee', 'blue',   'ClusterIP',  2, 1.9)
  addE('svc-pod',  'svc',    'pod',     '#22c55e', 'green',  '→ Pod',      3, 1.6)

  // 状态回写
  addE('pod-api',  'pod',   'apisvr',  '#fbbf24', 'orange', 'status',     1, 3.0)

  return edges
})

// ── K8s 数据 ──────────────────────────────────────────────────────────
async function loadK8s() {
  loading.value = true
  try {
    const [nr, pr, sr, dr] = await Promise.allSettled([
      api.k8sNodes(), api.k8sPods(), api.k8sServices(), api.k8sDeployments(),
    ])
    const pick = r => r.status === 'fulfilled' ? (r.value?.data ?? r.value ?? []) : []
    k8sNodes.value       = pick(nr)
    k8sPods.value        = pick(pr)
    k8sServices.value    = pick(sr)
    k8sDeployments.value = pick(dr)
  } finally {
    loading.value = false
  }
}

function podsByNode(name) {
  return k8sPods.value.filter(p => p.node === name)
}

// ── 拓扑布局计算 ──────────────────────────────────────────────────────
function spreadX(count, w, pad = PAD_X) {
  if (!count) return []
  const W = w ?? topoW.value
  const usable = W - pad * 2
  return Array.from({ length: count }, (_, i) =>
    pad + usable * (i + 0.5) / count
  )
}

// 服务节点（含端口、颜色）
const topoSvcs = computed(() => {
  const xs = spreadX(k8sServices.value.length)
  return k8sServices.value.map((s, i) => ({
    ...s, x: xs[i] ?? 640,
    ports: (s.ports || []).join(' · ').slice(0, 22) || '-',
    fill:  s.type === 'NodePort' ? 'rgba(56,189,248,0.08)' : 'rgba(139,92,246,0.06)',
    stroke: s.type === 'NodePort' ? '#38bdf8' : '#a78bfa',
  }))
})

// Deployment 节点
const topoDeployments = computed(() => {
  const xs = spreadX(k8sDeployments.value.length)
  return k8sDeployments.value.map((d, i) => {
    const ok = d.ready === d.desired && d.desired > 0
    return {
      ...d, x: xs[i] ?? 640,
      ready:   d.ready   ?? d.readyReplicas   ?? 0,
      desired: d.desired ?? d.replicas        ?? 0,
      fill:   ok ? 'rgba(34,197,94,0.06)' : d.ready > 0 ? 'rgba(251,191,36,0.06)' : 'rgba(248,113,113,0.06)',
      stroke: ok ? '#22c55e'              : d.ready > 0 ? '#fbbf24'               : '#f87171',
    }
  })
})

// Pod 节点（最多取前 24 个）
const topoPods = computed(() => {
  const MAX = 24
  const pods = k8sPods.value.slice(0, MAX)
  const xs = spreadX(pods.length)
  return pods.map((p, i) => ({ ...p, x: xs[i] ?? 640 }))
})

// Node 节点
const topoNodes = computed(() => {
  const xs = spreadX(k8sNodes.value.length)
  return k8sNodes.value.map((n, i) => ({ ...n, x: xs[i] ?? 640 }))
})

// ── 连接线 ────────────────────────────────────────────────────────────
function elbowPath(x1, y1, x2, y2) {
  const mid = (y1 + y2) / 2
  return `M${x1},${y1} C${x1},${mid} ${x2},${mid} ${x2},${y2}`
}
function mkPackets(color, n = 2, baseDur = 1.8) {
  return Array.from({ length: n }, (_, i) => ({
    i, r: 3.5 - i * 0.5, dur: baseDur + i * 0.35, begin: i * baseDur / n,
  }))
}

const topoEdges = computed(() => {
  const edges = []
  let eid = 0

  // Service → Deployment (name prefix match)
  topoSvcs.value.forEach(svc => {
    const base = svc.name.replace(/-(svc|service|headless|np)$/i, '').toLowerCase()
    topoDeployments.value.forEach(dep => {
      const db = dep.name.toLowerCase()
      if (db.startsWith(base) || base.startsWith(db)) {
        edges.push({
          id: `sd-${eid++}`, d: elbowPath(svc.x, TOPO_Y.svc + SVC_H/2, dep.x, TOPO_Y.dep - DEP_H/2),
          color: svc.type === 'NodePort' ? '#38bdf8' : '#a78bfa',
          packets: mkPackets(svc.type === 'NodePort' ? '#38bdf8' : '#a78bfa', 3, 1.6),
        })
      }
    })
  })

  // Deployment → Pod (name prefix match, limit connections)
  topoDeployments.value.forEach(dep => {
    topoPods.value
      .filter(p => p.name.toLowerCase().startsWith(dep.name.toLowerCase()))
      .slice(0, 4)
      .forEach(pod => {
        edges.push({
          id: `dp-${eid++}`, d: elbowPath(dep.x, TOPO_Y.dep + DEP_H/2, pod.x, TOPO_Y.pod - POD_H/2),
          color: dep.stroke,
          packets: mkPackets(dep.stroke, 2, 2.0),
        })
      })
  })

  // Pod → Node
  topoPods.value.forEach(pod => {
    const nd = topoNodes.value.find(n => n.name === pod.node)
    if (nd) {
      edges.push({
        id: `pn-${eid++}`, d: elbowPath(pod.x, TOPO_Y.pod + POD_H/2, nd.x, TOPO_Y.node - NODE_H/2),
        color: podColor(pod.status),
        packets: mkPackets(podColor(pod.status), 1, 2.4),
      })
    }
  })

  return edges
})

function podColor(status) {
  // 后端返回 pod.status，可能值：Running / Pending / Failed / Succeeded / Unknown / NotReady
  if (!status) return '#6b7280'
  if (status === 'Running')   return '#22c55e'
  if (status === 'Pending')   return '#f59e0b'
  if (status === 'Succeeded') return '#3b82f6'
  if (status === 'Failed')    return '#ef4444'
  return '#94a3b8'
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
  height: 100%; background: #0d1117; color: #e6edf3; overflow: hidden;
}

/* ── 工具栏 ─────────────────────────────────────────────── */
.arch-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; background: #161b22;
  border-bottom: 1px solid rgba(48,54,61,0.9); flex-shrink: 0; flex-wrap: wrap; gap: 8px;
}
.arch-brand { display: flex; align-items: center; gap: 10px; }
.brand-icon { width: 20px; height: 20px; stroke: #38bdf8; }
.arch-brand > span:first-of-type { font-size: 15px; font-weight: 700; color: #e6edf3; }
.arch-subtitle { font-size: 11px; color: #586069; margin-left: 4px; }
.arch-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.view-tabs { display: flex; background: #0d1117; border-radius: 8px; padding: 3px; gap: 2px; border: 1px solid rgba(48,54,61,0.9); }
.vtab { padding: 5px 14px; border-radius: 6px; border: none; background: transparent; color: #586069; cursor: pointer; font-size: 12px; transition: .15s; }
.vtab.active { background: #38bdf8; color: #0d1117; font-weight: 600; }
.vtab:hover:not(.active) { color: #e6edf3; background: rgba(255,255,255,0.06); }

.toggle-pill { display: flex; align-items: center; gap: 7px; cursor: pointer; font-size: 12px; color: #8d96a0; user-select: none; }
.toggle-pill input { display: none; }
.pill-track { width: 32px; height: 18px; background: rgba(48,54,61,0.9); border-radius: 9px; position: relative; transition: background .2s; }
.toggle-pill input:checked ~ .pill-track { background: #38bdf8; }
.pill-thumb { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; background: #fff; border-radius: 50%; transition: left .2s; }
.toggle-pill input:checked ~ .pill-track .pill-thumb { left: 16px; }

.ctrl-btn { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(48,54,61,0.9); background: #161b22; color: #8d96a0; border-radius: 8px; cursor: pointer; font-size: 14px; transition: .15s; }
.ctrl-btn:hover { color: #38bdf8; border-color: rgba(56,189,248,0.45); }
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
.layer-txt { fill: #586069; font-size: 10px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; }
.node-icon { font-size: 18px; }
.node-name { fill: #e6edf3; font-size: 11.5px; font-weight: 700; }
.node-port { fill: #8d96a0; font-size: 9.5px; }
.grp-label { font-size: 10px; font-weight: 600; opacity: 0.7; }

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
.edge-active { animation: dashFlow 2.5s linear infinite; filter: drop-shadow(0 0 3px currentColor); }
@keyframes dashFlow { to { stroke-dashoffset: -44; } }

/* hover 边标签 */
.edge-label-txt { font-size: 10px; font-weight: 700; pointer-events: none; }

.hover-ring { animation: ringPulse .6s ease-in-out infinite alternate; }
@keyframes ringPulse { from { opacity: .5; } to { opacity: 1; } }

/* ── 工具提示 ────────────────────────────────────────────── */
.node-tooltip {
  position: absolute; z-index: 100; pointer-events: none;
  background: #161b22; border: 1px solid rgba(48,54,61,0.9);
  border-radius: 12px; padding: 12px 14px; min-width: 200px; max-width: 280px;
  box-shadow: 0 8px 32px rgba(0,0,0,.6);
}
.tip-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.tip-icon { font-size: 18px; }
.tip-name { font-size: 13px; font-weight: 700; color: #e6edf3; flex: 1; }
.tip-badge { padding: 2px 8px; border-radius: 999px; font-size: 10px; font-weight: 600; }
.tip-badge.ok   { background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid rgba(34,197,94,0.3); }
.tip-badge.warn { background: rgba(251,191,36,0.15); color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }
.tip-rows { display: flex; flex-direction: column; gap: 5px; }
.tip-row { display: flex; justify-content: space-between; font-size: 11px; }
.tip-key { color: #586069; }
.tip-val { color: #e6edf3; font-weight: 500; text-align: right; max-width: 160px; }
.tip-calls { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(48,54,61,0.9); }
.tip-calls-title { font-size: 10px; color: #586069; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .05em; }
.tip-call-item { font-size: 11px; color: #38bdf8; padding: 1px 0; }

/* ── 图例 ────────────────────────────────────────────────── */
.arch-legend {
  position: absolute; bottom: 20px; right: 20px;
  background: rgba(22,27,34,0.92); border: 1px solid rgba(48,54,61,0.9);
  border-radius: 10px; padding: 10px 14px;
  display: flex; flex-direction: column; gap: 5px;
  font-size: 11px; backdrop-filter: blur(8px);
  box-shadow: 0 4px 24px rgba(0,0,0,.4);
}
.leg-row { display: flex; align-items: center; gap: 7px; color: #8d96a0; }
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

/* ── K8s 服务拓扑图 ──────────────────────────────────────── */
/* 外层横向 + 纵向滚动，SVG 按实际内容宽度展开 */
.k8s-wrap { flex: 1; overflow: auto; display: flex; flex-direction: column; }
.k8s-topo-svg { height: auto; display: block; min-width: 100%; }

.k8s-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 16px; background: #161b22; border-bottom: 1px solid rgba(48,54,61,0.9);
  flex-shrink: 0;
}
.k8s-topbar-stats { display: flex; gap: 16px; flex-wrap: wrap; }
.tstat { display: flex; align-items: center; gap: 5px; font-size: 12px; color: #8d96a0; }
.tstat-dot { width: 7px; height: 7px; border-radius: 50%; }
.tstat-dot.ok   { background: #22c55e; }
.tstat-dot.blue { background: #38bdf8; }
.tstat-dot.purple { background: #a78bfa; }
.tstat-dot.err  { background: #f87171; }

.k8s-loading, .k8s-empty {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 200px; color: #8b949e; gap: 12px;
}

/* SVG 텍스트 스타일 */
.topo-layer-txt { fill: #3c444e; font-size: 9px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.topo-node-name { fill: #e6edf3; font-size: 11.5px; font-weight: 700; }
.topo-node-sub  { fill: #8d96a0; font-size: 10px; }
.topo-ns-txt    { fill: #586069; font-size: 9.5px; }
.topo-badge-txt { font-size: 9px; font-weight: 700; }
.topo-pod-name  { fill: #e6edf3; font-size: 10.5px; font-weight: 600; dominant-baseline: middle; }
.topo-pod-sub   { fill: #8d96a0; font-size: 9.5px; dominant-baseline: middle; }

.topo-edge-dash { animation: dashFlow 6s linear infinite; }
@keyframes dashFlow { to { stroke-dashoffset: -36; } }

/* ── 缩放控制 ──────────────────────────────────────── */
.zoom-btns { display: flex; gap: 2px; }

/* ── K8s 部署流程视图 ────────────────────────────────── */
.deploy-flow-wrap { flex: 1; overflow: auto; padding: 8px; }
.deploy-svg { width: 100%; max-width: 1240px; height: auto; display: block; margin: 0 auto; }
.d-zone-lbl { font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.d-node-icon { font-size: 18px; dominant-baseline: middle; }
.d-node-name { fill: #e6edf3; font-size: 11.5px; font-weight: 700; }
.d-node-sub  { fill: #8d96a0; font-size: 10px; }
.d-step-num  { font-size: 9px; font-weight: 800; }
.d-edge-lbl  { font-size: 9.5px; font-weight: 600; }
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
