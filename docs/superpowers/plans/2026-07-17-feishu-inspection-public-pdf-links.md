# Feishu Inspection Public PDF Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add permanent, anonymous PDF links to every Feishu inspection notification while keeping non-inspection reports private.

**Architecture:** Add one focused delivery service that builds public inspection URLs and persists group-specific inspection reports. Expose an inspect-only anonymous PDF route, then pass its URL through the existing full-report and group-report Feishu card builders after the corresponding report JSON has been saved.

**Tech Stack:** Python 3.12, FastAPI, ReportLab, httpx, unittest, unittest.mock

## Global Constraints

- Cover global scheduled inspection, group scheduled inspection, group manual inspection, and report-page manual push.
- Use `GET /api/public/report/inspect/{report_id}.pdf` for anonymous access.
- Only `type=inspect` reports are public; existing daily and slowlog access rules remain unchanged.
- Use `Content-Disposition: inline` so browsers can preview and download the PDF.
- Build absolute links from `APP_URL`; when it is empty, send the card without a link and log a configuration warning.
- Public links have no independent expiration, but reports remain subject to `REPORT_RETENTION_DAYS`.
- Save report JSON before sending a Feishu card that links to it.
- Preserve existing card summaries, keyword checks, AI truncation, DingTalk behavior, and authenticated PDF export.
- Preserve unrelated working-tree changes and stage only files named by each task.

---

## File Structure

- Create `backend/services/inspect_report_delivery.py`: public URL construction and group inspection report persistence.
- Modify `backend/notifier.py`: add the public PDF action to full and group inspection cards.
- Modify `backend/auth/middleware.py`: allow only the inspect public PDF prefix without a session.
- Modify `backend/routers/reports.py`: add the anonymous inspect-only PDF endpoint and wire manual/report-generated pushes.
- Modify `backend/scheduler.py`: wire global and group scheduled pushes after report persistence.
- Create `backend/tests/test_feishu_inspect_pdf_links.py`: URL helper and card payload tests.
- Create `backend/tests/test_public_inspect_pdf.py`: authentication boundary and public endpoint tests.
- Create `backend/tests/test_inspect_report_delivery.py`: group report persistence tests.
- Create `backend/tests/test_inspect_notification_flows.py`: scheduler and report-router wiring tests.

---

### Task 1: Public URL Builder and Feishu Card Actions

**Files:**
- Create: `backend/services/inspect_report_delivery.py`
- Modify: `backend/notifier.py:244-326,329-393,568-586`
- Create: `backend/tests/test_feishu_inspect_pdf_links.py`

**Interfaces:**
- Produces: `build_public_inspect_pdf_url(report_id: str, app_url: str) -> str`
- Produces: `_build_feishu_group_inspect_card(group_name: str, results: list[dict], keyword: str = "", ai_text: str = "", report_url: str = "") -> dict`
- Produces: `send_feishu_group_inspect(group_name: str, results: list[dict], webhook_url: str, keyword: str = "", ai_text: str = "", report_url: str = "") -> dict`
- Consumes: Feishu interactive-card URL button format documented by Feishu Open Platform.

- [ ] **Step 1: Write the failing URL and card tests**

```python
import unittest

from notifier import _build_feishu_group_inspect_card, _build_feishu_inspect_card


def _action_urls(card: dict) -> list[str]:
    urls = []
    for element in card["card"]["elements"]:
        if element.get("tag") != "action":
            continue
        urls.extend(action.get("url", "") for action in element.get("actions", []))
    return [url for url in urls if url]


class FeishuInspectPdfLinkTests(unittest.TestCase):
    def test_public_url_uses_app_url_and_report_id(self):
        try:
            from services.inspect_report_delivery import build_public_inspect_pdf_url
        except ImportError as exc:
            self.fail(f"public inspection URL helper is missing: {exc}")

        self.assertEqual(
            build_public_inspect_pdf_url("inspect_20260717010101_grp-1", "https://aiops.example/"),
            "https://aiops.example/api/public/report/inspect/inspect_20260717010101_grp-1.pdf",
        )
        self.assertEqual(build_public_inspect_pdf_url("inspect_1", ""), "")

    def test_full_and_group_cards_include_public_pdf_button(self):
        url = "https://aiops.example/api/public/report/inspect/inspect_1.pdf"
        report = {
            "type": "inspect",
            "title": "主机巡检日报",
            "health_score": 80,
            "host_summary": {"total": 1, "normal": 1, "warning": 0, "critical": 0},
        }
        result = [{"overall": "normal", "hostname": "host-1", "checks": []}]

        full_card = _build_feishu_inspect_card(report, report_url=url)
        group_card = _build_feishu_group_inspect_card("核心组", result, report_url=url)

        self.assertEqual(_action_urls(full_card), [url])
        self.assertEqual(_action_urls(group_card), [url])
        self.assertEqual(
            full_card["card"]["elements"][-1]["actions"][0]["text"]["content"],
            "查看完整巡检 PDF",
        )
        self.assertEqual(
            group_card["card"]["elements"][-1]["actions"][0]["text"]["content"],
            "查看完整巡检 PDF",
        )

    def test_cards_omit_action_when_url_is_empty(self):
        report = {"type": "inspect", "health_score": 100, "host_summary": {}}
        self.assertEqual(_action_urls(_build_feishu_inspect_card(report)), [])
        self.assertEqual(_action_urls(_build_feishu_group_inspect_card("核心组", [])), [])
```

