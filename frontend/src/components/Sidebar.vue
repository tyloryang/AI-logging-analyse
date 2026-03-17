<template>
  <aside class="sidebar">
    <!-- Logo -->
    <div class="logo">
      <span class="logo-mark">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
          <rect x="3" y="14" width="7" height="7"/><path d="M14 17h3m0 0h3m-3 0v-3m0 3v3"/>
        </svg>
      </span>
      <span class="logo-text">AI<span class="logo-accent">OPS</span></span>
    </div>

    <!-- Navigation -->
    <nav class="nav">
      <RouterLink
        v-for="item in navItems" :key="item.path"
        :to="item.path" class="nav-item"
        :class="{ active: route.path === item.path }"
      >
        <span class="nav-icon" v-html="ICONS[item.module]"></span>
        <span class="nav-label">{{ item.label }}</span>
      </RouterLink>
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
        >{{ t.icon }} {{ t.label }}</button>
      </div>

      <div class="divider"></div>

      <!-- Connection status -->
      <div class="conn-status" :class="connected ? 'ok' : 'err'">
        <span class="dot"></span>
        <span class="conn-label">{{ connected ? 'Loki' : 'Loki 离线' }}</span>
      </div>
      <div class="conn-status" :class="promConnected ? 'ok' : 'err'">
        <span class="dot"></span>
        <span class="conn-label">{{ promConnected ? 'Prometheus' : 'Prometheus 离线' }}</span>
      </div>
      <div class="conn-status" :class="aiReady ? 'ok' : 'err'" :title="aiProvider">
        <span class="dot"></span>
        <span class="conn-label ai-label">{{ aiReady ? 'AI · ' + aiShortName : 'AI 未就绪' }}</span>
      </div>

      <div class="divider"></div>

      <!-- User row -->
      <div class="user-row">
        <RouterLink to="/profile" class="user-info">
          <span class="user-avatar">{{ auth.user?.username?.charAt(0)?.toUpperCase() }}</span>
          <span class="user-name">{{ auth.user?.displayName || auth.user?.username }}</span>
        </RouterLink>
        <button class="logout-btn" @click="handleLogout" title="退出登录">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </button>
      </div>
      <div v-if="auth.isAdmin" class="admin-links">
        <RouterLink to="/admin/users" class="admin-link">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>
          </svg>
          用户管理
        </RouterLink>
        <RouterLink to="/settings" class="admin-link">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 010 14.14M4.93 4.93a10 10 0 000 14.14"/>
          </svg>
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

const connected = ref(false)
const promConnected = ref(false)
const aiReady = ref(false)
const aiProvider = ref('')
const aiShortName = computed(() => {
  if (!aiProvider.value) return '未配置'
  if (aiProvider.value.startsWith('Anthropic')) return 'Claude'
  const m = aiProvider.value.match(/\((.+)\)/)
  return m ? m[1] : aiProvider.value
})

