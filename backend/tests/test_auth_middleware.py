import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.requests import Request
from starlette.responses import JSONResponse

from auth.middleware import AuthenticationMiddleware
from auth.router import _login_rate_key


def _request(path: str, method: str = "GET", headers=None) -> Request:
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": raw_headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )


class AuthenticationMiddlewareCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.middleware = AuthenticationMiddleware(lambda scope, receive, send: None)

    async def _next(self, request):
        return JSONResponse({"ok": True})

    async def test_public_endpoint_does_not_require_session(self):
        response = await self.middleware.dispatch(
            _request("/api/health"),
            self._next,
        )
        self.assertEqual(response.status_code, 200)

    async def test_private_endpoint_requires_session(self):
        response = await self.middleware.dispatch(
            _request("/api/settings"),
            self._next,
        )
        self.assertEqual(response.status_code, 401)

    async def test_cors_preflight_does_not_require_session(self):
        response = await self.middleware.dispatch(
            _request("/api/settings", method="OPTIONS"),
            self._next,
        )
        self.assertEqual(response.status_code, 200)

    async def test_authenticated_cross_origin_post_is_allowed(self):
        db = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = SimpleNamespace(status="active")
        db.execute = AsyncMock(return_value=result)

        session_context = MagicMock()
        session_context.__aenter__ = AsyncMock(return_value=db)
        session_context.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("auth.middleware.get_session", AsyncMock(return_value={"user_id": "user-1"})),
            patch("auth.middleware.AsyncSessionLocal", return_value=session_context),
        ):
            response = await self.middleware.dispatch(
                _request(
                    "/api/settings",
                    method="POST",
                    headers={
                        "Cookie": "session_id=session-1",
                        "Host": "api.example.com",
                        "Origin": "https://other.example.com",
                    },
                ),
                self._next,
            )

        self.assertEqual(response.status_code, 200)

    def test_login_rate_key_distinguishes_forwarded_clients(self):
        first = _request("/api/auth/login", headers={"X-Forwarded-For": "203.0.113.10"})
        second = _request("/api/auth/login", headers={"X-Forwarded-For": "203.0.113.11"})
        self.assertNotEqual(_login_rate_key(first), _login_rate_key(second))


if __name__ == "__main__":
    unittest.main()
