<template>
  <div class="page agent-page">
    <Transition name="toast">
      <div v-if="toast" class="toast-msg">{{ toast }}</div>
    </Transition>

    <div class="history-panel" :class="{ collapsed: !showHistory }">
      <div class="history-panel-header">
        <button class="new-conv-btn" @click="newConversation" :disabled="streaming">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          新建对话
        </button>
      </div>

      <div class="history-list" v-if="historyList.length">
        <div
          v-for="item in historyList"
          :key="item.conv_id"
          class="history-item"
          :class="{ active: item.conv_id === convIds[mode] }"
          @click="loadConversation(item)"
        >
          <span class="hi-mode-icon" v-html="getModeIconSvg(item.mode)"></span>
          <div class="hi-info">
            <div class="hi-title">{{ item.title || '新对话' }}</div>
            <div class="hi-date">
              <span class="hi-model-tag">{{ modelBadgeText }}</span>
              {{ fmtHistoryDate(item.updated_at) }}
            </div>
          </div>
          <button class="hi-del" @click.stop="deleteConversation(item.conv_id)" title="删除">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>

      <div class="history-empty" v-else>暂无历史记录</div>
    </div>

    <div class="chat-section">
      <div class="agent-header">
        <div class="agent-title">
          <button
            class="history-toggle"
            @click="showHistory = !showHistory"
            :title="showHistory ? '收起历史' : '展开历史'"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>

          <span class="agent-icon-wrap" v-html="AGENT_ICON"></span>

          <div class="agent-title-info">
            <div class="agent-title-row">
              <h1>AIOps 智能助手</h1>
              <span class="model-badge">{{ modelBadgeText }}</span>
              <span class="provider-badge">{{ providerBadgeText }}</span>
              <span class="exec-badge" v-if="streaming">执行中</span>
              <span class="exec-badge idle" v-else>待命</span>
            </div>
            <span class="subtitle">AIOps 助手工作台 · MCP 编排 · Skills 工具架 · 根因分析</span>
          </div>
        </div>

        <div class="header-right">
          <div class="mode-tabs">
            <button
              v-for="m in MODES"
              :key="m.key"
              class="mode-tab"
              :class="{ active: mode === m.key }"
              @click="switchMode(m.key)"
            >
              <span class="mode-icon" v-html="m.icon"></span>
              {{ m.label }}
            </button>
          </div>

          <div class="header-actions">
            <button class="hdr-btn" @click="openWorkbench('workspace')" :disabled="streaming">
              <span v-html="TOOLS_ICON"></span>
              工作台
            </button>
            <!-- Trace 面板开关 -->
            <button class="hdr-btn" :class="{ active: showTrace }" @click="showTrace = !showTrace" title="执行追踪面板">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
              </svg>
              追踪
            </button>
            <button class="hdr-btn" @click="newConversation" :disabled="streaming" title="新建对话">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              新会话
            </button>
          </div>
        </div>
      </div>

      <div class="quick-shelf">
        <button class="shelf-card" @click="openWorkbench('workspace')">
          <span class="shelf-kicker">HOME</span>
          <strong class="shelf-title mono">{{ workspaceChipText }}</strong>
          <span class="shelf-meta">{{ workspaceHintText }}</span>
        </button>

        <button class="shelf-card" @click="openWorkbench('model')">
          <span class="shelf-kicker">MODEL</span>
          <strong class="shelf-title">{{ activeModel?.name || aiModelShort }}</strong>
          <span class="shelf-meta">{{ activeModel?.provider || '未配置模型' }}</span>
        </button>

        <button class="shelf-card" @click="openWorkbench('mcp')">
          <span class="shelf-kicker">MCP</span>
          <strong class="shelf-title">{{ enabledMcpList.length }} 个已启用</strong>
          <span class="shelf-meta">{{ mcpSummaryText }}</span>
        </button>

        <button class="shelf-card" @click="openWorkbench('skill')">
          <span class="shelf-kicker">SKILLS</span>
          <strong class="shelf-title">{{ enabledSkillList.length }} 个已启用</strong>
          <span class="shelf-meta">{{ skillSummaryText }}</span>
        </button>
      </div>

      <div class="chat-area" ref="chatAreaRef">
        <div v-if="!messages.length" class="welcome-state">
          <div class="welcome-icon" v-html="AGENT_ICON"></div>
          <div class="welcome-title">{{ currentMode.label }}</div>
          <div class="welcome-desc">{{ currentMode.desc }}</div>

          <div class="welcome-runtime">
            <span class="runtime-chip">HOME {{ workspaceChipText }}</span>
            <span class="runtime-chip">MODEL {{ modelBadgeText }}</span>
            <span class="runtime-chip">MCP {{ enabledMcpList.length }}</span>
            <span class="runtime-chip">SKILL {{ enabledSkillList.length }}</span>
          </div>

          <div class="welcome-hints">
            <button
              v-for="hint in currentMode.hints"
              :key="hint"
              class="hint-btn"
              @click="sendMessage(hint)"
            >
              {{ hint }}
            </button>
          </div>
        </div>

        <template v-else>
          <div v-for="msg in messages" :key="msg.id" class="msg-wrapper" :class="msg.role">
            <div v-if="msg.role === 'user'" class="user-bubble">
              {{ msg.content }}
            </div>

            <div v-else class="assistant-msg">
              <div class="assistant-avatar" v-html="AGENT_ICON"></div>
              <div class="assistant-body">
                <template v-for="tc in msg.toolCalls" :key="tc.id">
                  <div v-if="isAnsibleTool(tc)" class="ansible-card" :class="{ pending: tc.pending }">
                    <div class="ansible-header">
                      <span class="ansible-icon">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                          <polyline points="9 11 12 14 22 4" />
                          <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
                        </svg>
                      </span>
                      <span class="ansible-title">Ansible Playbook 执行</span>
                      <span v-if="tc.pending" class="ansible-status running">运行中</span>
                      <span v-else-if="isAnsibleSuccess(tc)" class="ansible-status success">完成</span>
                      <span v-else class="ansible-status failed">失败</span>
                    </div>

                    <div class="ansible-body">
                      <div class="ansible-field">
                        <span class="ansible-key">目标主机</span>
                        <span class="ansible-val mono">{{ tc.input?.host || tc.input?.target || extractAnsibleField(tc, 'host') }}</span>
                      </div>
                      <div class="ansible-field">
                        <span class="ansible-key">执行方式</span>
                        <span class="ansible-val">ansible</span>
                      </div>
                      <div class="ansible-field">
                        <span class="ansible-key">超时</span>
                        <span class="ansible-val mono">{{ tc.input?.timeout || '30' }}s</span>
                      </div>
                      <div class="ansible-field" v-if="tc.output && extractTaskId(tc.output)">
                        <span class="ansible-key">任务编号</span>
                        <span class="ansible-val">#{{ extractTaskId(tc.output) }}</span>
                      </div>
                    </div>

                    <div v-if="tc.output && !tc.pending" class="ansible-log" @click="tc.expanded = !tc.expanded">
                      {{ tc.expanded ? '收起日志' : '查看执行日志' }}
                    </div>

                    <div v-if="tc.expanded && tc.output" class="tool-output">
                      <pre>{{ tc.output }}</pre>
                    </div>
                  </div>

                  <div v-else class="tool-card" :class="tc.pending ? 'pending' : 'done'">
                    <div class="tool-header" @click="tc.expanded = !tc.expanded">
                      <span class="tool-status-dot" :class="tc.pending ? 'spin' : 'ok'"></span>
                      <span class="tool-name">{{ TOOL_LABELS[tc.tool] || tc.tool }}</span>
                      <span v-if="!tc.pending" class="tool-params">{{ formatInput(tc.input) }}</span>
                      <span v-if="tc.pending" class="tool-pending-text">执行中...</span>
                      <span v-if="!tc.pending && tc.output" class="tool-expand-btn">
                        {{ tc.expanded ? '收起' : '查看结果' }}
                      </span>
                    </div>

                    <div v-if="tc.expanded && tc.output" class="tool-output">
                      <pre>{{ tc.output }}</pre>
                    </div>
                  </div>
                </template>

                <!-- 思考中动画（无内容无工具时显示）-->
                <div v-if="msg.streaming && !msg.content && !msg.toolCalls?.length" class="thinking-indicator">
                  <span class="think-dot"></span>
                  <span class="think-dot delay1"></span>
                  <span class="think-dot delay2"></span>
                  <span class="think-label">正在推理...</span>
                </div>

                <div v-if="msg.content || msg.streaming" class="ai-text">
                  <div class="ai-content" v-html="renderContent(msg.content)"></div>
                  <span v-if="msg.streaming" class="cursor-blink"></span>
                </div>
              </div>
            </div>
          </div>

          <div ref="bottomRef"></div>
        </template>
      </div>

      <div class="input-area">
        <div class="runtime-bar">
          <span class="runtime-chip">HOME {{ workspaceChipText }}</span>
          <span class="runtime-chip">MODEL {{ modelBadgeText }}</span>
          <span class="runtime-chip">MCP {{ enabledMcpList.length }}</span>
          <span class="runtime-chip">SKILL {{ enabledSkillList.length }}</span>
        </div>

        <div v-if="mode === 'inspect' && !messages.length" class="inspect-quick">
          <button class="btn-inspect" @click="startInspect" :disabled="streaming">
            <span v-if="streaming" class="spinner-sm"></span>
            <span v-else v-html="SCAN_ICON"></span>
            {{ streaming ? '巡检中...' : '一键开始巡检' }}
          </button>
          <span class="inspect-hint">自动检查主机、服务、日志异常并汇总巡检报告</span>
        </div>

        <div v-else class="input-shell">
          <div class="input-shell-head">
            <span class="shell-kicker">PROMPT</span>
            <button class="inline-link" @click="openWorkbench('workspace')">编辑工作台</button>
          </div>

          <div class="input-row">
            <textarea
              ref="inputRef"
              v-model="inputText"
              class="chat-input"
              :placeholder="currentMode.placeholder"
              :disabled="streaming"
              rows="1"
              @keydown.enter.exact.prevent="onEnter"
              @keydown.esc="inputText = ''"
              @input="autoResize"
            ></textarea>

            <button class="send-btn" :disabled="streaming || !inputText.trim()" @click="onSend">
              <span v-if="streaming" class="spinner-sm"></span>
              <span v-else v-html="SEND_ICON"></span>
            </button>
          </div>
        </div>

        <div class="input-actions">
          <span class="input-hint-text">Enter 发送 · Shift+Enter 换行 · Esc 清空</span>
          <button class="action-btn" @click="openWorkbench('workspace')">工作台</button>
          <button v-if="messages.length" class="action-btn" @click="clearChat">清空对话</button>
        </div>
      </div>
    </div>

    <!-- ── Trace 追踪面板（借鉴 OpenCowork Trace Panel）── -->
    <Transition name="trace-slide">
      <div v-if="showTrace" class="trace-panel">
        <div class="trace-header">
          <span class="trace-title">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            执行追踪
          </span>
          <span class="trace-count">{{ traceItems.length }} 步</span>
          <button class="trace-close" @click="showTrace = false">✕</button>
        </div>

        <!-- 四层进度条 -->
        <div class="trace-layers-bar">
          <div v-for="(lm, lk) in LAYER_META" :key="lk"
            class="trace-layer-pill"
            :class="{ active: traceItems.some(t => t.layer === lk) }"
            :style="{ '--lc': lm.color }">
            <span class="tlp-key">{{ lk }}</span>
            <span class="tlp-name">{{ lm.label }}</span>
            <span class="tlp-cnt">{{ traceItems.filter(t => t.layer === lk).length }}</span>
          </div>
        </div>

        <div class="trace-body">
          <div v-if="!traceItems.length" class="trace-empty">
            <div class="trace-empty-icon">⟳</div>
            <div>等待工具调用...</div>
          </div>

          <div v-for="(item, idx) in traceItems" :key="item.id"
            class="trace-item" :class="[item.pending ? 'running' : 'done', item.type]"
            @click="item.open = !item.open"
          >
            <div class="trace-item-head">
              <!-- 步骤序号 -->
              <span class="trace-step">{{ idx + 1 }}</span>
              <!-- 四层标签 -->
              <span class="trace-layer-badge"
                :style="{ background: item.lmeta?.bg, color: item.lmeta?.color, border: '1px solid '+(item.lmeta?.color||'#888')+'44' }">
                {{ item.layer }}·{{ item.lmeta?.label }}
              </span>
              <!-- 状态图标 -->
              <span class="trace-status-dot" :class="item.pending ? 'spin' : 'ok'"></span>
              <!-- 工具名 + 类型图标 -->
              <span class="trace-tool-icon">{{ item.typeIcon }}</span>
              <span class="trace-tool-name">{{ item.label }}</span>
              <!-- 耗时 -->
              <span v-if="!item.pending && item.elapsed" class="trace-elapsed">{{ item.elapsed }}</span>
              <span v-if="item.pending" class="trace-running-text">运行中...</span>
              <!-- 展开箭头 -->
              <span v-if="item.output || item.input" class="trace-arrow" :class="{ open: item.open }">▾</span>
            </div>

            <!-- 输入摘要 -->
            <div v-if="!item.pending && item.inputSummary" class="trace-input-row">
              <span class="trace-label">IN</span>
              <span class="trace-val">{{ item.inputSummary }}</span>
            </div>

            <!-- 输出摘要 -->
            <div v-if="!item.pending && item.outputSummary" class="trace-output-row">
              <span class="trace-label">OUT</span>
              <span class="trace-val ok">{{ item.outputSummary }}</span>
            </div>

            <!-- 展开详情 -->
            <div v-if="item.open && (item.input || item.output)" class="trace-detail">
              <div v-if="item.input" class="trace-detail-block">
                <div class="trace-detail-label">输入</div>
                <pre class="trace-pre">{{ JSON.stringify(item.input, null, 2) }}</pre>
              </div>
              <div v-if="item.output" class="trace-detail-block">
                <div class="trace-detail-label">输出</div>
                <pre class="trace-pre">{{ item.output.slice(0, 800) }}{{ item.output.length > 800 ? '\n...' : '' }}</pre>
              </div>
            </div>
          </div>

          <!-- 当前 streaming 思考中 -->
          <div v-if="streaming && !currentStreamingTool" class="trace-thinking">
            <span class="think-dot"></span>
            <span class="think-dot delay1"></span>
            <span class="think-dot delay2"></span>
            <span class="think-text">AI 推理中</span>
          </div>
        </div>
      </div>
    </Transition>

    <Transition name="fade">
      <div v-if="showWorkbench" class="workbench-backdrop" @click="closeWorkbench"></div>
    </Transition>

    <Transition name="drawer">
      <aside v-if="showWorkbench" class="workbench-panel">
        <div class="workbench-head">
          <div>
            <div class="workbench-kicker">AIOps Workspace</div>
            <h2>对话工作台</h2>
            <p>在对话框里直接切换 HOME、模型类型、MCP 和 Skills。</p>
          </div>
          <button class="close-btn" @click="closeWorkbench" title="关闭">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div class="workbench-body">
          <section class="bench-section" :class="{ focus: activeWorkbenchSection === 'workspace' }">
            <div class="bench-headline">
              <span class="bench-index">01</span>
              <div>
                <h3>HOME 工作目录</h3>
                <p>外部执行器会优先使用这个目录作为当前工作区。</p>
              </div>
            </div>

            <label class="field-label">Directory</label>
            <input
              v-model="workspaceDraft"
              class="field-input mono"
              placeholder="例如 D:\\LabNotes\\raw\\K8S可视化学习平台"
              @focus="activeWorkbenchSection = 'workspace'"
              @keydown.enter.prevent="saveWorkspace"
            />

            <div class="field-actions">
              <span class="field-note">{{ workspaceHintText }}</span>
              <div class="button-group">
                <button class="mini-btn" @click="resetWorkspace">恢复默认</button>
                <button class="mini-btn primary" @click="saveWorkspace">保存目录</button>
              </div>
            </div>
          </section>

          <section class="bench-section" :class="{ focus: activeWorkbenchSection === 'model' }">
            <div class="bench-headline">
              <span class="bench-index">02</span>
              <div>
                <h3>大模型类型</h3>
                <p>先选模型类型，再切换具体模型。当前对话请求会携带选中的模型。</p>
              </div>
            </div>

            <div class="provider-pills">
              <button
                v-for="provider in providerOptions"
                :key="provider.key"
                class="provider-pill"
                :class="{ active: assistantConfig.model_type === provider.key }"
                @click="setModelType(provider.key)"
              >
                {{ provider.label }}
              </button>
            </div>

            <div class="model-stack">
              <button
                v-for="model in filteredModels"
                :key="model.id"
                class="model-option"
                :class="{ active: model.active }"
                @click="selectModel(model)"
              >
                <div class="model-option-top">
                  <span class="model-option-name">{{ model.name }}</span>
                  <span class="model-active-tag" v-if="model.active">ACTIVE</span>
                </div>
                <div class="model-option-meta">
                  <span>{{ model.provider }}</span>
                  <code>{{ model.runtime_provider || 'default' }}</code>
                </div>
              </button>
            </div>
          </section>

          <section class="bench-section" :class="{ focus: activeWorkbenchSection === 'mcp' }">
            <div class="bench-headline">
              <span class="bench-index">03</span>
              <div>
                <h3>MCP 工具</h3>
                <p>启停对话可用的 MCP，并随手探测在线状态。</p>
              </div>
            </div>

            <div class="tool-stack">
              <div v-for="mcp in mcpList" :key="mcp.id" class="tool-row">
                <div class="tool-row-main">
                  <div class="tool-row-title">
                    <span class="status-dot" :class="mcp.ok ? 'ok' : 'err'"></span>
                    <strong>{{ mcp.name }}</strong>
                    <span class="tool-kind">{{ mcp.type }}</span>
                  </div>
                  <div class="tool-row-meta mono">{{ mcp.url }}</div>
                </div>

                <div class="tool-row-actions">
                  <button class="mini-btn" @click="pingMcp(mcp)">探测</button>
                  <button class="toggle-switch sm" type="button" :class="{ on: mcp.enabled }" @click="toggleMcp(mcp)">
                    <span class="toggle-thumb"></span>
                  </button>
                </div>
              </div>
            </div>
          </section>

          <section class="bench-section" :class="{ focus: activeWorkbenchSection === 'skill' }">
            <div class="bench-headline">
              <span class="bench-index">04</span>
              <div>
                <h3>Skills 工具架</h3>
                <p>按场景控制对话框可用技能，保持工具面板简洁。</p>
              </div>
            </div>

            <div class="skill-stack">
              <div v-for="skill in skillList" :key="skill.id" class="skill-row" :class="{ on: skill.enabled }">
                <div class="skill-main">
                  <div class="skill-title">
                    <span class="skill-icon">{{ skill.icon || '•' }}</span>
                    <strong>{{ skill.name }}</strong>
                  </div>
                  <div class="skill-desc">{{ skill.desc }}</div>
                  <div class="skill-tags">
                    <span v-for="tag in skill.tags || []" :key="tag" class="skill-tag">{{ tag }}</span>
                  </div>
                </div>

                <button class="toggle-switch sm" type="button" :class="{ on: skill.enabled }" @click="toggleSkill(skill)">
                  <span class="toggle-thumb"></span>
                </button>
              </div>
            </div>
          </section>
        </div>
      </aside>
    </Transition>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { fetchHealthStatus, getAiModelShort } from '../composables/useHealthStatus.js'

