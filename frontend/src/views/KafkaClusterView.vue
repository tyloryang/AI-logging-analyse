<template>
  <div class="kafka-page">
    <!-- ── 左侧连接列表 ─────────────────────────────────── -->
    <aside class="conn-panel">
      <div class="conn-head">
        <span class="conn-title">Kafka 连接</span>
        <button class="btn btn-primary btn-sm" @click="openEditor()">＋ 新增</button>
      </div>
      <div class="conn-list">
        <div
          v-for="c in clusters" :key="c.id"
          class="conn-item" :class="{ active: c.id === activeId }"
          @click="selectCluster(c.id)"
        >
          <span class="conn-dot" :style="{ background: c.color }"></span>
          <div class="conn-info">
            <div class="conn-name">{{ c.name }}</div>
            <div class="conn-addr">{{ (c.bootstrap_servers || [])[0] }}<span v-if="(c.bootstrap_servers||[]).length > 1"> +{{ c.bootstrap_servers.length - 1 }}</span></div>
          </div>
          <span v-if="c.env" class="conn-env">{{ c.env }}</span>
        </div>
        <div v-if="!clusters.length" class="conn-empty">
          暂无连接，点击「新增」添加 Kafka 集群<br/>
          <small>支持 Kafka 0.10+（含 2.12-2.8.2）</small>
        </div>
      </div>
    </aside>

    <!-- ── 主区域 ──────────────────────────────────────── -->
    <main class="main-panel">
      <div v-if="!activeId" class="empty-state full">
        <span class="icon">📨</span>
        <p>选择或新增一个 Kafka 连接开始管理</p>
      </div>

      <template v-else>
        <!-- 顶栏 -->
        <div class="topbar">
          <div class="topbar-left">
            <h1>{{ activeCluster?.name }}</h1>
            <span v-if="overview?.summary?.broker_version" class="badge badge-info">{{ overview.summary.broker_version }}</span>
            <span class="state-pill" :class="'tone-' + (overview?.summary?.state_tone || 'info')">
              {{ overview ? (overview.summary.state_tone === 'ok' ? '健康' : overview.summary.state_tone === 'warn' ? '副本欠同步' : '异常') : '...' }}
            </span>
          </div>
          <div class="topbar-right">
            <button class="btn btn-outline btn-sm" @click="testActive">测试连接</button>
            <button class="btn btn-outline btn-sm" @click="openEditor(activeCluster)">编辑</button>
            <button class="btn btn-outline btn-sm danger" @click="removeCluster">删除</button>
            <button class="btn btn-outline btn-sm" @click="refreshAll">⟳ 刷新</button>
          </div>
        </div>
        <div v-if="testResult" class="test-banner" :class="testResult.ok ? 'ok' : 'fail'">
          {{ testResult.message }}<span v-if="testResult.error">：{{ testResult.error }}</span>
          <button class="close-x" @click="testResult = null">×</button>
        </div>

        <!-- Tab 切换 -->
        <div class="tabs">
          <button v-for="t in TABS" :key="t.id" class="tab" :class="{ active: tab === t.id }" @click="switchTab(t.id)">
            {{ t.label }}
          </button>
        </div>

        <div v-if="loadError" class="empty-state" style="padding:40px">
          <span class="icon">⚠️</span><p>{{ loadError }}</p>
          <button class="btn btn-outline" @click="refreshAll">重试</button>
        </div>

        <!-- ══ 集群概览 ══ -->
        <div v-else-if="tab === 'overview'" class="pane">
          <div v-if="loading" class="loading-row"><div class="spinner"></div><span>加载集群元数据...</span></div>
          <template v-else-if="overview">
            <div class="kpi-row">
              <div class="kpi"><span>Broker</span><strong>{{ overview.summary.broker_count }}</strong></div>
              <div class="kpi"><span>Topic</span><strong>{{ overview.summary.topic_count }}</strong></div>
              <div class="kpi"><span>分区总数</span><strong>{{ overview.summary.partition_count }}</strong></div>
              <div class="kpi"><span>消费组</span><strong>{{ overview.summary.consumer_group_count }}</strong></div>
              <div class="kpi" :class="{ 'tone-warn': overview.summary.under_replicated_partitions > 0 }">
                <span>欠同步分区</span><strong>{{ overview.summary.under_replicated_partitions }}</strong>
              </div>
              <div class="kpi"><span>内部 Topic</span><strong>{{ overview.summary.internal_topic_count }}</strong></div>
            </div>
            <div class="section">
              <div class="sec-title">Broker 节点</div>
              <table class="tbl">
                <thead><tr><th>ID</th><th>地址</th><th>机架</th><th>角色</th></tr></thead>
                <tbody>
                  <tr v-for="b in overview.brokers" :key="b.id">
                    <td class="mono">{{ b.id }}</td>
                    <td class="mono">{{ b.host }}:{{ b.port }}</td>
                    <td>{{ b.rack || '-' }}</td>
                    <td><span v-if="b.is_controller" class="badge badge-warn">Controller</span><span v-else class="muted">Broker</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="section">
              <div class="sec-title">集群信息</div>
              <div class="kv-grid">
                <span class="k">Cluster ID</span><span class="v mono">{{ overview.summary.cluster_id || '-' }}</span>
                <span class="k">Controller</span><span class="v mono">{{ overview.summary.controller_id }}</span>
                <span class="k">协议版本</span><span class="v mono">{{ overview.summary.broker_version || '未知' }}</span>
                <span class="k">Bootstrap</span><span class="v mono">{{ (activeCluster?.bootstrap_servers || []).join(', ') }}</span>
              </div>
            </div>
          </template>
        </div>

        <!-- ══ Topic 管理 ══ -->
        <div v-else-if="tab === 'topics'" class="pane">
          <div class="pane-toolbar">
            <label class="chk"><input type="checkbox" v-model="includeInternal" @change="loadTopics"/> 显示内部 Topic</label>
            <button class="btn btn-primary btn-sm" @click="createVisible = true">＋ 创建 Topic</button>
          </div>
          <div v-if="topicsLoading" class="loading-row"><div class="spinner"></div><span>加载 Topic...</span></div>
          <template v-else>
            <table class="tbl">
              <thead><tr><th>Topic</th><th>分区</th><th>副本因子</th><th>消息总量</th><th>欠同步</th><th></th></tr></thead>
              <tbody>
                <tr v-for="t in topics" :key="t.name" :class="{ rowsel: t.name === selectedTopic }">
                  <td class="mono clickable" @click="showTopicDetail(t.name)">{{ t.name }}<span v-if="t.internal" class="badge badge-info" style="margin-left:6px">内部</span></td>
                  <td>{{ t.partitions }}</td>
                  <td>{{ t.replication_factor }}</td>
                  <td>{{ t.message_count.toLocaleString() }}</td>
                  <td><span :class="t.under_replicated ? 'val-err' : 'muted'">{{ t.under_replicated }}</span></td>
                  <td>
                    <button class="btn btn-outline btn-xs" @click="showTopicDetail(t.name)">详情</button>
                    <button class="btn btn-outline btn-xs danger" @click="removeTopic(t.name)">删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-if="!topics.length" class="empty-state" style="padding:32px"><p>暂无 Topic</p></div>

            <!-- Topic 详情 -->
            <div v-if="topicDetail" class="section">
              <div class="sec-title">
                {{ topicDetail.name }} — 分区明细（共 {{ topicDetail.message_count.toLocaleString() }} 条消息）
                <button class="close-x" @click="topicDetail = null">×</button>
              </div>
              <table class="tbl">
                <thead><tr><th>分区</th><th>Leader</th><th>Replicas</th><th>ISR</th><th>End Offset</th><th>状态</th></tr></thead>
                <tbody>
                  <tr v-for="p in topicDetail.partitions" :key="p.partition">
                    <td>{{ p.partition }}</td>
                    <td class="mono">{{ p.leader }}</td>
                    <td class="mono">{{ p.replicas.join(',') }}</td>
                    <td class="mono">{{ p.isr.join(',') }}</td>
                    <td>{{ p.end_offset.toLocaleString() }}</td>
                    <td><span :class="p.under_replicated ? 'val-err' : 'val-ok'">{{ p.under_replicated ? '欠同步' : '正常' }}</span></td>
                  </tr>
                </tbody>
              </table>
              <template v-if="topicDetail.configs?.length">
                <div class="sec-title" style="margin-top:14px">非默认配置</div>
                <div class="kv-grid">
                  <template v-for="c in topicDetail.configs" :key="c.name">
                    <span class="k mono">{{ c.name }}</span><span class="v mono">{{ c.value }}</span>
                  </template>
                </div>
              </template>

              <!-- 消息浏览 -->
              <div class="sec-title" style="margin-top:16px">消息浏览</div>
              <div class="msg-toolbar">
                <select v-model.number="msgQuery.partition" class="msg-sel">
                  <option :value="-1">全部分区</option>
                  <option v-for="p in topicDetail.partitions" :key="p.partition" :value="p.partition">分区 {{ p.partition }}</option>
                </select>
                <select v-model="msgQuery.direction" class="msg-sel">
                  <option value="latest">最新消息</option>
                  <option value="earliest">最早消息</option>
                  <option value="offset" :disabled="msgQuery.partition < 0">指定 Offset</option>
                </select>
                <input v-if="msgQuery.direction === 'offset'" v-model.number="msgQuery.offset" type="number" min="0"
                       class="msg-sel" style="width:120px" placeholder="起始 offset"/>
                <select v-model.number="msgQuery.limit" class="msg-sel">
                  <option :value="20">20 条</option><option :value="50">50 条</option>
                  <option :value="100">100 条</option><option :value="200">200 条</option>
                </select>
                <button class="btn btn-primary btn-sm" :disabled="msgLoading" @click="loadMessages">
                  {{ msgLoading ? '抓取中...' : '抓取消息' }}
                </button>
                <span v-if="msgResult" class="muted" style="font-size:11px">共 {{ msgResult.count }} 条</span>
              </div>
              <div v-if="msgError" class="test-banner fail">{{ msgError }}</div>
              <template v-if="msgResult">
                <table class="tbl" v-if="msgResult.messages.length">
                  <thead><tr><th style="width:54px">分区</th><th style="width:80px">Offset</th><th style="width:150px">时间</th><th style="width:110px">Key</th><th>Value</th><th style="width:64px">大小</th></tr></thead>
                  <tbody>
                    <template v-for="(m, mi) in msgResult.messages" :key="m.partition + '-' + m.offset">
                      <tr class="msg-row" @click="expandedMsg = expandedMsg === mi ? -1 : mi">
                        <td>{{ m.partition }}</td>
                        <td class="mono">{{ m.offset }}</td>
                        <td class="mono" style="font-size:11px">{{ fmtMsgTime(m.timestamp) }}</td>
                        <td class="mono ellip" :title="m.key">{{ m.key || '-' }}</td>
                        <td class="mono ellip">
                          <span v-if="m.value_format === 'json'" class="badge badge-info" style="margin-right:6px">JSON</span>
                          <span v-else-if="m.value_format === 'base64'" class="badge badge-warn" style="margin-right:6px">二进制</span>
                          {{ m.value.slice(0, 160) }}
                        </td>
                        <td class="muted" style="font-size:11px">{{ fmtBytes(m.size_bytes) }}</td>
                      </tr>
                      <tr v-if="expandedMsg === mi">
                        <td colspan="6" class="msg-expand">
                          <div v-if="m.headers?.length" class="msg-headers">
                            Headers：<span v-for="h in m.headers" :key="h.key" class="badge badge-info" style="margin-right:6px">{{ h.key }}={{ h.value }}</span>
                          </div>
                          <pre class="msg-pre">{{ prettyValue(m) }}</pre>
                          <div v-if="m.value_truncated" class="muted" style="font-size:11px">⚠ 消息超过 64KB，已截断展示</div>
                        </td>
                      </tr>
                    </template>
                  </tbody>
                </table>
                <div v-else class="empty-state" style="padding:20px"><p>该范围内没有消息</p></div>
              </template>
            </div>
          </template>
        </div>

        <!-- ══ 消费组 ══ -->
        <div v-else-if="tab === 'groups'" class="pane">
          <div v-if="groupsLoading" class="loading-row"><div class="spinner"></div><span>加载消费组...</span></div>
          <template v-else>
            <table class="tbl">
              <thead><tr><th>消费组</th><th>状态</th><th>成员数</th><th></th></tr></thead>
              <tbody>
                <tr v-for="g in groups" :key="g.group_id">
                  <td class="mono clickable" @click="showLag(g.group_id)">{{ g.group_id }}</td>
                  <td><span class="badge" :class="g.state === 'Stable' ? 'badge-ok' : 'badge-warn'">{{ g.state || '未知' }}</span></td>
                  <td>{{ g.member_count }}</td>
                  <td><button class="btn btn-outline btn-xs" @click="showLag(g.group_id)">Lag 详情</button></td>
                </tr>
              </tbody>
            </table>
            <div v-if="!groups.length" class="empty-state" style="padding:32px"><p>暂无消费组</p></div>

            <div v-if="lagDetail" class="section">
              <div class="sec-title">
                {{ lagDetail.group_id }} — 消费延迟
                <span class="badge" :class="lagDetail.total_lag > 0 ? 'badge-warn' : 'badge-ok'" style="margin-left:8px">总 Lag: {{ lagDetail.total_lag.toLocaleString() }}</span>
                <button class="close-x" @click="lagDetail = null">×</button>
              </div>
              <table class="tbl">
                <thead><tr><th>Topic</th><th>分区</th><th>已提交 Offset</th><th>End Offset</th><th>Lag</th></tr></thead>
                <tbody>
                  <tr v-for="p in lagDetail.partitions" :key="p.topic + p.partition">
                    <td class="mono">{{ p.topic }}</td>
                    <td>{{ p.partition }}</td>
                    <td>{{ p.committed.toLocaleString() }}</td>
                    <td>{{ p.end_offset.toLocaleString() }}</td>
                    <td><span :class="p.lag > 0 ? 'val-warn' : 'val-ok'">{{ p.lag.toLocaleString() }}</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </template>
    </main>

    <!-- ── 连接编辑弹窗 ────────────────────────────────── -->
    <div v-if="editorVisible" class="modal-mask" @click.self="editorVisible = false">
      <div class="modal">
        <h3>{{ form.id ? '编辑' : '新增' }} Kafka 连接</h3>
        <div class="form-grid">
          <label>连接名称 *</label>
          <input v-model="form.name" placeholder="如：生产 Kafka 集群"/>
          <label>Bootstrap Servers *</label>
          <textarea v-model="form.serversText" rows="3" placeholder="host1:9092&#10;host2:9092（每行一个或逗号分隔）"></textarea>
          <label>安全协议</label>
          <select v-model="form.security_protocol">
            <option>PLAINTEXT</option><option>SASL_PLAINTEXT</option><option>SSL</option><option>SASL_SSL</option>
          </select>
          <template v-if="form.security_protocol.includes('SASL')">
            <label>SASL 机制</label>
            <select v-model="form.sasl_mechanism">
              <option>PLAIN</option><option>SCRAM-SHA-256</option><option>SCRAM-SHA-512</option>
            </select>
            <label>用户名</label>
            <input v-model="form.username"/>
            <label>密码</label>
            <input v-model="form.password" type="password" :placeholder="form.id ? '留空则不修改' : ''"/>
          </template>
          <label>环境标签</label>
          <input v-model="form.env" placeholder="prod / staging / dev"/>
          <label>备注</label>
          <input v-model="form.note"/>
        </div>
        <div v-if="editorTest" class="test-banner" :class="editorTest.ok ? 'ok' : 'fail'" style="margin-top:10px">
          {{ editorTest.message }}<span v-if="editorTest.error">：{{ editorTest.error }}</span>
        </div>
        <div class="modal-actions">
          <button class="btn btn-outline" :disabled="editorTesting" @click="testEditorConfig">{{ editorTesting ? '测试中...' : '测试连接' }}</button>
          <span style="flex:1"></span>
          <button class="btn btn-outline" @click="editorVisible = false">取消</button>
          <button class="btn btn-primary" @click="saveCluster">保存</button>
        </div>
      </div>
    </div>

    <!-- ── 创建 Topic 弹窗 ─────────────────────────────── -->
    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal">
        <h3>创建 Topic</h3>
        <div class="form-grid">
          <label>Topic 名称 *</label>
          <input v-model="topicForm.name" placeholder="如：order-events"/>
          <label>分区数</label>
          <input v-model.number="topicForm.partitions" type="number" min="1" max="512"/>
          <label>副本因子</label>
          <input v-model.number="topicForm.replication_factor" type="number" min="1" max="16"/>
        </div>
        <div v-if="createError" class="test-banner fail" style="margin-top:10px">{{ createError }}</div>
        <div class="modal-actions">
          <button class="btn btn-outline" @click="createVisible = false">取消</button>
          <button class="btn btn-primary" @click="submitCreateTopic">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const TABS = [
  { id: 'overview', label: '集群概览' },
  { id: 'topics',   label: 'Topic 管理' },
  { id: 'groups',   label: '消费组' },
]

