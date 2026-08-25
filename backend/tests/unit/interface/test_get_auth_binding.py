from __future__ import annotations

from types import SimpleNamespace

import pytest
import structlog
from starlette.requests import Request

from cellar.application.shared.actor_context import current_actor, set_current_actor
from cellar.interface.dependencies._core import get_auth
from tests.fakes.fake_auth import FakeAuth


def _make_request() -> Request:
    return Request({"type": "http", "headers": [], "state": {}})


@pytest.fixture(autouse=True)
def _clear_log_context():
    """Guarantee a clean structlog context around every test, even on failure."""
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


@pytest.fixture(autouse=True)
def _reset_actor_context():
    """I1: get_auth sets the actor-context ContextVar as a side effect;
    reset it so tests don't bleed into each other."""
    set_current_actor(None)
    yield
    set_current_actor(None)


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


async def test_get_auth_binds_current_actor():
    """I1: the production get_auth wire is the only place that sets the
    audit actor-context — exercise it directly, not a fake that reimplements
    the side effect."""
    request = _make_request()
    fake = FakeAuth()
    result = await get_auth(request, fake)
    assert result is fake
    assert current_actor() == fake.user_id
    assert request.state.user_id == str(fake.user_id)


async def test_get_auth_leaves_current_actor_none_without_a_uuid_user_id():
    request = _make_request()
    auth = object()  # no user_id attribute at all
    await get_auth(request, auth)
    assert current_actor() is None
