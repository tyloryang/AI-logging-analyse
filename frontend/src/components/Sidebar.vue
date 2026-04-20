<template>
  <aside class="sidebar">
    <!-- Logo -->
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
      <template v-for="item in MENU" :key="item.id">
        <!-- 单级菜单项 -->
        <RouterLink
          v-if="!item.children && canShow(item)"
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item) }"
        >
          <span class="nav-icon" v-html="ICONS[item.icon]"></span>
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
        </RouterLink>

        <!-- 可展开分组 -->
        <div v-else-if="item.children" class="nav-group" :class="{ open: openGroups[item.id] }">
          <button
            class="nav-group-toggle"
            :class="{ active: isGroupActive(item) }"
            @click="toggleGroup(item.id)"
          >
            <span class="nav-icon" v-html="ICONS[item.icon]"></span>
            <span class="nav-label">{{ item.label }}</span>
            <span class="toggle-arrow" :class="{ rotated: openGroups[item.id] }">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>
            </span>
          </button>
          <div class="nav-sub" v-show="openGroups[item.id]">
            <RouterLink
              v-for="child in item.children"
              :key="child.to"
              :to="child.to"
              class="nav-sub-item"
              :class="{ active: route.path === child.to }"
            >
              <span class="sub-dot"></span>
              {{ child.label }}
            </RouterLink>
          </div>
        </div>
      </template>
    </nav>

    <!-- Footer -->
    <div class="sidebar-footer">
      <div class="theme-row">
        <button v-for="t in THEMES" :key="t.id" class="theme-btn" :class="{ active: currentTheme === t.id }" :title="t.label" @click="setTheme(t.id)">{{ t.icon }}</button>
      </div>
      <div class="divider"></div>
      <div class="status-grid">
        <div class="conn-status" :class="health.loki ? 'ok' : 'err'" title="Loki"><span class="dot"></span><span class="conn-label">Loki</span></div>
        <div class="conn-status" :class="health.prom ? 'ok' : 'err'" title="Prometheus"><span class="dot"></span><span class="conn-label">Prom</span></div>
        <div class="conn-status" :class="health.sw ? 'ok' : 'err'" title="SkyWalking"><span class="dot"></span><span class="conn-label">SW</span></div>
        <div class="conn-status" :class="health.ai ? 'ok' : 'err'" :title="health.aiProvider"><span class="dot"></span><span class="conn-label ai-label">{{ health.ai ? aiShortName : 'AI?' }}</span></div>
      </div>
      <div class="divider"></div>
      <div class="user-row">
        <RouterLink to="/profile" class="user-info">
          <span class="user-avatar">{{ auth.user?.username?.charAt(0)?.toUpperCase() }}</span>
          <span class="user-name">{{ auth.user?.displayName || auth.user?.username }}</span>
        </RouterLink>
        <button class="logout-btn" @click="handleLogout" title="退出登录">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
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
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRoute, RouterLink, useRouter } from 'vue-router'
import { api } from '../api/index.js'
import { useTheme, THEMES } from '../composables/useTheme.js'
import { useAuthStore } from '../stores/auth.js'

const route  = useRoute()
const router = useRouter()
const auth   = useAuthStore()
const { currentTheme, setTheme } = useTheme()

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}

// ── 健康状态 ────────────────────────────────────────────────────
const health = reactive({ loki: false, prom: false, sw: false, ai: false, aiProvider: '' })
const aiShortName = computed(() => {
  if (!health.aiProvider) return 'AI'
  if (health.aiProvider.startsWith('Anthropic')) return 'Claude'
  const m = health.aiProvider.match(/\((.+)\)/)
  return m ? m[1].slice(0, 8) : health.aiProvider.slice(0, 8)
})

onMounted(async () => {
  try {
    const r = await api.healthCheck()
    health.loki = r.loki_connected
    health.prom = r.prometheus_connected ?? false
    health.sw   = r.skywalking_connected  ?? false
    health.ai   = r.ai_ready ?? false
    health.aiProvider = r.ai_provider ?? ''
  } catch { /* ignore */ }
})

