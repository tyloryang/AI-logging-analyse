<template>
  <div class="kb-page">
    <!-- 头部 -->
    <div class="kb-head">
      <div>
        <h2 class="kb-title">📚 运维知识库</h2>
        <p class="kb-sub">故障案例 · 最佳实践 · 操作手册 · 安全合规 · 性能优化</p>
      </div>
      <button class="btn btn-primary" @click="openCreate">＋ 新增知识</button>
    </div>

    <!-- 工具栏：搜索 + 分类过滤 -->
    <div class="kb-toolbar">
      <div class="kb-search">
        <span class="s-icon">🔍</span>
        <input v-model="search" placeholder="搜索标题 / 内容 / 标签..." @input="onSearchInput" />
        <button v-if="search" class="s-clear" @click="search=''; load()">✕</button>
      </div>
      <div class="kb-cats">
        <button class="cat-chip" :class="{ active: activeCat === '' }" @click="activeCat=''; load()">
          全部 <em>{{ total }}</em>
        </button>
        <button
          v-for="c in categories" :key="c"
          class="cat-chip" :class="{ active: activeCat === c }"
          @click="activeCat = c; load()"
        >
          {{ c }} <em v-if="counts[c]">{{ counts[c] }}</em>
        </button>
      </div>
    </div>

    <!-- 列表 -->
    <div class="kb-body">
      <div v-if="loading" class="kb-empty">加载中...</div>
      <div v-else-if="!items.length" class="kb-empty">
        <span class="e-icon">📭</span>
        <p>暂无知识条目<br><small>点击「新增知识」创建第一条</small></p>
      </div>
      <div v-else class="kb-grid">
        <div v-for="k in items" :key="k.id" class="kb-card" @click="openDetail(k)">
          <div class="kc-head">
            <span class="kc-cat" :class="'cat-' + catIndex(k.category)">{{ k.category }}</span>
            <span class="kc-use" title="使用次数">👁 {{ k.usage_count || 0 }}</span>
          </div>
          <div class="kc-title">{{ k.title }}</div>
          <div class="kc-excerpt">{{ excerpt(k.content) }}</div>
          <div class="kc-tags">
            <span v-for="t in (k.tags || []).slice(0, 4)" :key="t" class="kc-tag">#{{ t }}</span>
          </div>
          <div class="kc-foot">
            <span class="kc-time">{{ fmtDate(k.updated_at) }}</span>
            <div class="kc-actions" @click.stop>
              <button class="ic-btn" @click="openEdit(k)" title="编辑">✎</button>
              <button class="ic-btn danger" @click="remove(k)" title="删除">🗑</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情抽屉 -->
    <transition name="slide">
      <div v-if="detail" class="kb-drawer-mask" @click.self="detail=null">
        <div class="kb-drawer">
          <div class="kd-head">
            <span class="kc-cat" :class="'cat-' + catIndex(detail.category)">{{ detail.category }}</span>
            <button class="kd-close" @click="detail=null">✕</button>
          </div>
          <h3 class="kd-title">{{ detail.title }}</h3>
          <div class="kd-tags">
            <span v-for="t in detail.tags" :key="t" class="kc-tag">#{{ t }}</span>
          </div>
          <div class="kd-section-t">内容</div>
          <pre class="kd-content">{{ detail.content || '（无内容）' }}</pre>
          <div v-if="detail.solutions?.length" class="kd-section-t">解决方案 / 处置步骤</div>
          <ol v-if="detail.solutions?.length" class="kd-solutions">
            <li v-for="(s, i) in detail.solutions" :key="i">{{ s }}</li>
          </ol>
          <div class="kd-meta">
            使用 {{ detail.usage_count || 0 }} 次 · 更新于 {{ fmtDate(detail.updated_at) }}
          </div>
          <div class="kd-foot">
            <button class="btn btn-outline" @click="openEdit(detail)">编辑</button>
            <button class="btn btn-danger" @click="remove(detail)">删除</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 新增/编辑表单 -->
    <transition name="fade">
      <div v-if="showForm" class="kb-modal-mask" @click.self="showForm=false">
        <div class="kb-modal">
          <div class="km-head">
            <span>{{ editingId ? '编辑知识' : '新增知识' }}</span>
            <button class="kd-close" @click="showForm=false">✕</button>
          </div>
          <div class="km-body">
            <label class="km-field">
              <span>标题 <em class="req">*</em></span>
              <input v-model="form.title" placeholder="例如：Pod CrashLoopBackOff 排查手册" />
            </label>
            <label class="km-field">
              <span>分类</span>
              <select v-model="form.category">
                <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
              </select>
            </label>
            <label class="km-field">
              <span>标签（逗号分隔）</span>
              <input v-model="form.tagsStr" placeholder="k8s, pod, crashloop" />
            </label>
            <label class="km-field">
              <span>内容（支持多行）</span>
              <textarea v-model="form.content" rows="8" placeholder="现象、排查步骤、原理..."></textarea>
            </label>
            <label class="km-field">
              <span>解决方案（每行一条）</span>
              <textarea v-model="form.solutionsStr" rows="4" placeholder="调大内存限制&#10;修复启动依赖"></textarea>
            </label>
          </div>
          <div class="km-foot">
            <button class="btn btn-primary" :disabled="saving || !form.title.trim()" @click="save">
              {{ saving ? '保存中...' : '保存' }}
            </button>
            <button class="btn btn-outline" @click="showForm=false">取消</button>
            <span v-if="formMsg" class="km-msg" :class="formOk ? 'ok' : 'err'">{{ formMsg }}</span>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { api } from '../api/index.js'