const clusters   = ref([])
const activeId   = ref('')
const tab        = ref('overview')
const loading    = ref(false)
const loadError  = ref('')
const overview   = ref(null)
const testResult = ref(null)

const topics        = ref([])
const topicsLoading = ref(false)
const includeInternal = ref(false)
const selectedTopic = ref('')
const topicDetail   = ref(null)

const groups        = ref([])
const groupsLoading = ref(false)
const lagDetail     = ref(null)

const activeCluster = computed(() => clusters.value.find(c => c.id === activeId.value))

// ── 连接管理 ──────────────────────────────────────────────────────────────
async function loadClusters() {
  try { clusters.value = await api.kafkaClusters() } catch { clusters.value = [] }
  if (!activeId.value && clusters.value.length) selectCluster(clusters.value[0].id)
}

function selectCluster(id) {
  activeId.value = id
  overview.value = null
  topicDetail.value = null
  lagDetail.value = null
  testResult.value = null
  switchTab('overview', true)
}

async function loadOverview() {
  loading.value = true
  loadError.value = ''
  try { overview.value = await api.kafkaOverview(activeId.value) }
  catch (e) { loadError.value = `集群元数据加载失败：${e}`; overview.value = null }
  finally { loading.value = false }
}

function switchTab(id, force = false) {
  if (tab.value === id && !force) return
  tab.value = id
  loadError.value = ''
  if (id === 'overview') loadOverview()
  else if (id === 'topics') loadTopics()
  else if (id === 'groups') loadGroups()
}

