<template>
  <aside class="sidebar">
    <!-- Logo -->
    <div class="logo">
      <span class="logo-mark">
        <UiIcon name="boxes" :size="16" />
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
          <UiIcon class="nav-icon" :name="item.icon" :size="14" />
          <span class="nav-label">{{ item.label }}</span>
          <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
        </RouterLink>

        <!-- 可展开分组 -->
        <div v-else-if="item.children && visibleChildren(item).length && canShow(item)" class="nav-group" :class="{ open: openGroups[item.id] }">
          <button
            class="nav-group-toggle"
            :class="{ active: isGroupActive(item) }"
            @click="toggleGroup(item.id)"
          >
            <UiIcon class="nav-icon" :name="item.icon" :size="14" />
            <span class="nav-label">{{ item.label }}</span>
            <span class="toggle-arrow" :class="{ rotated: openGroups[item.id] }">
              <UiIcon name="chevrondown" :size="11" />
            </span>
          </button>
          <div class="nav-sub" v-show="openGroups[item.id]">
            <RouterLink
              v-for="child in visibleChildren(item)"
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
        <button
          v-for="t in THEMES"
          :key="t.id"
          class="theme-btn"
          :class="{ active: currentTheme === t.id }"
          :title="t.label"
          @click="setTheme(t.id)"
        >
          <UiIcon :name="t.icon" :size="13" />
        </button>
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
          <UiIcon name="logout" :size="13" />
        </button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, RouterLink, useRouter } from 'vue-router'
import UiIcon from './UiIcon.vue'
import { fetchHealthStatus, getAiModelShort } from '../composables/useHealthStatus.js'
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
  return getAiModelShort(health.aiProvider).slice(0, 8)
})

let sidebarMounted = true
onBeforeUnmount(() => {
  sidebarMounted = false
})

onMounted(async () => {
  try {
    const r = await fetchHealthStatus()
    if (!sidebarMounted) return
    health.loki = r.loki_connected
    health.prom = r.prometheus_connected ?? false
    health.sw   = r.skywalking_connected  ?? false
    health.ai   = r.ai_ready ?? false
    health.aiProvider = r.ai_provider ?? ''
  } catch { /* ignore */ }
})

// ── 菜单定义 ────────────────────────────────────────────────────
const MENU = [
  { id: 'dashboard', icon: 'gauge', label: '仪表盘', to: '/', module: 'dashboard' },
  {
    id: 'host', icon: 'server', label: '主机中心',
    children: [
      { label: 'CMDB',     to: '/cmdb', module: 'cmdb' },
      { label: '任务工作台', to: '/hosts/workbench', module: 'host' },
      { label: '任务中心', to: '/hosts/tasks', module: 'host' },
      { label: '定时任务', to: '/hosts/cron', module: 'host' },
      { label: '主机申请', to: '/hosts/apply', module: 'host' },
    ],
  },
  // { id: 'cloud', icon: 'cloud', label: '多云管理', to: '/cloud' },
  {
    id: 'ticket', icon: 'clipboardlist', label: '工单系统',
    children: [
      { label: '应用发布', to: '/tickets/deploy', module: 'ticket' },
      { label: 'SQL 审计', to: '/tickets/sql', module: 'ticket' },
      { label: '事务工单', to: '/tickets/incident', module: 'ticket' },
      { label: '审批流',   to: '/tickets/approval', module: 'ticket' },
    ],
  },
  {
    id: 'container', icon: 'boxes', label: '容器管理',
    children: [
      { label: '容器列表',      to: '/containers', module: 'container' },
      { label: 'K8s 拓扑流图',  to: '/k8s/topology', module: 'container' },
      { label: '知识拓扑图',    to: '/k8s/relations', module: 'container' },
    ],
  },
  {
    id: 'middleware', icon: 'database', label: '中间件',
    children: [
      { label: '中间件概览', to: '/middleware', module: 'middleware' },
      { label: 'Redis Cluster', to: '/middleware/redis', module: 'middleware' },
      { label: 'Kafka', to: '/middleware/kafka', module: 'middleware' },
      { label: 'Elasticsearch', to: '/middleware/es', module: 'middleware' },
    ],
  },
  { id: 'workflow', icon: 'workflow', label: '工作流', to: '/workflows', module: 'workflow' },
  {
    id: 'cicd', icon: 'gitbranch', label: 'CI/CD',
    children: [
      { label: 'Jenkins', to: '/cicd/jenkins', module: 'cicd' },
    ],
  },
  {
    id: 'obs', icon: 'monitor', label: '可观测性',
    children: [
      { label: '监控大屏',   to: '/observability/bigscreen', module: 'dashboard' },
      { label: '指标图表',   to: '/observability/metric-charts', module: 'metrics' },
      { label: '监控看板',   to: '/observability/grafana', module: 'metrics' },
      { label: '日志分析',   to: '/observability/logs',    module: 'log' },
      { label: '链路追踪',   to: '/observability/trace',   module: 'skywalking' },
      { label: '接口 RED · SW', to: '/observability/api-red', module: 'skywalking' },
      { label: '分析报告',   to: '/tools/report',          module: 'report' },
      { label: '知识库',     to: '/tools/knowledge', module: 'knowledge' },
    ],
  },
  { id: 'events', icon: 'history',  label: '事件墙',   to: '/events', module: 'events' },
  {
    id: 'tools', icon: 'squaredashedmousepointer', label: '工具市场',
    children: [
      { label: '工具概览',   to: '/tools', module: 'tools' },
      { label: 'Java 诊断', to: '/tools/java-diagnostics', module: 'ssh' },
      { label: '慢日志分析', to: '/tools/slowlog',  module: 'slowlog' },
    ],
  },
  {
    id: 'aiops', icon: 'sparkles', label: 'AIOps 智能运维',
    children: [
      { label: '告警中心', to: '/aiops/alerts', module: 'alert' },
      { label: '根因分析', to: '/aiops/rca', module: 'agent' },
      { label: '异常检测', to: '/aiops/anomaly', module: 'agent' },
      { label: '知识图谱', to: '/aiops/knowledge-graph', module: 'knowledge' },
      { label: 'AI 工作台', to: '/aiops/workbench', module: 'agent' },
      { label: '智能助手', to: '/aiops/assistant', module: 'agent' },
      { label: '智能配置',  to: '/aiops/config', admin: true },
    ],
  },
  {
    id: 'system', icon: 'settings2', label: '系统管理', admin: true,
    children: [
      { label: '用户管理', to: '/admin/users', admin: true },
      { label: '系统配置', to: '/settings',    admin: true },
    ],
  },
]

