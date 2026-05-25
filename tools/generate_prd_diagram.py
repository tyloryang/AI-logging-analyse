from __future__ import annotations

import os
import shutil
import subprocess
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "screenshots"
SVG_PATH = OUTPUT_DIR / "project_prd_overview.svg"
PNG_PATH = OUTPUT_DIR / "project_prd_overview.png"

W = 2400
H = 1600

BG = "#f8f7f3"
PANEL = "#ffffff"
BORDER = "#e5e7eb"
TEXT = "#111827"
MUTED = "#6b7280"
SUBTLE = "#94a3b8"
GREEN = "#10a37f"
BLUE = "#2563eb"
ORANGE = "#f97316"
PURPLE = "#7c3aed"
RED = "#ef4444"


def is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def wrap_line(line: str, max_units: float) -> list[str]:
    parts: list[str] = []
    buf = ""
    units = 0.0
    for ch in line:
        ch_units = 1.0 if is_cjk(ch) else 0.58
        if buf and units + ch_units > max_units:
            parts.append(buf)
            buf = ""
            units = 0.0
        buf += ch
        units += ch_units
    if buf:
        parts.append(buf)
    return parts or [line]


def wrap_text(text: str, max_units: float) -> list[str]:
    lines: list[str] = []
    for raw in text.split("\n"):
        lines.extend(wrap_line(raw, max_units))
    return lines


