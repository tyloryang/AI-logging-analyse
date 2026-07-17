import unittest

from notifier import _build_feishu_group_inspect_card, _build_feishu_inspect_card


def _action_urls(card: dict) -> list[str]:
    urls = []
    for element in card["card"]["elements"]:
        if element.get("tag") != "action":
            continue
        urls.extend(action.get("url", "") for action in element.get("actions", []))
    return [url for url in urls if url]


class FeishuInspectPdfLinkTests(unittest.TestCase):
    def test_public_url_uses_app_url_and_report_id(self):
        try:
            from services.inspect_report_delivery import build_public_inspect_pdf_url
        except ImportError as exc:
            self.fail(f"public inspection URL helper is missing: {exc}")

        self.assertEqual(
            build_public_inspect_pdf_url("inspect_20260717010101_grp-1", "https://aiops.example/"),
            "https://aiops.example/api/public/report/inspect/inspect_20260717010101_grp-1.pdf",
        )
        self.assertEqual(build_public_inspect_pdf_url("inspect_1", ""), "")

    def test_full_and_group_cards_include_public_pdf_button(self):
        url = "https://aiops.example/api/public/report/inspect/inspect_1.pdf"
        report = {
            "type": "inspect",
            "title": "主机巡检日报",
            "health_score": 80,
            "host_summary": {"total": 1, "normal": 1, "warning": 0, "critical": 0},
        }
        result = [{"overall": "normal", "hostname": "host-1", "checks": []}]

        full_card = _build_feishu_inspect_card(report, report_url=url)
        group_card = _build_feishu_group_inspect_card("核心组", result, report_url=url)

        self.assertEqual(_action_urls(full_card), [url])
        self.assertEqual(_action_urls(group_card), [url])
        self.assertEqual(
            full_card["card"]["elements"][-1]["actions"][0]["text"]["content"],
            "查看完整巡检 PDF",
        )
        self.assertEqual(
            group_card["card"]["elements"][-1]["actions"][0]["text"]["content"],
            "查看完整巡检 PDF",
        )

    def test_cards_omit_action_when_url_is_empty(self):
        report = {"type": "inspect", "health_score": 100, "host_summary": {}}
        self.assertEqual(_action_urls(_build_feishu_inspect_card(report)), [])
        self.assertEqual(_action_urls(_build_feishu_group_inspect_card("核心组", [])), [])
