import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import Dashboard from '../views/Dashboard.vue'
import LogAnalysis from '../views/LogAnalysis.vue'
import MetricsMonitor from '../views/MetricsMonitor.vue'
import AlertHistory from '../views/AlertHistory.vue'
import AnalysisReport from '../views/AnalysisReport.vue'
import HostCMDB from '../views/HostCMDB.vue'
import SSHTerminal from '../views/SSHTerminal.vue'
import LoginView from '../views/LoginView.vue'
import RegisterView from '../views/RegisterView.vue'
import ForgotPassword from '../views/ForgotPassword.vue'
import ProfileView from '../views/ProfileView.vue'
import AdminUsers from '../views/AdminUsers.vue'
import SettingsView from '../views/SettingsView.vue'
import View403 from '../views/View403.vue'
import SlowLogView from '../views/SlowLogView.vue'

const routes = [
  // 公开路由
  { path: '/login',           component: LoginView,      name: 'login',    meta: { public: true } },
  { path: '/register',        component: RegisterView,   name: 'register', meta: { public: true } },
  { path: '/forgot-password', component: ForgotPassword, name: 'forgot',   meta: { public: true } },
  { path: '/403',             component: View403,        name: '403',      meta: { public: true } },

  // 需登录路由
  { path: '/',        component: Dashboard,      name: 'dashboard', meta: { module: 'dashboard' } },
  { path: '/logs',    component: LogAnalysis,    name: 'logs',      meta: { module: 'log' } },
  { path: '/metrics', component: MetricsMonitor, name: 'metrics',   meta: { module: 'metrics' } },
  { path: '/alerts',  component: AlertHistory,   name: 'alerts',    meta: { module: 'alert' } },
  { path: '/report',  component: AnalysisReport, name: 'report',    meta: { module: 'report' } },
  { path: '/hosts',   component: HostCMDB,       name: 'hosts',     meta: { module: 'cmdb' } },
  { path: '/ssh',     component: SSHTerminal,    name: 'ssh',       meta: { module: 'ssh'  } },
  { path: '/slowlog', component: SlowLogView,    name: 'slowlog',   meta: { module: 'slowlog' } },
  { path: '/profile', component: ProfileView,    name: 'profile' },
  { path: '/admin/users',    component: AdminUsers,   name: 'admin-users', meta: { admin: true } },
  { path: '/settings',       component: SettingsView, name: 'settings',    meta: { admin: true } },
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