// ── 菜单定义 ────────────────────────────────────────────────────
const MENU = [
  { id: 'dashboard', icon: 'dashboard', label: '仪表盘', to: '/' },
  { id: 'cmdb',      icon: 'cmdb',      label: 'CMDB',   to: '/cmdb', module: 'cmdb' },
  {
    id: 'host', icon: 'host', label: '主机中心',
    children: [
      { label: '主机资产', to: '/hosts/assets', module: 'cmdb' },
      { label: '任务中心', to: '/hosts/tasks' },
      { label: '定时任务', to: '/hosts/cron' },
      { label: '主机申请', to: '/hosts/apply' },
    ],
  },
  { id: 'cloud', icon: 'cloud', label: '多云管理', to: '/cloud' },
  {
    id: 'ticket', icon: 'ticket', label: '工单系统',
    children: [
      { label: '应用发布', to: '/tickets/deploy' },
      { label: 'SQL 审计', to: '/tickets/sql' },
      { label: '事务工单', to: '/tickets/incident' },
      { label: '审批流',   to: '/tickets/approval' },
    ],
  },
  { id: 'container',  icon: 'container',  label: '容器管理', to: '/containers' },
  {
    id: 'middleware', icon: 'middleware', label: '中间件',
    children: [
      { label: '中间件概览', to: '/middleware' },
      { label: 'Elasticsearch', to: '/middleware/es' },
    ],
  },
  {
    id: 'obs', icon: 'obs', label: '可观测性',
    children: [
      { label: '平台总览', to: '/observability/overview' },
      { label: '监控看板', to: '/observability/grafana', module: 'metrics' },
      { label: '日志中心', to: '/observability/logs',    module: 'log' },
      { label: '链路追踪', to: '/observability/trace',   module: 'skywalking' },
      { label: '告警中心', to: '/observability/alerts',  module: 'alert' },
    ],
  },
  { id: 'events', icon: 'event',  label: '事件墙',   to: '/events' },
  { id: 'tools',  icon: 'tools',  label: '工具市场', to: '/tools' },
  {
    id: 'aiops', icon: 'aiops', label: 'AIOps 智能运维',
    children: [
      { label: '🔴 故障大盘', to: '/aiops/fault' },
      { label: '🔔 告警中心', to: '/aiops/alerts' },
      { label: '🧠 根因分析', to: '/aiops/rca' },
      { label: '📊 异常检测', to: '/aiops/anomaly' },
      { label: '💬 智能助手', to: '/aiops/assistant' },
      { label: '⚙ 智能配置',  to: '/aiops/config' },
    ],
  },
]

// ── 展开状态 ────────────────────────────────────────────────────
const openGroups = reactive({
  host:       false,
  ticket:     false,
  middleware: false,
  obs:        true,
  aiops:      false,
})

function toggleGroup(id) {
  openGroups[id] = !openGroups[id]
}

// 路由变化时自动展开对应分组
function syncOpenGroups(path) {
  MENU.forEach(item => {
    if (item.children) {
      const match = item.children.some(c => path === c.to || path.startsWith(c.to + '/'))
      if (match) openGroups[item.id] = true
    }
  })
}
watch(() => route.path, syncOpenGroups, { immediate: true })

// ── 激活判断 ────────────────────────────────────────────────────
function isActive(item) {
  return item.to === '/' ? route.path === '/' : route.path.startsWith(item.to)
}
function isGroupActive(item) {
  return item.children?.some(c => route.path === c.to || route.path.startsWith(c.to + '/'))
}

// ── 权限显示 ────────────────────────────────────────────────────
function canShow(item) {
  return !item.module || auth.can(item.module, 'view')
}

