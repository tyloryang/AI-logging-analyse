<template>
  <div class="cost-page">
    <div class="cost-head">
      <div>
        <h2 class="cost-title">💰 资源成本分析</h2>
        <p class="cost-sub">基于 CMDB 主机规格估算 · 单价 CPU ¥{{ rates.cpu }}/核·时 · 内存 ¥{{ rates.mem }}/GB·时 · 磁盘 ¥{{ rates.disk }}/GB·时</p>
      </div>
      <button class="btn btn-outline" @click="load" :disabled="loading">🔄 刷新</button>
    </div>

    <div v-if="loading" class="cost-empty">加载中...</div>
    <template v-else-if="data">
      <!-- KPI -->
      <div class="cost-kpis">
        <div class="ck-card">
          <div class="ck-icon">💴</div>
          <div><div class="ck-val">¥{{ fmtNum(data.summary.total_monthly) }}</div><div class="ck-lbl">月度总成本（估算）</div></div>
        </div>
        <div class="ck-card">
          <div class="ck-icon">🖥️</div>
          <div><div class="ck-val">{{ data.summary.host_count }}</div><div class="ck-lbl">纳管主机 · 均 ¥{{ fmtNum(data.summary.avg_per_host) }}/台</div></div>
        </div>
        <div class="ck-card warn">
          <div class="ck-icon">🕳️</div>
          <div><div class="ck-val">¥{{ fmtNum(data.summary.idle_waste) }}</div><div class="ck-lbl">闲置浪费（低利用率）</div></div>
        </div>
        <div class="ck-card save">
          <div class="ck-icon">✂️</div>
          <div><div class="ck-val">¥{{ fmtNum(data.summary.potential_savings) }}</div><div class="ck-lbl">可优化节省/月</div></div>
        </div>
      </div>

      <div class="cost-cols">
        <!-- 左：按环境/分组成本 -->
        <div class="cost-panel">
          <div class="cp-tabs">
            <button :class="{ active: dim==='env' }" @click="dim='env'">按环境</button>
            <button :class="{ active: dim==='group' }" @click="dim='group'">按分组</button>
          </div>
          <div class="dist-bars">
            <div v-for="d in dist" :key="d.name" class="dist-row">
              <span class="dist-name">{{ d.name }}</span>
              <div class="dist-track"><div class="dist-fill" :style="{ width: distPct(d.value)+'%' }"></div></div>
              <span class="dist-val">¥{{ fmtNum(d.value) }}</span>
            </div>
          </div>
        </div>

        <!-- 右：优化建议 -->
        <div class="cost-panel">
          <div class="panel-title">💡 成本优化建议</div>
          <div v-if="!data.recommendations.length" class="empty-hint">暂无优化建议，资源利用率良好 ✓</div>
          <div v-for="(r, i) in data.recommendations" :key="i" class="rec-item" :class="'lv-'+r.level">
            <div class="rec-head">
              <span class="rec-type">{{ typeLabel(r.type) }}</span>
              <span class="rec-save">省 ¥{{ fmtNum(r.monthly_savings) }}/月</span>
            </div>
            <div class="rec-res">{{ r.resource }}</div>
            <div class="rec-desc">{{ r.description }}</div>
          </div>
        </div>
      </div>

      <!-- 主机成本表 -->
      <div class="cost-panel">
        <div class="panel-title">主机成本明细（月度，降序）</div>
        <div class="table-wrap">
          <table class="cost-table">
            <thead>
              <tr>
                <th>主机</th><th>环境</th><th>规格</th><th>CPU 利用</th><th>内存利用</th>
                <th>月成本</th><th>闲置浪费</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="h in data.hosts" :key="h.id">
                <td><b>{{ h.hostname }}</b><div class="th-ip">{{ h.ip }}</div></td>
                <td><span class="env-chip">{{ h.env }}</span></td>
                <td class="mono">{{ h.cpu_cores || '-' }}C / {{ h.memory_gb || '-' }}G / {{ h.disk_gb || '-' }}G</td>
                <td><span :class="useClass(h.cpu_usage_pct)">{{ pct(h.cpu_usage_pct) }}</span></td>
                <td><span :class="useClass(h.memory_usage_pct)">{{ pct(h.memory_usage_pct) }}</span></td>
                <td class="cost-cell">¥{{ fmtNum(h.monthly) }}</td>
                <td><span v-if="h.waste>0" class="waste-cell">¥{{ fmtNum(h.waste) }}</span><span v-else class="mono muted">-</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <p class="cost-note">※ 估算基于规格与单价，非真实账单。单价可用环境变量 COST_RATE_CPU/MEM/DISK 调整。</p>
      </div>
    </template>
    <div v-else class="cost-empty"><span class="e-icon">💰</span><p>暂无成本数据<br><small>请先在 CMDB 录入主机规格</small></p></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const data = ref(null)
