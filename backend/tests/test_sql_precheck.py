import unittest

from routers.tickets import analyze_sql_risk


class SqlPrecheckCase(unittest.TestCase):
    def test_delete_without_where_is_critical(self):
        result = analyze_sql_risk("DELETE FROM orders")
        self.assertEqual(result["risk_level"], "critical")
        self.assertTrue(any(item["rule"] == "missing_where" for item in result["findings"]))

    def test_select_is_low_risk(self):
        result = analyze_sql_risk("SELECT id, name FROM users WHERE id = 1")
        self.assertEqual(result["risk_level"], "low")

    def test_drop_is_critical(self):
        result = analyze_sql_risk("DROP TABLE payments")
        self.assertEqual(result["risk_level"], "critical")
        self.assertTrue(any(item["rule"] == "destructive_ddl" for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
