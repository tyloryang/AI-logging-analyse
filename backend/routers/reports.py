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
    load_slowlog_targets, save_slowlog_targets,
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
    for p in sorted(REPORTS_DIR.glob("*.json"), reverse=True)[:50]:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            reports.append({k: data[k] for k in [
                "id", "type", "title", "created_at", "health_score",
                "total_logs", "total_errors", "service_count", "active_alerts",
                # 慢日志报告专有摘要字段
                "total_queries", "alert_queries", "hosts_count",
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
    from datetime import date as date_cls, timedelta
    from slow_log_parser import parse_slow_log, build_summary
    from sql_cluster import cluster_slow_queries
    from routers.slowlog import _read_remote_file, _resolve_credential

    config  = load_slowlog_targets()
    targets = config.get("targets", [])
    if not targets:
        raise HTTPException(400, detail="未配置慢日志分析目标，请先在「慢日志报告 · 配置目标」中添加主机")

    date_days     = max(1, int(config.get("date_days", 1)))
    threshold_sec = float(config.get("threshold_sec", 1.0))
    alert_sec     = float(config.get("alert_sec", 10.0))

    today     = date_cls.today()
    date_from = (today - timedelta(days=date_days - 1)).strftime("%Y-%m-%d")
    date_to   = today.strftime("%Y-%m-%d")

    now       = datetime.now(timezone.utc)
    report_id = "slowlog_" + now.strftime("%Y%m%d%H%M%S")

    async def generate():
        host_results: list[dict] = []
        all_entries:  list[dict] = []
        errors:       list[dict] = []

        for t in targets:
            host_ip  = (t.get("host_ip") or "").strip()
            log_path = t.get("log_path") or "/mysqldata/mysql/data/3306/mysql-slow.log"
            if not host_ip:
                continue
            try:
                username, password, host, port = _resolve_credential(
                    host_ip,
                    credential_id=t.get("credential_id", ""),
                    username=t.get("ssh_user", ""),
                    password=t.get("ssh_password", ""),
                    port=int(t.get("ssh_port", 22)),
                )
                text    = await _read_remote_file(host, port, username, password, log_path)
                entries = parse_slow_log(
                    text,
                    date_from=date_from, date_to=date_to,
                    threshold_sec=threshold_sec, alert_sec=alert_sec,
                )
                try:
                    clusters = cluster_slow_queries(entries)
                except Exception:
                    clusters = []
                summary = build_summary(entries)
                for e in entries:
                    all_entries.append({**e, "_host_ip": host_ip})
                host_results.append({
                    "host_ip":        host_ip,
                    "total":          summary.get("total", 0),
                    "alert_count":    summary.get("alert_count", 0),
                    "avg_query_time": summary.get("avg_query_time", 0),
                    "max_query_time": summary.get("max_query_time", 0),
                    "top_clusters": [
                        {
                            "rank":        c["rank"],
                            "template":    c["template"],
                            "count":       c["count"],
                            "total_time":  c["total_time"],
                            "avg_time":    c["avg_time"],
                            "max_time":    c["max_time"],
                            "alert_count": c["alert_count"],
                        }
                        for c in clusters[:5]
                    ],
                })
            except Exception as e:
                errors.append({"host_ip": host_ip, "error": str(e)})

        total_queries = sum(r["total"] for r in host_results)
        alert_queries = sum(r["alert_count"] for r in host_results)
        avg_qt = (
            sum(r["avg_query_time"] * r["total"] for r in host_results) / total_queries
            if total_queries else 0.0
        )
        max_qt = max((r["max_query_time"] for r in host_results), default=0.0)

        # 健康评分
        if total_queries == 0:
            health_score = 50
        else:
            deduct = 0
            ratio = alert_queries / total_queries
            if ratio > 0.3:   deduct += 40
            elif ratio > 0.1: deduct += 20
            if max_qt > 60:   deduct += 20
            elif max_qt > 30: deduct += 10
            if avg_qt > 10:   deduct += 15
            elif avg_qt > 5:  deduct += 8
            health_score = max(0, 100 - deduct)

        top_slow = sorted(all_entries, key=lambda e: e.get("query_time", 0), reverse=True)[:10]
        top_slow_brief = [
            {
                "host_ip":       e.get("_host_ip", ""),
                "query_time":    e.get("query_time", 0),
                "rows_examined": e.get("rows_examined", 0),
                "sql_brief":     e.get("sql", "")[:200],
            }
            for e in top_slow
        ]

        meta = {
            "id":             report_id,
            "type":           "slowlog",
            "title":          f"MySQL 慢日志报告 {now.strftime('%Y-%m-%d')}",
            "created_at":     now.isoformat(),
            "health_score":   health_score,
            "date_from":      date_from,
            "date_to":        date_to,
            "total_queries":  total_queries,
            "alert_queries":  alert_queries,
            "avg_query_time": round(avg_qt, 2),
            "max_query_time": round(max_qt, 3),
            "hosts_count":    len(host_results),
            "host_results":   host_results,
            "top_slow":       top_slow_brief,
            "errors":         errors,
        }

        yield f"data: __META__{json.dumps(meta, ensure_ascii=False)}\n\n"

        if not all_entries:
            meta["ai_analysis"] = "未找到满足条件的慢查询记录，请检查目标主机、日志路径及时间范围配置。"
            (REPORTS_DIR / f"{report_id}.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            yield "data: [DONE]\n\n"
            return

        # 构建 AI 分析提示词
        prompt = f"""你是 MySQL 数据库性能专家，请分析以下慢查询日志汇总报告并给出优化建议。

**报告概况**
- 分析时间段：{date_from} ~ {date_to}
- 分析主机数：{len(host_results)} 台
- 慢查询总数：{total_queries}（≥{threshold_sec}s）
- 告警数（≥{alert_sec}s）：{alert_queries}
- 平均耗时：{round(avg_qt, 2)}s
- 最大耗时：{round(max_qt, 2)}s

**各主机情况**
"""
        for hr in host_results:
            prompt += (
                f"- {hr['host_ip']}：{hr['total']} 条慢查询，"
                f"{hr['alert_count']} 条告警，最大耗时 {hr['max_query_time']}s\n"
            )

        if top_slow_brief:
            prompt += "\n**TOP 10 最慢查询**\n"
            for i, s in enumerate(top_slow_brief, 1):
                sql_preview = s["sql_brief"][:200] + ("..." if len(s["sql_brief"]) >= 200 else "")
                prompt += (
                    f"\n[{i}] 主机={s['host_ip']} 耗时={s['query_time']}s "
                    f"扫描行={s['rows_examined']}\n"
                    f"SQL: {sql_preview}\n"
                )

        # 跨主机 Top 聚合模板
        all_clusters: list[dict] = []
        for hr in host_results:
            for c in hr.get("top_clusters", [])[:3]:
                all_clusters.append({**c, "host_ip": hr["host_ip"]})
        all_clusters.sort(key=lambda x: x.get("total_time", 0), reverse=True)
        if all_clusters:
            prompt += "\n**SQL 模板聚合 Top（按总耗时排序）**\n"
            for i, c in enumerate(all_clusters[:8], 1):
                prompt += (
                    f"\n[{i}] {c['host_ip']} 出现 {c['count']} 次，"
                    f"总耗时 {c['total_time']}s，单次最大 {c['max_time']}s\n"
                    f"模板: {c['template'][:200]}\n"
                )

        prompt += """
**请按以下结构输出分析报告**：
1. 整体评估（问题等级：严重/警告/正常）
2. 主要问题分析（高频/高耗时 SQL 的根因）
3. 具体优化建议（加索引、改写 SQL、分页、缓存等可操作方案）
4. 各主机重点关注事项
5. 优先处理顺序

使用中文输出，格式清晰，给出可操作的建议。"""

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
        (REPORTS_DIR / f"{report_id}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
