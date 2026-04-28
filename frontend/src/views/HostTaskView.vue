<template>
  <div class="task-view">
    <div class="page-header">
      <div class="header-left">
        <h1>任务中心</h1>
        <span class="subtitle">Ansible Playbook 执行管理</span>
      </div>
      <div class="header-right">
        <button class="btn-primary" @click="showCreate = true">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建任务
        </button>
        <button class="btn-ghost" @click="fetchTasks">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
          刷新
        </button>
      </div>
    </div>

    <!-- Task list -->
    <div class="table-wrap">
      <div v-if="loading" class="loading-row"><div class="spinner"></div> 加载中…</div>
      <table v-else class="task-table">
        <thead><tr>
          <th>任务名称</th><th>Playbook</th><th>状态</th><th>返回码</th><th>创建时间</th><th>耗时</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-if="!tasks.length"><td colspan="7" class="empty">暂无任务记录，点击「新建任务」开始执行</td></tr>
          <tr v-for="t in tasks" :key="t.id" @click="viewTask(t)" class="task-row">
            <td class="name-cell">{{ t.name }}</td>
            <td class="mono small muted">{{ t.playbook }}</td>
            <td><span class="status-badge" :class="t.status">{{ STATUS_LABEL[t.status] || t.status }}</span></td>
            <td :class="{ 'col-warn': t.return_code !== 0 && t.return_code !== null }">
              {{ t.return_code ?? '—' }}
            </td>
            <td class="muted small">{{ fmtTime(t.created_at) }}</td>
            <td class="muted small">{{ duration(t) }}</td>
            <td>
              <button class="btn-icon" title="删除" @click.stop="deleteTask(t.id)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6m4-6v6"/></svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal-header">
          <span>新建 Ansible 任务</span>
          <button class="close-btn" @click="showCreate = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>任务名称</label>
            <input v-model="form.name" placeholder="我的任务" class="form-input" />
          </div>
          <div class="form-row">
            <label>Playbook 路径</label>
            <input v-model="form.playbook" placeholder="/etc/ansible/site.yml" class="form-input" list="pb-list" />
            <datalist id="pb-list">
              <option v-for="pb in playbooks" :key="pb" :value="pb" />
            </datalist>
          </div>
          <div class="form-row">
            <label>Inventory</label>
            <input v-model="form.inventory" placeholder="hosts 或 localhost," class="form-input" />
          </div>
          <div class="form-row">
            <label>Extra Vars (JSON)</label>
            <textarea v-model="form.extraVarsStr" placeholder='{"key": "value"}' class="form-textarea"></textarea>
          </div>
          <div class="form-row">
            <label>描述</label>
            <input v-model="form.description" placeholder="可选描述" class="form-input" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn-primary" @click="submitTask" :disabled="creating">
            {{ creating ? '执行中…' : '立即执行' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Output modal -->
    <div v-if="activeTask" class="modal-overlay" @click.self="activeTask = null">
      <div class="modal wide">
        <div class="modal-header">
          <span>{{ activeTask.name }}</span>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="status-badge" :class="activeTask.status">{{ STATUS_LABEL[activeTask.status] }}</span>
            <button class="close-btn" @click="activeTask = null">✕</button>
          </div>
        </div>
        <div class="modal-body">
          <pre class="output-pre">{{ activeTask.output || '（暂无输出）' }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { api } from '../api/index.js'

const STATUS_LABEL = { pending: '等待', running: '执行中', success: '成功', failed: '失败', cancelled: '已取消' }

const tasks     = ref([])
const playbooks = ref([])
const loading   = ref(false)
const showCreate = ref(false)
const creating  = ref(false)
const activeTask = ref(null)

const form = ref({ name: '', playbook: '', inventory: 'hosts', extraVarsStr: '', description: '' })

async function fetchTasks() {
  loading.value = true
  try { tasks.value = await api.ansibleTasks() } catch { tasks.value = [] }
  finally { loading.value = false }
}

async function fetchPlaybooks() {
  try { playbooks.value = await api.ansiblePlaybooks() } catch { playbooks.value = [] }
}

async function submitTask() {
  if (!form.value.name || !form.value.playbook) return
  creating.value = true
  try {
    let extra = {}
    try { extra = form.value.extraVarsStr ? JSON.parse(form.value.extraVarsStr) : {} } catch { extra = {} }
    await api.ansibleCreateTask({ name: form.value.name, playbook: form.value.playbook, inventory: form.value.inventory, extra_vars: extra, description: form.value.description })
    showCreate.value = false
    form.value = { name: '', playbook: '', inventory: 'hosts', extraVarsStr: '', description: '' }
    await fetchTasks()
  } catch (e) { alert(`创建失败: ${e}`) }
  finally { creating.value = false }
}

async function deleteTask(id) {
  if (!confirm('确认删除该任务记录？')) return
  try { await api.ansibleDeleteTask(id); await fetchTasks() } catch { }
}

async function viewTask(t) {
  if (t.status === 'running') {
    try { t = await api.ansibleGetTask(t.id) } catch { }
  }
  activeTask.value = t
}

function fmtTime(ts) {
  if (!ts) return '—'
  return ts.replace('T', ' ').replace('Z', '').slice(0, 16)
}

function duration(t) {
  if (!t.started_at || !t.finished_at) return '—'
  const s = Math.round((new Date(t.finished_at) - new Date(t.started_at)) / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s/60)}m${s%60}s`
}

let _timer = null
onMounted(() => { fetchTasks(); fetchPlaybooks(); _timer = setInterval(fetchTasks, 10000) })
onUnmounted(() => clearInterval(_timer))
</script>

<style scoped>
.task-view { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--bg-base); color: var(--text-primary); }
.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 12px; border-bottom: 1px solid rgba(255,255,255,0.07); flex-shrink: 0; }
.header-left h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
.subtitle { font-size: 12px; color: var(--text-muted, #6e7681); }
.header-right { display: flex; gap: 8px; }
.btn-primary { display: flex; align-items: center; gap: 5px; background: var(--accent, #388bfd); border: none; color: #fff; border-radius: 6px; padding: 6px 14px; font-size: 12px; cursor: pointer; font-weight: 500; }
.btn-ghost   { display: flex; align-items: center; gap: 5px; background: var(--bg-hover); border: 1px solid var(--border); color: var(--text-primary); border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer; }
.btn-icon    { background: none; border: none; color: var(--text-muted); cursor: pointer; padding: 3px; border-radius: 4px; }
.btn-icon:hover { color: #f85149; background: rgba(248,81,73,0.1); }

.table-wrap { flex: 1; overflow: auto; padding: 12px 20px; }
.loading-row { display: flex; align-items: center; gap: 8px; padding: 40px; color: var(--text-muted); justify-content: center; }
.spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.1); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.task-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.task-table th { text-align: left; padding: 8px 10px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg-base); }
.task-table td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); }
.task-row { cursor: pointer; }
.task-row:hover td { background: rgba(255,255,255,0.03); }
.empty { text-align: center; color: var(--text-muted); padding: 40px !important; }

.name-cell { font-weight: 500; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.status-badge { padding: 2px 8px; border-radius: 10px; font-size: 10.5px; font-weight: 500; }
.status-badge.pending  { background: rgba(255,255,255,0.08); color: var(--text-muted); }
.status-badge.running  { background: rgba(56,139,253,0.15);  color: #388bfd; animation: pulse 1.2s infinite; }
.status-badge.success  { background: rgba(63,185,80,0.15);   color: #3fb950; }
.status-badge.failed   { background: rgba(248,81,73,0.15);   color: #f85149; }
.status-badge.cancelled{ background: rgba(210,153,34,0.15);  color: #d29922; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.6} }

.mono  { font-family: 'Cascadia Code', 'Consolas', monospace; }
.small { font-size: 11px; }
.muted { color: var(--text-muted, #6e7681); }
.col-warn { color: #d29922; font-weight: 500; }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.55); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; width: 480px; max-height: 80vh; display: flex; flex-direction: column; }
.modal.wide { width: 760px; }
.modal-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,0.07); font-weight: 600; font-size: 14px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; }
.modal-body { overflow: auto; padding: 16px; }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 16px; border-top: 1px solid rgba(255,255,255,0.07); }
.form-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.form-row label { font-size: 11.5px; color: var(--text-muted); font-weight: 500; }
.form-input, .form-textarea { background: var(--bg-base); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); padding: 7px 10px; font-size: 12px; outline: none; }
.form-input:focus, .form-textarea:focus { border-color: var(--accent); }
.form-textarea { resize: vertical; min-height: 60px; font-family: 'Cascadia Code', 'Consolas', monospace; }
.output-pre { background: var(--bg-base); border-radius: 8px; padding: 14px; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11px; line-height: 1.7; color: var(--text-primary); white-space: pre-wrap; word-break: break-all; min-height: 200px; max-height: 55vh; overflow: auto; margin: 0; }
</style>