const AGENT_ICON = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M9 11V7a3 3 0 0 1 6 0v4"/><circle cx="9" cy="16" r="1" fill="currentColor"/><circle cx="15" cy="16" r="1" fill="currentColor"/><path d="M12 3v2"/></svg>`
const SEND_ICON = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`
const SCAN_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h1m18 0h1M12 2v1m0 18v1M4.93 4.93l.7.7m12.74 12.74.7.7M4.93 19.07l.7-.7m12.74-12.74.7-.7"/><circle cx="12" cy="12" r="4"/></svg>`
const TOOLS_ICON = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.3-3.3a6 6 0 0 1-7.5 7.5l-6.7 6.7a2 2 0 1 1-2.8-2.8l6.7-6.7a6 6 0 0 1 7.5-7.5z"/></svg>`

const MODES = [
  {
    key: 'rca',
    label: '根因分析',
    desc: '描述异常现象，AI 会自动串联日志、指标和工具结果，输出 RCA 结论。',
    placeholder: '例如：支付接口超时且 5xx 增多，请分析根因...',
    hints: ['分析最近的服务错误', '为什么接口响应变慢了', '哪个服务出现了异常'],
    icon: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  },
  {
    key: 'inspect',
    label: '自主巡检',
    desc: '一键触发平台巡检，汇总主机、日志和服务异常，生成结构化报告。',
    placeholder: '可以指定巡检重点，或直接点击“一键开始巡检”...',
    hints: ['重点检查磁盘空间', '检查高负载主机', '查看最近出错的服务'],
    icon: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`,
  },
  {
    key: 'chat',
    label: '智能对话',
    desc: '自由提问，按需调度 MCP、Skills 和运维工具。',
    placeholder: '例如：帮我看看 nginx 最近的错误，或者检查 k8s 集群状态...',
    hints: ['查看所有服务的错误情况', '哪台主机 CPU 最高', '最近 1 小时有什么异常'],
    icon: `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
  },
]

