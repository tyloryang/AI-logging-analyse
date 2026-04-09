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
          <div class="field">
            <label>API Key{{ settings.ai_api_key_set ? '（已设置）' : '' }}</label>
            <input v-model="form.ai_api_key" type="password" :placeholder="settings.ai_api_key_set ? '留空不修改' : '输入 API Key'" />
          </div>
          <p class="field-hint">AI 配置修改后需重启服务才能生效</p>
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

    <!-- 保存按钮 -->
    <div class="save-row">
      <button class="btn btn-primary" @click="saveSettings" :disabled="saving">
        <span v-if="saving" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
        {{ saving ? '保存中...' : '保存配置' }}
      </button>
      <span class="save-hint">Prometheus / Loki URL 及飞书机器人配置变更立即生效，其余配置重启后生效</span>
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

const form = reactive({
  prometheus_url:           '',
  prometheus_username:      '',
  prometheus_password:      '',
  loki_url:                 '',
  loki_username:            '',
  loki_password:            '',
  ai_provider:              'anthropic',
  ai_base_url:              '',
  ai_model:                 '',
  ai_api_key:               '',
  feishu_bot_app_id:        '',
  feishu_bot_app_secret:    '',
  feishu_bot_encrypt_key:   '',
  feishu_bot_verify_token:  '',
})

const testing     = reactive({ prometheus: false, loki: false })
const testResults = reactive({ prometheus: null, loki: null })  // null | true | false

const promStatus     = computed(() => testResults.prometheus === null ? 'idle' : testResults.prometheus ? 'ok' : 'err')
const lokiStatus     = computed(() => testResults.loki === null ? 'idle' : testResults.loki ? 'ok' : 'err')
const promStatusText = computed(() => testResults.prometheus === null ? '未测试' : testResults.prometheus ? '连接正常' : '连接失败')
const lokiStatusText = computed(() => testResults.loki === null ? '未测试' : testResults.loki ? '连接正常' : '连接失败')

const webhookUrl = computed(() => {
  const host = window.location.hostname
  return `http://${host}:30800/api/feishu/webhook`
})

onMounted(async () => {
  try {
    const s = await api.getSettings()
    settings.value = s
    form.prometheus_url      = s.prometheus_url      || ''
    form.prometheus_username = s.prometheus_username || ''
    form.loki_url            = s.loki_url            || ''
    form.loki_username       = s.loki_username       || ''
    form.ai_provider         = s.ai_provider         || 'anthropic'
    form.ai_base_url         = s.ai_base_url         || ''
    form.ai_model            = s.ai_model            || ''
    form.feishu_bot_app_id      = s.feishu_bot_app_id      || ''
  } catch (e) {
    loadError.value = '加载配置失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误')
  }
})

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

async function saveSettings() {
  saving.value = true
  saveNote.value = ''
  try {
    const r = await api.saveSettings({ ...form })
    saveNote.value = r.note || '保存成功'
    // Refresh displayed settings
    settings.value = await api.getSettings()
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
.section-icon.prom   { background: rgba(232,93,15,0.15); color: #e85d0f; }
.section-icon.loki   { background: rgba(251,191,36,0.15); color: #d97706; }
.section-icon.ai     { background: var(--accent-dim); color: var(--accent); }
.section-icon.feishu { background: rgba(0,186,113,0.15); color: #00ba71; }

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
</style>
