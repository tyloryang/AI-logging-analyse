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
            Path(tmp, f"{report_id}.json").write_text(
                json.dumps(
                    {
                        "id": report_id,
                        "type": "inspect",
                        "title": "核心组巡检",
                        "health_score": 100,
                        "host_summary": {
                            "total": 0,
                            "normal": 0,
                            "warning": 0,
                            "critical": 0,
                        },
                        "ai_analysis": "正常",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
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
                patch(
                    "services.report_pdf.build_report_pdf",
                    side_effect=RuntimeError("render failed"),
                ),
            ):
                with self.assertRaises(HTTPException) as failure:
                    await reports.public_inspect_report_pdf(report_id)
        self.assertEqual(failure.exception.status_code, 500)

    def test_auth_middleware_allows_only_public_inspect_prefix(self):
        self.assertTrue(_is_public("/api/public/report/inspect/inspect_1.pdf"))
        self.assertFalse(_is_public("/api/report/daily_1/export.pdf"))
        self.assertFalse(_is_public("/api/public/report/daily/daily_1.pdf"))
