"""Global CORS policy shared by every FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


_ALL_HTTP_METHODS = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
_EXPOSED_RESPONSE_HEADERS = [
    "Cache-Control",
    "Content-Disposition",
    "Content-Type",
    "ETag",
    "Location",
    "X-Accel-Buffering",
    "X-Request-ID",
]


def add_permissive_cors(app: FastAPI) -> None:
    """Allow browser requests from every Origin, including credentialed ones.

    ``allow_origins=["*"]`` cannot be combined reliably with cookie
    credentials.  A full-match regular expression makes Starlette echo the
    concrete request Origin instead, so browsers receive an explicit
    ``Access-Control-Allow-Origin`` value together with
    ``Access-Control-Allow-Credentials: true``.

    Call this after other ``add_middleware`` calls so CORS is the outermost
    user middleware and also decorates authentication error responses.
    """

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r".*",
        allow_credentials=True,
        allow_methods=_ALL_HTTP_METHODS,
        # Starlette mirrors the browser's requested header names when this is
        # set, allowing uploads, API tokens, SSE reconnect headers, and future
        # custom headers without per-route CORS changes.
        allow_headers=["*"],
        expose_headers=_EXPOSED_RESPONSE_HEADERS,
        max_age=86400,
    )
