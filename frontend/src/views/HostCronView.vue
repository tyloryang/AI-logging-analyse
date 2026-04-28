<template>
  <div class="cron-view">
    <div class="cron-header">
      <div class="header-left">
        <h2>定时任务</h2>
        <span class="subtitle">基于 SSH 的内置计划执行</span>
      </div>
      <button class="btn btn-primary" @click="openCreate">+ 新建定时任务</button>
    </div>

    <div class="table-wrap">
      <div v-if="loading" class="empty-state"><div class="spinner"></div></div>
      <div v-else-if="!crons.length" class="empty-state">
        <span class="icon">⏰</span><p>暂无定时任务</p>
      </div>
      <table v-else class="cron-table">
        <thead>
          <tr>
            <th>名称</th><th>命令</th><th>Cron</th><th>目标</th><th>状态</th><th>上次运行</th><th>上次结果</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in crons" :key="c.id">
            <td class="cron-name">{{ c.name }}</td>
            <td class="cron-cmd mono">{{ c.command }}</td>
            <td class="mono small">{{ c.cron }}</td>
            <td class="small">{{ targetLabel(c) }}</td>
            <td>
              <span class="status-badge" :class="c.enabled ? 'enabled' : 'disabled'">
                {{ c.enabled ? '启用' : '停用' }}
              </span>
            </td>
            <td class="small">{{ fmt(c.last_run) }}</td>
            <td>
              <span v-if="c.last_status" class="status-badge" :class="c.last_status">
                {{ STATUS[c.last_status] || c.last_status }}
              </span>
              <span v-else class="small">—</span>
            </td>
            <td class="actions-cell">
              <button class="btn btn-xs btn-outline" @click="toggleEnabled(c)" :title="c.enabled ? '停用' : '启用'">
                {{ c.enabled ? '停用' : '启用' }}
              </button>
              <button class="btn btn-xs btn-primary" @click="runNow(c)" :disabled="runningId === c.id">
                <span v-if="runningId === c.id" class="spinner-sm"></span>
                {{ runningId === c.id ? '执行中' : '▶ 立即' }}
              </button>
              <button class="btn btn-xs btn-outline" @click="openEdit(c)">编辑</button>
              <button class="btn btn-xs btn-danger" @click="deleteCron(c.id)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 创建/编辑弹窗 -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ editId ? '编辑定时任务' : '新建定时任务' }}</span>
          <button class="close-btn" @click="showModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-group required"><label>任务名称</label><input v-model="form.name" placeholder="e.g. 每日磁盘检查" /></div>
          <div class="form-group required">
            <label>执行命令</label>
            <textarea v-model="form.command" rows="3" placeholder="df -h&#10;free -m" />
          </div>
          <div class="form-group required">
            <label>Cron 表达式 <span class="form-hint">分 时 日 月 周</span></label>
            <input v-model="form.cron" placeholder="0 9 * * *" />
            <div class="cron-presets">
              <button v-for="p in PRESETS" :key="p.v" class="preset-btn" @click="form.cron = p.v">{{ p.label }}</button>
            </div>
          </div>
          <div class="form-group">
            <label>目标主机</label>
            <select v-model="form.mode" class="form-select">
              <option value="group">按分组</option>
              <option value="hosts">指定主机</option>
            </select>
          </div>
          <div v-if="form.mode === 'group'" class="form-group">
            <label>选择分组</label>
            <select v-model="form.host_group" class="form-select">
              <option value="">请选择...</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.host_count || 0 }}台）</option>
            </select>
          </div>
          <div v-else class="form-group">
            <label>选择主机</label>
            <div class="host-check-list">
              <label v-for="h in cmdbHosts" :key="h.id" class="host-check-item">
                <input type="checkbox" :value="h.id" v-model="form.host_ids" />
                <span>{{ h.hostname }}</span><span class="mono small">{{ h.ip }}</span>
                <span v-if="!h.ssh_saved" class="no-ssh">无SSH</span>
              </label>
            </div>
          </div>
          <div class="form-row">
            <div class="form-group"><label>超时（秒）</label><input v-model.number="form.timeout" type="number" min="5" /></div>
            <div class="form-group" style="justify-content:flex-end;padding-top:18px">
              <label class="check-label"><input type="checkbox" v-model="form.enabled" /> 启用</label>
            </div>
          </div>
          <div class="form-group"><label>描述（可选）</label><input v-model="form.description" /></div>
          <div v-if="formError" class="form-error">{{ formError }}</div>
          <div class="form-actions">
            <button class="btn btn-outline" @click="showModal = false">取消</button>
            <button class="btn btn-primary" @click="save" :disabled="saving">
              <span v-if="saving" class="spinner-sm"></span>
              {{ editId ? '保存' : '创建' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/index.js'

const STATUS  = { pending: '等待', running: '执行中', success: '成功', failed: '失败', partial: '部分失败' }
const PRESETS = [
  { label: '每天 09:00', v: '0 9 * * *' },
  { label: '每小时',     v: '0 * * * *' },
  { label: '每 5 分钟',  v: '*/5 * * * *' },
  { label: '每周一 09:00', v: '0 9 * * 1' },
  { label: '每月1日',    v: '0 9 1 * *' },
]

const crons     = ref([])
const groups    = ref([])
const cmdbHosts = ref([])
const loading   = ref(false)
const runningId = ref('')
const showModal = ref(false)
const editId    = ref('')
const saving    = ref(false)
const formError = ref('')

const defaultForm = () => ({
  name: '', command: '', cron: '0 9 * * *',
  mode: 'group', host_group: '', host_ids: [],
  timeout: 60, enabled: true, description: '',
})
const form = ref(defaultForm())

function fmt(ts) { return ts ? ts.replace('T', ' ').slice(0, 16) : '—' }

function targetLabel(c) {
  if (c.host_group) {
    const g = groups.value.find(g => g.id === c.host_group)
    return g ? `分组: ${g.name}` : `分组: ${c.host_group}`
  }
  return c.host_ids?.length ? `${c.host_ids.length} 台主机` : '未配置'
}

async function fetchCrons() {
  loading.value = true
  try { crons.value = await api.ansibleCrons() } catch { crons.value = [] }
  finally { loading.value = false }
}

async function runNow(c) {
  runningId.value = c.id
  try {
    await api.ansibleRunCron(c.id)
    await fetchCrons()
  } catch (e) {
    alert(`触发失败: ${typeof e === 'string' ? e : JSON.stringify(e)}`)
  } finally {
    runningId.value = ''
  }
}

async function toggleEnabled(c) {
  await api.ansibleUpdateCron(c.id, { ...c, enabled: !c.enabled, mode: c.host_group ? 'group' : 'hosts' }).catch(() => {})
  await fetchCrons()
}

async function deleteCron(id) {
  if (!confirm('确认删除该定时任务？')) return
  await api.ansibleDeleteCron(id).catch(() => {})
  await fetchCrons()
}

function openCreate() {
  editId.value  = ''
  form.value    = defaultForm()
  formError.value = ''
  showModal.value = true
}

function openEdit(c) {
  editId.value = c.id
  formError.value = ''
  form.value = {
    name: c.name, command: c.command, cron: c.cron,
    mode: c.host_group ? 'group' : 'hosts',
    host_group: c.host_group || '',
    host_ids:   c.host_ids || [],
    timeout:    c.timeout || 60,
    enabled:    c.enabled,
    description: c.description || '',
  }
  showModal.value = true
}

async function save() {
  formError.value = ''
  const f = form.value
  if (!f.name.trim())    { formError.value = '任务名称不能为空'; return }
  if (!f.command.trim()) { formError.value = '执行命令不能为空'; return }
  if (!f.cron.trim())    { formError.value = 'Cron 表达式不能为空'; return }
  saving.value = true
  const payload = {
    name: f.name, command: f.command, cron: f.cron,
    host_group:  f.mode === 'group' ? f.host_group : '',
    host_ids:    f.mode === 'hosts' ? f.host_ids : [],
    timeout:     f.timeout, enabled: f.enabled, description: f.description,
  }
  try {
    if (editId.value) await api.ansibleUpdateCron(editId.value, payload)
    else await api.ansibleCreateCron(payload)
    showModal.value = false
    await fetchCrons()
  } catch (e) {
    formError.value = typeof e === 'string' ? e : '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  Promise.all([
    fetchCrons(),
    api.listGroups().then(r => { groups.value = r.data || [] }).catch(() => {}),
    api.getHosts().then(r => { cmdbHosts.value = r.data || [] }).catch(() => {}),
  ])
})
</script>

