from __future__ import annotations

from html import escape
from pathlib import Path
from xml.etree import ElementTree as ET


OUTPUT_DIR = Path("screenshots")
VIEW_W = 1560
VIEW_H = 1000
PNG_W = 2400
PNG_H = 1538


STYLES = {
    1: {
        "slug": "flat_icon",
        "name": "风格 1 · Flat Icon",
        "bg": "#ffffff",
        "panel": "#ffffff",
        "panel_stroke": "#e5e7eb",
        "text": "#111827",
        "muted": "#6b7280",
        "label_bg": "#ffffff",
        "font": "'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif",
        "rx": 10,
        "stroke_width": 1.4,
        "shadow": "shadow",
        "title_size": 22,
        "fills": {
            "input": "#eff6ff",
            "gateway": "#fff7ed",
            "service": "#ffffff",
            "agent": "#faf5ff",
            "automation": "#f0fdfa",
            "external": "#f0fdf4",
            "storage": "#f9fafb",
            "deploy": "#fefce8",
        },
        "strokes": {
            "input": "#bfdbfe",
            "gateway": "#fed7aa",
            "service": "#d1d5db",
            "agent": "#d8b4fe",
            "automation": "#99f6e4",
            "external": "#bbf7d0",
            "storage": "#d1d5db",
            "deploy": "#fde68a",
        },
        "arrows": {
            "main": "#2563eb",
            "external": "#ea580c",
            "ai": "#7c3aed",
            "storage": "#059669",
            "async": "#6b7280",
        },
    },
    2: {
        "slug": "dark_terminal",
        "name": "风格 2 · Dark Terminal",
        "bg": "url(#bg-grad)",
        "panel": "#0f172a",
        "panel_stroke": "#334155",
        "text": "#e2e8f0",
        "muted": "#94a3b8",
        "label_bg": "#0f172a",
        "font": "'Cascadia Code', 'Microsoft YaHei UI', 'Microsoft YaHei', 'SF Mono', Consolas, monospace",
        "rx": 7,
        "stroke_width": 1.3,
        "shadow": "glow-blue",
        "title_size": 20,
        "fills": {
            "input": "#1e3a5f",
            "gateway": "#1c1917",
            "service": "#0f172a",
            "agent": "#1e1b4b",
            "automation": "#052e2b",
            "external": "#052e16",
            "storage": "#111827",
            "deploy": "#422006",
        },
        "strokes": {
            "input": "#3b82f6",
            "gateway": "#f97316",
            "service": "#64748b",
            "agent": "#a855f7",
            "automation": "#14b8a6",
            "external": "#10b981",
            "storage": "#64748b",
            "deploy": "#eab308",
        },
        "arrows": {
            "main": "#3b82f6",
            "external": "#f97316",
            "ai": "#a855f7",
            "storage": "#10b981",
            "async": "#94a3b8",
        },
    },
    3: {
        "slug": "blueprint",
        "name": "风格 3 · Blueprint",
        "bg": "#0a1628",
        "panel": "#0d1f3c",
        "panel_stroke": "#00b4d8",
        "text": "#caf0f8",
        "muted": "#90e0ef",
        "label_bg": "#0a1628",
        "font": "'Microsoft YaHei UI', 'Microsoft YaHei', 'Courier New', monospace",
        "rx": 2,
        "stroke_width": 1.2,
        "shadow": None,
        "title_size": 20,
        "fills": {
            "input": "#0d1f3c",
            "gateway": "#132b4f",
            "service": "#0d1f3c",
            "agent": "#152554",
            "automation": "#103a46",
            "external": "#0d2b3c",
            "storage": "#10233d",
            "deploy": "#302512",
        },
        "strokes": {
            "input": "#48cae4",
            "gateway": "#f77f00",
            "service": "#00b4d8",
            "agent": "#ffffff",
            "automation": "#06d6a0",
            "external": "#48cae4",
            "storage": "#90e0ef",
            "deploy": "#f77f00",
        },
        "arrows": {
            "main": "#00b4d8",
            "external": "#f77f00",
            "ai": "#ffffff",
            "storage": "#06d6a0",
            "async": "#48cae4",
        },
    },
    4: {
        "slug": "notion_clean",
        "name": "风格 4 · Notion Clean",
        "bg": "#ffffff",
        "panel": "#ffffff",
        "panel_stroke": "#e5e7eb",
        "text": "#111827",
        "muted": "#6b7280",
        "label_bg": "#ffffff",
        "font": "'Microsoft YaHei UI', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif",
        "rx": 5,
        "stroke_width": 1.0,
        "shadow": None,
        "title_size": 22,
        "fills": {
            "input": "#f9fafb",
            "gateway": "#f9fafb",
            "service": "#ffffff",
            "agent": "#f9fafb",
            "automation": "#ffffff",
            "external": "#f9fafb",
            "storage": "#ffffff",
            "deploy": "#f9fafb",
        },
        "strokes": {
            "input": "#e5e7eb",
            "gateway": "#e5e7eb",
            "service": "#e5e7eb",
            "agent": "#e5e7eb",
            "automation": "#e5e7eb",
            "external": "#e5e7eb",
            "storage": "#e5e7eb",
            "deploy": "#e5e7eb",
        },
        "arrows": {
            "main": "#3b82f6",
            "external": "#3b82f6",
            "ai": "#3b82f6",
            "storage": "#9ca3af",
            "async": "#d1d5db",
        },
    },
    5: {
        "slug": "glassmorphism",
        "name": "风格 5 · Glassmorphism",
        "bg": "url(#glass-bg)",
        "panel": "#ffffff",
        "panel_stroke": "#ffffff",
        "text": "#f0f6fc",
        "muted": "#8b949e",
        "label_bg": "#0d1117",
        "font": "'Microsoft YaHei UI', 'Microsoft YaHei', 'Inter', -apple-system, 'Segoe UI', sans-serif",
        "rx": 14,
        "stroke_width": 1.1,
        "shadow": "glass-glow",
        "title_size": 22,
        "fills": {
            "input": "#58a6ff",
            "gateway": "#f78166",
            "service": "#ffffff",
            "agent": "#bc8cff",
            "automation": "#3fb950",
            "external": "#58a6ff",
            "storage": "#ffffff",
            "deploy": "#f78166",
        },
        "fill_opacity_by_cat": {
            "input": 0.11,
            "gateway": 0.10,
            "service": 0.06,
            "agent": 0.12,
            "automation": 0.10,
            "external": 0.08,
            "storage": 0.06,
            "deploy": 0.10,
        },
        "strokes": {
            "input": "#58a6ff",
            "gateway": "#f78166",
            "service": "#ffffff",
            "agent": "#bc8cff",
            "automation": "#3fb950",
            "external": "#58a6ff",
            "storage": "#ffffff",
            "deploy": "#f78166",
        },
        "arrows": {
            "main": "#58a6ff",
            "external": "#f78166",
            "ai": "#bc8cff",
            "storage": "#3fb950",
            "async": "#8b949e",
        },
    },
    6: {
        "slug": "claude_official",
        "name": "风格 6 · Claude Official",
        "bg": "#f8f6f3",
        "panel": "#f8f6f3",
        "panel_stroke": "#4a4a4a",
        "text": "#1a1a1a",
        "muted": "#6a6a6a",
        "label_bg": "#f8f6f3",
        "font": "'Microsoft YaHei UI', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif",
        "rx": 13,
        "stroke_width": 2.2,
        "shadow": None,
        "title_size": 22,
        "fills": {
            "input": "#a8c5e6",
            "gateway": "#f4e4c1",
            "service": "#f4e4c1",
            "agent": "#9dd4c7",
            "automation": "#9dd4c7",
            "external": "#a8c5e6",
            "storage": "#e8e6e3",
            "deploy": "#f4e4c1",
        },
        "strokes": {
            "input": "#4a4a4a",
            "gateway": "#4a4a4a",
            "service": "#4a4a4a",
            "agent": "#4a4a4a",
            "automation": "#4a4a4a",
            "external": "#4a4a4a",
            "storage": "#4a4a4a",
            "deploy": "#4a4a4a",
        },
        "arrows": {
            "main": "#5a5a5a",
            "external": "#5a5a5a",
            "ai": "#5a5a5a",
            "storage": "#5a5a5a",
            "async": "#5a5a5a",
        },
    },
    7: {
        "slug": "openai_official",
        "name": "风格 7 · OpenAI Official",
        "bg": "#ffffff",
        "panel": "#ffffff",
        "panel_stroke": "#e5e5e5",
        "text": "#0d0d0d",
        "muted": "#6e6e80",
        "label_bg": "#ffffff",
        "font": "'Microsoft YaHei UI', 'Microsoft YaHei', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif",
        "rx": 9,
        "stroke_width": 1.4,
        "shadow": None,
        "title_size": 22,
        "accent_strip": True,
        "fills": {
            "input": "#ffffff",
            "gateway": "#ffffff",
            "service": "#ffffff",
            "agent": "#ffffff",
            "automation": "#ffffff",
            "external": "#ffffff",
            "storage": "#ffffff",
            "deploy": "#ffffff",
        },
        "strokes": {
            "input": "#e5e5e5",
            "gateway": "#e5e5e5",
            "service": "#e5e5e5",
            "agent": "#e5e5e5",
            "automation": "#e5e5e5",
            "external": "#e5e5e5",
            "storage": "#e5e5e5",
            "deploy": "#e5e5e5",
        },
        "cat_accent": {
            "input": "#1d4ed8",
            "gateway": "#f97316",
            "service": "#71717a",
            "agent": "#10a37f",
            "automation": "#10a37f",
            "external": "#1d4ed8",
            "storage": "#71717a",
            "deploy": "#f97316",
        },
        "arrows": {
            "main": "#10a37f",
            "external": "#1d4ed8",
            "ai": "#10a37f",
            "storage": "#71717a",
            "async": "#71717a",
        },
    },
}


