"""日志、服务列表、AI 分析、指标统计路由。

路由前缀：/api/services  /api/logs  /api/metrics  /api/analyze
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from state import loki, analyzer, clusterer

logger = logging.getLogger(__name__)
router = APIRouter()
_TEMPLATE_CACHE: TTLCache = TTLCache(maxsize=64, ttl=30)
_TRACE_CACHE: TTLCache = TTLCache(maxsize=64, ttl=30)
_TEMPLATE_LOCKS: dict[str, asyncio.Lock] = {}
_TRACE_LOCKS: dict[str, asyncio.Lock] = {}


def _parse_time_ns(dt_str: Optional[str]) -> Optional[int]:
    """将 ISO datetime 字符串解析为纳秒时间戳，解析失败返回 None。"""
    if not dt_str:
        return None
    try:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                dt = datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1e9)
            except ValueError:
                continue
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1e9)
    except Exception:
        return None


def _build_cache_key(prefix: str, *parts) -> str:
    return json.dumps([prefix, *parts], ensure_ascii=False, separators=(",", ":"))


async def _get_clustered_templates(
    *,
    service: Optional[str],
    hours: float,
    limit: int,
    top_n: int,
    level: Optional[str],
    keyword: Optional[str],
    start_ns: Optional[int],
    end_ns: Optional[int],
    group_label: Optional[str] = None,
    group_value: Optional[str] = None,
    use_scan_timeout: bool = False,
) -> dict:
    cache_key = _build_cache_key(
        "templates",
        service or "",
        hours,
        limit,
        top_n,
        level or "",
        keyword or "",
        start_ns or "",
        end_ns or "",
        group_label or "",
        group_value or "",
        use_scan_timeout,
    )
    cached = _TEMPLATE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    lock = _TEMPLATE_LOCKS.setdefault(cache_key, asyncio.Lock())
    async with lock:
        cached = _TEMPLATE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        logs = await loki.query_logs(
            service=service,
            hours=hours,
            limit=limit,
            level=level,
            keyword=keyword,
            start_ns=start_ns,
            end_ns=end_ns,
            group_label=group_label,
            group_value=group_value,
            use_scan_timeout=use_scan_timeout,
        )
        templates = clusterer.cluster(logs, top_n=top_n)
        payload = {
            "templates": templates,
            "total_logs": len(logs),
            "total_templates": len(templates),
        }
        _TEMPLATE_CACHE[cache_key] = payload
        return payload


async def _trace_keyword_result(
    *,
    keyword: str,
    service: Optional[str],
    hours: float,
    start_ns: Optional[int],
    end_ns: Optional[int],
    group_label: Optional[str] = None,
    group_value: Optional[str] = None,
) -> dict:
    cache_key = _build_cache_key(
        "trace",
        keyword,
        service or "",
        hours,
        start_ns or "",
        end_ns or "",
        group_label or "",
        group_value or "",
    )
    cached = _TRACE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    lock = _TRACE_LOCKS.setdefault(cache_key, asyncio.Lock())
    async with lock:
        cached = _TRACE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        logs = await loki.query_logs(
            service=service,
            hours=hours,
            limit=50000,
            keyword=keyword,
            start_ns=start_ns,
            end_ns=end_ns,
            group_label=group_label,
            group_value=group_value,
            use_scan_timeout=True,
        )
        if not logs:
            payload = {"found": False, "keyword": keyword, "log_count": 0}
            _TRACE_CACHE[cache_key] = payload
            return payload

        sorted_logs = sorted(logs, key=lambda item: int(item["timestamp_ns"]))
        first = sorted_logs[0]
        last = sorted_logs[-1]
        first_ns = int(first["timestamp_ns"])
        last_ns = int(last["timestamp_ns"])
        duration_ns = last_ns - first_ns
        duration_ms = duration_ns / 1_000_000

        if duration_ms < 1:
            duration_str = f"{duration_ns / 1000:.1f} us"
        elif duration_ms < 1000:
            duration_str = f"{duration_ms:.3f} ms"
        elif duration_ms < 60_000:
            duration_str = f"{duration_ms / 1000:.3f} s"
        else:
            minutes = int(duration_ms // 60_000)
            seconds = (duration_ms % 60_000) / 1000
            duration_str = f"{minutes}m {seconds:.1f}s"

        payload = {
            "found": True,
            "keyword": keyword,
            "log_count": len(logs),
            "first_ts": first["timestamp"],
            "first_ts_ns": first_ns,
            "first_log": first["line"][:300],
            "first_service": first["labels"].get("app") or first["labels"].get("job") or "",
            "last_ts": last["timestamp"],
            "last_ts_ns": last_ns,
            "last_log": last["line"][:300],
            "last_service": last["labels"].get("app") or last["labels"].get("job") or "",
            "duration_ms": duration_ms,
            "duration_str": duration_str,
        }
        _TRACE_CACHE[cache_key] = payload
        return payload


# ── 服务列表 ──────────────────────────────────────────────────────────────────

@router.get("/api/services")
async def get_services(
    with_errors: bool = Query(True, description="false=快速路径，只返回服务名，跳过错误统计"),
):
    """获取所有服务列表。with_errors=false 用于前端首屏秒级渲染。"""
    try:
        services = await loki.get_services(with_errors=with_errors)
        return {"data": services, "total": len(services), "with_errors": with_errors}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki 连接失败: {e}")


@router.get("/api/services/error-counts")
async def get_service_error_counts(hours: float = Query(24, gt=0, le=168)):
    """单独返回各服务错误数（前端服务列表懒补）。"""
    try:
        counts = await loki.count_errors_by_service_fast(hours=hours)
        return {"data": counts, "total_errors": sum(counts.values())}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/services/grouped")
async def get_services_grouped(
    group_by: Optional[str] = Query(None, description="按 Loki 标签分组，如 namespace/env/team"),
    with_errors: bool = Query(True, description="false=只返回服务名分组，跳过错误统计（首屏秒级）"),
):
    """按指定 Loki 标签分组返回服务列表。with_errors=false 给前端首屏用。"""
    try:
        groups = await loki.get_grouped_services(group_label=group_by, with_errors=with_errors)
        return {"data": groups, "group_by": group_by or "", "with_errors": with_errors}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki 连接失败: {e}")


@router.get("/api/logs/labels")
async def get_log_labels():
    """返回 Loki 当前可见的标签清单，以及推荐的分组选项。"""
    try:
        return await loki.get_label_inventory()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki 标签读取失败: {e}")


@router.get("/api/logs/labels/{label}/values")
async def get_log_label_values(
    label: str,
    limit: int = Query(20, ge=1, le=200, description="返回多少个样例值"),
):
    """返回指定 Loki 标签的样例值。"""
    try:
        values = await loki.get_label_values(label)
        values = sorted(values)
        return {"label": label, "data": values[:limit], "total": len(values)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki 标签值读取失败: {e}")


# ── 日志查询 ──────────────────────────────────────────────────────────────────

@router.get("/api/logs/query-range")
async def query_loki_range(
    query: str = Query(..., description="LogQL query"),
    hours: float = Query(1, gt=0, le=168, description="Relative query window in hours"),
    limit: int = Query(200, ge=1, le=5000),
    direction: str = Query("backward", pattern="^(forward|backward)$"),
    start_time: Optional[str] = Query(None, description="ISO start time"),
    end_time: Optional[str] = Query(None, description="ISO end time"),
):
    """Run a raw Loki query_range and normalize stream rows for query pages."""
    try:
        end_ns = _parse_time_ns(end_time)
        if end_ns is None:
            end_ns = int(datetime.now(timezone.utc).timestamp() * 1e9)
        start_ns = _parse_time_ns(start_time)
        if start_ns is None:
            start_ns = int(end_ns - hours * 3600 * 1e9)
        rows = await loki.query_range(
            query=query,
            start_ts=start_ns,
            end_ts=end_ns,
            limit=limit,
            direction=direction,
            use_scan_timeout=True,
        )
        return {
            "data": rows,
            "total": len(rows),
            "query": query,
            "start_ns": start_ns,
            "end_ns": end_ns,
            "direction": direction,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


def _split_csv(raw: Optional[str]) -> list[str]:
    """把逗号分隔字符串切成去空的列表；None 返回 []。"""
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item and item.strip()]


def _parse_label_pairs(raw_list: Optional[list[str]]) -> dict[str, list[str]]:
    """把 ['ns:aiops', 'ns:kube-system', 'env:prod'] 解析为
    {'ns':['aiops','kube-system'], 'env':['prod']}；
    冒号后可有空格；同 key 值累加去重，最终由 LogQL builder 决定单值/regex。"""
    out: dict[str, list[str]] = {}
    for item in raw_list or []:
        if not item or ":" not in item:
            continue
        k, _, v = item.partition(":")
        k = k.strip()
        v = v.strip()
        if not k or not v:
            continue
        lst = out.setdefault(k, [])
        if v not in lst:
            lst.append(v)
    return out


@router.get("/api/logs")
async def get_logs(
    service: Optional[str] = Query(None, description="单个服务名（旧参数，与 services 合并）"),
    services: Optional[str] = Query(None, description="多个服务名，逗号分隔，如 svc-a,svc-b"),
    hours: float = Query(24, gt=0, description="查询时长（小时，支持小数）"),
    limit: int = Query(200, le=1000, description="每页条数（游标分页）"),
    level: Optional[str] = Query(None, description="日志级别过滤: error/warn/info"),
    keyword: Optional[str] = Query(None, description="单个关键字（旧参数，与 keywords 合并）"),
    keywords: Optional[str] = Query(None, description="多个关键字，逗号分隔"),
    keyword_mode: str = Query("and", description="多关键字组合：and=全部命中 / or=任一命中"),
    exclude_keywords: Optional[str] = Query(None, description="排除关键字，逗号分隔"),
    labels: list[str] = Query(default_factory=list, description="多标签过滤，每项 label:value，如 labels=namespace:aiops&labels=env:prod"),
    group_label: Optional[str] = Query(None, description="额外的 Loki 分组标签名（旧参数，与 labels 合并）"),
    group_value: Optional[str] = Query(None, description="额外的 Loki 分组标签值（旧参数）"),
    start_time: Optional[str] = Query(None, description="自定义开始时间 ISO 格式，如 2024-01-01T00:00"),
    end_time: Optional[str] = Query(None, description="自定义结束时间 ISO 格式，如 2024-01-01T23:59"),
    cursor_ns: Optional[int] = Query(None, description="游标：上一页最旧条目的纳秒时间戳，续页时传入"),
):
    """查询日志（游标分页，每页 limit 条，不超过 Loki 4MB 响应限制）

    - 多服务：`services=svc-a,svc-b` 生成 `{app=~"svc-a|svc-b"}`，一次查跨服务日志。
    - 多关键字 AND（默认）：`keywords=error,timeout` 生成 `|~ "error" |~ "timeout"`。
    - 多关键字 OR：加 `keyword_mode=or` → `|~ "(error|timeout)"`。
    - 排除：`exclude_keywords=health,ping` → `!~ "health" !~ "ping"`。
    """
    svc_list = _split_csv(services)
    kw_list = _split_csv(keywords)
    ex_list = _split_csv(exclude_keywords)
    label_pairs = _parse_label_pairs(labels)
    mode = (keyword_mode or "and").lower()
    if mode not in ("and", "or"):
        mode = "and"
    try:
        result = await loki.query_logs_page(
            service=service,
            services=svc_list or None,
            hours=hours,
            page_size=limit,
            cursor_ns=cursor_ns,
            level=level or None,
            keyword=keyword or None,
            keywords=kw_list or None,
            keyword_mode=mode,
            exclude_keywords=ex_list or None,
            group_label=group_label,
            group_value=group_value,
            extra_label_filters=label_pairs or None,
            start_ns=_parse_time_ns(start_time),
            end_ns=_parse_time_ns(end_time),
        )
        return {
            "data": result["data"],
            "has_more": result["has_more"],
            "next_cursor_ns": result["next_cursor_ns"],
            "total": len(result["data"]),
            "service": service,
            "services": svc_list,
            "keywords": kw_list,
            "keyword_mode": mode,
            "exclude_keywords": ex_list,
            "labels": label_pairs,
            "hours": hours,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/logs/context")
async def get_log_context(
    timestamp_ns: int = Query(..., description="选中日志的纳秒时间戳"),
    service: Optional[str] = Query(None, description="服务名"),
    line_prefix: Optional[str] = Query(None, description="日志内容前缀，用于精确命中当前行"),
    labels_json: Optional[str] = Query(None, description="当前日志 labels 的 JSON 对象"),
    hours: float = Query(24, gt=0, description="查询时长（小时，支持小数）"),
    before: int = Query(249, ge=0, le=500, description="向前取多少条"),
    after: int = Query(250, ge=0, le=500, description="向后取多少条"),
    start_time: Optional[str] = Query(None, description="自定义开始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="自定义结束时间 ISO 格式"),
):
    """围绕某条日志返回同一流的前后文。

    可靠性保证：任何失败都不再抛 5xx —— 先降级重查（去掉 line_prefix、
    放宽时间窗），仍失败则返回以点击行为中心的最小上下文 + error 说明，
    前端始终有内容可渲染。
    """
    label_filters: dict[str, str] | None = None
    try:
        if labels_json:
            parsed = json.loads(labels_json)
            if not isinstance(parsed, dict):
                raise ValueError("labels_json must be a JSON object")
            label_filters = {
                str(key): "" if value is None else str(value)
                for key, value in parsed.items()
            }
        start_ns = _parse_time_ns(start_time)
        end_ns = _parse_time_ns(end_time)
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"参数错误: {e}")

    async def _attempt(**overrides):
        params = dict(
            timestamp_ns=timestamp_ns,
            service=service or None,
            line_prefix=line_prefix or None,
            before=before,
            after=after,
            hours=hours,
            start_ns=start_ns,
            end_ns=end_ns,
            label_filters=label_filters,
        )
        params.update(overrides)
        return await loki.query_log_context(**params)

    last_error: Exception | None = None
    # 1) 正常查询 → 2) 降级：去 line_prefix、忽略自定义窗口放宽到 24h
    for attempt, overrides in enumerate((
        {},
        {"line_prefix": None, "start_ns": None, "end_ns": None, "hours": max(hours, 24.0)},
    )):
        try:
            result = await _attempt(**overrides)
            if attempt > 0:
                result["degraded"] = True
            return result
        except Exception as e:
            last_error = e
            logger.warning("[logs] context attempt %d failed: %s", attempt + 1, e)

    # 3) 兜底：返回仅含点击行的最小上下文（HTTP 200），前端可展示并提示
    anchor_labels = {k: v for k, v in (label_filters or {}).items() if v}
    return {
        "data": [{
            "timestamp": datetime.fromtimestamp(timestamp_ns / 1e9).strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp_ns": str(timestamp_ns),
            "line": line_prefix or "",
            "labels": anchor_labels,
        }],
        "anchor_index": 0,
        "anchor_found": False,
        "before_count": 0,
        "after_count": 0,
        "degraded": True,
        "error": f"上下文查询失败（已降级重试）: {last_error}",
    }


@router.get("/api/logs/errors")
async def get_error_logs(
    hours: float = Query(24, gt=0),
    limit: int = Query(5000, le=20000),
    group_label: Optional[str] = Query(None),
    group_value: Optional[str] = Query(None),
):
    """查询全量错误日志"""
    try:
        logs = await loki.query_error_logs(
            hours=hours,
            limit=limit,
            group_label=group_label,
            group_value=group_value,
        )
        return {"data": logs, "total": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/metrics/errors")
async def get_error_metrics(hours: float = Query(24, gt=0)):
    """各服务错误数统计（限时返回：预算内拿不到先返回上次结果，后台继续刷新）"""
    try:
        counts = await loki.count_errors_by_service_fast(hours=hours)
        return {
            "data": [{"service": k, "count": v} for k, v in counts.items()],
            "total_errors": sum(counts.values()),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── 日志模板聚合 ──────────────────────────────────────────────────────────────

@router.get("/api/logs/templates")
async def get_log_templates(
    service: Optional[str] = Query(None, description="服务名称"),
    hours: float = Query(24, gt=0, description="查询时长（小时，支持小数）"),
    limit: int = Query(10000, le=50000, description="参与聚类的日志上限"),
    top_n: int = Query(100, le=500, description="返回模板数上限"),
    level: Optional[str] = Query(None, description="日志级别过滤: error/warn，不传则聚类全量日志"),
    keyword: Optional[str] = Query(None, description="关键字过滤"),
    group_label: Optional[str] = Query(None, description="额外的 Loki 分组标签名"),
    group_value: Optional[str] = Query(None, description="额外的 Loki 分组标签值"),
    start_time: Optional[str] = Query(None, description="自定义开始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="自定义结束时间 ISO 格式"),
):
    """Drain3 日志模板聚类：将重复日志归纳为带 <*> 占位符的模板"""
    try:
        start_ns = _parse_time_ns(start_time)
        end_ns = _parse_time_ns(end_time)
        payload = await _get_clustered_templates(
            service=service,
            hours=hours,
            limit=limit,
            top_n=top_n,
            level=level,
            keyword=keyword or None,
            group_label=group_label,
            group_value=group_value,
            start_ns=start_ns,
            end_ns=end_ns,
        )
        return {
            "data": payload["templates"],
            "total_logs": payload["total_logs"],
            "total_templates": payload["total_templates"],
            "service": service,
            "hours": hours,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 关键字链路耗时分析 ────────────────────────────────────────────────────────

@router.get("/api/logs/trace")
async def trace_keyword(
    keyword: str = Query(..., description="追踪关键字，如 traceId 值"),
    service: Optional[str] = Query(None, description="服务名称"),
    hours: float = Query(24, gt=0, description="查询时长（小时，支持小数）"),
    group_label: Optional[str] = Query(None, description="额外的 Loki 分组标签名"),
    group_value: Optional[str] = Query(None, description="额外的 Loki 分组标签值"),
    start_time: Optional[str] = Query(None, description="自定义开始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="自定义结束时间 ISO 格式"),
):
    """
    计算关键字在日志中首次与末次出现的时间差（链路耗时 / TraceID 全链路追踪）。
    最多扫描 50000 条匹配日志，返回首尾时间戳及耗时。
    """
    try:
        start_ns = _parse_time_ns(start_time)
        end_ns = _parse_time_ns(end_time)
        return await _trace_keyword_result(
            keyword=keyword,
            service=service,
            hours=hours,
            start_ns=start_ns,
            end_ns=end_ns,
            group_label=group_label,
            group_value=group_value,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── 模板聚类 AI 分析 ──────────────────────────────────────────────────────────

@router.get("/api/analyze/templates/stream")
async def analyze_templates_stream(
    service: Optional[str] = Query(None),
    hours: float = Query(24, gt=0),
    level: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    group_label: Optional[str] = Query(None),
    group_value: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
):
    """流式 AI 分析日志模板聚类（SSE）"""
    try:
        start_ns = _parse_time_ns(start_time)
        end_ns = _parse_time_ns(end_time)
        payload = await _get_clustered_templates(
            service=service,
            hours=hours,
            limit=10000,
            top_n=30,
            level=level or None,
            keyword=keyword or None,
            group_label=group_label,
            group_value=group_value,
            start_ns=start_ns,
            end_ns=end_ns,
            use_scan_timeout=True,
        )
        templates = payload["templates"]

        if not templates:
            async def empty():
                yield "data: 该时间范围内未发现足够日志进行模板分析。\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(empty(), media_type="text/event-stream")

        async def generate():
            try:
                async for chunk in analyzer.analyze_templates_stream(templates, service or ""):
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:
                logger.exception("AI 模板分析流式输出异常")
                yield f"data: {json.dumps('[AI分析出错] ' + str(exc), ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── AI 流式分析 ───────────────────────────────────────────────────────────────

@router.get("/api/analyze/stream")
async def analyze_logs_stream(
    service:    Optional[str] = Query(None),
    hours:      float         = Query(24, gt=0),
    level:      Optional[str] = Query(None),
    keyword:    Optional[str] = Query(None),
    group_label: Optional[str] = Query(None),
    group_value: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time:   Optional[str] = Query(None),
):
    """流式 AI 分析日志（SSE）

    策略：
    1. 与日志流保持完全一致的过滤条件（不强制 error 级别）
    2. 字符预算采样（60k 字符 ≈ 20k tokens，适配 32k~128k 上下文模型）
       优先级：fatal/panic > error/exception > warn > info
       同级别内：最新优先（近期日志更有价值）
       去重：相同前缀的行只保留一条
    3. 独特模式 > 800 条时自动切换 Drain3 聚类，把万级日志压成 40 个模板
    """
    try:
        logs = await loki.query_logs(
            service=service,
            hours=hours,
            limit=3000,
            level=level or None,          # 不强制 error，与日志流保持一致
            keyword=keyword or None,
            group_label=group_label,
            group_value=group_value,
            start_ns=_parse_time_ns(start_time),
            end_ns=_parse_time_ns(end_time),
            use_scan_timeout=True,
        )

        if not logs:
            async def empty():
                yield "data: 该时间范围内未发现符合条件的日志。\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(empty(), media_type="text/event-stream")

        # ── 字符预算采样 ──────────────────────────────────────────────
        # 目标：60,000 字符日志内容 ≈ 20k tokens（为 prompt+回复预留空间）
        # 适用于 32k~128k 上下文的模型
        CHAR_BUDGET   = 60_000
        CLUSTER_THRESHOLD = 800   # 去重后独特模式超过此数量改用聚类

        def _severity(line: str) -> int:
            l = line.lower()
            if any(k in l for k in ("panic", "fatal", "critical")):           return 4
            if any(k in l for k in ("error", "exception", "traceback", "err")):return 3
            if "warn" in l:                                                    return 2
            return 1

        # Step1: 去重（相同前100字符视为同一模式，保留最新的）
        seen: dict[str, dict] = {}
        for log in logs:                          # logs 已按时间倒序（最新在前）
            key = log["line"][:100]
            if key not in seen:
                seen[key] = log
        deduped = list(seen.values())             # 保留每种模式最新的一条

        # Step2: 判断是否需要聚类
        use_cluster = len(deduped) > CLUSTER_THRESHOLD
        templates   = None
        sample      = []
        stats       = {"total": len(logs), "deduped": len(deduped)}

        if use_cluster:
            templates = clusterer.cluster(logs, top_n=40)
            stats["clusters"] = len(templates)
        else:
            # Step3: 按严重级别分桶，各桶内已是最新优先
            buckets: dict[int, list] = {4: [], 3: [], 2: [], 1: []}
            for log in deduped:
                buckets[_severity(log["line"])].append(log)

            # Step4: 按预算填充，高优先级优先，同时记录字符数
            char_used = 0
            for sev in (4, 3, 2, 1):
                for log in buckets[sev]:
                    line_str = f"[{log['timestamp']}] {log['line'][:300]}\n"
                    if char_used + len(line_str) > CHAR_BUDGET:
                        break
                    sample.append(log)
                    char_used += len(line_str)
                if char_used >= CHAR_BUDGET:
                    break

            # 恢复时间升序（便于 AI 阅读时间线）
            sample.sort(key=lambda x: x.get("timestamp_ns", 0))
            stats["sampled"] = len(sample)
            stats["chars"]   = char_used

        logger.info(
            "[AI分析] total=%d deduped=%d use_cluster=%s sample=%s",
            stats["total"], stats["deduped"], use_cluster,
            stats.get("clusters") or stats.get("sampled"),
        )

        async def generate():
            try:
                if use_cluster:
                    hint = (f"（原始日志 {stats['total']} 条，"
                            f"去重后 {stats['deduped']} 种模式，"
                            f"已聚类为 {stats['clusters']} 个模板）")
                    async for chunk in analyzer.analyze_templates_stream(
                        templates, service or "", extra_hint=hint,
                    ):
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                else:
                    async for chunk in analyzer.analyze_logs_stream(
                        sample, service or "",
                        extra_context=(
                            f"采样说明：原始 {stats['total']} 条 → "
                            f"去重后 {stats['deduped']} 条 → "
                            f"按严重级别优先采样 {stats['sampled']} 条"
                            f"（{stats['chars']} 字符）"
                        ),
                    ):
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:
                logger.exception("AI 分析流式输出异常")
                yield f"data: {json.dumps('[AI分析出错] ' + str(exc), ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
