<template>
  <transition name="cp-fade">
    <div v-if="open" class="cp-mask" @click.self="close">
      <div class="cp-box" @keydown.stop>
        <div class="cp-search">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            ref="inputEl"
            v-model="q"
            placeholder="搜索资源 / 跳转页面 / 执行命令"
            spellcheck="false"
            autocapitalize="off"
            @keydown.down.prevent="move(1)"
            @keydown.up.prevent="move(-1)"
            @keydown.enter.prevent="exec(filtered[idx])"
            @keydown.escape="close"
          />
          <span class="cp-kbd">esc</span>
        </div>

        <div class="cp-list" ref="listEl">
          <template v-if="!filtered.length">
            <div class="cp-empty">未找到匹配项 · 试试输入 "pod"、"主机"、"日志"、"kafka"</div>
          </template>
          <template v-else>
            <div
              v-for="(item, i) in filtered"
              :key="item._key"
              class="cp-item"
              :class="{ active: i === idx }"
              @click="exec(item)"
              @mouseenter="idx = i"
            >
              <span class="cp-icon" :class="'cat-' + item.category">{{ item.icon || iconOf(item.category) }}</span>
              <span class="cp-title">{{ item.label }}</span>
              <span v-if="item.sub" class="cp-sub">{{ item.sub }}</span>
              <span class="cp-cat">{{ catLabel(item.category) }}</span>
            </div>
          </template>
        </div>

        <div class="cp-foot">
          <span><kbd>↑↓</kbd> 选择</span>
          <span><kbd>↵</kbd> 执行</span>
          <span><kbd>esc</kbd> 关闭</span>
          <span class="cp-hint">⌘K / Ctrl+K 随时打开</span>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router = useRouter()
const open   = ref(false)
const q      = ref('')
const idx    = ref(0)
const inputEl = ref(null)
const listEl  = ref(null)

// ── 数据源：路由跳转、CMDB 主机、容器 Pod ─────────────────────────────────────
const NAV_ITEMS = [
  { id: 'go-dashboard',   category: 'nav', label: '仪表盘',           sub: '/',          icon: '◐', to: '/' },
  { id: 'go-cmdb',        category: 'nav', label: '主机 CMDB',        sub: '/cmdb',      icon: '🗂', to: '/cmdb' },
  { id: 'go-cmdb-inspect',category: 'nav', label: '主机巡检',         sub: '/cmdb?tab=inspect', icon: '🔍', to: '/cmdb?tab=inspect' },
  { id: 'go-cmdb-groups', category: 'nav', label: '分组管理',         sub: '/cmdb?tab=groups',  icon: '📁', to: '/cmdb?tab=groups' },
  { id: 'go-cmdb-credentials', category: 'nav', label: '凭证管理',    sub: '/cmdb?tab=credentials', icon: '🔑', to: '/cmdb?tab=credentials' },
  { id: 'go-containers',  category: 'nav', label: '容器管理',         sub: '/containers',  icon: '◰', to: '/containers' },
  { id: 'go-k8s-topo',    category: 'nav', label: 'K8s 拓扑',         sub: '/k8s/topology', icon: '🌐', to: '/k8s/topology' },
  { id: 'go-mw',          category: 'nav', label: '中间件概览',        sub: '/middleware', icon: '⚙', to: '/middleware' },
  { id: 'go-redis',       category: 'nav', label: 'Redis Cluster',    sub: '/middleware/redis', icon: '◆', to: '/middleware/redis' },
  { id: 'go-kafka',       category: 'nav', label: 'Kafka',            sub: '/middleware/kafka', icon: '◇', to: '/middleware/kafka' },
  { id: 'go-es',          category: 'nav', label: 'Elasticsearch',    sub: '/middleware/es',    icon: '◉', to: '/middleware/es' },
  { id: 'go-jenkins',     category: 'nav', label: 'Jenkins',          sub: '/cicd/jenkins',     icon: '⚒', to: '/cicd/jenkins' },
  { id: 'go-logs',        category: 'nav', label: '日志分析',         sub: '/observability/logs',     icon: '☰', to: '/observability/logs' },
  { id: 'go-alerts',      category: 'nav', label: '告警历史',         sub: '/observability/alerts',   icon: '!', to: '/observability/alerts' },
  { id: 'go-events',      category: 'nav', label: '事件墙',           sub: '/events',                 icon: '◷', to: '/events' },
  { id: 'go-grafana',     category: 'nav', label: 'Grafana 看板',     sub: '/observability/grafana',  icon: '▦', to: '/observability/grafana' },
  { id: 'go-trace',       category: 'nav', label: 'SkyWalking 链路',  sub: '/observability/trace',    icon: '↬', to: '/observability/trace' },
  { id: 'go-rca',         category: 'nav', label: 'AIOps 根因分析',   sub: '/aiops/rca',     icon: '✦', to: '/aiops/rca' },
  { id: 'go-fault',       category: 'nav', label: '故障态势',         sub: '/aiops/fault',   icon: '⚠', to: '/aiops/fault' },
  { id: 'go-assistant',   category: 'nav', label: 'AIOps 智能助手',   sub: '/aiops/assistant', icon: '✱', to: '/aiops/assistant' },
  { id: 'go-workbench',   category: 'nav', label: 'AI 工作台',        sub: '/aiops/workbench', icon: '✱', to: '/aiops/workbench' },
  { id: 'go-tickets-deploy', category: 'nav', label: '应用发布工单',   sub: '/tickets/deploy', icon: '◰', to: '/tickets/deploy' },
  { id: 'go-tools',       category: 'nav', label: '工具市场',         sub: '/tools',       icon: '⌗', to: '/tools' },
  { id: 'go-ssh-terminal',category: 'nav', label: 'SSH 终端',         sub: '/tools/ssh',   icon: '⌨', to: '/tools/ssh' },
  { id: 'go-settings',    category: 'nav', label: '系统设置',         sub: '/settings',    icon: '⚙', to: '/settings' },
  { id: 'go-profile',     category: 'nav', label: '个人资料',         sub: '/profile',     icon: '◉', to: '/profile' },
]

