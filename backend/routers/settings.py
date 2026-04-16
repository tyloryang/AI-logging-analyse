"""系统配置管理路由。"""

from __future__ import annotations

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

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "data" / "settings.json"


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
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _normalize_port(value: int | str | None, default: int = 8001) -> int:
    try:
        port = int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default
    return port if 1 <= port <= 65535 else default


class SettingsPayload(BaseModel):
    loki_url: str = ""
    loki_username: str = ""
    loki_password: str = ""
    prometheus_url: str = ""
    prometheus_username: str = ""
    prometheus_password: str = ""
    grafana_url: str = ""
    skywalking_oap_url: str = ""
    ai_provider: str = ""
    ai_base_url: str = ""
    ai_model: str = ""
    ai_api_key: str = ""
    feishu_bot_app_id: str = ""
    feishu_bot_app_secret: str = ""
    feishu_bot_encrypt_key: str = ""
    feishu_bot_verify_token: str = ""
    feishu_callback_host: str = "0.0.0.0"
    feishu_callback_port: int | str | None = 8001
    feishu_callback_public_base_url: str = ""


class TestPayload(BaseModel):
    url: str
    username: str = ""
    password: str = ""


@router.get("/api/settings")
async def get_settings():
    """读取当前生效配置，敏感字段以 *_set 形式返回。"""
    import state

    return {
        "loki_url": state.LOKI_URL,
        "loki_username": state.LOKI_USERNAME,
        "loki_password_set": bool(state.LOKI_PASSWORD),
        "prometheus_url": state.PROMETHEUS_URL,
        "prometheus_username": state.PROMETHEUS_USERNAME,
        "prometheus_password_set": bool(state.PROMETHEUS_PASSWORD),
        "ai_provider": os.getenv("AI_PROVIDER", "anthropic"),
        "ai_base_url": os.getenv("AI_BASE_URL", ""),
        "ai_model": os.getenv("AI_MODEL", ""),
        "ai_api_key_set": bool(
            os.getenv("ANTHROPIC_API_KEY") or os.getenv("AI_API_KEY")
        ),
        "grafana_url": os.getenv("GRAFANA_URL", "http://localhost:3000"),
        "skywalking_oap_url": os.getenv("SKYWALKING_OAP_URL", "http://localhost:12800"),
        "feishu_bot_app_id": os.getenv("FEISHU_BOT_APP_ID", ""),
        "feishu_bot_app_secret_set": bool(os.getenv("FEISHU_BOT_APP_SECRET", "")),
        "feishu_bot_encrypt_key_set": bool(os.getenv("FEISHU_BOT_ENCRYPT_KEY", "")),
        "feishu_bot_verify_token_set": bool(os.getenv("FEISHU_BOT_VERIFY_TOKEN", "")),
        "feishu_callback_host": os.getenv("FEISHU_CALLBACK_HOST", "0.0.0.0"),
        "feishu_callback_port": _normalize_port(os.getenv("FEISHU_CALLBACK_PORT")),
        "feishu_callback_public_base_url": os.getenv(
            "FEISHU_CALLBACK_PUBLIC_BASE_URL", ""
        ),
    }


