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
            saved = json.loads(
                Path(tmp, f"{report['id']}.json").read_text(encoding="utf-8")
            )

        self.assertEqual(saved["type"], "inspect")
        self.assertEqual(saved["group_id"], "grp-1")
        self.assertEqual(saved["all_hosts"][0]["ip"], "10.0.0.8")
        self.assertEqual(saved["ai_analysis"], "磁盘容量需要处理。")
        self.assertEqual(saved["host_summary"]["warning"], 1)
        save_meta.assert_awaited_once()
