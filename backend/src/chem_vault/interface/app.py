"""FastAPI application factory with Sentinel auth, DI container, and error handlers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chem_vault.infrastructure.di.container import create_container
from chem_vault.infrastructure.logging import configure_logging
from chem_vault.infrastructure.sentinel.auth import get_sentinel
from chem_vault.interface.error_handlers import register_error_handlers

sentinel = get_sentinel()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """App lifespan — initialize container, register Sentinel actions, cleanup."""
    # Structured logging
    import os
    configure_logging(
        json_output=os.getenv("LOG_FORMAT", "json") == "json",
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )

    # Initialize DI container and attach to app state
    container = create_container()
    app.state.container = container

    # Wire audit event handler — catch-all for all domain events
    from sqlalchemy.ext.asyncio import async_sessionmaker as async_sm

    from chem_vault.domain.shared.events import DomainEvent
    from chem_vault.infrastructure.messaging.audit_event_handler import AuditEventHandler
    from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher

    dispatcher = container[EventDispatcher]
    session_factory = container[async_sm]
    dispatcher.register(DomainEvent, AuditEventHandler(session_factory))

    # Temporal client — graceful fallback to None for local dev without Temporal
    from chem_vault.infrastructure.temporal import TemporalSettings, create_temporal_client

    try:
        temporal_settings = TemporalSettings()
        temporal_client = await create_temporal_client(temporal_settings)
        app.state.temporal_client = temporal_client
    except Exception:
        import structlog
        structlog.get_logger().warning("temporal_unavailable", msg="Temporal not reachable — bulk ops will run synchronously")
        app.state.temporal_client = None

    # Delegate to Sentinel's lifespan (registers service actions, fetches JWKS)
    async with sentinel.lifespan(app):
        yield

    # Cleanup: close httpx client used by vault integration
    import httpx

    try:
        vault_http = container[httpx.AsyncClient]
        await vault_http.aclose()
    except Exception:
        pass

    # Cleanup: dispose the database engine
    from sqlalchemy.ext.asyncio import AsyncEngine

    engine = container[AsyncEngine]
    await engine.dispose()


def create_app() -> FastAPI:
    """Build the FastAPI application with auth, CORS, DI, and error handling."""
    app = FastAPI(
        title="Chem-Vault",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # Auth middleware — validates IdP + Sentinel authz tokens
    sentinel.protect(
        app,
        exclude_paths=["/health", "/docs", "/openapi.json"],
    )

    # CORS — added last so it runs first (LIFO)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Domain error → HTTP response mapping
    register_error_handlers(app)

    # Routes
    from chem_vault.interface.routes.user import router as user_router
    from chem_vault.interface.routes.organizations import router as org_router
    from chem_vault.interface.routes.settings import router as settings_router
    from chem_vault.interface.routes.vocabularies import router as vocab_router
    from chem_vault.interface.routes.molecules import router as mol_router
    from chem_vault.interface.routes.disclosures import router as disclosure_router
    from chem_vault.interface.routes.merge import router as merge_router
    from chem_vault.interface.routes.relationships import router as rel_router
    from chem_vault.interface.routes.bulk_registration import router as bulk_reg_router
    from chem_vault.interface.routes.batches import router as batch_router
    from chem_vault.interface.routes.samples import router as sample_router
    from chem_vault.interface.routes.storage import router as storage_router
    from chem_vault.interface.routes.protocols import router as protocol_router
    from chem_vault.interface.routes.runs import router as run_router
    from chem_vault.interface.routes.readout_data import router as readout_data_router
    from chem_vault.interface.routes.audit import router as audit_router
    from chem_vault.interface.routes.synthesis_routes import router as synth_route_router
    from chem_vault.interface.routes.sample_requests import router as sample_request_router
    from chem_vault.interface.routes.shipments import router as shipment_router
    from chem_vault.interface.routes.synthesis_requests import router as synth_req_router

    app.include_router(user_router)
    app.include_router(org_router)
    app.include_router(settings_router)
    app.include_router(vocab_router)
    from chem_vault.interface.routes.export import router as export_router

    app.include_router(mol_router)
    app.include_router(export_router)
    app.include_router(disclosure_router)
    app.include_router(merge_router)
    app.include_router(rel_router)
    app.include_router(bulk_reg_router)
    app.include_router(batch_router)
    app.include_router(sample_router)
    app.include_router(storage_router)
    app.include_router(protocol_router)
    app.include_router(run_router)
    app.include_router(readout_data_router)
    app.include_router(audit_router)
    app.include_router(synth_route_router)
    app.include_router(sample_request_router)
    app.include_router(shipment_router)
    app.include_router(synth_req_router)

    from chem_vault.interface.routes.plate_templates import router as plate_template_router
    from chem_vault.interface.routes.registered_plates import router as registered_plates_router

    app.include_router(plate_template_router)
    app.include_router(registered_plates_router)

    from chem_vault.interface.routes.projects import router as project_router
    from chem_vault.interface.routes.collections import router as collection_router
    from chem_vault.interface.routes.saved_searches import router as saved_search_router

    app.include_router(project_router)
    app.include_router(collection_router)
    app.include_router(saved_search_router)

    from chem_vault.interface.routes.search import router as search_router
    app.include_router(search_router)

    from chem_vault.interface.routes.molecule_activity import router as molecule_activity_router
    app.include_router(molecule_activity_router)

    from chem_vault.interface.routes.plate_import import router as plate_import_router
    app.include_router(plate_import_router)

    from chem_vault.interface.routes.attachments import router as attachment_router
    app.include_router(attachment_router)

    from chem_vault.interface.routes.dashboard import router as dashboard_router
    app.include_router(dashboard_router)

    from chem_vault.interface.routes.custom_fields import router as custom_fields_router
    app.include_router(custom_fields_router)

    from chem_vault.interface.routes.salt_catalog import router as salt_catalog_router
    app.include_router(salt_catalog_router)

    from chem_vault.interface.routes.registration_forms import router as registration_forms_router
    app.include_router(registration_forms_router)

    from chem_vault.interface.routes.api_keys import router as api_keys_router
    app.include_router(api_keys_router)

    from chem_vault.interface.routes.ontology import router as ontology_router
    app.include_router(ontology_router)

    from chem_vault.interface.routes.protocol_forms import router as protocol_forms_router
    app.include_router(protocol_forms_router)

    from chem_vault.interface.routes.cdd_import import router as cdd_import_router
    app.include_router(cdd_import_router)

    from chem_vault.interface.routes.cdd_molecule_import import router as cdd_mol_import_router
    app.include_router(cdd_mol_import_router)

    from chem_vault.interface.routes.plate_setup import router as plate_setup_router
    app.include_router(plate_setup_router)

    from chem_vault.interface.routes.inventory_hub import router as inventory_hub_router
    app.include_router(inventory_hub_router)

    from chem_vault.interface.routes.protocol_hub import router as protocol_hub_router
    app.include_router(protocol_hub_router)

    from chem_vault.interface.routes.compound_flags import router as compound_flags_router
    app.include_router(compound_flags_router)

    # Health check (unauthenticated)
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
