<template>
  <div class="ticket-view">
    <div class="page-header">
      <div class="header-left">
        <h1>{{ config.title }}</h1>
        <span class="subtitle">{{ config.subtitle }}</span>
      </div>
      <div class="header-right">
        <button class="btn-primary" @click="openCreate">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建工单
        </button>
        <button class="btn-ghost" @click="fetchTickets">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
        </button>
      </div>
    </div>

    <!-- Status filter tabs -->
    <div class="status-tabs">
      <button v-for="s in STATUS_TABS" :key="s.key" class="st-tab" :class="{ active: filterStatus === s.key }" @click="filterStatus = s.key">
        {{ s.label }}
        <span class="st-count">{{ countByStatus(s.key) }}</span>
      </button>
    </div>

    <!-- Table -->
    <div class="table-wrap">
      <div v-if="loading" class="loading-row"><div class="spinner"></div></div>
      <table v-else class="ticket-table">
        <thead><tr>
          <th>编号</th><th>标题</th><th>优先级</th><th>状态</th><th>负责人</th><th>创建时间</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-if="!filteredTickets.length"><td colspan="7" class="empty">暂无工单</td></tr>
          <tr v-for="t in filteredTickets" :key="t.id" @click="viewTicket(t)" class="ticket-row">
            <td class="mono small accent">{{ t.no }}</td>
            <td class="title-cell">{{ t.title }}</td>
            <td><span class="pri-badge" :class="t.priority">{{ PRI_LABEL[t.priority] || t.priority }}</span></td>
            <td><span class="status-badge" :class="t.status">{{ ST_LABEL[t.status] || t.status }}</span></td>
            <td class="muted small">{{ t.assignee || '—' }}</td>
            <td class="muted small">{{ fmtTime(t.created_at) }}</td>
            <td class="action-cell" @click.stop>
              <button v-if="t.status==='pending'" class="btn-icon ok" title="批准" @click="approve(t)">✓</button>
              <button v-if="t.status==='pending'" class="btn-icon err" title="拒绝" @click="reject(t)">✗</button>
              <button v-if="['approved','in_progress'].includes(t.status)" class="btn-icon done" title="完成" @click="done(t)">⚑</button>
              <button class="btn-icon del" title="删除" @click="del(t)">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/></svg>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create Modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal-header">
          <span>新建{{ config.title }}</span>
          <button class="close-btn" @click="showCreate = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label>标题</label>
            <input v-model="form.title" class="form-input" :placeholder="config.titlePlaceholder" />
          </div>
          <div class="form-row">
            <label>优先级</label>
            <select v-model="form.priority" class="form-input">
              <option value="low">低</option>
              <option value="normal">普通</option>
              <option value="high">高</option>
              <option value="urgent">紧急</option>
            </select>
          </div>
          <div class="form-row">
            <label>负责人</label>
            <input v-model="form.assignee" class="form-input" placeholder="可选" />
          </div>
          <div v-for="field in config.extraFields" :key="field.key" class="form-row">
            <label>{{ field.label }}</label>
            <textarea v-if="field.type==='textarea'" v-model="form.extra[field.key]" class="form-textarea" :placeholder="field.placeholder"></textarea>
            <input v-else v-model="form.extra[field.key]" class="form-input" :placeholder="field.placeholder" />
          </div>
          <div class="form-row">
            <label>描述</label>
            <textarea v-model="form.description" class="form-textarea" placeholder="详细描述..."></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn-primary" @click="submitCreate" :disabled="creating">{{ creating ? '提交中…' : '提交工单' }}</button>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <div v-if="activeTicket" class="modal-overlay" @click.self="activeTicket = null">
      <div class="modal wide">
        <div class="modal-header">
          <span class="mono accent">{{ activeTicket.no }}</span>
          <span style="flex:1;margin-left:10px;font-size:14px;font-weight:600">{{ activeTicket.title }}</span>
          <span class="status-badge" :class="activeTicket.status">{{ ST_LABEL[activeTicket.status] }}</span>
          <button class="close-btn" @click="activeTicket = null">✕</button>
        </div>
        <div class="modal-body">
          <p class="desc-text">{{ activeTicket.description || '（无描述）' }}</p>
          <div v-if="activeTicket.extra && Object.keys(activeTicket.extra).length" class="extra-section">
            <div v-for="(v, k) in activeTicket.extra" :key="k" class="extra-row">
              <span class="extra-key">{{ k }}</span>
              <span>{{ v }}</span>
            </div>
          </div>
          <div v-if="activeTicket.history?.length" class="history-section">
            <div class="history-title">操作历史</div>
            <div v-for="h in activeTicket.history" :key="h.time" class="history-item">
              <span class="h-time muted small">{{ fmtTime(h.time) }}</span>
              <span class="h-status">{{ ST_LABEL[h.old_status] }} → {{ ST_LABEL[h.new_status] }}</span>
              <span v-if="h.comment" class="h-comment muted">{{ h.comment }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const props = defineProps({
  ticketType: { type: String, required: true },
  config: { type: Object, required: true },
})

const STATUS_TABS = [
  { key: '',            label: '全部' },
  { key: 'pending',     label: '待审批' },
  { key: 'approved',    label: '已批准' },
  { key: 'in_progress', label: '进行中' },
  { key: 'done',        label: '已完成' },
  { key: 'rejected',    label: '已拒绝' },
]
const ST_LABEL  = { pending: '待审批', approved: '已批准', rejected: '已拒绝', in_progress: '进行中', done: '已完成', cancelled: '已取消' }
const PRI_LABEL = { low: '低', normal: '普通', high: '高', urgent: '紧急' }

const tickets      = ref([])
const loading      = ref(false)
const showCreate   = ref(false)
const creating     = ref(false)
const activeTicket = ref(null)
const filterStatus = ref('')

const form = ref({ title: '', priority: 'normal', assignee: '', description: '', extra: {} })

const filteredTickets = computed(() =>
  filterStatus.value ? tickets.value.filter(t => t.status === filterStatus.value) : tickets.value
)

function countByStatus(s) {
  return s ? tickets.value.filter(t => t.status === s).length : tickets.value.length
}

async function fetchTickets() {
  loading.value = true
  try { tickets.value = await api.listTickets({ type: props.ticketType }) }
  catch { tickets.value = [] }
  finally { loading.value = false }
}

function openCreate() {
  form.value = { title: '', priority: 'normal', assignee: '', description: '', extra: {} }
  props.config.extraFields?.forEach(f => { form.value.extra[f.key] = '' })
  showCreate.value = true
}

async function submitCreate() {
  if (!form.value.title) return
  creating.value = true
  try {
    await api.createTicket({ type: props.ticketType, title: form.value.title, priority: form.value.priority, assignee: form.value.assignee, description: form.value.description, extra: form.value.extra })
    showCreate.value = false
    await fetchTickets()
  } catch (e) { alert(`提交失败: ${e}`) }
  finally { creating.value = false }
}

function viewTicket(t) { activeTicket.value = t }

async function approve(t) { await api.approveTicket(t.id); await fetchTickets() }
async function reject(t)  { const c = prompt('拒绝原因（可选）') ?? ''; await api.rejectTicket(t.id, c); await fetchTickets() }
async function done(t)    { await api.doneTicket(t.id); await fetchTickets() }
async function del(t)     { if (!confirm('确认删除？')) return; await api.deleteTicket(t.id); await fetchTickets() }

function fmtTime(ts) { return ts ? ts.replace('T', ' ').replace('Z', '').slice(0, 16) : '—' }

onMounted(fetchTickets)
</script>

<style scoped>
.ticket-view { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--bg-main, #0d1117); color: var(--text-primary, #e6edf3); }
.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 10px; border-bottom: 1px solid rgba(255,255,255,0.07); flex-shrink: 0; }
.header-left h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
.subtitle { font-size: 12px; color: var(--text-muted, #6e7681); }
.header-right { display: flex; gap: 8px; }
.btn-primary { display: flex; align-items: center; gap: 5px; background: var(--accent, #388bfd); border: none; color: #fff; border-radius: 6px; padding: 6px 14px; font-size: 12px; cursor: pointer; font-weight: 500; }
.btn-ghost { display: flex; align-items: center; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: var(--text-primary); border-radius: 6px; padding: 6px 10px; font-size: 12px; cursor: pointer; }

.status-tabs { display: flex; gap: 0; padding: 0 20px; border-bottom: 1px solid rgba(255,255,255,0.06); flex-shrink: 0; }
.st-tab { padding: 9px 14px; background: none; border: none; color: var(--text-muted); font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 5px; border-bottom: 2px solid transparent; transition: all .15s; }
.st-tab:hover { color: var(--text-primary); }
.st-tab.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 500; }
.st-count { font-size: 10px; background: rgba(255,255,255,0.1); padding: 1px 5px; border-radius: 8px; }

.table-wrap { flex: 1; overflow: auto; padding: 10px 20px; }
.loading-row { display: flex; align-items: center; justify-content: center; padding: 40px; }
.spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.1); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.ticket-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ticket-table th { text-align: left; padding: 8px 10px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid rgba(255,255,255,0.08); position: sticky; top: 0; background: var(--bg-main, #0d1117); }
.ticket-table td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); vertical-align: middle; }
.ticket-row { cursor: pointer; }
.ticket-row:hover td { background: rgba(255,255,255,0.03); }
.empty { text-align: center; color: var(--text-muted); padding: 40px !important; }
.title-cell { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.accent { color: var(--accent, #388bfd); }

.pri-badge { padding: 2px 7px; border-radius: 8px; font-size: 10.5px; }
.pri-badge.low    { background: rgba(255,255,255,0.06); color: var(--text-muted); }
.pri-badge.normal { background: rgba(56,139,253,0.1);  color: #388bfd; }
.pri-badge.high   { background: rgba(210,153,34,0.1);  color: #d29922; }
.pri-badge.urgent { background: rgba(248,81,73,0.1);   color: #f85149; }

.status-badge { padding: 2px 8px; border-radius: 8px; font-size: 10.5px; font-weight: 500; }
.status-badge.pending     { background: rgba(210,153,34,0.12); color: #d29922; }
.status-badge.approved    { background: rgba(63,185,80,0.12);  color: #3fb950; }
.status-badge.rejected    { background: rgba(248,81,73,0.12);  color: #f85149; }
.status-badge.in_progress { background: rgba(56,139,253,0.12); color: #388bfd; }
.status-badge.done        { background: rgba(255,255,255,0.08); color: var(--text-muted); }
.status-badge.cancelled   { background: rgba(255,255,255,0.06); color: var(--text-muted); }

.action-cell { display: flex; gap: 4px; align-items: center; }
.btn-icon { background: none; border: none; cursor: pointer; padding: 4px 6px; border-radius: 4px; color: var(--text-muted); font-size: 13px; }
.btn-icon.ok:hover   { color: #3fb950; background: rgba(63,185,80,0.1); }
.btn-icon.err:hover  { color: #f85149; background: rgba(248,81,73,0.1); }
.btn-icon.done:hover { color: #388bfd; background: rgba(56,139,253,0.1); }
.btn-icon.del:hover  { color: #f85149; background: rgba(248,81,73,0.1); }

.mono  { font-family: 'JetBrains Mono', monospace; }
.small { font-size: 11px; }
.muted { color: var(--text-muted, #6e7681); }

/* Modal */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.55); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal { background: var(--bg-card, #161b22); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; width: 480px; max-height: 80vh; display: flex; flex-direction: column; }
.modal.wide { width: 600px; }
.modal-header { display: flex; align-items: center; gap: 8px; padding: 14px 16px; border-bottom: 1px solid rgba(255,255,255,0.07); font-weight: 600; font-size: 13px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; margin-left: auto; }
.modal-body { overflow: auto; padding: 16px; }
.modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 16px; border-top: 1px solid rgba(255,255,255,0.07); }
.form-row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 11px; }
.form-row label { font-size: 11.5px; color: var(--text-muted); font-weight: 500; }
.form-input  { background: var(--bg-main, #0d1117); border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; color: var(--text-primary); padding: 7px 10px; font-size: 12px; outline: none; }
.form-textarea { background: var(--bg-main, #0d1117); border: 1px solid rgba(255,255,255,0.12); border-radius: 6px; color: var(--text-primary); padding: 7px 10px; font-size: 12px; outline: none; resize: vertical; min-height: 70px; }
.form-input:focus, .form-textarea:focus { border-color: var(--accent); }

.desc-text { font-size: 12.5px; color: var(--text-muted); margin-bottom: 12px; white-space: pre-wrap; }
.extra-section { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.extra-row { display: flex; gap: 10px; font-size: 12px; }
.extra-key { color: var(--text-muted); min-width: 80px; font-weight: 500; }
.history-section { border-top: 1px solid rgba(255,255,255,0.07); padding-top: 12px; }
.history-title { font-size: 11.5px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; }
.history-item { display: flex; gap: 10px; font-size: 11.5px; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.04); }
.h-status { font-weight: 500; }
.h-comment { flex: 1; }
</style>