def text_block(x: int, y: int, text: str, size: int, color: str, max_units: float, line_gap: int | None = None, weight: int = 400) -> str:
    gap = line_gap or int(size * 1.35)
    lines = wrap_text(text, max_units)
    out: list[str] = [f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}">']
    for i, line in enumerate(lines):
        dy = 0 if i == 0 else gap
        out.append(f'  <tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
    out.append("</text>")
    return "\n".join(out)


def chip(x: int, y: int, label: str, fill: str = "#f3f4f6", stroke: str = BORDER, color: str = TEXT) -> str:
    width = 22 + sum(18 if is_cjk(ch) else 10 for ch in label)
    return (
        f'<g>'
        f'<rect x="{x}" y="{y}" width="{width}" height="32" rx="16" fill="{fill}" stroke="{stroke}"/>'
        f'<text x="{x + width / 2}" y="{y + 21}" text-anchor="middle" fill="{color}" font-size="13" font-weight="600">{escape(label)}</text>'
        f'</g>'
    )


def panel(x: int, y: int, w: int, h: int, title: str, subtitle: str) -> str:
    return (
        f'<g>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{PANEL}" stroke="{BORDER}"/>'
        f'<rect x="{x}" y="{y}" width="6" height="{h}" rx="3" fill="{GREEN}"/>'
        f'<text x="{x + 22}" y="{y + 34}" fill="{MUTED}" font-size="13" font-weight="700" letter-spacing="0.08em">{escape(title)}</text>'
        f'<text x="{x + 22}" y="{y + 62}" fill="{TEXT}" font-size="23" font-weight="800">{escape(subtitle)}</text>'
        f'</g>'
    )


def card(x: int, y: int, w: int, h: int, title: str, body: list[str], accent: str, tag: str | None = None) -> str:
    lines = [
        f'<g>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="{PANEL}" stroke="{BORDER}"/>',
        f'<rect x="{x}" y="{y}" width="6" height="{h}" rx="3" fill="{accent}"/>',
    ]
    if tag:
        tag_w = 20 + sum(18 if is_cjk(ch) else 10 for ch in tag)
        lines += [
            f'<rect x="{x + w - tag_w - 16}" y="{y + 16}" width="{tag_w}" height="28" rx="14" fill="#f8fafc" stroke="{BORDER}"/>',
            f'<text x="{x + w - tag_w / 2 - 16}" y="{y + 35}" text-anchor="middle" fill="{accent}" font-size="12" font-weight="700">{escape(tag)}</text>',
        ]
    lines.append(f'<text x="{x + 20}" y="{y + 38}" fill="{TEXT}" font-size="20" font-weight="800">{escape(title)}</text>')
    body_y = y + 70
    for i, item in enumerate(body):
        lines.append(text_block(x + 20, body_y + i * 34, f"• {item}", 15, MUTED, max_units=24))
    lines.append("</g>")
    return "\n".join(lines)


def flow_box(x: int, y: int, w: int, h: int, title: str, body: str, accent: str) -> str:
    return (
        f'<g>'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="20" fill="#fbfdff" stroke="{BORDER}"/>'
        f'<rect x="{x}" y="{y}" width="6" height="{h}" rx="3" fill="{accent}"/>'
        f'<text x="{x + 18}" y="{y + 34}" fill="{TEXT}" font-size="18" font-weight="800">{escape(title)}</text>'
        f'{text_block(x + 18, y + 68, body, 14, MUTED, max_units=34, line_gap=19)}'
        f'</g>'
    )


def defs() -> str:
    return f"""
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fbfaf7"/>
      <stop offset="100%" stop-color="#f4f7fb"/>
    </linearGradient>
    <radialGradient id="glow-a" cx="18%" cy="12%" r="40%">
      <stop offset="0%" stop-color="{GREEN}" stop-opacity="0.09"/>
      <stop offset="100%" stop-color="{GREEN}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glow-b" cx="82%" cy="18%" r="35%">
      <stop offset="0%" stop-color="{BLUE}" stop-opacity="0.07"/>
      <stop offset="100%" stop-color="{BLUE}" stop-opacity="0"/>
    </radialGradient>
    <marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
      <polygon points="0,0 10,4 0,8" fill="{SUBTLE}"/>
    </marker>
  </defs>
"""


def connect(x1: int, y1: int, x2: int, y2: int) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{SUBTLE}" stroke-width="2" marker-end="url(#arrow)"/>'


def build_svg() -> str:
    left_x = 60
    left_w = 430
    center_x = 515
    center_w = 1090
    right_x = 1630
    right_w = 710
    panel_y = 150
    panel_h = 1390

    module_w = 338
    module_h = 166
    module_gap_x = 18
    module_gap_y = 18
    module_xs = [center_x + 20, center_x + 20 + module_w + module_gap_x, center_x + 20 + (module_w + module_gap_x) * 2]
    module_y1 = 228
    module_y2 = module_y1 + module_h + module_gap_y

    phase_h = 244
    phase_gap = 18
    phase_y1 = 228
    phase_y2 = phase_y1 + phase_h + phase_gap
    phase_y3 = phase_y2 + phase_h + phase_gap

    svg: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xml:lang="zh-CN" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        '  <style>',
        f'    text {{ font-family: "Microsoft YaHei UI", "Microsoft YaHei", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; }}',
        '  </style>',
        defs(),
        f'<rect width="{W}" height="{H}" fill="url(#bg)"/>',
        f'<rect width="{W}" height="{H}" fill="url(#glow-a)"/>',
        f'<rect width="{W}" height="{H}" fill="url(#glow-b)"/>',
        f'<text x="60" y="74" fill="{TEXT}" font-size="34" font-weight="900">AIOps 智能运维平台 PRD</text>',
        f'<text x="60" y="108" fill="{MUTED}" font-size="16">面向 DevOps / SRE，把告警治理、根因分析、自动化处置和复盘沉淀做成闭环</text>',
        chip(1915, 44, "v1.0"),
        chip(2040, 44, "产品图谱", fill="#ecfdf5", stroke="#bbf7d0", color=GREEN),
        panel(left_x, panel_y, left_w, panel_h, "PRODUCT CONTEXT", "为什么要做"),
        panel(center_x, panel_y, center_w, panel_h, "CORE SCOPE", "做什么"),
        panel(right_x, panel_y, right_w, panel_h, "ROADMAP", "怎么落地"),
        card(
            left_x + 18,
            250,
            left_w - 36,
            278,
            "背景痛点",
            [
                "告警噪音高，重复告警多",
                "日志 / 指标 / Trace 分散",
                "故障定位依赖人工拼接",
                "夜间响应慢，排障成本高",
            ],
            BLUE,
            "Pain"
        ),
        card(
            left_x + 18,
            548,
            left_w - 36,
            242,
            "目标用户",
            [
                "SRE / DevOps / 开发",
                "管理层关注日报与健康分",
                "飞书里直接触发分析和协作",
            ],
            ORANGE,
            "Users"
        ),
        card(
            left_x + 18,
            810,
            left_w - 36,
            258,
            "产品原则",
            [
                "AI 仅给建议，动作需人审",
                "不自研监控采集，复用现有体系",
                "不替代 IM，只做通知与协作入口",
                "优先做高频、可闭环的场景",
            ],
            GREEN,
            "Rule"
        ),
        card(
            left_x + 18,
            1088,
            left_w - 36,
            252,
            "验收指标",
            [
                "30 秒内输出初步 RCA",
                "同因 20 条告警收敛为 1 张卡",
                "每日 9:00 自动生成运维日报",
                "资源按分组隔离可见",
            ],
            PURPLE,
            "KPI"
        ),
    ]

    module_cards = [
        ("告警治理", ["接入 AlertManager / Webhook", "同因聚合、去重抑制", "飞书卡片实时推送"], GREEN, "Notify"),
        ("根因分析", ["联合日志 / 指标 / Trace / CMDB", "30 秒内输出摘要", "支持人工确认沉淀"], BLUE, "RCA"),
        ("可观测中心", ["日志中心 / 指标监控 / APM", "事件墙 / 慢日志 / 异常检测", "统一进入观测界面"], ORANGE, "Obs"),
        ("资源与平台", ["CMDB / 主机 / K8s / 中间件", "Redis / ES / Jenkins 接入", "资源拓扑和健康度"], PURPLE, "Asset"),
        ("自动化处置", ["SSH / 任务 / Cron / 审批", "报告导出 / 定时巡检", "变更动作需人工确认"], RED, "Auto"),
        ("AI 工作台", ["对话式排障与代码上下文", "多模型切换 / 历史会话", "记忆检索 / 报告生成"], "#0ea5e9", "Agent"),
    ]

    idx = 0
    for row_y in (module_y1, module_y2):
        for col_x in module_xs:
            title, body, accent, tag = module_cards[idx]
            svg.append(card(col_x, row_y, module_w, module_h, title, body, accent, tag))
            idx += 1

    flow_y = 650
    flow_h = 650
    svg.append(
        f'<g>'
        f'<rect x="{center_x + 20}" y="{flow_y}" width="{center_w - 40}" height="{flow_h}" rx="22" fill="#fbfdff" stroke="{BORDER}"/>'
        f'<rect x="{center_x + 20}" y="{flow_y}" width="6" height="{flow_h}" rx="3" fill="{GREEN}"/>'
        f'<text x="{center_x + 40}" y="{flow_y + 36}" fill="{TEXT}" font-size="20" font-weight="800">核心闭环</text>'
        f'<text x="{center_x + 40}" y="{flow_y + 64}" fill="{MUTED}" font-size="14">从触发到分析，再到处置和沉淀，形成可复用的运维闭环</text>'
        f'</g>'
    )
    chips = ["AlertManager", "Loki", "Prometheus", "SkyWalking", "CMDB", "SSH", "飞书"]
    chip_x = center_x + 40
    chip_y = flow_y + 92
    for label in chips:
        svg.append(chip(chip_x, chip_y, label, fill="#f8fafc"))
        chip_x += 102 if label != "SkyWalking" else 132

    step_y = flow_y + 158
    step_w = 236
    step_h = 180
    step_gap = 22
    step_titles = [
        ("1 触发", "告警到来\n用户点击分析\n定时巡检"),
        ("2 采集", "并发拉取日志\n指标、Trace、资产\n压缩上下文"),
        ("3 推理", "LangGraph ReAct\n工具调用 + 记忆\n生成结构化结论"),
        ("4 输出", "RCA 卡片\n飞书通知 / 工单\n报告和知识沉淀"),
    ]
    step_x = center_x + 40
    for i, (title, body) in enumerate(step_titles):
        svg.append(
            f'<g>'
            f'<rect x="{step_x}" y="{step_y}" width="{step_w}" height="{step_h}" rx="18" fill="#ffffff" stroke="{BORDER}"/>'
            f'<circle cx="{step_x + 22}" cy="{step_y + 22}" r="10" fill="{[BLUE, ORANGE, PURPLE, GREEN][i]}"/>'
            f'<text x="{step_x + 42}" y="{step_y + 27}" fill="{TEXT}" font-size="16" font-weight="800">{escape(title)}</text>'
            f'{text_block(step_x + 18, step_y + 62, body, 14, MUTED, max_units=18, line_gap=18)}'
            f'</g>'
        )
        if i < 3:
            svg.append(connect(step_x + step_w + 10, step_y + 90, step_x + step_w + 28, step_y + 90))
        step_x += step_w + step_gap

    svg.append(
        f'<g>'
        f'<rect x="{center_x + 40}" y="{flow_y + 372}" width="{center_w - 80}" height="230" rx="18" fill="#f8fafc" stroke="{BORDER}"/>'
        f'<text x="{center_x + 60}" y="{flow_y + 404}" fill="{TEXT}" font-size="16" font-weight="800">输出物</text>'
        f'{text_block(center_x + 60, flow_y + 436, "RCA 摘要 / 处置建议 / 相似案例 / 复盘报告 / 模型与技能配置", 14, MUTED, max_units=62, line_gap=18)}'
        f'</g>'
    )

    phases = [
        ("Phase 1 · 告警治理", ["Webhook 接入", "去重聚合与抑制", "告警中心 + 飞书卡片"], GREEN),
        ("Phase 2 · RCA 闭环", ["上下文采集", "AI 分析 + 异常检测", "报告导出 + 历史复盘"], BLUE),
        ("Phase 3 · 资产扩展", ["CloudAdapter", "多云接入 + 成本汇总", "统一资产视图"], PURPLE),
    ]
    for i, (title, body, accent) in enumerate(phases):
        y = [phase_y1, phase_y2, phase_y3][i]
        svg.append(card(right_x + 18, y, right_w - 36, phase_h, title, body, accent))

    svg.append(
        f'<g>'
        f'<rect x="{right_x + 18}" y="1038" width="{right_w - 36}" height="318" rx="18" fill="#fbfdff" stroke="{BORDER}"/>'
        f'<text x="{right_x + 36}" y="1072" fill="{TEXT}" font-size="18" font-weight="800">关键指标</text>'
        f'{chip(right_x + 36, 1104, "30 秒 RCA", fill="#ecfdf5", stroke="#bbf7d0", color=GREEN)}'
        f'{chip(right_x + 210, 1104, "20→1 卡片", fill="#eff6ff", stroke="#bfdbfe", color=BLUE)}'
        f'{chip(right_x + 36, 1150, "9:00 报告", fill="#fff7ed", stroke="#fed7aa", color=ORANGE)}'
        f'{chip(right_x + 210, 1150, "分组权限", fill="#faf5ff", stroke="#e9d5ff", color=PURPLE)}'
        f'{text_block(right_x + 36, 1214, "验收关注点：告警后是否能快速给出结论，是否能减少夜班噪音，是否能把结果沉淀成可复用知识。", 14, MUTED, max_units=34, line_gap=18)}'
        f'</g>'
    )

    svg.append(
        f'<text x="60" y="1548" fill="{SUBTLE}" font-size="12">基于当前仓库中的 AIOps 智能运维平台功能整理</text>'
        f'<text x="{W - 60}" y="1548" text-anchor="end" fill="{SUBTLE}" font-size="12">screenshots/project_prd_overview.svg</text>'
        f'</svg>'
    )
    return "\n".join(svg)


def render_png(svg_path: Path, png_path: Path) -> bool:
    chrome = os.getenv("CHROME_PATH") or shutil.which("chrome") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not chrome or not Path(chrome).exists():
        return False
    uri = svg_path.resolve().as_uri()
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--allow-file-access-from-files",
        "--force-device-scale-factor=1",
        f"--window-size={W},{H}",
        f"--screenshot={png_path}",
        uri,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return png_path.exists()


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    svg_path = SVG_PATH
    svg_path.write_text(build_svg(), encoding="utf-8")
    print(svg_path)
    if render_png(svg_path, PNG_PATH):
        print(PNG_PATH)


if __name__ == "__main__":
    main()
