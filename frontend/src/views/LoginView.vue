<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-brand">
        <span class="brand-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
            <rect x="3" y="14" width="7" height="7"/><path d="M14 17h3m0 0h3m-3 0v-3m0 3v3"/>
          </svg>
        </span>
        <span class="brand-text">AI<span class="brand-accent">OPS</span></span>
      </div>
      <h2 class="auth-title">欢迎回来</h2>
      <p class="auth-subtitle">智能运维平台</p>

      <form @submit.prevent="handleLogin" class="auth-form">
        <div class="form-group">
          <label>用户名</label>
          <input v-model="form.username" placeholder="请输入用户名" autofocus required />
        </div>
        <div class="form-group">
          <label>密码</label>
          <input v-model="form.password" type="password" placeholder="请输入密码" required />
        </div>
        <div v-if="error" class="auth-error">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          {{ error }}
        </div>
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
    error.value = typeof e === 'string' ? e : '用户名或密码错误'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  width: 100%;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-base, #0d1117);
  /* Subtle grid dot pattern */
  background-image: radial-gradient(circle, rgba(56,139,253,0.08) 1px, transparent 1px);
  background-size: 28px 28px;
  padding: 20px;
}

.auth-card {
  width: 100%; max-width: 380px;
  background: var(--bg-card, #161b22);
  border: 1px solid var(--border, #30363d);
  border-top: 2px solid var(--accent, #388bfd);
  border-radius: var(--radius-lg, 8px);
  padding: 36px 32px 28px;
  box-shadow: var(--shadow-md), 0 0 40px rgba(56,139,253,0.06);
}

.auth-brand {
  display: flex; align-items: center; gap: 9px;
  margin-bottom: 20px;
}
.brand-icon {
  width: 34px; height: 34px;
  background: var(--accent);
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  box-shadow: 0 0 0 3px var(--accent-dim);
}
.brand-text {
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 15px; font-weight: 700;
  color: var(--text-primary);
  letter-spacing: .08em;
}
.brand-accent { color: var(--accent); }

.auth-title {
  font-size: 20px; font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 3px;
}
.auth-subtitle {
  font-size: 12px; color: var(--text-muted);
  margin-bottom: 24px;
  text-transform: uppercase; letter-spacing: .06em;
}

.auth-form { display: flex; flex-direction: column; gap: 14px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label {
  font-size: 12px; font-weight: 500;
  color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: .05em;
}
.form-group input {
  background: var(--bg-input, #0d1117);
  border: 1px solid var(--border);
  border-radius: var(--radius, 3px);
  padding: 9px 12px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
}
.form-group input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim);
}

.auth-error {
  display: flex; align-items: center; gap: 7px;
  color: var(--error, #f85149); font-size: 13px;
  background: rgba(248,81,73,.08);
  border: 1px solid rgba(248,81,73,.2);
  padding: 8px 12px; border-radius: var(--radius, 3px);
}

.btn-auth {
  background: var(--accent, #388bfd);
  color: #fff;
  border: none; border-radius: var(--radius, 3px);
  padding: 10px;
  font-size: 14px; font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  margin-top: 4px;
  transition: background .15s, box-shadow .15s;
}
.btn-auth:hover:not(:disabled) {
  background: var(--accent-hover, #58a6ff);
  box-shadow: 0 0 0 3px var(--accent-dim);
}
.btn-auth:disabled { opacity: .5; cursor: not-allowed; }

.auth-links {
  display: flex; justify-content: space-between;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light, #21262d);
}
.auth-links a {
  font-size: 12px; color: var(--accent);
  text-decoration: none; transition: opacity .12s;
}
.auth-links a:hover { opacity: .75; }

.spinner-sm {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,.25);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
