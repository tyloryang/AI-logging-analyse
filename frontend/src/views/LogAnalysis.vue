<template>
  <div class="log-layout">
    <!-- 左侧标签过滤 -->
    <aside class="service-panel">
      <div class="panel-header">
        <span class="panel-title">日志标签筛选</span>
        <!-- 时间模式切换 -->
        <div class="time-mode-tabs">
          <button class="tmode-btn" :class="{ active: timeMode === 'relative' }" @click="timeMode = 'relative'; onTimeModeChange()">快速</button>
          <button class="tmode-btn" :class="{ active: timeMode === 'custom' }" @click="timeMode = 'custom'; onTimeModeChange()">自定义</button>
        </div>
        <!-- 相对时间选择 -->
        <select v-if="timeMode === 'relative'" v-model="hours" class="time-select" @change="onParamChange">
          <option value="0.016667">最近 1 分钟</option>
          <option value="0.083333">最近 5 分钟</option>
          <option value="0.25">最近 15 分钟</option>
          <option value="0.5">最近 30 分钟</option>
          <option value="1">最近 1 小时</option>
          <option value="6">最近 6 小时</option>
          <option value="24">最近 24 小时</option>
          <option value="72">最近 3 天</option>
        </select>
        <!-- 自定义时间范围 -->
        <div v-else class="custom-time-wrap">
          <!-- 时间戳快速粘贴：支持 2026-07-09 10:31:12 / ISO / 纳秒(19位)/毫秒/秒 时间戳，也支持 "起 ~ 止" 区间 -->
          <div class="ts-paste-row">
            <input
              type="text"
              v-model="tsPasteInput"
              class="dt-input ts-paste"
              placeholder="粘贴时间或时间段，如 2026-07-10 00:00:00 ~ 2026-07-10 14:30:00"
              @paste="onTsPaste"
              @keyup.enter="applyTsPaste()"
              title="支持单个时间、时间戳或起止时间段；粘贴后自动生效并查询" />
            <button type="button" class="ts-apply-btn" @click="applyTsPaste()" title="解析并应用">应用</button>
            <button type="button" class="ts-apply-btn" @click="copyCustomTimeRange" title="复制当前起止时间">
              {{ customTimeRangeCopied ? '已复制' : '复制' }}
            </button>
          </div>
          <div v-if="tsPasteError" class="ts-paste-err">{{ tsPasteError }}</div>
          <div v-if="tsCenterText" class="ts-range-chips">
            <span class="ts-range-label">围绕 {{ tsCenterText }} ±</span>
            <button v-for="m in TS_RANGE_PRESETS" :key="m.v"
                    class="ts-range-chip" :class="{ active: tsRangeMinutes === m.v }"
                    @click="applyCenterRange(m.v)">{{ m.label }}</button>
          </div>
          <div class="custom-time-inputs">
            <input
              type="text"
              v-model="customStart"
              class="dt-input custom-time-text"
              placeholder="开始时间 YYYY-MM-DD HH:mm:ss"
              aria-label="开始时间"
              autocomplete="off"
              @blur="onCustomTimeFieldCommit"
              @keyup.enter="onCustomTimeFieldCommit"
              @paste="onCustomTimeFieldPaste('start', $event)"
              title="可直接粘贴完整开始时间，如 2026-07-10 23:29:48" />
            <span class="dt-sep">→</span>
            <input
              type="text"
              v-model="customEnd"
              class="dt-input custom-time-text"
              placeholder="结束时间 YYYY-MM-DD HH:mm:ss"
              aria-label="结束时间"
              autocomplete="off"
              @blur="onCustomTimeFieldCommit"
              @keyup.enter="onCustomTimeFieldCommit"
              @paste="onCustomTimeFieldPaste('end', $event)"
              title="可直接粘贴完整结束时间，如 2026-07-10 23:39:48" />
          </div>
          <div v-if="customTimeError" class="ts-paste-err">{{ customTimeError }}</div>
        </div>
      </div>

      <div class="label-explorer">
        <div class="label-explorer-header" @click="labelExplorerOpen = !labelExplorerOpen">
          <span class="label-explorer-title">Loki 标签</span>
          <span class="label-explorer-actions">
            <button
              type="button"
              class="label-default-settings-btn"
              :class="{ active: defaultLabelSettingsOpen }"
              @click.stop="defaultLabelSettingsOpen = !defaultLabelSettingsOpen; labelExplorerOpen = true"
            >默认展示</button>
            <span class="label-explorer-toggle">{{ labelExplorerOpen ? '收起' : '展开' }}</span>
          </span>
        </div>
        <div v-show="labelExplorerOpen" class="label-explorer-body">
          <div v-if="loadingLabelCatalog" class="loading-row label-loading">
            <div class="spinner" style="width:14px;height:14px;border-width:2px"></div>
          </div>
          <template v-else>
            <div v-if="defaultLabelSettingsOpen" class="label-default-settings">
              <div class="label-default-settings-head">
                <span>勾选默认展示标签，第一项将在进入页面时自动选中</span>
                <button type="button" @click="restoreRecommendedDefaultLabels">恢复推荐</button>
              </div>
              <div class="label-default-options">
                <label v-for="item in labelCatalog" :key="item.name" class="label-default-option">
                  <input
                    type="checkbox"
                    :checked="defaultLabelNames.includes(item.name)"
                    @change="toggleDefaultLabelPreference(item.name)"
                  />
                  <span>{{ item.name }}</span>
                  <em>{{ labelRoleText(item) }}</em>
                </label>
              </div>
              <button type="button" class="label-default-done" @click="defaultLabelSettingsOpen = false">完成</button>
            </div>
            <div v-if="defaultLabelItems.length" class="label-default-strip">
              <span class="label-default-strip-title">默认标签</span>
              <button
                v-for="item in defaultLabelItems"
                :key="item.name"
                type="button"
                class="label-default-chip"
                :class="{ active: selectedLabelName === item.name }"
                @click="pickLabelName(item.name)"
              >{{ item.name }}</button>
            </div>
            <!-- 已加标签条件（chip 列表，AND 组合） -->
            <div v-if="activeLabelFilters.length" class="active-label-chips" title="所有条件 AND 组合，点 ✕ 单条移除">
              <span
                v-for="(item, idx) in activeLabelFilters"
                :key="item.label + '=' + item.value"
                class="active-label-chip"
              >
                <span class="chip-key">{{ item.label }}</span>
                <span class="chip-eq">=</span>
                <span class="chip-val">{{ item.value }}</span>
                <span class="chip-remove" @click="removeActiveLabel(idx)" title="移除">✕</span>
              </span>
              <button class="active-label-clear" @click="clearAllActiveLabels">清空</button>
            </div>
            <div v-if="labelCatalog.length" class="label-dropdown-panel">
              <!-- 标签名（可搜索 combobox） -->
              <div class="label-select-field">
                <span>标签名 <em class="hint-inline">可键入 label=v1,v2 回车秒加</em></span>
                <div class="combo" :class="{ open: showLabelNameDropdown }">
                  <input
                    ref="labelNameInputRef"
                    class="combo-input"
                    v-model="labelNameQuery"
                    :placeholder="selectedLabelName ? '' : '如 app / namespace，或 namespace=aiops,prod'"
                    @focus="showLabelNameDropdown = true"
                    @input="showLabelNameDropdown = true"
                    @keydown.esc="showLabelNameDropdown = false"
                    @keyup.enter="onLabelNameEnter"
                    @blur="hideLabelNameLater"
                  />
                  <span
                    v-if="selectedLabelName || labelNameQuery"
                    class="combo-clear"
                    @mousedown.prevent="clearLabelName"
                    title="清空"
                  >✕</span>
                  <span class="combo-caret" @mousedown.prevent="showLabelNameDropdown = !showLabelNameDropdown">▾</span>
                  <div v-show="showLabelNameDropdown && filteredLabels.length" class="combo-dropdown">
                    <div
                      v-for="item in filteredLabels"
                      :key="item.name"
                      class="combo-item"
                      :class="{ active: item.name === selectedLabelName }"
                      @mousedown.prevent="pickLabelName(item.name)"
                    >
                      <span class="combo-item-text">
                        <mark v-for="(seg, i) in highlight(item.name, labelNameQuery)" :key="i" :class="{ hl: seg.hit }">{{ seg.t }}</mark>
                      </span>
                      <span class="combo-item-meta">{{ labelRoleText(item) }}</span>
                    </div>
                  </div>
                  <div v-show="showLabelNameDropdown && !filteredLabels.length" class="combo-empty">未匹配到标签名</div>
                </div>
              </div>

              <!-- 标签值（点即加，无需二次确认） -->
              <div class="label-select-field">
                <span>标签值 <em class="hint-inline">点即加芯片；逗号分隔可批量</em></span>
                <div class="combo" :class="{ open: showLabelValueDropdown, disabled: !selectedLabelName || loadingLabelValueMap[selectedLabelName] }">
                  <input
                    ref="labelValueInputRef"
                    class="combo-input"
                    v-model="labelValueQuery"
                    :placeholder="loadingLabelValueMap[selectedLabelName] ? '加载中...' : '选值或输入 aiops,kube-system 回车批量加'"
                    :disabled="!selectedLabelName || loadingLabelValueMap[selectedLabelName]"
                    @focus="showLabelValueDropdown = true"
                    @input="showLabelValueDropdown = true"
                    @keydown.esc="showLabelValueDropdown = false"
                    @keyup.enter="onLabelValueEnter"
                    @blur="hideLabelValueLater"
                  />
                  <span
                    v-if="selectedLabelValue || labelValueQuery"
                    class="combo-clear"
                    @mousedown.prevent="clearLabelValue"
                    title="清空"
                  >✕</span>
                  <span class="combo-caret" @mousedown.prevent="showLabelValueDropdown = !showLabelValueDropdown">▾</span>
                  <div v-show="showLabelValueDropdown && filteredLabelValues.length" class="combo-dropdown">
                    <div class="combo-multi-hint quick-hint">
                      <span>💡 点击立即添加芯片，下拉不关</span>
                    </div>
                    <div
                      v-for="value in filteredLabelValues"
                      :key="value"
                      class="combo-item"
                      :class="{ chipped: hasChip(selectedLabelName, value) }"
                      :title="hasChip(selectedLabelName, value) ? '已加入过滤，点击可移除' : '点击加入过滤条件'"
                      @mousedown.prevent="quickAddLabelValue(value)"
                    >
                      <span class="combo-item-text">
                        <mark v-for="(seg, i) in highlight(value, labelValueQuery)" :key="i" :class="{ hl: seg.hit }">{{ seg.t }}</mark>
                      </span>
                      <span class="combo-item-meta" v-if="hasChip(selectedLabelName, value)">✓ 已加</span>
                    </div>
                  </div>
                  <div v-show="showLabelValueDropdown && !filteredLabelValues.length && !loadingLabelValueMap[selectedLabelName]" class="combo-empty">
                    {{ selectedLabelValues.length ? '未匹配到值' : '当前标签暂无样例值' }}
                  </div>
                </div>
              </div>

              <div v-if="selectedLabelName && !activeLabelFilters.length" class="label-flow-tip">
                💡 直接点值即可，多选就连续点
              </div>
            </div>
            <div v-else class="label-empty">未发现 Loki 标签</div>
          </template>
        </div>
      </div>

    </aside>

    <!-- 右侧内容区 -->
    <div class="log-panel">
      <!-- 工具栏 -->
      <div class="log-toolbar">
        <div class="toolbar-left">
          <!-- Tab 切换 -->
          <div class="tab-group">
            <button class="tab-btn" :class="{ active: activeTab === 'logs' }" @click="switchTab('logs')">
              📋 日志流
              <span class="tab-count">{{ logs.length }}</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'templates' }" @click="switchTab('templates')">
              🧩 模板聚合
              <span class="tab-count" v-if="templates.length">{{ templates.length }}</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'trace' }" @click="switchTab('trace')">
              ⏱ 耗时追踪
            </button>
          </div>
        </div>
        <div class="toolbar-right">
          <!-- 关键字搜索（日志流 / 模板聚合 tab 共用） -->
          <div v-if="activeTab !== 'trace'" class="keyword-wrap" title="服务端关键字（重新查询 Loki）">
            <span class="kw-icon">🔍</span>
            <input
              v-model="keyword"
              class="kw-input"
              placeholder="后端关键字（查询 Loki）..."
              @input="onKeywordInput"
              @keyup.enter="onParamChange"
            />
            <button v-if="keyword" class="kw-clear" @click="clearKeyword">✕</button>
          </div>
          <!-- 多服务选择（可跨服务同时查，等价 Loki app=~"a|b|c"） -->
          <div v-if="activeTab !== 'trace'" class="multi-filter-wrap svc-multi" title="多服务筛选：输入服务名回车加入，可选多个跨服务查看总体调用">
            <span class="kw-icon">≡</span>
            <span
              v-for="(svc, i) in selectedServices"
              :key="'svc-'+i"
              class="filter-chip include svc-chip"
              title="点击删除"
            >
              <span class="chip-prefix">◈</span>
              <span class="chip-text">{{ svc }}</span>
              <span class="chip-remove" @click.stop="removeServiceChip(i)" title="删除服务">✕</span>
            </span>
            <input
              v-model="serviceChipInput"
              list="svc-datalist"
              class="kw-input multi-input"
              :placeholder="selectedServices.length ? '再加服务...' : '服务名 (回车加入；可选多个)'"
              @keyup.enter="addServiceChip"
              @keydown.backspace="onServiceChipBackspace"
            />
            <datalist id="svc-datalist">
              <option v-for="s in allServicesList" :key="s" :value="s" />
            </datalist>
            <button v-if="selectedServices.length" class="kw-clear" @click="selectedServices = []; selectedService = ''; onParamChange()" title="清空全部服务">✕</button>
          </div>

          <!-- 多条件关键字过滤（服务端 Loki 查询：AND/OR 可切；- 前缀=排除） -->
          <div v-if="activeTab === 'logs'" class="multi-filter-wrap" title="多关键字：回车加入；- 前缀=排除；点 chip 切包含/排除；同时推到 Loki 服务端查询">
            <span class="kw-icon">⊕</span>
            <!-- AND / OR 切换 -->
            <div class="kw-mode-switch" title="AND=同时命中所有关键字；OR=命中任一即可">
              <button
                class="kw-mode-btn"
                :class="{ active: keywordMode === 'and' }"
                @click="keywordMode = 'and'; onParamChange()"
              >AND</button>
              <button
                class="kw-mode-btn"
                :class="{ active: keywordMode === 'or' }"
                @click="keywordMode = 'or'; onParamChange()"
              >OR</button>
            </div>
            <span
              v-for="(chip, i) in localKeywords"
              :key="i"
              class="filter-chip"
              :class="chip.exclude ? 'exclude' : 'include'"
              @click="toggleChipExclude(i); onParamChange()"
              :title="chip.exclude ? '排除（点击切回包含）' : '包含（点击切为排除）'"
            >
              <span class="chip-prefix">{{ chip.exclude ? '−' : '+' }}</span>
              <span class="chip-text">{{ chip.text }}</span>
              <span class="chip-remove" @click.stop="removeChip(i); onParamChange()" title="删除条件">✕</span>
            </span>
            <input
              v-model="localKeywordInput"
              class="kw-input multi-input"
              :placeholder="localKeywords.length ? '继续加条件...' : '关键字 (回车加入；- 前缀=排除)'"
              @keyup.enter="addChipFromInput"
              @keydown.backspace="onMultiInputBackspace"
            />
            <button v-if="localKeywords.length" class="kw-clear" @click="localKeywords = []; onParamChange()" title="清空全部条件">✕</button>
          </div>

          <!-- 日志流专有控件 -->
          <template v-if="activeTab === 'logs'">
            <select v-model="levelFilter" class="time-select" @change="onLevelChange">
              <option value="">全部级别</option>
              <option value="error">ERROR</option>
              <option value="warn">WARN</option>
              <option value="info">INFO</option>
              <option value="debug">DEBUG</option>
            </select>
            <button
              class="btn"
              :class="incidentOnly ? 'btn-incident-active' : 'btn-outline'"
              @click="toggleIncident"
              title="仅显示 ERROR/WARN 及含 error/exception/timeout 等关键字的日志"
            >⚡ 仅事件</button>
            <button class="btn btn-outline" @click="loadLogs" :disabled="loadingLogs">
              <span v-if="loadingLogs" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🔄</span>查询
            </button>
            <button class="btn btn-primary" @click="startAIAnalysis" :disabled="analyzingAI">
              <span v-if="analyzingAI" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🤖</span>AI 分析
            </button>
          </template>
          <!-- 模板聚合专有控件 -->
          <template v-if="activeTab === 'templates'">
            <span class="meta-info" v-if="templateMeta.total_logs">
              采样 {{ templateMeta.total_logs }} 条 → {{ templates.length }} 个模板
            </span>
            <select v-model="tplLevelFilter" class="time-select" @change="loadTemplates">
              <option value="">全量日志</option>
              <option value="error">仅 ERROR</option>
              <option value="warn">仅 WARN</option>
            </select>
            <button class="btn btn-outline" @click="loadTemplates" :disabled="loadingTemplates">
              <span v-if="loadingTemplates" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🔄</span>重新聚类
            </button>
            <button class="btn btn-primary" @click="startTplAIAnalysis" :disabled="analyzingTplAI || loadingTemplates || !templates.length">
              <span v-if="analyzingTplAI" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🤖</span>AI 分析
            </button>
          </template>
        </div>
      </div>

      <!-- AI 分析面板（日志流 tab） -->
      <transition name="fade">
        <div v-if="(aiContent || analyzingAI) && activeTab === 'logs'" class="ai-panel">
          <div class="ai-panel-header">
            <span>🤖 AI 分析结果</span>
            <button class="btn btn-outline btn-xs" @click="aiContent = ''">关闭</button>
          </div>
          <div class="ai-content" v-html="renderedAI"></div>
          <div v-if="analyzingAI" class="ai-typing">
            <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
          </div>
        </div>
      </transition>
      <!-- AI 分析面板（模板聚合 tab） -->
      <transition name="fade">
        <div v-if="(tplAiContent || analyzingTplAI) && activeTab === 'templates'" class="ai-panel">
          <div class="ai-panel-header">
            <span>🤖 模板聚类 AI 分析</span>
            <button class="btn btn-outline btn-xs" @click="tplAiContent = ''">关闭</button>
          </div>
          <div class="ai-content" v-html="renderedTplAI"></div>
          <div v-if="analyzingTplAI" class="ai-typing">
            <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
          </div>
        </div>
      </transition>

      <!-- ── 日志流 ── -->
      <div v-show="activeTab === 'logs'" class="log-container">
        <div v-if="loadingLogs && !filteredLogs.length" class="empty-state">
          <div class="spinner"></div><p>加载日志中...</p>
        </div>
        <div v-else-if="!filteredLogs.length" class="empty-state">
          <span class="icon">📭</span><p>暂无日志数据</p>
        </div>
        <template v-else>
          <div class="log-coverage-panel">
            <span v-if="loadingLogDistribution" class="coverage-loading">
              <span class="spinner" style="width:12px;height:12px;border-width:2px"></span>
              正在统计完整匹配量与 Pod 覆盖...
            </span>
            <template v-else-if="logCoverageSummary">
              <div class="coverage-summary">
                <strong>{{ logCoverageSummary.text }}</strong>
                <span v-if="logCoverageSummary.truncated" class="coverage-warning">
                  当前表格只是部分结果，请继续加载或点击 Pod 精确查询
                </span>
              </div>
              <div v-if="logDistribution.pods?.length" class="coverage-pods">
                <button
                  v-for="item in logDistribution.pods"
                  :key="`${item.namespace}/${item.pod}`"
                  type="button"
                  class="coverage-pod-chip"
                  :title="`只查询 ${item.namespace ? item.namespace + '/' : ''}${item.pod}`"
                  @click="drillIntoPod(item)"
                >
                  {{ item.namespace ? item.namespace + '/' : '' }}{{ item.pod }}
                  <strong>{{ item.count.toLocaleString() }}</strong>
                </button>
                <span v-if="logDistribution.total_pods > logDistribution.pods.length" class="coverage-more-pods">
                  仅展示日志量前 {{ logDistribution.pods.length }} 个 Pod
                </span>
              </div>
            </template>
            <span v-else-if="logDistributionError" class="coverage-error">
              完整数量统计失败：{{ logDistributionError }}；日志分页仍可正常使用
            </span>
          </div>
          <!-- 统计栏 -->
          <div class="log-stats-bar">
            <span class="log-stat-item">
              当前显示 <strong>{{ filteredLogs.length }}</strong> 条
              <span v-if="filteredLogs.length !== logs.length" class="log-stat-filtered">（过滤后）</span>
            </span>
            <span class="log-stat-sep">·</span>
            <span v-for="(cnt, lvl) in levelStats" :key="lvl" class="log-stat-item">
              <span class="lvl-dot" :class="'lvl-' + lvl"></span>{{ lvl.toUpperCase() }} {{ cnt }}
            </span>
          </div>
          <!-- 表格 -->
          <div ref="logScrollWrap" class="log-table-wrap" @scroll.passive="onLogScroll">
            <table class="log-table">
              <colgroup>
              <col style="width:168px">
              <col style="width:72px">
              <col style="width:130px">
              <col style="width:120px">
              <col>
              </colgroup>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>级别</th>
                  <th>服务</th>
                  <th>分组</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(log, i) in filteredLogs" :key="i"
                  class="log-row" :class="[logRowClass(log.line), { selected: isSelectedLog(log) }]"
                  @click="openDetail(log)"
                >
                  <td class="col-ts">{{ log.timestamp }}</td>
                  <td class="col-lvl">
                    <span class="lvl-badge" :class="'lvl-badge-' + extractLevel(log.line)">
                      {{ extractLevel(log.line).toUpperCase() }}
                    </span>
                  </td>
                  <td class="col-svc">{{ logServiceName(log) }}</td>
                  <td class="col-group">{{ logGroup(log) }}</td>
                  <td class="col-msg"><span class="log-msg-text"><template v-for="(seg, si) in highlightLogSegments(log.line)" :key="si"><mark v-if="seg.hit" class="log-kw-hit">{{ seg.text }}</mark><template v-else>{{ seg.text }}</template></template></span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- 加载更多 -->
          <div class="load-more-bar" :class="{ ready: hasMore && !loadingMore }">
            <span v-if="loadingMore" class="load-more-status">
              <span class="spinner" style="width:13px;height:13px;border-width:2px"></span>
              正在继续加载日志...
            </span>
            <span v-else-if="hasMore" class="load-more-status">
              已加载 {{ totalLoaded }} 条，向下滚动或
              <button type="button" class="load-more-btn" @click="loadMore">继续加载</button>
            </span>
            <span v-else class="load-more-status">
              当前查询已加载 {{ totalLoaded }} 条
            </span>
          </div>
        </template>
      </div>

      <!-- 日志详情模态框（居中弹出，包含原始记录 + 上下文滚动）-->
      <transition name="modal-fade">
        <div
          v-if="showDetailModal && detailLog"
          ref="detailModalMask"
          class="log-detail-modal-mask"
          @click.self="closeDetail"
          @keydown.esc.stop.prevent="closeDetail"
          tabindex="-1"
        >
          <div class="drawer-panel log-detail-modal" @click.stop>
            <div class="drawer-header">
              <span>日志详情 · 上下文</span>
              <button type="button" class="drawer-close" aria-label="关闭日志上下文" @click.stop="closeDetail">✕</button>
            </div>
            <div class="drawer-body">
              <!-- 元数据折叠区（默认收起，header 显示关键摘要，留更多空间给上下文） -->
              <div class="drawer-meta-section" :class="{ open: metaOpen }">
                <div class="drawer-meta-header" @click="metaOpen = !metaOpen">
                  <span class="meta-toggle">{{ metaOpen ? '▼' : '▶' }}</span>
                  <span class="meta-title">元数据</span>
                  <span class="meta-summary">
                    <span class="meta-summary-ts">{{ detailLog.timestamp }}</span>
                    <span class="lvl-badge mini" :class="'lvl-badge-' + extractLevel(detailLog.line)">
                      {{ extractLevel(detailLog.line).toUpperCase() }}
                    </span>
                    <span class="meta-summary-svc">{{ logServiceName(detailLog) }}</span>
                    <span class="meta-summary-ns">{{ logGroup(detailLog) }}</span>
                  </span>
                </div>
                <div v-if="metaOpen" class="drawer-meta-body">
                  <div class="drawer-row">
                    <span class="drawer-label">时间</span>
                    <span class="drawer-val">{{ detailLog.timestamp }}</span>
                  </div>
                  <div class="drawer-row">
                    <span class="drawer-label">级别</span>
                    <span class="lvl-badge" :class="'lvl-badge-' + extractLevel(detailLog.line)">
                      {{ extractLevel(detailLog.line).toUpperCase() }}
                    </span>
                  </div>
                  <div class="drawer-row">
                    <span class="drawer-label">服务</span>
                    <span class="drawer-val">{{ logServiceName(detailLog) }}</span>
                  </div>
                  <div class="drawer-row">
                    <span class="drawer-label">分组</span>
                    <span class="drawer-val">{{ logGroup(detailLog) }}</span>
                  </div>
                  <div v-if="detailLog.labels && Object.keys(detailLog.labels).length" class="drawer-row">
                    <span class="drawer-label">标签</span>
                    <div class="drawer-tags">
                      <template v-for="(v, k) in detailLog.labels" :key="k">
                        <button
                          v-if="isContainerLabel(k)"
                          type="button"
                          class="drawer-tag drawer-tag-link"
                          :title="containerLogLinkTitle(detailLog.labels)"
                          @click.stop="goToContainerLogs(detailLog.labels, v)"
                        >
                          {{ k }}=<em>{{ v }}</em><span class="drawer-tag-jump">↗</span>
                        </button>
                        <span v-else class="drawer-tag">{{ k }}=<em>{{ v }}</em></span>
                      </template>
                    </div>
                  </div>
                  <div class="drawer-row drawer-row-full">
                    <span class="drawer-label">内容</span>
                    <pre class="drawer-content">{{ displayLogLine(detailLog.line) }}</pre>
                  </div>
                </div>
              </div>
              <div class="drawer-row drawer-row-full">
                <div class="drawer-section-header">
                  <span class="drawer-section-title">
                    上下文
                    <span
                      v-if="loadingDetailContext"
                      class="spinner mini-inline"
                      title="后台加载前后上下文中..."
                    ></span>
                  </span>
                  <div class="drawer-section-actions">
                    <span v-if="detailContextBeforeCount || detailContextAfterCount" class="drawer-section-meta">
                      前 {{ detailContextBeforeCount }} / 后 {{ detailContextAfterCount }}
                    </span>
                    <button class="btn btn-outline btn-xs" @click="loadLogContext(detailLog, { reset: true })">刷新</button>
                  </div>
                </div>
                <div v-if="!detailContextError" class="drawer-context-search">
                  <div class="context-search-main-row">
                    <div
                      class="context-search-box"
                      :class="{ active: contextSearchTerms.length }"
                      title="可添加多个搜索条件；AND 条件需同时命中，OR 条件命中任一分组即可"
                    >
                      <span class="context-search-icon">⌕</span>
                      <template v-for="(kw, i) in contextSearchKeywords" :key="kw.id">
                        <button
                          v-if="i > 0"
                          type="button"
                          class="context-condition-join"
                          :class="kw.join"
                          :title="`点击切换为 ${kw.join === 'and' ? 'OR' : 'AND'}`"
                          @click.stop="toggleContextSearchJoin(i)"
                        >{{ kw.join.toUpperCase() }}</button>
                        <span class="filter-chip include context-search-chip">
                          <span class="chip-text">{{ kw.text }}</span>
                          <span class="chip-remove" @click.stop="removeContextSearchKeyword(i)" title="删除条件">✕</span>
                        </span>
                      </template>
                      <button
                        v-if="contextSearchKeywords.length"
                        type="button"
                        class="context-condition-join"
                        :class="contextSearchDraftJoin"
                        :title="`新条件使用 ${contextSearchDraftJoin.toUpperCase()} 连接，点击切换`"
                        @click.stop="toggleContextSearchDraftJoin"
                      >{{ contextSearchDraftJoin.toUpperCase() }}</button>
                      <input
                        v-model="contextSearchInput"
                        class="context-search-input"
                        :placeholder="contextSearchKeywords.length ? '输入下一个条件' : '输入搜索条件'"
                        @keydown="onContextSearchInputKeydown"
                      />
                      <button
                        type="button"
                        class="context-add-condition"
                        :disabled="!contextSearchInput.trim()"
                        title="添加搜索条件（也可按 Enter）"
                        @click.stop="addContextSearchKeywords"
                      >＋ 条件</button>
                      <button
                        v-if="contextSearchTerms.length || contextSearchInput"
                        type="button"
                        class="kw-clear"
                        @click="clearContextSearch"
                        title="清空搜索"
                      >✕</button>
                    </div>
                    <button
                      v-if="detailServiceDrilldown(detailLog.labels)"
                      type="button"
                      class="btn btn-outline btn-xs context-service-jump"
                      :title="serviceLogLinkTitle(detailLog.labels)"
                      @click.stop="goToMicroserviceLogs(detailLog.labels)"
                    >
                      跳转微服务日志 ↗
                    </button>
                  </div>
                  <div v-if="contextSearchTerms.length" class="context-search-actions">
                    <span class="context-search-count">
                      {{ contextSearchMatchCount ? `${activeContextSearchMatch + 1}/${contextSearchMatchCount}` : '0/0' }}
                    </span>
                    <button class="btn btn-outline btn-xs context-search-nav" :disabled="!contextSearchMatchCount" @click="jumpContextSearch(-1)">↑</button>
                    <button class="btn btn-outline btn-xs context-search-nav" :disabled="!contextSearchMatchCount" @click="jumpContextSearch(1)">↓</button>
                  </div>
                </div>
                <div v-if="detailContextError" class="drawer-context-state drawer-context-state-error">
                  {{ detailContextError }}
                </div>
                <div
                  v-else-if="detailContextLogs.length"
                  ref="contextScrollWrap"
                  class="drawer-context-list"
                  @scroll.passive="onContextScroll"
                >
                  <div v-if="loadingContextBefore" class="drawer-context-loading-more">
                    <span class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                    正在加载更早的上下文...
                  </div>
                  <div v-else-if="contextBeforeAtLimit" class="drawer-context-hint">已到达可用上下文上限</div>
                  <div
                    v-for="(item, idx) in detailContextLogs"
                    :key="`${item.timestamp_ns}-${idx}`"
                    :data-context-index="idx"
                    class="drawer-context-item"
                    :class="[
                      { active: idx === detailContextAnchorIndex },
                      { 'context-match': isContextSearchMatch(idx) },
                      { 'context-match-current': isCurrentContextSearchMatch(idx) },
                      logClass(item.line),
                    ]"
                  >
                    <span v-if="idx === detailContextAnchorIndex" class="anchor-marker" title="当前查询的记录">▶</span>
                    <span class="drawer-context-ts">{{ item.timestamp }}</span>
                    <span class="drawer-context-svc">{{ logServiceName(item) }}</span>
                    <span class="drawer-context-text">
                      <template v-for="(seg, segIdx) in contextHighlightedSegments(item.line)" :key="segIdx">
                        <mark v-if="seg.hit" class="context-keyword-hit">{{ seg.text }}</mark>
                        <span v-else>{{ seg.text }}</span>
                      </template>
                    </span>
                    <button
                      type="button"
                      class="context-copy-btn"
                      :class="{ copied: copiedContextLineKey === contextLineCopyKey(item, idx) }"
                      :title="copiedContextLineKey === contextLineCopyKey(item, idx) ? '已复制本行' : '复制本行'"
                      @click.stop="copyContextLine(item, idx)"
                    >
                      {{ copiedContextLineKey === contextLineCopyKey(item, idx) ? '已复制' : '复制' }}
                    </button>
                  </div>
                  <div v-if="loadingContextAfter" class="drawer-context-loading-more">
                    <span class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                    正在加载更晚的上下文...
                  </div>
                  <div v-else-if="contextAfterAtLimit" class="drawer-context-hint">已到达可用上下文上限</div>
                  <div v-if="!detailContextAnchorFound" class="drawer-context-hint">
                    未精确定位当前行，已展示同一日志流的邻近上下文。
                  </div>
                  <div class="drawer-context-hint">滚动到顶/底自动加载更多上下文。</div>
                </div>
                <div v-else class="drawer-context-state">未找到可展示的上下文日志。</div>
              </div>
            </div>
          </div>
        </div>
      </transition>

      <!-- ── 模板聚合 ── -->
      <div v-show="activeTab === 'templates'" class="template-container">
        <div v-if="loadingTemplates" class="empty-state">
          <div class="spinner"></div><p>Drain3 聚类中...</p>
        </div>
        <div v-else-if="tplError" class="empty-state">
          <span class="icon">⚠️</span>
          <p style="color:var(--error)">{{ tplError }}</p>
        </div>
        <div v-else-if="!templates.length" class="empty-state">
          <span class="icon">🧩</span>
          <p>当前条件下暂无日志可聚类<br><small style="color:var(--text-muted)">尝试切换「全量日志」或扩大时间范围</small></p>
        </div>
        <div v-else class="template-list">
          <div v-for="(tpl, i) in templates" :key="tpl.cluster_id" class="tpl-card">
            <!-- 头部：排名 + 计数 + 模板 -->
            <div class="tpl-header">
              <span class="tpl-rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
              <span class="tpl-count badge badge-error">{{ tpl.count }} 条</span>
              <span class="tpl-pct">{{ tplPct(tpl.count) }}%</span>
              <div class="tpl-bar-wrap">
                <div class="tpl-bar" :style="{ width: tplBarW(tpl.count) + '%' }"></div>
              </div>
            </div>
            <!-- 模板字符串 -->
            <div class="tpl-pattern" v-html="highlightWildcard(tpl.template)"></div>
            <!-- 服务分布 -->
            <div class="tpl-services" v-if="tpl.top_services.length">
              <span class="tpl-label">来源：</span>
              <span
                v-for="s in tpl.top_services" :key="s.name"
                class="svc-chip"
              >{{ s.name }}<em>{{ s.count }}</em></span>
            </div>
            <!-- 示例原文（可展开） -->
            <div class="tpl-example" v-if="tpl.example">
              <span class="tpl-label">示例：</span>
              <span class="tpl-example-text">
                <span class="tpl-example-ts">{{ tpl.example_ts }}</span>
                {{ tpl.example }}
              </span>
            </div>
          </div>
        </div>
      </div>
      <!-- ── 耗时追踪 Tab ── -->
      <div v-show="activeTab === 'trace'" class="trace-tab">
        <!-- 查询表单（单行紧凑工具栏） -->
        <div class="trace-form-bar">
          <!-- 追踪值输入 -->
          <div class="trace-input-wrap trace-input-grow">
            <span class="trace-input-icon">🔍</span>
            <input
              v-model="traceValue"
              class="trace-input"
              placeholder="追踪值：traceId、requestId、关键字..."
              @keyup.enter="runTrace"
            />
            <button v-if="traceValue" class="kw-clear" @click="traceValue = ''">✕</button>
          </div>
          <!-- 时间模式 -->
          <div class="time-mode-tabs" style="width:fit-content;flex-shrink:0">
            <button class="tmode-btn" :class="{ active: traceTimeMode === 'relative' }" @click="traceTimeMode = 'relative'">快速</button>
            <button class="tmode-btn" :class="{ active: traceTimeMode === 'custom' }" @click="switchTraceToCustom">自定义</button>
          </div>
          <select v-if="traceTimeMode === 'relative'" v-model="traceHours" class="time-select" style="width:120px;flex-shrink:0">
            <option value="1">最近 1 小时</option>
            <option value="6">最近 6 小时</option>
            <option value="24">最近 24 小时</option>
            <option value="72">最近 3 天</option>
            <option value="168">最近 7 天</option>
          </select>
          <template v-else>
            <input type="datetime-local" v-model="traceStart" class="dt-input" style="width:152px;flex-shrink:0" title="开始时间" />
            <span class="dt-sep" style="flex-shrink:0">→</span>
            <input type="datetime-local" v-model="traceEnd"   class="dt-input" style="width:152px;flex-shrink:0" title="结束时间" />
          </template>
          <!-- 当前服务提示 -->
          <span v-if="selectedService" class="trace-svc-hint" style="flex-shrink:0;font-size:12px;color:var(--text-muted);white-space:nowrap">
            服务: <em style="color:var(--primary)">{{ selectedService }}</em>
          </span>
          <!-- 分析按钮 -->
          <button
            class="btn btn-trace-primary"
            @click="runTrace"
            :disabled="!traceValue || tracingKeyword"
            style="flex-shrink:0"
          >
            <span v-if="tracingKeyword" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>⏱</span>
            开始分析
          </button>
        </div>

        <!-- 结果区 -->
        <div v-if="tracingKeyword" class="empty-state">
          <div class="spinner"></div>
          <p>正在全量扫描日志，计算首末耗时...</p>
          <small style="color:var(--text-muted)">最多扫描 50,000 条匹配日志</small>
        </div>
        <div v-else-if="traceResult" class="trace-result">
          <!-- 未找到 / 请求失败 -->
          <div v-if="!traceResult.found" class="trace-not-found">
            <span class="icon" style="font-size:28px">{{ traceResult._error ? '⚠️' : '🔍' }}</span>
            <p v-if="traceResult._error" style="color:var(--error);font-size:13px">
              请求失败：{{ traceResult._error }}
            </p>
            <p v-else>
              在指定时间范围内未找到包含 <em>{{ traceResult.keyword }}</em> 的日志
            </p>
            <small v-if="!traceResult._error" style="color:var(--text-muted)">
              请检查关键字拼写、时间范围或服务选择是否正确
            </small>
          </div>
          <!-- 找到了：子页签 -->
          <template v-else>
            <!-- 子页签切换栏 -->
            <div class="trace-sub-tabs">
              <button
                class="trace-sub-btn"
                :class="{ active: traceResultTab === 'overview' }"
                @click="traceResultTab = 'overview'"
              >
                ⏱ 耗时概览
              </button>
              <button
                class="trace-sub-btn"
                :class="{ active: traceResultTab === 'logs' }"
                @click="traceResultTab = 'logs'"
              >
                📋 匹配日志
                <span class="trace-sub-badge">
                  <span v-if="loadingTraceLogs" class="spinner" style="width:10px;height:10px;border-width:2px"></span>
                  <span v-else>{{ traceLogs.length }}</span>
                </span>
              </button>
            </div>

            <!-- ── 耗时概览页签 ── -->
            <div v-show="traceResultTab === 'overview'" class="trace-overview">
              <!-- 大耗时数字区 -->
              <div class="trace-hero">
                <div class="trace-hero-label">全链路耗时</div>
                <div class="trace-hero-duration">{{ traceResult.duration_str }}</div>
                <div class="trace-hero-meta">
                  关键字 <em>{{ traceResult.keyword }}</em>
                  · 共匹配 <strong>{{ traceResult.log_count }}</strong> 条日志
                  <span v-if="traceResult.log_count >= 50000" class="trace-limit-hint">（已达扫描上限）</span>
                </div>
              </div>
              <!-- 时间线 -->
              <div class="trace-timeline-card">
                <!-- 首次 -->
                <div class="trace-tl-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-dot dot-first"></div>
                    <div class="trace-tl-connector"></div>
                  </div>
                  <div class="trace-tl-body">
                    <div class="trace-tl-tag">首次出现</div>
                    <div class="trace-tl-ts">{{ traceResult.first_ts }}</div>
                    <span v-if="traceResult.first_service" class="trace-ep-svc">{{ traceResult.first_service }}</span>
                    <div class="trace-tl-log">{{ traceResult.first_log }}</div>
                  </div>
                </div>
                <!-- 耗时标注 -->
                <div class="trace-tl-row dur-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-line"></div>
                  </div>
                  <div class="trace-tl-dur-badge">{{ traceResult.duration_str }}</div>
                </div>
                <!-- 末次 -->
                <div class="trace-tl-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-dot dot-last"></div>
                  </div>
                  <div class="trace-tl-body">
                    <div class="trace-tl-tag">末次出现</div>
                    <div class="trace-tl-ts">{{ traceResult.last_ts }}</div>
                    <span v-if="traceResult.last_service" class="trace-ep-svc">{{ traceResult.last_service }}</span>
                    <div class="trace-tl-log">{{ traceResult.last_log }}</div>
                  </div>
                </div>
              </div>

              <!-- 每条耗时列表 -->
              <div class="trace-spans-card">
                <div class="trace-spans-header">
                  <span>每次出现耗时</span>
                  <span v-if="loadingTraceLogs" class="spinner" style="width:11px;height:11px;border-width:2px;flex-shrink:0"></span>
                  <span v-else class="trace-logs-count">{{ traceLogs.length }} 条</span>
                </div>
                <div v-if="loadingTraceLogs && !traceLogs.length" class="empty-state" style="padding:20px">
                  <div class="spinner"></div><p style="font-size:12px">加载中...</p>
                </div>
                <div v-else class="trace-span-list">
                  <div
                    v-for="(log, i) in traceLogs" :key="i"
                    class="trace-span-row"
                    :class="[logClass(log.line), { expanded: expandedSpans.has(i) }]"
                    @click="toggleSpan(i)"
                  >
                    <div class="trace-span-idx">{{ i + 1 }}</div>
                    <div class="trace-span-elapsed">{{ spanElapsed(log) }}</div>
                    <div class="trace-span-bar-wrap">
                      <div class="trace-span-bar" :style="{ width: spanBarW(log) + '%' }"></div>
                    </div>
                    <div class="trace-span-ts">{{ log.timestamp }}</div>
                    <span v-if="log.labels.app || log.labels.job" class="trace-ep-svc">{{ log.labels.app || log.labels.job }}</span>
                    <div class="trace-span-line">{{ log.line }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- ── 匹配日志页签 ── -->
            <div v-show="traceResultTab === 'logs'" class="trace-log-panel">
              <div class="trace-logs-header">
                <span>匹配日志（按时间升序）</span>
                <span v-if="loadingTraceLogs" class="spinner" style="width:12px;height:12px;border-width:2px;flex-shrink:0"></span>
                <span v-else class="trace-logs-count">{{ traceLogs.length }} 条</span>
                <span v-if="traceLogs.length >= 2000" class="trace-limit-hint" style="margin-left:4px">（仅展示前 2000 条）</span>
              </div>
              <div class="trace-log-list">
                <div v-if="loadingTraceLogs && !traceLogs.length" class="empty-state" style="padding:24px">
                  <div class="spinner"></div><p style="font-size:12px">加载日志列表...</p>
                </div>
                <div
                  v-for="(log, i) in traceLogs" :key="i"
                  class="log-line" :class="logClass(log.line)"
                >
                  <span class="log-ts">{{ log.timestamp }}</span>
                  <span class="log-svc">{{ log.labels.app || log.labels.job || '?' }}</span>
                  <span class="log-text">{{ log.line }}</span>
                </div>
              </div>
            </div>
          </template>
        </div>
        <!-- 初始提示 -->
        <div v-else class="empty-state" style="flex:1">
          <span class="icon" style="font-size:36px">⏱</span>
          <p>输入追踪值并选择时间范围，分析关键字首次到末次出现的耗时</p>
          <small style="color:var(--text-muted)">支持 traceId、requestId、订单号等任意字符串</small>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, streamSSE } from '../api/index.js'