// SVG icon set (Feather/Heroicons style, 24px viewBox)
const ICONS = {
  dashboard: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>`,
  log:       `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/></svg>`,
  metrics:   `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
  alert:     `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>`,
  report:    `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
  cmdb:      `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`,
  ssh:       `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
  slowlog:   `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
}

const allNavItems = [
  { path: '/',        label: '仪表盘',   module: 'dashboard' },
  { path: '/logs',    label: '日志分析',  module: 'log'       },
  { path: '/metrics', label: '指标监控',  module: 'metrics'   },
  { path: '/alerts',  label: '告警历史',  module: 'alert'     },
  { path: '/report',  label: '分析报告',  module: 'report'    },
  { path: '/hosts',   label: 'CMDB 巡检', module: 'cmdb'      },
  { path: '/ssh',     label: 'SSH 终端',  module: 'ssh'       },
  { path: '/slowlog', label: '慢日志分析', module: 'slowlog'   },
]
const navItems = computed(() =>
  allNavItems.filter(item => auth.can(item.module, 'view'))
)

onMounted(async () => {
  try {
    const r = await api.healthCheck()
    connected.value = r.loki_connected
    promConnected.value = r.prometheus_connected ?? false
    aiReady.value = r.ai_ready ?? false
    aiProvider.value = r.ai_provider ?? ''
  } catch {
    connected.value = false
    aiReady.value = false
  }
})
</script>

<style scoped>
.sidebar {
  width: 200px; min-width: 200px;
  background: var(--bg-sidebar, #010409);
  display: flex; flex-direction: column;
  overflow: hidden;
  border-right: 1px solid rgba(255,255,255,0.05);
}

/* ── Logo ── */
.logo {
  display: flex; align-items: center; gap: 9px;
  padding: 0 16px;
  height: 52px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.logo-mark {
  width: 28px; height: 28px;
  background: var(--accent);
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.logo-text {
  font-family: 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 13px; font-weight: 600;
  color: var(--text-sidebar-active, #e6edf3);
  letter-spacing: .06em;
}
.logo-accent { color: var(--accent); }

/* ── Nav ── */
.nav { flex: 1; padding: 8px 0; display: flex; flex-direction: column; overflow-y: auto; }
.nav-item {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 16px;
  color: var(--text-sidebar, #8b949e);
  text-decoration: none;
  font-size: 13px; font-weight: 400;
  transition: background .12s, color .12s;
  position: relative;
  border-left: 2px solid transparent;
}
.nav-item:hover {
  background: var(--sidebar-hover, rgba(255,255,255,0.04));
  color: var(--text-sidebar-active, #e6edf3);
  border-left-color: rgba(255,255,255,0.1);
}
.nav-item.active {
  background: var(--sidebar-active, rgba(56,139,253,0.12));
  color: var(--text-sidebar-active, #e6edf3);
  border-left-color: var(--accent, #388bfd);
  font-weight: 500;
}
.nav-item.active::after {
  content: '';
  position: absolute; left: 0; top: 0; bottom: 0; width: 2px;
  background: var(--accent);
  box-shadow: 0 0 8px var(--accent-glow);
}
.nav-icon { display: flex; align-items: center; width: 16px; flex-shrink: 0; }

/* ── Footer ── */
.sidebar-footer {
  padding: 10px 14px 14px;
  border-top: 1px solid rgba(255,255,255,0.05);
  display: flex; flex-direction: column; gap: 5px;
  flex-shrink: 0;
}

.theme-row { display: flex; gap: 4px; margin-bottom: 2px; }
.theme-btn {
  flex: 1; padding: 4px 6px; font-size: 11px;
  border-radius: 3px; border: 1px solid rgba(255,255,255,0.08);
  background: transparent; color: var(--text-sidebar);
  cursor: pointer; transition: all .12s; text-align: center;
  font-family: inherit;
}
.theme-btn:hover { background: rgba(255,255,255,0.06); color: var(--text-sidebar-active); }
.theme-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.divider { height: 1px; background: rgba(255,255,255,0.05); margin: 3px 0; }

/* ── Status dots ── */
.conn-status { display: flex; align-items: center; gap: 7px; font-size: 11px; color: var(--text-sidebar); }
.dot { position: relative; width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.conn-status.ok .dot  { background: var(--success, #3fb950); }
.conn-status.err .dot { background: var(--error,   #f85149); }

/* Pulse ring on ok status */
.conn-status.ok .dot::after {
  content: '';
  position: absolute;
  inset: -2px;
  border-radius: 50%;
  border: 1px solid var(--success, #3fb950);
  animation: pulse-dot 2s cubic-bezier(.4,0,.6,1) infinite;
  opacity: 0;
}
@keyframes pulse-dot {
  0%   { transform: scale(1);   opacity: .6; }
  70%  { transform: scale(2.2); opacity: 0;  }
  100% { transform: scale(2.2); opacity: 0;  }
}

.conn-label { color: var(--text-sidebar); }
.ai-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }

/* ── User ── */
.user-row { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; }
.user-info { display: flex; align-items: center; gap: 7px; text-decoration: none; }
.user-avatar {
  width: 24px; height: 24px;
  background: var(--accent);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: #fff; font-weight: 700;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(56,139,253,0.3);
  font-family: 'DM Sans', sans-serif;
}
.user-name { font-size: 12px; color: var(--text-sidebar-active); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 110px; }
.logout-btn {
  background: none; border: none;
  color: var(--text-muted, #3d444d);
  cursor: pointer; display: flex; align-items: center;
  padding: 3px; border-radius: 3px;
  transition: color .15s, background .15s;
}
.logout-btn:hover { color: var(--error); background: rgba(248,81,73,0.1); }

.admin-links { display: flex; flex-direction: column; gap: 3px; }
.admin-link {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; color: var(--accent);
  text-decoration: none; padding: 2px 0;
  transition: opacity .12s;
}
.admin-link:hover { opacity: .75; }
</style>
