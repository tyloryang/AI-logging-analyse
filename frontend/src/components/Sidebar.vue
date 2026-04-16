<template>
  <aside class="sidebar">
    <!-- Logo / Brand -->
    <div class="logo">
      <span class="logo-mark">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
          <rect x="3" y="14" width="7" height="7"/><path d="M14 17h3m0 0h3m-3 0v-3m0 3v3"/>
        </svg>
      </span>
      <div class="logo-texts">
        <span class="logo-text">AI<span class="logo-accent">Ops</span></span>
        <span class="logo-sub">智能运维平台</span>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="nav">
      <!-- 仪表盘 -->
      <RouterLink to="/" class="nav-item" :class="{ active: route.path === '/' }">
        <span class="nav-icon" v-html="ICONS.dashboard"></span>
        <span class="nav-label">仪表盘</span>
      </RouterLink>

      <!-- ── 可观测性 组 ── -->
      <div class="nav-group-label">可观测性</div>

      <RouterLink v-if="auth.can('log','view')" to="/logs" class="nav-item" :class="{ active: route.path === '/logs' }">
        <span class="nav-icon" v-html="ICONS.log"></span>
        <span class="nav-label">日志分析</span>
      </RouterLink>

      <RouterLink v-if="auth.can('slowlog','view')" to="/slowlog" class="nav-item" :class="{ active: route.path === '/slowlog' }">
        <span class="nav-icon" v-html="ICONS.slowlog"></span>
        <span class="nav-label">慢日志分析</span>
      </RouterLink>

      <RouterLink v-if="auth.can('metrics','view')" to="/metrics" class="nav-item" :class="{ active: route.path === '/metrics' }">
        <span class="nav-icon" v-html="ICONS.metrics"></span>
        <span class="nav-label">指标监控</span>
      </RouterLink>

      <RouterLink v-if="auth.can('skywalking','view')" to="/skywalking" class="nav-item" :class="{ active: route.path === '/skywalking' }">
        <span class="nav-icon" v-html="ICONS.skywalking"></span>
        <span class="nav-label">APM 链路追踪</span>
      </RouterLink>

      <RouterLink v-if="auth.can('alert','view')" to="/alerts" class="nav-item" :class="{ active: route.path === '/alerts' }">
        <span class="nav-icon" v-html="ICONS.alert"></span>
        <span class="nav-label">告警历史</span>
      </RouterLink>

      <RouterLink v-if="auth.can('report','view')" to="/report" class="nav-item" :class="{ active: route.path === '/report' }">
        <span class="nav-icon" v-html="ICONS.report"></span>
        <span class="nav-label">分析报告</span>
      </RouterLink>

      <!-- ── 运维管理 组 ── -->
      <div class="nav-group-label">运维管理</div>

      <RouterLink v-if="auth.can('cmdb','view')" to="/hosts" class="nav-item" :class="{ active: route.path === '/hosts' }">
        <span class="nav-icon" v-html="ICONS.cmdb"></span>
        <span class="nav-label">CMDB 巡检</span>
      </RouterLink>

      <RouterLink v-if="auth.can('ssh','view')" to="/ssh" class="nav-item" :class="{ active: route.path === '/ssh' }">
        <span class="nav-icon" v-html="ICONS.ssh"></span>
        <span class="nav-label">SSH 终端</span>
      </RouterLink>

      <!-- ── AIOps 组（可展开） ── -->
      <div class="nav-group-label">AIOps</div>

      <div class="nav-group" :class="{ open: aiopsOpen }">
        <button class="nav-group-toggle" @click="aiopsOpen = !aiopsOpen" :class="{ active: isAiopsActive }">
          <span class="nav-icon" v-html="ICONS.agent"></span>
          <span class="nav-label">AIOps</span>
          <span class="toggle-arrow" :class="{ rotated: aiopsOpen }">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
          </span>
        </button>
        <div class="nav-sub" v-show="aiopsOpen">
          <RouterLink v-if="auth.can('agent','view')" to="/agent" class="nav-sub-item" :class="{ active: route.path === '/agent' }">
            <span class="sub-dot"></span>
            智能助手
          </RouterLink>
          <RouterLink v-if="auth.can('agent','view')" to="/agent-config" class="nav-sub-item" :class="{ active: route.path === '/agent-config' }">
            <span class="sub-dot"></span>
            智能配置
          </RouterLink>
        </div>
      </div>
    </nav>

    <!-- Footer -->
    <div class="sidebar-footer">
      <!-- Theme toggle -->
      <div class="theme-row">
        <button
          v-for="t in THEMES" :key="t.id"
          class="theme-btn"
          :class="{ active: currentTheme === t.id }"
          :title="t.label"
          @click="setTheme(t.id)"
        >{{ t.icon }}</button>
      </div>

      <div class="divider"></div>

      <!-- Connection status -->
      <div class="status-grid">
        <div class="conn-status" :class="connected ? 'ok' : 'err'" title="Loki">
          <span class="dot"></span>
          <span class="conn-label">Loki</span>
        </div>
        <div class="conn-status" :class="promConnected ? 'ok' : 'err'" title="Prometheus">
          <span class="dot"></span>
          <span class="conn-label">Prom</span>
        </div>
        <div class="conn-status" :class="swConnected ? 'ok' : 'err'" title="SkyWalking">
          <span class="dot"></span>
          <span class="conn-label">SW</span>
        </div>
        <div class="conn-status" :class="aiReady ? 'ok' : 'err'" :title="aiProvider">
          <span class="dot"></span>
          <span class="conn-label ai-label">{{ aiReady ? aiShortName : 'AI?' }}</span>
        </div>
      </div>

      <div class="divider"></div>

      <!-- User row -->
      <div class="user-row">
        <RouterLink to="/profile" class="user-info">
          <span class="user-avatar">{{ auth.user?.username?.charAt(0)?.toUpperCase() }}</span>
          <span class="user-name">{{ auth.user?.displayName || auth.user?.username }}</span>
        </RouterLink>
        <button class="logout-btn" @click="handleLogout" title="退出登录">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </button>
      </div>
      <div v-if="auth.isAdmin" class="admin-links">
        <RouterLink to="/admin/users" class="admin-link">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>
          用户管理
        </RouterLink>
        <RouterLink to="/settings" class="admin-link">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 010 14.14M4.93 4.93a10 10 0 000 14.14"/></svg>
          系统配置
        </RouterLink>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, RouterLink, useRouter } from 'vue-router'
