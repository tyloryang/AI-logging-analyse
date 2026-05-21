<template>
  <div class="redis-view">
    <div class="cluster-bar">
      <div class="cb-logo">
        <span class="cb-logo-icon">R</span>
        Redis Manager
      </div>
      <button
        v-for="cluster in clusters"
        :key="cluster.id"
        class="cluster-tab"
        :class="{ active: activeId === cluster.id }"
        type="button"
        @click="switchCluster(cluster.id)"
      >
        <span class="ct-dot" :class="clusterHealthTone(cluster.id)"></span>
        <span class="ct-name" :style="activeId === cluster.id ? `color:${cluster.color || '#dc2626'}` : ''">
          {{ cluster.name }}
          <span v-if="cluster.env" class="ct-env" :class="`env-${cluster.env}`">{{ cluster.env.toUpperCase() }}</span>
        </span>
        <span class="ct-close" @click.stop="removeCluster(cluster.id)">×</span>
      </button>
      <button class="cb-add" type="button" title="添加 Redis 连接" @click="openClusterModal()">
        +
      </button>
    </div>

    <div class="page-shell">
      <section v-if="!clusters.length || !activeId" class="welcome card">
        <div class="welcome-mark">R</div>
        <h1>Redis 管理</h1>
        <p>统一维护 Redis 单机与 Redis Cluster 连接、连通性、节点状态、槽位覆盖和容量概览。</p>
        <button class="btn btn-primary" type="button" @click="openClusterModal()">添加 Redis 连接</button>
      </section>

      <template v-else>
        <section class="hero card">
          <div class="hero-left">
            <div class="hero-badge">
              <span class="hero-badge-dot"></span>
              <span>Middleware / Redis</span>
            </div>
            <div class="hero-title-row">
              <h1>{{ activeCluster?.name }}</h1>
              <span class="state-pill" :class="summaryTone">
                {{ stateText }}
              </span>
            </div>
            <p class="hero-subtitle">
              {{ activeCluster?.note || '查看 Redis 单机或集群的角色分布、槽位覆盖、节点连通性和实时负载情况。' }}
            </p>
          </div>
          <div class="hero-actions">
            <button class="btn btn-outline" type="button" @click="openClusterModal(activeId)">编辑连接</button>
            <button class="btn btn-outline" type="button" :disabled="testing" @click="testActiveCluster">
              {{ testing ? '测试中...' : '连接测试' }}
            </button>
            <button class="btn btn-primary" type="button" :disabled="loading" @click="loadOverview(activeId, { force: true })">
              {{ loading ? '刷新中...' : '刷新概览' }}
            </button>
          </div>
        </section>

        <section class="kpi-grid">
          <article v-for="item in kpis" :key="item.label" class="kpi card" :class="item.tone">
            <div class="kpi-label">{{ item.label }}</div>
            <div class="kpi-value">{{ item.value }}</div>
            <div class="kpi-hint">{{ item.hint }}</div>
          </article>
        </section>

        <section v-if="testResult" class="alert" :class="testResult.ok ? 'alert-success' : 'alert-error'">
          {{ testResult.ok ? `${testResult.message}，识别为 ${modeLabel(testResult.detected_mode)}` : `连接失败: ${testResult.error || testResult.message}` }}
        </section>

        <section v-if="loading && !overview" class="card loading-card">
          <div class="spinner"></div>
          <span>正在加载 Redis 概览...</span>
        </section>

        <template v-else-if="overview">
          <section class="main-grid">
            <article class="card summary-card">
              <div class="card-head">
                <div>
                  <h3>集群总览</h3>
                  <p>聚合 Redis 单机或集群状态、节点分布与槽位覆盖情况</p>
                </div>
                <span class="card-meta">{{ summary?.known_nodes || 0 }} 节点</span>
              </div>

              <div class="summary-grid">
                <div class="summary-item">
                  <span>模式 / 角色</span>
                  <strong>{{ summary?.mode_label || '-' }}</strong>
                </div>
                <div class="summary-item">
                  <span>Master / Replica</span>
                  <strong>{{ summary?.master_count || 0 }} / {{ summary?.replica_count || 0 }}</strong>
                </div>
                <div class="summary-item">
                  <span>已连接节点</span>
                  <strong>{{ summary?.connected_nodes || 0 }}</strong>
                </div>
                <div class="summary-item">
                  <span>总 QPS</span>
                  <strong>{{ formatCompact(summary?.total_ops_per_sec) }}</strong>
                </div>
                <div class="summary-item">
                  <span>总内存</span>
                  <strong>{{ summary?.total_memory_human || '0 B' }}</strong>
                </div>
                <div class="summary-item">
                  <span>总连接数</span>
                  <strong>{{ formatCompact(summary?.total_clients) }}</strong>
                </div>
                <div class="summary-item">
                  <span>Redis 版本</span>
                  <strong>{{ versionsText }}</strong>
                </div>
              </div>

              <div v-if="summary?.mode === 'cluster'" class="slot-panel">
                <div class="slot-head">
                  <span>槽位覆盖</span>
                  <strong>{{ summary?.coverage_pct || 0 }}%</strong>
                </div>
                <div class="slot-bar">
                  <span class="slot-ok" :style="{ width: `${slotOkPct}%` }"></span>
                  <span class="slot-pfail" :style="{ width: `${slotPfailPct}%` }"></span>
                  <span class="slot-fail" :style="{ width: `${slotFailPct}%` }"></span>
                </div>
                <div class="slot-legend">
                  <span>OK {{ summary?.slots_ok || 0 }}</span>
                  <span>PFAIL {{ summary?.slots_pfail || 0 }}</span>
                  <span>FAIL {{ summary?.slots_fail || 0 }}</span>
                </div>
              </div>
            </article>

            <article class="card shard-card">
              <div class="card-head">
                <div>
                  <h3>{{ summary?.mode === 'cluster' ? '分片拓扑' : '实例视图' }}</h3>
                  <p>{{ summary?.mode === 'cluster' ? '每个 shard 的槽位范围和主从成员' : '单机模式下展示当前实例角色与基本信息' }}</p>
                </div>
                <span class="card-meta">{{ shards.length }} {{ summary?.mode === 'cluster' ? 'Shards' : 'Instances' }}</span>
              </div>

              <div v-if="shards.length" class="shard-list">
                <div v-for="shard in shards" :key="shard.id" class="shard-item">
                  <div class="shard-top">
                    <strong>{{ shard.id }}</strong>
                    <span>{{ shard.slot_count }} slots</span>
                  </div>
                  <div class="shard-ranges">{{ shard.slot_ranges.join(', ') || '未识别槽位' }}</div>
                  <div class="shard-members">
                    <span
                      v-for="node in shard.nodes"
                      :key="`${shard.id}-${node.id}-${node.role}`"
                      class="shard-member"
                      :class="node.role === 'master' ? 'master' : 'replica'"
                    >
                      {{ node.role === 'master' ? 'M' : 'R' }} {{ node.host }}:{{ node.port }}
                    </span>
                  </div>
                </div>
              </div>

              <div v-else class="empty-block">
                暂无 shard 信息
              </div>
            </article>
          </section>

          <section class="card table-card">
            <div class="card-head">
              <div>
                <h3>节点列表</h3>
                <p>按角色和风险优先级排序，优先暴露异常节点</p>
              </div>
              <div class="table-tools">
                <button
                  class="filter-pill"
                  :class="{ active: roleFilter === '' }"
                  type="button"
                  @click="roleFilter = ''"
                >
                  全部
                </button>
                <button
                  class="filter-pill"
                  :class="{ active: roleFilter === 'master' }"
                  type="button"
                  @click="roleFilter = 'master'"
                >
                  Master
                </button>
                <button
                  class="filter-pill"
                  :class="{ active: roleFilter === 'replica' }"
                  type="button"
                  @click="roleFilter = 'replica'"
                >
                  Replica
                </button>
              </div>
            </div>

            <div class="table-wrap">
              <table class="table">
                <thead>
                  <tr>
                    <th>角色</th>
                    <th>节点</th>
                    <th>状态</th>
                    <th>槽位</th>
                    <th>连接数</th>
                    <th>QPS</th>
                    <th>内存</th>
                    <th>命中率</th>
                    <th>版本</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!filteredNodes.length">
                    <td colspan="9" class="empty-cell">当前筛选条件下没有节点</td>
                  </tr>
                  <tr v-for="node in filteredNodes" :key="node.id" :class="node.status">
                    <td>
                      <span class="role-tag" :class="node.role">{{ node.role_text }}</span>
                    </td>
                    <td class="mono">
                      <div>{{ node.host }}:{{ node.port }}</div>
                      <small class="muted">{{ node.master_id ? `master=${node.master_id.slice(0, 8)}` : node.flags_text }}</small>
                    </td>
                    <td>
                      <span class="status-badge" :class="nodeStatusTone(node)">
                        {{ nodeStatusText(node) }}
                      </span>
                    </td>
                    <td>{{ node.slot_count || '-' }}</td>
                    <td>{{ formatCompact(node.connected_clients) }}</td>
                    <td>{{ formatCompact(node.ops_per_sec) }}</td>
                    <td>{{ node.used_memory_human || '-' }}</td>
                    <td>{{ node.keyspace_hit_rate == null ? '-' : `${node.keyspace_hit_rate}%` }}</td>
                    <td>{{ node.redis_version || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>
      </template>
    </div>

    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal">
        <div class="modal-title">{{ editingId ? '编辑 Redis 连接' : '添加 Redis 连接' }}</div>
        <div class="form-row">
          <div class="form-group grow">
            <label class="form-label">连接名称 *</label>
            <input v-model.trim="form.name" class="form-input" placeholder="生产 Redis / Redis Cluster" />
          </div>
          <div class="form-group narrow">
            <label class="form-label">环境</label>
            <select v-model="form.env" class="form-input">
              <option value="">无</option>
              <option value="prod">PROD</option>
              <option value="uat">UAT</option>
              <option value="sit">SIT</option>
              <option value="dev">DEV</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group grow">
            <label class="form-label">连接模式</label>
            <select v-model="form.mode" class="form-input">
              <option value="auto">自动识别</option>
              <option value="standalone">单机</option>
              <option value="cluster">集群</option>
            </select>
          </div>
          <div class="form-group grow">
            <label class="form-label">节点说明</label>
            <div class="form-readonly">
              {{ form.mode === 'cluster' ? '至少填写 1 个集群节点，系统按 Cluster 方式连接' : form.mode === 'standalone' ? '填写任意一个单机节点地址，系统按单机方式连接' : '默认先探测 cluster_enabled，再自动选择单机或集群连接方式' }}
            </div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">{{ form.mode === 'standalone' ? '节点地址 *' : '启动节点 *' }}</label>
          <textarea
            v-model="form.startup_nodes_text"
            class="form-textarea"
            rows="4"
            placeholder="10.0.0.11:6379&#10;10.0.0.12:6379&#10;10.0.0.13:6379"
          ></textarea>
          <div class="form-hint">支持换行、逗号分隔，也支持 `redis://host:port`。单机模式下填 1 个即可。</div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">用户名</label>
            <input v-model.trim="form.username" class="form-input" placeholder="默认可留空" />
          </div>
          <div class="form-group">
            <label class="form-label">密码</label>
            <input v-model="form.password" class="form-input" type="password" :placeholder="editingId ? '留空表示不修改' : '可留空'" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group narrow">
            <label class="form-label">TLS</label>
            <select v-model="form.tls" class="form-input">
              <option :value="false">关闭</option>
              <option :value="true">开启</option>
            </select>
          </div>
          <div class="form-group grow">
            <label class="form-label">标识颜色</label>
            <input v-model.trim="form.color" class="form-input mono" placeholder="#dc2626" />
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">备注</label>
          <input v-model.trim="form.note" class="form-input" placeholder="如：订单缓存集群、核心链路" />
        </div>

        <div v-if="modalTestResult" class="alert" :class="modalTestResult.ok ? 'alert-success' : 'alert-error'">
          {{ modalTestResult.ok ? `${modalTestResult.message}，识别为 ${modeLabel(modalTestResult.detected_mode)}${modalTestResult.cluster_state ? `，状态 ${modalTestResult.cluster_state}` : ''}` : `连接失败: ${modalTestResult.error || modalTestResult.message}` }}
        </div>

        <div class="modal-footer">
          <button class="btn btn-outline" type="button" :disabled="saving || testingConfig" @click="testFormConfig">
            {{ testingConfig ? '测试中...' : '测试配置' }}
          </button>
          <div class="footer-actions">
            <button class="btn btn-outline" type="button" @click="closeModal">取消</button>
            <button class="btn btn-primary" type="button" :disabled="saving" @click="submitCluster">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/index.js'

const clusters = ref([])
const overviewCache = ref({})
const activeId = ref('')
const loading = ref(false)
const testing = ref(false)
const testResult = ref(null)
const roleFilter = ref('')

const showModal = ref(false)
const editingId = ref('')
const saving = ref(false)
const testingConfig = ref(false)
const modalTestResult = ref(null)
const form = ref(makeEmptyForm())

const activeCluster = computed(() => clusters.value.find((item) => item.id === activeId.value) || null)
const overview = computed(() => overviewCache.value[activeId.value] || null)
const summary = computed(() => overview.value?.summary || null)
const nodes = computed(() => overview.value?.nodes || [])
const shards = computed(() => overview.value?.shards || [])
const versionsText = computed(() => {
  const versions = summary.value?.versions || []
  return versions.length ? versions.join(' / ') : '-'
})

const summaryTone = computed(() => summary.value?.state_tone || 'warn')
const stateText = computed(() => {
  const mode = summary.value?.mode
  const state = summary.value?.cluster_state || 'unknown'
  if (mode === 'standalone') {
    return state === 'ok' ? 'Standalone OK' : state.toUpperCase()
  }
  return state === 'ok' ? 'Cluster OK' : state
})
const slotOkPct = computed(() => ratioPct(summary.value?.slots_ok))
const slotPfailPct = computed(() => ratioPct(summary.value?.slots_pfail))
const slotFailPct = computed(() => ratioPct(summary.value?.slots_fail))

const kpis = computed(() => [
  {
    label: 'Shards',
    value: summary.value?.shard_count ?? 0,
    hint: `Master ${summary.value?.master_count ?? 0} / Replica ${summary.value?.replica_count ?? 0}`,
    tone: 'info',
  },
  {
    label: '节点健康',
    value: `${summary.value?.connected_nodes ?? 0}/${summary.value?.known_nodes ?? 0}`,
    hint: summary.value?.unhealthy_nodes ? `${summary.value.unhealthy_nodes} 个节点需关注` : '当前未发现离线节点',
    tone: summary.value?.unhealthy_nodes ? 'warn' : 'ok',
  },
  {
    label: '槽位覆盖',
    value: `${summary.value?.coverage_pct ?? 0}%`,
    hint: `OK ${summary.value?.slots_ok ?? 0} / FAIL ${summary.value?.slots_fail ?? 0}`,
    tone: (summary.value?.slots_fail ?? 0) > 0 ? 'danger' : (summary.value?.slots_pfail ?? 0) > 0 ? 'warn' : 'ok',
  },
  {
    label: '总吞吐',
    value: formatCompact(summary.value?.total_ops_per_sec),
    hint: `连接 ${formatCompact(summary.value?.total_clients)} / 内存 ${summary.value?.total_memory_human || '0 B'}`,
    tone: 'info',
  },
])

const filteredNodes = computed(() => {
  const list = roleFilter.value
    ? nodes.value.filter((node) => node.role === roleFilter.value)
    : nodes.value

  return [...list].sort((left, right) => {
    const toneRank = toneWeight(nodeStatusTone(left)) - toneWeight(nodeStatusTone(right))
    if (toneRank !== 0) return toneRank
    if (left.role !== right.role) return left.role === 'master' ? -1 : 1
    return `${left.host}:${left.port}`.localeCompare(`${right.host}:${right.port}`)
  })
})

function makeEmptyForm() {
  return {
    name: '',
    startup_nodes_text: '',
    mode: 'auto',
    username: '',
    password: '',
    tls: false,
    env: '',
    note: '',
    color: '#dc2626',
  }
}

function normalizeNodesInput(text) {
  return String(text || '')
    .replace(/\r/g, '\n')
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function buildPayload() {
  return {
    name: form.value.name.trim(),
    startup_nodes: normalizeNodesInput(form.value.startup_nodes_text),
    mode: form.value.mode || 'auto',
    username: form.value.username.trim(),
    password: form.value.password,
    tls: Boolean(form.value.tls),
    env: form.value.env,
    note: form.value.note.trim(),
    color: form.value.color.trim() || '#dc2626',
  }
}

function ratioPct(value) {
  const total = 16384
  const amount = Number(value || 0)
  return total > 0 ? Math.round((amount / total) * 1000) / 10 : 0
}

function modeLabel(mode) {
  return {
    auto: '自动识别',
    standalone: '单机',
    cluster: '集群',
  }[mode] || mode || '-'
}

function formatCompact(value) {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return '-'
  if (Math.abs(num) >= 1e9) return `${(num / 1e9).toFixed(1)}G`
  if (Math.abs(num) >= 1e6) return `${(num / 1e6).toFixed(1)}M`
  if (Math.abs(num) >= 1e3) return `${(num / 1e3).toFixed(1)}K`
  return `${Math.round(num)}`
}

function toneWeight(tone) {
  return { danger: 0, warn: 1, ok: 2, info: 3 }[tone] ?? 9
}

function nodeStatusTone(node) {
  if (!node.connected) return 'danger'
  if (node.probe_error || node.status === 'warn') return 'warn'
  if (node.master_link_status && node.master_link_status !== 'up') return 'warn'
  return 'ok'
}

function nodeStatusText(node) {
  if (!node.connected) return 'OFFLINE'
  if (node.probe_error) return 'DEGRADED'
  if (node.master_link_status && node.master_link_status !== 'up') return 'REPL-SYNC'
  return 'ONLINE'
}

function clusterHealthTone(clusterId) {
  const item = overviewCache.value[clusterId]?.summary
  return item?.state_tone || 'warn'
}

async function loadClusters({ preserveActive = true } = {}) {
  const result = await api.redisClusters().catch(() => [])
  clusters.value = Array.isArray(result) ? result : []
  if (!clusters.value.length) {
    activeId.value = ''
    return
  }
  const existing = preserveActive ? clusters.value.find((item) => item.id === activeId.value) : null
  activeId.value = existing?.id || clusters.value[0].id
}

async function loadOverview(clusterId, { force = false } = {}) {
  if (!clusterId) return
  if (!force && overviewCache.value[clusterId]) return overviewCache.value[clusterId]
  loading.value = true
  try {
    const result = await api.redisOverview(clusterId)
    overviewCache.value = { ...overviewCache.value, [clusterId]: result }
    return result
  } finally {
    loading.value = false
  }
}

async function switchCluster(clusterId) {
  activeId.value = clusterId
  roleFilter.value = ''
  testResult.value = null
  await loadOverview(clusterId)
}

async function testActiveCluster() {
  if (!activeId.value) return
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await api.redisTestCluster(activeId.value)
  } finally {
    testing.value = false
  }
}

function openClusterModal(clusterId = '') {
  editingId.value = clusterId
  modalTestResult.value = null
  if (clusterId) {
    const cluster = clusters.value.find((item) => item.id === clusterId)
    form.value = {
      name: cluster?.name || '',
      startup_nodes_text: (cluster?.startup_nodes || []).join('\n'),
      mode: cluster?.mode || 'auto',
      username: cluster?.username || '',
      password: '',
      tls: Boolean(cluster?.tls),
      env: cluster?.env || '',
      note: cluster?.note || '',
      color: cluster?.color || '#dc2626',
    }
  } else {
    form.value = makeEmptyForm()
  }
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingId.value = ''
  modalTestResult.value = null
}

async function testFormConfig() {
  const payload = buildPayload()
  if (!payload.name || !payload.startup_nodes.length) return
  testingConfig.value = true
  modalTestResult.value = null
  try {
    modalTestResult.value = await api.redisTestConfig({
      ...payload,
      cluster_id: editingId.value || '',
    })
  } finally {
    testingConfig.value = false
  }
}

async function submitCluster() {
  const payload = buildPayload()
  if (!payload.name || !payload.startup_nodes.length) return
  saving.value = true
  try {
    if (editingId.value) {
      await api.redisUpdateCluster(editingId.value, payload)
    } else {
      const created = await api.redisAddCluster(payload)
      activeId.value = created.id
    }
    overviewCache.value = {}
    await loadClusters()
    if (activeId.value) await loadOverview(activeId.value, { force: true })
    closeModal()
  } finally {
    saving.value = false
  }
}

async function removeCluster(clusterId) {
  if (!window.confirm('确认删除该 Redis 集群配置？')) return
  await api.redisDeleteCluster(clusterId)
  delete overviewCache.value[clusterId]
  await loadClusters({ preserveActive: false })
  if (activeId.value) await loadOverview(activeId.value, { force: true })
}

onMounted(async () => {
  await loadClusters()
  if (activeId.value) await loadOverview(activeId.value, { force: true })
})
</script>

<style scoped>
.redis-view {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(circle at top right, rgba(220, 38, 38, 0.07), transparent 30%),
    radial-gradient(circle at top left, rgba(251, 146, 60, 0.08), transparent 22%),
    var(--bg-base);
}

.cluster-bar {
  height: 46px;
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.92);
  overflow-x: auto;
}

.cb-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  border-right: 1px solid var(--border);
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}

