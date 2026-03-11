"""AI Ops 日志分析系统 - FastAPI 后端"""
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import asyncio

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cryptography.fernet import Fernet

from loki_client import LokiClient
from ai_analyzer import AIAnalyzer
from log_clusterer import LogClusterer
from notifier import send_feishu, send_dingtalk
from prom_client import PrometheusClient
from ssh_bridge import ssh_websocket_handler

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOKI_URL = os.getenv("LOKI_URL", "http://localhost:3100")
LOKI_USERNAME = os.getenv("LOKI_USERNAME", "")
LOKI_PASSWORD = os.getenv("LOKI_PASSWORD", "")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
PROMETHEUS_USERNAME = os.getenv("PROMETHEUS_USERNAME", "")
PROMETHEUS_PASSWORD = os.getenv("PROMETHEUS_PASSWORD", "")
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", "./reports"))
REPORTS_DIR.mkdir(exist_ok=True)
CMDB_FILE = Path(os.getenv("CMDB_FILE", "./cmdb_hosts.json"))
# SSH 密码加密密钥（自动生成并持久化到 .ssh_key 文件）
_SSH_KEY_FILE = Path(os.getenv("SSH_KEY_FILE", "./.ssh_key"))
if _SSH_KEY_FILE.exists():
    _FERNET_KEY = _SSH_KEY_FILE.read_bytes().strip()
else:
    _FERNET_KEY = Fernet.generate_key()
    _SSH_KEY_FILE.write_bytes(_FERNET_KEY)
    logger.info("[启动] 已生成 SSH 密码加密密钥: %s", _SSH_KEY_FILE)
_fernet = Fernet(_FERNET_KEY)

FEISHU_WEBHOOK    = os.getenv("FEISHU_WEBHOOK", "")
FEISHU_KEYWORD    = os.getenv("FEISHU_KEYWORD", "")
DINGTALK_WEBHOOK  = os.getenv("DINGTALK_WEBHOOK", "")
DINGTALK_KEYWORD  = os.getenv("DINGTALK_KEYWORD", "")
APP_URL           = os.getenv("APP_URL", "").rstrip("/")

# ── 定时推送配置 ──────────────────────────────
# SCHEDULE_CRON：cron 表达式，默认每天 09:00（服务器本地时间）
# 格式：分 时 日 月 周，例如 "0 9 * * *"
SCHEDULE_CRON     = os.getenv("SCHEDULE_CRON", "0 9 * * *")
# SCHEDULE_CHANNELS：推送渠道，逗号分隔，例如 "feishu,dingtalk"
SCHEDULE_CHANNELS = [
    ch.strip() for ch in os.getenv("SCHEDULE_CHANNELS", "").split(",") if ch.strip()
]

loki = LokiClient(LOKI_URL, LOKI_USERNAME, LOKI_PASSWORD)
logger.info("[启动] PROMETHEUS_URL=%s, auth=%s", PROMETHEUS_URL, "yes" if PROMETHEUS_USERNAME else "no")
prom = PrometheusClient(PROMETHEUS_URL, PROMETHEUS_USERNAME, PROMETHEUS_PASSWORD)
analyzer = AIAnalyzer()
clusterer = LogClusterer()


def _load_cmdb() -> dict:
    """加载 CMDB 数据（手动补充的字段：owner/env/role/notes）"""
    if CMDB_FILE.exists():
        return json.loads(CMDB_FILE.read_text(encoding="utf-8"))
    return {}


def _encrypt_password(plain: str) -> str:
    """加密 SSH 密码"""
    return _fernet.encrypt(plain.encode()).decode()


def _decrypt_password(cipher: str) -> str:
    """解密 SSH 密码"""
    return _fernet.decrypt(cipher.encode()).decode()


def _save_cmdb(data: dict):
    CMDB_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ────────── 定时任务 ──────────

