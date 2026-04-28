<template>
  <div class="task-view">
    <div class="task-header">
      <div class="header-left">
        <h2>任务中心</h2>
        <span class="subtitle">SSH 命令执行历史</span>
      </div>
      <div class="header-right">
        <button class="btn btn-primary" @click="openRunModal">▶ 立即执行</button>
        <button class="btn btn-outline" @click="load" :disabled="loading">↺ 刷新</button>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="table-wrap">
      <div v-if="loading" class="empty-state"><div class="spinner"></div><span>加载中...</span></div>
      <div v-else-if="!tasks.length" class="empty-state">
        <span class="icon">📋</span><p>暂无任务记录</p>
      </div>
      <table v-else class="task-table">
        <thead>
          <tr>
            <th>任务名</th><th>命令</th><th>目标主机</th><th>状态</th><th>耗时</th><th>完成时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in tasks" :key="t.id" class="task-row" @click="openDetail(t.id)">
            <td class="task-name">{{ t.name }}</td>
            <td class="task-cmd mono">{{ t.command }}</td>
            <td class="task-hosts">{{ t.target_count || 0 }} 台</td>
            <td><span class="status-badge" :class="t.status">{{ STATUS[t.status] || t.status }}</span></td>
            <td class="small">{{ elapsed(t) }}</td>
            <td class="small">{{ fmt(t.finished_at) }}</td>
            <td @click.stop>
              <button class="btn btn-xs btn-outline" @click="openDetail(t.id)">详情</button>
              <button class="btn btn-xs btn-danger" @click="deleteTask(t.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 立即执行弹窗 -->
    <div v-if="showRunModal" class="modal-overlay" @click.self="showRunModal = false">
      <div class="modal">
        <div class="modal-header"><span>立即执行任务</span><button class="close-btn" @click="showRunModal = false">✕</button></div>
        <div class="modal-body">
          <div class="form-group"><label>任务名称</label><input v-model="runForm.name" placeholder="e.g. 检查磁盘" /></div>
          <div class="form-group"><label>执行命令</label><textarea v-model="runForm.command" rows="3" placeholder="df -h&#10;free -m&#10;ps aux | head -20" /></div>
          <div class="form-group">
            <label>目标主机</label>
            <select v-model="runForm.mode" class="form-select">
              <option value="group">按分组</option>
              <option value="hosts">指定主机</option>
            </select>
          </div>
          <div v-if="runForm.mode === 'group'" class="form-group">
            <label>选择分组</label>
            <select v-model="runForm.host_group" class="form-select">
              <option value="">请选择分组...</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.host_count || 0 }}台）</option>
            </select>
          </div>
          <div v-else class="form-group">
            <label>选择主机（可多选）</label>
            <div class="host-check-list">
              <label v-for="h in cmdbHosts" :key="h.id" class="host-check-item">
                <input type="checkbox" :value="h.id" v-model="runForm.host_ids" />
                <span>{{ h.hostname }}</span><span class="mono small">{{ h.ip }}</span>
                <span v-if="!h.ssh_saved" class="no-ssh">无SSH</span>
              </label>
            </div>
          </div>
          <div class="form-group"><label>超时（秒）</label><input v-model.number="runForm.timeout" type="number" min="5" max="3600" /></div>
          <div v-if="runError" class="form-error">{{ runError }}</div>
          <div class="form-actions">
            <button class="btn btn-outline" @click="showRunModal = false">取消</button>
            <button class="btn btn-primary" @click="submitRun" :disabled="running">
              <span v-if="running" class="spinner-sm"></span>
              {{ running ? '执行中...' : '▶ 执行' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情抽屉 -->
    <div v-if="detail" class="drawer-overlay" @click.self="detail = null">
      <div class="drawer">
        <div class="drawer-header">
          <span>{{ detail.name }}</span>
          <span class="status-badge" :class="detail.status">{{ STATUS[detail.status] || detail.status }}</span>
          <button class="close-btn" @click="detail = null">✕</button>
        </div>
        <div class="drawer-body">
          <div class="detail-meta">
            <div><span class="meta-k">命令</span><code class="mono">{{ detail.command }}</code></div>
            <div><span class="meta-k">摘要</span><span>{{ detail.summary || '—' }}</span></div>
            <div><span class="meta-k">开始</span><span>{{ fmt(detail.started_at) }}</span></div>
            <div><span class="meta-k">完成</span><span>{{ fmt(detail.finished_at) }}</span></div>
          </div>
          <div v-if="detail.status === 'running'" class="running-tip">任务执行中... <span class="spinner-sm"></span></div>
          <div v-for="r in (detail.host_results || [])" :key="r.ip" class="host-result" :class="r.rc === 0 ? 'ok' : 'err'">
            <div class="host-result-head">
              <span class="host-result-name">{{ r.hostname || r.ip }}</span>
              <span class="mono small">{{ r.ip }}</span>
              <span class="rc-badge" :class="r.rc === 0 ? 'ok' : 'err'">exit {{ r.rc }}</span>
            </div>
            <div v-if="r.error" class="host-result-err">{{ r.error }}</div>
            <pre v-if="r.stdout" class="output-pre">{{ r.stdout }}</pre>
            <pre v-if="r.stderr" class="output-pre stderr">{{ r.stderr }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/index.js'

const STATUS = { pending: '等待', running: '执行中', success: '成功', failed: '失败', partial: '部分失败', cancelled: '已取消' }

const tasks   = ref([])
const loading = ref(false)
const detail  = ref(null)
const groups  = ref([])
const cmdbHosts = ref([])

// 执行弹窗
const showRunModal = ref(false)
const running      = ref(false)
const runError     = ref('')
const runForm = ref({ name: '', command: '', mode: 'group', host_group: '', host_ids: [], timeout: 60 })

function fmt(ts) { return ts ? ts.replace('T', ' ').slice(0, 16) : '—' }
function elapsed(t) {
  if (!t.started_at || !t.finished_at) return '—'
  const s = (new Date(t.finished_at) - new Date(t.started_at)) / 1000
  return s < 60 ? `${s.toFixed(1)}s` : `${(s / 60).toFixed(1)}m`
}

async function load() {
  loading.value = true
  try { tasks.value = await api.ansibleTasks() } catch { tasks.value = [] }
  finally { loading.value = false }
}

async function openDetail(id) {
  try {
    detail.value = await api.ansibleGetTask(id)
    // 若任务还在运行，轮询直到完成
    if (detail.value?.status === 'running') {
      const poll = setInterval(async () => {
        const t = await api.ansibleGetTask(id).catch(() => null)
        if (t) detail.value = t
        if (t?.status !== 'running') { clearInterval(poll); load() }
      }, 2000)
    }
  } catch (e) { alert('加载详情失败') }
}

async function deleteTask(id) {
  if (!confirm('确认删除该任务记录？')) return
  await api.ansibleDeleteTask(id).catch(() => {})
  await load()
}

function openRunModal() {
  runForm.value = { name: '', command: '', mode: 'group', host_group: '', host_ids: [], timeout: 60 }
  runError.value = ''
  showRunModal.value = true
}

async function submitRun() {
  runError.value = ''
  const form = runForm.value
  if (!form.name.trim()) { runError.value = '请填写任务名称'; return }
  if (!form.command.trim()) { runError.value = '请填写执行命令'; return }
  if (form.mode === 'group' && !form.host_group) { runError.value = '请选择目标分组'; return }
  if (form.mode === 'hosts' && !form.host_ids.length) { runError.value = '请至少选择一台主机'; return }
  running.value = true
  try {
    const payload = {
      name: form.name, command: form.command, timeout: form.timeout,
      host_ids:   form.mode === 'hosts' ? form.host_ids : [],
      host_group: form.mode === 'group' ? form.host_group : '',
    }
    const task = await api.ansibleCreateTask(payload)
    showRunModal.value = false
    await load()
    await openDetail(task.id)
  } catch (e) {
    runError.value = typeof e === 'string' ? e : '执行失败'
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  await Promise.all([
    load(),
    api.listGroups().then(r => { groups.value = r.data || [] }).catch(() => {}),
    api.getHosts().then(r => { cmdbHosts.value = r.data || [] }).catch(() => {}),
  ])
})
</script>

<style scoped>
.task-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; padding: 20px; gap: 14px; background: var(--bg-base); color: var(--text-primary); }
.task-header { display: flex; justify-content: space-between; align-items: center; }
.header-left h2 { font-size: 18px; font-weight: 600; margin: 0; }
.subtitle { font-size: 12px; color: var(--text-muted); margin-left: 8px; }
.header-right { display: flex; gap: 8px; }
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 6px 14px; border-radius: 6px; border: 1px solid transparent; font-size: 13px; cursor: pointer; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-outline { background: transparent; border-color: var(--border); color: var(--text-primary); }
.btn-danger  { background: rgba(248,81,73,.08); color: var(--error); border-color: rgba(248,81,73,.3); }
.btn-xs { padding: 2px 8px; font-size: 11px; }
.table-wrap { flex: 1; overflow: auto; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.task-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.task-table thead { position: sticky; top: 0; }
.task-table th { padding: 9px 12px; background: var(--bg-header, var(--bg-base)); border-bottom: 1px solid var(--border); text-align: left; font-size: 11px; color: var(--text-muted); font-weight: 600; }
.task-table td { padding: 9px 12px; border-bottom: 1px solid var(--border-faint, var(--border)); }
.task-row:hover td { background: var(--bg-hover); cursor: pointer; }
.task-name { font-weight: 500; }
.task-cmd { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mono { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px; }
.small { font-size: 12px; color: var(--text-muted); }
.status-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.status-badge.pending   { background: var(--bg-hover); color: var(--text-muted); }
.status-badge.running   { background: rgba(56,139,253,.12); color: var(--accent); }
.status-badge.success   { background: rgba(63,185,80,.12); color: var(--success); }
.status-badge.failed    { background: rgba(248,81,73,.12); color: var(--error); }
.status-badge.partial   { background: rgba(210,153,34,.12); color: var(--warning); }
.status-badge.cancelled { background: var(--bg-hover); color: var(--text-muted); }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 160px; gap: 8px; color: var(--text-muted); }
.empty-state .icon { font-size: 32px; }
.spinner { width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
.spinner-sm { display: inline-block; width: 13px; height: 13px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
/* 弹窗 */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 100; display: flex; align-items: center; justify-content: center; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; width: 520px; max-height: 88vh; display: flex; flex-direction: column; overflow: hidden; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 14px; color: var(--text-primary); }
.modal-body { overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 12px; }
.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-group label { font-size: 12px; color: var(--text-muted); }
.form-group input, .form-group textarea, .form-select { padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input, var(--bg-base)); color: var(--text-primary); font-size: 13px; width: 100%; box-sizing: border-box; }
.form-group textarea { resize: vertical; font-family: 'Cascadia Code', 'Consolas', monospace; }
.host-check-list { display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; padding: 8px; background: var(--bg-input, var(--bg-base)); }
.host-check-item { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 4px; font-size: 12px; cursor: pointer; }
.host-check-item:hover { background: var(--bg-hover); }
.no-ssh { font-size: 10px; padding: 1px 5px; border-radius: 8px; background: rgba(248,81,73,.12); color: var(--error); }
.form-error { color: var(--error); font-size: 12px; padding: 6px 10px; background: rgba(248,81,73,.08); border-radius: 5px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; }
/* 详情抽屉 */
.drawer-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 100; display: flex; justify-content: flex-end; }
.drawer { width: 560px; background: var(--bg-card); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.drawer-header { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 14px; }
.drawer-header .close-btn { margin-left: auto; }
.drawer-body { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.detail-meta { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
.meta-k { color: var(--text-muted); min-width: 40px; display: inline-block; }
.running-tip { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--accent); }
.host-result { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.host-result.ok { border-color: rgba(63,185,80,.3); }
.host-result.err { border-color: rgba(248,81,73,.3); }
.host-result-head { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--bg-hover); font-size: 13px; }
.host-result-name { font-weight: 600; }
.rc-badge { margin-left: auto; font-size: 11px; padding: 1px 7px; border-radius: 8px; }
.rc-badge.ok  { background: rgba(63,185,80,.12); color: var(--success); }
.rc-badge.err { background: rgba(248,81,73,.12); color: var(--error); }
.host-result-err { padding: 8px 12px; color: var(--error); font-size: 12px; }
.output-pre { margin: 0; padding: 10px 12px; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px; line-height: 1.6; color: var(--text-primary); white-space: pre-wrap; word-break: break-all; background: var(--bg-base); max-height: 300px; overflow: auto; }
.output-pre.stderr { color: var(--warning); }
</style>
