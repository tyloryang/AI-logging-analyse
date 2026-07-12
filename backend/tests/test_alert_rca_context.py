import unittest
import importlib
import sys
import types
from unittest.mock import patch


fake_state = types.ModuleType("state")
fake_state.load_groups = lambda: []
with patch.dict(sys.modules, {"state": fake_state}):
    _collect_alert_labels = importlib.import_module("routers.alerts")._collect_alert_labels


class AlertRCAContextTests(unittest.TestCase):
    def test_original_alert_start_time_is_forwarded_to_rca_labels(self):
        labels = _collect_alert_labels({
            "group_labels": {"alertname": "InterfaceSlow"},
            "common_labels": {"cluster": "z1", "namespace": "analyse"},
            "raw_alerts": [{
                "labels": {"service": "analyse", "pod": "analyse-abc"},
                "startsAt": "2026-07-12T10:01:00Z",
            }],
        })

        self.assertEqual(labels["startsAt"], "2026-07-12T10:01:00Z")
        self.assertEqual(labels["pod"], "analyse-abc")


if __name__ == "__main__":
    unittest.main()
