<template>
  <div class="mw-page page">
    <section class="mw-hero card">
      <div class="mw-hero-left">
        <div class="mw-badge">
          <span class="mw-badge-icon" v-html="MIDDLEWARE_ICON"></span>
          <span>Middleware Overview</span>
        </div>
        <div class="mw-title-row">
          <h1>中间件概览</h1>
          <span class="mw-title-pill" :class="abnormalInstances ? 'danger' : 'ok'">
            {{ abnormalInstances ? `${abnormalInstances} 个异常实例` : '运行正常' }}
          </span>
        </div>
        <p class="mw-subtitle">
          聚合 Prometheus 采集的中间件状态、实例可用性与关键指标，把故障入口提前暴露出来。
        </p>
      </div>

      <div class="mw-hero-actions">
        <button class="btn btn-outline" :disabled="loading" @click="resetView">
          重置视图
        </button>
        <button class="btn btn-primary" :disabled="loading" @click="fetchAll">
          {{ loading ? '刷新中...' : '刷新数据' }}
        </button>
      </div>
    </section>

    <section class="mw-kpi-grid">
      <article
        v-for="item in topStats"
        :key="item.label"
        class="mw-kpi card"
        :class="item.tone"
      >
        <div class="mw-kpi-label">{{ item.label }}</div>
        <div class="mw-kpi-value">{{ item.value }}</div>
        <div class="mw-kpi-hint">{{ item.hint }}</div>
      </article>
    </section>

    <section v-if="loading && !instances.length" class="card mw-loading">
      <div class="spinner"></div>
      <span>正在加载中间件状态...</span>
    </section>

    <section v-else-if="!instances.length" class="card mw-empty">
      <div class="mw-empty-icon" v-html="MIDDLEWARE_ICON"></div>
      <h3>Prometheus 中暂未发现中间件 Exporter</h3>
      <p>请先确认 `mysql_exporter`、`redis_exporter`、`nginx_exporter` 等已接入监控。</p>
    </section>

    <template v-else>
      <section class="mw-main-grid">
        <article class="card mw-types-card">
          <div class="mw-card-head">
            <div>
              <h3>中间件分组</h3>
              <p>按类型查看可用性，优先聚焦有异常的组</p>
            </div>
            <span class="mw-card-meta">{{ summaryCards.length }} 类</span>
          </div>

          <div class="mw-type-grid">
            <button
              v-for="item in summaryCards"
              :key="item.type"
              class="mw-type-card"
              :class="[item.tone, { active: selectedType === item.type }]"
              type="button"
              @click="selectType(item.type)"
            >
              <div class="mw-type-head">
                <span class="mw-type-icon" :class="item.icon">
                  <span v-html="iconSvg(item.icon)"></span>
                </span>
                <span class="mw-type-health" :class="item.tone">{{ item.healthText }}</span>
              </div>
              <div class="mw-type-title">{{ item.label }}</div>
              <div class="mw-type-ratio">
                <strong>{{ item.up }}</strong>
                <span>/ {{ item.total }} 在线</span>
              </div>
              <div class="mw-type-progress">
                <span :style="{ width: `${item.availability}%` }"></span>
              </div>
              <div class="mw-type-foot">
                <span>可用率 {{ item.availabilityText }}</span>
                <span>{{ item.riskText }}</span>
              </div>
            </button>
          </div>
        </article>

        <article class="card mw-alert-card">
          <div class="mw-card-head">
            <div>
              <h3>异常概览</h3>
              <p>把当前最值得排查的实例和中间件组排在前面</p>
            </div>
            <span class="mw-card-meta">{{ anomalyItems.length }} 条</span>
          </div>

          <div v-if="anomalyItems.length" class="mw-alert-list">
            <button
              v-for="item in anomalyItems"
              :key="item.key"
              class="mw-alert-item"
              :class="item.tone"
              type="button"
              @click="handleAnomalyClick(item)"
            >
              <div class="mw-alert-level">{{ item.level }}</div>
              <div class="mw-alert-body">
                <div class="mw-alert-title">{{ item.title }}</div>
                <div class="mw-alert-desc">{{ item.description }}</div>
              </div>
              <div class="mw-alert-tail">查看</div>
            </button>
          </div>

          <div v-else class="mw-alert-empty">
            <div class="mw-alert-empty-dot"></div>
            <div>
              <strong>当前没有发现明显异常</strong>
              <p>建议抽查 Redis / MySQL / Nginx 关键指标，确认业务高峰前没有隐患。</p>
            </div>
          </div>
        </article>
      </section>

      <section class="card mw-instances-card">
        <div class="mw-card-head">
          <div>
            <h3>实例列表</h3>
            <p>{{ selectedTypeLabel ? `当前筛选：${selectedTypeLabel}` : '展示全部中间件实例' }}</p>
          </div>
          <div class="mw-filter-pills">
            <button
              class="mw-filter-pill"
              :class="{ active: selectedType === '' }"
              type="button"
              @click="selectType('')"
            >
              全部
            </button>
            <button
              v-for="item in summaryCards"
              :key="item.type"
              class="mw-filter-pill"
              :class="{ active: selectedType === item.type }"
              type="button"
              @click="selectType(item.type)"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <div class="mw-table-wrap">
          <table class="mw-table">
            <thead>
              <tr>
                <th>类型</th>
                <th>Job</th>
                <th>实例</th>
                <th>状态</th>
                <th>建议动作</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredInstances.length">
                <td colspan="6" class="mw-empty-cell">当前筛选下没有实例</td>
              </tr>
              <tr
                v-for="inst in filteredInstances"
                :key="inst.id"
                :class="{ active: activeInstance?.id === inst.id }"
              >
                <td>
                  <span class="mw-type-tag">{{ inst.label }}</span>
                </td>
                <td class="mono muted">{{ inst.job }}</td>
                <td class="mono">{{ inst.instance }}</td>
                <td>
                  <span class="mw-status" :class="inst.status === 'up' ? 'ok' : 'err'">
                    <i></i>
                    {{ inst.status === 'up' ? 'UP' : 'DOWN' }}
                  </span>
                </td>
                <td class="mw-recommend">{{ recommendationText(inst) }}</td>
                <td>
                  <button class="btn btn-outline btn-sm" @click="inspectInstance(inst)">
                    查看指标
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="activeInstance" class="card mw-metrics-card">
        <div class="mw-card-head">
          <div>
            <h3>{{ activeInstance.label }} 指标视图</h3>
            <p>{{ activeInstance.instance }}</p>
          </div>
          <div class="mw-metrics-actions">
            <span class="mw-card-meta">{{ instanceMetrics.length }} 项指标</span>
            <button class="btn btn-outline btn-sm" @click="closeMetrics">关闭</button>
          </div>
        </div>

        <div class="mw-metrics-summary">
          <article
            v-for="metric in highlightedMetrics"
            :key="metric.name"
            class="mw-metric-highlight"
            :class="metric.tone"
          >
            <div class="mw-metric-name">{{ metric.name }}</div>
            <div class="mw-metric-value">{{ metric.displayValue }}</div>
            <div class="mw-metric-hint">{{ metric.hint }}</div>
          </article>
        </div>

        <div v-if="instanceMetrics.length" class="mw-metric-grid">
          <article
            v-for="metric in instanceMetrics"
            :key="metric.name"
            class="mw-metric-card"
            :class="metric.tone"
          >
            <div class="mw-metric-head">
              <span>{{ metric.name }}</span>
              <em>{{ metric.toneLabel }}</em>
            </div>
            <div class="mw-metric-main">{{ metric.displayValue }}</div>
            <div class="mw-metric-query mono">{{ metric.query }}</div>
          </article>
        </div>

        <div v-else class="mw-empty-cell">
          当前实例没有匹配到指标，可能 Prometheus 尚未采集或标签未对齐。
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/index.js'

