import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from routers.agent import _resolve_workspace
from routers.agent_config import _serialize_sa_public


class AgentWorkspaceSecurityCase(unittest.TestCase):
    @patch.dict("os.environ", {"AIOPS_AGENT_WORKSPACE_ROOTS": ""}, clear=False)
    def test_rejects_workspace_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(HTTPException) as raised:
                _resolve_workspace(temp_dir)
        self.assertEqual(raised.exception.status_code, 403)

    def test_accepts_explicit_workspace_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                "os.environ",
                {"AIOPS_AGENT_WORKSPACE_ROOTS": temp_dir},
                clear=False,
            ):
                resolved = _resolve_workspace(temp_dir)
        self.assertEqual(resolved, Path(temp_dir).resolve())


class AgentConfigSecretCase(unittest.TestCase):
    def test_service_account_tokens_are_masked_without_mutating_source(self):
        source = [{"id": "sa-1", "token": "super-secret-token"}]
        public = _serialize_sa_public(source)

        self.assertEqual(public[0]["token"], "sup***en")
        self.assertTrue(public[0]["token_set"])
        self.assertEqual(source[0]["token"], "super-secret-token")

    def test_empty_service_account_token_is_omitted(self):
        public = _serialize_sa_public([{"id": "sa-1", "token": ""}])
        self.assertNotIn("token", public[0])
        self.assertFalse(public[0]["token_set"])


if __name__ == "__main__":
    unittest.main()
