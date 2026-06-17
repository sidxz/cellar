"""Pure-ASGI middleware: per-request id, structured access log, context cleanup."""

from __future__ import annotations

import time
import uuid
from typing import Any

from cellar.infrastructure.logging import (
    bind_request_context,
    clear_request_context,
    get_logger,
)

logger = get_logger(__name__)

_ACCESS_LOG_EXCLUDE = frozenset({"/health"})


class RequestContextMiddleware:
    """Bind a request id (+method/path) for the whole request, log completion.

    Pure ASGI (not ``BaseHTTPMiddleware``) so contextvars bound here propagate
    downstream and are reliably cleared in ``finally``.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        method = scope.get("method", "")
        path = scope.get("path", "")
        client = scope.get("client")
        client_ip = client[0] if client else None

        bind_request_context(
            request_id=request_id, http_method=method, http_path=path
        )
        status_holder: dict[str, int] = {"status": 0}
        start = time.monotonic()

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers_list = list(message.get("headers", []))
                headers_list.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers_list}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if path not in _ACCESS_LOG_EXCLUDE:
                state = scope.get("state") or {}
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                logger.info(
                    "request.completed",
                    request_id=request_id,
                    method=method,
                    path=path,
                    status_code=status_holder["status"],
                    duration_ms=duration_ms,
                    client_ip=client_ip,
                    user_id=state.get("user_id"),
                    workspace_id=state.get("workspace_id"),
                )
            clear_request_context()
