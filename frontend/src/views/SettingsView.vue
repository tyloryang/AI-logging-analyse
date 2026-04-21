<template>
  <div class="page">
    <div class="page-header">
      <h1>系统配置</h1>
      <span class="subtitle">连接设置 · 仅管理员可见</span>
    </div>

    <div v-if="loadError" class="alert-error">{{ loadError }}</div>

    <div v-if="saveNote" class="alert-note">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
      {{ saveNote }}
    </div>

    <div class="settings-grid">

      <!-- Prometheus -->
      <div class="card settings-section">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon prom">P</span>
            Prometheus
          </div>
          <span class="conn-badge" :class="promStatus">
            <span class="badge-dot"></span>
            {{ promStatusText }}
          </span>
        </div>

        <div class="field-group">
          <div class="field">
            <label>接入地址</label>
            <div class="input-row">
              <input v-model="form.prometheus_url" placeholder="http://192.168.x.x:9090" />
              <button class="btn btn-outline btn-sm" @click="testConn('prometheus')" :disabled="testing.prometheus">
                {{ testing.prometheus ? '测试中...' : '测试连接' }}
              </button>
            </div>
          </div>
          <div class="field-row">
            <div class="field">
              <label>用户名（可选）</label>
              <input v-model="form.prometheus_username" placeholder="留空表示无认证" />
            </div>
            <div class="field">
              <label>密码{{ settings.prometheus_password_set ? '（已设置）' : '' }}</label>
              <input v-model="form.prometheus_password" type="password" :placeholder="settings.prometheus_password_set ? '留空不修改' : '留空表示无认证'" />
            </div>
          </div>
        </div>
      </div>

      <!-- Loki -->
      <div class="card settings-section">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon loki">L</span>
            Loki
          </div>
          <span class="conn-badge" :class="lokiStatus">
            <span class="badge-dot"></span>
            {{ lokiStatusText }}
          </span>
        </div>

        <div class="field-group">
          <div class="field">
            <label>接入地址</label>
            <div class="input-row">
              <input v-model="form.loki_url" placeholder="http://192.168.x.x:3100" />
              <button class="btn btn-outline btn-sm" @click="testConn('loki')" :disabled="testing.loki">
                {{ testing.loki ? '测试中...' : '测试连接' }}
              </button>
            </div>
          </div>
          <div class="field-row">
            <div class="field">
              <label>用户名（可选）</label>
              <input v-model="form.loki_username" placeholder="留空表示无认证" />
            </div>
            <div class="field">
              <label>密码{{ settings.loki_password_set ? '（已设置）' : '' }}</label>
              <input v-model="form.loki_password" type="password" :placeholder="settings.loki_password_set ? '留空不修改' : '留空表示无认证'" />
            </div>
          </div>
        </div>
      </div>

      <!-- Grafana & SkyWalking -->
      <div class="card settings-section">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon grafana">G</span>
            可观测性平台
          </div>
        </div>
        <div class="field-group">
          <div class="field-row">
            <div class="field">
              <label>Grafana 地址</label>
              <input v-model="form.grafana_url" placeholder="http://192.168.x.x:3000" />
            </div>
            <div class="field">
              <label>
                Grafana API Key
                <span class="conn-badge" :class="settings.grafana_api_key_set ? 'ok' : 'idle'" style="margin-left:6px;font-size:10px">
                  {{ settings.grafana_api_key_set ? '已配置' : '未配置' }}
                </span>
              </label>
              <div class="input-with-btn">
                <input v-model="form.grafana_api_key" type="password" placeholder="glsa_xxxx...（Service Account Token）" autocomplete="new-password" />
                <button
                  class="btn btn-outline btn-sm"
                  :disabled="testingGrafana"
                  @click="testGrafana"
                >{{ testingGrafana ? '检测中...' : '测试连通' }}</button>
              </div>
              <!-- 测试结果 -->
              <div v-if="grafanaTestResult" class="grafana-test-result" :class="grafanaTestResult.ok ? 'ok' : 'err'">
                <template v-if="grafanaTestResult.ok">
                  <span class="test-icon">✓</span>
                  连接正常，发现 <b>{{ grafanaTestResult.count }}</b> 个看板
                  <span class="test-version" v-if="grafanaTestResult.version">· Grafana {{ grafanaTestResult.version }}</span>
                </template>
                <template v-else>
                  <span class="test-icon">✗</span>
                  {{ grafanaTestResult.error }}
                </template>
              </div>
            </div>
          </div>
          <div class="field-row">
            <div class="field">
              <label>SkyWalking OAP 地址</label>
              <input v-model="form.skywalking_oap_url" placeholder="http://192.168.x.x:12800" />
            </div>
            <div class="field"></div>
          </div>
          <p class="field-hint">
            Grafana 看板将在"Grafana 看板"页面以 iframe 嵌入展示（需要在 grafana.ini 中设置
            <code>allow_embedding = true</code> 或环境变量 <code>GF_SECURITY_ALLOW_EMBEDDING=true</code>）。
          </p>

          <!-- Grafana 看板管理 -->
          <div class="boards-section">
            <div class="boards-header">
              <span class="boards-title">Grafana 看板列表</span>
              <button class="btn-sm" @click="showAddBoard = !showAddBoard">+ 添加看板</button>
            </div>

            <!-- 添加表单 -->
            <div v-if="showAddBoard" class="add-board-form">
              <input v-model="newBoard.title" placeholder="看板名称（如 Node Exporter）" class="board-input" />
              <input v-model="newBoard.uid" placeholder="Grafana UID（如 rYdddlPWk）" class="board-input" />
              <input v-model="newBoard.url" placeholder="完整 URL（可选，覆盖 UID 拼接）" class="board-input" />
              <div class="add-board-actions">
                <button class="btn-primary-sm" @click="addBoard" :disabled="!newBoard.title">确认添加</button>
                <button class="btn-ghost-sm" @click="showAddBoard = false">取消</button>
              </div>
            </div>

            <!-- 看板列表 -->
            <div class="boards-list">
              <div v-for="b in grafanaBoards" :key="b.id" class="board-row">
                <span class="board-icon">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
                </span>
                <span class="board-title">{{ b.title }}</span>
                <span class="board-uid" v-if="b.uid">{{ b.uid }}</span>
                <span class="board-tag" v-if="b.custom">自定义</span>
                <a v-if="b.url" :href="b.url" target="_blank" class="board-link" title="在新标签打开">↗</a>
                <button v-if="b.custom" class="board-del" @click="removeBoard(b.id)" title="删除">×</button>
              </div>
              <div v-if="!grafanaBoards.length" class="boards-empty">暂无看板，请先配置 Grafana 地址</div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI Provider -->
      <div class="card settings-section">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon ai">AI</span>
            AI 模型
          </div>
          <span class="conn-badge" :class="settings.ai_api_key_set ? 'ok' : 'err'">
            <span class="badge-dot"></span>
            {{ settings.ai_api_key_set ? 'API Key 已配置' : '未配置' }}
          </span>
        </div>

        <div class="field-group">
          <div class="field-row">
            <div class="field">
              <label>Provider</label>
              <select v-model="form.ai_provider">
                <option value="anthropic">Anthropic (Claude)</option>
                <option value="openai">OpenAI Compatible</option>
              </select>
            </div>
            <div class="field">
              <label>模型名称</label>
              <input v-model="form.ai_model" :placeholder="form.ai_provider === 'anthropic' ? 'claude-opus-4-6' : 'Qwen3-32B'" />
            </div>
          </div>
          <div class="field" v-if="form.ai_provider === 'openai'">
            <label>Base URL</label>
            <input v-model="form.ai_base_url" placeholder="http://192.168.x.x:8000/v1" />
          </div>
          <div class="field" v-if="form.ai_provider === 'openai'">
            <label class="checkbox-line">
              <input v-model="form.ai_enable_thinking" type="checkbox" />
              开启 Thinking 模式（仅部分模型支持，如 QwQ；Qwen3 等默认应关闭）
            </label>
          </div>
          <div class="field">
            <label>API Key{{ settings.ai_api_key_set ? '（已设置）' : '' }}</label>
            <div class="input-row">
              <input v-model="form.ai_api_key" type="password" :placeholder="settings.ai_api_key_set ? '留空不修改' : '输入 API Key'" />
              <button class="btn btn-outline btn-sm" @click="testAI" :disabled="testingAI">
                {{ testingAI ? '测试中...' : '测试连接' }}
              </button>
            </div>
            <div v-if="aiTestResult !== null" class="conn-test-result" :class="aiTestResult ? 'ok' : 'err'">
              {{ aiTestMsg }}
            </div>
          </div>
          <div class="feishu-security-title">
            <span class="security-label">Agent 执行器</span>
            <span class="security-hint">可切换为外部 Claude Code / Codex CLI 执行 ReAct</span>
          </div>
          <div class="field-row">
            <div class="field">
              <label>执行模式</label>
              <select v-model="form.agent_executor">
                <option value="langgraph">内置 LangGraph ReAct</option>
                <option value="aiops_cli">本项目 aiops_cli 子进程</option>
                <option value="external_cli">外部 Agent CLI（Claude Code / Codex）</option>
              </select>
            </div>
            <div class="field">
              <label>超时时间（秒）</label>
              <input v-model.number="form.agent_external_timeout" type="number" min="30" placeholder="240" />
            </div>
          </div>
          <template v-if="form.agent_executor === 'external_cli'">
            <div class="field-row">
              <div class="field">
                <label>CLI 命令</label>
                <input v-model="form.agent_external_command" placeholder="留空自动寻找 claude；或填写 claude / codex / 完整路径" />
              </div>
              <div class="field">
                <label>CLI 参数</label>
                <input v-model="form.agent_external_args" placeholder="-p" />
              </div>
            </div>
            <div class="field">
              <label>工作目录</label>
              <input v-model="form.agent_external_workdir" placeholder="留空默认项目根目录 D:\\loki-log-analyse" />
            </div>
            <label class="checkbox-line">
              <input v-model="form.agent_external_use_stdin" type="checkbox" />
              通过 stdin 传入问题（默认作为最后一个命令参数传入）
            </label>
            <p class="field-hint">示例：Claude Code 可用命令 `claude`、参数 `-p`；切到外部 CLI 后，飞书和右侧 AI 助手都会走该执行器。</p>
          </template>
          <p class="field-hint">AI 模型配置会热更新；外部 CLI 模式依赖本机已安装对应命令。</p>
        </div>
      </div>

      <!-- 飞书机器人 -->
      <div class="card settings-section feishu-section">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon feishu">飞</span>
            飞书机器人
          </div>
          <span class="conn-badge" :class="settings.feishu_bot_app_secret_set ? 'ok' : 'idle'">
            <span class="badge-dot"></span>
            {{ settings.feishu_bot_app_secret_set ? '已配置' : '未配置' }}
          </span>
        </div>

        <div class="field-group">
          <!-- App ID / Secret -->
          <div class="field-row">
            <div class="field">
              <label>App ID</label>
              <input v-model="form.feishu_bot_app_id" placeholder="cli_xxxxxxxxxxxxxxxx" />
            </div>
            <div class="field">
              <label>App Secret{{ settings.feishu_bot_app_secret_set ? '（已设置）' : '' }}</label>
              <input v-model="form.feishu_bot_app_secret" type="password"
                     :placeholder="settings.feishu_bot_app_secret_set ? '留空不修改' : '输入 App Secret'" />
            </div>
          </div>

          <div class="field">
            <label class="checkbox-line">
              <input v-model="form.feishu_require_mention" type="checkbox" />
              群聊仅在 @ 机器人后回复
            </label>
            <p class="field-hint">开启后可避免机器人响应群内所有消息；关闭后，群聊里不 @ 也会处理 Jenkins / K8s / ES 等问题。</p>
          </div>

          <!-- 安全配置：Encrypt Key / Verify Token -->
          <div class="feishu-security-title">
            <span class="security-label">安全配置（可选）</span>
            <span class="security-hint">开启飞书事件加密 / 签名校验时填写</span>
          </div>
          <div class="field-row">
            <div class="field">
              <label>Encrypt Key{{ settings.feishu_bot_encrypt_key_set ? '（已设置）' : '' }}</label>
              <input v-model="form.feishu_bot_encrypt_key" type="password"
                     :placeholder="settings.feishu_bot_encrypt_key_set ? '留空不修改' : '事件加密密钥（可选）'" />
            </div>
            <div class="field">
              <label>Verify Token{{ settings.feishu_bot_verify_token_set ? '（已设置）' : '' }}</label>
              <input v-model="form.feishu_bot_verify_token" type="password"
                     :placeholder="settings.feishu_bot_verify_token_set ? '留空不修改' : '签名校验 Token（可选）'" />
            </div>
          </div>

          <div class="feishu-security-title">
            <span class="security-label">独立回调服务</span>
            <span class="security-hint">绑定地址和端口用于单独启动飞书回调进程</span>
          </div>
          <div class="field-row">
            <div class="field">
              <label>绑定 Host / IP</label>
              <input v-model="form.feishu_callback_host" placeholder="0.0.0.0" />
            </div>
            <div class="field">
              <label>绑定端口</label>
              <input v-model.number="form.feishu_callback_port" type="number" min="1" max="65535" placeholder="8001" />
            </div>
          </div>
          <div class="field">
            <label>公网 Base URL（可选）</label>
            <input
              v-model="form.feishu_callback_public_base_url"
              placeholder="https://your-public-domain-or-ip:8001"
            />
            <p class="field-hint">如为空，页面将自动使用当前访问主机 + 独立回调端口拼出回调地址。</p>
          </div>

          <!-- Webhook URL -->
          <div class="field">
            <label>Webhook 回调地址（粘贴到飞书开放平台 → 事件与回调）</label>
            <div class="webhook-url-row">
              <code class="webhook-url">{{ webhookUrl }}</code>
              <button class="btn btn-outline btn-sm" @click="copyWebhook">{{ copied ? '已复制' : '复制' }}</button>
            </div>
          </div>

          <!-- 配置指引 -->
          <div class="feishu-guide">
            <div class="guide-step"><span class="step-num">1</span>飞书开放平台 → 创建/选择应用 → 开启<strong>机器人</strong>能力</div>
            <div class="guide-step"><span class="step-num">2</span>事件与回调 → 配置事件 → 添加 <code>im.message.receive_v1</code></div>
            <div class="guide-step"><span class="step-num">3</span>将上方 Webhook URL 填入回调地址，保存后飞书会发送验证请求</div>
            <div class="guide-step"><span class="step-num">4</span>如需加密，在飞书侧配置 Encrypt Key 后填入本页并保存</div>
            <div class="guide-step"><span class="step-num">5</span>发布应用，在群里添加机器人，即可 @ 机器人开始对话</div>
          </div>
        </div>
      </div>

    </div>

    <!-- 运维工具 -->
    <div class="settings-grid" style="margin-top:16px">

      <!-- Kubernetes -->
      <div class="card settings-section">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon k8s">K8s</span>
            Kubernetes 容器管理
          </div>
          <span class="conn-badge" :class="k8sTestResult === true ? 'ok' : k8sTestResult === false ? 'err' : 'idle'">
            <span class="badge-dot"></span>
            {{ k8sTestResult === true ? '连接正常' : k8sTestResult === false ? '连接失败' : '未测试' }}
          </span>
        </div>
        <div class="field-group">
          <div class="field-row">
            <div class="field" style="flex:1">
              <label>kubeconfig 文件路径</label>
              <div class="input-row">
                <input v-model="form.k8s_kubeconfig"
                       placeholder="留空自动查找（优先用 backend/data/kubeconfig）" />
                <button class="btn btn-sm" :disabled="testingK8s" @click="testK8s" style="white-space:nowrap">
                  {{ testingK8s ? '测试中...' : '测试连接' }}
                </button>
              </div>
              <div class="field-hint">
                推荐：直接把 kubeconfig 文件放到 <code>backend/data/kubeconfig</code>，留空即可自动识别，无需填路径。
              </div>
              <div v-if="k8sTestMsg" class="test-msg" :class="k8sTestResult ? 'ok' : 'err'">
                {{ k8sTestMsg }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Ansible -->
      <div class="card settings-section">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon ansible">A</span>
            Ansible 主机任务
          </div>
          <span class="conn-badge" :class="form.ansible_base_dir ? 'ok' : 'idle'">
            <span class="badge-dot"></span>
            {{ form.ansible_base_dir ? '已配置' : '未配置' }}
          </span>
        </div>
        <div class="field-group">
          <div class="field-row">
            <div class="field" style="flex:1">
              <label>Playbook 根目录</label>
              <input v-model="form.ansible_base_dir"
                     placeholder="如 /opt/ansible 或留空使用 ANSIBLE_BASE_DIR 环境变量" />
              <div class="field-hint">该目录下的 .yml / .yaml 文件会被自动识别为可选 Playbook</div>
            </div>
          </div>
        </div>
      </div>

      <!-- 多云管理（已隐藏）-->
      <div v-if="false" class="card settings-section cloud-section">
        <div class="section-head">
          <div class="section-title">
            <span class="section-icon cloud">☁</span>
            多云管理
          </div>
          <span class="conn-badge" :class="anyCloudConfigured ? 'ok' : 'idle'">
            <span class="badge-dot"></span>
            {{ anyCloudConfigured ? '已配置' : '未配置' }}
          </span>
        </div>
        <div class="field-group">

          <!-- 阿里云 -->
          <div class="cloud-provider-title">
            <span class="provider-dot aliyun"></span>阿里云 Aliyun
          </div>
          <div class="field-row">
            <div class="field">
              <label>Access Key ID</label>
              <input v-model="form.aliyun_access_key_id" placeholder="LTAI5t..." />
            </div>
            <div class="field">
              <label>Access Key Secret{{ settings.aliyun_access_key_secret_set ? '（已设置）' : '' }}</label>
              <input v-model="form.aliyun_access_key_secret" type="password"
                     :placeholder="settings.aliyun_access_key_secret_set ? '留空不修改' : '输入 Secret'" />
            </div>
          </div>

          <!-- AWS -->
          <div class="cloud-provider-title" style="margin-top:6px">
            <span class="provider-dot aws"></span>Amazon Web Services (AWS)
          </div>
          <div class="field-row">
            <div class="field">
              <label>Access Key ID</label>
              <input v-model="form.aws_access_key_id" placeholder="AKIA..." />
            </div>
            <div class="field">
              <label>Secret Access Key{{ settings.aws_secret_access_key_set ? '（已设置）' : '' }}</label>
              <input v-model="form.aws_secret_access_key" type="password"
                     :placeholder="settings.aws_secret_access_key_set ? '留空不修改' : '输入 Secret'" />
            </div>
          </div>
          <div class="field-row">
            <div class="field">
              <label>默认 Region</label>
              <input v-model="form.aws_region" placeholder="ap-east-1" />
            </div>
            <div class="field"></div>
          </div>

          <!-- 腾讯云 -->
          <div class="cloud-provider-title" style="margin-top:6px">
            <span class="provider-dot tencent"></span>腾讯云 Tencent Cloud
          </div>
          <div class="field-row">
            <div class="field">
              <label>SecretId</label>
              <input v-model="form.tencent_secret_id" placeholder="AKIDxxxx..." />
            </div>
            <div class="field">
              <label>SecretKey{{ settings.tencent_secret_key_set ? '（已设置）' : '' }}</label>
              <input v-model="form.tencent_secret_key" type="password"
                     :placeholder="settings.tencent_secret_key_set ? '留空不修改' : '输入 SecretKey'" />
            </div>
          </div>

          <!-- 华为云 -->
          <div class="cloud-provider-title" style="margin-top:6px">
            <span class="provider-dot huawei"></span>华为云 HUAWEI Cloud
          </div>
          <div class="field-row">
            <div class="field">
              <label>Access Key ID (AK)</label>
              <input v-model="form.huawei_access_key_id" placeholder="输入 AK" />
            </div>
            <div class="field">
              <label>Secret Access Key (SK){{ settings.huawei_secret_access_key_set ? '（已设置）' : '' }}</label>
              <input v-model="form.huawei_secret_access_key" type="password"
                     :placeholder="settings.huawei_secret_access_key_set ? '留空不修改' : '输入 SK'" />
            </div>
          </div>
          <div class="field-row">
            <div class="field">
              <label>Project ID</label>
              <input v-model="form.huawei_project_id" placeholder="0cd2..."  />
            </div>
            <div class="field"></div>
          </div>

        </div>
      </div>

    </div>

    <!-- 保存按钮 -->
    <div class="save-row">
      <button class="btn btn-primary" @click="saveSettings" :disabled="saving">
        <span v-if="saving" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
        {{ saving ? '保存中...' : '保存配置' }}
      </button>
      <span class="save-hint">Prometheus / Loki 和飞书密钥配置会立即生效；独立回调服务 Host / 端口改动需重启该独立服务。</span>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const settings  = ref({})
const loadError = ref('')
const saveNote  = ref('')
const saving    = ref(false)
const copied    = ref(false)

// Grafana 看板管理
const grafanaBoards = ref([])
const showAddBoard  = ref(false)
const newBoard = reactive({ title: '', uid: '', url: '' })

const form = reactive({
  prometheus_url:           '',
  prometheus_username:      '',
  prometheus_password:      '',
  loki_url:                 '',
  loki_username:            '',
  loki_password:            '',
  grafana_url:              '',
  grafana_api_key:          '',
  skywalking_oap_url:       '',
  ai_provider:              'anthropic',
  ai_base_url:              '',
  ai_model:                 '',
  ai_api_key:               '',
  ai_enable_thinking:       false,
  agent_executor:           'langgraph',
  agent_external_command:   '',
  agent_external_args:      '-p',
  agent_external_use_stdin: false,
  agent_external_timeout:   240,
  agent_external_workdir:   '',
  feishu_bot_app_id:        '',
  feishu_bot_app_secret:    '',
  feishu_bot_encrypt_key:   '',
  feishu_bot_verify_token:  '',
  feishu_require_mention:   true,
  feishu_callback_host:     '0.0.0.0',
  feishu_callback_port:     8001,
  feishu_callback_public_base_url: '',
  k8s_kubeconfig:           '',
  ansible_base_dir:         '',
  // 多云凭证
  aliyun_access_key_id:     '',
  aliyun_access_key_secret: '',
  aws_access_key_id:        '',
  aws_secret_access_key:    '',
  aws_region:               '',
  tencent_secret_id:        '',
  tencent_secret_key:       '',
  huawei_access_key_id:     '',
  huawei_secret_access_key: '',
  huawei_project_id:        '',
})

const testing     = reactive({ prometheus: false, loki: false })
const testResults = reactive({ prometheus: null, loki: null })  // null | true | false

const testingGrafana    = ref(false)
const grafanaTestResult = ref(null)

const testingK8s  = ref(false)
const k8sTestResult = ref(null)   // null | true | false
const k8sTestMsg  = ref('')

const testingAI   = ref(false)
const aiTestResult = ref(null)    // null | true | false
const aiTestMsg   = ref('')

const anyCloudConfigured = computed(() =>
  !!(form.aliyun_access_key_id || settings.value?.aliyun_access_key_secret_set ||
     form.aws_access_key_id    || settings.value?.aws_secret_access_key_set ||
     form.tencent_secret_id    || settings.value?.tencent_secret_key_set ||
     form.huawei_access_key_id || settings.value?.huawei_secret_access_key_set)
)

const promStatus     = computed(() => testResults.prometheus === null ? 'idle' : testResults.prometheus ? 'ok' : 'err')
const lokiStatus     = computed(() => testResults.loki === null ? 'idle' : testResults.loki ? 'ok' : 'err')
const promStatusText = computed(() => testResults.prometheus === null ? '未测试' : testResults.prometheus ? '连接正常' : '连接失败')
const lokiStatusText = computed(() => testResults.loki === null ? '未测试' : testResults.loki ? '连接正常' : '连接失败')

const webhookUrl = computed(() => {
  const protocol = window.location.protocol || 'http:'
  const host = window.location.hostname
  const publicBaseUrl = (form.feishu_callback_public_base_url || '').trim().replace(/\/$/, '')
  if (publicBaseUrl) {
    return `${publicBaseUrl}/webhook/event`
  }
  const port = form.feishu_callback_port || 8001
  return `${protocol}//${host}:${port}/webhook/event`
})

function applySettings(s) {
  settings.value = s
  form.prometheus_url = s.prometheus_url || ''
  form.prometheus_username = s.prometheus_username || ''
  form.loki_url = s.loki_url || ''
  form.loki_username = s.loki_username || ''
  form.grafana_url = s.grafana_url || ''
  // grafana_api_key 不回显到表单（敏感字段），只保留用户主动输入的值
  // 若服务端已配置（grafana_api_key_set=true），保持表单为空让用户选择是否覆盖
  form.skywalking_oap_url = s.skywalking_oap_url || ''
  form.ai_provider = s.ai_provider || 'anthropic'
  form.ai_base_url = s.ai_base_url || ''
  form.ai_model = s.ai_model || ''
  form.ai_enable_thinking = !!s.ai_enable_thinking
  form.agent_executor = s.agent_executor || 'langgraph'
  form.agent_external_command = s.agent_external_command || ''
  form.agent_external_args = s.agent_external_args || '-p'
  form.agent_external_use_stdin = !!s.agent_external_use_stdin
  form.agent_external_timeout = Number(s.agent_external_timeout) || 240
  form.agent_external_workdir = s.agent_external_workdir || ''
  form.k8s_kubeconfig    = s.k8s_kubeconfig    || ''
  form.ansible_base_dir  = s.ansible_base_dir  || ''
  form.aliyun_access_key_id     = s.aliyun_access_key_id     || ''
  form.aws_access_key_id        = s.aws_access_key_id        || ''
  form.aws_region               = s.aws_region               || ''
  form.tencent_secret_id        = s.tencent_secret_id        || ''
  form.huawei_access_key_id     = s.huawei_access_key_id     || ''
  form.huawei_project_id        = s.huawei_project_id        || ''
  form.feishu_bot_app_id = s.feishu_bot_app_id || ''
  form.feishu_require_mention = s.feishu_require_mention !== false
  form.feishu_callback_host = s.feishu_callback_host || '0.0.0.0'
  form.feishu_callback_port = Number(s.feishu_callback_port) || 8001
  form.feishu_callback_public_base_url = s.feishu_callback_public_base_url || ''
}

async function loadGrafanaBoards() {
  try {
    const data = await api.observabilityGrafanaBoards()
    grafanaBoards.value = data.boards || []
  } catch (e) {
    // non-fatal
  }
}

async function addBoard() {
  if (!newBoard.title) return
  try {
    await api.addGrafanaBoard({ title: newBoard.title, uid: newBoard.uid, url: newBoard.url })
    newBoard.title = ''; newBoard.uid = ''; newBoard.url = ''
    showAddBoard.value = false
    await loadGrafanaBoards()
  } catch (e) {
    alert('添加失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误'))
  }
}

