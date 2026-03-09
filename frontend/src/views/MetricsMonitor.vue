<template>
  <div class="page">
    <div class="page-header">
      <h1>指标监控</h1>
      <span class="subtitle">各服务错误趋势</span>
    </div>

    <div v-if="loading" class="empty-state" style="height:300px">
      <div class="spinner"></div><p>加载中...</p>
    </div>

    <template v-else>
      <div class="card">
        <div class="card-header" style="margin-bottom:16px">
          <h3>错误分布（最近 {{ hours }} 小时）</h3>
          <select v-model="hours" class="time-select" @change="load" style="width:140px">
            <option value="6">最近 6 小时</option>
            <option value="24">最近 24 小时</option>
            <option value="72">最近 3 天</option>
          </select>
        </div>
        <div v-if="!data.length" class="empty-state" style="padding:40px">
          <span class="icon">📊</span><p>暂无错误数据</p>
        </div>
        <div v-else class="chart-list">
          <div v-for="item in data" :key="item.service" class="chart-row">
            <span class="chart-svc">{{ item.service }}</span>
            <div class="chart-bar-wrap">
              <div class="chart-bar" :style="{ width: barW(item.count) + '%', background: barColor(item.count) }"></div>
            </div>
            <span class="chart-cnt" :style="{ color: barColor(item.count) }">{{ item.count }}</span>
          </div>
        </div>
      </div>

      <div class="card" style="margin-top:20px">
        <h3 style="margin-bottom:16px;font-size:15px;font-weight:600">汇总</h3>
        <div class="summary-grid">
          <div class="summary-item">
            <div class="s-val">{{ totalErrors.toLocaleString() }}</div>
            <div class="s-label">总错误数</div>
          </div>
          <div class="summary-item">
            <div class="s-val">{{ data.length }}</div>
            <div class="s-label">受影响服务数</div>
          </div>
          <div class="summary-item">
            <div class="s-val" style="color:var(--error)">{{ data[0]?.service || '-' }}</div>
            <div class="s-label">最高错误服务</div>
          </div>
          <div class="summary-item">
            <div class="s-val">{{ data[0]?.count?.toLocaleString() || 0 }}</div>
            <div class="s-label">最高错误数</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const data = ref([])
const loading = ref(true)
const hours = ref('24')
const totalErrors = computed(() => data.value.reduce((s, v) => s + v.count, 0))
const maxVal = computed(() => Math.max(...data.value.map(d => d.count), 1))

function barW(n) { return Math.round(n / maxVal.value * 100) }
function barColor(n) {
  const ratio = n / maxVal.value
  if (ratio > 0.6) return 'var(--error)'
  if (ratio > 0.3) return 'var(--warning)'
  return 'var(--info)'
}

async function load() {
  loading.value = true
  try {
    const r = await api.getErrorMetrics(hours.value)
    data.value = r.data
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<style scoped>
.page { padding: 24px; max-width: 1000px; }
.page-header { margin-bottom: 24px; }
.page-header h1 { font-size: 22px; font-weight: 700; }
.subtitle { color: var(--text-muted); font-size: 13px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.time-select { background: var(--bg-hover); border: 1px solid var(--border); color: var(--text-primary); padding: 6px 10px; border-radius: 6px; font-size: 13px; cursor: pointer; }
.chart-list { display: flex; flex-direction: column; gap: 10px; }
.chart-row { display: flex; align-items: center; gap: 14px; }
.chart-svc { width: 200px; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.chart-bar-wrap { flex: 1; height: 10px; background: var(--bg-hover); border-radius: 5px; overflow: hidden; }
.chart-bar { height: 100%; border-radius: 5px; transition: width .4s; }
.chart-cnt { width: 60px; text-align: right; font-size: 13px; font-weight: 600; flex-shrink: 0; }
.summary-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; }
.summary-item { background: var(--bg-base); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: center; }
.s-val { font-size: 22px; font-weight: 700; color: var(--text-primary); }
.s-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
</style>
