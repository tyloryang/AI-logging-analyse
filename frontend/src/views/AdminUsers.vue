<template>
  <div class="admin-page">
    <div class="page-header">
      <h2>👥 用户管理</h2>
      <button class="btn btn-primary" @click="showCreateModal = true">+ 新建用户</button>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <select v-model="filterStatus" @change="loadUsers">
        <option value="">全部状态</option>
        <option value="pending">待审批</option>
        <option value="active">正常</option>
        <option value="locked">已锁定</option>
        <option value="disabled">已禁用</option>
      </select>
    </div>

    <!-- 用户表格 -->
    <div class="table-wrap">
      <div v-if="loading" class="empty-state"><div class="spinner"></div><p>加载中...</p></div>
      <table v-else class="user-table">
        <thead>
          <tr>
            <th>用户名</th><th>邮箱</th><th>昵称</th><th>角色</th><th>状态</th><th>注册时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id">
            <td class="username">{{ u.username }}</td>
            <td class="small">{{ u.email }}</td>
            <td>{{ u.display_name }}</td>
            <td><span class="role-badge" :class="{ admin: u.is_superuser }">{{ u.is_superuser ? '管理员' : '普通用户' }}</span></td>
            <td><span class="status-badge" :class="u.status">{{ statusLabel(u.status) }}</span></td>
            <td class="small">{{ u.created_at.slice(0, 10) }}</td>
            <td class="actions-cell">
              <button v-if="u.status === 'pending'" class="btn btn-xs btn-ok" @click="approve(u)">审批</button>
              <button v-if="u.status === 'locked'" class="btn btn-xs btn-ok" @click="unlock(u)">解锁</button>
              <button class="btn btn-xs btn-outline" @click="openPerms(u)">权限</button>
              <button v-if="!u.is_superuser" class="btn btn-xs btn-group-assign" @click="openGroupAssign(u)" title="分配 CMDB 分组">分组</button>
              <button v-if="u.status !== 'disabled' && u.id !== authStore.user?.id"
                      class="btn btn-xs btn-danger" @click="disable(u)">禁用</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 创建用户弹窗 -->
    <transition name="fade">
      <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
        <div class="modal-box">
          <div class="modal-header"><span>新建用户</span><button class="btn btn-xs btn-outline" @click="showCreateModal = false">✕</button></div>
          <div class="modal-body">
            <div class="form-grid">
              <div class="form-group"><label>用户名</label><input v-model="createForm.username" placeholder="username" /></div>
              <div class="form-group"><label>邮箱</label><input v-model="createForm.email" type="email" placeholder="email@example.com" /></div>
              <div class="form-group"><label>昵称</label><input v-model="createForm.display_name" placeholder="显示名称" /></div>
              <div class="form-group"><label>密码</label><input v-model="createForm.password" type="password" placeholder="至少8位" /></div>
            </div>
            <label class="check-row"><input type="checkbox" v-model="createForm.is_superuser" /> 设为管理员</label>
            <div v-if="createError" class="form-error">{{ createError }}</div>
            <button class="btn btn-primary" style="margin-top:12px" @click="createUser" :disabled="createLoading">
              {{ createLoading ? '创建中...' : '创建用户' }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 权限分配弹窗 -->
    <transition name="fade">
      <div v-if="showPermsModal" class="modal-overlay" @click.self="showPermsModal = false">
        <div class="modal-box modal-wide">
          <div class="modal-header">
            <span>权限设置 · {{ permUser?.username }}</span>
            <button class="btn btn-xs btn-outline" @click="showPermsModal = false">✕</button>
          </div>
          <div class="modal-body">
            <div v-if="permsLoading" class="empty-state"><div class="spinner"></div></div>
            <div v-else>
              <div class="perm-table">
                <div class="perm-row header">
                  <span>模块</span><span>无权限</span><span>只读</span><span>可操作</span>
                </div>
                <div v-for="p in editPerms" :key="p.module_id" class="perm-row">
                  <span class="mod-name">{{ p.name }}</span>
                  <label><input type="radio" :name="p.module_id" value="none" v-model="p.level" /></label>
                  <label><input type="radio" :name="p.module_id" value="view" v-model="p.level" /></label>
                  <label><input type="radio" :name="p.module_id" value="operate" v-model="p.level" /></label>
                </div>
              </div>
              <div v-if="permsError" class="form-error" style="margin-top:8px">{{ permsError }}</div>
              <button class="btn btn-primary" style="margin-top:14px" @click="savePerms" :disabled="permsSaving">
                {{ permsSaving ? '保存中...' : '保存权限' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- CMDB 分组分配弹窗 -->
    <transition name="fade">
      <div v-if="showGroupModal" class="modal-overlay" @click.self="showGroupModal = false">
        <div class="modal-box modal-wide">
          <div class="modal-header">
            <span>CMDB 分组权限 · {{ groupUser?.username }}</span>
            <button class="btn btn-xs btn-outline" @click="showGroupModal = false">✕</button>
          </div>
          <div class="modal-body">
            <p class="group-hint">
              普通用户只能查看、导出、同步其分配分组内的主机。未分配任何分组则无法看到任何主机。
            </p>
            <div v-if="groupLoading" class="empty-state"><div class="spinner"></div></div>
            <div v-else class="group-check-list">
              <label v-for="g in allGroups" :key="g.id" class="group-check-item"
                     :class="{ selected: selectedGroupIds.includes(g.id) }">
                <input type="checkbox" :value="g.id" v-model="selectedGroupIds" />
                <span class="group-check-name">{{ g.name }}</span>
                <span class="group-check-count">{{ g.host_count || 0 }} 台</span>
              </label>
              <div v-if="!allGroups.length" class="empty-state" style="height:80px">
                暂无分组，请先在 CMDB → 分组管理中创建
              </div>
            </div>
            <div v-if="groupError" class="form-error" style="margin-top:8px">{{ groupError }}</div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:14px">
              <span style="font-size:12px;color:var(--text-muted)">
                已选 {{ selectedGroupIds.length }} / {{ allGroups.length }} 个分组
              </span>
              <div style="display:flex;gap:8px">
                <button class="btn btn-outline btn-xs" @click="selectedGroupIds = []">清空</button>
                <button class="btn btn-outline btn-xs" @click="selectedGroupIds = allGroups.map(g=>g.id)">全选</button>
                <button class="btn btn-primary" @click="saveGroups" :disabled="groupSaving">
                  {{ groupSaving ? '保存中...' : '保存分组' }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()
const users = ref([])
const loading = ref(false)
const filterStatus = ref('')

const showCreateModal = ref(false)
const createForm = reactive({ username: '', email: '', display_name: '', password: '', is_superuser: false })
const createError = ref('')
const createLoading = ref(false)

const showPermsModal = ref(false)
const permUser = ref(null)
const editPerms = ref([])
const permsLoading = ref(false)
const permsError = ref('')
const permsSaving = ref(false)

const STATUS_LABELS = { pending: '待审批', active: '正常', locked: '已锁定', disabled: '已禁用' }
function statusLabel(s) { return STATUS_LABELS[s] || s }

async function loadUsers() {
  loading.value = true
  try {
    const params = filterStatus.value ? { status: filterStatus.value } : {}
    users.value = await api.adminListUsers(params)
  } finally {
    loading.value = false
  }
}

async function approve(u) {
  await api.adminApproveUser(u.id)
  await loadUsers()
}

async function unlock(u) {
  await api.adminUnlockUser(u.id)
  await loadUsers()
}

async function disable(u) {
  if (!confirm(`确认禁用用户 ${u.username}？`)) return
  await api.adminDisableUser(u.id)
  await loadUsers()
}

async function createUser() {
  createLoading.value = true
  createError.value = ''
  try {
    await api.adminCreateUser(createForm)
    showCreateModal.value = false
    Object.assign(createForm, { username: '', email: '', display_name: '', password: '', is_superuser: false })
    await loadUsers()
  } catch (e) {
    createError.value = typeof e === 'string' ? e : '创建失败'
  } finally {
    createLoading.value = false
  }
}

async function openPerms(u) {
  permUser.value = u
  showPermsModal.value = true
  permsLoading.value = true
  permsError.value = ''
  try {
    editPerms.value = await api.adminGetPermissions(u.id)
  } finally {
    permsLoading.value = false
  }
}

async function savePerms() {
  permsSaving.value = true
  permsError.value = ''
  try {
    await api.adminSetPermissions(permUser.value.id, {
      permissions: editPerms.value.map(p => ({ module_id: p.module_id, level: p.level }))
    })
    showPermsModal.value = false
  } catch (e) {
    permsError.value = typeof e === 'string' ? e : '保存失败'
  } finally {
    permsSaving.value = false
  }
}

onMounted(loadUsers)

// ── CMDB 分组分配 ─────────────────────────────────────────────────────────────
const showGroupModal    = ref(false)
const groupUser         = ref(null)
const allGroups         = ref([])
const selectedGroupIds  = ref([])
const groupLoading      = ref(false)
const groupSaving       = ref(false)
const groupError        = ref('')

async function openGroupAssign(u) {
  groupUser.value        = u
  groupError.value       = ''
  selectedGroupIds.value = []
  showGroupModal.value   = true
  groupLoading.value     = true
  try {
    const res = await api.adminGetUserCmdbGroups(u.id)
    allGroups.value        = res.all_groups || []
    selectedGroupIds.value = res.group_ids  || []
  } catch (e) {
    groupError.value = typeof e === 'string' ? e : '加载分组失败'
  } finally {
    groupLoading.value = false
  }
}

async function saveGroups() {
  groupSaving.value = true
  groupError.value  = ''
  try {
    await api.adminSetUserCmdbGroups(groupUser.value.id, { group_ids: selectedGroupIds.value })
    showGroupModal.value = false
  } catch (e) {
    groupError.value = typeof e === 'string' ? e : '保存失败'
  } finally {
    groupSaving.value = false
  }
}
</script>

<style scoped>
.admin-page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { font-size: 20px; color: var(--text-base, #e2e8f0); margin: 0; }
.filter-bar { margin-bottom: 14px; }
.filter-bar select { background: var(--bg-card, #1a1d2e); border: 1px solid var(--border, #2a2d3e); color: var(--text-base, #e2e8f0); padding: 6px 12px; border-radius: 6px; font-size: 13px; }
.table-wrap { background: var(--bg-card, #1a1d2e); border: 1px solid var(--border, #2a2d3e); border-radius: 8px; overflow: hidden; }
.user-table { width: 100%; border-collapse: collapse; font-size: 13px; color: var(--text-base, #e2e8f0); }
.user-table thead th { padding: 10px 14px; background: var(--bg-base, #0f1117); border-bottom: 1px solid var(--border, #2a2d3e); text-align: left; color: var(--text-muted, #8892a4); }
.user-table tbody tr:hover { background: rgba(255,255,255,.03); }
.user-table td { padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,.04); }
.user-table .small { font-size: 12px; color: var(--text-muted, #8892a4); }
.status-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.status-badge.active { background: rgba(72,199,142,.15); color: #48c78e; }
.status-badge.pending { background: rgba(255,193,7,.15); color: #ffc107; }
.status-badge.locked { background: rgba(255,107,107,.15); color: #ff6b6b; }
.status-badge.disabled { background: rgba(136,146,164,.1); color: var(--text-muted, #8892a4); }
.role-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: rgba(136,146,164,.1); color: var(--text-muted, #8892a4); }
.role-badge.admin { background: rgba(124,131,255,.15); color: var(--accent, #7c83ff); }
.actions-cell { display: flex; gap: 6px; flex-wrap: wrap; }
.btn { border-radius: 5px; cursor: pointer; font-size: 13px; padding: 5px 12px; border: 1px solid transparent; transition: opacity .2s; }
.btn-primary { background: var(--accent, #7c83ff); color: #fff; border: none; }
.btn-outline { background: transparent; border-color: var(--border, #2a2d3e); color: var(--text-base, #e2e8f0); }
.btn-xs { padding: 3px 8px; font-size: 12px; }
.btn-ok { background: rgba(72,199,142,.15); color: #48c78e; border-color: rgba(72,199,142,.3); }
.btn-danger { background: rgba(255,107,107,.1); color: #ff6b6b; border-color: rgba(255,107,107,.3); }
.btn:hover:not(:disabled) { opacity: .8; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.empty-state { display: flex; align-items: center; justify-content: center; height: 120px; gap: 10px; color: var(--text-muted, #8892a4); }
.spinner { width: 20px; height: 20px; border: 2px solid var(--border, #2a2d3e); border-top-color: var(--accent, #7c83ff); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
/* 弹窗 */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--bg-card, #1a1d2e); border: 1px solid var(--border, #2a2d3e); border-radius: 10px; width: 480px; max-width: 95vw; max-height: 90vh; overflow-y: auto; }
.modal-wide { width: 560px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border, #2a2d3e); font-size: 15px; color: var(--text-base, #e2e8f0); }
.modal-body { padding: 20px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 12px; color: var(--text-muted, #8892a4); }
.form-group input { background: var(--bg-base, #0f1117); border: 1px solid var(--border, #2a2d3e); border-radius: 6px; padding: 8px 10px; color: var(--text-base, #e2e8f0); font-size: 13px; outline: none; }
.form-group input:focus { border-color: var(--accent, #7c83ff); }
.check-row { display: flex; align-items: center; gap: 8px; color: var(--text-base, #e2e8f0); font-size: 13px; margin-top: 10px; cursor: pointer; }
.form-error { color: var(--error, #ff6b6b); font-size: 13px; background: rgba(255,107,107,.1); padding: 8px 12px; border-radius: 6px; margin-top: 8px; }
/* 权限表格 */
.perm-table { display: flex; flex-direction: column; gap: 2px; }
.perm-row { display: grid; grid-template-columns: 1fr 80px 80px 80px; align-items: center; padding: 8px 10px; border-radius: 6px; }
.perm-row.header { font-size: 12px; color: var(--text-muted, #8892a4); background: var(--bg-base, #0f1117); }
.perm-row:not(.header) { background: rgba(255,255,255,.02); }
.perm-row:not(.header):hover { background: rgba(255,255,255,.05); }
.perm-row label { display: flex; justify-content: center; cursor: pointer; }
.mod-name { font-size: 13px; color: var(--text-base, #e2e8f0); }
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
/* 分组分配 */
.btn-group-assign { background: rgba(56,139,253,.12); color: var(--accent, #7c83ff); border-color: rgba(56,139,253,.3); }
.group-hint { font-size: 12px; color: var(--text-muted, #8892a4); margin-bottom: 12px; line-height: 1.6; }
.group-check-list { display: flex; flex-direction: column; gap: 4px; max-height: 320px; overflow-y: auto; }
.group-check-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 6px; cursor: pointer; border: 1px solid transparent; transition: all .15s; }
.group-check-item:hover { background: rgba(255,255,255,.04); }
.group-check-item.selected { background: rgba(56,139,253,.08); border-color: rgba(56,139,253,.2); }
.group-check-item input[type=checkbox] { width: 15px; height: 15px; cursor: pointer; accent-color: var(--accent, #7c83ff); }
.group-check-name { flex: 1; font-size: 13px; color: var(--text-base, #e2e8f0); }
.group-check-count { font-size: 11px; color: var(--text-muted, #8892a4); }
</style>
