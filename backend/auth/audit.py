"""操作审计日志工具"""
from sqlalchemy.ext.asyncio import AsyncSession
from auth.models import AuditLog


async def write_audit(
    db: AsyncSession,
    action: str,
    *,
    user_id: str = None,
    resource: str = None,
    ip: str = "",
    status: str = "success",
    detail: str = None,
):
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        ip=ip,
        status=status,
        detail=detail,
    )
    db.add(log)
    await db.commit()
