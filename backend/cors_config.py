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
    """Allow requests from every Origin, including credentialed requests.

    A full-match regular expression makes Starlette echo the concrete request
    Origin instead of returning ``*``, which is required when browsers send
    credentials. Register this after other user middleware so authentication
    and authorization error responses also receive CORS headers.
    """

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r".*",
        allow_credentials=True,
        allow_methods=_ALL_HTTP_METHODS,
        allow_headers=["*"],
        expose_headers=_EXPOSED_RESPONSE_HEADERS,
        max_age=86400,
    )
