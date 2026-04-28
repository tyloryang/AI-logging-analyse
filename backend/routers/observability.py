"""可观测性平台总览路由

端点：
  GET  /api/observability/overview   — 汇总统计（告警数/错误数/Trace量/Grafana看板数）
  GET  /api/observability/alerts     — 最近告警列表
  GET  /api/observability/traces     — 最近 Trace 列表
  GET  /api/observability/services   — 有异常的服务拓扑
  POST /api/observability/analyze    — 流式 AI 分析（SSE）
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from state import loki, prom, analyzer, load_hosts_list
from skywalking_client import sw_client, check_connectivity as sw_check

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/observability", tags=["observability"])

# Grafana 看板定义（uid 与 Grafana 官方 dashboard uid 对齐）
_GRAFANA_BOARD_DEFS = [
    {"id": "node-exporter",  "title": "Node Exporter Full",    "uid": "rYdddlPWk"},
    {"id": "jvm",            "title": "JVM Micrometer",        "uid": "4PSsg1MZz"},
    {"id": "mysql",          "title": "MySQL Overview",        "uid": "MQWgroiiz"},
    {"id": "redis",          "title": "Redis Dashboard",       "uid": "x7ozmSZMk"},
]

def _build_grafana_boards():
    """每次调用时读取 env + settings.json，支持热更新和自定义看板"""
    base = os.getenv("GRAFANA_URL", "").strip().rstrip("/")
    # 合并默认 + 自定义
    try:
        settings_file = Path(__file__).resolve().parent.parent / "data" / "settings.json"
        custom_boards: list[dict] = []
        if settings_file.exists():
            d = json.loads(settings_file.read_text(encoding="utf-8"))
            custom_boards = d.get("grafana_boards", [])
    except Exception:
        custom_boards = []

    combined = list(_GRAFANA_BOARD_DEFS)
    existing_ids = {b["id"] for b in combined}
    for b in custom_boards:
        if b.get("id") not in existing_ids:
            combined.append(b)

    result = []
    for b in combined:
        if b.get("url"):
            result.append({**b})
        elif base and b.get("uid"):
            result.append({**b, "url": f"{base}/d/{b['uid']}/{b['id']}"})
        else:
            result.append({**b, "url": ""})
    return result


# ── 辅助：从 Loki 获取各服务错误数 ─────────────────────────────────────────

async def _get_loki_error_count(hours: int = 1) -> tuple[int, list[dict]]:
    """返回 (total_error_count, [{service, count}]) """
    try:
        services_raw = await loki.get_services()
        total = 0
        breakdown = []
        for svc in services_raw:
            cnt = svc.get("error_count", 0) or 0
            total += cnt
            if cnt > 0:
                breakdown.append({"service": svc.get("name", ""), "count": cnt})
        breakdown.sort(key=lambda x: x["count"], reverse=True)
        return total, breakdown
    except Exception as e:
        logger.warning("[obs] Loki error count failed: %s", e)
        return 0, []


# ── 辅助：从 SkyWalking 获取 Trace 数 ──────────────────────────────────────

async def _get_sw_trace_count(hours: int = 1) -> tuple[int, list[dict]]:
    """返回 (trace_count, recent_traces)"""
    try:
        result = await sw_client.get_traces(hours=hours, page=1, page_size=20)
        traces = result.get("traces", [])
        total = result.get("total", len(traces))
        recent = []
        for t in traces[:10]:
            recent.append({
                "trace_id":   t.get("traceIds", [""])[0] if t.get("traceIds") else t.get("key", ""),
                "service":    t.get("endpointNames", [""])[0] if t.get("endpointNames") else "",
                "endpoint":   t.get("endpointNames", ["--"])[0] if t.get("endpointNames") else "--",
                "duration":   t.get("duration", 0),
                "start_time": t.get("start", ""),
                "error":      t.get("isError", False),
            })
        return total, recent
    except Exception as e:
        logger.warning("[obs] SkyWalking trace count failed: %s", e)
        return 0, []


# ── 辅助：从 Prometheus 获取告警数（alertmanager alerts） ──────────────────

async def _get_alert_count() -> tuple[int, list[dict]]:
    """返回 (alert_count, recent_alerts)"""
    try:
        # 尝试通过 Prometheus ALERTS 指标
        result = await prom.query('ALERTS{alertstate="firing"}', timeout=5)
        data = result.get("data", {}).get("result", [])
        alerts = []
        for item in data:
            metric = item.get("metric", {})
            alerts.append({
                "service":    metric.get("job", metric.get("instance", "unknown")),
                "name":       metric.get("alertname", "Unknown Alert"),
                "severity":   metric.get("severity", "warning"),
                "namespace":  metric.get("namespace", "production"),
                "time":       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            })
        return len(alerts), alerts[:10]
    except Exception as e:
        logger.warning("[obs] Alert count failed: %s", e)
        return 0, []


# ── 辅助：构造有问题的服务列表（根因中心数据） ─────────────────────────────

async def _get_problem_services(error_breakdown: list[dict], recent_alerts: list[dict]) -> list[dict]:
    """合并 Loki 错误服务 + 告警服务，生成根因中心卡片数据"""
    service_map: dict[str, dict] = {}

    for item in error_breakdown:
        svc = item["service"]
        if svc not in service_map:
            service_map[svc] = {
                "service":  svc,
                "errors":   0,
                "alerts":   0,
                "traces":   0,
                "severity": "warning",
                "summary":  "",
            }
        service_map[svc]["errors"] += item["count"]
        service_map[svc]["severity"] = "error" if item["count"] > 50 else "warning"
        service_map[svc]["summary"] = f"最近 1h 产生 {item['count']} 条错误日志"

    for alert in recent_alerts:
        svc = alert["service"]
        if svc not in service_map:
            service_map[svc] = {
                "service":  svc,
                "errors":   0,
                "alerts":   0,
                "traces":   0,
                "severity": alert.get("severity", "warning"),
                "summary":  alert.get("name", ""),
            }
        service_map[svc]["alerts"] += 1

    result = sorted(service_map.values(), key=lambda x: (x["alerts"] + x["errors"]), reverse=True)
    return result[:6]


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/overview
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/overview")
async def get_overview(hours: int = Query(1, ge=1, le=24)):
    """
    汇总返回：
      - alert_count      告警触发数
      - error_count      服务错误数
      - trace_count      Trace 量
      - grafana_count    Grafana 看板数
      - recent_alerts    最近告警列表
      - recent_traces    最近 Trace 列表
      - problem_services 有问题的服务（根因中心）
      - grafana_boards   看板列表
    """
    (alert_count, recent_alerts), \
    (error_count, error_breakdown), \
    (trace_count, recent_traces) = await asyncio.gather(
        _get_alert_count(),
        _get_loki_error_count(hours),
        _get_sw_trace_count(hours),
    )

    problem_services = await _get_problem_services(error_breakdown, recent_alerts)

    grafana_boards = _build_grafana_boards()
    return {
        "alert_count":      alert_count,
        "error_count":      error_count,
        "trace_count":      trace_count,
        "grafana_count":    len(grafana_boards),
        "hours":            hours,
        "recent_alerts":    recent_alerts,
        "recent_traces":    recent_traces,
        "problem_services": problem_services,
        "grafana_boards":   grafana_boards,
        "grafana_url":      os.getenv("GRAFANA_URL", "").strip().rstrip("/"),
        "error_breakdown":  error_breakdown,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/alerts
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/alerts")
async def get_alerts(limit: int = Query(20, ge=1, le=100)):
    _, alerts = await _get_alert_count()
    return {"data": alerts, "total": len(alerts)}


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/traces
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/traces")
async def get_traces(hours: int = Query(1), limit: int = Query(20)):
    _, traces = await _get_sw_trace_count(hours)
    return {"data": traces[:limit], "total": len(traces)}


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/services
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/services")
async def get_problem_services(hours: int = Query(1)):
    (_, recent_alerts), (_, error_breakdown) = await asyncio.gather(
        _get_alert_count(),
        _get_loki_error_count(hours),
    )
    services = await _get_problem_services(error_breakdown, recent_alerts)
    return {"data": services}


# ══════════════════════════════════════════════════════════════════════════════
# 端点：POST /api/observability/analyze  （SSE 流式 AI 分析）
# ══════════════════════════════════════════════════════════════════════════════

class AnalyzeRequest:
    pass

from pydantic import BaseModel

class AnalyzeReq(BaseModel):
    question: str = "分析当前系统健康状况"
    hours: int = 1

async def _get_host_metrics() -> list[dict]:
    """获取 CMDB 所有主机的 Prometheus 实时指标。"""
    try:
        cmdb_hosts = load_hosts_list()
        if not cmdb_hosts:
            return []
        all_metrics    = await prom.get_all_host_metrics()
        all_partitions = await prom.get_all_partitions()
        # 建立 ip → instance 映射
        discovered = await prom.discover_hosts()
        ip_to_inst = {h["ip"]: h["instance"] for h in discovered if h.get("ip")}

        result = []
        for h in cmdb_hosts:
            ip   = h.get("ip", "")
            inst = ip_to_inst.get(ip, f"{ip}:9100")
            m    = all_metrics.get(inst, {})
            parts = all_partitions.get(inst, [])
            # 取根分区使用率
            root_disk = next((p["usage_pct"] for p in parts if p.get("mountpoint") == "/"), None)
            result.append({
                "hostname":  h.get("hostname") or ip,
                "ip":        ip,
                "group":     h.get("group", ""),
                "env":       h.get("env", ""),
                "cpu":       m.get("cpu_usage"),
                "mem":       m.get("mem_usage"),
                "disk_root": root_disk,
                "load5":     m.get("load5"),
                "has_data":  bool(m),
            })
        return result
    except Exception as e:
        logger.warning("[analyze] 获取主机指标失败: %s", e)
        return []


async def _get_k8s_summary() -> dict:
    """获取 K8s 集群摘要（Pod 状态）。"""
    try:
        from services.k8s_store import load_k8s_clusters
        clusters = load_k8s_clusters()
        if not clusters:
            return {}
        from kubernetes import client as k8s_client, config as k8s_config
        default_cluster = next((c for c in clusters if c.get("default")), clusters[0])
        kubeconfig = default_cluster.get("kubeconfig_content") or default_cluster.get("kubeconfig_path")
        if not kubeconfig:
            return {}
        # 简化：直接返回已知信息
        return {"cluster_name": default_cluster.get("name", "default")}
    except Exception:
        return {}


@router.post("/analyze")
async def analyze_observability(req: AnalyzeReq):
    """对可观测性数据做全面 AI 流式分析（含服务器状态）"""

    async def _stream():
        # 1. 并发收集所有上下文数据
        try:
            results = await asyncio.gather(
                _get_alert_count(),
                _get_loki_error_count(req.hours),
                _get_sw_trace_count(req.hours),
                _get_host_metrics(),
                return_exceptions=True,
            )
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
            return

        (alert_count, recent_alerts) = results[0] if not isinstance(results[0], Exception) else (0, [])
        (error_count, error_breakdown) = results[1] if not isinstance(results[1], Exception) else (0, [])
        (trace_count, recent_traces)  = results[2] if not isinstance(results[2], Exception) else (0, [])
        host_metrics = results[3] if not isinstance(results[3], Exception) else []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 2. 构造全面 prompt
        context_lines = [
            f"当前时间：{now_str}",
            f"统计范围：最近 {req.hours} 小时",
            "",
        ]

        # ── 服务器状态 ──────────────────────────────────────────
        context_lines.append("## 服务器实时状态")
        if host_metrics:
            has_data_hosts = [h for h in host_metrics if h["has_data"]]
            no_data_hosts  = [h for h in host_metrics if not h["has_data"]]

            if has_data_hosts:
                # 危险指标（CPU>80 / 内存>85 / 磁盘>85）
                danger = []
                warn   = []
                normal = []
                for h in has_data_hosts:
                    issues = []
                    if h["cpu"] is not None and h["cpu"] > 80:
                        issues.append(f"CPU {h['cpu']:.0f}%")
                    if h["mem"] is not None and h["mem"] > 85:
                        issues.append(f"内存 {h['mem']:.0f}%")
                    if h["disk_root"] is not None and h["disk_root"] > 85:
                        issues.append(f"磁盘 {h['disk_root']:.0f}%")
                    if issues:
                        if any(">90" in i or int(''.join(filter(str.isdigit, i.split()[1].rstrip('%'))))>=90 for i in issues if '%' in i):
                            danger.append((h, issues))
                        else:
                            warn.append((h, issues))
                    else:
                        normal.append(h)

                context_lines.append(f"- 在线主机：{len(has_data_hosts)} 台，离线/无数据：{len(no_data_hosts)} 台")
                if danger:
                    context_lines.append(f"- 🔴 严重异常主机（{len(danger)} 台）：")
                    for h, issues in danger[:5]:
                        context_lines.append(f"    {h['hostname']}({h['ip']}) {' / '.join(issues)}")
                if warn:
                    context_lines.append(f"- 🟡 警告主机（{len(warn)} 台）：")
                    for h, issues in warn[:5]:
                        context_lines.append(f"    {h['hostname']}({h['ip']}) {' / '.join(issues)}")
                if normal:
                    context_lines.append(f"- ✅ 正常主机：{len(normal)} 台")

                # 最高资源占用
                by_cpu  = sorted([h for h in has_data_hosts if h["cpu"] is not None],  key=lambda x: -x["cpu"])
                by_mem  = sorted([h for h in has_data_hosts if h["mem"] is not None],  key=lambda x: -x["mem"])
                by_disk = sorted([h for h in has_data_hosts if h["disk_root"] is not None], key=lambda x: -x["disk_root"])
                if by_cpu:
                    context_lines.append(f"- CPU 最高：{by_cpu[0]['hostname']} {by_cpu[0]['cpu']:.1f}%")
                if by_mem:
                    context_lines.append(f"- 内存最高：{by_mem[0]['hostname']} {by_mem[0]['mem']:.1f}%")
                if by_disk:
                    context_lines.append(f"- 磁盘最高：{by_disk[0]['hostname']} {by_disk[0]['disk_root']:.1f}%（根分区）")

            if no_data_hosts:
                names = ", ".join(h["hostname"] for h in no_data_hosts[:5])
                context_lines.append(f"- 无 Prometheus 数据（未安装 node_exporter 或离线）：{names}")
        else:
            context_lines.append("- 暂无主机数据（Prometheus 未配置或无 CMDB 主机）")

        # ── 告警 ────────────────────────────────────────────────
        context_lines += ["", "## 告警状态"]
        context_lines.append(f"- 活跃告警：{alert_count} 条")
        if recent_alerts:
            # 按严重度统计
            by_sev: dict[str, int] = {}
            for a in recent_alerts:
                s = a.get("severity", "unknown")
                by_sev[s] = by_sev.get(s, 0) + 1
            for sev, cnt in sorted(by_sev.items(), key=lambda x: {"critical":0,"error":1,"warning":2}.get(x[0],9)):
                context_lines.append(f"  - {sev}: {cnt} 条")
            context_lines.append("- 最近告警：")
            for a in recent_alerts[:5]:
                context_lines.append(f"  [{a.get('severity','?')}] {a.get('service','?')}: {a.get('alertname') or a.get('name','?')}")

        # ── 日志错误 ────────────────────────────────────────────
        context_lines += ["", "## 日志错误（Loki）"]
        context_lines.append(f"- 错误日志总数：{error_count} 条（最近 {req.hours} 小时）")
        if error_breakdown:
            context_lines.append("- 错误最多的服务：")
            for e in error_breakdown[:8]:
                context_lines.append(f"  - {e['service']}: {e['count']} 条")

        # ── APM Trace ───────────────────────────────────────────
        context_lines += ["", "## APM 链路追踪（SkyWalking）"]
        context_lines.append(f"- Trace 总量：{trace_count}")
        if recent_traces:
            errors = [t for t in recent_traces if t.get("error")]
            slow   = [t for t in recent_traces if t.get("duration", 0) > 1000]
            if errors:
                context_lines.append(f"- 错误 Trace：{len(errors)} 条")
                for t in errors[:3]:
                    context_lines.append(f"  ❌ {t.get('service','?')} {t.get('endpoint','?')} {t.get('duration',0)}ms")
            if slow:
                context_lines.append(f"- 慢请求（>1s）：{len(slow)} 条")

        prompt = "\n".join(context_lines)
        prompt += f"\n\n---\n用户问题：{req.question}"

        system = (
            "你是一名资深 SRE 工程师，负责全栈运维分析。"
            "请根据以下全面的运维数据（服务器状态 + 告警 + 日志 + 链路追踪），"
            "给出系统当前健康状况的综合评估和优先处理建议。\n"
            "输出格式：\n"
            "## 🖥️ 服务器状况\n（分析 CPU/内存/磁盘异常，点出需关注的主机）\n"
            "## 🚨 告警与错误\n（归纳告警模式和日志错误根因）\n"
            "## 🔗 链路追踪\n（是否有慢接口或错误接口）\n"
            "## ✅ 优先处理建议\n（编号列表，最多5条，按紧急程度排序）\n"
            "语言简洁专业，每节不超过5行。"
        )

        # 3. 流式输出
        try:
            full_prompt = f"{system}\n\n{prompt}"
            async for chunk in analyzer.provider.stream(full_prompt, max_tokens=2000):
                yield f"data: {json.dumps({'type':'token','text':chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type':'done'})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ══════════════════════════════════════════════════════════════════════════════
# Grafana 看板管理（自定义看板增删改查）
# 自定义看板存储在 data/settings.json["grafana_boards"]
# ══════════════════════════════════════════════════════════════════════════════

from pathlib import Path as _Path

_SETTINGS_FILE = _Path(__file__).resolve().parent.parent / "data" / "settings.json"


def _load_settings() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_settings(data: dict) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _all_boards_raw() -> list[dict]:
    """合并默认看板 + 自定义看板"""
    custom: list[dict] = _load_settings().get("grafana_boards", [])
    combined = list(_GRAFANA_BOARD_DEFS)
    existing_ids = {b["id"] for b in combined}
    for b in custom:
        if b.get("id") not in existing_ids:
            combined.append(b)
    return combined


class GrafanaBoardIn(BaseModel):
    title: str
    uid: str = ""
    url: str = ""   # 完整 URL（直接填写时优先；uid 用于拼接）


@router.get("/grafana/boards")
async def list_grafana_boards():
    """返回全部看板（默认 + 自定义），附带完整 URL"""
    base = os.getenv("GRAFANA_URL", "").strip().rstrip("/")
    boards = []
    for b in _all_boards_raw():
        full_url = b.get("url") or (f"{base}/d/{b['uid']}/{b['id']}" if b.get("uid") else "")
        boards.append({**b, "url": full_url, "custom": b.get("custom", False)})
    return {"boards": boards, "grafana_url": base}


@router.post("/grafana/boards")
async def add_grafana_board(board: GrafanaBoardIn):
    """添加自定义 Grafana 看板"""
    import uuid as _uuid
    settings = _load_settings()
    customs: list[dict] = settings.get("grafana_boards", [])
    new_board = {
        "id": f"custom-{_uuid.uuid4().hex[:8]}",
        "title": board.title.strip(),
        "uid": board.uid.strip(),
        "url": board.url.strip(),
        "custom": True,
    }
    customs.append(new_board)
    settings["grafana_boards"] = customs
    _save_settings(settings)
    return {"ok": True, "board": new_board}


@router.delete("/grafana/boards/{board_id}")
async def delete_grafana_board(board_id: str):
    """删除自定义 Grafana 看板（默认看板不可删）"""
    settings = _load_settings()
    customs: list[dict] = settings.get("grafana_boards", [])
    before = len(customs)
    customs = [b for b in customs if b.get("id") != board_id]
    if len(customs) == before:
        # 尝试删除默认看板 → 拒绝
        if any(b["id"] == board_id for b in _GRAFANA_BOARD_DEFS):
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(status_code=400, detail="默认看板不可删除")
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=404, detail="看板不存在")
    settings["grafana_boards"] = customs
    _save_settings(settings)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# Grafana 自动发现：调用 Grafana HTTP API 获取全部看板
# ══════════════════════════════════════════════════════════════════════════════

def _read_grafana_settings() -> tuple[str, str]:
    """直接从 settings.json 读取 grafana_url 和 grafana_api_key，比 env 更实时。"""
    settings_file = Path(__file__).resolve().parent.parent / "data" / "settings.json"
    try:
        d = json.loads(settings_file.read_text(encoding="utf-8"))
        base    = d.get("grafana_url", "").strip().rstrip("/")
        api_key = d.get("grafana_api_key", "").strip()
        return base, api_key
    except Exception:
        return (os.getenv("GRAFANA_URL", "") or "").strip().rstrip("/"), \
               (os.getenv("GRAFANA_API_KEY", "") or "").strip()


@router.get("/grafana/discover")
async def discover_grafana_boards():
    """
    调用 Grafana /api/search 自动发现所有已安装看板。
    需要在系统配置中填写 Grafana URL 和 API Key（或开启匿名访问）。
    """
    import httpx

    base, api_key = _read_grafana_settings()

    if not base:
        return {"boards": [], "error": "未配置 GRAFANA_URL，请先在系统配置中填写 Grafana 地址", "grafana_url": ""}

    headers: dict[str, str] = {}
    if api_key:
        # 兼容用户直接粘贴带 "Bearer " 前缀的 token
        token = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        headers["Authorization"] = token

    search_url = f"{base}/api/search"
    logger.info("[grafana-discover] GET %s  api_key_set=%s", search_url, bool(api_key))

    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False, headers=headers) as client:
            resp = await client.get(search_url, params={"type": "dash-db", "limit": 500})
            logger.info("[grafana-discover] status=%s", resp.status_code)
            resp.raise_for_status()
            raw: list[dict] = resp.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        body_text = e.response.text[:200]
        if status == 401:
            msg = "API Key 无效或已过期（401 Unauthorized）"
        elif status == 403:
            msg = "API Key 权限不足，需要 Viewer 以上角色（403 Forbidden）"
        else:
            msg = f"Grafana 返回 {status}：{body_text}"
        logger.warning("[grafana-discover] error: %s", msg)
        return {"boards": [], "error": msg, "grafana_url": base}
    except httpx.ConnectError as e:
        msg = f"无法连接 Grafana（{base}）：{e}"
        logger.warning("[grafana-discover] connect error: %s", msg)
        return {"boards": [], "error": msg, "grafana_url": base}
    except httpx.TimeoutException:
        msg = f"连接 Grafana 超时（{base}），请检查地址和网络"
        logger.warning("[grafana-discover] timeout: %s", base)
        return {"boards": [], "error": msg, "grafana_url": base}
    except Exception as e:
        logger.exception("[grafana-discover] unexpected error")
        return {"boards": [], "error": str(e), "grafana_url": base}

    boards = []
    for item in raw:
        uid      = item.get("uid", "")
        url_path = item.get("url", "")
        full_url = f"{base}{url_path}" if url_path.startswith("/") else url_path
        boards.append({
            "id":     uid or str(item.get("id", "")),
            "uid":    uid,
            "title":  item.get("title", ""),
            "url":    full_url,
            "tags":   item.get("tags", []),
            "folder": item.get("folderTitle", "General"),
            "custom": False,
        })

    boards.sort(key=lambda b: (b["folder"], b["title"]))
    logger.info("[grafana-discover] found %d boards", len(boards))
    return {"boards": boards, "total": len(boards), "grafana_url": base}


@router.get("/grafana/test")
async def test_grafana_connection():
    """诊断 Grafana 连通性，返回详细状态（供排查自动发现失败时使用）"""
    import httpx

    base, api_key = _read_grafana_settings()

    result = {
        "grafana_url":   base,
        "api_key_set":   bool(api_key),
        "version":       "",
        "health_ok":     False,
        "search_ok":     False,
        "search_count":  0,
        "health_error":  "",
        "search_error":  "",
    }

    if not base:
        result["health_error"] = "GRAFANA_URL 未配置"
        return result

    headers: dict[str, str] = {}
    if api_key:
        token = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        headers["Authorization"] = token

    async with httpx.AsyncClient(timeout=8.0, trust_env=False, headers=headers) as client:
        # 1. 健康检查（无需认证），同时读取版本号
        try:
            r = await client.get(f"{base}/api/health")
            result["health_ok"] = r.status_code == 200
            if result["health_ok"]:
                try:
                    result["version"] = r.json().get("version", "")
                except Exception:
                    pass
            else:
                result["health_error"] = f"HTTP {r.status_code}"
        except Exception as e:
            result["health_error"] = str(e)

        # 2. 搜索接口（需要认证或匿名）— 拉取全量以获得准确数量
        try:
            r = await client.get(f"{base}/api/search", params={"type": "dash-db", "limit": 500})
            if r.status_code == 200:
                result["search_ok"] = True
                result["search_count"] = len(r.json())
            elif r.status_code == 401:
                result["search_error"] = "401 Unauthorized：需要 API Key 或开启匿名访问"
            elif r.status_code == 403:
                result["search_error"] = "403 Forbidden：API Key 权限不足"
            else:
                result["search_error"] = f"HTTP {r.status_code}: {r.text[:100]}"
        except Exception as e:
            result["search_error"] = str(e)

    return result


# ── Grafana 反向代理 ──────────────────────────────────────────────────────────
# 前端 iframe 指向 /api/grafana-proxy/<path>，后端透明转发并注入 API Key。
# 这样浏览器不需要登录 Grafana，认证完全由后端承担。

from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response as _Response
import re as _re


@router.websocket("/grafana-proxy/{gpath:path}")
async def grafana_ws_proxy(websocket: WebSocket, gpath: str):
    """WebSocket 代理：转发 Grafana Live (/api/live/ws) 连接"""
    import websockets as _ws

    base, api_key = _read_grafana_settings()
    if not base:
        await websocket.close(code=1011, reason="GRAFANA_URL 未配置")
        return

    qs = websocket.url.query
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    target = f"{ws_base}/{gpath}" + (f"?{qs}" if qs else "")

    extra_headers = {}
    if api_key:
        token = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        extra_headers["Authorization"] = token

    await websocket.accept()
    try:
        async with _ws.connect(target, additional_headers=extra_headers, ssl=None) as upstream:
            async def _up():
                try:
                    async for msg in upstream:
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception:
                    pass

            async def _down():
                try:
                    async for msg in websocket.iter_bytes():
                        await upstream.send(msg)
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass

            await asyncio.gather(_up(), _down())
    except Exception as e:
        logger.debug("[grafana-ws] upstream error: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.api_route(
    "/grafana-proxy/{gpath:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def grafana_proxy(gpath: str, request: Request):
    base, api_key = _read_grafana_settings()

    if not base:
        return _Response(content="GRAFANA_URL 未配置", status_code=503)

    qs = request.url.query
    target_url = f"{base}/{gpath}" + (f"?{qs}" if qs else "")

    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "origin", "referer", "authorization", "cookie")
    }
    if api_key:
        token = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        forward_headers["Authorization"] = token

    body = await request.body()

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                content=body or None,
            )
    except Exception as e:
        return _Response(content=str(e), status_code=502)

    skip_headers = {"transfer-encoding", "content-encoding", "content-length",
                    "x-frame-options", "content-security-policy"}
    resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in skip_headers
    }

    content = resp.content
    content_type = resp.headers.get("content-type", "")
    proxy_base = "/api/observability/grafana-proxy"

    if "text/html" in content_type:
        text = content.decode("utf-8", errors="replace")

        # ① 重写 Grafana boot data 中的 appSubUrl / appUrl
        #    appSubUrl 告诉 Grafana SPA 它的客户端路由根路径，必须与代理前缀一致
        #    否则 SPA 会把 /api/observability/grafana-proxy/d/xxx 当成未知路由报 404
        grafana_origin_esc = _re.escape(base)
        text = _re.sub(
            r'"appSubUrl"\s*:\s*"[^"]*"',
            f'"appSubUrl":"{proxy_base}"',
            text,
        )
        text = _re.sub(
            rf'"appUrl"\s*:\s*"[^"]*"',
            f'"appUrl":"{proxy_base}/"',
            text,
        )

        # ② 注入 <base href> + fetch/XHR 拦截脚本，放在 <head> 最前面
        #    <base href> 让 HTML 中的相对路径资源走代理
        #    fetch/XHR 拦截让 SPA 运行时的数据 API 请求也走代理
        head_inject = f"""<base href="{proxy_base}/">
<script>
(function(){{
  var _pb={json.dumps(proxy_base)};
  function _rw(u){{
    if(typeof u==='string'&&u.startsWith('/')&&!u.startsWith(_pb))
      return _pb+u;
    return u;
  }}
  var _f=window.fetch;
  window.fetch=function(u,o){{return _f.call(this,_rw(u),o);}};
  var _xo=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(m,u){{
    arguments[1]=_rw(u);return _xo.apply(this,arguments);
  }};
}})();
</script>"""
        if "<head>" in text:
            text = text.replace("<head>", "<head>" + head_inject, 1)
        elif "<Head>" in text:
            text = text.replace("<Head>", "<Head>" + head_inject, 1)
        else:
            text = head_inject + text

        content = text.encode("utf-8")
        resp_headers["content-type"] = "text/html; charset=utf-8"

    return _Response(
        content=content,
        status_code=resp.status_code,
        headers=resp_headers,
        media_type=content_type or None,
    )