<style scoped>
.cron-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; padding: 20px; gap: 14px; background: var(--bg-base); color: var(--text-primary); }
.cron-header { display: flex; justify-content: space-between; align-items: center; }
.header-left h2 { font-size: 18px; font-weight: 600; margin: 0; }
.subtitle { font-size: 12px; color: var(--text-muted); margin-left: 8px; }
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 6px 14px; border-radius: 6px; border: 1px solid transparent; font-size: 13px; cursor: pointer; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: #fff; }
.btn-outline { background: transparent; border-color: var(--border); color: var(--text-primary); }
.btn-danger  { background: rgba(248,81,73,.08); color: var(--error); border-color: rgba(248,81,73,.3); }
.btn-xs { padding: 2px 8px; font-size: 11px; }
.table-wrap { flex: 1; overflow: auto; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.cron-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cron-table thead { position: sticky; top: 0; }
.cron-table th { padding: 9px 12px; background: var(--bg-header, var(--bg-base)); border-bottom: 1px solid var(--border); text-align: left; font-size: 11px; color: var(--text-muted); font-weight: 600; white-space: nowrap; }
.cron-table td { padding: 9px 12px; border-bottom: 1px solid var(--border-faint, var(--border)); white-space: nowrap; }
.cron-name { font-weight: 500; }
.cron-cmd { max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
.mono { font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px; }
.small { font-size: 12px; color: var(--text-muted); }
.actions-cell { display: flex; gap: 4px; }
.status-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.status-badge.enabled  { background: rgba(63,185,80,.12); color: var(--success); }
.status-badge.disabled { background: var(--bg-hover); color: var(--text-muted); }
.status-badge.success  { background: rgba(63,185,80,.12); color: var(--success); }
.status-badge.failed   { background: rgba(248,81,73,.12); color: var(--error); }
.status-badge.partial  { background: rgba(210,153,34,.12); color: var(--warning); }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 160px; gap: 8px; color: var(--text-muted); }
.empty-state .icon { font-size: 32px; }
.spinner { width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
.spinner-sm { display: inline-block; width: 12px; height: 12px; border: 2px solid rgba(255,255,255,.4); border-top-color: #fff; border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
/* 弹窗 */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 100; display: flex; align-items: center; justify-content: center; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; width: 540px; max-height: 88vh; display: flex; flex-direction: column; overflow: hidden; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 14px; color: var(--text-primary); }
.modal-body { overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 12px; }
.form-group { display: flex; flex-direction: column; gap: 5px; }
.form-group.required label::after { content: ' *'; color: var(--error); }
.form-group label { font-size: 12px; color: var(--text-muted); }
.form-hint { font-weight: 400; font-style: italic; }
.form-group input, .form-group textarea, .form-select { padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input, var(--bg-base)); color: var(--text-primary); font-size: 13px; width: 100%; box-sizing: border-box; }
.form-group textarea { resize: vertical; font-family: 'Cascadia Code', 'Consolas', monospace; }
.form-row { display: flex; gap: 12px; }
.form-row .form-group { flex: 1; }
.check-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; color: var(--text-primary); }
.cron-presets { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; }
.preset-btn { padding: 2px 8px; border-radius: 10px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); font-size: 11px; cursor: pointer; }
.preset-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.host-check-list { display: flex; flex-direction: column; gap: 3px; max-height: 160px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; padding: 6px; background: var(--bg-input, var(--bg-base)); }
.host-check-item { display: flex; align-items: center; gap: 8px; padding: 3px 6px; border-radius: 4px; font-size: 12px; cursor: pointer; }
.host-check-item:hover { background: var(--bg-hover); }
.no-ssh { font-size: 10px; padding: 1px 5px; border-radius: 8px; background: rgba(248,81,73,.12); color: var(--error); }
.form-error { color: var(--error); font-size: 12px; padding: 6px 10px; background: rgba(248,81,73,.08); border-radius: 5px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; }
</style>
