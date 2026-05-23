<template>
  <div class="workbench-page">
    <Transition name="toast">
      <div v-if="toast.text" class="toast-msg" :class="toast.type">
        {{ toast.text }}
      </div>
    </Transition>

    <div class="workbench-shell">
      <aside class="project-pane">
        <div class="pane-head">
          <div class="pane-brand">
            <div class="pane-kicker">AI Workspace</div>
            <h2>开发工作台</h2>
            <p>按 Claude 本地工作区标准组织项目、对话和设置。</p>
          </div>
          <button class="icon-btn" type="button" @click="openSettings('models')">
            设置
          </button>
        </div>

        <div class="pane-summary">
          <div class="summary-cell">
            <span>配置</span>
            <strong>{{ workspaceMeta.settings_files || 0 }}</strong>
          </div>
          <div class="summary-cell">
            <span>根目录</span>
            <strong>{{ workspaceMeta.explicit_roots || 0 }}</strong>
          </div>
          <div class="summary-cell">
            <span>最近项目</span>
            <strong>{{ workspaceMeta.recent_projects || 0 }}</strong>
          </div>
          <div class="summary-cell">
            <span>项目数</span>
            <strong>{{ filteredProjects.length }}</strong>
          </div>
        </div>

        <div class="pane-search">
          <input
            v-model.trim="searchText"
            class="search-input"
            type="text"
            placeholder="搜索项目、路径、技术栈"
          >
        </div>

        <div v-if="loadError" class="load-error">
          {{ loadError }}
        </div>

        <div class="section-title-row">
          <span class="section-title">项目</span>
          <button class="new-session-global" @click="newSessionGlobal" type="button" title="新建会话（无项目）">+</button>
        </div>

        <div class="project-list">
          <div
            v-for="project in filteredProjects"
            :key="project.path"
            class="project-group"
            :class="{ active: selectedPath === project.path }"
          >
            <!-- 项目头部行 -->
            <div
              class="project-item"
              :class="{ active: selectedPath === project.path, expanded: expandedProjects.has(project.path) }"
              @click="toggleProject(project)"
            >
              <span class="project-expand-arrow">{{ expandedProjects.has(project.path) ? '▾' : '▸' }}</span>
              <span class="project-folder-icon">📁</span>
              <div class="project-item-body">
                <div class="project-name-row">
                  <strong class="project-name">{{ project.name }}</strong>
                  <span v-if="project.git_branch" class="branch-badge mono">{{ project.git_branch }}</span>
                </div>
                <div class="project-path mono" :title="project.path">{{ shortenPath(project.path) }}</div>
              </div>
              <!-- 新建对话按钮 -->
              <button
                class="proj-new-btn"
                type="button"
                title="在此项目新建对话"
                @click.stop="newSessionForProject(project)"
              >＋</button>
            </div>

            <!-- 展开：历史对话列表 -->
            <div v-if="expandedProjects.has(project.path)" class="conv-list">
              <div v-if="loadingConvs.has(project.path)" class="conv-loading">加载中...</div>
              <div v-else-if="!projectConvs(project.path).length" class="conv-empty">暂无对话历史</div>
              <button
                v-for="conv in projectConvs(project.path)"
                :key="conv.conv_id"
                class="conv-item"
                :class="{ active: activeConvId === conv.conv_id }"
                type="button"
                @click="loadConversation(project, conv)"
              >
                <span class="conv-icon">💬</span>
                <div class="conv-item-body">
                  <span class="conv-title">{{ conv.title || '未命名对话' }}</span>
                  <span class="conv-time">{{ formatTime(conv.updated_at) }}</span>
                </div>
                <button class="conv-del-btn" type="button" title="删除" @click.stop="deleteConv(conv)">×</button>
              </button>
            </div>
          </div>

          <div v-if="!filteredProjects.length" class="empty-state">
            没有发现项目，请在下方手动填写工作目录。
          </div>
        </div>

        <div class="pane-manual">
          <div class="section-title compact">手动工作目录</div>
          <input
            v-model.trim="manualPath"
            class="manual-input mono"
            type="text"
            :disabled="streaming"
            placeholder="例如 D:\code\my-project"
          >
          <div class="manual-actions">
            <button class="primary-btn" type="button" :disabled="!manualPath || streaming" @click="applyManualPath">
              应用目录
            </button>
            <button class="ghost-btn" type="button" :disabled="streaming" @click="reloadWorkspace">
              {{ loading ? '加载中...' : '刷新发现' }}
            </button>
          </div>
        </div>
      </aside>

      <main class="main-pane">
        <header class="main-head">
          <div class="main-head-copy">
            <div class="pane-kicker">Workspace Session</div>
            <h1>{{ selectedProject?.name || '选择一个本地项目' }}</h1>
            <div class="main-subline">
              <span class="mono">{{ selectedPath || '尚未设置工作目录' }}</span>
              <span v-if="selectedProject?.git_branch" class="sub-pill mono">{{ selectedProject.git_branch }}</span>
              <span class="sub-pill">{{ selectedProject ? formatTime(selectedProject.last_active_at) : '等待项目选择' }}</span>
            </div>
          </div>

          <div class="main-head-actions">
            <!-- 执行器切换 -->
            <div class="executor-switch" :class="wbExecutor === 'external_cli' ? 'exec-claude' : ''">
              <span class="exec-label">执行器</span>
              <button
                class="exec-btn"
                :class="{ active: wbExecutor === '' || wbExecutor === 'langgraph' }"
                type="button"
                @click="wbExecutor = 'langgraph'"
                title="使用项目内置 LangGraph ReAct Agent"
              >⚙ LangGraph</button>
              <button
                class="exec-btn exec-claude-btn"
                :class="{ active: wbExecutor === 'external_cli', disabled: !claudeAvailable && !detectingExecutors }"
                type="button"
                @click="wbExecutor = 'external_cli'"
                :title="claudeAvailable ? 'Claude Code 已安装，点击切换' : '未检测到 claude 命令，请先安装 Claude Code CLI'"
              >
                <span>◈ Claude Code</span>
                <span v-if="detectingExecutors" class="exec-detecting">检测中...</span>
                <span v-else-if="claudeAvailable" class="exec-ok">●</span>
                <span v-else class="exec-unavail">○</span>
              </button>
            </div>

            <button class="ghost-btn" type="button" :disabled="!selectedProject || streaming" @click="sendQuickPrompt('scan')">
              扫描项目
            </button>
            <button class="ghost-btn" type="button" :disabled="!selectedProject || streaming" @click="sendQuickPrompt('entry')">
              分析入口
            </button>
            <button class="primary-btn" type="button" @click="openSettings('models')">
              工作台设置
            </button>
          </div>
        </header>

        <section class="workspace-canvas">
          <!-- 顶部 Canvas 条 -->
          <div class="canvas-bar">
            <div class="canvas-title">工作区记录</div>
            <div class="canvas-meta">
              <span class="meta-chip">MODEL {{ modelBadgeText }}</span>
              <span class="meta-chip">PROVIDER {{ providerBadgeText }}</span>
              <span class="meta-chip">HOME {{ currentHomeText }}</span>
              <span class="meta-chip exec-mode-chip" :class="wbExecutor === 'external_cli' ? 'chip-claude' : ''">
                EXEC {{ wbExecutor === 'external_cli' ? 'Claude Code' : 'LangGraph' }}
              </span>
            </div>
            <!-- 文件改动面板开关 -->
            <button class="canvas-changes-btn" :class="{ active: showChangesPanel }"
              @click="toggleChangesPanel" type="button"
              :title="showChangesPanel ? '隐藏文件改动' : '显示文件改动'">
              <span>⌥</span> 改动 {{ changedFiles.length || '' }}
            </button>
          </div>

          <!-- 主体：对话区 + 右侧文件改动面板 -->
          <div class="canvas-body">

          <div v-if="selectedProject" class="context-strip">
            <div class="context-card">
              <span class="context-label">项目摘要</span>
              <strong>{{ selectedProject.summary || '本地工作区项目' }}</strong>
            </div>
            <div class="context-card">
              <span class="context-label">标记文件</span>
              <strong>{{ selectedProject.marker_files?.slice(0, 3).join(' · ') || '未识别' }}</strong>
            </div>
            <div class="context-card">
              <span class="context-label">命令提示</span>
              <strong>{{ currentHintText }}</strong>
            </div>
          </div>

          <!-- 左侧：对话主区 -->
          <div class="canvas-body-main">
          <div class="conversation-scroll">
            <div v-if="!messages.length" class="welcome-doc">
              <div class="doc-eyebrow">Ready</div>
              <h3>{{ selectedProject ? `已加载 ${selectedProject.name}` : '左侧选择项目后开始对话' }}</h3>
              <p>
                {{ selectedProject
                  ? '建议先让模型扫描目录、识别启动命令和入口文件，再继续阅读代码、规划改动或执行排障。'
                  : '这个工作台会把所选目录作为 home_dir 传给模型，使其围绕当前项目做开发辅助。' }}
              </p>

              <!-- Open Design 风格 Starter Cards：点击填入 Composer，不立即发送 -->
              <div v-if="selectedProject" class="starter-grid">
                <button
                  v-for="card in starterCards"
                  :key="card.prompt"
                  class="starter-card"
                  type="button"
                  :disabled="streaming"
                  @click="fillComposer(card.prompt)"
                >
                  <span class="sc-icon">{{ card.icon }}</span>
                  <div class="sc-body">
                    <span class="sc-title">{{ card.title }}</span>
                    <span class="sc-tag">{{ card.tag }}</span>
                  </div>
                </button>
              </div>
            </div>

            <template v-else>
              <div
                v-for="message in messages"
                :key="message.id"
                class="message-block"
                :class="message.role"
              >
                <div v-if="message.role === 'user'" class="query-card">
                  <div class="query-label">你的请求</div>
                  <div class="query-text">{{ message.content }}</div>
                </div>

                <article v-else class="answer-card">
                  <div class="answer-head">
                    <div class="answer-mark">AI</div>
                    <div class="answer-title">
                      <strong>工作台回复</strong>
                      <span>{{ selectedProject?.name || 'Project' }}</span>
                    </div>
                  </div>

                  <div v-if="message.toolCalls?.length" class="tool-timeline">
                    <button
                      v-for="toolCall in message.toolCalls"
                      :key="toolCall.id"
                      class="tool-row"
                      :class="{ pending: toolCall.pending }"
                      type="button"
                      @click="toolCall.expanded = !toolCall.expanded"
                    >
                      <span class="tool-state" :class="{ pending: toolCall.pending }"></span>
                      <span class="tool-name">{{ toolCall.tool }}</span>
                      <span class="tool-input">{{ formatInput(toolCall.input) }}</span>
                      <span class="tool-toggle">{{ toolCall.expanded ? '收起' : '展开' }}</span>
                    </button>

                    <pre
                      v-for="toolCall in message.toolCalls.filter(item => item.expanded && item.output)"
                      :key="`${toolCall.id}-output`"
                      class="tool-output"
                    >{{ toolCall.output }}</pre>
                  </div>

                  <div v-if="message.content || message.streaming" class="answer-content" v-html="renderContent(message.content)"></div>
                  <span v-if="message.streaming" class="stream-cursor"></span>
                </article>
              </div>
              <div ref="bottomRef"></div>
            </template>
          </div>

          <footer class="composer-wrap">
            <div class="composer-shell">
              <span class="composer-prefix">/workspace</span>
              <textarea
                ref="inputRef"
                v-model="inputText"
                class="composer-input"
                :disabled="streaming || !selectedPath"
                :placeholder="selectedPath ? '输入开发任务、阅读需求或排障问题…' : '先选择左侧项目或填写手动工作目录'"
                rows="1"
                @keydown.enter.exact.prevent="onSend"
                @input="autoResize"
              ></textarea>
              <button v-if="streaming" class="stop-btn" type="button" @click="stopStreaming">
                ⬛ 停止
              </button>
              <button v-else class="send-btn" type="button" :disabled="!selectedPath || !inputText.trim()" @click="onSend">
                发送
              </button>
            </div>
            <div class="composer-foot">
              <span>{{ currentHintText }}</span>
              <span v-if="lastTokenUsage" class="token-chip">
                ↑{{ lastTokenUsage.input_tokens }} ↓{{ lastTokenUsage.output_tokens }} tokens
              </span>
              <button class="foot-link" type="button" :disabled="streaming || !selectedPath" @click="resetConversation">
                新对话
              </button>
            </div>
          </footer>
          </div><!-- /canvas-body-main -->
          </div><!-- /canvas-body -->

          <!-- 右侧文件改动面板 -->
          <aside v-if="showChangesPanel && selectedPath" class="changes-panel">
            <div class="cp-header">
              <span class="cp-title">文件改动</span>
              <span class="cp-branch mono" v-if="gitBranch">⎇ {{ gitBranch }}</span>
              <button class="cp-refresh" @click="refreshGitStatus" :disabled="gitLoading">↻</button>
            </div>
            <div v-if="gitLoading" class="cp-loading"><div class="spinner" style="width:12px;height:12px;border-width:2px"></div></div>
            <div v-else-if="!changedFiles.length" class="cp-empty">工作区干净，无改动文件</div>
            <div v-else class="cp-file-list">
              <div v-for="f in changedFiles" :key="f.file"
                class="cp-file-row" :class="{ active: diffFile === f.file }"
                @click="loadDiff(f.file)">
                <span class="cp-status-badge" :class="'fst-' + f.status">{{ f.xy }}</span>
                <span class="cp-filename mono">{{ f.file }}</span>
              </div>
            </div>
            <!-- Diff 查看 -->
            <div v-if="diffFile && diffContent" class="cp-diff-wrap">
              <div class="cp-diff-header">
                <span class="mono">{{ diffFile }}</span>
                <button class="cp-close-diff" @click="diffFile = ''; diffContent = ''">✕</button>
              </div>
              <pre class="cp-diff-pre" v-html="highlightDiff(diffContent)"></pre>
            </div>
          </aside>
        </section>
      </main>
    </div>

    <teleport to="body">
      <Transition name="fade">
        <div v-if="settingsOpen" class="settings-overlay" @click.self="settingsOpen = false">
          <div class="settings-dialog" @click.stop>
            <!-- 左侧导航 -->
            <aside class="settings-nav">
              <div class="settings-caption">设置</div>
              <button
                v-for="tab in SETTINGS_TABS"
                :key="tab.key"
                class="settings-nav-item"
                :class="{ active: settingsTab === tab.key }"
                type="button"
                @click="settingsTab = tab.key"
              >
                <span class="settings-nav-icon">{{ tab.icon }}</span>
                <span>{{ tab.label }}</span>
              </button>
            </aside>

            <!-- 右侧内容 -->
            <section class="settings-body">
              <div class="settings-head">
                <div class="settings-head-text">
                  <h3>{{ activeSettings.title }}</h3>
                  <p>{{ activeSettings.desc }}</p>
                </div>
                <button class="close-btn" type="button" @click="settingsOpen = false">×</button>
              </div>

              <div v-if="settingsTab === 'models'" class="settings-scroll">
                <div class="settings-row">
                  <div
                    v-for="model in modelOptions"
                    :key="model.id"
                    class="model-card-wrap"
                  >
                    <!-- 模型卡片行 -->
                    <div
                      class="model-card"
                      :class="{ active: model.active }"
                    >
                      <div class="model-card-main" @click="!streaming && activateModel(model.id)">
                        <div class="model-head">
                          <strong>{{ model.name }}</strong>
                          <span v-if="busyStates.modelId === model.id" class="pending-chip">切换中...</span>
                          <span v-else-if="model.active" class="active-chip">已启用</span>
                        </div>
                        <div class="model-subline">{{ model.provider }} · {{ model.runtime_provider || 'default' }}</div>
                        <div class="model-runtime mono">{{ model.runtime_model || model.name }}</div>
                        <div v-if="model.base_url" class="model-base mono">{{ model.base_url }}</div>
                      </div>
                      <!-- 编辑按钮 -->
                      <button
                        class="model-edit-icon"
                        type="button"
                        title="编辑模型参数"
                        @click.stop="wbEditModelId === model.id ? (wbEditModelId = null) : openWbEditModel(model)"
                      >✎</button>
                    </div>

                    <!-- 内联编辑面板 -->
                    <div v-if="wbEditModelId === model.id" class="wb-edit-panel">
                      <div class="wb-edit-title">编辑 · {{ model.name }}</div>
                      <div class="wb-edit-grid">
                        <label class="wb-ef">
                          <span>显示名称</span>
                          <input v-model="wbEditForm.name" class="settings-input" />
                        </label>
                        <label class="wb-ef">
                          <span>运行协议</span>
                          <select v-model="wbEditForm.runtime_provider" class="settings-input">
                            <option value="openai">openai-compatible</option>
                            <option value="anthropic">anthropic</option>
                          </select>
                        </label>
                        <label class="wb-ef wb-ef-full">
                          <span>Model ID <em style="color:#f87171">*</em></span>
                          <input v-model="wbEditForm.runtime_model" class="settings-input mono" />
                        </label>
                        <label v-if="wbEditForm.runtime_provider === 'openai'" class="wb-ef wb-ef-full">
                          <span>Base URL</span>
                          <input v-model="wbEditForm.base_url" class="settings-input mono"
                            placeholder="http://192.168.x.x:11434/v1" />
                        </label>
                        <label v-if="wbEditForm.runtime_provider === 'openai'" class="wb-ef">
                          <span>Wire API</span>
                          <select v-model="wbEditForm.wire_api" class="settings-input">
                            <option value="">自动识别</option>
                            <option value="chat">chat</option>
                            <option value="responses">responses</option>
                          </select>
                        </label>
                        <label v-if="wbEditForm.runtime_provider === 'openai'" class="wb-ef wb-ef-check">
                          <input type="checkbox" v-model="wbEditForm.enable_thinking" />
                          <span>开启 Thinking</span>
                        </label>
                        <label class="wb-ef wb-ef-full">
                          <span>API Key（留空保留原值）</span>
                          <input v-model="wbEditForm.api_key" type="password" class="settings-input mono"
                            placeholder="sk-... 或留空" />
                        </label>
                      </div>
                      <div class="wb-edit-actions">
                        <button class="primary-btn" type="button" @click="saveWbEditModel(model)" :disabled="wbEditSaving">
                          {{ wbEditSaving ? '保存中...' : '保存' }}
                        </button>
                        <button class="ghost-btn" type="button" @click="wbEditModelId = null">取消</button>
                        <span v-if="wbEditMsg" :style="{ color: wbEditOk ? '#22c55e' : '#f87171', fontSize: '12px' }">{{ wbEditMsg }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 通用配置 Tab -->
              <div v-else-if="settingsTab === 'general'" class="settings-scroll">
                <div class="sb-group">
                  <div class="sb-group-title">对话参数</div>
                  <div class="sb-field">
                    <label class="sb-label">工作目录</label>
                    <input v-model="generalForm.home_dir" class="settings-input mono"
                      placeholder="例如 D:\code\my-project 或 /home/user/project" />
                    <span class="sb-hint">设置后自动关联到当前项目上下文</span>
                  </div>
                  <div class="sb-field-row">
                    <div class="sb-field">
                      <label class="sb-label">最大轮次</label>
                      <input v-model.number="generalForm.max_turns" type="number" min="1" max="100" class="settings-input" />
                    </div>
                    <div class="sb-field">
                      <label class="sb-label">确认模式</label>
                      <select v-model="generalForm.confirm_mode" class="settings-input">
                        <option value="auto">自动执行</option>
                        <option value="ask">每次确认</option>
                        <option value="dry">仅预览</option>
                      </select>
                    </div>
                  </div>
                  <div class="sb-field sb-checkbox-field">
                    <label class="sb-checkbox">
                      <input type="checkbox" v-model="generalForm.stream" />
                      <span>启用流式输出（SSE）</span>
                    </label>
                  </div>
                </div>
                <div class="sb-actions">
                  <button class="primary-btn" type="button" @click="saveGeneralConfig" :disabled="generalSaving">
                    {{ generalSaving ? '保存中...' : '保存配置' }}
                  </button>
                  <span v-if="generalMsg" class="sb-msg ok">{{ generalMsg }}</span>
                </div>
              </div>

              <!-- 执行器 Tab -->
              <div v-else-if="settingsTab === 'executor'" class="settings-scroll">
                <div class="sb-group">
                  <div class="sb-group-title">执行模式</div>
                  <div class="sb-field-row">
                    <div class="sb-field">
                      <label class="sb-label">Agent 执行器</label>
                      <select v-model="executorForm.agent_executor" class="settings-input">
                        <option value="langgraph">内置 LangGraph ReAct</option>
                        <option value="aiops_cli">aiops_cli 子进程</option>
                        <option value="external_cli">外部 Agent CLI</option>
                      </select>
                    </div>
                    <div class="sb-field">
                      <label class="sb-label">超时时间（秒）</label>
                      <input v-model.number="executorForm.agent_external_timeout" type="number" min="30" class="settings-input" />
                    </div>
                  </div>
                </div>
                <div v-if="executorForm.agent_executor === 'external_cli'" class="sb-group">
                  <div class="sb-group-title">外部 CLI 配置</div>
                  <div class="sb-field-row">
                    <div class="sb-field">
                      <label class="sb-label">CLI 命令</label>
                      <input v-model="executorForm.agent_external_command" class="settings-input mono"
                        placeholder="claude 或完整路径" />
                    </div>
                    <div class="sb-field">
                      <label class="sb-label">CLI 参数</label>
                      <input v-model="executorForm.agent_external_args" class="settings-input mono" placeholder="-p" />
                    </div>
                  </div>
                  <div class="sb-field">
                    <label class="sb-label">工作目录</label>
                    <input v-model="executorForm.agent_external_workdir" class="settings-input mono"
                      placeholder="留空使用项目根目录" />
                  </div>
                  <div class="sb-field sb-checkbox-field">
                    <label class="sb-checkbox">
                      <input type="checkbox" v-model="executorForm.agent_external_use_stdin" />
                      <span>通过 stdin 传入问题（否则作为最后一个参数）</span>
                    </label>
                  </div>
                </div>
                <div class="sb-actions">
                  <button class="primary-btn" type="button" @click="saveExecutorConfig" :disabled="executorSaving">
                    {{ executorSaving ? '保存中...' : '保存配置' }}
                  </button>
                  <span v-if="executorMsg" class="sb-msg ok">{{ executorMsg }}</span>
                </div>
              </div>

              <!-- 工作目录 Tab -->
              <div v-else-if="settingsTab === 'workspace'" class="settings-scroll">
                <div class="settings-block">
                  <label>当前工作目录</label>
                  <input v-model.trim="manualPath" class="settings-input mono" type="text" placeholder="例如 D:\code\my-project">
                  <div class="settings-actions">
                    <button class="primary-btn" type="button" :disabled="busyStates.workspace || !manualPath.trim()" @click="applyManualPath">
                      {{ busyStates.workspace ? '应用中...' : '应用目录' }}
                    </button>
                    <button class="ghost-btn" type="button" :disabled="busyStates.reloading" @click="reloadWorkspace">
                      {{ busyStates.reloading ? '刷新中...' : '重新发现' }}
                    </button>
                  </div>
                </div>

                <div class="settings-block">
                  <label>已发现根目录</label>
                  <div class="settings-chip-list">
                    <span v-for="root in workspaceRoots" :key="root.path" class="settings-chip mono">
                      {{ root.path }}
                    </span>
                  </div>
                </div>
              </div>

              <div v-else-if="settingsTab === 'mcp'" class="settings-scroll">
                <div v-for="mcp in mcpList" :key="mcp.id" class="setting-item">
                  <div class="setting-copy">
                    <div class="setting-headline">
                      <strong>{{ mcp.name }}</strong>
                      <span class="status-pill" :class="mcp.enabled ? 'enabled' : 'muted'">
                        {{ mcp.enabled ? '已启用' : '已停用' }}
                      </span>
                      <span class="status-pill" :class="getMcpStatusClass(mcp)">
                        {{ getMcpStatusText(mcp) }}
                      </span>
                    </div>
                    <span>{{ mcp.type }} · {{ mcp.url }}</span>
                  </div>
                  <div class="setting-actions">
                    <button class="ghost-mini" type="button" :disabled="busyStates.pinging[mcp.id] || busyStates.mcps[mcp.id]" @click="pingMcp(mcp)">
                      {{ busyStates.pinging[mcp.id] ? '探测中...' : '探测' }}
                    </button>
                    <button
                      class="switch-btn"
                      :class="{ active: mcp.enabled, pending: busyStates.mcps[mcp.id] }"
                      :disabled="busyStates.mcps[mcp.id] || busyStates.pinging[mcp.id]"
                      type="button"
                      @click="toggleMcp(mcp)"
                    >
                      <span class="switch-thumb"></span>
                    </button>
                  </div>
                </div>
              </div>

              <div v-else class="settings-scroll">
                <div v-for="skill in skillList" :key="skill.id" class="setting-item">
                  <div class="setting-copy">
                    <div class="setting-headline">
                      <strong>{{ skill.name }}</strong>
                      <span class="status-pill" :class="skill.enabled ? 'enabled' : 'muted'">
                        {{ skill.enabled ? '已启用' : '已停用' }}
                      </span>
                    </div>
                    <span>{{ skill.desc }}</span>
                  </div>
                  <button
                    class="switch-btn"
                    :class="{ active: skill.enabled, pending: busyStates.skills[skill.id] }"
                    :disabled="busyStates.skills[skill.id]"
                    type="button"
                    @click="toggleSkill(skill)"
                  >
                    <span class="switch-thumb"></span>
                  </button>
                </div>
              </div>
            </section>
          </div>
        </div>
      </Transition>
    </teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../api/index.js'
import { fetchHealthStatus, getAiModelShort } from '../composables/useHealthStatus.js'
import { safeRandomUUID } from '../utils/uuid.js'

/** 与 AIAgent.vue 同款 fetch 封装，携带 Cookie、抛出带 detail 的错误 */
async function apiFetch(url, options = {}) {
  const resp = await fetch(url, { credentials: 'include', ...options })
  const text = await resp.text()
  let data = null
  if (text) {
    try { data = JSON.parse(text) } catch { data = text }
  }
  if (!resp.ok) {
    const detail = (data && typeof data === 'object' && data.detail)
      || (typeof data === 'string' && data)
      || `HTTP ${resp.status}`
    throw new Error(detail)
  }
  return data
}

const SETTINGS_TABS = [
  { key: 'models',   label: '大模型',   icon: '◈', title: '大模型',   desc: '管理 API 配置以访问模型。' },
  { key: 'general',  label: '通用',     icon: '≡', title: '通用',     desc: '工作台行为与对话参数。' },
  { key: 'executor', label: '执行器',   icon: '⚙', title: '执行器',   desc: '配置 Agent 执行模式与超时策略。' },
  { key: 'mcp',      label: 'MCP',     icon: '⇄', title: 'MCP 工具', desc: '控制工作台可用的 MCP 连接与在线状态。' },
  { key: 'skills',   label: 'Skills',  icon: '✦', title: 'Skills',   desc: '启停当前工作台可调用的技能工具。' },
  { key: 'workspace',label: '工作目录', icon: '⌂', title: '工作目录', desc: '自动发现 Claude 最近工作区，也支持手动切换目录。' },
]

const loading = ref(true)
const streaming = ref(false)
const loadError = ref('')
const searchText = ref('')
const inputText = ref('')
const manualPath = ref('')
const aiModelShort = ref('AI')
const settingsOpen = ref(false)
const settingsTab = ref('models')
const selectedPath = ref('')
const messages     = ref([])
const inputRef     = ref(null)
const bottomRef    = ref(null)

// ── 项目 + 历史对话 ────────────────────────────────────────────────────────────
const expandedProjects = ref(new Set())          // 展开的项目 path
const projectConvsMap  = ref({})                 // { projectPath: [conv,...] }
const loadingConvs     = ref(new Set())          // 正在加载的项目 path
const activeConvId     = ref('')                 // 当前加载的历史对话 ID

function projectConvs(path) {
  return projectConvsMap.value[path] || []
}

async function toggleProject(project) {
  const path = project.path
  const s = new Set(expandedProjects.value)
  if (s.has(path)) {
    s.delete(path)
    expandedProjects.value = s
    return
  }
  s.add(path)
  expandedProjects.value = s

  // 选中该项目
  if (selectedPath.value !== path) {
    selectProject(project)
  }
  // 加载该项目的历史对话
  await fetchProjectConvs(path)
}

async function fetchProjectConvs(path) {
  if (loadingConvs.value.has(path)) return
  const ls = new Set(loadingConvs.value)
  ls.add(path)
  loadingConvs.value = ls
  try {
    const r = await apiFetch(`/api/agent/conversations?project_path=${encodeURIComponent(path)}`)
    if (Array.isArray(r)) {
      projectConvsMap.value = { ...projectConvsMap.value, [path]: r }
    }
  } catch {}
  finally {
    const ls2 = new Set(loadingConvs.value)
    ls2.delete(path)
    loadingConvs.value = ls2
  }
}

async function loadConversation(project, conv) {
  if (selectedPath.value !== project.path) selectProject(project)
  activeConvId.value = conv.conv_id
  try {
    const r = await apiFetch(`/api/agent/conversations/${conv.conv_id}`)
    messages.value = (r.messages || []).map((m, i) => ({
      id:      i,
      role:    m.role,
      content: typeof m.content === 'string' ? m.content : JSON.stringify(m.content),
      toolCalls: [],
    }))
    // 同步 convId 让后续发消息继续追加到该会话
    if (window._setWorkbenchConvId) window._setWorkbenchConvId(conv.conv_id)
  } catch {}
}

function newSessionForProject(project) {
  if (selectedPath.value !== project.path) selectProject(project)
  resetConversation()
}

function newSessionGlobal() {
  activeConvId.value = ''
  resetConversation()
}

async function deleteConv(conv) {
  try {
    await apiFetch(`/api/agent/conversations/${conv.conv_id}`, { method: 'DELETE' })
    // 从各项目列表中移除
    const updated = {}
    for (const [path, list] of Object.entries(projectConvsMap.value)) {
      updated[path] = list.filter(c => c.conv_id !== conv.conv_id)
    }
    projectConvsMap.value = updated
    if (activeConvId.value === conv.conv_id) {
      activeConvId.value = ''
      messages.value = []
    }
  } catch {}
}

// 保存对话时附带 project_path
function getCurrentConvSavePayload(msgs) {
  return {
    mode:         'workbench',
    title:        msgs[0]?.content?.slice(0, 60) || '未命名对话',
    messages:     msgs,
    project_path: selectedPath.value || '',
  }
}
const toast = reactive({
  text: '',
  type: 'info',
})

const workspaceData = reactive({
  roots: [],
  projects: [],
  selected_path: '',
  source_summary: {},
})

const assistantConfig = reactive({
  home_dir: '',
})

const modelOptions = ref([])
const mcpList = ref([])
const skillList = ref([])
const busyStates = reactive({
  workspace: false,
  reloading: false,
  modelId: '',
  pinging: {},
  mcps: {},
  skills: {},
})

// ── 工作台内联模型编辑 ─────────────────────────────────────────────────────
const wbEditModelId   = ref(null)
const wbEditSaving    = ref(false)
const wbEditMsg       = ref('')
const wbEditOk        = ref(false)
const wbEditForm      = reactive({
  name: '', provider: '', runtime_provider: 'openai',
  runtime_model: '', base_url: '', wire_api: '',
  enable_thinking: false, api_key: '',
})

function isLocalModelWb(model) {
  const p = (model?.runtime_provider || model?.provider || '').toLowerCase()
  return p === 'openai' || p === 'local' || p === 'ollama'
}

function openWbEditModel(model) {
  wbEditModelId.value = model.id
  wbEditMsg.value     = ''
  Object.assign(wbEditForm, {
    name:             model.name             || '',
    provider:         model.provider         || '',
    runtime_provider: model.runtime_provider || 'openai',
    runtime_model:    model.runtime_model    || '',
    base_url:         model.base_url         || '',
    wire_api:         model.wire_api         || '',
    enable_thinking:  !!model.enable_thinking,
    api_key:          '',
  })
}

async function saveWbEditModel(model) {
  if (!wbEditForm.runtime_model.trim()) {
    wbEditMsg.value = 'Model ID 不能为空'; wbEditOk.value = false; return
  }
  wbEditSaving.value = true; wbEditMsg.value = ''
  try {
    await api.updateAgentModel(model.id, {
      name:             wbEditForm.name.trim()          || undefined,
      provider:         wbEditForm.provider.trim()      || undefined,
      runtime_provider: wbEditForm.runtime_provider,
      runtime_model:    wbEditForm.runtime_model.trim() || undefined,
      base_url:         wbEditForm.base_url.trim()      || undefined,
      wire_api:         wbEditForm.wire_api              || undefined,
      enable_thinking:  wbEditForm.runtime_provider === 'openai' ? !!wbEditForm.enable_thinking : false,
      api_key:          wbEditForm.api_key.trim()       || undefined,
    })
    // 刷新模型列表
    const r = await api.listAgentModels()
    modelOptions.value = r?.data || []
    wbEditMsg.value = '保存成功'; wbEditOk.value = true
    setTimeout(() => { wbEditModelId.value = null; wbEditMsg.value = '' }, 1200)
  } catch (e) {
    wbEditMsg.value = '保存失败: ' + e; wbEditOk.value = false
  } finally { wbEditSaving.value = false }
}

// ── 停止生成 ──────────────────────────────────────────────────────────────────
let _stopController: AbortController | null = null

function stopStreaming() {
  _stopController?.abort()
  streaming.value = false
}

// ── Token 用量统计 ─────────────────────────────────────────────────────────────
const lastTokenUsage = ref<{ input_tokens: number; output_tokens: number } | null>(null)

// ── 文件改动面板 ──────────────────────────────────────────────────────────────
const showChangesPanel = ref(false)
const changedFiles     = ref<{ file: string; status: string; xy: string }[]>([])
const gitBranch        = ref('')
const gitLoading       = ref(false)
const diffFile         = ref('')
const diffContent      = ref('')

function toggleChangesPanel() {
  showChangesPanel.value = !showChangesPanel.value
  if (showChangesPanel.value && selectedPath.value) refreshGitStatus()
}

async function refreshGitStatus() {
  if (!selectedPath.value || gitLoading.value) return
  gitLoading.value = true
  diffFile.value = ''; diffContent.value = ''
  try {
    const r = await api.agentGitStatus(selectedPath.value)
    if (r.ok) {
      changedFiles.value = r.files || []
      gitBranch.value    = r.branch || ''
    }
  } catch {}
  finally { gitLoading.value = false }
}

async function loadDiff(file: string) {
  diffFile.value = file; diffContent.value = ''
  try {
    const r = await api.agentGitDiff(selectedPath.value, file)
    if (r.ok) diffContent.value = r.diff || '（无差异）'
  } catch {}
}

function highlightDiff(text: string): string {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^(\+[^+].*)$/mg, '<span class="diff-add">$1</span>')
    .replace(/^(-[^-].*)$/mg, '<span class="diff-del">$1</span>')
    .replace(/^(@@.+@@)$/mg, '<span class="diff-hunk">$1</span>')
    .replace(/^(diff --git.*)$/mg, '<span class="diff-header">$1</span>')
}