function refreshAll() { switchTab(tab.value, true) }

async function testActive() {
  testResult.value = { ok: true, message: '测试中...' }
  try { testResult.value = await api.kafkaTestCluster(activeId.value) }
  catch (e) { testResult.value = { ok: false, message: '测试失败', error: String(e) } }
}

// ── 连接编辑 ──────────────────────────────────────────────────────────────
const editorVisible = ref(false)
const editorTest    = ref(null)
const editorTesting = ref(false)
const form = ref({})

function openEditor(cluster = null) {
  editorTest.value = null
  form.value = cluster
    ? { ...cluster, serversText: (cluster.bootstrap_servers || []).join('\n'), password: '' }
    : { name: '', serversText: '', security_protocol: 'PLAINTEXT', sasl_mechanism: 'PLAIN',
        username: '', password: '', env: '', note: '', color: '#0ea5e9' }
  editorVisible.value = true
}

function _payload() {
  return {
    name: form.value.name,
    bootstrap_servers: (form.value.serversText || '').split(/[\n,]/).map(s => s.trim()).filter(Boolean),
    security_protocol: form.value.security_protocol,
    sasl_mechanism: form.value.sasl_mechanism,
    username: form.value.username || '',
    password: form.value.password || '',
    env: form.value.env || '',
    note: form.value.note || '',
    color: form.value.color || '#0ea5e9',
  }
}

