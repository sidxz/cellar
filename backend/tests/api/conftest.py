"""API test fixtures — test-specific FastAPI app with FakeAuth, real DB."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Mapping

# Set duar env before any cellar imports — allows module-level get_duar() to succeed.
# Must NOT use .env files (cross-contamination between DatabaseSettings and DuarSettings).
os.environ["DUAR_SERVICE_KEY"] = "test-key-for-api-tests"
os.environ["DUAR_URL"] = "https://duar.example.com"
os.environ["DUAR_SERVICE_NAME"] = "cellar"
# Required since Duar 0.11.0 (authz mode) — get_duar() raises ValueError without it.
os.environ["DUAR_IDP_AUDIENCE"] = "test-audience.apps.googleusercontent.com"
# Disable Temporal so the DI container binds NullExportOrchestrator (and the other Null
# orchestrators) without needing a running Temporal server.
os.environ["TEMPORAL_DISABLED"] = "1"

import pytest
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.application.auth import LOAN_APPROVE_ACTION
from cellar.application.shared.org_directory import OrgDirectoryPort
from cellar.infrastructure.di.container import create_container
from cellar.infrastructure.duar.org_directory import OrgSummary
from cellar.infrastructure.persistence.settings import DatabaseSettings
from cellar.interface.error_handlers import register_error_handlers
from cellar.interface.dependencies import get_auth
from tests.fakes.fake_auth import FakeAuth

# Single source of truth for the stubbed Duar org-directory entry —
# imported by tests/api/test_org_directory.py. Lives here (rather than the
# test module) so conftest never has to import a specific test module.
ORG_ID = uuid.uuid4()

# The org_id carried by the default `fake_auth` (and therefore `client`) fixture —
# imported by tests that assert owner_org_id defaults from auth.
AUTH_ORG_ID = uuid.uuid4()

# A second, distinct org id — for cross-org visibility tests (plate_visibility
# private-org exclusion) where the caller's org must differ from AUTH_ORG_ID.
OTHER_ORG_ID = uuid.uuid4()


class _StubOrgDirectory:
    """Static Duar org directory — every org id the API tests use, so the
    strict visibility rule ("every other org is excluded") sees all of them.
    Never makes HTTP calls."""

    async def list_orgs(self) -> list[OrgSummary]:
        return [
            OrgSummary(id=ORG_ID, slug="abbvie", name="AbbVie", is_public=False),
            OrgSummary(id=AUTH_ORG_ID, slug="tamu", name="TAMU", is_public=False),
            OrgSummary(id=OTHER_ORG_ID, slug="partner", name="Partner", is_public=False),
        ]


STUB_ORG_DIRECTORY = _StubOrgDirectory()


def _create_test_app(
    database_url: str, fake_auth: FakeAuth, overrides: Mapping[type, object] | None = None
) -> FastAPI:
    """Build a FastAPI app for testing — no Duar middleware, FakeAuth for routes."""
    app = FastAPI()

    # DI container pointed at test DB — _env_file=None avoids loading .env
    db_settings = DatabaseSettings(database_url=database_url, _env_file=None)  # type: ignore[call-arg]
    container = create_container(
        db_settings, overrides={OrgDirectoryPort: STUB_ORG_DIRECTORY, **(overrides or {})}
    )
    app.state.container = container

    # Error handlers (so DomainError → proper HTTP status)
    register_error_handlers(app)

    # Import routes
    from cellar.interface.routes.user import router as user_router
    from cellar.interface.routes.org_directory import router as org_directory_router
    from cellar.interface.routes.organizations import router as org_router
    from cellar.interface.routes.settings import router as settings_router
    from cellar.interface.routes.vocabularies import router as vocab_router
    from cellar.interface.routes.molecules import router as mol_router
    from cellar.interface.routes.export import router as export_router
    from cellar.interface.routes.export import legacy_router as export_legacy_router
    from cellar.interface.routes.plate_templates import router as plate_template_router
    from cellar.interface.routes.projects import router as project_router
    from cellar.interface.routes.favorites import router as favorites_router
    from cellar.interface.routes.collections import router as collection_router
    from cellar.interface.routes.collection_import_previews import (
        router as collection_import_previews_router,
    )
    from cellar.interface.routes.collection_import_templates import (
        router as collection_import_templates_router,
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
    from cellar.interface.routes.run_import import router as run_import_router
    from cellar.interface.routes.scaffold_tree import router as scaffold_tree_router
    from cellar.interface.routes.sar_analysis import router as sar_analysis_router
    from cellar.interface.routes.umap_cluster import router as umap_cluster_router
    from cellar.interface.routes.kiosk import router as kiosk_router
    from cellar.interface.routes.kiosk_devices import router as kiosk_device_router
    from cellar.interface.routes.org_plate_policies import router as org_plate_policy_router
    from cellar.interface.routes.plate_groups import router as plate_group_router
    from cellar.interface.routes.plate_loans import router as plate_loan_router
    from cellar.interface.routes.registered_plates import router as registered_plates_router
    from cellar.interface.routes.plate_import import router as plate_import_router
    from cellar.interface.routes.tags import router as tags_router
    from cellar.interface.routes.tags import assignment_router as tag_assignment_router
    from cellar.interface.routes.protocols import router as protocols_router
    from cellar.interface.routes.runs import router as runs_router
    from cellar.interface.routes.targets import router as targets_router
    from cellar.interface.routes.inventory_hub import router as inventory_hub_router
    from cellar.interface.routes.version import router as version_router

    app.include_router(user_router)
    app.include_router(org_router)
    app.include_router(org_directory_router)
    app.include_router(settings_router)
    app.include_router(vocab_router)
    app.include_router(mol_router)
    app.include_router(export_router)
    app.include_router(export_legacy_router)
    app.include_router(plate_template_router)
    app.include_router(registered_plates_router)
    app.include_router(plate_group_router)
    app.include_router(plate_import_router)
    app.include_router(org_plate_policy_router)
    app.include_router(plate_loan_router)
    app.include_router(kiosk_device_router)
    app.include_router(kiosk_router)
    app.include_router(project_router)
    app.include_router(favorites_router)
    app.include_router(collection_router)
    app.include_router(collection_import_previews_router)
    app.include_router(collection_import_templates_router)
    app.include_router(saved_search_router)
    app.include_router(search_router)
    app.include_router(search_algorithms_router)
    app.include_router(batch_router)
    app.include_router(scaffold_tree_router)
    app.include_router(sar_analysis_router)
    app.include_router(umap_cluster_router)
    app.include_router(audit_router)
    app.include_router(admin_delete_router)
    app.include_router(campaign_router)
    app.include_router(campaign_channels_router)
    app.include_router(campaign_results_router)
    app.include_router(campaign_publishing_router)
    app.include_router(drc_batch_router)
    app.include_router(readout_data_router)
    app.include_router(run_import_router)
    app.include_router(tags_router)
    app.include_router(tag_assignment_router)
    app.include_router(protocols_router)
    app.include_router(runs_router)
    app.include_router(targets_router)
    app.include_router(inventory_hub_router)
    app.include_router(version_router)

    # Override the stable auth wrapper (not the sentinel SDK directly)
    app.dependency_overrides[get_auth] = lambda: fake_auth

    # Stub the Duar org directory for the /api/v1/orgs route too.
    from cellar.interface.dependencies import get_org_directory

    app.dependency_overrides[get_org_directory] = lambda: STUB_ORG_DIRECTORY

    return app


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def fake_auth(workspace_id: uuid.UUID, user_id: uuid.UUID) -> FakeAuth:
    return FakeAuth(role="admin", workspace_id=workspace_id, user_id=user_id, org_id=AUTH_ORG_ID)


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
def make_target(api_app: FastAPI, workspace_id: uuid.UUID):
    """Seed a mirror target row directly (there is no create route — prot-cellar owns targets).

    Returns ``async (name, *, target_type="single_protein") -> str`` (the new id).
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import TargetModel

    async def _make(name: str, *, target_type: str = "single_protein") -> str:
        tid = uuid.uuid4()
        factory = api_app.state.container[async_sessionmaker]
        async with factory() as session, session.begin():
            session.add(
                TargetModel(
                    id=tid,
                    workspace_id=workspace_id,
                    name=name,
                    target_type=target_type,
                    source_version=1,
                )
            )
        return str(tid)

    return _make


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


