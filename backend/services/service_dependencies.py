"""Service dependency records used by structured RCA evidence collection."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from json_snapshot_store import read_json_file, write_json_file


_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "service_dependencies.json"
_SOURCE_PRIORITY = {
    "pod_runtime": 400,
    "pod_env": 400,
    "configmap": 400,
    "config_center": 300,
    "cmdb": 200,
    "code": 100,
    "code_config": 100,
}


def load_dependencies() -> list[dict[str, Any]]:
    data = read_json_file(_DATA_FILE, default=[])
    return [dict(item) for item in data] if isinstance(data, list) else []


def save_dependencies(records: list[dict[str, Any]]) -> None:
    write_json_file(_DATA_FILE, records, ensure_parent=True)


def upsert_dependency(record: dict[str, Any]) -> dict[str, Any]:
    item = dict(record or {})
    item["id"] = str(item.get("id") or f"dep_{int(time.time() * 1000)}")
    item["source"] = str(item.get("source") or "cmdb")
    records = load_dependencies()
    for index, existing in enumerate(records):
        if existing.get("id") == item["id"]:
            records[index] = item
            break
    else:
        records.append(item)
    save_dependencies(records)
    return item


def delete_dependency(dependency_id: str) -> bool:
    records = load_dependencies()
    remaining = [item for item in records if str(item.get("id")) != dependency_id]
    if len(remaining) == len(records):
        return False
    save_dependencies(remaining)
    return True


def _matches(value: Any, expected: str) -> bool:
    actual = str(value or "").strip()
    wanted = str(expected or "").strip()
    return not actual or not wanted or actual == wanted


def resolve_dependency(
    records: list[dict[str, Any]],
    *,
    cluster: str = "",
    namespace: str = "",
    service: str = "",
    dependency_type: str = "mysql",
) -> dict[str, Any]:
    """Resolve one dependency while retaining lower-priority conflicting records."""
    candidates = [
        dict(item)
        for item in records
        if str(item.get("dependency_type") or "").lower() == dependency_type.lower()
        and _matches(item.get("cluster"), cluster)
        and _matches(item.get("namespace"), namespace)
        and _matches(item.get("service"), service)
    ]
    candidates.sort(
        key=lambda item: (
            -_SOURCE_PRIORITY.get(str(item.get("source") or "cmdb").lower(), 0),
            str(item.get("id") or ""),
        )
    )
    if not candidates:
        return {
            "selected": None,
            "candidates": [],
            "conflicts": [],
            "confidence_penalty": 0,
        }

    selected = candidates[0]
    selected_target = str(selected.get("target") or selected.get("host") or "")
    conflicts = [
        item
        for item in candidates[1:]
        if str(item.get("target") or item.get("host") or "") != selected_target
    ]
    return {
        "selected": selected,
        "candidates": candidates,
        "conflicts": conflicts,
        "confidence_penalty": min(30, len(conflicts) * 10),
    }


def resolve_saved_dependency(**identity: str) -> dict[str, Any]:
    return resolve_dependency(load_dependencies(), **identity)
