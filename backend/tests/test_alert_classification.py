import unittest

from services.alert_dedup import alert_types, classify_alert


class AlertClassificationCase(unittest.TestCase):
    def test_infra_alert_classification(self):
        alert = {
            "labels": {
                "alertname": "K8sNodeDiskPressure",
                "severity": "critical",
                "node": "worker-01",
            },
            "annotations": {"summary": "node disk pressure is high"},
        }

        self.assertEqual(classify_alert(alert), "infra")

    def test_business_metric_alert_classification(self):
        alert = {
            "labels": {
                "alertname": "APISuccessRateLow",
                "service": "checkout-service",
                "severity": "warning",
            },
            "annotations": {"summary": "接口成功率低于 99%"},
        }

        self.assertEqual(classify_alert(alert), "business")

    def test_error_log_alert_classification(self):
        alert = {
            "labels": {
                "alertname": "LokiErrorLogsSpike",
                "service": "payment-service",
                "severity": "error",
            },
            "annotations": {
                "summary": "错误日志突增",
                "description": "java.lang.NullPointerException in callback handler",
            },
        }

        self.assertEqual(classify_alert(alert), "log_exception")

    def test_explicit_alert_type_wins(self):
        alert = {
            "labels": {
                "alertname": "CheckoutExceptionBudget",
                "alert_type": "business",
            },
            "annotations": {"summary": "业务异常预算消耗过快"},
        }

        self.assertEqual(classify_alert(alert), "business")

    def test_alert_type_metadata_is_exposed(self):
        keys = {item["key"] for item in alert_types()}
        self.assertEqual(keys, {"infra", "business", "log_exception"})


if __name__ == "__main__":
    unittest.main()
