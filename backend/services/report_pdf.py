"""分析报告 PDF 导出（reportlab Platypus，参考 pdf skill 实践）。

支持三类日报：
  daily   — 运维日报：核心指标 / 节点状态 / Top10 错误服务 / AI 分析
  inspect — 主机巡检日报：主机概况 / Top 问题 / 异常主机明细 / AI 分析
  slowlog — MySQL 慢日志日报：统计概览 / Top 慢查询 / 各实例结果 / AI 分析

中文方案：优先注册系统 TTF（微软雅黑/黑体/Noto），找不到回退 reportlab
内置 CID 字体 STSong-Light（零文件依赖，跨平台可用）。
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

_FONT_NAME = "AIOpsCJK"
_FONT_BOLD = "AIOpsCJK-Bold"
_font_ready = False

_TTF_CANDIDATES = [
    # (regular, bold)
    (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"),
    (r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simhei.ttf"),
    ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
     "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
     "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
]


def _ensure_fonts() -> tuple[str, str]:
    """注册中文字体，返回 (正文字体名, 加粗字体名)。"""
    global _font_ready, _FONT_NAME, _FONT_BOLD
    if _font_ready:
        return _FONT_NAME, _FONT_BOLD

    for regular, bold in _TTF_CANDIDATES:
        try:
            if Path(regular).exists():
                pdfmetrics.registerFont(TTFont(_FONT_NAME, regular))
                pdfmetrics.registerFont(
                    TTFont(_FONT_BOLD, bold if Path(bold).exists() else regular))
                _font_ready = True
                return _FONT_NAME, _FONT_BOLD
        except Exception as exc:
            logger.debug("[report_pdf] 字体注册失败 %s: %s", regular, exc)

    # 回退：内置 CID 字体（无 bold 变体，用同名）
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    _FONT_NAME = _FONT_BOLD = "STSong-Light"
    _font_ready = True
    return _FONT_NAME, _FONT_BOLD


_ACCENT = colors.HexColor("#d97757")
_MUTED = colors.HexColor("#6b6b6b")
_BORDER = colors.HexColor("#dddddd")
_HEAD_BG = colors.HexColor("#f5f0ec")


def _styles():
    font, bold = _ensure_fonts()
    return {
        "title": ParagraphStyle("title", fontName=bold, fontSize=18, leading=24,
                                textColor=colors.HexColor("#333333")),
        "meta": ParagraphStyle("meta", fontName=font, fontSize=9, leading=13,
                               textColor=_MUTED),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=13, leading=18,
                             textColor=_ACCENT, spaceBefore=6),
        "body": ParagraphStyle("body", fontName=font, fontSize=10, leading=16),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=9, leading=13),
        "cellhead": ParagraphStyle("cellhead", fontName=bold, fontSize=9, leading=13),
        "score": ParagraphStyle("score", fontName=bold, fontSize=30, leading=34,
                                alignment=TA_CENTER),
    }


def _esc(text) -> str:
    return (str(text if text is not None else "-")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _score_color(score: int):
    if score >= 80:
        return colors.HexColor("#2f9e44")
    if score >= 60:
        return colors.HexColor("#e8930c")
    return colors.HexColor("#d63031")


def _kv_table(rows: list[tuple[str, str]], st) -> Table:
    """两列 x N 的指标卡表（label 上、value 下，按 4 个一行排布）。"""
    per_row = 4
    data, row_labels, row_values = [], [], []
    for label, value in rows:
        row_labels.append(Paragraph(_esc(label), st["cell"]))
        row_values.append(Paragraph(f"<b>{_esc(value)}</b>", st["cellhead"]))
        if len(row_labels) == per_row:
            data += [row_values, row_labels]
            row_labels, row_values = [], []
    if row_labels:
        pad = per_row - len(row_labels)
        data += [row_values + [""] * pad, row_labels + [""] * pad]
    table = Table(data, colWidths=[42 * mm] * per_row)
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (-1, 1), _MUTED),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _data_table(headers: list[str], rows: list[list], st,
                col_widths: list[float] | None = None) -> Table:
    data = [[Paragraph(f"<b>{_esc(h)}</b>", st["cellhead"]) for h in headers]]
    for row in rows:
        data.append([Paragraph(_esc(cell), st["cell"]) for cell in row])
    table = Table(data, colWidths=col_widths, repeatRows=1, splitInRow=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _HEAD_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, _BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _md_paragraphs(text: str, st) -> list:
    """AI 分析 markdown → 段落列表（标题/列表/加粗的轻量转换）。"""
    flow = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or set(line) <= {"-", "—", "*"}:
            continue
        line = _esc(line)
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"`([^`]+)`", r"<font face='Courier'>\1</font>", line)
        if line.startswith("#"):
            flow.append(Paragraph(line.lstrip("# "), st["h2"]))
        elif re.match(r"^[-*•]\s+", line):
            flow.append(Paragraph("• " + re.sub(r"^[-*•]\s+", "", line), st["body"]))
        elif re.match(r"^\d+[.、)]\s*", line):
            flow.append(Paragraph(line, st["body"]))
        else:
            flow.append(Paragraph(line, st["body"]))
    return flow or [Paragraph("（无 AI 分析内容）", st["body"])]


_TYPE_LABELS = {
    "daily": "运维日报",
    "inspect": "主机巡检日报",
    "slowlog": "MySQL 慢日志日报",
}


def _section(title: str, st) -> list:
    return [
        Spacer(1, 8),
        Paragraph(title, st["h2"]),
        HRFlowable(width="100%", thickness=0.6, color=_BORDER, spaceAfter=6),
    ]


def _build_daily(report: dict, st) -> list:
    flow = _section("运行概况", st)
    node = report.get("node_status") or {}
    interface = report.get("interface_status") or {}
    flow.append(_kv_table([
        ("覆盖服务", report.get("service_count", 0)),
        ("活跃告警", report.get("active_alerts", 0)),
        ("节点正常", node.get("normal", "-")),
        ("节点异常", node.get("abnormal", "-")),
        ("接口状态", interface.get("status", "未采集")),
        ("异常接口", interface.get("abnormal_interfaces", "-")),
    ], st))

    summaries = report.get("service_error_summaries") or []
    if summaries:
        flow += _section("微服务错误一句话概括", st)
        flow.append(_data_table(
            ["微服务", "高频关键字", "一句话结论"],
            [[item.get("service", "-"), "、".join(item.get("keywords") or []) or "样本不足",
              item.get("summary", "-")] for item in summaries],
            st, col_widths=[35 * mm, 45 * mm, 70 * mm]))

    keywords = report.get("error_keywords") or []
    if keywords:
        flow += _section("高频错误关键字", st)
        flow.append(_data_table(
            ["关键字", "样本频次", "涉及服务"],
            [[item.get("keyword", "-"), item.get("count", 0),
              "、".join(item.get("services") or []) or "-"] for item in keywords],
            st, col_widths=[40 * mm, 25 * mm, 85 * mm]))

    interface_rows = interface.get("rows") or []
    flow += _section("接口监控状况评估", st)
    if interface_rows:
        flow.append(_data_table(
            ["状态", "应用", "方法", "接口", "5xx率", "P95"],
            [[row.get("status", "-"), row.get("application", "-"), row.get("method", "-"),
              row.get("uri", "-"), f"{row.get('error_ratio', 0)}%",
              f"{row.get('p95_ms', 0)}ms"] for row in interface_rows[:20]],
            st, col_widths=[18 * mm, 28 * mm, 15 * mm, 55 * mm, 17 * mm, 17 * mm]))
    else:
        flow.append(Paragraph("未采集到 http_server 接口指标，无法评估接口成功率与延迟。", st["body"]))
    return flow


def _build_inspect(report: dict, st) -> list:
    flow = _section("主机概况", st)
    summary = report.get("host_summary") or {}
    flow.append(_kv_table([
        ("主机总数", summary.get("total", "-")),
        ("正常", summary.get("normal", "-")),
        ("警告", summary.get("warning", "-")),
        ("严重", summary.get("critical", "-")),
    ], st))

    sections = report.get("group_sections") or []
    if not sections and report.get("all_hosts"):
        sections = [{"group_name": report.get("group_name") or "全部主机",
                     "hosts": report.get("all_hosts") or []}]
    for group in sections:
        hosts = group.get("hosts") or []
        flow += _section(f"{group.get('group_name', '未分组')}（{len(hosts)} 台，告警优先）", st)
        rows = []
        for host in hosts:
            disks = "；".join(
                f"{p.get('mountpoint') or p.get('mount') or '-'} "
                f"{p.get('usage_pct', p.get('used_pct', '-'))}% "
                f"({p.get('used_gb', '-')}/{p.get('total_gb', p.get('size_gb', '-'))}GB)"
                for p in (host.get("partitions") or [])
            ) or "未采集"
            processes = "；".join(
                f"{index}. {proc.get('service') or proc.get('comm') or '-'} "
                f"CPU {proc.get('cpu', '-')}%/MEM {proc.get('mem', '-')}%"
                for index, proc in enumerate(host.get("process_top10") or [], 1)
            ) or host.get("process_error") or "未采集"
            rows.append([
                host.get("overall", "-"),
                host.get("ip", "-"),
                host.get("role") or host.get("os") or "-",
                host.get("hostname", "-"),
                f"{host.get('cpu_pct', '-')}%",
                f"{host.get('mem_pct', '-')}%",
                disks,
                processes,
                host.get("owner") or "未配置",
                host.get("datacenter") or "未配置",
            ])
        flow.append(_data_table(
            ["状态", "服务器IP", "服务器", "主机名", "CPU", "内存",
             "磁盘具体占用", "进程占用Top10", "负责人", "机房"],
            rows, st,
            col_widths=[14 * mm, 25 * mm, 20 * mm, 25 * mm, 18 * mm,
                        18 * mm, 40 * mm, 52 * mm, 22 * mm, 22 * mm]))
    return flow


def _build_slowlog(report: dict, st) -> list:
    flow = _section("慢查询统计", st)
    flow.append(_kv_table([
        ("统计范围", f"{report.get('date_from', '-')} ~ {report.get('date_to', '-')}"),
        ("慢查询总数", f"{report.get('total_queries', 0):,}"),
        ("告警级查询", report.get("alert_queries", 0)),
        ("实例数", report.get("hosts_count", 0)),
        ("平均耗时(s)", round(float(report.get("avg_query_time") or 0), 2)),
        ("最大耗时(s)", round(float(report.get("max_query_time") or 0), 2)),
    ], st))

    top_slow = report.get("top_slow") or []
    if top_slow:
        flow += _section("Top 慢查询", st)
        rows = []
        for q in top_slow[:15]:
            sql = str(q.get("sql_brief") or q.get("sql") or q.get("query") or q.get("fingerprint") or "-")
            rows.append([
                q.get("host_ip") or q.get("host", "-"),
                round(float(q.get("query_time") or q.get("avg_time") or 0), 2),
                q.get("count", q.get("cnt", "-")),
                sql[:220] + ("…" if len(sql) > 220 else ""),
            ])
        flow.append(_data_table(
            ["实例", "耗时(s)", "次数", "SQL"],
            rows, st, col_widths=[26 * mm, 16 * mm, 13 * mm, 95 * mm]))

    host_results = report.get("host_results") or []
    if host_results:
        flow += _section("各实例结果", st)
        flow.append(_data_table(
            ["实例", "慢查询数", "告警数", "平均耗时(s)", "最大耗时(s)"],
            [[h.get("host_ip", "-"), h.get("total", 0), h.get("alert_count", 0),
              round(float(h.get("avg_query_time") or 0), 2),
              round(float(h.get("max_query_time") or 0), 2)]
             for h in host_results[:20]],
            st, col_widths=[40 * mm, 27 * mm, 25 * mm, 29 * mm, 29 * mm]))
    return flow


def build_report_pdf(report: dict) -> bytes:
    """报告 dict → PDF 字节流。"""
    st = _styles()
    report_type = report.get("type", "daily")
    type_label = _TYPE_LABELS.get(report_type, "分析报告")
    title = report.get("title") or type_label
    created = str(report.get("created_at", ""))[:19].replace("T", " ")
    score = int(report.get("health_score") or 0)

    buf = io.BytesIO()
    page_size = landscape(A4) if report_type == "inspect" else A4
    doc = SimpleDocTemplate(
        buf, pagesize=page_size,
        topMargin=16 * mm, bottomMargin=16 * mm,
        leftMargin=18 * mm, rightMargin=18 * mm,
        title=title, author="SxDevOps AIOps",
    )

    score_para = Paragraph(f"{score}", ParagraphStyle(
        "sc", parent=st["score"], textColor=_score_color(score)))
    head = Table(
        [[
            [Paragraph(_esc(title), st["title"]),
             Spacer(1, 4),
             Paragraph(f"{type_label} · 生成时间 {created} · SxDevOps AIOps 平台",
                       st["meta"])],
            [score_para, Paragraph("健康评分", ParagraphStyle(
                "sl", parent=st["meta"], alignment=TA_CENTER))],
        ]],
        colWidths=[128 * mm, 40 * mm],
    )
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))

    flow: list = [head, Spacer(1, 4),
                  HRFlowable(width="100%", thickness=1, color=_ACCENT)]

    flow += _section("第一部分 · AI 结论", st)
    flow += _md_paragraphs(report.get("ai_analysis", ""), st)

    builders = {"daily": _build_daily, "inspect": _build_inspect,
                "slowlog": _build_slowlog}
    builder = builders.get(report_type)
    if builder:
        try:
            flow += builder(report, st)
        except Exception as exc:
            logger.warning("[report_pdf] %s 章节渲染失败: %s", report_type, exc)
            flow.append(Paragraph(f"（部分内容渲染失败: {_esc(exc)}）", st["meta"]))

    doc.build(flow)
    return buf.getvalue()
