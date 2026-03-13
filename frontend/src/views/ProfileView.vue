<template>
  <div class="profile-page">
    <div class="profile-card">
      <h2 class="card-title">👤 个人中心</h2>

      <div class="info-section">
        <div class="info-row"><span class="label">用户名</span><span>{{ auth.user?.username }}</span></div>
        <div class="info-row"><span class="label">邮箱</span><span>{{ auth.user?.email }}</span></div>
        <div class="info-row"><span class="label">角色</span><span>{{ auth.isAdmin ? '管理员' : '普通用户' }}</span></div>
      </div>

      <div class="section-title">我的权限</div>
      <div class="perm-grid">
        <div v-for="(level, mod) in auth.permissions" :key="mod" class="perm-item" :class="'perm-' + level">
          <span class="mod-name">{{ modLabel(mod) }}</span>
          <span class="perm-badge" :class="level">{{ levelLabel(level) }}</span>
        </div>
      </div>

      <div class="section-title" style="margin-top:28px">修改密码</div>
      <form @submit.prevent="handleChangePassword" class="pwd-form">
        <div class="form-group">
          <label>原密码</label>
          <input v-model="pwdForm.old_password" type="password" placeholder="输入原密码" required />
        </div>
        <div class="form-group">
          <label>新密码</label>
          <input v-model="pwdForm.new_password" type="password" placeholder="至少8位，含字母和数字" required />
        </div>
        <div v-if="pwdError" class="form-error">{{ pwdError }}</div>
        <div v-if="pwdSuccess" class="form-success">{{ pwdSuccess }}</div>
        <button type="submit" class="btn-primary" :disabled="pwdLoading">
          {{ pwdLoading ? '修改中...' : '修改密码' }}
        </button>
      </form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { api } from '../api/index.js'

const auth = useAuthStore()
const pwdForm = reactive({ old_password: '', new_password: '' })
const pwdLoading = ref(false)
const pwdError = ref('')
const pwdSuccess = ref('')

const MOD_LABELS = {
  dashboard: '仪表盘', log: '日志分析', metrics: '指标监控',
  alert: '告警历史', report: '分析报告', cmdb: '主机CMDB',
  inspect: '主机巡检', ssh: 'SSH终端', admin: '用户管理',
}
const LEVEL_LABELS = { none: '无权限', view: '只读', operate: '可操作' }

function modLabel(id) { return MOD_LABELS[id] || id }
function levelLabel(l) { return LEVEL_LABELS[l] || l }

async function handleChangePassword() {
  pwdLoading.value = true
  pwdError.value = ''
  pwdSuccess.value = ''
  try {
    await api.changePassword(pwdForm)
    pwdSuccess.value = '密码修改成功'
    pwdForm.old_password = ''
    pwdForm.new_password = ''
  } catch (e) {
    pwdError.value = typeof e === 'string' ? e : '修改失败'
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.profile-page { padding: 24px; max-width: 640px; }
.profile-card { background: var(--bg-card, #1a1d2e); border: 1px solid var(--border, #2a2d3e); border-radius: 10px; padding: 28px; }
.card-title { font-size: 18px; color: var(--text-base, #e2e8f0); margin: 0 0 20px; }
.info-section { display: flex; flex-direction: column; gap: 10px; margin-bottom: 24px; }
.info-row { display: flex; gap: 16px; font-size: 14px; color: var(--text-base, #e2e8f0); }
.info-row .label { width: 60px; color: var(--text-muted, #8892a4); flex-shrink: 0; }
.section-title { font-size: 13px; color: var(--text-muted, #8892a4); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 12px; }
.perm-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.perm-item { display: flex; align-items: center; gap: 8px; background: var(--bg-base, #0f1117); border: 1px solid var(--border, #2a2d3e); border-radius: 6px; padding: 6px 12px; }
.mod-name { font-size: 13px; color: var(--text-base, #e2e8f0); }
.perm-badge { font-size: 11px; padding: 2px 7px; border-radius: 4px; }
.perm-badge.operate { background: rgba(124,131,255,.15); color: var(--accent, #7c83ff); }
.perm-badge.view { background: rgba(72,199,142,.15); color: #48c78e; }
.perm-badge.none { background: rgba(136,146,164,.1); color: var(--text-muted, #8892a4); }
.pwd-form { display: flex; flex-direction: column; gap: 14px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; color: var(--text-muted, #8892a4); }
.form-group input { background: var(--bg-base, #0f1117); border: 1px solid var(--border, #2a2d3e); border-radius: 6px; padding: 9px 12px; color: var(--text-base, #e2e8f0); font-size: 14px; outline: none; transition: border-color .2s; }
.form-group input:focus { border-color: var(--accent, #7c83ff); }
.form-error { color: var(--error, #ff6b6b); font-size: 13px; background: rgba(255,107,107,.1); padding: 8px 12px; border-radius: 6px; }
.form-success { color: #48c78e; font-size: 13px; background: rgba(72,199,142,.1); padding: 8px 12px; border-radius: 6px; }
.btn-primary { background: var(--accent, #7c83ff); color: #fff; border: none; border-radius: 6px; padding: 9px 20px; font-size: 14px; font-weight: 600; cursor: pointer; align-self: flex-start; transition: opacity .2s; }
.btn-primary:disabled { opacity: .6; cursor: not-allowed; }
</style>
