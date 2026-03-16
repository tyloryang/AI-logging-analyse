"""系统配置管理路由

路由：
  GET  /api/settings              — 读取当前配置（密码脱敏）
  PUT  /api/settings              — 保存配置并热重载 URL
  POST /api/settings/test/prometheus — 测试 Prometheus 连接
  POST /api/settings/test/loki       — 测试 Loki 连接
"""
import json
import logging
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.deps import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_admin)])

SETTINGS_FILE = Path("./data/settings.json")


def _load() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save(data: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


class SettingsPayload(BaseModel):
    loki_url:             str = ""
    loki_username:        str = ""
    loki_password:        str = ""   # 空字符串 = 不修改
    prometheus_url:       str = ""
    prometheus_username:  str = ""
    prometheus_password:  str = ""   # 空字符串 = 不修改
    ai_provider:          str = ""
    ai_base_url:          str = ""
    ai_model:             str = ""
    ai_api_key:           str = ""   # 空字符串 = 不修改


class TestPayload(BaseModel):
    url:      str
    username: str = ""
    password: str = ""


@router.get("/api/settings")
async def get_settings():
    """读取当前生效配置（密码已脱敏）"""
    import state
    return {
        "loki_url":               state.LOKI_URL,
        "loki_username":          state.LOKI_USERNAME,
        "loki_password_set":      bool(state.LOKI_PASSWORD),
        "prometheus_url":         state.PROMETHEUS_URL,
        "prometheus_username":    state.PROMETHEUS_USERNAME,
        "prometheus_password_set": bool(state.PROMETHEUS_PASSWORD),
        "ai_provider":            os.getenv("AI_PROVIDER", "anthropic"),
        "ai_base_url":            os.getenv("AI_BASE_URL", ""),
        "ai_model":               os.getenv("AI_MODEL", ""),
        "ai_api_key_set":         bool(
            os.getenv("ANTHROPIC_API_KEY") or os.getenv("AI_API_KEY")
        ),
    }


@router.put("/api/settings")
async def update_settings(body: SettingsPayload):
    """
    保存配置到 data/settings.json。
    - Prometheus / Loki URL 立即热重载（修改对象属性，无需重启）
    - 认证信息、AI 配置写入文件，重启后完全生效
    """
    existing = _load()

    # 按字段更新（密码类字段仅在非空时覆盖）
    if body.loki_url:            existing["loki_url"]            = body.loki_url
    if body.loki_username is not None:
                                  existing["loki_username"]       = body.loki_username
    if body.loki_password:       existing["loki_password"]       = body.loki_password
    if body.prometheus_url:      existing["prometheus_url"]      = body.prometheus_url
    if body.prometheus_username is not None:
                                  existing["prometheus_username"] = body.prometheus_username
    if body.prometheus_password: existing["prometheus_password"] = body.prometheus_password
    if body.ai_provider:         existing["ai_provider"]         = body.ai_provider
    if body.ai_base_url is not None:
                                  existing["ai_base_url"]         = body.ai_base_url
    if body.ai_model is not None: existing["ai_model"]           = body.ai_model
    if body.ai_api_key:          existing["ai_api_key"]          = body.ai_api_key

    _save(existing)

    # 热重载：只更新 URL（不影响 auth，无需重建 httpx.AsyncClient）
    import state
    hot_reloaded = []
    if body.prometheus_url:
        state.prom.base_url  = body.prometheus_url.rstrip("/")
        state.PROMETHEUS_URL = body.prometheus_url
        hot_reloaded.append("prometheus_url")
    if body.loki_url:
        state.loki.base_url  = body.loki_url.rstrip("/")
        state.LOKI_URL       = body.loki_url
        hot_reloaded.append("loki_url")

    note = (
        f"已立即生效：{', '.join(hot_reloaded)}；认证信息/AI 配置重启后生效"
        if hot_reloaded
        else "配置已保存，重启服务后生效"
    )
    logger.info("[settings] 配置已更新：%s", existing)
    return {"ok": True, "note": note, "hot_reloaded": hot_reloaded}


@router.post("/api/settings/test/prometheus")
async def test_prometheus(body: TestPayload):
    """测试 Prometheus 连接"""
    url = body.url.rstrip("/")
    try:
        kw: dict = {
            "url": f"{url}/api/v1/query",
            "params": {"query": "up"},
        }
        if body.username:
            kw["auth"] = (body.username, body.password)
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(**kw)
            return {"ok": r.status_code == 200, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/settings/test/loki")
async def test_loki(body: TestPayload):
    """测试 Loki 连接"""
    url = body.url.rstrip("/")
    try:
        kw: dict = {"url": f"{url}/loki/api/v1/labels"}
        if body.username:
            kw["auth"] = (body.username, body.password)
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(**kw)
            return {"ok": r.status_code == 200, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)}
