

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


def _build_feishu_inspect_card(report: dict, keyword: str = "", report_url: str = "") -> dict:
    """构造巡检日报飞书交互卡片（用于 /notify 接口推送已生成的报告）"""
    score   = report.get("health_score", 0)
    title   = report.get("title", "主机巡检日报")
    summary = report.get("host_summary", {})
    ai      = (report.get("ai_analysis") or "").strip()
    scope_note = (report.get("summary_scope_note") or summary.get("scope_note") or "").strip()
    extra_hosts = report.get("prometheus_extra_hosts", []) or []

    total    = summary.get("total", 0)
    normal   = summary.get("normal", 0)
    warning  = summary.get("warning", 0)
    critical = summary.get("critical", 0)

    summary_line = (
        f"**主机总数**: {total}  "
        f"**正常**: {normal}  "
        f"**警告**: {warning}  "
        f"**严重**: {critical}"
    )
    header_content = f"{_health_emoji(score)} **健康评分**: {score}/100\n{summary_line}"
    if keyword and keyword not in header_content and keyword not in title:
        header_content = keyword + "\n" + header_content

    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": header_content}}]

    if scope_note:
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": f"**统计口径**\n{scope_note}"}})

    if extra_hosts:
        lines = []
        for item in extra_hosts[:8]:
            label = item.get("hostname") or item.get("job") or item.get("instance") or item.get("ip") or "unknown"
            lines.append(f"- `{item.get('ip') or item.get('instance', '-')}` · {label}")
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": "**Prometheus 额外发现的非 CMDB 实例**\n" + "\n".join(lines),
        }})

    # 告警主机
    abnormal = report.get("abnormal_hosts", [])
    if abnormal:
        lines = []
        for r in abnormal[:10]:
            status_icon = "🔴" if r.get("overall") == "critical" else "🟡"
            hostname = r.get("hostname") or r.get("ip") or r.get("instance", "?")
            issues = [c["item"] for c in r.get("checks", []) if c.get("status") != "normal"]
            issue_text = "、".join(issues[:3]) + ("…" if len(issues) > 3 else "")
            lines.append(f"{status_icon} **{hostname}** — {issue_text}")
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": "**⚠️ 告警主机**\n" + "\n".join(lines),
        }})

    if ai:
        ai_excerpt = ai[:800] + ("..." if len(ai) > 800 else "")
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


def _build_feishu_group_inspect_card(
    group_name: str,
    results: list[dict],
    keyword: str = "",
    ai_text: str = "",
) -> dict:
    """构造按分组的主机巡检飞书告警卡片"""
    total    = len(results)
    normal   = sum(1 for r in results if r.get("overall") == "normal")
    warning  = sum(1 for r in results if r.get("overall") == "warning")
    critical = sum(1 for r in results if r.get("overall") == "critical")

    score = int(100 * normal / total) if total else 100
    color = _health_color_feishu(score)
    emoji = _health_emoji(score)

    summary_line = (
        f"**主机总数**: {total}  "
        f"**正常**: {normal}  "
        f"**警告**: {warning}  "
        f"**严重**: {critical}"
    )
    header_content = f"{emoji} **健康评分**: {score}/100\n{summary_line}"
    if keyword and keyword not in header_content:
        header_content = keyword + "\n" + header_content

    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": header_content}}]

    # 列出告警主机（warning + critical）
    alert_hosts = [r for r in results if r.get("overall") != "normal"]
    if alert_hosts:
        lines = []
        for r in alert_hosts[:10]:
            status_icon = "🔴" if r.get("overall") == "critical" else "🟡"
            hostname = r.get("hostname") or r.get("ip") or r.get("instance", "?")
            issues = [
                c["item"] for c in r.get("checks", [])
                if c.get("status") != "normal"
            ]
            issue_text = "、".join(issues[:3]) + ("…" if len(issues) > 3 else "")
            lines.append(f"{status_icon} **{hostname}** — {issue_text}")
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": "**⚠️ 告警主机**\n" + "\n".join(lines),
        }})

    if ai_text:
        ai_excerpt = ai_text.strip()[:800] + ("..." if len(ai_text) > 800 else "")
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {
            "tag": "lark_md",
            "content": f"**🤖 AI 分析**\n{ai_excerpt}",
        }})

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"🔍 主机巡检 · {group_name}"},
                "template": color,
            },
            "elements": elements,
        },
    }


async def send_feishu_group_inspect(
    group_name: str,
    results: list[dict],
    webhook_url: str,
    keyword: str = "",
    ai_text: str = "",
) -> dict:
    """按分组发送主机巡检告警到飞书群"""
    payload = _build_feishu_group_inspect_card(group_name, results, keyword=keyword, ai_text=ai_text)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", -1) == 0:
                return {"ok": True, "msg": "发送成功"}
            return {"ok": False, "msg": data.get("msg", str(data))}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


async def send_feishu(report: dict, webhook_url: str, keyword: str = "", report_url: str = "") -> dict:
    """发送飞书消息，返回 {"ok": bool, "msg": str}"""
    if report.get("type") == "slowlog":
        payload = _build_feishu_slowlog_card(report, keyword=keyword, report_url=report_url)
    elif report.get("type") == "inspect":
        payload = _build_feishu_inspect_card(report, keyword=keyword, report_url=report_url)
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