- [ ] **Step 2: Run the tests and confirm the missing interface is detected**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_feishu_inspect_pdf_links -v
```

Expected: FAIL because `services.inspect_report_delivery` and the group `report_url` parameter do not exist.

- [ ] **Step 3: Implement the URL helper**

Create `backend/services/inspect_report_delivery.py` with:

```python
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
```

- [ ] **Step 4: Add the inspection PDF buttons**

In `_build_feishu_inspect_card()`, change the existing button text to `查看完整巡检 PDF`.

Change the group card signature to include `report_url: str = ""`. Immediately before the existing `return` statement, append the action only for a non-empty URL:

```python
if report_url:
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看完整巡检 PDF"},
            "type": "primary",
            "url": report_url,
        }],
    })
```

Pass the new optional argument through the sender:

```python
async def send_feishu_group_inspect(
    group_name: str,
    results: list[dict],
    webhook_url: str,
    keyword: str = "",
    ai_text: str = "",
    report_url: str = "",
) -> dict:
    payload = _build_feishu_group_inspect_card(
        group_name,
        results,
        keyword=keyword,
        ai_text=ai_text,
        report_url=report_url,
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code", -1) == 0:
                return {"ok": True, "msg": "发送成功"}
            return {"ok": False, "msg": data.get("msg", str(data))}
    except Exception as exc:
        return {"ok": False, "msg": str(exc)}
```

- [ ] **Step 5: Run the focused tests**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_feishu_inspect_pdf_links -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Commit Task 1**

```powershell
git add backend/services/inspect_report_delivery.py backend/notifier.py backend/tests/test_feishu_inspect_pdf_links.py
git commit -m "feat(feishu): add inspection PDF card links"
```

---

### Task 2: Inspect-Only Anonymous PDF Endpoint

**Files:**
- Modify: `backend/auth/middleware.py:16-28`
- Modify: `backend/routers/reports.py:840-864`
- Create: `backend/tests/test_public_inspect_pdf.py`

**Interfaces:**
- Consumes: `build_public_inspect_pdf_url()` route contract from Task 1.
- Produces: `public_inspect_report_pdf(report_id: str) -> Response`
- Produces: public path prefix `/api/public/report/inspect/`.

- [ ] **Step 1: Write failing endpoint and authentication tests**

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from auth.middleware import _is_public
from routers import reports


class PublicInspectPdfTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_inspect_route_returns_inline_pdf(self):
        self.assertTrue(
            hasattr(reports, "public_inspect_report_pdf"),
            "public inspect PDF endpoint is missing",
        )
        with tempfile.TemporaryDirectory() as tmp:
            report_id = "inspect_20260717010101_grp-1"
            Path(tmp, f"{report_id}.json").write_text(json.dumps({
                "id": report_id,
                "type": "inspect",
                "title": "核心组巡检",
                "health_score": 100,
                "host_summary": {"total": 0, "normal": 0, "warning": 0, "critical": 0},
                "ai_analysis": "正常",
            }, ensure_ascii=False), encoding="utf-8")
            with patch.object(reports, "REPORTS_DIR", Path(tmp)):
                response = await reports.public_inspect_report_pdf(report_id)

        self.assertEqual(response.media_type, "application/pdf")
        self.assertTrue(response.body.startswith(b"%PDF"))
        self.assertTrue(response.headers["content-disposition"].startswith("inline;"))

    async def test_public_route_rejects_non_inspect_and_invalid_ids(self):
        self.assertTrue(hasattr(reports, "public_inspect_report_pdf"))
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "daily_1.json").write_text(
                json.dumps({"id": "daily_1", "type": "daily"}),
                encoding="utf-8",
            )
            with patch.object(reports, "REPORTS_DIR", Path(tmp)):
                with self.assertRaises(HTTPException) as non_inspect:
                    await reports.public_inspect_report_pdf("daily_1")
                with self.assertRaises(HTTPException) as traversal:
                    await reports.public_inspect_report_pdf("../secrets")

        self.assertEqual(non_inspect.exception.status_code, 404)
        self.assertEqual(traversal.exception.status_code, 404)

    async def test_public_route_returns_404_for_removed_report(self):
        self.assertTrue(hasattr(reports, "public_inspect_report_pdf"))
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(reports, "REPORTS_DIR", Path(tmp)):
                with self.assertRaises(HTTPException) as missing:
                    await reports.public_inspect_report_pdf("inspect_removed")
        self.assertEqual(missing.exception.status_code, 404)

    async def test_public_route_maps_pdf_render_failure_to_500(self):
        self.assertTrue(hasattr(reports, "public_inspect_report_pdf"))
        with tempfile.TemporaryDirectory() as tmp:
            report_id = "inspect_render_failure"
            Path(tmp, f"{report_id}.json").write_text(
                json.dumps({"id": report_id, "type": "inspect"}),
                encoding="utf-8",
            )
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch("services.report_pdf.build_report_pdf", side_effect=RuntimeError("render failed")),
            ):
                with self.assertRaises(HTTPException) as failure:
                    await reports.public_inspect_report_pdf(report_id)
        self.assertEqual(failure.exception.status_code, 500)

    def test_auth_middleware_allows_only_public_inspect_prefix(self):
        self.assertTrue(_is_public("/api/public/report/inspect/inspect_1.pdf"))
        self.assertFalse(_is_public("/api/report/daily_1/export.pdf"))
        self.assertFalse(_is_public("/api/public/report/daily/daily_1.pdf"))
```

- [ ] **Step 2: Run the tests and confirm the endpoint and public prefix are missing**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_public_inspect_pdf -v
```

Expected: FAIL because the endpoint is absent and `_is_public()` rejects the new path.

- [ ] **Step 3: Add the exact public authentication prefix**

Change `backend/auth/middleware.py` to:

```python
_PUBLIC_PREFIXES = (
    "/api/events/ingest/",
    "/api/public/report/inspect/",
)
```

- [ ] **Step 4: Add safe report lookup and the public endpoint**

Add near the existing PDF export route in `backend/routers/reports.py`:

```python
_SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _public_inspect_report_path(report_id: str) -> Path:
    if not _SAFE_REPORT_ID.fullmatch(report_id or ""):
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    reports_root = REPORTS_DIR.resolve()
    report_path = (reports_root / f"{report_id}.json").resolve()
    if report_path.parent != reports_root:
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    return report_path


@router.get("/api/public/report/inspect/{report_id}.pdf")
async def public_inspect_report_pdf(report_id: str):
    report_path = _public_inspect_report_path(report_id)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    data = _read_report_json(report_path)
    if not data or data.get("type") != "inspect":
        raise HTTPException(status_code=404, detail="巡检报告不存在")

    from services.report_pdf import build_report_pdf
    try:
        pdf_bytes = await asyncio.to_thread(build_report_pdf, data)
    except Exception as exc:
        logger.exception("[report] 公开巡检 PDF 导出失败 %s", report_id)
        raise HTTPException(status_code=500, detail=f"PDF 生成失败: {exc}") from exc

    encoded = quote(f"{data.get('title', report_id)}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded}"},
    )
