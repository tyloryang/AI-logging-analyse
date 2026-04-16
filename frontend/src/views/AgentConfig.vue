<template>
  <div class="page agent-config-page">

    <!-- Toast 提示 -->
    <Transition name="toast">
      <div v-if="toast" class="toast-msg">{{ toast }}</div>
    </Transition>

    <!-- ── 页头 ── -->
    <div class="page-header">
      <div>
        <h1>
          <span class="brand-prefix">AIOps</span>
          <span class="separator"> | </span>
          智能体配置
        </h1>
        <p class="subtitle">在这里设置你的智能体，MCP、Skill，模型市场让 AI 变成超能力</p>
      </div>
      <button class="btn btn-primary save-btn" @click="saveConfig" :disabled="saving">
        <span v-if="saving" class="spinner-sm-dark"></span>
        <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
        {{ saving ? '保存中...' : '保存配置' }}
      </button>
    </div>

    <!-- ── 顶部统计 ── -->
    <div class="stats-bar">
      <div class="stat-item">
        <div class="stat-num">{{ stats.models }}</div>
        <div class="stat-lbl">模型接入数</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-num">{{ stats.mcps }}</div>
        <div class="stat-lbl">配置的 MCP</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-num">{{ stats.skills }}</div>
        <div class="stat-lbl">配置的 Skill</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-num">{{ stats.sa }}</div>
        <div class="stat-lbl">对话的 SA</div>
      </div>
      <div class="stat-divider"></div>
      <div class="stat-item">
        <div class="stat-num" :class="{ 'stat-zero': !stats.actions }">{{ stats.actions }}</div>
        <div class="stat-lbl">行动金额</div>
      </div>
    </div>

    <!-- ── 标签页 ── -->
    <div class="tabs-bar">
      <button
        v-for="tab in TABS" :key="tab.key"
        class="tab-btn" :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >{{ tab.label }}</button>
    </div>

    <!-- ── 基础配置 ── -->
    <div v-if="activeTab === 'basic'" class="tab-content basic-layout">

      <!-- 左侧表单 -->
      <div class="basic-form card">
        <div class="form-section">
          <label class="form-label">助手名称</label>
          <input v-model="config.name" class="form-input" placeholder="例如：SxDevOps 智能运维助手" />
        </div>

        <div class="form-section">
          <label class="form-label">角色定义 <span class="form-hint">（System Prompt 的核心身份描述）</span></label>
          <textarea v-model="config.definition" class="form-textarea" rows="3"
            placeholder="例如：你是一名资深 SRE 工程师，负责保障平台稳定性..."></textarea>
        </div>

        <div class="form-section">
          <label class="form-label">MCP 能力说明 <span class="form-hint">（告知 AI 可用哪些 MCP 工具）</span></label>
          <textarea v-model="config.mcp_desc" class="form-textarea" rows="3"
            placeholder="例如：你可以通过下方的 MCP 与 Redis、Nacos 通信，获取业务数据..."></textarea>
        </div>

        <div class="form-section">
          <label class="form-label">Skill 能力说明 <span class="form-hint">（告知 AI 可调用哪些自动化能力）</span></label>
          <textarea v-model="config.skill_desc" class="form-textarea" rows="3"
            placeholder="例如：还可以通过调用 Skill 完成自动化巡检 order-service 等能力..."></textarea>
        </div>

        <div class="form-section form-row">
          <label class="form-label">Skill 执行模式</label>
          <div class="radio-group">
            <label class="radio-item" v-for="opt in SKILL_MODES" :key="opt.value">
              <input type="radio" v-model="config.skill_mode" :value="opt.value" />
              <span>{{ opt.label }}</span>
            </label>
          </div>
        </div>
      </div>

      <!-- 右侧：行为与表现 -->
      <div class="behavior-panel card">
        <div class="behavior-title">行为与表现</div>

        <div class="toggle-list">
          <div class="toggle-item" v-for="b in behaviors" :key="b.key">
            <div class="toggle-info">
              <div class="toggle-name">{{ b.name }}</div>
              <div class="toggle-desc">{{ b.desc }}</div>
            </div>
            <button
              class="toggle-switch" :class="{ on: b.enabled }"
              @click="b.enabled = !b.enabled"
            >
              <span class="toggle-thumb"></span>
            </button>
          </div>
        </div>

        <!-- 模型选择 -->
        <div class="model-section">
          <div class="behavior-title" style="margin-top:20px;">当前模型</div>
          <div class="model-card" v-for="m in configModels" :key="m.id"
               :class="{ 'model-active': m.active }" @click="selectModel(m)">
            <div class="model-icon">🤖</div>
            <div class="model-info">
              <div class="model-name">{{ m.name }}</div>
              <div class="model-tag">{{ m.provider }}</div>
            </div>
            <span v-if="m.active" class="model-check">✓</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── MCP 配置 ── -->
    <div v-if="activeTab === 'mcp'" class="tab-content">
      <div class="card">
        <div class="section-toolbar">
          <span class="section-count">已配置 {{ mcpList.length }} 个 MCP</span>
          <button class="btn btn-outline btn-sm" @click="showAddMcp = !showAddMcp">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            添加 MCP
          </button>
        </div>
        <!-- 添加 MCP 表单 -->
        <div v-if="showAddMcp" class="add-form">
          <input v-model="newMcp.name" class="form-input" placeholder="名称，如：Redis MCP" style="flex:1" />
          <select v-model="newMcp.type" class="form-input" style="width:90px">
            <option value="http">HTTP</option>
            <option value="stdio">Stdio</option>
          </select>
          <input v-model="newMcp.url" class="form-input" placeholder="地址，如：localhost:6379" style="flex:2" />
          <button class="btn btn-primary btn-sm" @click="addMcp">确认添加</button>
          <button class="btn btn-outline btn-sm" @click="showAddMcp = false">取消</button>
        </div>
        <table>
          <thead>
            <tr>
              <th>名称</th><th>类型</th><th>地址</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in mcpList" :key="m.id">
              <td><strong>{{ m.name }}</strong></td>
              <td><span class="badge badge-info">{{ m.type }}</span></td>
              <td class="mono" style="font-size:12px;">{{ m.url }}</td>
              <td>
                <span class="status-dot" :class="m.ok ? 'ok' : 'err'"></span>
                {{ m.ok ? '正常' : '离线' }}
              </td>
              <td>
                <button class="action-link" @click="removeMcp(m.id)">删除</button>
              </td>
            </tr>
            <tr v-if="!mcpList.length">
              <td colspan="5" class="empty-cell">暂无 MCP 配置，点击「添加 MCP」开始</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── Skill 配置 ── -->
    <div v-if="activeTab === 'skill'" class="tab-content">
      <div class="card">
        <div class="section-toolbar">
          <span class="section-count">已启用 {{ skillList.filter(s=>s.enabled).length }} / {{ skillList.length }} 个 Skill</span>
          <button class="btn btn-outline btn-sm">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            导入 Skill
          </button>
        </div>
        <div class="skill-grid">
          <div class="skill-card card" v-for="s in skillList" :key="s.id" :class="{ 'skill-on': s.enabled }">
            <div class="skill-header">
              <span class="skill-icon">{{ s.icon }}</span>
              <span class="skill-name">{{ s.name }}</span>
              <button class="toggle-switch sm" :class="{ on: s.enabled }" @click="s.enabled = !s.enabled; toggleSkill(s)">
                <span class="toggle-thumb"></span>
              </button>
            </div>
            <div class="skill-desc">{{ s.desc }}</div>
            <div class="skill-tags">
              <span class="skill-tag" v-for="t in s.tags" :key="t">{{ t }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 模型市场 ── -->
    <div v-if="activeTab === 'models'" class="tab-content">
      <div class="model-market">
        <div class="market-card card" v-for="m in marketModels" :key="m.id">
          <div class="market-header">
            <span class="market-logo">{{ m.logo }}</span>
            <div>
              <div class="market-name">{{ m.name }}</div>
              <div class="market-provider">{{ m.provider }}</div>
            </div>
            <button
              class="btn btn-sm"
              :class="m.connected ? 'btn-outline' : 'btn-primary'"
              @click="toggleModel(m)"
            >{{ m.connected ? '已接入' : '接入' }}</button>
          </div>
          <div class="market-desc">{{ m.desc }}</div>
          <div class="market-tags">
            <span class="skill-tag" v-for="t in m.tags" :key="t">{{ t }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ── SA 接入 ── -->
    <div v-if="activeTab === 'sa'" class="tab-content">
      <div class="card">
        <div class="section-toolbar">
          <span class="section-count">已接入 {{ saList.filter(s=>s.active).length }} / {{ saList.length }} 个 SA</span>
          <button class="btn btn-outline btn-sm" @click="showAddSa = !showAddSa">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            接入 SA
          </button>
        </div>
        <div v-if="showAddSa" class="add-form">
          <input v-model="newSa.name" class="form-input" placeholder="SA 名称" style="flex:1" />
          <input v-model="newSa.endpoint" class="form-input" placeholder="接口地址" style="flex:2" />
          <input v-model="newSa.token" class="form-input" placeholder="鉴权 Token（可选）" style="flex:2" />
          <button class="btn btn-primary btn-sm" @click="addSa">确认接入</button>
          <button class="btn btn-outline btn-sm" @click="showAddSa = false">取消</button>
        </div>
        <table>
          <thead>
            <tr><th>SA 名称</th><th>接口地址</th><th>状态</th><th>对话数</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="s in saList" :key="s.id">
              <td><strong>{{ s.name }}</strong></td>
              <td class="mono" style="font-size:12px">{{ s.endpoint }}</td>
              <td>
                <span class="status-dot" :class="s.active ? 'ok' : 'err'"></span>
                {{ s.active ? '活跃' : '停用' }}
              </td>
              <td class="mono">{{ s.conversations || 0 }}</td>
              <td>
                <button class="action-link" style="color:var(--warning)" @click="toggleSa(s)">
                  {{ s.active ? '停用' : '启用' }}
                </button>
                <button class="action-link" @click="removeSa(s.id)">删除</button>
              </td>
            </tr>
            <tr v-if="!saList.length">
              <td colspan="5" class="empty-cell">暂无 SA 接入配置</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── 其他 ── -->
    <div v-if="activeTab === 'other'" class="tab-content">
      <div class="card" style="max-width:600px">
        <div class="form-section">
          <label class="form-label">最大对话轮次</label>
          <input v-model.number="config.max_turns" type="number" class="form-input" style="width:120px" min="1" max="50" />
        </div>
        <div class="form-section form-row">
          <label class="form-label">流式输出</label>
          <button class="toggle-switch" :class="{ on: config.stream }" @click="config.stream = !config.stream">
            <span class="toggle-thumb"></span>
          </button>
        </div>
        <div class="form-section">
          <label class="form-label">执行确认模式</label>
          <div class="radio-group">
            <label class="radio-item"><input type="radio" v-model="config.confirm_mode" value="auto" /> 自动执行</label>
            <label class="radio-item"><input type="radio" v-model="config.confirm_mode" value="ask" /> 每次确认</label>
            <label class="radio-item"><input type="radio" v-model="config.confirm_mode" value="dry" /> 仅预览</label>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'

const TABS = [
  { key: 'basic',  label: '基础配置' },
  { key: 'mcp',    label: 'MCP' },
  { key: 'skill',  label: 'Skill' },
  { key: 'sa',     label: 'SA 接入' },
  { key: 'models', label: '模型市场' },
  { key: 'other',  label: '其他' },
]
const SKILL_MODES = [
  { value: 'auto',    label: '自动执行' },
  { value: 'confirm', label: '执行前确认' },
  { value: 'dry',     label: '仅限预览' },
]
const activeTab = ref('basic')
const saving    = ref(false)
const toast     = ref('')

// ── API 辅助 ─────────────────────────────────────────────────────────
async function apiFetch(url, opts = {}) {
  const resp = await fetch(url, { credentials: 'include', ...opts })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

function showToast(msg, ms = 2000) {
  toast.value = msg
  setTimeout(() => { toast.value = '' }, ms)
}

// ── 统计 ─────────────────────────────────────────────────────────────
const stats = reactive({ models: 0, mcps: 0, skills: 0, sa: 0, actions: 0 })

async function loadStats() {
  try {
    const d = await apiFetch('/api/agent-config/stats')
    Object.assign(stats, d)
  } catch { /* ignore */ }
}

// ── 基础配置 ─────────────────────────────────────────────────────────
const config = reactive({
  name: '', definition: '', mcp_desc: '', skill_desc: '',
  skill_mode: 'confirm', max_turns: 20, stream: true, confirm_mode: 'ask',
})
const configModels = ref([])

async function loadBasic() {
  try {
    const d = await apiFetch('/api/agent-config')
    const b = d.basic || {}
    Object.assign(config, {
      name:         b.name        || '',
      definition:   b.definition  || '',
      mcp_desc:     b.mcp_desc    || '',
      skill_desc:   b.skill_desc  || '',
      skill_mode:   b.skill_mode  || 'confirm',
      max_turns:    b.max_turns   ?? 20,
      stream:       b.stream      ?? true,
      confirm_mode: b.confirm_mode || 'ask',
    })
    configModels.value = d.models || []
  } catch { /* ignore */ }
}

async function saveConfig() {
  saving.value = true
  try {
    await apiFetch('/api/agent-config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name:         config.name,
        definition:   config.definition,
        mcp_desc:     config.mcp_desc,
        skill_desc:   config.skill_desc,
        skill_mode:   config.skill_mode,
        max_turns:    config.max_turns,
        stream:       config.stream,
        confirm_mode: config.confirm_mode,
      }),
    })
    // 保存行为开关
    await apiFetch('/api/agent-config/behaviors', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ behaviors: behaviors.map(b => ({ key: b.key, enabled: b.enabled })) }),
    })
    showToast('✓ 配置已保存')
    await loadStats()
  } catch (e) {
    showToast(`❌ 保存失败：${e.message}`)
  } finally {
    saving.value = false
  }
}

