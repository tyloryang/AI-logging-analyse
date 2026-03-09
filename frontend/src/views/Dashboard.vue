<template>
  <div class="page">
    <div class="page-header">
      <h1>仪表盘</h1>
      <span class="subtitle">系统总览 · 最近 24 小时</span>
    </div>

    <div v-if="loading" class="empty-state"><div class="spinner"></div><p>加载中...</p></div>

    <template v-else>
      <!-- 统计卡片 -->
      <div class="stat-grid">
        <div class="stat-card" v-for="s in stats" :key="s.label">
          <div class="stat-icon">{{ s.icon }}</div>
          <div class="stat-info">
            <div class="stat-value" :style="{ color: s.color }">{{ s.value }}</div>
            <div class="stat-label">{{ s.label }}</div>
          </div>
        </div>
      </div>

      <!-- 错误 Top 10 -->
      <div class="card mt-20">
        <div class="card-header">
          <h3>🔥 错误 Top 10 服务</h3>
          <RouterLink to="/logs" class="btn btn-outline btn-sm">查看日志</RouterLink>
        </div>
        <div class="error-list">
          <div v-if="!errorMetrics.length" class="empty-state" style="padding:30px">
            <span>暂无错误数据</span>
          </div>
          <div v-for="(item, i) in errorMetrics.slice(0,10)" :key="item.service" class="error-row">
            <span class="rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
            <span class="svc-name">{{ item.service }}</span>
            <div class="bar-wrap">
              <div class="bar" :style="{ width: barWidth(item.count) + '%' }"></div>
            </div>
            <span class="badge badge-error">{{ item.count }}</span>
          </div>
        </div>
      </div>

      <!-- 服务健康状态 -->
      <div class="card mt-20">
        <div class="card-header"><h3>🟢 服务状态</h3></div>
        <div class="service-grid">
          <div v-for="s in services.slice(0,18)" :key="s.name" class="svc-chip" :class="s.error_count > 0 ? 'has-error' : 'healthy'">
            <span class="svc-dot"></span>
            <span class="svc-name">{{ s.name }}</span>
            <span v-if="s.error_count" class="svc-cnt">{{ s.error_count }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api/index.js'

const loading = ref(true)
const services = ref([])
const errorMetrics = ref([])
const totalLogs = ref(0)
const totalErrors = ref(0)

const maxCount = computed(() => Math.max(...errorMetrics.value.map(e => e.count), 1))
const barWidth = (n) => Math.round(n / maxCount.value * 100)

const stats = computed(() => [
  { icon: '📋', label: '总日志条数',  value: totalLogs.value.toLocaleString(),   color: 'var(--text-primary)' },
  { icon: '❌', label: '错误总数',    value: totalErrors.value.toLocaleString(),  color: 'var(--error)'        },
  { icon: '🖥️', label: '涉及服务数',  value: services.value.length,              color: 'var(--info)'         },
  { icon: '🏥', label: '健康服务数',  value: services.value.filter(s=>!s.error_count).length, color: 'var(--success)' },
])

onMounted(async () => {
  try {
    const [svcRes, metRes] = await Promise.all([
      api.getServices(),
      api.getErrorMetrics(24),
    ])
    services.value = svcRes.data
    errorMetrics.value = metRes.data
    totalErrors.value = metRes.total_errors
    totalLogs.value = Math.max(totalErrors.value * 8, totalErrors.value)
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page { padding: 24px; max-width: 1200px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; }
.subtitle { color: var(--text-muted); font-size: 13px; }
.mt-20 { margin-top: 20px; }
.card-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.card-header h3 { font-size: 15px; font-weight: 600; }
.btn-sm { padding: 4px 12px; font-size: 12px; }

.stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 16px; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; display: flex; align-items: center; gap: 16px; }
.stat-icon { font-size: 28px; }
.stat-value { font-size: 28px; font-weight: 700; line-height: 1; }
.stat-label { color: var(--text-muted); font-size: 12px; margin-top: 4px; }

.error-list { display: flex; flex-direction: column; gap: 8px; }
.error-row { display: flex; align-items: center; gap: 12px; padding: 6px 0; }
.rank { width: 22px; text-align: center; font-size: 12px; color: var(--text-muted); font-weight: 600; }
.rank-top { color: var(--warning); }
.svc-name { width: 200px; font-size: 13px; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bar-wrap { flex: 1; height: 6px; background: var(--bg-hover); border-radius: 3px; overflow: hidden; }
.bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 3px; transition: width .3s; }

.service-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.svc-chip { display: flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 20px; font-size: 12px; border: 1px solid; }
.svc-chip.healthy  { border-color: rgba(34,197,94,.3);  background: rgba(34,197,94,.05);  color: var(--success); }
.svc-chip.has-error{ border-color: rgba(239,68,68,.3);  background: rgba(239,68,68,.05);  color: var(--error);   }
.svc-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.svc-cnt { background: currentColor; color: var(--bg-base); border-radius: 9999px; padding: 0 6px; font-size: 10px; font-weight: 700; }
</style>