const MIDDLEWARE_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>`

const summary = ref([])
const instances = ref([])
const metricsCache = ref({})
const loading = ref(false)
const selectedType = ref('')
const activeInstance = ref(null)
const activeMetrics = ref(null)

const totalTypes = computed(() => summary.value.length)
const totalInstances = computed(() => instances.value.length)
const healthyInstances = computed(() => instances.value.filter((item) => item.status === 'up').length)
const abnormalInstances = computed(() => totalInstances.value - healthyInstances.value)
const availabilityRate = computed(() => {
  if (!totalInstances.value) return 0
  return Math.round((healthyInstances.value / totalInstances.value) * 100)
})

const selectedTypeLabel = computed(() => summaryCards.value.find((item) => item.type === selectedType.value)?.label || '')

const filteredInstances = computed(() => {
  const list = selectedType.value
    ? instances.value.filter((item) => item.type === selectedType.value)
    : instances.value
  return [...list].sort((left, right) => {
    if (left.status !== right.status) return left.status === 'down' ? -1 : 1
    return left.label.localeCompare(right.label, 'zh-CN')
  })
})

const summaryCards = computed(() => {
  const typeSet = new Set(instances.value.map((item) => item.type))
  return summary.value.map((item) => {
    const type = findTypeByLabel(item.label)
    const availability = item.total ? Math.round((item.up / item.total) * 100) : 0
    const tone = item.up === 0 ? 'danger' : item.up < item.total ? 'warn' : 'ok'
    return {
      ...item,
      type,
      availability,
      availabilityText: `${availability}%`,
      tone,
      healthText: item.up === 0 ? '全部离线' : item.up < item.total ? '部分异常' : '运行健康',
      riskText: item.up === item.total ? '建议做容量巡检' : `待排查 ${item.total - item.up} 个实例`,
      discovered: typeSet.has(type),
    }
  })
})

const anomalyItems = computed(() => {
  const groupItems = summaryCards.value
    .filter((item) => item.up < item.total)
    .map((item) => ({
      key: `group-${item.type}`,
      type: 'group',
      tone: item.up === 0 ? 'danger' : 'warn',
      level: item.up === 0 ? '严重' : '关注',
      title: `${item.label} 可用性异常`,
      description: `${item.total - item.up}/${item.total} 个实例不可用，建议优先检查 ${item.label} exporter 和服务存活`,
      targetType: item.type,
    }))

  const instanceItems = instances.value
    .filter((item) => item.status === 'down')
    .map((item) => ({
      key: item.id,
      type: 'instance',
      tone: 'danger',
      level: '严重',
      title: `${item.label} 实例离线`,
      description: `${item.instance} 当前状态 DOWN，建议先验证端口可达、Exporter 和主服务状态`,
      targetType: item.type,
      instance: item,
    }))

  return [...instanceItems, ...groupItems]
})

const topStats = computed(() => [
  {
    label: '已发现类型',
    value: totalTypes.value,
    hint: '当前 Prometheus 中识别出的中间件类型数量',
    tone: 'info',
  },
  {
    label: '实例总数',
    value: totalInstances.value,
    hint: `${healthyInstances.value} 个健康，${abnormalInstances.value} 个异常`,
    tone: abnormalInstances.value ? 'warn' : 'ok',
  },
  {
    label: '整体可用率',
    value: `${availabilityRate.value}%`,
    hint: abnormalInstances.value ? '建议优先看异常概览' : '当前没有发现离线实例',
    tone: abnormalInstances.value ? 'warn' : 'ok',
  },
  {
    label: '高风险入口',
    value: anomalyItems.value.length,
    hint: anomalyItems.value.length ? '已按优先级聚合故障入口' : '暂无显著异常',
    tone: anomalyItems.value.length ? 'danger' : 'ok',
  },
])

const instanceMetrics = computed(() => {
  if (!activeMetrics.value || !activeInstance.value) return []
  const rawList = activeMetrics.value.metrics || []
  const matched = rawList.filter((item) => item.instance === activeInstance.value.instance)
  const list = matched.length ? matched : rawList
  return list.map((item) => decorateMetric(item))
})

const highlightedMetrics = computed(() => instanceMetrics.value.slice(0, 4))

function findTypeByLabel(label) {
  const match = instances.value.find((item) => item.label === label)
  return match?.type || label.toLowerCase()
}

function iconSvg(icon) {
  const icons = {
    db: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>`,
    cache: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
    queue: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`,
    web: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>`,
    search: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  }
  return icons[icon] || icons.web
}

