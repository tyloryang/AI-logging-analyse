<template>
  <div class="jenkins-page">

    <!-- ── 顶部：实例选择 + 操作 ────────────────────────────────── -->
    <div class="jenkins-topbar">
      <div class="instance-selector">
        <span class="topbar-label">Jenkins 实例</span>
        <div class="instance-tabs">
          <button
            v-for="inst in instances" :key="inst.id"
            class="inst-tab"
            :class="{ active: activeId === inst.id, default: inst.default }"
            @click="switchInstance(inst.id)"
          >
            <span class="inst-dot" :class="connStatus[inst.id]"></span>
            {{ inst.name }}
            <span v-if="inst.default" class="default-badge">默认</span>
          </button>
          <button class="inst-add-btn" @click="openAddInstance" title="添加实例">+</button>
        </div>
      </div>
      <div class="topbar-right">
        <button class="btn btn-outline btn-sm" @click="openEditInstance(activeInstance)" :disabled="!activeInstance">管理实例</button>
        <button class="btn btn-primary btn-sm" @click="openBuild(null)">▶ 触发构建</button>
        <button class="btn btn-outline btn-sm" @click="reload" :disabled="loading">↺</button>
      </div>
    </div>

    <!-- ── 主体：左侧 Views + 右侧 Job 列表 ─────────────────────── -->
    <div class="jenkins-body">

      <!-- 左侧：Views 分类 -->
      <aside class="views-sidebar">
        <div class="views-title">视图分类</div>
        <div v-if="loadingViews" class="views-loading"><div class="spinner-sm"></div></div>
        <div v-else class="views-list">
          <div
            class="view-item"
            :class="{ active: selectedView === '' }"
            @click="selectView('')"
          >
            <span class="view-icon">📋</span>
            <span class="view-name">全部 Jobs</span>
            <span class="view-count">{{ totalJobs }}</span>
          </div>
          <div
            v-for="v in views" :key="v.name"
            class="view-item"
            :class="{ active: selectedView === v.name }"
            @click="selectView(v.name)"
          >
            <span class="view-icon">{{ v.fail_count > 0 ? '🔴' : '📁' }}</span>
            <span class="view-name">{{ v.name }}</span>
            <span class="view-count" :class="v.fail_count > 0 ? 'err' : ''">{{ v.job_count }}</span>
          </div>
        </div>
      </aside>

      <!-- 右侧：Job 列表 -->
      <div class="jobs-panel">
        <!-- 统计 -->
        <div class="stats-row">
          <div class="stat-card">
            <div class="stat-val">{{ jobs.length }}</div>
            <div class="stat-label">{{ selectedView || 'Jobs' }}</div>
          </div>
          <div class="stat-card ok">
            <div class="stat-val">{{ countByColor('blue') }}</div>
            <div class="stat-label">成功</div>
          </div>
          <div class="stat-card error">
            <div class="stat-val">{{ countByColor('red') }}</div>
            <div class="stat-label">失败</div>
          </div>
          <div class="stat-card warn">
            <div class="stat-val">{{ runningBuilds.length }}</div>
            <div class="stat-label">构建中</div>
          </div>
          <div style="flex:1"></div>
          <input v-model="search" class="search-input" placeholder="搜索 Job..." />
        </div>

        <!-- Tabs -->
        <div class="tab-bar">
          <button class="tab-btn" :class="{ active: tab === 'jobs' }"    @click="tab='jobs'">Job 列表</button>
          <button class="tab-btn" :class="{ active: tab === 'running' }" @click="tab='running'; loadRunning()">运行中</button>
          <button class="tab-btn" :class="{ active: tab === 'queue' }"   @click="tab='queue'; loadQueue()">队列</button>
        </div>

        <!-- Job 表格 -->
        <div v-show="tab === 'jobs'" class="table-wrap">
          <div v-if="!activeId" class="empty-state"><span class="icon">🔌</span><p>请先<button class="link-btn" @click="openAddInstance">添加 Jenkins 实例</button></p></div>
          <div v-else-if="loading" class="empty-state"><div class="spinner"></div></div>
          <div v-else-if="!filteredJobs.length" class="empty-state"><span class="icon">🔍</span><p>无匹配 Job</p></div>
          <table v-else class="data-table">
            <thead><tr><th>状态</th><th>Job 名称</th><th>最近构建</th><th>结果</th><th>时间</th><th>耗时</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="j in filteredJobs" :key="j.name" @click="selectJob(j)">
                <td><span class="status-dot" :class="colorClass(j.color)"></span></td>
                <td class="job-name">{{ j.name }}</td>
                <td class="mono small">#{{ j.lastBuild?.number ?? '-' }}</td>
                <td><span class="result-badge" :class="resultClass(j.lastBuild?.result)">{{ resultLabel(j.lastBuild?.result) }}</span></td>
                <td class="small text-muted">{{ fmtTs(j.lastBuild?.timestamp) }}</td>
                <td class="small text-muted">{{ fmtDur(j.lastBuild?.duration) }}</td>
                <td @click.stop><button class="btn btn-xs btn-outline" @click="openBuild(j)">▶</button><button class="btn btn-xs btn-outline" @click="viewLogs(j)">📄</button></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- 运行中 -->
        <div v-show="tab === 'running'" class="table-wrap">
          <div v-if="!runningBuilds.length" class="empty-state"><span class="icon">✅</span><p>当前无运行中构建</p></div>
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
          <div v-if="!queueItems.length" class="empty-state"><span class="icon">📭</span><p>队列为空</p></div>
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
      </div>

      <!-- 右侧详情 -->
      <div v-if="selectedJob" class="detail-panel">
        <div class="detail-header"><span class="detail-title">{{ selectedJob.name }}</span><button class="close-btn" @click="selectedJob=null">✕</button></div>
        <div class="detail-body">
          <div class="build-select-row">
            <label>构建号</label>
            <select v-model="buildNum" @change="loadBuildDetail" class="build-select">
              <option value="lastBuild">最新</option>
              <option v-for="n in buildNumbers" :key="n" :value="String(n)">#{{ n }}</option>
            </select>
          </div>
          <div v-if="buildDetail" class="build-detail">
            <div class="detail-row"><span class="dl">结果</span><span class="dv"><span class="result-badge" :class="resultClass(buildDetail.result)">{{ resultLabel(buildDetail.result) }}</span></span></div>
            <div class="detail-row"><span class="dl">构建号</span><span class="dv mono">#{{ buildDetail.number }}</span></div>
            <div class="detail-row"><span class="dl">时间</span><span class="dv small">{{ fmtTs(buildDetail.timestamp) }}</span></div>
            <div class="detail-row"><span class="dl">耗时</span><span class="dv">{{ fmtDur(buildDetail.duration) }}</span></div>
            <div class="detail-row"><span class="dl">链接</span><span class="dv"><a :href="buildDetail.url" target="_blank" class="jenkins-link">Jenkins ↗</a></span></div>
          </div>
          <div class="detail-actions">
            <button class="btn btn-primary" style="width:100%;margin-bottom:6px" @click="openBuild(selectedJob)">▶ 触发新构建</button>
            <button class="btn btn-outline" style="width:100%" @click="viewLogs(selectedJob)">📄 查看日志</button>
          </div>
          <div v-if="logContent" class="log-wrap">
            <div class="log-header">
              <span>日志（末尾 {{ logLines }} 行）</span>
              <select v-model.number="logLines" @change="loadLog(selectedJob)" class="log-lines-select"><option :value="50">50</option><option :value="100">100</option><option :value="200">200</option><option :value="500">500</option></select>
            </div>
            <pre class="log-content">{{ logContent }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 触发构建弹窗 -->
    <div v-if="showBuildModal" class="modal-mask" @click.self="showBuildModal=false">
      <div class="modal-card">
        <div class="modal-header"><span>触发构建</span><button class="close-btn" @click="showBuildModal=false">✕</button></div>
        <div class="modal-body">
          <div class="form-group"><label>Job 名称</label><input v-model="buildForm.job" placeholder="Job 名称" @input="onBuildJobSearch" /><div v-if="buildSuggestions.length" class="suggest-list"><div v-for="s in buildSuggestions" :key="s.name" class="suggest-item" @click="buildForm.job=s.name; buildSuggestions=[]">{{ s.name }}</div></div></div>
          <div class="form-group"><label>参数 <span class="form-hint">（每行 KEY=VALUE）</span></label><textarea v-model="buildForm.paramsText" rows="4" placeholder="BRANCH=main&#10;ENV=prod"></textarea></div>
          <div v-if="buildMsg" class="build-msg" :class="buildMsgOk ? 'ok' : 'err'">{{ buildMsg }}</div>
          <div class="form-actions"><button class="btn btn-outline" @click="showBuildModal=false">取消</button><button class="btn btn-primary" @click="doTriggerBuild" :disabled="triggering"><span v-if="triggering" class="spinner-sm"></span> ▶ 触发</button></div>
        </div>
      </div>
    </div>

    <!-- 实例管理弹窗 -->
    <div v-if="showInstModal" class="modal-mask" @click.self="showInstModal=false">
      <div class="modal-card inst-modal">
        <div class="modal-header"><span>{{ editingInst ? '编辑实例' : '添加 Jenkins 实例' }}</span><button class="close-btn" @click="showInstModal=false">✕</button></div>
        <div class="modal-body">
          <div class="form-group"><label>实例名称</label><input v-model="instForm.name" placeholder="e.g. 生产 Jenkins" /></div>
          <div class="form-group"><label>Jenkins URL</label><input v-model="instForm.url" placeholder="http://jenkins.example.com:8080" /></div>
          <div class="form-group"><label>用户名</label><input v-model="instForm.username" placeholder="admin" /></div>
          <div class="form-group"><label>API Token <span class="form-hint">{{ editingInst ? '（留空保持不变）' : '' }}</span></label><input v-model="instForm.token" type="password" /></div>
          <div class="form-group"><label class="check-label"><input type="checkbox" v-model="instForm.default" /> 设为默认实例</label></div>
          <div v-if="instMsg" class="build-msg" :class="instOk ? 'ok' : 'err'">{{ instMsg }}</div>
          <div class="form-actions">
            <button class="btn btn-outline" @click="testInst" :disabled="instTesting"><span v-if="instTesting" class="spinner-sm"></span> 测试</button>
            <button v-if="editingInst" class="btn btn-danger" @click="deleteInst">删除</button>
            <button class="btn btn-primary" @click="saveInst" :disabled="instSaving"><span v-if="instSaving" class="spinner-sm"></span> 保存</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

// ── 实例管理 ──────────────────────────────────────────────────────────────────
const instances   = ref([])
const activeId    = ref('')
const connStatus  = ref({})   // {id: 'ok'|'err'|''}

const activeInstance = computed(() => instances.value.find(i => i.id === activeId.value) || null)

async function loadInstances() {
  try {
    const r = await api.jenkinsListInstances()
    instances.value = r.data || []
    if (!activeId.value && instances.value.length) {
      const def = instances.value.find(i => i.default) || instances.value[0]
      activeId.value = def.id
    }
  } catch {}
}

async function switchInstance(id) {
  activeId.value = id
  views.value = []
  jobs.value  = []
  selectedJob.value = null
  selectedView.value = ''
  await Promise.all([loadViews(), loadJobs()])
}

async function pingAll() {
  for (const inst of instances.value) {
    api.jenkinsTestInstance(inst.id)
      .then(r => { connStatus.value = { ...connStatus.value, [inst.id]: r.ok ? 'ok' : 'err' } })
      .catch(() => { connStatus.value = { ...connStatus.value, [inst.id]: 'err' } })
  }
}

// ── 实例弹窗 ─────────────────────────────────────────────────────────────────
const showInstModal = ref(false)
const editingInst   = ref(null)
const instForm      = ref({ name: '', url: '', username: '', token: '', default: false })
const instMsg       = ref('')
const instOk        = ref(false)
const instTesting   = ref(false)
const instSaving    = ref(false)

function openAddInstance() {
  editingInst.value = null
  instForm.value = { name: '', url: '', username: '', token: '', default: !instances.value.length }
  instMsg.value = ''
  showInstModal.value = true
}

function openEditInstance(inst) {
  if (!inst) return
  editingInst.value = inst
  instForm.value = { name: inst.name, url: inst.url, username: inst.username, token: '', default: inst.default }
  instMsg.value = ''
  showInstModal.value = true
}

async function testInst() {
  instTesting.value = true
  instMsg.value = ''
  // 先临时保存再测试
  if (editingInst.value) {
    await api.jenkinsUpdateInstance(editingInst.value.id, instForm.value).catch(() => {})
  } else {
    await api.jenkinsCreateInstance(instForm.value).catch(() => {})
    await loadInstances()
    const newest = instances.value[instances.value.length - 1]
    if (newest) editingInst.value = newest
  }
  if (!editingInst.value) { instTesting.value = false; return }
  try {
    const r = await api.jenkinsTestInstance(editingInst.value.id)
    instMsg.value = r.message
    instOk.value  = r.ok
  } catch (e) {
    instMsg.value = typeof e === 'string' ? e : '测试失败'
    instOk.value  = false
  } finally {
    instTesting.value = false
  }
}

async function saveInst() {
  instSaving.value = true
  instMsg.value = ''
  try {
    if (editingInst.value) {
      await api.jenkinsUpdateInstance(editingInst.value.id, instForm.value)
    } else {
      await api.jenkinsCreateInstance(instForm.value)
    }
    await loadInstances()
    await pingAll()
    showInstModal.value = false
    if (!activeId.value) {
      const def = instances.value.find(i => i.default) || instances.value[0]
      if (def) await switchInstance(def.id)
    }
  } catch (e) {
    instMsg.value = typeof e === 'string' ? e : '保存失败'
    instOk.value  = false
  } finally {
    instSaving.value = false
  }
}

async function deleteInst() {
  if (!editingInst.value || !confirm(`确认删除实例「${editingInst.value.name}」？`)) return
  await api.jenkinsDeleteInstance(editingInst.value.id).catch(() => {})
  showInstModal.value = false
  await loadInstances()
  await pingAll()
  if (activeId.value === editingInst.value.id) {
    const def = instances.value[0]
    if (def) await switchInstance(def.id)
    else activeId.value = ''
  }
}

// ── Views + Jobs ──────────────────────────────────────────────────────────────
const views        = ref([])
const jobs         = ref([])
const runningBuilds = ref([])
const queueItems   = ref([])
const loading      = ref(false)
const loadingViews = ref(false)
const search       = ref('')
const tab          = ref('jobs')
const selectedView = ref('')
const totalJobs    = computed(() => jobs.value.length)

const filteredJobs = computed(() => {
  const q = search.value.toLowerCase()
  return q ? jobs.value.filter(j => j.name.toLowerCase().includes(q)) : jobs.value
})

function countByColor(c) { return jobs.value.filter(j => (j.color||'').startsWith(c)).length }

async function loadViews() {
  if (!activeId.value) return
  loadingViews.value = true
  try {
    const r = await api.jenkinsGetViews(activeId.value)
    views.value = (r.data || []).filter(v => v.name !== 'All' && v.name !== '全部')
  } catch { views.value = [] }
  finally { loadingViews.value = false }
}

async function loadJobs() {
  if (!activeId.value) return
  loading.value = true
  try {
    const r = await api.jenkinsGetJobs(activeId.value, selectedView.value || undefined)
    jobs.value = r.data || []
  } catch { jobs.value = [] }
  finally { loading.value = false }
}

async function selectView(v) {
  selectedView.value = v
  await loadJobs()
}

async function loadRunning() {
  if (!activeId.value) return
  try { runningBuilds.value = (await api.jenkinsGetRunning(activeId.value)).data || [] } catch {}
}

async function loadQueue() {
  if (!activeId.value) return
  try { queueItems.value = (await api.jenkinsGetQueue(activeId.value)).data || [] } catch {}
}

async function cancelQueue(id) {
  if (!confirm(`取消队列 ${id}？`)) return
  await api.jenkinsCancelQueue(activeId.value, id).catch(() => {})
  await loadQueue()
}

function reload() {
  if (tab.value === 'jobs') { loadViews(); loadJobs() }
  else if (tab.value === 'running') loadRunning()
  else loadQueue()
}

// ── 格式化 ────────────────────────────────────────────────────────────────────
function fmtTs(ts) { if (!ts) return '-'; const d = new Date(ts); return `${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}` }
function fmtDur(ms) { if (!ms) return '-'; const s = Math.round(ms/1000); return s < 60 ? `${s}s` : `${Math.floor(s/60)}m${s%60}s` }
function colorClass(c) { if (!c) return 'unknown'; if (c.includes('blue')) return 'success'; if (c.includes('red')) return 'error'; if (c.includes('yellow')) return 'warning'; return 'muted' }
function resultClass(r) { return { SUCCESS:'success', FAILURE:'error', UNSTABLE:'warning', ABORTED:'muted' }[r] || 'muted' }
function resultLabel(r) { return { SUCCESS:'成功', FAILURE:'失败', UNSTABLE:'不稳定', ABORTED:'中止', null:'进行中', undefined:'-' }[r] ?? r ?? '-' }

// ── 详情 ──────────────────────────────────────────────────────────────────────
const selectedJob  = ref(null)
const buildDetail  = ref(null)
const buildNum     = ref('lastBuild')
const buildNumbers = ref([])
const logContent   = ref('')
const logLines     = ref(100)

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
  if (!selectedJob.value || !activeId.value) return
  try { buildDetail.value = await api.jenkinsGetBuildInfo(activeId.value, selectedJob.value.name, buildNum.value) } catch {}
}

