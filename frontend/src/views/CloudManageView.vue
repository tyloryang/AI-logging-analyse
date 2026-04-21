<template>
  <div class="cloud-view">
    <div class="page-header">
      <div class="header-left">
        <h1>多云管理</h1>
        <span class="subtitle">统一纳管多云资源，跨云成本与配置分析</span>
      </div>
    </div>

    <!-- Cloud accounts -->
    <div class="accounts-row">
      <div v-for="cloud in CLOUDS" :key="cloud.id" class="cloud-card" :class="{ active: activeCloud === cloud.id }" @click="activeCloud = cloud.id">
        <div class="cloud-logo" v-html="cloud.logo"></div>
        <div class="cloud-info">
          <div class="cloud-name">{{ cloud.name }}</div>
          <div class="cloud-status" :class="cloud.connected ? 'ok' : 'off'">
            {{ cloud.connected ? '已接入' : '未配置' }}
          </div>
        </div>
        <div v-if="cloud.connected" class="cloud-badge">{{ cloud.resourceCount }} 资源</div>
      </div>
    </div>

    <!-- Config tip for unconnected -->
    <div v-if="!activeCloudObj?.connected" class="config-tip">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" opacity=".4"><circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></svg>
      <div>
        <p>{{ activeCloudObj?.name }} 暂未配置 API 凭证</p>
        <p class="hint">在 <RouterLink to="/settings" class="settings-link">系统配置</RouterLink> 中添加 AccessKey / SecretKey 即可接入</p>
      </div>
    </div>

    <!-- Resource overview (mock for connected clouds) -->
    <div v-else class="resource-overview">
      <div class="overview-cards">
        <div v-for="r in RESOURCE_TYPES" :key="r.label" class="res-card">
          <div class="res-icon" :class="r.color" v-html="r.icon"></div>
          <div class="res-count">{{ r.count }}</div>
          <div class="res-label">{{ r.label }}</div>
        </div>
      </div>

      <div class="region-table-wrap">
        <div class="section-title">资源分布（按地域）</div>
        <table class="region-table">
          <thead><tr><th>地域</th><th>实例</th><th>运行中</th><th>已停止</th><th>费用/月</th></tr></thead>
          <tbody>
            <tr v-for="r in REGIONS" :key="r.region">
              <td>{{ r.region }}</td>
              <td>{{ r.instances }}</td>
              <td class="ok">{{ r.running }}</td>
              <td class="muted">{{ r.stopped }}</td>
              <td class="mono">¥{{ r.cost }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { RouterLink } from 'vue-router'

const CLOUDS = [
  {
    id: 'aliyun', name: '阿里云', connected: false, resourceCount: 0,
    logo: `<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/></svg>`,
  },
  {
    id: 'aws', name: 'AWS', connected: false, resourceCount: 0,
    logo: `<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/></svg>`,
  },
  {
    id: 'tencent', name: '腾讯云', connected: false, resourceCount: 0,
    logo: `<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><rect x="2" y="2" width="20" height="20" rx="4"/></svg>`,
  },
  {
    id: 'huawei', name: '华为云', connected: false, resourceCount: 0,
    logo: `<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><polygon points="12 2 22 8 22 16 12 22 2 16 2 8"/></svg>`,
  },
]

const RESOURCE_TYPES = [
  { label: 'ECS 实例',  count: 42, color: 'blue',   icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="3" width="20" height="14" rx="2"/></svg>` },
  { label: 'RDS 实例',  count: 8,  color: 'green',  icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>` },
  { label: 'OSS 存储',  count: 16, color: 'orange', icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>` },
  { label: 'SLB 负载',  count: 6,  color: 'purple', icon: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>` },
]

const REGIONS = [
  { region: '华东（上海）', instances: 18, running: 16, stopped: 2, cost: '12,400' },
  { region: '华北（北京）', instances: 14, running: 14, stopped: 0, cost: '9,800' },
  { region: '华南（深圳）', instances: 10, running: 8,  stopped: 2, cost: '7,200' },
]

const activeCloud = ref('aliyun')
const activeCloudObj = computed(() => CLOUDS.find(c => c.id === activeCloud.value))
</script>

<style scoped>
.cloud-view { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--bg-base); color: var(--text-primary); }
.page-header { padding: 16px 20px 12px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
.header-left h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
.subtitle { font-size: 12px; color: var(--text-muted); }

.accounts-row { display: flex; gap: 10px; padding: 14px 20px; flex-shrink: 0; }
.cloud-card { display: flex; align-items: center; gap: 10px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; cursor: pointer; transition: all .15s; min-width: 150px; }
.cloud-card:hover  { border-color: var(--text-secondary); }
.cloud-card.active { border-color: var(--accent); background: var(--accent-dim); }
.cloud-logo { width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; color: var(--text-muted); }
.cloud-name { font-size: 13px; font-weight: 500; }
.cloud-status { font-size: 10.5px; margin-top: 2px; }
.cloud-status.ok  { color: var(--success); }
.cloud-status.off { color: var(--text-muted); }
.cloud-badge { margin-left: auto; font-size: 10.5px; background: var(--accent-dim); color: var(--accent); padding: 2px 7px; border-radius: 8px; }

.config-tip { display: flex; align-items: flex-start; gap: 12px; margin: 0 20px; background: rgba(154,103,0,0.06); border: 1px solid rgba(154,103,0,0.2); border-radius: 10px; padding: 16px; }
.config-tip p { margin: 0 0 4px; font-size: 13px; }
.hint { font-size: 11.5px; color: var(--text-muted); }
.settings-link { color: var(--accent); text-decoration: none; }

.resource-overview { flex: 1; overflow: auto; padding: 0 20px 20px; display: flex; flex-direction: column; gap: 14px; }
.overview-cards { display: flex; gap: 10px; }
.res-card { flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 14px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
.res-icon { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
.res-icon.blue   { background: var(--accent-dim);              color: var(--accent); }
.res-icon.green  { background: rgba(26,127,55,0.1);            color: var(--success); }
.res-icon.orange { background: rgba(154,103,0,0.1);            color: var(--warning); }
.res-icon.purple { background: rgba(115,63,255,0.1);           color: #7c3aed; }
.res-count { font-size: 24px; font-weight: 700; }
.res-label { font-size: 11px; color: var(--text-muted); }

.section-title { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; }
.region-table-wrap { }
.region-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.region-table th { text-align: left; padding: 8px 10px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border); background: var(--bg-surface); }
.region-table td { padding: 8px 10px; border-bottom: 1px solid var(--border-light); color: var(--text-secondary); }
.region-table tr:hover td { background: var(--bg-hover); }
.ok   { color: var(--success); }
.muted { color: var(--text-muted); }
.mono  { font-family: 'Cascadia Code', 'Consolas', monospace; }
</style>
