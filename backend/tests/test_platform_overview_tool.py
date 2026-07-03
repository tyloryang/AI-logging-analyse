"""Platform overview tool tests."""
from __future__ import annotations

import json
import unittest
from pathlib import Path


class PlatformOverviewToolCase(unittest.IsolatedAsyncioTestCase):
    async def test_overview_returns_platform_facts_without_secrets(self):
        from agent.tool_modules.platform import get_platform_overview

        output = await get_platform_overview.ainvoke({"scope": "all"})

        self.assertIn("基础配置", output)
        self.assertIn("平台库存", output)
        self.assertIn("AI 助手配置", output)
        self.assertIn("MCP 接入", output)

        data_dir = Path(__file__).resolve().parents[1] / "data"
        sensitive_values: set[str] = set()
        for filename in (
            "settings.json",
            "agent_config.json",
            "cmdb_hosts.json",
            "groups.json",
            "es_clusters.json",
            "redis_clusters.json",
            "kafka_clusters.json",
            "jenkins.json",
            "k8s_clusters.json",
        ):
            path = data_dir / filename
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            self._collect_sensitive_values(data, sensitive_values)

        for value in sensitive_values:
            self.assertNotIn(value, output)

    def _collect_sensitive_values(self, value, out: set[str]) -> None:
        sensitive_tokens = (
            "password",
            "token",
            "api_key",
            "secret",
            "webhook",
            "kubeconfig",
            "ssh_key",
        )
        if isinstance(value, dict):
            for key, child in value.items():
                key_lower = str(key).lower()
                if any(token in key_lower for token in sensitive_tokens):
                    if isinstance(child, str) and len(child.strip()) >= 8:
                        out.add(child.strip())
                    continue
                self._collect_sensitive_values(child, out)
        elif isinstance(value, list):
            for item in value:
                self._collect_sensitive_values(item, out)


if __name__ == "__main__":
    unittest.main()