function formatMetricValue(metric) {
  const value = metric.value
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  if (metric.name.includes('命中率')) return `${(value * 100).toFixed(1)}%`
  if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}G`
  if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`
  if (Math.abs(value) >= 1e3) return `${(value / 1e3).toFixed(2)}K`
  return value % 1 === 0 ? `${value}` : value.toFixed(3)
}

function decorateMetric(metric) {
  const tone = metricTone(metric)
  return {
    ...metric,
    tone,
    toneLabel: tone === 'danger' ? '高风险' : tone === 'warn' ? '关注' : '正常',
    displayValue: formatMetricValue(metric),
    hint: metricHint(metric, tone),
  }
}

function metricTone(metric) {
  const name = metric.name || ''
  const value = Number(metric.value || 0)
  if (name.includes('5xx') && value > 0) return 'danger'
  if (name.includes('慢查询') && value > 0) return 'danger'
  if (name.includes('存活状态') && value < 1) return 'danger'
  if (name.includes('命中率') && value < 0.9) return 'warn'
  if (name.includes('活跃连接') && value > 500) return 'warn'
  if (name.includes('连接客户端数') && value > 300) return 'warn'
  return 'ok'
}

function metricHint(metric, tone) {
  if (tone === 'danger') return '建议优先排查'
  if (tone === 'warn') return '建议持续关注'
  return '指标平稳'
}

