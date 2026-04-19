<template>
  <div class="cron-view">
    <div class="page-header">
      <div class="header-left">
        <h1>定时任务</h1>
        <span class="subtitle">Ansible Playbook 定时调度</span>
      </div>
      <div class="header-right">
        <button class="btn-primary" @click="openCreate">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建定时任务
        </button>
        <button class="btn-ghost" @click="fetchCrons">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
          刷新
        </button>
      </div>
    </div>

    <div class="table-wrap">
      <div v-if="loading" class="loading-row"><div class="spinner"></div> 加载中…</div>
      <table v-else class="cron-table">
        <thead><tr>
          <th>名称</th><th>Cron</th><th>Playbook</th><th>状态</th><th>上次执行</th><th>最后结果</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-if="!crons.length"><td colspan="7" class="empty">暂无定时任务</td></tr>
          <tr v-for="c in crons" :key="c.id">
            <td class="name-cell">{{ c.name }}</td>
            <td><code class="cron-code">{{ c.cron }}</code></td>
            <td class="mono small muted">{{ c.playbook }}</td>
            <td>
              <span class="toggle-switch" :class="{ on: c.enabled }" @click="toggleCron(c)">
                {{ c.enabled ? '启用' : '停用' }}
              </span>
            </td>
            <td class="muted small">{{ c.last_run ? fmtTime(c.last_run) : '—' }}</td>
            <td>
              <span v-if="c.last_status" class="status-badge" :class="c.last_status">{{ STATUS_LABEL[c.last_status] || c.last_status }}</span>
              <span v-else class="muted">—</span>
            </td>
            <td class="action-cell">
              <button class="btn-icon run" title="立即执行" @click="runNow(c)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              </button>
              <button class="btn-icon edit" title="编辑" @click="openEdit(c)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
              </button>
              <button class="btn-icon del" title="删除" @click="deleteCron(c.id)">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/></svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create / Edit Modal -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ editId ? '编辑定时任务' : '新建定时任务' }}</span>
          <button class="close-btn" @click="showModal = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>任务名称</label>
            <input v-model="form.name" class="form-input" placeholder="我的定时任务" />
          </div>
          <div class="form-row">
            <label>Cron 表达式</label>
            <input v-model="form.cron" class="form-input" placeholder="0 9 * * *" />
            <div class="cron-hint">分 时 日 月 星期 — 例：每天9点 = <code>0 9 * * *</code></div>
          </div>
          <div class="form-row">
            <label>Playbook 路径</label>
            <input v-model="form.playbook" class="form-input" placeholder="/etc/ansible/site.yml" list="pb-list2" />
            <datalist id="pb-list2">
              <option v-for="pb in playbooks" :key="pb" :value="pb" />
            </datalist>
          </div>
          <div class="form-row">
            <label>Inventory</label>
            <input v-model="form.inventory" class="form-input" placeholder="hosts" />
          </div>
          <div class="form-row">
            <label>Extra Vars (JSON)</label>
            <textarea v-model="form.extraVarsStr" class="form-textarea" placeholder='{"key": "value"}'></textarea>
          </div>
          <div class="form-row">
            <label>状态</label>
            <label class="checkbox-row"><input type="checkbox" v-model="form.enabled" /> 启用</label>
          </div>
          <div class="form-row">
            <label>描述</label>
            <input v-model="form.description" class="form-input" placeholder="可选" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="showModal = false">取消</button>
          <button class="btn-primary" @click="submitCron" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api/index.js'

const STATUS_LABEL = { pending: '等待', running: '执行中', success: '成功', failed: '失败' }

const crons     = ref([])
const playbooks = ref([])
const loading   = ref(false)
const showModal = ref(false)
const saving    = ref(false)
const editId    = ref(null)
const form      = ref({ name: '', cron: '0 9 * * *', playbook: '', inventory: 'hosts', extraVarsStr: '', enabled: true, description: '' })

async function fetchCrons() {
  loading.value = true
  try { crons.value = await api.ansibleCrons() } catch { crons.value = [] }
  finally { loading.value = false }
}

async function fetchPlaybooks() {
  try { playbooks.value = await api.ansiblePlaybooks() } catch { playbooks.value = [] }
}

function openCreate() { editId.value = null; form.value = { name: '', cron: '0 9 * * *', playbook: '', inventory: 'hosts', extraVarsStr: '', enabled: true, description: '' }; showModal.value = true }
function openEdit(c) {
  editId.value = c.id
  form.value = { name: c.name, cron: c.cron, playbook: c.playbook, inventory: c.inventory, extraVarsStr: c.extra_vars ? JSON.stringify(c.extra_vars) : '', enabled: c.enabled, description: c.description || '' }
  showModal.value = true
}

async function submitCron() {
  if (!form.value.name || !form.value.cron || !form.value.playbook) return
  saving.value = true
  try {
    let extra = {}
    try { extra = form.value.extraVarsStr ? JSON.parse(form.value.extraVarsStr) : {} } catch { }
    const payload = { name: form.value.name, cron: form.value.cron, playbook: form.value.playbook, inventory: form.value.inventory, extra_vars: extra, enabled: form.value.enabled, description: form.value.description }
    if (editId.value) await api.ansibleUpdateCron(editId.value, payload)
    else await api.ansibleCreateCron(payload)
    showModal.value = false
    await fetchCrons()
  } catch (e) { alert(`保存失败: ${e}`) }
  finally { saving.value = false }
}

