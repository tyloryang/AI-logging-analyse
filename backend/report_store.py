"""报告元数据 DB 层（包含过期报告清理）

报告正文（含 AI 分析全文）继续存 JSON 文件，
元数据（id / title / health_score 等）存 SQLite 供快速列表查询。
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import Column, String, Integer, Text, select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db import Base, AsyncSessionLocal

logger = logging.getLogger(__name__)

_SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _parse_created_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _safe_report_path(reports_dir: Path, report_id: str) -> Path | None:
    if not _SAFE_REPORT_ID.fullmatch(str(report_id or "")):
        return None
    reports_root = reports_dir.resolve()
    candidate = (reports_root / f"{report_id}.json").resolve()
    if candidate.parent != reports_root:
        return None
    return candidate


# ── ORM 模型 ──────────────────────────────────────────────────────────────────

class ReportRecord(Base):
    __tablename__ = "report_meta"

    id            = Column(String(64),  primary_key=True)
    type          = Column(String(32),  nullable=False, default="daily")
    title         = Column(String(256), nullable=False,  default="")
    created_at    = Column(String(32),  nullable=False,  default="")   # ISO 字符串，便于排序
    health_score  = Column(Integer,     nullable=False,  default=0)
    # 运维日报字段
    total_logs    = Column(Integer,     default=0)
    total_errors  = Column(Integer,     default=0)
    service_count = Column(Integer,     default=0)
    active_alerts = Column(Integer,     default=0)
    # 慢日志 / 巡检报告附加摘要（序列化为 JSON）
    extra_json    = Column(Text,        default="{}")


# ── 写入 ─────────────────────────────────────────────────────────────────────

async def save_report_meta(report: dict) -> None:
    """插入或更新一条报告元数据记录（upsert via merge）"""
    extra = {
        k: report[k]
        for k in ("total_queries", "alert_queries", "hosts_count",
                  "group_id", "group_name")
        if k in report
    }
    rec = ReportRecord(
        id=report["id"],
        type=report.get("type", "daily"),
        title=report.get("title", ""),
        created_at=report.get("created_at", ""),
        health_score=report.get("health_score", 0),
        total_logs=report.get("total_logs", 0),
        total_errors=report.get("total_errors", 0),
        service_count=report.get("service_count", 0),
        active_alerts=report.get("active_alerts", 0),
        extra_json=json.dumps(extra, ensure_ascii=False),
    )
    try:
        async with AsyncSessionLocal() as db:
            await db.merge(rec)
            await db.commit()
    except Exception as exc:
        logger.warning("[report_store] save_report_meta 失败: %s", exc)


# ── 读取 ─────────────────────────────────────────────────────────────────────

async def list_report_meta(limit: int = 50) -> list[dict]:
    """按 created_at 倒序返回最新 N 条报告元数据"""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ReportRecord)
                .order_by(ReportRecord.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
    except Exception as exc:
        logger.warning("[report_store] list_report_meta 查询失败，降级读文件: %s", exc)
        return []

    out = []
    for r in rows:
        extra = {}
        try:
            extra = json.loads(r.extra_json or "{}")
        except Exception:
            pass
        d = {
            "id":            r.id,
            "type":          r.type,
            "title":         r.title,
            "created_at":    r.created_at,
            "health_score":  r.health_score,
            "total_logs":    r.total_logs,
            "total_errors":  r.total_errors,
            "service_count": r.service_count,
            "active_alerts": r.active_alerts,
        }
        d.update(extra)
        out.append(d)
    return out


# ── 启动同步 ──────────────────────────────────────────────────────────────────

async def sync_from_files(reports_dir: Path) -> tuple[int, int]:
    """将 reports/ 目录下已有 JSON 文件批量导入 DB（跳过已存在的记录）

    Returns:
        (imported_count, skipped_count)
    """
    ok = skipped = 0
    try:
        async with AsyncSessionLocal() as db:
            for p in sorted(reports_dir.glob("*.json"), reverse=True)[:300]:
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    rid = data.get("id")
                    if not rid:
                        continue
                    existing = await db.get(ReportRecord, rid)
                    if existing:
                        skipped += 1
                        continue
                    extra = {
                        k: data[k]
                        for k in ("total_queries", "alert_queries", "hosts_count",
                                  "group_id", "group_name")
                        if k in data
                    }
                    rec = ReportRecord(
                        id=rid,
                        type=data.get("type", "daily"),
                        title=data.get("title", ""),
                        created_at=data.get("created_at", ""),
                        health_score=data.get("health_score", 0),
                        total_logs=data.get("total_logs", 0),
                        total_errors=data.get("total_errors", 0),
                        service_count=data.get("service_count", 0),
                        active_alerts=data.get("active_alerts", 0),
                        extra_json=json.dumps(extra, ensure_ascii=False),
                    )
                    db.add(rec)
                    ok += 1
                except Exception:
                    pass
            await db.commit()
    except Exception as exc:
        logger.warning("[report_store] sync_from_files 失败: %s", exc)
    return ok, skipped


async def cleanup_old_reports(reports_dir: Path, retention_days: int) -> int:
    """删除超过 retention_days 天的报告文件及 DB 记录。

    Args:
        retention_days: 保留天数（0 = 不清理）
    Returns:
        删除的文件数量
    """
    if retention_days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    deleted = 0
    expired_file_ids: set[str] = set()
    expired_metadata_ids: set[str] = set()

    # JSON 是报告正文的事实来源；即使元数据注册失败，也必须能按保留期清理。
    reports_root = reports_dir.resolve()
    for path in reports_dir.glob("*.json"):
        try:
            resolved = path.resolve()
            if resolved.parent != reports_root or not resolved.is_file():
                continue
            if _safe_report_path(reports_root, path.stem) != resolved:
                continue
            data = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("id") != path.stem:
                continue
            created_at = _parse_created_at(data.get("created_at"))
            if created_at is not None and created_at < cutoff:
                expired_file_ids.add(path.stem)
        except (OSError, UnicodeError, json.JSONDecodeError):
            # 保守处理格式异常或无法安全读取的文件，避免误删无关 JSON。
            continue

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ReportRecord.id, ReportRecord.created_at)
            )
            for report_id, created_at_raw in result.all():
                created_at = _parse_created_at(created_at_raw)
                if (
                    created_at is not None
                    and created_at < cutoff
                    and _safe_report_path(reports_root, report_id) is not None
                ):
                    expired_metadata_ids.add(report_id)
    except Exception as exc:
        logger.warning("[report_store] 查询过期报告元数据失败: %s", exc)

    removed_file_ids: set[str] = set()
    for report_id in sorted(expired_file_ids):
        report_path = _safe_report_path(reports_root, report_id)
        if report_path is None:
            continue
        if report_path.exists():
            try:
                report_path.unlink()
                deleted += 1
            except OSError as exc:
                logger.warning(
                    "[report_store] 删除过期报告文件失败，保留元数据以便重试 %s: %s",
                    report_id,
                    exc,
                )
                continue
        removed_file_ids.add(report_id)

    # DB 年龄只能清理已经不存在的正文元数据；存在的 JSON 必须由自身内容
    # 独立证明已过期并先成功删除，防止陈旧元数据误删新鲜或异常文件。
    metadata_ids_to_remove = set(removed_file_ids)
    for report_id in expired_metadata_ids:
        report_path = _safe_report_path(reports_root, report_id)
        if report_path is not None and not report_path.exists():
            metadata_ids_to_remove.add(report_id)

    if metadata_ids_to_remove:
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(ReportRecord).where(
                        ReportRecord.id.in_(sorted(metadata_ids_to_remove))
                    )
                )
                await db.commit()
        except Exception as exc:
            logger.warning("[report_store] 删除过期报告元数据失败: %s", exc)

    logger.info(
        "[report_store] 清理过期报告: 删除 %d 个文件（保留 %d 天）",
        deleted,
        retention_days,
    )

    return deleted