async function testEditorConfig() {
  editorTesting.value = true
  editorTest.value = null
  try { editorTest.value = await api.kafkaTestConfig({ ..._payload(), cluster_id: form.value.id || '' }) }
  catch (e) { editorTest.value = { ok: false, message: '测试失败', error: String(e) } }
  finally { editorTesting.value = false }
}

async function saveCluster() {
  try {
    if (form.value.id) await api.kafkaUpdateCluster(form.value.id, _payload())
    else {
      const created = await api.kafkaAddCluster(_payload())
      activeId.value = created.id
    }
    editorVisible.value = false
    await loadClusters()
    refreshAll()
  } catch (e) {
    editorTest.value = { ok: false, message: '保存失败', error: String(e) }
  }
}

async function removeCluster() {
  if (!confirm(`确认删除连接「${activeCluster.value?.name}」？（不影响 Kafka 集群本身）`)) return
  await api.kafkaDeleteCluster(activeId.value)
  activeId.value = ''
  overview.value = null
  await loadClusters()
}

// ── Topic ─────────────────────────────────────────────────────────────────
async function loadTopics() {
  topicsLoading.value = true
  loadError.value = ''
  try { topics.value = (await api.kafkaTopics(activeId.value, includeInternal.value)).topics }
  catch (e) { loadError.value = `Topic 加载失败：${e}`; topics.value = [] }
  finally { topicsLoading.value = false }
}

