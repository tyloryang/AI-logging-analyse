<template>
  <div class="container-view">
    <!-- Header -->
    <div class="page-header">
      <div class="header-left">
        <h1>容器管理</h1>
        <span class="subtitle">Kubernetes 集群资源总览</span>
      </div>
      <div class="header-right">
        <select v-model="activeNs" class="ns-select" @change="fetchAll">
          <option value="">全部命名空间</option>
          <option v-for="ns in namespaces" :key="ns.name" :value="ns.name">{{ ns.name }}</option>
        </select>
        <button class="btn-refresh" @click="fetchAll" :disabled="loading">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
          刷新
        </button>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="error-banner">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      {{ error }}
    </div>

    <!-- Summary cards -->
    <div class="summary-row" v-if="summary">
      <div class="stat-card" :class="{ warn: summary.nodes.ready < summary.nodes.total }">
        <div class="stat-icon node">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ summary.nodes.ready }}<span class="stat-total">/{{ summary.nodes.total }}</span></div>
          <div class="stat-label">节点 Ready</div>
        </div>
      </div>
      <div class="stat-card" :class="{ warn: summary.pods.running < summary.pods.total }">
        <div class="stat-icon pod">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/></svg>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ summary.pods.running }}<span class="stat-total">/{{ summary.pods.total }}</span></div>
          <div class="stat-label">Pod Running</div>
        </div>
      </div>
      <div class="stat-card" :class="{ warn: summary.deployments.ready < summary.deployments.total }">
        <div class="stat-icon deploy">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
        </div>
        <div class="stat-body">
          <div class="stat-value">{{ summary.deployments.ready }}<span class="stat-total">/{{ summary.deployments.total }}</span></div>
          <div class="stat-label">Deployment Ready</div>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="tab-row">
      <button v-for="tab in TABS" :key="tab.id" class="tab-btn" :class="{ active: activeTab === tab.id }" @click="activeTab = tab.id">
        {{ tab.label }}
        <span class="tab-count" v-if="tabCount(tab.id) !== null">{{ tabCount(tab.id) }}</span>
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-row">
      <div class="spinner"></div> 加载中…
    </div>

    <!-- Pods table -->
    <div v-else-if="activeTab === 'pods'" class="table-wrap">
      <table class="k8s-table">
        <thead><tr>
          <th>名称</th><th>命名空间</th><th>状态</th><th>节点</th><th>IP</th><th>容器</th><th>重启</th><th>创建时间</th>
        </tr></thead>
        <tbody>
          <tr v-if="!pods.length"><td colspan="8" class="empty">暂无数据</td></tr>
          <tr v-for="p in pods" :key="p.namespace+'/'+p.name">
            <td class="name-cell">{{ p.name }}</td>
            <td><span class="ns-tag">{{ p.namespace }}</span></td>
            <td><span class="status-dot" :class="p.statusClass"></span>{{ p.status }}</td>
            <td class="muted">{{ p.node }}</td>
            <td class="mono muted">{{ p.ip }}</td>
            <td>
              <span v-for="c in p.containers" :key="c.name" class="container-tag" :class="{ ready: c.ready }">{{ c.name }}</span>
            </td>
            <td :class="{ 'col-warn': p.restarts > 0 }">{{ p.restarts }}</td>
            <td class="muted">{{ p.age }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Deployments table -->
    <div v-else-if="activeTab === 'deployments'" class="table-wrap">
      <table class="k8s-table">
        <thead><tr>
          <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>镜像</th><th>创建时间</th>
        </tr></thead>
        <tbody>
          <tr v-if="!deployments.length"><td colspan="6" class="empty">暂无数据</td></tr>
          <tr v-for="d in deployments" :key="d.namespace+'/'+d.name">
            <td class="name-cell">{{ d.name }}</td>
            <td><span class="ns-tag">{{ d.namespace }}</span></td>
            <td><span class="status-dot" :class="d.statusClass"></span>{{ d.status }}</td>
            <td>{{ d.ready }}/{{ d.desired }}</td>
            <td class="mono small">{{ d.images.join(', ') }}</td>
            <td class="muted">{{ d.age }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Services table -->
    <div v-else-if="activeTab === 'services'" class="table-wrap">
      <table class="k8s-table">
        <thead><tr>
          <th>名称</th><th>命名空间</th><th>类型</th><th>ClusterIP</th><th>端口</th><th>创建时间</th>
        </tr></thead>
        <tbody>
          <tr v-if="!services.length"><td colspan="6" class="empty">暂无数据</td></tr>
          <tr v-for="s in services" :key="s.namespace+'/'+s.name">
            <td class="name-cell">{{ s.name }}</td>
            <td><span class="ns-tag">{{ s.namespace }}</span></td>
            <td><span class="svc-type" :class="s.type.toLowerCase()">{{ s.type }}</span></td>
            <td class="mono small">{{ s.clusterIP }}</td>
            <td class="mono small">{{ s.ports.join(', ') }}</td>
            <td class="muted">{{ s.age }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Nodes table -->
    <div v-else-if="activeTab === 'nodes'" class="table-wrap">
      <table class="k8s-table">
        <thead><tr>
          <th>名称</th><th>状态</th><th>角色</th><th>版本</th><th>OS</th><th>创建时间</th>
        </tr></thead>
        <tbody>
          <tr v-if="!nodes.length"><td colspan="6" class="empty">暂无数据</td></tr>
          <tr v-for="n in nodes" :key="n.name">
            <td class="name-cell">{{ n.name }}</td>
            <td><span class="status-dot" :class="n.statusClass"></span>{{ n.status }}</td>
            <td><span class="role-tag">{{ n.roles }}</span></td>
            <td class="mono small">{{ n.version }}</td>
            <td class="small muted">{{ n.os }}</td>
            <td class="muted">{{ n.age }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/index.js'

const TABS = [
  { id: 'pods',        label: 'Pods' },
  { id: 'deployments', label: 'Deployments' },
  { id: 'services',    label: 'Services' },
  { id: 'nodes',       label: 'Nodes' },
]

const activeTab  = ref('pods')
const activeNs   = ref('')
const loading    = ref(false)
const error      = ref('')
const summary    = ref(null)
const namespaces = ref([])
const pods       = ref([])
const deployments = ref([])
const services   = ref([])
const nodes      = ref([])

function tabCount(id) {
  const m = { pods: pods.value.length, deployments: deployments.value.length, services: services.value.length, nodes: nodes.value.length }
  return m[id] ?? null
}

async function fetchAll() {
  loading.value = true
  error.value   = ''
  try {
    const ns = activeNs.value || undefined
    const [sum, nsList, podList, depList, svcList, nodeList] = await Promise.all([
      api.k8sSummary().catch(() => null),
      api.k8sNamespaces().catch(() => []),
      api.k8sPods(ns).catch(() => []),
      api.k8sDeployments(ns).catch(() => []),
      api.k8sServices(ns).catch(() => []),
      api.k8sNodes().catch(() => []),
    ])
    summary.value     = sum
    namespaces.value  = nsList
    pods.value        = podList
    deployments.value = depList
    services.value    = svcList
    nodes.value       = nodeList
  } catch (e) {
    error.value = `加载失败: ${e}`
  } finally {
    loading.value = false
  }
}

onMounted(fetchAll)
</script>

<style scoped>
.container-view { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--bg-base); color: var(--text-primary); }

.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 12px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
.header-left h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
.subtitle { font-size: 12px; color: var(--text-muted); }
.header-right { display: flex; align-items: center; gap: 8px; }
.ns-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); padding: 5px 10px; font-size: 12px; cursor: pointer; }
.btn-refresh { display: flex; align-items: center; gap: 5px; background: var(--accent-dim); border: 1px solid var(--border-accent); color: var(--accent); border-radius: 6px; padding: 5px 12px; font-size: 12px; cursor: pointer; transition: all .15s; }
.btn-refresh:hover { background: var(--accent-dim); filter: brightness(0.95); }
.btn-refresh:disabled { opacity: .5; cursor: not-allowed; }

.error-banner { margin: 12px 20px 0; background: rgba(207,34,46,0.07); border: 1px solid rgba(207,34,46,0.25); border-radius: 6px; padding: 8px 12px; font-size: 12px; color: var(--error); display: flex; align-items: center; gap: 7px; }

.summary-row { display: flex; gap: 12px; padding: 12px 20px 0; flex-shrink: 0; }
.stat-card { flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; display: flex; align-items: center; gap: 12px; }
.stat-card.warn { border-color: rgba(154,103,0,0.3); background: rgba(154,103,0,0.05); }
.stat-icon { width: 38px; height: 38px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
.stat-icon.node   { background: var(--accent-dim); color: var(--accent); }
.stat-icon.pod    { background: rgba(26,127,55,0.12); color: var(--success); }
.stat-icon.deploy { background: rgba(154,103,0,0.12); color: var(--warning); }
.stat-value { font-size: 22px; font-weight: 700; line-height: 1; }
.stat-total { font-size: 14px; color: var(--text-muted); font-weight: 400; }
.stat-label { font-size: 11px; color: var(--text-muted); margin-top: 3px; }

.tab-row { display: flex; gap: 4px; padding: 10px 20px 0; flex-shrink: 0; }
.tab-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid transparent; background: none; color: var(--text-secondary); font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all .15s; }
.tab-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.tab-btn.active { background: var(--accent-dim); border-color: var(--border-accent); color: var(--accent); font-weight: 500; }
.tab-count { font-size: 10px; background: var(--bg-surface); border: 1px solid var(--border); padding: 1px 5px; border-radius: 8px; color: var(--text-secondary); }

.loading-row { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 40px; color: var(--text-muted); }
.spinner { width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.table-wrap { flex: 1; overflow: auto; padding: 10px 20px 20px; }
.k8s-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.k8s-table th { text-align: left; padding: 8px 10px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border); white-space: nowrap; position: sticky; top: 0; background: var(--bg-base); }
.k8s-table td { padding: 7px 10px; border-bottom: 1px solid var(--border-light); vertical-align: middle; }
.k8s-table tr:hover td { background: var(--bg-hover); }
.empty { text-align: center; color: var(--text-muted); padding: 40px !important; }

.name-cell { font-weight: 500; font-family: 'JetBrains Mono', monospace; font-size: 11.5px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ns-tag   { background: var(--accent-dim); border: 1px solid var(--border-accent); color: var(--accent); padding: 1px 6px; border-radius: 10px; font-size: 10.5px; }
.role-tag { background: rgba(154,103,0,0.1); border: 1px solid rgba(154,103,0,0.2); color: var(--warning); padding: 1px 6px; border-radius: 10px; font-size: 10.5px; }
.svc-type { padding: 1px 6px; border-radius: 10px; font-size: 10.5px; }
.svc-type.clusterip    { background: var(--accent-dim);          color: var(--accent);   border: 1px solid var(--border-accent); }
.svc-type.nodeport     { background: rgba(154,103,0,0.1);        color: var(--warning);  border: 1px solid rgba(154,103,0,0.2); }
.svc-type.loadbalancer { background: rgba(26,127,55,0.1);        color: var(--success);  border: 1px solid rgba(26,127,55,0.2); }

.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
.status-dot.ok   { background: var(--success); }
.status-dot.warn { background: var(--warning); }
.status-dot.err  { background: var(--error); }

.container-tag { display: inline-block; font-size: 10px; padding: 1px 5px; border-radius: 4px; margin-right: 3px; background: var(--bg-surface); color: var(--text-secondary); border: 1px solid var(--border); }
.container-tag.ready { color: var(--success); background: rgba(26,127,55,0.08); border-color: rgba(26,127,55,0.2); }

.mono  { font-family: 'JetBrains Mono', monospace; }
.small { font-size: 11px; }
.muted { color: var(--text-muted); }
.col-warn { color: var(--warning); font-weight: 500; }
</style>
