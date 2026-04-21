<template>
  <div class="es-view">
    <!-- Cluster tabs bar -->
    <div class="cluster-bar">
      <div class="cb-logo">
        <span class="cb-logo-icon">⚡</span>
        ES Manager
      </div>
      <div
        v-for="c in clusters" :key="c.id"
        class="cluster-tab" :class="{ active: activeId === c.id }"
        @click="switchCluster(c.id)"
      >
        <span class="ct-dot" :class="healthDot(c)"></span>
        <span class="ct-name" :style="activeId === c.id ? `color:${c.color}` : ''">
          {{ c.name }}
          <span v-if="c.env" class="ct-env" :class="`env-${c.env}`">{{ c.env.toUpperCase() }}</span>
        </span>
        <span class="ct-close" @click.stop="removeCluster(c.id)">✕</span>
      </div>
      <div class="cb-add" @click="openAddModal()" title="添加集群">＋</div>
    </div>

    <div class="app-body">
      <!-- Welcome screen when no clusters -->
      <div v-if="!clusters.length || !activeId" class="welcome">
        <div class="welcome-icon">⚡</div>
        <div class="welcome-title">ES Manager Pro</div>
        <div class="welcome-sub">支持同时管理多个 Elasticsearch 集群，点击「＋」添加集群连接</div>
        <button class="btn btn-primary" style="padding:10px 28px;font-size:13px" @click="openAddModal()">＋ 添加集群</button>
      </div>

      <!-- Main layout when cluster selected -->
      <template v-else>
        <!-- Left nav -->
        <div class="sidebar-nav">
          <div class="nav-cluster-name">{{ clusterMeta?.cluster_name || activeCluster?.name }}</div>
          <div class="nav-section-label">监控</div>
          <div v-for="item in NAV_ITEMS" :key="item.id" class="nav-item" :class="{ active: activePage === item.id }" @click="activePage = item.id">
            <span class="ni">{{ item.icon }}</span>{{ item.label }}
          </div>
        </div>

        <!-- Page content -->
        <div class="main-content">
          <!-- OVERVIEW -->
          <div v-if="activePage === 'overview'" class="page-wrap">
            <div class="page-head">
              <div>
                <div class="page-title">集群概览</div>
                <div class="page-sub" v-if="overview">
                  {{ clusterMeta?.cluster_name }} · v{{ clusterMeta?.version }} ·
                  <span class="health-badge" :class="overview.health?.status">{{ overview.health?.status }}</span>
                </div>
              </div>
              <button class="btn btn-ghost btn-sm" @click="loadOverview">↻ 刷新</button>
            </div>
            <div v-if="loadingPage" class="loading"><div class="spinner"></div> 加载中…</div>
            <div v-else-if="overview" class="page-body">
              <!-- Health cards -->
              <div class="cards cards-4">
                <div class="card">
                  <div class="card-title">节点数</div>
                  <div class="metric-val metric-blue">{{ overview.health?.number_of_nodes ?? '—' }}</div>
                  <div class="metric-sub">数据节点: {{ overview.health?.number_of_data_nodes }}</div>
                </div>
                <div class="card">
                  <div class="card-title">索引数</div>
                  <div class="metric-val">{{ overview.stats?.indices?.count ?? '—' }}</div>
                  <div class="metric-sub">分片: {{ overview.health?.active_shards }}</div>
                </div>
                <div class="card">
                  <div class="card-title">文档总数</div>
                  <div class="metric-val">{{ fmtNum(overview.stats?.indices?.docs?.count) }}</div>
                  <div class="metric-sub">已删除: {{ fmtNum(overview.stats?.indices?.docs?.deleted) }}</div>
                </div>
                <div class="card">
                  <div class="card-title">存储大小</div>
                  <div class="metric-val">{{ overview.stats?.indices?.store?.size_in_bytes != null ? fmtBytes(overview.stats.indices.store.size_in_bytes) : '—' }}</div>
                  <div class="metric-sub" :class="overview.health?.status === 'red' ? 'metric-red' : overview.health?.status === 'yellow' ? 'metric-yellow' : 'metric-green'">
                    未分配分片: {{ overview.health?.unassigned_shards ?? 0 }}
                  </div>
                </div>
              </div>
              <!-- Nodes mini table -->
              <div v-if="overview.nodes_info?.length" class="tbl-wrap">
                <div class="tbl-toolbar"><span class="tbl-title">节点</span></div>
                <table>
                  <thead><tr><th>名称</th><th>IP</th><th>角色</th><th>Master</th><th>CPU%</th><th>堆内存%</th><th>磁盘%</th></tr></thead>
                  <tbody>
                    <tr v-for="n in overview.nodes_info" :key="n.name">
                      <td class="td-mono">{{ n.name }}</td>
                      <td class="td-mono">{{ n.ip }}</td>
                      <td><span class="badge badge-blue">{{ n['node.role'] }}</span></td>
                      <td>{{ n.master === '*' ? '★' : '' }}</td>
                      <td><div class="progress"><div class="progress-fill" :class="pClass(n.cpu)" :style="`width:${n.cpu}%`"></div></div></td>
                      <td><div class="progress"><div class="progress-fill" :class="pClass(n['heap.percent'])" :style="`width:${n['heap.percent']}%`"></div></div></td>
                      <td><div class="progress"><div class="progress-fill" :class="pClass(n['disk.used_percent'])" :style="`width:${n['disk.used_percent']}%`"></div></div></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- INDICES -->
          <div v-else-if="activePage === 'indices'" class="page-wrap">
            <div class="page-head">
              <div class="page-title">索引管理</div>
              <div class="flex gap-2">
                <input v-model="indexSearch" class="tbl-search" placeholder="搜索索引名…" />
                <button class="btn btn-ghost btn-sm" @click="loadIndices">↻ 刷新</button>
              </div>
            </div>
            <div v-if="loadingPage" class="loading"><div class="spinner"></div></div>
            <div v-else class="page-body">
              <div class="tbl-wrap">
                <table>
                  <thead><tr><th>健康</th><th>状态</th><th>索引名</th><th>主/副</th><th>文档数</th><th>存储</th><th>操作</th></tr></thead>
                  <tbody>
                    <tr v-if="!filteredIndices.length"><td colspan="7" class="empty">暂无索引</td></tr>
                    <tr v-for="idx in filteredIndices" :key="idx.index">
                      <td><span class="health-dot" :class="idx.health"></span></td>
                      <td><span class="badge" :class="idx.status === 'open' ? 'badge-green' : 'badge-gray'">{{ idx.status }}</span></td>
                      <td class="td-mono td-link" @click="showIndexDetail(idx)">{{ idx.index }}</td>
                      <td>{{ idx.pri }}/{{ idx.rep }}</td>
                      <td>{{ fmtNum(idx['docs.count']) }}</td>
                      <td class="td-mono">{{ idx['store.size'] }}</td>
                      <td class="flex gap-1">
                        <button class="btn btn-xs btn-ghost" @click="indexAction(idx.index, '_refresh')">刷新</button>
                        <button class="btn btn-xs btn-ghost" @click="indexAction(idx.index, '_flush')">Flush</button>
                        <button class="btn btn-xs btn-danger" @click="deleteIndex(idx.index)">删除</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- NODES -->
          <div v-else-if="activePage === 'nodes'" class="page-wrap">
            <div class="page-head">
              <div class="page-title">节点管理</div>
              <button class="btn btn-ghost btn-sm" @click="loadNodes">↻ 刷新</button>
            </div>
            <div v-if="loadingPage" class="loading"><div class="spinner"></div></div>
            <div v-else class="page-body">
              <div class="tbl-wrap">
                <table>
                  <thead><tr><th>名称</th><th>IP</th><th>角色</th><th>Master</th><th>CPU%</th><th>堆内存%</th><th>RAM%</th><th>磁盘%</th><th>负载1m</th></tr></thead>
                  <tbody>
                    <tr v-if="!nodes.length"><td colspan="9" class="empty">无节点数据</td></tr>
                    <tr v-for="n in nodes" :key="n.name">
                      <td class="td-mono">{{ n.name }}</td>
                      <td class="td-mono">{{ n.ip }}</td>
                      <td><span class="badge badge-blue">{{ n['node.role'] }}</span></td>
                      <td style="text-align:center">{{ n.master === '*' ? '⭐' : '' }}</td>
                      <td><meter-bar :val="parseInt(n.cpu)" /></td>
                      <td><meter-bar :val="parseInt(n['heap.percent'])" /></td>
                      <td><meter-bar :val="parseInt(n['ram.percent'])" /></td>
                      <td><meter-bar :val="parseInt(n['disk.used_percent'])" /></td>
                      <td class="td-mono">{{ n['load_1m'] }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- SHARDS -->
          <div v-else-if="activePage === 'shards'" class="page-wrap">
            <div class="page-head">
              <div class="page-title">分片视图</div>
              <div class="flex gap-2">
                <input v-model="shardIndexFilter" class="tbl-search" placeholder="按索引过滤…" />
                <button class="btn btn-ghost btn-sm" @click="loadShards">↻ 刷新</button>
              </div>
            </div>
            <div v-if="loadingPage" class="loading"><div class="spinner"></div></div>
            <div v-else class="page-body">
              <div class="tbl-wrap">
                <table>
                  <thead><tr><th>索引</th><th>分片</th><th>类型</th><th>状态</th><th>文档</th><th>大小</th><th>节点</th><th>未分配原因</th></tr></thead>
                  <tbody>
                    <tr v-if="!filteredShards.length"><td colspan="8" class="empty">无分片数据</td></tr>
                    <tr v-for="(s, i) in filteredShards" :key="i">
                      <td class="td-mono">{{ s.index }}</td>
                      <td>{{ s.shard }}</td>
                      <td><span class="shard-badge" :class="s.prirep === 'p' ? 'primary' : 'replica'">{{ s.prirep === 'p' ? 'P' : 'R' }}</span></td>
                      <td><span class="badge" :class="shardBadge(s.state)">{{ s.state }}</span></td>
                      <td>{{ fmtNum(s.docs) }}</td>
                      <td class="td-mono">{{ s.store }}</td>
                      <td class="td-mono">{{ s.node || '—' }}</td>
                      <td class="text-yellow small">{{ s['unassigned.reason'] || '' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- QUERY CONSOLE -->
          <div v-else-if="activePage === 'query'" class="page-wrap query-page">
            <div class="page-head">
              <div class="page-title">查询控制台</div>
              <div class="flex gap-2 items-center">
                <select v-model="qMethod" class="query-method">
                  <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
                </select>
                <input v-model="qPath" class="query-path" placeholder="API 路径" @keydown.ctrl.enter="runQuery" />
                <button class="btn btn-primary btn-sm" @click="runQuery" :disabled="querying">▶ 执行</button>
                <select v-model="qPreset" class="query-method" @change="applyPreset" style="max-width:180px">
                  <option value="">快捷命令…</option>
                  <optgroup label="集群">
                    <option value="GET|_cluster/health">集群健康</option>
                    <option value="GET|_cluster/stats">集群统计</option>
                    <option value="GET|_cluster/settings">集群设置</option>
                    <option value="GET|_cluster/pending_tasks">待处理任务</option>
                  </optgroup>
                  <optgroup label="节点">
                    <option value="GET|_cat/nodes?v&h=ip,name,heap.percent,disk.used_percent,cpu,master">节点列表</option>
                    <option value="GET|_nodes/stats/jvm">JVM统计</option>
                    <option value="GET|_nodes/hot_threads">热点线程</option>
                  </optgroup>
                  <optgroup label="索引">
                    <option value="GET|_cat/indices?v&s=store.size:desc">索引列表</option>
                    <option value="GET|_cat/shards?v">分片列表</option>
                    <option value="GET|_cat/aliases?v">别名列表</option>
                    <option value="GET|_cat/allocation?v">磁盘分配</option>
                  </optgroup>
                  <optgroup label="搜索">
                    <option value='POST|_search|{"query":{"match_all":{}},"size":10}'>全局搜索</option>
                  </optgroup>
                </select>
              </div>
            </div>
            <div class="query-layout">
              <div class="query-left">
                <div class="editor-wrap">
                  <div class="editor-header">
                    <span>请求体 (JSON)</span>
                    <div class="flex gap-2">
                      <span class="text-xs" :class="qBodyValid ? 'text-green' : 'text-red'">{{ qBodyStatus }}</span>
                      <button class="btn btn-xs btn-ghost" @click="formatBody">格式化</button>
                      <button class="btn btn-xs btn-ghost" @click="qBody = ''">清空</button>
                    </div>
                  </div>
                  <textarea v-model="qBody" class="editor" spellcheck="false" placeholder='{"query":{"match_all":{}}}' @input="validateBody" @keydown.ctrl.enter.prevent="runQuery"></textarea>
                </div>
                <div v-if="qHistory.length" class="q-history">
                  <span class="text-xs text-muted">历史:</span>
                  <span v-for="(h, i) in qHistory.slice(-8).reverse()" :key="i" class="q-hist-item" @click="loadHistory(h)">{{ h.method }} {{ h.path.slice(0, 30) }}</span>
                </div>
              </div>
              <div class="query-right">
                <div class="editor-wrap">
                  <div class="editor-header">
                    <span>响应结果</span>
                    <div class="flex gap-2">
                      <span v-if="qMeta" class="text-xs" :class="qMeta.ok ? 'text-green' : 'text-red'">{{ qMeta.status }} · {{ qMeta.ms }}ms</span>
                      <button class="btn btn-xs btn-ghost" @click="copyResult">复制</button>
                    </div>
                  </div>
                  <div class="result-content">
                    <div v-if="querying" class="loading"><div class="spinner"></div></div>
                    <pre v-else-if="qResult" class="json-out" v-html="highlightJson(qResult)"></pre>
                    <div v-else class="empty">执行查询后显示结果</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

        </div><!-- /main-content -->
      </template>
    </div><!-- /app-body -->

    <!-- Add/Edit Cluster Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
      <div class="modal">
        <div class="modal-title">{{ editingId ? '编辑集群' : '添加集群' }}</div>
        <div class="form-row">
          <div class="form-group" style="flex:1">
            <label class="form-label">连接名称 *</label>
            <input v-model="form.name" class="form-input" placeholder="生产-ES集群" />
          </div>
          <div class="form-group" style="width:90px">
            <label class="form-label">环境</label>
            <select v-model="form.env" class="form-input">
              <option value="">无</option><option value="prod">PROD</option>
              <option value="uat">UAT</option><option value="sit">SIT</option><option value="dev">DEV</option>
            </select>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Host *</label>
          <input v-model="form.host" class="form-input form-input-mono" placeholder="http://localhost:9200" />
        </div>
        <div class="form-row">
          <div class="form-group"><label class="form-label">用户名</label><input v-model="form.username" class="form-input" placeholder="elastic" /></div>
          <div class="form-group"><label class="form-label">密码</label><input v-model="form.password" class="form-input" type="password" placeholder="••••••" /></div>
        </div>
        <div class="form-group">
          <label class="form-label">API Key（优先）</label>
          <input v-model="form.api_key" class="form-input form-input-mono" placeholder="base64_encoded_api_key" />
        </div>
        <div class="form-group">
          <label class="form-label">备注</label>
          <input v-model="form.note" class="form-input" placeholder="可选" />
        </div>
        <div v-if="testResult" class="alert" :class="testResult.ok ? 'alert-success' : 'alert-error'">
          {{ testResult.ok ? `✓ 连接成功: ${testResult.cluster_name} v${testResult.version}` : `✗ 连接失败: ${testResult.error}` }}
        </div>
        <div class="modal-footer" style="justify-content:space-between">
          <button class="btn btn-ghost btn-sm" @click="testConnection" :disabled="testing">{{ testing ? '测试中…' : '🔌 测试连接' }}</button>
          <div class="flex gap-2">
            <button class="btn btn-ghost" @click="showModal = false">取消</button>
            <button class="btn btn-primary" @click="submitCluster" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Notify -->
    <div class="notif-container">
      <div v-for="n in notifs" :key="n.id" class="notif" :class="`notif-${n.type}`">{{ n.msg }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { api } from '../api/index.js'

// ── Inline component ────────────────────────────────────────────────────────
const MeterBar = {
  props: { val: Number },
  template: `<div style="display:flex;align-items:center;gap:6px"><div style="width:70px;height:5px;background:rgba(255,255,255,0.08);border-radius:3px;overflow:hidden"><div :style="{width:clamp(val||0,0,100)+'%',height:'100%',background:val>85?'#ef4444':val>65?'#eab308':'#22c55e',borderRadius:'3px'}"></div></div><span style="font-size:11px;color:#94a3b8;width:26px">{{val||0}}%</span></div>`,
  setup(p) { const clamp = (v,a,b) => Math.min(Math.max(v,a),b); return { clamp } }
}

const NAV_ITEMS = [
  { id: 'overview', icon: '📊', label: '集群概览' },
  { id: 'indices',  icon: '📁', label: '索引管理' },
  { id: 'nodes',    icon: '🖥',  label: '节点管理' },
  { id: 'shards',   icon: '🔷', label: '分片视图' },
  { id: 'query',    icon: '⚡',  label: '查询控制台' },
]

const clusters     = ref([])
const activeId     = ref(null)
const activePage   = ref('overview')
const loadingPage  = ref(false)
const clusterMeta  = ref(null)
const overview     = ref(null)
const indices      = ref([])
const nodes        = ref([])
const shards       = ref([])
const indexSearch  = ref('')
const shardIndexFilter = ref('')

// Query console
const qMethod    = ref('GET')
const qPath      = ref('_cluster/health')
const qBody      = ref('')
const qBodyValid = ref(true)
const qBodyStatus = ref('')
const qResult    = ref('')
const qMeta      = ref(null)
const qPreset    = ref('')
const qHistory   = ref([])
const querying   = ref(false)

// Modal
const showModal  = ref(false)
const editingId  = ref(null)
const saving     = ref(false)
const testing    = ref(false)
const testResult = ref(null)
const form       = ref({ name: '', host: '', username: '', password: '', api_key: '', env: '', note: '', color: '#4f8ef7' })

// Notifications
const notifs = ref([])

const activeCluster   = computed(() => clusters.value.find(c => c.id === activeId.value))
const filteredIndices = computed(() => indexSearch.value ? indices.value.filter(i => i.index.includes(indexSearch.value)) : indices.value)
const filteredShards  = computed(() => shardIndexFilter.value ? shards.value.filter(s => s.index.includes(shardIndexFilter.value)) : shards.value)

// ── Cluster ops ─────────────────────────────────────────────────────────────
async function loadClusters() {
  try { clusters.value = await api.esClusters() } catch { clusters.value = [] }
}

async function switchCluster(id) {
  activeId.value = id
  clusterMeta.value = null
  await loadPage()
}

async function loadPage() {
  if (!activeId.value) return
  if (activePage.value === 'overview') await loadOverview()
  else if (activePage.value === 'indices') await loadIndices()
  else if (activePage.value === 'nodes') await loadNodes()
  else if (activePage.value === 'shards') await loadShards()
}

watch(activePage, loadPage)

async function loadOverview() {
  loadingPage.value = true
  try {
    const data = await api.esOverview(activeId.value)
    overview.value = data
    clusterMeta.value = { cluster_name: data.health?.cluster_name, version: data.stats?.nodes?.versions?.[0] }
  } catch (e) { notify(`加载概览失败: ${e}`, 'error') }
  finally { loadingPage.value = false }
}

async function loadIndices() {
  loadingPage.value = true
  try { indices.value = await api.esIndices(activeId.value) }
  catch (e) { notify(`加载索引失败: ${e}`, 'error'); indices.value = [] }
  finally { loadingPage.value = false }
}

async function loadNodes() {
  loadingPage.value = true
  try { nodes.value = await api.esNodes(activeId.value) }
  catch (e) { nodes.value = [] }
  finally { loadingPage.value = false }
}

async function loadShards() {
  loadingPage.value = true
  try { shards.value = await api.esShards(activeId.value) }
  catch (e) { shards.value = [] }
  finally { loadingPage.value = false }
}

// ── Index actions ────────────────────────────────────────────────────────────
async function indexAction(index, action) {
  try {
    await api.esProxy(activeId.value, 'POST', `${index}/${action}`)
    notify(`${action} 成功`, 'success')
    await loadIndices()
  } catch (e) { notify(`操作失败: ${e}`, 'error') }
}

async function deleteIndex(index) {
  if (!confirm(`确认删除索引 "${index}"？此操作不可恢复！`)) return
  try {
    await api.esProxy(activeId.value, 'DELETE', index)
    notify(`索引 ${index} 已删除`, 'success')
    await loadIndices()
  } catch (e) { notify(`删除失败: ${e}`, 'error') }
}

// ── Query console ────────────────────────────────────────────────────────────
function validateBody() {
  if (!qBody.value.trim()) { qBodyValid.value = true; qBodyStatus.value = ''; return }
  try { JSON.parse(qBody.value); qBodyValid.value = true; qBodyStatus.value = '✓ JSON' }
  catch { qBodyValid.value = false; qBodyStatus.value = '✗ 语法错误' }
}

function formatBody() {
  try { qBody.value = JSON.stringify(JSON.parse(qBody.value), null, 2); qBodyValid.value = true; qBodyStatus.value = '✓ JSON' }
  catch {}
}

function applyPreset() {
  if (!qPreset.value) return
  const [method, path, body] = qPreset.value.split('|')
  qMethod.value = method
  qPath.value   = path
  if (body) try { qBody.value = JSON.stringify(JSON.parse(body), null, 2) } catch { qBody.value = body }
  qPreset.value = ''
}

async function runQuery() {
  if (!activeId.value || querying.value) return
  querying.value = true
  qMeta.value = null
  const t0 = Date.now()
  try {
    const body = qBody.value.trim() ? JSON.parse(qBody.value) : undefined
    const r = await api.esProxy(activeId.value, qMethod.value, qPath.value, body)
    qResult.value = JSON.stringify(r, null, 2)
    qMeta.value = { ok: true, status: 200, ms: Date.now() - t0 }
    pushHistory({ method: qMethod.value, path: qPath.value })
  } catch (e) {
    qResult.value = String(e?.response?.data ? JSON.stringify(e.response.data, null, 2) : e)
    qMeta.value = { ok: false, status: e?.response?.status || 0, ms: Date.now() - t0 }
  } finally { querying.value = false }
}

function pushHistory(item) {
  qHistory.value = [...qHistory.value.filter(h => h.method + h.path !== item.method + item.path), item].slice(-20)
}

function loadHistory(h) { qMethod.value = h.method; qPath.value = h.path }

function highlightJson(str) {
  return str.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
    if (/^"/.test(match)) {
      if (/:$/.test(match)) return `<span style="color:#7dd3fc">${match}</span>`
      return `<span style="color:#86efac">${match}</span>`
    }
    if (/true|false/.test(match)) return `<span style="color:#f472b6">${match}</span>`
    if (/null/.test(match))       return `<span style="color:#94a3b8">${match}</span>`
    return `<span style="color:#fbbf24">${match}</span>`
  })
}

function copyResult() { navigator.clipboard?.writeText(qResult.value); notify('已复制', 'success') }

// ── Cluster CRUD ─────────────────────────────────────────────────────────────
function openAddModal(id) {
  editingId.value = id || null
  testResult.value = null
  if (id) {
    const c = clusters.value.find(c => c.id === id)
    form.value = { name: c.name, host: c.host, username: c.username || '', password: '', api_key: '', env: c.env || '', note: c.note || '', color: c.color || '#4f8ef7' }
  } else {
    form.value = { name: '', host: 'http://localhost:9200', username: '', password: '', api_key: '', env: '', note: '', color: '#4f8ef7' }
  }
  showModal.value = true
}

async function testConnection() {
  if (!form.value.host || !form.value.name) return
  testing.value = true
  testResult.value = null
  try {
    // Save temp to test — if editing use existing id, else create temp
    if (editingId.value) {
      testResult.value = await api.esTestCluster(editingId.value)
    } else {
      // add temporarily
      const tmp = await api.esAddCluster({ ...form.value })
      try { testResult.value = await api.esTestCluster(tmp.id) }
      finally { await api.esDeleteCluster(tmp.id) }
    }
  } catch (e) { testResult.value = { ok: false, error: String(e) } }
  finally { testing.value = false }
}

async function submitCluster() {
  if (!form.value.name || !form.value.host) return
  saving.value = true
  try {
    if (editingId.value) {
      await api.esUpdateCluster(editingId.value, form.value)
      notify('集群配置已更新', 'success')
    } else {
      const c = await api.esAddCluster(form.value)
      await loadClusters()
      activeId.value = c.id
      await loadOverview()
      notify(`已添加集群: ${form.value.name}`, 'success')
    }
    showModal.value = false
    await loadClusters()
  } catch (e) { notify(`保存失败: ${e}`, 'error') }
  finally { saving.value = false }
}

async function removeCluster(id) {
  if (!confirm('确认移除该集群连接？')) return
  await api.esDeleteCluster(id)
  await loadClusters()
  if (activeId.value === id) {
    activeId.value = clusters.value[0]?.id || null
    if (activeId.value) await loadOverview()
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function healthDot(c) {
  // For now just return a color class based on cluster - would need health data
  return 'green'
}

function fmtNum(n) {
  if (n == null) return '—'
  const num = parseInt(n)
  if (isNaN(num)) return n
  return num.toLocaleString()
}

function fmtBytes(bytes) {
  if (!bytes) return '0B'
  const units = ['B','KB','MB','GB','TB']
  let i = 0, v = bytes
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(1)}${units[i]}`
}

function pClass(v) {
  const n = parseInt(v)
  if (n > 85) return 'pf-red'
  if (n > 65) return 'pf-yellow'
  return 'pf-green'
}

function shardBadge(state) {
  if (state === 'STARTED')      return 'badge-green'
  if (state === 'UNASSIGNED')   return 'badge-red'
  if (state === 'INITIALIZING') return 'badge-yellow'
  return 'badge-gray'
}

function showIndexDetail(idx) {
  qMethod.value = 'GET'
  qPath.value   = `${idx.index}/_stats`
  activePage.value = 'query'
  runQuery()
}

let _notifId = 0
function notify(msg, type = 'info') {
  const id = ++_notifId
  notifs.value.push({ id, msg, type })
  setTimeout(() => { notifs.value = notifs.value.filter(n => n.id !== id) }, 3500)
}

let _timer = null
onMounted(async () => {
  await loadClusters()
  if (clusters.value.length) {
    activeId.value = clusters.value[0].id
    await loadOverview()
  }
  _timer = setInterval(() => { if (activeId.value && activePage.value === 'overview') loadOverview() }, 30000)
})
onUnmounted(() => clearInterval(_timer))
</script>

<style scoped>
.es-view { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--bg-base); color: var(--text-primary); font-size: 13px; }

/* Cluster bar */
.cluster-bar { height: 44px; background: var(--bg-card); border-bottom: 1px solid var(--border); display: flex; align-items: stretch; flex-shrink: 0; overflow-x: auto; }
.cluster-bar::-webkit-scrollbar { height: 3px; }
.cluster-bar::-webkit-scrollbar-thumb { background: var(--border); }
.cb-logo { display: flex; align-items: center; gap: 8px; padding: 0 16px; font-weight: 700; font-size: 14px; color: var(--text-primary); border-right: 1px solid var(--border); flex-shrink: 0; }
.cb-logo-icon { background: linear-gradient(135deg, var(--accent), #a855f7); width: 24px; height: 24px; border-radius: 5px; display: flex; align-items: center; justify-content: center; font-size: 12px; }
.cluster-tab { display: flex; align-items: center; gap: 7px; padding: 0 12px; cursor: pointer; color: var(--text-secondary); font-size: 12px; border-right: 1px solid var(--border); border-bottom: 2px solid transparent; transition: .15s; flex-shrink: 0; min-width: 130px; }
.cluster-tab:hover { background: var(--bg-hover); color: var(--text-primary); }
.cluster-tab.active { background: var(--bg-hover); color: var(--text-primary); border-bottom-color: var(--accent); }
.ct-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.ct-dot.green  { background: var(--success); }
.ct-dot.yellow { background: var(--warning); }
.ct-dot.red    { background: var(--error); }
.ct-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; display: flex; align-items: center; gap: 5px; }
.ct-env { font-size: 9px; padding: 1px 4px; border-radius: 3px; background: var(--bg-surface); color: var(--text-secondary); }
.env-prod { background: rgba(207,34,46,.1);  color: var(--error); }
.env-uat  { background: rgba(154,103,0,.1);  color: var(--warning); }
.env-sit  { background: var(--accent-dim);   color: var(--accent); }
.env-dev  { background: rgba(168,85,247,.1); color: #a855f7; }
.ct-close { opacity: 0; font-size: 11px; color: var(--text-muted); transition: .15s; padding: 2px 4px; border-radius: 3px; }
.cluster-tab:hover .ct-close { opacity: 1; }
.ct-close:hover { background: rgba(207,34,46,.1); color: var(--error); }
.cb-add { display: flex; align-items: center; padding: 0 16px; cursor: pointer; color: var(--text-muted); font-size: 18px; flex-shrink: 0; transition: .15s; }
.cb-add:hover { color: var(--accent); }

/* App body */
.app-body { display: flex; flex: 1; overflow: hidden; }

/* Welcome */
.welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; }
.welcome-icon { width: 56px; height: 56px; background: linear-gradient(135deg, var(--accent), #a855f7); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 28px; }
.welcome-title { font-size: 22px; font-weight: 700; }
.welcome-sub { color: var(--text-secondary); font-size: 13px; text-align: center; max-width: 380px; line-height: 1.6; }

/* Sidebar nav */
.sidebar-nav { width: 190px; background: var(--bg-card); border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; padding-bottom: 12px; }
.nav-cluster-name { font-size: 12px; font-weight: 600; color: var(--text-primary); padding: 12px 14px 8px; border-bottom: 1px solid var(--border); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nav-section-label { font-size: 10px; font-weight: 600; color: var(--text-muted); letter-spacing: 1.5px; text-transform: uppercase; padding: 10px 14px 4px; }
.nav-item { display: flex; align-items: center; gap: 8px; padding: 7px 14px; cursor: pointer; color: var(--text-secondary); font-size: 12.5px; border-left: 2px solid transparent; transition: .12s; }
.nav-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.nav-item.active { background: var(--accent-dim); color: var(--accent); border-left-color: var(--accent); font-weight: 500; }
.ni { width: 17px; text-align: center; }

/* Main content */
.main-content { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.page-wrap { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
.page-head { padding: 12px 16px 10px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
.page-title { font-size: 14px; font-weight: 600; }
.page-sub { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.page-body { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }

/* Cards */
.cards { display: grid; gap: 10px; }
.cards-4 { grid-template-columns: repeat(4, 1fr); }
.card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
.card-title { font-size: 10px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .8px; margin-bottom: 7px; }
.metric-val { font-size: 24px; font-weight: 700; line-height: 1; }
.metric-sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.metric-blue   { color: var(--accent); }
.metric-green  { color: var(--success); }
.metric-yellow { color: var(--warning); }
.metric-red    { color: var(--error); }

/* Health */
.health-badge { padding: 2px 7px; border-radius: 5px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
.health-badge.green  { background: rgba(26,127,55,.12);  color: var(--success); }
.health-badge.yellow { background: rgba(154,103,0,.12);  color: var(--warning); }
.health-badge.red    { background: rgba(207,34,46,.12);  color: var(--error); }
.health-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.health-dot.green  { background: var(--success); }
.health-dot.yellow { background: var(--warning); }
.health-dot.red    { background: var(--error); }

/* Table */
.tbl-wrap { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.tbl-toolbar { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.tbl-title { font-size: 13px; font-weight: 600; }
.tbl-search { background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 5px 10px; color: var(--text-primary); font-size: 12px; outline: none; width: 180px; }
.tbl-search:focus { border-color: var(--accent); }
table { width: 100%; border-collapse: collapse; }
th { text-align: left; padding: 8px 12px; font-size: 10.5px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px; background: var(--bg-surface); border-bottom: 1px solid var(--border); white-space: nowrap; }
td { padding: 7px 12px; border-bottom: 1px solid var(--border-light); font-size: 12.5px; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--bg-hover); }
.td-mono { font-family: 'Cascadia Code', 'Consolas', 'Cascadia Code', monospace; font-size: 11.5px; }
.td-link { color: var(--accent); cursor: pointer; }
.td-link:hover { text-decoration: underline; }
.empty { text-align: center; padding: 30px; color: var(--text-muted); }

/* Badges */
.badge { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-green  { background: rgba(26,127,55,.1);  color: var(--success); }
.badge-yellow { background: rgba(154,103,0,.1);  color: var(--warning); }
.badge-red    { background: rgba(207,34,46,.1);  color: var(--error); }
.badge-blue   { background: var(--accent-dim);   color: var(--accent); }
.badge-gray   { background: var(--bg-surface);   color: var(--text-muted); border: 1px solid var(--border); }

/* Progress */
.progress { height: 5px; background: var(--bg-surface); border-radius: 3px; overflow: hidden; min-width: 50px; }
.progress-fill { height: 100%; border-radius: 3px; transition: width .4s; }
.pf-green  { background: var(--success); }
.pf-yellow { background: var(--warning); }
.pf-red    { background: var(--error); }

/* Shards */
.shard-badge { padding: 2px 6px; border-radius: 4px; font-size: 10.5px; font-weight: 700; }
.shard-badge.primary { background: rgba(26,127,55,.15);  color: var(--success); }
.shard-badge.replica { background: var(--accent-dim);    color: var(--accent); }

/* Query console */
.query-page { overflow: hidden; }
.query-layout { flex: 1; display: flex; gap: 10px; padding: 10px 16px 12px; overflow: hidden; min-height: 0; }
.query-left, .query-right { flex: 1; display: flex; flex-direction: column; gap: 6px; min-width: 0; overflow: hidden; }
.editor-wrap { flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; min-height: 0; }
.editor-header { padding: 6px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
textarea.editor { flex: 1; background: transparent; border: none; outline: none; padding: 10px 12px; color: var(--text-primary); font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px; line-height: 1.7; resize: none; min-height: 0; }
.result-content { flex: 1; overflow: auto; padding: 10px 12px; min-height: 0; }
pre.json-out { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11.5px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; color: var(--text-primary); margin: 0; }
.q-history { display: flex; align-items: center; gap: 6px; flex-shrink: 0; overflow-x: auto; }
.q-hist-item { font-size: 10.5px; background: var(--bg-surface); border: 1px solid var(--border); border-radius: 4px; padding: 2px 7px; cursor: pointer; white-space: nowrap; color: var(--text-secondary); font-family: 'Cascadia Code', 'Consolas', monospace; }
.q-hist-item:hover { border-color: var(--accent); color: var(--accent); }
.query-method { background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 5px 8px; color: var(--text-primary); font-size: 12px; cursor: pointer; outline: none; }
.query-path { flex: 1; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 5px 10px; color: var(--text-primary); font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px; outline: none; }
.query-path:focus { border-color: var(--accent); }

/* Buttons */
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: .15s; white-space: nowrap; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-primary:hover { background: var(--accent-hover); }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-ghost { background: var(--bg-surface); color: var(--text-secondary); border: 1px solid var(--border); }
.btn-ghost:hover { color: var(--text-primary); background: var(--bg-hover); }
.btn-danger { background: rgba(207,34,46,.08); color: var(--error); border: 1px solid rgba(207,34,46,.25); }
.btn-danger:hover { background: rgba(207,34,46,.15); }
.btn-sm { padding: 4px 10px; font-size: 11px; }
.btn-xs { padding: 2px 8px; font-size: 11px; }

/* Loading */
.loading { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 40px; color: var(--text-muted); }
.spinner { width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .6s linear infinite; flex-shrink: 0; }
@keyframes spin { to { transform: rotate(360deg); } }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 1000; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; width: 480px; max-width: 95vw; max-height: 85vh; overflow-y: auto; box-shadow: var(--shadow-md); }
.modal-title { font-size: 15px; font-weight: 600; margin-bottom: 16px; }
.form-group { margin-bottom: 12px; }
.form-label { display: block; font-size: 11px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .8px; margin-bottom: 5px; }
.form-input { width: 100%; background: var(--bg-input); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; color: var(--text-primary); font-size: 13px; outline: none; transition: .2s; }
.form-input:focus { border-color: var(--accent); }
.form-input::placeholder { color: var(--text-muted); }
.form-input-mono { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px; }
select.form-input option { background: var(--bg-card); }
.form-row { display: flex; gap: 10px; }
.form-row .form-group { flex: 1; }
.modal-footer { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); }

/* Alert */
.alert { padding: 10px 14px; border-radius: 8px; font-size: 12.5px; margin-bottom: 8px; }
.alert-success { background: rgba(26,127,55,.08);  border: 1px solid rgba(26,127,55,.25);  color: var(--success); }
.alert-error   { background: rgba(207,34,46,.08);  border: 1px solid rgba(207,34,46,.25);  color: var(--error); }

/* Notifications */
.notif-container { position: fixed; top: 54px; right: 16px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; pointer-events: none; }
.notif { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; font-size: 12.5px; display: flex; align-items: center; gap: 10px; pointer-events: all; box-shadow: var(--shadow-md); animation: slideIn .25s ease; max-width: 300px; }
@keyframes slideIn { from { transform: translateX(110%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
.notif-success { border-left: 3px solid var(--success); }
.notif-error   { border-left: 3px solid var(--error); }
.notif-info    { border-left: 3px solid var(--accent); }

/* Misc */
.flex { display: flex; }
.gap-2 { gap: 8px; }
.gap-1 { gap: 4px; }
.items-center { align-items: center; }
.small { font-size: 11px; }
.text-xs { font-size: 11px; }
.text-muted  { color: var(--text-muted); }
.text-green  { color: var(--success); }
.text-yellow { color: var(--warning); }
.text-red    { color: var(--error); }
</style>
