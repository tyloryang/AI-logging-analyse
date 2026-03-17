"""AI Ops 日志分析系统 - FastAPI 主入口

load_dotenv() 必须在所有本地模块 import 之前执行，
否则 state.py / auth/session.py 等模块级 os.getenv() 会取到默认值。
"""
from dotenv import load_dotenv
load_dotenv()

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import engine, Base, AsyncSessionLocal
from auth.router import router as auth_router
from auth.admin_router import router as admin_router
from auth import service as auth_service
from state import SCHEDULE_CRON, SCHEDULE_CHANNELS
from scheduler import scheduled_report_job
from routers.logs import router as logs_router
from routers.reports import router as reports_router
from routers.hosts import router as hosts_router
from routers.ssh import router as ssh_router
from routers.health import router as health_router
from routers.settings import router as settings_router
from routers.slowlog import router as slowlog_router

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

    yield

    scheduler.shutdown(wait=False)
    logger.info("[scheduler] 定时推送已停止")


# ── 应用组装 ──────────────────────────────────────────────────────────────────

app = FastAPI(title="AI Ops Log Analysis", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("DEV_RELOAD", "").lower() in ("1", "true", "yes"),
    )
