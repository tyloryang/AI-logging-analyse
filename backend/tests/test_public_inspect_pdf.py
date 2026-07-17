import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi import HTTPException

from auth.middleware import AuthenticationMiddleware, _is_public
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
                patch.object(reports.logger, "exception") as logged,
            ):
                with self.assertRaises(HTTPException) as failure:
                    await reports.public_inspect_report_pdf(report_id)
        self.assertEqual(failure.exception.status_code, 500)
        self.assertEqual(failure.exception.detail, "PDF 生成失败")
        self.assertNotIn("render failed", failure.exception.detail)
        logged.assert_called_once_with(
            "[report] 公开巡检 PDF 导出失败 %s", report_id
        )

    def test_auth_middleware_allows_only_public_inspect_prefix(self):
        self.assertTrue(_is_public("/api/public/report/inspect/inspect_1.pdf"))
        self.assertFalse(_is_public("/api/report/daily_1/export.pdf"))
        self.assertFalse(_is_public("/api/public/report/daily/daily_1.pdf"))

    async def test_real_middleware_and_router_enforce_public_pdf_boundary(self):
        app = FastAPI()
        app.include_router(reports.router)
        app.add_middleware(AuthenticationMiddleware)

        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            inspect_id = "inspect_public_asgi"
            daily_id = "daily_private_asgi"
            Path(reports_dir, f"{inspect_id}.json").write_text(
                json.dumps(
                    {
                        "id": inspect_id,
                        "type": "inspect",
                        "title": "ASGI 巡检",
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
            Path(reports_dir, f"{daily_id}.json").write_text(
                json.dumps({"id": daily_id, "type": "daily"}),
                encoding="utf-8",
            )
            transport = httpx.ASGITransport(app=app)
            with patch.object(reports, "REPORTS_DIR", reports_dir):
                async with httpx.AsyncClient(
                    transport=transport, base_url="http://testserver"
                ) as client:
                    public = await client.get(
                        f"/api/public/report/inspect/{inspect_id}.pdf"
                    )
                    non_inspect = await client.get(
                        f"/api/public/report/inspect/{daily_id}.pdf"
                    )
                    private_export = await client.get(
                        f"/api/report/{inspect_id}/export.pdf"
                    )
                    lookalike = await client.get(
                        f"/api/public/report/inspect-lookalike/{inspect_id}.pdf"
                    )

        self.assertEqual(public.status_code, 200)
        self.assertTrue(public.content.startswith(b"%PDF"))
        self.assertTrue(public.headers["content-disposition"].startswith("inline;"))
        self.assertEqual(non_inspect.status_code, 404)
        self.assertEqual(private_export.status_code, 401)
        self.assertEqual(lookalike.status_code, 401)
