"""CMDB 主机管理 + 主机巡检路由。

路由前缀：/api/hosts/*
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import io

from state import (
    prom, analyzer,
    load_cmdb, save_cmdb,
    encrypt_password, decrypt_password,
    PROMETHEUS_URL,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── 主机列表 ──────────────────────────────────────────────────────────────────

@router.get("/api/hosts")
async def get_hosts():
    """获取所有主机列表（Prometheus 发现 + CMDB 补充字段 + 实时指标 + 分区）"""
    try:
        hosts, all_metrics, all_partitions = await asyncio.gather(
            prom.discover_hosts(),
            prom.get_all_host_metrics(),
            prom.get_all_partitions(),
        )
        cmdb        = load_cmdb()
        cmdb_dirty  = False

        for host in hosts:
            inst = host["instance"]
            host["metrics"]    = all_metrics.get(inst, {})
            host["partitions"] = all_partitions.get(inst, [])
            extra = cmdb.get(inst, {})
            host["owner"]         = extra.get("owner", "")
            host["env"]           = extra.get("env", "")
            host["role"]          = extra.get("role", "")
            host["notes"]         = extra.get("notes", "")
            host["group"]         = extra.get("group", "")
            host["ssh_port"]      = extra.get("ssh_port", 22)
            host["ssh_user"]      = extra.get("ssh_user", "")
            host["ssh_saved"]     = bool(extra.get("ssh_password"))
            host["credential_id"] = extra.get("credential_id", "")
            if host["ip"] and host["ip"] != extra.get("ip"):
                cmdb.setdefault(inst, {})["ip"] = host["ip"]
                cmdb_dirty = True

        if cmdb_dirty:
            save_cmdb(cmdb)
        return {"data": hosts, "total": len(hosts), "prometheus_url": PROMETHEUS_URL}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus 连接失败: {e}")


class HostUpdateRequest(BaseModel):
    owner:         Optional[str] = None
    env:           Optional[str] = None
    role:          Optional[str] = None
    notes:         Optional[str] = None
    group:         Optional[str] = None  # 分组 ID
    ssh_port:      Optional[int] = None
    ssh_user:      Optional[str] = None
    ssh_password:  Optional[str] = None  # 明文传入，加密存储
    credential_id: Optional[str] = None  # 关联凭证库中的凭证


@router.put("/api/hosts/{instance:path}")
async def update_host(instance: str, body: HostUpdateRequest):
    """更新主机 CMDB 信息"""
    cmdb = load_cmdb()
    if instance not in cmdb:
        cmdb[instance] = {}
    for field in ("owner", "env", "role", "notes", "group", "ssh_port", "ssh_user"):
        val = getattr(body, field)
        if val is not None:
            cmdb[instance][field] = val
    if body.ssh_password is not None:
        if body.ssh_password:
            cmdb[instance]["ssh_password"] = encrypt_password(body.ssh_password)
        else:
            cmdb[instance].pop("ssh_password", None)
    if body.credential_id is not None:
        if body.credential_id:
            cmdb[instance]["credential_id"] = body.credential_id
            cmdb[instance].pop("ssh_password", None)
        else:
            cmdb[instance].pop("credential_id", None)
    save_cmdb(cmdb)
    return {"ok": True, "instance": instance}


# ── 巡检 ──────────────────────────────────────────────────────────────────────

def _inspection_issue_counts(results: list[dict]) -> list[tuple[str, int]]:
    counter: dict[str, int] = {}
    for result in results:
        for check in result.get("checks", []):
            if check.get("status") == "normal":
                continue
            item = check.get("item", "未知项")
            counter[item] = counter.get(item, 0) + 1
    return sorted(counter.items(), key=lambda item: item[1], reverse=True)


def _build_inspection_fallback_summary(
    results: list[dict], summary: dict, error: Exception | None = None
) -> str:
    total    = summary.get("total", len(results))
    normal   = summary.get("normal", 0)
    warning  = summary.get("warning", 0)
    critical = summary.get("critical", 0)
    issue_counts   = _inspection_issue_counts(results)
    top_issue_text = "、".join(
        f"{item}（{count}台）" for item, count in issue_counts[:3]
    ) or "暂未发现重复性异常项"

    abnormal_hosts = [r for r in results if r.get("overall") != "normal"]
    abnormal_hosts.sort(
        key=lambda item: (
            {"critical": 2, "warning": 1, "normal": 0}.get(item.get("overall", "normal"), 0),
            sum(1 for c in item.get("checks", []) if c.get("status") != "normal"),
        ),
        reverse=True,
    )
    top_host_text = "；".join(
        f"{host.get('hostname') or host.get('instance')}({host.get('ip', '-')})"
        for host in abnormal_hosts[:3]
    ) or "暂无异常主机"

    parts = [
        f"本次巡检共覆盖 {total} 台主机，其中正常 {normal} 台、警告 {warning} 台、严重 {critical} 台。",
        f"当前最集中的异常项为：{top_issue_text}。",
        f"需优先关注的主机：{top_host_text}。",
        "建议先处理严重主机，再按高频异常项排查资源瓶颈、容量风险和连接状态波动。",
        "未来24小时若不处理，异常项可能继续扩散到更多主机，并导致性能抖动、告警增加或服务稳定性下降。",
    ]
    if error:
        parts.append(f"AI 服务暂不可用，当前显示的是规则摘要（{error}）。")
    return "\n\n".join(parts)


async def _generate_inspection_summary(
    results: list[dict], summary: dict
) -> tuple[str, str, bool, str]:
    provider_name = analyzer.provider_name
    try:
        chunks: list[str] = []
        async for chunk in analyzer.generate_inspection_summary(results, summary):
            chunks.append(chunk)
        content = "".join(chunks).strip()
        if not content:
            raise RuntimeError("AI 返回内容为空")
        return content, provider_name, False, ""
    except Exception as exc:
        logger.exception("巡检 AI 总结生成失败")
        fallback = _build_inspection_fallback_summary(results, summary, exc)
        return fallback, provider_name, True, str(exc)


@router.get("/api/hosts/inspect")
async def inspect_all_hosts():
    """巡检全量主机，SSE 流式返回数据（不含 AI 分析）"""
    async def generate():
        try:
            results = await prom.inspect_hosts()
            summary = {
                "total":    len(results),
                "normal":   sum(1 for r in results if r["overall"] == "normal"),
                "warning":  sum(1 for r in results if r["overall"] == "warning"),
                "critical": sum(1 for r in results if r["overall"] == "critical"),
            }
            yield f"data: {json.dumps({'type': 'inspect_data', 'data': results, 'summary': summary}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("巡检 SSE 流异常")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class InspectAIRequest(BaseModel):
    results: list
    summary: dict


@router.post("/api/hosts/inspect/ai")
async def inspect_ai_summary(req: InspectAIRequest):
    """对已有巡检结果做 AI 流式分析（按需调用）"""
    async def generate():
        provider_name = analyzer.provider_name
        yield f"data: {json.dumps({'type': 'ai_meta', 'provider': provider_name, 'fallback': False}, ensure_ascii=False)}\n\n"
        try:
            async for chunk in analyzer.generate_inspection_summary(req.results, req.summary):
                yield f"data: {json.dumps({'type': 'ai_chunk', 'text': chunk}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception("巡检 AI 流式总结失败，降级为规则摘要")
            fallback = _build_inspection_fallback_summary(req.results, req.summary, exc)
            yield f"data: {json.dumps({'type': 'ai_meta', 'provider': provider_name, 'fallback': True}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'ai_chunk', 'text': fallback}, ensure_ascii=False)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class InspectExcelRequest(BaseModel):
    results: list
    summary: dict
    ai_text: str = ""


@router.post("/api/hosts/inspect/excel")
async def export_inspect_excel(req: InspectExcelRequest):
    """根据传入的巡检结果生成 Excel 文件并下载"""
    try:
        results  = req.results
        summary  = req.summary
        ai_text  = req.ai_text
        now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")

        wb = Workbook()

        STATUS_COLOR = {"normal": "FF67C23A", "warning": "FFE6A23C", "critical": "FFF56C6C"}
        STATUS_TEXT  = {"normal": "正常", "warning": "警告", "critical": "严重"}

        def hfill(color="FF1F3A5F"):
            return PatternFill("solid", fgColor=color)

        def tborder():
            s = Side(style="thin", color="FFCCCCCC")
            return Border(left=s, right=s, top=s, bottom=s)

        def col_widths(ws, widths):
            for i, w in enumerate(widths, 1):
                ws.column_dimensions[get_column_letter(i)].width = w

        def header_row(ws, headers, row=1):
            for col, h in enumerate(headers, 1):
                c           = ws.cell(row=row, column=col, value=h)
                c.font      = Font(bold=True, color="FFFFFFFF", size=10)
                c.fill      = hfill()
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                c.border    = tborder()

        def data_cell(ws, row, col, value, status=None):
            c           = ws.cell(row=row, column=col, value=value)
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border    = tborder()
            if status and status in STATUS_COLOR:
                c.fill = PatternFill("solid", fgColor=STATUS_COLOR[status])
                c.font = Font(color="FFFFFFFF", size=9)
            else:
                c.font = Font(size=9)

        # Sheet 1: 巡检概况
        ws1 = wb.active
        ws1.title = "巡检概况"
        ws1.column_dimensions["A"].width = 22
        ws1.column_dimensions["B"].width = 40

        def s1(r, k, v, bold=False):
            ck = ws1.cell(row=r, column=1, value=k)
            cv = ws1.cell(row=r, column=2, value=v)
            ck.font      = Font(bold=True, color="FFFFFFFF", size=10)
            ck.fill      = hfill("FF243850")
            cv.font      = Font(bold=bold, size=10)
            ck.alignment = cv.alignment = Alignment(vertical="center", wrap_text=True)
            ck.border    = cv.border    = tborder()
            ws1.row_dimensions[r].height = 18

        s1(1, "巡检时间",     now_str, bold=True)
        s1(2, "巡检主机总数", summary.get("total", 0))
        s1(3, "正常主机",     summary.get("normal", 0))
        s1(4, "警告主机",     summary.get("warning", 0))
        s1(5, "严重主机",     summary.get("critical", 0))

        issue_cnt: dict[str, int] = {}
        for r in results:
            for c in r.get("checks", []):
                if c.get("status") != "normal":
                    issue_cnt[c.get("item", "未知")] = issue_cnt.get(c.get("item", "未知"), 0) + 1
        top_issues = sorted(issue_cnt.items(), key=lambda x: x[1], reverse=True)[:8]

        ws1.cell(row=7, column=1, value="高频异常项").font = Font(bold=True, size=10)
        header_row(ws1, ["异常检查项", "影响主机数"], row=8)
        for i, (item, cnt) in enumerate(top_issues, 9):
            ws1.cell(row=i, column=1, value=item).border    = tborder()
            ws1.cell(row=i, column=2, value=cnt).border     = tborder()
            ws1.cell(row=i, column=1).font      = Font(size=9)
            ws1.cell(row=i, column=2).font      = Font(size=9)
            ws1.cell(row=i, column=1).alignment = Alignment(vertical="center")
            ws1.cell(row=i, column=2).alignment = Alignment(horizontal="center", vertical="center")

        ai_start = 9 + len(top_issues) + 2
        ws1.cell(row=ai_start, column=1, value="AI 分析总结").font = Font(bold=True, size=10)
        if ai_text:
            c           = ws1.cell(row=ai_start + 1, column=1, value=ai_text)
            c.font      = Font(size=9)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border    = tborder()
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
        header_row(ws2, headers2)
        col_widths(ws2, [18, 16, 22, 10, 10, 14, 14, 14, 10, 14, 14, 12, 12, 40])
        ws2.row_dimensions[1].height = 22

        for ri, h in enumerate(results, 2):
            overall      = h.get("overall", "normal")
            status_label = STATUS_TEXT.get(overall, overall)

            def fmt(v, decimals=1):
                return round(v, decimals) if v is not None else "-"

            m           = h.get("metrics") or {}
            uptime_days = "-"
            us = m.get("uptime_seconds")
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
                fmt(m.get("cpu_usage")), fmt(m.get("mem_usage")), fmt(m.get("mem_total_gb")),
                fmt(m.get("load5")), fmt(m.get("net_recv_mbps")), fmt(m.get("net_send_mbps")),
                m.get("tcp_estab") or "-", uptime_days, disk_text,
            ]
            for ci, val in enumerate(row_vals, 1):
                data_cell(ws2, ri, ci, val, overall if ci == 5 else None)
            ws2.row_dimensions[ri].height = 16

        ws2.freeze_panes = "A2"

        # Sheet 3: 异常项明细
        ws3 = wb.create_sheet("异常项明细")
        headers3 = ["主机名", "IP地址", "检查项", "当前值", "状态", "阈值说明"]
        header_row(ws3, headers3)
        col_widths(ws3, [18, 16, 20, 20, 10, 30])
        ws3.row_dimensions[1].height = 22

        ri3 = 2
        for h in results:
            for ck in [c for c in h.get("checks", []) if c.get("status") != "normal"]:
                status = ck.get("status", "warning")
                row3 = [
                    h.get("hostname", "-"), h.get("ip", "-"),
                    ck.get("item", "-"), ck.get("value", "-"),
                    STATUS_TEXT.get(status, status), ck.get("threshold", "-"),
                ]
                for ci, val in enumerate(row3, 1):
                    data_cell(ws3, ri3, ci, val, status if ci == 5 else None)
                ws3.row_dimensions[ri3].height = 16
                ri3 += 1

        ws3.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename     = f"主机巡检_{now_str.replace(':', '-')}.xlsx"
        encoded_name = quote(filename, encoding="utf-8")
        return Response(
            content=buf.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
        )
    except Exception as e:
        logger.exception("巡检 Excel 导出失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/hosts/{instance:path}/inspect")
async def inspect_single_host(instance: str):
    """巡检单台主机"""
    try:
        results = await prom.inspect_hosts(instances=[instance])
        if not results:
            raise HTTPException(status_code=404, detail="主机未找到")
        return results[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
