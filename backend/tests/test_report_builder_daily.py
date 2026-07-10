import unittest

import report_builder


class DailyReportSummaryTests(unittest.TestCase):
    def test_service_errors_are_summarized_without_log_counts(self):
        summaries, keywords = report_builder.summarize_service_errors(
            {"order-service": 12, "payment-service": 4},
            [
                {
                    "labels": {"app": "order-service"},
                    "line": "java.net.ConnectException: Connection refused",
                },
                {
                    "labels": {"app": "payment-service"},
                    "line": "java.sql.SQLException: deadlock found",
                },
            ],
        )

        by_service = {item["service"]: item for item in summaries}
        self.assertIn("连接拒绝", by_service["order-service"]["summary"])
        self.assertIn("SQL异常", by_service["payment-service"]["summary"])
        self.assertNotIn("12 条", by_service["order-service"]["summary"])
        self.assertEqual(keywords[0]["count"], 1)

    def test_missing_samples_are_reported_as_insufficient(self):
        summaries, keywords = report_builder.summarize_service_errors(
            {"inventory-service": 2},
            [],
        )

        self.assertIn("样本不足", summaries[0]["summary"])
        self.assertEqual(keywords, [])

    def test_slowlog_prompt_is_result_and_action_oriented(self):
        prompt = report_builder.build_slowlog_ai_prompt({
            "host_results": [{
                "host_ip": "10.0.0.9",
                "total": 2,
                "alert_count": 1,
                "max_query_time": 12,
                "top_clusters": [],
            }],
            "top_slow": [{
                "host_ip": "10.0.0.9",
                "query_time": 12,
                "rows_examined": 10000,
                "sql_brief": "select * from orders",
            }],
            "total_queries": 2,
            "alert_queries": 1,
            "avg_query_time": 7,
            "max_query_time": 12,
            "date_from": "2026-07-08",
            "date_to": "2026-07-09",
            "_threshold_sec": 1,
            "_alert_sec": 10,
            "_all_entries": [],
        })

        self.assertIn("P0/P1/P2", prompt)
        self.assertIn("EXPLAIN", prompt)
        self.assertIn("不要臆造字段", prompt)


class InterfaceStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_interface_status_prioritizes_5xx_and_latency(self):
        old_query = report_builder.prom.query_instant

        async def fake_query(query, timeout=20):
            metric = {
                "application": "order-service",
                "uri": "/api/orders",
                "method": "GET",
            }
            if 'status=~"5.."' in query:
                return [{"metric": metric, "value": [0, "8"]}]
            if "histogram_quantile" in query:
                return [{"metric": metric, "value": [0, "2200"]}]
            return [{"metric": metric, "value": [0, "100"]}]

        report_builder.prom.query_instant = fake_query
        try:
            result = await report_builder.collect_interface_status()
        finally:
            report_builder.prom.query_instant = old_query

        self.assertTrue(result["available"])
        self.assertEqual(result["status"], "critical")
        self.assertEqual(result["abnormal_interfaces"], 1)
        self.assertEqual(result["rows"][0]["error_ratio"], 8.0)
        self.assertEqual(result["rows"][0]["p95_ms"], 2200.0)


if __name__ == "__main__":
    unittest.main()
