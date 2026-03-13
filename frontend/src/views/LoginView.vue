<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-logo">🤖 AI Ops</div>
      <h2 class="auth-title">登录</h2>
      <form @submit.prevent="handleLogin" class="auth-form">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="form.username" placeholder="请输入用户名" autofocus required />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="请输入密码" required />
        </div>
        <div v-if="error" class="auth-error">{{ error }}</div>
        <button type="submit" class="btn-auth" :disabled="loading">
          <span v-if="loading" class="spinner-sm"></span>
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
      <div class="auth-links">
        <RouterLink to="/register">注册账号</RouterLink>
        <RouterLink to="/forgot-password">忘记密码</RouterLink>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({ username: '', password: '' })
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(form.username, form.password)
    router.push('/')
  } catch (e) {
    error.value = typeof e === 'string' ? e : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-base, #0f1117);
}
.auth-card {
  width: 380px;
  background: var(--bg-card, #1a1d2e);
  border: 1px solid var(--border, #2a2d3e);
  border-radius: 12px;
  padding: 36px 32px;
}
.auth-logo { font-size: 22px; font-weight: 700; color: var(--accent, #7c83ff); margin-bottom: 8px; }
.auth-title { font-size: 20px; color: var(--text-base, #e2e8f0); margin: 0 0 24px; }
.auth-form { display: flex; flex-direction: column; gap: 16px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; color: var(--text-muted, #8892a4); }
.form-group input {
  background: var(--bg-base, #0f1117);
  border: 1px solid var(--border, #2a2d3e);
  border-radius: 6px;
  padding: 9px 12px;
  color: var(--text-base, #e2e8f0);
  font-size: 14px;
  outline: none;
  transition: border-color .2s;
}
.form-group input:focus { border-color: var(--accent, #7c83ff); }
.auth-error { color: var(--error, #ff6b6b); font-size: 13px; background: rgba(255,107,107,.1); padding: 8px 12px; border-radius: 6px; }
.btn-auth {
  background: var(--accent, #7c83ff);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 10px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: opacity .2s;
}
.btn-auth:disabled { opacity: .6; cursor: not-allowed; }
.btn-auth:hover:not(:disabled) { opacity: .88; }
.auth-links { display: flex; justify-content: space-between; margin-top: 16px; }
.auth-links a { font-size: 13px; color: var(--accent, #7c83ff); text-decoration: none; }
.auth-links a:hover { text-decoration: underline; }
.spinner-sm { width: 14px; height: 14px; border: 2px solid rgba(255,255,255,.3); border-top-color: #fff; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
