"""Shared fail-closed authentication helpers for inbound webhooks."""

from __future__ import annotations

import hmac
import os

from fastapi import HTTPException


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def require_ingest_token(
    *,
    token_env: str,
    direct_token: str | None,
    authorization: str | None,
    allow_unauthenticated_env: str,
) -> None:
    expected = os.getenv(token_env, "").strip()
    if not expected:
        if env_flag(allow_unauthenticated_env):
            return
        raise HTTPException(status_code=503, detail=f"{token_env} is not configured")

    provided = (direct_token or "").strip()
    bearer = (authorization or "").strip()
    bearer_token = bearer[7:].strip() if bearer.lower().startswith("bearer ") else ""
    if (provided and hmac.compare_digest(provided, expected)) or (
        bearer_token and hmac.compare_digest(bearer_token, expected)
    ):
        return
    raise HTTPException(status_code=401, detail="invalid ingest token")