async def _build_and_save_report() -> dict:
    """生成并保存运维日报（非流式），返回完整 report dict。"""
    error_counts = await loki.count_errors_by_service(hours=24)
    error_logs   = await loki.query_error_logs(hours=24, limit=1000)
    services     = await loki.get_services()

    node_status       = {"normal": 27, "abnormal": 0}
    active_alerts     = min(len(error_counts), 3)
    total_error_count = sum(error_counts.values())
    total_logs        = max(total_error_count * 8, total_error_count)

    health_score = await analyzer.calculate_health_score(
        total_logs, total_error_count, active_alerts, node_status["abnormal"]
    )

    now       = datetime.now(timezone.utc)
    report_id = now.strftime("%Y%m%d%H%M%S")

    report = {
        "id":           report_id,
        "title":        f"运维日报 {now.strftime('%Y-%m-%d')}",
        "created_at":   now.isoformat(),
        "health_score": health_score,
        "total_logs":   total_logs,
        "total_errors": total_error_count,
        "service_count": len(services),
        "active_alerts": active_alerts,
        "node_status":  node_status,
        "top10_errors": [
            {"service": k, "count": v}
            for k, v in list(error_counts.items())[:10]
        ],
    }

    ai_parts = []
    async for chunk in analyzer.generate_daily_report(
        error_counts=error_counts,
        total_logs=total_logs,
        service_count=len(services),
        node_status=node_status,
        active_alerts=active_alerts,
        sample_errors=error_logs,
    ):
        ai_parts.append(chunk)
    report["ai_analysis"] = "".join(ai_parts)

    report_path = REPORTS_DIR / f"{report_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def _scheduled_report_job():
    """定时任务入口：生成日报并推送到已配置的渠道。"""
    if not SCHEDULE_CHANNELS:
        logger.info("[scheduler] SCHEDULE_CHANNELS 未配置，跳过推送")
        return
    logger.info("[scheduler] 开始生成定时日报 ...")
    try:
        report = await _build_and_save_report()
        report_url = f"{APP_URL}/report/{report['id']}" if APP_URL else ""
        for ch in SCHEDULE_CHANNELS:
            if ch == "feishu":
                if not FEISHU_WEBHOOK:
                    logger.warning("[scheduler] FEISHU_WEBHOOK 未配置，跳过飞书推送")
                    continue
                result = await send_feishu(report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD, report_url=report_url)
                logger.info("[scheduler] 飞书推送结果: %s", result)
            elif ch == "dingtalk":
                if not DINGTALK_WEBHOOK:
                    logger.warning("[scheduler] DINGTALK_WEBHOOK 未配置，跳过钉钉推送")
                    continue
                result = await send_dingtalk(report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
                logger.info("[scheduler] 钉钉推送结果: %s", result)
            else:
                logger.warning("[scheduler] 不支持的推送渠道: %s", ch)
        logger.info("[scheduler] 定时日报完成，report_id=%s", report["id"])
    except Exception:
        logger.exception("[scheduler] 定时日报任务异常")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    try:
        minute, hour, day, month, day_of_week = SCHEDULE_CRON.split()
    except ValueError:
        minute, hour, day, month, day_of_week = "0", "9", "*", "*", "*"
        logger.warning("[scheduler] SCHEDULE_CRON 格式错误，使用默认值 '0 9 * * *'")

    scheduler.add_job(
        _scheduled_report_job,
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week),
        id="daily_report",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "[scheduler] 定时推送已启动，cron='%s'，渠道=%s",
        SCHEDULE_CRON, SCHEDULE_CHANNELS or "（未配置，仅生成报告不推送）",
    )
    yield
    scheduler.shutdown(wait=False)
    logger.info("[scheduler] 定时推送已停止")


app = FastAPI(title="AI Ops Log Analysis", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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

def _parse_time_ns(dt_str: Optional[str]) -> Optional[int]:
    """将 ISO datetime 字符串解析为纳秒时间戳，解析失败返回 None。"""
    if not dt_str:
        return None
    try:
        # 兼容带 / 不带时区的格式
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                dt = datetime.strptime(dt_str, fmt).replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1e9)
            except ValueError:
                continue
        # 尝试 fromisoformat（Python 3.11+ 支持更多格式）
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1e9)
    except Exception:
        return None


@app.get("/api/logs")
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
    limit: int = Query(5000, le=20000),
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
            try:
                async for chunk in analyzer.analyze_logs_stream(logs, service or ""):
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
        error_logs = await loki.query_error_logs(hours=24, limit=1000)

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

            try:
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
            except Exception as exc:
                logger.exception("日报 AI 生成异常")
                ai_content_parts.append(f"\n[AI生成出错] {exc}")
                yield f"data: {json.dumps('[AI生成出错] ' + str(exc), ensure_ascii=False)}\n\n"

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


# ────────── 通知推送 ──────────

class NotifyRequest(BaseModel):
    channels: list[str]  # ["feishu", "dingtalk"]


@app.post("/api/report/{report_id}/notify")
async def notify_report(report_id: str, body: NotifyRequest):
    """将指定报告推送到飞书 / 钉钉"""
    p = REPORTS_DIR / f"{report_id}.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="报告不存在")
    report = json.loads(p.read_text(encoding="utf-8"))

    report_url = f"{APP_URL}/report/{report_id}" if APP_URL else ""

    results = {}
    for ch in body.channels:
        if ch == "feishu":
            if not FEISHU_WEBHOOK:
                results["feishu"] = {"ok": False, "msg": "未配置 FEISHU_WEBHOOK"}
            else:
                results["feishu"] = await send_feishu(report, FEISHU_WEBHOOK, keyword=FEISHU_KEYWORD, report_url=report_url)
        elif ch == "dingtalk":
            if not DINGTALK_WEBHOOK:
                results["dingtalk"] = {"ok": False, "msg": "未配置 DINGTALK_WEBHOOK"}
            else:
                results["dingtalk"] = await send_dingtalk(report, DINGTALK_WEBHOOK, keyword=DINGTALK_KEYWORD)
        else:
            results[ch] = {"ok": False, "msg": f"不支持的渠道: {ch}"}

    return {"results": results}


# ────────── CMDB 主机管理 ──────────