@pytest.fixture
async def editor_client_own_org(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client scoped to an editor role with a known org_id.

    For the cross-org assignment guard (owner_org_id must match auth.org_id
    unless admin) — ``editor_client`` deliberately leaves org_id unset, which
    can't exercise the "same org" branch of that guard.
    """
    editor_auth = FakeAuth(
        role="editor", workspace_id=workspace_id, user_id=user_id, org_id=AUTH_ORG_ID
    )
    app = _create_test_app(database_url, editor_auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = app.state.container[AsyncEngine]
    await engine.dispose()


@pytest.fixture
async def approver_client_own_org(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client scoped to an editor role with a known org_id
    (``AUTH_ORG_ID``) and the ``cellar:approve_loan`` RBAC action granted —
    the "owner-org editor WITH action" identity for plate-loan authority
    tests (mirrors ``editor_client_own_org`` exactly, plus the grant)."""
    approver_auth = FakeAuth(
        role="editor",
        workspace_id=workspace_id,
        user_id=user_id,
        org_id=AUTH_ORG_ID,
        granted_actions={LOAN_APPROVE_ACTION},
    )
    app = _create_test_app(database_url, approver_auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = app.state.container[AsyncEngine]
    await engine.dispose()


@pytest.fixture
async def denied_editor_client_own_org(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client scoped to an editor role with a known org_id
    (``AUTH_ORG_ID``) and NO RBAC actions granted — proves the action-denial
    branch (the default ``FakeAuth(granted_actions=None)`` used by
    ``editor_client_own_org`` is permissive, so it can't exercise this path)."""
    denied_auth = FakeAuth(
        role="editor",
        workspace_id=workspace_id,
        user_id=user_id,
        org_id=AUTH_ORG_ID,
        granted_actions=set(),
    )
    app = _create_test_app(database_url, denied_auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = app.state.container[AsyncEngine]
    await engine.dispose()


@pytest.fixture
async def editor_client_other_org(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client scoped to an editor role with a *different* org_id
    (``OTHER_ORG_ID``) than ``AUTH_ORG_ID`` — the second identity needed for
    cross-org plate visibility tests (a caller whose org == the plate's owner
    org, distinct from the default `client`/`editor_client_own_org` org)."""
    editor_auth = FakeAuth(
        role="editor", workspace_id=workspace_id, user_id=user_id, org_id=OTHER_ORG_ID
    )
    app = _create_test_app(database_url, editor_auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = app.state.container[AsyncEngine]
    await engine.dispose()


@pytest.fixture
async def viewer_client(
    database_url: str, _run_migrations: None, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> AsyncIterator[AsyncClient]:
    """Async HTTP client scoped to a viewer role (for 403 tests)."""
    viewer_auth = FakeAuth(role="viewer", workspace_id=workspace_id, user_id=user_id)
    app = _create_test_app(database_url, viewer_auth)
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    engine = app.state.container[AsyncEngine]
    await engine.dispose()
