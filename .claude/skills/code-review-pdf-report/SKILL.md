---
name: code-review-pdf-report
description: >
  对当前代码变更（或指定文件/PR）执行代码审查，规则来源结合 /code-review 内置检查项
  （correctness bugs / reuse & simplification / efficiency / OWASP 安全项）与项目自定义
  规则文件 .claude/review-rules.yaml，审查结果生成 PDF 报告。支持 --audience
  internal|external 切换报告模板（内部工程留档 vs 对外/合规正式报告，已脱敏）。
  当用户要求"生成代码审查报告"、"出一份PDF审查报告"、"给这次改动做审查报告"、
  "review 一下并出份报告给客户/审计"时使用此技能。
---

# 代码审查 → PDF 报告 编排

本 skill 是一个**编排层**，不重新实现审查逻辑或 PDF 渲染逻辑，而是把两个已有能力串起来：

- 审查逻辑 —— 复用 `code-review` 技能的分析方式（correctness bugs / reuse-simplification-
  efficiency / OWASP 安全项），再叠加项目自定义规则
- PDF 渲染 —— 复用 `pdf` 技能，把最终 Markdown 内容转换成 PDF 文件

本 skill 自身只负责：**定范围 → 拼规则 → 汇总 findings → 选模板 → 交给 pdf 技能渲染**。

## 参数

- `scope`（可选）：默认是当前分支相对 main 的 diff（`git diff [base-branch]...HEAD`）；
  也可以是 `--pr <编号>`（用 `gh pr diff <编号>`）或显式文件列表
- `--audience internal|external`（默认 `internal`）：决定用哪份报告模板
- `--effort low|medium|high|xhigh`（默认 `medium`）：审查深度，含义与 `/code-review` 一致

## 流程

### 1. 确定审查范围
没有指定 scope 时用 `git status` + `git diff [base-branch]...HEAD` 拿到本次改动的文件列表和内容。
指定了 `--pr <编号>` 时改用 `gh pr diff <编号>`。

### 2. 内置规则审查
按当前 scope、以 `--effort` 指定的深度，执行等价于 `/code-review` 的分析：
correctness bugs（真实会出错的逻辑缺陷，不是风格问题）+ reuse/simplification/efficiency +
OWASP Top 10 相关安全缺陷。每条 finding 记录为：

```
{
  rule_source: "built-in",
  category: "correctness" | "simplification" | "security" | "efficiency",
  severity: "critical" | "high" | "medium" | "low",
  file, line, summary, failure_scenario, recommendation, snippet
}
```

### 3. 自定义规则审查
读取 `.claude/review-rules.yaml`：

- **文件不存在** → 跳过此步，在最终报告里如实注明"本次未应用自定义规则"，不要报错阻断流程。
- **文件存在** → 对每条 rule，用 `applies_to` 的 glob 匹配本次改动文件；命中的文件里检查
  该规则 `description` 描述的条件是否被违反。命中即产出一条 finding：

```
{
  rule_source: "custom:<rule_id>",
  category: rule.category,
  severity: rule.severity,
  file, line, summary, recommendation
}
```

### 4. 合并、去重、排序
把两组 findings 合并，按 severity 降序排列（critical > high > medium > low）。
同一个 `file:line` 若同时被内置规则和自定义规则命中，只保留一条（取更高的 severity），
并在描述里注明"该问题同时匹配 {{rule_id}}"。

### 5. 计算摘要统计与 PASS/FAIL
按 severity 分别计数。判定规则（可按团队需要调整阈值，调整时在报告里注明用的是哪套阈值）：

- 存在任意 `critical` → **FAIL**
- 没有 critical 但 `high` 数量 ≥ 3 → **FAIL**
- 其余情况 → **PASS**

### 6. 套用模板生成 Markdown 报告内容
根据 `--audience` 选择模板结构：

- `internal` → 按 `.claude/skills/code-review-pdf-report/templates/internal-report.md` 的结构，
  findings **完整展开**（文件路径、行号、代码片段都保留）。
- `external` → 按 `.claude/skills/code-review-pdf-report/templates/external-report.md` 的结构，
  findings **脱敏为类别级摘要**（只保留 severity + category + 一句话摘要 + 一句话建议，
  **不得出现**具体文件路径、变量名、代码片段、密钥/URL 等内部信息 —— 这是硬性要求，不是可选项）。

把模板里的占位符（`{{scope}}`、`{{count_critical}}` 等）替换成第 1-5 步算出来的真实值，
生成一份完整的 Markdown 文本。

### 7. 渲染 PDF
用 Skill 工具调用 `pdf` 技能，把第 6 步生成的 Markdown 内容转换为 PDF，
输出到项目根目录 `reports/code-review-<YYYYMMDD-HHmm>-<audience>.pdf`
（`reports/` 目录不存在则先创建）。

### 8. 回报结果
告诉用户：

- 生成的 PDF 文件路径
- severity 统计（critical/high/medium/low 各多少条）
- PASS / FAIL 结论
- 本次读取了几条自定义规则（以及是否有文件缺失/规则不适用的情况）

## 边界

- **找不到 `.claude/review-rules.yaml` 不算错误**——内置规则依然可以正常出报告，
  只需要在报告里如实注明"本次未应用自定义规则"。
- **external 报告的脱敏是硬性要求**：不允许出现内部文件路径、变量名、密钥片段等敏感信息，
  即使 findings 本身包含这些细节，渲染进 external 模板时也必须先摘要化。
- **不要重新发明审查引擎**：安全类检查复用 `code-review` 已覆盖的 OWASP 范围即可，
  不需要在本 skill 里单独实现 SQL 注入检测器之类的静态分析工具。
- **不要重新发明 PDF 渲染**：Markdown → PDF 一律交给 `pdf` 技能处理，本 skill 不直接
  调用 reportlab/weasyprint 等库。
- 如果 `.claude/review-rules.yaml` 的 YAML 格式解析失败，提示用户文件有语法错误并给出
  具体报错，不要静默跳过导致用户以为规则生效了实际没生效。

## 相关文件

- 自定义规则定义：[.claude/review-rules.yaml](../../review-rules.yaml)
- 内部报告模板：[templates/internal-report.md](templates/internal-report.md)
- 外部报告模板：[templates/external-report.md](templates/external-report.md)
