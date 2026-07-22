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
from fastapi.middleware.gzip import GZipMiddleware

from db import engine, Base, AsyncSessionLocal
from auth.router import router as auth_router
from auth.admin_router import router as admin_router
from auth import service as auth_service
from auth.middleware import AuthenticationMiddleware
from cors_config import add_permissive_cors
from state import SCHEDULE_CRON, SCHEDULE_CHANNELS, REPORTS_DIR, migrate_cmdb_storage
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
from routers.k8s_agent import router as k8s_agent_router
from routers.ansible_tasks import router as ansible_router
from routers.events import router as events_router
from routers.middleware import router as middleware_router
from routers.tickets import router as tickets_router
from routers.elasticsearch import router as es_router
from routers.redis_clusters import router as redis_router
from routers.kafka_clusters import router as kafka_router
from routers.alerts import router as alerts_router
from routers.rca import router as rca_router
from routers.knowledge_graph import router as kg_router
from routers.jenkins import router as jenkins_router
from routers.topology import router as topology_router
from routers.cc_haha import router as cc_haha_router
from routers.db_ai import router as db_ai_router
from routers.knowledge import router as knowledge_router
from routers.workflows import router as workflows_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("[config] %s=%r is invalid, using %s", name, raw, default)
        return default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _gzip_enabled() -> bool:
    return os.getenv("GZIP_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


def _path_should_skip_gzip(path: str) -> bool:
    # Starlette 0.38 compresses streaming responses too; skip SSE and downloads.
    lowered = (path or "").lower()
    skip_tokens = ("stream", "export", "template", "excel", "download")
    return any(token in lowered for token in skip_tokens)


class SelectiveGZipMiddleware(GZipMiddleware):
    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") == "http" and _path_should_skip_gzip(scope.get("path", "")):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


async def _migrate_add_columns(conn) -> None:
    """增量 DDL 迁移：为已有表补加新列，幂等（列已存在时跳过）。
    仅支持 SQLite（项目默认数据库）。
    """
    import sqlalchemy as sa

    migrations = [
        # (table, column, portable_type_ddl)
        ("agent_conversations", "project_path", "VARCHAR(500) DEFAULT ''"),
    ]
    for table, col, col_ddl in migrations:
        try:
            def inspect_columns(sync_conn):
                inspector = sa.inspect(sync_conn)
                if not inspector.has_table(table):
                    return None
                return {column["name"] for column in inspector.get_columns(table)}

            existing_cols = await conn.run_sync(inspect_columns)
            if existing_cols is None:
                logger.debug("[migration] table %s does not exist, skip", table)
                continue
            if col not in existing_cols:
                await conn.execute(
                    sa.text(f"ALTER TABLE {table} ADD COLUMN {col} {col_ddl}")
                )
                logger.info("[migration] ALTER TABLE %s ADD COLUMN %s  ✓", table, col)
            else:
                logger.debug("[migration] %s.%s already exists, skip", table, col)
        except Exception as exc:
            logger.warning("[migration] %s.%s failed: %s", table, col, exc)


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

    # 统一 cron tick：Ansible 计划任务 + 工作流定时任务（每分钟检查表达式）
    from services.cron_ticker import run_cron_tick
    scheduler.add_job(
        run_cron_tick,
        CronTrigger(minute="*"),
        id="cron_ticker",
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
        # 增量迁移：为已存在的表补加新列（SQLite / PostgreSQL 兼容）
        await _migrate_add_columns(conn)
    async with AsyncSessionLocal() as db:
        await auth_service.sync_modules(db)
        created = await auth_service.ensure_admin(db)
        if created:
            logger.info("[AUTH] 初始管理员账号已创建")

    cmdb_stats = await asyncio.to_thread(migrate_cmdb_storage)
    logger.info("[CMDB] 数据库存储已就绪: %s", cmdb_stats)

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

if _gzip_enabled():
    app.add_middleware(
        SelectiveGZipMiddleware,
        minimum_size=_env_int("GZIP_MIN_SIZE", 1024, min_value=0),
        compresslevel=_env_int("GZIP_COMPRESS_LEVEL", 6, min_value=1, max_value=9),
    )
app.add_middleware(AuthenticationMiddleware)
# Must be registered last: Starlette's last added middleware is outermost, so
# authentication failures and every Router response receive CORS headers.
add_permissive_cors(app)

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
app.include_router(k8s_agent_router, prefix="/api/k8s")
app.include_router(ansible_router)
app.include_router(events_router)
app.include_router(middleware_router)
app.include_router(tickets_router)
app.include_router(es_router)
app.include_router(redis_router)
app.include_router(kafka_router)
app.include_router(alerts_router)
app.include_router(rca_router)
app.include_router(kg_router)
app.include_router(jenkins_router)
app.include_router(cc_haha_router)
app.include_router(topology_router)
app.include_router(db_ai_router)
app.include_router(knowledge_router)
app.include_router(workflows_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=os.getenv("DEV_RELOAD", "").lower() in ("1", "true", "yes"),
    )
