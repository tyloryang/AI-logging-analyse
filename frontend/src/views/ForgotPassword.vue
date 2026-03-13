<template>
  <div class="auth-page">
    <div class="auth-card">
      <div class="auth-logo">🤖 AI Ops</div>
      <h2 class="auth-title">忘记密码</h2>
      <div class="forgot-body">
        <div class="icon">🔒</div>
        <p>密码重置需要联系系统管理员。</p>
        <p class="muted">请向管理员说明您的用户名，由管理员在用户管理后台为您重置密码。</p>
      </div>
      <RouterLink to="/login" class="btn-back">返回登录</RouterLink>
    </div>
  </div>
</template>

<script setup>
import { RouterLink } from 'vue-router'
</script>

<style scoped>
.auth-page { min-height: 100vh; display: flex; align-items: center; justify-content: center; background: var(--bg-base, #0f1117); }
.auth-card { width: 380px; background: var(--bg-card, #1a1d2e); border: 1px solid var(--border, #2a2d3e); border-radius: 12px; padding: 36px 32px; text-align: center; }
.auth-logo { font-size: 22px; font-weight: 700; color: var(--accent, #7c83ff); margin-bottom: 8px; }
.auth-title { font-size: 20px; color: var(--text-base, #e2e8f0); margin: 0 0 24px; }
.forgot-body { color: var(--text-base, #e2e8f0); }
.icon { font-size: 40px; margin-bottom: 16px; }
.muted { font-size: 13px; color: var(--text-muted, #8892a4); margin-top: 8px; line-height: 1.6; }
.btn-back { display: block; margin-top: 24px; background: var(--accent, #7c83ff); color: #fff; border-radius: 6px; padding: 10px; font-size: 15px; font-weight: 600; text-decoration: none; transition: opacity .2s; }
.btn-back:hover { opacity: .88; }
</style>