// 对话完成后自动刷新文件改动
function afterStreamDone() {
  if (showChangesPanel.value && selectedPath.value) {
    setTimeout(refreshGitStatus, 500)
  }
}

// ── 执行器切换（LangGraph / Claude Code 等） ──────────────────────────────────
// '' = 跟随系统设置，'langgraph' = 内置，'external_cli' = Claude Code
const wbExecutor        = ref('')
const availableExecutors = ref([])
const detectingExecutors = ref(false)

async function detectExecutors() {
  detectingExecutors.value = true
  try {
    const r = await apiFetch('/api/agent/executors/detect')
    availableExecutors.value = r?.executors || []
  } catch {}
  finally { detectingExecutors.value = false }
}

const claudeAvailable = computed(() =>
  availableExecutors.value.find(e => e.cmd === 'claude')?.available === true
)
const currentExecutorLabel = computed(() => {
  if (!wbExecutor.value) return '系统默认'
  if (wbExecutor.value === 'langgraph') return 'LangGraph'
  if (wbExecutor.value === 'external_cli') {
    const found = availableExecutors.value.find(e => e.available && e.cmd)
    return found ? found.name : 'External CLI'
  }
  return wbExecutor.value
})

// ── 通用配置 & 执行器（工作台本地状态） ──────────────────────────────────────
const generalForm = reactive({
  home_dir:     '',
  max_turns:    20,
  stream:       true,
  confirm_mode: 'ask',
})
const executorForm = reactive({
  agent_executor:         'langgraph',
  agent_external_timeout: 240,
  agent_external_command: '',
  agent_external_args:    '-p',
  agent_external_workdir: '',
  agent_external_use_stdin: false,
})
const generalSaving  = ref(false)
const generalMsg     = ref('')
const executorSaving = ref(false)
const executorMsg    = ref('')