async function viewLogs(j) {
  if (!selectedJob.value || selectedJob.value.name !== j.name) selectJob(j)
  await loadLog(j)
}

async function loadLog(j) {
  logContent.value = '加载中...'
  try {
    const r = await api.jenkinsGetBuildLogs(activeId.value, j.name, buildNum.value, logLines.value)
    logContent.value = r.log || '（日志为空）'
  } catch (e) {
    logContent.value = '加载失败：' + (typeof e === 'string' ? e : '未知')
  }
}

// ── 触发构建 ──────────────────────────────────────────────────────────────────
const showBuildModal   = ref(false)
const buildForm        = ref({ job: '', paramsText: '' })
const buildSuggestions = ref([])
const triggering       = ref(false)
const buildMsg         = ref('')
const buildMsgOk       = ref(false)

function openBuild(j) { buildForm.value = { job: j?.name || '', paramsText: '' }; buildSuggestions.value = []; buildMsg.value = ''; showBuildModal.value = true }
function onBuildJobSearch() { const q = buildForm.value.job.toLowerCase(); buildSuggestions.value = q ? jobs.value.filter(j => j.name.toLowerCase().includes(q)).slice(0, 8) : [] }

async function doTriggerBuild() {
  buildMsg.value = ''
  if (!buildForm.value.job.trim()) { buildMsg.value = '请输入 Job 名称'; buildMsgOk.value = false; return }
  triggering.value = true
  const params = {}
  for (const line of buildForm.value.paramsText.split('\n')) {
    const idx = line.indexOf('=')
    if (idx > 0) params[line.slice(0, idx).trim()] = line.slice(idx+1).trim()
  }
  try {
    const r = await api.jenkinsBuild(activeId.value, { job: buildForm.value.job, params: Object.keys(params).length ? params : null })
    buildMsg.value = r.message || '已触发'
    buildMsgOk.value = r.ok !== false
    if (buildMsgOk.value) setTimeout(() => { showBuildModal.value = false; loadJobs() }, 1500)
  } catch (e) {
    buildMsg.value = '触发失败：' + (typeof e === 'string' ? e : '未知')
    buildMsgOk.value = false
  } finally {
    triggering.value = false
  }
}