// ── 展开状态 ────────────────────────────────────────────────────
const openGroups = reactive({
  host:       false,
  ticket:     false,
  container:  false,   // 容器管理（含 K8s 拓扑流图）
  middleware: false,
  workflow:   false,
  cicd:       false,
  obs:        true,
  tools:      false,
  aiops:      false,
  system:     false,
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
  if (item.admin && !auth.isAdmin) return false
  return !item.module || auth.can(item.module, 'view')
}

function visibleChildren(item) {
  return (item.children || []).filter(canShow)
}

</script>

<style scoped>
.sidebar {
  width: 224px; min-width: 224px;
  background: linear-gradient(180deg, rgba(23, 21, 19, 0.98), rgba(18, 16, 14, 0.98));
  display: flex; flex-direction: column;
  overflow: hidden;
  border-right: 1px solid rgba(255,255,255,0.05);
  box-shadow: inset -1px 0 0 rgba(255,255,255,0.03), 10px 0 24px rgba(0,0,0,0.12);
  position: relative;
}

.sidebar::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: linear-gradient(180deg, var(--accent), rgba(255,255,255,0.15));
  opacity: 0.9;
}

/* ── Logo ── */
.logo {
  display: flex; align-items: center; gap: 12px;
  padding: 0 18px; height: 68px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
  background: linear-gradient(180deg, rgba(255,255,255,0.03), transparent);
}
.logo-mark {
  width: 34px; height: 34px;
  background: linear-gradient(135deg, var(--accent), #e08a68);
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; flex-shrink: 0;
  box-shadow: 0 10px 24px rgba(200, 108, 78, 0.28);
}
.logo-texts { display: flex; flex-direction: column; gap: 1px; }
.logo-text  { font-family: 'Cascadia Code', 'Consolas','Cascadia Code',monospace; font-size: 13px; font-weight: 700; color: var(--text-sidebar-strong,#fff); letter-spacing:.06em; line-height:1.2; }
.logo-accent { color: var(--accent); }
.logo-sub   { font-size: 9px; font-weight: 600; color: rgba(245, 244, 237, 0.65); letter-spacing:.14em; line-height:1; opacity:.9; }

/* ── Nav ── */
.nav { flex: 1; padding: 10px 0 8px; display: flex; flex-direction: column; overflow-y: auto; scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; }
.nav::-webkit-scrollbar { width: 3px; }
.nav::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

/* ── 单级菜单项 ── */
.nav-item {
  display: flex; align-items: center; gap: 9px;
  margin: 0 8px 2px;
  padding: 10px 12px;
  border-radius: 14px;
  color: var(--text-sidebar, #96a2b9);
  text-decoration: none; font-size: 13px; font-weight: 400;
  transition: background .15s, color .15s, transform .15s, box-shadow .15s;
  cursor: pointer;
}
.nav-item:hover { background: var(--bg-sidebar-hover); color: var(--text-sidebar-strong,#fff); transform: translateX(1px); }
.nav-item.active {
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.22), rgba(var(--accent-rgb), 0.12));
  color: var(--text-sidebar-strong);
  box-shadow: inset 0 0 0 1px rgba(var(--accent-rgb), 0.24);
  font-weight: 500;
}
.nav-icon { display: flex; align-items: center; width: 15px; flex-shrink: 0; opacity: .75; }
.nav-item:hover .nav-icon, .nav-item.active .nav-icon { opacity: 1; }
.nav-badge { margin-left: auto; font-size: 10px; background: var(--accent); color: #fff; padding: 1px 6px; border-radius: 999px; font-weight: 600; }

/* ── 展开分组 ── */
.nav-group {
  margin: 0 8px 4px;
}
.nav-group-toggle {
  display: flex; align-items: center; gap: 9px;
  padding: 10px 12px; width: 100%;
  border-radius: 14px;
  color: var(--text-sidebar,#96a2b9);
  font-size: 13px; font-weight: 400;
  background: transparent; border: none;
  cursor: pointer; text-align: left;
  transition: background .15s, color .15s, transform .15s, box-shadow .15s;
}
.nav-group-toggle:hover { background: var(--bg-sidebar-hover); color: var(--text-sidebar-strong,#fff); transform: translateX(1px); }
.nav-group-toggle .nav-icon { opacity: .75; }
.nav-group-toggle:hover .nav-icon { opacity: 1; }
.nav-group-toggle.active {
  color: var(--text-sidebar-strong);
  background: linear-gradient(135deg, rgba(var(--accent-rgb), 0.18), rgba(var(--accent-rgb), 0.10));
  box-shadow: inset 0 0 0 1px rgba(var(--accent-rgb), 0.18);
}
.nav-group-toggle.active .nav-icon { opacity: 1; }

.toggle-arrow { margin-left: auto; display: flex; align-items: center; transition: transform .2s; opacity: .5; }
.toggle-arrow.rotated { transform: rotate(180deg); }

.nav-sub { display: flex; flex-direction: column; padding: 4px 0 2px; }
.nav-sub-item {
  display: flex; align-items: center; gap: 8px;
  margin: 2px 4px 0 22px;
  padding: 8px 10px 8px 14px;
  border-radius: 12px;
  color: var(--text-sidebar,#96a2b9); font-size: 12.5px;
  text-decoration: none;
  transition: background .15s, color .15s, transform .15s;
}
.nav-sub-item:hover { background: rgba(255,255,255,0.05); color: var(--text-sidebar-strong,#fff); transform: translateX(1px); }
.nav-sub-item.active { color: var(--text-sidebar-strong); background: rgba(var(--accent-rgb), 0.16); font-weight: 500; }
.sub-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; opacity: .4; flex-shrink: 0; }
.nav-sub-item.active .sub-dot { opacity: 1; background: var(--accent); }

/* ── Footer ── */
.sidebar-footer {
  padding: 12px;
  margin: 8px 10px 12px;
  border-top: 1px solid rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 18px;
  background: rgba(255,255,255,0.03);
  backdrop-filter: blur(12px);
  display: flex; flex-direction: column; gap: 6px; flex-shrink: 0;
}
.theme-row { display: flex; gap: 4px; }
.theme-btn { flex: 1; padding: 5px; font-size: 13px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.08); background: transparent; cursor: pointer; transition: all .15s; text-align: center; }
.theme-btn:hover { background: rgba(255,255,255,0.08); }
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
.logout-btn { background: none; border: none; color: rgba(255,255,255,0.32); cursor: pointer; display: flex; align-items: center; padding: 6px; border-radius: 8px; transition: color .15s, background .15s, transform .15s; }
.logout-btn:hover { color: var(--error); background: rgba(248,81,73,0.12); transform: translateY(-1px); }
.admin-links { display: flex; flex-direction: column; gap: 2px; }
.admin-link { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--accent); text-decoration: none; padding: 2px 0; opacity: .8; transition: opacity .12s; }
.admin-link:hover { opacity: 1; }
</style>
