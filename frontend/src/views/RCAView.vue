<template>
  <div class="page rca-view">
    <div class="page-header">
      <h1>根因分析</h1>
      <span class="subtitle">AI 驱动 · 跨域关联 · 处置建议</span>
    </div>

    <!-- 触发面板 -->
    <div class="card trigger-card">
      <div class="card-header"><h3>发起分析</h3></div>
      <div class="trigger-form">
        <div class="form-row">
          <div class="field">
            <label>目标服务（可选）</label>
            <input v-model="form.service" placeholder="留空表示全局分析" />
          </div>
          <div class="field">
            <label>告警名称（可选）</label>
            <input v-model="form.alert_name" placeholder="如 HighCPU / 订单服务超时" />
          </div>
          <div class="field">
            <label>分析时间窗口</label>
            <select v-model.number="form.hours">
              <option :value="0.5">最近 30 分钟</option>
              <option :value="1">最近 1 小时</option>
              <option :value="3">最近 3 小时</option>
              <option :value="6">最近 6 小时</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label>额外上下文（可选）</label>
          <textarea v-model="form.extra_context" rows="2" placeholder="粘贴相关日志片段或异常描述..."></textarea>
        </div>
        <div class="trigger-actions">
          <button class="btn btn-primary" @click="startStream" :disabled="streaming">
            <span v-if="streaming" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
            {{ streaming ? '分析中...' : '🧠 开始 AI 分析' }}
          </button>
          <span v-if="streaming" class="streaming-hint">AI 正在关联日志 / 指标 / Trace 数据，请稍候...</span>
        </div>
      </div>

      <!-- 流式输出区 -->
      <div v-if="streamOutput || streaming" class="stream-output">
        <div class="stream-label">AI 分析输出</div>
        <div class="stream-content" v-html="renderedOutput"></div>
        <div v-if="streaming" class="stream-cursor">▌</div>
      </div>
    </div>

    <!-- 历史记录 -->
    <div class="card" style="margin-top:16px">
      <div class="card-header">
        <h3>分析历史</h3>
        <button class="btn btn-outline btn-sm" @click="loadHistory">刷新</button>
      </div>

      <div v-if="!history.length" class="empty-state">
        <div class="icon">🔍</div>
        <div>暂无分析记录，点击「开始 AI 分析」触发首次分析</div>
      </div>

      <div v-else class="history-list">
        <div
          v-for="r in history"
          :key="r.id"
          class="history-item"
          :class="{ active: selected?.id === r.id }"
          @click="selected = r"
        >
          <div class="history-head">
            <span class="history-svc">{{ r.service || 'global' }}</span>
            <span v-if="r.alert_name" class="history-alert">{{ r.alert_name }}</span>
            <span class="history-time mono">{{ fmtTime(r.created_at) }}</span>
          </div>
          <div class="history-preview">{{ preview(r.result) }}</div>
        </div>
      </div>
    </div>

    <!-- 详情侧边栏 -->
    <Transition name="slide">
      <div v-if="selected" class="detail-drawer">
        <div class="drawer-header">
          <span class="drawer-title">{{ selected.service }} · {{ fmtTime(selected.created_at) }}</span>
          <button class="drawer-close" @click="selected = null">×</button>
        </div>
        <div class="drawer-body">
          <div class="detail-meta">
            <span>服务：<b>{{ selected.service }}</b></span>
            <span v-if="selected.alert_name">告警：<b>{{ selected.alert_name }}</b></span>
            <span>窗口：{{ selected.context_hours }}h</span>
          </div>
          <div class="result-content" v-html="renderMd(selected.result)"></div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const form = ref({ service: '', alert_name: '', hours: 1, extra_context: '' })
const streaming    = ref(false)
const streamOutput = ref('')
const history      = ref([])
const selected     = ref(null)

const renderedOutput = computed(() => renderMd(streamOutput.value))

function renderMd(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^## (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h5>$1</h5>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
    .replace(/\n/g, '<br>')
}

