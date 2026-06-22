<template>
  <div class="landing">
    <!-- 顶部导航 -->
    <header class="hero-top">
      <div class="brand-row">
        <span class="brand-mark">Sx</span>
        <div class="brand-name">
          <strong>SxDevOps</strong><span class="brand-sub">· AI Agent</span>
        </div>
      </div>
      <div class="hero-top-right">
        <span class="tag-line">思而后行 · 行必有证</span>
      </div>
    </header>

    <!-- 主区：左 hero + 右登录卡 -->
    <main class="landing-main">
      <section class="hero-text">
        <h1 class="hero-title">
          <span class="hero-serif">统一运维智能体平台</span>
          <span class="hero-sub">让协作闭环更高效</span>
        </h1>
        <p class="hero-desc">
          面向产研团队的统一入口，围绕可观测性、事件中心、任务中心和 AIOps，
          沉淀从发现异常到闭环复盘的完整链路。
        </p>

        <!-- 4 大模块卡 -->
        <div class="module-grid">
          <div class="mod-card mod-aiops">
            <div class="mod-head"><span class="mod-icon">✦</span><span>AIOps</span></div>
            <p>串联观测、事件与资源上下文，辅助根因分析、处置建议和审计复盘。</p>
          </div>
          <div class="mod-card mod-obs">
            <div class="mod-head"><span class="mod-icon">◐</span><span>可观测性</span></div>
            <p>统计系统 SLA，统一查看指标、日志、链路与告警，快速定位异常和性能瓶颈。</p>
          </div>
          <div class="mod-card mod-event">
            <div class="mod-head"><span class="mod-icon">◷</span><span>事件中心</span></div>
            <p>收敛应用发布、运维事务、任务调度等事件，支撑影响分析与跟踪，辅助 AI 分析。</p>
          </div>
          <div class="mod-card mod-task">
            <div class="mod-head"><span class="mod-icon">⌖</span><span>任务中心</span></div>
            <p>集中管理任务，生成 AIOps 待执行项，形成可追踪、可审计的执行闭环。</p>
          </div>
        </div>

        <!-- 协作链路 4 步 -->
        <div class="flow-row">
          <span class="flow-label">协作链路</span>
          <div class="flow-step"><span class="fs-num">1</span>看态势</div>
          <span class="flow-arrow">→</span>
          <div class="flow-step"><span class="fs-num">2</span>找证据</div>
          <span class="flow-arrow">→</span>
          <div class="flow-step"><span class="fs-num">3</span>问系统</div>
          <span class="flow-arrow">→</span>
          <div class="flow-step"><span class="fs-num">4</span>确认动作</div>
        </div>
      </section>

      <!-- 右侧登录卡 -->
      <aside class="login-card">
        <div class="login-head">
          <h2>登录工作台</h2>
          <p>使用平台账号进入 SxDevOps</p>
        </div>
        <form @submit.prevent="handleLogin" class="login-form">
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
          <button type="submit" class="btn-login" :disabled="loading">
            <span v-if="loading" class="spinner-sm"></span>
            {{ loading ? '登录中...' : '进入工作台' }}
          </button>
          <p class="demo-hint">演示账号：<code>aiopscode</code> / <code>AiopsCode@2026</code></p>
        </form>
        <div class="login-links">
          <RouterLink to="/register">注册账号</RouterLink>
          <RouterLink to="/forgot-password">忘记密码</RouterLink>
        </div>
      </aside>
    </main>

    <footer class="hero-foot">
      <span>SxDevOps · 让运维从「查系统」升级为「看态势、找证据、问系统、确认动作」</span>
    </footer>
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
.landing {
  min-height: 100vh; width: 100%;
  display: flex; flex-direction: column;
  background: var(--bg-base);
  background-image:
    radial-gradient(ellipse at 0% 0%, rgba(var(--accent-rgb), 0.08), transparent 40%),
    radial-gradient(ellipse at 100% 100%, rgba(var(--accent-rgb), 0.05), transparent 35%);
  overflow-y: auto;
}

/* 顶部 ── */
.hero-top {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 36px;
}
.brand-row { display: flex; align-items: center; gap: 12px; }
.brand-mark {
  width: 38px; height: 38px;
  background: var(--accent); color: #fff;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-serif); font-size: 18px; font-weight: 700;
  font-style: italic;
}
.brand-name strong { font-family: var(--font-serif); font-size: 19px; font-weight: 600; letter-spacing: -0.01em; color: var(--text-primary); }
.brand-sub { color: var(--text-muted); font-size: 13px; margin-left: 6px; }
.hero-top-right .tag-line { color: var(--text-secondary); font-size: 13px; letter-spacing: 0.06em; }

/* 主区 ── */
.landing-main {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) 380px;
  gap: 60px;
  padding: 24px 56px 48px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
  align-items: start;
}

