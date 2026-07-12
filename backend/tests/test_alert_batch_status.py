import json
import tempfile
import unittest
from pathlib import Path

import services.alert_dedup as alert_dedup


class AlertBatchStatusCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_data_file = alert_dedup._DATA_FILE
        alert_dedup._DATA_FILE = Path(self.temp_dir.name) / "alert_groups.json"
        alert_dedup._DATA_FILE.write_text(
            json.dumps(
                {
                    "groups": {
                        "alert-a": {"id": "alert-a", "status": "new"},
                        "alert-b": {"id": "alert-b", "status": "grouped"},
                        "alert-c": {"id": "alert-c", "status": "resolved"},
                    },
                    "suppressed": {},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        alert_dedup._DATA_FILE = self.original_data_file
        self.temp_dir.cleanup()

    def test_batch_resolve_updates_existing_groups_and_reports_missing(self):
        result = alert_dedup.update_groups_status(
            ["alert-a", "alert-b", "missing", "alert-a"],
            "resolved",
        )

        self.assertEqual(result["requested"], 3)
        self.assertEqual(result["updated"], ["alert-a", "alert-b"])
        self.assertEqual(result["missing"], ["missing"])
        state = alert_dedup._load()
        self.assertEqual(state["groups"]["alert-a"]["status"], "resolved")
        self.assertIn("resolved_at", state["groups"]["alert-b"])

    def test_batch_suppress_skips_resolved_and_already_suppressed_groups(self):
        alert_dedup.update_groups_status(["alert-a"], "suppressed")

        result = alert_dedup.update_groups_status(
            ["alert-a", "alert-b", "alert-c"],
            "suppressed",
        )

        self.assertEqual(result["updated"], ["alert-b"])
        self.assertEqual(result["skipped"], ["alert-a", "alert-c"])
        state = alert_dedup._load()
        self.assertIn("rca|alert-b", state["suppressed"])


if __name__ == "__main__":
    unittest.main()
