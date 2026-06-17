from __future__ import annotations

from types import SimpleNamespace

import structlog
from starlette.requests import Request

from cellar.interface.dependencies._core import get_auth


def _make_request() -> Request:
    return Request({"type": "http", "headers": [], "state": {}})


async def test_get_auth_binds_user_and_workspace():
    structlog.contextvars.clear_contextvars()
    request = _make_request()
    auth = SimpleNamespace(user_id="u-1", workspace_id="w-1")
    result = await get_auth(request, auth)
    assert result is auth
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["user_id"] == "u-1"
    assert ctx["workspace_id"] == "w-1"
    assert request.state.user_id == "u-1"
    assert request.state.workspace_id == "w-1"
    structlog.contextvars.clear_contextvars()
