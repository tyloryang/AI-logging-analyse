import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  // 公开路由
  { path: '/login',           component: () => import('../views/LoginView.vue'),     name: 'login',    meta: { public: true } },
  { path: '/register',        component: () => import('../views/RegisterView.vue'),  name: 'register', meta: { public: true } },
  { path: '/forgot-password', component: () => import('../views/ForgotPassword.vue'),name: 'forgot',   meta: { public: true } },
  { path: '/403',             component: () => import('../views/View403.vue'),       name: '403',      meta: { public: true } },

  // 需登录路由
  { path: '/',        component: () => import('../views/Dashboard.vue'),      name: 'dashboard', meta: { module: 'dashboard' } },
  { path: '/logs',    component: () => import('../views/LogAnalysis.vue'),    name: 'logs',      meta: { module: 'log' } },
  { path: '/metrics', component: () => import('../views/MetricsMonitor.vue'), name: 'metrics',   meta: { module: 'metrics' } },
  { path: '/alerts',  component: () => import('../views/AlertHistory.vue'),   name: 'alerts',    meta: { module: 'alert' } },
  { path: '/report',  component: () => import('../views/AnalysisReport.vue'), name: 'report',    meta: { module: 'report' } },
  { path: '/hosts',   component: () => import('../views/HostCMDB.vue'),       name: 'hosts',     meta: { module: 'cmdb' } },
  { path: '/ssh',     component: () => import('../views/SSHTerminal.vue'),    name: 'ssh',       meta: { module: 'ssh'  } },
  { path: '/slowlog', component: () => import('../views/SlowLogView.vue'),    name: 'slowlog',   meta: { module: 'slowlog' } },
  { path: '/agent',      component: () => import('../views/AIAgent.vue'),        name: 'agent',      meta: { module: 'agent'      } },
  { path: '/skywalking', component: () => import('../views/SkyWalkingView.vue'), name: 'skywalking', meta: { module: 'skywalking' } },
  { path: '/profile',       component: () => import('../views/ProfileView.vue'), name: 'profile' },
  { path: '/admin/users',   component: () => import('../views/AdminUsers.vue'),  name: 'admin-users', meta: { admin: true } },
  { path: '/settings',      component: () => import('../views/SettingsView.vue'),name: 'settings',    meta: { admin: true } },
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