async function toggleCron(c) {
  try {
    await api.ansibleUpdateCron(c.id, { ...c, enabled: !c.enabled })
    await fetchCrons()
  } catch { }
}

async function runNow(c) {
  try { await api.ansibleRunCron(c.id); await fetchCrons() } catch (e) { alert(`触发失败: ${e}`) }
}

async function deleteCron(id) {
  if (!confirm('确认删除？')) return
  try { await api.ansibleDeleteCron(id); await fetchCrons() } catch { }
}

function fmtTime(ts) { return ts ? ts.replace('T', ' ').replace('Z', '').slice(0, 16) : '—' }

onMounted(() => { fetchCrons(); fetchPlaybooks() })
</script>

<style scoped>
.cron-view { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--bg-main, #0d1117); color: var(--text-primary, #e6edf3); }
.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 12px; border-bottom: 1px solid rgba(255,255,255,0.07); flex-shrink: 0; }
.header-left h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
.subtitle { font-size: 12px; color: var(--text-muted, #6e7681); }
.header-right { display: flex; gap: 8px; }
.btn-primary { display: flex; align-items: center; gap: 5px; background: var(--accent, #388bfd); border: none; color: #fff; border-radius: 6px; padding: 6px 14px; font-size: 12px; cursor: pointer; font-weight: 500; }
.btn-ghost   { display: flex; align-items: center; gap: 5px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text-primary); border-radius: 6px; padding: 6px 12px; font-size: 12px; cursor: pointer; }

.table-wrap { flex: 1; overflow: auto; padding: 12px 20px; }
.loading-row { display: flex; align-items: center; gap: 8px; padding: 40px; justify-content: center; color: var(--text-muted); }
.spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.1); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.cron-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.cron-table th { text-align: left; padding: 8px 10px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid rgba(255,255,255,0.08); position: sticky; top: 0; background: var(--bg-main, #0d1117); }
.cron-table td { padding: 9px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); vertical-align: middle; }
.cron-table tr:hover td { background: rgba(255,255,255,0.03); }
.empty { text-align: center; color: var(--text-muted); padding: 40px !important; }

.name-cell { font-weight: 500; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cron-code { font-family: 'JetBrains Mono', monospace; background: rgba(56,139,253,0.08); color: #388bfd; border: 1px solid rgba(56,139,253,0.2); padding: 2px 7px; border-radius: 5px; font-size: 11px; }
.cron-hint { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.cron-hint code { font-family: 'JetBrains Mono', monospace; color: #388bfd; }

.toggle-switch { padding: 2px 10px; border-radius: 10px; font-size: 10.5px; font-weight: 500; cursor: pointer; user-select: none; }
.toggle-switch.on  { background: rgba(63,185,80,0.15);  color: #3fb950; border: 1px solid rgba(63,185,80,0.3); }
.toggle-switch:not(.on) { background: rgba(255,255,255,0.06); color: var(--text-muted); border: 1px solid rgba(255,255,255,0.12); }

.status-badge { padding: 2px 8px; border-radius: 10px; font-size: 10.5px; font-weight: 500; }
.status-badge.success { background: rgba(63,185,80,0.15); color: #3fb950; }
.status-badge.failed  { background: rgba(248,81,73,0.15); color: #f85149; }
.status-badge.running { background: rgba(56,139,253,0.15); color: #388bfd; }

.action-cell { display: flex; gap: 6px; }
.btn-icon { background: none; border: none; cursor: pointer; padding: 4px; border-radius: 4px; color: var(--text-muted); }
.btn-icon.run:hover  { color: #3fb950; background: rgba(63,185,80,0.1); }
.btn-icon.edit:hover { color: #388bfd; background: rgba(56,139,253,0.1); }
.btn-icon.del:hover  { color: #f85149; background: rgba(248,81,73,0.1); }

.mono  { font-family: 'JetBrains Mono', monospace; }
.small { font-size: 11px; }
.muted { color: var(--text-muted, #6e7681); }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.55); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: var(--bg-card, #161b22); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; width: 480px; max-height: 80vh; display: flex; flex-direction: column; }
.modal-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,0.07); font-weight: 600; font-size: 14px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; }
.modal-body { overflow: auto; padding: 16px; }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 16px; border-top: 1px solid rgba(255,255,255,0.07); }
.form-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.form-row label { font-size: 11.5px; color: var(--text-muted); font-weight: 500; }
.form-input, .form-textarea { background: var(--bg-main, #0d1117); border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; color: var(--text-primary); padding: 7px 10px; font-size: 12px; outline: none; }
.form-input:focus, .form-textarea:focus { border-color: var(--accent); }
.form-textarea { resize: vertical; min-height: 60px; font-family: 'JetBrains Mono', monospace; }
.checkbox-row { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-primary); cursor: pointer; }
</style>
