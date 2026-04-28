"""管理员路由 /api/admin/*"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
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
from state import load_user_groups, save_user_groups, load_groups, load_hosts_list

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    status: Optional[str] = None,
    _: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
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


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """禁用用户（保留数据，仅停用登录）。"""
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


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """彻底删除用户（不可恢复，同时清除分组权限记录）。"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, detail="用户不存在")
    if user.id == admin.id:
        raise HTTPException(400, detail="不能删除自己")
    username = user.username
    await db.delete(user)
    await db.commit()
    # 同步清理 user_groups 记录
    ug = load_user_groups()
    if user_id in ug:
        del ug[user_id]
        save_user_groups(ug)
    await write_audit(db, "admin.delete_user", user_id=admin.id, resource=username,
                      ip=request.client.host if request.client else "")
    return {"message": f"用户 {username} 已彻底删除"}


@router.get("/users/{user_id}/permissions")
async def get_permissions(
    user_id: str,
    _: User = Depends(require_admin),
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
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    await service.update_permissions(db, user_id, [p.model_dump() for p in body.permissions])
    await write_audit(db, "admin.update_permissions", user_id=admin.id, resource=user_id,
                      ip=request.client.host if request.client else "")
    return {"message": "权限更新成功"}


@router.get("/modules")
async def list_modules(
    _: User = Depends(require_admin),
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
    _: User = Depends(require_admin),
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



# ── 用户 CMDB 分组权限 ────────────────────────────────────────────────────────

class UserGroupsRequest(BaseModel):
    group_ids: list[str]   # 空列表表示"无权访问任何分组"


@router.get("/users/{user_id}/cmdb-groups")
async def get_user_cmdb_groups(
    user_id: str,
    _: User = Depends(require_admin),
):
    """获取用户被分配的 CMDB 分组列表（含每组主机数）。"""
    ug = load_user_groups()
    groups = load_groups()
    hosts = load_hosts_list()
    # 统计每组主机数
    count: dict[str, int] = {}
    for h in hosts:
        gid = h.get("group", "")
        if gid:
            count[gid] = count.get(gid, 0) + 1
    for g in groups:
        g["host_count"] = count.get(g["id"], 0)
    group_map = {g["id"]: g for g in groups}
    assigned_ids = ug.get(user_id, [])
    return {
        "user_id": user_id,
        "group_ids": assigned_ids,
        "groups": [group_map[gid] for gid in assigned_ids if gid in group_map],
        "all_groups": groups,
    }


@router.put("/users/{user_id}/cmdb-groups")
async def set_user_cmdb_groups(
    user_id: str,
    body: UserGroupsRequest,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """设置用户可访问的 CMDB 分组（超管不受限，此设置只对普通用户生效）。"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_superuser:
        return {"ok": True, "message": "管理员用户不受分组限制，设置已忽略"}
    ug = load_user_groups()
    ug[user_id] = list(set(body.group_ids))   # 去重
    save_user_groups(ug)
    return {"ok": True, "group_ids": ug[user_id]}