async function showTopicDetail(name) {
  selectedTopic.value = name
  topicDetail.value = null
  msgResult.value = null
  msgError.value = ''
  expandedMsg.value = -1
  msgQuery.value = { partition: -1, direction: 'latest', offset: 0, limit: 50 }
  try { topicDetail.value = await api.kafkaTopicDetail(activeId.value, name) }
  catch (e) { loadError.value = `Topic 详情加载失败：${e}` }
}

// ── 消息浏览 ──────────────────────────────────────────────────────────────
const msgQuery   = ref({ partition: -1, direction: 'latest', offset: 0, limit: 50 })
const msgResult  = ref(null)
const msgLoading = ref(false)
const msgError   = ref('')
const expandedMsg = ref(-1)

async function loadMessages() {
  if (!topicDetail.value) return
  msgLoading.value = true
  msgError.value = ''
  expandedMsg.value = -1
  const q = msgQuery.value
  const params = {
    partition: q.partition,
    direction: q.direction === 'offset' ? 'earliest' : q.direction,
    offset: q.direction === 'offset' ? q.offset : -1,
    limit: q.limit,
  }
  try { msgResult.value = await api.kafkaMessages(activeId.value, topicDetail.value.name, params) }
  catch (e) { msgError.value = `消息抓取失败：${e}`; msgResult.value = null }
  finally { msgLoading.value = false }
}