const TOOL_LABELS = {
  query_error_logs: '查询错误日志',
  count_errors_by_service: '统计错误数量',
  get_services_list: '获取服务列表',
  get_host_metrics: '获取主机指标',
  inspect_all_hosts: '全量主机巡检',
  query_recent_logs: '查询最近日志',
}

const route = useRoute()
const mode = ref('chat')
const messages = ref([])
const inputText = ref('')
const streaming = ref(false)
const showHistory = ref(true)
const showTrace   = ref(false)   // Trace 追踪面板开关

// 工具类型 → 颜色/图标（参考 OpenCowork 类型化设计）
const TOOL_TYPE_MAP = {
  query_error_logs:      { type:'log',     color:'#fbbf24', icon:'📋', label:'查询错误日志' },
  query_recent_logs:     { type:'log',     color:'#fbbf24', icon:'📋', label:'查询日志' },
  count_errors_by_service:{ type:'metrics', color:'#a78bfa', icon:'📊', label:'统计错误' },
  get_host_metrics:      { type:'metrics', color:'#a78bfa', icon:'📊', label:'主机指标' },
  get_k8s_summary:       { type:'k8s',     color:'#38bdf8', icon:'☸️', label:'K8s 概览' },
  get_k8s_pods:          { type:'k8s',     color:'#38bdf8', icon:'☸️', label:'K8s Pods' },
  get_k8s_nodes:         { type:'k8s',     color:'#38bdf8', icon:'☸️', label:'K8s 节点' },
  get_k8s_namespaces:    { type:'k8s',     color:'#38bdf8', icon:'☸️', label:'K8s 命名空间' },
  inspect_all_hosts:     { type:'ssh',     color:'#22c55e', icon:'🖥️', label:'主机巡检' },
  get_services_list:     { type:'svc',     color:'#22c55e', icon:'🔗', label:'服务列表' },
  recall_similar_incidents:{ type:'mem',   color:'#f87171', icon:'🧠', label:'记忆检索' },
  export_report_pdf:     { type:'report',  color:'#fb923c', icon:'📄', label:'生成报告' },
  search_daily_reports:  { type:'report',  color:'#fb923c', icon:'📋', label:'搜索报告' },
  firecrawl_search_web:  { type:'web',     color:'#a78bfa', icon:'🌐', label:'网络搜索' },
  firecrawl_scrape_url:  { type:'web',     color:'#a78bfa', icon:'🌐', label:'网页抓取' },
  run_ssh_command:       { type:'ssh',     color:'#22c55e', icon:'💻', label:'SSH 命令' },
  call_mcp_tool:         { type:'mcp',     color:'#38bdf8', icon:'🔌', label:'MCP 工具' },
}

// 工具 → 所属四层思考层级
const TOOL_LAYER_MAP = {
  // L2 检索层工具
  query_error_logs:          'L2', query_recent_logs: 'L2',
  count_errors_by_service:   'L2', get_host_metrics:  'L2',
  get_k8s_summary:           'L2', get_k8s_pods:      'L2',
  get_k8s_nodes:             'L2', get_k8s_namespaces:'L2',
  get_k8s_deployments:       'L2', get_k8s_services:  'L2',
  recall_similar_incidents:  'L2', search_daily_reports:'L2',
  get_services_list:         'L2', get_middleware_summary:'L2',
  firecrawl_search_web:      'L2', firecrawl_scrape_url:'L2',
  // L3 推理/执行工具
  run_ssh_command:           'L3', inspect_all_hosts: 'L3',
  call_mcp_tool:             'L3', list_mcp_tools:    'L3',
  // L4 沉淀/输出工具
  export_report_pdf:         'L4', search_daily_reports_detail:'L4',
}
const LAYER_META = {
  L1: { label:'感知', color:'#38bdf8', bg:'rgba(56,189,248,.15)' },
  L2: { label:'检索', color:'#fbbf24', bg:'rgba(251,191,36,.12)' },
  L3: { label:'推理', color:'#22c55e', bg:'rgba(34,197,94,.12)'  },
  L4: { label:'沉淀', color:'#a78bfa', bg:'rgba(167,139,250,.12)' },
}

// 从所有消息中提取 Trace 条目（带类型+层级信息）
const traceItems = computed(() => {
  const items = []
  messages.value.forEach(msg => {
    if (msg.role !== 'assistant') return
    ;(msg.toolCalls || []).forEach(tc => {
      const meta  = TOOL_TYPE_MAP[tc.tool] || { type:'generic', color:'#8d96a0', icon:'⚙️', label: tc.tool }
      const layer = TOOL_LAYER_MAP[tc.tool] || 'L2'
      const lmeta = LAYER_META[layer]
      const input  = tc.input  || {}
      const output = tc.output || ''
      const inputKeys  = Object.keys(input).slice(0, 2).map(k => `${k}=${JSON.stringify(input[k]).slice(0,20)}`).join(' ')
      const outputLine = typeof output === 'string' ? output.split('\n')[0].slice(0, 60) : ''
      items.push({
        id:            tc.id,
        tool:          tc.tool,
        label:         meta.label,
        typeIcon:      meta.icon,
        type:          meta.type,
        color:         meta.color,
        layer, lmeta,
        pending:       tc.pending,
        input,  output,
        inputSummary:  inputKeys || null,
        outputSummary: outputLine || null,
        elapsed:       tc.elapsed || null,
        open:          false,
      })
    })
  })
  return items
})

// 当前正在调用的工具（用于 streaming 状态判断）
const currentStreamingTool = computed(() => {
  if (!streaming.value) return null
  const last = messages.value[messages.value.length - 1]
  if (!last || last.role !== 'assistant') return null
  const calls = last.toolCalls || []
  return calls.find(tc => tc.pending) || null
})
const historyList = ref([])
const chatAreaRef = ref(null)
const bottomRef = ref(null)
const inputRef = ref(null)
const showWorkbench = ref(false)
const activeWorkbenchSection = ref('workspace')
const toast = ref('')

const assistantConfig = reactive({
  home_dir: '',
  model_type: 'anthropic',
})

const modelList = ref([])
const mcpList = ref([])
const skillList = ref([])
const workspaceDraft = ref('')
const aiModelShort = ref('AI')

let aiModelMounted = true
let toastTimer = null
let msgIdCounter = 0
let currentAssistantMsg = null

function genUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    try {
      return crypto.randomUUID()
    } catch {
      // ignore
    }
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, ch => {
    const r = Math.random() * 16 | 0
    return (ch === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
  })
}

const convIds = ref({
  rca: genUUID(),
  inspect: genUUID(),
  chat: genUUID(),
})

const currentMode = computed(() => MODES.find(item => item.key === mode.value) || MODES[2])
const activeModel = computed(() => modelList.value.find(item => item.active) || modelList.value[0] || null)
const enabledMcpList = computed(() => mcpList.value.filter(item => item.enabled))
const enabledSkillList = computed(() => skillList.value.filter(item => item.enabled))
const modelBadgeText = computed(() => activeModel.value?.name || aiModelShort.value || 'AI')
const providerBadgeText = computed(() => activeModel.value?.provider || aiModelShort.value || 'Provider')
const workspaceChipText = computed(() => shortenPath(assistantConfig.home_dir) || 'Repo Root')
const workspaceHintText = computed(() => assistantConfig.home_dir || '使用服务默认目录')
const mcpSummaryText = computed(() => summarizeNames(enabledMcpList.value.map(item => item.name), 2, '未启用 MCP'))
const skillSummaryText = computed(() => summarizeNames(enabledSkillList.value.map(item => item.name), 2, '未启用 Skills'))

const providerOptions = computed(() => {
  const seen = new Map()
  for (const model of modelList.value) {
    const key = getProviderKey(model)
    if (!seen.has(key)) {
      seen.set(key, {
        key,
        label: model?.provider || key.toUpperCase(),
      })
    }
  }
  return Array.from(seen.values())
})

const filteredModels = computed(() => {
  const type = normalizeSlug(assistantConfig.model_type)
  const matches = modelList.value.filter(model => getProviderKey(model) === type)
  return matches.length ? matches : modelList.value
})