CAT_LABELS = {
    "input": "入口",
    "gateway": "网关",
    "service": "服务",
    "agent": "AI 核心",
    "automation": "自动化",
    "external": "外部系统",
    "storage": "数据",
    "deploy": "部署",
}


NODES = [
    ("browser", 90, 165, 220, 82, "Vue 3 前端", "看板 / APM / SSH", "input"),
    ("nginx", 90, 315, 220, 74, "Nginx 静态站点", "Vite 构建 + /api 代理", "gateway"),
    ("feishu_event", 90, 465, 220, 78, "飞书事件入口", "消息 / URL Challenge", "input"),
    ("deploy", 90, 635, 220, 74, "部署形态", "Docker Compose / K8s", "deploy"),
    ("api", 440, 165, 240, 88, "FastAPI 主服务", "路由 + CORS + 生命周期", "service"),
    ("feishu_cb", 690, 165, 185, 88, "飞书回调服务", "独立 IP / 端口", "service"),
    ("auth", 430, 330, 180, 78, "Auth / RBAC", "会话 + 审批 + 审计", "service"),
    ("routers", 670, 330, 210, 78, "业务 Routers", "日志 / 主机 / 报告 / 链路", "service"),
    ("agent", 430, 510, 220, 88, "LangGraph Agent", "ReAct + 工具 + SSE", "agent"),
    ("scheduler", 670, 510, 210, 88, "APScheduler", "日报 / 巡检 cron", "automation"),
    ("loki", 1010, 160, 180, 70, "Loki", "日志查询 / LogQL", "external"),
    ("prom", 1260, 160, 200, 70, "Prometheus", "指标 / 主机发现", "external"),
    ("sky", 1010, 330, 180, 70, "SkyWalking", "APM 链路追踪", "external"),
    ("remote", 1260, 330, 200, 70, "远程主机", "SSH / MySQL 慢日志", "external"),
    ("ai", 1010, 510, 180, 75, "AI Provider", "Qwen / Claude / OpenAI", "external"),
    ("notify", 1260, 510, 200, 75, "飞书 / 钉钉", "报告推送 + 对话回复", "external"),
    ("redis", 390, 790, 160, 72, "Redis", "Session / 失败计数", "storage"),
    ("sqldb", 590, 790, 175, 72, "SQL DB", "SQLite / MySQL / PG", "storage"),
    ("reports", 805, 790, 160, 72, "Reports", "JSON / Excel", "storage"),
    ("milvus", 1005, 790, 180, 72, "Milvus Memory", "相似事件检索", "storage"),
    ("checkpoint", 1225, 790, 190, 72, "Checkpointer", "SQLite / MemorySaver", "storage"),
]


