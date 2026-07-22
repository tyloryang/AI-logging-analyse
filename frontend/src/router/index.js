import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  // ── 公开路由 ─────────────────────────────────────────────────
  { path: '/login',           component: () => import('../views/LoginView.vue'),     name: 'login',    meta: { public: true } },
  { path: '/register',        component: () => import('../views/RegisterView.vue'),  name: 'register', meta: { public: true } },
  { path: '/forgot-password', component: () => import('../views/ForgotPassword.vue'),name: 'forgot',   meta: { public: true } },
  { path: '/403',             component: () => import('../views/View403.vue'),       name: '403',      meta: { public: true } },

  // ── 1. 仪表盘 ─────────────────────────────────────────────────
  { path: '/', component: () => import('../views/Dashboard.vue'), name: 'dashboard', meta: { module: 'dashboard' } },

  // ── 2. CMDB ───────────────────────────────────────────────────
  { path: '/cmdb', component: () => import('../views/HostCMDB.vue'), name: 'cmdb', meta: { module: 'cmdb' } },

  // ── 3. 主机中心 ───────────────────────────────────────────────
  { path: '/hosts/tasks',  component: () => import('../views/HostTaskView.vue'),    name: 'host-tasks', meta: { module: 'host' } },
  { path: '/hosts/workbench', component: () => import('../views/TaskWorkbenchView.vue'), name: 'host-workbench', meta: { module: 'host' } },
  { path: '/hosts/cron',   component: () => import('../views/HostCronView.vue'),    name: 'host-cron', meta: { module: 'host' } },
  { path: '/hosts/apply',  component: () => import('../views/HostApplyView.vue'),   name: 'host-apply', meta: { module: 'host' } },
  { path: '/workflows', component: () => import('../views/WorkflowView.vue'), name: 'workflows', meta: { module: 'workflow' } },

  // ── 4. 多云管理（已隐藏）─────────────────────────────────────
  // { path: '/cloud', component: () => import('../views/CloudManageView.vue'), name: 'cloud' },

  // ── 5. 工单系统 ───────────────────────────────────────────────
  { path: '/tickets/deploy',   component: () => import('../views/TicketDeployView.vue'),   name: 'ticket-deploy', meta: { module: 'ticket' } },
  { path: '/tickets/sql',      component: () => import('../views/TicketSqlView.vue'),      name: 'ticket-sql', meta: { module: 'ticket' } },
  { path: '/tickets/incident', component: () => import('../views/TicketIncidentView.vue'), name: 'ticket-incident', meta: { module: 'ticket' } },
  { path: '/tickets/approval', component: () => import('../views/TicketApprovalView.vue'), name: 'ticket-approval', meta: { module: 'ticket' } },

  // ── 6. 容器管理 ───────────────────────────────────────────────
  { path: '/containers', component: () => import('../views/ContainerView.vue'), name: 'containers', meta: { module: 'container' } },
  { path: '/k8s/topology',   component: () => import('../views/K8sTopologyView.vue'),         name: 'k8s-topology', meta: { module: 'container' } },
  { path: '/k8s/relations',  component: () => import('../views/K8sResourceRelationView.vue'),  name: 'k8s-relations', meta: { module: 'container' } },

  // ── 7. 中间件 ─────────────────────────────────────────────────
  { path: '/middleware',    component: () => import('../views/MiddlewareView.vue'),     name: 'middleware', meta: { module: 'middleware' } },
  { path: '/middleware/redis', component: () => import('../views/RedisClusterView.vue'), name: 'middleware-redis', meta: { module: 'middleware' } },
  { path: '/middleware/kafka', component: () => import('../views/KafkaClusterView.vue'), name: 'middleware-kafka', meta: { module: 'middleware' } },
  { path: '/middleware/es', component: () => import('../views/ElasticsearchView.vue'),  name: 'middleware-es', meta: { module: 'middleware' } },

  // ── 7.5. CI/CD ────────────────────────────────────────────────
  { path: '/cicd/jenkins', component: () => import('../views/JenkinsView.vue'), name: 'cicd-jenkins', meta: { module: 'cicd' } },

  // ── 8. 可观测性 ───────────────────────────────────────────────
  { path: '/observability/overview', component: () => import('../views/Dashboard.vue'),      name: 'obs-overview', meta: { module: 'dashboard' } },
  { path: '/observability/bigscreen', component: () => import('../views/BigScreenView.vue'), name: 'obs-bigscreen', meta: { fullscreen: true, module: 'dashboard' } },
  // 自定义 PromQL 图表面板（替代 指标查询 / 接口指标·Prom，两者组件文件保留）
  { path: '/observability/metric-charts', component: () => import('../views/PromChartsView.vue'), name: 'obs-metric-charts', meta: { module: 'metrics' } },
  { path: '/observability/metrics-query', redirect: '/observability/metric-charts' },
  { path: '/observability/http-server-metrics', redirect: '/observability/metric-charts' },
  { path: '/observability/grafana',  component: () => import('../views/GrafanaView.vue'),    name: 'obs-grafana',  meta: { module: 'metrics' } },
  { path: '/observability/logs',     component: () => import('../views/LogAnalysis.vue'),    name: 'obs-logs',     meta: { module: 'log' } },
  { path: '/observability/trace',    component: () => import('../views/SkyWalkingView.vue'), name: 'obs-trace',    meta: { module: 'skywalking' } },
  { path: '/observability/api-red',  component: () => import('../views/ApiRedView.vue'),     name: 'obs-api-red',  meta: { module: 'skywalking' } },
  // AlertHistory 已下线（与 AIOps 告警中心重复），组件文件保留；旧路径重定向到告警中心
  { path: '/observability/alerts',   redirect: '/aiops/alerts' },

  // ── 9. 事件墙 ─────────────────────────────────────────────────
  { path: '/events', component: () => import('../views/EventWallView.vue'), name: 'events', meta: { module: 'events' } },

  // ── 10. 工具市场 ──────────────────────────────────────────────
  { path: '/tools',         component: () => import('../views/ToolMarketView.vue'), name: 'tools', meta: { module: 'tools' } },
  { path: '/tools/java-diagnostics', component: () => import('../views/JavaDiagnosticView.vue'), name: 'tools-java-diagnostics', meta: { module: 'ssh' } },
  // SSH 终端独立保留，CMDB 内部入口改为凭证管理。
  { path: '/tools/ssh', component: () => import('../views/SSHTerminal.vue'), name: 'tools-ssh', meta: { module: 'ssh' } },
  { path: '/tools/slowlog', component: () => import('../views/SlowLogView.vue'),    name: 'tools-slowlog', meta: { module: 'slowlog' } },
  { path: '/tools/report',  component: () => import('../views/AnalysisReport.vue'), name: 'tools-report',  meta: { module: 'report' } },
  { path: '/tools/knowledge', component: () => import('../views/KnowledgeView.vue'), name: 'tools-knowledge', meta: { module: 'knowledge' } },
  // MetricsMonitor 已下线（仪表盘/指标图表子集），组件文件保留；旧路径重定向到指标图表
  { path: '/tools/metrics', redirect: '/observability/metric-charts' },

  // ── 11. AIOps 智能运维 ────────────────────────────────────────
  // FaultDashboard 已下线（与监控大屏重复），组件文件保留；旧路径重定向到监控大屏
  { path: '/aiops/fault',     redirect: '/observability/bigscreen' },
  { path: '/aiops/alerts',    component: () => import('../views/AlertCenterView.vue'),    name: 'aiops-alerts', meta: { module: 'alert' } },
  { path: '/aiops/rca',       component: () => import('../views/RCAView.vue'),            name: 'aiops-rca', meta: { module: 'agent' } },
  { path: '/aiops/anomaly',   component: () => import('../views/AnomalyView.vue'),        name: 'aiops-anomaly', meta: { module: 'agent' } },
  { path: '/aiops/knowledge-graph', component: () => import('../views/KnowledgeGraphView.vue'), name: 'aiops-kgraph', meta: { module: 'knowledge' } },
  { path: '/aiops/workbench', component: () => import('../views/AIWorkbenchView.vue'),    name: 'aiops-workbench', meta: { module: 'agent' } },
  // Claude 模块已下线（保留智能助手），组件文件保留；旧路径重定向到智能助手
  { path: '/aiops/claude',    redirect: '/aiops/assistant' },
  { path: '/aiops/cc-haha',  component: () => import('../views/CcHahaView.vue'),         name: 'aiops-cc-haha',   meta: { module: 'agent' } },
  { path: '/aiops/assistant', component: () => import('../views/AIAgent.vue'),     name: 'aiops-assistant', meta: { module: 'agent' } },
  { path: '/aiops/config',    component: () => import('../views/AgentConfig.vue'), name: 'aiops-config', meta: { admin: true } },

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
  { path: '/ssh',          redirect: '/tools/ssh' },
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
