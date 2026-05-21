<template>
  <div class="page rca-page">
    <div class="page-header rca-header">
      <div>
        <h1>根因分析</h1>
        <span class="subtitle">告警 / 巡检 / 异常检测统一进入结构化 RCA 闭环</span>
      </div>
      <div class="header-stats">
        <div class="header-chip">
          <span class="chip-label">专家案例</span>
          <b>{{ expertCases.length }}</b>
        </div>
        <div class="header-chip">
          <span class="chip-label">反馈模型</span>
          <b>{{ feedback.categories?.length || 0 }}</b>
        </div>
        <button class="btn btn-outline btn-sm" @click="refreshAll" :disabled="loadingHistory">
          {{ loadingHistory ? '刷新中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div class="rca-layout">
      <div class="rca-main">
        <section class="rca-panel trigger-panel">
          <div class="panel-head">
            <div>
              <div class="eyebrow">Manual Trigger</div>
              <h3>发起分析</h3>
            </div>
            <span class="panel-hint">当前页面也会接收告警中心、巡检页和异常检测页跳转过来的 RCA run</span>
          </div>

          <div class="trigger-grid">
            <label class="field">
              <span>目标服务</span>
              <input v-model="form.service" placeholder="为空表示全局分析" />
            </label>
            <label class="field">
              <span>告警/事件名</span>
              <input v-model="form.alert_name" placeholder="如 payment 5xx / 主机巡检异常" />
            </label>
            <label class="field">
              <span>时间窗口</span>
              <select v-model.number="form.hours">
                <option :value="0.5">最近 30 分钟</option>
                <option :value="1">最近 1 小时</option>
                <option :value="3">最近 3 小时</option>
                <option :value="6">最近 6 小时</option>
              </select>
            </label>
          </div>

          <label class="field field-full">
            <span>额外上下文</span>
            <textarea
              v-model="form.extra_context"
              rows="3"
              placeholder="补充日志片段、变更说明、业务现象、影响范围..."
            ></textarea>
          </label>

          <div class="trigger-actions">
            <button class="btn btn-primary" @click="startRun" :disabled="launching">
              <span v-if="launching" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
              {{ launching ? '启动中...' : '开始 RCA' }}
            </button>
            <span class="trigger-tip">流程会自动采集 logs / metrics / trace / CMDB / 代码变更，再并行验证 3 个假设。</span>
          </div>
        </section>

        <template v-if="selected">
          <section class="rca-panel hero-panel">
            <div class="hero-head">
              <div>
                <div class="hero-title">{{ selected.alert_name || selected.service }}</div>
                <div class="hero-meta">
                  <span class="source-pill">{{ sourceLabel(selected.source_type) }}</span>
                  <span class="status-pill" :class="selected.status">{{ statusLabel(selected.status) }}</span>
                  <span class="mono">{{ fmtTime(selected.created_at) }}</span>
                  <span class="mono">ID {{ selected.id }}</span>
                </div>
              </div>
              <div class="hero-score" :class="scoreClass(topHypothesis?.score || 0)">
                <div class="hero-score-label">Top Score</div>
                <div class="hero-score-val">{{ topHypothesis?.score || '--' }}</div>
              </div>
            </div>

            <div class="hero-summary">{{ selected.final_summary || '正在生成 RCA 结论...' }}</div>

            <div class="hero-metrics">
              <div class="mini-stat">
                <span>来源对象</span>
                <b>{{ selected.source_name || selected.service }}</b>
              </div>
              <div class="mini-stat">
                <span>分析窗口</span>
                <b>{{ selected.context_hours }}h</b>
              </div>
              <div class="mini-stat">
                <span>假设数</span>
                <b>{{ selected.hypotheses?.length || 0 }}</b>
              </div>
              <div class="mini-stat">
                <span>人工确认</span>
                <b>{{ confirmationLabel(selected.human_confirmation?.status) }}</b>
              </div>
            </div>

            <div class="timeline">
              <div v-for="item in selected.timeline || []" :key="`${item.stage}-${item.at}`" class="timeline-item">
                <div class="timeline-dot" :class="item.status || 'done'"></div>
                <div class="timeline-content">
                  <div class="timeline-title">{{ item.title }}</div>
                  <div class="timeline-detail">{{ item.detail }}</div>
                </div>
                <div class="timeline-time mono">{{ fmtTime(item.at) }}</div>
              </div>
            </div>
          </section>

          <section class="rca-panel">
            <div class="panel-head">
              <div>
                <div class="eyebrow">Parallel Validators</div>
                <h3>三假设并行验证</h3>
              </div>
              <span class="panel-hint">每个假设都带证据、评分和推荐排障命令</span>
            </div>

            <div v-if="isRunning(selected.status)" class="pending-banner">
              正在采集上下文并运行验证 Agent，请等待当前 run 完成。
            </div>

            <div v-else-if="!selected.hypotheses?.length" class="empty-inline">当前 run 还没有产出假设。</div>

            <div v-else class="hypothesis-grid">
              <article
                v-for="hypothesis in selected.hypotheses"
                :key="hypothesis.id"
                class="hypothesis-card"
                :class="[hypothesis.validation_status, { chosen: selected.human_confirmation?.chosen_hypothesis_id === hypothesis.id }]"
              >
                <div class="hypothesis-top">
                  <span class="validator-chip">{{ hypothesis.agent_name }}</span>
                  <span class="score-chip" :class="scoreClass(hypothesis.score)">{{ hypothesis.score }} 分</span>
                </div>

                <div class="hypothesis-title">{{ hypothesis.title }}</div>
                <div class="hypothesis-desc">{{ hypothesis.validation_summary || hypothesis.description }}</div>

                <div class="hypothesis-block">
                  <div class="block-title">证据</div>
                  <div v-for="(evidence, idx) in hypothesis.evidence || []" :key="idx" class="bullet-line">{{ evidence }}</div>
                </div>

                <div class="hypothesis-block">
                  <div class="block-title">建议命令</div>
                  <code v-for="(command, idx) in hypothesis.commands || []" :key="idx" class="command-chip">{{ command }}</code>
                </div>

                <div class="hypothesis-actions">
                  <button
                    class="btn btn-sm btn-primary"
                    :disabled="confirming || !canConfirm(selected)"
                    @click="confirmHypothesis(hypothesis)"
                  >
                    {{ selected.human_confirmation?.chosen_hypothesis_id === hypothesis.id ? '已确认' : '确认为根因' }}
                  </button>
                </div>
              </article>
            </div>

            <div v-if="canConfirm(selected)" class="confirm-box">
              <label class="field field-full">
                <span>人工确认备注</span>
                <textarea v-model="confirmNote" rows="2" placeholder="记录影响范围、确认依据、处置结论..." />
              </label>
              <button class="btn btn-outline btn-sm" :disabled="confirming" @click="markNeedsReview">
                标记为待复核
              </button>
            </div>
          </section>

          <section class="rca-panel">
            <div class="panel-head">
              <div>
                <div class="eyebrow">Collected Context</div>
                <h3>上下文采集</h3>
              </div>
              <span class="panel-hint">包含日志、指标、Trace、CMDB、代码库、变更和历史专家案例</span>
            </div>

            <div v-if="!contextSections.length" class="empty-inline">暂无上下文。</div>
            <div v-else class="context-grid">
              <article v-for="section in contextSections" :key="section.key" class="context-card">
                <div class="context-title">{{ section.title || section.key }}</div>
                <div class="context-summary">{{ section.summary || '无摘要' }}</div>

                <div v-if="section.key === 'similar_cases'" class="case-hit-list">
                  <div v-for="caseItem in section.items || []" :key="caseItem.id" class="case-hit">
                    <div class="case-hit-head">
                      <strong>{{ caseItem.title }}</strong>
                      <span class="mini-badge">{{ caseItem.score }}</span>
                    </div>
                    <div class="case-hit-sub">{{ caseItem.category }} · {{ caseItem.service || 'global' }}</div>
                    <div class="case-hit-desc">{{ caseItem.resolution || caseItem.root_cause }}</div>
                  </div>
                </div>

                <div v-else class="context-lines">
                  <div
                    v-for="(item, idx) in normalizeSectionItems(section.items)"
                    :key="idx"
                    class="context-line"
                  >
                    {{ formatSectionItem(item) }}
                  </div>
                </div>
              </article>
            </div>
          </section>
        </template>

        <section v-else class="rca-panel empty-panel">
          <div class="empty-state">
            <div class="icon">🧠</div>
            <div>选择一个 RCA run，或者手动发起新的根因分析。</div>
          </div>
        </section>
      </div>

      <aside class="rca-side">
        <section class="rca-panel side-panel">
          <div class="panel-head">
            <div>
              <div class="eyebrow">Run History</div>
              <h3>分析历史</h3>
            </div>
          </div>

          <div v-if="!history.length" class="empty-inline">暂无历史记录。</div>
          <div v-else class="history-list">
            <button
              v-for="item in history"
              :key="item.id"
              class="history-item"
              :class="{ active: selected?.id === item.id }"
              @click="openRecord(item.id)"
            >
              <div class="history-row">
                <span class="history-source">{{ sourceLabel(item.source_type) }}</span>
                <span class="history-status" :class="item.status">{{ statusLabel(item.status) }}</span>
              </div>
              <div class="history-title">{{ item.alert_name || item.service }}</div>
              <div class="history-summary">{{ item.final_summary || preview(item.result) }}</div>
              <div class="history-time mono">{{ fmtTime(item.created_at) }}</div>
            </button>
          </div>
        </section>

        <section class="rca-panel side-panel">
          <div class="panel-head">
            <div>
              <div class="eyebrow">Expert Library</div>
              <h3>专家案例</h3>
            </div>
          </div>

          <div v-if="!expertCases.length" class="empty-inline">还没有人工确认沉淀的案例。</div>
          <div v-else class="expert-list">
            <article v-for="item in expertCases.slice(0, 8)" :key="item.id" class="expert-item">
              <div class="expert-head">
                <strong>{{ item.title }}</strong>
                <span class="mini-badge">{{ item.category }}</span>
              </div>
              <div class="expert-meta">{{ item.service || 'global' }} · {{ fmtTime(item.created_at) }}</div>
              <div class="expert-desc">{{ item.summary || item.root_cause }}</div>
            </article>
          </div>
        </section>

        <section class="rca-panel side-panel">
          <div class="panel-head">
            <div>
              <div class="eyebrow">Adaptive Feedback</div>
              <h3>反馈权重</h3>
            </div>
          </div>

          <div v-if="!feedback.categories?.length" class="empty-inline">暂无反馈权重数据。</div>
          <div v-else class="feedback-list">
            <div v-for="item in feedback.categories" :key="item.key" class="feedback-item">
              <div class="feedback-head">
                <strong>{{ item.title }}</strong>
                <span class="mini-badge">{{ item.weight }}</span>
              </div>
              <div class="feedback-meta">
                confirmed {{ item.confirmed }} · rejected {{ item.rejected }}
                <span v-if="item.accuracy !== null">· accuracy {{ item.accuracy }}%</span>
              </div>
            </div>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/index.js'

const route = useRoute()
const router = useRouter()

const form = ref({ service: '', alert_name: '', hours: 1, extra_context: '' })
const history = ref([])
const selected = ref(null)
const expertCases = ref([])
const feedback = ref({ categories: [] })
const loadingHistory = ref(false)
const launching = ref(false)
const confirming = ref(false)
const confirmNote = ref('')

let pollTimer = null

const topHypothesis = computed(() => selected.value?.hypotheses?.[0] || null)

const contextSections = computed(() => {
  const context = selected.value?.context || {}
  return Object.entries(context)
    .filter(([, value]) => value && (value.summary || (Array.isArray(value.items) && value.items.length)))
    .map(([key, value]) => ({ key, ...value }))
})

function isRunning(status) {
  return ['pending', 'running'].includes(status)
}

function statusLabel(status) {
  return {
    pending: '等待中',
    running: '分析中',
    awaiting_confirmation: '待确认',
    confirmed: '已确认',
    needs_review: '待复核',
    error: '失败',
  }[status] || status || '--'
}

function confirmationLabel(status) {
  return {
    pending: '待确认',
    confirmed: '已确认',
    needs_review: '待复核',
  }[status] || '--'
}

function sourceLabel(sourceType) {
  return {
    manual: '手动',
    alert: '告警',
    inspection: '巡检',
    anomaly: '异常检测',
  }[sourceType] || sourceType || 'manual'
}

function scoreClass(score) {
  if (score >= 75) return 'high'
  if (score >= 50) return 'mid'
  return 'low'
}

function fmtTime(iso) {
  if (!iso) return '--'
  return iso.slice(0, 19).replace('T', ' ')
}

function preview(text) {
  if (!text) return '暂无摘要'
  const plain = text.replace(/#+\s/g, '').replace(/\*\*/g, '').replace(/\s+/g, ' ').trim()
  return plain.slice(0, 90) + (plain.length > 90 ? '...' : '')
}

function normalizeSectionItems(items) {
  if (!Array.isArray(items)) return []
  return items
}

function formatSectionItem(item) {
  if (item == null) return '--'
  if (typeof item === 'string') return item
  if (typeof item === 'object') return Object.values(item).join(' · ')
  return String(item)
}

function canConfirm(record) {
  if (!record || isRunning(record.status)) return false
  return !['confirmed', 'needs_review'].includes(record.human_confirmation?.status)
}

function upsertHistory(record) {
  if (!record?.id) return
  const idx = history.value.findIndex(item => item.id === record.id)
  if (idx === -1) history.value = [record, ...history.value]
  else history.value.splice(idx, 1, record)
}

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer)
    pollTimer = null
  }
}

