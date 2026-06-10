"""工具分组视图单测：分组完备性 + 按 confirm_mode 裁剪。"""
import unittest


class DomainCompletenessCase(unittest.TestCase):
    def test_all_tool_names_unique(self):
        from agent.tool_groups import ALL_TOOL_NAMES
        self.assertEqual(len(ALL_TOOL_NAMES), len(set(ALL_TOOL_NAMES)))

    def test_read_only_subset(self):
        from agent.tool_groups import ALL_TOOL_NAMES, READ_ONLY_TOOLS
        self.assertTrue(set(READ_ONLY_TOOLS).issubset(set(ALL_TOOL_NAMES)))
        self.assertIn("query_error_logs", READ_ONLY_TOOLS)
        self.assertNotIn("call_mcp_tool", READ_ONLY_TOOLS)
        self.assertNotIn("execute_ssh_command", READ_ONLY_TOOLS)

    def test_safe_auto_contains_low_risk(self):
        from agent.tool_groups import SAFE_AUTO_TOOLS
        self.assertIn("export_report_pdf", SAFE_AUTO_TOOLS)
        self.assertIn("firecrawl_search_web", SAFE_AUTO_TOOLS)
        # high risk 不应进入 SAFE_AUTO
        self.assertNotIn("execute_ssh_command", SAFE_AUTO_TOOLS)
        self.assertNotIn("jenkins_build_job", SAFE_AUTO_TOOLS)


class RuntimeFilterCase(unittest.TestCase):
    def test_ask_mode_hides_high_risk(self):
        from agent.tool_groups import names_for_runtime
        names = names_for_runtime(confirm_mode="ask")
        self.assertIn("query_error_logs", names)
        self.assertNotIn("execute_ssh_command", names)
        self.assertNotIn("call_mcp_tool", names)
        self.assertNotIn("jenkins_build_job", names)

    def test_auto_mode_includes_high(self):
        from agent.tool_groups import names_for_runtime
        names = names_for_runtime(confirm_mode="auto")
        self.assertIn("call_mcp_tool", names)
        self.assertIn("execute_ssh_command", names)


class ToolsForRuntimeCase(unittest.TestCase):
    """模拟 graph.py 用法：传入对象列表按 confirm_mode 裁剪。"""

    class _FakeTool:
        def __init__(self, name):
            self.name = name

    def test_filter_preserves_identity(self):
        from agent.tool_groups import tools_for_runtime
        t1 = self._FakeTool("query_error_logs")
        t2 = self._FakeTool("execute_ssh_command")
        t3 = self._FakeTool("get_host_metrics")
        out = tools_for_runtime([t1, t2, t3], confirm_mode="ask")
        names = [t.name for t in out]
        self.assertIn("query_error_logs", names)
        self.assertIn("get_host_metrics", names)
        self.assertNotIn("execute_ssh_command", names)


if __name__ == "__main__":
    unittest.main()
