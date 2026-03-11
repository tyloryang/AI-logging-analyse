import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import LogAnalysis from '../views/LogAnalysis.vue'
import MetricsMonitor from '../views/MetricsMonitor.vue'
import AlertHistory from '../views/AlertHistory.vue'
import AnalysisReport from '../views/AnalysisReport.vue'
import HostCMDB from '../views/HostCMDB.vue'

const routes = [
  { path: '/',          component: Dashboard,      name: 'dashboard'   },
  { path: '/logs',      component: LogAnalysis,    name: 'logs'        },
  { path: '/metrics',   component: MetricsMonitor, name: 'metrics'     },
  { path: '/alerts',    component: AlertHistory,   name: 'alerts'      },
  { path: '/report',    component: AnalysisReport, name: 'report'      },
  { path: '/hosts',     component: HostCMDB,       name: 'hosts'       },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
