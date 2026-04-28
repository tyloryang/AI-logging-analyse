"""运维日报 / 巡检日报路由。

路由前缀：/api/report/*
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional

from state import (
    loki, prom, analyzer,
    REPORTS_DIR,
    FEISHU_WEBHOOK, FEISHU_KEYWORD,
    DINGTALK_WEBHOOK, DINGTALK_KEYWORD,
    APP_URL,
    load_slowlog_targets, save_slowlog_targets,
    load_groups, load_cmdb,
)
from notifier import send_feishu, send_dingtalk, send_feishu_group_inspect
from report_builder import collect_inspect_data, build_inspect_meta
from report_store import save_report_meta, list_report_meta

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 运维日报 ──────────────────────────────────────────────────────────────────

class ReportMeta(BaseModel):
    id: str
    title: str
    created_at: str
    health_score: int
    total_logs: int
    total_errors: int
    service_count: int
    active_alerts: int


@router.get("/api/report/generate")
async def generate_report():
    """触发生成运维日报，流式返回 AI 分析内容"""
    try:
        error_counts = await loki.count_errors_by_service(hours=24)
        error_logs   = await loki.query_error_logs(hours=24, limit=1000)

        services          = await loki.get_services()
        total_error_count = sum(error_counts.values())
        total_logs        = total_error_count * 8   # Loki 无法廉价地统计总量，以错误数估算
        active_alerts     = len(error_counts)       # 有错误的服务数

        try:
            hosts       = await prom.discover_hosts()
            node_normal = sum(1 for h in hosts if h.get("state") == "up")
            node_status = {"normal": node_normal, "abnormal": len(hosts) - node_normal}
        except Exception:
            node_status = {"normal": 0, "abnormal": 0}

        health_score = await analyzer.calculate_health_score(
            total_logs, total_error_count, active_alerts, node_status["abnormal"]
        )

        now       = datetime.now(timezone.utc)
        report_id = now.strftime("%Y%m%d%H%M%S")

        meta = {
            "id":            report_id,
            "title":         f"运维日报 {now.strftime('%Y-%m-%d')}",
            "created_at":    now.isoformat(),
            "health_score":  health_score,
            "total_logs":    total_logs,
            "total_errors":  total_error_count,
            "service_count": len(services),
            "active_alerts": active_alerts,
            "node_status":   node_status,
            "top10_errors":  [
                {"service": k, "count": v}
                for k, v in list(error_counts.items())[:10]
            ],
        }

        report_path    = REPORTS_DIR / f"{report_id}.json"
        ai_content_parts: list[str] = []

        async def generate():
            yield f"data: __META__{json.dumps(meta, ensure_ascii=False)}\n\n"
            try:
                async for chunk in analyzer.generate_daily_report(
                    error_counts=error_counts,
                    total_logs=total_logs,
                    service_count=len(services),
                    node_status=node_status,
                    active_alerts=active_alerts,
                    sample_errors=error_logs,
                ):
                    ai_content_parts.append(chunk)
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.exception("日报 AI 生成异常")
                ai_content_parts.append(f"\n[AI生成出错] {exc}")
                yield f"data: {json.dumps('[AI生成出错] ' + str(exc), ensure_ascii=False)}\n\n"
            meta["ai_analysis"] = "".join(ai_content_parts)
            report_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            asyncio.create_task(save_report_meta(meta))
            # 后台写入 Milvus（不阻塞 SSE 流）
            try:
                from agent.report_memory import get_report_memory
                asyncio.create_task(get_report_memory().save(meta))
            except Exception:
                pass
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/report/list")
async def list_reports():
    """历史报告列表（从 DB 查询元数据，不再逐文件读取）"""
    rows = await list_report_meta(limit=50)
    # DB 为空时降级到文件扫描（首次启动 sync 尚未完成的容错）
    if not rows:
        for p in sorted(REPORTS_DIR.glob("*.json"), reverse=True)[:50]:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                rows.append({k: data[k] for k in [
                    "id", "type", "title", "created_at", "health_score",
                    "total_logs", "total_errors", "service_count", "active_alerts",
                    "total_queries", "alert_queries", "hosts_count",
                ] if k in data})
            except Exception:
                pass
    return {"data": rows}


# ── 巡检日报 ──────────────────────────────────────────────────────────────────

UNGROUPED_GROUP_ID = "__ungrouped__"
UNGROUPED_GROUP_NAME = "未分组"


def _build_inspect_summary(results: list[dict], group_name: str = "") -> dict:
    total = len(results)
    summary = {
        "total": total,
        "normal": sum(1 for r in results if r.get("overall") == "normal"),
        "warning": sum(1 for r in results if r.get("overall") == "warning"),
        "critical": sum(1 for r in results if r.get("overall") == "critical"),
        "cmdb_total": total,
        "prometheus_extra_count": 0,
        "scope": "cmdb",
    }
    summary["scope_note"] = f"统计口径：按 CMDB 主机 {total} 台统计，正常/警告/严重数量均以 CMDB 主机为基准。"
    if group_name:
        summary["group_name"] = group_name
    return summary


def _build_inspect_top_issues(results: list[dict]) -> list[dict]:
    issue_cnt: dict[str, int] = {}
    for r in results:
        for c in r.get("checks", []):
            if c.get("status") != "normal":
                item = c.get("item", "未知")
                issue_cnt[item] = issue_cnt.get(item, 0) + 1
    return [{"item": k, "count": v} for k, v in sorted(issue_cnt.items(), key=lambda x: x[1], reverse=True)[:10]]


def _sort_abnormal_hosts(results: list[dict]) -> list[dict]:
    abnormal_hosts = [r for r in results if r.get("overall") != "normal"]
    abnormal_hosts.sort(
        key=lambda r: {"critical": 2, "warning": 1}.get(r.get("overall", "normal"), 0),
        reverse=True,
    )
    return abnormal_hosts


def _append_missing_cmdb_hosts(results: list[dict], group_id: str = "") -> list[dict]:
    cmdb = load_cmdb()
    expected = [
        {"ip": ip, **meta}
        for ip, meta in cmdb.items()
        if not group_id or meta.get("group") == group_id
    ]
    found_ips = {
        (r.get("ip") or r.get("instance", "").split(":")[0]).strip()
        for r in results
        if (r.get("ip") or r.get("instance"))
    }
    merged = list(results)
    for host in expected:
        ip = (host.get("ip") or "").strip()
        if not ip or ip in found_ips:
            continue
        merged.append({
            "instance": ip,
            "ip": ip,
            "hostname": host.get("hostname") or ip,
            "os": host.get("os") or host.get("platform", ""),
            "job": "",
            "state": "missing",
            "overall": "critical",
            "checks": [{
                "item": "Prometheus 监控",
                "value": "未发现该主机监控数据",
                "status": "critical",
                "threshold": "应存在可抓取 target",
            }],
            "metrics": {},
            "partitions": [],
        })
    merged.sort(
        key=lambda r: {"critical": 2, "warning": 1}.get(r.get("overall", "normal"), 0),
        reverse=True,
    )
    return merged


def _inspect_health_score(summary: dict) -> int:
    total = summary.get("total", 0)
    if total <= 0:
        return 100
    score = 100
    score -= min(40, int(summary.get("critical", 0) / total * 200))
    score -= min(30, int(summary.get("warning", 0) / total * 100))
    return max(0, score)


def _group_inspect_results(results: list[dict]) -> list[dict]:
    groups = load_groups()
    group_order = {g["id"]: idx for idx, g in enumerate(groups)}
    group_names = {g["id"]: g.get("name", g["id"]) for g in groups}
    cmdb = load_cmdb()

    grouped: dict[str, dict] = {}
    for result in results:
        ip = (result.get("ip") or result.get("instance", "").split(":")[0]).strip()
        host_meta = cmdb.get(ip, {})
        raw_group_id = (host_meta.get("group") or "").strip()
        key = raw_group_id or UNGROUPED_GROUP_ID
        group_name = group_names.get(raw_group_id, raw_group_id) if raw_group_id else UNGROUPED_GROUP_NAME
        bucket = grouped.setdefault(key, {
            "group_id": "" if key == UNGROUPED_GROUP_ID else key,
            "group_name": group_name,
            "sort_index": group_order.get(raw_group_id, len(group_order) + (1 if raw_group_id else 2)),
            "results": [],
        })
        bucket["results"].append(result)

    return sorted(grouped.values(), key=lambda item: (item["sort_index"], item["group_name"]))


def _group_ai_fallback(group_name: str, summary: dict) -> str:
    return (
        f"分组「{group_name}」共 {summary.get('total', 0)} 台主机，"
        f"正常 {summary.get('normal', 0)} 台、告警 {summary.get('warning', 0)} 台、"
        f"严重 {summary.get('critical', 0)} 台。"
        "建议优先处理严重主机和高频异常项。"
    )


async def _build_group_analyses(grouped_results: list[dict]) -> list[dict]:
    analyses = []
    for item in grouped_results:
        summary = _build_inspect_summary(item["results"], item["group_name"])
        ai_parts: list[str] = []
        try:
            async for chunk in analyzer.generate_inspection_summary(item["results"], summary):
                ai_parts.append(chunk)
            ai_text = "".join(ai_parts).strip()
        except Exception as exc:
            logger.warning("分组 %s AI 分析生成失败: %s", item["group_name"], exc)
            ai_text = _group_ai_fallback(item["group_name"], summary)

        analyses.append({
            "group_id": item["group_id"],
            "group_name": item["group_name"],
            "host_summary": summary,
            "top_issues": _build_inspect_top_issues(item["results"]),
            "abnormal_hosts": _sort_abnormal_hosts(item["results"])[:20],
            "health_score": _inspect_health_score(summary),
            "ai_analysis": ai_text,
        })
    return analyses


def _compose_group_ai_text(group_analyses: list[dict]) -> str:
    sections: list[str] = []
    for item in group_analyses:
        summary = item.get("host_summary", {})
        header = (
            f"【分组：{item.get('group_name') or UNGROUPED_GROUP_NAME}】\n"
            f"主机 {summary.get('total', 0)} 台，正常 {summary.get('normal', 0)} 台，"
            f"告警 {summary.get('warning', 0)} 台，严重 {summary.get('critical', 0)} 台"
        )
        body = (item.get("ai_analysis") or "").strip() or "暂无 AI 分析结果"
        sections.append(f"{header}\n{body}")
    return "\n\n".join(sections).strip()


def _build_group_report_from_inspect(report: dict, group_analysis: dict, group_results: list[dict]) -> dict:
    created_at = report.get("created_at", "")
    date_text = created_at[:10] if created_at else ""
    group_name = group_analysis.get("group_name") or UNGROUPED_GROUP_NAME
    summary = group_analysis.get("host_summary") or _build_inspect_summary(group_results, group_name)
    return {
        "id": report.get("id", ""),
        "type": "inspect",
        "group_id": group_analysis.get("group_id", ""),
        "group_name": group_name,
        "title": f"主机巡检日报【{group_name}】 {date_text}".strip(),
        "created_at": created_at,
        "health_score": group_analysis.get("health_score", _inspect_health_score(summary)),
        "host_summary": summary,
        "top_issues": group_analysis.get("top_issues") or _build_inspect_top_issues(group_results),
        "abnormal_hosts": group_analysis.get("abnormal_hosts") or _sort_abnormal_hosts(group_results)[:20],
        "all_hosts": group_results,
        "prometheus_extra_hosts": [],
        "prometheus_extra_count": 0,
        "summary_scope_note": summary.get("scope_note", ""),
        "ai_analysis": (group_analysis.get("ai_analysis") or "").strip() or report.get("ai_analysis", ""),
        "group_analyses": [group_analysis],
    }


def _split_inspect_report_by_group(report: dict) -> dict[str, dict]:
    if report.get("group_id"):
        return {report.get("group_id", ""): report}

    all_hosts = report.get("all_hosts", [])
    if not all_hosts:
        return {}

    grouped_results = _group_inspect_results(all_hosts)
    analyses = {
        (item.get("group_id") or UNGROUPED_GROUP_ID): item
        for item in (report.get("group_analyses") or [])
    }

    split_reports: dict[str, dict] = {}
    for item in grouped_results:
        key = item["group_id"] or UNGROUPED_GROUP_ID
        analysis = analyses.get(key, {
            "group_id": item["group_id"],
            "group_name": item["group_name"],
            "host_summary": _build_inspect_summary(item["results"], item["group_name"]),
            "top_issues": _build_inspect_top_issues(item["results"]),
            "abnormal_hosts": _sort_abnormal_hosts(item["results"])[:20],
            "health_score": _inspect_health_score(_build_inspect_summary(item["results"], item["group_name"])),
            "ai_analysis": "",
        })
        split_reports[item["group_id"]] = _build_group_report_from_inspect(report, analysis, item["results"])
    return split_reports


@router.get("/api/report/inspect/generate")
async def generate_inspect_report(group_id: Optional[str] = Query(None)):
    """生成主机巡检日报，流式返回 AI 分析；可通过 group_id 限定分组"""
    try:
        group_name = ""
        if group_id:
            groups = load_groups()
            g = next((g for g in groups if g["id"] == group_id), None)
            group_name = g["name"] if g else group_id
        data = await collect_inspect_data(group_id=group_id or "", group_name=group_name)
        results = data["results"]
        summary = data["summary"]
        top_issues = data["top_issues"]
        abnormal_hosts = data["abnormal_hosts"]
        all_hosts_brief = data["all_hosts"]
        health_score = data["health_score"]
        meta = build_inspect_meta(data, group_id or "", group_name)

        report_path = REPORTS_DIR / f"{meta['id']}.json"
        async def generate():
            yield f"data: __META__{json.dumps(meta, ensure_ascii=False)}\n\n"
            if group_id:
                ai_parts: list[str] = []
                try:
                    async for chunk in analyzer.generate_host_inspect_report(results, summary):
                        ai_parts.append(chunk)
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                except Exception as exc:
                    logger.exception("巡检日报 AI 生成异常")
                    ai_parts.append(f"\n[AI生成出错] {exc}")
                    yield f"data: {json.dumps('[AI生成出错] ' + str(exc), ensure_ascii=False)}\n\n"
                ai_text = "".join(ai_parts).strip()
                meta["group_analyses"] = [{
                    "group_id": group_id or "",
                    "group_name": group_name or UNGROUPED_GROUP_NAME,
                    "host_summary": summary,
                    "top_issues": top_issues,
                    "abnormal_hosts": abnormal_hosts[:20],
                    "health_score": health_score,
                    "ai_analysis": ai_text,
                }]
                meta["ai_analysis"] = ai_text
            else:
                grouped_results = _group_inspect_results(all_hosts_brief)
                if not grouped_results:
                    meta["group_analyses"] = []
                    meta["ai_analysis"] = "未找到可用于分组分析的主机数据。"
                    yield f"data: {json.dumps(meta['ai_analysis'], ensure_ascii=False)}\n\n"
                else:
                    group_analyses = await _build_group_analyses(grouped_results)
                    combined_text = _compose_group_ai_text(group_analyses)
                    meta["group_analyses"] = group_analyses
                    meta["ai_analysis"] = combined_text
                    for chunk in [combined_text[i:i + 800] for i in range(0, len(combined_text), 800)]:
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            report_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            asyncio.create_task(save_report_meta(meta))
            # 后台写入 Milvus
            try:
                from agent.report_memory import get_report_memory
                asyncio.create_task(get_report_memory().save(meta))
            except Exception:
                pass
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _find_latest_group_inspect_report(group_id: str) -> Optional[dict]:
    """在 REPORTS_DIR 中找到指定分组最新的、已含 AI 分析的巡检报告，没有则返回 None"""
    best = None
    for p in sorted(REPORTS_DIR.glob("inspect_*.json"), reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if data.get("type") == "inspect" and data.get("group_id") == group_id and data.get("ai_analysis"):
                best = data
                break   # 按文件名倒序，第一个即最新
        except Exception:
            continue
    return best


@router.post("/api/report/inspect/generate-groups")
async def generate_inspect_report_all_groups():
    """为每个配置了飞书 webhook 的分组生成巡检报告并推送。
    优先复用已有 AI 分析的最新报告；若不存在则重新采集并生成 AI 后推送。"""
    groups = load_groups()
    cmdb   = load_cmdb()

    results = []
    for group in groups:
        webhook = group.get("feishu_webhook", "")
        if not webhook:
            results.append({"group_id": group["id"], "group_name": group.get("name", ""), "skipped": True, "reason": "未配置飞书 webhook"})
            continue

        group_id   = group["id"]
        group_name = group.get("name", group_id)
        keyword    = group.get("feishu_keyword", "")

        instances = [inst for inst, meta in cmdb.items() if meta.get("group") == group_id]
        if not instances:
            results.append({"group_id": group_id, "group_name": group_name, "skipped": True, "reason": "该分组无主机"})
            continue

        try:
            # ① 优先使用已有报告（有 AI 分析）
            existing = _find_latest_group_inspect_report(group_id)
            if existing:
                host_results = existing.get("all_hosts", [])
                ai_text      = existing.get("ai_analysis", "")
                source       = "cached"
            else:
                # ② 重新采集 + 生成 AI + 保存报告
                inspect_data = await collect_inspect_data(
                    instances=instances,
                    group_id=group_id,
                    group_name=group_name,
                )
                full_results = inspect_data["results"]
                summary = inspect_data["summary"]
                ai_parts: list[str] = []
                try:
                    async for chunk in analyzer.generate_host_inspect_report(full_results, summary):
                        ai_parts.append(chunk)
                except Exception as ai_exc:
                    logger.warning("分组 %s AI生成失败: %s", group_name, ai_exc)
                ai_text = "".join(ai_parts)
                meta_g = build_inspect_meta(inspect_data, group_id, group_name)
                meta_g["ai_analysis"] = ai_text
                meta_g["group_analyses"] = [{
                    "group_id": group_id,
                    "group_name": group_name,
                    "host_summary": summary,
                    "top_issues": inspect_data["top_issues"],
                    "abnormal_hosts": inspect_data["abnormal_hosts"],
                    "health_score": inspect_data["health_score"],
                    "ai_analysis": ai_text,
                }]
                try:
                    (REPORTS_DIR / f"{meta_g['id']}.json").write_text(
                        json.dumps(meta_g, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    asyncio.create_task(save_report_meta(meta_g))
                except Exception as save_exc:
                    logger.warning("分组 %s 报告保存失败: %s", group_name, save_exc)

                # 推送时使用完整巡检结果（含 checks 字段）
                host_results = full_results
                source = "generated"

            push_result = await send_feishu_group_inspect(
                group_name, host_results, webhook, keyword=keyword, ai_text=ai_text
            )
            results.append({
                "group_id":   group_id,
                "group_name": group_name,
                "hosts":      len(host_results),
                "source":     source,
                "push":       push_result,
            })
        except Exception as exc:
            logger.exception("分组 %s 巡检推送失败", group_name)
            results.append({"group_id": group_id, "group_name": group_name, "error": str(exc)})

    return {"results": results}


@router.get("/api/report/inspect/{report_id}/excel")
async def download_inspect_report_excel(report_id: str):
    """下载主机巡检日报 Excel 文件"""
    p = REPORTS_DIR / f"{report_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("type") != "inspect":
        raise HTTPException(status_code=400, detail="该报告不是巡检类型")

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        import io

        wb = Workbook()

        STATUS_COLOR = {"normal": "FF67C23A", "warning": "FFE6A23C", "critical": "FFF56C6C"}
        STATUS_TEXT  = {"normal": "正常", "warning": "警告", "critical": "严重"}

        def header_fill(color="FF1F3A5F"):
            return PatternFill("solid", fgColor=color)

        def thin_border():
            s = Side(style="thin", color="FFCCCCCC")
            return Border(left=s, right=s, top=s, bottom=s)

        def set_col_widths(ws, widths):
            for i, w in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = w

        def write_header_row(ws, headers, row=1):
            for col, h in enumerate(headers, 1):
                c = ws.cell(row=row, column=col, value=h)
                c.font      = Font(bold=True, color="FFFFFFFF", size=10)
                c.fill      = header_fill()
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                c.border    = thin_border()

        def write_data_cell(ws, row, col, value, status=None):
            c           = ws.cell(row=row, column=col, value=value)
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border    = thin_border()
            if status and status in STATUS_COLOR:
                c.fill = PatternFill("solid", fgColor=STATUS_COLOR[status])
                c.font = Font(color="FFFFFFFF", size=9)
            else:
                c.font = Font(size=9)
            return c

        summary_d  = data.get("host_summary", {})
        all_hosts  = data.get("all_hosts", [])
        top_issues = data.get("top_issues", [])
        ai_text    = data.get("ai_analysis", "")
        title      = data.get("title", "主机巡检日报")
        created    = data.get("created_at", "")[:19].replace("T", " ")

        # Sheet 1: 巡检概况
        ws1 = wb.active
        ws1.title = "巡检概况"
        ws1.column_dimensions["A"].width = 22
        ws1.column_dimensions["B"].width = 40

        def s1_row(r, k, v, bold=False):
            ck = ws1.cell(row=r, column=1, value=k)
            cv = ws1.cell(row=r, column=2, value=v)
            ck.font      = Font(bold=True, color="FFFFFFFF", size=10)
            ck.fill      = header_fill("FF243850")
            cv.font      = Font(bold=bold, size=10)
            ck.alignment = cv.alignment = Alignment(vertical="center", wrap_text=True)
            ck.border    = cv.border    = thin_border()
            ws1.row_dimensions[r].height = 18

        s1_row(1, "报告名称",     title, bold=True)
        s1_row(2, "生成时间",     created)
        s1_row(3, "健康评分",     f"{data.get('health_score', '-')}/100")
        s1_row(4, "巡检主机总数", summary_d.get("total", 0))
        s1_row(5, "正常主机",     summary_d.get("normal", 0))
        s1_row(6, "警告主机",     summary_d.get("warning", 0))
        s1_row(7, "严重主机",     summary_d.get("critical", 0))

        ws1.cell(row=9, column=1, value="高频异常项").font = Font(bold=True, size=10)
        write_header_row(ws1, ["异常检查项", "影响主机数"], row=10)
        for i, issue in enumerate(top_issues, 11):
            ws1.cell(row=i, column=1, value=issue.get("item", "")).border    = thin_border()
            ws1.cell(row=i, column=2, value=issue.get("count", 0)).border    = thin_border()
            ws1.cell(row=i, column=1).font      = Font(size=9)
            ws1.cell(row=i, column=2).font      = Font(size=9)
            ws1.cell(row=i, column=1).alignment = Alignment(vertical="center")
            ws1.cell(row=i, column=2).alignment = Alignment(horizontal="center", vertical="center")

        ai_start = 11 + len(top_issues) + 2
        ws1.cell(row=ai_start, column=1, value="AI 分析总结").font = Font(bold=True, size=10)
        if ai_text:
            c           = ws1.cell(row=ai_start + 1, column=1, value=ai_text)
            c.font      = Font(size=9)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border    = thin_border()
            ws1.merge_cells(
                start_row=ai_start + 1, start_column=1,
                end_row=ai_start + 1,   end_column=2,
            )
            ws1.row_dimensions[ai_start + 1].height = max(60, len(ai_text) // 3)

        # Sheet 2: 全部主机明细
        ws2 = wb.create_sheet("全部主机明细")
        headers2 = [
            "主机名", "IP地址", "操作系统", "状态", "巡检结果",
            "CPU使用率(%)", "内存使用率(%)", "内存总量(GB)",
            "负载(5m)", "网络收(Mbps)", "网络发(Mbps)",
            "TCP连接数", "运行时长(天)", "磁盘分区详情",
        ]
        write_header_row(ws2, headers2)
        set_col_widths(ws2, [18, 16, 22, 10, 10, 14, 14, 14, 10, 14, 14, 12, 12, 40])
        ws2.row_dimensions[1].height = 22

        for ri, h in enumerate(all_hosts, 2):
            overall      = h.get("overall", "normal")
            status_label = STATUS_TEXT.get(overall, overall)

            def fmt(v, decimals=1):
                return round(v, decimals) if v is not None else "-"

            uptime_days = "-"
            us = h.get("uptime_s")
            if us is not None:
                uptime_days = round(us / 86400, 1)

            partitions = h.get("partitions") or []
            disk_text  = "  ".join(
                f"{pt.get('mountpoint','?')} {pt.get('usage_pct','-')}%"
                for pt in partitions
            ) if partitions else "-"

            row_vals = [
                h.get("hostname", "-"), h.get("ip", "-"), h.get("os", "-"),
                h.get("state", "-"), status_label,
                fmt(h.get("cpu_pct")), fmt(h.get("mem_pct")), fmt(h.get("mem_total")),
                fmt(h.get("load5")), fmt(h.get("net_recv")), fmt(h.get("net_send")),
                h.get("tcp_estab") or "-", uptime_days, disk_text,
            ]
            for ci, val in enumerate(row_vals, 1):
                st = overall if ci == 5 else None
                write_data_cell(ws2, ri, ci, val, st)
            ws2.row_dimensions[ri].height = 16

        ws2.freeze_panes = "A2"

        # Sheet 3: 异常项明细
        ws3 = wb.create_sheet("异常项明细")
        headers3 = ["主机名", "IP地址", "检查项", "当前值", "状态", "阈值说明"]
        write_header_row(ws3, headers3)
        set_col_widths(ws3, [18, 16, 20, 20, 10, 30])
        ws3.row_dimensions[1].height = 22

        ri3 = 2
        for h in all_hosts:
            for ck in [c for c in h.get("checks", []) if c.get("status") != "normal"]:
                status = ck.get("status", "warning")
                row3 = [
                    h.get("hostname", "-"), h.get("ip", "-"),
                    ck.get("item", "-"), ck.get("value", "-"),
                    STATUS_TEXT.get(status, status), ck.get("threshold", "-"),
                ]
                for ci, val in enumerate(row3, 1):
                    write_data_cell(ws3, ri3, ci, val, status if ci == 5 else None)
                ws3.row_dimensions[ri3].height = 16
                ri3 += 1

        ws3.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename     = f"巡检日报_{report_id}.xlsx"
        encoded_name = quote(filename, encoding="utf-8")
        return Response(
            content=buf.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
        )
    except Exception as e:
        logger.exception("Excel 导出失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/report/{report_id}")
async def get_report(report_id: str):
    """获取指定报告详情"""
    p = REPORTS_DIR / f"{report_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    return json.loads(p.read_text(encoding="utf-8"))


# ── 通知推送 ──────────────────────────────────────────────────────────────────

class NotifyRequest(BaseModel):
    channels: list[str]  # ["feishu", "dingtalk"]


@router.post("/api/report/{report_id}/notify")
async def notify_report(report_id: str, body: NotifyRequest):
    """将指定报告推送到飞书 / 钉钉"""
    p = REPORTS_DIR / f"{report_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    report     = json.loads(p.read_text(encoding="utf-8"))
    report_url = f"{APP_URL}/report/{report_id}" if APP_URL else ""

    results = {}
    for ch in body.channels:
        if ch == "feishu":
            if not FEISHU_WEBHOOK:
                results["feishu"] = {"ok": False, "msg": "未配置 FEISHU_WEBHOOK"}
            else:
                results["feishu"] = await send_feishu(
                    report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD, report_url=report_url
                )
        elif ch == "dingtalk":
            if not DINGTALK_WEBHOOK:
                results["dingtalk"] = {"ok": False, "msg": "未配置 DINGTALK_WEBHOOK"}
            else:
                results["dingtalk"] = await send_dingtalk(
                    report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD
                )
        else:
            results[ch] = {"ok": False, "msg": f"不支持的渠道: {ch}"}

    return {"results": results}


@router.post("/api/report/{report_id}/notify-groups")
async def notify_report_groups(report_id: str, group_id: Optional[str] = Query(None)):
    """将指定报告推送到分组。
    若传入 group_id 则只推送该分组；否则推送所有已配置 webhook 的分组。"""
    p = REPORTS_DIR / f"{report_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    report     = json.loads(p.read_text(encoding="utf-8"))
    report_url = f"{APP_URL}/report/{report_id}" if APP_URL else ""

    all_groups = load_groups()
    group_reports = _split_inspect_report_by_group(report) if report.get("type") == "inspect" else {}
    # 若指定分组则只取该分组，否则取全部
    target_groups = [g for g in all_groups if g["id"] == group_id] if group_id else all_groups

    results = []
    for group in target_groups:
        gid        = group["id"]
        group_name = group.get("name", gid)
        pushed: dict[str, dict] = {}
        payload_report = group_reports.get(gid, report) if group_reports else report

        if report.get("type") == "inspect" and group_reports and gid not in group_reports:
            results.append({"group_id": gid, "group_name": group_name, "skipped": True, "reason": "该分组在当前报告中无主机"})
            continue

        feishu_wh = group.get("feishu_webhook", "")
        if feishu_wh:
            keyword = group.get("feishu_keyword", FEISHU_KEYWORD)
            pushed["feishu"] = await send_feishu(payload_report, feishu_wh, keyword=keyword, report_url=report_url)

        dingtalk_wh = group.get("dingtalk_webhook", "")
        if dingtalk_wh:
            keyword = group.get("dingtalk_keyword", DINGTALK_KEYWORD)
            pushed["dingtalk"] = await send_dingtalk(payload_report, dingtalk_wh, keyword=keyword)

        if not pushed:
            results.append({"group_id": gid, "group_name": group_name, "skipped": True, "reason": "未配置 webhook"})
        else:
            results.append({"group_id": gid, "group_name": group_name, "push": pushed})

    return {"results": results}


# ── 慢日志分析报告 ─────────────────────────────────────────────────────────────

class SlowlogTargetsConfig(BaseModel):
    enabled:       bool  = False
    date_days:     int   = 1
    threshold_sec: float = 1.0
    alert_sec:     float = 10.0
    targets:       list  = []


@router.get("/api/report/slowlog/targets")
async def get_slowlog_targets():
    """获取慢日志定时报告目标配置"""
    return load_slowlog_targets()


@router.put("/api/report/slowlog/targets")
async def put_slowlog_targets(body: SlowlogTargetsConfig):
    """保存慢日志定时报告目标配置"""
    save_slowlog_targets(body.model_dump())
    return {"ok": True}


@router.get("/api/report/slowlog/generate")
async def generate_slowlog_report():
    """根据已保存的目标配置生成慢日志分析报告，SSE 流式返回"""
    from report_builder import collect_slowlog_data, build_slowlog_ai_prompt

    config = load_slowlog_targets()
    if not config.get("targets"):
        raise HTTPException(400, detail="未配置慢日志分析目标，请先在「慢日志报告 · 配置目标」中添加主机")

    async def generate():
        data = await collect_slowlog_data(config)
        if data is None:
            yield f"data: {json.dumps('未找到满足条件的慢查询记录', ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        meta = {k: v for k, v in data.items() if not k.startswith("_")}
        yield f"data: __META__{json.dumps(meta, ensure_ascii=False)}\n\n"

        if not data.get("_all_entries"):
            meta["ai_analysis"] = "未找到满足条件的慢查询记录，请检查目标主机、日志路径及时间范围配置。"
            (REPORTS_DIR / f"{meta['id']}.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            asyncio.create_task(save_report_meta(meta))
            yield "data: [DONE]\n\n"
            return

        prompt = build_slowlog_ai_prompt(data)
        ai_parts: list[str] = []
        try:
            async for chunk in analyzer.provider.stream(prompt, max_tokens=3000):
                ai_parts.append(chunk)
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("[slowlog_report] AI 生成异常")
            ai_parts.append(f"\n[AI生成出错] {exc}")
            yield f"data: {json.dumps('[AI生成出错] ' + str(exc), ensure_ascii=False)}\n\n"

        meta["ai_analysis"] = "".join(ai_parts)
        (REPORTS_DIR / f"{meta['id']}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        asyncio.create_task(save_report_meta(meta))
        try:
            from agent.report_memory import get_report_memory
            asyncio.create_task(get_report_memory().save(meta))
        except Exception:
            pass
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
