"""Unified quick routing for deterministic AIOps chat entrypoints."""

from __future__ import annotations

import os

from agent.es_quick_actions import get_es_quick_reply, mentions_es
from agent.k8s_quick_actions import get_k8s_quick_reply, mentions_k8s

_JENKINS_KEYWORDS = (
    "jenkins",
    "pipeline",
    "job",
    "jenkinsfile",
    "ci",
    "cd",
    "构建",
    "流水线",
    "发布",
    "上线",
    "打包",
    "触发构建",
    "构建日志",
    "构建历史",
)


def _refresh_env() -> None:
    try:
        from runtime_env import refresh_runtime_settings_env

        refresh_runtime_settings_env()
    except Exception:
        pass


def quick_actions_enabled(channel: str = "") -> bool:
    """Whether deterministic one-shot quick actions should bypass ReAct."""
    _refresh_env()
    names = []
    if channel:
        names.append(f"{channel.upper()}_QUICK_ACTIONS")
    names.append("AIOPS_QUICK_ACTIONS")

    for name in names:
        value = os.getenv(name, "").strip().lower()
        if value:
            return value in {"1", "true", "yes", "on", "quick"}
    return False


def mentions_jenkins(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in _JENKINS_KEYWORDS)


def detect_mode(text: str) -> str:
    if mentions_jenkins(text):
        return "jenkins_ops"
    if mentions_es(text):
        return "es_ops"
    if mentions_k8s(text):
        return "k8s_ops"
    return "chat"


async def get_quick_reply(text: str) -> str | None:
    es_reply = await get_es_quick_reply(text)
    if es_reply:
        return es_reply
    return await get_k8s_quick_reply(text)