const items = ref([])
const categories = ref(['故障案例', '最佳实践', '操作手册', '安全合规', '性能优化'])
const counts = ref({})
const total = ref(0)
const loading = ref(false)
const search = ref('')
const activeCat = ref('')
let searchTimer = null

const detail = ref(null)
const showForm = ref(false)
const editingId = ref(null)
const saving = ref(false)
const formMsg = ref('')
const formOk = ref(false)
const form = reactive({ title: '', category: '故障案例', tagsStr: '', content: '', solutionsStr: '' })

async function load() {
  loading.value = true
  try {
    const params = {}
    if (search.value.trim()) params.search = search.value.trim()
    if (activeCat.value) params.category = activeCat.value
    const r = await api.knowledgeList(params)
    items.value = r.data || []
    total.value = r.total ?? items.value.length
    if (r.categories) categories.value = r.categories
  } catch { items.value = [] }
  finally { loading.value = false }
}

async function loadCounts() {
  try {
    const r = await api.knowledgeCategories()
    counts.value = r.counts || {}
    if (r.categories) categories.value = r.categories
  } catch { /* ignore */ }
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 300)
}

async function openDetail(k) {
  detail.value = k
  try {
    const r = await api.knowledgeUse(k.id)
    k.usage_count = r.usage_count ?? (k.usage_count || 0) + 1
  } catch { /* ignore */ }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { title: '', category: '故障案例', tagsStr: '', content: '', solutionsStr: '' })
  formMsg.value = ''
  showForm.value = true
}

function openEdit(k) {
  detail.value = null
  editingId.value = k.id
  Object.assign(form, {
    title: k.title || '',
    category: k.category || '故障案例',
    tagsStr: (k.tags || []).join(', '),
    content: k.content || '',
    solutionsStr: (k.solutions || []).join('\n'),
  })
  formMsg.value = ''
  showForm.value = true
}

async function save() {
  if (!form.title.trim()) return
  saving.value = true; formMsg.value = ''
  const payload = {
    title: form.title.trim(),
    category: form.category,
    tags: form.tagsStr.split(',').map(s => s.trim()).filter(Boolean),
    content: form.content,
    solutions: form.solutionsStr.split('\n').map(s => s.trim()).filter(Boolean),
  }
  try {
    if (editingId.value) await api.knowledgeUpdate(editingId.value, payload)
    else await api.knowledgeCreate(payload)
    formMsg.value = '保存成功'; formOk.value = true
    await Promise.all([load(), loadCounts()])
    setTimeout(() => { showForm.value = false }, 600)
  } catch (e) {
    formMsg.value = '保存失败：' + e; formOk.value = false
  } finally { saving.value = false }
}

async function remove(k) {
  if (!confirm(`确认删除知识「${k.title}」？`)) return
  try {
    await api.knowledgeDelete(k.id)
    detail.value = null
    await Promise.all([load(), loadCounts()])
  } catch (e) { alert('删除失败：' + e) }
}

