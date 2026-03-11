<template>
  <aside class="sidebar">
    <div class="logo">
      <span class="logo-icon">⬡</span>
      <span class="logo-text">AI <span class="logo-ops">OPS</span></span>
    </div>

    <nav class="nav">
      <RouterLink
        v-for="item in navItems" :key="item.path"
        :to="item.path" class="nav-item"
        :class="{ active: route.path === item.path }"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-label">{{ item.label }}</span>
        <span v-if="route.path === item.path" class="nav-active-bar"></span>
      </RouterLink>
    </nav>

    <!-- Theme switcher -->
    <div class="theme-section">
      <div class="theme-label">主题</div>
      <div class="theme-dots">
        <button
          v-for="t in THEMES" :key="t.id"
          class="theme-dot"
          :class="{ active: currentTheme === t.id }"
          :title="t.label"
          :style="{ '--dot-color': t.color }"
          @click="setTheme(t.id)"
        ></button>
      </div>
    </div>

    <div class="sidebar-footer">
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
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { api } from '../api/index.js'
import { useTheme, THEMES } from '../composables/useTheme.js'

const route = useRoute()
const { currentTheme, setTheme } = useTheme()

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

const navItems = [
  { path: '/',        icon: '◈', label: '仪表盘'   },
  { path: '/logs',    icon: '≡', label: '日志分析'  },
  { path: '/metrics', icon: '△', label: '指标监控'  },
  { path: '/alerts',  icon: '◎', label: '告警历史'  },
  { path: '/report',  icon: '☰', label: '分析报告'  },
  { path: '/hosts',   icon: '⬡', label: 'CMDB 巡检' },
]

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
  background: var(--bg-sidebar);
  border-right: 1px solid var(--glass-border);
  display: flex; flex-direction: column;
  padding: 16px 0;
  position: relative;
  z-index: 10;
}

/* Subtle glow line on right edge */
.sidebar::after {
  content: '';
  position: absolute;
  top: 0; right: -1px; bottom: 0;
  width: 1px;
  background: linear-gradient(to bottom, transparent, var(--accent), transparent);
  opacity: 0.4;
}

.logo {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 20px 20px;
  border-bottom: 1px solid var(--glass-border);
  margin-bottom: 8px;
}
.logo-icon {
  font-size: 22px;
  color: var(--accent);
  text-shadow: var(--accent-glow);
  line-height: 1;
}
.logo-text {
  font-size: 15px; font-weight: 800;
  color: var(--text-primary);
  letter-spacing: 1.5px;
}
.logo-ops {
  color: var(--accent);
  text-shadow: 0 0 8px var(--accent);
}

.nav { flex: 1; padding: 8px 10px; display: flex; flex-direction: column; gap: 2px; }
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border-radius: 6px;
  color: var(--text-secondary); text-decoration: none;
  font-size: 13px; font-weight: 500;
  transition: all .18s;
  position: relative;
  overflow: hidden;
}
.nav-item:hover {
  background: var(--accent-dim);
  color: var(--accent);
}
.nav-item.active {
  background: var(--accent-dim);
  color: var(--accent);
  font-weight: 600;
}
.nav-active-bar {
  position: absolute;
  right: 0; top: 20%; bottom: 20%;
  width: 2px;
  background: var(--accent);
  border-radius: 2px;
  box-shadow: 0 0 6px var(--accent);
}
.nav-icon { font-size: 14px; width: 16px; text-align: center; }

/* Theme switcher */
.theme-section {
  padding: 12px 20px;
  border-top: 1px solid var(--glass-border);
  border-bottom: 1px solid var(--glass-border);
}
.theme-label {
  font-size: 10px; font-weight: 700;
  letter-spacing: .1em;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-bottom: 8px;
}
.theme-dots {
  display: flex; gap: 8px; flex-wrap: wrap;
}
.theme-dot {
  width: 18px; height: 18px;
  border-radius: 50%;
  border: 2px solid transparent;
  background: var(--dot-color);
  cursor: pointer;
  transition: all .2s;
  position: relative;
  box-shadow: 0 0 6px var(--dot-color);
}
.theme-dot:hover {
  transform: scale(1.25);
  box-shadow: 0 0 12px var(--dot-color);
}
.theme-dot.active {
  border-color: #fff;
  transform: scale(1.2);
  box-shadow: 0 0 14px var(--dot-color);
}

/* Footer */
.sidebar-footer {
  padding: 12px 20px 0;
  display: flex; flex-direction: column; gap: 6px;
}
.conn-status { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text-muted); }
.dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.conn-status.ok .dot  { background: var(--success); box-shadow: 0 0 5px var(--success); }
.conn-status.err .dot { background: var(--error);   box-shadow: 0 0 5px var(--error);   }
.ai-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
</style>
