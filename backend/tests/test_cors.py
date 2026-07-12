import unittest

import httpx
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from cors_config import add_permissive_cors


class RejectRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path == "/api/private":
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return await call_next(request)


class PermissiveCorsCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app = FastAPI()

        @app.get("/api/health")
        async def health():
            return {"ok": True}

        @app.get("/api/private")
        async def private():
            return {"ok": True}

        app.add_middleware(RejectRequestMiddleware)
        add_permissive_cors(app)

        transport = httpx.ASGITransport(app=app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_arbitrary_origin_and_request_headers_pass_preflight(self):
        origin = "https://frontend.any-domain.example"
        response = await self.client.options(
            "/api/private",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "x-arbitrary-header,content-type",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], origin)
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
        self.assertIn("PATCH", response.headers["access-control-allow-methods"])
        self.assertIn("x-arbitrary-header", response.headers["access-control-allow-headers"].lower())

    async def test_public_response_has_cors_and_download_headers(self):
        origin = "https://another.example"
        response = await self.client.get("/api/health", headers={"Origin": origin})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], origin)
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")
        self.assertIn("Content-Disposition", response.headers["access-control-expose-headers"])

    async def test_outer_cors_decorates_authentication_error(self):
        origin = "https://unauthenticated.example"
        response = await self.client.get("/api/private", headers={"Origin": origin})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["access-control-allow-origin"], origin)
        self.assertEqual(response.headers["access-control-allow-credentials"], "true")


if __name__ == "__main__":
    unittest.main()