import { api } from '../api/index.js'
import { useTheme, THEMES } from '../composables/useTheme.js'
import { useAuthStore } from '../stores/auth.js'

const route = useRoute()
const { currentTheme, setTheme } = useTheme()
const auth = useAuthStore()
const router = useRouter()

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}

const connected    = ref(false)
const promConnected = ref(false)
const swConnected  = ref(false)
const aiReady      = ref(false)
const aiProvider   = ref('')
const aiShortName  = computed(() => {
  if (!aiProvider.value) return 'AI'
  if (aiProvider.value.startsWith('Anthropic')) return 'Claude'
  const m = aiProvider.value.match(/\((.+)\)/)
  return m ? m[1].slice(0, 8) : aiProvider.value.slice(0, 8)
})

// AIOps 子菜单展开状态
const isAiopsActive = computed(() => ['/agent', '/agent-config'].includes(route.path))
const aiopsOpen = ref(isAiopsActive.value)

// 当路由变化时，若进入 AIOps 相关页面则自动展开
import { watch } from 'vue'
watch(() => route.path, (p) => {
  if (['/agent', '/agent-config'].includes(p)) aiopsOpen.value = true
})

const ICONS = {
  dashboard:  `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>`,
  log:        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/></svg>`,
  metrics:    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
  alert:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>`,
  report:     `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
  cmdb:       `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`,
  ssh:        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
  slowlog:    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  skywalking: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><line x1="12" y1="7" x2="5" y2="17"/><line x1="12" y1="7" x2="19" y2="17"/><line x1="5" y1="19" x2="19" y2="19"/></svg>`,
  agent:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M9 11V7a3 3 0 0 1 6 0v4"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/><path d="M12 3v2"/></svg>`,
}

onMounted(async () => {
  try {
    const r = await api.healthCheck()
    connected.value    = r.loki_connected
    promConnected.value = r.prometheus_connected ?? false
    swConnected.value  = r.skywalking_connected ?? false
    aiReady.value      = r.ai_ready ?? false
    aiProvider.value   = r.ai_provider ?? ''
  } catch {
    connected.value = false
    aiReady.value   = false
  }
})
</script>

