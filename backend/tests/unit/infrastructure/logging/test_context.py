from __future__ import annotations

import structlog

from cellar.infrastructure.logging.context import (
    bind_request_context,
    bind_user_context,
    clear_request_context,
)



def test_bind_request_then_clear():
    clear_request_context()
    bind_request_context(request_id="r-1", http_method="GET", http_path="/m")
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["request_id"] == "r-1"
    assert ctx["http_method"] == "GET"
    assert ctx["http_path"] == "/m"
    clear_request_context()
    assert structlog.contextvars.get_contextvars() == {}


def test_bind_user_skips_none():
    clear_request_context()
    bind_user_context(user_id="u-1", workspace_id=None)
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["user_id"] == "u-1"
    assert "workspace_id" not in ctx
    clear_request_context()