function normalizeSlug(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function getProviderKey(model) {
  return normalizeSlug(model?.provider || model?.runtime_provider || 'model')
}

function getProviderLabel(providerKey) {
  return providerOptions.value.find(item => item.key === providerKey)?.label || providerKey
}

function shortenPath(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const normalized = raw.replace(/\\/g, '/')
  const parts = normalized.split('/').filter(Boolean)
  if (parts.length <= 2) return raw
  return `.../${parts.slice(-2).join('/')}`
}

function summarizeNames(names, limit = 2, fallback = '未配置') {
  const clean = names.filter(Boolean)
  if (!clean.length) return fallback
  if (clean.length <= limit) return clean.join(' · ')
  return `${clean.slice(0, limit).join(' · ')} +${clean.length - limit}`
}

async function apiFetch(url, options = {}) {
  const resp = await fetch(url, {
    credentials: 'include',
    ...options,
  })
  const text = await resp.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }
  if (!resp.ok) {
    const detail = (data && typeof data === 'object' && data.detail) || (typeof data === 'string' && data) || `HTTP ${resp.status}`
    throw new Error(detail)
  }
  return data
}

function showToast(message, duration = 2200) {
  toast.value = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value = ''
  }, duration)
}

async function fetchAiModel() {
  try {
    const data = await fetchHealthStatus()
    if (!aiModelMounted) return
    aiModelShort.value = getAiModelShort(data.ai_provider || '')
  } catch {
    // ignore
  }
}

function openWorkbench(section = 'workspace') {
  activeWorkbenchSection.value = section
  showWorkbench.value = true
}

function closeWorkbench() {
  showWorkbench.value = false
}

function handleWindowKeydown(event) {
  if (event.key === 'Escape' && showWorkbench.value) {
    closeWorkbench()
  }
}

function getModeIconSvg(modeKey) {
  return MODES.find(item => item.key === modeKey)?.icon || ''
}

function fmtHistoryDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now - date
  const diffDays = Math.floor(diffMs / 86400000)
  if (diffDays === 0) return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (diffDays < 7) return `${diffDays} 天前`
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

async function loadHistoryList() {
  try {
    historyList.value = await apiFetch('/api/agent/conversations') || []
  } catch {
    // ignore
  }
}

async function loadWorkbenchData() {
  try {
    const [configData, mcpData, skillData] = await Promise.all([
      apiFetch('/api/agent-config'),
      apiFetch('/api/agent-config/mcps'),
      apiFetch('/api/agent-config/skills'),
    ])

    const basic = configData?.basic || {}
    assistantConfig.home_dir = String(basic.home_dir || '').trim()
    modelList.value = (configData?.models || []).map(item => ({ ...item }))
    assistantConfig.model_type = normalizeSlug(basic.model_type || getProviderKey(activeModel.value))
    if (!assistantConfig.model_type && modelList.value.length) {
      assistantConfig.model_type = getProviderKey(modelList.value.find(item => item.active) || modelList.value[0])
    }
    workspaceDraft.value = assistantConfig.home_dir
    mcpList.value = (mcpData?.data || []).map(item => ({ ...item }))
    skillList.value = (skillData?.data || []).map(item => ({ ...item }))
  } catch (error) {
    showToast(`加载工作台失败：${error.message}`)
  }
}

async function saveBasicConfig(payload, successMessage = '', silent = false) {
  const data = await apiFetch('/api/agent-config', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  const basic = data?.basic || {}
  if (Object.prototype.hasOwnProperty.call(basic, 'home_dir')) {
    assistantConfig.home_dir = String(basic.home_dir || '').trim()
    workspaceDraft.value = assistantConfig.home_dir
  }
  if (Object.prototype.hasOwnProperty.call(basic, 'model_type')) {
    assistantConfig.model_type = normalizeSlug(basic.model_type)
  }

  if (!silent && successMessage) {
    showToast(successMessage)
  }
}

async function saveWorkspace() {
  const previous = assistantConfig.home_dir
  const nextHome = workspaceDraft.value.trim()
  assistantConfig.home_dir = nextHome
  try {
    await saveBasicConfig(
      { home_dir: nextHome },
      nextHome ? '工作目录已更新' : '已恢复默认工作目录',
    )
  } catch (error) {
    assistantConfig.home_dir = previous
    workspaceDraft.value = previous
    showToast(`保存工作目录失败：${error.message}`)
  }
}

async function resetWorkspace() {
  workspaceDraft.value = ''
  await saveWorkspace()
}

function markActiveModel(modelId) {
  for (const model of modelList.value) {
    model.active = model.id === modelId
  }
}

async function setModelType(providerKey) {
  const previousType = assistantConfig.model_type
  assistantConfig.model_type = providerKey
  try {
    await saveBasicConfig({ model_type: providerKey }, '', true)
    const current = activeModel.value
    if (!current || getProviderKey(current) !== providerKey) {
      const target = modelList.value.find(model => getProviderKey(model) === providerKey)
      if (target) {
        await selectModel(target, { skipTypeSave: true, successMessage: `模型已切换为 ${target.name}` })
        return
      }
    }
    showToast(`模型类型已切换为 ${getProviderLabel(providerKey)}`)
  } catch (error) {
    assistantConfig.model_type = previousType
    showToast(`切换模型类型失败：${error.message}`)
  }
}

async function selectModel(model, options = {}) {
  const previousId = activeModel.value?.id || ''
  const previousType = assistantConfig.model_type
  const nextType = getProviderKey(model)
  markActiveModel(model.id)
  assistantConfig.model_type = nextType

  try {
    await apiFetch('/api/agent-config/models/active', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: model.id }),
    })
    if (!options.skipTypeSave) {
      await saveBasicConfig({ model_type: nextType }, '', true)
    }
    showToast(options.successMessage || `模型已切换为 ${model.name}`)
  } catch (error) {
    if (previousId) markActiveModel(previousId)
    assistantConfig.model_type = previousType
    showToast(`切换模型失败：${error.message}`)
  }
}

async function toggleMcp(mcp) {
  const previous = !!mcp.enabled
  const nextEnabled = !previous
  mcp.enabled = nextEnabled
  try {
    await apiFetch(`/api/agent-config/mcps/${mcp.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: nextEnabled }),
    })
    showToast(`${nextEnabled ? '已启用' : '已停用'} ${mcp.name}`)
  } catch (error) {
    mcp.enabled = previous
    showToast(`更新 MCP 失败：${error.message}`)
  }
}

async function pingMcp(mcp) {
  try {
    const result = await apiFetch(`/api/agent-config/mcps/${mcp.id}/ping`, {
      method: 'POST',
    })
    mcp.ok = !!result?.ok
    showToast(result?.ok ? `${mcp.name} 在线` : `${mcp.name} 不可达`)
  } catch (error) {
    showToast(`探测 MCP 失败：${error.message}`)
  }
}

async function toggleSkill(skill) {
  const previous = !!skill.enabled
  const nextEnabled = !previous
  skill.enabled = nextEnabled
  try {
    await apiFetch(`/api/agent-config/skills/${skill.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: nextEnabled }),
    })
    showToast(`${nextEnabled ? '已启用' : '已停用'} ${skill.name}`)
  } catch (error) {
    skill.enabled = previous
    showToast(`更新 Skill 失败：${error.message}`)
  }
}