function recommendationText(instance) {
  if (instance.status === 'down') {
    return '先查服务存活、Exporter、端口与认证'
  }
  if (instance.type === 'redis') return '关注连接数与内存占用'
  if (instance.type === 'mysql' || instance.type === 'postgres') return '关注连接数、慢查询与缓存命中率'
  if (instance.type === 'nginx') return '关注活跃连接与 5xx'
  return '建议抽查关键指标'
}

function selectType(type) {
  selectedType.value = selectedType.value === type ? '' : type
}

function resetView() {
  selectedType.value = ''
  activeInstance.value = null
  activeMetrics.value = null
}

async function fetchAll() {
  loading.value = true
  try {
    const [summaryResult, instanceResult] = await Promise.all([
      api.middlewareSummary().catch(() => []),
      api.middlewareInstances().catch(() => []),
    ])
    summary.value = Array.isArray(summaryResult) ? summaryResult : []
    instances.value = Array.isArray(instanceResult) ? instanceResult : []
    metricsCache.value = {}
    if (activeInstance.value) {
      const latest = instances.value.find((item) => item.id === activeInstance.value.id)
      if (latest) {
        await inspectInstance(latest)
      } else {
        activeInstance.value = null
        activeMetrics.value = null
      }
    }
  } finally {
    loading.value = false
  }
}

async function loadMetrics(type) {
  if (metricsCache.value[type]) return metricsCache.value[type]
  const result = await api.middlewareMetrics(type).catch(() => ({ label: type, metrics: [] }))
  metricsCache.value[type] = result
  return result
}

async function inspectInstance(instance) {
  activeInstance.value = instance
  selectedType.value = instance.type
  activeMetrics.value = await loadMetrics(instance.type)
}

function closeMetrics() {
  activeInstance.value = null
  activeMetrics.value = null
}

function handleAnomalyClick(item) {
  if (item.instance) {
    inspectInstance(item.instance)
    return
  }
  selectedType.value = item.targetType || ''
}

