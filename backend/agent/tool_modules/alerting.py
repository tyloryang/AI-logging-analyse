"""Alertmanager 告警池工具（供 aiops_router / alertmanager.md skill 使用）。

数据来自 /api/alerts/webhook 落到 alert_dedup 池里的告警分组，
让 AI 不依赖用户复述就能拿到『当前都有什么在告警』。
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
async def get_current_alerts(status: str = "firing", service: str = "", limit: int = 20) -> str:
    """查询当前告警池（Alertmanager webhook 落库的告警分组）。

    status=按状态筛：firing（默认）/ acked / resolved / suppressed / 空=全部
    service=按服务名模糊筛（可选）
    limit=最多返回条数（默认 20）

    典型用途：用户问『现在有哪些告警 / 平台什么状态』或 aiops_router
    需要『除了这条告警还有什么在同时爆』做关联分析时首选。"""
    try:
        from services.alert_dedup import list_groups

        groups = list_groups(
            status=status or None,
            service=service or None,
            limit=limit,
        )
        if not groups:
            scope = f"status={status or '全部'}" + (f" service~{service}" if service else "")
            return f"当前告警池为空（{scope}）—— 没有匹配的告警分组。"

        sev_emoji = {"critical": "🔴", "error": "🔴", "warning": "🟡", "info": "🔵"}
        lines = [f"**当前告警（{len(groups)} 组，status={status or '全部'}）**\n"]
        for g in groups:
            emoji = sev_emoji.get(g.get("severity", "warning"), "🟡")
            svc = g.get("service") or "-"
            ns = g.get("namespace") or "-"
            lines.append(
                f"- {emoji} **{g.get('alertname', '?')}** "
                f"service={svc} ns={ns} 次数×{g.get('count', 1)} "
                f"最近={g.get('last_at', '?')} 状态={g.get('status', '?')}"
            )
        lines.append("\n下一步：对可疑告警按 aiops-router SKILL 走 L1-L5 排障流程。")
        return "\n".join(lines)
    except Exception as e:
        return f"读取告警池失败：{e}"


__all__ = ["get_current_alerts"]
