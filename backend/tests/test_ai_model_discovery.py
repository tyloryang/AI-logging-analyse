import unittest

from services.ai_model_discovery import model_discovery_url, normalize_discovered_models


class AIModelDiscoveryCase(unittest.TestCase):
    def test_normalizes_openai_and_local_gateway_models(self):
        models = normalize_discovered_models({
            "data": [
                {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
                {"id": "qwen3-32b", "name": "Qwen 3 32B", "provider": "local"},
                {"id": "gpt-4o", "display_name": "GPT-4o"},
            ]
        })

        self.assertEqual([model["id"] for model in models], ["gpt-4o", "qwen3-32b"])
        self.assertEqual(models[0]["name"], "GPT-4o")
        self.assertEqual(models[1]["owned_by"], "local")

    def test_accepts_models_array_and_string_items(self):
        models = normalize_discovered_models({
            "models": ["llama3.1", {"model": "deepseek-r1", "type": "chat"}]
        })

        self.assertEqual([model["id"] for model in models], ["deepseek-r1", "llama3.1"])
        self.assertEqual(models[0]["type"], "chat")

    def test_builds_provider_specific_model_urls(self):
        self.assertEqual(
            model_discovery_url("openai", "http://127.0.0.1:11434/v1/"),
            "http://127.0.0.1:11434/v1/models",
        )
        self.assertEqual(
            model_discovery_url("anthropic"),
            "https://api.anthropic.com/v1/models",
        )
        with self.assertRaises(ValueError):
            model_discovery_url("openai", "")


if __name__ == "__main__":
    unittest.main()
