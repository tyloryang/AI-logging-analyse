import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from loki_client import LokiClient


class LokiLogDistributionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = LokiClient("http://loki.test")

    async def asyncTearDown(self):
        await self.client._client.aclose()

    async def test_distribution_returns_exact_total_and_sorted_pod_counts(self):
        self.client._detect_service_label = AsyncMock(return_value="app")
        self.client._detect_namespace_label = AsyncMock(return_value=("namespace", ["prod"]))
        self.client._detect_pod_label = AsyncMock(return_value="pod")
        self.client._instant_query = AsyncMock(
            return_value={
                "status": "success",
                "data": {
                    "resultType": "vector",
                    "result": [
                        {"metric": {"namespace": "prod", "pod": "api-2"}, "value": [1, "7"]},
                        {"metric": {"namespace": "prod", "pod": "api-1"}, "value": [1, "42"]},
                    ],
                },
            }
        )

        result = await self.client.query_log_distribution(
            service="api",
            start_ns=1_000_000_000,
            end_ns=301_000_000_000,
            top_n=10,
        )

        self.assertEqual(result["total_logs"], 49)
        self.assertEqual(result["total_pods"], 2)
        self.assertEqual([item["pod"] for item in result["pods"]], ["api-1", "api-2"])
        self.assertEqual(result["group_labels"], {"namespace": "namespace", "pod": "pod"})
        query = self.client._instant_query.await_args.args[0]
        self.assertIn('sum by (namespace, pod)', query)
        self.assertIn('count_over_time({app="api"}[5m])', query)


class LogRouteMetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_log_page_identifies_returned_rows_as_page_metadata(self):
        fake_loki = types.SimpleNamespace(
            query_logs_page=AsyncMock(
                return_value={
                    "data": [{"timestamp_ns": "2"}, {"timestamp_ns": "1"}],
                    "has_more": True,
                    "next_cursor_ns": 1,
                }
            )
        )
        fake_state = types.ModuleType("state")
        fake_state.loki = fake_loki
        fake_state.analyzer = object()
        fake_state.clusterer = object()

        previous = sys.modules.pop("routers.logs", None)
        try:
            with patch.dict(sys.modules, {"state": fake_state}):
                logs_router = importlib.import_module("routers.logs")
                result = await logs_router.get_logs(
                    service=None,
                    services=None,
                    hours=1,
                    limit=200,
                    level=None,
                    keyword=None,
                    keywords=None,
                    keyword_mode="and",
                    exclude_keywords=None,
                    labels=[],
                    group_label=None,
                    group_value=None,
                    start_time="2026-07-12T04:34:34",
                    end_time="2026-07-12T04:39:34",
                    cursor_ns=None,
                )
        finally:
            sys.modules.pop("routers.logs", None)
            if previous is not None:
                sys.modules["routers.logs"] = previous

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["returned_count"], 2)
        self.assertEqual(result["page_size"], 200)
        self.assertTrue(result["truncated"])


if __name__ == "__main__":
    unittest.main()