onMounted(fetchAll)
</script>

<style scoped>
.mw-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  background:
    radial-gradient(circle at top right, rgba(96, 165, 250, 0.08), transparent 34%),
    radial-gradient(circle at top left, rgba(251, 191, 36, 0.08), transparent 26%),
    var(--bg-base);
}

.mw-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 20px 22px;
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.9), rgba(255, 255, 255, 0.98));
}

.mw-hero-left {
  min-width: 0;
}

.mw-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
}

.mw-badge-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.mw-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.mw-title-row h1 {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
}

.mw-title-pill {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.mw-title-pill.ok {
  background: rgba(34, 197, 94, 0.12);
  color: var(--success);
}

.mw-title-pill.danger {
  background: rgba(239, 68, 68, 0.12);
  color: var(--error);
}

.mw-subtitle {
  margin-top: 10px;
  max-width: 720px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.mw-hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mw-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.mw-kpi {
  padding: 18px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98));
}

.mw-kpi-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.mw-kpi-value {
  margin-top: 8px;
  font-size: 30px;
  line-height: 1.1;
  font-weight: 700;
  color: var(--text-primary);
}

.mw-kpi-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.mw-kpi.ok {
  box-shadow: inset 0 0 0 1px rgba(34, 197, 94, 0.18);
}

.mw-kpi.warn {
  box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.18);
}

.mw-kpi.danger {
  box-shadow: inset 0 0 0 1px rgba(239, 68, 68, 0.18);
}

.mw-kpi.info {
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.18);
}

.mw-loading,
.mw-empty {
  min-height: 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
}

.mw-empty-icon {
  color: var(--text-muted);
  opacity: 0.5;
}

.mw-empty h3 {
  font-size: 18px;
  color: var(--text-primary);
}

.mw-empty p {
  color: var(--text-secondary);
}

.mw-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.7fr);
  gap: 16px;
}

.mw-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.mw-card-head h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.mw-card-head p {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.mw-card-meta {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.12);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.mw-type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
  gap: 12px;
}

.mw-type-card {
  border: none;
  border-radius: 18px;
  padding: 16px;
  text-align: left;
  cursor: pointer;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.95);
}

.mw-type-card.active {
  box-shadow:
    inset 0 0 0 1px rgba(59, 130, 246, 0.28),
    0 10px 26px rgba(37, 99, 235, 0.08);
}

.mw-type-card.warn {
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.96), rgba(255, 255, 255, 0.98));
}

.mw-type-card.danger {
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.96), rgba(255, 255, 255, 0.98));
}

