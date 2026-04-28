"""日志、服务列表、AI 分析、指标统计路由。

路由前缀：/api/services  /api/logs  /api/metrics  /api/analyze
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from state import loki, analyzer, clusterer

logger = logging.getLogger(__name__)
router = APIRouter()


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


# ── 服务列表 ──────────────────────────────────────────────────────────────────

@router.get("/api/services")
async def get_services():
    """获取所有服务及其错误数"""
    try:
        services = await loki.get_services()
        return {"data": services, "total": len(services)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki 连接失败: {e}")


@router.get("/api/services/grouped")
async def get_services_grouped():
    """获取按 K8s namespace 分组的服务列表（日志中心环境分组用）。"""
    try:
        groups = await loki.get_grouped_services()
        return {"data": groups}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki 连接失败: {e}")


# ── 日志查询 ──────────────────────────────────────────────────────────────────

@router.get("/api/logs")
async def get_logs(
    service: Optional[str] = Query(None, description="服务名称"),
    hours: int = Query(24, description="查询时长（小时）"),
    limit: int = Query(2000, le=10000, description="返回条数"),
    level: Optional[str] = Query(None, description="日志级别过滤: error/warn/info"),
    keyword: Optional[str] = Query(None, description="关键字过滤（不区分大小写）"),
    start_time: Optional[str] = Query(None, description="自定义开始时间 ISO 格式，如 2024-01-01T00:00"),
    end_time: Optional[str] = Query(None, description="自定义结束时间 ISO 格式，如 2024-01-01T23:59"),
):
    """查询日志"""
    try:
        logs = await loki.query_logs(
            service=service,
            hours=hours,
            limit=limit,
            level=level or None,
            keyword=keyword or None,
            start_ns=_parse_time_ns(start_time),
            end_ns=_parse_time_ns(end_time),
        )
        return {"data": logs, "total": len(logs), "service": service, "hours": hours}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/logs/errors")
async def get_error_logs(
    hours: int = Query(24),
    limit: int = Query(5000, le=20000),
):
    """查询全量错误日志"""
    try:
        logs = await loki.query_error_logs(hours=hours, limit=limit)
        return {"data": logs, "total": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/metrics/errors")
async def get_error_metrics(hours: int = Query(24)):
    """各服务错误数统计"""
    try:
        counts = await loki.count_errors_by_service(hours=hours)
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
    hours: int = Query(24, description="查询时长（小时）"),
    limit: int = Query(10000, le=50000, description="参与聚类的日志上限"),
    top_n: int = Query(100, le=500, description="返回模板数上限"),
    level: Optional[str] = Query(None, description="日志级别过滤: error/warn，不传则聚类全量日志"),
    keyword: Optional[str] = Query(None, description="关键字过滤"),
    start_time: Optional[str] = Query(None, description="自定义开始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="自定义结束时间 ISO 格式"),
):
    """Drain3 日志模板聚类：将重复日志归纳为带 <*> 占位符的模板"""
    try:
        logs = await loki.query_logs(
            service=service, hours=hours, limit=limit, level=level,
            keyword=keyword or None,
            start_ns=_parse_time_ns(start_time),
            end_ns=_parse_time_ns(end_time),
        )
        templates = clusterer.cluster(logs, top_n=top_n)
        return {
            "data": templates,
            "total_logs": len(logs),
            "total_templates": len(templates),
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
    hours: int = Query(24, description="查询时长（小时）"),
    start_time: Optional[str] = Query(None, description="自定义开始时间 ISO 格式"),
    end_time: Optional[str] = Query(None, description="自定义结束时间 ISO 格式"),
):
    """
    计算关键字在日志中首次与末次出现的时间差（链路耗时 / TraceID 全链路追踪）。
    最多扫描 50000 条匹配日志，返回首尾时间戳及耗时。
    """
    try:
        logs = await loki.query_logs(
            service=service,
            hours=hours,
            limit=50000,
            keyword=keyword,
            start_ns=_parse_time_ns(start_time),
            end_ns=_parse_time_ns(end_time),
            use_scan_timeout=True,   # 大量扫描使用 120s 超时
        )
        if not logs:
            return {"found": False, "keyword": keyword, "log_count": 0}

        sorted_logs = sorted(logs, key=lambda x: int(x["timestamp_ns"]))
        first = sorted_logs[0]
        last  = sorted_logs[-1]

        first_ns   = int(first["timestamp_ns"])
        last_ns    = int(last["timestamp_ns"])
        duration_ns = last_ns - first_ns
        duration_ms = duration_ns / 1_000_000

        if duration_ms < 1:
            duration_str = f"{duration_ns / 1000:.1f} µs"
        elif duration_ms < 1000:
            duration_str = f"{duration_ms:.3f} ms"
        elif duration_ms < 60_000:
            duration_str = f"{duration_ms / 1000:.3f} s"
        else:
            minutes = int(duration_ms // 60_000)
            seconds = (duration_ms % 60_000) / 1000
            duration_str = f"{minutes}m {seconds:.1f}s"

        return {
            "found":        True,
            "keyword":      keyword,
            "log_count":    len(logs),
            "first_ts":     first["timestamp"],
            "first_ts_ns":  first_ns,
            "first_log":    first["line"][:300],
            "first_service": first["labels"].get("app") or first["labels"].get("job") or "",
            "last_ts":      last["timestamp"],
            "last_ts_ns":   last_ns,
            "last_log":     last["line"][:300],
            "last_service": last["labels"].get("app") or last["labels"].get("job") or "",
            "duration_ms":  duration_ms,
            "duration_str": duration_str,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ── 模板聚类 AI 分析 ──────────────────────────────────────────────────────────

@router.get("/api/analyze/templates/stream")
async def analyze_templates_stream(
    service: Optional[str] = Query(None),
    hours: int = Query(24),
    level: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
):
    """流式 AI 分析日志模板聚类（SSE）"""
    try:
        logs = await loki.query_logs(
            service=service, hours=hours, limit=10000, level=level or None,
            keyword=keyword or None,
            start_ns=_parse_time_ns(start_time),
            end_ns=_parse_time_ns(end_time),
            use_scan_timeout=True,
        )
        templates = clusterer.cluster(logs, top_n=30)

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
    hours:      int           = Query(24),
    level:      Optional[str] = Query(None),
    keyword:    Optional[str] = Query(None),
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