```

Move `import asyncio` to the module imports so both PDF endpoints use it, and add `import re` plus `from pathlib import Path` if not already present.

- [ ] **Step 5: Run endpoint and existing PDF tests**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_public_inspect_pdf tests.test_report_pdf -v
```

Expected: all public endpoint and long-row PDF tests pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add backend/auth/middleware.py backend/routers/reports.py backend/tests/test_public_inspect_pdf.py
git commit -m "feat(report): expose inspect-only public PDF"
```

---

### Task 3: Persist Group-Specific Inspection Reports Before Notification

**Files:**
- Modify: `backend/services/inspect_report_delivery.py`
- Create: `backend/tests/test_inspect_report_delivery.py`

**Interfaces:**
- Produces: `save_group_inspect_report(results: list[dict], group_id: str, group_name: str, ai_text: str) -> dict`
- Consumes: `report_builder.build_inspect_meta()` and `report_store.save_report_meta()`.

- [ ] **Step 1: Write the failing persistence test**

```python
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from services import inspect_report_delivery


class InspectReportDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_group_report_is_saved_before_returning_public_id(self):
        self.assertTrue(
            hasattr(inspect_report_delivery, "save_group_inspect_report"),
            "group inspection persistence helper is missing",
        )
        results = [{
            "overall": "warning",
            "ip": "10.0.0.8",
            "hostname": "app-1",
            "checks": [{"item": "磁盘 /", "status": "warning", "value": "90%"}],
            "partitions": [{"mountpoint": "/", "usage_pct": 90}],
            "process_top10": [{"service": "java", "cpu": 30, "mem": 20}],
        }]

        with tempfile.TemporaryDirectory() as tmp:
            save_meta = AsyncMock()
            with (
                patch.object(inspect_report_delivery, "REPORTS_DIR", Path(tmp)),
                patch.object(inspect_report_delivery, "save_report_meta", save_meta),
            ):
                report = await inspect_report_delivery.save_group_inspect_report(
                    results,
                    group_id="grp-1",
                    group_name="核心组",
                    ai_text="磁盘容量需要处理。",
                )
            saved = json.loads(Path(tmp, f"{report['id']}.json").read_text(encoding="utf-8"))

        self.assertEqual(saved["type"], "inspect")
        self.assertEqual(saved["group_id"], "grp-1")
        self.assertEqual(saved["all_hosts"][0]["ip"], "10.0.0.8")
        self.assertEqual(saved["ai_analysis"], "磁盘容量需要处理。")
        self.assertEqual(saved["host_summary"]["warning"], 1)
        save_meta.assert_awaited_once()
