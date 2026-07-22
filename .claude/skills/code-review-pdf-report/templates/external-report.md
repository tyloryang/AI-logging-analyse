<!--
对外/合规正式报告模板。禁止出现内部文件路径、变量名、密钥片段等敏感信息 —— 这是硬性要求。
findings 只脱敏到"类别 + 严重程度 + 摘要 + 建议"级别。
-->

# 代码质量审查报告

- **项目**：{{project_name}}
- **审查范围**：{{scope_summary}}（不标注具体分支名/内部路径，仅描述"本次变更范围"）
- **审查日期**：{{date}}
- **结论**：**{{PASS_FAIL}}** —— {{one_line_conclusion}}

## 执行摘要

本次审查覆盖 {{files_reviewed}} 个文件的变更，共识别 {{total_findings}} 项问题，
其中严重问题 {{count_critical}} 项、重要问题 {{count_high}} 项、
一般问题 {{count_medium}} 项、轻微问题 {{count_low}} 项。

{{overall_risk_statement}}

## 问题类别分布

| 类别 | 数量 | 风险等级 |
|---|---|---|
| 安全 (Security) | {{security_count}} | {{security_risk}} |
| 可靠性 (Reliability) | {{reliability_count}} | {{reliability_risk}} |
| 可维护性 (Maintainability) | {{maintainability_count}} | {{maintainability_risk}} |

## 主要发现（摘要级别，已脱敏）

<!-- 每条只保留类别 + 严重程度 + 一句话摘要 + 一句话建议，不出现文件路径/代码片段/变量名 -->
1. **[{{severity}}] {{category}}** —— {{finding_summary}}。建议：{{recommendation}}
2. ...

## 审查方法说明

本报告由自动化静态审查生成，覆盖代码正确性、可复用性/简洁性、执行效率与常见安全缺陷
（OWASP Top 10 相关项）等维度，并结合项目内部质量规范补充审查。

## 免责声明

本报告基于自动化工具生成的审查结果，仅反映审查时间点的代码状态，
不构成完整的安全渗透测试、合规认证或法律意见。
