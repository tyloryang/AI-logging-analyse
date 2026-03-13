"""管理员路由 /api/admin/*"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from db import get_db
from auth.models import User, Module, AuditLog, Permission
from auth.schemas import (
    CreateUserRequest, UpdateUserRequest, UpdatePermissionsRequest,
    UserOut, ModuleOut, AuditLogOut
)
from auth.password import hash_password
from auth.deps import require_admin
from auth.audit import write_audit
from auth import service, session as sess

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    status: Optional[str] = None,
    _: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    q = select(User).order_by(desc(User.created_at))
    if status:
        q = q.where(User.status == status)
    result = await db.execute(q)
    users = result.scalars().all()
    return [
        {
            "id": u.id, "username": u.username, "email": u.email,
            "display_name": u.display_name, "status": u.status,
            "is_superuser": u.is_superuser,
            "created_at": u.created_at.isoformat() if u.created_at else "",
        }
        for u in users
    ]


@router.post("/users")
async def create_user(
    body: CreateUserRequest,
    request: Request,
    admin: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    try:
        user = await service.register_user(db, body.username, body.email, body.password, body.display_name)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    user.status = "active"
    user.is_superuser = body.is_superuser
    await db.commit()
    await write_audit(db, "admin.create_user", user_id=admin.id, resource=body.username,
                      ip=request.client.host if request.client else "")
    return {"message": "用户创建成功", "id": user.id}


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    body: UpdateUserRequest,
    request: Request,
    admin: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, detail="用户不存在")
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.email is not None:
        user.email = body.email
    if body.status is not None:
        user.status = body.status
    if body.is_superuser is not None:
        user.is_superuser = body.is_superuser
    await db.commit()
    await write_audit(db, "admin.update_user", user_id=admin.id, resource=user.username,
                      ip=request.client.host if request.client else "")
    return {"message": "更新成功"}


@router.post("/users/{user_id}/approve")
async def approve_user(
    user_id: str,
    request: Request,
    admin: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, detail="用户不存在")
    if user.status != "pending":
        raise HTTPException(400, detail="只能审批 pending 状态的用户")
    user.status = "active"
    await db.commit()
    await write_audit(db, "admin.approve_user", user_id=admin.id, resource=user.username,
                      ip=request.client.host if request.client else "")
    return {"message": "审批通过"}


@router.post("/users/{user_id}/unlock")
async def unlock_user(
    user_id: str,
    request: Request,
    admin: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, detail="用户不存在")
    user.status = "active"
    user.failed_attempts = 0
    await sess.clear_locked(user.id)
    await db.commit()
    await write_audit(db, "admin.unlock_user", user_id=admin.id, resource=user.username,
                      ip=request.client.host if request.client else "")
    return {"message": "账号已解锁"}


@router.delete("/users/{user_id}")
async def disable_user(
    user_id: str,
    request: Request,
    admin: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(400, detail="不能禁用自己")
    user.status = "disabled"
    await db.commit()
    await write_audit(db, "admin.disable_user", user_id=admin.id, resource=user.username,
                      ip=request.client.host if request.client else "")
    return {"message": "用户已禁用"}


@router.get("/users/{user_id}/permissions")
async def get_permissions(
    user_id: str,
    _: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    perms = await service.get_user_permissions(db, user_id)
    # 补全所有模块（没配置的默认 none）
    result = await db.execute(select(Module))
    modules = result.scalars().all()
    return [{"module_id": m.id, "name": m.name, "level": perms.get(m.id, "none")} for m in modules]


@router.put("/users/{user_id}/permissions")
async def set_permissions(
    user_id: str,
    body: UpdatePermissionsRequest,
    request: Request,
    admin: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    await service.update_permissions(db, user_id, [p.model_dump() for p in body.permissions])
    await write_audit(db, "admin.update_permissions", user_id=admin.id, resource=user_id,
                      ip=request.client.host if request.client else "")
    return {"message": "权限更新成功"}


@router.get("/modules")
async def list_modules(
    _: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Module))
    return [{"id": m.id, "name": m.name, "description": m.description} for m in result.scalars()]


@router.get("/audit-logs")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    username: Optional[str] = None,
    _: User = require_admin,
    db: AsyncSession = Depends(get_db),
):
    q = select(AuditLog).order_by(desc(AuditLog.created_at))
    if action:
        q = q.where(AuditLog.action.contains(action))
    if username:
        user_result = await db.execute(select(User).where(User.username == username))
        u = user_result.scalar_one_or_none()
        if u:
            q = q.where(AuditLog.user_id == u.id)
        else:
            return {"items": [], "total": 0}
    offset = (page - 1) * page_size
    q = q.offset(offset).limit(page_size)
    result = await db.execute(q)
    logs = result.scalars().all()
    return {
        "items": [
            {
                "id": l.id, "user_id": l.user_id, "action": l.action,
                "resource": l.resource, "ip": l.ip, "status": l.status,
                "detail": l.detail,
                "created_at": l.created_at.isoformat() if l.created_at else "",
            }
            for l in logs
        ],
        "page": page,
        "page_size": page_size,
    }