.cb-logo-icon {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff;
  font-size: 13px;
}

.cluster-tab,
.cb-add {
  border: none;
  background: transparent;
  cursor: pointer;
}

.cluster-tab {
  min-width: 156px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-right: 1px solid var(--border);
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
}

.cluster-tab.active {
  background: rgba(255, 255, 255, 0.84);
  border-bottom-color: #dc2626;
  color: var(--text-primary);
}

.ct-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ct-dot.ok {
  background: var(--success);
}

.ct-dot.warn {
  background: #f59e0b;
}

.ct-dot.danger {
  background: var(--error);
}

.ct-name {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 6px;
}

.ct-env {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
}

.env-prod {
  color: var(--error);
}

.env-uat {
  color: #b45309;
}

.env-sit {
  color: var(--accent);
}

.env-dev {
  color: #7c3aed;
}

.ct-close {
  opacity: 0;
  color: var(--text-muted);
}

.cluster-tab:hover .ct-close {
  opacity: 1;
}

.cb-add {
  padding: 0 16px;
  font-size: 22px;
  color: var(--text-muted);
}

.cb-add:hover {
  color: #dc2626;
}

.page-shell {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 20px;
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.05);
}

.welcome {
  min-height: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  text-align: center;
}

.welcome-mark {
  width: 72px;
  height: 72px;
  border-radius: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  font-weight: 800;
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff;
  box-shadow: 0 20px 38px rgba(239, 68, 68, 0.2);
}