// ── 图标库 ──────────────────────────────────────────────────────
const ICONS = {
  dashboard:  `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>`,
  cmdb:       `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`,
  host:       `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  cloud:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z"/></svg>`,
  ticket:     `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z"/></svg>`,
  container:  `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>`,
  middleware: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>`,
  obs:        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`,
  event:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 01-3.46 0"/></svg>`,
  tools:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>`,
  aiops:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M9 11V7a3 3 0 016 0v4"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/><path d="M12 3v2"/></svg>`,
}
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
  padding: 0 14px; height: 56px;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  flex-shrink: 0;
}
.logo-mark {
  width: 30px; height: 30px;
  background: var(--accent);
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(56,139,253,0.35);
}
.logo-texts { display: flex; flex-direction: column; gap: 1px; }
.logo-text  { font-family: 'JetBrains Mono','Cascadia Code',monospace; font-size: 13px; font-weight: 700; color: var(--text-sidebar-active,#fff); letter-spacing:.03em; line-height:1.2; }
.logo-accent { color: var(--accent); }
.logo-sub   { font-size: 9px; font-weight: 600; color: var(--accent); letter-spacing:.12em; line-height:1; opacity:.8; }

/* ── Nav ── */
.nav { flex: 1; padding: 6px 0 4px; display: flex; flex-direction: column; overflow-y: auto; scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; }
.nav::-webkit-scrollbar { width: 3px; }
.nav::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

/* ── 单级菜单项 ── */
.nav-item {
  display: flex; align-items: center; gap: 9px;
  padding: 8px 14px;
  color: var(--text-sidebar, #96a2b9);
  text-decoration: none; font-size: 13px; font-weight: 400;
  transition: background .12s, color .12s;
  border-left: 2px solid transparent;
  cursor: pointer;
}
.nav-item:hover { background: rgba(255,255,255,0.05); color: var(--text-sidebar-active,#fff); }
.nav-item.active { background: rgba(56,139,253,0.14); color: #fff; border-left-color: var(--accent,#388bfd); font-weight: 500; }
.nav-icon { display: flex; align-items: center; width: 15px; flex-shrink: 0; opacity: .75; }
.nav-item:hover .nav-icon, .nav-item.active .nav-icon { opacity: 1; }
.nav-badge { margin-left: auto; font-size: 10px; background: var(--accent); color: #fff; padding: 1px 5px; border-radius: 8px; font-weight: 600; }

/* ── 展开分组 ── */
.nav-group-toggle {
  display: flex; align-items: center; gap: 9px;
  padding: 8px 14px; width: 100%;
  color: var(--text-sidebar,#96a2b9);
  font-size: 13px; font-weight: 400;
  background: none; border: none; border-left: 2px solid transparent;
  cursor: pointer; text-align: left;
  transition: background .12s, color .12s;
}
.nav-group-toggle:hover { background: rgba(255,255,255,0.05); color: var(--text-sidebar-active,#fff); }
.nav-group-toggle .nav-icon { opacity: .75; }
.nav-group-toggle:hover .nav-icon { opacity: 1; }
.nav-group-toggle.active { color: var(--accent); border-left-color: transparent; }
.nav-group-toggle.active .nav-icon { opacity: 1; }

.toggle-arrow { margin-left: auto; display: flex; align-items: center; transition: transform .2s; opacity: .5; }
.toggle-arrow.rotated { transform: rotate(180deg); }

.nav-sub { display: flex; flex-direction: column; }
.nav-sub-item {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 14px 7px 36px;
  color: var(--text-sidebar,#96a2b9); font-size: 12.5px;
  text-decoration: none; border-left: 2px solid transparent;
  transition: background .12s, color .12s;
}
.nav-sub-item:hover { background: rgba(255,255,255,0.04); color: var(--text-sidebar-active,#fff); }
.nav-sub-item.active { color: #fff; background: rgba(56,139,253,0.14); border-left-color: var(--accent); font-weight: 500; }
.sub-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; opacity: .4; flex-shrink: 0; }
.nav-sub-item.active .sub-dot { opacity: 1; background: var(--accent); }

/* ── Footer ── */
.sidebar-footer { padding: 8px 12px 12px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; flex-direction: column; gap: 5px; flex-shrink: 0; }
.theme-row { display: flex; gap: 4px; }
.theme-btn { flex: 1; padding: 4px; font-size: 13px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.08); background: transparent; cursor: pointer; transition: all .12s; text-align: center; }
.theme-btn:hover { background: rgba(255,255,255,0.06); }
.theme-btn.active { background: var(--accent); border-color: var(--accent); }
.divider { height: 1px; background: rgba(255,255,255,0.06); margin: 3px 0; }
.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 8px; }
.conn-status { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-sidebar); }
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; position: relative; }
.conn-status.ok .dot  { background: var(--success,#3fb950); }
.conn-status.err .dot { background: var(--error,#f85149); }
.conn-label { color: rgba(255,255,255,0.45); font-size: 10.5px; }
.ai-label { max-width: 55px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-row { display: flex; align-items: center; justify-content: space-between; padding: 3px 0; }
.user-info { display: flex; align-items: center; gap: 7px; text-decoration: none; }
.user-avatar { width: 24px; height: 24px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #fff; font-weight: 700; flex-shrink: 0; }
.user-name { font-size: 12px; color: rgba(255,255,255,0.7); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100px; }
.logout-btn { background: none; border: none; color: rgba(255,255,255,0.25); cursor: pointer; display: flex; align-items: center; padding: 3px; border-radius: 3px; transition: color .15s, background .15s; }
.logout-btn:hover { color: var(--error); background: rgba(248,81,73,0.12); }
.admin-links { display: flex; flex-direction: column; gap: 2px; }
.admin-link { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--accent); text-decoration: none; padding: 2px 0; opacity: .8; transition: opacity .12s; }
.admin-link:hover { opacity: 1; }
</style>
