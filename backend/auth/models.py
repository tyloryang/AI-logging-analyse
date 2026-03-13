"""SQLAlchemy ORM 模型"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Enum, Text,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship
from db import Base

def _uuid():
    return str(uuid.uuid4())

def _now():
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id             = Column(String(36), primary_key=True, default=_uuid)
    username       = Column(String(64), unique=True, nullable=False, index=True)
    email          = Column(String(128), unique=True, nullable=False, index=True)
    password_hash  = Column(String(128), nullable=False)
    display_name   = Column(String(64), default="")
    status         = Column(Enum("pending", "active", "locked", "disabled", name="user_status"), default="pending")
    is_superuser   = Column(Boolean, default=False)
    failed_attempts= Column(Integer, default=0)
    locked_until   = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=_now)
    updated_at     = Column(DateTime, default=_now, onupdate=_now)

    permissions    = relationship("Permission", back_populates="user", cascade="all, delete-orphan")


class Module(Base):
    __tablename__ = "modules"

    id          = Column(String(64), primary_key=True)
    name        = Column(String(128), nullable=False)
    description = Column(String(256), default="")
    created_at  = Column(DateTime, default=_now)

    permissions = relationship("Permission", back_populates="module", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("user_id", "module_id"),)

    id        = Column(String(36), primary_key=True, default=_uuid)
    user_id   = Column(String(36), ForeignKey("users.id"), nullable=False)
    module_id = Column(String(64), ForeignKey("modules.id"), nullable=False)
    level     = Column(Enum("none", "view", "operate", name="perm_level"), default="none")
    updated_at= Column(DateTime, default=_now, onupdate=_now)

    user   = relationship("User", back_populates="permissions")
    module = relationship("Module", back_populates="permissions")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id        = Column(String(36), primary_key=True, default=_uuid)
    user_id   = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action    = Column(String(128), nullable=False)
    resource  = Column(String(256), nullable=True)
    ip        = Column(String(64), default="")
    status    = Column(Enum("success", "fail", name="audit_status"), default="success")
    detail    = Column(Text, nullable=True)
    created_at= Column(DateTime, default=_now)
