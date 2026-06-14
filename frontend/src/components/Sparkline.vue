<template>
  <div class="spark-wrap" :style="{ height: height + 'px' }">
    <svg :viewBox="`0 0 ${width} ${height}`" preserveAspectRatio="none" class="spark-svg">
      <!-- 网格 -->
      <g v-if="showGrid" class="spark-grid">
        <line v-for="(y, i) in gridYs" :key="'h' + i"
          x1="0" :y1="y" :x2="width" :y2="y" />
      </g>

      <!-- 面积 -->
      <path v-if="areaPath" :d="areaPath" class="spark-area" :style="{ fill: tone }" />

      <!-- 折线 -->
      <path :d="linePath" class="spark-line" :style="{ stroke: tone }" />

      <!-- 最后一点 -->
      <circle v-if="lastPoint" :cx="lastPoint.x" :cy="lastPoint.y" r="2.5"
        class="spark-dot" :style="{ fill: tone }" />

      <!-- 鼠标悬停指示线 -->
      <g v-if="hoverIdx >= 0 && hoverPoint" class="spark-hover">
        <line :x1="hoverPoint.x" y1="0" :x2="hoverPoint.x" :y2="height" />
        <circle :cx="hoverPoint.x" :cy="hoverPoint.y" r="3" :style="{ fill: tone }" />
      </g>
    </svg>

    <!-- 当前值 / Y 轴范围 / hover tooltip -->
    <div v-if="showLabels" class="spark-labels">
      <span class="spark-current" :style="{ color: tone }">
        {{ hoverIdx >= 0 ? fmt(values[hoverIdx]) : fmt(lastValue) }}{{ unit }}
      </span>
      <span class="spark-range">
        min {{ fmt(minVal) }} / max {{ fmt(maxVal) }}
      </span>
    </div>

    <div
      class="spark-tracker"
      @mousemove="onMouseMove"
      @mouseleave="hoverIdx = -1"
    ></div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  values: { type: Array, default: () => [] },     // [number]
  width:  { type: Number, default: 280 },
  height: { type: Number, default: 60 },
  tone:   { type: String, default: '#D97757' },   // 陶土橙
  showGrid: { type: Boolean, default: true },
  showLabels: { type: Boolean, default: true },
  unit:   { type: String, default: '' },
  fmt:    { type: Function, default: (v) => v == null ? '—' : (Math.round(v * 100) / 100) },
})

const hoverIdx = ref(-1)

const validVals = computed(() => props.values.filter(v => Number.isFinite(v)))
const minVal = computed(() => validVals.value.length ? Math.min(...validVals.value) : 0)
const maxVal = computed(() => validVals.value.length ? Math.max(...validVals.value) : 1)
const lastValue = computed(() => {
  for (let i = props.values.length - 1; i >= 0; i--) {
    if (Number.isFinite(props.values[i])) return props.values[i]
  }
  return null
})

function pointAt(i, v) {
  const n = props.values.length
  const x = n <= 1 ? props.width / 2 : (i / (n - 1)) * props.width
  const range = Math.max(maxVal.value - minVal.value, 1e-9)
  const padY = 4
  const y = props.height - padY - ((v - minVal.value) / range) * (props.height - padY * 2)
  return { x, y }
}

const linePath = computed(() => {
  if (!props.values.length) return ''
  const parts = []
  let firstDrawn = false
  props.values.forEach((v, i) => {
    if (!Number.isFinite(v)) return
    const p = pointAt(i, v)
    parts.push(`${firstDrawn ? 'L' : 'M'} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
    firstDrawn = true
  })
  return parts.join(' ')
})

const areaPath = computed(() => {
  if (!props.values.length || !linePath.value) return ''
  // 沿曲线下方闭合
  const validIdx = props.values
    .map((v, i) => Number.isFinite(v) ? i : -1)
    .filter(i => i >= 0)
  if (!validIdx.length) return ''
  const first = pointAt(validIdx[0], props.values[validIdx[0]])
  const last  = pointAt(validIdx[validIdx.length - 1], props.values[validIdx[validIdx.length - 1]])
  return `${linePath.value} L ${last.x.toFixed(1)} ${props.height} L ${first.x.toFixed(1)} ${props.height} Z`
})

const lastPoint = computed(() => {
  for (let i = props.values.length - 1; i >= 0; i--) {
    if (Number.isFinite(props.values[i])) return pointAt(i, props.values[i])
  }
  return null
})

const hoverPoint = computed(() => {
  if (hoverIdx.value < 0) return null
  const v = props.values[hoverIdx.value]
  if (!Number.isFinite(v)) return null
  return pointAt(hoverIdx.value, v)
})

const gridYs = computed(() => {
  // 3 条水平网格线
  const padY = 4
  const usable = props.height - padY * 2
  return [padY, padY + usable * 0.5, props.height - padY]
})

function onMouseMove(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const x = e.clientX - rect.left
  const n = props.values.length
  if (n <= 1) { hoverIdx.value = 0; return }
  const idx = Math.round((x / rect.width) * (n - 1))
  hoverIdx.value = Math.max(0, Math.min(n - 1, idx))
}
</script>

<style scoped>
.spark-wrap {
  position: relative;
  width: 100%;
  background: var(--bg-surface);
  border-radius: 6px;
  overflow: hidden;
}
.spark-svg { width: 100%; height: 100%; display: block; }
.spark-grid line { stroke: var(--border-light); stroke-width: 0.5; stroke-dasharray: 2 3; }
.spark-area { opacity: 0.16; }
.spark-line { fill: none; stroke-width: 1.6; stroke-linejoin: round; stroke-linecap: round; }
.spark-dot { stroke: var(--bg-card); stroke-width: 1.2; }
.spark-hover line { stroke: var(--border-strong); stroke-width: 1; stroke-dasharray: 2 2; }
.spark-hover circle { stroke: var(--bg-card); stroke-width: 1.5; }

.spark-labels {
  position: absolute; top: 4px; right: 8px;
  display: flex; flex-direction: column; align-items: flex-end;
  font-size: 10.5px; pointer-events: none;
  text-shadow: 0 0 2px var(--bg-base);
}
.spark-current { font-weight: 700; font-family: var(--font-mono); font-size: 13px; }
.spark-range { color: var(--text-muted); font-family: var(--font-mono); }

.spark-tracker {
  position: absolute; inset: 0; cursor: crosshair;
}
</style>
