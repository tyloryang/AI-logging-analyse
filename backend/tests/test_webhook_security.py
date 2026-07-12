import unittest
from unittest.mock import patch

from fastapi import HTTPException

from services.webhook_security import require_ingest_token


class WebhookSecurityCase(unittest.TestCase):
    def _require(self, direct_token=None, authorization=None):
        require_ingest_token(
            token_env="TEST_INGEST_TOKEN",
            direct_token=direct_token,
            authorization=authorization,
            allow_unauthenticated_env="TEST_ALLOW_UNAUTHENTICATED",
        )

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_configuration_fails_closed(self):
        with self.assertRaises(HTTPException) as raised:
            self._require()
        self.assertEqual(raised.exception.status_code, 503)

    @patch.dict("os.environ", {"TEST_INGEST_TOKEN": "secret"}, clear=True)
    def test_rejects_invalid_token(self):
        with self.assertRaises(HTTPException) as raised:
            self._require(direct_token="wrong")
        self.assertEqual(raised.exception.status_code, 401)

    @patch.dict("os.environ", {"TEST_INGEST_TOKEN": "secret"}, clear=True)
    def test_accepts_header_and_bearer_tokens(self):
        self._require(direct_token="secret")
        self._require(authorization="Bearer secret")

    @patch.dict(
        "os.environ",
        {"TEST_ALLOW_UNAUTHENTICATED": "1"},
        clear=True,
    )
    def test_explicit_development_opt_out(self):
        self._require()


if __name__ == "__main__":
    unittest.main()