```

- [ ] **Step 2: Run the test and confirm the persistence helper is missing**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_inspect_report_delivery -v
```

Expected: FAIL with `group inspection persistence helper is missing`.

- [ ] **Step 3: Implement group report construction and persistence**

Extend `backend/services/inspect_report_delivery.py`:

```python
from pathlib import Path

from json_snapshot_store import write_json_file
from report_builder import build_inspect_meta
from report_store import save_report_meta
from state import REPORTS_DIR


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
        for item, count in sorted(issue_counts.items(), key=lambda pair: pair[1], reverse=True)[:10]
    ]
    abnormal_hosts = sorted(
        [item for item in results if item.get("overall") != "normal"],
        key=lambda item: {"critical": 2, "warning": 1}.get(item.get("overall", "normal"), 0),
        reverse=True,
    )
    health_score = int(100 * normal / total) if total else 100
    return {
        "summary": summary,
        "top_issues": top_issues,
        "abnormal_hosts": abnormal_hosts[:20],
        "all_hosts": results,
        "group_sections": [{"group_name": group_name, "hosts": results}],
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
    report["ai_analysis"] = str(ai_text or "").strip()
    report_path: Path = REPORTS_DIR / f"{report['id']}.json"
    write_json_file(report_path, report, ensure_parent=True)
    await save_report_meta(report)
    return report
```

- [ ] **Step 4: Run the persistence test**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_inspect_report_delivery -v
```

Expected: the group report test passes and writes a complete inspect JSON before returning.

- [ ] **Step 5: Commit Task 3**

```powershell
git add backend/services/inspect_report_delivery.py backend/tests/test_inspect_report_delivery.py
git commit -m "feat(report): persist group inspection deliveries"
```

---

### Task 4: Wire Every Inspection Notification Flow

**Files:**
- Modify: `backend/scheduler.py:114-212,215-275,277-326`
- Modify: `backend/routers/reports.py:468-546,1097-1126,1130-1172`
- Create: `backend/tests/test_inspect_notification_flows.py`

**Interfaces:**
- Consumes: `build_public_inspect_pdf_url()` from Task 1.
- Consumes: `save_group_inspect_report()` from Task 3.
- Consumes: `send_feishu(report: dict, webhook_url: str, keyword: str = "", report_url: str = "") -> dict` and `send_feishu_group_inspect(group_name: str, results: list[dict], webhook_url: str, keyword: str = "", ai_text: str = "", report_url: str = "") -> dict`.
- Produces: all global and group Feishu inspection calls carry a URL only after JSON persistence.

- [ ] **Step 1: Write failing scheduler wiring tests**

```python
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

