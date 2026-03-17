<template>
  <div class="page">

    <!-- ── 页头 ─────────────────────────────────────────────────────── -->
    <div class="page-header">
      <h1>MySQL 慢日志分析</h1>
      <span class="subtitle">多主机 · 时间段 · AI 分析 · drain3 聚合</span>
    </div>

    <!-- ── 凭证区 ─────────────────────────────────────────────────── -->
    <div class="card cred-card">
      <div class="cred-header" @click="credOpen = !credOpen">
        <span class="cred-title">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
          SSH 凭证（所有主机共用）
        </span>
        <span class="cred-status">
          <span v-if="credMode==='auto'"   class="cred-set">CMDB 自动</span>
          <span v-else-if="credMode==='lib' && cred.credential_id" class="cred-set">凭证库 · {{ selectedCredName }}</span>
          <span v-else-if="credMode==='manual' && cred.ssh_user"   class="cred-set">手动 · {{ cred.ssh_user }}</span>
          <span v-else class="cred-unset">未配置</span>
        </span>
        <svg class="chevron" :class="{ open: credOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
      </div>

      <div v-if="credOpen" class="cred-body">
        <!-- 模式切换 -->
        <div class="mode-tabs">
          <button class="mode-tab" :class="{ active: credMode==='auto' }"   @click="credMode='auto'">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 12h4l2-4"/></svg>
            CMDB 自动
          </button>
          <button class="mode-tab" :class="{ active: credMode==='lib' }"    @click="credMode='lib'">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2H3v16h5l4 4 4-4h5V2z"/><line x1="9" y1="9" x2="15" y2="9"/><line x1="9" y1="13" x2="13" y2="13"/></svg>
            凭证库
          </button>
          <button class="mode-tab" :class="{ active: credMode==='manual' }" @click="credMode='manual'">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
            手动输入
          </button>
        </div>

        <!-- CMDB 自动：不需要额外配置 -->
        <div v-if="credMode==='auto'" class="mode-hint">
          每台主机将自动从 CMDB 凭证绑定中查找 SSH 认证信息。
        </div>

        <!-- 凭证库 -->
        <div v-if="credMode==='lib'" class="cred-grid">
          <div class="field field-wide">
            <label>选择凭证</label>
            <select v-model="cred.credential_id" class="sel-full">
              <option value="">-- 请选择凭证 --</option>
              <option v-for="c in credList" :key="c.id" :value="c.id">
                {{ c.name }} ({{ c.username }}{{ c.host ? ' · ' + c.host : '' }})
              </option>
            </select>
          </div>
          <div v-if="!credList.length" class="field-hint">
            凭证库为空，请先在 <router-link to="/hosts" class="link">CMDB 巡检</router-link> 中添加凭证。
          </div>
        </div>

        <!-- 手动输入 -->
        <div v-if="credMode==='manual'" class="cred-grid">
          <div class="field">
            <label>SSH 用户名</label>
            <input v-model="cred.ssh_user" placeholder="root" />
          </div>
          <div class="field">
            <label>SSH 密码</label>
            <input v-model="cred.ssh_password" type="password" placeholder="密码" />
          </div>
          <div class="field field-narrow">
            <label>SSH 端口</label>
            <input v-model.number="cred.ssh_port" type="number" min="1" max="65535" />
          </div>
        </div>

        <!-- 时间段 + 阈值（始终显示） -->
        <div class="cred-grid" style="margin-top: 12px;">
          <div class="field">
            <label>起始日期</label>
            <input v-model="cred.date_from" type="date" />
          </div>
          <div class="field">
            <label>结束日期</label>
            <input v-model="cred.date_to" type="date" />
          </div>
          <div class="field" style="justify-content: flex-end; padding-top: 18px;">
            <div class="quick-dates">
              <button class="btn-ghost" @click="setRange(0)">今天</button>
              <button class="btn-ghost" @click="setRange(1)">昨天</button>
              <button class="btn-ghost" @click="setRange(7)">近7天</button>
              <button class="btn-ghost" @click="setRange(30)">近30天</button>
              <button class="btn-ghost" @click="cred.date_from=''; cred.date_to=''">不限</button>
            </div>
          </div>
          <div class="field field-narrow">
            <label>最小耗时(s)</label>
            <input v-model.number="cred.threshold_sec" type="number" min="0.1" step="0.5" />
          </div>
          <div class="field field-narrow">
            <label>告警阈值(s)</label>
            <input v-model.number="cred.alert_sec" type="number" min="1" step="1" />
          </div>
        </div>
      </div>
    </div>

    <!-- ── 分析目标 ────────────────────────────────────────────────── -->
    <div class="card targets-card">
      <div class="targets-header">
        <h3>分析目标</h3>
        <div class="targets-actions">
          <!-- 批量从 CMDB 添加 -->
          <div class="batch-wrap" v-if="cmdbHosts.length">
            <button class="btn-ghost" @click="batchOpen = !batchOpen">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
              从主机库添加
              <span v-if="batchSelected.size" class="badge">{{ batchSelected.size }}</span>
            </button>
            <!-- 批量选择面板 -->
            <div v-if="batchOpen" class="batch-panel">
              <div class="batch-search">
                <input v-model="batchQ" placeholder="搜索主机..." class="batch-inp" autofocus />
                <button class="btn-link" @click="batchSelectAll">全选</button>
                <button class="btn-link" @click="batchSelected.clear()">清空</button>
              </div>
              <div class="batch-list">
                <label v-for="h in filteredCmdb" :key="h.instance" class="batch-row"
                  :class="{ 'has-cred': h.has_credential }">
                  <input type="checkbox" :value="h.instance"
                    :checked="batchSelected.has(h.instance)"
                    @change="toggleBatch(h.instance)" />
                  <span class="batch-ip mono">{{ h.ip || '—' }}</span>
                  <span class="batch-name">{{ h.hostname || h.instance }}</span>
                  <span v-if="h.has_credential" class="batch-cred-tag">
                    {{ h.credential_name || '已绑定' }}
                  </span>
                  <span v-else class="batch-nocred">无凭证</span>
                </label>
              </div>
              <div class="batch-footer">
                <button class="btn-primary btn-sm" @click="applyBatch" :disabled="!batchSelected.size">
                  添加 {{ batchSelected.size }} 台
                </button>
                <button class="btn-ghost btn-sm" @click="batchOpen = false">取消</button>
              </div>
            </div>
          </div>
          <button class="btn-ghost" @click="addTarget">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            手动添加
          </button>
          <button class="btn-primary" :disabled="fetching || !validTargets.length" @click="fetchAll">
            <span v-if="fetching" class="spinner-xs"></span>
            <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            {{ fetching ? '读取中...' : '获取并解析' }}
          </button>
          <button class="btn-secondary" :disabled="!hasEntries || analyzing" @click="startAnalysis">
            <span v-if="analyzing" class="spinner-xs"></span>
            <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
            {{ analyzing ? 'AI 分析中...' : 'AI 分析建议' }}
          </button>
        </div>
      </div>

      <!-- 目标行 -->
      <div class="target-row" v-for="(t, i) in targets" :key="t.id">
        <div class="target-index">{{ i + 1 }}</div>
        <div class="target-fields">
          <!-- IP 选择：CMDB 下拉 + 手动输入 -->
          <div class="ip-wrap">
            <input v-model="t.host_ip" placeholder="IP 或从主机库选择" class="inp-ip"
              @focus="t._suggest = true" @blur="hideSuggest(t)"
              @input="t._suggest = true" @keyup.enter="fetchAll" />
            <div v-if="t._suggest && suggestHosts(t).length" class="suggest-list">
              <div v-for="h in suggestHosts(t)" :key="h.instance"
                class="suggest-item" @mousedown.prevent="pickHost(t, h)">
                <span class="mono suggest-ip">{{ h.ip }}</span>
                <span class="suggest-name">{{ h.hostname || h.instance }}</span>
                <span v-if="h.has_credential" class="suggest-cred">{{ h.credential_name || '已绑定' }}</span>
              </div>
            </div>
          </div>
          <!-- 显示绑定的主机名 -->
          <span v-if="t._hostname" class="target-hostname">{{ t._hostname }}</span>
          <input v-model="t.log_path" placeholder="/mysqldata/mysql/data/3306/mysql-slow.log" class="inp-path" />
          <span class="target-status" :class="statusClass(t)">
            <span v-if="t.loading" class="spinner-xs2"></span>
            <template v-else>{{ statusLabel(t) }}</template>
          </span>
          <span v-if="t.error" class="target-error" :title="t.error">{{ t.error.slice(0, 60) }}</span>
        </div>
        <button class="btn-remove" :disabled="targets.length <= 1" @click="removeTarget(i)" title="删除">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <!-- 无 CMDB 主机提示 -->
      <div v-if="!cmdbHostsLoading && !cmdbHosts.length" class="no-cmdb-hint">
        CMDB 中暂无主机，请先在
        <router-link to="/hosts" class="link">CMDB 巡检</router-link>
        中录入主机和 SSH 凭证。
      </div>
    </div>

    <!-- ── AI 分析 ────────────────────────────────────────────────── -->
    <div v-if="aiText || analyzing" class="card ai-card">
      <div class="ai-header">
        <span class="ai-badge">AI</span>
        <span>分析建议</span>
        <button v-if="!analyzing" class="btn-icon" @click="aiText = ''" title="关闭">✕</button>
      </div>
      <div class="ai-body" v-html="renderedAi"></div>
      <div v-if="analyzing" class="ai-typing">
        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
      </div>
    </div>

    <!-- ── 结果区 ─────────────────────────────────────────────────── -->
    <div v-if="hasEntries" class="results-section">
      <div v-if="resultTabs.length > 1" class="tab-bar">
        <button v-for="tab in resultTabs" :key="tab.key"
          class="tab-btn" :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key">
          <span class="tab-dot" :class="tab.worstSeverity"></span>
          {{ tab.label }}
          <span class="tab-count">{{ tab.total }}</span>
        </button>
      </div>

      <template v-for="tab in resultTabs" :key="tab.key">
        <div v-if="activeTab === tab.key">
          <div class="stats-row">
            <div class="stat-mini" v-for="s in tab.statCards" :key="s.label" :style="{'--c': s.color}">
              <span class="stat-val mono">{{ s.val }}</span>
              <span class="stat-lbl">{{ s.label }}</span>
            </div>
          </div>

          <div class="view-tabs">
            <button class="view-tab" :class="{ active: tab.view==='detail' }" @click="tab.view='detail'">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3.5" cy="6" r="1.5"/><circle cx="3.5" cy="12" r="1.5"/><circle cx="3.5" cy="18" r="1.5"/></svg>
              明细列表
            </button>
            <button class="view-tab" :class="{ active: tab.view==='cluster' }" @click="tab.view='cluster'">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><line x1="12" y1="8" x2="5.5" y2="16"/><line x1="12" y1="8" x2="18.5" y2="16"/></svg>
              模板聚合
              <span class="cluster-count" v-if="tab.target.clusters.length">{{ tab.target.clusters.length }}</span>
            </button>
          </div>

          <!-- 明细 -->
          <div v-if="tab.view==='detail'" class="card table-card">
            <div class="table-header">
              <h3>慢查询明细</h3>
              <div class="filters">
                <select v-model="tab.filterSeverity" class="sel">
                  <option value="">全部</option>
                  <option value="critical">严重 (≥60s)</option>
                  <option value="warning">警告 (≥10s)</option>
                  <option value="info">一般</option>
                </select>
                <input v-model="tab.filterUser" placeholder="用户过滤" class="filter-input" />
                <input v-model="tab.filterSql" placeholder="SQL关键字" class="filter-input" />
              </div>
            </div>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th class="col-sev">#</th>
                    <th class="col-time">时间</th>
                    <th class="col-qt" @click="toggleSort(tab,'query_time')" style="cursor:pointer">
                      耗时(s) {{ tab.sortField==='query_time' ? (tab.sortAsc?'↑':'↓') : '↕' }}
                    </th>
                    <th class="col-rows" @click="toggleSort(tab,'rows_examined')" style="cursor:pointer">
                      扫描行 {{ tab.sortField==='rows_examined' ? (tab.sortAsc?'↑':'↓') : '↕' }}
                    </th>
                    <th class="col-user">用户@主机</th>
                    <th class="col-sql">SQL</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="e in pagedEntries(tab)" :key="e.id">
                    <tr :class="['row-'+e.severity, { 'row-selected': tab.expandedId===e.id }]"
                        @click="tab.expandedId = tab.expandedId===e.id ? null : e.id">
                      <td class="col-sev"><span class="sev-dot" :class="e.severity"></span></td>
                      <td class="col-time mono">{{ e.time_str }}</td>
                      <td class="col-qt"><span class="qt-badge" :class="e.severity">{{ e.query_time }}s</span></td>
                      <td class="col-rows mono">{{ fmtNum(e.rows_examined) }}</td>
                      <td class="col-user mono">{{ e.user }}@{{ e.host }}</td>
                      <td class="col-sql"><span class="sql-brief">{{ e.sql.slice(0,120) }}{{ e.sql.length>120?'…':'' }}</span></td>
                    </tr>
                    <tr v-if="tab.expandedId===e.id" class="detail-row">
                      <td colspan="6">
                        <div class="detail-box">
                          <div class="detail-meta">
                            <span>锁定：{{ e.lock_time }}s</span>
                            <span>返回行：{{ fmtNum(e.rows_sent) }}</span>
                            <span v-if="e.is_alert" class="alert-tag">⚠ 告警</span>
                          </div>
                          <pre class="sql-full">{{ e.sql }}</pre>
                        </div>
                      </td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
            <div v-if="totalPages(tab) > 1" class="pagination">
              <button :disabled="tab.page===1" @click="tab.page--">‹</button>
              <span>{{ tab.page }} / {{ totalPages(tab) }}</span>
              <button :disabled="tab.page===totalPages(tab)" @click="tab.page++">›</button>
              <span class="page-info">共 {{ filteredEntries(tab).length }} 条</span>
            </div>
          </div>

          <!-- 聚合 -->
          <div v-if="tab.view==='cluster'" class="card cluster-card">
            <div class="table-header">
              <h3>SQL 模板聚合 · drain3</h3>
              <span class="cluster-tip">相似 SQL 自动归组，按总耗时排序</span>
            </div>
            <div v-if="!tab.target.clusters.length" class="empty-cluster">暂无聚合数据</div>
            <div v-else class="cluster-list">
              <div v-for="c in tab.target.clusters" :key="c.cluster_id"
                class="cluster-item" :class="['ci-'+c.severity]">
                <div class="ci-header" @click="c._open = !c._open">
                  <span class="ci-rank">#{{ c.rank }}</span>
                  <span class="ci-sev" :class="c.severity"></span>
                  <span class="ci-count">{{ c.count }} 次</span>
                  <span class="ci-time">
                    <span class="ci-label">总耗时</span><strong>{{ c.total_time }}s</strong>
                    <span class="ci-sep">·</span>
                    <span class="ci-label">均值</span>{{ c.avg_time }}s
                    <span class="ci-sep">·</span>
                    <span class="ci-label">最大</span>{{ c.max_time }}s
                  </span>
                  <span class="ci-rows"><span class="ci-label">均扫描行</span>{{ fmtNum(c.avg_rows) }}</span>
                  <span v-if="c.alert_count" class="ci-alert">⚠ {{ c.alert_count }} 告警</span>
                  <svg class="ci-chevron" :class="{ open: c._open }" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                </div>
                <div class="ci-template">
                  <span class="ci-tpl-label">模板</span>
                  <code class="ci-tpl-sql">{{ c.template }}</code>
                </div>
                <div v-if="c._open" class="ci-samples">
                  <div class="ci-sample-title">代表性慢查询（最多3条）</div>
                  <div v-for="s in c.samples" :key="s.id" class="ci-sample">
                    <div class="ci-sample-meta">
                      <span class="qt-badge" :class="s.query_time>=60?'critical':s.query_time>=10?'warning':'info'">{{ s.query_time }}s</span>
                      <span class="mono">扫描 {{ fmtNum(s.rows_examined) }} 行</span>
                      <span class="mono">{{ s.user }}</span>
                      <span class="mono text-muted">{{ s.time_str }}</span>
                    </div>
                    <pre class="ci-sample-sql">{{ s.sql }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 空态 -->
    <div v-else-if="!fetching" class="empty-hint">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
      <p>从主机库选择目标，或手动输入 IP，点击「获取并解析」</p>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api/index.js'

// ── CMDB 主机 & 凭证库 ────────────────────────────────────────────────────
const cmdbHosts        = ref([])
const cmdbHostsLoading = ref(false)
const credList         = ref([])

onMounted(async () => {
  cmdbHostsLoading.value = true
  try {
    const [hostRes, credRes] = await Promise.all([
      api.slowlogHosts(),
      api.listCredentials(),
    ])
    cmdbHosts.value = (hostRes.data ?? []).filter(h => h.ip)
    credList.value  = credRes.data ?? credRes ?? []
  } catch {}
  cmdbHostsLoading.value = false
})

// ── 共享凭证（持久化） ─────────────────────────────────────────────────────
const CRED_KEY = 'slowlog_cred2'
const saved = (() => { try { return JSON.parse(sessionStorage.getItem(CRED_KEY) || '{}') } catch { return {} } })()
const credOpen = ref(true)
const credMode = ref(saved.credMode ?? 'auto')   // 'auto' | 'lib' | 'manual'
const cred = reactive({
  credential_id: saved.credential_id ?? '',
  ssh_user:      saved.ssh_user      ?? '',
  ssh_password:  saved.ssh_password  ?? '',
  ssh_port:      saved.ssh_port      ?? 22,
  threshold_sec: saved.threshold_sec ?? 1.0,
  alert_sec:     saved.alert_sec     ?? 10.0,
  date_from:     saved.date_from     ?? '',
  date_to:       saved.date_to       ?? '',
})
watch([credMode, cred], () => {
  sessionStorage.setItem(CRED_KEY, JSON.stringify({ credMode: credMode.value, ...cred }))
}, { deep: true })

const selectedCredName = computed(() => {
  const c = credList.value.find(c => c.id === cred.credential_id)
  return c ? c.name : ''
})

function setRange(days) {
  const to = new Date(), from = new Date()
  if (days === 0) {
    cred.date_from = cred.date_to = to.toISOString().slice(0, 10)
  } else if (days === 1) {
    from.setDate(from.getDate() - 1)
    cred.date_from = cred.date_to = from.toISOString().slice(0, 10)
  } else {
    from.setDate(from.getDate() - (days - 1))
    cred.date_from = from.toISOString().slice(0, 10)
    cred.date_to   = to.toISOString().slice(0, 10)
  }
}

// ── 批量选择面板 ─────────────────────────────────────────────────────────
const batchOpen     = ref(false)
const batchQ        = ref('')
const batchSelected = reactive(new Set())

const filteredCmdb = computed(() => {
  const q = batchQ.value.toLowerCase()
  return q
    ? cmdbHosts.value.filter(h => h.ip.includes(q) || (h.hostname||'').toLowerCase().includes(q))
    : cmdbHosts.value
})
function toggleBatch(instance) {
  if (batchSelected.has(instance)) batchSelected.delete(instance)
  else batchSelected.add(instance)
}
function batchSelectAll() {
  filteredCmdb.value.forEach(h => batchSelected.add(h.instance))
}
function applyBatch() {
  const existing = new Set(targets.value.map(t => t.host_ip))
  for (const inst of batchSelected) {
    const h = cmdbHosts.value.find(h => h.instance === inst)
    if (!h || existing.has(h.ip)) continue
    const t = makeTarget()
    t.host_ip   = h.ip
    t._hostname = h.hostname || h.instance
    targets.value.push(t)
  }
  // 清掉唯一的空行
  if (targets.value.length > 1) {
    const idx = targets.value.findIndex(t => !t.host_ip)
    if (idx !== -1) targets.value.splice(idx, 1)
  }
  batchSelected.clear()
  batchOpen.value = false
}

// ── 分析目标 ─────────────────────────────────────────────────────────────
let _id = 0
function makeTarget() {
  return reactive({
    id: ++_id, host_ip: '', log_path: '/mysqldata/mysql/data/3306/mysql-slow.log',
    _hostname: '', _suggest: false,
    loading: false, error: '',
    entries: [], clusters: [],
    summary: { total: 0, alert_count: 0, avg_query_time: 0, max_query_time: 0 },
    filterSeverity: '', filterUser: '', filterSql: '',
    sortField: 'query_time', sortAsc: false,
    page: 1, expandedId: null, view: 'detail',
  })
}
const targets      = ref([makeTarget()])
const fetching     = ref(false)
const validTargets = computed(() => targets.value.filter(t => t.host_ip.trim()))
function addTarget()     { targets.value.push(makeTarget()) }
function removeTarget(i) { if (targets.value.length > 1) targets.value.splice(i, 1) }

// IP 输入自动补全
function suggestHosts(t) {
  const q = (t.host_ip || '').toLowerCase()
  if (!q) return cmdbHosts.value.slice(0, 8)
  return cmdbHosts.value
    .filter(h => h.ip.includes(q) || (h.hostname||'').toLowerCase().includes(q))
    .slice(0, 6)
}
function pickHost(t, h) {
  t.host_ip   = h.ip
  t._hostname = h.hostname || h.instance
  t._suggest  = false
}
function hideSuggest(t) { setTimeout(() => { t._suggest = false }, 150) }

function statusClass(t) {
  if (t.loading) return 'status-loading'
  if (t.error)   return 'status-error'
  if (t.entries.length) return t.summary.alert_count > 0 ? 'status-warn' : 'status-ok'
  return 'status-idle'
}
function statusLabel(t) {
  if (t.error)          return '失败'
  if (t.entries.length) return `${t.entries.length} 条`
  return '–'
}

// ── 并行获取 ─────────────────────────────────────────────────────────────
function buildCredPayload() {
  if (credMode.value === 'lib')    return { credential_id: cred.credential_id, ssh_user: '', ssh_password: '' }
  if (credMode.value === 'manual') return { credential_id: '', ssh_user: cred.ssh_user, ssh_password: cred.ssh_password }
  return { credential_id: '', ssh_user: '', ssh_password: '' }  // auto: CMDB lookup
}

async function fetchAll() {
  const list = validTargets.value
  if (!list.length) return
  fetching.value = true
  aiText.value   = ''
  const credPayload = buildCredPayload()

  await Promise.all(list.map(async t => {
    t.loading = true; t.error = ''; t.entries = []; t.clusters = []; t.page = 1
    try {
      const res = await api.slowlogFetch({
        host_ip:       t.host_ip,
        log_path:      t.log_path,
        date_from:     cred.date_from || null,
        date_to:       cred.date_to   || null,
        ssh_port:      cred.ssh_port,
        threshold_sec: cred.threshold_sec,
        alert_sec:     cred.alert_sec,
        ...credPayload,
      })
      t.entries  = res.entries  ?? []
      t.clusters = (res.clusters ?? []).map(c => reactive({ ...c, _open: false }))
      t.summary  = res.summary  ?? {}
    } catch (e) {
      t.error = typeof e === 'string' ? e : (e?.message || '获取失败')
    } finally {
      t.loading = false
    }
  }))

  fetching.value = false
  const first = resultTabs.value.find(tab => tab.total > 0)
  if (first) activeTab.value = first.key
}

// ── 结果 Tabs ────────────────────────────────────────────────────────────
const activeTab  = ref('')
const resultTabs = computed(() =>
  targets.value.filter(t => t.entries.length || t.error).map(t => {
    const worst = t.entries.some(e => e.severity==='critical') ? 'critical'
                : t.entries.some(e => e.severity==='warning')  ? 'warning' : 'info'
    return {
      key: String(t.id),
      label: t._hostname ? `${t.host_ip} (${t._hostname})` : t.host_ip,
      total: t.entries.length,
      worstSeverity: worst,
      target: t,
      statCards: [
        { label: '慢查询总数',   val: t.summary.total,          color: 'var(--accent)'  },
        { label: '告警数(≥10s)', val: t.summary.alert_count,    color: 'var(--error)'   },
        { label: '平均耗时',     val: (t.summary.avg_query_time??0)+'s', color: 'var(--warning)' },
        { label: '最长耗时',     val: (t.summary.max_query_time??0)+'s', color: 'var(--error)'   },
      ],
      get view()            { return t.view },           set view(v)           { t.view = v },
      get filterSeverity()  { return t.filterSeverity }, set filterSeverity(v) { t.filterSeverity=v; t.page=1 },
      get filterUser()      { return t.filterUser },     set filterUser(v)     { t.filterUser=v; t.page=1 },
      get filterSql()       { return t.filterSql },      set filterSql(v)      { t.filterSql=v; t.page=1 },
      get sortField()       { return t.sortField },      set sortField(v)      { t.sortField=v },
      get sortAsc()         { return t.sortAsc },        set sortAsc(v)        { t.sortAsc=v },
      get page()            { return t.page },           set page(v)           { t.page=v },
      get expandedId()      { return t.expandedId },     set expandedId(v)     { t.expandedId=v },
    }
  })
)
watch(resultTabs, tabs => {
  if (tabs.length && !tabs.find(t => t.key === activeTab.value))
    activeTab.value = tabs[0]?.key ?? ''
})
const hasEntries = computed(() => targets.value.some(t => t.entries.length > 0))

// ── 表格辅助 ────────────────────────────────────────────────────────────
const PAGE_SIZE = 20
function toggleSort(tab, field) {
  if (tab.sortField===field) tab.sortAsc=!tab.sortAsc
  else { tab.sortField=field; tab.sortAsc=false }
  tab.page=1
}
function filteredEntries(tab) {
  let list = tab.target.entries
  if (tab.filterSeverity) list=list.filter(e=>e.severity===tab.filterSeverity)
  if (tab.filterUser)     list=list.filter(e=>(e.user+'@'+e.host).includes(tab.filterUser))
  if (tab.filterSql)      list=list.filter(e=>e.sql.toLowerCase().includes(tab.filterSql.toLowerCase()))
  const dir=tab.sortAsc?1:-1
  return [...list].sort((a,b)=>dir*(a[tab.sortField]-b[tab.sortField]))
}
function totalPages(tab)   { return Math.max(1, Math.ceil(filteredEntries(tab).length/PAGE_SIZE)) }
function pagedEntries(tab) { const s=(tab.page-1)*PAGE_SIZE; return filteredEntries(tab).slice(s,s+PAGE_SIZE) }

// ── AI 分析 ──────────────────────────────────────────────────────────────
const analyzing  = ref(false)
const aiText     = ref('')
const renderedAi = computed(() =>
  aiText.value
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/^### (.+)$/gm,'<h4>$1</h4>')
    .replace(/^## (.+)$/gm,'<h3>$1</h3>')
    .replace(/^# (.+)$/gm,'<h2>$1</h2>')
    .replace(/^(\d+\.) /gm,'<br>$1 ')
    .replace(/\n/g,'<br>')
)
function startAnalysis() {
  if (!hasEntries.value) return
  analyzing.value=true; aiText.value=''
  const all = targets.value
    .flatMap(t=>t.entries.filter(e=>!e.is_ignore).map(e=>({...e,_host:t.host_ip})))
    .sort((a,b)=>b.query_time-a.query_time).slice(0,15)
  const params = new URLSearchParams({
    entries_json: JSON.stringify(all),
    host_ip: targets.value.filter(t=>t.entries.length).map(t=>t.host_ip).join(', '),
    date: [cred.date_from, cred.date_to].filter(Boolean).join(' ~ '),
  })
  const es = new EventSource(`/api/slowlog/analyze/stream?${params}`)
  es.onmessage = ev => {
    if (ev.data==='[DONE]') { es.close(); analyzing.value=false; return }
    try { const d=JSON.parse(ev.data); if(d.chunk) aiText.value+=d.chunk; if(d.error){ aiText.value+='\n[出错] '+d.error; es.close(); analyzing.value=false } } catch {}
  }
  es.onerror = () => { es.close(); analyzing.value=false }
}

function fmtNum(n) {
  if (n>=1_000_000) return (n/1_000_000).toFixed(1)+'M'
  if (n>=1_000)     return (n/1_000).toFixed(1)+'K'
  return String(n??0)
}
</script>

<style scoped>
.page { flex:1; min-height:0; overflow-y:auto; padding:20px 24px; display:flex; flex-direction:column; gap:12px; }
.page-header { display:flex; align-items:baseline; gap:10px; }
.page-header h1 { font-size:16px; font-weight:600; color:var(--text-primary); }
.subtitle { font-size:12px; color:var(--text-muted); }
.card { background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-card); }

/* ── 凭证 ─────────────────────────────────────────────────────────── */
.cred-header { display:flex; align-items:center; gap:8px; padding:12px 16px; cursor:pointer; user-select:none; border-radius:var(--radius-card); }
.cred-header:hover { background:var(--bg-hover); }
.cred-title { display:flex; align-items:center; gap:6px; font-size:12px; font-weight:600; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.05em; }
.cred-status { margin-left:auto; font-size:11px; }
.cred-set   { color:var(--success); }
.cred-unset { color:var(--text-muted); }
.chevron { transition:transform .2s; flex-shrink:0; color:var(--text-muted); }
.chevron.open { transform:rotate(180deg); }
.cred-body { padding:4px 16px 16px; border-top:1px solid var(--border-light); }

/* 凭证模式 tab */
.mode-tabs { display:flex; gap:4px; margin:12px 0 10px; }
.mode-tab { display:flex; align-items:center; gap:5px; padding:5px 12px; border:1px solid var(--border); border-radius:var(--radius); background:transparent; color:var(--text-secondary); font-size:12px; cursor:pointer; font-family:inherit; transition:all .12s; }
.mode-tab:hover { border-color:var(--accent); color:var(--accent); }
.mode-tab.active { background:var(--accent); border-color:var(--accent); color:#fff; }
.mode-hint { font-size:12px; color:var(--text-muted); padding:8px 0; }

.cred-grid { display:flex; gap:12px; flex-wrap:wrap; align-items:end; }
.cred-grid .field { flex:1; min-width:130px; }
.field { display:flex; flex-direction:column; gap:5px; }
.field label { font-size:11px; font-weight:500; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.05em; }
.field input, .sel-full { background:var(--bg-input); border:1px solid var(--border); border-radius:var(--radius); padding:7px 10px; color:var(--text-primary); font-size:13px; font-family:inherit; outline:none; transition:border-color .12s; }
.field input:focus, .sel-full:focus { border-color:var(--accent); }
.sel-full { width:100%; }
.field-wide { flex:2; min-width:260px; }
.field-narrow { flex:0 0 100px; }
.field-hint { font-size:11px; color:var(--text-muted); align-self:center; }
.link { color:var(--accent); text-decoration:none; }
.link:hover { text-decoration:underline; }
.quick-dates { display:flex; gap:4px; flex-wrap:wrap; }

/* ── 目标 ─────────────────────────────────────────────────────────── */
.targets-card { padding:0; }
.targets-header { display:flex; align-items:center; gap:8px; padding:12px 16px; border-bottom:1px solid var(--border-light); flex-wrap:wrap; gap:8px; }
.targets-header h3 { font-size:12px; font-weight:600; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.07em; flex:1; }
.targets-actions { display:flex; gap:6px; align-items:center; flex-wrap:wrap; }

/* 批量面板 */
.batch-wrap { position:relative; }
.badge { background:var(--accent); color:#fff; font-size:10px; font-weight:700; padding:0 5px; border-radius:8px; line-height:16px; margin-left:2px; }
.batch-panel { position:absolute; top:calc(100% + 6px); left:0; z-index:100; width:360px; background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-card); box-shadow:0 8px 24px rgba(0,0,0,.4); }
.batch-search { display:flex; align-items:center; gap:6px; padding:10px 12px; border-bottom:1px solid var(--border-light); }
.batch-inp { flex:1; background:var(--bg-input); border:1px solid var(--border); border-radius:var(--radius); padding:5px 8px; color:var(--text-primary); font-size:12px; font-family:inherit; outline:none; }
.batch-inp:focus { border-color:var(--accent); }
.btn-link { background:none; border:none; color:var(--accent); font-size:11px; cursor:pointer; padding:2px 4px; font-family:inherit; }
.btn-link:hover { text-decoration:underline; }
.batch-list { max-height:240px; overflow-y:auto; }
.batch-row { display:flex; align-items:center; gap:8px; padding:7px 12px; cursor:pointer; font-size:12px; }
.batch-row:hover { background:var(--bg-hover); }
.batch-row input[type=checkbox] { width:14px; height:14px; accent-color:var(--accent); cursor:pointer; flex-shrink:0; }
.batch-ip { width:110px; flex-shrink:0; color:var(--text-primary); font-size:11px; }
.batch-name { flex:1; color:var(--text-secondary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.batch-cred-tag { font-size:10px; color:var(--success); background:rgba(63,185,80,.1); padding:1px 6px; border-radius:3px; white-space:nowrap; }
.batch-nocred   { font-size:10px; color:var(--text-muted); }
.batch-footer { display:flex; gap:8px; padding:10px 12px; border-top:1px solid var(--border-light); }

.target-row { display:flex; align-items:center; gap:10px; padding:9px 16px; border-bottom:1px solid var(--border-light); }
.target-row:last-child { border-bottom:none; }
.target-index { font-size:11px; color:var(--text-muted); width:16px; text-align:center; flex-shrink:0; }
.target-fields { display:flex; gap:8px; flex:1; align-items:center; flex-wrap:wrap; }

.ip-wrap { position:relative; }
.inp-ip  { width:150px; }
.inp-path { flex:1; min-width:240px; }
.inp-ip, .inp-path { background:var(--bg-input); border:1px solid var(--border); border-radius:var(--radius); padding:6px 9px; color:var(--text-primary); font-size:12px; font-family:inherit; outline:none; transition:border-color .12s; }
.inp-ip:focus, .inp-path:focus { border-color:var(--accent); }

.suggest-list { position:absolute; top:calc(100% + 2px); left:0; width:320px; background:var(--bg-card); border:1px solid var(--border); border-radius:var(--radius-card); box-shadow:0 6px 20px rgba(0,0,0,.4); z-index:99; overflow:hidden; }
.suggest-item { display:flex; align-items:center; gap:8px; padding:7px 10px; cursor:pointer; font-size:12px; }
.suggest-item:hover { background:var(--bg-hover); }
.suggest-ip   { width:115px; flex-shrink:0; color:var(--text-primary); font-size:11px; }
.suggest-name { flex:1; color:var(--text-secondary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.suggest-cred { font-size:10px; color:var(--success); white-space:nowrap; }

.target-hostname { font-size:11px; color:var(--text-muted); white-space:nowrap; }
.target-status { font-size:11px; font-weight:500; padding:2px 8px; border-radius:3px; white-space:nowrap; flex-shrink:0; }
.status-idle    { color:var(--text-muted); }
.status-loading { color:var(--accent); }
.status-ok   { color:var(--success); background:rgba(63,185,80,.1); }
.status-warn { color:var(--warning); background:rgba(210,153,34,.1); }
.status-error{ color:var(--error);   background:rgba(248,81,73,.1); }
.target-error { font-size:11px; color:var(--error); opacity:.85; max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.btn-remove { background:none; border:none; color:var(--text-muted); cursor:pointer; padding:4px; border-radius:3px; display:flex; flex-shrink:0; transition:color .12s, background .12s; }
.btn-remove:hover:not(:disabled) { color:var(--error); background:rgba(248,81,73,.1); }
.btn-remove:disabled { opacity:.3; cursor:not-allowed; }
.no-cmdb-hint { padding:12px 16px; font-size:12px; color:var(--text-muted); }

/* ── 按钮 ─────────────────────────────────────────────────────────── */
.btn-primary,.btn-secondary,.btn-ghost { display:flex; align-items:center; gap:5px; padding:6px 12px; border:none; border-radius:var(--radius); font-size:12px; font-weight:500; cursor:pointer; font-family:inherit; transition:background .12s,opacity .12s; white-space:nowrap; }
.btn-primary  { background:var(--accent); color:#fff; }
.btn-primary:hover:not(:disabled) { background:var(--accent-hover); }
.btn-secondary { background:var(--bg-surface); border:1px solid var(--border); color:var(--text-primary); }
.btn-secondary:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); }
.btn-ghost { background:transparent; border:1px solid var(--border); color:var(--text-secondary); }
.btn-ghost:hover:not(:disabled) { border-color:var(--accent); color:var(--accent); background:rgba(56,139,253,.05); }
.btn-primary:disabled,.btn-secondary:disabled,.btn-ghost:disabled { opacity:.4; cursor:not-allowed; }
.btn-sm { padding:4px 10px; font-size:11px; }
.btn-icon { background:none; border:none; color:var(--text-muted); cursor:pointer; font-size:14px; margin-left:auto; }

/* ── AI ───────────────────────────────────────────────────────────── */
.ai-card { padding:16px 20px; border-left:3px solid var(--accent); }
.ai-header { display:flex; align-items:center; gap:8px; margin-bottom:12px; font-size:13px; font-weight:600; color:var(--text-primary); }
.ai-badge { background:var(--accent); color:#fff; font-size:10px; font-weight:700; padding:1px 6px; border-radius:3px; }
.ai-body { font-size:13px; color:var(--text-primary); line-height:1.7; white-space:pre-wrap; }
.ai-body :deep(h2),.ai-body :deep(h3),.ai-body :deep(h4) { color:var(--accent); margin:10px 0 4px; }
.ai-body :deep(strong) { color:var(--warning); }
.ai-typing { display:flex; gap:4px; margin-top:10px; }
.dot { width:6px; height:6px; border-radius:50%; background:var(--accent); animation:blink 1.2s infinite; }
.dot:nth-child(2){animation-delay:.2s} .dot:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}

/* ── 结果 Tabs ────────────────────────────────────────────────────── */
.results-section { display:flex; flex-direction:column; gap:10px; }
.tab-bar { display:flex; gap:4px; flex-wrap:wrap; }
.tab-btn { display:flex; align-items:center; gap:5px; padding:6px 12px; border:1px solid var(--border); border-radius:var(--radius); background:var(--bg-card); color:var(--text-secondary); font-size:12px; cursor:pointer; font-family:inherit; transition:all .12s; }
.tab-btn:hover { border-color:var(--accent); color:var(--accent); }
.tab-btn.active { background:var(--accent); border-color:var(--accent); color:#fff; }
.tab-dot { width:6px; height:6px; border-radius:50%; }
.tab-dot.critical{background:#f85149} .tab-dot.warning{background:#d29922} .tab-dot.info{background:#3fb950}
.tab-btn.active .tab-dot{background:rgba(255,255,255,.7)}
.tab-count { font-size:10px; opacity:.8; }

.view-tabs { display:flex; gap:4px; margin-bottom:8px; }
.view-tab { display:flex; align-items:center; gap:6px; padding:5px 12px; border:1px solid var(--border); border-radius:var(--radius); background:var(--bg-card); color:var(--text-secondary); font-size:12px; cursor:pointer; font-family:inherit; transition:all .12s; }
.view-tab:hover { border-color:var(--accent); color:var(--accent); }
.view-tab.active { background:var(--bg-surface); border-color:var(--accent); color:var(--accent); font-weight:500; }
.cluster-count { background:var(--accent); color:#fff; font-size:10px; font-weight:700; padding:0 5px; border-radius:8px; line-height:16px; }

/* ── 汇总 ─────────────────────────────────────────────────────────── */
.stats-row { display:grid; grid-template-columns:repeat(4,1fr); gap:10px; }
.stat-mini { background:var(--bg-card); border:1px solid var(--border); border-top:2px solid var(--c,var(--accent)); border-radius:var(--radius-card); padding:12px 14px; display:flex; flex-direction:column; gap:4px; }
.stat-val { font-size:22px; font-weight:600; color:var(--c,var(--accent)); line-height:1; }
.stat-lbl { font-size:10px; color:var(--text-muted); text-transform:uppercase; letter-spacing:.06em; }

/* ── 明细表格 ─────────────────────────────────────────────────────── */
.table-card { padding:0; }
.table-header { display:flex; align-items:center; justify-content:space-between; padding:12px 16px; border-bottom:1px solid var(--border-light); }
.table-header h3 { font-size:12px; font-weight:600; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.07em; }
.filters { display:flex; gap:8px; }
.sel,.filter-input { background:var(--bg-input); border:1px solid var(--border); border-radius:var(--radius); padding:5px 8px; color:var(--text-primary); font-size:12px; font-family:inherit; outline:none; }
.sel:focus,.filter-input:focus { border-color:var(--accent); }
.filter-input { width:120px; }
.table-wrap { overflow-x:auto; }
table { width:100%; border-collapse:collapse; }
th { padding:8px 10px; font-size:10px; font-weight:600; color:var(--text-secondary); text-transform:uppercase; letter-spacing:.06em; text-align:left; white-space:nowrap; border-bottom:1px solid var(--border-light); }
td { padding:7px 10px; font-size:12px; border-bottom:1px solid var(--border-light); vertical-align:middle; }
tr:last-child td{border-bottom:none} tr:hover td{background:var(--bg-hover)}
.row-selected td{background:var(--bg-active)!important}
.row-critical td{background:rgba(248,81,73,.03)} .row-warning td{background:rgba(210,153,34,.03)}
.col-sev{width:28px} .col-time{width:140px;font-size:11px} .col-qt{width:90px} .col-rows{width:80px} .col-user{width:140px} .col-sql{max-width:0}
.sev-dot{display:inline-block;width:7px;height:7px;border-radius:50%}
.sev-dot.critical{background:var(--error);box-shadow:0 0 4px var(--error)} .sev-dot.warning{background:var(--warning)} .sev-dot.info{background:var(--success)}
.qt-badge{padding:2px 7px;border-radius:3px;font-weight:600;font-family:'JetBrains Mono',monospace;font-size:11px}
.qt-badge.critical{background:rgba(248,81,73,.15);color:var(--error)} .qt-badge.warning{background:rgba(210,153,34,.15);color:var(--warning)} .qt-badge.info{background:rgba(63,185,80,.12);color:var(--success)}
.sql-brief{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:480px;color:var(--text-secondary);font-family:'JetBrains Mono',monospace;font-size:11px}
.detail-row td{background:var(--bg-surface)!important;padding:0}
.detail-box{padding:12px 14px}
.detail-meta{display:flex;gap:14px;font-size:11px;color:var(--text-muted);margin-bottom:8px}
.alert-tag{color:var(--error);font-weight:600}
.sql-full{background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-primary);white-space:pre-wrap;word-break:break-all;max-height:200px;overflow-y:auto;margin:0}
.pagination{display:flex;align-items:center;gap:8px;padding:10px 16px;border-top:1px solid var(--border-light);font-size:12px;color:var(--text-muted)}
.pagination button{background:var(--bg-surface);border:1px solid var(--border);border-radius:var(--radius);padding:2px 10px;color:var(--text-primary);cursor:pointer;font-size:14px}
.pagination button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)} .pagination button:disabled{opacity:.4;cursor:not-allowed}
.page-info{margin-left:auto}

/* ── 聚合 ─────────────────────────────────────────────────────────── */
.cluster-card{padding:0} .cluster-tip{font-size:11px;color:var(--text-muted);margin-left:8px}
.empty-cluster{padding:30px;text-align:center;color:var(--text-muted);font-size:13px}
.cluster-list{display:flex;flex-direction:column}
.cluster-item{border-bottom:1px solid var(--border-light)} .cluster-item:last-child{border-bottom:none}
.ci-header{display:flex;align-items:center;gap:10px;padding:10px 16px;cursor:pointer;transition:background .1s}
.ci-header:hover{background:var(--bg-hover)}
.ci-rank{font-size:11px;font-weight:700;color:var(--text-muted);width:22px;flex-shrink:0}
.ci-sev{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.ci-sev.critical{background:var(--error);box-shadow:0 0 5px var(--error)} .ci-sev.warning{background:var(--warning)} .ci-sev.info{background:var(--success)}
.ci-count{font-size:12px;font-weight:600;color:var(--accent);min-width:48px}
.ci-time{display:flex;align-items:center;gap:5px;font-size:12px;flex:1} .ci-time strong{color:var(--error);font-family:'JetBrains Mono',monospace}
.ci-rows{font-size:11px;color:var(--text-muted);display:flex;gap:4px;align-items:center}
.ci-label{font-size:10px;color:var(--text-muted)} .ci-sep{color:var(--border)}
.ci-alert{font-size:11px;color:var(--warning);font-weight:600}
.ci-chevron{transition:transform .2s;color:var(--text-muted);flex-shrink:0} .ci-chevron.open{transform:rotate(180deg)}
.ci-template{display:flex;align-items:flex-start;gap:8px;padding:6px 16px 10px 56px;background:rgba(0,0,0,.15)}
.ci-tpl-label{font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;padding-top:2px}
.ci-tpl-sql{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);word-break:break-all;white-space:pre-wrap;line-height:1.5}
.ci-samples{padding:10px 16px 14px 56px;background:var(--bg-surface)}
.ci-sample-title{font-size:10px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
.ci-sample{margin-bottom:10px;border-left:2px solid var(--border);padding-left:10px} .ci-sample:last-child{margin-bottom:0}
.ci-sample-meta{display:flex;align-items:center;gap:10px;font-size:11px;margin-bottom:5px;flex-wrap:wrap}
.ci-sample-sql{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);white-space:pre-wrap;word-break:break-all;max-height:150px;overflow-y:auto;background:var(--bg-input);border:1px solid var(--border);border-radius:var(--radius);padding:8px 10px;margin:0}
.ci-critical .ci-header{border-left:3px solid var(--error)} .ci-warning .ci-header{border-left:3px solid var(--warning)} .ci-info .ci-header{border-left:3px solid transparent}

/* ── Spinners ─────────────────────────────────────────────────────── */
.spinner-xs{width:12px;height:12px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;display:inline-block}
.spinner-xs2{width:10px;height:10px;border:2px solid rgba(255,255,255,.2);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite;display:inline-block}
@keyframes spin{to{transform:rotate(360deg)}}
.empty-hint{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:60px 20px;color:var(--text-muted);font-size:13px}
.mono{font-family:'JetBrains Mono',monospace} .text-muted{color:var(--text-muted)}
</style>