CONTAINERS = [
    (50, 120, 300, 800, "入口与部署层"),
    (390, 120, 520, 550, "FastAPI 后端与 AI 自动化"),
    (970, 120, 530, 550, "可观测与外部系统"),
    (360, 740, 1140, 170, "数据、记忆与报表持久化"),
]


ARROWS = [
    ([(200, 247), (200, 315)], "main", "加载应用", (244, 283), False),
    ([(310, 352), (370, 352), (370, 209), (440, 209)], "main", "HTTP / SSE / WS", (362, 281), False),
    ([(310, 504), (360, 504), (360, 108), (782, 108), (782, 165)], "async", "POST 事件", (562, 105), False),
    ([(782, 253), (930, 253), (930, 476), (540, 476), (540, 510)], "async", "消息入队", (928, 365), True),
    ([(520, 253), (520, 330)], "main", "认证", (555, 292), False),
    ([(620, 253), (620, 296), (775, 296), (775, 330)], "main", "路由分发", (700, 288), False),
    ([(880, 356), (930, 356), (930, 195), (1010, 195)], "external", "LogQL", (932, 270), False),
    ([(880, 370), (940, 370), (940, 118), (1360, 118), (1360, 160)], "external", "PromQL", (1150, 115), False),
    ([(880, 385), (950, 385), (950, 365), (1010, 365)], "external", "Trace", (954, 412), False),
    ([(880, 400), (940, 400), (940, 442), (1360, 442), (1360, 400)], "external", "SSH / SlowLog", (1135, 438), False),
    ([(540, 598), (540, 682), (1100, 682), (1100, 585)], "ai", "LLM 调用", (815, 675), False),
    ([(600, 598), (600, 716), (1360, 716), (1360, 585)], "ai", "对话回复", (980, 709), False),
    ([(880, 554), (940, 554), (940, 632), (1360, 632), (1360, 585)], "external", "定时推送", (1145, 625), True),
    ([(430, 369), (370, 369), (370, 728), (470, 728), (470, 790)], "storage", "Session", (388, 560), True),
    ([(880, 369), (925, 369), (925, 728), (678, 728), (678, 790)], "storage", "ORM", (918, 610), True),
    ([(775, 598), (775, 708), (885, 708), (885, 790)], "storage", "生成报表", (836, 701), True),
    ([(540, 598), (540, 710), (1095, 710), (1095, 790)], "storage", "记忆读写", (830, 703), True),
    ([(600, 598), (600, 732), (1320, 732), (1320, 790)], "storage", "检查点", (1110, 725), True),
    ([(310, 672), (370, 672), (370, 650), (770, 650), (770, 598)], "async", "部署编排", (565, 643), True),
]


