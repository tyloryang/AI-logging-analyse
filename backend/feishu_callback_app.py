"""Standalone Feishu callback service entrypoint."""

from __future__ import annotations

import os

from fastapi import FastAPI

from runtime_env import bootstrap_runtime_env

bootstrap_runtime_env()

from routers.feishu_bot import feishu_webhook, router as feishu_bot_router  # noqa: E402

app = FastAPI(title="Feishu Callback Service", version="1.0.0")
app.include_router(feishu_bot_router)
app.add_api_route("/", feishu_webhook, methods=["POST"], include_in_schema=False)


@app.get("/")
async def root():
    return {
        "ok": True,
        "service": "feishu-callback",
        "webhook_path": "/webhook/event",
    }


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "feishu-callback"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "feishu_callback_app:app",
        host=os.getenv("FEISHU_CALLBACK_HOST", "0.0.0.0"),
        port=int(os.getenv("FEISHU_CALLBACK_PORT", "8001")),
        reload=os.getenv("DEV_RELOAD", "").lower() in ("1", "true", "yes"),
    )
