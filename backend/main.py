"""AI Ops 日志分析系统 - FastAPI 后端"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from loki_client import LokiClient
from ai_analyzer import AIAnalyzer
from log_clusterer import LogClusterer

load_dotenv()

app = FastAPI(title="AI Ops Log Analysis", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
LOKI_USERNAME = os.getenv("LOKI_USERNAME", "")
LOKI_PASSWORD = os.getenv("LOKI_PASSWORD", "")
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "./reports"))
REPORTS_DIR.mkdir(exist_ok=True)

loki = LokiClient(LOKI_URL, LOKI_USERNAME, LOKI_PASSWORD)
analyzer = AIAnalyzer()
clusterer = LogClusterer()


# ────────── 服务列表 ──────────

@app.get("/api/services")
async def get_services():
    """获取所有服务及其错误数"""
    try:
        services = await loki.get_services()
        return {"data": services, "total": len(services)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Loki 连接失败: {e}")


# ────────── 日志查询 ──────────

@app.get("/api/logs")
async def get_logs(
    service: Optional[str] = Query(None, description="服务名称"),
    hours: int = Query(24, description="查询时长（小时）"),
    limit: int = Query(500, le=2000, description="返回条数"),
    level: Optional[str] = Query(None, description="日志级别过滤: error/warn/info"),
):
    """查询日志"""
    try:
        logs = await loki.query_logs(
            service=service,
            hours=hours,
            limit=limit,
            level=level or None,
        )
        return {
            "data": logs,
            "total": len(logs),
            "service": service,
            "hours": hours,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/logs/errors")
async def get_error_logs(
    hours: int = Query(24),
    limit: int = Query(1000, le=2000),
):
    """查询全量错误日志"""
    try:
        logs = await loki.query_error_logs(hours=hours, limit=limit)
        return {"data": logs, "total": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.get("/api/metrics/errors")
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


# ────────── 日志模板聚合 ──────────

@app.get("/api/logs/templates")
async def get_log_templates(
    service: Optional[str] = Query(None, description="服务名称"),
    hours: int = Query(24, description="查询时长（小时）"),
    limit: int = Query(2000, le=5000, description="参与聚类的日志上限"),
    top_n: int = Query(50, le=200, description="返回模板数上限"),
    level: Optional[str] = Query(None, description="日志级别过滤: error/warn，不传则聚类全量日志"),
):
    """Drain3 日志模板聚类：将重复日志归纳为带 <*> 占位符的模板"""
    try:
        logs = await loki.query_logs(service=service, hours=hours, limit=limit, level=level)
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


# ────────── AI 分析 ──────────

@app.get("/api/analyze/stream")
async def analyze_logs_stream(
    service: Optional[str] = Query(None),
    hours: int = Query(24),
):
    """流式 AI 分析日志（SSE）"""
    try:
        logs = await loki.query_error_logs(service=service, hours=hours)
        if not logs:
            async def empty():
                yield "data: 该时间范围内未发现错误日志。\n\n"
                yield "data: [DONE]\n\n"
            return StreamingResponse(empty(), media_type="text/event-stream")

        async def generate():
            async for chunk in analyzer.analyze_logs_stream(logs, service or ""):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ────────── 日报 ──────────

class ReportMeta(BaseModel):
    id: str
    title: str
    created_at: str
    health_score: int
    total_logs: int
    total_errors: int
    service_count: int
    active_alerts: int


@app.get("/api/report/generate")
async def generate_report():
    """触发生成运维日报，流式返回 AI 分析内容"""
    try:
        # 并发获取数据
        error_counts = await loki.count_errors_by_service(hours=24)
        error_logs = await loki.query_error_logs(hours=24, limit=200)

        # 节点状态（模拟，实际可接 Prometheus）
        node_status = {"normal": 27, "abnormal": 0}
        active_alerts = min(len(error_counts), 3)

        services = await loki.get_services()
        total_error_count = sum(error_counts.values())

        # 估算总日志量（错误日志通常占总量 5-15%）
        total_logs = max(total_error_count * 8, total_error_count)

        health_score = await analyzer.calculate_health_score(
            total_logs, total_error_count, active_alerts, node_status["abnormal"]
        )

        now = datetime.now(timezone.utc)
        report_id = now.strftime("%Y%m%d%H%M%S")

        # 保存报告元数据（不含 AI 分析，AI 分析实时流式返回）
        meta = {
            "id": report_id,
            "title": f"运维日报 {now.strftime('%Y-%m-%d')}",
            "created_at": now.isoformat(),
            "health_score": health_score,
            "total_logs": total_logs,
            "total_errors": total_error_count,
            "service_count": len(services),
            "active_alerts": active_alerts,
            "node_status": node_status,
            "top10_errors": [
                {"service": k, "count": v}
                for k, v in list(error_counts.items())[:10]
            ],
        }

        report_path = REPORTS_DIR / f"{report_id}.json"
        ai_content_parts = []

        async def generate():
            # 先发送报告元数据
            yield f"data: __META__{json.dumps(meta, ensure_ascii=False)}\n\n"

            # 流式 AI 分析
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

            # 保存完整报告
            meta["ai_analysis"] = "".join(ai_content_parts)
            report_path.write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/report/list")
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


@app.get("/api/report/{report_id}")
async def get_report(report_id: str):
    """获取指定报告详情"""
    p = REPORTS_DIR / f"{report_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    data = json.loads(p.read_text(encoding="utf-8"))
    return data


# ────────── 健康检查 ──────────

@app.get("/api/health")
async def health():
    try:
        await loki.get_all_labels()
        loki_ok = True
    except Exception:
        loki_ok = False
    try:
        ai_name = analyzer.provider_name
        ai_ok = True
    except Exception as e:
        ai_name = str(e)
        ai_ok = False
    return {
        "status": "ok",
        "loki_connected": loki_ok,
        "loki_url": LOKI_URL,
        "ai_provider": ai_name,
        "ai_ready": ai_ok,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=True,
    )