async function saveConversation() {
  if (!messages.value.length || streaming.value) return
  const title = messages.value.find(item => item.role === 'user')?.content?.slice(0, 60) || '新对话'
  const convId = convIds.value[mode.value]
  const plainMessages = messages.value.map(item => ({
    id: item.id,
    role: item.role,
    content: item.content,
    toolCalls: item.role === 'assistant'
      ? (item.toolCalls || []).map(tc => ({
        id: tc.id,
        tool: tc.tool,
        input: tc.input,
        output: tc.output,
        pending: false,
        expanded: false,
      }))
      : [],
    streaming: false,
    done: true,
  }))

  try {
    await apiFetch(`/api/agent/conversations/${convId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: mode.value,
        title,
        messages: plainMessages,
      }),
    })
    await loadHistoryList()
  } catch {
    // ignore
  }
}

async function loadConversation(item) {
  if (streaming.value) return
  try {
    const data = await apiFetch(`/api/agent/conversations/${item.conv_id}`)
    mode.value = data?.mode || item.mode
    convIds.value[mode.value] = item.conv_id
    messages.value = (data?.messages || []).map(message => reactive({
      ...message,
      toolCalls: (message.toolCalls || []).map(toolCall => reactive({ ...toolCall })),
    }))
    nextTick(() => bottomRef.value?.scrollIntoView({ behavior: 'smooth' }))
  } catch {
    // ignore
  }
}

async function deleteConversation(convId) {
  try {
    await apiFetch(`/api/agent/conversations/${convId}`, {
      method: 'DELETE',
    })
    historyList.value = historyList.value.filter(item => item.conv_id !== convId)
    if (convIds.value[mode.value] === convId) {
      clearChat()
    }
  } catch {
    // ignore
  }
}

function newConversation() {
  clearChat()
}

function applyRoutePreset() {
  const requestedMode = String(route.query.mode || '').trim()
  if (requestedMode && MODES.some(item => item.key === requestedMode)) {
    mode.value = requestedMode
  }

  const presetPrompt = String(route.query.prompt || '').trim()
  if (!presetPrompt) return
  inputText.value = presetPrompt
  nextTick(() => {
    if (!inputRef.value) return
    inputRef.value.style.height = 'auto'
    inputRef.value.style.height = `${Math.min(inputRef.value.scrollHeight, 160)}px`
  })
}

function formatInput(input) {
  if (!input || typeof input !== 'object') return ''
  const parts = Object.entries(input)
    .filter(([, value]) => value !== '' && value !== null && value !== undefined && value !== 0)
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
  return parts.length ? `(${parts.join(', ')})` : ''
}

function scrollToBottom() {
  nextTick(() => {
    bottomRef.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

function autoResize(event) {
  const el = event.target
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 160)}px`
}

function switchMode(nextMode) {
  if (streaming.value) return
  mode.value = nextMode
  clearChat()
}

function clearChat() {
  messages.value = []
  currentAssistantMsg = null
  streaming.value = false
  inputText.value = ''
  convIds.value[mode.value] = genUUID()
  if (inputRef.value) inputRef.value.style.height = 'auto'
}

function onEnter() {
  onSend()
}

function onSend() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return
  sendMessage(text)
  inputText.value = ''
  if (inputRef.value) inputRef.value.style.height = 'auto'
}

function startInspect() {
  sendMessage('请执行全面系统巡检，检查所有主机状态和日志异常，生成完整巡检报告。')
}

function getModelRuntimeProvider(model) {
  const runtimeProvider = String(model?.runtime_provider || '').trim().toLowerCase()
  if (runtimeProvider) return runtimeProvider
  return getProviderKey(model) === 'anthropic' ? 'anthropic' : 'openai'
}

function buildAgentPayload(text) {
  return {
    message: text,
    conv_id: convIds.value[mode.value],
    home_dir: assistantConfig.home_dir.trim(),
    model_name: activeModel.value?.name || '',
    model_provider: getModelRuntimeProvider(activeModel.value),
  }
}

async function sendMessage(text) {
  if (streaming.value) return

  messages.value.push({
    id: ++msgIdCounter,
    role: 'user',
    content: text,
  })
  scrollToBottom()

  const assistantMsg = reactive({
    id: ++msgIdCounter,
    role: 'assistant',
    content: '',
    toolCalls: [],
    streaming: true,
    done: false,
  })
  messages.value.push(assistantMsg)
  currentAssistantMsg = assistantMsg
  streaming.value = true

  try {
    const resp = await fetch(`/api/agent/${mode.value}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(buildAgentPayload(text)),
    })

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    if (!resp.body) throw new Error('服务端未返回流式数据')

    const reader = resp.body.getReader()
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
            handleEvent(JSON.parse(line.slice(6)), assistantMsg)
          } catch {
            // ignore parse errors
          }
        }
      }
    }
  } catch (error) {
    assistantMsg.content += `\n\n错误：${error.message}`
    assistantMsg.streaming = false
    assistantMsg.done = true
    streaming.value = false
    currentAssistantMsg = null
    saveConversation()
  }
}

function handleEvent(data, message) {
  switch (data.type) {
    case 'token':
      message.content += data.text || ''
      scrollToBottom()
      break

    case 'tool_start':
      message.toolCalls.push(reactive({
        id: ++msgIdCounter,
        tool: data.tool || '',
        input: data.input || {},
        output: null,
        pending: true,
        expanded: false,
      }))
      scrollToBottom()
      break

    case 'tool_end': {
      const toolCall = [...message.toolCalls].reverse().find(item => item.tool === data.tool && item.pending)
      if (toolCall) {
        toolCall.output = data.output || ''
        toolCall.pending = false
      }
      scrollToBottom()
      break
    }

    case 'replace_content':
      message.content = data.text || ''
      scrollToBottom()
      break

    case 'done':
      message.streaming = false
      message.done = true
      streaming.value = false
      currentAssistantMsg = null
      scrollToBottom()
      saveConversation()
      break

    case 'error':
      message.content += `${message.content ? '\n\n' : ''}错误：${data.message || '未知错误'}`
      message.streaming = false
      message.done = true
      streaming.value = false
      currentAssistantMsg = null
      scrollToBottom()
      saveConversation()
      break
  }
}

function isAnsibleTool(toolCall) {
  const tool = String(toolCall.tool || '').toLowerCase()
  return tool.includes('ansible') || tool.includes('playbook') || tool.includes('run_task') || tool.includes('execute_task')
}

function isAnsibleSuccess(toolCall) {
  if (!toolCall.output) return false
  const output = typeof toolCall.output === 'string' ? toolCall.output : JSON.stringify(toolCall.output)
  return output.includes('success') || output.includes('ok') || output.includes('完成') || output.includes('PLAY RECAP')
}

function extractAnsibleField(toolCall, field) {
  if (!toolCall.input) return '--'
  const payload = typeof toolCall.input === 'string'
    ? (() => {
      try {
        return JSON.parse(toolCall.input)
      } catch {
        return {}
      }
    })()
    : toolCall.input
  return payload[field] || payload.hosts || payload.inventory || '--'
}

function extractTaskId(output) {
  if (!output) return null
  const text = typeof output === 'string' ? output : JSON.stringify(output)
  const match = text.match(/task[_\s]?id[:\s]+(\d+)/i) || text.match(/#(\d+)/)
  return match ? match[1] : null
}

function renderContent(text) {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/^(\d+)\.\s+(.+)$/gm, '<div class="ai-li"><span class="ai-li-num">$1</span>$2</div>')
  html = html.replace(/^[-•]\s+(.+)$/gm, '<div class="ai-li"><span class="ai-li-dot">•</span>$1</div>')
  html = html.replace(/`([^`]+)`/g, '<code class="ai-code">$1</code>')
  html = html.replace(/## (.+?)(\n|$)/g, '<div class="ai-section-title">$1</div>')
  html = html.replace(/\n/g, '<br>')
  return html
}

onMounted(async () => {
  window.addEventListener('keydown', handleWindowKeydown)
  applyRoutePreset()
  await Promise.all([
    loadHistoryList(),
    loadWorkbenchData(),
    fetchAiModel(),
  ])
})

onBeforeUnmount(() => {
  aiModelMounted = false
  if (toastTimer) clearTimeout(toastTimer)
  window.removeEventListener('keydown', handleWindowKeydown)
})
</script>

<style scoped>
.agent-page {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
  background:
    radial-gradient(circle at top right, rgba(36, 74, 136, 0.18), transparent 26%),
    radial-gradient(circle at left bottom, rgba(18, 120, 102, 0.16), transparent 22%),
    var(--bg-base, #0b1220);
}

.chat-section {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.history-panel {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(10, 15, 27, 0.92);
  backdrop-filter: blur(18px);
  overflow: hidden;
  transition: width 0.2s ease;
}

.history-panel.collapsed {
  width: 0;
  border-right: none;
}

.history-panel-header {
  padding: 10px 10px 8px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}

.new-conv-btn,
.hdr-btn,
.hint-btn,
.btn-inspect,
.send-btn,
.action-btn,
.history-toggle,
.mode-tab,
.shelf-card,
.close-btn,
.provider-pill,
.model-option,
.mini-btn,
.inline-link {
  font-family: inherit;
}

.new-conv-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(93, 173, 226, 0.24);
  background: linear-gradient(180deg, rgba(24, 38, 58, 0.88), rgba(11, 18, 32, 0.88));
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.new-conv-btn:hover:not(:disabled),
.hdr-btn:hover:not(:disabled),
.history-toggle:hover,
.mode-tab:hover,
.hint-btn:hover,
.action-btn:hover,
.provider-pill:hover,
.mini-btn:hover,
.inline-link:hover {
  border-color: rgba(93, 173, 226, 0.42);
  color: var(--text-primary);
}

.new-conv-btn:disabled,
.hdr-btn:disabled,
.btn-inspect:disabled,
.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 6px 4px;
}

.history-empty {
  padding: 20px 12px;
  color: var(--text-muted);
  font-size: 12px;
  text-align: center;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.12s ease, transform 0.12s ease;
}

.history-item:hover {
  background: rgba(255, 255, 255, 0.04);
  transform: translateX(2px);
}

.history-item.active {
  background: linear-gradient(180deg, rgba(17, 47, 87, 0.6), rgba(16, 30, 53, 0.72));
  box-shadow: inset 0 0 0 1px rgba(93, 173, 226, 0.24);
}

.hi-mode-icon,
.mode-icon,
.agent-icon-wrap,
.assistant-avatar,
.welcome-icon {
  display: flex;
  align-items: center;
  justify-content: center;
}

.hi-mode-icon {
  color: var(--text-muted);
}

.hi-info {
  flex: 1;
  min-width: 0;
}

.hi-title {
  color: var(--text-primary);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hi-date {
  margin-top: 2px;
  color: var(--text-muted);
  font-size: 11px;
}

.hi-model-tag {
  display: inline-flex;
  align-items: center;
  margin-right: 6px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(41, 121, 255, 0.12);
  color: var(--accent, #5dade2);
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 9px;
  font-weight: 700;
}

.hi-del {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s ease;
}

.history-item:hover .hi-del {
  opacity: 1;
}

.hi-del:hover {
  color: #f87171;
  background: rgba(248, 113, 113, 0.1);
}

.agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 16px 20px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(13, 21, 36, 0.96), rgba(13, 21, 36, 0.78));
  backdrop-filter: blur(18px);
}

.agent-title {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.history-toggle,
.hdr-btn,
.close-btn,
.provider-pill,
.mini-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.72);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.16s ease;
}

.history-toggle {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
}

.agent-icon-wrap {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 12px;
  background:
    linear-gradient(135deg, rgba(93, 173, 226, 0.2), rgba(62, 207, 142, 0.16)),
    rgba(12, 22, 38, 0.9);
  color: var(--accent, #5dade2);
  box-shadow: inset 0 0 0 1px rgba(93, 173, 226, 0.22);
}

.agent-icon-wrap :deep(svg),
.assistant-avatar :deep(svg),
.welcome-icon :deep(svg) {
  width: 18px;
  height: 18px;
}

.agent-title-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-title-row h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 700;
}

.subtitle {
  color: var(--text-muted);
  font-size: 11px;
}

.model-badge,
.provider-badge,
.exec-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
}

.model-badge {
  background: rgba(41, 121, 255, 0.12);
  color: var(--accent, #5dade2);
  border: 1px solid rgba(41, 121, 255, 0.24);
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.provider-badge {
  background: rgba(56, 189, 248, 0.08);
  color: #93c5fd;
  border: 1px solid rgba(56, 189, 248, 0.14);
}

.exec-badge {
  background: rgba(250, 204, 21, 0.12);
  color: #facc15;
  border: 1px solid rgba(250, 204, 21, 0.2);
}

.exec-badge::before {
  content: '';
  width: 5px;
  height: 5px;
  margin-right: 5px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 0.8s step-end infinite;
}

.exec-badge.idle {
  background: rgba(34, 197, 94, 0.1);
  color: #4ade80;
  border-color: rgba(34, 197, 94, 0.18);
}

.exec-badge.idle::before {
  animation: none;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.mode-tabs {
  display: flex;
  gap: 8px;
  padding: 4px;
  border-radius: 14px;
  background: rgba(7, 13, 24, 0.72);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.12);
}

.mode-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.mode-tab.active {
  color: #e2e8f0;
  background: linear-gradient(180deg, rgba(17, 47, 87, 0.84), rgba(13, 23, 39, 0.92));
  border-color: rgba(93, 173, 226, 0.28);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.hdr-btn {
  padding: 8px 12px;
  font-size: 12px;
  white-space: nowrap;
}

.quick-shelf {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 14px 20px 8px;
  background: linear-gradient(180deg, rgba(12, 18, 30, 0.86), rgba(12, 18, 30, 0.22));
}

.shelf-card {
  min-width: 0;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background:
    linear-gradient(180deg, rgba(17, 25, 40, 0.95), rgba(10, 15, 27, 0.88));
  cursor: pointer;
  text-align: left;
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.shelf-card:hover {
  transform: translateY(-2px);
  border-color: rgba(93, 173, 226, 0.24);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
}

.shelf-kicker,
.shell-kicker,
.workbench-kicker,
.bench-index,
.bench-headline p,
.field-note,
.tool-kind {
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.shelf-kicker {
  display: block;
  color: #7dd3fc;
  font-size: 10px;
  font-weight: 700;
}

.shelf-title {
  display: block;
  margin-top: 6px;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.shelf-meta {
  display: block;
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-area {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.welcome-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 40px 20px;
  text-align: center;
}

.welcome-icon {
  width: 58px;
  height: 58px;
  border-radius: 18px;
  background:
    linear-gradient(135deg, rgba(93, 173, 226, 0.18), rgba(52, 211, 153, 0.16)),
    rgba(12, 18, 30, 0.92);
  color: var(--accent, #5dade2);
  box-shadow: inset 0 0 0 1px rgba(93, 173, 226, 0.24);
}

.welcome-title {
  color: var(--text-primary);
  font-size: 22px;
  font-weight: 700;
}

.welcome-desc {
  max-width: 520px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.7;
}

.welcome-runtime,
.runtime-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.runtime-chip {
  display: inline-flex;
  align-items: center;
  padding: 5px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.7);
  color: var(--text-secondary);
  border: 1px solid rgba(148, 163, 184, 0.14);
  font-size: 11px;
  white-space: nowrap;
}

.welcome-hints {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-top: 6px;
}

.hint-btn {
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.72);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.16s ease;
}

.hint-btn:hover {
  background: rgba(17, 47, 87, 0.54);
  color: var(--text-primary);
}

.msg-wrapper {
  display: flex;
}

.msg-wrapper.user {
  justify-content: flex-end;
}

.msg-wrapper.assistant {
  justify-content: flex-start;
}

.user-bubble {
  max-width: 72%;
  padding: 12px 16px;
  border-radius: 16px 16px 4px 16px;
  background: linear-gradient(135deg, #2563eb, #0f766e);
  color: #fff;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
  box-shadow: 0 10px 30px rgba(15, 118, 110, 0.22);
}

.assistant-msg {
  display: flex;
  gap: 10px;
  max-width: 88%;
}

.assistant-avatar {
  width: 30px;
  height: 30px;
  margin-top: 2px;
  flex-shrink: 0;
  border-radius: 10px;
  color: var(--accent, #5dade2);
  border: 1px solid rgba(93, 173, 226, 0.2);
  background: linear-gradient(135deg, rgba(93, 173, 226, 0.18), rgba(52, 211, 153, 0.14));
}

.assistant-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tool-card,
.ansible-card,
.ai-text,
.input-shell,
.bench-section,
.tool-row,
.skill-row {
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(12, 18, 30, 0.92);
}

/* ── Trace 追踪面板 ─────────────────────────────── */
.trace-panel {
  width: 300px; flex-shrink: 0;
  display: flex; flex-direction: column;
  background: var(--bg-card); border-left: 1px solid var(--border);
  overflow: hidden;
}
/* 四层进度条 */
.trace-layers-bar {
  display: flex; gap: 4px; padding: 8px 10px 0;
  border-bottom: 1px solid var(--border-light); padding-bottom: 8px;
}
.trace-layer-pill {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 5px 4px; border-radius: 8px; border: 1px solid var(--border-light);
  background: var(--bg-surface); opacity: .4; transition: .2s;
}
.trace-layer-pill.active { opacity: 1; border-color: var(--lc); background: color-mix(in srgb, var(--lc) 12%, transparent); }
.tlp-key  { font-size: 9px; font-weight: 800; color: var(--lc); letter-spacing: .04em; }
.tlp-name { font-size: 9px; color: var(--text-muted); }
.tlp-cnt  { font-size: 11px; font-weight: 700; color: var(--text-primary); }

.trace-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.trace-title { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 700; color: var(--text-secondary); flex: 1; }
.trace-count  { font-size: 11px; color: var(--accent); background: var(--accent-dim); padding: 1px 7px; border-radius: 999px; }
.trace-close  { background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 14px; padding: 0 2px; }

.trace-body { flex: 1; overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 6px; }
.trace-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 40px 20px; color: var(--text-muted); font-size: 12px; }
.trace-empty-icon { font-size: 28px; opacity: .4; animation: spin .8s linear infinite; }

.trace-item {
  border-radius: 10px; border: 1px solid var(--border);
  background: var(--bg-surface); cursor: pointer;
  transition: border-color .15s, background .15s;
  overflow: hidden;
}
.trace-item:hover { border-color: var(--border-accent); background: var(--bg-hover); }
.trace-item.running { border-color: rgba(251,191,36,.3); }
.trace-item.done    { border-color: rgba(34,197,94,.15); }

.trace-item-head {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 10px; flex-wrap: wrap;
}
.trace-step { width: 18px; height: 18px; border-radius: 50%; background: var(--accent-dim); color: var(--accent); font-size: 9px; font-weight: 700; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.trace-layer-badge { font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 4px; flex-shrink: 0; letter-spacing: .04em; }
.trace-status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.trace-status-dot.ok   { background: var(--success); }
.trace-status-dot.spin { border: 2px solid rgba(251,191,36,.3); border-top-color: var(--warning); animation: spin .8s linear infinite; }
.trace-tool-icon  { font-size: 13px; }
.trace-tool-name  { font-size: 11px; font-weight: 600; color: var(--text-primary); flex: 1; }
.trace-elapsed    { font-size: 10px; color: var(--success); background: rgba(34,197,94,.1); padding: 1px 5px; border-radius: 4px; }
.trace-running-text { font-size: 10px; color: var(--warning); font-style: italic; }
.trace-arrow      { color: var(--text-muted); font-size: 11px; transition: transform .15s; }
.trace-arrow.open { transform: rotate(180deg); }

.trace-input-row, .trace-output-row {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 4px 10px; font-size: 10.5px;
}
.trace-label { font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px; background: var(--bg-hover); color: var(--text-muted); flex-shrink: 0; margin-top: 1px; }
.trace-val    { color: var(--text-secondary); word-break: break-all; line-height: 1.5; }
.trace-val.ok { color: var(--success); }

.trace-detail { padding: 6px 10px 8px; border-top: 1px solid var(--border-light); }
.trace-detail-label { font-size: 9px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 3px; }
.trace-detail-block + .trace-detail-block { margin-top: 8px; }
.trace-pre { font-size: 10px; font-family: 'Cascadia Code','Consolas',monospace; color: var(--text-secondary); overflow-x: auto; line-height: 1.5; white-space: pre; margin: 0; max-height: 160px; overflow-y: auto; }

/* Trace 面板进入动画 */
.trace-slide-enter-active, .trace-slide-leave-active { transition: width .2s, opacity .2s; overflow: hidden; }
.trace-slide-enter-from, .trace-slide-leave-to { width: 0 !important; opacity: 0; }

/* 思考中动画 */
.thinking-indicator {
  display: flex; align-items: center; gap: 5px;
  padding: 8px 12px; background: var(--bg-surface);
  border-radius: 10px; border: 1px solid var(--border-light);
}
.think-label { font-size: 11px; color: var(--text-muted); }
.think-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent); animation: thinkPulse 1.2s ease-in-out infinite;
}
.think-dot.delay1 { animation-delay: .2s; }
.think-dot.delay2 { animation-delay: .4s; }
@keyframes thinkPulse { 0%,100%{ opacity:.2; transform:scale(.7); } 50%{ opacity:1; transform:scale(1); } }

/* Trace 面板内思考中 */
.trace-thinking {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 12px; border-radius: 10px;
  border: 1px dashed var(--border);
  background: var(--bg-hover);
}
.think-text { font-size: 11px; color: var(--text-muted); }

/* ── 工具卡片（保留原有样式） ─────────────────── */
.tool-card {
  border-radius: 12px;
  overflow: hidden;
  font-size: 12px;
}

.tool-card.pending {
  border-color: rgba(250, 204, 21, 0.24);
}

.tool-card.done {
  border-color: rgba(74, 222, 128, 0.18);
}

/* hdr-btn active state for trace */
.hdr-btn.active {
  background: var(--accent-dim);
  color: var(--accent);
  border-color: var(--border-accent);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 10px;
  cursor: pointer;
}

.tool-header:hover {
  background: rgba(255, 255, 255, 0.03);
}

.tool-status-dot {
  width: 8px;
  height: 8px;
  flex-shrink: 0;
  border-radius: 50%;
}

.tool-status-dot.ok {
  background: #4ade80;
}

.tool-status-dot.spin {
  border: 2px solid rgba(250, 204, 21, 0.22);
  border-top-color: #facc15;
  animation: spin 0.8s linear infinite;
}

.tool-name {
  color: var(--text-primary);
  font-weight: 700;
}

.tool-params,
.tool-output pre,
.mono {
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.tool-params,
.tool-row-meta {
  color: var(--text-muted);
  font-size: 11px;
}

.tool-pending-text {
  color: #facc15;
  font-style: italic;
}

.tool-expand-btn {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 11px;
}

.tool-output {
  border-top: 1px solid rgba(148, 163, 184, 0.14);
  padding: 9px 10px;
  background: rgba(6, 10, 18, 0.94);
}

.tool-output pre {
  margin: 0;
  max-height: 240px;
  overflow-y: auto;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}

.ansible-card {
  min-width: 280px;
  border-radius: 12px;
  overflow: hidden;
  border-color: rgba(74, 222, 128, 0.2);
}

.ansible-card.pending {
  border-color: rgba(250, 204, 21, 0.24);
}

.ansible-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  background: rgba(74, 222, 128, 0.06);
  border-bottom: 1px solid rgba(74, 222, 128, 0.14);
}

.ansible-card.pending .ansible-header {
  background: rgba(250, 204, 21, 0.06);
  border-bottom-color: rgba(250, 204, 21, 0.14);
}

.ansible-icon {
  display: flex;
  align-items: center;
  color: #4ade80;
}

.ansible-card.pending .ansible-icon {
  color: #facc15;
}

.ansible-title {
  flex: 1;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 700;
}

.ansible-status {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.ansible-status.running {
  background: rgba(250, 204, 21, 0.14);
  color: #facc15;
}

.ansible-status.success {
  background: rgba(74, 222, 128, 0.14);
  color: #4ade80;
}

.ansible-status.failed {
  background: rgba(248, 113, 113, 0.12);
  color: #f87171;
}

.ansible-body {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ansible-field {
  display: flex;
  gap: 12px;
  align-items: center;
}

.ansible-key {
  width: 60px;
  flex-shrink: 0;
  color: var(--text-muted);
  font-size: 11px;
}

.ansible-val {
  color: var(--text-primary);
  font-size: 12px;
}

.ansible-log {
  padding: 6px 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
}

.ansible-log:hover {
  color: var(--text-secondary);
}

.ai-text {
  padding: 12px 14px;
  border-radius: 4px 16px 16px 16px;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.8;
}

.cursor-blink {
  display: inline-block;
  width: 2px;
  height: 14px;
  margin-left: 2px;
  background: var(--accent, #5dade2);
  vertical-align: middle;
  animation: blink 0.9s step-end infinite;
}

.ai-content :deep(.ai-section-title) {
  margin: 10px 0 4px;
  padding-left: 8px;
  border-left: 3px solid var(--accent, #5dade2);
  color: var(--accent, #5dade2);
  font-size: 13px;
  font-weight: 700;
}

.ai-content :deep(strong) {
  color: var(--text-primary);
  font-weight: 700;
}

.ai-content :deep(.ai-li) {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin: 4px 0;
  padding-left: 4px;
}

.ai-content :deep(.ai-li-num) {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--accent, #5dade2);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.ai-content :deep(.ai-li-dot) {
  color: var(--accent, #5dade2);
  font-weight: 700;
}

.ai-content :deep(.ai-code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(37, 99, 235, 0.12);
  color: #93c5fd;
  font-size: 11px;
}

.input-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 20px 14px;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(10, 15, 27, 0.2), rgba(10, 15, 27, 0.88));
}

.runtime-bar {
  justify-content: flex-start;
}

.inspect-quick {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.btn-inspect {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 11px 22px;
  border-radius: 12px;
  border: 1px solid rgba(93, 173, 226, 0.32);
  background: linear-gradient(135deg, rgba(25, 89, 200, 0.14), rgba(14, 116, 144, 0.12));
  color: #bfdbfe;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.16s ease;
}

.btn-inspect:hover:not(:disabled) {
  transform: translateY(-1px);
}

.inspect-hint {
  color: var(--text-muted);
  font-size: 12px;
}

.input-shell {
  padding: 10px;
  border-radius: 16px;
}

.input-shell-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.shell-kicker {
  color: #7dd3fc;
  font-size: 10px;
  font-weight: 700;
}

.inline-link {
  border: none;
  background: none;
  color: #93c5fd;
  font-size: 11px;
  cursor: pointer;
}

.input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.chat-input {
  flex: 1;
  min-height: 42px;
  max-height: 160px;
  padding: 11px 12px;
  resize: none;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(6, 10, 18, 0.9);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
  outline: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.chat-input:focus {
  border-color: rgba(93, 173, 226, 0.32);
  box-shadow: 0 0 0 3px rgba(93, 173, 226, 0.08);
}

.chat-input:disabled {
  opacity: 0.55;
}

.chat-input::placeholder {
  color: var(--text-muted);
}

.send-btn {
  width: 42px;
  height: 42px;
  flex-shrink: 0;
  border-radius: 12px;
  border: 1px solid rgba(41, 121, 255, 0.3);
  background: linear-gradient(135deg, #2563eb, #0f766e);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: transform 0.16s ease, opacity 0.16s ease;
}

.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.input-hint-text {
  flex: 1;
  color: var(--text-muted);
  font-size: 11px;
}

.action-btn {
  border: none;
  background: none;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
}

.workbench-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(2, 6, 23, 0.45);
  backdrop-filter: blur(2px);
  z-index: 12;
}

.workbench-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(420px, 100%);
  z-index: 13;
  display: flex;
  flex-direction: column;
  border-left: 1px solid rgba(148, 163, 184, 0.14);
  background:
    linear-gradient(180deg, rgba(10, 15, 27, 0.98), rgba(8, 12, 20, 0.98));
  box-shadow: -24px 0 48px rgba(0, 0, 0, 0.24);
}

.workbench-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 18px 14px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
}

.workbench-kicker {
  color: #7dd3fc;
  font-size: 10px;
  font-weight: 700;
}

.workbench-head h2 {
  margin: 6px 0 4px;
  color: var(--text-primary);
  font-size: 20px;
}

.workbench-head p {
  margin: 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.6;
}

.close-btn {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
}

.workbench-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.bench-section {
  border-radius: 18px;
  padding: 14px;
  transition: border-color 0.16s ease, transform 0.16s ease;
}

.bench-section.focus {
  border-color: rgba(93, 173, 226, 0.24);
  transform: translateY(-1px);
}

.bench-headline {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.bench-index {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(41, 121, 255, 0.12);
  color: #93c5fd;
  font-size: 11px;
  font-weight: 800;
  flex-shrink: 0;
}

.bench-headline h3 {
  margin: 0 0 4px;
  color: var(--text-primary);
  font-size: 14px;
}

.bench-headline p {
  margin: 0;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.6;
}

.field-label {
  display: block;
  margin-bottom: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.field-input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(6, 10, 18, 0.92);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}

.field-input:focus {
  border-color: rgba(93, 173, 226, 0.32);
  box-shadow: 0 0 0 3px rgba(93, 173, 226, 0.08);
}

.field-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
}

.field-note {
  color: var(--text-muted);
  font-size: 10px;
}

.button-group {
  display: flex;
  gap: 8px;
}

.mini-btn {
  padding: 7px 10px;
  font-size: 11px;
}

.mini-btn.primary {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.22), rgba(15, 118, 110, 0.16));
  color: #e2e8f0;
  border-color: rgba(41, 121, 255, 0.24);
}

.provider-pills {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.provider-pill {
  padding: 7px 10px;
  font-size: 11px;
}

.provider-pill.active {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.18), rgba(14, 116, 144, 0.12));
  color: #e2e8f0;
  border-color: rgba(93, 173, 226, 0.26);
}

.model-stack,
.tool-stack,
.skill-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.model-option {
  width: 100%;
  padding: 12px;
  text-align: left;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(6, 10, 18, 0.72);
  color: var(--text-primary);
  cursor: pointer;
  transition: all 0.16s ease;
}

.model-option:hover {
  border-color: rgba(93, 173, 226, 0.24);
}

.model-option.active {
  border-color: rgba(93, 173, 226, 0.3);
  background: linear-gradient(180deg, rgba(17, 47, 87, 0.54), rgba(7, 13, 24, 0.92));
}

.model-option-top,
.tool-row-title,
.skill-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-option-top {
  justify-content: space-between;
}

.model-option-name {
  font-size: 13px;
  font-weight: 700;
}

.model-option-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--text-muted);
  font-size: 11px;
}

.model-option-meta code {
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(41, 121, 255, 0.12);
  color: #93c5fd;
  font-size: 10px;
}

.model-active-tag {
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(74, 222, 128, 0.12);
  color: #4ade80;
  font-size: 10px;
  font-weight: 800;
}

.tool-row,
.skill-row {
  border-radius: 14px;
  padding: 12px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.tool-row-main,
.skill-main {
  flex: 1;
  min-width: 0;
}

.tool-kind {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.1);
  color: #7dd3fc;
  font-size: 10px;
  font-weight: 700;
}

.tool-row-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.tool-row-meta {
  margin-top: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.skill-row.on {
  border-color: rgba(93, 173, 226, 0.24);
}

.skill-icon {
  font-size: 16px;
}

.skill-desc {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.skill-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.skill-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(41, 121, 255, 0.1);
  color: #93c5fd;
  font-size: 10px;
}

.toggle-switch {
  position: relative;
  width: 36px;
  height: 20px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.22);
  cursor: pointer;
  transition: background 0.16s ease;
  flex-shrink: 0;
}

.toggle-switch.on {
  background: linear-gradient(135deg, #2563eb, #0f766e);
}

.toggle-switch.sm {
  width: 30px;
  height: 18px;
}

.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.28);
  transition: transform 0.16s ease;
}

.toggle-switch.sm .toggle-thumb {
  width: 14px;
  height: 14px;
}

.toggle-switch.on .toggle-thumb {
  transform: translateX(16px);
}

.toggle-switch.sm.on .toggle-thumb {
  transform: translateX(12px);
}

.spinner-sm {
  width: 14px;
  height: 14px;
  display: inline-block;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.toast-msg {
  position: absolute;
  top: 18px;
  right: 20px;
  z-index: 20;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid rgba(93, 173, 226, 0.2);
  background: rgba(10, 15, 27, 0.95);
  color: var(--text-primary);
  font-size: 12px;
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.24);
}

.toast-enter-active,
.toast-leave-active,
.fade-enter-active,
.fade-leave-active,
.drawer-enter-active,
.drawer-leave-active {
  transition: all 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
  transform: translateX(24px);
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

@keyframes pulse {
  50% {
    opacity: 0.55;
  }
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1240px) {
  .quick-shelf {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 960px) {
  .agent-header {
    align-items: flex-start;
    flex-direction: column;
  }

  .header-right {
    width: 100%;
    flex-direction: column;
    align-items: stretch;
  }

  .mode-tabs {
    width: 100%;
    justify-content: space-between;
  }

  .header-actions {
    justify-content: flex-end;
  }
}

@media (max-width: 820px) {
  .history-panel {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    z-index: 14;
    width: 260px;
  }

  .history-panel.collapsed {
    width: 0;
  }

  .quick-shelf {
    grid-template-columns: 1fr;
  }

  .assistant-msg,
  .user-bubble {
    max-width: 100%;
  }
}

@media (max-width: 640px) {
  .agent-header,
  .quick-shelf,
  .chat-area,
  .input-area {
    padding-left: 14px;
    padding-right: 14px;
  }

  .mode-tabs {
    flex-wrap: wrap;
  }

  .mode-tab {
    flex: 1 1 calc(50% - 4px);
    justify-content: center;
  }

  .field-actions,
  .inspect-quick,
  .input-actions {
    flex-direction: column;
    align-items: flex-start;
  }

  .button-group,
  .header-actions {
    width: 100%;
  }

  .button-group .mini-btn,
  .header-actions .hdr-btn {
    flex: 1;
  }
}

/* Align with current AIOps theme */
.page.agent-page {
  position: relative;
  display: flex;
  gap: 16px;
  padding: 20px 24px;
  overflow: hidden;
  background: transparent;
}

.history-panel,
.chat-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-sm);
}

.history-panel {
  width: 236px;
  backdrop-filter: none;
}

.history-panel-header {
  padding: 12px;
  border-bottom-color: var(--border-light);
}

.chat-section {
  background: var(--bg-card);
}

.agent-header,
.quick-shelf,
.input-area {
  background: transparent;
  backdrop-filter: none;
}

.agent-header {
  padding: 16px 18px 12px;
  border-bottom-color: var(--border-light);
}

.quick-shelf {
  padding: 0 18px 14px;
}

.chat-area {
  padding: 0 18px 18px;
}

.input-area {
  padding: 12px 18px 16px;
  border-top-color: var(--border-light);
}

.new-conv-btn,
.history-toggle,
.hdr-btn,
.close-btn,
.provider-pill,
.mini-btn,
.mode-tab {
  background: var(--bg-card);
  border-color: var(--border);
  color: var(--text-secondary);
  box-shadow: none;
}

.new-conv-btn {
  justify-content: flex-start;
  padding: 8px 10px;
  border-radius: var(--radius);
  background: var(--bg-surface);
}

.new-conv-btn:hover:not(:disabled),
.history-toggle:hover,
.hdr-btn:hover:not(:disabled),
.close-btn:hover,
.provider-pill:hover,
.mini-btn:hover,
.action-btn:hover,
.inline-link:hover {
  background: var(--bg-hover);
  border-color: var(--border-accent);
  color: var(--accent);
}

.history-item:hover {
  background: var(--bg-hover);
  transform: none;
}

.history-item.active {
  background: var(--accent-dim);
  box-shadow: none;
}

.agent-icon-wrap,
.assistant-avatar,
.welcome-icon {
  background: var(--accent-dim);
  color: var(--accent);
  border: 1px solid var(--border-accent);
  box-shadow: none;
}

.agent-title-row h1 {
  font-size: 15px;
  font-weight: 600;
}

.subtitle {
  color: var(--text-secondary);
  font-size: 12px;
}

.model-badge {
  background: var(--accent-dim);
  color: var(--accent);
  border-color: var(--border-accent);
}

.provider-badge {
  background: var(--bg-surface);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}

.exec-badge {
  background: rgba(var(--warning-rgb), 0.12);
  color: var(--warning);
  border-color: rgba(var(--warning-rgb), 0.22);
}

.exec-badge.idle {
  background: rgba(var(--success-rgb), 0.12);
  color: var(--success);
  border-color: rgba(var(--success-rgb), 0.22);
}

.mode-tabs {
  gap: 6px;
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.mode-tab {
  border-radius: var(--radius);
  background: var(--bg-surface);
}

.mode-tab:hover {
  background: var(--bg-hover);
  color: var(--accent);
  border-color: var(--border-accent);
}

.mode-tab.active {
  background: var(--accent-dim);
  color: var(--accent);
  border-color: var(--border-accent);
}

.shelf-card {
  border-radius: var(--radius-card);
  border-color: var(--border);
  background: var(--bg-surface);
  box-shadow: none;
}

.shelf-card:hover {
  transform: none;
  background: var(--bg-card);
  border-color: var(--border-accent);
  box-shadow: var(--shadow-sm);
}

.shelf-kicker,
.shell-kicker,
.workbench-kicker {
  color: var(--accent);
}

.runtime-chip,
.tool-kind,
.skill-tag,
.model-option-meta code {
  background: var(--accent-dim);
  color: var(--accent);
  border: 1px solid transparent;
}

.runtime-chip {
  background: var(--bg-surface);
  border-color: var(--border);
  color: var(--text-secondary);
}

.hint-btn {
  background: var(--bg-card);
  border-color: var(--border);
  color: var(--text-secondary);
}

.hint-btn:hover {
  background: var(--accent-dim);
  color: var(--accent);
  border-color: var(--border-accent);
}

.user-bubble {
  background: var(--accent);
  box-shadow: none;
}

.tool-card,
.ansible-card,
.ai-text,
.input-shell,
.bench-section,
.tool-row,
.skill-row,
.model-option {
  background: var(--bg-surface);
  border-color: var(--border);
  box-shadow: none;
}

.tool-header:hover {
  background: var(--bg-hover);
}

.tool-card.pending {
  border-color: rgba(var(--warning-rgb), 0.28);
}

.tool-card.done,
.ansible-card {
  border-color: var(--border);
}

.tool-output {
  background: color-mix(in srgb, var(--bg-surface) 72%, var(--bg-base));
  border-top-color: var(--border-light);
}

.ansible-header {
  background: rgba(var(--success-rgb), 0.08);
  border-bottom-color: var(--border-light);
}

.ansible-card.pending .ansible-header {
  background: rgba(var(--warning-rgb), 0.08);
  border-bottom-color: var(--border-light);
}

.ansible-icon {
  color: var(--success);
}

.ansible-card.pending .ansible-icon {
  color: var(--warning);
}

.ansible-status.running {
  background: rgba(var(--warning-rgb), 0.12);
  color: var(--warning);
}

.ansible-status.success {
  background: rgba(var(--success-rgb), 0.12);
  color: var(--success);
}

.ansible-status.failed {
  background: rgba(var(--error-rgb), 0.12);
  color: var(--error);
}

.ai-text {
  background: var(--bg-card);
  line-height: 1.75;
}

.ai-content :deep(.ai-code) {
  background: var(--accent-dim);
  color: var(--accent);
}

.btn-inspect {
  border-color: var(--border-accent);
  background: var(--accent-dim);
  color: var(--accent);
}

.btn-inspect:hover:not(:disabled),
.send-btn:hover:not(:disabled) {
  transform: none;
}

.input-shell {
  padding: 12px;
  border-radius: var(--radius-card);
}

.inline-link {
  color: var(--accent);
}

.chat-input,
.field-input {
  background: var(--bg-input);
  border-color: var(--border);
}

.chat-input:focus,
.field-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px rgba(var(--accent-rgb), 0.1);
}

.send-btn,
.toggle-switch.on,
.mini-btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.send-btn {
  box-shadow: none;
}

.workbench-backdrop {
  background: rgba(9, 18, 36, 0.26);
  backdrop-filter: none;
}

.workbench-panel {
  top: 12px;
  right: 12px;
  bottom: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  background: var(--bg-card);
  box-shadow: var(--shadow-md);
}

.workbench-head {
  padding: 16px 18px 14px;
  border-bottom-color: var(--border-light);
}

.bench-section {
  border-radius: var(--radius-card);
}

.bench-section.focus {
  border-color: var(--border-accent);
  transform: none;
  box-shadow: var(--shadow-sm);
}

.bench-index {
  background: var(--accent-dim);
  color: var(--accent);
}

.provider-pill.active,
.model-option.active,
.skill-row.on {
  background: var(--accent-dim);
  border-color: var(--border-accent);
  color: var(--text-primary);
}

.model-active-tag {
  background: rgba(var(--success-rgb), 0.12);
  color: var(--success);
}

.toggle-switch {
  background: var(--border-strong);
}

.toast-msg {
  background: var(--bg-card);
  border-color: var(--border);
  box-shadow: var(--shadow-md);
}

@media (max-width: 820px) {
  .page.agent-page {
    padding: 16px;
  }

  .history-panel {
    box-shadow: var(--shadow-md);
  }

  .workbench-panel {
    left: 16px;
    right: 16px;
    top: 16px;
    bottom: 16px;
    width: auto;
  }
}

@media (max-width: 640px) {
  .page.agent-page {
    padding: 14px;
    gap: 12px;
  }
}
</style>