function selectModel(m) {
  configModels.value.forEach(x => x.active = false)
  m.active = true
  apiFetch('/api/agent-config/models/active', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_id: m.id }),
  }).catch(() => {})
}

// ── 行为开关 ─────────────────────────────────────────────────────────
const behaviors = ref([])

async function loadBehaviors() {
  try {
    const d = await apiFetch('/api/agent-config/behaviors')
    behaviors.value = d.data || []
  } catch { /* ignore */ }
}

// ── MCP ──────────────────────────────────────────────────────────────
const mcpList = ref([])

async function loadMcps() {
  try {
    const d = await apiFetch('/api/agent-config/mcps')
    mcpList.value = d.data || []
  } catch { /* ignore */ }
}

const showAddMcp = ref(false)
const newMcp = reactive({ name: '', type: 'http', url: '' })

async function addMcp() {
  if (!newMcp.name || !newMcp.url) return
  try {
    const created = await apiFetch('/api/agent-config/mcps', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...newMcp }),
    })
    mcpList.value.push(created)
    newMcp.name = ''; newMcp.url = ''; newMcp.type = 'http'
    showAddMcp.value = false
    await loadStats()
    showToast('✓ MCP 已添加')
  } catch (e) {
    showToast(`❌ 添加失败：${e.message}`)
  }
}

