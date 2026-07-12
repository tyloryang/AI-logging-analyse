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
        <p class="subtitle">在这里统一配置智能体、MCP、Skills 和自定义模型，所有大模型参数都可按你的渠道独立维护</p>
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
          <input v-model="config.name" class="form-input" placeholder="例如：AIOps 智能运维助手" />
        </div>

        <div class="form-section">
          <div class="form-section-head">
            <label class="form-label">角色定义 <span class="form-hint">（System Prompt 的核心身份描述）</span></label>
            <div class="template-bar">
              <span class="template-label">快速模板</span>
              <button class="template-chip" v-for="t in ROLE_TEMPLATES" :key="t.key"
                @click="config.definition = t.text" :title="t.text.slice(0, 80) + '...'">{{ t.label }}</button>
            </div>
          </div>
          <textarea v-model="config.definition" class="form-textarea" rows="5"
            placeholder="建议包含 4 段：①身份（你是谁，资深 SRE / DBA / K8s 专家 / 只读分析师）  ②职责（守护稳定性 / 故障分析 / 配置审核）  ③工作原则（先调工具拿事实再下结论 / 高风险操作必经审批）  ④输出风格（结构化、用中文、给可执行步骤）"></textarea>
          <div class="form-meta">
            <span class="form-counter" :class="{ warn: (config.definition || '').length > 800 }">
              {{ (config.definition || '').length }} / 1500 字
            </span>
            <span class="form-tip">提示：长 prompt 会增加每轮 token 消耗，建议 ≤800 字</span>
          </div>
        </div>

        <div class="form-section">
          <label class="form-label">MCP 能力说明 <span class="form-hint">（告知 AI 可用哪些 MCP 工具）</span></label>
          <textarea v-model="config.mcp_desc" class="form-textarea" rows="3"
            placeholder="例如：你可以通过下方已配置的 MCP 与 Redis、Nacos、Prometheus 通信，获取业务配置和实时指标。"></textarea>
        </div>

        <div class="form-section">
          <div class="form-section-head">
            <label class="form-label">Skill 能力说明 <span class="form-hint">（告知 AI 可调用哪些自动化能力）</span></label>
            <div class="template-bar">
              <span class="template-label">快速模板</span>
              <button class="template-chip" v-for="t in SKILL_DESC_TEMPLATES" :key="t.key"
                @click="config.skill_desc = t.text" :title="t.text.slice(0, 80) + '...'">{{ t.label }}</button>
            </div>
          </div>
          <textarea v-model="config.skill_desc" class="form-textarea" rows="4"
            placeholder="建议按「能力类别」组织：①查询类（查日志/指标/Pod 状态）  ②诊断类（巡检主机/分析慢日志）  ③执行类（重启服务/滚动更新）。同时说明高风险动作的二次确认机制。"></textarea>
          <div class="form-meta">
            <span class="form-counter" :class="{ warn: (config.skill_desc || '').length > 600 }">
              {{ (config.skill_desc || '').length }} / 1000 字
            </span>
            <span class="form-tip">Skill 实际执行权限由「工具风险注册表」+ behaviors.auto 决定</span>
          </div>
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
          <select v-model="newMcp.type" class="form-input" style="width:150px">
            <option value="http">HTTP</option>
            <option value="sse">SSE</option>
            <option value="streamable_http">Streamable HTTP</option>
            <option value="stdio">Stdio</option>
          </select>
          <input v-model="newMcp.url" class="form-input" placeholder="地址，如：http://192.168.9.226:8000/sse" style="flex:2" />
          <button class="btn btn-primary btn-sm" @click="addMcp">确认添加</button>
          <button class="btn btn-outline btn-sm" @click="showAddMcp = false">取消</button>
        </div>
        <div v-if="editingMcpId" class="add-form add-form-edit">
          <span class="form-chip">编辑 MCP</span>
          <input v-model="editingMcp.name" class="form-input" placeholder="名称" style="flex:1" />
          <select v-model="editingMcp.type" class="form-input" style="width:150px">
            <option value="http">HTTP</option>
            <option value="sse">SSE</option>
            <option value="streamable_http">Streamable HTTP</option>
            <option value="stdio">Stdio</option>
          </select>
          <input v-model="editingMcp.url" class="form-input" placeholder="地址" style="flex:2" />
          <label class="inline-toggle">
            <span>启用</span>
            <button class="toggle-switch sm" type="button" :class="{ on: editingMcp.enabled }" @click="editingMcp.enabled = !editingMcp.enabled">
              <span class="toggle-thumb"></span>
            </button>
          </label>
          <button class="btn btn-primary btn-sm" @click="saveMcp">保存修改</button>
          <button class="btn btn-outline btn-sm" @click="cancelEditMcp">取消</button>
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
                <span class="mcp-enabled-tag" :class="{ off: !m.enabled }">{{ m.enabled ? '已启用' : '已停用' }}</span>
              </td>
              <td>
                <button class="action-link" style="color:var(--warning)" @click="toggleMcp(m)">{{ m.enabled ? '停用' : '启用' }}</button>
                <button class="action-link" style="color:var(--accent)" @click="startEditMcp(m)">编辑</button>
                <button class="action-link" style="color:var(--accent)" @click="pingMcp(m)">检测</button>
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
          <span class="section-count">
            已启用 {{ skillList.filter(s=>s.enabled).length }} / {{ skillList.length }} 个 Skill
            <span v-if="installedSkillCount" class="installed-count">已安装 {{ installedSkillCount }}</span>
            <span v-if="superpowersSkillCount" class="superpowers-count">⚡ Superpowers {{ superpowersSkillCount }}</span>
            <span v-if="githubHighStarSkillCount" class="github-count">★ GitHub 高星 {{ githubHighStarSkillCount }}</span>
          </span>
          <div class="section-toolbar-actions">
            <button class="btn btn-outline btn-sm" @click="showAddSkill = !showAddSkill" title="手动新增 Skill">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              新增
            </button>
            <button class="btn btn-outline btn-sm" @click="triggerImportSkills" title="从 JSON 文件导入">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              导入
            </button>
            <button class="btn btn-outline btn-sm" @click="exportSkills" :disabled="!skillList.length" title="导出全部 Skill 为 JSON">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              导出
            </button>
            <input ref="importSkillsInput" type="file" accept="application/json,.json" style="display:none" @change="onImportSkillsFile" />
          </div>
        </div>

        <!-- 导入结果汇总 -->
        <div v-if="importResult" class="import-result" :class="importResult.kind">
          <span>{{ importResult.text }}</span>
          <button class="import-result-close" @click="importResult = null">✕</button>
        </div>

        <!-- 新增 Skill 表单 -->
        <div v-if="showAddSkill" class="add-form add-form-edit">
          <span class="form-chip">新增 Skill</span>
          <input v-model="newSkill.icon" class="form-input" placeholder="图标" style="width:60px" maxlength="4" />
          <input v-model="newSkill.name" class="form-input" placeholder="Skill 名称，如：主机巡检" style="flex:1" />
          <input v-model="newSkill.desc" class="form-input" placeholder="说明，如：自动巡检所有主机 CPU/内存/磁盘" style="flex:2" />
          <select v-model="newSkill.tool_name" class="form-input" style="width:200px" :title="selectedToolHint">
            <option value="">未绑定工具</option>
            <option v-for="t in availableTools" :key="t.name" :value="t.name">
              {{ t.name }} · {{ riskLabel(t.risk) }}
            </option>
          </select>
          <input v-model="newSkillTagsInput" class="form-input" placeholder="标签（逗号分隔）" style="width:180px" />
          <button class="btn btn-primary btn-sm" @click="addSkill">确认</button>
          <button class="btn btn-outline btn-sm" @click="cancelAddSkill">取消</button>
        </div>

        <div class="skill-grid">
          <div class="skill-card card" v-for="s in skillList" :key="s.id" :class="{ 'skill-on': s.enabled }">
            <div class="skill-header">
              <span class="skill-icon">{{ s.icon }}</span>
              <span class="skill-name">{{ s.name }}</span>
              <button v-if="!s.installed" class="skill-delete" @click.stop="removeSkill(s)" title="删除该 Skill">✕</button>
              <button class="toggle-switch sm" :class="{ on: s.enabled }" @click="s.enabled = !s.enabled; toggleSkill(s)">
                <span class="toggle-thumb"></span>
              </button>
            </div>
            <div class="skill-desc">{{ s.desc }}</div>
            <div v-if="s.installed" class="skill-source-row">
              <span class="skill-source" :class="{ superpowers: s.source === 'Superpowers', github: s.source_kind === 'github-high-star' }">
                {{ s.source_kind === 'github-high-star' ? `★ ${s.source}` : (s.source === 'Superpowers' ? '⚡ Superpowers' : '📦 项目技能') }}
              </span>
              <span v-if="s.source_stars" class="skill-stars" :title="`Star 快照日期：${s.source_checked_at || '未知'}`">★ {{ formatStars(s.source_stars) }}</span>
              <code class="skill-path" :title="s.installed_path">{{ s.installed_path }}</code>
            </div>
            <div class="skill-meta-row">
              <span v-if="s.tool_name" class="skill-tool" :title="`绑定工具：${s.tool_name}`">
                🔗 {{ s.tool_name }}
              </span>
              <span v-else-if="s.installed" class="skill-tool installed" title="由 SKILL.md 在编码智能体中按需加载">📄 文件型 Skill</span>
              <span v-else class="skill-tool warn" title="未绑定工具，启用后 LLM 无法实际调用">⚠ 未绑定工具</span>
            </div>
            <div class="skill-tags">
              <span class="skill-tag" v-for="t in s.tags" :key="t">{{ t }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 模型配置 ── -->
    <div v-if="activeTab === 'models'" class="tab-content">
      <div class="card">
        <div class="section-toolbar">
          <span class="section-count">已配置 {{ modelList.length }} 个模型</span>
          <button class="btn btn-outline btn-sm" @click="showAddModel = !showAddModel">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            新增模型
          </button>
        </div>

        <div v-if="showAddModel" class="add-form add-form-edit">
          <span class="form-chip">新增模型</span>
          <input v-model="newModel.name" class="form-input" placeholder="显示名称，如 私有推理模型 / Claude / Gemini" style="flex:1" />
          <input v-model="newModel.provider" class="form-input" placeholder="Provider 标签，如 OpenAI / Claude / Gemini" style="width:170px" />
          <select v-model="newModel.runtime_provider" class="form-input" style="width:150px">
            <option value="openai">openai-compatible</option>
            <option value="anthropic">anthropic</option>
          </select>
          <input v-model="newModel.runtime_model" class="form-input mono" placeholder="运行时模型名，如 your-model-id" style="flex:1.2" />
          <input v-if="newModel.runtime_provider === 'openai'" v-model="newModel.base_url" class="form-input mono" placeholder="Base URL，可留空走全局" style="flex:1.6" />
          <select v-if="newModel.runtime_provider === 'openai'" v-model="newModel.wire_api" class="form-input" style="width:130px">
            <option value="">自动识别</option>
            <option value="chat">chat</option>
            <option value="responses">responses</option>
          </select>
          <label v-if="newModel.runtime_provider === 'openai'" class="inline-toggle">
            <span>Thinking</span>
            <button class="toggle-switch sm" type="button" :class="{ on: newModel.enable_thinking }" @click="newModel.enable_thinking = !newModel.enable_thinking">
              <span class="toggle-thumb"></span>
            </button>
          </label>
          <input v-model="newModel.api_key" class="form-input mono" type="password" placeholder="API Key，可留空走全局" style="flex:1.3" />
          <label class="inline-toggle">
            <span>设为激活</span>
            <button class="toggle-switch sm" type="button" :class="{ on: newModel.active }" @click="newModel.active = !newModel.active">
              <span class="toggle-thumb"></span>
            </button>
          </label>
          <button class="btn btn-primary btn-sm" @click="addModel">确认新增</button>
          <button class="btn btn-outline btn-sm" @click="cancelAddModel">取消</button>
        </div>

        <div v-if="editingModelId" class="add-form add-form-edit">
          <span class="form-chip">编辑模型</span>
          <input v-model="editingModel.name" class="form-input" placeholder="显示名称" style="flex:1" />
          <input v-model="editingModel.provider" class="form-input" placeholder="Provider 标签" style="width:170px" />
          <select v-model="editingModel.runtime_provider" class="form-input" style="width:150px">
            <option value="openai">openai-compatible</option>
            <option value="anthropic">anthropic</option>
          </select>
          <input v-model="editingModel.runtime_model" class="form-input mono" placeholder="运行时模型名" style="flex:1.2" />
          <input v-if="editingModel.runtime_provider === 'openai'" v-model="editingModel.base_url" class="form-input mono" placeholder="Base URL，可留空走全局" style="flex:1.6" />
          <select v-if="editingModel.runtime_provider === 'openai'" v-model="editingModel.wire_api" class="form-input" style="width:130px">
            <option value="">自动识别</option>
            <option value="chat">chat</option>
            <option value="responses">responses</option>
          </select>
          <label v-if="editingModel.runtime_provider === 'openai'" class="inline-toggle">
            <span>Thinking</span>
            <button class="toggle-switch sm" type="button" :class="{ on: editingModel.enable_thinking }" @click="editingModel.enable_thinking = !editingModel.enable_thinking">
              <span class="toggle-thumb"></span>
            </button>
          </label>
          <input v-model="editingModel.api_key" class="form-input mono" type="password" placeholder="留空则保留原值" style="flex:1.3" />
          <button class="btn btn-primary btn-sm" @click="saveModel">保存修改</button>
          <button class="btn btn-outline btn-sm" @click="cancelEditModel">取消</button>
        </div>

        <table>
          <thead>
            <tr>
              <th>显示名</th><th>Provider</th><th>运行时</th><th>连接参数</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in modelList" :key="m.id">
              <td>
                <strong>{{ m.name }}</strong>
                <div class="mini-desc mono">{{ m.id }}</div>
              </td>
              <td>
                <div>{{ m.provider }}</div>
                <div class="mini-desc mono">{{ m.runtime_provider || 'default' }}</div>
              </td>
              <td>
                <div class="mono">{{ m.runtime_model || m.name }}</div>
                <div class="mini-desc">{{ m.wire_api || 'auto' }} · {{ m.enable_thinking ? 'thinking on' : 'thinking off' }}</div>
              </td>
              <td>
                <div class="mono">{{ m.base_url || '使用全局 Base URL / 默认配置' }}</div>
                <div class="mini-desc">{{ m.api_key_set ? '已配置专属 API Key' : '使用全局 Key 或无 Key' }}</div>
              </td>
              <td>
                <span class="mcp-enabled-tag" :class="{ off: !m.active }">{{ m.active ? '当前激活' : '未激活' }}</span>
              </td>
              <td>
                <button class="action-link" style="color:var(--warning)" @click="activateModel(m)" :disabled="m.active">设为激活</button>
                <button class="action-link" style="color:var(--accent)" @click="startEditModel(m)">编辑</button>
                <button class="action-link" @click="removeModel(m.id)">删除</button>
              </td>
            </tr>
            <tr v-if="!modelList.length">
              <td colspan="6" class="empty-cell">暂无模型配置，点“新增模型”后即可接入任意自定义大模型。</td>
            </tr>
          </tbody>
        </table>
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
  { key: 'models', label: '模型配置' },
  { key: 'other',  label: '其他' },
]
const SKILL_MODES = [
  { value: 'auto',    label: '自动执行' },
  { value: 'confirm', label: '执行前确认' },
  { value: 'dry',     label: '仅限预览' },
]