function excerpt(content) {
  const t = (content || '').replace(/\n+/g, ' ').trim()
  return t.length > 90 ? t.slice(0, 90) + '…' : t
}
function catIndex(cat) { return Math.max(0, categories.value.indexOf(cat)) }
function fmtDate(t) {
  if (!t) return '-'
  const d = new Date(t)
  return isNaN(d) ? '-' : `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

onMounted(() => { load(); loadCounts() })
</script>

<style scoped>
.kb-page { height: 100%; overflow-y: auto; padding: 20px 24px; background: var(--bg-base); }
.kb-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.kb-title { font-size: 20px; font-weight: 600; color: var(--text-primary); }
.kb-sub { font-size: 13px; color: var(--text-muted); margin-top: 4px; }

.kb-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: 18px; }
.kb-search { display: flex; align-items: center; gap: 8px; padding: 7px 12px; background: var(--bg-card);
  border: 1px solid var(--border); border-radius: 8px; min-width: 280px; }
.kb-search input { flex: 1; border: 0; background: transparent; outline: none; color: var(--text-primary); font-size: 13px; }
.s-icon { opacity: .6; } .s-clear { border: 0; background: transparent; color: var(--text-muted); cursor: pointer; }
.kb-cats { display: flex; flex-wrap: wrap; gap: 8px; }
.cat-chip { padding: 6px 12px; font-size: 12px; border: 1px solid var(--border); border-radius: 999px;
  background: var(--bg-card); color: var(--text-secondary); cursor: pointer; transition: all .12s; }
.cat-chip:hover { border-color: var(--accent); }
.cat-chip.active { background: var(--accent, #d97757); color: #fff; border-color: var(--accent); }
.cat-chip em { font-style: normal; opacity: .7; margin-left: 3px; }

.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.kb-card { padding: 16px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
  cursor: pointer; transition: all .15s; display: flex; flex-direction: column; gap: 9px; }
.kb-card:hover { border-color: var(--accent); transform: translateY(-2px); box-shadow: var(--shadow-md); }
.kc-head { display: flex; align-items: center; justify-content: space-between; }
.kc-cat { font-size: 11px; padding: 2px 9px; border-radius: 999px; font-weight: 500; }
.cat-0 { background: rgba(248,113,113,.15); color: #f87171; }
.cat-1 { background: rgba(52,211,153,.15); color: #34d399; }
.cat-2 { background: rgba(56,189,248,.15); color: #38bdf8; }
.cat-3 { background: rgba(167,139,250,.15); color: #a78bfa; }
.cat-4 { background: rgba(251,191,36,.15); color: #fbbf24; }
.kc-use { font-size: 11px; color: var(--text-muted); }
.kc-title { font-size: 15px; font-weight: 600; color: var(--text-primary); line-height: 1.4; }
.kc-excerpt { font-size: 12px; color: var(--text-secondary); line-height: 1.6; min-height: 38px; }
.kc-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.kc-tag { font-size: 11px; color: var(--accent); background: var(--accent-dim, rgba(217,119,87,.1)); padding: 1px 7px; border-radius: 5px; }
.kc-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 2px; }
.kc-time { font-size: 11px; color: var(--text-muted); }
.kc-actions { display: flex; gap: 6px; }
.ic-btn { width: 26px; height: 26px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-hover);
  color: var(--text-secondary); cursor: pointer; font-size: 13px; }
.ic-btn:hover { border-color: var(--accent); color: var(--accent); }
.ic-btn.danger:hover { border-color: var(--error); color: var(--error); }

.kb-empty { text-align: center; padding: 60px 20px; color: var(--text-muted); }
.e-icon { font-size: 40px; display: block; margin-bottom: 12px; }

/* 详情抽屉 */
.kb-drawer-mask { position: fixed; inset: 0; z-index: 1000; background: rgba(0,0,0,.4); display: flex; justify-content: flex-end; }
.kb-drawer { width: 560px; max-width: 92vw; height: 100%; background: var(--bg-card); border-left: 1px solid var(--border);
  padding: 22px 26px; overflow-y: auto; }
.kd-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.kd-close { border: 0; background: transparent; font-size: 18px; color: var(--text-muted); cursor: pointer; }
.kd-title { font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; }
.kd-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 18px; }
.kd-section-t { font-size: 12px; font-weight: 600; color: var(--accent); margin: 16px 0 8px; padding-left: 8px; border-left: 3px solid var(--accent); }
.kd-content { white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.75; color: var(--text-primary);
  background: var(--bg-base); border: 1px solid var(--border); border-radius: 8px; padding: 14px; font-family: inherit; margin: 0; }
.kd-solutions { margin: 0; padding-left: 22px; display: flex; flex-direction: column; gap: 8px; }
.kd-solutions li { font-size: 13px; color: var(--text-primary); line-height: 1.6; }
.kd-meta { font-size: 12px; color: var(--text-muted); margin: 20px 0 14px; }
.kd-foot { display: flex; gap: 10px; }

/* 表单弹窗 */
.kb-modal-mask { position: fixed; inset: 0; z-index: 1001; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; }
.kb-modal { width: 600px; max-width: 94vw; max-height: 90vh; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 14px; display: flex; flex-direction: column; overflow: hidden; }
.km-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--border);
  font-size: 15px; font-weight: 600; color: var(--text-primary); }
.km-body { padding: 18px 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; }
.km-field { display: flex; flex-direction: column; gap: 6px; }
.km-field > span { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
.req { color: var(--error); }
.km-field input, .km-field select, .km-field textarea {
  border: 1px solid var(--border); border-radius: 8px; background: var(--bg-base); color: var(--text-primary);
  padding: 8px 11px; font-size: 13px; font-family: inherit; outline: none; }
.km-field textarea { resize: vertical; line-height: 1.6; }
.km-field input:focus, .km-field select:focus, .km-field textarea:focus { border-color: var(--accent); }
.km-foot { display: flex; align-items: center; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--border); }
.km-msg { font-size: 12px; } .km-msg.ok { color: var(--success, #22c55e); } .km-msg.err { color: var(--error); }

.slide-enter-active, .slide-leave-active { transition: opacity .25s; }
.slide-enter-from, .slide-leave-to { opacity: 0; }
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