async function saveGeneralConfig() {
  generalSaving.value = true; generalMsg.value = ''
  try {
    await api.saveAgentConfig({
      home_dir:     generalForm.home_dir.trim(),
      max_turns:    Number(generalForm.max_turns) || 20,
      stream:       generalForm.stream,
      confirm_mode: generalForm.confirm_mode,
    })
    generalMsg.value = '已保存'
    if (generalForm.home_dir.trim()) {
      selectedPath.value = generalForm.home_dir.trim()
      manualPath.value   = generalForm.home_dir.trim()
    }
    setTimeout(() => { generalMsg.value = '' }, 1500)
  } catch (e) { generalMsg.value = '保存失败: ' + e }
  finally { generalSaving.value = false }
}

async function saveExecutorConfig() {
  executorSaving.value = true; executorMsg.value = ''
  try {
    await api.saveSettings({
      agent_executor:           executorForm.agent_executor,
      agent_external_timeout:   Number(executorForm.agent_external_timeout) || 240,
      agent_external_command:   executorForm.agent_external_command.trim(),
      agent_external_args:      executorForm.agent_external_args.trim(),
      agent_external_workdir:   executorForm.agent_external_workdir.trim(),
      agent_external_use_stdin: executorForm.agent_external_use_stdin,
    })
    executorMsg.value = '已保存'
    setTimeout(() => { executorMsg.value = '' }, 1500)
  } catch (e) { executorMsg.value = '保存失败: ' + e }
  finally { executorSaving.value = false }
}

