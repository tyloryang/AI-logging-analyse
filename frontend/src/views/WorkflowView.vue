<template>
  <div class="wf-page">
    <div class="wf-head">
      <div>
        <h2 class="wf-title">工作流编排</h2>
        <p class="wf-sub">参考 itops-agent-platform 的 workflow / tasks / scheduled-tasks 模型，串联诊断、审批、执行与验证。</p>
      </div>
      <div class="wf-actions">
        <button class="btn btn-outline" @click="loadAll" :disabled="loading">刷新</button>
        <button class="btn btn-primary" @click="openCreateWorkflow">新建工作流</button>
      </div>
    </div>

    <div class="wf-kpis">
      <div class="kpi"><b>{{ summary.workflows }}</b><span>工作流</span></div>
      <div class="kpi"><b>{{ summary.templates }}</b><span>模板</span></div>
      <div class="kpi"><b>{{ summary.tasks }}</b><span>执行任务</span></div>
      <div class="kpi"><b>{{ summary.enabled_schedules }}</b><span>启用计划</span></div>
    </div>

    <div class="wf-tabs">
      <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
        {{ tab.label }}
      </button>
    </div>

    <section v-if="activeTab === 'workflows'" class="wf-section">
      <div class="wf-toolbar">
        <div class="search">
          <input v-model="search" placeholder="搜索工作流名称、描述或标签..." @input="onSearchInput" />
        </div>
        <select v-model="templateFilter" @change="loadWorkflows">
          <option value="all">全部</option>
          <option value="template">模板</option>
          <option value="custom">自定义</option>
        </select>
      </div>

      <div v-if="loading" class="empty">加载中...</div>
      <div v-else-if="!workflows.length" class="empty">
        <span>暂无工作流</span>
        <button class="btn btn-primary" @click="openCreateWorkflow">创建第一个</button>
      </div>
      <div v-else class="workflow-grid">
        <article v-for="workflow in workflows" :key="workflow.id" class="workflow-card">
          <div class="card-top">
            <span class="badge" :class="workflow.is_template ? 'tpl' : 'custom'">{{ workflow.is_template ? '模板' : '自定义' }}</span>
            <span class="state" :class="workflow.status">{{ workflow.status === 'enabled' ? '启用' : '停用' }}</span>
          </div>
          <h3>{{ workflow.name }}</h3>
          <p>{{ workflow.description || '暂无描述' }}</p>
          <div class="tags">
            <span v-for="tag in (workflow.tags || []).slice(0, 4)" :key="tag">#{{ tag }}</span>
          </div>
          <div class="meta-row">
            <span>{{ workflow.nodes?.length || 0 }} 节点</span>
            <span>{{ workflow.edges?.length || 0 }} 连线</span>
            <span>{{ triggerLabel(workflow.trigger_type) }}</span>
          </div>
          <div class="node-strip">
            <span v-for="node in (workflow.nodes || []).slice(0, 6)" :key="node.id">{{ node.label || node.id }}</span>
          </div>
          <div class="card-actions">
            <button class="btn btn-primary" @click="run(workflow)">执行</button>
            <button class="btn btn-outline" @click="openEditWorkflow(workflow)">编辑</button>
            <button class="btn btn-outline" @click="duplicate(workflow)">复制</button>
            <button class="btn btn-danger" @click="removeWorkflow(workflow)">删除</button>
          </div>
        </article>
      </div>
    </section>

    <section v-else-if="activeTab === 'tasks'" class="wf-section">
      <div class="wf-toolbar">
        <strong>执行任务</strong>
        <button class="btn btn-outline" @click="loadTasks">刷新任务</button>
      </div>
      <div v-if="!tasks.length" class="empty">暂无执行记录</div>
      <table v-else class="wf-table">
        <thead>
          <tr><th>任务名</th><th>工作流</th><th>状态</th><th>节点</th><th>开始时间</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="task in tasks" :key="task.id" @click="detailTask = task">
            <td>{{ task.name }}</td>
            <td>{{ task.workflow_name }}</td>
            <td><span class="status" :class="task.status">{{ statusLabel(task.status) }}</span></td>
            <td>{{ task.execution_order?.length || 0 }}</td>
            <td>{{ fmt(task.start_time || task.created_at) }}</td>
            <td @click.stop>
              <button class="btn btn-xs btn-outline" @click="detailTask = task">详情</button>
              <button v-if="task.status === 'running' || task.status === 'paused'" class="btn btn-xs btn-danger" @click="cancelTask(task)">取消</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <section v-else class="wf-section">
      <div class="wf-toolbar">
        <strong>定时任务</strong>
        <button class="btn btn-primary" @click="openCreateSchedule">新增计划</button>
      </div>
      <div v-if="!schedules.length" class="empty">暂无定时任务</div>
      <table v-else class="wf-table">
        <thead>
          <tr><th>名称</th><th>工作流</th><th>Cron</th><th>状态</th><th>最近执行</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="schedule in schedules" :key="schedule.id">
            <td>{{ schedule.name }}</td>
            <td>{{ schedule.workflow_name || workflowName(schedule.workflow_id) }}</td>
            <td class="mono">{{ schedule.cron_expression }}</td>
            <td><span class="status" :class="schedule.enabled ? 'success' : 'paused'">{{ schedule.enabled ? '启用' : '停用' }}</span></td>
            <td>{{ schedule.last_run_at ? fmt(schedule.last_run_at) : '未执行' }}</td>
            <td>
              <button class="btn btn-xs btn-outline" @click="toggleSchedule(schedule)">{{ schedule.enabled ? '停用' : '启用' }}</button>
              <button class="btn btn-xs btn-outline" @click="openEditSchedule(schedule)">编辑</button>
              <button class="btn btn-xs btn-danger" @click="removeSchedule(schedule)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="showWorkflowForm" class="modal-mask" @click.self="showWorkflowForm = false">
      <div class="modal">
        <div class="modal-head">
          <span>{{ editingWorkflowId ? '编辑工作流' : '新建工作流' }}</span>
          <button @click="showWorkflowForm = false">×</button>
        </div>
        <div class="modal-body">
          <label><span>名称</span><input v-model="workflowForm.name" placeholder="例如：告警响应闭环" /></label>
          <label><span>描述</span><textarea v-model="workflowForm.description" rows="3" placeholder="说明触发场景和执行目标"></textarea></label>
          <div class="form-grid">
            <label><span>触发方式</span><select v-model="workflowForm.trigger_type"><option value="manual">手动</option><option value="alert">告警</option><option value="schedule">定时</option><option value="webhook">Webhook</option></select></label>
            <label><span>状态</span><select v-model="workflowForm.status"><option value="enabled">启用</option><option value="disabled">停用</option></select></label>
          </div>
          <label><span>标签（逗号分隔）</span><input v-model="workflowForm.tagsStr" placeholder="alert, aiops, remediation" /></label>
          <label><span>节点（每行一个，按名称自动识别类型：指标采集/日志扫描/AI 诊断/健康检查/审批/执行处置/通知/报告）</span><textarea v-model="workflowForm.nodeLines" rows="7" placeholder="告警触发&#10;采集指标&#10;AI 诊断&#10;人工审批&#10;执行处置&#10;通知值班"></textarea></label>
          <div class="form-grid">
            <label>
              <span>处置命令（「执行处置」节点通过 Ansible 执行，可留空）</span>
              <input v-model="workflowForm.actionCommand" placeholder="例如：systemctl restart nginx" />
            </label>
            <label>
              <span>处置目标分组</span>
              <select v-model="workflowForm.actionHostGroup">
                <option value="">未指定</option>
                <option v-for="g in hostGroups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.host_count || 0 }} 台）</option>
              </select>
            </label>
          </div>
          <label class="check-line"><input type="checkbox" v-model="workflowForm.is_template" />保存为模板</label>
          <div v-if="formError" class="form-error">{{ formError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-primary" :disabled="savingWorkflow" @click="saveWorkflow">{{ savingWorkflow ? '保存中...' : '保存' }}</button>
          <button class="btn btn-outline" @click="showWorkflowForm = false">取消</button>
        </div>
      </div>
    </div>

    <div v-if="showScheduleForm" class="modal-mask" @click.self="showScheduleForm = false">
      <div class="modal modal-sm">
        <div class="modal-head">
          <span>{{ editingScheduleId ? '编辑定时任务' : '新增定时任务' }}</span>
          <button @click="showScheduleForm = false">×</button>
        </div>
        <div class="modal-body">
          <label><span>名称</span><input v-model="scheduleForm.name" /></label>
          <label><span>工作流</span><select v-model="scheduleForm.workflow_id"><option value="">请选择工作流</option><option v-for="workflow in workflows" :key="workflow.id" :value="workflow.id">{{ workflow.name }}</option></select></label>
          <label><span>Cron 表达式</span><input v-model="scheduleForm.cron_expression" placeholder="0 9 * * *" /></label>
          <label><span>描述</span><textarea v-model="scheduleForm.description" rows="3"></textarea></label>
          <label class="check-line"><input type="checkbox" v-model="scheduleForm.enabled" />启用计划</label>
        </div>
        <div class="modal-foot">
          <button class="btn btn-primary" @click="saveSchedule">保存</button>
          <button class="btn btn-outline" @click="showScheduleForm = false">取消</button>
        </div>
      </div>
    </div>

    <div v-if="detailTask" class="drawer-mask" @click.self="detailTask = null">
      <aside class="drawer">
        <div class="drawer-head">
          <span>{{ detailTask.name }}</span>
          <button @click="detailTask = null">×</button>
        </div>
        <div class="detail-grid">
          <div><span>工作流</span><b>{{ detailTask.workflow_name }}</b></div>
          <div><span>状态</span><b>{{ statusLabel(detailTask.status) }}</b></div>
          <div><span>开始</span><b>{{ fmt(detailTask.start_time) }}</b></div>
          <div><span>结束</span><b>{{ fmt(detailTask.end_time) }}</b></div>
        </div>
        <div class="drawer-section">节点结果</div>
        <div v-if="!Object.keys(detailTask.node_results || {}).length" class="empty small">
          {{ detailTask.status === 'running' ? '执行中…' : '暂无节点结果' }}
        </div>
        <div
          v-for="nodeId in detailTask.execution_order || Object.keys(detailTask.node_results || {})"
          :key="nodeId"
        >
          <div v-if="detailTask.node_results?.[nodeId]" class="node-result" :class="detailTask.node_results[nodeId].status">
            <div class="node-result-head">
              <span class="node-dot" :class="detailTask.node_results[nodeId].status"></span>
              <b>{{ nodeLabel(nodeId) }}</b>
              <em>{{ detailTask.node_results[nodeId].status === 'success' ? '成功' : '失败' }}</em>
            </div>
            <pre>{{ detailTask.node_results[nodeId].output }}</pre>
          </div>
          <div v-else-if="detailTask.status === 'running' && detailTask.current_node_id === nodeId" class="node-result running">
            <div class="node-result-head">
              <span class="node-dot running"></span>
              <b>{{ nodeLabel(nodeId) }}</b>
              <em>执行中…</em>
            </div>
          </div>
        </div>

        <div class="drawer-section">执行日志</div>
        <div v-if="!(detailTask.logs || []).length" class="empty small">暂无日志</div>
        <div v-for="(log, index) in detailTask.logs || []" :key="index" class="log-row" :class="log.level">
          <span>{{ log.level || 'info' }}</span>
          <p>{{ log.message }}</p>
        </div>
        <div class="drawer-section">上下文</div>
        <pre class="json-pre">{{ JSON.stringify(detailTask.context || {}, null, 2) }}</pre>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api/index.js'

const tabs = [
  { key: 'workflows', label: '工作流定义' },
  { key: 'tasks', label: '执行任务' },
  { key: 'schedules', label: '定时任务' },
]

const activeTab = ref('workflows')
const loading = ref(false)
const workflows = ref([])
const tasks = ref([])
const schedules = ref([])
const search = ref('')
const templateFilter = ref('all')
const detailTask = ref(null)
const summary = reactive({ workflows: 0, templates: 0, tasks: 0, scheduled_tasks: 0, enabled_schedules: 0, task_status: {} })

let searchTimer = null

const showWorkflowForm = ref(false)
const editingWorkflowId = ref('')
const savingWorkflow = ref(false)
const formError = ref('')
const workflowForm = reactive({
  name: '',
  description: '',
  tagsStr: '',
  trigger_type: 'manual',
  status: 'enabled',
  is_template: false,
  nodeLines: '',
  actionCommand: '',
  actionHostGroup: '',
})
const hostGroups = ref([])

const showScheduleForm = ref(false)
const editingScheduleId = ref('')
const scheduleForm = reactive({
  name: '',
  description: '',
  workflow_id: '',
  cron_expression: '0 9 * * *',
  enabled: true,
})

const workflowMap = computed(() => Object.fromEntries(workflows.value.map(item => [item.id, item.name])))

function workflowName(id) {
  return workflowMap.value[id] || id || '-'
}

function nodeLabel(nodeId) {
  const workflow = workflows.value.find(item => item.id === detailTask.value?.workflow_id)
  const node = (workflow?.nodes || []).find(item => String(item.id) === String(nodeId))
  return node?.label || nodeId
}

function triggerLabel(value) {
  return { manual: '手动触发', alert: '告警触发', schedule: '定时触发', webhook: 'Webhook' }[value] || value || '手动触发'
}

function statusLabel(value) {
  return { success: '成功', running: '运行中', failed: '失败', paused: '暂停', cancelled: '已取消' }[value] || value || '-'
}

function fmt(iso) {
  if (!iso) return '-'
  return String(iso).slice(0, 19).replace('T', ' ')
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadWorkflows, 250)
}

async function loadSummary() {
  try { Object.assign(summary, await api.workflowSummary()) } catch { /* ignore */ }
}

async function loadWorkflows() {
  loading.value = true
  try {
    const params = {}
    if (search.value.trim()) params.search = search.value.trim()
    if (templateFilter.value !== 'all') params.template = templateFilter.value
    const result = await api.listWorkflows(params)
    workflows.value = result.data || []
  } catch {
    workflows.value = []
  } finally {
    loading.value = false
  }
}

async function loadTasks() {
  try {
    const result = await api.listWorkflowTasks({ limit: 100 })
    tasks.value = result.data || []
  } catch { tasks.value = [] }
}

async function loadSchedules() {
  try {
    const result = await api.listScheduledTasks()
    schedules.value = result.data || []
  } catch { schedules.value = [] }
}

async function loadAll() {
  await Promise.all([loadSummary(), loadWorkflows(), loadTasks(), loadSchedules()])
  if (!hostGroups.value.length) {
    api.listGroups().then(r => { hostGroups.value = r.data || [] }).catch(() => {})
  }
}

// 按节点名称推断类型 → 对应后端真实执行器（workflow_engine）
const NODE_TYPE_RULES = [
  { type: 'metrics', re: /(指标|采集|metrics|cpu|内存)/i },
  { type: 'log', re: /(日志|log)/i },
  { type: 'agent', re: /(诊断|分析|ai|智能|根因)/i },
  { type: 'approval', re: /(审批|确认|approve)/i },
  { type: 'check', re: /(检查|验证|健康|check|探活)/i },
  { type: 'notify', re: /(通知|播报|推送|飞书|notify)/i },
  { type: 'report', re: /(报告|沉淀|总结|report)/i },
  { type: 'action', re: /(执行|处置|修复|重启|清理)/i },
]

function inferNodeType(label, index, total) {
  if (index === 0) return 'trigger'
  for (const rule of NODE_TYPE_RULES) {
    if (rule.re.test(label)) return rule.type
  }
  return index === total - 1 ? 'report' : 'action'
}

function graphFromLines(text) {
  const labels = String(text || '').split('\n').map(item => item.trim()).filter(Boolean)
  const nodes = labels.map((label, index) => ({ id: `n${index + 1}`, type: inferNodeType(label, index, labels.length), label }))
  const edges = nodes.slice(1).map((node, index) => ({ source: nodes[index].id, target: node.id }))
  return { nodes, edges }
}

function linesFromNodes(nodes) {
  return (nodes || []).map(node => node.label || node.id).join('\n')
}

function openCreateWorkflow() {
  editingWorkflowId.value = ''
  Object.assign(workflowForm, {
    name: '',
    description: '',
    tagsStr: '',
    trigger_type: 'manual',
    status: 'enabled',
    is_template: false,
    nodeLines: '触发\n采集指标\nAI 诊断\n审批\n执行处置\n通知值班',
    actionCommand: '',
    actionHostGroup: '',
  })
  formError.value = ''
  showWorkflowForm.value = true
}

function openEditWorkflow(workflow) {
  editingWorkflowId.value = workflow.id
  const cfg = workflow.agent_configs || {}
  Object.assign(workflowForm, {
    name: workflow.name || '',
    description: workflow.description || '',
    tagsStr: (workflow.tags || []).join(', '),
    trigger_type: workflow.trigger_type || 'manual',
    status: workflow.status || 'enabled',
    is_template: !!workflow.is_template,
    nodeLines: linesFromNodes(workflow.nodes),
    actionCommand: cfg.action_command || '',
    actionHostGroup: cfg.action_host_group || '',
  })
  formError.value = ''
  showWorkflowForm.value = true
}

async function saveWorkflow() {
  if (!workflowForm.name.trim()) {
    formError.value = '请填写工作流名称'
    return
  }
  const graph = graphFromLines(workflowForm.nodeLines)
  if (!graph.nodes.length) {
    formError.value = '至少需要一个节点'
    return
  }
  savingWorkflow.value = true
  try {
    const payload = {
      name: workflowForm.name.trim(),
      description: workflowForm.description,
      tags: workflowForm.tagsStr.split(',').map(item => item.trim()).filter(Boolean),
      trigger_type: workflowForm.trigger_type,
      status: workflowForm.status,
      is_template: workflowForm.is_template ? 1 : 0,
      nodes: graph.nodes,
      edges: graph.edges,
      agent_configs: {
        action_command: workflowForm.actionCommand.trim(),
        action_host_group: workflowForm.actionHostGroup,
      },
    }
    if (editingWorkflowId.value) await api.updateWorkflow(editingWorkflowId.value, payload)
    else await api.createWorkflow(payload)
    showWorkflowForm.value = false
    await loadAll()
  } catch (error) {
    formError.value = String(error)
  } finally {
    savingWorkflow.value = false
  }
}

async function duplicate(workflow) {
  const payload = {
    ...workflow,
    name: `${workflow.name} 副本`,
    is_template: 0,
  }
  delete payload.id
  delete payload.created_at
  delete payload.updated_at
  await api.createWorkflow(payload)
  await loadAll()
}

async function removeWorkflow(workflow) {
  if (!window.confirm(`删除工作流「${workflow.name}」？`)) return
  await api.deleteWorkflow(workflow.id)
  await loadAll()
}

async function run(workflow) {
  if (!window.confirm(`立即执行工作流「${workflow.name}」？将真实调用指标/日志/AI/通知等能力。`)) return
  const result = await api.runWorkflow(workflow.id, {
    name: `手动执行 - ${workflow.name}`,
    input: '',
    context: { source: 'workflow-ui' },
  })
  detailTask.value = result.data
  activeTab.value = 'tasks'
  await Promise.all([loadSummary(), loadTasks()])
}

// ── 运行中任务轮询：刷新任务列表 + 打开的详情 ────────────────────────────
let taskPollTimer = null

async function pollRunning() {
  const hasRunning = tasks.value.some(t => t.status === 'running')
    || detailTask.value?.status === 'running'
  if (!hasRunning) return
  await loadTasks()
  if (detailTask.value?.id) {
    try {
      const result = await api.getWorkflowTask(detailTask.value.id)
      if (result?.data) detailTask.value = result.data
    } catch { /* ignore */ }
  }
}

async function cancelTask(task) {
  await api.cancelWorkflowTask(task.id)
  await Promise.all([loadSummary(), loadTasks()])
}

function openCreateSchedule() {
  editingScheduleId.value = ''
  Object.assign(scheduleForm, {
    name: '',
    description: '',
    workflow_id: workflows.value[0]?.id || '',
    cron_expression: '0 9 * * *',
    enabled: true,
  })
  showScheduleForm.value = true
}

function openEditSchedule(schedule) {
  editingScheduleId.value = schedule.id
  Object.assign(scheduleForm, {
    name: schedule.name || '',
    description: schedule.description || '',
    workflow_id: schedule.workflow_id || '',
    cron_expression: schedule.cron_expression || '0 9 * * *',
    enabled: !!schedule.enabled,
  })
  showScheduleForm.value = true
}

async function saveSchedule() {
  if (!scheduleForm.name.trim() || !scheduleForm.workflow_id) return
  const payload = { ...scheduleForm, name: scheduleForm.name.trim() }
  if (editingScheduleId.value) await api.updateScheduledTask(editingScheduleId.value, payload)
  else await api.createScheduledTask(payload)
  showScheduleForm.value = false
  await Promise.all([loadSummary(), loadSchedules()])
}

async function toggleSchedule(schedule) {
  await api.toggleScheduledTask(schedule.id)
  await Promise.all([loadSummary(), loadSchedules()])
}

async function removeSchedule(schedule) {
  if (!window.confirm(`删除定时任务「${schedule.name}」？`)) return
  await api.deleteScheduledTask(schedule.id)
  await Promise.all([loadSummary(), loadSchedules()])
}

onMounted(() => {
  loadAll()
  taskPollTimer = setInterval(pollRunning, 2500)
})

onBeforeUnmount(() => {
  if (taskPollTimer) clearInterval(taskPollTimer)
})
</script>

<style scoped>
.wf-page { height: 100%; overflow-y: auto; padding: 20px 24px; background: var(--bg-base); color: var(--text-primary); }
.wf-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.wf-title { margin: 0; font-size: 20px; font-weight: 700; }
.wf-sub { margin: 5px 0 0; color: var(--text-muted); font-size: 12px; }
.wf-actions, .card-actions, .modal-foot { display: flex; gap: 8px; align-items: center; }
.btn { border: 1px solid var(--border); background: var(--bg-card); color: var(--text-primary); padding: 7px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }
.btn:hover { border-color: var(--accent); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.btn-outline { background: transparent; }
.btn-danger { color: var(--error, #f85149); border-color: rgba(248,81,73,.35); background: transparent; }
.btn-xs { padding: 4px 8px; font-size: 11px; }
.wf-kpis { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin-bottom: 14px; }
.kpi { border: 1px solid var(--border); background: var(--bg-card); border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 4px; }
.kpi b { font-size: 24px; color: var(--accent); }
.kpi span { font-size: 12px; color: var(--text-muted); }
.wf-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }
.wf-tabs button { border: none; background: transparent; color: var(--text-muted); padding: 10px 14px; cursor: pointer; border-bottom: 2px solid transparent; }
.wf-tabs button.active { color: var(--text-primary); border-bottom-color: var(--accent); font-weight: 700; }
.wf-section { min-height: 320px; }
.wf-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.search { flex: 1; }
input, textarea, select { width: 100%; border: 1px solid var(--border); background: var(--bg-card); color: var(--text-primary); border-radius: 6px; padding: 8px 10px; box-sizing: border-box; font: inherit; }
textarea { resize: vertical; }
.workflow-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.workflow-card { border: 1px solid var(--border); background: var(--bg-card); border-radius: 8px; padding: 14px; display: flex; flex-direction: column; gap: 10px; min-height: 230px; }
.card-top, .meta-row { display: flex; align-items: center; gap: 8px; }
.card-top { justify-content: space-between; }
.workflow-card h3 { margin: 0; font-size: 15px; }
.workflow-card p { margin: 0; color: var(--text-muted); font-size: 12px; line-height: 1.5; min-height: 36px; }
.badge, .state, .status { display: inline-flex; align-items: center; padding: 2px 7px; border-radius: 999px; font-size: 11px; border: 1px solid transparent; }
.badge.tpl { color: #38bdf8; border-color: rgba(56,189,248,.35); background: rgba(56,189,248,.1); }
.badge.custom { color: #a78bfa; border-color: rgba(167,139,250,.35); background: rgba(167,139,250,.1); }
.state.enabled, .status.success { color: #22c55e; border-color: rgba(34,197,94,.35); background: rgba(34,197,94,.1); }
.state.disabled, .status.paused, .status.cancelled { color: var(--text-muted); border-color: var(--border); background: rgba(148,163,184,.08); }
.status.failed { color: var(--error); border-color: rgba(248,81,73,.35); background: rgba(248,81,73,.08); }
.status.running { color: #fbbf24; border-color: rgba(251,191,36,.35); background: rgba(251,191,36,.08); }
.tags { display: flex; flex-wrap: wrap; gap: 6px; min-height: 22px; }
.tags span { font-size: 11px; color: var(--accent); background: rgba(56,139,253,.08); border: 1px solid rgba(56,139,253,.16); border-radius: 999px; padding: 2px 7px; }
.meta-row { color: var(--text-muted); font-size: 11px; }
.node-strip { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
.node-strip span { font-size: 11px; border: 1px solid var(--border); border-radius: 5px; padding: 4px 6px; color: var(--text-secondary); }
.empty { min-height: 180px; display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center; color: var(--text-muted); border: 1px dashed var(--border); border-radius: 8px; }
.empty.small { min-height: 80px; }
.wf-table { width: 100%; border-collapse: collapse; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; font-size: 12px; }
.wf-table th, .wf-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; }
.wf-table th { color: var(--text-muted); font-weight: 600; background: rgba(255,255,255,.02); }
.wf-table tbody tr { cursor: pointer; }
.wf-table tbody tr:hover { background: var(--sidebar-hover, rgba(255,255,255,.04)); }
.mono { font-family: 'Cascadia Code', Consolas, monospace; }
.modal-mask, .drawer-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 50; display: flex; align-items: center; justify-content: center; }
.modal { width: min(680px, calc(100vw - 32px)); max-height: calc(100vh - 48px); overflow: hidden; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 18px 50px rgba(0,0,0,.35); display: flex; flex-direction: column; }
.modal-sm { width: min(520px, calc(100vw - 32px)); }
.modal-head, .drawer-head { display: flex; align-items: center; justify-content: space-between; padding: 14px 16px; border-bottom: 1px solid var(--border); font-weight: 700; }
.modal-head button, .drawer-head button { background: none; border: none; color: var(--text-muted); font-size: 20px; cursor: pointer; }
.modal-body { padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
.modal-body label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--text-muted); }
.modal-body label span { font-weight: 600; color: var(--text-secondary); }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.check-line { flex-direction: row !important; align-items: center; color: var(--text-primary) !important; }
.check-line input { width: auto; }
.form-error { color: var(--error); font-size: 12px; }
.modal-foot { padding: 14px 16px; border-top: 1px solid var(--border); }
.drawer-mask { align-items: stretch; justify-content: flex-end; }
.drawer { width: min(520px, 100vw); background: var(--bg-card); border-left: 1px solid var(--border); overflow-y: auto; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 16px; }
.detail-grid div { border: 1px solid var(--border); border-radius: 6px; padding: 10px; display: flex; flex-direction: column; gap: 4px; }
.detail-grid span { color: var(--text-muted); font-size: 11px; }
.drawer-section { padding: 12px 16px 8px; color: var(--text-secondary); font-size: 12px; font-weight: 700; }
.log-row { display: grid; grid-template-columns: 58px 1fr; gap: 8px; margin: 8px 16px; padding: 9px 10px; border: 1px solid var(--border); border-radius: 6px; }
.log-row span { font-size: 11px; color: var(--accent); text-transform: uppercase; }
.log-row p { margin: 0; font-size: 12px; color: var(--text-primary); }
.json-pre { margin: 8px 16px 18px; padding: 12px; background: rgba(0,0,0,.18); border: 1px solid var(--border); border-radius: 6px; color: var(--text-secondary); font-size: 12px; white-space: pre-wrap; }
.node-result { margin: 8px 16px; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.node-result.failed { border-color: rgba(248, 81, 73, .4); }
.node-result-head { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: rgba(0,0,0,.12); }
.node-result-head b { flex: 1; font-size: 12px; color: var(--text-primary); }
.node-result-head em { font-style: normal; font-size: 11px; color: var(--text-muted); }
.node-result.failed .node-result-head em { color: var(--error); }
.node-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); flex-shrink: 0; }
.node-dot.failed { background: var(--error); }
.node-dot.running { background: var(--accent); animation: nodePulse 1s ease-in-out infinite; }
.node-result pre { margin: 0; padding: 10px; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; color: var(--text-secondary); max-height: 220px; overflow: auto; }
@keyframes nodePulse { 50% { opacity: .35; } }
@media (max-width: 760px) {
  .wf-head, .wf-toolbar { flex-direction: column; align-items: stretch; }
  .wf-kpis { grid-template-columns: repeat(2, 1fr); }
  .form-grid, .detail-grid { grid-template-columns: 1fr; }
}
</style>
