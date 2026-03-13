<template>
  <aside class="sidebar">
    <div class="logo">
      <span class="logo-icon">🤖</span>
      <span class="logo-text">AI Ops</span>
    </div>

    <nav class="nav">
      <RouterLink
        v-for="item in navItems" :key="item.path"
        :to="item.path" class="nav-item"
        :class="{ active: route.path === item.path }"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-label">{{ item.label }}</span>
      </RouterLink>
    </nav>

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

      <div class="conn-status" :class="connected ? 'ok' : 'err'">
        <span class="dot"></span>
        <span>{{ connected ? 'Loki 已连接' : 'Loki 未连接' }}</span>
      </div>
      <div class="conn-status" :class="promConnected ? 'ok' : 'err'">
        <span class="dot"></span>
        <span>{{ promConnected ? 'Prometheus 已连接' : 'Prometheus 未连接' }}</span>
      </div>
      <div class="conn-status" :class="aiReady ? 'ok' : 'err'" :title="aiProvider">
        <span class="dot"></span>
        <span class="ai-label">{{ aiReady ? 'AI ' + aiShortName : 'AI 未就绪' }}</span>
      </div>
      <div class="divider"></div>
      <div class="user-row">
        <RouterLink to="/profile" class="user-info">
          <span class="user-avatar">{{ auth.user?.username?.charAt(0)?.toUpperCase() }}</span>
          <span class="user-name">{{ auth.user?.displayName || auth.user?.username }}</span>
        </RouterLink>
        <button class="logout-btn" @click="handleLogout" title="退出登录">⏻</button>
      </div>
      <RouterLink v-if="auth.isAdmin" to="/admin/users" class="admin-link">⚙ 用户管理</RouterLink>
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

const allNavItems = [
  { path: '/',        icon: '📊', label: '仪表盘',   module: 'dashboard' },
  { path: '/logs',    icon: '📋', label: '日志分析',  module: 'log'       },
  { path: '/metrics', icon: '📈', label: '指标监控',  module: 'metrics'   },
  { path: '/alerts',  icon: '🔔', label: '告警历史',  module: 'alert'     },
  { path: '/report',  icon: '📝', label: '分析报告',  module: 'report'    },
  { path: '/hosts',   icon: '🖥️', label: 'CMDB 巡检', module: 'cmdb'      },
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
/* 侧边栏使用固定深蓝色，不受主题变量影响 */
.sidebar {
  width: 200px; min-width: 200px;
  background: #182132;
  display: flex; flex-direction: column;
  overflow: hidden;
}

.logo {
  display: flex; align-items: center; gap: 9px;
  padding: 0 16px;
  height: 52px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
  flex-shrink: 0;
}
.logo-icon { font-size: 18px; }
.logo-text { font-size: 14px; font-weight: 600; color: #fff; letter-spacing: .02em; }

.nav { flex: 1; padding: 8px 0; display: flex; flex-direction: column; overflow-y: auto; }
.nav-item {
  display: flex; align-items: center; gap: 9px;
  padding: 10px 20px;
  color: #96a2b9; text-decoration: none;
  font-size: 13px; transition: background .12s, color .12s;
  position: relative;
}
.nav-item:hover { background: rgba(255,255,255,0.06); color: #d3dce6; }
.nav-item.active {
  background: rgba(58,132,255,0.15);
  color: #fff;
}
.nav-item.active::before {
  content: '';
  position: absolute; left: 0; top: 20%; bottom: 20%;
  width: 3px; background: #3a84ff; border-radius: 0 2px 2px 0;
}
.nav-icon { font-size: 14px; width: 16px; text-align: center; }

.sidebar-footer {
  padding: 10px 14px 14px;
  border-top: 1px solid rgba(255,255,255,0.06);
  display: flex; flex-direction: column; gap: 5px;
  flex-shrink: 0;
}

.theme-row { display: flex; gap: 4px; margin-bottom: 2px; }
.theme-btn {
  flex: 1; padding: 4px 6px; font-size: 11px;
  border-radius: 2px; border: 1px solid rgba(255,255,255,0.1);
  background: transparent; color: #96a2b9;
  cursor: pointer; transition: all .12s; text-align: center;
}
.theme-btn:hover { background: rgba(255,255,255,0.08); color: #d3dce6; }
.theme-btn.active { background: #3a84ff; border-color: #3a84ff; color: #fff; }

.divider { height: 1px; background: rgba(255,255,255,0.06); margin: 2px 0; }

.conn-status { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #6b7a99; }
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.conn-status.ok .dot  { background: #2dcb56; }
.conn-status.err .dot { background: #ea3636; }
.ai-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
.user-row { display: flex; align-items: center; justify-content: space-between; padding: 6px 0; }
.user-info { display: flex; align-items: center; gap: 8px; text-decoration: none; color: var(--text-base); }
.user-avatar { width: 26px; height: 26px; background: var(--accent); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; color: #fff; font-weight: 700; flex-shrink: 0; }
.user-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100px; }
.logout-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; padding: 2px 4px; transition: color .2s; }
.logout-btn:hover { color: var(--error); }
.admin-link { display: block; font-size: 12px; color: var(--accent); text-decoration: none; padding: 4px 0; }
.admin-link:hover { text-decoration: underline; }
</style>