const ACTION_ITEMS = [
  { id: 'act-import',    category: 'action', label: '导入主机（Excel）', sub: 'CMDB · 一键导入', icon: '⇪', to: '/cmdb?action=import' },
  { id: 'act-add-host',  category: 'action', label: '新建主机',           sub: 'CMDB · +', icon: '⊕', to: '/cmdb?action=add' },
  { id: 'act-add-group', category: 'action', label: '新建分组',           sub: 'CMDB · 分组管理', icon: '⊕', to: '/cmdb?tab=groups&action=add' },
  { id: 'act-template',  category: 'action', label: '下载主机导入模板',    sub: 'CMDB · Excel', icon: '⤓', url: '/api/hosts/template' },
  { id: 'act-export',    category: 'action', label: '导出 CMDB 主机表',    sub: 'CMDB · Excel', icon: '⤓', url: '/api/hosts/export' },
  { id: 'act-redis-add', category: 'action', label: '新建 Redis 连接',    sub: '中间件', icon: '⊕', to: '/middleware/redis?action=add' },
  { id: 'act-kafka-add', category: 'action', label: '新建 Kafka 连接',    sub: '中间件', icon: '⊕', to: '/middleware/kafka?action=add' },
]

const hosts = ref([])
const k8sPods = ref([])

// 远程数据 lazy 加载：成功才标记已加载，失败下次重试
let dataLoaded = false
async function ensureData() {
  if (dataLoaded && hosts.value.length) return
  try {
    const r = await api.getHosts()
    hosts.value = r?.data || []
    dataLoaded = true
  } catch {
    dataLoaded = false   // 允许下次再试（登录后会重新拉）
  }
}

const dynamicItems = computed(() => {
  const items = []
  for (const h of hosts.value) {
    items.push({
      _key: 'host-' + h.id,
      category: 'host',
      label: h.hostname || h.ip,
      sub: `${h.ip}${h.group_name ? ' · ' + h.group_name : ''}`,
      icon: '◉',
      to: `/cmdb?focus=${encodeURIComponent(h.ip)}`,
    })
  }
  return items
})

const allItems = computed(() => {
  const list = [
    ...ACTION_ITEMS.map(x => ({ ...x, _key: x.id })),
    ...NAV_ITEMS.map(x => ({ ...x, _key: x.id })),
    ...dynamicItems.value,
  ]
  return list
})