import {
  CONTEXT_INITIAL_SIDE,
  CONTEXT_MAX_SIDE,
  nextContextCount,
} from '../utils/logLoading.mjs'
import {
  buildCoverageSummary,
  countLoadedPods,
  replacePodFilters,
} from '../utils/logCoverage.mjs'
import { displayLogLine } from '../utils/logDisplay.mjs'
import {
  resolveDefaultLabelNames,
  toggleDefaultLabelName,
} from '../utils/logLabelPreferences.mjs'

const router = useRouter()

// ── 公共状态 ─────────────────────────────
const selectedService = ref('')
const hours          = ref('0.083333')
const groupBy        = ref('namespace')
const selectedGroupLabel = ref('')
const selectedGroupValue = ref('')
const labelCatalog   = ref([])
const loadingLabelCatalog = ref(false)
const labelExplorerOpen = ref(true)
const defaultLabelSettingsOpen = ref(false)
const defaultLabelNames = ref([])
const recommendedDefaultLabelNames = ref([])
const serviceLabelName = ref('')     // Loki 服务标签名（如 app），钻取联动用
const openLabelGroups = ref(new Set())
const labelValueMap = ref({})
const labelValueTotals = ref({})
const loadingLabelValueMap = ref({})
const selectedLabelName = ref('')
const selectedLabelValue = ref('')
// 可搜索下拉：查询词 + 展开状态
const labelNameQuery = ref('')
const labelValueQuery = ref('')
const showLabelNameDropdown = ref(false)
const showLabelValueDropdown = ref(false)
let hideLabelNameTimer = null
let hideLabelValueTimer = null
// 多标签条件：数组形式 [{label, value}]，同 label 允许多值累加成 regex
const activeLabelFilters = ref([])
// 标签值批量勾选缓冲：保留 API 以兼容旧代码，但 UI 已换成『点即加』
const pickedLabelValues = ref([])
// DOM refs：选完标签名自动 focus 值输入框，省一次点击
const labelNameInputRef = ref(null)
const labelValueInputRef = ref(null)