async function pollRecord(id) {
  stopPolling()

  const tick = async () => {
    try {
      const record = await api.rcaResult(id)
      upsertHistory(record)
      if (selected.value?.id === id) selected.value = record

      if (isRunning(record.status)) {
        pollTimer = setTimeout(tick, 1500)
        return
      }

      await Promise.all([loadExpertCases(), loadFeedback(), loadHistory(false)])
    } catch {
      pollTimer = setTimeout(tick, 2000)
    }
  }

  await tick()
}

async function loadHistory(syncRoute = true) {
  loadingHistory.value = true
  try {
    const result = await api.rcaResults(80)
    history.value = result.results || []
    if (!selected.value && history.value.length) selected.value = history.value[0]
    if (syncRoute) await openFromRoute()
  } finally {
    loadingHistory.value = false
  }
}

async function loadExpertCases() {
  const result = await api.rcaExpertCases(30)
  expertCases.value = result.cases || []
}

async function loadFeedback() {
  feedback.value = await api.rcaFeedback()
}

async function refreshAll() {
  await Promise.all([loadHistory(true), loadExpertCases(), loadFeedback()])
}

async function openRecord(id) {
  const record = await api.rcaResult(id)
  selected.value = record
  upsertHistory(record)
  if (route.query.rca_id !== id) {
    router.replace({ path: '/aiops/rca', query: { ...route.query, rca_id: id } })
  }
  if (isRunning(record.status)) {
    await pollRecord(id)
  }
}

