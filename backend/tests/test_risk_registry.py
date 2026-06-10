"""风险注册表与 risk_guard 决策表单测。"""
import unittest

from agent.risk_registry import (
    GuardDecision,
    ToolRisk,
    filter_callable_tools,
    risk_guard,
    risk_of,
)


class RiskOfCase(unittest.TestCase):
    def test_known_read_tool(self):
        self.assertEqual(risk_of("query_error_logs"), ToolRisk.READ)

    def test_known_write_high(self):
        self.assertEqual(risk_of("call_mcp_tool"), ToolRisk.WRITE_HIGH)

    def test_unknown_tool_default_high(self):
        self.assertEqual(risk_of("totally_made_up_tool"), ToolRisk.WRITE_HIGH)


class GuardCase(unittest.TestCase):
    def test_read_always_executes(self):
        self.assertEqual(risk_guard("query_error_logs"), GuardDecision.EXECUTE)
        self.assertEqual(
            risk_guard("query_error_logs", confirm_mode="ask", behaviors_auto=False),
            GuardDecision.EXECUTE,
        )

    def test_write_low_needs_auto_or_confirm_mode(self):
        self.assertEqual(
            risk_guard("export_report_pdf", confirm_mode="ask", behaviors_auto=False),
            GuardDecision.APPROVAL,
        )
        self.assertEqual(
            risk_guard("export_report_pdf", confirm_mode="auto"),
            GuardDecision.EXECUTE,
        )
        self.assertEqual(
            risk_guard("export_report_pdf", behaviors_auto=True),
            GuardDecision.EXECUTE,
        )

    def test_write_high_needs_auto_and_confidence(self):
        # auto 但无置信度 → APPROVAL
        self.assertEqual(
            risk_guard("call_mcp_tool", behaviors_auto=True),
            GuardDecision.APPROVAL,
        )
        # auto + 置信度低 → APPROVAL
        self.assertEqual(
            risk_guard("call_mcp_tool", behaviors_auto=True, llm_confidence=0.5),
            GuardDecision.APPROVAL,
        )
        # auto + 置信度足够 → EXECUTE
        self.assertEqual(
            risk_guard("call_mcp_tool", behaviors_auto=True, llm_confidence=0.9),
            GuardDecision.EXECUTE,
        )
        # 无 auto → 即使高置信度也 APPROVAL
        self.assertEqual(
            risk_guard("call_mcp_tool", behaviors_auto=False, llm_confidence=0.99),
            GuardDecision.APPROVAL,
        )

    def test_unknown_tool_defaults_to_approval(self):
        self.assertEqual(
            risk_guard("never_seen_tool", confirm_mode="auto", behaviors_auto=True),
            GuardDecision.APPROVAL,
        )


class FilterCase(unittest.TestCase):
    def test_ask_mode_hides_high_risk(self):
        names = ["query_error_logs", "export_report_pdf", "call_mcp_tool"]
        out = filter_callable_tools(names, confirm_mode="ask")
        self.assertIn("query_error_logs", out)
        self.assertIn("export_report_pdf", out)
        self.assertNotIn("call_mcp_tool", out)

    def test_auto_mode_includes_high(self):
        names = ["query_error_logs", "call_mcp_tool"]
        out = filter_callable_tools(names, confirm_mode="auto")
        self.assertIn("call_mcp_tool", out)


if __name__ == "__main__":
    unittest.main()