.welcome h1 {
  font-size: 28px;
  color: var(--text-primary);
}

.welcome p {
  max-width: 560px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 22px;
  background:
    linear-gradient(135deg, rgba(254, 242, 242, 0.95), rgba(255, 255, 255, 0.98)),
    #fff;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  font-size: 12px;
  font-weight: 700;
}

.hero-badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
}

.hero-title-row {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-title-row h1 {
  font-size: 30px;
  color: var(--text-primary);
}

.hero-subtitle {
  margin-top: 10px;
  max-width: 760px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.state-pill,
.card-meta,
.filter-pill,
.role-tag,
.status-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.state-pill {
  height: 30px;
  padding: 0 12px;
}

.state-pill.ok,
.status-badge.ok,
.kpi.ok {
  background: rgba(34, 197, 94, 0.12);
  color: var(--success);
}

.state-pill.warn,
.status-badge.warn,
.kpi.warn {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.state-pill.danger,
.status-badge.danger,
.kpi.danger {
  background: rgba(239, 68, 68, 0.12);
  color: var(--error);
}

.kpi.info {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98));
  color: inherit;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.kpi {
  padding: 18px;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.kpi-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.kpi-value {
  margin-top: 8px;
  font-size: 30px;
  line-height: 1.1;
  font-weight: 800;
  color: var(--text-primary);
}

.kpi-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.alert {
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 600;
}

.alert-success {
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  color: var(--success);
}

.alert-error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: var(--error);
}

.loading-card {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(148, 163, 184, 0.3);
  border-top-color: #ef4444;
  border-radius: 50%;
  animation: spin .7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  gap: 16px;
}

.summary-card,
.shard-card,
.table-card {
  padding: 18px;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.card-head h3 {
  font-size: 16px;
  color: var(--text-primary);
}

.card-head p {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.card-meta {
  height: 28px;
  padding: 0 10px;
  background: rgba(148, 163, 184, 0.12);
  color: var(--text-secondary);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.summary-item {
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.summary-item span {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
}

.summary-item strong {
  display: block;
  margin-top: 8px;
  font-size: 22px;
  color: var(--text-primary);
}

.slot-panel {
  margin-top: 18px;
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(253, 186, 116, 0.2);
}

.slot-head,
.slot-legend,
.shard-top,
.table-tools,
.modal-footer,
.footer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.slot-head strong {
  font-size: 22px;
  color: var(--text-primary);
}

.slot-bar {
  margin-top: 12px;
  height: 12px;
  border-radius: 999px;
  overflow: hidden;
  display: flex;
  background: rgba(226, 232, 240, 0.9);
}

.slot-bar span {
  height: 100%;
}

.slot-ok {
  background: linear-gradient(90deg, #ef4444, #f97316);
}

.slot-pfail {
  background: #f59e0b;
}

.slot-fail {
  background: #b91c1c;
}

.slot-legend {
  margin-top: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.shard-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.shard-item {
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.shard-top strong {
  color: var(--text-primary);
}

.shard-top span,
.shard-ranges {
  color: var(--text-secondary);
  font-size: 12px;
}

.shard-ranges {
  margin-top: 6px;
  line-height: 1.6;
}

.shard-members {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.shard-member {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.shard-member.master,
.role-tag.master {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.shard-member.replica,
.role-tag.replica {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
}

.table-tools {
  flex-wrap: wrap;
}

.filter-pill {
  height: 30px;
  padding: 0 12px;
  border: none;
  background: rgba(226, 232, 240, 0.7);
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-pill.active {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.table-wrap {
  overflow: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th,
.table td {
  padding: 12px 10px;
  border-bottom: 1px solid var(--border-light);
  vertical-align: middle;
}

.table th {
  text-align: left;
  color: var(--text-secondary);
  font-size: 12px;
}

.table tbody tr:hover td {
  background: rgba(148, 163, 184, 0.04);
}

.table tbody tr.warn td {
  background: rgba(245, 158, 11, 0.04);
}

.table tbody tr.fail td {
  background: rgba(239, 68, 68, 0.05);
}

.empty-cell,
.empty-block {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
}

.status-badge {
  height: 26px;
  padding: 0 10px;
}

.mono {
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.muted {
  color: var(--text-secondary);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 40px;
  padding: 0 16px;
  border-radius: 12px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}

.btn-primary {
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff;
  box-shadow: 0 12px 28px rgba(239, 68, 68, 0.18);
}

.btn-outline {
  background: rgba(255, 255, 255, 0.85);
  color: var(--text-primary);
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 1000;
}

.modal {
  width: 560px;
  max-width: 100%;
  max-height: 90vh;
  overflow: auto;
  padding: 22px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 28px 60px rgba(15, 23, 42, 0.18);
}

.modal-title {
  font-size: 18px;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-group {
  margin-bottom: 14px;
}

.form-group.grow {
  flex: 1;
}

.form-group.narrow {
  width: 120px;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
}

.form-input,
.form-textarea {
  width: 100%;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.9);
  color: var(--text-primary);
  font-size: 13px;
  padding: 10px 12px;
  outline: none;
}

.form-textarea {
  resize: vertical;
  min-height: 110px;
}

.form-input:focus,
.form-textarea:focus {
  border-color: rgba(239, 68, 68, 0.45);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.08);
}

.form-readonly {
  min-height: 44px;
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.9);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 1180px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .main-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 860px) {
  .page-shell {
    padding: 12px;
  }

  .hero {
    flex-direction: column;
  }

  .hero-actions,
  .summary-grid,
  .form-row,
  .kpi-grid {
    grid-template-columns: 1fr;
  }

  .hero-actions,
  .form-row {
    display: flex;
    flex-direction: column;
  }

  .form-group.narrow {
    width: auto;
  }
}
</style>