function fmtMsgTime(ts) {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN', { hour12: false })
}

function fmtBytes(n) {
  if (n == null) return '-'
  if (n < 1024) return n + ' B'
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB'
  return (n / 1024 / 1024).toFixed(1) + ' MB'
}

function prettyValue(m) {
  if (m.value_format === 'json') {
    try { return JSON.stringify(JSON.parse(m.value), null, 2) } catch { /* fallthrough */ }
  }
  return m.value
}

const createVisible = ref(false)
const createError   = ref('')
const topicForm = ref({ name: '', partitions: 3, replication_factor: 1 })

async function submitCreateTopic() {
  createError.value = ''
  try {
    await api.kafkaCreateTopic(activeId.value, topicForm.value)
    createVisible.value = false
    topicForm.value = { name: '', partitions: 3, replication_factor: 1 }
    await loadTopics()
  } catch (e) { createError.value = String(e) }
}

async function removeTopic(name) {
  if (!confirm(`⚠️ 确认删除 Topic「${name}」？此操作不可恢复，所有消息将丢失！`)) return
  try {
    await api.kafkaDeleteTopic(activeId.value, name)
    if (topicDetail.value?.name === name) topicDetail.value = null
    await loadTopics()
  } catch (e) { loadError.value = `删除失败：${e}` }
}