async function removeMcp(id) {
  if (!confirm('确认删除该 MCP？')) return
  try {
    await apiFetch(`/api/agent-config/mcps/${id}`, { method: 'DELETE' })
    mcpList.value = mcpList.value.filter(m => m.id !== id)
    await loadStats()
    showToast('✓ 已删除')
  } catch (e) {
    showToast(`❌ 删除失败：${e.message}`)
  }
}

async function toggleMcp(m) {
  try {
    await apiFetch(`/api/agent-config/mcps/${m.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: m.enabled }),
    })
  } catch { m.enabled = !m.enabled }
}

// ── Skill ─────────────────────────────────────────────────────────────
const skillList = ref([])

async function loadSkills() {
  try {
    const d = await apiFetch('/api/agent-config/skills')
    skillList.value = d.data || []
  } catch { /* ignore */ }
}

async function toggleSkill(s) {
  try {
    await apiFetch(`/api/agent-config/skills/${s.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: s.enabled }),
    })
    await loadStats()
  } catch { s.enabled = !s.enabled }
}

// ── 模型市场（静态数据 + 接入状态从 backend 读取） ────────────────────
const marketModels = ref([
  { id: 'claude-opus',   logo: '🤖', name: 'Claude Opus 4.6',   provider: 'Anthropic', connected: false, desc: '最强推理能力，支持长上下文与工具调用，适合复杂根因分析场景。', tags: ['推理强', '工具调用', '128k'] },
  { id: 'claude-sonnet', logo: '🤖', name: 'Claude Sonnet 4.6', provider: 'Anthropic', connected: false, desc: '高性价比，速度与能力均衡，适合日常智能助手场景。',             tags: ['均衡', '快速', '200k'] },
  { id: 'qwen3-32b',     logo: '🔮', name: 'Qwen3-32B',          provider: 'Local',     connected: false, desc: '开源本地部署，无需外网，数据不出域，适合企业私有化部署。',     tags: ['本地', '开源', '私有化'] },
  { id: 'gpt4o',         logo: '🌐', name: 'GPT-4o',             provider: 'OpenAI',    connected: false, desc: '多模态能力，支持图像理解，适合需要视觉分析的运维场景。',         tags: ['多模态', '图像', '128k'] },
])