function preview(text) {
  if (!text) return '（无内容）'
  const plain = text.replace(/#+\s/g, '').replace(/\*\*/g, '')
  return plain.slice(0, 120) + (plain.length > 120 ? '...' : '')
}

function fmtTime(iso) {
  if (!iso) return '—'
  return iso.slice(0, 19).replace('T', ' ')
}

async function startStream() {
  streaming.value = true
  streamOutput.value = ''
  selected.value = null

  const params = new URLSearchParams({
    ...(form.value.service     && { service: form.value.service }),
    ...(form.value.alert_name  && { alert_name: form.value.alert_name }),
    hours: form.value.hours,
    ...(form.value.extra_context && { extra_context: form.value.extra_context }),
  })

  try {
    const resp = await fetch(`/api/rca/analyze/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        service:       form.value.service || null,
        alert_name:    form.value.alert_name,
        hours:         form.value.hours,
        extra_context: form.value.extra_context,
      }),
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      const text = decoder.decode(value)
      for (const line of text.split('\n')) {
        if (line.startsWith('data: ')) {
          const chunk = line.slice(6)
          if (chunk === '[DONE]') break
          streamOutput.value += chunk
        }
      }
    }
  } catch (e) {
    streamOutput.value += `\n\n（请求失败: ${e.message}）`
  } finally {
    streaming.value = false
    await loadHistory()
  }
}

async function loadHistory() {
  try {
    const r = await api.rcaResults(50)
    history.value = r.results || []
  } catch {}
}

onMounted(loadHistory)
</script>

<style scoped>
.trigger-card { margin-bottom: 0; }
.trigger-form { display: flex; flex-direction: column; gap: 12px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 11px; font-weight: 500; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .05em; }
.field input, .field select, .field textarea { width: 100%; }
.field textarea { resize: vertical; }
.trigger-actions { display: flex; align-items: center; gap: 12px; }
.streaming-hint { font-size: 12px; color: var(--text-muted); }

.stream-output {
  margin-top: 14px; padding: 14px 16px;
  background: var(--bg-surface); border: 1px solid var(--border);
  border-radius: var(--radius); position: relative;
}
.stream-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 10px; }
.stream-content { font-size: 13px; line-height: 1.7; color: var(--text-primary); }
.stream-content :deep(h4) { font-size: 13px; font-weight: 700; color: var(--accent); margin: 10px 0 4px; }
.stream-content :deep(h5) { font-size: 12px; font-weight: 600; margin: 8px 0 2px; }
.stream-content :deep(li) { margin-left: 16px; list-style: disc; }
.stream-cursor { display: inline-block; animation: blink .7s step-end infinite; color: var(--accent); font-weight: 700; }
@keyframes blink { 50% { opacity: 0; } }

.history-list { display: flex; flex-direction: column; gap: 6px; }
.history-item {
  padding: 10px 14px; border-radius: var(--radius);
  border: 1px solid var(--border); cursor: pointer; transition: all .12s;
}
.history-item:hover { border-color: var(--border-accent); background: var(--bg-hover); }
.history-item.active { border-color: var(--accent); background: var(--accent-dim); }
.history-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.history-svc { font-weight: 600; font-size: 13px; }
.history-alert { font-size: 11px; background: var(--bg-surface); border: 1px solid var(--border); padding: 1px 6px; border-radius: 3px; color: var(--text-secondary); }
.history-time { font-size: 11px; color: var(--text-muted); margin-left: auto; }
.history-preview { font-size: 12px; color: var(--text-muted); line-height: 1.4; }

/* 详情抽屉 */
.detail-drawer {
  position: fixed; top: 0; right: 0; bottom: 0; width: 480px;
  background: var(--bg-card); border-left: 1px solid var(--border);
  box-shadow: var(--shadow-md); z-index: 200; display: flex; flex-direction: column;
}
.drawer-header {
  display: flex; align-items: center; gap: 10px;
  padding: 16px 20px; border-bottom: 1px solid var(--border-light); flex-shrink: 0;
}
.drawer-title { font-size: 13px; font-weight: 600; flex: 1; color: var(--text-primary); }
.drawer-close { background: none; border: none; font-size: 20px; cursor: pointer; color: var(--text-muted); }
.drawer-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.detail-meta { display: flex; gap: 16px; font-size: 12px; color: var(--text-muted); margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid var(--border-light); }
.result-content { font-size: 13px; line-height: 1.8; color: var(--text-primary); }
.result-content :deep(h4) { font-size: 13px; font-weight: 700; color: var(--accent); margin: 12px 0 4px; }
.result-content :deep(li) { margin-left: 18px; list-style: disc; margin-bottom: 2px; }

.slide-enter-active, .slide-leave-active { transition: transform .2s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }
</style>