import scheduler


class SchedulerInspectNotificationLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_schedule_passes_saved_inspect_pdf_url(self):
        daily = {"id": "daily_1", "type": "daily"}
        inspect = {"id": "inspect_1", "type": "inspect"}
        send_feishu = AsyncMock(return_value={"ok": True})
        with (
            patch.object(scheduler, "SCHEDULE_CHANNELS", ["feishu"]),
            patch.object(scheduler, "FEISHU_WEBHOOK", "https://feishu.example/hook"),
            patch.object(scheduler, "APP_URL", "https://aiops.example"),
            patch.object(scheduler, "_build_and_save_report", AsyncMock(return_value=daily)),
            patch.object(scheduler, "collect_inspect_data", AsyncMock(return_value={"results": []})),
            patch.object(scheduler, "_build_inspect_report", AsyncMock(return_value=inspect)),
            patch.object(scheduler, "_build_slowlog_report", AsyncMock(return_value=None)),
            patch.object(scheduler, "send_feishu", send_feishu),
            patch.object(scheduler, "_send_group_inspect_notifications", AsyncMock(return_value=[])),
            patch("state.REPORT_RETENTION_DAYS", 0),
        ):
            await scheduler.scheduled_report_job()

        inspect_call = send_feishu.await_args_list[1]
        self.assertEqual(
            inspect_call.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_1.pdf",
        )

    async def test_group_notification_saves_before_sending_link(self):
        events = []

        async def save_report(results, group_id, group_name, ai_text):
            events.append("saved")
            return {"id": "inspect_1_grp-1", "type": "inspect"}

        async def send_group(**kwargs):
            events.append("sent")
            self.assertEqual(
                kwargs["report_url"],
                "https://aiops.example/api/public/report/inspect/inspect_1_grp-1.pdf",
            )
            return {"ok": True}

        result = [{"group": "grp-1", "overall": "normal", "checks": []}]
        with (
            patch.object(scheduler, "APP_URL", "https://aiops.example"),
            patch.object(scheduler, "load_groups", return_value=[{
                "id": "grp-1",
                "name": "核心组",
                "schedule_enabled": True,
                "feishu_webhook": "https://feishu.example/hook",
            }]),
            patch.object(scheduler, "load_hosts_list", return_value=[]),
            patch.object(scheduler.analyzer, "generate_inspection_summary", _empty_stream),
            patch.object(scheduler, "save_group_inspect_report", save_report),
            patch.object(scheduler, "send_feishu_group_inspect", send_group),
        ):
            await scheduler._send_group_inspect_notifications(result)

        self.assertEqual(events, ["saved", "sent"])

    async def test_per_group_schedule_saves_and_links_group_report(self):
        results = [{"group": "grp-1", "overall": "normal", "checks": []}]
        inspect_data = {
            "results": results,
            "summary": {"total": 1, "normal": 1, "warning": 0, "critical": 0},
        }
        save_report = AsyncMock(return_value={"id": "inspect_1_grp-1", "type": "inspect"})
        send_group = AsyncMock(return_value={"ok": True})
        with (
            patch.object(scheduler, "APP_URL", "https://aiops.example"),
            patch.object(scheduler, "load_groups", return_value=[{
                "id": "grp-1",
                "name": "核心组",
                "schedule_enabled": True,
                "schedule_time": datetime.now().strftime("%H:%M"),
                "feishu_webhook": "https://feishu.example/hook",
            }]),
            patch.object(scheduler, "load_hosts_list", return_value=[{
                "ip": "10.0.0.8",
                "group": "grp-1",
            }]),
            patch.object(scheduler, "collect_inspect_data", AsyncMock(return_value=inspect_data)),
            patch.object(scheduler.analyzer, "generate_inspection_summary", _empty_stream),
            patch.object(scheduler, "save_group_inspect_report", save_report),
            patch.object(scheduler, "send_feishu_group_inspect", send_group),
        ):
            await scheduler.run_group_schedule_job()

        save_report.assert_awaited_once()
        self.assertEqual(
            send_group.await_args.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_1_grp-1.pdf",
        )


async def _empty_stream(results, summary):
    if False:
        yield ""