async function removeBoard(id) {
  if (!confirm('确认删除该看板？')) return
  try {
    await api.deleteGrafanaBoard(id)
    await loadGrafanaBoards()
  } catch (e) {
    alert('删除失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误'))
  }
}

onMounted(async () => {
  try {
    applySettings(await api.getSettings())
  } catch (e) {
    loadError.value = '加载配置失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误')
  }
  loadGrafanaBoards()
})

async function testGrafana() {
  testingGrafana.value    = true
  grafanaTestResult.value = null

  // 若表单里填了新 URL 或新 Key，先保存使其热重载，再测试
  const needSave = form.grafana_url || form.grafana_api_key
  if (needSave) {
    try {
      await api.saveSettings({ ...form })
    } catch (_) { /* 保存失败不阻断测试 */ }
  }

  try {
    const r = await api.testGrafanaConnection()
    if (r.health_ok && r.search_ok) {
      grafanaTestResult.value = { ok: true, count: r.search_count, version: r.version || '' }
    } else {
      const err = r.search_error || r.health_error || '连接失败'
      grafanaTestResult.value = { ok: false, error: err }
    }
    // 刷新 API Key 状态徽章
    settings.value = { ...settings.value, grafana_api_key_set: r.api_key_set }
    // 刷新看板列表
    loadGrafanaBoards()
  } catch (e) {
    grafanaTestResult.value = { ok: false, error: typeof e === 'string' ? e : (e?.message || '请求失败') }
  } finally {
    testingGrafana.value = false
  }
}