const activeTab      = ref('logs')

// 时间模式：默认查询当前时刻之前 5 分钟；仍可切回 relative（最近N小时）
const initialTimeRange = recentFiveMinuteRange()
const timeMode    = ref('custom')
const customStart = ref(initialTimeRange.start)
const customEnd   = ref(initialTimeRange.end)
let appliedCustomTimeKey = `${initialTimeRange.start}|${initialTimeRange.end}`

// 时间戳快速粘贴
const tsPasteInput   = ref('')
const tsPasteError   = ref('')
const customTimeError = ref('')
const customTimeRangeCopied = ref(false)
const tsCenter       = ref(null)   // 解析出的中心时刻（Date）
const tsRangeMinutes = ref(5)      // 当前应用的 ± 分钟数
const TS_RANGE_PRESETS = [
  { v: 1,  label: '1分' },
  { v: 5,  label: '5分' },
  { v: 15, label: '15分' },
  { v: 30, label: '30分' },
  { v: 60, label: '1小时' },
]
const tsCenterText = computed(() => tsCenter.value ? fmtDateTimeSec(tsCenter.value) : '')

// 关键字搜索
const keyword      = ref('')         // 后端单关键字（旧参数，仍保留）
const localKeywords     = ref([])    // 多条件过滤：[{ text, exclude }] AND/OR，同时推到 Loki 服务端
const localKeywordInput = ref('')    // 多条件输入框临时状态
const keywordMode  = ref('and')      // 多关键字组合模式 and/or
// 多服务：LogAnalysis 支持一次查多个服务的日志（跨服务调用链排障用）
const selectedServices  = ref([])    // 已选服务列表 chip
const serviceChipInput  = ref('')    // 服务 chip 输入临时状态
const allServicesList   = ref([])    // 服务名下拉候选（datalist）
let   searchTimer  = null

function addChipFromInput() {
  const raw = (localKeywordInput.value || '').trim()
  if (!raw) return
  // - 前缀视为排除
  const exclude = raw.startsWith('-') && raw.length > 1
  const text = exclude ? raw.slice(1).trim() : raw
  if (!text) return
  // 同文本去重
  if (localKeywords.value.some(c => c.text === text && c.exclude === exclude)) {
    localKeywordInput.value = ''
    return
  }
  localKeywords.value.push({ text, exclude })
  localKeywordInput.value = ''
  onParamChange()
}

function addServiceChip() {
  const raw = (serviceChipInput.value || '').trim()
  if (!raw) return
  if (selectedServices.value.includes(raw)) { serviceChipInput.value = ''; return }
  selectedServices.value.push(raw)
  serviceChipInput.value = ''
  // 单值 selectedService 保持与首个已选服务同步，便于跳转/URL 兼容
  if (selectedServices.value.length === 1) selectedService.value = raw
  onParamChange()
}

function removeServiceChip(i) {
  selectedServices.value.splice(i, 1)
  if (!selectedServices.value.length && selectedService.value) selectedService.value = ''
  else if (selectedServices.value.length) selectedService.value = selectedServices.value[0]
  onParamChange()
}

function onServiceChipBackspace() {
  if (serviceChipInput.value === '' && selectedServices.value.length) {
    selectedServices.value.pop()
    onParamChange()
  }
}

// 组装本页所有请求都要带的多条件参数（服务/关键字/排除/模式/标签）
function multiFilterParams() {
  const p = {}
  const svcs = selectedServices.value
  if (svcs.length > 1) p.services = svcs.join(',')
  else if (svcs.length === 1) p.service = svcs[0]
  else if (selectedService.value) p.service = selectedService.value

  const inc = localKeywords.value.filter(c => !c.exclude).map(c => c.text)
  const exc = localKeywords.value.filter(c =>  c.exclude).map(c => c.text)
  if (inc.length) {
    p.keywords = inc.join(',')
    if (inc.length > 1) p.keyword_mode = keywordMode.value
  } else if (keyword.value) {
    p.keyword = keyword.value
  }
  if (exc.length) p.exclude_keywords = exc.join(',')

  // 多标签条件：axios 收到数组会自动展开成 labels=a:x&labels=b:y
  if (activeLabelFilters.value.length) {
    p.labels = activeLabelFilters.value.map(x => `${x.label}:${x.value}`)
  }
  return p
}

function toggleChipExclude(i) {
  const c = localKeywords.value[i]
  if (!c) return
  localKeywords.value.splice(i, 1, { ...c, exclude: !c.exclude })
}

function removeChip(i) {
  localKeywords.value.splice(i, 1)
}

// 输入框空时按 backspace：删掉最后一个 chip（IDE / 邮件客户端常见交互）
function onMultiInputBackspace() {
  if (localKeywordInput.value === '' && localKeywords.value.length) {
    localKeywords.value.pop()
  }
}
let   logsAbort = null
let   loadMoreAbort = null
let   logDistributionAbort = null
let   templatesAbort = null
let   traceLogsAbort = null
let   detailContextAbort = null
let   copiedContextLineTimer = null
let   logsRequestId = 0
let   loadMoreRequestId = 0
let   logDistributionRequestId = 0
let   templatesRequestId = 0
let   detailContextRequestId = 0

const selectedLabelValues = computed(() => (
  selectedLabelName.value ? (labelValueMap.value[selectedLabelName.value] || []) : []
))

// ── 可搜索下拉过滤（大小写不敏感包含匹配） ──
function _fuzzyFilter(items, query, textFn) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return items
  return items.filter(it => textFn(it).toLowerCase().includes(q))
}

const filteredLabels = computed(() => (
  _fuzzyFilter(labelCatalog.value || [], labelNameQuery.value, it => it.name)
))
const defaultLabelItems = computed(() => defaultLabelNames.value
  .map(name => labelCatalog.value.find(item => item.name === name))
  .filter(Boolean))
const filteredLabelValues = computed(() => (
  _fuzzyFilter(selectedLabelValues.value, labelValueQuery.value, v => String(v))
))

// 高亮命中片段，切成 [{t, hit}] 数组供 <mark class="hl"> 渲染
function highlight(text, query) {
  const str = String(text ?? '')
  const q = (query || '').trim()
  if (!q) return [{ t: str, hit: false }]
  const idx = str.toLowerCase().indexOf(q.toLowerCase())
  if (idx < 0) return [{ t: str, hit: false }]
  const out = []
  if (idx > 0) out.push({ t: str.slice(0, idx), hit: false })
  out.push({ t: str.slice(idx, idx + q.length), hit: true })
  if (idx + q.length < str.length) out.push({ t: str.slice(idx + q.length), hit: false })
  return out
}

function pickLabelName(name) {
  selectedLabelName.value = name
  labelNameQuery.value = name
  showLabelNameDropdown.value = false
  // 复位标签值搜索 + 清空跨 label 的勾选缓冲，避免把 A 标签的值误加到 B
  labelValueQuery.value = ''
  pickedLabelValues.value = []
  onLabelDropdownChange()
  // 智能串联：选完标签名 → 自动 focus 值输入框，用户直接选值即可（省一步）
  nextTick(() => {
    labelValueInputRef.value?.focus?.()
    showLabelValueDropdown.value = true
  })
}

const LOKI_DEFAULT_LABELS_STORAGE_KEY = 'aiops.logs.default-labels.v1'