```

- [ ] **Step 2: Write failing report-router wiring tests**

Add to the same test file:

```python
import json
import tempfile
from pathlib import Path

from routers import reports


class ReportRouterInspectNotificationLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_inspect_push_uses_public_pdf_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_1.json").write_text(json.dumps({
                "id": "inspect_1",
                "type": "inspect",
                "host_summary": {},
            }), encoding="utf-8")
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", "https://aiops.example"),
                patch.object(reports, "FEISHU_WEBHOOK", "https://feishu.example/hook"),
                patch.object(reports, "send_feishu", sender),
            ):
                await reports.notify_report("inspect_1", reports.NotifyRequest(channels=["feishu"]))

        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_1.pdf",
        )

    async def test_manual_group_push_saves_and_links_group_specific_report(self):
        self.assertTrue(
            hasattr(reports, "save_group_inspect_report"),
            "report router has not wired group report persistence",
        )
        full_report = {
            "id": "inspect_all",
            "type": "inspect",
            "group_id": "",
            "created_at": "2026-07-17T01:01:01+00:00",
            "all_hosts": [{
                "group": "grp-1",
                "group_name": "核心组",
                "overall": "normal",
                "checks": [],
            }],
            "group_analyses": [{
                "group_id": "grp-1",
                "group_name": "核心组",
                "ai_analysis": "运行正常。",
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_all.json").write_text(
                json.dumps(full_report, ensure_ascii=False),
                encoding="utf-8",
            )
            save_group = AsyncMock(return_value={"id": "inspect_group", "type": "inspect"})
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", "https://aiops.example"),
                patch.object(reports, "load_groups", return_value=[{
                    "id": "grp-1",
                    "name": "核心组",
                    "feishu_webhook": "https://feishu.example/hook",
                }]),
                patch.object(reports, "save_group_inspect_report", save_group),
                patch.object(reports, "send_feishu", sender),
            ):
                await reports.notify_report_groups("inspect_all", group_id="grp-1")

        save_group.assert_awaited_once()
        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_group.pdf",
        )

    async def test_empty_app_url_still_sends_card_without_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "inspect_1.json").write_text(
                json.dumps({"id": "inspect_1", "type": "inspect", "host_summary": {}}),
                encoding="utf-8",
            )
            sender = AsyncMock(return_value={"ok": True})
            with (
                patch.object(reports, "REPORTS_DIR", Path(tmp)),
                patch.object(reports, "APP_URL", ""),
                patch.object(reports, "FEISHU_WEBHOOK", "https://feishu.example/hook"),
                patch.object(reports, "send_feishu", sender),
            ):
                await reports.notify_report("inspect_1", reports.NotifyRequest(channels=["feishu"]))

        self.assertEqual(sender.await_args.kwargs["report_url"], "")

    async def test_cached_generated_group_push_uses_cached_report_id(self):
        sender = AsyncMock(return_value={"ok": True})
        cached = {
            "id": "inspect_cached_grp-1",
            "type": "inspect",
            "group_id": "grp-1",
            "all_hosts": [{"overall": "normal", "checks": []}],
            "ai_analysis": "运行正常。",
        }
        with (
            patch.object(reports, "APP_URL", "https://aiops.example"),
            patch.object(reports, "load_groups", return_value=[{
                "id": "grp-1",
                "name": "核心组",
                "feishu_webhook": "https://feishu.example/hook",
            }]),
            patch.object(reports, "load_cmdb", return_value={
                "10.0.0.8:9100": {"group": "grp-1"},
            }),
            patch.object(reports, "_find_latest_group_inspect_report", return_value=cached),
            patch.object(reports, "send_feishu_group_inspect", sender),
        ):
            await reports.generate_inspect_report_all_groups()

        self.assertEqual(
            sender.await_args.kwargs["report_url"],
            "https://aiops.example/api/public/report/inspect/inspect_cached_grp-1.pdf",
        )
```

- [ ] **Step 3: Run the flow tests and confirm URLs/persistence are missing**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_inspect_notification_flows -v
```

Expected: FAIL because the scheduler and router still send inspection cards without public PDF URLs and do not call the group persistence helper.

- [ ] **Step 4: Wire scheduler imports and global scheduled inspection**

Add imports in `backend/scheduler.py`:

```python
from services.inspect_report_delivery import (
    build_public_inspect_pdf_url,
    save_group_inspect_report,
)
```