<style scoped>
.sidebar {
  width: 192px; min-width: 192px;
  background: var(--bg-sidebar, #182132);
  display: flex; flex-direction: column;
  overflow: hidden;
  border-right: 1px solid rgba(255,255,255,0.06);
}

/* ── Logo ── */
.logo {
  display: flex; align-items: center; gap: 10px;
  padding: 0 14px;
  height: 56px;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  flex-shrink: 0;
}
.logo-mark {
  width: 30px; height: 30px;
  background: var(--accent);
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(56,139,253,0.35);
}
.logo-texts { display: flex; flex-direction: column; gap: 1px; }
.logo-text {
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 13px; font-weight: 700;
  color: var(--text-sidebar-active, #fff);
  letter-spacing: .03em;
  line-height: 1.2;
}
.logo-accent { color: var(--accent); }
.logo-sub {
  font-size: 9px; font-weight: 600;
  color: var(--accent);
  letter-spacing: .12em;
  line-height: 1;
  opacity: .8;
}

/* ── Nav ── */
.nav { flex: 1; padding: 6px 0 4px; display: flex; flex-direction: column; overflow-y: auto; }

.nav-group-label {
  font-size: 10px; font-weight: 600;
  color: rgba(255,255,255,0.25);
  letter-spacing: .1em;
  text-transform: uppercase;
  padding: 12px 14px 4px;
  line-height: 1;
}

.nav-item {
  display: flex; align-items: center; gap: 9px;
  padding: 8px 14px;
  color: var(--text-sidebar, #96a2b9);
  text-decoration: none;
  font-size: 13px; font-weight: 400;
  transition: background .12s, color .12s;
  border-left: 2px solid transparent;
  cursor: pointer;
}
.nav-item:hover {
  background: rgba(255,255,255,0.05);
  color: var(--text-sidebar-active, #fff);
}
.nav-item.active {
  background: rgba(56,139,253,0.14);
  color: #fff;
  border-left-color: var(--accent, #388bfd);
  font-weight: 500;
}
.nav-icon { display: flex; align-items: center; width: 15px; flex-shrink: 0; opacity: .75; }
.nav-item:hover .nav-icon,
.nav-item.active .nav-icon { opacity: 1; }

/* ── AIOps Expandable Group ── */
.nav-group-toggle {
  display: flex; align-items: center; gap: 9px;
  padding: 8px 14px; width: 100%;
  color: var(--text-sidebar, #96a2b9);
  font-size: 13px; font-weight: 400;
  background: none; border: none; border-left: 2px solid transparent;
  cursor: pointer; text-align: left;
  transition: background .12s, color .12s;
}
.nav-group-toggle:hover {
  background: rgba(255,255,255,0.05);
  color: var(--text-sidebar-active, #fff);
}
.nav-group-toggle.active {
  color: var(--accent);
}
.toggle-arrow {
  margin-left: auto;
  display: flex; align-items: center;
  transition: transform .2s;
  opacity: .5;
}
.toggle-arrow.rotated { transform: rotate(180deg); }

.nav-sub { display: flex; flex-direction: column; }
.nav-sub-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 14px 7px 36px;
  color: var(--text-sidebar, #96a2b9);
  font-size: 12.5px;
  text-decoration: none;
  border-left: 2px solid transparent;
  transition: background .12s, color .12s;
}
.nav-sub-item:hover {
  background: rgba(255,255,255,0.04);
  color: var(--text-sidebar-active, #fff);
}
.nav-sub-item.active {
  color: #fff;
  background: rgba(56,139,253,0.14);
  border-left-color: var(--accent);
  font-weight: 500;
}
.sub-dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: currentColor;
  opacity: .4;
  flex-shrink: 0;
}
.nav-sub-item.active .sub-dot { opacity: 1; background: var(--accent); }

/* ── Footer ── */
.sidebar-footer {
  padding: 8px 12px 12px;
  border-top: 1px solid rgba(255,255,255,0.06);
  display: flex; flex-direction: column; gap: 5px;
  flex-shrink: 0;
}

.theme-row { display: flex; gap: 4px; }
.theme-btn {
  flex: 1; padding: 4px; font-size: 13px;
  border-radius: 4px; border: 1px solid rgba(255,255,255,0.08);
  background: transparent; cursor: pointer;
  transition: all .12s; text-align: center;
}
.theme-btn:hover { background: rgba(255,255,255,0.06); }
.theme-btn.active { background: var(--accent); border-color: var(--accent); }

.divider { height: 1px; background: rgba(255,255,255,0.06); margin: 3px 0; }

/* ── Status grid (2×2) ── */
.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 8px; }
.conn-status { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-sidebar); }
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.conn-status.ok .dot  { background: var(--success, #3fb950); }
.conn-status.err .dot { background: var(--error,   #f85149); }
.conn-status.ok .dot::after {
  content: ''; position: absolute; inset: -2px;
  border-radius: 50%; border: 1px solid var(--success);
  animation: pulse-dot 2s ease infinite; opacity: 0;
}
.dot { position: relative; }
@keyframes pulse-dot {
  0%   { transform: scale(1);   opacity: .5; }
  70%  { transform: scale(2.2); opacity: 0;  }
  100% { transform: scale(2.2); opacity: 0;  }
}
.conn-label { color: rgba(255,255,255,0.45); font-size: 10.5px; }
.ai-label { max-width: 55px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── User ── */
.user-row { display: flex; align-items: center; justify-content: space-between; padding: 3px 0; }
.user-info { display: flex; align-items: center; gap: 7px; text-decoration: none; }
.user-avatar {
  width: 24px; height: 24px;
  background: var(--accent); border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: #fff; font-weight: 700;
  flex-shrink: 0;
}
.user-name { font-size: 12px; color: rgba(255,255,255,0.7); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100px; }
.logout-btn {
  background: none; border: none; color: rgba(255,255,255,0.25);
  cursor: pointer; display: flex; align-items: center;
  padding: 3px; border-radius: 3px; transition: color .15s, background .15s;
}
.logout-btn:hover { color: var(--error); background: rgba(248,81,73,0.12); }

.admin-links { display: flex; flex-direction: column; gap: 2px; }
.admin-link {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: var(--accent);
  text-decoration: none; padding: 2px 0;
  opacity: .8; transition: opacity .12s;
}
.admin-link:hover { opacity: 1; }
</style>
