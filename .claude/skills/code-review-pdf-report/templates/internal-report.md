<!--
内部工程留档模板。findings 完整展开，允许出现文件路径、行号、代码片段。
占位符 {{...}} 由 SKILL.md 编排时填充，本文件只定义结构，不是可执行模板引擎。
-->

# 代码审查报告（内部工程留档）

- **审查范围**：{{scope}}
- **审查时间**：{{date}}
- **审查工具**：Claude Code /code-review-pdf-report（effort: {{effort}}）
- **规则来源**：/code-review 内置检查项 + `.claude/review-rules.yaml`（v{{rules_version}}，共 {{custom_rule_count}} 条自定义规则）
- **结论**：{{PASS_FAIL}}

## 摘要

| 严重程度 | 数量 |
|---|---|
| Critical | {{count_critical}} |
| High | {{count_high}} |
| Medium | {{count_medium}} |
| Low | {{count_low}} |
| **合计** | {{count_total}} |

## 详细发现

> 按 severity 降序排列，每条一个小节。

### [{{severity}}] {{title}}

- **规则**：{{rule_id}}（{{rule_source}}，如同时命中内置与自定义规则则一并列出）
- **位置**：`{{file}}:{{line}}`
- **问题**：{{summary}}
- **触发场景**：{{failure_scenario}}
- **建议**：{{recommendation}}
- **代码片段**：
  ```{{language}}
  {{snippet}}
  ```

<!-- 重复以上小节，覆盖全部 findings -->

## 附录：本次审查覆盖范围

- 内置规则：correctness bugs / reuse & simplification / efficiency / OWASP 安全项
- 自定义规则：{{custom_rule_ids}}
- 未应用的自定义规则（如 `.claude/review-rules.yaml` 缺失或规则不适用于本次改动文件）：{{skipped_rules}}