async function openFromRoute() {
  const rcaId = String(route.query.rca_id || '').trim()
  if (!rcaId) return
  if (selected.value?.id === rcaId) return
  try {
    await openRecord(rcaId)
  } catch {
    // ignore invalid query id
  }
}

async function startRun() {
  launching.value = true
  try {
    const result = await api.rcaTrigger({
      service: form.value.service || null,
      alert_name: form.value.alert_name,
      hours: form.value.hours,
      extra_context: form.value.extra_context,
      source_type: 'manual',
    })
    if (result?.record) {
      selected.value = result.record
      upsertHistory(result.record)
    }
    if (result?.rca_id) {
      router.replace({ path: '/aiops/rca', query: { ...route.query, rca_id: result.rca_id } })
      await pollRecord(result.rca_id)
    }
  } finally {
    launching.value = false
  }
}

async function confirmHypothesis(hypothesis) {
  if (!selected.value) return
  confirming.value = true
  try {
    const record = await api.rcaConfirm(selected.value.id, {
      hypothesis_id: hypothesis.id,
      note: confirmNote.value,
      confirmed_by: 'manual',
      decision: 'confirmed',
      resolve_alert: false,
    })
    selected.value = record
    upsertHistory(record)
    confirmNote.value = ''
    await Promise.all([loadExpertCases(), loadFeedback(), loadHistory(false)])
  } finally {
    confirming.value = false
  }
}