@router.put("/api/settings")
async def update_settings(body: SettingsPayload):
    """
    保存配置到 backend/data/settings.json。

    - Prometheus / Loki 连接信息在当前主进程中立即热重载
    - AI Provider 在当前主进程懒重建
    - 飞书机器人密钥立即写入当前主进程环境变量
    - 独立飞书回调服务的 Host / Port 需要重启该独立服务后才会生效
    """
    import state
    from loki_client import LokiClient
    from prom_client import PrometheusClient

    existing = _load()

    if body.loki_url:
        existing["loki_url"] = body.loki_url
    if body.loki_username is not None:
        existing["loki_username"] = body.loki_username
    if body.loki_password:
        existing["loki_password"] = body.loki_password

    if body.prometheus_url:
        existing["prometheus_url"] = body.prometheus_url
    if body.prometheus_username is not None:
        existing["prometheus_username"] = body.prometheus_username
    if body.prometheus_password:
        existing["prometheus_password"] = body.prometheus_password

    if body.grafana_url is not None:
        existing["grafana_url"] = body.grafana_url
    if body.skywalking_oap_url is not None:
        existing["skywalking_oap_url"] = body.skywalking_oap_url

    if body.ai_provider:
        existing["ai_provider"] = body.ai_provider
    if body.ai_base_url is not None:
        existing["ai_base_url"] = body.ai_base_url
    if body.ai_model is not None:
        existing["ai_model"] = body.ai_model
    if body.ai_api_key:
        existing["ai_api_key"] = body.ai_api_key

    if body.feishu_bot_app_id is not None:
        existing["feishu_bot_app_id"] = body.feishu_bot_app_id
    if body.feishu_bot_app_secret:
        existing["feishu_bot_app_secret"] = body.feishu_bot_app_secret
    if body.feishu_bot_encrypt_key:
        existing["feishu_bot_encrypt_key"] = body.feishu_bot_encrypt_key
    if body.feishu_bot_verify_token:
        existing["feishu_bot_verify_token"] = body.feishu_bot_verify_token

    callback_host = (body.feishu_callback_host or "0.0.0.0").strip() or "0.0.0.0"
    callback_port = _normalize_port(body.feishu_callback_port)
    callback_public_base_url = (body.feishu_callback_public_base_url or "").strip()

    existing["feishu_callback_host"] = callback_host
    existing["feishu_callback_port"] = callback_port
    existing["feishu_callback_public_base_url"] = callback_public_base_url

    _save(existing)

    hot_reloaded: list[str] = []
    restart_required: list[str] = []

    new_loki_url = existing.get("loki_url", state.LOKI_URL)
    new_loki_username = existing.get("loki_username", state.LOKI_USERNAME)
    new_loki_password = existing.get("loki_password", state.LOKI_PASSWORD)
    loki_changed = (
        new_loki_url != state.LOKI_URL
        or new_loki_username != state.LOKI_USERNAME
        or new_loki_password != state.LOKI_PASSWORD
    )
    if loki_changed:
        state.loki = LokiClient(new_loki_url, new_loki_username, new_loki_password)
        state.LOKI_URL = new_loki_url
        state.LOKI_USERNAME = new_loki_username
        state.LOKI_PASSWORD = new_loki_password
        hot_reloaded.append("loki")

    new_prometheus_url = existing.get("prometheus_url", state.PROMETHEUS_URL)
    new_prometheus_username = existing.get(
        "prometheus_username", state.PROMETHEUS_USERNAME
    )
    new_prometheus_password = existing.get(
        "prometheus_password", state.PROMETHEUS_PASSWORD
    )
    prometheus_changed = (
        new_prometheus_url != state.PROMETHEUS_URL
        or new_prometheus_username != state.PROMETHEUS_USERNAME
        or new_prometheus_password != state.PROMETHEUS_PASSWORD
    )
    if prometheus_changed:
        state.prom = PrometheusClient(
            new_prometheus_url,
            new_prometheus_username,
            new_prometheus_password,
        )
        state.PROMETHEUS_URL = new_prometheus_url
        state.PROMETHEUS_USERNAME = new_prometheus_username
        state.PROMETHEUS_PASSWORD = new_prometheus_password
        hot_reloaded.append("prometheus")

    # Grafana / SkyWalking URL 热更新（直接写环境变量，observability 路由每次请求时读取）
    new_grafana_url = existing.get("grafana_url", os.getenv("GRAFANA_URL", "http://localhost:3000"))
    new_sw_url = existing.get("skywalking_oap_url", os.getenv("SKYWALKING_OAP_URL", "http://localhost:12800"))
    if new_grafana_url:
        os.environ["GRAFANA_URL"] = new_grafana_url
        hot_reloaded.append("grafana_url")
    if new_sw_url:
        os.environ["SKYWALKING_OAP_URL"] = new_sw_url
        hot_reloaded.append("skywalking_oap_url")

    new_ai_provider = existing.get("ai_provider", os.getenv("AI_PROVIDER", "anthropic"))
    new_ai_base_url = existing.get("ai_base_url", os.getenv("AI_BASE_URL", ""))
    new_ai_model = existing.get("ai_model", os.getenv("AI_MODEL", ""))
    ai_changed = (
        str(new_ai_provider) != os.getenv("AI_PROVIDER", "anthropic")
        or str(new_ai_base_url) != os.getenv("AI_BASE_URL", "")
        or str(new_ai_model) != os.getenv("AI_MODEL", "")
        or bool(body.ai_api_key)
    )
    if ai_changed:
        os.environ["AI_PROVIDER"] = str(new_ai_provider)
        os.environ["AI_BASE_URL"] = str(new_ai_base_url)
        os.environ["AI_MODEL"] = str(new_ai_model)
        if body.ai_api_key:
            if str(new_ai_provider).lower() == "openai":
                os.environ["AI_API_KEY"] = body.ai_api_key
            else:
                os.environ["ANTHROPIC_API_KEY"] = body.ai_api_key
        state.analyzer._provider = None
        hot_reloaded.append("ai_provider")

    if os.getenv("FEISHU_BOT_APP_ID", "") != body.feishu_bot_app_id:
        os.environ["FEISHU_BOT_APP_ID"] = body.feishu_bot_app_id
        hot_reloaded.append("feishu_bot_app_id")
    if body.feishu_bot_app_secret:
        os.environ["FEISHU_BOT_APP_SECRET"] = body.feishu_bot_app_secret
        hot_reloaded.append("feishu_bot_app_secret")
        try:
            from routers.feishu_bot import _token_cache

            _token_cache["token"] = ""
            _token_cache["expires_at"] = 0.0
        except Exception:
            pass
    if body.feishu_bot_encrypt_key:
        os.environ["FEISHU_BOT_ENCRYPT_KEY"] = body.feishu_bot_encrypt_key
        hot_reloaded.append("feishu_bot_encrypt_key")
    if body.feishu_bot_verify_token:
        os.environ["FEISHU_BOT_VERIFY_TOKEN"] = body.feishu_bot_verify_token
        hot_reloaded.append("feishu_bot_verify_token")

    current_callback_host = os.getenv("FEISHU_CALLBACK_HOST", "0.0.0.0")
    current_callback_port = _env_int("FEISHU_CALLBACK_PORT", 8001)
    current_callback_public_base_url = os.getenv("FEISHU_CALLBACK_PUBLIC_BASE_URL", "")

    os.environ["FEISHU_CALLBACK_HOST"] = callback_host
    os.environ["FEISHU_CALLBACK_PORT"] = str(callback_port)
    os.environ["FEISHU_CALLBACK_PUBLIC_BASE_URL"] = callback_public_base_url

    if current_callback_host != callback_host:
        restart_required.append("feishu_callback_host")
    if current_callback_port != callback_port:
        restart_required.append("feishu_callback_port")
    if current_callback_public_base_url != callback_public_base_url:
        hot_reloaded.append("feishu_callback_public_base_url")

    note_parts: list[str] = []
    if hot_reloaded:
        note_parts.append(f"已立即生效：{', '.join(hot_reloaded)}")
    if restart_required:
        note_parts.append(
            f"需重启独立飞书回调服务后生效：{', '.join(restart_required)}"
        )
    if not note_parts:
        note_parts.append("配置已保存")

    note = "；".join(note_parts)
    logger.info("[settings] 配置已更新，热生效=%s，需重启=%s", hot_reloaded, restart_required)
    return {
        "ok": True,
        "note": note,
        "hot_reloaded": hot_reloaded,
        "restart_required": restart_required,
    }


@router.post("/api/settings/test/prometheus")
async def test_prometheus(body: TestPayload):
    """测试 Prometheus 连接。"""
    url = body.url.rstrip("/")
    try:
        kw: dict = {
            "url": f"{url}/api/v1/query",
            "params": {"query": "up"},
        }
        if body.username:
            kw["auth"] = (body.username, body.password)
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(**kw)
            return {"ok": response.status_code == 200, "status": response.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.post("/api/settings/test/loki")
async def test_loki(body: TestPayload):
    """测试 Loki 连接。"""
    url = body.url.rstrip("/")
    try:
        kw: dict = {"url": f"{url}/loki/api/v1/labels"}
        if body.username:
            kw["auth"] = (body.username, body.password)
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(**kw)
            return {"ok": response.status_code == 200, "status": response.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