// ── 消费组 ────────────────────────────────────────────────────────────────
async function loadGroups() {
  groupsLoading.value = true
  loadError.value = ''
  try { groups.value = (await api.kafkaGroups(activeId.value)).groups }
  catch (e) { loadError.value = `消费组加载失败：${e}`; groups.value = [] }
  finally { groupsLoading.value = false }
}

async function showLag(gid) {
  lagDetail.value = null
  try { lagDetail.value = await api.kafkaGroupLag(activeId.value, gid) }
  catch (e) { loadError.value = `Lag 查询失败：${e}` }
}

onMounted(loadClusters)
</script>

<style scoped>
.kafka-page { display: flex; height: 100%; min-height: calc(100vh - 0px); }

/* 左侧连接面板 */
.conn-panel { width: 240px; flex-shrink: 0; border-right: 1px solid var(--border); display: flex; flex-direction: column; background: var(--bg-card); }
.conn-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 12px; border-bottom: 1px solid var(--border); }
.conn-title { font-weight: 700; font-size: 14px; }
.conn-list { flex: 1; overflow-y: auto; padding: 8px; }
.conn-item { display: flex; align-items: center; gap: 8px; padding: 10px; border-radius: 8px; cursor: pointer; border: 1px solid transparent; }
.conn-item:hover { background: var(--bg-hover, rgba(255,255,255,.04)); }
.conn-item.active { border-color: var(--primary, #3b82f6); background: rgba(59,130,246,.08); }
.conn-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.conn-info { flex: 1; min-width: 0; }
.conn-name { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conn-addr { font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.conn-env { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(14,165,233,.15); color: #38bdf8; }
.conn-empty { padding: 28px 12px; text-align: center; color: var(--text-muted); font-size: 12px; line-height: 1.8; }

/* 主区域 */
.main-panel { flex: 1; overflow-y: auto; padding: 18px 22px; }
.topbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.topbar-left { display: flex; align-items: center; gap: 10px; }
.topbar-left h1 { font-size: 19px; font-weight: 700; }
.topbar-right { display: flex; gap: 8px; }
.state-pill { font-size: 11px; padding: 2px 10px; border-radius: 99px; font-weight: 600; }
.tone-ok { background: rgba(34,197,94,.15); color: #4ade80; }
.tone-warn { background: rgba(245,158,11,.15); color: #fbbf24; }
.tone-danger { background: rgba(239,68,68,.15); color: #f87171; }
.tone-info { background: rgba(148,163,184,.15); color: #94a3b8; }

.test-banner { padding: 8px 12px; border-radius: 8px; font-size: 12px; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
.test-banner.ok { background: rgba(34,197,94,.1); color: #4ade80; border: 1px solid rgba(34,197,94,.3); }
.test-banner.fail { background: rgba(239,68,68,.1); color: #f87171; border: 1px solid rgba(239,68,68,.3); }
.close-x { margin-left: auto; background: none; border: none; color: inherit; cursor: pointer; font-size: 14px; }

/* Tabs */
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }
.tab { padding: 8px 16px; background: none; border: none; border-bottom: 2px solid transparent; color: var(--text-muted); font-size: 13px; cursor: pointer; }
.tab.active { color: var(--primary, #3b82f6); border-bottom-color: var(--primary, #3b82f6); font-weight: 600; }

/* KPI */
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 16px; }
.kpi { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; display: flex; flex-direction: column; gap: 4px; }
.kpi span { font-size: 11px; color: var(--text-muted); }
.kpi strong { font-size: 20px; font-weight: 700; }
.kpi.tone-warn strong { color: #fbbf24; }

/* Section / 表格 */
.section { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
.sec-title { font-size: 13px; font-weight: 700; margin-bottom: 10px; display: flex; align-items: center; }
.tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.tbl th { text-align: left; padding: 7px 10px; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); font-size: 11.5px; }
.tbl td { padding: 7px 10px; border-bottom: 1px solid var(--border); }
.tbl tr:last-child td { border-bottom: none; }
.tbl tr.rowsel td { background: rgba(59,130,246,.06); }
.mono { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 12px; }
.muted { color: var(--text-muted); }
.clickable { cursor: pointer; color: var(--primary, #3b82f6); }
.clickable:hover { text-decoration: underline; }
.val-ok { color: #4ade80; }
.val-warn { color: #fbbf24; }
.val-err { color: #f87171; }

.kv-grid { display: grid; grid-template-columns: 220px 1fr; gap: 6px 14px; font-size: 12.5px; }
.kv-grid .k { color: var(--text-muted); }

.pane-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.chk { font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; cursor: pointer; }

.loading-row { display: flex; align-items: center; gap: 10px; padding: 36px; justify-content: center; color: var(--text-muted); font-size: 13px; }
.spinner { width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--primary, #3b82f6); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.empty-state { display: flex; flex-direction: column; align-items: center; gap: 10px; color: var(--text-muted); }
.empty-state.full { height: 70vh; justify-content: center; }
.empty-state .icon { font-size: 36px; }

/* 弹窗 */
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.55); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal { background: var(--bg-card, #1e293b); border: 1px solid var(--border); border-radius: 12px; padding: 20px 22px; width: 460px; max-height: 86vh; overflow-y: auto; }
.modal h3 { font-size: 15px; font-weight: 700; margin-bottom: 14px; }
.form-grid { display: grid; grid-template-columns: 110px 1fr; gap: 10px 12px; align-items: center; font-size: 12.5px; }
.form-grid label { color: var(--text-muted); }
.form-grid input, .form-grid select, .form-grid textarea {
  background: var(--bg-input, rgba(255,255,255,.05)); border: 1px solid var(--border); border-radius: 7px;
  padding: 7px 10px; color: inherit; font-size: 12.5px; width: 100%;
}
.modal-actions { display: flex; gap: 8px; margin-top: 16px; }

/* 按钮 */
.btn { border-radius: 7px; cursor: pointer; border: 1px solid transparent; font-size: 12.5px; padding: 6px 14px; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-xs { padding: 2px 8px; font-size: 11px; margin-right: 4px; }
.btn-primary { background: var(--primary, #3b82f6); color: #fff; }
.btn-outline { background: transparent; border-color: var(--border); color: inherit; }
.btn-outline:hover { border-color: var(--primary, #3b82f6); }
.btn.danger { color: #f87171; }
.btn.danger:hover { border-color: #f87171; }

.badge { font-size: 10.5px; padding: 1px 8px; border-radius: 99px; font-weight: 600; }
.badge-ok { background: rgba(34,197,94,.15); color: #4ade80; }
.badge-warn { background: rgba(245,158,11,.15); color: #fbbf24; }
.badge-info { background: rgba(59,130,246,.15); color: #60a5fa; }

/* 消息浏览 */
.msg-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.msg-sel { background: var(--bg-input, rgba(255,255,255,.05)); border: 1px solid var(--border); border-radius: 7px; padding: 5px 8px; color: inherit; font-size: 12px; }
.msg-row { cursor: pointer; }
.msg-row:hover td { background: rgba(59,130,246,.05); }
.ellip { max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.msg-expand { background: rgba(0,0,0,.18); }
.msg-headers { font-size: 11.5px; margin-bottom: 8px; color: var(--text-muted); }
.msg-pre { font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11.5px; line-height: 1.5;
  white-space: pre-wrap; word-break: break-all; max-height: 360px; overflow-y: auto;
  background: rgba(0,0,0,.25); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; margin: 0; }
</style>