.mw-type-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.mw-type-icon {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.mw-type-icon.db {
  background: rgba(59, 130, 246, 0.12);
  color: #3b82f6;
}

.mw-type-icon.cache {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.mw-type-icon.queue {
  background: rgba(245, 158, 11, 0.14);
  color: #f59e0b;
}

.mw-type-icon.web {
  background: rgba(34, 197, 94, 0.12);
  color: #22c55e;
}

.mw-type-icon.search {
  background: rgba(139, 92, 246, 0.12);
  color: #8b5cf6;
}

.mw-type-health {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.mw-type-health.ok {
  background: rgba(34, 197, 94, 0.12);
  color: var(--success);
}

.mw-type-health.warn {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.mw-type-health.danger {
  background: rgba(239, 68, 68, 0.12);
  color: var(--error);
}

.mw-type-title {
  margin-top: 14px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.mw-type-ratio {
  margin-top: 8px;
  color: var(--text-secondary);
}

.mw-type-ratio strong {
  font-size: 26px;
  color: var(--text-primary);
}

.mw-type-progress {
  margin-top: 14px;
  height: 8px;
  border-radius: 999px;
  background: rgba(226, 232, 240, 0.95);
  overflow: hidden;
}

.mw-type-progress span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #60a5fa, #34d399);
}

.mw-type-card.warn .mw-type-progress span {
  background: linear-gradient(90deg, #f59e0b, #fb7185);
}

.mw-type-card.danger .mw-type-progress span {
  background: linear-gradient(90deg, #f87171, #ef4444);
}

.mw-type-foot {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.mw-alert-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mw-alert-item {
  border: none;
  width: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.95);
  cursor: pointer;
  text-align: left;
}

.mw-alert-item.warn {
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.96), rgba(255, 255, 255, 0.98));
}

.mw-alert-item.danger {
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.96), rgba(255, 255, 255, 0.98));
}

.mw-alert-level {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, #f59e0b, #f97316);
  flex-shrink: 0;
}

.mw-alert-item.danger .mw-alert-level {
  background: linear-gradient(135deg, #f87171, #ef4444);
}

.mw-alert-body {
  flex: 1;
  min-width: 0;
}

.mw-alert-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.mw-alert-desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.mw-alert-tail {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.mw-alert-empty {
  min-height: 180px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 4px;
}

.mw-alert-empty-dot {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 8px rgba(34, 197, 94, 0.12);
}

.mw-alert-empty strong {
  display: block;
  color: var(--text-primary);
}

.mw-alert-empty p {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.mw-filter-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.mw-filter-pill {
  border: none;
  border-radius: 999px;
  padding: 7px 12px;
  background: rgba(226, 232, 240, 0.7);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.mw-filter-pill.active {
  background: rgba(59, 130, 246, 0.12);
  color: var(--accent);
  font-weight: 700;
}

.mw-table-wrap {
  overflow: auto;
}

.mw-table {
  width: 100%;
  border-collapse: collapse;
}

.mw-table th,
.mw-table td {
  padding: 12px 10px;
  border-bottom: 1px solid var(--border-light);
  vertical-align: middle;
}

.mw-table th {
  color: var(--text-secondary);
  font-size: 12px;
}

.mw-table tbody tr:hover td {
  background: rgba(148, 163, 184, 0.04);
}

.mw-table tbody tr.active td {
  background: rgba(59, 130, 246, 0.06);
}

.mw-empty-cell {
  padding: 24px !important;
  text-align: center;
  color: var(--text-secondary);
}

.mw-type-tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.08);
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
}

.mw-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
}

.mw-status i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.mw-status.ok {
  color: var(--success);
}

.mw-status.ok i {
  background: var(--success);
}

.mw-status.err {
  color: var(--error);
}

.mw-status.err i {
  background: var(--error);
}

.mw-recommend {
  color: var(--text-secondary);
  font-size: 12px;
}

.mw-metrics-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mw-metrics-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.mw-metric-highlight,
.mw-metric-card {
  border-radius: 16px;
  padding: 14px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.95);
}

.mw-metric-highlight.warn,
.mw-metric-card.warn {
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.96), rgba(255, 255, 255, 0.98));
}

.mw-metric-highlight.danger,
.mw-metric-card.danger {
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.96), rgba(255, 255, 255, 0.98));
}

.mw-metric-name {
  font-size: 12px;
  color: var(--text-secondary);
}

.mw-metric-value,
.mw-metric-main {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
}

.mw-metric-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.mw-metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.mw-metric-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.mw-metric-head em {
  font-style: normal;
  font-weight: 700;
}

.mw-metric-query {
  margin-top: 12px;
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}

.mono {
  font-family: 'Cascadia Code', 'Consolas', 'Cascadia Code', monospace;
}

.muted {
  color: var(--text-secondary);
}

@media (max-width: 1200px) {
  .mw-kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .mw-main-grid {
    grid-template-columns: 1fr;
  }

  .mw-metrics-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 840px) {
  .mw-hero {
    flex-direction: column;
  }

  .mw-hero-actions {
    width: 100%;
  }

  .mw-kpi-grid,
  .mw-metrics-summary {
    grid-template-columns: 1fr;
  }

  .mw-type-grid {
    grid-template-columns: 1fr;
  }
}
</style>
