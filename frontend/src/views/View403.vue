<template>
  <div class="page-403">
    <div class="content">
      <div class="icon">🚫</div>
      <h2>403 · 无访问权限</h2>
      <p class="muted">您没有访问该页面的权限，请联系管理员分配权限。</p>
      <div class="actions">
        <RouterLink to="/" class="btn-home">返回首页</RouterLink>
        <button class="btn-logout" @click="handleLogout">退出登录</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { RouterLink, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const router = useRouter()

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.page-403 { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg-base, #0f1117); }
.content { text-align: center; color: var(--text-base, #e2e8f0); }
.icon { font-size: 56px; margin-bottom: 16px; }
h2 { font-size: 24px; margin: 0 0 12px; }
.muted { font-size: 14px; color: var(--text-muted, #8892a4); margin-bottom: 28px; }
.actions { display: flex; gap: 12px; justify-content: center; }
.btn-home { background: var(--accent, #7c83ff); color: #fff; border-radius: 6px; padding: 9px 20px; text-decoration: none; font-size: 14px; font-weight: 600; transition: opacity .2s; }
.btn-home:hover { opacity: .88; }
.btn-logout { background: transparent; border: 1px solid var(--border, #2a2d3e); color: var(--text-muted, #8892a4); border-radius: 6px; padding: 9px 20px; font-size: 14px; cursor: pointer; transition: border-color .2s; }
.btn-logout:hover { border-color: var(--text-muted, #8892a4); }
</style>
