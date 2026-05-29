"""API test fixtures — test-specific FastAPI app with FakeAuth, real DB."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

# Set sentinel env before any cellar imports — allows module-level get_sentinel() to succeed.
# Must NOT use .env files (cross-contamination between DatabaseSettings and SentinelSettings).
os.environ["SENTINEL_SERVICE_KEY"] = "test-key-for-api-tests"
os.environ["SENTINEL_URL"] = "https://sentinel.example.com"
os.environ["SENTINEL_SERVICE_NAME"] = "cellar"
# Disable Temporal so the DI container binds NullExportOrchestrator (and the other Null
# orchestrators) without needing a running Temporal server.
os.environ["TEMPORAL_DISABLED"] = "1"

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.infrastructure.di.container import create_container
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.interface.error_handlers import register_error_handlers
from cellar.interface.dependencies import get_auth
from tests.fakes.fake_auth import FakeAuth


def _create_test_app(database_url: str, fake_auth: FakeAuth) -> FastAPI:
    """Build a FastAPI app for testing — no Sentinel middleware, FakeAuth for routes."""
    app = FastAPI()

    # DI container pointed at test DB — _env_file=None avoids loading .env
    db_settings = DatabaseSettings(database_url=database_url, _env_file=None)  # type: ignore[call-arg]
    container = create_container(db_settings)
    app.state.container = container

    # Error handlers (so DomainError → proper HTTP status)
    register_error_handlers(app)

    # Import routes
    from cellar.interface.routes.user import router as user_router
    from cellar.interface.routes.organizations import router as org_router
    from cellar.interface.routes.settings import router as settings_router
    from cellar.interface.routes.vocabularies import router as vocab_router
    from cellar.interface.routes.molecules import router as mol_router
    from cellar.interface.routes.export import router as export_router
    from cellar.interface.routes.export import legacy_router as export_legacy_router
    from cellar.interface.routes.plate_templates import router as plate_template_router
    from cellar.interface.routes.projects import router as project_router
    from cellar.interface.routes.collections import router as collection_router
    from cellar.interface.routes.collection_import_previews import (
        router as collection_import_previews_router,
    )
    from cellar.interface.routes.saved_searches import router as saved_search_router
    from cellar.interface.routes.search import router as search_router
    from cellar.interface.routes.search_algorithms import router as search_algorithms_router
    from cellar.interface.routes.audit import router as audit_router
    from cellar.interface.routes.admin_delete import router as admin_delete_router
    from cellar.interface.routes.campaigns import router as campaign_router
    from cellar.interface.routes.campaigns_channels import (
        router as campaign_channels_router,
    )
    from cellar.interface.routes.campaigns_publishing import (
        router as campaign_publishing_router,
    )
    from cellar.interface.routes.campaigns_results import (
        router as campaign_results_router,
    )
    from cellar.interface.routes.batches import router as batch_router
    from cellar.interface.routes.dose_response_curves import router as drc_batch_router
    from cellar.interface.routes.readout_data import router as readout_data_router
    from cellar.interface.routes.scaffold_tree import router as scaffold_tree_router
    from cellar.interface.routes.umap_cluster import router as umap_cluster_router

    app.include_router(user_router)
    app.include_router(org_router)
    app.include_router(settings_router)
    app.include_router(vocab_router)
    app.include_router(mol_router)
    app.include_router(export_router)
    app.include_router(export_legacy_router)
    app.include_router(plate_template_router)
    app.include_router(project_router)
    app.include_router(collection_router)
    app.include_router(collection_import_previews_router)
    app.include_router(saved_search_router)
    app.include_router(search_router)
    app.include_router(search_algorithms_router)
    app.include_router(batch_router)
    app.include_router(scaffold_tree_router)
    app.include_router(umap_cluster_router)
    app.include_router(audit_router)
    app.include_router(admin_delete_router)
    app.include_router(campaign_router)
    app.include_router(campaign_channels_router)
    app.include_router(campaign_results_router)
    app.include_router(campaign_publishing_router)
    app.include_router(drc_batch_router)
    app.include_router(readout_data_router)

    # Override the stable auth wrapper (not the sentinel SDK directly)
    app.dependency_overrides[get_auth] = lambda: fake_auth

    return app


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def fake_auth(workspace_id: uuid.UUID, user_id: uuid.UUID) -> FakeAuth:
    return FakeAuth(role="admin", workspace_id=workspace_id, user_id=user_id)


@pytest.fixture
async def api_app(
    database_url: str, _run_migrations: None, fake_auth: FakeAuth
) -> AsyncIterator[FastAPI]:
    """Function-scoped test app with FakeAuth. Depends on _run_migrations from root conftest."""
    app = _create_test_app(database_url, fake_auth)
    yield app
    # Cleanup engine
    container = app.state.container
    engine = container[AsyncEngine]
    await engine.dispose()


@pytest.fixture
async def client(api_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Async HTTP client for API tests (admin auth)."""
    transport = ASGITransport(app=api_app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def editor_client(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client scoped to an editor role (for 403 tests)."""
    editor_auth = FakeAuth(role="editor", workspace_id=workspace_id, user_id=user_id)
    app = _create_test_app(database_url, editor_auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = app.state.container[AsyncEngine]
    await engine.dispose()
