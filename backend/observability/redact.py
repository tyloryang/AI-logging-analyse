"""脱敏中间件 —— LLM prompt / span attribute 入参前必经此函数。

规则覆盖：Bearer token、API key、PEM 私钥、中国手机号、邮箱、身份证号、密码字面量。
所有正则均经过 tests/test_redact.py 验证；新增规则务必补单测。
"""
from __future__ import annotations

import re
from typing import Any

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # 凭据类（顺序：先大段密钥块，再行内 token，再字段名后面的值）
    (re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----"), "<REDACTED_PEM>"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"), r"\1<REDACTED_TOKEN>"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*[\"']?)[A-Za-z0-9._\-]{16,}"), r"\1<REDACTED_KEY>"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*[\"']?)[^\s\"',;]{16,}"), r"\1<REDACTED_AUTH>"),
    (re.compile(r"(?i)(password\s*[:=]\s*[\"']?)[^\s\"',;]{6,}"), r"\1<REDACTED_PWD>"),
    (re.compile(r"(?i)(secret\s*[:=]\s*[\"']?)[A-Za-z0-9._\-]{8,}"), r"\1<REDACTED_SECRET>"),
    # PII（中国大陆常见）
    (re.compile(r"\b1[3-9]\d{9}\b"), "<REDACTED_PHONE>"),
    (re.compile(r"\b[\w.+\-]+@[\w\-]+\.[\w.\-]+\b"), "<REDACTED_EMAIL>"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "<REDACTED_IDCARD>"),
    (re.compile(r"\b\d{16,19}\b(?=\s|$|[,;])"), "<REDACTED_BANKCARD>"),
]


def redact(text: Any) -> str:
    """对字符串执行脱敏；非字符串入参原样 str() 后处理。空值直返。"""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return text
    for pat, repl in _PATTERNS:
        text = pat.sub(repl, text)
    return text


def redact_dict(payload: dict[str, Any], skip_keys: set[str] | None = None) -> dict[str, Any]:
    """递归脱敏字典。skip_keys 中的键名（不区分大小写）整值直接替换为 <REDACTED_FIELD>。"""
    sensitive = {"password", "api_key", "apikey", "token", "secret", "authorization"}
    if skip_keys:
        sensitive |= {k.lower() for k in skip_keys}

    def _walk(value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if str(k).lower() in sensitive and v not in (None, "", 0, False):
                    out[k] = "<REDACTED_FIELD>"
                else:
                    out[k] = _walk(v)
            return out
        if isinstance(value, list):
            return [_walk(item) for item in value]
        if isinstance(value, str):
            return redact(value)
        return value

    return _walk(payload)
