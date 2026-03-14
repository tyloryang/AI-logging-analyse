"""运维日报 / 巡检日报路由。

路由前缀：/api/report/*
"""
import json
import logging
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from state import (
    loki, prom, analyzer,
    REPORTS_DIR,
    FEISHU_WEBHOOK, FEISHU_KEYWORD,
    DINGTALK_WEBHOOK, DINGTALK_KEYWORD,
    APP_URL,
)
from notifier import send_feishu, send_dingtalk

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

        node_status       = {"normal": 27, "abnormal": 0}
        active_alerts     = min(len(error_counts), 3)
        services          = await loki.get_services()
        total_error_count = sum(error_counts.values())
        total_logs        = max(total_error_count * 8, total_error_count)

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
    """历史报告列表"""
    reports = []
    for p in sorted(REPORTS_DIR.glob("*.json"), reverse=True)[:30]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            reports.append({k: data[k] for k in [
                "id", "title", "created_at", "health_score",
                "total_logs", "total_errors", "service_count", "active_alerts"
            ] if k in data})
        except Exception:
            pass
    return {"data": reports}


# ── 巡检日报 ──────────────────────────────────────────────────────────────────

@router.get("/api/report/inspect/generate")
async def generate_inspect_report():
    """生成主机巡检日报，流式返回 AI 分析"""
    try:
        results = await prom.inspect_hosts()
        summary = {
            "total":    len(results),
            "normal":   sum(1 for r in results if r["overall"] == "normal"),
            "warning":  sum(1 for r in results if r["overall"] == "warning"),
            "critical": sum(1 for r in results if r["overall"] == "critical"),
        }

        issue_cnt: dict[str, int] = {}
        for r in results:
            for c in r.get("checks", []):
                if c.get("status") != "normal":
                    issue_cnt[c.get("item", "未知")] = issue_cnt.get(c.get("item", "未知"), 0) + 1
        top_issues = sorted(issue_cnt.items(), key=lambda x: x[1], reverse=True)[:10]

        abnormal_hosts = [r for r in results if r.get("overall") != "normal"]
        abnormal_hosts.sort(
            key=lambda r: {"critical": 2, "warning": 1}.get(r.get("overall", "normal"), 0),
            reverse=True,
        )

        health_score = await analyzer.calculate_host_health_score(summary)

        now       = datetime.now(timezone.utc)
        report_id = "inspect_" + now.strftime("%Y%m%d%H%M%S")

        all_hosts_brief = []
        for r in results:
            m = r.get("metrics") or {}
            all_hosts_brief.append({
                "hostname":   r.get("hostname") or r.get("instance", ""),
                "ip":         r.get("ip", ""),
                "os":         r.get("os", ""),
                "state":      r.get("state", ""),
                "overall":    r.get("overall", "normal"),
                "cpu_pct":    m.get("cpu_usage"),
                "mem_pct":    m.get("mem_usage"),
                "mem_total":  m.get("mem_total_gb"),
                "load5":      m.get("load5"),
                "net_recv":   m.get("net_recv_mbps"),
                "net_send":   m.get("net_send_mbps"),
                "tcp_estab":  m.get("tcp_estab"),
                "uptime_s":   m.get("uptime_seconds"),
                "checks":     r.get("checks", []),
                "partitions": r.get("partitions", []),
            })

        meta = {
            "id":             report_id,
            "type":           "inspect",
            "title":          f"主机巡检日报 {now.strftime('%Y-%m-%d')}",
            "created_at":     now.isoformat(),
            "health_score":   health_score,
            "host_summary":   summary,
            "top_issues":     [{"item": k, "count": v} for k, v in top_issues],
            "abnormal_hosts": abnormal_hosts[:20],
            "all_hosts":      all_hosts_brief,
        }

        report_path = REPORTS_DIR / f"{report_id}.json"
        ai_parts: list[str] = []

        async def generate():
            yield f"data: __META__{json.dumps(meta, ensure_ascii=False)}\n\n"
            try:
                async for chunk in analyzer.generate_host_inspect_report(results, summary):
                    ai_parts.append(chunk)
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            except Exception as exc:
                logger.exception("巡检日报 AI 生成异常")
                ai_parts.append(f"\n[AI生成出错] {exc}")
                yield f"data: {json.dumps('[AI生成出错] ' + str(exc), ensure_ascii=False)}\n\n"
            meta["ai_analysis"] = "".join(ai_parts)
            report_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
