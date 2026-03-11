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
      <div class="conn-status" :class="connected ? 'ok' : 'err'">
        <span class="dot"></span>
        <span>{{ connected ? 'Loki 已连接' : 'Loki 未连接' }}</span>
      </div>
      <div class="conn-status" :class="promConnected ? 'ok' : 'err'" style="margin-top:6px">
        <span class="dot"></span>
        <span>{{ promConnected ? 'Prometheus 已连接' : 'Prometheus 未连接' }}</span>
      </div>
      <div class="conn-status" :class="aiReady ? 'ok' : 'err'" style="margin-top:6px" :title="aiProvider">
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

const route = useRoute()
const connected = ref(false)
const promConnected = ref(false)
const aiReady = ref(false)
const aiProvider = ref('')
const aiShortName = computed(() => {
  if (!aiProvider.value) return '未配置'
  // "Anthropic (claude-opus-4-6)" -> "Claude"
  if (aiProvider.value.startsWith('Anthropic')) return 'Claude'
  // "OpenAI-compatible (Qwen3-32B)" -> "Qwen3-32B"
  const m = aiProvider.value.match(/\((.+)\)/)
  return m ? m[1] : aiProvider.value
})

const navItems = [
  { path: '/',        icon: '📊', label: '仪表盘'   },
  { path: '/logs',    icon: '📋', label: '日志分析'  },
  { path: '/metrics', icon: '📈', label: '指标监控'  },
  { path: '/alerts',  icon: '🔔', label: '告警历史'  },
  { path: '/report',  icon: '📝', label: '分析报告'  },
  { path: '/hosts',   icon: '🖥️', label: 'CMDB 巡检' },
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
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column;
  padding: 16px 0;
}
.logo {
  display: flex; align-items: center; gap: 10px;
  padding: 0 20px 20px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}
.logo-icon { font-size: 22px; }
.logo-text { font-size: 16px; font-weight: 700; color: var(--text-primary); letter-spacing: .5px; }

.nav { flex: 1; padding: 8px 10px; display: flex; flex-direction: column; gap: 2px; }
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border-radius: 6px;
  color: var(--text-secondary); text-decoration: none;
  font-size: 13px; transition: all .15s;
}
.nav-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.nav-item.active { background: var(--bg-active); color: var(--accent-hover); }
.nav-icon { font-size: 15px; }

.sidebar-footer { padding: 16px 20px 0; border-top: 1px solid var(--border); }
.conn-status { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-muted); }
.dot { width: 7px; height: 7px; border-radius: 50%; }
.conn-status.ok .dot  { background: var(--success); box-shadow: 0 0 6px var(--success); }
.conn-status.err .dot { background: var(--error);   box-shadow: 0 0 6px var(--error);   }
.ai-label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
</style>