// 角色定义快速模板（点击注入到 textarea，可二次编辑）
const ROLE_TEMPLATES = [
  {
    key: 'sre',
    label: '资深 SRE',
    text: `你是一名资深 SRE（网站可靠性工程师），负责保障 AIOps 平台稳定性。

【职责】
- 实时监控告警、快速定位故障根因、给出可执行修复方案
- 主动发现潜在风险（容量、慢查询、依赖异常）并给出优化建议

【工作原则】
- 先调工具拿事实，不靠记忆下结论
- 高风险操作（重启/扩缩容/改配置）必须二次确认或走审批
- 输出结构化中文：先结论，再依据，最后操作步骤（带回滚预案）

【自我介绍】
直接说"我是 AIOps 智能运维助手"，不要主动声明基于大模型。`,
  },
  {
    key: 'reader',
    label: '只读分析师',
    text: `你是 AIOps 只读分析助手，只用查询类工具，不执行任何写操作。

【职责】
- 帮用户读懂日志、指标、Trace
- 在数据基础上给出趋势与异常解读，不下定论

【工作原则】
- 只调 query/get/list/inspect 类工具
- 如果用户问"怎么改/重启"，告知"已切到只读模式，请联系有写权限的同事"`,
  },
  {
    key: 'k8s',
    label: 'K8s 专家',
    text: `你是 Kubernetes 集群专家，专注容器编排、Pod 排障、资源拓扑分析。

【职责】
- 用 K8s 工具查 Pod/Deployment/Service/ConfigMap 状态
- 对 CrashLoopBackOff、ImagePullBackOff、OOMKilled 等典型故障给出诊断步骤
- ConfigMap 修改时必须先 diff 关键 key 再走审批

【输出】
- 列出"已查的资源 / 关键观察 / 假设根因 / 验证步骤 / 修复 + 回滚"`,
  },
  {
    key: 'db',
    label: 'DBA',
    text: `你是数据库 / 中间件运维专家，覆盖 MySQL、Redis、Kafka、Elasticsearch。

【职责】
- 慢查询分析、连接池/内存/复制状态巡检
- 索引建议、Key 大小/过期策略评估
- 备份/恢复方案审核（不直接 drop/flush）

【禁忌】
- 任何 DROP / FLUSHALL / TRUNCATE / 删除主从同步状态的操作必须人工审批`,
  },
]

