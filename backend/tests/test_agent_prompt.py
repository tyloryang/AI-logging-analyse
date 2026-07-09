"""AIOps Agent system prompt regression tests."""
import unittest


class AgentPromptCase(unittest.TestCase):
    def test_chat_prompt_uses_on_demand_tool_policy(self):
        from agent.graph import _build_system_prompt

        prompt = _build_system_prompt("chat", mcps=[])

        self.assertIn("【按需工具策略】", prompt)
        self.assertIn("不要默认串行执行 get_services_list", prompt)
        self.assertNotIn("【四层思考框架", prompt)
        self.assertNotIn("多源并发收集数据", prompt)

    def test_diagnostic_modes_keep_four_layer_prompt(self):
        from agent.graph import _build_system_prompt

        for mode in ("rca", "inspect"):
            with self.subTest(mode=mode):
                prompt = _build_system_prompt(mode, mcps=[])
                self.assertIn("【四层思考框架", prompt)

    def test_existing_system_prompt_is_replaced(self):
        from langchain_core.messages import HumanMessage, SystemMessage

        from agent.graph import _with_current_system_prompt

        messages = [
            SystemMessage(content="old prompt"),
            HumanMessage(content="hello"),
        ]
        out = _with_current_system_prompt(messages, "new prompt")

        self.assertEqual(out[0].content, "new prompt")
        self.assertEqual(out[1].content, "hello")
        self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
