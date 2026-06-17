from __future__ import annotations

import structlog
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from cellar.infrastructure.logging.config import configure_logging
from cellar.infrastructure.logging.settings import LoggingSettings
from cellar.interface.middleware.request_context import RequestContextMiddleware


def _client():
    async def ok(request):
        # prove request_id is visible downstream via contextvars
        rid = structlog.contextvars.get_contextvars().get("request_id")
        return PlainTextResponse(rid or "none")

    async def boom(request):
        raise RuntimeError("kaboom")

    app = Starlette(
        routes=[Route("/ok", ok), Route("/boom", boom), Route("/health", ok)]
    )
    app.add_middleware(RequestContextMiddleware)
    return TestClient(app, raise_server_exceptions=False)


def test_mints_request_id_and_echoes_header():
    r = _client().get("/ok")
    assert r.status_code == 200
    assert r.headers["x-request-id"]
    assert r.text == r.headers["x-request-id"]  # same id downstream


def test_passes_through_supplied_request_id():
    r = _client().get("/ok", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"
    assert r.text == "abc-123"


def test_access_log_emitted_with_fields():
    configure_logging(LoggingSettings(_env_file=None, format="json"))
    with structlog.testing.capture_logs() as logs:
        _client().get("/ok")
    completed = [e for e in logs if e["event"] == "request.completed"]
    assert completed
    entry = completed[0]
    assert entry["method"] == "GET"
    assert entry["path"] == "/ok"
    assert entry["status_code"] == 200
    assert "duration_ms" in entry


def test_health_excluded_from_access_log():
    with structlog.testing.capture_logs() as logs:
        _client().get("/health")
    assert not [e for e in logs if e["event"] == "request.completed"]


def test_context_cleared_after_request():
    structlog.contextvars.clear_contextvars()
    _client().get("/ok")
    assert structlog.contextvars.get_contextvars() == {}


def test_clears_context_even_on_error():
    structlog.contextvars.clear_contextvars()
    r = _client().get("/boom")
    assert r.status_code == 500
    assert structlog.contextvars.get_contextvars() == {}