// Skill 能力说明快速模板
const SKILL_DESC_TEMPLATES = [
  {
    key: 'standard',
    label: '标准三段',
    text: `你可以通过下方 Skill 完成以下三类自动化能力：

①【查询类】查日志（Loki）、查指标（Prometheus）、查 K8s 资源状态、检索历史报告与相似故障
②【诊断类】全量主机巡检、慢查询 Top-N、模板聚类、根因定位
③【执行类】滚动重启 Deployment、ConfigMap 改键、Ansible Playbook 推送

执行类 Skill 默认进审批流，behaviors.auto 开启 + 风险等级低时才自动跑。`,
  },
  {
    key: 'minimal',
    label: '极简版',
    text: `你可以调用下方 Skill 中已启用的能力来辅助分析与处置问题。
具体调用哪个工具由你自己根据问题判断；只读类直接调，写类需告知用户后再触发。`,
  },
  {
    key: 'detail',
    label: '细分类',
    text: `Skill 能力清单（按调用频率排序）：

- query_error_logs / count_errors_by_service：日志快速定位
- get_host_metrics / inspect_all_hosts：主机指标与全量巡检
- get_k8s_summary / get_k8s_pods / get_k8s_deployments：集群快照
- recall_similar_incidents / search_daily_reports：历史检索
- es_list_indices / es_cluster_health：ES 状态
- export_report_pdf：生成 PDF 报告（低风险，可自动）
- call_mcp_tool：通用 MCP（写动作走审批）

每次回答前先简述选择某个 Skill 的理由，再调用。`,
  },
]
const activeTab = ref('basic')
const saving    = ref(false)
const toast     = ref('')

