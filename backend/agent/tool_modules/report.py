"""报告导出工具：触发后端报告生成 + 返回 PDF 下载链接。"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
async def export_report_pdf(report_type: str = "daily") -> str:
    """生成运维报告并导出为可下载的 PDF（HTML 格式，浏览器打印即可存为 PDF）。
    report_type: 'daily'=运维日报（默认），'inspect'=主机巡检报告。
    用户说「生成PDF报告」「导出报告」「生成运维日报PDF」时调用。
    返回报告摘要和下载链接。
    """
    import httpx as _httpx
    from state import APP_URL as _APP_URL

    base_url = (_APP_URL or "http://localhost:8000").rstrip("/")

    try:
        if report_type == "inspect":
            gen_url = f"{base_url}/api/report/inspect/generate"
        else:
            gen_url = f"{base_url}/api/report/generate"

        report_id = None
        title = ""
        score = 0
        errors = 0

        async with _httpx.AsyncClient(timeout=120) as client:
            async with client.stream("GET", gen_url) as resp:
                if resp.status_code != 200:
                    return f"报告生成失败（HTTP {resp.status_code}）"
                async for line in resp.aiter_lines():
                    if line.startswith("data: __META__"):
                        import json as _json
                        try:
                            meta = _json.loads(line[len("data: __META__"):])
                            report_id = meta.get("id")
                            title = meta.get("title", "")
                            score = meta.get("health_score", 0)
                            errors = meta.get("total_errors", 0)
                        except Exception:
                            pass
                    elif line == "data: [DONE]":
                        break

        if not report_id:
            return "报告生成成功，但未获取到报告 ID，请在「分析报告」页面手动下载。"

        download_url = f"{base_url}/api/report/{report_id}/export.html"
        return (
            f"✅ 报告已生成：**{title}**\n\n"
            f"- 健康评分：{score}/100\n"
            f"- 错误数：{errors}\n\n"
            f"📄 **PDF 下载链接**（浏览器打开后按 Ctrl+P → 另存为 PDF）：\n"
            f"{download_url}\n\n"
            f"或在「分析报告」页面找到该报告，点击「导出 PDF」按钮。"
        )
    except Exception as e:
        return f"报告生成异常：{e}"


__all__ = ["export_report_pdf"]