const loading = ref(false)
const dim = ref('env')
const rates = computed(() => data.value?.rates || { cpu: 0.1, mem: 0.02, disk: 0.0005 })
const dist = computed(() => (dim.value === 'env' ? data.value?.by_env : data.value?.by_group) || [])
const distMax = computed(() => Math.max(1, ...dist.value.map(d => d.value)))

async function load() {
  loading.value = true
  try { data.value = await api.costOverview() }
  catch { data.value = null }
  finally { loading.value = false }
}

function distPct(v) { return Math.round(v / distMax.value * 100) }
function fmtNum(n) { return Number(n || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }
function pct(v) { return (typeof v === 'number') ? v.toFixed(1) + '%' : '-' }
function useClass(v) { return typeof v !== 'number' ? 'mono muted' : (v < 15 ? 'use-low' : v > 80 ? 'use-high' : 'use-mid') }
function typeLabel(t) { return { idle: '🔴 闲置', downsize: '🟡 降配', reserved: '🔵 预留' }[t] || t }

onMounted(load)
</script>

<style scoped>
.cost-page { height: 100%; overflow-y: auto; padding: 20px 24px; background: var(--bg-base); }
.cost-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.cost-title { font-size: 20px; font-weight: 600; color: var(--text-primary); }
.cost-sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.cost-empty { text-align: center; padding: 70px; color: var(--text-muted); }
.e-icon { font-size: 44px; display: block; margin-bottom: 14px; }

.cost-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 18px; }
.ck-card { display: flex; align-items: center; gap: 14px; padding: 16px 18px; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 12px; border-left: 3px solid var(--accent); }
.ck-card.warn { border-left-color: #fbbf24; } .ck-card.save { border-left-color: #22c55e; }
.ck-icon { font-size: 26px; }
.ck-val { font-size: 24px; font-weight: 800; color: var(--text-primary); }
.ck-lbl { font-size: 12px; color: var(--text-muted); margin-top: 3px; }

.cost-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 18px; }
.cost-panel { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.panel-title { font-size: 13px; font-weight: 600; color: var(--text-secondary); margin-bottom: 14px; }
.cp-tabs { display: flex; gap: 6px; margin-bottom: 14px; }
.cp-tabs button { padding: 5px 14px; font-size: 12px; border: 1px solid var(--border); border-radius: 7px;
  background: var(--bg-hover); color: var(--text-secondary); cursor: pointer; }
.cp-tabs button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.dist-bars { display: flex; flex-direction: column; gap: 10px; }
.dist-row { display: flex; align-items: center; gap: 10px; }
.dist-name { width: 90px; font-size: 12px; color: var(--text-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dist-track { flex: 1; height: 16px; background: var(--bg-hover); border-radius: 8px; overflow: hidden; }
.dist-fill { height: 100%; background: linear-gradient(90deg, var(--accent), #f0a882); border-radius: 8px; transition: width .5s; }
.dist-val { width: 80px; text-align: right; font-size: 12px; font-weight: 700; color: var(--text-primary); }

.rec-item { padding: 11px 13px; border-radius: 9px; background: var(--bg-hover); border-left: 3px solid var(--border); margin-bottom: 9px; }
.rec-item.lv-high { border-left-color: #f87171; } .rec-item.lv-medium { border-left-color: #fbbf24; }
.rec-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
.rec-type { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.rec-save { font-size: 12px; font-weight: 700; color: #22c55e; }
.rec-res { font-size: 12px; color: var(--text-secondary); font-family: monospace; }
.rec-desc { font-size: 12px; color: var(--text-muted); margin-top: 3px; }
.empty-hint { font-size: 13px; color: var(--text-muted); padding: 20px; text-align: center; }

.table-wrap { overflow-x: auto; }
.cost-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cost-table th { text-align: left; padding: 9px 10px; color: var(--text-muted); font-weight: 500;
  border-bottom: 1px solid var(--border); white-space: nowrap; }
.cost-table td { padding: 9px 10px; border-bottom: 1px solid var(--border-light, var(--border)); color: var(--text-primary); }
.th-ip { font-size: 11px; color: var(--text-muted); }
.env-chip { font-size: 11px; padding: 1px 8px; border-radius: 999px; background: var(--accent-dim, rgba(217,119,87,.1)); color: var(--accent); }
.mono { font-family: 'Cascadia Code', monospace; } .muted { color: var(--text-muted); }
.use-low { color: #f87171; font-weight: 600; } .use-mid { color: var(--text-primary); } .use-high { color: #fbbf24; font-weight: 600; }
.cost-cell { font-weight: 700; color: var(--accent); }
.waste-cell { color: #fbbf24; font-weight: 600; }
.cost-note { font-size: 11px; color: var(--text-muted); margin-top: 12px; }
</style>
