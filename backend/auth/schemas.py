"""Pydantic 请求/响应模型"""
from typing import Optional, Dict, List
from pydantic import BaseModel, EmailStr, field_validator
import re

# ── 认证 ──────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    display_name: str = ""

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("密码长度至少 8 位")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("密码必须包含字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含数字")
        return v

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("密码长度至少 8 位")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("密码必须包含字母")
        if not re.search(r"\d", v):
            raise ValueError("密码必须包含数字")
        return v

class UserOut(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    status: str
    is_superuser: bool
    created_at: str

    model_config = {"from_attributes": True}

class MeOut(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    is_superuser: bool
    permissions: Dict[str, str]  # {module_id: level}

# ── 管理员 ──────────────────────────────────

class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    display_name: str = ""
    is_superuser: bool = False

class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    is_superuser: Optional[bool] = None

class PermissionItem(BaseModel):
    module_id: str
    level: str  # none / view / operate

class UpdatePermissionsRequest(BaseModel):
    permissions: List[PermissionItem]

class ModuleOut(BaseModel):
    id: str
    name: str
    description: str

    model_config = {"from_attributes": True}

class AuditLogOut(BaseModel):
    id: str
    user_id: Optional[str]
    action: str
    resource: Optional[str]
    ip: str
    status: str
    detail: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}
