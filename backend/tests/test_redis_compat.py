import unittest
from unittest.mock import patch

import auth.session as session


class RedisCompatibilityCase(unittest.TestCase):
    def test_session_client_forces_resp2_for_redis5(self):
        previous_backend = session._backend
        previous_url = session.REDIS_URL
        fake_client = object()
        session._backend = None
        session.REDIS_URL = "redis://:password@redis.example:6379/0"
        try:
            with patch("redis.asyncio.from_url", return_value=fake_client) as from_url:
                self.assertIs(session._get_backend(), fake_client)
                from_url.assert_called_once_with(
                    session.REDIS_URL,
                    decode_responses=True,
                    protocol=2,
                )
        finally:
            session._backend = previous_backend
            session.REDIS_URL = previous_url


if __name__ == "__main__":
    unittest.main()
