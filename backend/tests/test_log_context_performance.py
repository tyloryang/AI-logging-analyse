import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


class LogContextPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_time_window_failure_does_not_retry_with_24_hours(self):
        fake_state = types.ModuleType("state")
        fake_state.loki = types.SimpleNamespace(query_log_context=AsyncMock(side_effect=RuntimeError("timeout")))
        fake_state.analyzer = object()
        fake_state.clusterer = object()

        previous = sys.modules.pop("routers.logs", None)
        try:
            with patch.dict(sys.modules, {"state": fake_state}):
                logs_router = importlib.import_module("routers.logs")
                result = await logs_router.get_log_context(
                    timestamp_ns=1783831134023198872,
                    service="node-exporter",
                    line_prefix="anchor",
                    labels_json='{"app":"node-exporter"}',
                    hours=24,
                    before=20,
                    after=20,
                    start_time="2026-07-12T04:34:34",
                    end_time="2026-07-12T04:39:34",
                )
        finally:
            sys.modules.pop("routers.logs", None)
            if previous is not None:
                sys.modules["routers.logs"] = previous

        self.assertEqual(fake_state.loki.query_log_context.await_count, 1)
        self.assertTrue(result["degraded"])
        self.assertEqual(result["anchor_index"], 0)
        self.assertIn("timeout", result["error"])


if __name__ == "__main__":
    unittest.main()
