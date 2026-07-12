import unittest
from unittest.mock import patch

from auth import session


class SessionSecurityCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend_patch = patch.object(session, "_backend", session._MemStore())
        self.limit_patch = patch.object(session, "LOGIN_IP_FAIL_MAX", 2)
        self.backend_patch.start()
        self.limit_patch.start()

    async def asyncTearDown(self):
        self.limit_patch.stop()
        self.backend_patch.stop()

    async def test_ip_limit_counts_unknown_user_failures(self):
        self.assertFalse(await session.is_ip_limited("203.0.113.10"))
        await session.incr_ip_fail("203.0.113.10")
        self.assertFalse(await session.is_ip_limited("203.0.113.10"))
        await session.incr_ip_fail("203.0.113.10")
        self.assertTrue(await session.is_ip_limited("203.0.113.10"))

    async def test_ip_counters_are_independent(self):
        await session.incr_ip_fail("203.0.113.10")
        await session.incr_ip_fail("203.0.113.10")
        self.assertFalse(await session.is_ip_limited("203.0.113.11"))


if __name__ == "__main__":
    unittest.main()
