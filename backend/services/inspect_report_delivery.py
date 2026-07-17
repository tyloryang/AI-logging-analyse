"""Persistence and public-link helpers for Feishu inspection delivery."""
from __future__ import annotations

from urllib.parse import quote


def build_public_inspect_pdf_url(report_id: str, app_url: str) -> str:
    base_url = str(app_url or "").strip().rstrip("/")
    clean_report_id = str(report_id or "").strip()
    if not base_url or not clean_report_id:
        return ""
    encoded_report_id = quote(clean_report_id, safe="")
    return f"{base_url}/api/public/report/inspect/{encoded_report_id}.pdf"