onMounted(async () => {
  await loadInstances()
  if (activeId.value) {
    await Promise.all([loadViews(), loadJobs(), loadRunning()])
    pingAll()
  }
})
</script>

<style scoped>
.jenkins-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

/* 顶栏 */
.jenkins-topbar { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; background: var(--bg-card); border-bottom: 1px solid var(--border); flex-shrink: 0; gap: 12px; flex-wrap: wrap; }
.topbar-label { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.instance-selector { display: flex; align-items: center; gap: 10px; }
.instance-tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.inst-tab { display: flex; align-items: center; gap: 5px; padding: 4px 12px; border-radius: 16px; border: 1px solid var(--border); background: transparent; color: var(--text-secondary); font-size: 12px; cursor: pointer; transition: all .15s; }
.inst-tab:hover { background: var(--bg-hover); }
.inst-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.inst-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-muted); }
.inst-dot.ok  { background: var(--success); }
.inst-dot.err { background: var(--error); }
.default-badge { font-size: 9px; padding: 0 4px; border-radius: 6px; background: rgba(255,255,255,.25); }
.inst-add-btn { width: 26px; height: 26px; border-radius: 50%; border: 1px dashed var(--border); background: transparent; color: var(--text-muted); cursor: pointer; font-size: 16px; display: flex; align-items: center; justify-content: center; }
.inst-add-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.topbar-right { display: flex; gap: 6px; margin-left: auto; }

