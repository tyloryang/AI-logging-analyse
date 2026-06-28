import unittest

from routers.events import _normalize_external_event


class EventIngestNormalizeCase(unittest.TestCase):
    def test_jenkins_failure_maps_to_error_event(self):
        event = _normalize_external_event(
            "jenkins",
            {
                "job_name": "order-release",
                "build_number": 42,
                "status": "FAILED",
                "message": "deploy failed",
                "application": "order-service",
            },
        )
        self.assertEqual(event["source"], "jenkins")
        self.assertEqual(event["severity"], "error")
        self.assertEqual(event["labels"]["resource_type"], "jenkins_build")
        self.assertEqual(event["labels"]["resource_id"], "42")

    def test_custom_event_keeps_labels(self):
        event = _normalize_external_event(
            "custom",
            {
                "event_id": "evt-1",
                "title": "Cache warmup",
                "severity": "warning",
                "labels": {"system": "checkout"},
            },
        )
        self.assertEqual(event["id"], "external-custom-evt-1")
        self.assertEqual(event["labels"]["system"], "checkout")
        self.assertEqual(event["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