async function loadMarketStatus() {
  try {
    const d = await apiFetch('/api/agent-config/models')
    const activeIds = new Set((d.data || []).filter(m => m.active).map(m => m.id))
    marketModels.value.forEach(m => { m.connected = activeIds.has(m.id) })
  } catch { /* ignore */ }
}

async function toggleModel(m) {
  m.connected = !m.connected
  try {
    if (m.connected) {
      await apiFetch('/api/agent-config/models/active', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: m.id }),
      })
    }
    await loadStats()
  } catch { m.connected = !m.connected }
}

// ── SA 接入管理 ───────────────────────────────────────────────────────
const saList = ref([])
const showAddSa = ref(false)
const newSa = reactive({ name: '', endpoint: '', token: '' })

async function loadSa() {
  try {
    const d = await apiFetch('/api/agent-config/sa')
    saList.value = d.data || []
  } catch { /* ignore */ }
}

async function addSa() {
  if (!newSa.name || !newSa.endpoint) return
  try {
    const created = await apiFetch('/api/agent-config/sa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newSa.name, endpoint: newSa.endpoint, token: newSa.token }),
    })
    saList.value.push(created)
    newSa.name = ''; newSa.endpoint = ''; newSa.token = ''
    showAddSa.value = false
    await loadStats()
    showToast('✓ SA 已接入')
  } catch (e) {
    showToast(`❌ 接入失败：${e.message}`)
  }
}

