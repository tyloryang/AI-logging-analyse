"""知识库类工具：Milvus 历史召回 + 历史日报检索。"""
from __future__ import annotations

import glob
import json
import logging
import os
from datetime import datetime, timedelta, timezone

from langchain_core.tools import tool

from ._shared import _REPORTS_DIR

logger = logging.getLogger(__name__)


@tool
async def recall_similar_incidents(query: str, top_k: int = 3) -> str:
    """从历史运维事件库中检索与当前问题语义相似的历史案例（根因分析报告、巡检结论等）。
    分析新问题前优先调用，查看是否有类似历史事件和已知解决方案。
    query=描述当前问题的关键词或问句, top_k=返回最相似的案例数。
    """
    try:
        from agent.milvus_memory import get_memory
        hits = await get_memory().search(query, top_k)
        if hits is None or not hits:
            return "历史事件库中未找到相似案例（库可能为空或 Milvus/Embedding 暂时不可用）。"
        lines = [f"找到 {len(hits)} 条相似历史案例：\n"]
        for i, h in enumerate(hits, 1):
            ts = datetime.fromtimestamp(h["created_at"]).strftime("%Y-%m-%d %H:%M")
            mode_label = {"rca": "根因分析", "inspect": "巡检", "chat": "对话"}.get(h["mode"], h["mode"])
            lines.append(f"【案例 {i}】相似度={h['score']} | {mode_label} | {ts}")
            lines.append(f"  问题：{h['user_query']}")
            if h.get("affected_services"):
                lines.append(f"  涉及：{h['affected_services']}")
            if h.get("root_cause"):
                lines.append(f"  根因：{h['root_cause']}")
            if h.get("resolution"):
                lines.append(f"  处置：{h['resolution']}")
            elif h.get("full_summary"):
                excerpt = h["full_summary"][:400] + ("..." if len(h["full_summary"]) > 400 else "")
                lines.append(f"  详情：{excerpt}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"检索历史案例失败（Milvus 不可用）：{e}"


@tool
async def search_daily_reports(keyword: str = "", days: int = 30, limit: int = 8) -> str:
    """搜索历史运维日报/巡检日报/慢日志报告。
    keyword=关键词或问题描述（支持语义搜索，如"网络故障""磁盘满""calico"）。
    days=搜索最近N天（默认30，0=不限）。
    limit=最多返回条数（默认8）。
    适合：分析历史故障趋势、某服务反复出现的问题、特定时间段系统状况。
    """
    try:
        pattern = os.path.join(_REPORTS_DIR, "*.json")
        files = sorted(glob.glob(pattern), reverse=True)
        kw_lower = keyword.lower().strip()

        if days > 0:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            def _in_range(path: str) -> bool:
                try:
                    ts = "".join(filter(str.isdigit, os.path.basename(path)))[:14]
                    dt = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                    return dt >= cutoff
                except Exception:
                    return True
            files = [f for f in files if _in_range(f)]

        file_matched: list[dict] = []
        for fpath in files:
            try:
                with open(fpath, encoding="utf-8") as fp:
                    report = json.load(fp)
            except Exception:
                continue
            if kw_lower:
                search_text = (
                    report.get("title", "") + " " +
                    report.get("ai_analysis", "") + " " +
                    " ".join(e.get("service", "") for e in report.get("top10_errors", [])) + " " +
                    " ".join(i.get("item", "") for i in report.get("top_issues", []))
                ).lower()
                if kw_lower not in search_text:
                    continue
            file_matched.append(report)
            if len(file_matched) >= limit:
                break

        milvus_hits: list[dict] = []
        if keyword:
            try:
                from agent.report_memory import get_report_memory
                hits = await get_report_memory().search(keyword, top_k=limit)
                if days > 0:
                    import time as _time
                    cutoff_ts = _time.time() - days * 86400
                    hits = [h for h in hits if h.get("created_at", 0) >= cutoff_ts]
                milvus_hits = hits
            except Exception as exc:
                logger.debug("[search_daily_reports] Milvus 搜索失败: %s", exc)

        seen_ids: set[str] = set()
        merged: list[tuple[str, dict]] = []

        for r in file_matched:
            rid = r.get("id", "")
            if rid not in seen_ids:
                seen_ids.add(rid)
                merged.append(("关键词", r))

        for h in milvus_hits:
            rid = h.get("report_id", "")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                merged.append(("语义", {
                    "id":          rid,
                    "title":       h.get("title", ""),
                    "created_at":  "",
                    "health_score": h.get("health_score", "-"),
                    "ai_analysis": h.get("ai_summary", ""),
                    "_top_issues": h.get("top_issues", ""),
                    "_score":      h.get("score", 0),
                    "_type":       h.get("report_type", ""),
                }))

        merged = merged[:limit]

        if not merged:
            scope = f"最近 {days} 天" if days > 0 else "所有时间"
            kw_hint = f"（关键词：{keyword}）" if keyword else ""
            return f"{scope}内未找到匹配的日报{kw_hint}。"

        lines = [f"找到 {len(merged)} 条历史日报（关键词匹配+语义匹配）：\n"]
        for src, r in merged:
            date_str = r.get("created_at", "")[:10] or r.get("date_str", "")
            score = r.get("health_score", "-")
            analysis = r.get("ai_analysis", "")
            summary = analysis[:350].replace("\n", " ") + ("…" if len(analysis) > 350 else "")
            top_issues = (
                ", ".join(e.get("service", "") for e in r.get("top10_errors", [])[:3])
                or ", ".join(i.get("item", "") for i in r.get("top_issues", [])[:3])
                or r.get("_top_issues", "")
                or "无"
            )
            sim_hint = f"  相似度：{r['_score']}" if "_score" in r else ""
            lines.append(
                f"【{r.get('title', date_str)}】[{src}]{sim_hint}\n"
                f"  日期：{date_str}  健康评分：{score}/100\n"
                f"  主要问题：{top_issues}\n"
                f"  分析摘要：{summary}\n"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"搜索历史日报失败：{e}"


__all__ = ["recall_similar_incidents", "search_daily_reports"]
