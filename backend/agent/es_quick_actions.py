"""Elasticsearch quick actions for deterministic chat and CLI handling."""

from __future__ import annotations

import json
import re

_KW_INDEX = "\u7d22\u5f15"
_KW_INDEX_LIST = "\u7d22\u5f15\u5217\u8868"
_KW_ES_CLUSTER = "es\u96c6\u7fa4"
_KW_ES_INDEX = "es\u7d22\u5f15"
_KW_FAILED = "\u5931\u8d25"
_KW_NOT_ENABLED = "\u672a\u627e\u5230\u6216\u672a\u542f\u7528"

_ES_KEYWORDS = (
    "elasticsearch",
    "opensearch",
    _KW_ES_CLUSTER,
    _KW_ES_INDEX,
    _KW_INDEX,
    "indices",
    "index list",
    "list indices",
)

_INDEX_PATTERN_REGEXES = (
    "(?:\\u7d22\\u5f15|indices?|index(?:\\s+list)?)(?:\\u5217\\u8868)?[\\s:\\uff1a`'\"]+([a-zA-Z0-9*._:-]+)",
    "[`'\"]([a-zA-Z0-9*._:-]+)[`'\"]\\s*(?:\\u7d22\\u5f15|indices?|index)",
    "(?:^|[\\s`'\"])([a-zA-Z0-9*._:-]+)\\s*(?:\\u7d22\\u5f15|indices?|index)",
)


def mentions_es(text: str) -> bool:
    lower = text.lower()
    return any(keyword in lower for keyword in _ES_KEYWORDS) or bool(
        re.search(r"(?<![a-z])es(?![a-z])", lower)
    )


def detect_mode(text: str) -> str:
    return "es_ops" if mentions_es(text) else "chat"


def is_es_indices_question(text: str) -> bool:
    lower = text.lower()
    if not mentions_es(text):
        return False
    return any(
        keyword in lower
        for keyword in (_KW_INDEX_LIST, _KW_INDEX, "indices", "index list", "list indices")
    )


def extract_index_pattern(text: str) -> str:
    stripped = text.strip()
    for pattern in _INDEX_PATTERN_REGEXES:
        match = re.search(pattern, stripped, flags=re.IGNORECASE)
        if not match:
            continue
        value = (match.group(1) or "").strip()
        if value and value.lower() not in {"es", "elasticsearch", "opensearch", "index", "indices"}:
            return value
    return "*"


def _looks_like_failure(result: str) -> bool:
    lower = result.lower()
    return any(
        keyword in lower
        for keyword in (
            _KW_FAILED,
            "failed",
            "error",
            "exception",
            "traceback",
            "connecterror",
            "timed out",
            "connection refused",
            "name or service not known",
            _KW_NOT_ENABLED,
        )
    )


async def get_es_quick_reply(text: str) -> str | None:
    if not is_es_indices_question(text):
        return None

    from agent.tools import call_mcp_tool, es_list_indices

    pattern = extract_index_pattern(text)
    direct_result = await es_list_indices.ainvoke({"pattern": pattern})
    if isinstance(direct_result, str) and not _looks_like_failure(direct_result):
        return direct_result

    fallback_result = await call_mcp_tool.ainvoke(
        {
            "mcp_name": "ES MCP",
            "action": "list_indices",
            "params": json.dumps({"pattern": pattern}, ensure_ascii=False),
        }
    )
    return str(fallback_result)
