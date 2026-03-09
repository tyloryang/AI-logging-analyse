<template>
  <div class="page">
    <div class="page-header">
      <h1>告警历史</h1>
      <span class="subtitle">基于错误日志自动生成告警记录</span>
    </div>

    <div v-if="loading" class="empty-state" style="height:300px">
      <div class="spinner"></div><p>加载中...</p>
    </div>

    <template v-else>
      <div class="alert-stats">
        <div class="as-item critical"><span class="as-num">{{ counts.critical }}</span><span class="as-label">严重</span></div>
        <div class="as-item warning"><span class="as-num">{{ counts.warning }}</span><span class="as-label">警告</span></div>
        <div class="as-item info"><span class="as-num">{{ counts.info }}</span><span class="as-label">提示</span></div>
      </div>

      <div class="card" style="margin-top:16px">
        <div v-if="!alerts.length" class="empty-state" style="padding:40px">
          <span class="icon">🔔</span><p>暂无告警记录</p>
        </div>
        <div v-else class="alert-table">
          <div class="table-head">
            <span>级别</span><span>服务</span><span>描述</span><span>错误数</span><span>时间</span>
          </div>
          <div v-for="a in alerts" :key="a.id" class="table-row">
            <span class="al-level" :class="'al-' + a.level">{{ a.level.toUpperCase() }}</span>
            <span class="al-svc">{{ a.service }}</span>
            <span class="al-desc">{{ a.service }} 检测到 {{ a.count }} 条错误日志</span>
            <span class="al-cnt badge" :class="a.level === 'critical' ? 'badge-error' : a.level === 'warning' ? 'badge-warn' : 'badge-info'">{{ a.count }}</span>
            <span class="al-time">{{ a.time }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const loading = ref(true)
const alerts = ref([])

const counts = computed(() => ({
  critical: alerts.value.filter(a => a.level === 'critical').length,
  warning:  alerts.value.filter(a => a.level === 'warning').length,
  info:     alerts.value.filter(a => a.level === 'info').length,
}))

function alertLevel(count) {
  if (count >= 100) return 'critical'
  if (count >= 10)  return 'warning'
  return 'info'
}

onMounted(async () => {
  try {
    const r = await api.getErrorMetrics(24)
    const now = new Date()
    alerts.value = r.data.map((item, i) => ({
      id: i,
      service: item.service,
      count: item.count,
      level: alertLevel(item.count),
      time: new Date(now - i * 120000).toLocaleString('zh-CN', { hour12: false }),
    }))
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page { padding: 24px; max-width: 1100px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; }
.subtitle { color: var(--text-muted); font-size: 13px; }

.alert-stats { display: flex; gap: 16px; }
.as-item { display: flex; flex-direction: column; align-items: center; padding: 16px 28px; border-radius: var(--radius); border: 1px solid; }
.as-item.critical { border-color: rgba(239,68,68,.4); background: rgba(239,68,68,.06); }
.as-item.warning  { border-color: rgba(245,158,11,.4); background: rgba(245,158,11,.06); }
.as-item.info     { border-color: rgba(59,130,246,.4); background: rgba(59,130,246,.06); }
.as-num { font-size: 28px; font-weight: 800; }
.as-item.critical .as-num { color: var(--error); }
.as-item.warning  .as-num { color: var(--warning); }
.as-item.info     .as-num { color: var(--info); }
.as-label { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

.alert-table { display: flex; flex-direction: column; }
.table-head { display: grid; grid-template-columns: 80px 160px 1fr 80px 160px; gap: 12px; padding: 10px 14px; background: var(--bg-hover); border-radius: 6px; font-size: 12px; color: var(--text-muted); font-weight: 600; margin-bottom: 4px; }
.table-row { display: grid; grid-template-columns: 80px 160px 1fr 80px 160px; gap: 12px; padding: 10px 14px; border-bottom: 1px solid var(--border); font-size: 13px; align-items: center; }
.table-row:hover { background: var(--bg-hover); }
.al-level { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; text-align: center; }
.al-critical { background: rgba(239,68,68,.15); color: var(--error); }
.al-warning  { background: rgba(245,158,11,.15); color: var(--warning); }
.al-info     { background: rgba(59,130,246,.15);  color: var(--info); }
.al-svc  { color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.al-desc { color: var(--text-secondary); font-size: 12px; }
.al-time { color: var(--text-muted); font-size: 12px; }
</style>
