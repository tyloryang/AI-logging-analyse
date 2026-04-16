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

from state import loki, prom, analyzer
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

@router.post("/analyze")
async def analyze_observability(req: AnalyzeReq):
    """对可观测性数据做 AI 流式分析"""

    async def _stream():
        # 1. 收集上下文数据
        try:
            (alert_count, recent_alerts), \
            (error_count, error_breakdown), \
            (trace_count, recent_traces) = await asyncio.gather(
                _get_alert_count(),
                _get_loki_error_count(req.hours),
                _get_sw_trace_count(req.hours),
            )
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
            return

        # 2. 构造 prompt
        context_lines = [
            f"当前时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"统计时间范围：最近 {req.hours} 小时",
            f"",
            f"## 告警概况",
            f"- 触发告警数：{alert_count}",
        ]
        for a in recent_alerts[:5]:
            context_lines.append(f"  - [{a.get('severity','?')}] {a.get('service','?')}: {a.get('name','?')}")

        context_lines += [
            f"",
            f"## 服务错误",
            f"- 错误总数：{error_count}",
        ]
        for e in error_breakdown[:5]:
            context_lines.append(f"  - {e['service']}: {e['count']} 条错误")

        context_lines += [
            f"",
            f"## APM Trace",
            f"- Trace 总量：{trace_count}",
        ]
        for t in recent_traces[:3]:
            status = "❌" if t.get("error") else "✅"
            context_lines.append(f"  - {status} {t.get('service','?')} {t.get('endpoint','?')} {t.get('duration',0)}ms")

        prompt = "\n".join(context_lines)
        prompt += f"\n\n---\n用户问题：{req.question}"

        system = (
            "你是一名资深 SRE 工程师，负责分析可观测性平台数据。"
            "请根据以下运维数据，给出简洁的根因分析和行动建议。"
            "输出格式：\n## 告警分析\n## 错误根因\n## 建议行动\n"
            "每节保持简短，建议行动使用编号列表，最多3条。"
        )

        # 3. 流式输出
        try:
            full_prompt = f"{system}\n\n{prompt}"
            async for chunk in analyzer.provider.stream(full_prompt, max_tokens=1500):
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

@router.get("/grafana/discover")
async def discover_grafana_boards():
    """
    调用 Grafana /api/search 自动发现所有已安装看板。
    需要在系统配置中填写 Grafana URL 和 API Key（或开启匿名访问）。
    """
    import httpx

    # 先刷新环境变量，确保通过 settings 页面保存的 key 立即生效
    try:
        from runtime_env import refresh_runtime_settings_env
        refresh_runtime_settings_env()
    except Exception:
        pass

    base    = (os.getenv("GRAFANA_URL", "") or "").strip().rstrip("/")
    api_key = (os.getenv("GRAFANA_API_KEY", "") or "").strip()

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

    try:
        from runtime_env import refresh_runtime_settings_env
        refresh_runtime_settings_env()
    except Exception:
        pass

    base    = (os.getenv("GRAFANA_URL", "") or "").strip().rstrip("/")
    api_key = (os.getenv("GRAFANA_API_KEY", "") or "").strip()

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
