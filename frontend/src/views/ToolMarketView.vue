<template>
  <div class="tool-market">
    <div class="page-header">
      <div class="header-left">
        <h1>工具市场</h1>
        <span class="subtitle">运维工具集合，快速入口</span>
      </div>
    </div>

    <div class="tools-grid">
      <RouterLink v-for="tool in TOOLS" :key="tool.to" :to="tool.to" class="tool-card">
        <div class="tool-icon" :class="tool.color" v-html="tool.icon"></div>
        <div class="tool-body">
          <div class="tool-name">{{ tool.name }}</div>
          <div class="tool-desc">{{ tool.desc }}</div>
        </div>
        <div class="tool-arrow">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>
        </div>
      </RouterLink>
    </div>
  </div>
</template>

<script setup>
import { RouterLink } from 'vue-router'

const TOOLS = [
  {
    name: 'SSH 终端',
    desc: '基于 Web 的 SSH 终端，支持多会话并行操作',
    to: '/tools/ssh',
    color: 'green',
    icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
  },
  {
    name: '慢日志分析',
    desc: 'MySQL 慢查询日志采集与 TOP-N 分析',
    to: '/tools/slowlog',
    color: 'orange',
    icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  },
  {
    name: '指标监控',
    desc: 'Prometheus 自定义指标查询与可视化',
    to: '/tools/metrics',
    color: 'blue',
    icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>`,
  },
  {
    name: '分析报告',
    desc: 'AI 生成运维日报，支持定时推送飞书 / 钉钉',
    to: '/tools/report',
    color: 'purple',
    icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
  },
  {
    name: 'AIOps 助手',
    desc: '基于大模型的智能运维对话，支持根因分析',
    to: '/aiops/assistant',
    color: 'pink',
    icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M9 11V7a3 3 0 016 0v4"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/></svg>`,
  },
  {
    name: 'Grafana 看板',
    desc: '嵌入 Grafana 监控大盘，支持自动发现看板',
    to: '/observability/grafana',
    color: 'yellow',
    icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>`,
  },
]
</script>

<style scoped>
.tool-market { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--bg-main, #0d1117); color: var(--text-primary, #e6edf3); }
.page-header { padding: 16px 20px 12px; border-bottom: 1px solid rgba(255,255,255,0.07); flex-shrink: 0; }
.header-left h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
.subtitle { font-size: 12px; color: var(--text-muted, #6e7681); }

.tools-grid { padding: 20px; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; overflow: auto; }
.tool-card { display: flex; align-items: center; gap: 14px; background: var(--bg-card, #161b22); border: 1px solid rgba(255,255,255,0.07); border-radius: 12px; padding: 18px; text-decoration: none; color: var(--text-primary); transition: border-color .15s, background .15s, transform .15s; }
.tool-card:hover { border-color: rgba(255,255,255,0.18); background: rgba(255,255,255,0.02); transform: translateY(-1px); }

.tool-icon { width: 44px; height: 44px; border-radius: 10px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.tool-icon.green  { background: rgba(63,185,80,0.15);  color: #3fb950; }
.tool-icon.orange { background: rgba(232,108,0,0.15);  color: #e86c00; }
.tool-icon.blue   { background: rgba(56,139,253,0.15); color: #388bfd; }
.tool-icon.purple { background: rgba(115,63,255,0.15); color: #8b5cf6; }
.tool-icon.pink   { background: rgba(236,72,153,0.15); color: #ec4899; }
.tool-icon.yellow { background: rgba(210,153,34,0.15); color: #d29922; }

.tool-body { flex: 1; min-width: 0; }
.tool-name { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.tool-desc { font-size: 11.5px; color: var(--text-muted); line-height: 1.5; }
.tool-arrow { color: var(--text-muted); opacity: 0; transition: opacity .15s; }
.tool-card:hover .tool-arrow { opacity: 1; color: var(--accent); }
</style>