// ── API 辅助 ─────────────────────────────────────────────────────────
async function apiFetch(url, opts = {}) {
  const resp = await fetch(url, { credentials: 'include', ...opts })
  const text = await resp.text()
  let payload = {}
  if (text) {
    try { payload = JSON.parse(text) } catch { payload = { detail: text } }
  }
  if (!resp.ok) {
    throw new Error(payload.detail || payload.message || `HTTP ${resp.status}`)
  }
  return payload
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
const modelList = ref([])
const showAddModel = ref(false)
const newModel = reactive(createEmptyModel())
const editingModelId = ref('')
const editingModel = reactive(createEmptyModel())

function createEmptyModel() {
  return {
    name: '',
    provider: '',
    runtime_provider: 'openai',
    runtime_model: '',
    base_url: '',
    api_key: '',
    wire_api: '',
    enable_thinking: false,
    active: false,
  }
}

function resetModelForm(target) {
  Object.assign(target, createEmptyModel())
}

function syncModels(models = []) {
  const next = models.map(item => ({ ...item }))
  configModels.value = next
  modelList.value = next
}

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
    syncModels(d.models || [])
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
      body: JSON.stringify({ behaviors: behaviors.value.map(b => ({ key: b.key, enabled: b.enabled })) }),
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
  }).then(r => {
    const activeId = r?.data?.id || m.id
    syncModels(modelList.value.map(item => ({
      ...item,
      ...(item.id === activeId ? r?.data || {} : {}),
      active: item.id === activeId,
    })))
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
const editingMcpId = ref('')
const editingMcp = reactive({ name: '', type: 'http', url: '', enabled: true })

function resetMcpForm(target) {
  Object.assign(target, { name: '', type: 'http', url: '', enabled: true })
}

function replaceMcp(updated) {
  if (!updated?.id) return
  const idx = mcpList.value.findIndex(item => item.id === updated.id)
  if (idx >= 0) {
    mcpList.value.splice(idx, 1, { ...mcpList.value[idx], ...updated })
  }
}

async function addMcp() {
  if (!newMcp.name.trim() || !newMcp.url.trim()) {
    showToast('❌ MCP 名称和地址不能为空')
    return
  }
  try {
    const created = await apiFetch('/api/agent-config/mcps', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newMcp.name.trim(),
        type: newMcp.type,
        url: newMcp.url.trim(),
      }),
    })
    mcpList.value.push(created)
    resetMcpForm(newMcp)
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
    if (editingMcpId.value === id) cancelEditMcp()
    await loadStats()
    showToast('✓ 已删除')
  } catch (e) {
    showToast(`❌ 删除失败：${e.message}`)
  }
}

