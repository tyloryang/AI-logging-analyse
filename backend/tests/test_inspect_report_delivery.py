import json
import re
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
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
            async def register_meta(saved_report):
                report_path = Path(tmp, f"{saved_report['id']}.json")
                self.assertTrue(report_path.is_file())

            save_meta = AsyncMock(side_effect=register_meta)
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
            saved = json.loads(
                Path(tmp, f"{report['id']}.json").read_text(encoding="utf-8")
            )

        self.assertEqual(saved["type"], "inspect")
        self.assertEqual(saved["group_id"], "grp-1")
        self.assertEqual(saved["all_hosts"][0]["ip"], "10.0.0.8")
        self.assertEqual(saved["ai_analysis"], "磁盘容量需要处理。")
        self.assertEqual(saved["host_summary"]["warning"], 1)
        save_meta.assert_awaited_once_with(report)

    async def test_untrusted_group_ids_cannot_control_the_report_path(self):
        group_ids = [
            "grp/unsafe",
            "grp/../nested",
            "核心组" * 30,
            "x" * 100,
        ]
        with tempfile.TemporaryDirectory() as tmp:
            reports_dir = Path(tmp)
            with (
                patch.object(inspect_report_delivery, "REPORTS_DIR", reports_dir),
                patch.object(
                    inspect_report_delivery,
                    "save_report_meta",
                    AsyncMock(),
                ),
            ):
                for group_id in group_ids:
                    with self.subTest(group_id=group_id):
                        report = await inspect_report_delivery.save_group_inspect_report(
                            [],
                            group_id=group_id,
                            group_name="边界组",
                            ai_text="",
                        )
                        report_path = reports_dir / f"{report['id']}.json"
                        saved = json.loads(report_path.read_text(encoding="utf-8"))

                        self.assertRegex(report["id"], r"^[A-Za-z0-9_-]{1,64}$")
                        self.assertLessEqual(len(report["id"]), 64)
                        self.assertEqual(report_path.resolve().parent, reports_dir.resolve())
                        self.assertEqual(report["group_id"], group_id)
                        self.assertEqual(saved["group_id"], group_id)

            self.assertFalse(any(path.is_dir() for path in reports_dir.iterdir()))

    async def test_repeated_group_deliveries_get_distinct_report_ids(self):
        fixed_now = datetime(2026, 7, 17, 1, 2, 3, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(inspect_report_delivery, "REPORTS_DIR", Path(tmp)),
                patch.object(
                    inspect_report_delivery,
                    "save_report_meta",
                    AsyncMock(),
                ),
                patch("report_builder.datetime") as report_datetime,
            ):
                report_datetime.now.return_value = fixed_now
                first = await inspect_report_delivery.save_group_inspect_report(
                    [], "grp-1", "核心组", ""
                )
                second = await inspect_report_delivery.save_group_inspect_report(
                    [], "grp-1", "核心组", ""
                )

        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", first["id"]))
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", second["id"]))

    async def test_nested_metrics_are_normalized_for_pdf_without_mutating_input(self):
        results = [{
            "instance": "10.0.0.8:9100",
            "ip": "10.0.0.8",
            "hostname": "app-1",
            "os": "Linux",
            "state": "up",
            "group": "grp-1",
            "group_name": "核心组",
            "overall": "normal",
            "metrics": {
                "cpu_usage": 12.5,
                "mem_usage": 34.5,
                "mem_total_gb": 64,
                "load1": 0.8,
                "net_recv_mbps": 1.2,
                "disk_write_mbps": 3.4,
                "tcp_estab": 42,
                "uptime_seconds": 86400,
            },
            "checks": [],
            "partitions": [{"mountpoint": "/", "usage_pct": 20}],
            "process_top10": [{"service": "java", "cpu": 10, "mem": 8}],
        }]
        original_results = deepcopy(results)

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(inspect_report_delivery, "REPORTS_DIR", Path(tmp)),
                patch.object(
                    inspect_report_delivery,
                    "save_report_meta",
                    AsyncMock(),
                ),
            ):
                report = await inspect_report_delivery.save_group_inspect_report(
                    results,
                    group_id="grp-1",
                    group_name="核心组",
                    ai_text="运行正常。",
                )
            saved = json.loads(
                Path(tmp, f"{report['id']}.json").read_text(encoding="utf-8")
            )

        host = saved["all_hosts"][0]
        self.assertEqual(host.get("cpu_pct"), 12.5)
        self.assertEqual(host.get("mem_pct"), 34.5)
        self.assertEqual(host.get("mem_total"), 64)
        self.assertEqual(host.get("load1"), 0.8)
        self.assertEqual(host.get("net_recv"), 1.2)
        self.assertEqual(host.get("disk_write"), 3.4)
        self.assertEqual(host.get("tcp_estab"), 42)
        self.assertEqual(host.get("uptime_s"), 86400)
        self.assertNotIn("metrics", host)
        self.assertEqual(saved["group_sections"][0]["hosts"][0], host)
        self.assertEqual(results, original_results)

        from services.report_pdf import build_report_pdf

        self.assertTrue(build_report_pdf(saved).startswith(b"%PDF"))

    async def test_already_flattened_host_metrics_are_preserved(self):
        results = [{
            "ip": "10.0.0.9",
            "hostname": "app-2",
            "overall": "normal",
            "cpu_pct": 7.5,
            "mem_pct": 18.5,
            "mem_total": 32,
            "checks": [],
            "partitions": [],
            "process_top10": [],
        }]

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(inspect_report_delivery, "REPORTS_DIR", Path(tmp)),
                patch.object(
                    inspect_report_delivery,
                    "save_report_meta",
                    AsyncMock(),
                ),
            ):
                report = await inspect_report_delivery.save_group_inspect_report(
                    results,
                    group_id="grp-2",
                    group_name="应用组",
                    ai_text="运行正常。",
                )

        host = report["all_hosts"][0]
        self.assertEqual(host.get("cpu_pct"), 7.5)
        self.assertEqual(host.get("mem_pct"), 18.5)
        self.assertEqual(host.get("mem_total"), 32)