async function markNeedsReview() {
  if (!selected.value || !selected.value.hypotheses?.length) return
  confirming.value = true
  try {
    const record = await api.rcaConfirm(selected.value.id, {
      hypothesis_id: selected.value.hypotheses[0].id,
      note: confirmNote.value || '人工标记为待复核',
      confirmed_by: 'manual',
      decision: 'needs_review',
      resolve_alert: false,
    })
    selected.value = record
    upsertHistory(record)
  } finally {
    confirming.value = false
  }
}

watch(() => route.query.rca_id, () => {
  openFromRoute()
})

onMounted(async () => {
  await refreshAll()
  await openFromRoute()
  if (selected.value && isRunning(selected.value.status)) {
    await pollRecord(selected.value.id)
  }
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.rca-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.rca-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.header-stats {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.header-chip {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background:
    linear-gradient(135deg, rgba(56,139,253,.12), rgba(24,31,42,.02)),
    var(--bg-card);
  min-width: 110px;
}

.chip-label {
  display: block;
  font-size: 10px;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.rca-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 330px;
  gap: 16px;
  min-height: 0;
}

.rca-main,
.rca-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
}

.rca-panel {
  background:
    radial-gradient(circle at top right, rgba(56,139,253,.09), transparent 38%),
    linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,0)),
    var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 18px;
  box-shadow: var(--shadow-sm);
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.panel-head h3 {
  margin: 4px 0 0;
  font-size: 15px;
}

.eyebrow {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .12em;
  color: var(--text-muted);
}

.panel-hint {
  font-size: 12px;
  color: var(--text-muted);
}

.trigger-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field span {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: .06em;
}

.field-full {
  margin-top: 12px;
}

.field input,
.field select,
.field textarea {
  width: 100%;
}

.trigger-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 14px;
}