async function pingMcp(m) {
  try {
    const r = await apiFetch(`/api/agent-config/mcps/${m.id}/ping`, { method: 'POST' })
    m.ok = r.ok
    showToast(r.ok ? `✓ ${m.name} 连通正常` : `${m.name} 无法连通`)
  } catch (e) {
    showToast(`❌ 检测失败：${e.message}`)
  }
}

function startEditMcp(m) {
  showAddMcp.value = false
  editingMcpId.value = m.id
  Object.assign(editingMcp, {
    name: m.name || '',
    type: m.type || 'http',
    url: m.url || '',
    enabled: m.enabled !== false,
  })
}

function cancelEditMcp() {
  editingMcpId.value = ''
  resetMcpForm(editingMcp)
}

async function saveMcp() {
  if (!editingMcpId.value) return
  if (!editingMcp.name.trim() || !editingMcp.url.trim()) {
    showToast('❌ MCP 名称和地址不能为空')
    return
  }
  try {
    const updated = await apiFetch(`/api/agent-config/mcps/${editingMcpId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: editingMcp.name.trim(),
        type: editingMcp.type,
        url: editingMcp.url.trim(),
        enabled: !!editingMcp.enabled,
      }),
    })
    replaceMcp(updated)
    cancelEditMcp()
    await loadStats()
    showToast('✓ MCP 已更新')
  } catch (e) {
    showToast(`❌ 更新失败：${e.message}`)
  }
}

async function toggleMcp(m) {
  const previous = !!m.enabled
  const next = !previous
  m.enabled = next
  try {
    const updated = await apiFetch(`/api/agent-config/mcps/${m.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: next }),
    })
    replaceMcp(updated)
    await loadStats()
    showToast(next ? '✓ MCP 已启用' : '✓ MCP 已停用')
  } catch (e) {
    m.enabled = previous
    showToast(`❌ 操作失败：${e.message}`)
  }
}

