"""Runtime environment bootstrap shared by backend entrypoints."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

_BOOTSTRAPPED = False
_BACKEND_DIR = Path(__file__).resolve().parent
_DOTENV_FILE = _BACKEND_DIR / ".env"
_SETTINGS_FILE = _BACKEND_DIR / "data" / "settings.json"

_SETTINGS_ENV_MAPPING = {
    "loki_url": "LOKI_URL",
    "loki_username": "LOKI_USERNAME",
    "loki_password": "LOKI_PASSWORD",
    "prometheus_url": "PROMETHEUS_URL",
    "prometheus_username": "PROMETHEUS_USERNAME",
    "prometheus_password": "PROMETHEUS_PASSWORD",
    "grafana_url": "GRAFANA_URL",
    "grafana_api_key": "GRAFANA_API_KEY",
    "skywalking_oap_url": "SKYWALKING_OAP_URL",
    "ai_provider": "AI_PROVIDER",
    "ai_base_url": "AI_BASE_URL",
    "ai_model": "AI_MODEL",
    "ai_enable_thinking": "AI_ENABLE_THINKING",
    "feishu_bot_app_id": "FEISHU_BOT_APP_ID",
    "feishu_bot_app_secret": "FEISHU_BOT_APP_SECRET",
    "feishu_bot_encrypt_key": "FEISHU_BOT_ENCRYPT_KEY",
    "feishu_bot_verify_token": "FEISHU_BOT_VERIFY_TOKEN",
    "feishu_require_mention": "FEISHU_REQUIRE_MENTION",
    "feishu_callback_host": "FEISHU_CALLBACK_HOST",
    "feishu_callback_port": "FEISHU_CALLBACK_PORT",
    "feishu_callback_public_base_url": "FEISHU_CALLBACK_PUBLIC_BASE_URL",
    "agent_executor": "AIOPS_AGENT_EXECUTOR",
    "agent_external_command": "AIOPS_EXTERNAL_AGENT_COMMAND",
    "agent_external_args": "AIOPS_EXTERNAL_AGENT_ARGS",
    "agent_external_use_stdin": "AIOPS_EXTERNAL_AGENT_USE_STDIN",
    "agent_external_timeout": "AIOPS_EXTERNAL_AGENT_TIMEOUT",
    "agent_external_workdir": "AIOPS_EXTERNAL_AGENT_WORKDIR",
}


def _load_runtime_settings() -> dict:
    if not _SETTINGS_FILE.exists():
        return {}

    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _apply_runtime_settings_env() -> None:
    """Override process env with persisted settings from backend/data/settings.json."""
    settings = _load_runtime_settings()
    if not settings:
        return

    for settings_key, env_key in _SETTINGS_ENV_MAPPING.items():
        value = settings.get(settings_key)
        if value not in (None, ""):
            os.environ[env_key] = str(value)

    ai_api_key = settings.get("ai_api_key")
    if ai_api_key not in (None, ""):
        ai_provider = str(
            settings.get("ai_provider") or os.getenv("AI_PROVIDER", "anthropic")
        ).lower()
        if ai_provider == "openai":
            os.environ["AI_API_KEY"] = str(ai_api_key)
        else:
            os.environ["ANTHROPIC_API_KEY"] = str(ai_api_key)


def bootstrap_runtime_env() -> None:
    """Load backend/.env first, then apply persisted runtime settings."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    load_dotenv(dotenv_path=_DOTENV_FILE)
    _apply_runtime_settings_env()
    _BOOTSTRAPPED = True


def refresh_runtime_settings_env() -> None:
    """Refresh process env from backend/data/settings.json."""
    _apply_runtime_settings_env()
