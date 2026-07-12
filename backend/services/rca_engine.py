"""Structured RCA engine for alert, inspection, anomaly, and manual triggers."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from json_snapshot_store import read_json_file, write_json_file

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_DIR = _BACKEND_DIR.parent

_RCA_FILE = _BACKEND_DIR / "data" / "rca_results.json"
_EXPERT_CASE_FILE = _BACKEND_DIR / "data" / "rca_expert_cases.json"
_FEEDBACK_FILE = _BACKEND_DIR / "data" / "rca_feedback.json"

_MAX_LOGS = 300
_CTX_TIMEOUT = 10.0
_MAX_RESULTS = 300
_MAX_CASES = 500
_MAX_LOG_CONTEXT_ANCHORS = 3

_STATUS_RUNNING = {"pending", "running"}
_STATUS_FINAL = {"awaiting_confirmation", "confirmed", "needs_review", "error"}

_CATEGORY_META: dict[str, dict[str, str]] = {
    "application_bug": {
        "title": "应用自身异常或代码缺陷",
        "summary": "异常更像是服务内部逻辑、异常处理或代码级问题触发。",
    },
    "dependency_failure": {
        "title": "下游依赖或网络链路异常",
        "summary": "错误特征更接近数据库、缓存、消息队列、DNS 或网络超时。",
    },
    "resource_bottleneck": {
        "title": "资源瓶颈或容量不足",
        "summary": "CPU、内存、磁盘、P99 或吞吐异常表明实例已接近容量边界。",
    },
    "platform_host_issue": {
        "title": "主机、节点或平台层异常",
        "summary": "巡检、节点状态或基础设施指标显示平台层存在异常。",
    },
    "change_regression": {
        "title": "近期变更引入回归",
        "summary": "近期发布、配置变更或代码提交与本次异常时间上高度相关。",
    },
}

_DEFAULT_FEEDBACK = {
    "weights": {
        "application_bug": 1.0,
        "dependency_failure": 1.0,
        "resource_bottleneck": 1.0,
        "platform_host_issue": 1.0,
        "change_regression": 1.0,
    },
    "stats": {
        "application_bug": {"confirmed": 0, "rejected": 0},
        "dependency_failure": {"confirmed": 0, "rejected": 0},
        "resource_bottleneck": {"confirmed": 0, "rejected": 0},
        "platform_host_issue": {"confirmed": 0, "rejected": 0},
        "change_regression": {"confirmed": 0, "rejected": 0},
    },
    "updated_at": "",
}

_WORD_RE = re.compile(r"[a-zA-Z0-9_.:/-]{2,}|[\u4e00-\u9fff]{2,}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _text_or_empty(value: Any) -> str:
    return "" if value is None else str(value)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _deep_merge(base: dict, patch: dict) -> dict:
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in _WORD_RE.finditer(text or "")}


def _compact_text(text: str, limit: int = 160) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(raw) <= limit:
        return raw
    return raw[: limit - 3] + "..."


def _normalize_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _load_results() -> list[dict]:
    data = read_json_file(_RCA_FILE, default=[])
    if not isinstance(data, list):
        return []
    return [_normalize_record(item) for item in data if isinstance(item, dict)]


def _save_results(results: list[dict]) -> None:
    write_json_file(_RCA_FILE, results[-_MAX_RESULTS:], ensure_parent=True)


def _load_expert_cases() -> list[dict]:
    data = read_json_file(_EXPERT_CASE_FILE, default=[])
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _save_expert_cases(cases: list[dict]) -> None:
    write_json_file(_EXPERT_CASE_FILE, cases[-_MAX_CASES:], ensure_parent=True)


def _load_feedback() -> dict:
    data = read_json_file(_FEEDBACK_FILE, default=deepcopy(_DEFAULT_FEEDBACK))
    if not isinstance(data, dict):
        data = deepcopy(_DEFAULT_FEEDBACK)

    merged = deepcopy(_DEFAULT_FEEDBACK)
    _deep_merge(merged, data)
    if not merged.get("updated_at"):
        merged["updated_at"] = _now_iso()
    return merged


def _save_feedback(profile: dict) -> None:
    payload = deepcopy(_DEFAULT_FEEDBACK)
    _deep_merge(payload, profile or {})
    payload["updated_at"] = _now_iso()
    write_json_file(_FEEDBACK_FILE, payload, ensure_parent=True)


def _timeline(stage: str, title: str, detail: str = "", status: str = "done") -> dict:
    return {
        "stage": stage,
        "title": title,
        "detail": detail,
        "status": status,
        "at": _now_iso(),
    }


def _normalize_hypothesis(item: dict, index: int) -> dict:
    category = str(item.get("category") or "application_bug")
    meta = _CATEGORY_META.get(category, _CATEGORY_META["application_bug"])
    score = int(round(_safe_float(item.get("score"), 0)))
    confidence = str(item.get("confidence") or ("high" if score >= 80 else "medium" if score >= 55 else "low"))
    return {
        "id": str(item.get("id") or f"hyp_{index + 1}"),
        "rank": int(item.get("rank") or index + 1),
        "agent_name": str(item.get("agent_name") or f"Validator-{index + 1}"),
        "category": category,
        "title": str(item.get("title") or meta["title"]),
        "description": str(item.get("description") or meta["summary"]),
        "score": score,
        "confidence": confidence,
        "validation_status": str(
            item.get("validation_status")
            or ("supported" if score >= 70 else "possible" if score >= 45 else "weak")
        ),
        "validation_summary": str(item.get("validation_summary") or ""),
        "evidence": [str(v) for v in _normalize_list(item.get("evidence")) if str(v).strip()],
        "commands": [str(v) for v in _normalize_list(item.get("commands")) if str(v).strip()],
    }


def _build_result_markdown(record: dict) -> str:
    hypotheses = [_normalize_hypothesis(item, idx) for idx, item in enumerate(record.get("hypotheses", []))]
    top = hypotheses[0] if hypotheses else None
    human = record.get("human_confirmation", {}) or {}
    context = record.get("context", {}) or {}

    lines: list[str] = []
    lines.append("## 根因摘要")
    lines.append(record.get("final_summary") or (top["title"] if top else "暂无结论"))
    lines.append("")
    lines.append("## 触发源")
    lines.append(f"- 来源类型：{record.get('source_type', 'manual')}")
    lines.append(f"- 服务：{record.get('service') or 'global'}")
    if record.get("alert_name"):
        lines.append(f"- 告警/事件：{record['alert_name']}")
    if record.get("source_name"):
        lines.append(f"- 来源对象：{record['source_name']}")
    lines.append(f"- 分析窗口：{record.get('context_hours', 1)}h")

    lines.append("")
    lines.append("## 假设验证")
    if not hypotheses:
        lines.append("- 暂未产出结构化假设")
    for item in hypotheses:
        lines.append(f"### {item['rank']}. {item['title']}（{item['score']}分）")
        lines.append(f"- 验证结论：{item['validation_summary'] or item['description']}")
        for evidence in item.get("evidence", [])[:4]:
            lines.append(f"- 证据：{evidence}")
        for command in item.get("commands", [])[:3]:
            lines.append(f"- 建议命令：`{command}`")

    metric_evidence = context.get("metric_evidence") if isinstance(context, dict) else None
    if isinstance(metric_evidence, dict) and metric_evidence.get("pack"):
        pack = metric_evidence["pack"]
        summary = pack.get("summary", {})
        lines.append("")
        lines.append("## 指标证据链")
        lines.append(
            f"- 查询计划：{summary.get('planned', 0)} 条（预算 {summary.get('budget', 8)} 条），"
            f"执行 {summary.get('executed', 0)} 条，窗口 {summary.get('window_minutes', 60)} 分钟"
        )
        for ev in pack.get("evidence", []):
            if ev["status"] == "no_data":
                lines.append(f"- ❓ {ev['name']}：{ev['detail'] or '无数据'}（证据缺失，不代表正常）")
            else:
                mark = "⚠️" if ev["status"] == "abnormal" else "✅"
                trend_text = {"up": "↑", "down": "↓", "flat": "→"}.get(ev["trend"], "")
                lines.append(
                    f"- {mark} {ev['name']}：当前 {ev['latest']}{ev['unit']} {trend_text}"
                    f"（基线 {ev['baseline']}{ev['unit']}，峰值 {ev['peak']}{ev['unit']}"
                    + (f"，{ev['detail']}" if ev["detail"] else "") + "）"
                )
        for gap in pack.get("gaps", [])[:4]:
            lines.append(f"- 缺口：{gap}")

    lines.append("")
    lines.append("## 关键上下文")
    for key in ("kubernetes", "slowlog", "loki", "prometheus", "skywalking", "cmdb", "changes", "codebase", "inspection", "similar_cases", "metric_evidence"):
        section = context.get(key) if isinstance(context, dict) else None
        if not isinstance(section, dict):
            continue
        title = section.get("title") or key
        summary = section.get("summary") or ""
        if summary:
            lines.append(f"- {title}：{summary}")

    lines.append("")
    lines.append("## 人工确认")
    if human.get("status") == "confirmed":
        lines.append(f"- 已确认：{human.get('chosen_title') or human.get('chosen_hypothesis_id') or '已确认'}")
        if human.get("note"):
            lines.append(f"- 备注：{human['note']}")
    elif human.get("status") == "needs_review":
        lines.append("- 当前状态：待人工复核")
        if human.get("note"):
            lines.append(f"- 备注：{human['note']}")
    else:
        lines.append("- 当前状态：待人工确认")

    return "\n".join(lines).strip()


def _normalize_record(record: dict) -> dict:
    item = dict(record or {})
    item["id"] = str(item.get("id") or f"rca_{int(time.time())}")
    item["created_at"] = item.get("created_at") or _now_iso()
    item["updated_at"] = item.get("updated_at") or item["created_at"]
    item["service"] = str(item.get("service") or "global")
    item["alert_name"] = str(item.get("alert_name") or "")
    item["source_type"] = str(item.get("source_type") or ("alert" if item.get("alert_group_id") else "manual"))
    item["source_id"] = str(item.get("source_id") or item.get("alert_group_id") or "")
    item["source_name"] = str(item.get("source_name") or "")
    item["status"] = str(item.get("status") or ("awaiting_confirmation" if item.get("result") else "pending"))
    item["context_hours"] = _safe_float(item.get("context_hours"), 1.0)
    item["extra_context"] = str(item.get("extra_context") or "")
    item["context"] = item.get("context") if isinstance(item.get("context"), dict) else {}
    item["phase"] = str(item.get("phase") or ("analysis_ready" if item.get("hypotheses") else "pending"))
    item["collector_states"] = item.get("collector_states") if isinstance(item.get("collector_states"), dict) else {}
    item["sla"] = item.get("sla") if isinstance(item.get("sla"), dict) else {}
    item["source_labels"] = item.get("source_labels") if isinstance(item.get("source_labels"), dict) else {}
    item["timeline"] = [entry for entry in _normalize_list(item.get("timeline")) if isinstance(entry, dict)]
    item["hypotheses"] = [_normalize_hypothesis(hyp, idx) for idx, hyp in enumerate(_normalize_list(item.get("hypotheses")))]
    item["feedback_snapshot"] = item.get("feedback_snapshot") if isinstance(item.get("feedback_snapshot"), dict) else {}
    item["expert_matches"] = [entry for entry in _normalize_list(item.get("expert_matches")) if isinstance(entry, dict)]
    human = item.get("human_confirmation") if isinstance(item.get("human_confirmation"), dict) else {}
    item["human_confirmation"] = {
        "status": str(human.get("status") or "pending"),
        "chosen_hypothesis_id": str(human.get("chosen_hypothesis_id") or ""),
        "chosen_title": str(human.get("chosen_title") or ""),
        "note": str(human.get("note") or ""),
        "confirmed_by": str(human.get("confirmed_by") or ""),
        "confirmed_at": str(human.get("confirmed_at") or ""),
        "feedback_applied": bool(human.get("feedback_applied")),
    }
    if not item.get("final_summary"):
        top = item["hypotheses"][0] if item["hypotheses"] else None
        item["final_summary"] = top["validation_summary"] if top else ""
    if not item.get("result") or item["hypotheses"]:
        item["result"] = _build_result_markdown(item)
    return item


def list_rca(limit: int = 50) -> list[dict]:
    return list(reversed(_load_results()))[:limit]


def get_rca(rca_id: str) -> dict | None:
    for item in reversed(_load_results()):
        if item.get("id") == rca_id:
            return item
    return None


def save_rca(record: dict) -> str:
    """Persist one RCA record and return its id."""
    normalized = _normalize_record(record)
    results = _load_results()
    for idx, item in enumerate(results):
        if item.get("id") == normalized["id"]:
            results[idx] = normalized
            _save_results(results)
            return normalized["id"]
    results.append(normalized)
    _save_results(results)
    return normalized["id"]


def update_rca(rca_id: str, patch: dict) -> dict | None:
    results = _load_results()
    for idx, item in enumerate(results):
        if item.get("id") != rca_id:
            continue
        updated = deepcopy(item)
        _deep_merge(updated, patch or {})
        updated["updated_at"] = _now_iso()
        updated = _normalize_record(updated)
        results[idx] = updated
        _save_results(results)
        return updated
    return None


def create_pending_rca(
    *,
    service: str | None,
    alert_name: str = "",
    alert_group_id: str | None = None,
    hours: float = 1.0,
    extra_context: str = "",
    source_type: str = "manual",
    source_id: str = "",
    source_name: str = "",
    source_labels: dict[str, str] | None = None,
) -> dict:
    alert_name = _text_or_empty(alert_name)
    extra_context = _text_or_empty(extra_context)
    source_type = _text_or_empty(source_type) or "manual"
    source_id = _text_or_empty(source_id)
    source_name = _text_or_empty(source_name)
    rca_id = f"rca_{int(time.time() * 1000)}"
    now = _now_iso()
    record = {
        "id": rca_id,
        "created_at": now,
        "updated_at": now,
        "service": service or "global",
        "alert_name": alert_name,
        "alert_group_id": alert_group_id,
        "source_type": source_type,
        "source_id": source_id or alert_group_id or "",
        "source_name": source_name,
        "source_labels": source_labels or {},
        "status": "pending",
        "phase": "pending",
        "context_hours": hours,
        "extra_context": extra_context,
        "context": {},
        "collector_states": {},
        "sla": {
            "alert_started_at": (source_labels or {}).get("startsAt") or (source_labels or {}).get("alert_started_at") or "",
            "facts_deadline_ms": 5000,
            "analysis_deadline_ms": 15000,
        },
        "hypotheses": [],
        "expert_matches": [],
        "feedback_snapshot": _load_feedback(),
        "human_confirmation": {"status": "pending"},
        "timeline": [
            _timeline(
                "triggered",
                "收到 RCA 触发",
                f"{source_type} -> {service or 'global'} / {alert_name or 'manual'}",
            )
        ],
        "final_summary": "正在采集上下文并验证根因假设。",
        "result": "## 根因摘要\n正在采集上下文并验证根因假设。",
    }
    save_rca(record)
    return get_rca(rca_id) or _normalize_record(record)


def list_expert_cases(limit: int = 100) -> list[dict]:
    cases = list(reversed(_load_expert_cases()))
    return cases[:limit]


def get_feedback_profile() -> dict:
    profile = _load_feedback()
    categories: list[dict] = []
    for key, meta in _CATEGORY_META.items():
        weight = _safe_float(profile.get("weights", {}).get(key), 1.0)
        stats = profile.get("stats", {}).get(key, {}) or {}
        confirmed = int(stats.get("confirmed", 0) or 0)
        rejected = int(stats.get("rejected", 0) or 0)
        total = confirmed + rejected
        accuracy = round((confirmed / total) * 100, 1) if total else None
        categories.append(
            {
                "key": key,
                "title": meta["title"],
                "weight": round(weight, 3),
                "confirmed": confirmed,
                "rejected": rejected,
                "accuracy": accuracy,
            }
        )
    categories.sort(key=lambda item: item["weight"], reverse=True)
    return {
        "updated_at": profile.get("updated_at"),
        "categories": categories,
        "weights": profile.get("weights", {}),
        "stats": profile.get("stats", {}),
    }


def _find_hypothesis(record: dict, hypothesis_id: str) -> dict | None:
    for item in record.get("hypotheses", []) or []:
        if item.get("id") == hypothesis_id:
            return item
    return None


def confirm_rca(
    rca_id: str,
    *,
    hypothesis_id: str,
    note: str = "",
    confirmed_by: str = "",
    decision: str = "confirmed",
    resolve_alert: bool = False,
) -> dict:
    record = get_rca(rca_id)
    if not record:
        raise ValueError("RCA record not found")

    human = record.get("human_confirmation", {}) or {}
    if human.get("feedback_applied"):
        raise ValueError("Feedback already applied for this RCA record")

    chosen = _find_hypothesis(record, hypothesis_id)
    if not chosen:
        raise ValueError("Hypothesis not found")

    now = _now_iso()
    human_update = {
        "status": decision,
        "chosen_hypothesis_id": chosen["id"],
        "chosen_title": chosen["title"],
        "note": note,
        "confirmed_by": confirmed_by or "manual",
        "confirmed_at": now,
        "feedback_applied": decision == "confirmed",
    }

    patch = {
        "status": "confirmed" if decision == "confirmed" else "needs_review",
        "human_confirmation": human_update,
        "timeline": record.get("timeline", []) + [
            _timeline(
                "human_confirmation",
                "人工确认完成" if decision == "confirmed" else "人工标记待复核",
                note or chosen["title"],
            )
        ],
    }

    updated = update_rca(rca_id, patch)
    if not updated:
        raise ValueError("RCA record update failed")

    if decision == "confirmed":
        case = _create_expert_case(updated, chosen)
        _save_expert_case(case)
        _apply_feedback(updated, chosen["category"])
        updated = update_rca(
            rca_id,
            {
                "expert_case_id": case["id"],
                "human_confirmation": {"feedback_applied": True},
                "timeline": updated.get("timeline", []) + [
                    _timeline("expert_case", "案例已入专家库", case["title"])
                ],
            },
        ) or updated

        if resolve_alert and updated.get("alert_group_id"):
            try:
                from services.alert_dedup import update_group_status

                update_group_status(updated["alert_group_id"], "resolved", rca_id=updated["id"])
            except Exception as exc:
                logger.warning("[rca] failed to resolve alert after confirmation: %s", exc)

    return get_rca(rca_id) or updated


def _save_expert_case(case: dict) -> None:
    cases = _load_expert_cases()
    cases.append(case)
    _save_expert_cases(cases)


def _create_expert_case(record: dict, chosen: dict) -> dict:
    context = record.get("context", {}) or {}
    similar_text = []
    for section_key in ("loki", "prometheus", "skywalking", "inspection"):
        section = context.get(section_key) if isinstance(context, dict) else None
        if not isinstance(section, dict):
            continue
        summary = section.get("summary")
        if summary:
            similar_text.append(summary)

    return {
        "id": f"case_{int(time.time() * 1000)}",
        "created_at": _now_iso(),
        "source_run_id": record.get("id"),
        "service": record.get("service"),
        "source_type": record.get("source_type"),
        "title": f"{record.get('service')} / {chosen['title']}",
        "alert_name": record.get("alert_name"),
        "category": chosen.get("category"),
        "root_cause": chosen.get("title"),
        "summary": chosen.get("validation_summary") or record.get("final_summary", ""),
        "resolution": "；".join(chosen.get("commands", [])[:2]),
        "note": (record.get("human_confirmation", {}) or {}).get("note", ""),
        "keywords": sorted(
            _tokenize(
                " ".join(
                    [
                        str(record.get("service") or ""),
                        str(record.get("alert_name") or ""),
                        str(chosen.get("title") or ""),
                        str(chosen.get("validation_summary") or ""),
                        " ".join(similar_text),
                    ]
                )
            )
        )[:60],
        "commands": chosen.get("commands", [])[:5],
    }


def _apply_feedback(record: dict, chosen_category: str) -> None:
    profile = _load_feedback()
    weights = profile.setdefault("weights", {})
    stats = profile.setdefault("stats", {})

    for key in _CATEGORY_META:
        weights.setdefault(key, 1.0)
        stats.setdefault(key, {"confirmed": 0, "rejected": 0})

    for item in record.get("hypotheses", []) or []:
        category = str(item.get("category") or "")
        if category not in weights:
            continue
        if category == chosen_category:
            stats[category]["confirmed"] = int(stats[category].get("confirmed", 0) or 0) + 1
            weights[category] = round(_clamp(_safe_float(weights[category]) + 0.12, 0.6, 2.5), 3)
        else:
            stats[category]["rejected"] = int(stats[category].get("rejected", 0) or 0) + 1
            weights[category] = round(_clamp(_safe_float(weights[category]) - 0.03, 0.6, 2.5), 3)

    _save_feedback(profile)


def _build_matchers(labels: dict[str, str], *preferred_keys: str) -> str:
    matchers = []
    for key in preferred_keys:
        value = str(labels.get(key) or "").strip()
        if value:
            matchers.append(f'{key}="{value}"')
    return "{" + ",".join(matchers) + "}" if matchers else ""


async def _collect_loki(service: str | None, hours: float, source_labels: dict[str, str]) -> dict:
    try:
        import state

        logs = await asyncio.wait_for(
            state.loki.query_error_logs(service=service, hours=hours, limit=_MAX_LOGS),
            timeout=_CTX_TIMEOUT,
        )
        if not logs:
            return {"title": "日志", "summary": "最近窗口内未发现 ERROR 日志。", "items": [], "raw_count": 0}

        freq: dict[str, int] = {}
        samples: dict[str, str] = {}
        for entry in logs:
            line = str(entry.get("line") or entry.get("message") or "").strip()
            if not line:
                continue
            key = _compact_text(line, 180)
            freq[key] = freq.get(key, 0) + 1
            samples.setdefault(key, key)

        top = sorted(freq.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
        items = [f"[x{count}] {samples[text]}" for text, count in top]
        context_items = await _collect_log_context_items(state.loki, logs, service=service, hours=hours)
        summary = f"最近 {hours}h 共抓取 {len(logs)} 条错误日志，Top 模式已去重展示。"
        if context_items:
            summary += f" 已补充 {len(context_items)} 段错误日志前后文。"
        if service:
            summary = f"{service} 服务，" + summary
        if source_labels.get("namespace"):
            summary += f" namespace={source_labels['namespace']}。"
        return {
            "title": "日志",
            "summary": summary,
            "items": items + context_items[:4],
            "context_items": context_items,
            "raw_count": len(logs),
        }
    except asyncio.TimeoutError:
        return {"title": "日志", "summary": "Loki 查询超时。", "items": []}
    except Exception as exc:
        return {"title": "日志", "summary": f"Loki 查询失败: {exc}", "items": []}


def _context_label_filters(labels: dict) -> dict[str, str]:
    allowed = {
        "app", "service", "job", "namespace", "pod", "pod_name", "container",
        "container_name", "instance", "stream", "env", "cluster",
    }
    result: dict[str, str] = {}
    for key, value in (labels or {}).items():
        if key in allowed and value not in (None, ""):
            result[str(key)] = str(value)
    return result


async def _collect_log_context_items(loki, logs: list[dict], *, service: str | None, hours: float) -> list[str]:
    async def _one(entry: dict) -> str:
        try:
            timestamp_ns = int(entry.get("timestamp_ns") or 0)
            if timestamp_ns <= 0:
                return ""
            labels = entry.get("labels", {}) if isinstance(entry.get("labels"), dict) else {}
            line = str(entry.get("line") or entry.get("message") or "")
            context = await asyncio.wait_for(
                loki.query_log_context(
                    timestamp_ns=timestamp_ns,
                    service=service or labels.get("app") or labels.get("service") or labels.get("job") or None,
                    line_prefix=line[:120] or None,
                    before=3,
                    after=3,
                    hours=hours,
                    label_filters=_context_label_filters(labels),
                ),
                timeout=_CTX_TIMEOUT,
            )
            rows = context.get("data", []) if isinstance(context, dict) else []
            anchor_index = int(context.get("anchor_index", 0) or 0) if isinstance(context, dict) else 0
            rendered: list[str] = []
            for idx, row in enumerate(rows[:7]):
                marker = ">" if idx == anchor_index else " "
                ts = str(row.get("timestamp", ""))[:19]
                row_labels = row.get("labels", {}) if isinstance(row.get("labels"), dict) else {}
                svc = row_labels.get("app") or row_labels.get("service") or row_labels.get("job") or service or "unknown"
                rendered.append(f"{marker} [{ts}][{svc}] {str(row.get('line') or '')[:220]}")
            return "日志上下文:\n" + "\n".join(rendered) if rendered else ""
        except Exception:
            return ""

    tasks = [_one(entry) for entry in logs[:_MAX_LOG_CONTEXT_ANCHORS]]
    if not tasks:
        return []
    results = await asyncio.gather(*tasks)
    return [item for item in results if item]


async def _collect_prometheus(service: str | None, source_labels: dict[str, str]) -> dict:
    try:
        import state

        labels = dict(source_labels or {})
        if service and not labels.get("service"):
            labels["service"] = service

        matcher_parts = []
        for key in ("service", "job"):
            value = str(labels.get(key) or "").strip()
            if value:
                matcher_parts.append(f'{key}="{value}"')
        http_all = "{" + ",".join(matcher_parts) + "}" if matcher_parts else ""
        error_parts = list(matcher_parts)
        error_parts.append('status=~"5.."')
        http_5xx = "{" + ",".join(error_parts) + "}"

        queries = [
            ("cpu_usage_pct", "CPU 使用率", '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100', "%"),
            ("memory_usage_pct", "内存使用率", '100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100', "%"),
            (
                "http_5xx_ratio_pct",
                "HTTP 5xx 比例",
                f'sum(rate(http_requests_total{http_5xx}[5m])) / clamp_min(sum(rate(http_requests_total{http_all}[5m])), 0.0001) * 100',
                "%",
            ),
            (
                "p99_latency_ms",
                "P99 延迟",
                'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
                "ms",
            ),
        ]

        metrics: list[dict] = []
        for key, label, promql, unit in queries:
            try:
                result = await asyncio.wait_for(state.prom.query(promql), timeout=_CTX_TIMEOUT)
                if not result:
                    continue
                value = _safe_float(result[0].get("value", [0, 0])[1], 0.0)
                metrics.append({"key": key, "label": label, "value": round(value, 2), "unit": unit})
            except Exception:
                continue

        if not metrics:
            return {"title": "指标", "summary": "未抓取到 Prometheus 指标。", "items": [], "metrics": []}

        parts = [f"{item['label']}={item['value']}{item['unit']}" for item in metrics]
        return {
            "title": "指标",
            "summary": "；".join(parts),
            "items": parts,
            "metrics": metrics,
        }
    except Exception as exc:
        return {"title": "指标", "summary": f"Prometheus 查询失败: {exc}", "items": [], "metrics": []}


async def _collect_skywalking(service: str | None) -> dict:
    try:
        from skywalking_client import sw_client

        services = await asyncio.wait_for(sw_client.get_services(hours=1), timeout=_CTX_TIMEOUT)
        matched = [item for item in services if not service or service.lower() in str(item.get("name", "")).lower()]
        recent = await asyncio.wait_for(sw_client.get_traces(hours=1, error_only=True, page=1, page_size=8), timeout=_CTX_TIMEOUT)
        traces = recent.get("traces", []) if isinstance(recent, dict) else []

        items: list[str] = []
        for trace in traces[:5]:
            endpoint = ", ".join(trace.get("endpointNames", [])[:2]) or trace.get("serviceCode") or "-"
            items.append(f"{endpoint} / {trace.get('duration', 0)}ms / error={trace.get('isError', False)}")

        summary = f"最近 1h 发现 {len(traces)} 条异常 Trace，匹配服务 {len(matched)} 个。"
        if matched:
            summary += " 服务样本: " + ", ".join(str(item.get("name", "")) for item in matched[:4])
        return {
            "title": "Trace",
            "summary": summary,
            "items": items,
            "matched_services": [item.get("name", "") for item in matched[:10]],
            "error_trace_count": len(traces),
        }
    except Exception as exc:
        return {"title": "Trace", "summary": f"SkyWalking 查询失败: {exc}", "items": [], "error_trace_count": 0}


async def _collect_cmdb(service: str | None) -> dict:
    try:
        import state

        hosts = await asyncio.wait_for(state.prom.discover_hosts(), timeout=_CTX_TIMEOUT)
        if not hosts:
            return {"title": "CMDB", "summary": "未发现主机信息。", "items": []}
        items = [f"{host.get('instance')} ({host.get('state', '?')})" for host in hosts[:8]]
        summary = f"共发现 {len(hosts)} 台主机，展示前 {len(items)} 台。"
        if service:
            summary = f"{service} 关联主机视角: " + summary
        return {"title": "CMDB", "summary": summary, "items": items}
    except Exception as exc:
        return {"title": "CMDB", "summary": f"CMDB 查询失败: {exc}", "items": []}


def _run_git_command(args: list[str]) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "-c", f"safe.directory={_REPO_DIR}", *args],
            cwd=_REPO_DIR,
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        if completed.returncode != 0:
            return []
        stdout = _text_or_empty(getattr(completed, "stdout", None))
        return [line.strip() for line in stdout.splitlines() if line.strip()]
    except Exception:
        return []


def _collect_change_context(service: str | None) -> dict:
    grep_value = service or ""
    lines = _run_git_command(["log", "--oneline", "-n", "8"])
    if grep_value:
        service_lines = _run_git_command(["log", "--oneline", "-n", "5", "--grep", grep_value])
        if service_lines:
            lines = service_lines + [line for line in lines if line not in service_lines]
    if not lines:
        return {"title": "变更记录", "summary": "未获取到最近代码提交记录。", "items": []}
    return {
        "title": "变更记录",
        "summary": f"最近发现 {len(lines[:8])} 条代码变更记录。",
        "items": lines[:8],
    }


def _extract_code_terms(service: str | None, signal_text: str = "") -> list[str]:
    terms: list[str] = []
    if service:
        terms.append(service)
        normalized = service.replace("-", "_")
        if normalized != service:
            terms.append(normalized)
        compact = service.replace("-", "").replace("_", "")
        if compact != service and len(compact) >= 4:
            terms.append(compact)

    for match in re.findall(r"\b[A-Z][A-Za-z0-9_]*(?:Exception|Error)\b", signal_text or ""):
        terms.append(match)
    for match in re.findall(r"/[A-Za-z0-9_./{}:-]{3,}", signal_text or ""):
        if not match.startswith("//"):
            terms.append(match[:80])

    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        value = str(term or "").strip()
        if len(value) < 4:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if len(result) >= 6:
            break
    return result


def _rg_code_hits(terms: list[str]) -> list[str]:
    if not terms or not shutil.which("rg"):
        return []

    search_paths = [name for name in ("backend", "frontend", "docs") if (_REPO_DIR / name).exists()]
    if not search_paths:
        return []

    hits: list[str] = []
    for term in terms[:5]:
        try:
            completed = subprocess.run(
                [
                    "rg", "-n", "--fixed-strings",
                    "--glob", "!frontend/dist/**",
                    "--glob", "!node_modules/**",
                    "--glob", "!backend/data/**",
                    "--glob", "!*.map",
                    "--", term, *search_paths,
                ],
                cwd=_REPO_DIR,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            continue
        stdout = _text_or_empty(getattr(completed, "stdout", None))
        for line in stdout.splitlines()[:4]:
            line = line.strip()
            if line and line not in hits:
                hits.append(line[:260])
            if len(hits) >= 12:
                return hits
    return hits


def _collect_code_context(service: str | None, signal_text: str = "") -> dict:
    terms = _extract_code_terms(service, signal_text)
    source_hits = _rg_code_hits(terms)
    if source_hits:
        return {
            "title": "代码库",
            "summary": f"按服务名/异常类/接口路径命中 {len(source_hits)} 条源码线索。",
            "items": source_hits,
            "search_terms": terms,
        }

    if not service:
        return {"title": "代码库", "summary": "未指定服务，跳过代码路径聚焦。", "items": [], "search_terms": terms}

    needle = service.lower()
    hits: list[str] = []
    for base in (_REPO_DIR / "backend", _REPO_DIR / "frontend", _REPO_DIR / "docs"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if len(hits) >= 10:
                break
            if not path.is_file():
                continue
            name = str(path.relative_to(_REPO_DIR)).replace("\\", "/")
            if needle in name.lower():
                hits.append(name)
        if len(hits) >= 10:
            break

    if not hits:
        return {"title": "代码库", "summary": f"未在仓库中发现与 {service} 直接匹配的路径。", "items": [], "search_terms": terms}
    return {
        "title": "代码库",
        "summary": f"代码库中命中 {len(hits)} 个与服务名相关的路径。",
        "items": hits,
        "search_terms": terms,
    }


def _summarize_inspection_results(results: list[dict], summary: dict) -> dict:
    abnormal = [item for item in results if item.get("overall") != "normal"]
    items: list[str] = []
    for item in abnormal[:8]:
        checks = [check for check in item.get("checks", []) if check.get("status") != "normal"]
        check_text = "；".join(f"{check.get('item')}={check.get('value')}" for check in checks[:3]) or "无详细检查项"
        items.append(f"{item.get('hostname') or item.get('ip')} [{item.get('overall')}] {check_text}")
    return {
        "title": "巡检结果",
        "summary": f"巡检覆盖 {summary.get('total', len(results))} 台主机，严重 {summary.get('critical', 0)} 台，警告 {summary.get('warning', 0)} 台。",
        "items": items,
        "critical_count": int(summary.get("critical", 0) or 0),
        "warning_count": int(summary.get("warning", 0) or 0),
    }


def _match_similar_cases(
    *,
    service: str | None,
    alert_name: str,
    extra_context: str,
    context_sections: dict[str, dict],
    limit: int = 3,
) -> list[dict]:
    query_text = " ".join(
        [
            service or "",
            alert_name or "",
            extra_context or "",
            str(context_sections.get("loki", {}).get("summary", "")),
            str(context_sections.get("inspection", {}).get("summary", "")),
        ]
    )
    tokens = _tokenize(query_text)
    if not tokens:
        return []

    matches: list[dict] = []
    for case in _load_expert_cases():
        case_tokens = set(case.get("keywords") or [])
        overlap = len(tokens & case_tokens)
        if service and case.get("service") == service:
            overlap += 2
        if alert_name and alert_name.lower() in str(case.get("alert_name") or "").lower():
            overlap += 2
        if overlap <= 0:
            continue
        matches.append(
            {
                "id": case.get("id"),
                "title": case.get("title"),
                "service": case.get("service"),
                "category": case.get("category"),
                "root_cause": case.get("root_cause"),
                "resolution": case.get("resolution"),
                "created_at": case.get("created_at"),
                "score": overlap,
            }
        )

    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[:limit]


async def _collect_metric_evidence(
    service: str | None,
    labels: dict[str, str],
    hours: float,
) -> dict:
    """指标证据包（services.evidence）：模板化计划 + 预算 + 压缩 + 缺口。

    section 形状与其他上下文一致（title/summary/items），并携带原始 pack
    供前端和 markdown 渲染证据链。失败返回空 dict（不阻塞 RCA）。
    """
    try:
        from services.evidence import build_metric_evidence, evidence_to_text

        pack = await asyncio.wait_for(
            build_metric_evidence(
                service=service if service and service != "global" else None,
                instance=labels.get("instance") or labels.get("node") or None,
                hostname=labels.get("hostname") or labels.get("host") or None,
                pod=labels.get("pod") or None,
                namespace=labels.get("namespace") or None,
                window_minutes=max(15, min(int(hours * 60), 24 * 60)),
            ),
            timeout=30,
        )
        summary = pack.get("summary", {})
        items = []
        for ev in pack.get("evidence", []):
            if ev["status"] == "abnormal":
                items.append(f"[异常] {ev['name']}: 当前 {ev['latest']}{ev['unit']}，"
                             f"基线 {ev['baseline']}{ev['unit']}，{ev['detail']}")
            elif ev["status"] == "normal":
                items.append(f"[正常] {ev['name']}: {ev['latest']}{ev['unit']}（可作反证）")
        items += [f"[缺口] {gap}" for gap in pack.get("gaps", [])[:4]]
        return {
            "title": "指标证据链",
            "summary": (f"计划 {summary.get('planned', 0)} 条 / 执行 {summary.get('executed', 0)} 条，"
                        f"异常 {summary.get('abnormal', 0)} 条，缺失 {summary.get('missing', 0)} 条。"),
            "items": items[:10],
            "pack": pack,
            "prompt_text": evidence_to_text(pack),
        }
    except Exception as exc:
        logger.warning("[rca] metric evidence failed: %s", exc)
        return {}


async def collect_context(
    *,
    service: str | None,
    alert_name: str,
    hours: float,
    extra_context: str,
    source_labels: dict[str, str] | None = None,
    inspection_summary: dict | None = None,
    inspection_results: list[dict] | None = None,
    on_facts=None,
) -> dict[str, dict]:
    alert_name = _text_or_empty(alert_name)
    extra_context = _text_or_empty(extra_context)
    labels = source_labels or {}

    from services.rca_evidence import (
        collect_kubernetes_evidence,
        collect_slowlog_evidence,
        collect_two_stage,
    )

    collectors = {
        "kubernetes": lambda: collect_kubernetes_evidence(service=service, labels=labels),
        "slowlog": lambda: collect_slowlog_evidence(service=service, labels=labels),
        "loki": lambda: _collect_loki(service, hours, labels),
        "prometheus": lambda: _collect_prometheus(service, labels),
        "skywalking": lambda: _collect_skywalking(service),
        "cmdb": lambda: _collect_cmdb(service),
        "changes": lambda: asyncio.to_thread(_collect_change_context, service),
        "metric_evidence": lambda: _collect_metric_evidence(service, labels, hours),
        "codebase": lambda: asyncio.to_thread(_collect_code_context, service, extra_context),
    }
    staged = await collect_two_stage(
        collectors,
        facts_deadline_sec=5.0,
        final_deadline_sec=12.0,
        on_facts=on_facts,
    )
    context: dict[str, dict] = dict(staged.get("sections") or {})

    if extra_context.strip():
        context["extra"] = {
            "title": "额外上下文",
            "summary": _compact_text(extra_context, 220),
            "items": [line.strip() for line in extra_context.splitlines() if line.strip()][:8],
        }

    if inspection_summary or inspection_results:
        context["inspection"] = _summarize_inspection_results(inspection_results or [], inspection_summary or {})

    similar_cases = _match_similar_cases(
        service=service,
        alert_name=alert_name,
        extra_context=extra_context,
        context_sections=context,
    )
    context["similar_cases"] = {
        "title": "专家案例",
        "summary": f"命中 {len(similar_cases)} 条历史专家案例。",
        "items": similar_cases,
    }
    context["_collection"] = {
        "collector_states": staged.get("collector_states", {}),
        "facts_ready_ms": staged.get("facts_ready_ms"),
        "evidence_ready_ms": staged.get("evidence_ready_ms"),
    }
    return context


def _collect_signal_text(record: dict) -> str:
    parts = [
        _text_or_empty(record.get("service")),
        _text_or_empty(record.get("alert_name")),
        _text_or_empty(record.get("extra_context")),
    ]
    context = record.get("context", {}) or {}
    for value in context.values():
        if not isinstance(value, dict):
            continue
        parts.append(str(value.get("summary") or ""))
        for item in value.get("items", [])[:8]:
            parts.append(str(item))
        for item in value.get("context_items", [])[:4]:
            parts.append(str(item))
    return " ".join(parts).strip().lower()


def _metric_value(context: dict, key: str) -> float:
    section = context.get("prometheus", {}) if isinstance(context, dict) else {}
    metrics = section.get("metrics", []) if isinstance(section, dict) else []
    for item in metrics:
        if item.get("key") == key:
            return _safe_float(item.get("value"), 0.0)
    return 0.0


def _build_commands(category: str, service: str, namespace: str) -> list[str]:
    svc = service if service and service != "global" else "<service>"
    ns = namespace or "<namespace>"
    mapping = {
        "application_bug": [
            f"kubectl logs deployment/{svc} -n {ns} --tail=200",
            f"kubectl logs deployment/{svc} -n {ns} --previous --tail=120",
            f"kubectl describe deployment/{svc} -n {ns}",
        ],
        "dependency_failure": [
            f"kubectl logs deployment/{svc} -n {ns} | grep -Ei 'timeout|refused|reset|dns'",
            "ss -antp | grep -E '3306|6379|9092|5672'",
            "curl -sv http://<dependency>/health",
        ],
        "resource_bottleneck": [
            f"kubectl top pod -n {ns} | grep {svc}",
            f"kubectl describe pod -n {ns} <pod-name>",
            "free -m && df -h && top -b -n1 | head -40",
        ],
        "platform_host_issue": [
            "kubectl get nodes -o wide",
            "kubectl describe node <node-name>",
            "dmesg -T | tail -n 80",
        ],
        "change_regression": [
            f"kubectl rollout history deployment/{svc} -n {ns}",
            "git log --oneline --since='24 hours ago'",
            f"kubectl describe deployment/{svc} -n {ns}",
        ],
    }
    return mapping.get(category, mapping["application_bug"])


def _namespace_from_record(record: dict) -> str:
    labels = record.get("source_labels", {}) or {}
    if labels.get("namespace"):
        return str(labels.get("namespace"))
    if labels.get("kubernetes_namespace"):
        return str(labels.get("kubernetes_namespace"))
    inspection = (record.get("context") or {}).get("inspection", {})
    if isinstance(inspection, dict):
        summary = str(inspection.get("summary") or "")
        if "namespace=" in summary:
            return summary.split("namespace=", 1)[1].split()[0].strip("。;,")
    return "default"


def _candidate_base_scores(record: dict) -> dict[str, tuple[int, list[str]]]:
    context = record.get("context", {}) or {}
    signal_text = _collect_signal_text(record)
    loki_items = context.get("loki", {}).get("items", []) if isinstance(context.get("loki"), dict) else []
    similar = context.get("similar_cases", {}).get("items", []) if isinstance(context.get("similar_cases"), dict) else []

    cpu = _metric_value(context, "cpu_usage_pct")
    mem = _metric_value(context, "memory_usage_pct")
    err_ratio = _metric_value(context, "http_5xx_ratio_pct")
    p99 = _metric_value(context, "p99_latency_ms")
    raw_logs = int(context.get("loki", {}).get("raw_count", 0) or 0)
    trace_errors = int(context.get("skywalking", {}).get("error_trace_count", 0) or 0)
    code_hits = len(context.get("codebase", {}).get("items", []) if isinstance(context.get("codebase"), dict) else [])
    inspect_critical = int(context.get("inspection", {}).get("critical_count", 0) or 0)
    inspect_warning = int(context.get("inspection", {}).get("warning_count", 0) or 0)
    recent_changes = len(context.get("changes", {}).get("items", []) if isinstance(context.get("changes"), dict) else [])

    def has_any(*words: str) -> bool:
        return any(word in signal_text for word in words)

    evidence_map: dict[str, list[str]] = {key: [] for key in _CATEGORY_META}
    score_map = {key: 18 for key in _CATEGORY_META}

    # 指标证据包异常项 → 直接给资源类假设加权（结构化证据优先于文本信号）
    evidence_pack = context.get("metric_evidence", {}).get("pack", {}) \
        if isinstance(context.get("metric_evidence"), dict) else {}
    for ev_item in evidence_pack.get("evidence", []):
        if ev_item.get("status") != "abnormal":
            continue
        name = str(ev_item.get("name", ""))
        note = (f"指标证据：{name} 当前 {ev_item.get('latest')}{ev_item.get('unit', '')}，"
                f"基线 {ev_item.get('baseline')}{ev_item.get('unit', '')}（{ev_item.get('detail', '')}）")
        if any(k in name for k in ("CPU", "内存", "负载", "磁盘", "分区")):
            score_map["resource_bottleneck"] += 20
            evidence_map["resource_bottleneck"].append(note)
        elif any(k in name for k in ("错误率", "5xx", "延迟", "P95")):
            score_map["application_bug"] += 16
            evidence_map["application_bug"].append(note)
        elif any(k in name for k in ("重启", "down")):
            score_map["platform_host_issue"] += 16
            evidence_map["platform_host_issue"].append(note)

    if has_any("exception", "traceback", "nullpointer", "panic", "illegal", "stack", "500", "5xx"):
        score_map["application_bug"] += 24
        evidence_map["application_bug"].append("日志中出现异常栈、Exception、5xx 或代码级报错特征。")
    if raw_logs >= 30:
        score_map["application_bug"] += 8
        evidence_map["application_bug"].append(f"Loki 最近窗口抓到 {raw_logs} 条错误日志，应用内部故障概率升高。")
    if err_ratio >= 5:
        score_map["application_bug"] += 10
        evidence_map["application_bug"].append(f"HTTP 5xx 比例达到 {err_ratio:.2f}%。")
    if code_hits > 0 and has_any("exception", "traceback", "error", "500", "5xx"):
        score_map["application_bug"] += 10
        evidence_map["application_bug"].append(f"源码检索命中 {code_hits} 条服务/异常/接口相关线索。")

    if has_any("timeout", "timed out", "connection refused", "reset by peer", "dns", "upstream", "redis", "mysql", "postgres", "kafka", "rabbitmq", "es", "elasticsearch"):
        score_map["dependency_failure"] += 24
        evidence_map["dependency_failure"].append("日志中存在 timeout、refused、reset、DNS 或下游组件关键字。")
    if trace_errors > 0:
        score_map["dependency_failure"] += 8
        evidence_map["dependency_failure"].append(f"SkyWalking 最近 1h 发现 {trace_errors} 条异常 Trace。")

    if cpu >= 85 or mem >= 85:
        score_map["resource_bottleneck"] += 26
        evidence_map["resource_bottleneck"].append(f"资源指标异常，CPU={cpu:.2f}% / MEM={mem:.2f}%。")
    if p99 >= 1500:
        score_map["resource_bottleneck"] += 10
        evidence_map["resource_bottleneck"].append(f"P99 延迟达到 {p99:.2f}ms。")
    if has_any("oom", "outofmemory", "killed", "throttl", "disk", "no space", "cpu throttling"):
        score_map["resource_bottleneck"] += 12
        evidence_map["resource_bottleneck"].append("日志中出现 OOM、限流、磁盘耗尽等容量信号。")

    if inspect_critical > 0 or has_any("node", "hostdown", "nodedown", "instance down", "offline"):
        score_map["platform_host_issue"] += 24
        evidence_map["platform_host_issue"].append(f"巡检严重主机 {inspect_critical} 台，或存在节点/实例下线告警。")
    if inspect_warning > 0:
        score_map["platform_host_issue"] += 8
        evidence_map["platform_host_issue"].append(f"巡检警告主机 {inspect_warning} 台。")

    if recent_changes > 0:
        score_map["change_regression"] += 18
        evidence_map["change_regression"].append(f"近窗口命中 {recent_changes} 条代码变更记录。")
    if has_any("deploy", "release", "rollback", "migration", "version", "configmap", "helm"):
        score_map["change_regression"] += 12
        evidence_map["change_regression"].append("上下文中存在发布、回滚、迁移或配置变更信号。")

    for case in similar[:3]:
        category = str(case.get("category") or "")
        if category in score_map:
            score_map[category] += min(10, int(case.get("score") or 0))
            evidence_map[category].append(
                f"专家库命中相似案例：{case.get('title')}（相似分 {case.get('score')}）。"
            )

    for key, items in evidence_map.items():
        if not items and loki_items:
            items.append(f"当前未发现强特征，保留该假设作为备选路径。日志样本：{_compact_text(str(loki_items[0]), 90)}")

    return {key: (score_map[key], evidence_map[key]) for key in score_map}


async def _validate_candidate(
    *,
    category: str,
    rank: int,
    record: dict,
    base_score: int,
    evidence: list[str],
    feedback_weight: float,
) -> dict:
    await asyncio.sleep(0)
    meta = _CATEGORY_META[category]
    namespace = _namespace_from_record(record)
    commands = _build_commands(category, record.get("service", "global"), namespace)

    adjusted = int(round(base_score * feedback_weight))
    adjusted = int(_clamp(adjusted, 10, 99))
    if adjusted >= 75:
        summary = f"{meta['summary']} 当前证据链较强，建议优先验证。"
        status = "supported"
    elif adjusted >= 50:
        summary = f"{meta['summary']} 当前证据中等，建议并行验证。"
        status = "possible"
    else:
        summary = f"{meta['summary']} 当前证据偏弱，仅作为兜底假设。"
        status = "weak"

    return {
        "id": f"hyp_{rank}",
        "rank": rank,
        "agent_name": f"Validator-{rank}",
        "category": category,
        "title": meta["title"],
        "description": meta["summary"],
        "score": adjusted,
        "validation_status": status,
        "validation_summary": summary,
        "evidence": evidence[:6],
        "commands": commands,
    }


def _slowlog_hypotheses(context: dict) -> list[dict]:
    section = context.get("slowlog") if isinstance(context, dict) else None
    candidates = section.get("candidates", []) if isinstance(section, dict) else []
    hypotheses: list[dict] = []
    for index, candidate in enumerate(candidates[:3], start=1):
        score = int(candidate.get("score") or 0)
        confidence = str(candidate.get("confidence") or "low")
        query_time = _safe_float(candidate.get("query_time"), 0.0)
        fingerprint = str(candidate.get("sql_fingerprint") or "未知 SQL 特征")
        evidence = []
        for item in candidate.get("evidence", []) or []:
            if isinstance(item, dict):
                points = int(item.get("score") or 0)
                evidence.append(f"{item.get('detail') or item.get('rule')}（{points:+d}分）")
            else:
                evidence.append(str(item))
        status = "supported" if confidence == "high" else "possible" if confidence == "medium" else "weak"
        hypotheses.append({
            "id": f"hyp_{index}",
            "rank": index,
            "agent_name": f"SlowSQL-Validator-{index}",
            "category": "dependency_failure",
            "title": f"慢 SQL 候选 #{index}（{query_time:g}s）",
            "description": fingerprint,
            "score": score,
            "confidence": confidence,
            "validation_status": status,
            "validation_summary": f"该候选为{confidence}置信度概率匹配，不代表已建立 Trace 与 SQL 的确定关联。",
            "evidence": evidence[:8],
            "commands": [
                "对候选 SQL 执行 EXPLAIN / EXPLAIN ANALYZE",
                "核对索引、扫描行数和大对象字段读取范围",
                "优化后复测接口 P95/P99 与 SQL 执行时间",
            ],
        })
    return hypotheses


async def _generate_hypotheses(record: dict) -> list[dict]:
    slowlog_hypotheses = _slowlog_hypotheses(record.get("context", {}) or {})
    if len(slowlog_hypotheses) >= 3:
        return slowlog_hypotheses[:3]

    feedback = _load_feedback()
    weights = feedback.get("weights", {})
    scored = _candidate_base_scores(record)
    ranked = sorted(scored.items(), key=lambda item: item[1][0] * _safe_float(weights.get(item[0]), 1.0), reverse=True)[:3]

    tasks = []
    for index, (category, (base_score, evidence)) in enumerate(ranked, start=1):
        tasks.append(
            _validate_candidate(
                category=category,
                rank=index,
                record=record,
                base_score=base_score,
                evidence=evidence,
                feedback_weight=_safe_float(weights.get(category), 1.0),
            )
        )

    hypotheses = await asyncio.gather(*tasks)
    if slowlog_hypotheses:
        occupied = {item.get("category") for item in slowlog_hypotheses}
        hypotheses = slowlog_hypotheses + [item for item in hypotheses if item.get("category") not in occupied]
    hypotheses.sort(key=lambda item: (-item["score"], item["rank"]))
    hypotheses = hypotheses[:3]
    for index, item in enumerate(hypotheses, start=1):
        item["rank"] = index
        item["id"] = f"hyp_{index}"
        item["agent_name"] = f"Validator-{index}"
    return hypotheses


def _build_final_summary(record: dict) -> str:
    top = (record.get("hypotheses") or [None])[0]
    if not top:
        return "暂无高置信度根因，请继续补充上下文。"

    human = record.get("human_confirmation", {}) or {}
    tail = ""
    if human.get("status") == "confirmed":
        tail = " 已经人工确认并回写专家库。"
    elif human.get("status") == "pending":
        tail = " 当前等待人工确认。"

    score = int(top.get("score") or 0)
    return f"首选根因是“{top.get('title')}”，综合评分 {score} 分。{top.get('validation_summary', '')}{tail}".strip()


async def analyze_stream(
    service: str | None,
    alert_name: str = "",
    hours: float = 1.0,
    extra_context: str = "",
) -> AsyncIterator[str]:
    """Compatibility stream API. The new UI uses async trigger + polling."""
    alert_name = _text_or_empty(alert_name)
    extra_context = _text_or_empty(extra_context)
    record = await run_rca(
        service=service,
        alert_name=alert_name,
        alert_group_id=None,
        hours=hours,
        extra_context=extra_context,
        source_type="manual",
    )
    result_text = _text_or_empty((get_rca(record) or {}).get("result"))
    for line in result_text.splitlines(True):
        yield line


def _record_rca_event(record: dict, phase: str, *, severity: str = "info") -> None:
    """Write only RCA state transitions to the event wall."""
    try:
        from routers import events as event_router

        payload = {
            "event_id": f"{record.get('id')}-{phase}",
            "title": f"RCA {phase}",
            "message": record.get("final_summary") or phase,
            "service": record.get("service") or "",
            "severity": severity,
            "status": phase,
            "resource_type": "rca_run",
            "resource_id": record.get("id") or "",
            "labels": {"rca_id": record.get("id") or "", "phase": phase},
        }
        event = event_router._normalize_external_event("rca", payload)
        events = event_router._load_external_events()
        old_index = next((index for index, item in enumerate(events) if item.get("id") == event["id"]), None)
        if old_index is None:
            events.insert(0, event)
        else:
            events[old_index] = {**events[old_index], **event}
        event_router._save_external_events(events)
        event_router._stats_cache.clear()
    except Exception as exc:
        logger.warning("[rca] failed to record event wall transition: %s", exc)


async def _notify_rca_completion(
    record: dict,
    *,
    group_loader=None,
    target_resolver=None,
    sender=None,
) -> None:
    alert_group_id = str(record.get("alert_group_id") or "")
    if not alert_group_id:
        return
    try:
        if group_loader is None or target_resolver is None:
            from routers.alerts import _resolve_alert_targets, get_group

            group_loader = group_loader or get_group
            target_resolver = target_resolver or _resolve_alert_targets
        if sender is None:
            from notifier import send_feishu_rca_result

            sender = send_feishu_rca_result

        group = group_loader(alert_group_id)
        if not group:
            return
        base_url = os.getenv("AIOPS_PUBLIC_URL", "").strip().rstrip("/")
        report_url = f"{base_url}/#/aiops/rca?rca_id={record.get('id')}" if base_url else ""
        targets = target_resolver(group) or []
        if targets:
            for target in targets:
                result = await sender(
                    record,
                    target["webhook_url"],
                    report_url=report_url,
                    keyword=target.get("keyword", ""),
                    target_name=target.get("group_name", ""),
                )
                if not result.get("ok"):
                    logger.warning("[rca] Feishu completion push failed: %s", result.get("msg"))
            return

        fallback_webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
        if fallback_webhook:
            await sender(
                record,
                fallback_webhook,
                report_url=report_url,
                keyword=os.getenv("FEISHU_KEYWORD", "").strip(),
                target_name="default-feishu-group",
            )
    except Exception as exc:
        logger.warning("[rca] failed to push completion to Feishu: %s", exc)


async def run_rca(
    *,
    service: str | None,
    alert_name: str = "",
    alert_group_id: str | None = None,
    hours: float = 1.0,
    extra_context: str = "",
    source_type: str = "manual",
    source_id: str = "",
    source_name: str = "",
    source_labels: dict[str, str] | None = None,
    inspection_summary: dict | None = None,
    inspection_results: list[dict] | None = None,
    existing_id: str | None = None,
) -> str:
    """Run full RCA and persist a structured RCA run."""
    alert_name = _text_or_empty(alert_name)
    extra_context = _text_or_empty(extra_context)
    source_type = _text_or_empty(source_type) or "manual"
    source_id = _text_or_empty(source_id)
    source_name = _text_or_empty(source_name)
    record = get_rca(existing_id) if existing_id else None
    if not record:
        record = create_pending_rca(
            service=service,
            alert_name=alert_name,
            alert_group_id=alert_group_id,
            hours=hours,
            extra_context=extra_context,
            source_type=source_type,
            source_id=source_id,
            source_name=source_name,
            source_labels=source_labels,
        )

    rca_id = record["id"]

    started_monotonic = time.monotonic()
    try:
        update_rca(
            rca_id,
            {
                "status": "running",
                "phase": "collecting",
                "timeline": record.get("timeline", []) + [
                    _timeline("context", "开始采集上下文", "logs / metrics / trace / CMDB / changes / codebase")
                ],
            },
        )
        _record_rca_event(get_rca(rca_id) or record, "collecting")

        async def publish_facts(snapshot: dict) -> None:
            facts_ready_ms = int(snapshot.get("facts_ready_ms") or round((time.monotonic() - started_monotonic) * 1000))
            current_record = get_rca(rca_id) or record
            updated = update_rca(
                rca_id,
                {
                    "status": "facts_ready",
                    "phase": "facts_ready",
                    "context": snapshot.get("sections", {}),
                    "collector_states": snapshot.get("collector_states", {}),
                    "sla": {
                        "facts_ready_at": _now_iso(),
                        "facts_ready_ms": facts_ready_ms,
                        "facts_deadline_met": facts_ready_ms <= 5000,
                    },
                    "timeline": current_record.get("timeline", []) + [
                        _timeline("facts_ready", "第一阶段事实已就绪", f"耗时 {facts_ready_ms}ms；慢采集器继续执行")
                    ],
                    "final_summary": "第一阶段事实已就绪，正在生成根因候选。",
                },
            ) or current_record
            if alert_group_id:
                try:
                    from services.alert_dedup import update_group_status

                    update_group_status(
                        alert_group_id,
                        "analyzing",
                        rca_id=rca_id,
                        extra_updates={
                            "analysis_hook": {
                                "status": "facts_ready",
                                "facts_ready_at": updated.get("sla", {}).get("facts_ready_at", ""),
                                "facts_ready_ms": facts_ready_ms,
                            }
                        },
                    )
                except Exception as exc:
                    logger.warning("[rca] failed to update facts-ready alert state: %s", exc)
            _record_rca_event(updated, "facts_ready")

        context = await collect_context(
            service=service,
            alert_name=alert_name,
            hours=hours,
            extra_context=extra_context,
            source_labels=source_labels,
            inspection_summary=inspection_summary,
            inspection_results=inspection_results,
            on_facts=publish_facts,
        )

        collection = context.get("_collection", {}) if isinstance(context, dict) else {}
        current = update_rca(
            rca_id,
            {
                "status": "evidence_ready",
                "phase": "evidence_ready",
                "context": context,
                "collector_states": collection.get("collector_states", {}),
                "sla": {
                    "facts_ready_ms": collection.get("facts_ready_ms"),
                    "evidence_ready_ms": collection.get("evidence_ready_ms"),
                    "evidence_ready_at": _now_iso(),
                },
                "timeline": (get_rca(rca_id) or {}).get("timeline", [])
                + [_timeline("context_done", "上下文采集完成", "证据已写入 RCA run")],
            },
        ) or (get_rca(rca_id) or record)
        _record_rca_event(current, "evidence_ready")

        remaining = max(0.05, 15.0 - (time.monotonic() - started_monotonic))
        try:
            hypotheses = await asyncio.wait_for(_generate_hypotheses(current), timeout=remaining)
        except asyncio.TimeoutError:
            hypotheses = _slowlog_hypotheses(context)
            current["analysis_timeout"] = True
        current["hypotheses"] = hypotheses
        current["expert_matches"] = context.get("similar_cases", {}).get("items", []) if isinstance(context.get("similar_cases"), dict) else []
        current["status"] = "awaiting_confirmation"
        current["phase"] = "analysis_ready"
        analysis_ready_ms = round((time.monotonic() - started_monotonic) * 1000)
        current.setdefault("sla", {})["analysis_ready_at"] = _now_iso()
        current["sla"]["analysis_ready_ms"] = analysis_ready_ms
        current["sla"]["analysis_deadline_met"] = analysis_ready_ms <= 15000
        current["final_summary"] = _build_final_summary(current)
        current["result"] = _build_result_markdown(current)
        current["timeline"] = current.get("timeline", []) + [
            _timeline("hypothesis_done", "多假设并行验证完成", "3 个假设已完成评分并等待人工确认")
        ]
        save_rca(current)
        _record_rca_event(current, "analysis_ready")
        asyncio.create_task(_notify_rca_completion(current))

        if alert_group_id:
            try:
                from services.alert_dedup import update_group_status

                update_group_status(
                    alert_group_id,
                    "analyzing",
                    rca_id=rca_id,
                    extra_updates={
                        "analysis_hook": {
                            "status": "analysis_ready",
                            "analysis_ready_at": current.get("sla", {}).get("analysis_ready_at", ""),
                            "analysis_ready_ms": analysis_ready_ms,
                            "top_confidence": (hypotheses[0].get("confidence") if hypotheses else ""),
                        }
                    },
                )
            except Exception as exc:
                logger.warning("[rca] failed to update alert group status: %s", exc)

        return rca_id
    except Exception as exc:
        logger.exception("[rca] structured RCA failed")
        update_rca(
            rca_id,
            {
                "status": "error",
                "phase": "error",
                "final_summary": f"RCA 执行失败: {exc}",
                "result": f"## 根因摘要\nRCA 执行失败：{exc}",
                "timeline": (get_rca(rca_id) or {}).get("timeline", []) + [
                    _timeline("error", "RCA 执行失败", str(exc), status="error")
                ],
            },
        )
        raise
