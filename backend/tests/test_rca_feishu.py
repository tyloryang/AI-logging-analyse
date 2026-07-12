import unittest

from notifier import _build_feishu_rca_card


class RCAFeishuCardTests(unittest.TestCase):
    def test_card_contains_only_top_candidate_confidence_and_rca_link(self):
        record = {
            "id": "rca-1",
            "service": "analyse",
            "alert_name": "InterfaceSlow",
            "hypotheses": [
                {"title": "慢 SQL 候选 #1", "confidence": "high", "score": 90},
                {"title": "候选 #2", "confidence": "medium", "score": 70},
            ],
        }

        card = _build_feishu_rca_card(
            record,
            report_url="https://aiops.example/#/aiops/rca?rca_id=rca-1",
        )
        content = card["card"]["elements"][0]["text"]["content"]
        actions = card["card"]["elements"][1]["actions"]

        self.assertIn("慢 SQL 候选 #1", content)
        self.assertIn("高置信度", content)
        self.assertNotIn("候选 #2", content)
        self.assertEqual(actions[0]["url"], "https://aiops.example/#/aiops/rca?rca_id=rca-1")


if __name__ == "__main__":
    unittest.main()