After `_build_inspect_report()` returns, construct and pass the URL:

```python
inspect_report = await _build_inspect_report(inspect_data)
inspect_report_url = build_public_inspect_pdf_url(inspect_report["id"], APP_URL)
if not inspect_report_url:
    logger.warning("[scheduler] APP_URL 未配置，飞书巡检卡片不附带 PDF 链接")

result2 = await send_feishu(
    inspect_report,
    FEISHU_WEBHOOK,
    keyword=FEISHU_KEYWORD,
    report_url=inspect_report_url,
)
```

- [ ] **Step 5: Save group scheduler reports before sending**

In both `_send_group_inspect_notifications()` and `run_group_schedule_job()`, insert this sequence after AI text is ready and before `send_feishu_group_inspect()`:

```python
group_report = await save_group_inspect_report(
    results=results,
    group_id=gid,
    group_name=group_name,
    ai_text=ai_text,
)
report_url = build_public_inspect_pdf_url(group_report["id"], APP_URL)
if not report_url:
    logger.warning("[scheduler] APP_URL 未配置，分组 '%s' 巡检卡片不附带 PDF 链接", group_name)
res = await send_feishu_group_inspect(
    group_name=group_name,
    results=results,
    webhook_url=group["feishu_webhook"],
    keyword=group.get("feishu_keyword", ""),
    ai_text=ai_text,
    report_url=report_url,
)
```

For `run_group_schedule_job()`, bind `gid = group["id"]` and `group_name = group["name"]` before using the shared sequence.

- [ ] **Step 6: Wire generated-group and manual report pushes**

Add the same two delivery imports to `backend/routers/reports.py`.

In `generate_inspect_report_all_groups()`:

- For cached reports, set `delivery_report = existing`.
- For generated reports, replace the current best-effort `meta_g` write block with an awaited call to `save_group_inspect_report()` and set `delivery_report` to its result.
- Build `report_url` from `delivery_report["id"]` and pass it to `send_feishu_group_inspect()`.

The final send sequence must be:

```python
report_url = build_public_inspect_pdf_url(delivery_report["id"], APP_URL)
if not report_url:
    logger.warning("分组 %s 巡检报告缺少公开地址：APP_URL 未配置", group_name)
push_result = await send_feishu_group_inspect(
    group_name,
    host_results,
    webhook,
    keyword=keyword,
    ai_text=ai_text,
    report_url=report_url,
)
```

In `notify_report()`, select the link by report type:

```python
if report.get("type") == "inspect":
    report_url = build_public_inspect_pdf_url(report_id, APP_URL)
    if not report_url:
        logger.warning("巡检报告 %s 推送未附带 PDF：APP_URL 未配置", report_id)
else:
    report_url = f"{APP_URL}/report/{report_id}" if APP_URL else ""
```

In `notify_report_groups()`, before sending an inspect payload to Feishu, persist the group-specific payload and use its ID:

```python
if payload_report.get("type") == "inspect":
    if report.get("group_id") == gid:
        delivery_report = report
    else:
        delivery_report = await save_group_inspect_report(
            results=payload_report.get("all_hosts", []),
            group_id=gid,
            group_name=group_name,
            ai_text=payload_report.get("ai_analysis", ""),
        )
    feishu_report_url = build_public_inspect_pdf_url(delivery_report["id"], APP_URL)
    if not feishu_report_url:
        logger.warning("分组 %s 巡检报告推送未附带 PDF：APP_URL 未配置", group_name)
else:
    feishu_report_url = f"{APP_URL}/report/{report_id}" if APP_URL else ""

pushed["feishu"] = await send_feishu(
    delivery_report if payload_report.get("type") == "inspect" else payload_report,
    feishu_wh,
    keyword=keyword,
    report_url=feishu_report_url,
)
```

Initialize `delivery_report = payload_report` before the conditional so the variable is defined for every branch.

- [ ] **Step 7: Expand flow tests for generated groups and `APP_URL` fallback**

Add assertions that:

- `generate_inspect_report_all_groups()` passes a URL based on the cached or newly saved group report ID.
- `notify_report_groups()` saves and links a group-specific report rather than the parent full-report ID.
- Empty `APP_URL` produces `report_url=""` but still calls the Feishu sender.

Use `AsyncMock` for report persistence and senders; use event side effects as in Step 1 when save-before-send order matters.