.hero-text { min-width: 0; }
.hero-title { display: flex; flex-direction: column; gap: 6px; margin-bottom: 16px; }
.hero-serif {
  font-family: var(--font-serif);
  font-size: 38px; font-weight: 500;
  letter-spacing: -0.018em;
  color: var(--text-primary);
}
.hero-sub {
  font-family: var(--font-serif);
  font-size: 24px; font-weight: 400;
  color: var(--accent);
  font-style: italic;
}
.hero-desc {
  color: var(--text-secondary);
  font-size: 14.5px; line-height: 1.7;
  max-width: 640px;
  margin-bottom: 32px;
}

/* 模块卡片网格 */
.module-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin-bottom: 28px;
}
.mod-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
  transition: border-color .2s, transform .2s, box-shadow .2s;
}
.mod-card:hover {
  border-color: var(--border-accent);
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}
.mod-head {
  display: flex; align-items: center; gap: 8px;
  font-weight: 600; font-size: 15px;
  margin-bottom: 8px;
  color: var(--text-primary);
}
.mod-icon {
  width: 28px; height: 28px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px;
  background: var(--accent-soft); color: var(--accent);
}
.mod-card p {
  color: var(--text-secondary);
  font-size: 12.5px; line-height: 1.6;
}
.mod-card.mod-aiops .mod-icon { background: rgba(217,119,87,.16); color: var(--accent); }
.mod-card.mod-obs .mod-icon { background: rgba(99,130,91,.16); color: var(--success); }
.mod-card.mod-event .mod-icon { background: rgba(96,165,250,.16); color: #60a5fa; }
.mod-card.mod-task .mod-icon { background: rgba(197,138,70,.16); color: var(--warning); }

/* 协作链路 */
.flow-row {
  display: flex; align-items: center; gap: 12px;
  flex-wrap: wrap;
  padding: 14px 18px;
  background: var(--bg-surface); border-radius: 12px;
  border: 1px dashed var(--border-strong);
}
.flow-label { color: var(--text-muted); font-size: 13px; margin-right: 4px; }
.flow-step {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 4px 12px; border-radius: 99px;
  background: var(--bg-card); border: 1px solid var(--border);
  font-size: 13px; color: var(--text-primary); font-weight: 500;
}
.fs-num {
  width: 18px; height: 18px;
  background: var(--accent); color: #fff;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 10.5px; font-weight: 700;
}
.flow-arrow { color: var(--accent); font-weight: 700; }

/* 登录卡 */
.login-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 28px 28px 24px;
  box-shadow: var(--shadow);
  position: sticky; top: 24px;
}
.login-head { margin-bottom: 18px; }
.login-head h2 { font-family: var(--font-serif); font-size: 20px; font-weight: 500; margin-bottom: 4px; }
.login-head p { color: var(--text-muted); font-size: 12.5px; }

.login-form { display: flex; flex-direction: column; gap: 14px; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label {
  font-size: 12px; font-weight: 500;
  color: var(--text-secondary);
}
.form-group input {
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: 10px; padding: 9px 14px;
  color: var(--text-primary); font-size: 13.5px; font-family: inherit;
  outline: none;
  transition: border-color .15s, box-shadow .15s;
}
.form-group input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(var(--accent-rgb), 0.12);
}

.auth-error {
  display: flex; align-items: center; gap: 7px;
  color: var(--error); font-size: 12.5px;
  background: rgba(var(--error-rgb), 0.08);
  border: 1px solid rgba(var(--error-rgb), 0.22);
  padding: 8px 12px; border-radius: 8px;
}

.btn-login {
  background: var(--accent); color: #fff;
  border: none; border-radius: 10px;
  padding: 11px;
  font-size: 14px; font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  transition: background .15s;
}
.btn-login:hover:not(:disabled) { background: var(--accent-hover); }
.btn-login:disabled { opacity: .55; cursor: not-allowed; }

.demo-hint {
  font-size: 11.5px; color: var(--text-muted);
  text-align: center; margin-top: 2px;
}
.demo-hint code {
  background: var(--bg-surface); padding: 1px 6px;
  border-radius: 4px; font-family: var(--font-mono);
  font-size: 11px; color: var(--text-primary);
}

.login-links {
  display: flex; justify-content: space-between;
  margin-top: 18px; padding-top: 16px;
  border-top: 1px solid var(--border-light);
}
.login-links a {
  font-size: 12.5px; color: var(--accent);
  text-decoration: none;
}
.login-links a:hover { opacity: .8; }

/* 底部 */
.hero-foot {
  text-align: center; padding: 16px 24px;
  border-top: 1px solid var(--border-light);
  color: var(--text-muted); font-size: 12px;
}

.spinner-sm {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%;
  animation: spin .7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 响应式 */
@media (max-width: 960px) {
  .landing-main { grid-template-columns: 1fr; padding: 20px; gap: 32px; }
  .login-card { position: static; }
  .hero-serif { font-size: 28px; }
  .hero-sub { font-size: 18px; }
  .module-grid { grid-template-columns: 1fr; }
}
</style>