// ── Skill ─────────────────────────────────────────────────────────────
const skillList = ref([])
const availableTools = ref([])
const showAddSkill = ref(false)
const newSkill = reactive({ icon: '🛠️', name: '', desc: '', tool_name: '', enabled: true })
const newSkillTagsInput = ref('')
const importSkillsInput = ref(null)
const importResult = ref(null)
const installedSkillCount = computed(() => skillList.value.filter(s => s.installed).length)
const superpowersSkillCount = computed(() => skillList.value.filter(s => s.installed && s.source === 'Superpowers').length)
const githubHighStarSkillCount = computed(() => skillList.value.filter(s => s.installed && s.source_kind === 'github-high-star').length)

function formatStars(value) {
  const stars = Number(value || 0)
  if (stars >= 1000) return `${(stars / 1000).toFixed(stars >= 100000 ? 0 : 1)}k`
  return String(stars)
}

const RISK_LABELS = {
  read:        '只读 · 自动放行',
  write_low:   '低风险写',
  write_high:  '高风险写 · 需审批',
  destructive: '破坏性 · 严禁自动',
}
function riskLabel(r) { return RISK_LABELS[r] || (r || '未知') }
const selectedToolHint = '工具的风险等级由 backend/agent/risk_registry.py 决定'

async function loadSkills() {
  try {
    const d = await apiFetch('/api/agent-config/skills')
    skillList.value = d.data || []
  } catch { /* ignore */ }
}

async function loadAvailableTools() {
  try {
    const d = await apiFetch('/api/agent-config/skills/available-tools')
    availableTools.value = d.data || []
  } catch { availableTools.value = [] }
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

function cancelAddSkill() {
  showAddSkill.value = false
  newSkill.icon = '🛠️'
  newSkill.name = ''
  newSkill.desc = ''
  newSkill.tool_name = ''
  newSkill.enabled = true
  newSkillTagsInput.value = ''
}

async function addSkill() {
  const name = newSkill.name.trim()
  if (!name) { showToast('❌ 请填写 Skill 名称'); return }
  try {
    const tags = newSkillTagsInput.value.split(/[,，]/).map(t => t.trim()).filter(Boolean)
    const created = await apiFetch('/api/agent-config/skills', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        desc: newSkill.desc.trim(),
        icon: (newSkill.icon || '🛠️').trim(),
        tool_name: newSkill.tool_name.trim(),
        tags,
        enabled: !!newSkill.enabled,
      }),
    })
    skillList.value.push(created)
    cancelAddSkill()
    await loadStats()
    showToast('✓ Skill 已新增')
  } catch (e) {
    showToast(`❌ 新增失败：${e.message}`)
  }
}

async function removeSkill(s) {
  if (!confirm(`确定删除 Skill「${s.name}」？此操作不可撤销。`)) return
  try {
    await apiFetch(`/api/agent-config/skills/${s.id}`, { method: 'DELETE' })
    skillList.value = skillList.value.filter(item => item.id !== s.id)
    await loadStats()
    showToast('✓ 已删除')
  } catch (e) {
    showToast(`❌ 删除失败：${e.message}`)
  }
}

function triggerImportSkills() {
  importResult.value = null
  if (importSkillsInput.value) {
    importSkillsInput.value.value = ''
    importSkillsInput.value.click()
  }
}