- [ ] **Step 8: Run all notification flow tests**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_inspect_notification_flows tests.test_feishu_inspect_pdf_links tests.test_inspect_report_delivery -v
```

Expected: all inspection notification tests pass.

- [ ] **Step 9: Commit Task 4**

```powershell
git add backend/scheduler.py backend/routers/reports.py backend/tests/test_inspect_notification_flows.py
git commit -m "feat(feishu): link all inspection notifications to PDF"
```

---

### Task 5: Full Regression and Acceptance Verification

**Files:**
- Verify all files changed in Tasks 1-4.
- Update tests only if verification reveals a real uncovered requirement; do not weaken assertions.

**Interfaces:**
- Consumes: all interfaces produced by Tasks 1-4.
- Produces: verified public PDF and Feishu notification behavior.

- [ ] **Step 1: Run focused inspection, report, Feishu, scheduler, and authentication tests**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest discover -s tests -p 'test_*report*.py' -v
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m unittest tests.test_host_inspection_report tests.test_feishu_inspect_pdf_links tests.test_public_inspect_pdf tests.test_inspect_report_delivery tests.test_inspect_notification_flows tests.test_auth_middleware -v
```

Expected: zero failures and zero errors.

- [ ] **Step 2: Compile every changed Python module**

Run:

```powershell
& 'D:\loki-log-analyse\.venv\Scripts\python.exe' -m py_compile backend/services/inspect_report_delivery.py backend/notifier.py backend/auth/middleware.py backend/routers/reports.py backend/scheduler.py
```

Expected: exit code 0 with no output.

- [ ] **Step 3: Check the exact diff and whitespace**

Run:

```powershell
git diff --check
git status --short
git diff -- backend/services/inspect_report_delivery.py backend/notifier.py backend/auth/middleware.py backend/routers/reports.py backend/scheduler.py backend/tests/test_feishu_inspect_pdf_links.py backend/tests/test_public_inspect_pdf.py backend/tests/test_inspect_report_delivery.py backend/tests/test_inspect_notification_flows.py
```

Expected: `git diff --check` exits 0; the scoped diff contains only the approved feature and its tests. Existing unrelated working-tree changes remain untouched.

- [ ] **Step 4: Perform an HTTP smoke test with an anonymous client**

Start the backend using the repository's normal development command with `APP_URL` set to the browser-reachable base URL. Create or reuse one inspect report, then request the newest retained inspect report without a `session_id` cookie:

```powershell
$reportsPath = if ($env:REPORTS_DIR) { $env:REPORTS_DIR } else { 'backend/reports' }
$reportFile = Get-ChildItem -LiteralPath $reportsPath -Filter 'inspect_*.json' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $reportFile) { throw 'No retained inspect report is available for the smoke test' }
$reportId = [IO.Path]::GetFileNameWithoutExtension($reportFile.Name)
$smokePath = Join-Path $env:TEMP 'inspect-report-smoke.pdf'
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/public/report/inspect/$reportId.pdf" -OutFile $smokePath
$bytes = [IO.File]::ReadAllBytes($smokePath)
if ($bytes.Length -lt 4 -or [Text.Encoding]::ASCII.GetString($bytes, 0, 4) -ne '%PDF') {
    throw 'Anonymous inspection PDF smoke test did not return a PDF'
}
Write-Output $bytes.Length
```

Expected: HTTP 200 and a non-empty file beginning with `%PDF` without a login cookie.

- [ ] **Step 5: Review acceptance criteria**

Confirm all of the following from test evidence and the smoke test:

- Global Feishu inspection cards contain the public PDF URL.
- Group Feishu inspection cards contain their own group report URL.
- Manual report pushes use the same public URL for inspect reports.
- Daily and slowlog reports remain unavailable through the public inspect route.
- Empty `APP_URL` never produces a localhost or relative button.
- Removed reports return 404 through the public route.

- [ ] **Step 6: Commit any verification-only corrections**

If verification required a legitimate correction, stage only the files named in this plan and commit:

```powershell
git add backend/services/inspect_report_delivery.py backend/notifier.py backend/auth/middleware.py backend/routers/reports.py backend/scheduler.py backend/tests/test_feishu_inspect_pdf_links.py backend/tests/test_public_inspect_pdf.py backend/tests/test_inspect_report_delivery.py backend/tests/test_inspect_notification_flows.py
git commit -m "test(report): verify public inspection PDF delivery"
```

If no correction was needed, do not create an empty commit.