LEGEND = [
    ("main", "主请求 / SSE / WebSocket"),
    ("external", "外部查询 / 推送"),
    ("ai", "AI 推理 / 工具调用"),
    ("storage", "存储 / 记忆读写"),
]


def text_width(text: str, size: int = 12) -> int:
    width = 0
    for char in text:
        width += size if "\u4e00" <= char <= "\u9fff" else int(size * 0.6)
    return width


def add_defs(lines: list[str], style: dict) -> None:
    lines.append("  <defs>")
    if style["slug"] == "dark_terminal":
        lines.append('    <linearGradient id="bg-grad" x1="0%" y1="0%" x2="100%" y2="100%">')
        lines.append('      <stop offset="0%" stop-color="#0f0f1a"/>')
        lines.append('      <stop offset="100%" stop-color="#1a1a2e"/>')
        lines.append("    </linearGradient>")
        lines.append('    <filter id="glow-blue" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0" dy="0" stdDeviation="2" flood-color="#3b82f6" flood-opacity="0.25"/></filter>')
    if style["slug"] == "blueprint":
        lines.append('    <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">')
        lines.append('      <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#112240" stroke-width="0.7"/>')
        lines.append("    </pattern>")
    if style["slug"] == "glassmorphism":
        lines.append('    <linearGradient id="glass-bg" x1="0%" y1="0%" x2="100%" y2="100%">')
        lines.append('      <stop offset="0%" stop-color="#0d1117"/>')
        lines.append('      <stop offset="50%" stop-color="#161b22"/>')
        lines.append('      <stop offset="100%" stop-color="#0d1117"/>')
        lines.append("    </linearGradient>")
        lines.append('    <radialGradient id="glow-a" cx="30%" cy="38%" r="45%"><stop offset="0%" stop-color="#58a6ff" stop-opacity="0.22"/><stop offset="100%" stop-color="#58a6ff" stop-opacity="0"/></radialGradient>')
        lines.append('    <radialGradient id="glow-b" cx="74%" cy="58%" r="38%"><stop offset="0%" stop-color="#bc8cff" stop-opacity="0.18"/><stop offset="100%" stop-color="#bc8cff" stop-opacity="0"/></radialGradient>')
        lines.append('    <filter id="glass-glow" x="-25%" y="-25%" width="150%" height="150%"><feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#000000" flood-opacity="0.22"/></filter>')
    if style["slug"] == "flat_icon":
        lines.append('    <filter id="shadow" x="-15%" y="-15%" width="130%" height="130%"><feDropShadow dx="0" dy="8" stdDeviation="6" flood-color="#111827" flood-opacity="0.08"/></filter>')
    for key, color in style["arrows"].items():
        lines.append(f'    <marker id="arrow-{key}" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
        lines.append(f'      <polygon points="0 0, 10 3.5, 0 7" fill="{color}"/>')
        lines.append("    </marker>")
    lines.append("  </defs>")


def add_background(lines: list[str], style: dict) -> None:
    lines.append(f'  <rect x="0" y="0" width="{VIEW_W}" height="{VIEW_H}" fill="{style["bg"]}"/>')
    if style["slug"] == "blueprint":
        lines.append(f'  <rect x="0" y="0" width="{VIEW_W}" height="{VIEW_H}" fill="url(#grid)" opacity="0.75"/>')
    if style["slug"] == "glassmorphism":
        lines.append(f'  <rect x="0" y="0" width="{VIEW_W}" height="{VIEW_H}" fill="url(#glow-a)"/>')
        lines.append(f'  <rect x="0" y="0" width="{VIEW_W}" height="{VIEW_H}" fill="url(#glow-b)"/>')


def add_container(lines: list[str], style: dict, x: int, y: int, w: int, h: int, title: str) -> None:
    dash = ' stroke-dasharray="7,5"' if style["slug"] != "claude_official" else ""
    opacity = 0.55 if style["slug"] in ("dark_terminal", "blueprint") else (0.04 if style["slug"] == "glassmorphism" else 0)
    lines.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{style["rx"]}" fill="{style["panel"]}" fill-opacity="{opacity}" stroke="{style["panel_stroke"]}" stroke-opacity="0.75" stroke-width="1"{dash}/>')
    lines.append(f'  <text x="{x + 16}" y="{y + 24}" fill="{style["muted"]}" font-size="12" font-weight="700" letter-spacing="0.06em">{escape(title)}</text>')


def add_node(lines: list[str], style: dict, node: tuple) -> None:
    node_id, x, y, w, h, title, subtitle, category = node
    fill = style["fills"][category]
    stroke = style["strokes"][category]
    opacity = style.get("fill_opacity_by_cat", {}).get(category, 1.0)
    filter_attr = f' filter="url(#{style["shadow"]})"' if style.get("shadow") and category in ("agent", "input", "service") else ""
    lines.append(f'  <g id="node-{node_id}">')
    if style["slug"] == "glassmorphism":
        lines.append(f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{style["rx"]}" fill="#ffffff" fill-opacity="0.025"/>')
    lines.append(f'    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{style["rx"]}" fill="{fill}" fill-opacity="{opacity}" stroke="{stroke}" stroke-width="{style["stroke_width"]}"{filter_attr}/>')
    if style.get("accent_strip"):
        lines.append(f'    <rect x="{x}" y="{y}" width="5" height="{h}" rx="2" fill="{style["cat_accent"][category]}"/>')
    if style["slug"] == "glassmorphism":
        lines.append(f'    <line x1="{x + 10}" y1="{y + 1}" x2="{x + w - 10}" y2="{y + 1}" stroke="#ffffff" stroke-opacity="0.24" stroke-width="1"/>')
    if style["slug"] in ("notion_clean", "openai_official"):
        lines.append(f'    <text x="{x + 16}" y="{y + 20}" fill="{style["muted"]}" font-size="10" font-weight="600" letter-spacing="0.08em">{CAT_LABELS[category]}</text>')
        title_y = y + 43
    else:
        lines.append(f'    <circle cx="{x + 18}" cy="{y + 19}" r="5" fill="{stroke}"/>')
        title_y = y + 31
    lines.append(f'    <text x="{x + 16}" y="{title_y}" fill="{style["text"]}" font-size="15" font-weight="700">{escape(title)}</text>')
    lines.append(f'    <text x="{x + 16}" y="{title_y + 22}" fill="{style["muted"]}" font-size="12" font-weight="400">{escape(subtitle)}</text>')
    lines.append("  </g>")


def add_arrow(lines: list[str], style: dict, points: list[tuple[int, int]], kind: str, label: str, label_xy: tuple[int, int], dashed: bool) -> None:
    color = style["arrows"][kind]
    path = "M " + " L ".join(f"{x},{y}" for x, y in points)
    dash = ' stroke-dasharray="6,4"' if dashed else ""
    stroke_width = 2.1 if kind in ("main", "ai") else 1.7
    if style["slug"] in ("blueprint", "notion_clean", "openai_official"):
        stroke_width -= 0.3
    if style["slug"] == "claude_official":
        stroke_width = 2.0 if not dashed else 1.7
    lines.append(f'  <path d="{path}" fill="none" stroke="{color}" stroke-width="{stroke_width:.1f}" stroke-linejoin="round" stroke-linecap="round" marker-end="url(#arrow-{kind})"{dash}/>')
    label_x, label_y = label_xy
    width = text_width(label, 12) + 14
    lines.append(f'  <rect x="{label_x - width / 2:.1f}" y="{label_y - 15:.1f}" width="{width}" height="20" rx="5" fill="{style["label_bg"]}" fill-opacity="0.96"/>')
    lines.append(f'  <text x="{label_x}" y="{label_y}" fill="{color}" font-size="12" font-weight="600" text-anchor="middle">{escape(label)}</text>')


def add_legend(lines: list[str], style: dict) -> None:
    x = 44
    y = VIEW_H - 60
    fill = style["panel"] if style["slug"] in ("dark_terminal", "blueprint") else style["label_bg"]
    opacity = 0.72 if style["slug"] in ("dark_terminal", "blueprint") else (0.07 if style["slug"] == "glassmorphism" else 0.96)
    lines.append(f'  <rect x="{x - 14}" y="{y - 22}" width="610" height="48" rx="10" fill="{fill}" fill-opacity="{opacity}" stroke="{style["panel_stroke"]}" stroke-opacity="0.45"/>')
    offset = x
    for kind, label in LEGEND:
        color = style["arrows"][kind]
        lines.append(f'  <line x1="{offset}" y1="{y}" x2="{offset + 34}" y2="{y}" stroke="{color}" stroke-width="2" marker-end="url(#arrow-{kind})"/>')
        lines.append(f'  <text x="{offset + 42}" y="{y + 4}" fill="{style["muted"]}" font-size="12">{escape(label)}</text>')
        offset += 144


def generate_svg(index: int, style: dict) -> Path:
    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xml:lang="zh-CN" viewBox="0 0 {VIEW_W} {VIEW_H}" width="{PNG_W}" height="{PNG_H}">',
        "  <style>",
        f"    text {{ font-family: {style['font']}; }}",
        "  </style>",
    ]
    add_defs(lines, style)
    add_background(lines, style)
    title = "AI Ops 智能运维平台 · 项目架构图"
    subtitle = "Vue 3 + FastAPI + LangGraph + Loki / Prometheus / SkyWalking + 独立飞书回调服务"
    lines.append(f'  <text x="44" y="54" fill="{style["text"]}" font-size="{style["title_size"]}" font-weight="800">{escape(title)}</text>')
    lines.append(f'  <text x="44" y="82" fill="{style["muted"]}" font-size="13">{escape(style["name"])} ｜ {escape(subtitle)}</text>')
    for container in CONTAINERS:
        add_container(lines, style, *container)
    for node in NODES:
        add_node(lines, style, node)
    for arrow in ARROWS:
        add_arrow(lines, style, *arrow)
    add_legend(lines, style)
    lines.append(f'  <text x="{VIEW_W - 40}" y="{VIEW_H - 32}" fill="{style["muted"]}" font-size="11" text-anchor="end">输出文件：screenshots/project_architecture_style_{index}_{style["slug"]}</text>')
    lines.append("</svg>")

    OUTPUT_DIR.mkdir(exist_ok=True)
    output = OUTPUT_DIR / f"project_architecture_style_{index}_{style['slug']}.svg"
    output.write_text("\n".join(lines), encoding="utf-8")
    ET.parse(output)
    return output


def main() -> None:
    for index, style in STYLES.items():
        path = generate_svg(index, style)
        print(path)


if __name__ == "__main__":
    main()