.trigger-tip {
  font-size: 12px;
  color: var(--text-muted);
}

.hero-panel {
  border-color: rgba(56,139,253,.22);
}

.hero-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.hero-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.hero-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.source-pill,
.status-pill,
.mini-badge,
.validator-chip,
.score-chip {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}

.source-pill {
  background: rgba(56,139,253,.12);
  color: var(--accent);
}

.status-pill.pending,
.history-status.pending {
  background: rgba(210,153,34,.12);
  color: var(--warning);
}

.status-pill.running,
.history-status.running {
  background: rgba(56,139,253,.12);
  color: var(--accent);
}

.status-pill.awaiting_confirmation,
.history-status.awaiting_confirmation {
  background: rgba(14,165,233,.12);
  color: #0ea5e9;
}

.status-pill.confirmed,
.history-status.confirmed {
  background: rgba(26,127,55,.12);
  color: var(--success);
}

.status-pill.needs_review,
.history-status.needs_review,
.timeline-dot.error {
  background: rgba(248,81,73,.12);
  color: var(--error);
}

.hero-score {
  min-width: 110px;
  border-radius: 16px;
  padding: 12px;
  text-align: right;
  border: 1px solid var(--border);
  background: var(--bg-surface);
}

.hero-score.high { border-color: rgba(26,127,55,.28); }
.hero-score.mid { border-color: rgba(210,153,34,.28); }
.hero-score.low { border-color: rgba(248,81,73,.22); }

