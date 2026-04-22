<template>
  <div class="jenkins-page">
    <!-- 顶部统计 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-val">{{ jobs.length }}</div>
        <div class="stat-label">Job 总数</div>
      </div>
      <div class="stat-card ok">
        <div class="stat-val">{{ countByColor('blue') }}</div>
        <div class="stat-label">最近成功</div>
      </div>
      <div class="stat-card error">
        <div class="stat-val">{{ countByColor('red') }}</div>
        <div class="stat-label">最近失败</div>
      </div>
      <div class="stat-card warn">
        <div class="stat-val">{{ runningBuilds.length }}</div>
        <div class="stat-label">正在构建</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">{{ queueItems.length }}</div>
        <div class="stat-label">队列等待</div>
      </div>
      <!-- 连接状态 -->
      <div class="conn-indicator" :class="connOk ? 'ok' : 'err'">
        <span class="dot"></span>
        <span>{{ connOk ? 'Jenkins 已连接' : '未连接' }}</span>
        <button class="btn btn-xs btn-outline" @click="showConfig = true" style="margin-left:8px">配置</button>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="tab-group">
        <button class="tab-btn" :class="{ active: tab === 'jobs' }"    @click="tab='jobs'">Job 列表</button>
        <button class="tab-btn" :class="{ active: tab === 'running' }" @click="tab='running'; loadRunning()">运行中</button>
        <button class="tab-btn" :class="{ active: tab === 'queue' }"   @click="tab='queue'; loadQueue()">构建队列</button>
      </div>
      <div style="flex:1"></div>
      <input v-if="tab==='jobs'" v-model="search" class="search-input" placeholder="搜索 Job 名称..." @input="onSearch" />
      <button class="btn btn-outline" @click="reload" :disabled="loading">
        <span v-if="loading" class="spinner"></span><span v-else>↺</span> 刷新
      </button>
      <button v-if="tab==='jobs'" class="btn btn-primary" @click="openBuild(null)">▶ 触发构建</button>
    </div>

    <!-- Job 列表 -->
    <div v-show="tab === 'jobs'" class="table-wrap">
      <div v-if="loading && !jobs.length" class="empty-state"><div class="spinner"></div><p>加载中...</p></div>
      <div v-else-if="!connOk && !jobs.length" class="empty-state">
        <span class="icon">🔌</span>
        <p>Jenkins 未连接，请先<button class="link-btn" @click="showConfig=true">配置连接</button></p>
      </div>
      <div v-else-if="!filteredJobs.length" class="empty-state"><span class="icon">🔍</span><p>未找到 Job</p></div>
      <table v-else class="data-table">
        <thead>
          <tr>
            <th>状态</th>
            <th>Job 名称</th>
            <th>最近构建</th>
            <th>结果</th>
            <th>时间</th>
            <th>耗时</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="j in filteredJobs" :key="j.name" @click="selectJob(j)">
            <td><span class="status-dot" :class="colorClass(j.color)"></span></td>
            <td class="job-name">{{ j.name }}</td>
            <td class="mono small">#{{ j.lastBuild?.number ?? '-' }}</td>
            <td><span class="result-badge" :class="resultClass(j.lastBuild?.result)">{{ resultLabel(j.lastBuild?.result) }}</span></td>
            <td class="small text-muted">{{ fmtTs(j.lastBuild?.timestamp) }}</td>
            <td class="small text-muted">{{ fmtDur(j.lastBuild?.duration) }}</td>
            <td class="action-cell" @click.stop>
              <button class="btn btn-xs btn-outline" @click="openBuild(j)" title="触发构建">▶</button>
              <button class="btn btn-xs btn-outline" @click="viewLogs(j)" title="查看日志">📄</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 运行中 -->
    <div v-show="tab === 'running'" class="table-wrap">
      <div v-if="!runningBuilds.length" class="empty-state"><span class="icon">✅</span><p>当前没有正在运行的构建</p></div>
      <table v-else class="data-table">
        <thead><tr><th>Job</th><th>构建号</th><th>触发时间</th><th>预估剩余</th></tr></thead>
        <tbody>
          <tr v-for="b in runningBuilds" :key="b.job+b.number">
            <td class="job-name">{{ b.job }}</td>
            <td class="mono small">#{{ b.number }}</td>
            <td class="small text-muted">{{ fmtTs(b.timestamp) }}</td>
            <td class="small">{{ Math.round((b.estimatedDuration||0)/1000) }}s</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 队列 -->
    <div v-show="tab === 'queue'" class="table-wrap">
      <div v-if="!queueItems.length" class="empty-state"><span class="icon">📭</span><p>构建队列为空</p></div>
      <table v-else class="data-table">
        <thead><tr><th>队列 ID</th><th>Job</th><th>等待原因</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="item in queueItems" :key="item.id">
            <td class="mono small">{{ item.id }}</td>
            <td class="job-name">{{ item.task?.name ?? '-' }}</td>
            <td class="small text-muted">{{ item.why ?? '-' }}</td>
            <td @click.stop><button class="btn btn-xs btn-danger" @click="cancelQueue(item.id)">取消</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 右侧详情面板 -->
    <div v-if="selectedJob" class="detail-panel">
      <div class="detail-header">
        <span class="detail-title">{{ selectedJob.name }}</span>
        <button class="close-btn" @click="selectedJob=null">✕</button>
      </div>
      <div class="detail-body">
        <div class="build-select-row">
          <label>构建号</label>
          <select v-model="buildNum" @change="loadBuildDetail">
            <option value="lastBuild">最新构建</option>
            <option v-for="n in buildNumbers" :key="n" :value="String(n)">#{{ n }}</option>
          </select>
        </div>
        <div v-if="buildDetail" class="build-detail">
          <div class="detail-row"><span class="dl">结果</span><span class="dv"><span class="result-badge" :class="resultClass(buildDetail.result)">{{ resultLabel(buildDetail.result) }}</span></span></div>
          <div class="detail-row"><span class="dl">构建号</span><span class="dv mono">#{{ buildDetail.number }}</span></div>
          <div class="detail-row"><span class="dl">触发时间</span><span class="dv small">{{ fmtTs(buildDetail.timestamp) }}</span></div>
          <div class="detail-row"><span class="dl">耗时</span><span class="dv">{{ fmtDur(buildDetail.duration) }}</span></div>
          <div class="detail-row"><span class="dl">链接</span><span class="dv"><a :href="buildDetail.url" target="_blank" class="jenkins-link">打开 Jenkins ↗</a></span></div>
        </div>
        <div class="detail-actions">
          <button class="btn btn-primary" style="width:100%;margin-bottom:6px" @click="openBuild(selectedJob)">▶ 触发新构建</button>
          <button class="btn btn-outline" style="width:100%" @click="viewLogs(selectedJob)">📄 查看日志</button>
        </div>
        <!-- 日志展示 -->
        <div v-if="logContent" class="log-wrap">
          <div class="log-header">
            <span>构建日志（末尾 {{ logLines }} 行）</span>
            <select v-model.number="logLines" @change="loadLog(selectedJob)" class="log-lines-select">
              <option :value="50">50行</option>
              <option :value="100">100行</option>
              <option :value="200">200行</option>
              <option :value="500">500行</option>
            </select>
          </div>
          <pre class="log-content">{{ logContent }}</pre>
        </div>
      </div>
    </div>

    <!-- 触发构建弹窗 -->
    <div v-if="showBuildModal" class="modal-mask" @click.self="showBuildModal=false">
      <div class="modal-card">
        <div class="modal-header"><span>触发构建</span><button class="close-btn" @click="showBuildModal=false">✕</button></div>
        <div class="modal-body">
          <div class="form-group">
            <label>Job 名称</label>
            <input v-model="buildForm.job" placeholder="输入 Job 名称" @input="onBuildJobSearch" />
            <div v-if="buildSuggestions.length" class="suggest-list">
              <div v-for="s in buildSuggestions" :key="s.name" class="suggest-item" @click="buildForm.job=s.name; buildSuggestions=[]">{{ s.name }}</div>
            </div>
          </div>
          <div class="form-group">
            <label>构建参数 <span class="form-hint">（可选，每行 KEY=VALUE）</span></label>
            <textarea v-model="buildForm.paramsText" rows="4" placeholder="BRANCH=main&#10;ENV=prod"></textarea>
          </div>
          <div v-if="buildMsg" class="build-msg" :class="buildMsgOk ? 'ok' : 'err'">{{ buildMsg }}</div>
          <div class="form-actions">
            <button class="btn btn-outline" @click="showBuildModal=false">取消</button>
            <button class="btn btn-primary" @click="doTriggerBuild" :disabled="triggering">
              <span v-if="triggering" class="spinner"></span> ▶ 触发
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Jenkins 配置弹窗 -->
    <div v-if="showConfig" class="modal-mask" @click.self="showConfig=false">
      <div class="modal-card" style="max-width:420px">
        <div class="modal-header"><span>Jenkins 连接配置</span><button class="close-btn" @click="showConfig=false">✕</button></div>
        <div class="modal-body">
          <div class="form-group"><label>Jenkins URL</label><input v-model="cfgForm.url" placeholder="http://jenkins.example.com:8080" /></div>
          <div class="form-group"><label>用户名</label><input v-model="cfgForm.username" placeholder="admin" /></div>
          <div class="form-group"><label>API Token <span class="form-hint">（用户设置→API Token）</span></label><input v-model="cfgForm.token" type="password" placeholder="留空保持不变" /></div>
          <div v-if="cfgMsg" class="build-msg" :class="cfgOk ? 'ok' : 'err'">{{ cfgMsg }}</div>
          <div class="form-actions">
            <button class="btn btn-outline" @click="testConn" :disabled="cfgTesting">
              <span v-if="cfgTesting" class="spinner"></span> 测试连接
            </button>
            <button class="btn btn-primary" @click="saveConfig" :disabled="cfgSaving">
              <span v-if="cfgSaving" class="spinner"></span> 保存
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const tab          = ref('jobs')
const jobs         = ref([])
const runningBuilds = ref([])
const queueItems   = ref([])
const loading      = ref(false)
const search       = ref('')
const connOk       = ref(false)
const selectedJob  = ref(null)
const buildDetail  = ref(null)
const buildNum     = ref('lastBuild')
const buildNumbers = ref([])
const logContent   = ref('')
const logLines     = ref(100)