async function onImportSkillsFile(ev) {
  const file = ev.target.files && ev.target.files[0]
  if (!file) return
  try {
    const text = await file.text()
    let parsed
    try { parsed = JSON.parse(text) } catch (e) {
      importResult.value = { kind: 'err', text: `❌ JSON 解析失败：${e.message}` }
      return
    }
    // 兼容两种格式：直接数组 / {skills: [...]} 包装
    const items = Array.isArray(parsed) ? parsed
                : Array.isArray(parsed?.skills) ? parsed.skills
                : null
    if (!items) {
      importResult.value = { kind: 'err', text: '❌ 文件结构错误：根需为 Skill 数组，或形如 {"skills": [...]}' }
      return
    }

    const strategy = confirm(`即将导入 ${items.length} 条 Skill。\n\n点击「确定」=覆盖已存在的同名 Skill；\n点击「取消」=跳过已存在的（保留旧记录）。`)
      ? 'overwrite' : 'skip'

    const res = await apiFetch('/api/agent-config/skills/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skills: items, strategy }),
    })
    await loadSkills()
    await loadStats()
    const errSuffix = res.errors && res.errors.length ? `，${res.errors.length} 条错误（行号：${res.errors.map(e=>e.index).join(',')}）` : ''
    importResult.value = {
      kind: res.errors && res.errors.length ? 'warn' : 'ok',
      text: `✓ 导入完成：新增 ${res.imported}，${strategy==='overwrite'?'覆盖':'跳过'} ${strategy==='overwrite'?res.overwritten:res.skipped}${errSuffix}`,
    }
  } catch (e) {
    importResult.value = { kind: 'err', text: `❌ 导入失败：${e.message}` }
  }
}

function exportSkills() {
  const blob = new Blob([JSON.stringify({
    exported_at: new Date().toISOString(),
    skills: skillList.value.map(({ id, ...rest }) => rest),
  }, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `aiops-skills-${new Date().toISOString().slice(0,10)}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  showToast('✓ 已导出')
}

// ── 模型配置 ───────────────────────────────────────────────────────────
async function loadModels() {
  try {
    const d = await apiFetch('/api/agent-config/models')
    syncModels(d.data || [])
  } catch { /* ignore */ }
}

function buildModelPayload(form, { includeEmptyApiKey = false } = {}) {
  const payload = {
    name: form.name.trim(),
    provider: form.provider.trim(),
    runtime_provider: form.runtime_provider,
    runtime_model: form.runtime_model.trim(),
    base_url: form.runtime_provider === 'openai' ? form.base_url.trim() : '',
    wire_api: form.runtime_provider === 'openai' ? form.wire_api : '',
    enable_thinking: form.runtime_provider === 'openai' ? !!form.enable_thinking : false,
    active: !!form.active,
  }
  const apiKey = form.api_key.trim()
  if (apiKey || includeEmptyApiKey) payload.api_key = apiKey
  return payload
}

async function activateModel(model) {
  try {
    const r = await apiFetch('/api/agent-config/models/active', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: model.id }),
    })
    const activeId = r?.data?.id || model.id
    syncModels(modelList.value.map(item => ({
      ...item,
      ...(item.id === activeId ? r?.data || {} : {}),
      active: item.id === activeId,
    })))
    await loadStats()
    showToast('✓ 模型已切换')
  } catch (e) {
    showToast(`❌ 切换失败：${e.message}`)
  }
}

function startEditModel(model) {
  editingModelId.value = model.id
  Object.assign(editingModel, {
    name: model.name || '',
    provider: model.provider || '',
    runtime_provider: model.runtime_provider || 'openai',
    runtime_model: model.runtime_model || '',
    base_url: model.base_url || '',
    api_key: '',
    wire_api: model.wire_api || '',
    enable_thinking: !!model.enable_thinking,
    active: !!model.active,
  })
}

function cancelEditModel() {
  editingModelId.value = ''
  resetModelForm(editingModel)
}

function cancelAddModel() {
  showAddModel.value = false
  resetModelForm(newModel)
}

async function addModel() {
  if (!newModel.name.trim() || !newModel.runtime_model.trim()) {
    showToast('❌ 显示名称和运行时模型名不能为空')
    return
  }
  try {
    await apiFetch('/api/agent-config/models', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildModelPayload(newModel, { includeEmptyApiKey: true })),
    })
    cancelAddModel()
    await loadBasic()
    await loadStats()
    showToast('✓ 模型已新增')
  } catch (e) {
    showToast(`❌ 新增失败：${e.message}`)
  }
}

async function saveModel() {
  if (!editingModelId.value) return
  if (!editingModel.name.trim() || !editingModel.runtime_model.trim()) {
    showToast('❌ 显示名称和运行时模型名不能为空')
    return
  }
  try {
    await apiFetch(`/api/agent-config/models/${editingModelId.value}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildModelPayload(editingModel)),
    })
    cancelEditModel()
    await loadBasic()
    await loadStats()
    showToast('✓ 模型已更新')
  } catch (e) {
    showToast(`❌ 更新失败：${e.message}`)
  }
}