.hero-score-label {
  font-size: 10px;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--text-muted);
}

.hero-score-val {
  font-size: 26px;
  font-weight: 800;
  margin-top: 4px;
}

.hero-summary {
  margin-top: 14px;
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.mini-stat {
  padding: 12px;
  border-radius: 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
}

.mini-stat span {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.mini-stat b {
  font-size: 13px;
  color: var(--text-primary);
}

.timeline {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
}

.timeline-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: 6px;
  background: var(--accent);
}

.timeline-content {
  min-width: 0;
}

.timeline-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.timeline-detail {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.timeline-time {
  font-size: 11px;
  color: var(--text-muted);
}

.pending-banner,
.empty-inline {
  padding: 12px;
  border-radius: 12px;
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 13px;
}

.hypothesis-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.hypothesis-card {
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 16px;
  background:
    linear-gradient(180deg, rgba(255,255,255,.02), rgba(255,255,255,0)),
    var(--bg-card);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.hypothesis-card.supported { border-color: rgba(26,127,55,.28); }
.hypothesis-card.possible { border-color: rgba(210,153,34,.28); }
.hypothesis-card.weak { border-color: rgba(248,81,73,.18); }
.hypothesis-card.chosen { box-shadow: 0 0 0 1px rgba(56,139,253,.35) inset; }

.hypothesis-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.validator-chip {
  background: rgba(56,139,253,.12);
  color: var(--accent);
}

.score-chip.high { background: rgba(26,127,55,.12); color: var(--success); }
.score-chip.mid { background: rgba(210,153,34,.12); color: var(--warning); }
.score-chip.low { background: rgba(248,81,73,.12); color: var(--error); }

.hypothesis-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.hypothesis-desc {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.hypothesis-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.block-title {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .1em;
  color: var(--text-muted);
}

.bullet-line {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.command-chip {
  display: block;
  white-space: normal;
  font-size: 11px;
  line-height: 1.5;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
}

.hypothesis-actions {
  margin-top: auto;
}

.confirm-box {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.context-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.context-card {
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 14px;
  background: var(--bg-surface);
}

.context-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.context-summary {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-top: 6px;
}

.context-lines,
.case-hit-list {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.context-line {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.55;
}

.case-hit {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: rgba(56,139,253,.05);
}

.case-hit-head,
.feedback-head,
.expert-head,
.history-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.case-hit-sub,
.case-hit-desc,
.feedback-meta,
.expert-meta,
.expert-desc,
.history-summary,
.history-time {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}

.side-panel {
  padding: 16px;
}

.history-list,
.expert-list,
.feedback-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.history-item {
  text-align: left;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 12px;
  background: var(--bg-surface);
  cursor: pointer;
  transition: all .14s;
}

.history-item:hover,
.history-item.active {
  border-color: rgba(56,139,253,.32);
  background: rgba(56,139,253,.08);
}

.history-source {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--text-muted);
}

.history-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  margin-top: 6px;
}

.expert-item,
.feedback-item {
  padding: 12px;
  border-radius: 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border-light);
}

.empty-panel {
  min-height: 240px;
}

@media (max-width: 1280px) {
  .rca-layout {
    grid-template-columns: 1fr;
  }

  .rca-side {
    order: -1;
  }

  .hero-metrics,
  .hypothesis-grid,
  .context-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .rca-header,
  .panel-head,
  .hero-head,
  .trigger-actions {
    flex-direction: column;
    align-items: stretch;
  }

  .trigger-grid,
  .hero-metrics,
  .hypothesis-grid,
  .context-grid {
    grid-template-columns: 1fr;
  }

  .timeline-item {
    grid-template-columns: 10px minmax(0, 1fr);
  }

  .timeline-time {
    display: none;
  }
}
</style>
