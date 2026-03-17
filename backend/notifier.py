

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


def _build_feishu_card(report: dict, keyword: str = "", report_url: str = "") -> dict:
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

    # 若配置了关键词且标题中未包含，在指标行前拼入（确保通过飞书关键词安全校验）
    header_content = f"{_health_emoji(score)} **健康评分**: {score}/100\n{metrics}"
    if keyword and keyword not in header_content and keyword not in title:
        header_content = keyword + "\n" + header_content

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": header_content,
            },
        },
    ]

    if top_lines:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🔥 错误 Top 5 服务**\n{top_lines}"},
        })

    if ai:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**🤖 AI 分析**\n{ai.strip()}"},
        })

    if report_url:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看完整报告"},
                "type": "primary",
                "url": report_url,
            }],
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


def _build_dingtalk_markdown(report: dict, keyword: str = "") -> dict:
    """构造钉钉 Markdown 消息。keyword 会插入消息首行确保通过关键词安全策略。"""
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

    # 若配置了关键词且消息中尚未包含，插入消息顶部（不影响显示，仅用于通过安全校验）
    text = "\n".join(lines)
    if keyword and keyword not in text:
        text = keyword + "\n" + text

    return {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": text,
        },
    }


def _build_feishu_slowlog_card(report: dict, keyword: str = "", report_url: str = "") -> dict:
    """构造慢日志报告飞书交互卡片"""
    score      = report.get("health_score", 0)
    title      = report.get("title", "MySQL 慢日志报告")
    date_range = f"{report.get('date_from', '')} ~ {report.get('date_to', '')}"
    ai         = (report.get("ai_analysis") or "").strip()

    metrics_line = (
        f"**分析主机**: {report.get('hosts_count', 0)} 台  "
        f"**慢查询总数**: {report.get('total_queries', 0):,}  "
        f"**告警数**: {report.get('alert_queries', 0):,}  "
        f"**最大耗时**: {report.get('max_query_time', 0)}s"
    )
    header_content = (
        f"{_health_emoji(score)} **健康评分**: {score}/100\n"
        f"分析时段：{date_range}\n{metrics_line}"
    )
    if keyword and keyword not in header_content and keyword not in title:
        header_content = keyword + "\n" + header_content

    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": header_content}}]

    host_results = report.get("host_results", [])
    if host_results:
        host_lines = "\n".join(
            f"- **{h['host_ip']}**：{h['total']} 条，"
            f"{h['alert_count']} 告警，最大 {h['max_query_time']}s"
            for h in host_results
        )
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": f"**🖥️ 各主机情况**\n{host_lines}",
        }})

    top_slow = report.get("top_slow", [])[:5]
    if top_slow:
        lines = [
            f"{i+1}. **{s['host_ip']}** — {s['query_time']}s — "
            f"`{s['sql_brief'][:80]}{'...' if len(s['sql_brief']) >= 80 else ''}`"
            for i, s in enumerate(top_slow)
        ]
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": "**🐌 Top 5 慢查询**\n" + "\n".join(lines),
        }})

    if ai:
        ai_excerpt = ai[:600] + ("..." if len(ai) > 600 else "")
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": f"**🤖 AI 分析**\n{ai_excerpt}",
        }})

    if report_url:
        elements.append({"tag": "hr"})
        elements.append({"tag": "action", "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看完整报告"},
            "type": "primary",
            "url": report_url,
        }]})

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title":    {"tag": "plain_text", "content": title},
                "template": _health_color_feishu(score),
            },
            "elements": elements,
        },
    }


async def send_feishu(report: dict, webhook_url: str, keyword: str = "", report_url: str = "") -> dict:
    """发送飞书消息，返回 {"ok": bool, "msg": str}"""
    if report.get("type") == "slowlog":
        payload = _build_feishu_slowlog_card(report, keyword=keyword, report_url=report_url)
    else:
        payload = _build_feishu_card(report, keyword=keyword, report_url=report_url)
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


async def send_dingtalk(report: dict, webhook_url: str, keyword: str = "") -> dict:
    """发送钉钉消息，返回 {"ok": bool, "msg": str}"""
    payload = _build_dingtalk_markdown(report, keyword=keyword)
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