async function toggleSa(s) {
  const next = !s.active
  try {
    await apiFetch(`/api/agent-config/sa/${s.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: next }),
    })
    s.active = next
    await loadStats()
  } catch (e) {
    showToast(`❌ 操作失败：${e.message}`)
  }
}

async function removeSa(id) {
  if (!confirm('确认删除该 SA？')) return
  try {
    await apiFetch(`/api/agent-config/sa/${id}`, { method: 'DELETE' })
    saList.value = saList.value.filter(s => s.id !== id)
    await loadStats()
    showToast('✓ 已删除')
  } catch (e) {
    showToast(`❌ 删除失败：${e.message}`)
  }
}

// ── 初始化 ────────────────────────────────────────────────────────────
onMounted(async () => {
  await Promise.all([loadBasic(), loadBehaviors(), loadMcps(), loadSkills(), loadMarketStatus(), loadSa(), loadStats()])
})
</script>

<style scoped>
.agent-config-page { padding: 20px 24px; height: 100%; overflow-y: auto; }

/* ── 页头 ── */
.page-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 18px;
}
.page-header h1 {
  font-size: 16px; font-weight: 600; color: var(--text-primary);
  display: flex; align-items: center; gap: 4px;
}
.brand-prefix { color: var(--accent); }
.separator { color: var(--text-muted); }
.subtitle { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.save-btn { gap: 6px; }

/* ── Stats bar ── */
.stats-bar {
  display: flex; align-items: center;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 14px 28px; gap: 0;
  margin-bottom: 18px;
  box-shadow: var(--shadow-sm);
}
.stat-item { flex: 1; text-align: center; }
.stat-num {
  font-size: 26px; font-weight: 700;
  color: var(--accent);
  font-family: 'JetBrains Mono', monospace;
  line-height: 1.1;
}
.stat-zero { color: var(--text-muted); }
.stat-lbl { font-size: 12px; color: var(--text-secondary); margin-top: 3px; }
.stat-divider { width: 1px; background: var(--border); align-self: stretch; margin: 0 4px; }

/* ── Tabs ── */
.tabs-bar {
  display: flex; gap: 2px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 18px;
}
.tab-btn {
  padding: 8px 18px; font-size: 13px;
  border: none; background: none; cursor: pointer;
  color: var(--text-secondary);
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  font-family: inherit;
  transition: color .12s, border-color .12s;
}
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 500;
}

/* ── Tab content ── */
.tab-content { animation: fadeIn .15s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; } }

/* ── Basic layout ── */
.basic-layout { display: grid; grid-template-columns: 1fr 300px; gap: 16px; }

.basic-form { display: flex; flex-direction: column; gap: 18px; }

.form-section { display: flex; flex-direction: column; gap: 6px; }
.form-section.form-row { flex-direction: row; align-items: center; justify-content: space-between; }
.form-label { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.form-hint { font-weight: 400; color: var(--text-muted); font-size: 11px; }
.form-input {
  width: 100%; padding: 7px 10px;
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: var(--radius); color: var(--text-primary); font-size: 13px;
  font-family: inherit;
}
.form-input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }
.form-textarea {
  width: 100%; padding: 8px 10px; resize: vertical;
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: var(--radius); color: var(--text-primary); font-size: 13px;
  font-family: inherit; line-height: 1.6;
}
.form-textarea:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }

.radio-group { display: flex; gap: 16px; }
.radio-item { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-secondary); cursor: pointer; }
.radio-item input { accent-color: var(--accent); }

/* ── Behavior panel ── */
.behavior-panel { }
.behavior-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 12px; }

.toggle-list { display: flex; flex-direction: column; gap: 14px; }
.toggle-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.toggle-info { flex: 1; }
.toggle-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.toggle-desc { font-size: 11px; color: var(--text-muted); margin-top: 2px; line-height: 1.4; }

/* Toggle switch */
.toggle-switch {
  width: 36px; height: 20px; border-radius: 10px;
  background: var(--border); border: none; cursor: pointer;
  position: relative; transition: background .2s; flex-shrink: 0;
  padding: 0;
}
.toggle-switch.on { background: var(--accent); }
.toggle-thumb {
  position: absolute; top: 2px; left: 2px;
  width: 16px; height: 16px; border-radius: 50%;
  background: #fff; transition: transform .2s;
  box-shadow: 0 1px 3px rgba(0,0,0,.3);
  display: block;
}
.toggle-switch.on .toggle-thumb { transform: translateX(16px); }
.toggle-switch.sm { width: 28px; height: 16px; }
.toggle-switch.sm .toggle-thumb { width: 12px; height: 12px; }
.toggle-switch.sm.on .toggle-thumb { transform: translateX(12px); }

/* Model selection */
.model-section { margin-top: 8px; }
.model-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; border-radius: var(--radius-card);
  border: 1px solid var(--border); cursor: pointer;
  margin-bottom: 8px; transition: border-color .12s, background .12s;
}
.model-card:hover { border-color: var(--accent); background: var(--accent-dim); }
.model-active { border-color: var(--accent) !important; background: var(--accent-dim) !important; }
.model-icon { font-size: 18px; }
.model-info { flex: 1; }
.model-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.model-tag { font-size: 11px; color: var(--text-muted); }
.model-check { color: var(--success); font-weight: 700; font-size: 15px; }

/* ── MCP/Skill table ── */
.section-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
}
.section-count { font-size: 12px; color: var(--text-secondary); }
.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }
.status-dot.ok { background: var(--success); }
.status-dot.err { background: var(--error); }
.action-link { background: none; border: none; color: var(--error); font-size: 12px; cursor: pointer; }
.action-link:hover { opacity: .75; }
.empty-cell { text-align: center; color: var(--text-muted); padding: 32px !important; font-size: 13px; }

/* ── Skill grid ── */
.skill-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 14px; }
.skill-card { padding: 14px 16px; opacity: .65; transition: opacity .15s, border-color .15s; }
.skill-card.skill-on { opacity: 1; border-color: var(--accent); }
.skill-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.skill-icon { font-size: 18px; }
.skill-name { flex: 1; font-size: 13px; font-weight: 600; color: var(--text-primary); }
.skill-desc { font-size: 12px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 8px; }
.skill-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.skill-tag { font-size: 10px; padding: 2px 7px; background: var(--accent-dim); color: var(--accent); border-radius: 3px; }

/* ── Model market ── */
.model-market { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
.market-card { padding: 16px; }
.market-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.market-logo { font-size: 22px; }
.market-name { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.market-provider { font-size: 11px; color: var(--text-muted); }
.market-desc { font-size: 12px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 10px; }
.market-tags { display: flex; gap: 4px; flex-wrap: wrap; }

/* ── 添加 MCP 表单 ── */
.add-form {
  display: flex; gap: 8px; align-items: center;
  padding: 10px 14px; margin-bottom: 10px;
  background: var(--bg-surface);
  border: 1px dashed var(--accent);
  border-radius: var(--radius-card);
  flex-wrap: wrap;
}

/* ── Toast 提示 ── */
.toast-msg {
  position: fixed; top: 20px; right: 24px; z-index: 9999;
  padding: 10px 20px; border-radius: 6px;
  background: var(--bg-card); border: 1px solid var(--border);
  font-size: 13px; color: var(--text-primary);
  box-shadow: var(--shadow-md);
}
.toast-enter-active, .toast-leave-active { transition: all .2s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-8px); }

/* ── Spinner ── */
.spinner-sm-dark {
  display: inline-block; width: 13px; height: 13px;
  border: 2px solid rgba(255,255,255,.3);
  border-top-color: #fff; border-radius: 50%;
  animation: spin .8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