// ── 数据加载 ──────────────────────────────────────────────────────────────────
async function loadJobs() {
  loading.value = true
  try {
    const res = await api.jenkinsGetJobs()
    jobs.value = res.data || []
    connOk.value = true
  } catch {
    connOk.value = false
  } finally {
    loading.value = false
  }
}

async function loadRunning() {
  try {
    const res = await api.jenkinsGetRunning()
    runningBuilds.value = res.data || []
  } catch {}
}

async function loadQueue() {
  try {
    const res = await api.jenkinsGetQueue()
    queueItems.value = res.data || []
  } catch {}
}

function reload() {
  if (tab.value === 'jobs') loadJobs()
  else if (tab.value === 'running') loadRunning()
  else loadQueue()
}

onMounted(async () => {
  await loadConfig()
  loadJobs()
  loadRunning()
})

// ── 过滤 ──────────────────────────────────────────────────────────────────────
const filteredJobs = computed(() => {
  if (!search.value) return jobs.value
  const q = search.value.toLowerCase()
  return jobs.value.filter(j => j.name.toLowerCase().includes(q))
})

function onSearch() {}

// ── 统计 ──────────────────────────────────────────────────────────────────────
function countByColor(c) { return jobs.value.filter(j => j.color === c || j.color?.startsWith(c)).length }