/* 主体布局 */
.jenkins-body { flex: 1; display: flex; overflow: hidden; min-height: 0; }

/* Views 侧边栏 */
.views-sidebar { width: 180px; flex-shrink: 0; background: var(--bg-card); border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.views-title { font-size: 11px; font-weight: 600; color: var(--text-muted); padding: 10px 12px 6px; text-transform: uppercase; letter-spacing: .04em; }
.views-loading { display: flex; justify-content: center; padding: 12px; }
.views-list { flex: 1; overflow-y: auto; padding: 4px 8px 8px; display: flex; flex-direction: column; gap: 2px; }
.view-item { display: flex; align-items: center; gap: 7px; padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 12px; color: var(--text-secondary); transition: background .12s; }
.view-item:hover { background: var(--bg-hover); }
.view-item.active { background: var(--accent-dim, rgba(56,139,253,.12)); color: var(--accent); font-weight: 600; }
.view-icon { font-size: 13px; }
.view-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.view-count { font-size: 10px; padding: 1px 5px; border-radius: 8px; background: var(--bg-hover); }
.view-count.err { background: rgba(248,81,73,.12); color: var(--error); }

/* Jobs 面板 */
.jobs-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; padding: 12px; gap: 10px; }
.stats-row { display: flex; gap: 8px; flex-shrink: 0; align-items: center; flex-wrap: wrap; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 7px; padding: 8px 14px; min-width: 70px; }
.stat-card.ok .stat-val { color: var(--success); }
.stat-card.error .stat-val { color: var(--error); }
.stat-card.warn .stat-val { color: var(--warning); }
.stat-val { font-size: 18px; font-weight: 700; }
.stat-label { font-size: 10px; color: var(--text-muted); }
.search-input { padding: 5px 10px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 12px; width: 180px; }
.tab-bar { display: flex; gap: 2px; flex-shrink: 0; }
.tab-btn { padding: 5px 14px; font-size: 12px; border: 1px solid var(--border); border-radius: 5px; background: transparent; color: var(--text-secondary); cursor: pointer; }
.tab-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.table-wrap { flex: 1; overflow: auto; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table thead { position: sticky; top: 0; }
.data-table th { background: var(--bg-header, var(--bg-base)); padding: 8px 12px; text-align: left; font-size: 11px; font-weight: 600; color: var(--text-muted); border-bottom: 1px solid var(--border); white-space: nowrap; }
.data-table td { padding: 7px 12px; border-bottom: 1px solid var(--border-faint, var(--border)); white-space: nowrap; }
.data-table tbody tr:hover { background: var(--bg-hover); cursor: pointer; }
.job-name { font-weight: 500; }
.mono { font-family: 'Cascadia Code','Consolas',monospace; }
.small { font-size: 12px; }
.text-muted { color: var(--text-muted); }
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.status-dot.success { background: var(--success); }
.status-dot.error   { background: var(--error); }
.status-dot.warning { background: var(--warning); }
.status-dot.muted   { background: var(--text-muted); }
.result-badge { font-size: 11px; padding: 2px 7px; border-radius: 10px; }
.result-badge.success { background: rgba(63,185,80,.12); color: var(--success); }
.result-badge.error   { background: rgba(248,81,73,.12); color: var(--error); }
.result-badge.warning { background: rgba(210,153,34,.12); color: var(--warning); }
.result-badge.muted   { background: var(--bg-hover); color: var(--text-muted); }

/* 详情面板 */
.detail-panel { width: 300px; flex-shrink: 0; background: var(--bg-card); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.detail-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.detail-title { font-weight: 600; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
.detail-body { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
.build-select-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.build-select { flex: 1; padding: 3px 6px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg-input); color: var(--text-primary); font-size: 11px; }
.build-detail { display: flex; flex-direction: column; gap: 5px; }
.detail-row { display: flex; gap: 8px; font-size: 12px; }
.dl { color: var(--text-muted); min-width: 42px; }
.dv { color: var(--text-primary); }
.jenkins-link { color: var(--accent); text-decoration: none; font-size: 11px; }
.detail-actions { display: flex; flex-direction: column; gap: 5px; }
.log-wrap { flex: 1; display: flex; flex-direction: column; gap: 4px; min-height: 0; }
.log-header { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted); align-items: center; }
.log-lines-select { padding: 1px 4px; border: 1px solid var(--border); border-radius: 3px; background: var(--bg-input); color: var(--text-primary); font-size: 10px; }
.log-content { flex: 1; overflow: auto; background: var(--bg-base); color: var(--text-primary); font-family: 'Cascadia Code','Consolas',monospace; font-size: 10px; line-height: 1.5; padding: 8px; border-radius: 5px; white-space: pre; max-height: 320px; }

/* 按钮 */
.btn { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px; border-radius: 5px; border: 1px solid transparent; font-size: 13px; cursor: pointer; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-outline { background: transparent; border-color: var(--border); color: var(--text-secondary); }
.btn-danger  { background: rgba(248,81,73,.08); color: var(--error); border-color: rgba(248,81,73,.3); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-xs { padding: 2px 7px; font-size: 11px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 15px; }
.link-btn { background: none; border: none; color: var(--accent); cursor: pointer; text-decoration: underline; font-size: 13px; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 160px; gap: 8px; color: var(--text-muted); }
.empty-state .icon { font-size: 28px; }
.spinner { width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
.spinner-sm { display: inline-block; width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 弹窗 */
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 200; display: flex; align-items: center; justify-content: center; }
.modal-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; width: 480px; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden; }
.inst-modal { width: 420px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 13px 18px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 14px; }
.modal-body { overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group label { font-size: 12px; color: var(--text-muted); }
.form-hint { font-weight: 400; font-style: italic; }
.form-group input, .form-group textarea { padding: 7px 10px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 13px; }
.form-group textarea { resize: vertical; font-family: 'Cascadia Code','Consolas',monospace; }
.check-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; color: var(--text-primary); }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
.build-msg { font-size: 12px; padding: 6px 10px; border-radius: 5px; }
.build-msg.ok  { background: rgba(63,185,80,.12); color: var(--success); }
.build-msg.err { background: rgba(248,81,73,.12); color: var(--error); }
.suggest-list { position: absolute; background: var(--bg-card); border: 1px solid var(--border); border-radius: 5px; z-index: 10; max-height: 180px; overflow-y: auto; width: 100%; }
.suggest-item { padding: 7px 12px; font-size: 13px; cursor: pointer; }
.suggest-item:hover { background: var(--bg-hover); }
.form-group { position: relative; }
</style>
