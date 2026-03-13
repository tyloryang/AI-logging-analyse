<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-logo">🤖 AI Ops</div>
      <h2 class="auth-title">注册账号</h2>

      <div v-if="success" class="auth-success">
        <div class="success-icon">✅</div>
        <p>注册成功！</p>
        <p class="muted">您的账号正在等待管理员审批，审批通过后即可登录。</p>
        <RouterLink to="/login" class="btn-auth" style="margin-top:16px;display:block;text-align:center;text-decoration:none">返回登录</RouterLink>
      </div>

      <form v-else @submit.prevent="handleRegister" class="auth-form">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="form.username" placeholder="字母/数字，3-32位" required autofocus />
        </div>
        <div class="form-group">
          <label>邮箱</label>
          <input v-model="form.email" type="email" placeholder="your@email.com" required />
        </div>
        <div class="form-group">
          <label>昵称（可选）</label>
          <input v-model="form.display_name" placeholder="显示名称" />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="至少8位，含字母和数字" required />
        </div>
        <div v-if="error" class="auth-error">{{ error }}</div>
        <button type="submit" class="btn-auth" :disabled="loading">
          <span v-if="loading" class="spinner-sm"></span>
          {{ loading ? '提交中...' : '提交注册' }}
        </button>
        <RouterLink to="/login" class="back-link">已有账号？去登录</RouterLink>
      </form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api/index.js'

const form = reactive({ username: '', email: '', password: '', display_name: '' })
const loading = ref(false)
const error = ref('')
const success = ref(false)

async function handleRegister() {
  loading.value = true
  error.value = ''
  try {
    await api.register(form)
    success.value = true
  } catch (e) {
    error.value = typeof e === 'string' ? e : '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg-base, #0f1117); }
.auth-card { width: 400px; background: var(--bg-card, #1a1d2e); border: 1px solid var(--border, #2a2d3e); border-radius: 12px; padding: 36px 32px; }
.auth-logo { font-size: 22px; font-weight: 700; color: var(--accent, #7c83ff); margin-bottom: 8px; }
.auth-title { font-size: 20px; color: var(--text-base, #e2e8f0); margin: 0 0 24px; }
.auth-form { display: flex; flex-direction: column; gap: 14px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; color: var(--text-muted, #8892a4); }
.form-group input { background: var(--bg-base, #0f1117); border: 1px solid var(--border, #2a2d3e); border-radius: 6px; padding: 9px 12px; color: var(--text-base, #e2e8f0); font-size: 14px; outline: none; transition: border-color .2s; }
.form-group input:focus { border-color: var(--accent, #7c83ff); }
.auth-error { color: var(--error, #ff6b6b); font-size: 13px; background: rgba(255,107,107,.1); padding: 8px 12px; border-radius: 6px; }
.btn-auth { background: var(--accent, #7c83ff); color: #fff; border: none; border-radius: 6px; padding: 10px; font-size: 15px; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: opacity .2s; }
.btn-auth:disabled { opacity: .6; cursor: not-allowed; }
.back-link { text-align: center; font-size: 13px; color: var(--accent, #7c83ff); text-decoration: none; }
.back-link:hover { text-decoration: underline; }
.auth-success { text-align: center; color: var(--text-base, #e2e8f0); }
.success-icon { font-size: 40px; margin-bottom: 12px; }
.muted { font-size: 13px; color: var(--text-muted, #8892a4); margin-top: 6px; }
.spinner-sm { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
