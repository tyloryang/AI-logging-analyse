import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  // ── 公开路由 ─────────────────────────────────────────────────
  { path: '/login',           component: () => import('../views/LoginView.vue'),     name: 'login',    meta: { public: true } },
  { path: '/register',        component: () => import('../views/RegisterView.vue'),  name: 'register', meta: { public: true } },
  { path: '/forgot-password', component: () => import('../views/ForgotPassword.vue'),name: 'forgot',   meta: { public: true } },
  { path: '/403',             component: () => import('../views/View403.vue'),       name: '403',      meta: { public: true } },

  // ── 1. 仪表盘 ─────────────────────────────────────────────────
  { path: '/', component: () => import('../views/Dashboard.vue'), name: 'dashboard' },

  // ── 2. CMDB ───────────────────────────────────────────────────
  { path: '/cmdb', component: () => import('../views/HostCMDB.vue'), name: 'cmdb', meta: { module: 'cmdb' } },

  // ── 3. 主机中心 ───────────────────────────────────────────────
  { path: '/hosts/assets', component: () => import('../views/HostCMDB.vue'),        name: 'host-assets', meta: { module: 'cmdb' } },
  { path: '/hosts/tasks',  component: () => import('../views/HostTaskView.vue'),    name: 'host-tasks' },
  { path: '/hosts/cron',   component: () => import('../views/HostCronView.vue'),    name: 'host-cron' },
  { path: '/hosts/apply',  component: () => import('../views/HostApplyView.vue'),   name: 'host-apply' },

  // ── 4. 多云管理 ───────────────────────────────────────────────
  { path: '/cloud', component: () => import('../views/CloudManageView.vue'), name: 'cloud' },

  // ── 5. 工单系统 ───────────────────────────────────────────────
  { path: '/tickets/deploy',   component: () => import('../views/TicketDeployView.vue'),   name: 'ticket-deploy' },
  { path: '/tickets/sql',      component: () => import('../views/TicketSqlView.vue'),      name: 'ticket-sql' },
  { path: '/tickets/incident', component: () => import('../views/TicketIncidentView.vue'), name: 'ticket-incident' },
  { path: '/tickets/approval', component: () => import('../views/TicketApprovalView.vue'), name: 'ticket-approval' },

  // ── 6. 容器管理 ───────────────────────────────────────────────
  { path: '/containers', component: () => import('../views/ContainerView.vue'), name: 'containers' },

  // ── 7. 中间件 ─────────────────────────────────────────────────
  { path: '/middleware',    component: () => import('../views/MiddlewareView.vue'),     name: 'middleware' },
  { path: '/middleware/es', component: () => import('../views/ElasticsearchView.vue'),  name: 'middleware-es' },

  // ── 8. 可观测性 ───────────────────────────────────────────────
  { path: '/observability/overview', component: () => import('../views/Dashboard.vue'),      name: 'obs-overview' },
  { path: '/observability/grafana',  component: () => import('../views/GrafanaView.vue'),    name: 'obs-grafana',  meta: { module: 'metrics' } },
  { path: '/observability/logs',     component: () => import('../views/LogAnalysis.vue'),    name: 'obs-logs',     meta: { module: 'log' } },
  { path: '/observability/trace',    component: () => import('../views/SkyWalkingView.vue'), name: 'obs-trace',    meta: { module: 'skywalking' } },
  { path: '/observability/alerts',   component: () => import('../views/AlertHistory.vue'),   name: 'obs-alerts',   meta: { module: 'alert' } },

  // ── 9. 事件墙 ─────────────────────────────────────────────────
  { path: '/events', component: () => import('../views/EventWallView.vue'), name: 'events' },

  // ── 10. 工具市场 ──────────────────────────────────────────────
  { path: '/tools',         component: () => import('../views/ToolMarketView.vue'), name: 'tools' },
  { path: '/tools/ssh',     component: () => import('../views/SSHTerminal.vue'),    name: 'tools-ssh',     meta: { module: 'ssh' } },
  { path: '/tools/slowlog', component: () => import('../views/SlowLogView.vue'),    name: 'tools-slowlog', meta: { module: 'slowlog' } },
  { path: '/tools/report',  component: () => import('../views/AnalysisReport.vue'), name: 'tools-report',  meta: { module: 'report' } },
  { path: '/tools/metrics', component: () => import('../views/MetricsMonitor.vue'), name: 'tools-metrics', meta: { module: 'metrics' } },

  // ── 11. AIOps ─────────────────────────────────────────────────
  { path: '/aiops/assistant', component: () => import('../views/AIAgent.vue'),     name: 'aiops-assistant', meta: { module: 'agent' } },
  { path: '/aiops/config',    component: () => import('../views/AgentConfig.vue'), name: 'aiops-config',    meta: { module: 'agent' } },

  // ── 管理页 ────────────────────────────────────────────────────
  { path: '/profile',     component: () => import('../views/ProfileView.vue'),  name: 'profile' },
  { path: '/admin/users', component: () => import('../views/AdminUsers.vue'),   name: 'admin-users', meta: { admin: true } },
  { path: '/settings',    component: () => import('../views/SettingsView.vue'), name: 'settings',    meta: { admin: true } },

  // ── 旧路由兼容重定向 ──────────────────────────────────────────
  { path: '/logs',         redirect: '/observability/logs' },
  { path: '/metrics',      redirect: '/tools/metrics' },
  { path: '/grafana',      redirect: '/observability/grafana' },
  { path: '/alerts',       redirect: '/observability/alerts' },
  { path: '/skywalking',   redirect: '/observability/trace' },
  { path: '/hosts',        redirect: '/cmdb' },
  { path: '/ssh',          redirect: '/tools/ssh' },
  { path: '/slowlog',      redirect: '/tools/slowlog' },
  { path: '/report',       redirect: '/tools/report' },
  { path: '/agent',        redirect: '/aiops/assistant' },
  { path: '/agent-config', redirect: '/aiops/config' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true

  const auth = useAuthStore()
  if (!auth.isLoggedIn) {
    const ok = await auth.fetchMe()
    if (!ok) return '/login'
  }

  if (to.meta.admin && !auth.isAdmin) return '/403'
  if (to.meta.module && !auth.can(to.meta.module, 'view')) return '/403'

  return true
})

export default router