// ── 格式化 ────────────────────────────────────────────────────────────────────
function fmtTs(ts) {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function fmtDur(ms) {
  if (!ms) return '-'
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s/60)}m${s%60}s`
}
function colorClass(c) {
  if (!c) return 'unknown'
  if (c.includes('blue')) return 'success'
  if (c.includes('red')) return 'error'
  if (c.includes('yellow')) return 'warning'
  if (c.includes('notbuilt') || c.includes('disabled')) return 'muted'
  return 'muted'
}
function resultClass(r) {
  return { SUCCESS:'success', FAILURE:'error', UNSTABLE:'warning', ABORTED:'muted' }[r] || 'muted'
}
function resultLabel(r) {
  return { SUCCESS:'成功', FAILURE:'失败', UNSTABLE:'不稳定', ABORTED:'已中止', null:'进行中', undefined:'-' }[r] ?? r ?? '-'
}

// ── Job 详情 ──────────────────────────────────────────────────────────────────
function selectJob(j) {
  if (selectedJob.value?.name === j.name) { selectedJob.value = null; return }
  selectedJob.value = j
  buildDetail.value = null
  buildNum.value = 'lastBuild'
  logContent.value = ''
  buildNumbers.value = j.lastBuild?.number ? Array.from({length: Math.min(j.lastBuild.number, 20)}, (_, i) => j.lastBuild.number - i) : []
  loadBuildDetail()
}

async function loadBuildDetail() {
  if (!selectedJob.value) return
  try {
    buildDetail.value = await api.jenkinsGetBuildInfo(selectedJob.value.name, buildNum.value)
  } catch {}
}

async function viewLogs(j) {
  if (!selectedJob.value || selectedJob.value.name !== j.name) selectJob(j)
  await loadLog(j)
}

async function loadLog(j) {
  logContent.value = '加载中...'
  try {
    const res = await api.jenkinsGetBuildLogs(j.name, buildNum.value, logLines.value)
    logContent.value = res.log || '（日志为空）'
  } catch (e) {
    logContent.value = '日志加载失败：' + (typeof e === 'string' ? e : '未知错误')
  }
}

// ── 触发构建 ──────────────────────────────────────────────────────────────────
const showBuildModal   = ref(false)
const buildForm        = ref({ job: '', paramsText: '' })
const buildSuggestions = ref([])
const triggering       = ref(false)
const buildMsg         = ref('')
const buildMsgOk       = ref(false)

function openBuild(j) {
  buildForm.value = { job: j?.name || '', paramsText: '' }
  buildSuggestions.value = []
  buildMsg.value = ''
  showBuildModal.value = true
}

function onBuildJobSearch() {
  const q = buildForm.value.job.toLowerCase()
  buildSuggestions.value = q ? jobs.value.filter(j => j.name.toLowerCase().includes(q)).slice(0, 8) : []
}

async function doTriggerBuild() {
  buildMsg.value = ''
  if (!buildForm.value.job.trim()) { buildMsg.value = '请输入 Job 名称'; buildMsgOk.value = false; return }
  triggering.value = true
  const params = {}
  for (const line of buildForm.value.paramsText.split('\n')) {
    const idx = line.indexOf('=')
    if (idx > 0) params[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
  }
  try {
    const res = await api.jenkinsBuild({ job: buildForm.value.job, params: Object.keys(params).length ? params : null })
    buildMsg.value = res.message || '已触发'
    buildMsgOk.value = res.ok !== false
    if (buildMsgOk.value) setTimeout(() => { showBuildModal.value = false; loadJobs() }, 1500)
  } catch (e) {
    buildMsg.value = '触发失败：' + (typeof e === 'string' ? e : '未知')
    buildMsgOk.value = false
  } finally {
    triggering.value = false
  }
}

// ── 取消队列 ──────────────────────────────────────────────────────────────────
async function cancelQueue(id) {
  if (!confirm(`确定取消队列 ID ${id} 的构建？`)) return
  await api.jenkinsCancelQueue(id)
  loadQueue()
}

// ── 配置 ──────────────────────────────────────────────────────────────────────
const showConfig = ref(false)
const cfgForm    = ref({ url: '', username: '', token: '' })
const cfgMsg     = ref('')
const cfgOk      = ref(false)
const cfgTesting = ref(false)
const cfgSaving  = ref(false)

async function loadConfig() {
  try {
    const res = await api.jenkinsGetConfig()
    cfgForm.value.url      = res.url || ''
    cfgForm.value.username = res.username || ''
    connOk.value = !!res.url
  } catch {}
}

async function testConn() {
  cfgTesting.value = true
  cfgMsg.value = ''
  await saveConfig(false)
  try {
    const res = await api.jenkinsTest()
    cfgMsg.value = res.message
    cfgOk.value  = res.ok
    connOk.value = res.ok
  } catch (e) {
    cfgMsg.value = '测试失败：' + (typeof e === 'string' ? e : '未知')
    cfgOk.value  = false
  } finally {
    cfgTesting.value = false
  }
}

async function saveConfig(close = true) {
  cfgSaving.value = true
  try {
    await api.jenkinsSaveConfig({ url: cfgForm.value.url, username: cfgForm.value.username, token: cfgForm.value.token || '' })
    cfgMsg.value = '保存成功'
    cfgOk.value  = true
    if (close) { showConfig.value = false; loadJobs() }
  } catch (e) {
    cfgMsg.value = '保存失败：' + (typeof e === 'string' ? e : '未知')
    cfgOk.value  = false
  } finally {
    cfgSaving.value = false
  }
}
</script>

<style scoped>
.jenkins-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; padding: 16px; gap: 12px; position: relative; }

/* 统计 */
.stats-row { display: flex; gap: 10px; flex-shrink: 0; align-items: center; flex-wrap: wrap; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 10px 16px; min-width: 80px; }
.stat-card.ok .stat-val { color: var(--success); }
.stat-card.error .stat-val { color: var(--error); }
.stat-card.warn .stat-val { color: var(--warning); }
.stat-val { font-size: 20px; font-weight: 700; }
.stat-label { font-size: 11px; color: var(--text-muted); }
.conn-indicator { display: flex; align-items: center; gap: 5px; font-size: 12px; padding: 6px 12px; border-radius: 6px; background: var(--bg-card); border: 1px solid var(--border); }
.conn-indicator.ok { border-color: var(--success); color: var(--success); }
.conn-indicator.err { border-color: var(--error); color: var(--error); }
.dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; display: inline-block; }

/* 工具栏 */
.toolbar { display: flex; gap: 8px; align-items: center; flex-shrink: 0; flex-wrap: wrap; }
.tab-group { display: flex; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.tab-btn { padding: 6px 14px; font-size: 13px; border: none; background: transparent; color: var(--text-secondary); cursor: pointer; }
.tab-btn.active { background: var(--accent); color: #fff; }
.search-input { padding: 5px 10px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 13px; width: 220px; }

/* 表格 */
.table-wrap { flex: 1; overflow: auto; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table thead { position: sticky; top: 0; z-index: 2; }
.data-table th { background: var(--bg-header); padding: 8px 12px; text-align: left; font-size: 11px; font-weight: 600; color: var(--text-muted); border-bottom: 1px solid var(--border); white-space: nowrap; }
.data-table td { padding: 7px 12px; border-bottom: 1px solid var(--border-faint, var(--border)); white-space: nowrap; }
.data-table tbody tr:hover { background: var(--bg-hover); cursor: pointer; }
.job-name { font-weight: 500; }
.mono { font-family: 'Cascadia Code','Consolas',monospace; }
.small { font-size: 12px; }
.text-muted { color: var(--text-muted); }
.action-cell { display: flex; gap: 4px; }

/* 状态 */
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.status-dot.success { background: var(--success); }
.status-dot.error { background: var(--error); }
.status-dot.warning { background: var(--warning); }
.status-dot.muted { background: var(--text-muted); }
.status-dot.unknown { background: var(--border); }
.result-badge { font-size: 11px; padding: 2px 7px; border-radius: 10px; }
.result-badge.success { background: rgba(63,185,80,.12); color: var(--success); }
.result-badge.error { background: rgba(248,81,73,.12); color: var(--error); }
.result-badge.warning { background: rgba(210,153,34,.12); color: var(--warning); }
.result-badge.muted { background: var(--bg-hover); color: var(--text-muted); }

/* 按钮 */
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 5px 12px; border-radius: 5px; border: 1px solid transparent; font-size: 13px; cursor: pointer; transition: all .15s; white-space: nowrap; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.btn-outline { background: transparent; border-color: var(--border); color: var(--text-secondary); }
.btn-outline:hover { background: var(--bg-hover); }
.btn-danger { background: rgba(248,81,73,.12); color: var(--error); border-color: var(--error); }
.btn-xs { padding: 2px 7px; font-size: 11px; }
.link-btn { background: none; border: none; color: var(--accent); cursor: pointer; text-decoration: underline; }

/* 空状态 */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: var(--text-muted); gap: 8px; }
.empty-state .icon { font-size: 32px; }
.spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 右侧面板 */
.detail-panel { position: absolute; top: 0; right: 0; bottom: 0; width: 340px; background: var(--bg-card); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; z-index: 10; }
.detail-header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.detail-title { font-weight: 600; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }
.detail-body { flex: 1; overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.build-select-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.build-select-row select { flex: 1; padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-input); color: var(--text-primary); font-size: 12px; }
.build-detail { display: flex; flex-direction: column; gap: 6px; }
.detail-row { display: flex; gap: 8px; font-size: 12px; }
.dl { color: var(--text-muted); min-width: 60px; flex-shrink: 0; }
.dv { color: var(--text-primary); }
.jenkins-link { color: var(--accent); text-decoration: none; font-size: 12px; }
.detail-actions { display: flex; flex-direction: column; gap: 6px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; }

/* 日志 */
.log-wrap { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.log-header { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
.log-lines-select { padding: 2px 6px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-input); color: var(--text-primary); font-size: 11px; }
.log-content { flex: 1; overflow: auto; background: #0d1117; color: #c9d1d9; font-family: 'Cascadia Code','Consolas',monospace; font-size: 11px; line-height: 1.5; padding: 10px; border-radius: 6px; white-space: pre; max-height: 400px; }

/* 弹窗 */
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 200; display: flex; align-items: center; justify-content: center; }
.modal-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; width: 500px; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 14px; }
.modal-body { overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 12px; }
.form-group { display: flex; flex-direction: column; gap: 4px; position: relative; }
.form-group label { font-size: 12px; color: var(--text-muted); }
.form-hint { font-weight: 400; font-style: italic; }
.form-group input, .form-group textarea, .form-group select { padding: 7px 10px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 13px; }
.form-group textarea { resize: vertical; font-family: 'Cascadia Code','Consolas',monospace; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
.build-msg { font-size: 12px; padding: 6px 10px; border-radius: 5px; }
.build-msg.ok { background: rgba(63,185,80,.12); color: var(--success); }
.build-msg.err { background: rgba(248,81,73,.12); color: var(--error); }
.suggest-list { position: absolute; top: 100%; left: 0; right: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 5px; z-index: 10; max-height: 200px; overflow-y: auto; }
.suggest-item { padding: 7px 12px; font-size: 13px; cursor: pointer; }
.suggest-item:hover { background: var(--bg-hover); }
</style>