async function loadGeneralAndExecutor() {
  try {
    const cfg = await api.getAgentConfig()
    const basic = cfg?.basic || {}
    Object.assign(generalForm, {
      home_dir:     basic.home_dir     || '',
      max_turns:    basic.max_turns    ?? 20,
      stream:       basic.stream       ?? true,
      confirm_mode: basic.confirm_mode || 'ask',
    })
  } catch {}
  try {
    const s = await api.getSettings()
    Object.assign(executorForm, {
      agent_executor:           s?.agent_executor           || 'langgraph',
      agent_external_timeout:   s?.agent_external_timeout   ?? 240,
      agent_external_command:   s?.agent_external_command   || '',
      agent_external_args:      s?.agent_external_args      || '-p',
      agent_external_workdir:   s?.agent_external_workdir   || '',
      agent_external_use_stdin: s?.agent_external_use_stdin ?? false,
    })
  } catch {}
}

const projectSessions = new Map()
let msgId = 0
let currentConvId = genUUID()
let toastTimer = null

// ── 持久化：localStorage 保存当前项目/对话，DB 保存消息 ────────────────────────
const WB_KEY = 'wb:state'

// tabs: { [projectPath]: { convId, title } } — 记录每个项目最近活跃的对话
function saveWbLocal() {
  try {
    const raw = loadWbLocal() || {}
    const tabs = raw.tabs || {}
    if (selectedPath.value && currentConvId) {
      tabs[selectedPath.value] = {
        convId: currentConvId,
        title:  messages.value.find(m => m.role === 'user')?.content?.slice(0, 60) || '',
      }
    }
    localStorage.setItem(WB_KEY, JSON.stringify({
      selectedPath: selectedPath.value,
      convId:       currentConvId,
      tabs,
    }))
  } catch {}
}

function loadWbLocal() {
  try { return JSON.parse(localStorage.getItem(WB_KEY) || 'null') }
  catch { return null }
}

function getTabForProject(path) {
  try { return (loadWbLocal()?.tabs || {})[path] || null }
  catch { return null }
}

