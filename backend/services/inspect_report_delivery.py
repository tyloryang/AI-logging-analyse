"""Persistence and public-link helpers for Feishu inspection delivery."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from json_snapshot_store import write_json_file
from report_builder import _build_host_brief, build_inspect_meta
from report_store import save_report_meta
from state import REPORTS_DIR


def _group_delivery_report_id(group_id: str) -> str:
    group_digest = sha256(str(group_id or "").encode("utf-8")).hexdigest()[:12]
    return f"inspect_{group_digest}_{uuid4().hex}"


def _normalize_host_result(result: dict) -> dict:
    host = _build_host_brief(result)
    for key, value in host.items():
        if value is None and result.get(key) is not None:
            host[key] = result[key]
    return host


def build_public_inspect_pdf_url(report_id: str, app_url: str) -> str:
    base_url = str(app_url or "").strip().rstrip("/")
    clean_report_id = str(report_id or "").strip()
    if not base_url or not clean_report_id:
        return ""
    encoded_report_id = quote(clean_report_id, safe="")
    return f"{base_url}/api/public/report/inspect/{encoded_report_id}.pdf"


def _group_inspect_data(results: list[dict], group_name: str) -> dict:
    total = len(results)
    normal = sum(1 for item in results if item.get("overall") == "normal")
    warning = sum(1 for item in results if item.get("overall") == "warning")
    critical = sum(1 for item in results if item.get("overall") == "critical")
    summary = {
        "total": total,
        "normal": normal,
        "warning": warning,
        "critical": critical,
        "cmdb_total": total,
        "prometheus_extra_count": 0,
        "scope": "cmdb",
        "group_name": group_name,
        "scope_note": f"统计口径：按 CMDB 分组「{group_name}」内 {total} 台主机统计。",
    }
    issue_counts: dict[str, int] = {}
    for result in results:
        for check in result.get("checks", []):
            if check.get("status") == "normal":
                continue
            item = check.get("item", "未知")
            issue_counts[item] = issue_counts.get(item, 0) + 1
    top_issues = [
        {"item": item, "count": count}
        for item, count in sorted(
            issue_counts.items(), key=lambda pair: pair[1], reverse=True
        )[:10]
    ]
    abnormal_hosts = sorted(
        [item for item in results if item.get("overall") != "normal"],
        key=lambda item: {"critical": 2, "warning": 1}.get(
            item.get("overall", "normal"), 0
        ),
        reverse=True,
    )
    normalized_results = [_normalize_host_result(result) for result in results]
    health_score = int(100 * normal / total) if total else 100
    return {
        "summary": summary,
        "top_issues": top_issues,
        "abnormal_hosts": abnormal_hosts[:20],
        "all_hosts": normalized_results,
        "group_sections": [{"group_name": group_name, "hosts": normalized_results}],
        "prometheus_extra_hosts": [],
        "scope_note": summary["scope_note"],
        "health_score": health_score,
    }


async def save_group_inspect_report(
    results: list[dict],
    group_id: str,
    group_name: str,
    ai_text: str,
) -> dict:
    report = build_inspect_meta(
        _group_inspect_data(results, group_name),
        group_id=group_id,
        group_name=group_name,
    )
    report["id"] = _group_delivery_report_id(group_id)
    report["ai_analysis"] = str(ai_text or "").strip()
    report_path: Path = REPORTS_DIR / f"{report['id']}.json"
    write_json_file(report_path, report, ensure_parent=True)
    await save_report_meta(report)
    return report
