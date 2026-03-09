

"""飞书 / 钉钉 Webhook 通知器"""
import os
import httpx


def _health_color_feishu(score: int) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "orange"
    return "red"


def _health_emoji(score: int) -> str:
    if score >= 80:
        return "✅"
    if score >= 60:
        return "⚠️"
    return "❌"


def _build_feishu_card(report: dict) -> dict:
    """构造飞书交互卡片"""
    score = report.get("health_score", 0)
    title = report.get("title", "运维日报")
    top10 = report.get("top10_errors", [])[:5]
    ai = report.get("ai_analysis", "") or ""

    # 指标行
    metrics = (
        f"**总日志**: {report.get('total_logs', 0):,}  "
        f"**错误数**: {report.get('total_errors', 0):,}  "
        f"**涉及服务**: {report.get('service_count', 0)}  "
        f"**活跃告警**: {report.get('active_alerts', 0)}"
    )

    # Top 错误服务
    top_lines = ""
    if top10:
        lines = [f"{i+1}. **{x['service']}** — {x['count']:,} 条" for i, x in enumerate(top10)]
        top_lines = "\n".join(lines)

    # AI 摘要（取前 300 字）
    ai_summary = ai[:300].strip()
    if len(ai) > 300:
        ai_summary += "…"

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"{_health_emoji(score)} **健康评分**: {score}/100\n{metrics}",
            },
        },
    ]

    if top_lines:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🔥 错误 Top 5 服务**\n{top_lines}"},
        })

    if ai_summary:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🤖 AI 分析摘要**\n{ai_summary}"},
        })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": _health_color_feishu(score),
            },
            "elements": elements,
        },
    }


def _build_dingtalk_markdown(report: dict) -> dict:
    """构造钉钉 Markdown 消息"""
    score = report.get("health_score", 0)
    title = report.get("title", "运维日报")
    top10 = report.get("top10_errors", [])[:5]
    ai = report.get("ai_analysis", "") or ""

    emoji = _health_emoji(score)
    lines = [
        f"## {emoji} {title}",
        "",
        f"**健康评分**: {score}/100",
        f"**总日志**: {report.get('total_logs', 0):,} &nbsp; "
        f"**错误数**: {report.get('total_errors', 0):,} &nbsp; "
        f"**涉及服务**: {report.get('service_count', 0)} &nbsp; "
        f"**活跃告警**: {report.get('active_alerts', 0)}",
    ]

    if top10:
        lines += ["", "### 🔥 错误 Top 5 服务"]
        for i, x in enumerate(top10):
            lines.append(f"{i+1}. **{x['service']}** — {x['count']:,} 条")

    if ai:
        summary = ai[:300].strip()
        if len(ai) > 300:
            summary += "…"
        lines += ["", "### 🤖 AI 分析摘要", summary]

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": "\n".join(lines),
        },
    }


async def send_feishu(report: dict, webhook_url: str) -> dict:
    """发送飞书消息，返回 {"ok": bool, "msg": str}"""
    payload = _build_feishu_card(report)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # 飞书成功时 code=0
            if data.get("code", -1) == 0:
                return {"ok": True, "msg": "发送成功"}
            return {"ok": False, "msg": data.get("msg", str(data))}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def send_dingtalk(report: dict, webhook_url: str) -> dict:
    """发送钉钉消息，返回 {"ok": bool, "msg": str}"""
    payload = _build_dingtalk_markdown(report)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            # 钉钉成功时 errcode=0
            if data.get("errcode", -1) == 0:
                return {"ok": True, "msg": "发送成功"}
            return {"ok": False, "msg": data.get("errmsg", str(data))}
    except Exception as e:
        return {"ok": False, "msg": str(e)}