async function saveCurrentConvToDB() {
  if (!currentConvId || !messages.value.length) return
  try {
    const serialized = messages.value.map(m => ({
      role:      m.role,
      content:   m.content || '',
      toolCalls: (m.toolCalls || []).map(tc => ({
        tool:   tc.tool,
        input:  tc.input,
        output: tc.output || '',
      })),
    }))
    const title = messages.value.find(m => m.role === 'user')?.content?.slice(0, 60) || '未命名对话'
    await apiFetch(`/api/agent/conversations/${currentConvId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode:         'workbench',
        title,
        messages:     serialized,
        project_path: selectedPath.value || '',
      }),
    })
    // 刷新左侧该项目的历史列表
    if (selectedPath.value) {
      await fetchProjectConvs(selectedPath.value)
    }
  } catch (err) {
    console.warn('[saveCurrentConvToDB] failed:', err)
  }
  saveWbLocal()
}

// selectedPath 变化时更新 localStorage
watch(selectedPath, saveWbLocal)

const workspaceMeta = computed(() => workspaceData.source_summary || {})
const workspaceRoots = computed(() => workspaceData.roots || [])
const activeModel = computed(() => modelOptions.value.find(item => item.active) || modelOptions.value[0] || null)
const activeSettings = computed(() => SETTINGS_TABS.find(item => item.key === settingsTab.value) || SETTINGS_TABS[0])
const modelBadgeText = computed(() => activeModel.value?.name || aiModelShort.value || 'AI')
const providerBadgeText = computed(() => activeModel.value?.provider || aiModelShort.value || 'Provider')
const currentHomeText = computed(() => shortenPath(selectedPath.value || assistantConfig.home_dir) || '未设置')

const filteredProjects = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  const list = workspaceData.projects || []
  if (!keyword) return list
  return list.filter(project => {
    const haystack = [
      project.name,
      project.path,
      project.summary,
      ...(project.stack_labels || []),
      ...(project.marker_files || []),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(keyword)
  })
})

const selectedProject = computed(() => {
  return (workspaceData.projects || []).find(item => item.path === selectedPath.value) || null
})

const quickPrompts = computed(() => {
  const project = selectedProject.value
  if (!project) return []
  const prompts = [...(project.quick_prompts || [])]
  prompts.push(`请梳理 ${project.name} 的目录结构、模块职责和关键配置文件。`)
  prompts.push(`请识别 ${project.name} 的启动入口、构建命令和本地开发流程。`)
  prompts.push(`请为 ${project.name} 制定一个最小可执行的开发接手计划。`)
  return prompts.slice(0, 6)
})

// Open Design 风格 Starter Cards（点击填入 Composer，不立即发送）
const starterCards = computed(() => {
  const p = selectedProject.value
  if (!p) return []
  const name = p.name
  const stack = p.stack_labels?.join('、') || '未知技术栈'
  return [
    { icon: '▦', title: '项目扫描',    tag: 'Onboarding',  prompt: `请全面扫描 ${name} 项目，梳理目录结构、技术栈（${stack}）、核心模块、关键配置文件，以及各目录的职责分工。` },
    { icon: '⌘', title: '启动分析',    tag: 'DevFlow',     prompt: `请分析 ${name} 项目的启动方式、入口文件、构建命令、环境变量配置，以及本地开发的完整流程。` },
    { icon: '◈', title: '接手计划',    tag: 'Takeover',    prompt: `请为 ${name} 制定一个最小可执行的开发接手计划：包括阅读顺序、高风险模块、关键依赖和建议的第一步改动。` },
    { icon: '⚡', title: '问题诊断',    tag: 'Debug',       prompt: `当前 ${name} 项目遇到了问题，请帮我逐步排查。先列出可能的原因分类，再给出对应的诊断命令。` },
    { icon: '✦', title: '代码审查',    tag: 'Review',      prompt: `请对 ${name} 项目的核心代码进行审查，重点关注：安全风险、性能瓶颈、代码质量问题和可以立即改进的点。` },
    { icon: '◉', title: '文档生成',    tag: 'Docs',        prompt: `请为 ${name} 项目生成一份完整的技术文档，包括：架构说明、API 清单、部署指南和贡献者指南。` },
  ]
})

function fillComposer(prompt) {
  inputText.value = prompt
  // 聚焦到输入框，让用户可以直接修改或发送
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.focus()
      autoResize({ target: inputRef.value })
    }
  })
}

const currentHintText = computed(() => {
  const hints = selectedProject.value?.command_hints || []
  return hints.length ? hints.join(' · ') : '建议先执行项目扫描，识别入口和运行方式'
})

function genUUID() {
  return safeRandomUUID()
}

function shortenPath(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const normalized = raw.replace(/\\/g, '/')
  const parts = normalized.split('/').filter(Boolean)
  if (parts.length <= 2) return raw
  return `.../${parts.slice(-2).join('/')}`
}

function formatSource(value) {
  const source = String(value || '')
  if (source.includes('agent_config')) return '当前配置'
  if (source.includes('current_repo')) return '当前仓库'
  if (source.includes('claude_projects')) return 'Claude 最近项目'
  if (source.includes('claude_settings_root')) return 'Claude 根目录'
  if (source.includes('claude_root_scan')) return '根目录扫描'
  return source || '本地来源'
}

function formatTime(value) {
  if (!value) return '最近未记录'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '最近未记录'
  const diffMs = Date.now() - date.getTime()
  const diffHours = Math.floor(diffMs / 3600000)
  if (diffHours <= 0) return '刚刚使用'
  if (diffHours < 24) return `${diffHours} 小时前`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 7) return `${diffDays} 天前`
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function getErrorText(error, fallback = '操作失败') {
  if (typeof error === 'string') return error
  if (typeof error?.detail === 'string') return error.detail
  if (error?.message) return error.message
  return fallback
}

function showToast(text, type = 'info', ms = 2400) {
  if (toastTimer) clearTimeout(toastTimer)
  toast.text = String(text || '').trim()
  toast.type = type
  if (!toast.text) return
  toastTimer = setTimeout(() => {
    toast.text = ''
    toast.type = 'info'
  }, ms)
}

function setPending(map, key, value) {
  if (!key) return
  if (value) map[key] = true
  else delete map[key]
}

function getMcpStatusText(mcp) {
  if (mcp?.ok === true) return '在线'
  if (mcp?.ok === false) return '离线'
  return '未探测'
}

function getMcpStatusClass(mcp) {
  if (mcp?.ok === true) return 'ok'
  if (mcp?.ok === false) return 'down'
  return 'muted'
}

function autoResize(event) {
  const el = event.target
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 180)}px`
}

function scrollToBottom() {
  nextTick(() => {
    bottomRef.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

function formatInput(input) {
  if (!input || typeof input !== 'object') return ''
  return Object.entries(input)
    .filter(([, value]) => value !== '' && value !== null && value !== undefined)
    .slice(0, 3)
    .map(([key, value]) => `${key}=${typeof value === 'string' ? value : JSON.stringify(value)}`)
    .join(' · ')
}

function renderContent(text) {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/^(\d+)\.\s+(.+)$/gm, '<div class="md-row"><span class="md-index">$1</span>$2</div>')
  html = html.replace(/^[-*]\s+(.+)$/gm, '<div class="md-row"><span class="md-dot"></span>$1</div>')
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>')
  html = html.replace(/## (.+?)(\n|$)/g, '<div class="md-title">$1</div>')
  html = html.replace(/\n/g, '<br>')
  return html
}

function getRuntimeProvider(model) {
  const runtimeProvider = String(model?.runtime_provider || '').trim().toLowerCase()
  if (runtimeProvider) return runtimeProvider
  const provider = String(model?.provider || '').trim().toLowerCase()
  return provider === 'anthropic' ? 'anthropic' : 'openai'
}

function getRuntimeModel(model) {
  return String(model?.runtime_model || model?.name || '').trim()
}

function openSettings(tab = 'models') {
  settingsTab.value = tab
  settingsOpen.value = true
  loadGeneralAndExecutor()
}

function ensureProjectSession(path) {
  const key = String(path || '').trim()
  if (!key) return null
  if (!projectSessions.has(key)) {
    projectSessions.set(key, {
      convId: genUUID(),
      messages: [],
    })
  }
  return projectSessions.get(key)
}

function loadProjectSession(path) {
  const session = ensureProjectSession(path)
  if (!session) {
    messages.value = []
    currentConvId = genUUID()
    return
  }
  currentConvId = session.convId
  messages.value = session.messages
  scrollToBottom()
}

async function refreshHealth() {
  try {
    const result = await fetchHealthStatus()
    aiModelShort.value = getAiModelShort(result.ai_provider || '')
  } catch {
    aiModelShort.value = 'AI'
  }
}

function syncModels(config) {
  modelOptions.value = (config?.models || []).map(item => ({ ...item }))
}

function syncConfigCollections(config) {
  mcpList.value = (config?.mcps || []).map(item => ({ ...item }))
  skillList.value = (config?.skills || []).map(item => ({ ...item }))
}

function syncWorkspaceSelection(preferredPath = '') {
  const allProjects = workspaceData.projects || []
  const nextPath =
    preferredPath ||
    selectedPath.value ||
    assistantConfig.home_dir ||
    workspaceData.selected_path ||
    allProjects[0]?.path ||
    ''

  selectedPath.value = nextPath
  manualPath.value = nextPath
  loadProjectSession(nextPath)
}

async function loadWorkbench({ preserveSelection = true } = {}) {
  loading.value = true
  loadError.value = ''
  let ok = false
  try {
    const [config, discovery] = await Promise.all([
      api.getAgentConfig(),
      api.discoverAgentWorkspace(),
      refreshHealth(),
    ])

    assistantConfig.home_dir = String(config?.basic?.home_dir || '').trim()
    workspaceData.roots = discovery?.roots || []
    workspaceData.projects = discovery?.projects || []
    workspaceData.selected_path = discovery?.selected_path || ''
    workspaceData.source_summary = discovery?.source_summary || {}

    syncModels(config)
    syncConfigCollections(config)
    syncWorkspaceSelection(preserveSelection ? selectedPath.value || assistantConfig.home_dir : assistantConfig.home_dir)
    ok = true
  } catch (error) {
    loadError.value = getErrorText(error, '工作台初始化失败')
  } finally {
    loading.value = false
  }
  return ok
}

async function reloadWorkspace() {
  if (streaming.value || busyStates.reloading) return
  busyStates.reloading = true
  try {
    const ok = await loadWorkbench({ preserveSelection: true })
    if (ok) showToast('项目发现已刷新', 'success')
    else showToast(loadError.value || '项目发现刷新失败', 'error', 3200)
  } finally {
    busyStates.reloading = false
  }
}

function markActiveProject(path) {
  const next = String(path || '').trim()
  workspaceData.projects = (workspaceData.projects || []).map(project => ({
    ...project,
    active: project.path === next,
  }))
}

async function saveHomeDir(path) {
  const next = String(path || '').trim()
  await api.saveAgentConfig({ home_dir: next })
  assistantConfig.home_dir = next
  markActiveProject(next)
}

async function selectProject(project) {
  if (!project?.path || streaming.value) return
  const previousPath = selectedPath.value
  selectedPath.value = project.path
  manualPath.value = project.path
  // 自动展开该项目（如果还没展开）
  const s = new Set(expandedProjects.value)
  if (!s.has(project.path)) {
    s.add(project.path)
    expandedProjects.value = s
    await fetchProjectConvs(project.path)
  }
  loadProjectSession(project.path)

  // 恢复该项目上次打开的对话（tabs 机制）
  const tab = getTabForProject(project.path)
  if (tab?.convId && tab.convId !== currentConvId) {
    const convList = projectConvs(project.path)
    const savedConv = convList.find(c => c.conv_id === tab.convId)
    if (savedConv) {
      await loadConversation(project, savedConv)
    } else {
      // 对话 ID 存在但 DB 里暂时没有（新会话），复用该 convId
      currentConvId = tab.convId
    }
  }
  try {
    await saveHomeDir(project.path)
    showToast(`已切换到 ${project.name}`, 'success')
  } catch (error) {
    selectedPath.value = previousPath
    manualPath.value = previousPath
    loadProjectSession(previousPath)
    showToast(`切换项目失败：${getErrorText(error)}`, 'error', 3200)
  }
}

async function applyManualPath() {
  const path = manualPath.value.trim()
  if (!path || streaming.value || busyStates.workspace) return
  const previousPath = selectedPath.value
  const previousManualPath = manualPath.value
  busyStates.workspace = true
  try {
    if (!projectSessions.has(path)) {
      projectSessions.set(path, {
        convId: genUUID(),
        messages: [],
      })
    }
    selectedPath.value = path
    loadProjectSession(path)
    await saveHomeDir(path)

    if (!(workspaceData.projects || []).some(item => item.path === path)) {
      workspaceData.projects = [
        {
          id: path.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'manual-workspace',
          name: path.split(/[\\/]/).filter(Boolean).pop() || path,
          path,
          source: 'agent_config',
          summary: '手动指定的工作目录',
          stack_labels: [],
          marker_files: [],
          top_level_dirs: [],
          command_hints: [],
          quick_prompts: [
            '请扫描这个目录并识别项目结构。',
            '请识别启动方式和依赖安装步骤。',
            '请分析主要入口和开发改动点。',
          ],
          active: true,
        },
        ...(workspaceData.projects || []).map(item => ({ ...item, active: false })),
      ]
    }
    showToast(`工作目录已应用：${path}`, 'success')
  } catch (error) {
    selectedPath.value = previousPath
    manualPath.value = previousManualPath
    loadProjectSession(previousPath)
    showToast(`应用目录失败：${getErrorText(error)}`, 'error', 3200)
  } finally {
    busyStates.workspace = false
  }
}

async function activateModel(modelId) {
  if (!modelId || streaming.value || busyStates.modelId) return
  const targetModel = modelOptions.value.find(model => model.id === modelId)
  if (targetModel?.active) {
    showToast(`${targetModel.name} 已是当前模型`)
    return
  }
  busyStates.modelId = modelId
  try {
    await api.setAgentActiveModel(modelId)
    modelOptions.value = modelOptions.value.map(model => ({
      ...model,
      active: model.id === modelId,
    }))
    showToast(`已切换到 ${targetModel?.name || modelId}`, 'success')
  } catch (error) {
    showToast(`模型切换失败：${getErrorText(error)}`, 'error', 3200)
  } finally {
    busyStates.modelId = ''
  }
}

async function toggleMcp(mcp) {
  if (!mcp?.id || busyStates.mcps[mcp.id]) return
  const previous = !!mcp.enabled
  setPending(busyStates.mcps, mcp.id, true)
  mcp.enabled = !mcp.enabled
  try {
    await api.updateAgentMcp(mcp.id, { enabled: mcp.enabled })
    showToast(`${mcp.name} 已${mcp.enabled ? '启用' : '停用'}`, 'success')
  } catch (error) {
    mcp.enabled = previous
    showToast(`MCP 更新失败：${getErrorText(error)}`, 'error', 3200)
  } finally {
    setPending(busyStates.mcps, mcp.id, false)
  }
}

async function pingMcp(mcp) {
  if (!mcp?.id || busyStates.pinging[mcp.id]) return
  setPending(busyStates.pinging, mcp.id, true)
  try {
    const result = await api.pingAgentMcp(mcp.id)
    mcp.ok = !!result?.ok
    showToast(result?.ok ? `${mcp.name} 连通正常` : `${mcp.name} 无法连通`, result?.ok ? 'success' : 'error', result?.ok ? 2200 : 3200)
  } catch (error) {
    mcp.ok = false
    showToast(`探测失败：${getErrorText(error)}`, 'error', 3200)
  } finally {
    setPending(busyStates.pinging, mcp.id, false)
  }
}

async function toggleSkill(skill) {
  if (!skill?.id || busyStates.skills[skill.id]) return
  const previous = !!skill.enabled
  setPending(busyStates.skills, skill.id, true)
  skill.enabled = !skill.enabled
  try {
    await api.updateAgentSkill(skill.id, { enabled: skill.enabled })
    showToast(`${skill.name} 已${skill.enabled ? '启用' : '停用'}`, 'success')
  } catch (error) {
    skill.enabled = previous
    showToast(`Skill 更新失败：${getErrorText(error)}`, 'error', 3200)
  } finally {
    setPending(busyStates.skills, skill.id, false)
  }
}

function resetConversation() {
  if (!selectedPath.value || streaming.value) return
  const session = {
    convId: genUUID(),
    messages: [],
  }
  projectSessions.set(selectedPath.value, session)
  currentConvId = session.convId
  messages.value = session.messages
  inputText.value = ''
  if (inputRef.value) inputRef.value.style.height = 'auto'
}

function buildQuickPrompt(kind) {
  const project = selectedProject.value
  if (!project) return ''
  if (kind === 'scan') {
    return `请扫描 ${project.path} 这个项目，概括目录结构、技术栈、核心模块和关键配置文件。`
  }
  if (kind === 'entry') {
    return `请分析 ${project.path} 这个项目的启动方式、入口文件、构建命令和本地开发流程。`
  }
  return `请基于 ${project.path} 这个项目，给出一个最小可执行的开发接手计划，包括阅读顺序、关键模块和高风险点。`
}

function sendQuickPrompt(kind) {
  const prompt = buildQuickPrompt(kind)
  if (prompt) sendMessage(prompt)
}

function onSend() {
  const text = inputText.value.trim()
  if (!text || streaming.value || !selectedPath.value) return
  sendMessage(text)
  inputText.value = ''
  if (inputRef.value) inputRef.value.style.height = 'auto'
}

async function sendMessage(text) {
  if (streaming.value || !selectedPath.value) return

  const session = ensureProjectSession(selectedPath.value)
  if (!session) return

  const userMessage = {
    id: ++msgId,
    role: 'user',
    content: text,
  }
  session.messages.push(userMessage)

  const assistantMessage = reactive({
    id: ++msgId,
    role: 'assistant',
    content: '',
    toolCalls: [],
    streaming: true,
    done: false,
  })
  session.messages.push(assistantMessage)

  messages.value = session.messages
  streaming.value = true
  scrollToBottom()

  _stopController = new AbortController()
  try {
    const response = await fetch('/api/agent/chat', {
      method: 'POST',
      credentials: 'include',
      signal: _stopController.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        conv_id: currentConvId,
        home_dir: selectedPath.value,
        executor: wbExecutor.value,   // 执行器覆盖：'' | 'langgraph' | 'external_cli'
        model_id: activeModel.value?.id || '',
        model_name: getRuntimeModel(activeModel.value),
        model_provider: getRuntimeProvider(activeModel.value),
        model_base_url: String(activeModel.value?.base_url || '').trim(),
        model_wire_api: String(activeModel.value?.wire_api || '').trim(),
        model_enable_thinking: !!activeModel.value?.enable_thinking,
      }),
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    if (!response.body) {
      throw new Error('服务端没有返回流式响应')
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let splitIndex = -1
      while ((splitIndex = buffer.indexOf('\n\n')) !== -1) {
        const chunk = buffer.slice(0, splitIndex)
        buffer = buffer.slice(splitIndex + 2)
        for (const line of chunk.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            handleEvent(JSON.parse(line.slice(6)), assistantMessage)
          } catch {
            // ignore malformed events
          }
        }
      }
    }
  } catch (error) {
    assistantMessage.content += `${assistantMessage.content ? '\n\n' : ''}错误：${error.message}`
    assistantMessage.streaming = false
    assistantMessage.done = true
    streaming.value = false
    scrollToBottom()
  }
}

function handleEvent(data, assistantMessage) {
  switch (data.type) {
    case 'token':
      assistantMessage.content += data.text || ''
      scrollToBottom()
      break
    case 'tool_start':
      assistantMessage.toolCalls.push(
        reactive({
          id: ++msgId,
          tool: data.tool || 'tool',
          input: data.input || {},
          output: '',
          pending: true,
          expanded: false,
        }),
      )
      scrollToBottom()
      break
    case 'tool_end': {
      const target = [...assistantMessage.toolCalls].reverse().find(item => item.tool === data.tool && item.pending)
      if (target) {
        target.output = data.output || ''
        target.pending = false
      }
      // 每次工具调用结束后保存一次（防止长对话中途中断丢失）
      saveCurrentConvToDB()
      scrollToBottom()
      break
    }
    case 'replace_content':
      assistantMessage.content = data.text || ''
      scrollToBottom()
      break
    case 'done':
      assistantMessage.streaming = false
      assistantMessage.done = true
      streaming.value = false
      if (data.usage) lastTokenUsage.value = data.usage  // token 统计
      scrollToBottom()
      saveCurrentConvToDB()
      afterStreamDone()   // 刷新文件改动面板
      break
    case 'error':
      assistantMessage.content += `${assistantMessage.content ? '\n\n' : ''}错误：${data.message || '未知错误'}`
      assistantMessage.streaming = false
      assistantMessage.done = true
      streaming.value = false
      scrollToBottom()
      saveCurrentConvToDB()
      afterStreamDone()
      break
  }
}

onMounted(async () => {
  await loadWorkbench({ preserveSelection: false })
  detectExecutors()   // 后台检测可用执行器

  // 恢复上次状态
  const saved = loadWbLocal()
  if (!saved?.selectedPath) return

  // 找到匹配的项目
  const project = (workspaceData.projects || []).find(p => p.path === saved.selectedPath)
  if (!project) return

  // 恢复项目选择
  await selectProject(project)

  // 展开项目并加载历史
  const s = new Set(expandedProjects.value)
  s.add(project.path)
  expandedProjects.value = s
  await fetchProjectConvs(project.path)

  // 恢复上次的对话（先找 DB 里的，找不到就用内存里的）
  if (saved.convId) {
    const convList = projectConvs(project.path)
    const conv = convList.find(c => c.conv_id === saved.convId)
    if (conv) {
      await loadConversation(project, conv)
    } else {
      // DB 里没有（可能是新开的还没保存），恢复 convId 让后续消息追加进去
      currentConvId = saved.convId
    }
  }
})
</script>

<style scoped>
.workbench-page {
  --wb-bg: #edf3fa;
  --wb-shell: #f5f9fd;
  --wb-panel: #fbfdff;
  --wb-paper: #ffffff;
  --wb-border: #d6e1ee;
  --wb-border-strong: #c4d3e5;
  --wb-text: #152132;
  --wb-text-soft: #5c6d83;
  --wb-text-faint: #8393a8;
  --wb-accent: #388bfd;
  --wb-accent-soft: rgba(56, 139, 253, 0.12);
  --wb-accent-line: rgba(56, 139, 253, 0.28);
  --wb-shadow: 0 22px 60px rgba(15, 23, 42, 0.08);
  --wb-font-display: "Segoe UI Variable Display", "PingFang SC", "Microsoft YaHei UI", sans-serif;
  --wb-font-body: "Segoe UI Variable", "PingFang SC", "Microsoft YaHei UI", sans-serif;
  height: 100%;
  overflow: hidden;
  background:
    radial-gradient(circle at top right, rgba(56, 139, 253, 0.12), transparent 24%),
    radial-gradient(circle at left bottom, rgba(17, 184, 166, 0.08), transparent 22%),
    var(--wb-bg);
  color: var(--wb-text);
  font-family: var(--wb-font-body);
}

.workbench-shell {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 18px;
  height: 100%;
  padding: 18px;
}

.project-pane,
.main-pane {
  min-height: 0;
  border: 1px solid var(--wb-border);
  border-radius: 24px;
  overflow: hidden;
  box-shadow: var(--wb-shadow);
}

.project-pane {
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #f8fbfe, #edf4fb);
}

.pane-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 22px 22px 16px;
}

.pane-brand h2,
.main-head h1,
.settings-head h3,
.welcome-doc h3 {
  font-family: var(--wb-font-display);
  font-weight: 700;
  letter-spacing: -0.01em;
}

.pane-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--wb-accent);
}

.pane-brand h2 {
  margin-top: 6px;
  font-size: 27px;
  line-height: 1.1;
}

.pane-brand p,
.main-head-copy p,
.settings-head p,
.welcome-doc p {
  margin-top: 8px;
  color: var(--wb-text-soft);
  font-size: 12.5px;
  line-height: 1.6;
}

.icon-btn,
.primary-btn,
.ghost-btn,
.quick-btn,
.foot-link,
.send-btn,
.close-btn,
.switch-btn,
.ghost-mini,
.settings-nav-item,
.tool-row,
/* ── 项目 + 历史对话树 ── */
.section-title-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 4px 6px;
}
.new-session-global {
  width: 22px; height: 22px; border-radius: 5px; font-size: 16px; line-height: 1;
  border: 1px solid var(--wb-border); background: transparent; cursor: pointer;
  color: var(--wb-text-soft); display: flex; align-items: center; justify-content: center;
}
.new-session-global:hover { background: var(--wb-accent); color: #fff; border-color: var(--wb-accent); }

.project-group { margin-bottom: 4px; border-radius: 8px; overflow: hidden; }

.project-item {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 8px 8px;
  border-radius: 8px; cursor: pointer; font: inherit;
  border: 1px solid transparent;
  background: transparent; transition: background .12s, border-color .12s;
  position: relative;
}
.project-item:hover { background: rgba(0,0,0,.04); }
.project-item.active { background: rgba(59,130,246,.07); border-color: rgba(59,130,246,.2); }

.project-expand-arrow { font-size: 11px; color: var(--wb-text-muted); flex-shrink: 0; width: 12px; }
.project-folder-icon  { font-size: 15px; flex-shrink: 0; }
.project-item-body    { flex: 1; min-width: 0; text-align: left; }
.project-name-row     { display: flex; align-items: center; gap: 6px; }
.project-name         { font-size: 13px; font-weight: 600; color: var(--wb-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.project-path         { font-size: 10px; color: var(--wb-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 1px; }

.proj-new-btn {
  flex-shrink: 0; opacity: 0; width: 22px; height: 22px;
  border-radius: 5px; border: 1px solid var(--wb-border); background: transparent;
  cursor: pointer; font-size: 15px; line-height: 1; color: var(--wb-text-soft);
  display: flex; align-items: center; justify-content: center; transition: opacity .12s;
}
.project-item:hover .proj-new-btn { opacity: 1; }
.proj-new-btn:hover { background: var(--wb-accent); color: #fff; border-color: var(--wb-accent); }

/* 历史对话列表 */
.conv-list    { padding: 2px 0 4px 28px; display: flex; flex-direction: column; gap: 1px; }
.conv-loading { font-size: 11px; color: var(--wb-text-muted); padding: 4px 8px; }
.conv-empty   { font-size: 11px; color: var(--wb-text-muted); padding: 4px 8px; font-style: italic; }

.conv-item {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 5px 8px; border-radius: 6px;
  border: none; background: transparent; cursor: pointer; font: inherit;
  text-align: left; transition: background .1s; position: relative;
}
.conv-item:hover { background: rgba(0,0,0,.05); }
.conv-item.active { background: rgba(59,130,246,.1); }
.conv-icon     { font-size: 12px; flex-shrink: 0; }
.conv-item-body{ flex: 1; min-width: 0; }
.conv-title    { display: block; font-size: 12px; color: var(--wb-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-time     { display: block; font-size: 10px; color: var(--wb-text-muted); margin-top: 1px; }
.conv-del-btn  {
  opacity: 0; flex-shrink: 0; width: 18px; height: 18px; border-radius: 4px;
  border: none; background: transparent; cursor: pointer; font-size: 13px; color: var(--wb-text-muted);
  display: flex; align-items: center; justify-content: center; transition: opacity .1s;
}
.conv-item:hover .conv-del-btn { opacity: 1; }
.conv-del-btn:hover { background: rgba(239,68,68,.1); color: #ef4444; }

.project-item {
  font: inherit;
}

.icon-btn,
.ghost-btn,
.ghost-mini,
.quick-btn,
.foot-link {
  border: 1px solid var(--wb-border);
  background: rgba(255, 255, 255, 0.76);
  color: var(--wb-text-soft);
}

.icon-btn,
.primary-btn,
.ghost-btn,
.quick-btn,
.send-btn,
.ghost-mini {
  border-radius: 12px;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease, color 0.18s ease;
}

.icon-btn,
.ghost-mini {
  padding: 9px 12px;
}

.primary-btn,
.send-btn {
  border: 1px solid var(--wb-accent);
  background: linear-gradient(135deg, var(--wb-accent), #2563eb);
  color: #fff;
}

.primary-btn,
.ghost-btn,
.quick-btn {
  padding: 10px 14px;
}

.icon-btn:hover,
.primary-btn:hover,
.ghost-btn:hover,
.quick-btn:hover,
.send-btn:hover,
.ghost-mini:hover,
.foot-link:hover,
.settings-nav-item:hover,
.tool-row:hover,
.project-item:hover {
  transform: translateY(-1px);
}

.pane-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 0 22px 14px;
}

.summary-cell {
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(56, 139, 253, 0.12);
  background: rgba(255, 255, 255, 0.72);
}

.summary-cell span,
.project-source,
.context-label,
.query-label,
.composer-foot,
.project-foot,
.settings-caption {
  font-size: 11px;
  color: var(--wb-text-faint);
}

.summary-cell strong {
  display: block;
  margin-top: 4px;
  font-size: 22px;
  color: var(--wb-text);
}

.pane-search,
.pane-manual {
  padding: 0 22px;
}

.search-input,
.manual-input,
.settings-input,
.composer-input {
  width: 100%;
  border-radius: 14px;
  border: 1px solid var(--wb-border);
  background: rgba(255, 255, 255, 0.88);
  color: var(--wb-text);
  outline: none;
  transition: border-color 0.18s ease, box-shadow 0.18s ease;
}

.search-input,
.manual-input,
.settings-input {
  height: 42px;
  padding: 0 14px;
}

.search-input:focus,
.manual-input:focus,
.settings-input:focus,
.composer-input:focus {
  border-color: var(--wb-accent-line);
  box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.08);
}

.load-error {
  margin: 12px 22px 0;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(203, 59, 48, 0.18);
  background: rgba(203, 59, 48, 0.08);
  color: #b13c33;
  font-size: 12px;
}

.section-title {
  padding: 16px 22px 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--wb-text-faint);
}

.section-title.compact {
  padding: 0 0 10px;
}

.project-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0 22px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.project-item {
  width: 100%;
  text-align: left;
  padding: 14px 14px 12px;
  border: 1px solid var(--wb-border);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.66);
  color: inherit;
}

.project-item.active {
  border-color: var(--wb-accent-line);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: inset 0 0 0 1px rgba(56, 139, 253, 0.08);
}

.project-head,
.project-name-wrap,
.project-foot,
.manual-actions,
.main-head,
/* 执行器切换 */
.executor-switch {
  display: flex; align-items: center; gap: 4px;
  background: rgba(255,255,255,.7); border: 1px solid var(--wb-border);
  border-radius: 10px; padding: 3px 8px 3px 6px;
  transition: border-color .15s;
}
.executor-switch.exec-claude {
  border-color: rgba(56,139,253,.4);
  background: rgba(56,139,253,.06);
}
.exec-label { font-size: 10px; color: var(--wb-text-soft); font-weight: 600;
  text-transform: uppercase; letter-spacing: .06em; margin-right: 2px; }
.exec-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 10px; border-radius: 7px; font-size: 12px; font-weight: 500;
  border: 1px solid transparent; background: transparent;
  color: var(--wb-text-soft); cursor: pointer; transition: all .12s;
}
.exec-btn:hover { background: rgba(0,0,0,.05); color: var(--wb-text); }
.exec-btn.active { background: #fff; border-color: var(--wb-border); color: var(--wb-text);
  box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.exec-claude-btn.active { background: rgba(56,139,253,.12); border-color: rgba(56,139,253,.3);
  color: #388bfd; }
.exec-claude-btn.disabled { opacity: .5; cursor: not-allowed; }
.exec-ok       { color: #22c55e; font-size: 9px; }
.exec-unavail  { color: #94a3b8; font-size: 9px; }
.exec-detecting { font-size: 10px; color: var(--wb-text-soft); }

.main-head-actions,
.main-subline,
.canvas-bar,
.canvas-meta,
.context-strip,
.answer-head,
.tool-row,
.composer-shell,
.settings-dialog,
.settings-head,
.settings-actions,
.setting-item,
.setting-actions,
.model-head {
  display: flex;
  align-items: center;
}

.project-head,
.canvas-bar,
.settings-head,
.setting-item {
  justify-content: space-between;
}

.project-name-wrap {
  gap: 8px;
  min-width: 0;
}

.folder-mark {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: var(--wb-accent-soft);
  border: 1px solid var(--wb-accent-line);
  flex-shrink: 0;
}

.project-name {
  font-size: 14px;
  color: var(--wb-text);
}

.branch-badge,
.sub-pill,
.meta-chip,
.tag-chip,
.child-chip,
.active-chip,
.pending-chip,
.status-pill,
.settings-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 11px;
  white-space: nowrap;
}

.branch-badge,
.meta-chip,
.sub-pill,
.settings-chip {
  border: 1px solid var(--wb-border);
  background: rgba(255, 255, 255, 0.84);
  color: var(--wb-text-soft);
}

.project-source {
  margin-top: 8px;
}

.project-path {
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--wb-text-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-tags,
.project-children,
.settings-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.project-tags {
  margin-top: 10px;
}

.tag-chip,
.child-chip,
.active-chip {
  background: var(--wb-accent-soft);
  color: var(--wb-accent);
}

.pending-chip {
  background: rgba(215, 155, 25, 0.14);
  color: #9a6700;
}

.project-children {
  margin-top: 10px;
}

.project-foot {
  justify-content: space-between;
  margin-top: 12px;
}

.empty-state {
  padding: 18px;
  text-align: center;
  border: 1px dashed var(--wb-border-strong);
  border-radius: 18px;
  color: var(--wb-text-soft);
  background: rgba(255, 255, 255, 0.56);
}

.pane-manual {
  padding-bottom: 20px;
  border-top: 1px solid rgba(114, 101, 88, 0.1);
  margin-top: auto;
  padding-top: 16px;
}

.manual-actions {
  gap: 10px;
  margin-top: 10px;
}

.main-pane {
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, var(--wb-shell), var(--wb-panel));
}

.main-head {
  justify-content: space-between;
  gap: 16px;
  padding: 24px 26px 18px;
  border-bottom: 1px solid rgba(114, 101, 88, 0.12);
}

.main-head h1 {
  margin-top: 6px;
  font-size: 33px;
  line-height: 1.08;
}

.main-subline,
.main-head-actions,
.canvas-meta {
  gap: 8px;
  flex-wrap: wrap;
}

.workspace-canvas {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
  padding: 18px 22px 22px;
}

/* 主体：对话 + 文件改动面板并排 */
.canvas-body {
  flex: 1; min-height: 0; display: flex; gap: 14px; overflow: hidden;
}
.canvas-body-main {
  flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden;
}

/* 文件改动面板开关 */
.canvas-changes-btn {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px; border-radius: 8px; font-size: 11px; font-weight: 600;
  border: 1px solid var(--wb-border); background: transparent;
  color: var(--wb-text-soft); cursor: pointer; transition: .12s; margin-left: auto;
}
.canvas-changes-btn:hover { background: var(--wb-accent-soft); color: var(--wb-accent); }
.canvas-changes-btn.active { background: var(--wb-accent-soft); color: var(--wb-accent); border-color: var(--wb-accent-line); }
.exec-mode-chip.chip-claude { background: rgba(56,139,253,.1); color: #388bfd; }

/* 停止按钮 */
.stop-btn {
  padding: 6px 14px; border-radius: 10px; font-size: 12px; font-weight: 600;
  border: 1px solid rgba(239,68,68,.3); background: rgba(239,68,68,.08);
  color: #ef4444; cursor: pointer; transition: .12s;
}
.stop-btn:hover { background: rgba(239,68,68,.15); }

/* Token 统计 */
.token-chip { font-size: 10px; color: var(--wb-text-faint); margin: 0 6px; }

/* 右侧文件改动面板 */
.changes-panel {
  width: 260px; flex-shrink: 0; display: flex; flex-direction: column;
  background: var(--wb-paper); border: 1px solid var(--wb-border);
  border-radius: 16px; overflow: hidden;
}
.cp-header {
  display: flex; align-items: center; gap: 7px;
  padding: 10px 12px; border-bottom: 1px solid var(--wb-border); flex-shrink: 0;
}
.cp-title  { font-size: 12px; font-weight: 700; color: var(--wb-text); }
.cp-branch { font-size: 10px; color: var(--wb-text-soft); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-refresh { padding: 2px 6px; border-radius: 5px; border: 1px solid var(--wb-border); background: transparent; cursor: pointer; font-size: 12px; color: var(--wb-text-soft); }
.cp-loading { display: flex; justify-content: center; padding: 16px; }
.cp-empty   { font-size: 12px; color: var(--wb-text-soft); padding: 16px 12px; text-align: center; }
.cp-file-list { flex: 1; overflow-y: auto; }
.cp-file-row  { display: flex; align-items: center; gap: 7px; padding: 6px 12px; cursor: pointer; font-size: 12px; border-bottom: 1px solid rgba(0,0,0,.04); }
.cp-file-row:hover  { background: rgba(0,0,0,.03); }
.cp-file-row.active { background: var(--wb-accent-soft); }
.cp-status-badge { font-size: 10px; font-weight: 700; padding: 1px 4px; border-radius: 3px; flex-shrink: 0; font-family: monospace; }
.fst-modified  { background: rgba(249,196,74,.15); color: #b45309; }
.fst-added     { background: rgba(34,197,94,.12);  color: #15803d; }
.fst-deleted   { background: rgba(239,68,68,.12);  color: #dc2626; }
.fst-renamed   { background: rgba(139,92,246,.12); color: #7c3aed; }
.fst-untracked { background: rgba(156,163,175,.12);color: #6b7280; }
.fst-changed   { background: rgba(249,196,74,.15); color: #b45309; }
.cp-filename   { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cp-diff-wrap  { flex-shrink: 0; border-top: 1px solid var(--wb-border); max-height: 50%; display: flex; flex-direction: column; }
.cp-diff-header { display: flex; align-items: center; justify-content: space-between; padding: 5px 10px; border-bottom: 1px solid var(--wb-border); font-size: 11px; color: var(--wb-text-soft); flex-shrink: 0; }
.cp-close-diff  { background: none; border: none; cursor: pointer; color: var(--wb-text-soft); font-size: 13px; }
.cp-diff-pre   { flex: 1; overflow-y: auto; padding: 8px; margin: 0; font-family: monospace; font-size: 11px; line-height: 1.6; white-space: pre; background: #0d1117; color: #c9d1d9; }
.cp-diff-pre :deep(.diff-add)    { display: block; background: rgba(63,185,80,.15); color: #3fb950; }
.cp-diff-pre :deep(.diff-del)    { display: block; background: rgba(248,81,73,.12); color: #f85149; }
.cp-diff-pre :deep(.diff-hunk)   { display: block; color: #58a6ff; }
.cp-diff-pre :deep(.diff-header) { display: block; color: #8b949e; font-weight: 600; }

.canvas-bar {
  padding: 0 4px 14px;
}

.canvas-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--wb-text);
}

.context-strip {
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.context-card {
  min-width: 180px;
  flex: 1 1 220px;
  padding: 13px 14px;
  border-radius: 16px;
  border: 1px solid var(--wb-border);
  background: rgba(255, 255, 255, 0.78);
}

.context-label {
  display: block;
  margin-bottom: 6px;
}

.context-card strong {
  font-size: 13px;
  line-height: 1.55;
  color: var(--wb-text);
}

.conversation-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 6px;
}

.welcome-doc,
.answer-card,
.query-card {
  border-radius: 22px;
  border: 1px solid var(--wb-border);
  background: var(--wb-paper);
  box-shadow: 0 10px 30px rgba(44, 31, 20, 0.05);
}

.welcome-doc {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 44px 48px;
  text-align: left;
}

.doc-eyebrow {
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--wb-accent);
}

.welcome-doc h3 {
  font-size: 30px;
  line-height: 1.15;
}

.quick-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
}

/* Open Design 风格 Starter Cards */
.starter-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-top: 24px;
  width: 100%;
  max-width: 620px;
}
.starter-card {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 12px 14px; border-radius: 14px; text-align: left;
  border: 1px solid var(--wb-border); background: var(--wb-paper);
  cursor: pointer; color: inherit; transition: all .15s;
}
.starter-card:hover:not(:disabled) {
  border-color: var(--wb-accent-line);
  background: var(--wb-accent-soft);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(56,139,253,.1);
}
.starter-card:disabled { opacity: .5; cursor: not-allowed; }
.sc-icon { font-size: 18px; flex-shrink: 0; line-height: 1; margin-top: 1px; }
.sc-body { display: flex; flex-direction: column; gap: 2px; }
.sc-title { font-size: 13px; font-weight: 600; color: var(--wb-text); }
.sc-tag  { font-size: 10px; color: var(--wb-text-soft); font-weight: 500; }

.message-block {
  margin-bottom: 16px;
}

.query-card {
  padding: 18px 20px;
}

.query-label {
  margin-bottom: 8px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.query-text {
  color: var(--wb-text);
  line-height: 1.8;
}

.answer-card {
  padding: 18px 20px 20px;
}

.answer-head {
  gap: 12px;
  margin-bottom: 14px;
}

.answer-mark {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  background: var(--wb-accent-soft);
  color: var(--wb-accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  flex-shrink: 0;
}

.answer-title strong {
  display: block;
  font-size: 14px;
  color: var(--wb-text);
}

.answer-title span {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  color: var(--wb-text-faint);
}

.tool-timeline {
  margin-bottom: 14px;
}

.tool-row {
  width: 100%;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--wb-border);
  border-radius: 14px;
  background: #f7fbff;
  color: var(--wb-text-soft);
  margin-bottom: 8px;
  cursor: pointer;
}

.tool-state {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #1f8f59;
  flex-shrink: 0;
}

.tool-state.pending {
  background: #d79b19;
}

.tool-name {
  font-weight: 700;
  color: var(--wb-text);
}

.tool-input {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: left;
}

.tool-toggle {
  flex-shrink: 0;
}

.tool-output {
  margin: 0 0 10px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--wb-border);
  background: #f5f9fd;
  color: var(--wb-text-soft);
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.answer-content {
  color: var(--wb-text);
  line-height: 1.82;
}

.answer-content :deep(.md-title) {
  margin: 8px 0 10px;
  font-size: 16px;
  font-weight: 700;
}

.answer-content :deep(.md-row) {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 5px 0;
}

.answer-content :deep(.md-index) {
  min-width: 18px;
  color: var(--wb-accent);
  font-weight: 700;
}

.answer-content :deep(.md-dot) {
  width: 7px;
  height: 7px;
  margin-top: 10px;
  border-radius: 999px;
  background: var(--wb-accent);
  flex-shrink: 0;
}

.answer-content :deep(.inline-code),
.branch-badge,
.project-path,
.settings-chip,
.meta-chip,
.sub-pill,
.composer-prefix,
.composer-input,
.tool-output {
  font-family: "Cascadia Code", "Consolas", "Source Code Pro", monospace;
}

.answer-content :deep(.inline-code) {
  padding: 2px 7px;
  border-radius: 8px;
  border: 1px solid var(--wb-border);
  background: #f5f9fd;
  color: var(--wb-accent);
}

.stream-cursor {
  display: inline-block;
  width: 8px;
  height: 18px;
  margin-top: 10px;
  border-radius: 999px;
  background: var(--wb-accent);
  animation: blink 1s steps(1) infinite;
}

.composer-wrap {
  margin-top: 16px;
}

.composer-shell {
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--wb-border-strong);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.96);
}

.composer-prefix {
  flex-shrink: 0;
  color: var(--wb-accent);
  font-size: 12px;
}

.composer-input {
  min-height: 44px;
  max-height: 180px;
  padding: 10px 0;
  border: none;
  background: transparent;
  resize: none;
  box-shadow: none;
}

.composer-input:focus {
  border: none;
  box-shadow: none;
}

.send-btn {
  flex-shrink: 0;
  width: 100px;
  padding: 10px 14px;
}

.composer-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 6px 0;
}

.foot-link {
  border-radius: 10px;
  padding: 6px 10px;
  cursor: pointer;
}

.settings-overlay {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
  padding: 24px; z-index: 1200; pointer-events: auto;
}

.settings-dialog {
  width: min(960px, 100%);
  height: min(680px, 90vh);
  border-radius: 16px;
  overflow: hidden;
  background: #ffffff;
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.22), 0 0 0 1px rgba(0,0,0,.08);
  pointer-events: auto;
  display: flex;
}

.settings-nav {
  width: 196px; flex-shrink: 0;
  padding: 20px 12px 20px 16px;
  border-right: 1px solid #e8eaed;
  background: #f8f9fa;
  display: flex; flex-direction: column;
  overflow-y: auto;
}

.settings-caption {
  font-size: 15px; font-weight: 700;
  color: #1a1a1a; padding: 0 6px;
  margin-bottom: 12px;
}

.toast-msg {
  position: fixed;
  top: 18px;
  right: 22px;
  z-index: 90;
  max-width: min(420px, calc(100vw - 36px));
  padding: 12px 16px;
  border-radius: 14px;
  border: 1px solid var(--wb-border);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.14);
  color: var(--wb-text);
  font-size: 13px;
  line-height: 1.45;
}

.toast-msg.success {
  border-color: rgba(31, 143, 89, 0.24);
  color: #17663f;
}

.toast-msg.error {
  border-color: rgba(203, 59, 48, 0.22);
  color: #b13c33;
}

.settings-nav-item {
  width: 100%; display: flex; align-items: center; gap: 9px;
  padding: 8px 10px; border: none; border-radius: 8px;
  background: transparent; color: #4a5568;
  cursor: pointer; text-align: left; font-size: 13px;
  margin-bottom: 2px; transition: background .1s;
}
.settings-nav-item:hover { background: #eef0f3; color: #1a1a1a; }
.settings-nav-item.active {
  background: #e8f0fe; color: #1a56db; font-weight: 600;
}
.settings-nav-icon {
  width: 18px; text-align: center; font-size: 14px; flex-shrink: 0;
}

.settings-body {
  flex: 1; min-width: 0;
  display: flex; flex-direction: column;
  background: #ffffff; overflow: hidden;
}

.settings-head {
  display: flex; align-items: flex-start; justify-content: space-between;
  padding: 24px 28px 18px;
  border-bottom: 1px solid #e8eaed;
  flex-shrink: 0;
}
.settings-head-text h3 {
  font-size: 20px; font-weight: 700; color: #1a1a1a; margin: 0 0 4px;
}
.settings-head-text p {
  font-size: 13px; color: #6b7280; margin: 0;
}

.close-btn {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  border: 1px solid #e8eaed; background: #fff; color: #6b7280;
  font-size: 18px; line-height: 1; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .1s;
}
.close-btn:hover { background: #f1f3f4; color: #1a1a1a; }

.settings-scroll {
  flex: 1; min-height: 0; overflow-y: auto;
  padding: 24px 28px;
}

.settings-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

/* ── 新 Tab 内容样式 ── */
.sb-group {
  margin-bottom: 24px; padding: 16px; border-radius: 10px;
  border: 1px solid #e8eaed; background: #fafafa;
}
.sb-group-title {
  font-size: 12px; font-weight: 600; color: #6b7280;
  text-transform: uppercase; letter-spacing: .05em;
  margin-bottom: 12px;
}
.sb-field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 12px; }
.sb-field:last-child { margin-bottom: 0; }
.sb-field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
.sb-label { font-size: 12px; font-weight: 500; color: #374151; }
.sb-hint  { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.sb-checkbox-field { margin-bottom: 0; }
.sb-checkbox { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.sb-checkbox span { font-size: 13px; color: #374151; }
.sb-actions { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.sb-msg { font-size: 12px; }
.sb-msg.ok  { color: #16a34a; }
.sb-msg.err { color: #dc2626; }
.settings-input {
  padding: 7px 10px; font-size: 13px; border-radius: 6px;
  border: 1px solid #d1d5db; background: #fff; color: #1a1a1a;
  width: 100%; box-sizing: border-box; outline: none;
}
.settings-input:focus { border-color: #1a56db; box-shadow: 0 0 0 2px rgba(26,86,219,.12); }
.settings-input.mono { font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; }

.model-card-wrap  { display: flex; flex-direction: column; gap: 0; }

.model-card {
  display: flex; align-items: flex-start;
  text-align: left;
  padding: 14px 12px 14px 16px;
  border-radius: 10px;
  border: 1px solid #e8eaed;
  background: #fff;
  color: inherit;
  transition: border-color 0.15s, box-shadow 0.15s;
  position: relative;
}
.model-card-main {
  flex: 1; cursor: pointer;
}
.model-card-main:hover { opacity: .9; }
.model-base { font-size: 11px; color: rgba(80,100,130,.6); font-family: monospace; margin-top: 3px; }

.model-edit-icon {
  flex-shrink: 0; align-self: flex-start;
  padding: 4px 8px; border-radius: 8px; border: 1px solid var(--wb-border);
  background: transparent; cursor: pointer; font-size: 13px; color: var(--wb-text-soft);
  margin-left: 8px; transition: all .12s; opacity: 0;
}
.model-card:hover .model-edit-icon { opacity: 1; }
.model-edit-icon:hover { background: var(--wb-accent); color: #fff; border-color: var(--wb-accent); }

.model-card:hover { border-color: #1a56db; }
.model-card.active {
  border-color: #1a56db;
  box-shadow: 0 0 0 2px rgba(26,86,219,.1);
  background: #f0f4ff;
}

/* 内联编辑面板 */
.wb-edit-panel {
  margin-top: 6px; padding: 14px 16px;
  background: rgba(248,250,255,.9); border: 1px solid rgba(56,139,253,.2);
  border-radius: 14px;
}
.wb-edit-title { font-size: 12px; font-weight: 600; color: var(--wb-accent); margin-bottom: 10px; }
.wb-edit-grid  { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; margin-bottom: 10px; }
.wb-ef         { display: flex; flex-direction: column; gap: 3px; }
.wb-ef span    { font-size: 11px; color: var(--wb-text-soft); }
.wb-ef.wb-ef-full  { grid-column: 1 / -1; }
.wb-ef.wb-ef-check { flex-direction: row; align-items: center; gap: 6px; padding-top: 16px; }
.wb-ef.wb-ef-check span { font-size: 12px; color: var(--wb-text); }
.wb-edit-actions { display: flex; align-items: center; gap: 8px; }

.model-card:hover {
  transform: translateY(-1px);
}

.model-card:disabled,
.ghost-mini:disabled,
.switch-btn:disabled {
  cursor: not-allowed;
  opacity: 0.68;
  transform: none;
}

.model-subline,
.model-runtime,
.setting-copy span {
  margin-top: 4px;
  color: #6b7280;
  font-size: 12px;
}

.settings-block {
  padding: 16px 0 10px;
}
.settings-block label {
  display: block; margin-bottom: 10px;
  font-size: 12px; font-weight: 600; color: #374151;
}
.settings-actions { gap: 10px; margin-top: 10px; }

/* 通用 Setting item 白色主题 */
.setting-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0; border-bottom: 1px solid #f1f3f4;
}
.setting-item:last-child { border-bottom: none; }
.setting-headline { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
.setting-copy span { color: #9ca3af; }
.status-pill {
  padding: 2px 7px; border-radius: 10px; font-size: 11px; font-weight: 600;
}
.status-pill.enabled { background: #d1fae5; color: #065f46; }
.status-pill.muted   { background: #f3f4f6; color: #6b7280; }
.status-pill.online  { background: #dbeafe; color: #1e40af; }
.status-pill.offline { background: #fee2e2; color: #991b1b; }
.status-pill.unknown { background: #fef3c7; color: #92400e; }

.settings-chip-list {
  gap: 10px;
}

.setting-item {
  gap: 16px;
  padding: 14px 0;
  border-bottom: 1px solid rgba(114, 101, 88, 0.1);
}

.setting-copy {
  min-width: 0;
}

.setting-headline {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.setting-copy strong {
  color: var(--wb-text);
}

.status-pill.enabled,
.status-pill.ok {
  background: rgba(31, 143, 89, 0.12);
  color: #17663f;
}

.status-pill.down {
  background: rgba(203, 59, 48, 0.12);
  color: #b13c33;
}

.status-pill.muted {
  background: rgba(131, 147, 168, 0.12);
  color: var(--wb-text-soft);
}

.setting-actions {
  gap: 10px;
  flex-shrink: 0;
}

.switch-btn {
  position: relative;
  width: 54px;
  height: 30px;
  border-radius: 999px;
  border: 1px solid var(--wb-border);
  background: #efe9df;
  cursor: pointer;
}

.switch-btn.active {
  background: rgba(56, 139, 253, 0.16);
  border-color: var(--wb-accent-line);
}

.switch-btn.pending {
  box-shadow: 0 0 0 3px rgba(56, 139, 253, 0.08);
}

.switch-thumb {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: #fff;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12);
  transition: transform 0.18s ease;
}

.switch-btn.active .switch-thumb {
  transform: translateX(24px);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.18s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  50.01%, 100% { opacity: 0; }
}

@media (max-width: 1180px) {
  .workbench-shell {
    grid-template-columns: 296px minmax(0, 1fr);
  }

  .main-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .main-head-actions {
    width: 100%;
  }
}

@media (max-width: 920px) {
  .workbench-page {
    overflow: auto;
  }

  .workbench-shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .project-pane,
  .main-pane {
    min-height: 420px;
  }

  .settings-dialog {
    flex-direction: column;
    height: min(820px, 92vh);
  }

  .settings-nav {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--wb-border);
    display: flex;
    gap: 8px;
    overflow: auto;
  }

  .settings-caption {
    display: none;
  }

  .settings-nav-item {
    width: auto;
    margin-bottom: 0;
    white-space: nowrap;
  }
}
</style>