async function removeModel(id) {
  if (!confirm('确认删除该模型配置？')) return
  try {
    await apiFetch(`/api/agent-config/models/${id}`, { method: 'DELETE' })
    await loadBasic()
    await loadStats()
    showToast('✓ 模型已删除')
  } catch (e) {
    showToast(`❌ 删除失败：${e.message}`)
  }
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
  await Promise.all([loadBasic(), loadBehaviors(), loadMcps(), loadSkills(), loadModels(), loadSa(), loadStats(), loadAvailableTools()])
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
  font-family: 'Cascadia Code', 'Consolas', monospace;
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
.skill-meta-row { display: flex; gap: 6px; margin-bottom: 6px; flex-wrap: wrap; }
.skill-tool { font-size: 11px; padding: 2px 8px; background: var(--bg-hover); border-radius: 4px; color: var(--text-secondary); }
.skill-tool.warn { background: rgba(245, 158, 11, .12); color: #d97706; }
.skill-tool.installed { background: rgba(34, 197, 94, .12); color: #16a34a; }
.skill-delete { background: none; border: 0; cursor: pointer; color: var(--text-muted); font-size: 14px; padding: 2px 6px; border-radius: 4px; }
.skill-delete:hover { background: rgba(239, 68, 68, .12); color: #dc2626; }
.skill-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.skill-tag { font-size: 10px; padding: 2px 7px; background: var(--accent-dim); color: var(--accent); border-radius: 3px; }
.skill-source-row { display: flex; align-items: center; gap: 6px; margin: -2px 0 8px; min-width: 0; }
.skill-source { flex: 0 0 auto; font-size: 10px; padding: 2px 7px; border-radius: 999px; color: #2563eb; background: rgba(37, 99, 235, .10); }
.skill-source.superpowers { color: #b45309; background: rgba(245, 158, 11, .14); }
.skill-source.github { color: #7c3aed; background: rgba(124, 58, 237, .12); }
.skill-stars { flex: 0 0 auto; font-size: 10px; color: #b45309; }
.skill-path { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; color: var(--text-muted); background: transparent; }
.installed-count, .superpowers-count, .github-count { display: inline-flex; margin-left: 8px; padding: 2px 7px; border-radius: 999px; font-size: 10px; background: var(--bg-hover); color: var(--text-secondary); }
.superpowers-count { color: #b45309; background: rgba(245, 158, 11, .14); }
.github-count { color: #7c3aed; background: rgba(124, 58, 237, .12); }

/* Skill 工具栏：新增 / 导入 / 导出三件套 */
.section-toolbar-actions { display: flex; gap: 6px; }

/* 导入结果横幅 */
.import-result {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 14px; margin: 0 0 12px;
  border-radius: 6px; font-size: 13px;
  border: 1px solid transparent;
}
.import-result.ok   { background: rgba(34, 197, 94, .10); border-color: rgba(34, 197, 94, .35); color: #16a34a; }
.import-result.warn { background: rgba(245, 158, 11, .10); border-color: rgba(245, 158, 11, .4);  color: #d97706; }
.import-result.err  { background: rgba(239, 68, 68, .10);  border-color: rgba(239, 68, 68, .35); color: #dc2626; }
.import-result-close { background: none; border: 0; color: inherit; opacity: .55; cursor: pointer; font-size: 14px; }
.import-result-close:hover { opacity: 1; }

/* 角色定义 / Skill 说明区：快速模板栏 + 字符计数 */
.form-section-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-bottom: 6px;
}
.template-bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.template-label { font-size: 11px; color: var(--text-muted); margin-right: 2px; }
.template-chip {
  font-size: 11px; padding: 3px 9px;
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 999px;
  cursor: pointer; color: var(--text-secondary);
  transition: border-color .12s, color .12s, background .12s;
}
.template-chip:hover { border-color: var(--accent); color: var(--accent); background: var(--accent-dim); }
.form-meta {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 4px; font-size: 11px; color: var(--text-muted);
}
.form-counter.warn { color: #d97706; }
.form-tip { color: var(--text-muted); }

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

.form-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 11px;
  font-weight: 600;
}

.inline-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.mini-desc {
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
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