function readSavedDefaultLabelNames() {
  try {
    const raw = localStorage.getItem(LOKI_DEFAULT_LABELS_STORAGE_KEY)
    if (raw == null) return null
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

function saveDefaultLabelNames() {
  try {
    localStorage.setItem(LOKI_DEFAULT_LABELS_STORAGE_KEY, JSON.stringify(defaultLabelNames.value))
  } catch {}
}

function toggleDefaultLabelPreference(labelName) {
  defaultLabelNames.value = toggleDefaultLabelName(defaultLabelNames.value, labelName)
  saveDefaultLabelNames()
}

function restoreRecommendedDefaultLabels() {
  defaultLabelNames.value = [...recommendedDefaultLabelNames.value]
  saveDefaultLabelNames()
}

// 标签名输入框回车：支持 `label=val1,val2` 一次性生成多条 chip
function onLabelNameEnter() {
  const raw = (labelNameQuery.value || '').trim()
  if (!raw) return
  // 快捷格式：包含 = 直接解析
  if (raw.includes('=')) {
    const [k, ...rest] = raw.split('=')
    const key = k.trim()
    const valsRaw = rest.join('=').trim()
    if (!key || !valsRaw) return
    const vals = valsRaw.split(',').map(s => s.trim()).filter(Boolean)
    if (!vals.length) return
    vals.forEach((v, i) => addActiveLabel(key, v, {
      silent: true, skipRefresh: i < vals.length - 1,
    }))
    // 加完清空输入
    labelNameQuery.value = ''
    labelValueQuery.value = ''
    selectedLabelName.value = key
    selectedLabelValue.value = ''
    showLabelNameDropdown.value = false
    return
  }
  // 无 = 时：如果搜到唯一标签名，自动选中它
  const matches = filteredLabels.value
  if (matches.length === 1) {
    pickLabelName(matches[0].name)
  }
}

// 值输入框回车：把当前搜索词（支持逗号分隔）作为值批量加入
function onLabelValueEnter() {
  if (!selectedLabelName.value) return
  const raw = (labelValueQuery.value || '').trim()
  if (!raw) return
  const vals = raw.split(',').map(s => s.trim()).filter(Boolean)
  vals.forEach((v, i) => addActiveLabel(selectedLabelName.value, v, {
    silent: true, skipRefresh: i < vals.length - 1,
  }))
  labelValueQuery.value = ''
  selectedLabelValue.value = ''
  // 保持下拉打开，方便继续加
}

// 点击下拉里某个值 = 立即加/移除 chip（切换态）
function quickAddLabelValue(value) {
  if (!selectedLabelName.value) return
  const v = String(value)
  const idx = activeLabelFilters.value.findIndex(
    x => x.label === selectedLabelName.value && x.value === v,
  )
  if (idx >= 0) {
    // 二次点击 = 移除
    removeActiveLabel(idx)
  } else {
    addActiveLabel(selectedLabelName.value, v, { silent: true })
    labelValueQuery.value = ''
    refreshActiveData()
  }
  // 保持下拉打开 + 值输入框继续聚焦，方便连续操作
  clearTimeout(hideLabelValueTimer)
  showLabelValueDropdown.value = true
  nextTick(() => labelValueInputRef.value?.focus?.())
}

function hasChip(label, value) {
  if (!label || value === '' || value == null) return false
  const v = String(value)
  return activeLabelFilters.value.some(x => x.label === label && x.value === v)
}
function clearLabelName() {
  selectedLabelName.value = ''
  labelNameQuery.value = ''
  labelValueQuery.value = ''
  selectedLabelValue.value = ''
  showLabelNameDropdown.value = true
}
function hideLabelNameLater() {
  clearTimeout(hideLabelNameTimer)
  hideLabelNameTimer = setTimeout(() => { showLabelNameDropdown.value = false }, 120)
}

function pickLabelValue(value) {
  selectedLabelValue.value = value
  labelValueQuery.value = String(value)
  showLabelValueDropdown.value = false
  onLabelValueDropdownChange()
}

// 勾选式多选：点行 = 切换 picked（不关闭下拉，支持连续勾多个）
function togglePickLabelValue(value) {
  const v = String(value)
  const list = pickedLabelValues.value
  const idx = list.indexOf(v)
  if (idx >= 0) list.splice(idx, 1)
  else list.push(v)
  // 同步 selectedLabelValue 为『最近点的』，让 combo-input 显示可用
  if (list.length) {
    selectedLabelValue.value = list[list.length - 1]
    labelValueQuery.value = list[list.length - 1]
  } else {
    selectedLabelValue.value = ''
    labelValueQuery.value = ''
  }
}
function clearLabelValue() {
  selectedLabelValue.value = ''
  labelValueQuery.value = ''
  showLabelValueDropdown.value = true
}
function hideLabelValueLater() {
  clearTimeout(hideLabelValueTimer)
  hideLabelValueTimer = setTimeout(() => { showLabelValueDropdown.value = false }, 120)
}

// selectedLabelName/Value 被其它路径（_applyRouteQuery / loadLabelCatalog）
// 修改时，同步输入框显示，避免"值已选但输入框为空"的错觉
watch(selectedLabelName, (v) => {
  if (v && !labelNameQuery.value) labelNameQuery.value = v
  else if (!v) labelNameQuery.value = ''
})
watch(selectedLabelValue, (v) => {
  if (v && !labelValueQuery.value) labelValueQuery.value = String(v)
  else if (!v) labelValueQuery.value = ''
})

function logServiceName(log) {
  return log?.labels?.app || log?.labels?.job || selectedService.value || '—'
}

function logGroup(log) {
  const labels = log?.labels || {}
  if (selectedGroupLabel.value && labels[selectedGroupLabel.value]) return labels[selectedGroupLabel.value]
  if (groupBy.value && labels[groupBy.value]) return labels[groupBy.value]
  return (
    labels.namespace ||
    labels.k8s_namespace_name ||
    labels.kubernetes_namespace ||
    labels.k8s_namespace ||
    labels.ns ||
    '默认'
  )
}

const CONTAINER_LABEL_KEYS = new Set([
  'container',
  'container_name',
  'k8s_container',
  'k8s_container_name',
  'kubernetes_container',
  'kubernetes_container_name',
])
const POD_LABEL_KEYS = [
  'pod',
  'pod_name',
  'k8s_pod',
  'k8s_pod_name',
  'kubernetes_pod',
  'kubernetes_pod_name',
]
const NAMESPACE_LABEL_KEYS = [
  'namespace',
  'k8s_namespace',
  'k8s_namespace_name',
  'kubernetes_namespace',
  'kubernetes_namespace_name',
  'ns',
]
const CLUSTER_LABEL_KEYS = [
  'cluster_id',
  'cluster',
  'cluster_name',
  'k8s_cluster',
  'k8s_cluster_name',
  'kubernetes_cluster',
  'kubernetes_cluster_name',
]
const SERVICE_LABEL_KEYS = [
  'service',
  'service_name',
  'svc',
  'app',
  'app_name',
  'application',
  'application_name',
  'component',
  'workload',
  'deployment',
  'statefulset',
  'daemonset',
  'job',
  'k8s_app',
  'k8s_app_name',
  'k8s_label_app',
  'k8s_label_app_kubernetes_io_name',
  'app_kubernetes_io_name',
  'app_kubernetes_io_instance',
  'kubernetes_name',
  'container',
  'container_name',
]
const LOW_VALUE_LABEL_KEYS = new Set([
  '__name__',
  'filename',
  'level',
  'severity',
  'stream',
  'cluster',
  'cluster_id',
  'namespace',
  'pod',
  'pod_name',
  'instance',
  'host',
  'hostname',
  'node',
  'ip',
])

function normalizeLabelKey(key) {
  return String(key || '')
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

function isContainerLabel(key) {
  return CONTAINER_LABEL_KEYS.has(normalizeLabelKey(key))
}

function labelValue(labels, keys) {
  const normalizedMap = new Map(
    Object.entries(labels || {}).map(([key, value]) => [normalizeLabelKey(key), value]),
  )
  for (const key of keys) {
    const value = normalizedMap.get(key)
    if (value !== undefined && value !== null && String(value).trim() !== '') return String(value)
  }
  return ''
}

function compactQuery(query) {
  return Object.fromEntries(
    Object.entries(query).filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== ''),
  )
}

function containerLogLinkTitle(labels) {
  const pod = labelValue(labels, POD_LABEL_KEYS)
  const namespace = labelValue(labels, NAMESPACE_LABEL_KEYS)
  if (pod && namespace) return `跳转到 ${namespace}/${pod} 的容器日志`
  if (pod) return `跳转到 ${pod} 的容器日志`
  return '跳转到容器日志页'
}

function labelEntryValue(entry) {
  return entry ? String(entry.value ?? '').trim() : ''
}

function labelEntryFromAliases(labels, keys) {
  const normalized = Object.entries(labels || {}).map(([key, value]) => ({
    label: key,
    normalized: normalizeLabelKey(key),
    value,
  }))
  for (const alias of keys) {
    const normalizedAlias = normalizeLabelKey(alias)
    const match = normalized.find(item => item.normalized === normalizedAlias)
    if (match && String(match.value ?? '').trim() !== '') {
      return { label: match.label, value: String(match.value).trim() }
    }
  }
  return null
}

function detailContainerValue(labels) {
  return labelEntryValue(labelEntryFromAliases(labels, [...CONTAINER_LABEL_KEYS]))
}

function detailServiceDrilldown(labels) {
  const serviceAliases = uniqueContextTerms([
    normalizeLabelKey(serviceLabelName.value),
    ...SERVICE_LABEL_KEYS,
  ])
  const direct = labelEntryFromAliases(labels, serviceAliases)
  if (direct) return { ...direct, serviceLike: true }
  const entries = Object.entries(labels || {})
    .map(([label, value]) => ({ label, normalized: normalizeLabelKey(label), value: String(value ?? '').trim() }))
    .filter(item => item.value && !item.normalized.startsWith('__'))
  const preferred = entries.find(item => !LOW_VALUE_LABEL_KEYS.has(item.normalized)) || entries[0]
  return preferred ? { label: preferred.label, value: preferred.value, serviceLike: false } : null
}

function serviceLogLinkTitle(labels) {
  const target = detailServiceDrilldown(labels)
  if (!target) return '跳转到容器页面的微服务日志'
  return `跳转到容器页面查看 ${target.label}=${target.value} 的微服务日志`
}

function goToMicroserviceLogs(labels) {
  const target = detailServiceDrilldown(labels)
  if (!target) return

  closeDetail()
  router.push({
    name: 'containers',
    query: compactQuery({
      view: 'logs',
      pod: labelValue(labels, POD_LABEL_KEYS),
      namespace: labelValue(labels, NAMESPACE_LABEL_KEYS),
      container: detailContainerValue(labels),
      cluster_id: labelValue(labels, CLUSTER_LABEL_KEYS),
      service: target.serviceLike ? target.value : '',
      service_label: target.serviceLike ? target.label : '',
    }),
  })
}

function applyRouteLabelFilters(params) {
  const labels = params.getAll('labels')
  for (const item of labels) {
    if (!item || !item.includes(':')) continue
    const [label, ...rest] = item.split(':')
    const value = rest.join(':')
    if (label && value) {
      addActiveLabel(label, value, { silent: true, skipRefresh: true })
    }
  }
}

function goToContainerLogs(labels, containerValue) {
  const container = String(containerValue ?? '').trim()
  if (!container) return
  router.push({
    name: 'containers',
    query: compactQuery({
      view: 'logs',
      pod: labelValue(labels, POD_LABEL_KEYS),
      namespace: labelValue(labels, NAMESPACE_LABEL_KEYS),
      container,
      cluster_id: labelValue(labels, CLUSTER_LABEL_KEYS),
    }),
  })
}

// 返回当前时刻往前 5 分钟的本地时间范围。
function recentFiveMinuteRange(formatter = fmtDateTimeSec) {
  const now = new Date()
  return {
    start: formatter(new Date(now.getTime() - 5 * 60 * 1000)),
    end: formatter(now),
  }
}

// 本地时间字符串转成 UTC ISO 再发给后端。
function toUtcStr(localStr) {
  if (!localStr) return ''
  const parsed = parseFlexibleTime(localStr)
  return parsed ? parsed.toISOString().slice(0, 19) : ''   // "2025-03-25T02:00:30"
}

// Date → datetime-local 输入值（本地时间，秒精度）
function toLocalInput(d) {
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
         `T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function fmtDateTimeSec(d) {
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// 智能解析各种标准时间/时间戳 → Date（无法解析返回 null）
//   核心场景：直接复制日志里的 2026-07-10 09:53:43（可含毫秒/斜杠/T 分隔/时区）
//   兼容：ISO(带/不带 Z 或 ±时区) / 纳秒(≥16位)/毫秒(13位)/秒(10位) epoch
//   健壮：容忍前后空白、多空格、制表符，甚至从整行日志文本中提取首个时间
function parseFlexibleTime(raw) {
  const s = String(raw || '').trim()
  if (!s) return null
  const pad2 = n => String(n).padStart(2, '0')
  const toEpoch = digits => {
    // ≥13 位取前 13 位为毫秒（纳秒/微秒/毫秒），否则按秒
    const ms = digits.length >= 13 ? Number(digits.slice(0, 13)) : Number(digits) * 1000
    const d = new Date(ms)
    return isNaN(d.getTime()) ? null : d
  }

  // 整串是纯数字 → epoch 时间戳
  if (/^\d+$/.test(s)) return toEpoch(s)

  // 从文本中提取「日期[ 时间][时区]」，容忍多空格/制表符/整行复制
  const m = s.match(
    /(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[\sT]+(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.(\d+))?\s*(Z|[+-]\d{2}:?\d{2})?)?/
  )
  if (m) {
    const [, Y, Mo, D, h, mi, se, frac, tz] = m
    const year = Number(Y)
    const month = Number(Mo)
    const day = Number(D)
    const hour = Number(h || 0)
    const minute = Number(mi || 0)
    const second = Number(se || 0)
    const validParts = month >= 1 && month <= 12 && day >= 1 && day <= 31 &&
      hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59 && second >= 0 && second <= 59
    if (!validParts) return null
    const calendarDate = new Date(year, month - 1, day)
    if (calendarDate.getFullYear() !== year || calendarDate.getMonth() !== month - 1 || calendarDate.getDate() !== day) {
      return null
    }
    if (h == null) {
      return calendarDate
    }
    if (tz) {
      // 带时区 → 拼成标准 ISO 交给 Date（毫秒截断到 3 位，时区补冒号）
      const iso = `${Y}-${pad2(Mo)}-${pad2(D)}T${pad2(h)}:${pad2(mi)}:${pad2(se || 0)}` +
                  `${frac ? '.' + frac.slice(0, 3) : ''}${tz.replace(/([+-]\d{2})(\d{2})$/, '$1:$2')}`
      const d = new Date(iso)
      return isNaN(d.getTime()) ? null : d
    }
    // 无时区 → 按本地时间构造（不依赖浏览器对字符串的解析差异）
    const local = new Date(year, month - 1, day, hour, minute, second)
    return local.getFullYear() === year && local.getMonth() === month - 1 && local.getDate() === day &&
      local.getHours() === hour && local.getMinutes() === minute && local.getSeconds() === second
      ? local
      : null
  }

  // 文本里夹带的纯 epoch（10~19 位数字）
  const em = s.match(/\d{10,19}/)
  if (em) return toEpoch(em[0])

  // 兜底：交给浏览器
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}

const _TS_RANGE_SEP = /\s*(?:~|～|至|到|—|,|、)\s*|\s+-\s+/

// 解析粘贴内容：区间(起~止)直接填两端，单点作为中心 + 默认 ±范围
function applyTsPaste() {
  const raw = (tsPasteInput.value || '').trim()
  tsPasteError.value = ''
  if (!raw) return

  const parts = raw.split(_TS_RANGE_SEP).map(x => x.trim()).filter(Boolean)
  if (parts.length >= 2) {
    const a = parseFlexibleTime(parts[0])
    const b = parseFlexibleTime(parts[1])
    if (a && b) {
      const [start, end] = a <= b ? [a, b] : [b, a]
      tsCenter.value = null
      customStart.value = fmtDateTimeSec(start)
      customEnd.value = fmtDateTimeSec(end)
      onCustomTimeChange()
      return
    }
  }

  const center = parseFlexibleTime(parts[0] || raw)
  if (!center) {
    tsPasteError.value = '无法识别，请粘贴标准时间或时间戳'
    return
  }
  tsCenter.value = center
  applyCenterRange(tsRangeMinutes.value)
}

function onTsPaste(e) {
  const text = e?.clipboardData?.getData('text')
  if (text != null) {
    tsPasteInput.value = text
    e.preventDefault()
  }
  // 粘贴后自动解析，无需再点按钮
  nextTick(applyTsPaste)
}

async function copyCustomTimeRange() {
  if (!customStart.value || !customEnd.value) {
    tsPasteError.value = '请先填写完整的开始时间和结束时间'
    return
  }
  const text = `${customStart.value.replace('T', ' ')} ~ ${customEnd.value.replace('T', ' ')}`
  try {
    await navigator.clipboard.writeText(text)
    customTimeRangeCopied.value = true
    setTimeout(() => { customTimeRangeCopied.value = false }, 1500)
  } catch {
    tsPasteError.value = '浏览器不允许访问剪贴板，请手动复制时间段'
  }
}

// 围绕中心时刻 ± N 分钟生成时间范围并查询
function applyCenterRange(minutes) {
  if (!tsCenter.value) return
  tsRangeMinutes.value = minutes
  const c = tsCenter.value.getTime()
  customStart.value = fmtDateTimeSec(new Date(c - minutes * 60000))
  customEnd.value   = fmtDateTimeSec(new Date(c + minutes * 60000))
  onCustomTimeChange()
}

// 构建时间参数（relative 或 custom）
function timeParams() {
  if (timeMode.value === 'custom' && customStart.value && customEnd.value) {
    return { start_time: toUtcStr(customStart.value), end_time: toUtcStr(customEnd.value) }
  }
  return { hours: hours.value }
}

function currentGroupParams() {
  if (!selectedGroupLabel.value || !selectedGroupValue.value) {
    return {}
  }
  return {
    group_label: selectedGroupLabel.value,
    group_value: selectedGroupValue.value,
  }
}

// ── 日志流 ───────────────────────────────
const logs         = ref([])
const levelFilter  = ref('')
const loadingLogs  = ref(false)
const loadingMore  = ref(false)
const hasMore      = ref(false)
const nextCursorNs = ref(null)
const totalLoaded  = ref(0)
const logScrollWrap = ref(null)
const logDistribution = ref(null)
const loadingLogDistribution = ref(false)
const logDistributionError = ref('')
const analyzingAI  = ref(false)
const aiContent    = ref('')

// 仅事件过滤
const incidentOnly = ref(false)
const INCIDENT_KEYWORDS = ['error', 'exception', 'fail', 'timeout', 'refused', 'panic', 'oom', 'fatal', 'traceback']

// 详情抽屉
const detailLog   = ref(null)
const showDetailModal = ref(false)
const loadingDetailContext = ref(false)
const detailContextLogs = ref([])
const detailContextAnchorIndex = ref(-1)
const detailContextAnchorFound = ref(true)
const detailContextBeforeCount = ref(0)
const detailContextAfterCount = ref(0)
const detailContextError = ref('')
const detailModalMask = ref(null)
const contextScrollWrap = ref(null)
const metaOpen = ref(false)   // 元数据折叠状态：默认收起，给上下文留位
const contextSearchInput = ref('')
const contextSearchKeywords = ref([])
const contextSearchDraftJoin = ref('and')
const activeContextSearchMatch = ref(0)
const copiedContextLineKey = ref('')
let contextSearchConditionId = 0

// 上下文窗口大小：初始 250 前 + 250 后；每次滚动到边界扩 +200，最大 500（后端 API 限制）
const CONTEXT_INITIAL_BEFORE = CONTEXT_INITIAL_SIDE
const CONTEXT_INITIAL_AFTER  = CONTEXT_INITIAL_SIDE
const contextWantedBefore = ref(CONTEXT_INITIAL_BEFORE)
const contextWantedAfter  = ref(CONTEXT_INITIAL_AFTER)
const loadingContextBefore = ref(false)
const loadingContextAfter  = ref(false)
// 实际返回数小于请求数时，表示该方向已无更多数据（或到达边界）
const contextBeforeAtLimit = ref(false)
const contextAfterAtLimit  = ref(false)
let contextScrollPending = null   // 用于触底/触顶滚动锚点保留

// 提取日志级别
function extractLevel(line) {
  const l = (line || '').toLowerCase()
  if (/\berror\b|exception|fatal|panic|traceback/.test(l)) return 'error'
  if (/\bwarn(ing)?\b/.test(l))                            return 'warn'
  if (/\binfo\b/.test(l))                                  return 'info'
  if (/\bdebug\b/.test(l))                                 return 'debug'
  return 'other'
}

function logRowClass(line) {
  const lvl = extractLevel(line)
  if (lvl === 'error') return 'row-error'
  if (lvl === 'warn')  return 'row-warn'
  return ''
}

function isSameLog(a, b) {
  if (!a || !b) return false
  const aTs = a.timestamp_ns != null ? String(a.timestamp_ns) : ''
  const bTs = b.timestamp_ns != null ? String(b.timestamp_ns) : ''
  if (aTs && bTs) return aTs === bTs && (a.line || '') === (b.line || '')
  return a === b
}

function isSelectedLog(log) {
  return isSameLog(log, detailLog.value)
}

function scrollContextAnchorIntoView() {
  const anchor = contextScrollWrap.value?.querySelector('.drawer-context-item.active')
  if (!anchor) return false
  anchor.scrollIntoView({ block: 'center', behavior: 'auto' })
  return true
}

function splitContextSearchTerms(raw) {
  return String(raw || '')
    .split(/[,，、;；]+/)
    .map(item => item.trim())
    .filter(Boolean)
}

function uniqueContextTerms(items) {
  const seen = new Set()
  const out = []
  for (const item of items) {
    const text = String(item || '').trim()
    if (!text) continue
    const key = text.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(text)
  }
  return out
}

const contextSearchConditions = computed(() => {
  const conditions = contextSearchKeywords.value.map(item => ({
    text: item.text,
    join: item.join,
  }))
  for (const text of splitContextSearchTerms(contextSearchInput.value)) {
    conditions.push({
      text,
      join: conditions.length ? contextSearchDraftJoin.value : 'and',
    })
  }
  const seen = new Set()
  return conditions.filter(item => {
    const key = item.text.toLowerCase()
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})

const contextSearchTerms = computed(() => uniqueContextTerms(
  contextSearchConditions.value.map(item => item.text),
))

// AND 的优先级高于 OR：A AND B OR C AND D => (A AND B) OR (C AND D)
const contextSearchConditionGroups = computed(() => {
  const groups = []
  for (const condition of contextSearchConditions.value) {
    const term = condition.text.toLowerCase()
    if (!groups.length || condition.join === 'or') {
      groups.push([term])
    } else {
      groups[groups.length - 1].push(term)
    }
  }
  return groups
})

function contextLogSearchText(log) {
  return [
    log?.timestamp || '',
    logServiceName(log),
    log?.line || '',
  ].join(' ').toLowerCase()
}

function contextLogMatchesSearch(log) {
  const groups = contextSearchConditionGroups.value
  if (!groups.length) return false
  const haystack = contextLogSearchText(log)
  return groups.some(group => group.every(term => haystack.includes(term)))
}

const contextSearchMatches = computed(() => {
  if (!contextSearchTerms.value.length) return []
  return detailContextLogs.value
    .map((log, idx) => contextLogMatchesSearch(log) ? idx : -1)
    .filter(idx => idx >= 0)
})

const contextSearchMatchCount = computed(() => contextSearchMatches.value.length)
const contextSearchMatchIndexSet = computed(() => new Set(contextSearchMatches.value))

function escapeRegExp(text) {
  return String(text).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const contextSearchRegex = computed(() => {
  const terms = contextSearchTerms.value
    .slice()
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
  if (!terms.length) return null
  return new RegExp(terms.join('|'), 'gi')
})

// 按正则把文本切成 [{text, hit}] 片段，供 <mark> 高亮渲染（大小写不敏感由正则的 i 标志保证）
function segmentByRegex(line, regex) {
  const text = String(line ?? '')
  if (!regex) return [{ text, hit: false }]

  const out = []
  let lastIndex = 0
  regex.lastIndex = 0
  let match = regex.exec(text)
  while (match) {
    const start = match.index
    const end = start + match[0].length
    if (start > lastIndex) out.push({ text: text.slice(lastIndex, start), hit: false })
    out.push({ text: text.slice(start, end), hit: true })
    lastIndex = end
    if (match[0].length === 0) regex.lastIndex += 1
    match = regex.exec(text)
  }
  if (lastIndex < text.length) out.push({ text: text.slice(lastIndex), hit: false })
  return out.length ? out : [{ text, hit: false }]
}

function contextHighlightedSegments(line) {
  return segmentByRegex(displayLogLine(line), contextSearchRegex.value)
}

function contextLineCopyKey(item, idx) {
  return `${item?.timestamp_ns || item?.timestamp || 'line'}-${idx}`
}

function contextLineCopyText(item) {
  const parts = []
  if (item?.timestamp) parts.push(String(item.timestamp))
  const service = logServiceName(item)
  if (service) parts.push(String(service))
  const prefix = parts.join(' ')
  const line = displayLogLine(item?.line)
  return prefix ? `${prefix} ${line}`.trim() : line
}

function fallbackCopyText(text) {
  if (typeof document === 'undefined') return false
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  textarea.style.top = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    return document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
  }
}

async function writeClipboardText(text) {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return true
  }
  return fallbackCopyText(text)
}

async function copyContextLine(item, idx) {
  const text = contextLineCopyText(item)
  if (!text) return
  try {
    const ok = await writeClipboardText(text)
    if (!ok) return
    copiedContextLineKey.value = contextLineCopyKey(item, idx)
    clearTimeout(copiedContextLineTimer)
    copiedContextLineTimer = setTimeout(() => {
      copiedContextLineKey.value = ''
      copiedContextLineTimer = null
    }, 1600)
  } catch {
    // 浏览器或权限不允许复制时保持静默，避免打断日志排障流程。
  }
}

// ── 主日志流关键字高亮（忽略大小写）──────────────────────────────
// 命中的关键字来源：服务端单关键字 keyword + 多条件 include chips（排除项不高亮）
const activeSearchTerms = computed(() => {
  const seen = new Set()
  const terms = []
  const push = raw => {
    const t = String(raw || '').trim()
    if (!t) return
    const key = t.toLowerCase()
    if (seen.has(key)) return
    seen.add(key)
    terms.push(t)
  }
  for (const chip of localKeywords.value) {
    if (!chip.exclude) push(chip.text)
  }
  push(keyword.value)
  return terms
})

const logSearchRegex = computed(() => {
  const terms = activeSearchTerms.value
    .slice()
    .sort((a, b) => b.length - a.length)   // 长词优先，避免短词抢占
    .map(escapeRegExp)
  if (!terms.length) return null
  return new RegExp(terms.join('|'), 'gi')  // i = 忽略大小写
})

function highlightLogSegments(line) {
  return segmentByRegex(displayLogLine(line), logSearchRegex.value)
}

function isContextSearchMatch(idx) {
  return contextSearchMatchIndexSet.value.has(idx)
}

function isCurrentContextSearchMatch(idx) {
  if (!contextSearchMatches.value.length) return false
  return contextSearchMatches.value[activeContextSearchMatch.value] === idx
}

function scrollToCurrentContextSearchMatch() {
  const idx = contextSearchMatches.value[activeContextSearchMatch.value]
  if (idx == null) return false
  const target = contextScrollWrap.value?.querySelector(`[data-context-index="${idx}"]`)
  if (!target) return false
  target.scrollIntoView({ block: 'center', behavior: 'smooth' })
  return true
}

function addContextSearchKeywords() {
  const terms = splitContextSearchTerms(contextSearchInput.value)
  if (!terms.length) return
  const existing = new Set(contextSearchKeywords.value.map(item => item.text.toLowerCase()))
  for (const text of terms) {
    const key = text.toLowerCase()
    if (existing.has(key)) continue
    contextSearchKeywords.value.push({
      id: ++contextSearchConditionId,
      text,
      join: contextSearchKeywords.value.length ? contextSearchDraftJoin.value : 'and',
    })
    existing.add(key)
  }
  contextSearchInput.value = ''
  activeContextSearchMatch.value = 0
  nextTick(scrollToCurrentContextSearchMatch)
}

function toggleContextSearchJoin(index) {
  if (index <= 0 || !contextSearchKeywords.value[index]) return
  const condition = contextSearchKeywords.value[index]
  condition.join = condition.join === 'and' ? 'or' : 'and'
}

function toggleContextSearchDraftJoin() {
  contextSearchDraftJoin.value = contextSearchDraftJoin.value === 'and' ? 'or' : 'and'
}

function removeContextSearchKeyword(index) {
  contextSearchKeywords.value.splice(index, 1)
  activeContextSearchMatch.value = 0
  nextTick(scrollToCurrentContextSearchMatch)
}

function clearContextSearch() {
  contextSearchInput.value = ''
  contextSearchKeywords.value = []
  contextSearchDraftJoin.value = 'and'
  activeContextSearchMatch.value = 0
}

function resetContextSearch() {
  contextSearchInput.value = ''
  contextSearchKeywords.value = []
  contextSearchDraftJoin.value = 'and'
  activeContextSearchMatch.value = 0
}

function onContextSearchInputKeydown(event) {
  if (event.key === 'Enter' || event.key === ',' || event.key === '，') {
    event.preventDefault()
    addContextSearchKeywords()
    return
  }
  if (event.key === 'Backspace' && !contextSearchInput.value && contextSearchKeywords.value.length) {
    contextSearchKeywords.value.pop()
    activeContextSearchMatch.value = 0
    nextTick(scrollToCurrentContextSearchMatch)
  }
}

function jumpContextSearch(delta) {
  const total = contextSearchMatches.value.length
  if (!total) return
  activeContextSearchMatch.value = (activeContextSearchMatch.value + delta + total) % total
  nextTick(scrollToCurrentContextSearchMatch)
}

watch(contextSearchMatches, (matches) => {
  if (!matches.length) {
    activeContextSearchMatch.value = 0
    return
  }
  if (activeContextSearchMatch.value >= matches.length) {
    activeContextSearchMatch.value = matches.length - 1
  }
})

watch(
  () => contextSearchConditions.value.map(item => `${item.join}:${item.text}`).join('\n'),
  () => {
    activeContextSearchMatch.value = 0
    nextTick(scrollToCurrentContextSearchMatch)
  },
)

const filteredLogs = computed(() => {
  let list = logs.value
  // 前端 incidentOnly 过滤（已从后端拿全量，在前端二次过滤）
  if (incidentOnly.value) {
    list = list.filter(log => {
      const l = (log.line || '').toLowerCase()
      return /\berror\b|exception|fatal|panic|\bwarn\b/.test(l) ||
             INCIDENT_KEYWORDS.some(kw => l.includes(kw))
    })
  }
  // 本地多条件过滤：include 全部命中(AND)；任一 exclude 命中即剔除
  if (localKeywords.value.length) {
    const includes = localKeywords.value.filter(c => !c.exclude).map(c => c.text.toLowerCase())
    const excludes = localKeywords.value.filter(c =>  c.exclude).map(c => c.text.toLowerCase())
    list = list.filter(log => {
      const line = (log.line || '').toLowerCase()
      if (includes.length && !includes.every(t => line.includes(t))) return false
      if (excludes.length &&  excludes.some(t => line.includes(t))) return false
      return true
    })
  }
  return list
})

const levelStats = computed(() => {
  const stats = {}
  for (const log of filteredLogs.value) {
    const lvl = extractLevel(log.line)
    stats[lvl] = (stats[lvl] || 0) + 1
  }
  return stats
})

const loadedPodCount = computed(() => countLoadedPods(
  logs.value,
  logDistribution.value?.group_labels?.pod,
))

const logCoverageSummary = computed(() => {
  if (!logDistribution.value) return null
  return buildCoverageSummary({
    totalLogs: logDistribution.value.total_logs,
    loadedCount: totalLoaded.value,
    loadedPods: loadedPodCount.value,
    totalPods: logDistribution.value.total_pods,
    hasMore: hasMore.value,
  })
})

function drillIntoPod(item) {
  const namespaceLabel = logDistribution.value?.group_labels?.namespace || ''
  const podLabel = logDistribution.value?.group_labels?.pod || ''
  if (!podLabel || !item?.pod) return
  activeLabelFilters.value = replacePodFilters(activeLabelFilters.value, {
    namespaceLabel,
    namespace: item.namespace,
    podLabel,
    pod: item.pod,
  })
  selectedGroupLabel.value = podLabel
  selectedGroupValue.value = item.pod
  selectedLabelName.value = podLabel
  selectedLabelValue.value = item.pod
  groupBy.value = podLabel
  loadLogs()
}

function toggleIncident() {
  incidentOnly.value = !incidentOnly.value
}

function contextServiceName(log) {
  return log?.labels?.app || log?.labels?.job || selectedService.value || ''
}

function normalizeRequestError(error) {
  if (typeof error === 'string') return error
  if (Array.isArray(error)) {
    return error
      .map(item => item?.msg || item?.message || '')
      .filter(Boolean)
      .join('；') || '请求失败'
  }
  if (error?.detail) return normalizeRequestError(error.detail)
  return error?.message || '请求失败'
}

function closeDetail() {
  detailContextRequestId += 1
  detailContextAbort?.abort()
  detailContextAbort = null
  showDetailModal.value = false
  detailLog.value = null
  metaOpen.value = false   // 下次打开重新收起，焦点回到上下文
  loadingDetailContext.value = false
  loadingContextBefore.value = false
  loadingContextAfter.value = false
  detailContextLogs.value = []
  detailContextAnchorIndex.value = -1
  detailContextAnchorFound.value = true
  detailContextBeforeCount.value = 0
  detailContextAfterCount.value = 0
  detailContextError.value = ''
  contextWantedBefore.value = CONTEXT_INITIAL_BEFORE
  contextWantedAfter.value = CONTEXT_INITIAL_AFTER
  contextBeforeAtLimit.value = false
  contextAfterAtLimit.value = false
  contextScrollPending = null
  copiedContextLineKey.value = ''
  clearTimeout(copiedContextLineTimer)
  copiedContextLineTimer = null
  resetContextSearch()
}

/**
 * 加载上下文。统一入口：
 *   - opts.reset: true   重置 wanted before/after 至初始值（默认 false，保留扩展量）
 *   - opts.direction: 'before' | 'after' | null  滚动加载方向，用于保留滚动锚点
 */
async function loadLogContext(log = detailLog.value, opts = {}) {
  if (!log?.timestamp_ns) return

  if (opts.reset) {
    contextWantedBefore.value = CONTEXT_INITIAL_BEFORE
    contextWantedAfter.value = CONTEXT_INITIAL_AFTER
    contextBeforeAtLimit.value = false
    contextAfterAtLimit.value = false
  }

  const requestId = ++detailContextRequestId
  detailContextAbort?.abort()
  const controller = new AbortController()
  detailContextAbort = controller

  const direction = opts.direction || null
  if (!direction) loadingDetailContext.value = true
  if (direction === 'before') loadingContextBefore.value = true
  if (direction === 'after')  loadingContextAfter.value = true
  if (!direction) {
    // 乐观渲染：立即把 detailLog 放进 list 作为锚点，让用户秒看到自己点的那条
    // 不显示"正在加载上下文..."大块文字，后台异步补全前后日志后 merge
    detailContextLogs.value = log ? [{ ...log }] : []
    detailContextAnchorIndex.value = log ? 0 : -1
    detailContextAnchorFound.value = true
    detailContextBeforeCount.value = 0
    detailContextAfterCount.value = 0
    contextScrollPending = null
  }
  detailContextError.value = ''

  // 保留滚动锚点（用于"加载更早"时不让用户跳到顶部）
  const wrap = contextScrollWrap.value
  let savedScroll = null
  if (direction === 'before' && wrap) {
    savedScroll = { prevHeight: wrap.scrollHeight, prevTop: wrap.scrollTop }
  }

  const wantedBefore = Math.min(contextWantedBefore.value, CONTEXT_MAX_SIDE)
  const wantedAfter  = Math.min(contextWantedAfter.value, CONTEXT_MAX_SIDE)

  try {
    const result = await api.getLogContext({
      timestamp_ns: log.timestamp_ns,
      service: contextServiceName(log) || undefined,
      line_prefix: (log.line || '').slice(0, 200) || undefined,
      labels_json: JSON.stringify(log.labels || {}),
      before: wantedBefore,
      after: wantedAfter,
      ...timeParams(),
    }, { signal: controller.signal })

    if (requestId !== detailContextRequestId || detailLog.value !== log) return

    const prevBeforeCount = detailContextBeforeCount.value
    detailContextLogs.value = result.data || []
    detailContextAnchorIndex.value = result.anchor_index ?? -1
    detailContextAnchorFound.value = result.anchor_found !== false
    detailContextBeforeCount.value = result.before_count ?? 0
    detailContextAfterCount.value = result.after_count ?? 0
    // 后端降级兜底时带 error 说明：数据照常渲染，同时给出提示
    detailContextError.value = result.error || ''

    // 前端兜底：保证锚点 = 用户实际点击的那条
    //   1) 用 timestamp_ns + line 严格匹配查 anchor index
    //   2) 同 ts 但 line 不同 → 用 detailLog 覆盖那一行
    //   3) 完全找不到 → 按 ts 排序插入 detailLog 作为锚点行
    if (log?.timestamp_ns && detailContextLogs.value.length) {
      const targetTs   = String(log.timestamp_ns)
      const targetLine = log.line || ''

      let exact = detailContextLogs.value.findIndex(
        item => String(item.timestamp_ns) === targetTs && item.line === targetLine,
      )

      if (exact < 0) {
        // 同 ts 但 line 内容不同的位置：用 detailLog 替换那条
        const sameTsIdx = detailContextLogs.value.findIndex(
          item => String(item.timestamp_ns) === targetTs,
        )
        if (sameTsIdx >= 0) {
          detailContextLogs.value.splice(sameTsIdx, 1, { ...log })
          exact = sameTsIdx
        }
      }

      if (exact < 0) {
        // 完全没有同 ts 行 → 按时间戳升序插入
        const targetNum = Number(targetTs)
        let insertAt = detailContextLogs.value.findIndex(
          item => Number(item.timestamp_ns) > targetNum,
        )
        if (insertAt < 0) insertAt = detailContextLogs.value.length
        detailContextLogs.value.splice(insertAt, 0, { ...log })
        exact = insertAt
      }

      detailContextAnchorIndex.value = exact
      detailContextAnchorFound.value = true
    }

    // 判断该方向是否还能继续扩展：
    //  - 返回数 < 请求数 → 该方向已无更多日志
    //  - 已达后端 le=500 上限 → 不能再扩
    if (direction === 'before' || opts.reset || !direction) {
      contextBeforeAtLimit.value = (detailContextBeforeCount.value < wantedBefore) ||
                                   wantedBefore >= CONTEXT_MAX_SIDE
    }
    if (direction === 'after' || opts.reset || !direction) {
      contextAfterAtLimit.value = (detailContextAfterCount.value < wantedAfter) ||
                                  wantedAfter >= CONTEXT_MAX_SIDE
    }

    // 'before' 方向加载完后，把 scrollTop 补到新的同等"上方距离"，避免视野跳变
    if (direction === 'before' && wrap && savedScroll) {
      await nextTick()
      const addedHeight = wrap.scrollHeight - savedScroll.prevHeight
      wrap.scrollTop = savedScroll.prevTop + addedHeight
    }

    // 初始加载或刷新：自动滚到锚点居中
    if (!direction && detailContextAnchorIndex.value >= 0) {
      contextScrollPending = 'anchor'
      await nextTick()
      // 直接在 scroll 容器内查 .active 行，比函数式 ref 可靠
      // (setup script 模板里 ref 自动 unwrap，:ref="el => myRef = el" 写法不会回写)
      const anchor = contextScrollWrap.value?.querySelector('.drawer-context-item.active')
      if (anchor) anchor.scrollIntoView({ block: 'center', behavior: 'auto' })
    }
  } catch (error) {
    if (isCanceled(error)) return
    if (requestId !== detailContextRequestId || detailLog.value !== log) return
    if (!direction) detailContextError.value = normalizeRequestError(error)
  } finally {
    const shouldScrollAnchor = requestId === detailContextRequestId &&
                               !direction &&
                               contextScrollPending === 'anchor'
    if (requestId === detailContextRequestId) {
      if (!direction) loadingDetailContext.value = false
      if (direction === 'before') loadingContextBefore.value = false
      if (direction === 'after')  loadingContextAfter.value = false
    }
    if (detailContextAbort === controller) {
      detailContextAbort = null
    }
    if (shouldScrollAnchor) {
      await nextTick()
      if (requestId === detailContextRequestId && detailLog.value === log) {
        scrollContextAnchorIntoView()
        contextScrollPending = null
      }
    }
  }
}

function loadMoreContextBefore() {
  if (loadingDetailContext.value || loadingContextBefore.value) return
  if (contextBeforeAtLimit.value) return
  if (contextWantedBefore.value >= CONTEXT_MAX_SIDE) {
    contextBeforeAtLimit.value = true
    return
  }
  contextWantedBefore.value = nextContextCount(contextWantedBefore.value)
  loadLogContext(detailLog.value, { direction: 'before' })
}

function loadMoreContextAfter() {
  if (loadingDetailContext.value || loadingContextAfter.value) return
  if (contextAfterAtLimit.value) return
  if (contextWantedAfter.value >= CONTEXT_MAX_SIDE) {
    contextAfterAtLimit.value = true
    return
  }
  contextWantedAfter.value = nextContextCount(contextWantedAfter.value)
  loadLogContext(detailLog.value, { direction: 'after' })
}

function onContextScroll(event) {
  const t = event?.target
  if (!t) return
  if (loadingDetailContext.value) return
  // 距顶部 < 80px → 加载更早；距底部 < 80px → 加载更晚
  if (t.scrollTop < 80 && !loadingContextBefore.value) {
    loadMoreContextBefore()
  }
  const distBottom = t.scrollHeight - t.scrollTop - t.clientHeight
  if (distBottom < 80 && !loadingContextAfter.value) {
    loadMoreContextAfter()
  }
}

function openDetail(log) {
  resetContextSearch()
  detailLog.value = log
  showDetailModal.value = true
  loadLogContext(log, { reset: true })   // 切换日志时重置窗口
  nextTick(() => detailModalMask.value?.focus?.())
}

function onLogDetailKeydown(event) {
  if (event.key !== 'Escape' || !showDetailModal.value) return
  event.preventDefault()
  closeDetail()
}

function onLevelChange() {
  loadLogs()
}

function onLogScroll(event) {
  const target = event?.target
  if (!target || loadingLogs.value || loadingMore.value || !hasMore.value) return
  const remaining = target.scrollHeight - target.scrollTop - target.clientHeight
  if (remaining <= 160) {
    loadMore()
  }
}

async function ensureLogViewportFilled() {
  await nextTick()
  const el = logScrollWrap.value
  if (!el || loadingLogs.value || loadingMore.value || !hasMore.value) return
  const remaining = el.scrollHeight - el.scrollTop - el.clientHeight
  if (remaining <= 40) {
    loadMore()
  }
}

// ── 模板聚合 AI ───────────────────────────
function isCanceled(error) {
  return error?.name === 'CanceledError' ||
         error?.code === 'ERR_CANCELED' ||
         error === 'canceled' ||
         (typeof error === 'string' && error.toLowerCase() === 'canceled')
}

const tplAiContent  = ref('')
const analyzingTplAI = ref(false)

// ── 耗时追踪 Tab ──────────────────────────
const traceValue     = ref('')
const traceTimeMode  = ref('relative')   // 默认快速模式，避免空 custom 字段误导
const traceHours     = ref('24')
const traceStart     = ref('')
const traceEnd       = ref('')
const traceResult      = ref(null)
const traceLogs        = ref([])
const tracingKeyword   = ref(false)   // trace API 请求中
const loadingTraceLogs = ref(false)   // 日志列表加载中（独立状态）
const traceResultTab   = ref('overview')  // 结果子页签：overview | logs
const expandedSpans    = ref(new Set())   // 已展开的行索引

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const renderedAI = computed(() =>
  escapeHtml(aiContent.value)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
)
const renderedTplAI = computed(() =>
  escapeHtml(tplAiContent.value)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
)

function logClass(line) {
  const l = line.toLowerCase()
  if (/\berror\b|exception|fatal|panic/.test(l)) return 'level-error'
  if (/\bwarn(ing)?\b/.test(l))                  return 'level-warn'
  return ''
}

// ── 模板聚合 ─────────────────────────────
const templates        = ref([])
const loadingTemplates = ref(false)
const templateMeta     = ref({ total_logs: 0, total_templates: 0 })
const tplLevelFilter   = ref('')
const tplError         = ref('')

const maxTplCount = computed(() =>
  templates.value[0]?.count || 1
)
const totalTplLogs = computed(() =>
  templates.value.reduce((s, t) => s + t.count, 0) || 1
)
function tplBarW(cnt) {
  return Math.round(cnt / maxTplCount.value * 100)
}
function tplPct(cnt) {
  return (cnt / totalTplLogs.value * 100).toFixed(1)
}
function highlightWildcard(tpl) {
  return escapeHtml(tpl).replace(/&lt;\*&gt;/g, '<span class="wildcard">&lt;*&gt;</span>')
}

async function loadLabelCatalog() {
  loadingLabelCatalog.value = true
  try {
    const result = await api.getLogLabels()
    labelCatalog.value = result.data || []
    serviceLabelName.value = result.service_label
      || labelCatalog.value.find(item => item.role === 'service')?.name
      || ''
    const availableLabelNames = labelCatalog.value.map(item => item.name)
    recommendedDefaultLabelNames.value = resolveDefaultLabelNames(
      null,
      availableLabelNames,
      [result.default_group_by, result.service_label].filter(Boolean),
    )
    defaultLabelNames.value = resolveDefaultLabelNames(
      readSavedDefaultLabelNames(),
      availableLabelNames,
      recommendedDefaultLabelNames.value,
    )
    if (result.default_group_by) {
      groupBy.value = result.default_group_by
    }
    const preferredLabel = defaultLabelNames.value[0]
      || result.default_group_by
      || result.service_label
      || labelCatalog.value[0]?.name
      || ''
    if (preferredLabel) {
      selectedLabelName.value = preferredLabel
      selectedLabelValue.value = ''
      openLabelGroups.value = new Set([preferredLabel])
      await ensureLabelValues(preferredLabel)
    }
  } catch (error) {
    labelCatalog.value = []
    defaultLabelNames.value = []
    recommendedDefaultLabelNames.value = []
    openLabelGroups.value = new Set()
    selectedLabelName.value = ''
    selectedLabelValue.value = ''
  } finally {
    loadingLabelCatalog.value = false
  }
}

function labelRoleText(item) {
  if (item?.role === 'service') return '服务'
  if (item?.role === 'namespace') return '命名空间'
  if (item?.role === 'group') return '分组'
  return '标签'
}

function setLabelLoading(labelName, value) {
  loadingLabelValueMap.value = { ...loadingLabelValueMap.value, [labelName]: value }
}

async function ensureLabelValues(labelName) {
  if (!labelName || labelValueMap.value[labelName]) return
  setLabelLoading(labelName, true)
  try {
    const result = await api.getLogLabelValues(labelName, { limit: 80 })
    labelValueMap.value = { ...labelValueMap.value, [labelName]: result.data || [] }
    labelValueTotals.value = { ...labelValueTotals.value, [labelName]: result.total || 0 }
  } catch (error) {
    labelValueMap.value = { ...labelValueMap.value, [labelName]: [] }
    labelValueTotals.value = { ...labelValueTotals.value, [labelName]: 0 }
  } finally {
    setLabelLoading(labelName, false)
  }
}

async function toggleLabelGroup(labelName) {
  if (!labelName) return
  const next = new Set(openLabelGroups.value)
  if (next.has(labelName)) {
    next.delete(labelName)
  } else {
    next.add(labelName)
    ensureLabelValues(labelName)
  }
  openLabelGroups.value = next
}

async function onLabelDropdownChange() {
  selectedLabelValue.value = ''
  if (selectedLabelName.value) {
    await ensureLabelValues(selectedLabelName.value)
  }
}

function onLabelValueDropdownChange() {
  if (selectedLabelName.value && selectedLabelValue.value) {
    applyLabelFilter(selectedLabelName.value, selectedLabelValue.value)
  }
}

function isSelectedLabelFilter(labelName, value) {
  return selectedGroupLabel.value === labelName && selectedGroupValue.value === value
}

function refreshActiveData() {
  if (activeTab.value === 'logs') {
    loadLogs()
  } else if (activeTab.value === 'templates') {
    loadTemplates()
  }
}

function applyLabelFilter(labelName, value) {
  // 兼容旧调用：直接以一条 chip 的形式生效
  selectedLabelName.value = labelName
  selectedLabelValue.value = value
  labelNameQuery.value = labelName
  labelValueQuery.value = String(value ?? '')
  showLabelNameDropdown.value = false
  showLabelValueDropdown.value = false
  addActiveLabel(labelName, value, { skipRefresh: false })
}

function addActiveLabel(labelName, value, opts = {}) {
  if (!labelName || value === '' || value == null) return
  const val = String(value)
  const list = activeLabelFilters.value
  // 同 label+value 才去重；同 label 不同 value 累加（生成 label=~"a|b|c" regex）
  if (list.some(x => x.label === labelName && x.value === val)) {
    if (!opts.silent) {
      labelValueQuery.value = ''
      selectedLabelValue.value = ''
      showLabelValueDropdown.value = false
    }
    return
  }
  list.push({ label: labelName, value: val })
  // 单条 groupBy 联动（保持原有分组统计能力）
  selectedGroupLabel.value = labelName
  selectedGroupValue.value = val
  if (groupBy.value !== labelName) groupBy.value = labelName
  if (!opts.silent) {
    showLabelNameDropdown.value = false
    showLabelValueDropdown.value = false
    labelValueQuery.value = ''
    selectedLabelValue.value = ''
  }
  if (!opts.skipRefresh) refreshActiveData()
}

// 批量：若有勾选值，用勾选值集合；否则回退到单值 selectedLabelValue
function addActiveLabelBatch() {
  if (!selectedLabelName.value) return
  const list = pickedLabelValues.value.length
    ? [...pickedLabelValues.value]
    : (selectedLabelValue.value ? [selectedLabelValue.value] : [])
  if (!list.length) return
  list.forEach((v, i) => {
    addActiveLabel(selectedLabelName.value, v, {
      silent: true,
      skipRefresh: i < list.length - 1,
    })
  })
  // 一轮结束后清空勾选缓冲 + 关下拉
  pickedLabelValues.value = []
  showLabelValueDropdown.value = false
  labelValueQuery.value = ''
  selectedLabelValue.value = ''
}

function removeActiveLabel(idx) {
  activeLabelFilters.value.splice(idx, 1)
  if (activeLabelFilters.value.length) {
    const last = activeLabelFilters.value[activeLabelFilters.value.length - 1]
    selectedGroupLabel.value = last.label
    selectedGroupValue.value = last.value
  } else {
    selectedGroupLabel.value = ''
    selectedGroupValue.value = ''
  }
  refreshActiveData()
}

function clearAllActiveLabels() {
  activeLabelFilters.value = []
  selectedGroupLabel.value = ''
  selectedGroupValue.value = ''
  refreshActiveData()
}

function clearLabelFilter() {
  clearAllActiveLabels()
}

async function loadLogs() {
  const requestId = ++logsRequestId
  logsAbort?.abort()
  loadMoreAbort?.abort()
  logDistributionAbort?.abort()
  const controller = new AbortController()
  logsAbort = controller
  loadingLogs.value = true
  logs.value = []
  hasMore.value = false
  nextCursorNs.value = null
  totalLoaded.value = 0
  logDistribution.value = null
  logDistributionError.value = ''
  try {
    const r = await api.getLogs({
      level:    levelFilter.value || undefined,
      limit:    200,
      ...multiFilterParams(),
      ...currentGroupParams(),
      ...timeParams(),
    }, { signal: controller.signal })
    if (requestId !== logsRequestId) return
    logs.value = r.data
    hasMore.value      = r.has_more ?? false
    nextCursorNs.value = r.next_cursor_ns ?? null
    totalLoaded.value  = r.data?.length ?? 0
    void loadLogDistribution(requestId, {
      start_ns: r.query_start_ns,
      end_ns: r.query_end_ns,
    })
    await ensureLogViewportFilled()
  } catch (error) {
    if (!isCanceled(error)) {
      logs.value = []
      hasMore.value = false
      nextCursorNs.value = null
      totalLoaded.value = 0
    }
  } finally {
    if (requestId === logsRequestId) {
      loadingLogs.value = false
    }
    if (logsAbort === controller) {
      logsAbort = null
    }
  }
}

async function loadMore() {
  if (!hasMore.value || !nextCursorNs.value || loadingMore.value) return
  const requestId = ++loadMoreRequestId
  const baseLogsRequestId = logsRequestId
  loadMoreAbort?.abort()
  const controller = new AbortController()
  loadMoreAbort = controller
  loadingMore.value = true
  try {
    const r = await api.getLogs({
      level:      levelFilter.value || undefined,
      limit:      200,
      cursor_ns:  nextCursorNs.value,
      ...multiFilterParams(),
      ...currentGroupParams(),
      ...timeParams(),
    }, { signal: controller.signal })
    if (requestId !== loadMoreRequestId || baseLogsRequestId !== logsRequestId) return
    logs.value = [...logs.value, ...(r.data || [])]
    hasMore.value      = r.has_more ?? false
    nextCursorNs.value = r.next_cursor_ns ?? null
    totalLoaded.value  = logs.value.length
    await ensureLogViewportFilled()
  } catch (error) {
    if (!isCanceled(error)) {
      hasMore.value = false
    }
  } finally {
    if (requestId === loadMoreRequestId) {
      loadingMore.value = false
    }
    if (loadMoreAbort === controller) {
      loadMoreAbort = null
    }
  }
}

async function loadTemplates() {
  const requestId = ++templatesRequestId
  templatesAbort?.abort()
  const controller = new AbortController()
  templatesAbort = controller
  loadingTemplates.value = true
  templates.value = []
  tplError.value = ''
  try {
    const r = await api.getTemplates({
      limit:    10000,
      top_n:    100,
      level:    tplLevelFilter.value || undefined,
      ...multiFilterParams(),
      ...currentGroupParams(),
      ...timeParams(),
    }, { signal: controller.signal })
    if (requestId !== templatesRequestId) return
    templates.value = r.data
    templateMeta.value = { total_logs: r.total_logs, total_templates: r.total_templates }
  } catch (error) {
    if (isCanceled(error)) return
    tplError.value = typeof error === 'string' ? error : (error?.message || '聚类请求失败，请检查后端连接')
  } finally {
    if (requestId === templatesRequestId) {
      loadingTemplates.value = false
    }
    if (templatesAbort === controller) {
      templatesAbort = null
    }
  }
}

function onParamChange() {
  if (activeTab.value === 'logs')      loadLogs()
  else                                 loadTemplates()
}

function onTimeModeChange() {
  if (timeMode.value === 'relative') {
    customStart.value = ''
    customEnd.value   = ''
    tsPasteInput.value = ''
    tsPasteError.value = ''
    customTimeError.value = ''
    tsCenter.value = null
    appliedCustomTimeKey = ''
    onParamChange()
  } else {
    const r = recentFiveMinuteRange()
    if (!customStart.value) customStart.value = r.start
    if (!customEnd.value)   customEnd.value   = r.end
    onCustomTimeChange()
  }
}

async function loadLogDistribution(baseLogsRequestId = logsRequestId, windowBounds = {}) {
  const requestId = ++logDistributionRequestId
  logDistributionAbort?.abort()
  const controller = new AbortController()
  logDistributionAbort = controller
  loadingLogDistribution.value = true
  logDistributionError.value = ''
  try {
    const r = await api.getLogPodDistribution({
      level: levelFilter.value || undefined,
      top_n: 20,
      ...multiFilterParams(),
      ...currentGroupParams(),
      ...timeParams(),
      ...windowBounds,
    }, { signal: controller.signal })
    if (requestId !== logDistributionRequestId || baseLogsRequestId !== logsRequestId) return
    logDistribution.value = r
  } catch (error) {
    if (!isCanceled(error) && requestId === logDistributionRequestId) {
      logDistributionError.value = typeof error === 'string' ? error : (error?.message || 'Pod 分布统计失败')
    }
  } finally {
    if (requestId === logDistributionRequestId) loadingLogDistribution.value = false
    if (logDistributionAbort === controller) logDistributionAbort = null
  }
}

function parseCustomTimeInput(raw) {
  const value = String(raw || '').trim()
  if (!value) return null
  const hasDateAndTime = /\d{4}[-/]\d{1,2}[-/]\d{1,2}[\sT]+\d{1,2}:\d{2}/.test(value)
  const isEpoch = /^\d{10,19}$/.test(value)
  return hasDateAndTime || isEpoch ? parseFlexibleTime(value) : null
}

function validateCustomTimeRange() {
  if (!customStart.value || !customEnd.value) {
    customTimeError.value = '请填写完整的开始时间和结束时间'
    return null
  }

  const start = parseCustomTimeInput(customStart.value)
  if (!start) {
    customTimeError.value = '开始时间格式无效，请输入 YYYY-MM-DD HH:mm:ss'
    return null
  }
  const end = parseCustomTimeInput(customEnd.value)
  if (!end) {
    customTimeError.value = '结束时间格式无效，请输入 YYYY-MM-DD HH:mm:ss'
    return null
  }
  if (end < start) {
    customTimeError.value = '结束时间不能早于开始时间'
    return null
  }

  customStart.value = fmtDateTimeSec(start)
  customEnd.value = fmtDateTimeSec(end)
  customTimeError.value = ''
  return { start, end }
}

function onCustomTimeFieldPaste(field, event) {
  const text = event?.clipboardData?.getData('text')
  if (text == null) return
  event.preventDefault()
  if (field === 'start') customStart.value = text.trim()
  else customEnd.value = text.trim()
  nextTick(onCustomTimeFieldCommit)
}

function onCustomTimeFieldCommit() {
  applyCustomTimeRangeIfChanged()
}

function onCustomTimeChange() {
  applyCustomTimeRangeIfChanged()
}

function applyCustomTimeRangeIfChanged() {
  if (!validateCustomTimeRange()) return
  const key = `${customStart.value}|${customEnd.value}`
  if (key === appliedCustomTimeKey) return
  appliedCustomTimeKey = key
  onParamChange()
}

function onKeywordInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(onParamChange, 500)
}

function clearKeyword() {
  keyword.value = ''
  onParamChange()
}

function traceTimeParams() {
  if (traceTimeMode.value === 'custom' && traceStart.value && traceEnd.value) {
    if (traceEnd.value < traceStart.value) {
      alert('结束时间不能早于开始时间')
      throw new Error('invalid time range')
    }
    // 本地时间 → UTC，避免服务端按 UTC 错误解析
    return { start_time: toUtcStr(traceStart.value), end_time: toUtcStr(traceEnd.value) }
  }
  return { hours: traceHours.value }
}

async function runTrace() {
  if (!traceValue.value) return

  // 验证自定义时间范围
  if (traceTimeMode.value === 'custom' && (!traceStart.value || !traceEnd.value)) {
    alert('请填写完整的开始时间和结束时间')
    return
  }

  tracingKeyword.value = true
  loadingTraceLogs.value = false
  traceResult.value = null
  traceLogs.value = []
  traceResultTab.value = 'overview'
  expandedSpans.value = new Set()

  let tp
  try { tp = traceTimeParams() } catch { tracingKeyword.value = false; return }

  // ── 第一步：计算首末耗时 ──────────────────
  let traceData = null
  try {
    traceData = await api.traceKeyword({
      keyword: traceValue.value,
      service: selectedService.value || undefined,
      ...currentGroupParams(),
      ...tp,
    })
    traceResult.value = traceData
  } catch (e) {
    traceResult.value = { found: false, keyword: traceValue.value, log_count: 0, _error: String(e) }
    tracingKeyword.value = false
    return
  }
  tracingKeyword.value = false   // 耗时计算完成，立即解除主加载状态

  // ── 第二步：加载匹配日志列表（独立加载，不影响结果展示）──
  if (traceData.found) {
    traceLogsAbort?.abort()
    const controller = new AbortController()
    traceLogsAbort = controller
    loadingTraceLogs.value = true
    try {
      const logsR = await api.getLogs({
        keyword: traceValue.value,
        service: selectedService.value || undefined,
        limit: 2000,
        ...currentGroupParams(),
        ...tp,
      }, { signal: controller.signal })
      traceLogs.value = [...(logsR.data || [])].reverse()  // 升序展示
    } catch (error) {
      if (isCanceled(error)) return
      traceLogs.value = []  // 日志列表加载失败不影响耗时结果
    } finally {
      loadingTraceLogs.value = false
      if (traceLogsAbort === controller) {
        traceLogsAbort = null
      }
    }
  }
}

function switchTraceToCustom() {
  traceTimeMode.value = 'custom'
  const r = recentFiveMinuteRange(toLocalInput)
  if (!traceStart.value) traceStart.value = r.start
  if (!traceEnd.value)   traceEnd.value   = r.end
}

function toggleSpan(i) {
  const s = new Set(expandedSpans.value)
  s.has(i) ? s.delete(i) : s.add(i)
  expandedSpans.value = s
}

function spanElapsed(log) {
  const firstNs = traceResult.value?.first_ts_ns
  if (!firstNs) return ''
  const ms = (parseInt(log.timestamp_ns) - firstNs) / 1_000_000
  if (ms <= 0) return '+0'
  if (ms < 1)       return `+${(ms * 1000).toFixed(0)} µs`
  if (ms < 1000)    return `+${ms.toFixed(1)} ms`
  if (ms < 60000)   return `+${(ms / 1000).toFixed(3)} s`
  return `+${Math.floor(ms / 60000)}m ${((ms % 60000) / 1000).toFixed(1)}s`
}

function spanBarW(log) {
  const firstNs = traceResult.value?.first_ts_ns
  const totalMs = traceResult.value?.duration_ms
  if (!firstNs || !totalMs) return 0
  const ms = (parseInt(log.timestamp_ns) - firstNs) / 1_000_000
  return Math.min(100, Math.max(0, (ms / totalMs) * 100))
}

function startTplAIAnalysis() {
  if (analyzingTplAI.value) return
  tplAiContent.value = ''
  analyzingTplAI.value = true
  const params = new URLSearchParams({
    ...multiFilterParams(),
    ...(tplLevelFilter.value ? { level: tplLevelFilter.value } : {}),
    ...currentGroupParams(),
  })
  if (timeMode.value === 'custom' && customStart.value && customEnd.value) {
    params.set('start_time', toUtcStr(customStart.value))
    params.set('end_time',   toUtcStr(customEnd.value))
  } else {
    params.set('hours', hours.value)
  }
  streamSSE(
    `/api/analyze/templates/stream?${params}`,
    chunk => { try { tplAiContent.value += JSON.parse(chunk) } catch { tplAiContent.value += chunk } },
    () => { analyzingTplAI.value = false },
    () => { analyzingTplAI.value = false },
  )
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'templates' && !templates.value.length) loadTemplates()
  // trace tab 不自动加载，等用户输入后手动触发
}

function startAIAnalysis() {
  aiContent.value = ''
  analyzingAI.value = true
  const params = new URLSearchParams({
    ...timeParams(),
    ...multiFilterParams(),
    ...(levelFilter.value ? { level: levelFilter.value } : {}),
    ...currentGroupParams(),
  })
  streamSSE(
    `/api/analyze/stream?${params}`,
    (chunk) => { try { aiContent.value += JSON.parse(chunk) } catch { aiContent.value += chunk } },
    () => { analyzingAI.value = false },
    () => { analyzingAI.value = false },
  )
}

// 钻取入口：从 URL ?service=&level=&hours=&q= 预填查询条件（指标→日志）
function _applyRouteQuery() {
  const params = (typeof window !== 'undefined' && window.location.hash.includes('?'))
    ? new URLSearchParams(window.location.hash.split('?')[1])
    : new URLSearchParams()
  const q = Object.fromEntries(params)
  if (q.service) selectedService.value = q.service
  if (q.level)   levelFilter.value = q.level
  if (q.hours) {
    hours.value = String(q.hours)
    timeMode.value = 'relative'
    customStart.value = ''
    customEnd.value = ''
  }
  if (q.q)       keyword.value = q.q
  applyRouteLabelFilters(params)
}

// 钻取联动：URL 带 service 进入时，标签面板默认展示该服务的标签上下文——
// 展开 Loki 标签面板、标签名选中服务标签并加载值列表；若服务名确认是该
// 标签的值，则直接转成可见的筛选 chip（app=服务），日志分组显示随之联动，
// 并移除重复的服务 chip 避免同条件二次 AND。
async function _applyServiceDrilldown() {
  const svc = selectedService.value || selectedServices.value[0] || ''
  if (!svc) return
  const serviceLabel = serviceLabelName.value || 'app'

  labelExplorerOpen.value = true
  selectedLabelName.value = serviceLabel
  labelNameQuery.value = serviceLabel
  await ensureLabelValues(serviceLabel)

  const values = labelValueMap.value[serviceLabel] || []
  if (values.includes(svc)) {
    addActiveLabel(serviceLabel, svc, { silent: true, skipRefresh: true })
    selectedServices.value = selectedServices.value.filter(s => s !== svc)
    if (selectedService.value === svc) selectedService.value = ''
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onLogDetailKeydown)
  _applyRouteQuery()
  // 已有 URL ?service=xxx 兼容进 chip
  if (selectedService.value && !selectedServices.value.length) {
    selectedServices.value.push(selectedService.value)
  }
  // 日志是首屏主内容：立即发起，不再串行等待标签目录和错误统计。
  loadLogs()
  const catalogPromise = loadLabelCatalog()
  const servicesPromise = api.getServices({ with_errors: false }).catch(() => null)

  await catalogPromise
  await _applyServiceDrilldown()
  // 服务名只走快速路径，不在首屏计算全量错误数。
  try {
    const r = await servicesPromise
    const data = r?.data ?? r
    if (Array.isArray(data)) {
      allServicesList.value = data.map(s => typeof s === 'string' ? s : (s.name || s.service || '')).filter(Boolean)
    }
  } catch {}
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onLogDetailKeydown)
  clearTimeout(searchTimer)
  logsAbort?.abort()
  loadMoreAbort?.abort()
  logDistributionAbort?.abort()
  templatesAbort?.abort()
  traceLogsAbort?.abort()
  detailContextAbort?.abort()
  clearTimeout(copiedContextLineTimer)
})
</script>

<style scoped>
.log-layout { display: flex; height: 100%; overflow: hidden; }

/* 左侧服务面板 */
.service-panel {
  width: 340px; min-width: 320px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
.panel-header { padding: 12px 12px 10px; border-bottom: 1px solid var(--border); }
.panel-title {
  display: block; font-size: 12px; font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.time-select {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 5px 8px; border-radius: 5px; font-size: 12px; cursor: pointer;
}
/* 时间模式切换 */
.time-mode-tabs {
  display: flex; margin-bottom: 6px;
  background: var(--bg-base); border-radius: 5px; padding: 2px;
}
.tmode-btn {
  flex: 1; padding: 3px 0; font-size: 11px; border: none;
  background: transparent; color: var(--text-muted);
  border-radius: 4px; cursor: pointer; transition: all .12s;
}
.tmode-btn.active { background: var(--bg-active); color: var(--text-primary); }

/* 自定义时间输入 */
.custom-time-wrap {
  display: flex; flex-direction: column; gap: 4px; margin-top: 2px;
}
.dt-input {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 4px 6px; border-radius: 5px; font-size: 11px;
}
.custom-time-text {
  min-width: 0;
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}
.custom-time-text:focus {
  border-color: var(--accent);
  outline: 2px solid var(--accent-dim, rgba(217,119,87,.12));
  outline-offset: 0;
}
.dt-sep {
  text-align: center; font-size: 10px; color: var(--text-muted); line-height: 1;
}
/* 时间戳快速粘贴 */
.ts-paste-row { display: flex; gap: 4px; }
.ts-paste { flex: 1; min-width: 0; }
.ts-apply-btn {
  flex-shrink: 0; padding: 4px 8px; font-size: 11px;
  border: 1px solid var(--accent); border-radius: 5px;
  background: var(--accent-dim, rgba(217,119,87,.12)); color: var(--accent);
  cursor: pointer; white-space: nowrap;
}
.ts-apply-btn:hover { background: var(--accent); color: #fff; }
.ts-paste-err { font-size: 10px; color: var(--error, #d63031); }
.ts-range-chips {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  padding: 4px 0 2px;
}
.ts-range-label { font-size: 10px; color: var(--text-muted); margin-right: 2px; }
.ts-range-chip {
  padding: 2px 7px; font-size: 10px; border: 1px solid var(--border);
  border-radius: 10px; background: var(--bg-hover); color: var(--text-secondary);
  cursor: pointer; transition: all .12s;
}
.ts-range-chip:hover { border-color: var(--accent); color: var(--accent); }
.ts-range-chip.active { background: var(--accent); border-color: var(--accent); color: #fff; }
.custom-time-inputs { display: flex; flex-direction: column; gap: 4px; margin-top: 2px; }
.label-explorer {
  background: var(--bg-card);
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.label-explorer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
  cursor: pointer;
}
.label-explorer-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.label-explorer-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.label-default-settings-btn {
  border: 1px solid var(--border);
  border-radius: 5px;
  background: transparent;
  color: var(--text-muted);
  padding: 2px 7px;
  font-size: 10px;
  cursor: pointer;
}
.label-default-settings-btn:hover,
.label-default-settings-btn.active {
  border-color: var(--accent);
  color: var(--accent-hover);
  background: rgba(99,102,241,.08);
}
.label-explorer-toggle {
  font-size: 11px;
  color: var(--text-muted);
}
.label-explorer-body {
  padding: 0 12px 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.label-default-settings {
  margin-bottom: 8px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-base);
}
.label-default-settings-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 7px;
  color: var(--text-secondary);
  font-size: 11px;
}
.label-default-settings-head button,
.label-default-done {
  border: none;
  background: transparent;
  color: var(--accent-hover);
  font-size: 10px;
  cursor: pointer;
}
.label-default-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 5px 8px;
  max-height: 170px;
  overflow-y: auto;
}
.label-default-option {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
}
.label-default-option input { accent-color: var(--accent); }
.label-default-option span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.label-default-option em {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 9px;
  font-style: normal;
}
.label-default-done {
  display: block;
  margin: 7px 0 0 auto;
  padding: 2px 6px;
}
.label-default-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-bottom: 7px;
}
.label-default-strip-title {
  color: var(--text-muted);
  font-size: 10px;
}
.label-default-chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--bg-base);
  color: var(--text-secondary);
  padding: 3px 8px;
  font-size: 10px;
  cursor: pointer;
}
.label-default-chip:hover,
.label-default-chip.active {
  border-color: var(--accent);
  background: var(--accent-dim);
  color: var(--accent-hover);
}
.label-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.label-chip {
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-secondary);
  border-radius: 9999px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
  max-width: 100%;
}
.label-chip:hover {
  border-color: var(--border-accent);
  color: var(--text-primary);
}
.label-chip.active {
  background: var(--accent-dim);
  border-color: var(--border-accent);
  color: var(--accent);
}
.label-chip.groupable::after {
  content: ' *';
  opacity: .7;
}
.active-label-filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding: 6px 8px;
  border: 1px solid rgba(99,102,241,.35);
  border-radius: 8px;
  background: rgba(99,102,241,.1);
  color: var(--text-secondary);
  font-size: 11px;
}
.active-label-filter em {
  color: var(--accent-hover);
  font-style: normal;
  word-break: break-all;
}
.active-label-filter button {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  font-size: 11px;
}
.label-dropdown-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.label-select-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 11px;
  color: var(--text-muted);
}
.label-select-field select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-base);
  color: var(--text-primary);
  padding: 7px 8px;
  font-size: 12px;
}
.label-dropdown-apply {
  border: 1px solid var(--border-accent);
  border-radius: 7px;
  background: var(--accent-dim);
  color: var(--accent);
  padding: 7px 8px;
  cursor: pointer;
  font-size: 12px;
}
.label-dropdown-apply:disabled {
  opacity: .5;
  cursor: not-allowed;
}

/* 可搜索下拉 combobox */
.combo {
  position: relative;
  display: flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-base);
  transition: border-color .12s, box-shadow .12s;
}
.combo.open { border-color: var(--accent, #818cf8); box-shadow: 0 0 0 2px rgba(129,140,248,.15); }
.combo.disabled { opacity: .5; pointer-events: none; }
.combo-input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  padding: 7px 8px;
  font-size: 12px;
  outline: none;
}
.combo-input::placeholder { color: var(--text-muted); }
.combo-clear, .combo-caret {
  padding: 0 6px;
  font-size: 11px;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
  transition: color .12s;
}
.combo-clear:hover, .combo-caret:hover { color: var(--text-primary); }
.combo-caret { padding-right: 8px; font-size: 10px; }
.combo-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0; right: 0;
  z-index: 20;
  max-height: 260px;
  overflow-y: auto;
  background: var(--bg-card, #1a1a1a);
  border: 1px solid var(--border);
  border-radius: 7px;
  box-shadow: 0 4px 16px rgba(0,0,0,.28);
  padding: 4px;
}
.combo-item {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background .1s;
}
.combo-item:hover { background: var(--bg-hover, rgba(255,255,255,.06)); }
.combo-item.active {
  background: rgba(129,140,248,.14);
  color: var(--accent, #818cf8);
}
.combo-item-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.combo-item-text mark {
  background: transparent;
  color: inherit;
  padding: 0;
}
.combo-item-text mark.hl {
  background: rgba(129,140,248,.28);
  color: #fff;
  font-weight: 600;
  border-radius: 2px;
  padding: 0 1px;
}
.combo-item-meta {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-muted);
  opacity: .8;
}

/* 勾选式多选：每行前的复选圆点 + 头部提示条 */
.combo-multi-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  margin-bottom: 2px;
  font-size: 10px;
  color: var(--text-muted);
  border-bottom: 1px dashed var(--border);
}
.combo-multi-hint em {
  color: var(--accent, #818cf8);
  font-style: normal;
  font-weight: 600;
  padding: 0 2px;
}
.combo-multi-clear {
  background: transparent;
  border: 0;
  font-size: 10px;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
}
.combo-multi-clear:hover { color: var(--error, #f85149); }
.combo-item-multi { gap: 8px; }
.combo-check {
  display: inline-flex;
  align-items: center; justify-content: center;
  width: 14px; height: 14px;
  border: 1.5px solid var(--border);
  border-radius: 3px;
  color: transparent;
  flex-shrink: 0;
  transition: background .12s, border-color .12s, color .12s;
}
.combo-check.on {
  background: var(--accent, #818cf8);
  border-color: var(--accent, #818cf8);
  color: #fff;
}
.combo-item.picked {
  background: rgba(129,140,248,.10);
  color: var(--accent, #818cf8);
}

/* 点即加：已加值行的视觉反馈（更淡的紫底 + ✓已加 徽标） */
.combo-item.chipped {
  background: rgba(129,140,248,.08);
}
.combo-item.chipped .combo-item-meta {
  color: var(--accent, #818cf8);
  font-weight: 600;
  opacity: 1;
}
.quick-hint {
  color: #38bdf8;
  border-color: rgba(56,189,248,.35);
}
.hint-inline {
  font-style: normal;
  font-size: 10px;
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 6px;
}
.label-flow-tip {
  font-size: 11px;
  color: var(--text-muted);
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(129,140,248,.06);
  border: 1px dashed rgba(129,140,248,.28);
}
.combo-empty {
  position: absolute;
  top: calc(100% + 4px);
  left: 0; right: 0;
  z-index: 20;
  padding: 12px 10px;
  background: var(--bg-card, #1a1a1a);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}

/* 多标签条件 chip 列表（已加的过滤条件） */
.active-label-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px;
  margin-bottom: 6px;
  background: var(--bg-hover, rgba(255,255,255,.03));
  border: 1px dashed var(--border);
  border-radius: 7px;
}
.active-label-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 7px;
  border-radius: 999px;
  background: rgba(129,140,248,.14);
  border: 1px solid rgba(129,140,248,.36);
  color: var(--accent, #818cf8);
  font-size: 11px;
  font-family: 'Cascadia Code','Consolas',monospace;
  line-height: 1.4;
}
.active-label-chip .chip-key { font-weight: 600; }
.active-label-chip .chip-eq  { opacity: .6; }
.active-label-chip .chip-val { color: var(--text-primary); }
.active-label-chip .chip-remove {
  margin-left: 3px;
  padding: 0 3px;
  font-size: 10px;
  opacity: .55;
  cursor: pointer;
}
.active-label-chip .chip-remove:hover { opacity: 1; }
.active-label-clear {
  background: transparent;
  border: 0;
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  margin-left: auto;
}
.active-label-clear:hover { color: var(--error, #f85149); }
.label-group-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}
.label-group-card {
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-base);
  overflow: hidden;
}
.label-group-card.active {
  border-color: rgba(99,102,241,.45);
}
.label-group-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  padding: 7px 8px;
  cursor: pointer;
  text-align: left;
}
.label-group-header:hover {
  background: var(--bg-hover);
}
.label-group-main {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.label-group-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono, 'Consolas', monospace);
  font-size: 11.5px;
  color: var(--text-primary);
}
.label-group-role {
  flex-shrink: 0;
  border-radius: 9999px;
  background: var(--bg-hover);
  color: var(--text-muted);
  padding: 1px 6px;
  font-size: 10px;
}
.label-group-card.groupable .label-group-role {
  color: var(--accent);
  background: rgba(99,102,241,.13);
}
.label-group-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}
.label-total {
  min-width: 18px;
  text-align: right;
}
.label-values-card {
  padding: 0 8px 8px;
  background: transparent;
  border: 0;
}
.label-values-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.label-values-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}
.label-values-meta {
  font-size: 11px;
  color: var(--text-muted);
}
.label-values-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.label-value-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  border: 1px solid var(--border);
  padding: 3px 8px;
  border-radius: 9999px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  font-size: 11px;
  word-break: break-all;
  cursor: pointer;
}
.label-value-chip:hover,
.label-value-chip.active {
  border-color: var(--border-accent);
  color: var(--accent);
  background: var(--accent-dim);
}
.label-empty {
  font-size: 11px;
  color: var(--text-muted);
  padding: 4px 0;
}
.label-loading {
  padding: 8px 0;
}

/* 关键字搜索框 */
.keyword-wrap {
  display: flex; align-items: center;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px; padding: 0 8px; gap: 5px;
  min-width: 160px; max-width: 240px;
}
.kw-icon { font-size: 12px; flex-shrink: 0; }
.kw-input {
  flex: 1; background: transparent; border: none;
  color: var(--text-primary); font-size: 12px;
  padding: 5px 0; outline: none;
}
.kw-input::placeholder { color: var(--text-muted); }
.kw-clear {
  background: none; border: none; color: var(--text-muted);
  font-size: 11px; cursor: pointer; padding: 2px;
  line-height: 1; flex-shrink: 0;
}
.kw-clear:hover { color: var(--text-primary); }

/* 二次本地过滤框：次要色调，与服务端 keyword 视觉区分 */
.keyword-wrap.secondary {
  border-color: rgba(99,102,241,.35);
  background: rgba(99,102,241,.06);
  min-width: 150px; max-width: 200px;
}
.keyword-wrap.secondary .kw-icon { color: var(--accent, #818cf8); }

/* 多条件本地过滤 */
.multi-filter-wrap {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  padding: 3px 6px;
  border: 1px solid rgba(99,102,241,.35);
  background: rgba(99,102,241,.06);
  border-radius: 6px;
  min-width: 220px;
  max-width: 460px;
}
.multi-filter-wrap .kw-icon { color: var(--accent, #818cf8); flex-shrink: 0; margin-right: 2px; }
.multi-filter-wrap .multi-input {
  flex: 1;
  min-width: 90px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 12px;
  padding: 4px 0;
  outline: none;
}
.multi-filter-wrap .multi-input::placeholder { color: var(--text-muted); }

.filter-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-family: monospace;
  cursor: pointer;
  border: 1px solid transparent;
  white-space: nowrap;
  user-select: none;
  transition: background .12s, border-color .12s;
}
.filter-chip.include {
  background: rgba(63,185,80,.15);
  border-color: rgba(63,185,80,.35);
  color: #3fb950;
}
.filter-chip.exclude {
  background: rgba(248,81,73,.15);
  border-color: rgba(248,81,73,.35);
  color: var(--error, #f85149);
  text-decoration: line-through;
}
.filter-chip:hover { filter: brightness(1.15); }
.chip-prefix { font-weight: 700; opacity: .8; }
.chip-text { font-weight: 500; }
.chip-remove {
  margin-left: 2px;
  padding: 0 2px;
  font-size: 10px;
  opacity: .6;
  cursor: pointer;
}
.chip-remove:hover { opacity: 1; }

/* 服务多选 chip 蓝色系，与关键字 chip 区分 */
.multi-filter-wrap.svc-multi .kw-icon { color: #38bdf8; }
.filter-chip.svc-chip {
  background: rgba(56,189,248,.14);
  border: 1px solid rgba(56,189,248,.36);
  color: #38bdf8;
}
.filter-chip.svc-chip .chip-prefix { color: #38bdf8; }

/* AND / OR 切换 pill */
.kw-mode-switch {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
  margin-right: 4px;
  flex-shrink: 0;
}
.kw-mode-btn {
  background: transparent;
  color: var(--text-muted);
  border: 0;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background .12s, color .12s;
}
.kw-mode-btn:hover { color: var(--text-primary); }
.kw-mode-btn.active {
  background: var(--accent, #818cf8);
  color: #fff;
}

.svc-ns-arrow { font-size: 8px; transition: transform .2s; display: inline-block; }
.svc-ns-arrow.open { transform: rotate(90deg); }
.loading-row { display: flex; justify-content: center; padding: 12px; }

/* 右侧 */
.log-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* 工具栏 */
.log-toolbar {
  padding: 8px 14px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  justify-content: space-between; gap: 12px;
  flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }

/* Tab */
.tab-group { display: flex; gap: 2px; background: var(--bg-base); padding: 3px; border-radius: 8px; }
.tab-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 14px; border-radius: 6px;
  border: none; background: transparent;
  color: var(--text-muted); font-size: 13px;
  cursor: pointer; transition: all .15s;
}
.tab-btn:hover  { color: var(--text-primary); }
.tab-btn.active { background: var(--bg-active); color: var(--text-primary); }
.tab-count {
  background: var(--bg-hover);
  color: var(--text-muted);
  font-size: 11px; padding: 0 6px;
  border-radius: 9999px; font-weight: 600;
}
.tab-btn.active .tab-count { background: var(--accent-dim); color: var(--accent); }
.meta-info { font-size: 12px; color: var(--text-muted); }

/* AI 面板 */
.ai-panel {
  margin: 10px 14px; padding: 14px 16px;
  background: rgba(99,102,241,.07);
  border: 1px solid rgba(99,102,241,.25);
  border-radius: var(--radius);
  flex-shrink: 0;
}
.ai-panel-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; font-size: 13px; font-weight: 600;
  color: var(--accent-hover);
}
.btn-xs { padding: 2px 8px; font-size: 11px; }
.ai-content {
  font-size: 13px; line-height: 1.8; color: var(--text-secondary);
  max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
}
.ai-typing { display: flex; gap: 4px; margin-top: 8px; }
.ai-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }

/* 日志列表容器 */
.log-container { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* 统计栏 */
.log-coverage-panel {
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: rgba(99,102,241,.045);
  flex-shrink: 0;
}
.coverage-loading,
.coverage-error {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 12px; color: var(--text-muted);
}
.coverage-error { color: #f59e0b; }
.coverage-summary {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  color: var(--text-secondary); font-size: 12px;
}
.coverage-warning { color: #f59e0b; font-weight: 500; }
.coverage-pods {
  display: flex; gap: 6px; align-items: center;
  overflow-x: auto; padding-top: 7px;
}
.coverage-pod-chip {
  flex: 0 0 auto; border: 1px solid var(--border); border-radius: 12px;
  background: var(--bg-card); color: var(--text-secondary);
  padding: 3px 8px; font-size: 11px; cursor: pointer;
}
.coverage-pod-chip:hover { border-color: var(--accent); color: var(--accent-hover); }
.coverage-pod-chip strong { margin-left: 4px; color: var(--accent-hover); }
.coverage-more-pods { flex: 0 0 auto; font-size: 11px; color: var(--text-muted); }
.log-stats-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 6px 16px; font-size: 12px; color: var(--text-muted);
  background: var(--bg-base); border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.log-stat-sep { opacity: .4; }
.log-stat-filtered { color: var(--accent); margin-left: 3px; }
.log-stat-item { display: flex; align-items: center; gap: 4px; }
.lvl-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.lvl-error { background: #f87171; }
.lvl-warn  { background: #fb923c; }
.lvl-info  { background: #60a5fa; }
.lvl-debug { background: #6b7280; }
.lvl-other { background: #6b7280; }

/* 表格区 */
.log-table-wrap {
  flex: 1; overflow-y: auto;
  font-family: 'Consolas', 'Cascadia Code', 'Consolas', monospace; font-size: 12px;
}
.log-table {
  width: 100%; border-collapse: collapse; table-layout: fixed;
}
.log-table thead {
  position: sticky; top: 0; z-index: 1;
  background: var(--bg-card);
}
.log-table th {
  padding: 7px 12px; text-align: left;
  font-size: 11px; font-weight: 600; letter-spacing: .04em;
  color: var(--text-muted); border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.log-row {
  cursor: pointer; transition: background .1s;
  border-bottom: 1px solid rgba(46,49,80,.35);
}
.log-row:hover    { background: var(--bg-hover); }
.log-row.row-error { background: var(--log-error); }
.log-row.row-warn  { background: var(--log-warn); }
.log-row td { padding: 5px 12px; vertical-align: top; }
.col-ts  { color: var(--text-muted); white-space: nowrap; font-size: 11px; }
.col-svc { color: var(--accent-hover); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-group { color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-msg { color: var(--text-secondary); overflow: hidden; }
.log-msg-text {
  display: -webkit-box;
  min-height: 3.1em;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}
.row-error .col-msg { color: #fca5a5; }
.row-warn  .col-msg { color: #fcd34d; }
/* 关键字命中高亮（忽略大小写） */
.col-msg mark.log-kw-hit {
  background: var(--accent, #d97757);
  color: #fff;
  padding: 0 1px;
  border-radius: 2px;
  font-weight: 600;
}
.log-row.selected,
.log-row.selected:hover {
  background: rgba(250,204,21,.18);
}
.log-row.selected td {
  background: rgba(250,204,21,.16);
  border-top: 1px solid rgba(250,204,21,.75);
  border-bottom: 1px solid rgba(250,204,21,.75);
}
.log-row.selected td:first-child {
  box-shadow: inset 4px 0 0 #facc15;
}
.log-row.selected .col-ts,
.log-row.selected .col-svc,
.log-row.selected .col-group {
  color: #fde68a;
}
.log-row.selected .col-msg {
  color: #fff7ed;
  font-weight: 600;
}

/* 级别徽章 */
.lvl-badge {
  display: inline-block; padding: 1px 7px; border-radius: 4px;
  font-size: 10px; font-weight: 700; letter-spacing: .04em;
  white-space: nowrap;
}
.lvl-badge-error { background: rgba(248,113,113,.15); color: #f87171; border: 1px solid rgba(248,113,113,.3); }
.lvl-badge-warn  { background: rgba(251,146,60,.15);  color: #fb923c; border: 1px solid rgba(251,146,60,.3); }
.lvl-badge-info  { background: rgba(96,165,250,.15);  color: #60a5fa; border: 1px solid rgba(96,165,250,.3); }
.lvl-badge-debug { background: rgba(107,114,128,.15); color: #9ca3af; border: 1px solid rgba(107,114,128,.3); }
.lvl-badge-other { background: rgba(107,114,128,.12); color: #9ca3af; border: 1px solid rgba(107,114,128,.2); }

/* 仅事件按钮 */
.btn-incident-active {
  background: rgba(251,191,36,.15);
  border: 1px solid rgba(251,191,36,.5);
  color: #fbbf24;
  padding: 5px 12px; border-radius: 6px; font-size: 12px;
  cursor: pointer; display: inline-flex; align-items: center; gap: 5px;
}

/* 加载更多 */
.load-more-bar {
  display: flex; justify-content: center;
  padding: 10px 14px; border-top: 1px solid var(--border);
  background: var(--bg-card);
}
.load-more-bar.ready {
  background: linear-gradient(180deg, rgba(99,102,241,.04), transparent);
}
.load-more-status {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--text-muted);
}
.load-more-btn {
  border: 1px solid var(--accent); border-radius: 5px;
  background: transparent; color: var(--accent-hover);
  padding: 3px 9px; font-size: 12px; cursor: pointer;
}
.load-more-btn:hover { background: rgba(99,102,241,.1); }

/* 日志详情居中模态框 */
.log-detail-modal-mask {
  position: fixed; inset: 0; z-index: 300;
  background: rgba(0,0,0,.55); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
  padding: 32px;
  outline: none;
}
.drawer-panel.log-detail-modal {
  width: min(880px, 96vw); max-height: 92vh; height: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  display: flex; flex-direction: column;
  box-shadow: 0 24px 80px rgba(0,0,0,.55);
  overflow: hidden;
}
.drawer-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  flex-shrink: 0;
}
.drawer-close {
  background: none; border: none; color: var(--text-muted);
  font-size: 14px; cursor: pointer; padding: 4px;
}
.drawer-close:hover { color: var(--text-primary); }
.drawer-body { flex: 1; overflow-y: auto; padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; }

/* 元数据折叠区 */
.drawer-meta-section {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-base);
  overflow: hidden;
  flex-shrink: 0;
}
.drawer-meta-header {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  transition: background .15s;
}
.drawer-meta-header:hover { background: var(--bg-hover); }
.drawer-meta-section.open .drawer-meta-header {
  border-bottom: 1px solid var(--border);
}
.meta-toggle {
  display: inline-block;
  width: 10px;
  font-size: 9px;
  color: var(--text-muted);
}
.meta-title { font-weight: 600; color: var(--text-secondary); }
.meta-summary {
  flex: 1; min-width: 0;
  display: flex; align-items: center; gap: 8px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 11px;
}
.meta-summary-ts { color: var(--text-muted); font-family: monospace; }
.meta-summary-svc { color: var(--accent); font-weight: 500; }
.meta-summary-ns  { color: var(--text-muted); }
.lvl-badge.mini { font-size: 9px; padding: 0 5px; line-height: 1.4; }
.drawer-meta-body {
  padding: 12px 14px;
  display: flex; flex-direction: column; gap: 12px;
  background: var(--bg-card);
}
.drawer-row { display: flex; align-items: flex-start; gap: 12px; }
.drawer-row-full { flex-direction: column; gap: 6px; }
.drawer-label {
  width: 44px; flex-shrink: 0; font-size: 11px; font-weight: 600;
  color: var(--text-muted); padding-top: 2px; text-align: right;
}
.drawer-val { font-size: 13px; color: var(--text-primary); word-break: break-all; }
.drawer-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.drawer-tag {
  font-size: 11px; padding: 2px 8px;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 9999px; color: var(--text-muted);
}
.drawer-tag em { color: var(--accent-hover); font-style: normal; }
.drawer-tag-link {
  display: inline-flex; align-items: center; gap: 4px;
  appearance: none; font-family: inherit; font-size: 11px;
  line-height: 1.4; cursor: pointer;
  border-color: rgba(56, 189, 248, .45);
  color: var(--accent);
}
.drawer-tag-link:hover {
  background: rgba(56, 189, 248, .10);
  border-color: var(--accent-hover);
  color: var(--accent-hover);
}
.drawer-tag-jump { font-size: 10px; opacity: .75; }
.drawer-content {
  margin: 0; padding: 12px 14px;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 6px; font-size: 12px; font-family: 'Consolas', monospace;
  color: var(--text-secondary); line-height: 1.7;
  word-break: break-all; white-space: pre-wrap;
  max-height: 60vh; overflow-y: auto;
}

/* 抽屉动画 */
.drawer-section-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 8px;
}
.drawer-section-title {
  font-size: 12px; font-weight: 600; color: var(--text-primary);
  display: inline-flex; align-items: center; gap: 6px;
}
/* 标题旁的小内联 spinner：弱化加载感知 */
.spinner.mini-inline {
  width: 10px;
  height: 10px;
  border-width: 1.5px;
  border-color: var(--text-muted);
  border-top-color: transparent;
  opacity: .65;
  vertical-align: middle;
}
.drawer-section-actions {
  display: flex; align-items: center; gap: 8px;
}
.drawer-section-meta {
  font-size: 11px; color: var(--text-muted);
}
.drawer-context-search {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.context-search-main-row {
  flex: 1 1 520px;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.context-search-box {
  flex: 1 1 320px;
  min-width: 240px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 7px;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px;
  min-height: 32px;
}
.context-search-box.active {
  border-color: rgba(56,189,248,.45);
  background: rgba(56,189,248,.06);
}
.context-search-icon {
  color: #38bdf8;
  font-size: 13px;
  line-height: 1;
  flex-shrink: 0;
}
.context-search-chip {
  cursor: default;
}
.context-condition-join {
  flex-shrink: 0;
  height: 22px;
  padding: 0 6px;
  border: 1px solid rgba(56,189,248,.35);
  border-radius: 999px;
  background: rgba(56,189,248,.09);
  color: #38bdf8;
  font-size: 10px;
  font-weight: 700;
  line-height: 20px;
  cursor: pointer;
}
.context-condition-join.or {
  border-color: rgba(251,191,36,.4);
  background: rgba(251,191,36,.1);
  color: #fbbf24;
}
.context-condition-join:hover {
  filter: brightness(1.15);
}
.context-search-input {
  flex: 1 1 120px;
  min-width: 110px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 12px;
  padding: 3px 0;
  outline: none;
}
.context-search-input::placeholder {
  color: var(--text-muted);
}
.context-add-condition {
  flex-shrink: 0;
  height: 24px;
  padding: 0 7px;
  border: 1px solid rgba(56,189,248,.35);
  border-radius: 5px;
  background: rgba(56,189,248,.08);
  color: #38bdf8;
  font-size: 11px;
  cursor: pointer;
}
.context-add-condition:hover:not(:disabled) {
  border-color: #38bdf8;
  background: rgba(56,189,248,.14);
}
.context-add-condition:disabled {
  opacity: .42;
  cursor: not-allowed;
}
.context-search-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.context-service-jump {
  height: 32px;
  flex-shrink: 0;
  white-space: nowrap;
  border-color: rgba(56,189,248,.45);
  color: #38bdf8;
}
.context-service-jump:hover {
  border-color: #38bdf8;
  background: rgba(56,189,248,.08);
}
.context-search-count {
  min-width: 46px;
  text-align: center;
  color: var(--text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.context-search-nav {
  width: 24px;
  height: 24px;
  padding: 0;
  justify-content: center;
}
.drawer-context-state {
  display: flex; align-items: center; gap: 8px;
  min-height: 42px; padding: 0 2px;
  font-size: 12px; color: var(--text-muted);
}
.drawer-context-state-error { color: var(--error); }
.drawer-context-list {
  display: flex; flex-direction: column; gap: 6px;
  max-height: 76vh; overflow-y: auto;
  padding: 4px 4px 4px 28px;   /* 左侧 28px 给锚点 ▶ 标记预留 */
}
.drawer-context-loading-more {
  display: flex; align-items: center; justify-content: center;
  gap: 8px; padding: 8px;
  font-size: 11px; color: var(--text-muted);
  background: var(--bg-base);
  border: 1px dashed var(--border);
  border-radius: 6px;
}
.drawer-context-item {
  width: 100%; display: grid;
  grid-template-columns: 138px 120px minmax(0, 1fr);
  gap: 10px; align-items: start;
  padding: 10px 68px 10px 12px;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-secondary);
  font-family: 'Consolas', monospace; font-size: 12px; line-height: 1.6;
  text-align: left; cursor: default;
  position: relative;
}
.drawer-context-item.level-error { background: var(--log-error); }
.drawer-context-item.level-warn  { background: var(--log-warn); }

/* 锚点行（开始查看的日志）— 实色高反差 */
.drawer-context-item.active {
  background: #facc15;            /* 实色亮黄 */
  border-color: #facc15;
  color: #1f2937;                  /* 深字 */
  font-weight: 600;
  box-shadow:
    inset 5px 0 0 0 #ea580c,       /* 左侧橙色实色条 */
    0 0 0 2px #facc15,
    0 8px 22px rgba(250,204,21,.45);
  z-index: 2;
}
.drawer-context-item.active .drawer-context-ts,
.drawer-context-item.active .drawer-context-svc,
.drawer-context-item.active .drawer-context-text {
  color: #1f2937;
}
/* 锚点是 error/warn 时：用红色实色加重，因为问题日志更要突出 */
.drawer-context-item.active.level-error,
.drawer-context-item.active.level-warn {
  background: #f85149;
  border-color: #f85149;
  color: #fff;
  box-shadow:
    inset 5px 0 0 0 #7f1d1d,
    0 0 0 2px #f85149,
    0 8px 22px rgba(248,81,73,.5);
}
.drawer-context-item.active.level-error .drawer-context-ts,
.drawer-context-item.active.level-warn  .drawer-context-ts,
.drawer-context-item.active.level-error .drawer-context-svc,
.drawer-context-item.active.level-warn  .drawer-context-svc,
.drawer-context-item.active.level-error .drawer-context-text,
.drawer-context-item.active.level-warn  .drawer-context-text {
  color: #fff;
}

.anchor-marker {
  position: absolute;
  left: -22px;
  top: 50%;
  transform: translateY(-50%);
  color: #ea580c;
  font-size: 14px;
  font-weight: 900;
  pointer-events: none;
  animation: anchor-pulse 1.2s ease-in-out infinite;
}
.drawer-context-item.active.level-error .anchor-marker,
.drawer-context-item.active.level-warn  .anchor-marker { color: #f85149; }
@keyframes anchor-pulse {
  0%, 100% { opacity: 1; transform: translateY(-50%) translateX(0); }
  50%      { opacity: .55; transform: translateY(-50%) translateX(3px); }
}
.drawer-context-item.context-match {
  border-color: rgba(56,189,248,.45);
  box-shadow: inset 3px 0 0 rgba(56,189,248,.65);
}
.drawer-context-item.context-match-current {
  outline: 2px solid #38bdf8;
  outline-offset: 1px;
  border-color: #38bdf8;
}
.drawer-context-ts,
.drawer-context-svc { color: var(--text-muted); white-space: nowrap; }
.drawer-context-svc {
  color: var(--accent-hover); overflow: hidden; text-overflow: ellipsis;
}
.drawer-context-text {
  min-width: 0; word-break: break-all;
}
.context-copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 24px;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255,255,255,.04);
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1;
  font-family: var(--font-sans, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
  cursor: pointer;
  opacity: .62;
  transition: opacity .12s, color .12s, border-color .12s, background .12s;
}
.drawer-context-item:hover .context-copy-btn,
.context-copy-btn:focus-visible,
.context-copy-btn.copied {
  opacity: 1;
}
.context-copy-btn:hover {
  color: var(--text-primary);
  border-color: var(--border-accent);
  background: var(--bg-hover);
}
.context-copy-btn.copied {
  color: #22c55e;
  border-color: rgba(34,197,94,.55);
  background: rgba(34,197,94,.12);
}
.drawer-context-item.active .context-copy-btn {
  color: #1f2937;
  border-color: rgba(31,41,55,.35);
  background: rgba(255,255,255,.62);
}
.drawer-context-item.active.level-error .context-copy-btn,
.drawer-context-item.active.level-warn .context-copy-btn {
  color: #fff;
  border-color: rgba(255,255,255,.55);
  background: rgba(255,255,255,.18);
}
.context-keyword-hit {
  display: inline;
  padding: 0 2px;
  border-radius: 2px;
  background: rgba(250,204,21,.42);
  color: inherit;
  font-weight: 700;
}
.drawer-context-item.active .context-keyword-hit {
  background: rgba(31,41,55,.22);
}
.drawer-context-item.active.level-error .context-keyword-hit,
.drawer-context-item.active.level-warn .context-keyword-hit {
  background: rgba(255,255,255,.28);
}
.drawer-context-hint {
  font-size: 11px; color: var(--text-muted); padding: 0 2px;
}

@media (max-width: 720px) {
  .drawer-context-search {
    align-items: stretch;
  }
  .context-search-main-row {
    flex-direction: column;
    align-items: stretch;
  }
  .context-search-box {
    flex-basis: 100%;
  }
  .drawer-context-item {
    grid-template-columns: 1fr;
    gap: 4px;
    padding-right: 68px;
  }
}

/* 模态淡入 + 卡片轻微上推 */
.modal-fade-enter-active, .modal-fade-leave-active {
  transition: opacity .18s ease, background .18s ease;
}
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; background: transparent; }
.modal-fade-enter-active .drawer-panel.log-detail-modal,
.modal-fade-leave-active .drawer-panel.log-detail-modal {
  transition: transform .18s ease, opacity .18s ease;
}
.modal-fade-enter-from .drawer-panel.log-detail-modal,
.modal-fade-leave-to   .drawer-panel.log-detail-modal {
  transform: translateY(12px) scale(.985); opacity: 0;
}

/* ── 模板聚合 ── */
.template-container { flex: 1; overflow-y: auto; padding: 12px 16px; }
.template-list { display: flex; flex-direction: column; gap: 10px; }

.tpl-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  transition: border-color .15s;
}
.tpl-card:hover { border-color: rgba(99,102,241,.4); }

.tpl-header {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px;
}
.tpl-rank {
  width: 22px; text-align: center;
  font-size: 12px; font-weight: 700;
  color: var(--text-muted); flex-shrink: 0;
}
.tpl-rank.rank-top { color: var(--warning); }
.tpl-count { flex-shrink: 0; }
.tpl-pct { font-size: 11px; color: var(--text-muted); flex-shrink: 0; width: 44px; }
.tpl-bar-wrap { flex: 1; height: 6px; background: var(--bg-hover); border-radius: 3px; overflow: hidden; }
.tpl-bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 3px; transition: width .4s; }

.tpl-pattern {
  font-family: 'Consolas', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 8px 12px;
  word-break: break-all;
  line-height: 1.7;
  margin-bottom: 10px;
}
:deep(.wildcard) {
  color: var(--accent-hover);
  background: rgba(99,102,241,.15);
  border-radius: 3px;
  padding: 0 3px;
  font-weight: 600;
}

.tpl-services { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tpl-label { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.svc-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; padding: 2px 8px;
  background: rgba(59,130,246,.1);
  border: 1px solid rgba(59,130,246,.25);
  color: var(--info); border-radius: 9999px;
}
.svc-chip em { font-style: normal; opacity: .7; }

.tpl-example {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: 11px;
}
.tpl-example-text {
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
  overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; flex: 1;
}
.tpl-example-ts { color: var(--text-muted); opacity: .6; margin-right: 6px; }

@keyframes pulse { 0%,80%,100%{opacity:.2} 40%{opacity:1} }

/* ═══════════════════════════════════════
   耗时追踪 Tab
═══════════════════════════════════════ */
.trace-tab {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; padding: 10px 16px; gap: 10px;
}

/* 查询工具栏（单行） */
.trace-form-bar {
  display: flex; align-items: center; gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  flex-shrink: 0;
}
.trace-input-grow { flex: 1; min-width: 0; }
.trace-bar-select { width: 130px; flex-shrink: 0; }
.trace-input-wrap {
  display: flex; align-items: center;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px; padding: 0 10px; gap: 6px;
  transition: border-color .15s;
}
.trace-input-wrap:focus-within {
  border-color: rgba(234,179,8,.5);
  box-shadow: 0 0 0 2px rgba(234,179,8,.08);
}
.trace-input-icon { font-size: 13px; flex-shrink: 0; }
.trace-input {
  flex: 1; background: transparent; border: none;
  color: var(--text-primary); font-size: 13px;
  padding: 6px 0; outline: none;
}
.trace-input::placeholder { color: var(--text-muted); }

/* 开始分析按钮 */
.btn-trace-primary {
  background: linear-gradient(135deg, rgba(234,179,8,.2), rgba(234,179,8,.1));
  border: 1px solid rgba(234,179,8,.45);
  color: #fbbf24; padding: 7px 20px;
  border-radius: 6px; font-size: 13px; font-weight: 600;
  cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  transition: all .15s; white-space: nowrap;
}
.btn-trace-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(234,179,8,.3), rgba(234,179,8,.18));
  border-color: rgba(234,179,8,.7);
}
.btn-trace-primary:disabled { opacity: .4; cursor: not-allowed; }

/* 结果区域 */
.trace-result {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  min-height: 0;
}

/* 未找到 */
.trace-not-found {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 40px;
  color: var(--text-muted); font-size: 13px; gap: 8px;
}
.trace-not-found em { color: var(--text-primary); font-style: normal; font-weight: 500; }

/* ── 子页签切换栏 ── */
.trace-sub-tabs {
  display: flex; gap: 2px;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 8px; padding: 3px;
  flex-shrink: 0; margin-bottom: 10px;
  width: fit-content;
}
.trace-sub-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 16px; border-radius: 6px;
  border: none; background: transparent;
  color: var(--text-muted); font-size: 13px;
  cursor: pointer; transition: all .15s;
}
.trace-sub-btn:hover { color: var(--text-primary); }
.trace-sub-btn.active {
  background: var(--bg-active); color: var(--text-primary);
}
.trace-sub-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 20px; height: 18px; padding: 0 5px;
  background: var(--bg-hover); border-radius: 9999px;
  font-size: 11px; color: var(--text-muted); font-weight: 600;
}
.trace-sub-btn.active .trace-sub-badge {
  background: rgba(234,179,8,.15); color: #fbbf24;
}

/* ── 耗时概览页签 ── */
.trace-overview {
  flex: 1; overflow-y: auto;
  display: flex; flex-direction: column; gap: 16px;
}

/* 大数字英雄区 */
.trace-hero {
  background: var(--bg-card);
  border: 1px solid rgba(234,179,8,.3);
  border-radius: var(--radius);
  padding: 28px 32px;
  display: flex; flex-direction: column; gap: 6px;
  align-items: flex-start;
}
.trace-hero-label {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .6px; color: var(--text-muted);
}
.trace-hero-duration {
  font-size: 56px; font-weight: 700; color: #fbbf24;
  font-variant-numeric: tabular-nums; line-height: 1;
  letter-spacing: -2px;
}
.trace-hero-meta {
  font-size: 13px; color: var(--text-muted); margin-top: 4px;
}
.trace-hero-meta em { color: var(--text-primary); font-style: normal; font-weight: 500; }
.trace-hero-meta strong { color: var(--text-primary); }
.trace-limit-hint { font-size: 11px; color: var(--warning); }

/* 时间线卡片 */
.trace-timeline-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
}
.trace-tl-row {
  display: flex; align-items: stretch; gap: 16px;
}
.trace-tl-left {
  display: flex; flex-direction: column; align-items: center;
  width: 20px; flex-shrink: 0;
}
.trace-tl-dot {
  width: 14px; height: 14px; border-radius: 50%;
  flex-shrink: 0;
}
.dot-first { background: #34d399; box-shadow: 0 0 8px rgba(52,211,153,.6); }
.dot-last  { background: #f87171; box-shadow: 0 0 8px rgba(248,113,113,.6); }
.trace-tl-connector {
  flex: 1; width: 2px;
  background: repeating-linear-gradient(
    180deg, rgba(234,179,8,.4) 0 4px, transparent 4px 8px
  );
  margin: 4px 0;
}
.trace-tl-line {
  flex: 1; width: 2px;
  background: repeating-linear-gradient(
    180deg, rgba(234,179,8,.4) 0 4px, transparent 4px 8px
  );
}
.trace-tl-body {
  flex: 1; display: flex; flex-direction: column; gap: 4px;
  padding: 0 0 20px;
}
.dur-row .trace-tl-body { padding: 0; justify-content: center; }
.trace-tl-tag {
  font-size: 10px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .5px; color: var(--text-muted);
}
.trace-tl-ts {
  font-size: 15px; font-weight: 600; color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.trace-ep-svc {
  display: inline-block; font-size: 10px; padding: 1px 7px;
  background: rgba(99,102,241,.15); border: 1px solid rgba(99,102,241,.3);
  color: var(--accent-hover); border-radius: 9999px; width: fit-content;
}
.trace-tl-log {
  font-size: 12px; color: var(--text-muted);
  font-family: 'Consolas', monospace;
  word-break: break-all; line-height: 1.5;
}
.trace-tl-dur-badge {
  font-size: 13px; font-weight: 700; color: #fbbf24;
  background: rgba(234,179,8,.1);
  border: 1px solid rgba(234,179,8,.3);
  border-radius: 6px; padding: 3px 12px;
  font-variant-numeric: tabular-nums;
  align-self: flex-start;
}

/* ── 匹配日志页签 ── */
.trace-log-panel {
  flex: 1; display: flex; flex-direction: column; gap: 8px;
  overflow: hidden; min-height: 0;
}
.trace-logs-header {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; font-weight: 500; color: var(--text-muted);
  flex-shrink: 0;
}
.trace-logs-count {
  font-size: 11px; padding: 1px 7px;
  background: var(--bg-hover); border-radius: 9999px;
  color: var(--text-muted);
}
.trace-log-list {
  flex: 1; overflow-y: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-family: 'Consolas', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
}

/* ── 每条耗时列表 ── */
.trace-spans-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  flex-shrink: 0;
}
.trace-spans-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  font-size: 12px; font-weight: 500; color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  background: var(--bg-base);
}
.trace-span-list {
  max-height: 400px; overflow-y: auto;
  font-family: 'Consolas', 'Cascadia Code', 'Consolas', monospace; font-size: 11px;
}
.trace-span-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 5px 14px;
  border-bottom: 1px solid rgba(46,49,80,.35);
  transition: background .1s;
  cursor: pointer;
}
.trace-span-row:hover { background: var(--bg-hover); }
.trace-span-row.level-error { background: var(--log-error); }
.trace-span-row.level-warn  { background: var(--log-warn); }
.trace-span-idx {
  width: 30px; text-align: right; flex-shrink: 0;
  color: var(--text-muted); font-size: 10px;
}
.trace-span-elapsed {
  width: 90px; flex-shrink: 0;
  color: #fbbf24; font-weight: 600; font-size: 11px;
  font-variant-numeric: tabular-nums; text-align: right;
}
.trace-span-bar-wrap {
  width: 80px; flex-shrink: 0;
  height: 4px; background: rgba(255,255,255,.07);
  border-radius: 2px; overflow: hidden;
}
.trace-span-bar {
  height: 100%;
  background: linear-gradient(90deg, #34d399, #fbbf24);
  border-radius: 2px; transition: width .2s;
  min-width: 2px;
}
.trace-span-ts {
  width: 138px; flex-shrink: 0;
  color: var(--text-muted); font-size: 10px;
  white-space: nowrap;
}
.trace-span-line {
  flex: 1; color: var(--text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  line-height: 1.5; padding-top: 1px;
}
.trace-span-row.expanded .trace-span-line {
  white-space: pre-wrap; word-break: break-all;
  text-overflow: unset; overflow: visible;
}
.trace-span-idx,
.trace-span-elapsed,
.trace-span-bar-wrap,
.trace-span-ts,
.trace-ep-svc {
  flex-shrink: 0; margin-top: 2px;
}
</style>
