"""认证路由 /api/auth/*"""
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db import get_db
from auth import service, session as sess
from auth.schemas import RegisterRequest, LoginRequest, ChangePasswordRequest, MeOut, UserOut
from auth.models import User
from auth.password import hash_password, verify_password
from auth.audit import write_audit
from auth.deps import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _login_rate_key(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    forwarded = forwarded or request.headers.get("x-real-ip", "").strip()
    return f"{peer}|{forwarded[:64]}" if forwarded else peer


@router.post("/register")
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        user = await service.register_user(db, body.username, body.email, body.password, body.display_name)
    except ValueError as e:
        raise HTTPException(400, detail=str(e))
    await write_audit(db, "register", user_id=user.id, ip=request.client.host if request.client else "")
    return {"message": "注册成功，等待管理员审批"}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else ""
    rate_key = _login_rate_key(request)
    if await sess.is_ip_limited(rate_key):
        raise HTTPException(429, detail="登录尝试过于频繁，请稍后再试")
    try:
        user, session_id = await service.login_user(db, body.username, body.password, ip)
    except ValueError as e:
        await sess.incr_ip_fail(rate_key)
        await write_audit(db, "login", ip=ip, status="fail", detail=str(e))
        raise HTTPException(401, detail=str(e))

    perms = await service.get_user_permissions(db, user.id)
    await write_audit(db, "login", user_id=user.id, ip=ip, status="success")

    secure_env = os.getenv("SESSION_COOKIE_SECURE", "").strip().lower()
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
    secure_cookie = secure_env in {"1", "true", "yes", "on"} or (
        not secure_env and (forwarded_proto == "https" or request.url.scheme == "https")
    )

    response.set_cookie(
        "session_id", session_id,
        httponly=True, samesite="lax", path="/",
        secure=secure_cookie,
        max_age=int(sess.SESSION_TTL),
    )
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "is_superuser": user.is_superuser,
        "permissions": perms,
    }


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    session_id = request.cookies.get("session_id")
    user = None
    try:
        user = await current_user(request, db)
    except Exception:
        pass
    if session_id:
        await sess.delete_session(session_id)
    response.delete_cookie("session_id", path="/")
    await write_audit(db, "logout", user_id=user.id if user else None,
                      ip=request.client.host if request.client else "")
    return {"message": "已退出登录"}


@router.get("/me", response_model=MeOut)
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    user = await current_user(request, db)
    perms = await service.get_user_permissions(db, user.id)
    return MeOut(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_superuser=user.is_superuser,
        permissions=perms,
    )


@router.put("/password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await current_user(request, db)
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, detail="原密码错误")
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    await write_audit(db, "change_password", user_id=user.id,
                      ip=request.client.host if request.client else "")
    return {"message": "密码修改成功"}
