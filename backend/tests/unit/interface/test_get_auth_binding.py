from __future__ import annotations

from types import SimpleNamespace

import pytest
import structlog
from starlette.requests import Request

from cellar.interface.dependencies._core import get_auth


def _make_request() -> Request:
    return Request({"type": "http", "headers": [], "state": {}})


@pytest.fixture(autouse=True)
def _clear_log_context():
    """Guarantee a clean structlog context around every test, even on failure."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


async def test_get_auth_binds_user_and_workspace():
    request = _make_request()
    auth = SimpleNamespace(user_id="u-1", workspace_id="w-1")
    result = await get_auth(request, auth)
    assert result is auth
    ctx = structlog.contextvars.get_contextvars()
    assert ctx["user_id"] == "u-1"
    assert ctx["workspace_id"] == "w-1"
    assert request.state.user_id == "u-1"
    assert request.state.workspace_id == "w-1"


async def test_get_auth_handles_none_auth():
    request = _make_request()
    auth = SimpleNamespace(user_id=None, workspace_id=None)
    result = await get_auth(request, auth)
    assert result is auth
    ctx = structlog.contextvars.get_contextvars()
    assert "user_id" not in ctx          # bind_user_context skips None
    assert "workspace_id" not in ctx
    assert request.state.user_id is None
    assert request.state.workspace_id is None
