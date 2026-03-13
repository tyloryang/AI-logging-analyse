"""认证业务逻辑"""
import os
import secrets
import string
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from auth.models import User, Module, Permission
from auth.password import hash_password, verify_password
from auth import session as sess

LOGIN_FAIL_MAX = int(os.getenv("LOGIN_FAIL_MAX", "5"))

# 系统预置模块列表（新增模块在此追加即可）
SYSTEM_MODULES = [
    {"id": "dashboard", "name": "仪表盘",   "description": "系统总览"},
    {"id": "log",       "name": "日志分析", "description": "Loki 日志查询与 AI 分析"},
    {"id": "metrics",   "name": "指标监控", "description": "Prometheus 指标图表"},
    {"id": "alert",     "name": "告警历史", "description": "告警记录"},
    {"id": "report",    "name": "分析报告", "description": "运维日报生成与推送"},
    {"id": "cmdb",      "name": "主机 CMDB","description": "主机管理与 CMDB 信息"},
    {"id": "inspect",   "name": "主机巡检", "description": "阈值巡检与 AI 分析"},
    {"id": "ssh",       "name": "SSH 终端", "description": "Web SSH 终端"},
    {"id": "admin",     "name": "用户管理", "description": "用户、权限与审计"},
]


async def sync_modules(db: AsyncSession):
    """启动时同步模块表（upsert）"""
    for m in SYSTEM_MODULES:
        result = await db.execute(select(Module).where(Module.id == m["id"]))
        mod = result.scalar_one_or_none()
        if mod is None:
            db.add(Module(**m))
    await db.commit()


async def ensure_admin(db: AsyncSession) -> bool:
    """若无任何 active 用户，从环境变量创建初始 admin，返回是否创建"""
    result = await db.execute(select(User).where(User.status == "active").limit(1))
    if result.scalar_one_or_none():
        return False

    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "")
    if not admin_pass:
        chars = string.ascii_letters + string.digits + "!@#$%"
        admin_pass = "".join(secrets.choice(chars) for _ in range(16))
        print(f"\n[AUTH] 初始管理员密码（仅显示一次）: {admin_pass}\n")

    user = User(
        username=admin_user,
        email=f"{admin_user}@localhost",
        password_hash=hash_password(admin_pass),
        display_name="管理员",
        status="active",
        is_superuser=True,
    )
    db.add(user)
    await db.commit()
    return True


async def register_user(db: AsyncSession, username: str, email: str, password: str, display_name: str = "") -> User:
    # 检查重复
    r1 = await db.execute(select(User).where(User.username == username))
    if r1.scalar_one_or_none():
        raise ValueError("用户名已存在")
    r2 = await db.execute(select(User).where(User.email == email))
    if r2.scalar_one_or_none():
        raise ValueError("邮箱已被注册")

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        display_name=display_name or username,
        status="pending",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, username: str, password: str, ip: str = "") -> tuple[User, str]:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        raise ValueError("用户名或密码错误")

    if user.status == "disabled":
        raise ValueError("账号已被禁用")

    if user.status == "locked" or await sess.is_locked(user.id):
        raise ValueError("账号已锁定，请联系管理员解锁")

    if user.status == "pending":
        raise ValueError("账号等待管理员审批")

    if not verify_password(password, user.password_hash):
        count = await sess.incr_fail(username)
        if count >= LOGIN_FAIL_MAX:
            user.status = "locked"
            await sess.set_locked(user.id)
            await db.commit()
            raise ValueError(f"密码错误次数过多，账号已锁定")
        raise ValueError(f"用户名或密码错误（剩余尝试 {LOGIN_FAIL_MAX - count} 次）")

    await sess.clear_fail(username)
    session_id = await sess.create_session(user.id, user.username, ip)
    return user, session_id


async def get_user_permissions(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(Permission).where(Permission.user_id == user_id))
    return {p.module_id: p.level for p in result.scalars()}


async def update_permissions(db: AsyncSession, user_id: str, perms: list[dict]):
    for item in perms:
        result = await db.execute(
            select(Permission).where(
                Permission.user_id == user_id,
                Permission.module_id == item["module_id"]
            )
        )
        perm = result.scalar_one_or_none()
        if perm:
            perm.level = item["level"]
        else:
            db.add(Permission(user_id=user_id, module_id=item["module_id"], level=item["level"]))
    await db.commit()