async function testConn(type) {
  testing[type] = true
  testResults[type] = null
  try {
    const payload = type === 'prometheus'
      ? { url: form.prometheus_url, username: form.prometheus_username, password: form.prometheus_password }
      : { url: form.loki_url,       username: form.loki_username,       password: form.loki_password }
    const fn = type === 'prometheus' ? api.testPrometheus : api.testLoki
    const r = await fn(payload)
    testResults[type] = r.ok
  } catch {
    testResults[type] = false
  } finally {
    testing[type] = false
  }
}

async function copyWebhook() {
  try {
    await navigator.clipboard.writeText(webhookUrl.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    // fallback: select text
  }
}

async function testK8s() {
  testingK8s.value = true
  k8sTestResult.value = null
  k8sTestMsg.value = ''
  try {
    const r = await api.testK8s()
    k8sTestResult.value = r.ok
    k8sTestMsg.value = r.ok
      ? `连接成功，共 ${r.node_count} 个节点：${(r.nodes || []).join(', ')} （kubeconfig: ${r.kubeconfig}）`
      : `连接失败：${r.error}（kubeconfig: ${r.kubeconfig}）`
  } catch (e) {
    k8sTestResult.value = false
    k8sTestMsg.value = '请求失败：' + (typeof e === 'string' ? e : e?.message || '未知错误')
  } finally {
    testingK8s.value = false
  }
}

async function testAI() {
  testingAI.value = true
  aiTestResult.value = null
  aiTestMsg.value = ''
  try {
    const payload = {
      provider: form.ai_provider,
      base_url: form.ai_base_url,
      model: form.ai_model,
      api_key: form.ai_api_key,
    }
    const r = await api.testAI(payload)
    aiTestResult.value = r.ok
    aiTestMsg.value = r.ok
      ? `连接成功（${r.elapsed_ms} ms）模型：${r.model}，回答：${r.reply || '(空)'}`
      : `连接失败（HTTP ${r.status || ''}）：${r.error || '未知错误'}`
  } catch (e) {
    aiTestResult.value = false
    aiTestMsg.value = '请求失败：' + (typeof e === 'string' ? e : e?.message || '未知错误')
  } finally {
    testingAI.value = false
  }
}

async function saveSettings() {
  saving.value = true
  saveNote.value = ''
  try {
    const r = await api.saveSettings({ ...form })
    saveNote.value = r.note || '保存成功'
    applySettings(await api.getSettings())
    loadGrafanaBoards()
  } catch (e) {
    saveNote.value = '保存失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
  gap: 16px;
}

.settings-section { padding: 20px 22px; }

.section-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 18px; padding-bottom: 14px;
  border-bottom: 1px solid var(--border-light);
}
.section-title {
  display: flex; align-items: center; gap: 9px;
  font-size: 14px; font-weight: 600; color: var(--text-primary);
}
.section-icon {
  width: 26px; height: 26px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
}
.section-icon.prom    { background: rgba(232,93,15,0.15); color: #e85d0f; }
.section-icon.loki    { background: rgba(251,191,36,0.15); color: #d97706; }
.section-icon.ai      { background: var(--accent-dim); color: var(--accent); }
.section-icon.feishu  { background: rgba(0,186,113,0.15); color: #00ba71; }
.section-icon.grafana  { background: rgba(248,134,0,0.15); color: #f88600; }
.section-icon.k8s     { background: rgba(50,130,246,0.15); color: #3282f6; font-size:10px; }
.section-icon.ansible { background: rgba(238,0,0,0.12);    color: #e00000; }
.section-icon.cloud   { background: rgba(14,165,233,0.12); color: #0ea5e9; font-size:15px; line-height:1; }

.conn-badge {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; padding: 3px 10px; border-radius: 99px;
  border: 1px solid;
}
.conn-badge.idle { border-color: var(--border); color: var(--text-muted); }
.conn-badge.ok   { border-color: rgba(63,185,80,.3); color: var(--success); background: rgba(63,185,80,.08); }
.conn-badge.err  { border-color: rgba(248,81,73,.3); color: var(--error);   background: rgba(248,81,73,.08); }
.badge-dot { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }

.field-group { display: flex; flex-direction: column; gap: 14px; }
.field-row   { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label {
  font-size: 11px; font-weight: 500; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: .05em;
}
.field input, .field select { width: 100%; }
.input-row { display: flex; gap: 8px; }
.input-row input { flex: 1; }
.field-hint { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.checkbox-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}
.checkbox-line input { width: auto; }

.webhook-url-row {
  display: flex; align-items: center; gap: 8px;
  background: var(--bg-elevated, #1a1d23); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 6px 10px;
}
.webhook-url {
  flex: 1; font-size: 12px; color: var(--text-secondary);
  font-family: 'JetBrains Mono', monospace;
  word-break: break-all; background: none; border: none; padding: 0;
}

/* 飞书安全配置小标题 */
.feishu-security-title {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0 2px;
  border-top: 1px dashed var(--border-light);
}
.security-label {
  font-size: 11px; font-weight: 600; color: var(--text-secondary);
  text-transform: uppercase; letter-spacing: .05em;
}
.security-hint {
  font-size: 11px; color: var(--text-muted);
}

/* 飞书配置引导步骤 */
.feishu-guide {
  display: flex; flex-direction: column; gap: 6px;
  margin-top: 4px; padding: 10px 12px;
  background: rgba(0,186,113,0.04); border: 1px solid rgba(0,186,113,0.15);
  border-radius: var(--radius);
}
.guide-step {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 12px; color: var(--text-secondary); line-height: 1.5;
}
.guide-step code {
  font-size: 11px; padding: 1px 5px;
  background: rgba(0,186,113,0.12); border-radius: 3px;
  color: #00ba71; font-family: 'JetBrains Mono', monospace;
}
.guide-step strong { color: var(--text-primary); }
.step-num {
  flex-shrink: 0;
  width: 18px; height: 18px; border-radius: 50%;
  background: rgba(0,186,113,0.15); color: #00ba71;
  font-size: 10px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  margin-top: 1px;
}

.save-row {
  display: flex; align-items: center; gap: 14px;
  margin-top: 20px; padding-top: 16px;
  border-top: 1px solid var(--border-light);
}
.save-hint { font-size: 12px; color: var(--text-muted); }

.alert-error {
  margin-bottom: 14px; padding: 10px 14px;
  background: rgba(248,81,73,.08); border: 1px solid rgba(248,81,73,.2);
  border-radius: var(--radius); color: var(--error); font-size: 13px;
}
.alert-note {
  display: flex; align-items: center; gap: 7px;
  margin-bottom: 14px; padding: 10px 14px;
  background: rgba(56,139,253,.08); border: 1px solid rgba(56,139,253,.2);
  border-radius: var(--radius); color: var(--accent); font-size: 13px;
}

/* Grafana board management */
.boards-section { margin-top: 14px; }
.boards-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px;
}
.boards-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
.btn-sm {
  padding: 4px 10px; font-size: 11px; border-radius: 5px;
  border: 1px solid var(--border); background: var(--surface-2);
  color: var(--text-secondary); cursor: pointer; transition: all 0.12s;
}
.btn-sm:hover { border-color: var(--accent); color: var(--accent); }
.add-board-form {
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px; margin-bottom: 10px;
  display: flex; flex-direction: column; gap: 8px;
}
.board-input {
  width: 100%; padding: 6px 10px; font-size: 12px;
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-primary); outline: none;
  box-sizing: border-box;
}
.board-input:focus { border-color: var(--accent); }
.add-board-actions { display: flex; gap: 8px; }
.btn-primary-sm {
  padding: 5px 12px; font-size: 12px; border-radius: 5px;
  border: none; background: var(--accent); color: #fff; cursor: pointer;
}
.btn-primary-sm:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-ghost-sm {
  padding: 5px 12px; font-size: 12px; border-radius: 5px;
  border: 1px solid var(--border); background: none;
  color: var(--text-secondary); cursor: pointer;
}
.boards-list { display: flex; flex-direction: column; gap: 4px; }
.board-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--surface-2);
  font-size: 12px;
}
.board-icon { color: #f88600; flex-shrink: 0; }
.board-title { font-weight: 500; color: var(--text-primary); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.board-uid { font-family: var(--font-mono); font-size: 11px; color: var(--text-tertiary); flex-shrink: 0; }
.board-tag {
  padding: 1px 6px; font-size: 10px; border-radius: 3px;
  background: rgba(248,134,0,.12); color: #f88600; flex-shrink: 0;
}
.board-link { color: var(--accent); text-decoration: none; font-size: 13px; flex-shrink: 0; }
.board-link:hover { opacity: 0.75; }
.board-del {
  width: 20px; height: 20px; border-radius: 4px; border: none;
  background: rgba(248,81,73,.1); color: var(--error); cursor: pointer;
  font-size: 14px; line-height: 1; flex-shrink: 0; display: flex;
  align-items: center; justify-content: center;
}
.board-del:hover { background: rgba(248,81,73,.2); }
.boards-empty { font-size: 12px; color: var(--text-tertiary); padding: 8px 0; text-align: center; }

/* Grafana API Key 测试按钮行 */
.input-with-btn {
  display: flex; gap: 8px; align-items: stretch;
}
.input-with-btn input {
  flex: 1; min-width: 0;
}
.grafana-test-result {
  display: flex; align-items: center; gap: 6px;
  margin-top: 7px; padding: 7px 10px; border-radius: 6px;
  font-size: 12px; font-weight: 500;
}
.grafana-test-result.ok  {
  background: rgba(63,185,80,.08); border: 1px solid rgba(63,185,80,.25); color: var(--success);
}
.grafana-test-result.err {
  background: rgba(248,81,73,.08); border: 1px solid rgba(248,81,73,.25); color: var(--error);
}
.conn-test-result {
  margin-top: 6px; padding: 6px 10px; border-radius: 6px;
  font-size: 12px; font-weight: 500; word-break: break-all;
}
.conn-test-result.ok  {
  background: rgba(63,185,80,.08); border: 1px solid rgba(63,185,80,.25); color: var(--success);
}
.conn-test-result.err {
  background: rgba(248,81,73,.08); border: 1px solid rgba(248,81,73,.25); color: var(--error);
}
.test-icon { font-size: 13px; font-weight: 700; }
.test-version { font-weight: 400; color: var(--text-tertiary); }
/* 多云配置 */
.cloud-section { grid-column: 1 / -1; }
.cloud-provider-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  padding: 4px 0; border-top: 1px dashed var(--border-light); margin-top: 2px;
}
.cloud-provider-title:first-of-type { border-top: none; margin-top: 0; }
.provider-dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}
.provider-dot.aliyun  { background: #ff6a00; }
.provider-dot.aws     { background: #f90; }
.provider-dot.tencent { background: #0052d9; }
.provider-dot.huawei  { background: #c7000b; }

code {
  background: var(--surface-2); border: 1px solid var(--border);
  border-radius: 3px; padding: 1px 5px;
  font-family: var(--font-mono); font-size: 11px; color: var(--accent);
}
</style>