const filtered = computed(() => {
  const kw = q.value.trim().toLowerCase()
  if (!kw) return allItems.value.slice(0, 30)
  const tokens = kw.split(/\s+/).filter(Boolean)
  const scored = []
  for (const item of allItems.value) {
    const hay = (item.label + ' ' + (item.sub || '')).toLowerCase()
    let ok = true
    for (const t of tokens) { if (!hay.includes(t)) { ok = false; break } }
    if (!ok) continue
    // 简单加权：label 匹配靠前
    const score = (item.label.toLowerCase().includes(kw) ? 100 : 0)
                + (item.category === 'action' ? 30 : item.category === 'nav' ? 20 : 10)
    scored.push({ item, score })
  }
  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, 30).map(s => s.item)
})

// ── 交互 ─────────────────────────────────────────────────────────────────────
function move(delta) {
  if (!filtered.value.length) return
  idx.value = (idx.value + delta + filtered.value.length) % filtered.value.length
  nextTick(() => {
    const el = listEl.value?.querySelectorAll('.cp-item')?.[idx.value]
    el?.scrollIntoView({ block: 'nearest' })
  })
}

function exec(item) {
  if (!item) return
  close()
  if (item.url) {
    window.open(item.url, '_blank')
    return
  }
  if (item.to) {
    // hash 路由模式
    window.location.hash = '#' + item.to
  }
}

function close() {
  open.value = false
}

function toggle() {
  open.value = !open.value
  if (open.value) {
    q.value = ''
    idx.value = 0
    nextTick(() => inputEl.value?.focus())
    ensureData()
  }
}

function onKeydown(e) {
  // ⌘K / Ctrl+K 打开
  if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault()
    toggle()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

// 辅助
function iconOf(cat) { return cat === 'nav' ? '→' : cat === 'action' ? '⚡' : '·' }
function catLabel(cat) { return cat === 'nav' ? '页面' : cat === 'action' ? '动作' : cat === 'host' ? '主机' : cat }
</script>

<style scoped>
.cp-mask {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,.42);
  display: flex; justify-content: center;
  padding-top: 14vh;
}
.cp-box {
  width: min(640px, 92vw);
  height: fit-content; max-height: 60vh;
  background: var(--bg-card); color: var(--text-primary);
  border-radius: 16px;
  border: 1px solid var(--border);
  box-shadow: var(--shadow-md);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.cp-search {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 18px; border-bottom: 1px solid var(--border-light);
}
.cp-search svg { color: var(--text-muted); flex-shrink: 0; }
.cp-search input {
  flex: 1; border: none; background: none; outline: none;
  font-size: 15px; color: inherit; padding: 0; width: 100%;
  border-radius: 0;
}
.cp-search input::placeholder { color: var(--text-muted); }
.cp-kbd { font-size: 10.5px; padding: 2px 7px; border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); }

.cp-list {
  flex: 1; overflow-y: auto; padding: 6px;
  max-height: calc(60vh - 110px);
}
.cp-empty { padding: 30px 16px; text-align: center; color: var(--text-muted); font-size: 13px; }
.cp-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
}
.cp-item.active { background: var(--bg-hover); }
.cp-icon {
  width: 26px; height: 26px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  border-radius: 7px;
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 13px;
}
.cp-icon.cat-nav { background: rgba(99,130,91,.14); color: var(--success); }
.cp-icon.cat-action { background: var(--accent-soft); color: var(--accent); }
.cp-icon.cat-host { background: rgba(96,165,250,.14); color: #60a5fa; }
.cp-title { font-weight: 500; }
.cp-sub { color: var(--text-muted); font-size: 11.5px; margin-left: 4px; }
.cp-cat {
  margin-left: auto; font-size: 10.5px; padding: 1px 8px;
  border-radius: 99px; background: var(--bg-surface); color: var(--text-muted);
}

.cp-foot {
  display: flex; align-items: center; gap: 16px;
  padding: 9px 16px; border-top: 1px solid var(--border-light);
  font-size: 11.5px; color: var(--text-muted);
}
.cp-foot kbd {
  display: inline-block; padding: 1px 6px;
  border: 1px solid var(--border); border-radius: 4px;
  background: var(--bg-surface);
  font-family: var(--font-mono); font-size: 10px;
  margin-right: 4px;
}
.cp-hint { margin-left: auto; opacity: .7; }

/* 过渡 */
.cp-fade-enter-active, .cp-fade-leave-active { transition: opacity 0.18s ease; }
.cp-fade-enter-from, .cp-fade-leave-to { opacity: 0; }
.cp-fade-enter-active .cp-box, .cp-fade-leave-active .cp-box { transition: transform 0.2s ease; }
.cp-fade-enter-from .cp-box, .cp-fade-leave-to .cp-box { transform: translateY(-12px); }
</style>
