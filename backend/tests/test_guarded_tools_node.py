"""LangGraph guarded_tools_node 行为单测：
  - READ 工具直接放行并真实执行
  - WRITE_HIGH 工具被拦截，返回审批提示 ToolMessage
  - 未注册工具兜底返回错误
"""
import asyncio
import os
import unittest
from unittest.mock import patch


class _MockToolCall(dict):
    """LangChain tool_call 的最小协议：dict with name/args/id."""


class _MockAIMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class _MockState(dict):
    pass


class GuardedToolsNodeCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # 给 ai_analyzer 凑环境，graph import 链需要
        os.environ.setdefault("AI_PROVIDER", "anthropic")
        os.environ.setdefault("ANTHROPIC_API_KEY", "sk-fake")
        os.environ.setdefault("AI_MODEL", "claude-opus-4-7")
        from agent.graph import _build_guarded_tools_node

        # 构造两个伪 tool：一个 READ（query_error_logs 名字命中风险表）一个 HIGH
        class _FakeTool:
            def __init__(self, name, ret):
                self.name = name
                self._ret = ret
                self.invoked_with = None

            async def ainvoke(self, args, config=None):
                self.invoked_with = (args, config)
                return self._ret

        self.read_tool = _FakeTool("query_error_logs", "READ_RESULT")
        self.high_tool = _FakeTool("execute_ssh_command", "SSH_RESULT")
        self.node = _build_guarded_tools_node([self.read_tool, self.high_tool])

    async def test_read_tool_executes(self):
        msg = _MockAIMessage(
            tool_calls=[
                _MockToolCall({"name": "query_error_logs", "args": {"service": "x"}, "id": "c1"})
            ]
        )
        state = _MockState({"messages": [msg]})
        # confirm_mode=ask 也应放行 READ
        with patch(
            "routers.agent_config.get_agent_runtime_context",
            return_value={"confirm_mode": "ask", "behaviors_auto": False},
        ):
            out = await self.node(state, config={"configurable": {}})

        messages = out["messages"]
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].name, "query_error_logs")
        self.assertEqual(messages[0].content, "READ_RESULT")
        self.assertEqual(self.read_tool.invoked_with[0], {"service": "x"})

    async def test_high_risk_tool_blocked_in_ask_mode(self):
        msg = _MockAIMessage(
            tool_calls=[
                _MockToolCall({"name": "execute_ssh_command", "args": {"host": "h", "command": "ls"}, "id": "c2"})
            ]
        )
        state = _MockState({"messages": [msg]})
        with patch(
            "routers.agent_config.get_agent_runtime_context",
            return_value={"confirm_mode": "ask", "behaviors_auto": False},
        ):
            out = await self.node(state, config={"configurable": {}})

        messages = out["messages"]
        self.assertEqual(len(messages), 1)
        self.assertIn("RiskGuard", messages[0].content)
        self.assertIn("execute_ssh_command", messages[0].content)
        # 真工具不应被调用
        self.assertIsNone(self.high_tool.invoked_with)

    async def test_high_risk_executes_in_auto_mode_via_configurable(self):
        # behaviors_auto=True 但 confidence 未传 → 仍 APPROVAL（HIGH 需要 0.85+）
        msg = _MockAIMessage(
            tool_calls=[
                _MockToolCall({"name": "execute_ssh_command", "args": {"host": "h", "command": "ls"}, "id": "c3"})
            ]
        )
        state = _MockState({"messages": [msg]})
        with patch(
            "routers.agent_config.get_agent_runtime_context",
            return_value={"confirm_mode": "auto", "behaviors_auto": True},
        ):
            out = await self.node(state, config={"configurable": {}})

        # HIGH 即使 auto 模式也会被拦（没传 confidence）
        self.assertIn("RiskGuard", out["messages"][0].content)
        self.assertIsNone(self.high_tool.invoked_with)

    async def test_unknown_tool_returns_error(self):
        msg = _MockAIMessage(
            tool_calls=[
                _MockToolCall({"name": "never_registered_tool", "args": {}, "id": "c4"})
            ]
        )
        state = _MockState({"messages": [msg]})
        with patch(
            "routers.agent_config.get_agent_runtime_context",
            return_value={"confirm_mode": "ask", "behaviors_auto": False},
        ):
            out = await self.node(state, config={"configurable": {}})

        # 未注册工具：默认按 WRITE_HIGH 处理，先被 guard 拦截，根本不会落到 tool_map 兜底分支
        # 这里其实测的是"未知工具默认从严"的 e2e 表现
        self.assertEqual(len(out["messages"]), 1)
        content = out["messages"][0].content
        self.assertTrue(
            "RiskGuard" in content or "未注册" in content,
            f"unexpected content: {content!r}",
        )

    async def test_no_tool_calls_returns_empty(self):
        msg = _MockAIMessage(tool_calls=[])
        state = _MockState({"messages": [msg]})
        out = await self.node(state, config={})
        self.assertEqual(out, {"messages": []})


if __name__ == "__main__":
    unittest.main()
