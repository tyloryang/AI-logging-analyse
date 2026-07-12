"""Normalize model catalogs returned by OpenAI-compatible and Anthropic APIs."""

from __future__ import annotations


def model_discovery_url(provider: str, base_url: str = "") -> str:
    if provider == "anthropic":
        return "https://api.anthropic.com/v1/models"
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        raise ValueError("base_url is required for OpenAI-compatible discovery")
    return f"{normalized}/models"


def normalize_discovered_models(payload: object) -> list[dict[str, str]]:
    if isinstance(payload, dict):
        raw_items = payload.get("data") or payload.get("models") or []
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raw_items = []

    normalized: dict[str, dict[str, str]] = {}
    for item in raw_items if isinstance(raw_items, list) else []:
        if isinstance(item, str):
            model_id = item.strip()
            model_name = model_id
            model_type = "model"
            owned_by = ""
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("model") or item.get("name") or "").strip()
            model_name = str(item.get("display_name") or item.get("name") or model_id).strip()
            model_type = str(item.get("type") or item.get("object") or "model").strip()
            owned_by = str(item.get("owned_by") or item.get("provider") or "").strip()
        else:
            continue
        if not model_id:
            continue
        normalized[model_id] = {
            "id": model_id,
            "name": model_name or model_id,
            "type": model_type or "model",
            "owned_by": owned_by,
        }
    return sorted(normalized.values(), key=lambda model: model["id"].lower())
