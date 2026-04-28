"""AI Ops 日志分析系统 - FastAPI 主入口"""

import os
import sys

# Force UTF-8 early so Chinese prompts/logs do not fall back to ASCII in
# containers, Windows terminals, or inherited subprocess environments.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("LANG", "C.UTF-8")
os.environ.setdefault("LC_ALL", "C.UTF-8")

for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass

from runtime_env import bootstrap_runtime_env

bootstrap_runtime_env()

import asyncio
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import engine, Base, AsyncSessionLocal
from auth.router import router as auth_router
from auth.admin_router import router as admin_router
from auth import service as auth_service
from state import SCHEDULE_CRON, SCHEDULE_CHANNELS, REPORTS_DIR
from scheduler import scheduled_report_job, run_group_schedule_job
from routers.logs import router as logs_router
from routers.reports import router as reports_router
from routers.hosts import router as hosts_router
from routers.ssh import router as ssh_router
from routers.health import router as health_router
from routers.settings import router as settings_router
from routers.slowlog import router as slowlog_router
from routers.agent import router as agent_router
from routers.groups import router as groups_router
from routers.skywalking import router as skywalking_router
from routers.feishu_bot import router as feishu_bot_router
from routers.observability import router as observability_router
from routers.agent_config import router as agent_config_router
from routers.kubernetes import router as k8s_router
from routers.ansible_tasks import router as ansible_router
from routers.events import router as events_router
from routers.middleware import router as middleware_router
from routers.tickets import router as tickets_router
from routers.elasticsearch import router as es_router
from routers.alerts import router as alerts_router
from routers.rca import router as rca_router
from routers.jenkins import router as jenkins_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 定时任务 ─────────────────────────────────────
    scheduler = AsyncIOScheduler()
    try:
        minute, hour, day, month, day_of_week = SCHEDULE_CRON.split()
    except ValueError:
        minute, hour, day, month, day_of_week = "0", "9", "*", "*", "*"
        logger.warning("[scheduler] SCHEDULE_CRON 格式错误，使用默认值 '0 9 * * *'")

    scheduler.add_job(
        scheduled_report_job,
        CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week),
        id="daily_report",
        replace_existing=True,
    )

    # 异常检测：每 5 分钟执行一次
    from services.anomaly_detector import run_detection
    scheduler.add_job(
        run_detection,
        CronTrigger(minute="*/5"),
        id="anomaly_detection",
        replace_existing=True,
    )

    # 分组定时巡检：每分钟检查各组配置的推送时间
    scheduler.add_job(
        run_group_schedule_job,
        CronTrigger(minute="*"),
        id="group_schedule",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "[scheduler] 定时推送已启动，cron='%s'，渠道=%s",
        SCHEDULE_CRON, SCHEDULE_CHANNELS or "（未配置，仅生成报告不推送）",
    )

    # ── 数据库初始化 ──────────────────────────────────
    from pathlib import Path
    Path("./data").mkdir(exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as db:
        await auth_service.sync_modules(db)
        created = await auth_service.ensure_admin(db)
        if created:
            logger.info("[AUTH] 初始管理员账号已创建")

    # ── 历史报告元数据同步到 DB ────────────────────────────────────
    async def _sync_report_meta():
        try:
            from report_store import sync_from_files
            ok, skipped = await sync_from_files(REPORTS_DIR)
            if ok:
                logger.info("[report_store] 历史报告元数据同步: 导入 %d 条，跳过 %d 条", ok, skipped)
        except Exception as exc:
            logger.warning("[report_store] 元数据同步失败（不影响启动）: %s", exc)

    asyncio.create_task(_sync_report_meta())

    # ── 历史日报批量导入 Milvus（后台，不阻塞启动）────────────────
    async def _import_reports():
        try:
            from agent.report_memory import get_report_memory
            from state import REPORTS_DIR
            ok, skipped = await get_report_memory().batch_import(str(REPORTS_DIR))
            if ok:
                logger.info("[report_memory] 历史日报批量导入完成: 入库 %d 条，跳过 %d 条", ok, skipped)
        except Exception as exc:
            logger.warning("[report_memory] 批量导入失败（不影响启动）: %s", exc)

    asyncio.create_task(_import_reports())

    yield

    scheduler.shutdown(wait=False)
    logger.info("[scheduler] 定时推送已停止")


# ── 应用组装 ──────────────────────────────────────────────────────────────────

app = FastAPI(title="AI Ops Log Analysis", version="2.0.0", lifespan=lifespan)

_cors_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(logs_router)
app.include_router(reports_router)
app.include_router(hosts_router)
app.include_router(ssh_router)
app.include_router(health_router)
app.include_router(settings_router)

app.include_router(slowlog_router)
app.include_router(agent_router)
app.include_router(groups_router)
app.include_router(skywalking_router)
app.include_router(feishu_bot_router)
app.include_router(observability_router)
app.include_router(agent_config_router)
app.include_router(k8s_router)
app.include_router(ansible_router)
app.include_router(events_router)
app.include_router(middleware_router)
app.include_router(tickets_router)
app.include_router(es_router)
app.include_router(alerts_router)
app.include_router(rca_router)
app.include_router(jenkins_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("DEV_RELOAD", "").lower() in ("1", "true", "yes"),
    )
