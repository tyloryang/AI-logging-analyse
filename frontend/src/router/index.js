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
  { path: '/hosts/tasks',  component: () => import('../views/HostTaskView.vue'),    name: 'host-tasks' },
  { path: '/hosts/workbench', component: () => import('../views/TaskWorkbenchView.vue'), name: 'host-workbench' },
  { path: '/hosts/cron',   component: () => import('../views/HostCronView.vue'),    name: 'host-cron' },
  { path: '/hosts/apply',  component: () => import('../views/HostApplyView.vue'),   name: 'host-apply' },
  { path: '/workflows', component: () => import('../views/WorkflowView.vue'), name: 'workflows', meta: { module: 'workflow' } },

  // ── 4. 多云管理（已隐藏）─────────────────────────────────────
  // { path: '/cloud', component: () => import('../views/CloudManageView.vue'), name: 'cloud' },

  // ── 5. 工单系统 ───────────────────────────────────────────────
  { path: '/tickets/deploy',   component: () => import('../views/TicketDeployView.vue'),   name: 'ticket-deploy' },
  { path: '/tickets/sql',      component: () => import('../views/TicketSqlView.vue'),      name: 'ticket-sql' },
  { path: '/tickets/incident', component: () => import('../views/TicketIncidentView.vue'), name: 'ticket-incident' },
  { path: '/tickets/approval', component: () => import('../views/TicketApprovalView.vue'), name: 'ticket-approval' },

  // ── 6. 容器管理 ───────────────────────────────────────────────
  { path: '/containers', component: () => import('../views/ContainerView.vue'), name: 'containers' },
  { path: '/k8s/topology',   component: () => import('../views/K8sTopologyView.vue'),         name: 'k8s-topology' },
  { path: '/k8s/relations',  component: () => import('../views/K8sResourceRelationView.vue'),  name: 'k8s-relations' },

  // ── 7. 中间件 ─────────────────────────────────────────────────
  { path: '/middleware',    component: () => import('../views/MiddlewareView.vue'),     name: 'middleware' },
  { path: '/middleware/redis', component: () => import('../views/RedisClusterView.vue'), name: 'middleware-redis' },
  { path: '/middleware/kafka', component: () => import('../views/KafkaClusterView.vue'), name: 'middleware-kafka' },
  { path: '/middleware/es', component: () => import('../views/ElasticsearchView.vue'),  name: 'middleware-es' },

  // ── 7.5. CI/CD ────────────────────────────────────────────────
  { path: '/cicd/jenkins', component: () => import('../views/JenkinsView.vue'), name: 'cicd-jenkins' },

  // ── 8. 可观测性 ───────────────────────────────────────────────
  { path: '/observability/overview', component: () => import('../views/Dashboard.vue'),      name: 'obs-overview' },
  { path: '/observability/bigscreen', component: () => import('../views/BigScreenView.vue'), name: 'obs-bigscreen', meta: { fullscreen: true } },
  // 自定义 PromQL 图表面板（替代 指标查询 / 接口指标·Prom，两者组件文件保留）
  { path: '/observability/metric-charts', component: () => import('../views/PromChartsView.vue'), name: 'obs-metric-charts', meta: { module: 'metrics' } },
  { path: '/observability/metrics-query', redirect: '/observability/metric-charts' },
  { path: '/observability/http-server-metrics', redirect: '/observability/metric-charts' },
  { path: '/observability/logs-query', component: () => import('../views/LogsQueryView.vue'), name: 'obs-logs-query', meta: { module: 'log' } },
  { path: '/observability/grafana',  component: () => import('../views/GrafanaView.vue'),    name: 'obs-grafana',  meta: { module: 'metrics' } },
  { path: '/observability/logs',     component: () => import('../views/LogAnalysis.vue'),    name: 'obs-logs',     meta: { module: 'log' } },
  { path: '/observability/trace',    component: () => import('../views/SkyWalkingView.vue'), name: 'obs-trace',    meta: { module: 'skywalking' } },
  { path: '/observability/api-red',  component: () => import('../views/ApiRedView.vue'),     name: 'obs-api-red',  meta: { module: 'skywalking' } },
  // AlertHistory 已下线（与 AIOps 告警中心重复），组件文件保留；旧路径重定向到告警中心
  { path: '/observability/alerts',   redirect: '/aiops/alerts' },

  // ── 9. 事件墙 ─────────────────────────────────────────────────
  { path: '/events', component: () => import('../views/EventWallView.vue'), name: 'events' },

  // ── 10. 工具市场 ──────────────────────────────────────────────
  { path: '/tools',         component: () => import('../views/ToolMarketView.vue'), name: 'tools' },
  { path: '/tools/java-diagnostics', component: () => import('../views/JavaDiagnosticView.vue'), name: 'tools-java-diagnostics', meta: { module: 'ssh' } },
  // /tools/ssh 已并入 CMDB，保留路径重定向到 CMDB 的 SSH tab
  { path: '/tools/ssh', redirect: '/cmdb?tab=ssh' },
  { path: '/tools/slowlog', component: () => import('../views/SlowLogView.vue'),    name: 'tools-slowlog', meta: { module: 'slowlog' } },
  { path: '/tools/report',  component: () => import('../views/AnalysisReport.vue'), name: 'tools-report',  meta: { module: 'report' } },
  { path: '/tools/knowledge', component: () => import('../views/KnowledgeView.vue'), name: 'tools-knowledge' },
  // MetricsMonitor 已下线（仪表盘/指标图表子集），组件文件保留；旧路径重定向到指标图表
  { path: '/tools/metrics', redirect: '/observability/metric-charts' },

  // ── 11. AIOps 智能运维 ────────────────────────────────────────
  // FaultDashboard 已下线（与监控大屏重复），组件文件保留；旧路径重定向到监控大屏
  { path: '/aiops/fault',     redirect: '/observability/bigscreen' },
  { path: '/aiops/alerts',    component: () => import('../views/AlertCenterView.vue'),    name: 'aiops-alerts' },
  { path: '/aiops/rca',       component: () => import('../views/RCAView.vue'),            name: 'aiops-rca' },
  { path: '/aiops/anomaly',   component: () => import('../views/AnomalyView.vue'),        name: 'aiops-anomaly' },
  { path: '/aiops/workbench', component: () => import('../views/AIWorkbenchView.vue'),    name: 'aiops-workbench', meta: { module: 'agent' } },
  { path: '/aiops/claude',    component: () => import('../views/ClaudeCodePageView.vue'), name: 'aiops-claude',    meta: { module: 'agent' } },
  { path: '/aiops/cc-haha',  component: () => import('../views/CcHahaView.vue'),         name: 'aiops-cc-haha',   meta: { module: 'agent' } },
  { path: '/aiops/assistant', component: () => import('../views/AIAgent.vue'),     name: 'aiops-assistant', meta: { module: 'agent' } },
  { path: '/aiops/config',    component: () => import('../views/AgentConfig.vue'), name: 'aiops-config' },

  // ── 管理页 ────────────────────────────────────────────────────
  { path: '/profile',     component: () => import('../views/ProfileView.vue'),  name: 'profile' },
  { path: '/admin/users', component: () => import('../views/AdminUsers.vue'),   name: 'admin-users', meta: { admin: true } },
  { path: '/settings',    component: () => import('../views/SettingsView.vue'), name: 'settings',    meta: { admin: true } },

  // ── 旧路由兼容重定向 ──────────────────────────────────────────
  { path: '/logs',         redirect: '/observability/logs' },
  { path: '/metrics',      redirect: '/observability/metric-charts' },
  { path: '/grafana',      redirect: '/observability/grafana' },
  { path: '/alerts',       redirect: '/aiops/alerts' },
  { path: '/skywalking',   redirect: '/observability/trace' },
  { path: '/hosts/assets', redirect: '/cmdb' },
  { path: '/hosts',        redirect: '/cmdb' },
  { path: '/ssh',          redirect: '/cmdb?tab=ssh' },
  { path: '/slowlog',      redirect: '/tools/slowlog' },
  { path: '/report',       redirect: '/tools/report' },
  { path: '/agent',        redirect: '/aiops/assistant' },
  { path: '/workbench',    redirect: '/aiops/workbench' },
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
