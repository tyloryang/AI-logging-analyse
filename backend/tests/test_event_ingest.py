import unittest
from datetime import datetime, timezone

from routers.events import (
    _EVENT_ERROR_KEYWORDS,
    _event_is_visible_after_clear,
    _event_matches_error_keywords,
    _normalize_external_event,
    _resolve_error_keywords,
)


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

    def test_event_error_keywords_include_java_exception_filters(self):
        self.assertIn("NullPointerException", _EVENT_ERROR_KEYWORDS)
        self.assertIn("OutOfMlemoryError", _EVENT_ERROR_KEYWORDS)
        self.assertIn("IllegalAAccessException", _EVENT_ERROR_KEYWORDS)

    def test_event_error_keyword_aliases_match_common_spellings(self):
        memory_keywords = _resolve_error_keywords("OutOfMlemoryError")
        access_keywords = _resolve_error_keywords("IllegalAAccessException")
        bounds_keywords = _resolve_error_keywords("ArrayIndexOutOfBoundException")

        self.assertTrue(_event_matches_error_keywords("java.lang.OutOfMemoryError: heap", memory_keywords))
        self.assertTrue(_event_matches_error_keywords("java.lang.IllegalAccessException", access_keywords))
        self.assertTrue(_event_matches_error_keywords("java.lang.ArrayIndexOutOfBoundsException", bounds_keywords))
        self.assertFalse(_event_matches_error_keywords("plain error without java exception", memory_keywords))

    def test_clear_cutoff_hides_history_but_keeps_new_events(self):
        cutoff = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)
        self.assertFalse(_event_is_visible_after_clear(
            {"time": "2026-07-10T07:59:59Z", "status": "active"},
            cutoff,
        ))
        self.assertTrue(_event_is_visible_after_clear(
            {"time": "2026-07-10T08:00:01Z", "status": "active"},
            cutoff,
        ))

    def test_clear_cutoff_keeps_current_firing_alerts(self):
        cutoff = datetime(2026, 7, 10, 8, 0, tzinfo=timezone.utc)
        self.assertTrue(_event_is_visible_after_clear(
            {"time": "2026-07-10T07:00:00Z", "status": "firing"},
            cutoff,
        ))


if __name__ == "__main__":
    unittest.main()