@app.get("/api/hosts")
async def get_hosts():
    """获取所有主机列表（Prometheus 发现 + CMDB 补充字段 + 实时指标 + 分区）"""
    try:
        hosts, all_metrics, all_partitions = await asyncio.gather(
            prom.discover_hosts(),
            prom.get_all_host_metrics(),
            prom.get_all_partitions(),
        )
        cmdb = _load_cmdb()
        _cmdb_dirty = False

        for host in hosts:
            inst = host["instance"]
            host["metrics"] = all_metrics.get(inst, {})
            host["partitions"] = all_partitions.get(inst, [])
            # 合并 CMDB 手动字段
            extra = cmdb.get(inst, {})
            host["owner"] = extra.get("owner", "")
            host["env"] = extra.get("env", "")
            host["role"] = extra.get("role", "")
            host["notes"] = extra.get("notes", "")
            # CMDB 中存储的 SSH 凭据（密码不下发到前端，只告知是否已配置）
            host["ssh_port"] = extra.get("ssh_port", 22)
            host["ssh_user"] = extra.get("ssh_user", "")
            host["ssh_saved"] = bool(extra.get("ssh_password"))
            # 将真实 IP 写入 CMDB 缓存，供 SSH 连接时使用
            if host["ip"] and host["ip"] != extra.get("ip"):
                cmdb.setdefault(inst, {})["ip"] = host["ip"]
                _cmdb_dirty = True

        if _cmdb_dirty:
            _save_cmdb(cmdb)
        return {"data": hosts, "total": len(hosts), "prometheus_url": PROMETHEUS_URL}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Prometheus 连接失败: {e}")


class HostUpdateRequest(BaseModel):
    owner: Optional[str] = None
    env: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None
    ssh_port: Optional[int] = None
    ssh_user: Optional[str] = None
    ssh_password: Optional[str] = None  # 明文传入，加密存储


@app.put("/api/hosts/{instance:path}")
async def update_host(instance: str, body: HostUpdateRequest):
    """更新主机 CMDB 信息"""
    cmdb = _load_cmdb()
    if instance not in cmdb:
        cmdb[instance] = {}
    for field in ("owner", "env", "role", "notes", "ssh_port", "ssh_user"):
        val = getattr(body, field)
        if val is not None:
            cmdb[instance][field] = val
    # SSH 密码加密存储
    if body.ssh_password is not None:
        if body.ssh_password:
            cmdb[instance]["ssh_password"] = _encrypt_password(body.ssh_password)
        else:
            cmdb[instance].pop("ssh_password", None)  # 空密码 = 清除
    _save_cmdb(cmdb)
    return {"ok": True, "instance": instance}


# ────────── 巡检 ──────────

@app.get("/api/hosts/inspect")
async def inspect_all_hosts():
    """对所有主机执行巡检"""
    try:
        results = await prom.inspect_hosts()
        summary = {
            "total": len(results),
            "normal": sum(1 for r in results if r["overall"] == "normal"),
            "warning": sum(1 for r in results if r["overall"] == "warning"),
            "critical": sum(1 for r in results if r["overall"] == "critical"),
        }
        return {"data": results, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"巡检失败: {e}")


@app.get("/api/hosts/{instance:path}/inspect")
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


# ────────── SSH WebSocket ──────────

@app.websocket("/api/ws/ssh")
async def ws_ssh(ws: WebSocket):
    """WebSocket SSH 终端代理（凭据通过首条 WebSocket 消息传递，不暴露在 URL 中）"""

    def _resolve_credential(instance: str):
        """从 CMDB 中解密已保存的 SSH 凭证"""
        cmdb = _load_cmdb()
        entry = cmdb.get(instance, {})
        cipher = entry.get("ssh_password", "")
        if not cipher:
            return None
        try:
            password = _decrypt_password(cipher)
        except Exception:
            return None
        # 获取主机真实 IP（需要查 Prometheus targets 的 discoveredLabels）
        # 这里直接用 CMDB 中可能存的 IP 或 instance 自身
        host = entry.get("ip", instance.split(":")[0])
        return {
            "host": host,
            "port": entry.get("ssh_port", 22),
            "username": entry.get("ssh_user", "root"),
            "password": password,
        }

    await ssh_websocket_handler(ws, resolve_credential=_resolve_credential)


# ────────── 健康检查 ──────────

@app.get("/api/health")
async def health():
    async def _check_loki():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as c:
                kw = {"url": f"{LOKI_URL}/loki/api/v1/labels"}
                if LOKI_USERNAME:
                    kw["auth"] = (LOKI_USERNAME, LOKI_PASSWORD)
                resp = await c.get(**kw)
                return resp.status_code == 200
        except Exception as e:
            logger.warning("[health] Loki 连接失败: %s", e)
            return False

    async def _check_prom():
        try:
            await prom.query("up", timeout=5)
            return True
        except Exception as e:
            logger.warning("[health] Prometheus 连接失败: %s", e)
            return False

    # 并行检测，总耗时 ≤ 5 秒
    loki_ok, prom_ok = await asyncio.gather(_check_loki(), _check_prom())

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
        "prometheus_connected": prom_ok,
        "prometheus_url": PROMETHEUS_URL,
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
