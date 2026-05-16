"""FastAPI application factory with Sentinel auth, DI container, and error handlers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cellar.infrastructure.di.container import create_container
from cellar.infrastructure.logging import configure_logging
from cellar.infrastructure.sentinel.auth import get_sentinel
from cellar.interface.error_handlers import register_error_handlers


def create_app() -> FastAPI:
    """Build the FastAPI application with auth, CORS, DI, and error handling."""
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

        from cellar.domain.shared.events import DomainEvent
        from cellar.infrastructure.messaging.audit_event_handler import AuditEventHandler
        from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher

        dispatcher = container[EventDispatcher]
        session_factory = container[async_sm]
        dispatcher.register(DomainEvent, AuditEventHandler(session_factory))

        # Temporal client — graceful fallback to None for local dev without Temporal
        from cellar.infrastructure.temporal import TemporalSettings, create_temporal_client

        try:
            temporal_settings = TemporalSettings()
            temporal_client = await create_temporal_client(temporal_settings)
            app.state.temporal_client = temporal_client
        except Exception:
            import structlog

            structlog.get_logger().warning(
                "temporal_unavailable",
                msg="Temporal not reachable — bulk ops will run synchronously",
            )
            app.state.temporal_client = None

        # Workflow orchestrators — bind concrete adapter or null stand-in based
        # on Temporal availability. Routes/use cases see only the application
        # Protocols and never reach into ``temporalio`` themselves.
        from cellar.application.chemical_registration.bulk_registration_orchestrator import (
            BulkRegistrationOrchestrator,
        )
        from cellar.application.cdd_import.cdd_molecule_import_orchestrator import (
            CddMoleculeImportOrchestrator,
        )
        from cellar.application.cdd_import.cdd_plate_import_orchestrator import (
            CddPlateImportOrchestrator,
        )
        from cellar.application.export.orchestration import ExportOrchestrator
        from cellar.infrastructure.temporal.orchestrators import (
            NullBulkRegistrationOrchestrator,
            NullCddMoleculeImportOrchestrator,
            NullCddPlateImportOrchestrator,
            TemporalBulkRegistrationOrchestrator,
            TemporalCddMoleculeImportOrchestrator,
            TemporalCddPlateImportOrchestrator,
        )
        from cellar.infrastructure.temporal.orchestrators.export import (
            NullExportOrchestrator,
            TemporalExportOrchestrator,
        )

        if app.state.temporal_client is not None:
            mol_orch: CddMoleculeImportOrchestrator = TemporalCddMoleculeImportOrchestrator(
                app.state.temporal_client
            )
            plate_orch: CddPlateImportOrchestrator = TemporalCddPlateImportOrchestrator(
                app.state.temporal_client
            )
            bulk_orch: BulkRegistrationOrchestrator = TemporalBulkRegistrationOrchestrator(
                app.state.temporal_client
            )
            export_orch: ExportOrchestrator = TemporalExportOrchestrator(
                app.state.temporal_client
            )
        else:
            mol_orch = NullCddMoleculeImportOrchestrator()
            plate_orch = NullCddPlateImportOrchestrator()
            bulk_orch = NullBulkRegistrationOrchestrator()
            from cellar.application.export.render_export import RenderExport

            export_orch = NullExportOrchestrator(container[RenderExport])

        from lagom import Singleton

        container.define(CddMoleculeImportOrchestrator, Singleton(lambda: mol_orch))
        container.define(CddPlateImportOrchestrator, Singleton(lambda: plate_orch))
        container.define(BulkRegistrationOrchestrator, Singleton(lambda: bulk_orch))
        container.define(ExportOrchestrator, Singleton(lambda: export_orch))

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

    app = FastAPI(
        title="Cellar",
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
    import os

    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in cors_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Domain error → HTTP response mapping
    register_error_handlers(app)

    # Routes
    from cellar.interface.routes.user import router as user_router
    from cellar.interface.routes.organizations import router as org_router
    from cellar.interface.routes.settings import router as settings_router
    from cellar.interface.routes.vocabularies import router as vocab_router
    from cellar.interface.routes.molecules import router as mol_router
    from cellar.interface.routes.disclosures import router as disclosure_router
    from cellar.interface.routes.merge import router as merge_router
    from cellar.interface.routes.relationships import router as rel_router
    from cellar.interface.routes.bulk_registration import router as bulk_reg_router
    from cellar.interface.routes.batches import router as batch_router
    from cellar.interface.routes.samples import router as sample_router
    from cellar.interface.routes.storage import router as storage_router
    from cellar.interface.routes.protocols import router as protocol_router
    from cellar.interface.routes.targets import router as target_router
    from cellar.interface.routes.runs import router as run_router
    from cellar.interface.routes.readout_data import router as readout_data_router
    from cellar.interface.routes.audit import router as audit_router
    from cellar.interface.routes.synthesis_routes import router as synth_route_router
    from cellar.interface.routes.sample_requests import router as sample_request_router
    from cellar.interface.routes.shipments import router as shipment_router
    from cellar.interface.routes.synthesis_requests import router as synth_req_router

    app.include_router(user_router)
    app.include_router(org_router)
    app.include_router(settings_router)
    app.include_router(vocab_router)
    from cellar.interface.routes.export import router as export_router
    from cellar.interface.routes.export import legacy_router as export_legacy_router

    app.include_router(mol_router)
    app.include_router(export_router)
    app.include_router(export_legacy_router)
    app.include_router(disclosure_router)
    app.include_router(merge_router)
    app.include_router(rel_router)
    app.include_router(bulk_reg_router)
    app.include_router(batch_router)
    app.include_router(sample_router)
    app.include_router(storage_router)
    app.include_router(protocol_router)
    app.include_router(target_router)
    app.include_router(run_router)
    app.include_router(readout_data_router)
    from cellar.interface.routes.dose_response_curves import router as drc_batch_router

    app.include_router(drc_batch_router)
    app.include_router(audit_router)
    app.include_router(synth_route_router)
    app.include_router(sample_request_router)
    app.include_router(shipment_router)
    app.include_router(synth_req_router)

    from cellar.interface.routes.plate_templates import router as plate_template_router
    from cellar.interface.routes.registered_plates import router as registered_plates_router

    app.include_router(plate_template_router)
    app.include_router(registered_plates_router)

    from cellar.interface.routes.projects import router as project_router
    from cellar.interface.routes.collections import router as collection_router
    from cellar.interface.routes.saved_searches import router as saved_search_router
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

    app.include_router(project_router)
    app.include_router(collection_router)
    app.include_router(saved_search_router)
    app.include_router(campaign_router)
    app.include_router(campaign_channels_router)
    app.include_router(campaign_results_router)
    app.include_router(campaign_publishing_router)

    from cellar.interface.routes.search import router as search_router
    from cellar.interface.routes.search_algorithms import router as search_algorithms_router

    app.include_router(search_router)
    app.include_router(search_algorithms_router)

    from cellar.interface.routes.molecule_activity import router as molecule_activity_router

    app.include_router(molecule_activity_router)

    from cellar.interface.routes.plate_import import router as plate_import_router

    app.include_router(plate_import_router)

    from cellar.interface.routes.run_import import router as run_import_router

    app.include_router(run_import_router)

    from cellar.interface.routes.attachments import router as attachment_router

    app.include_router(attachment_router)

    from cellar.interface.routes.dashboard import router as dashboard_router

    app.include_router(dashboard_router)

    from cellar.interface.routes.custom_fields import router as custom_fields_router

    app.include_router(custom_fields_router)

    from cellar.interface.routes.salt_catalog import router as salt_catalog_router

    app.include_router(salt_catalog_router)

    from cellar.interface.routes.registration_forms import router as registration_forms_router

    app.include_router(registration_forms_router)

    from cellar.interface.routes.api_keys import router as api_keys_router

    app.include_router(api_keys_router)

    from cellar.interface.routes.data_sources import router as data_sources_router

    app.include_router(data_sources_router)

    from cellar.interface.routes.ontology import router as ontology_router

    app.include_router(ontology_router)

    from cellar.interface.routes.protocol_forms import router as protocol_forms_router

    app.include_router(protocol_forms_router)

    from cellar.interface.routes.cdd_import import router as cdd_import_router

    app.include_router(cdd_import_router)

    from cellar.interface.routes.cdd_molecule_import import router as cdd_mol_import_router

    app.include_router(cdd_mol_import_router)

    from cellar.interface.routes.cdd_plate_import import router as cdd_plate_import_router

    app.include_router(cdd_plate_import_router)

    from cellar.interface.routes.plate_setup import router as plate_setup_router

    app.include_router(plate_setup_router)

    from cellar.interface.routes.inventory_hub import router as inventory_hub_router

    app.include_router(inventory_hub_router)

    from cellar.interface.routes.protocol_hub import router as protocol_hub_router

    app.include_router(protocol_hub_router)

    from cellar.interface.routes.compound_flags import router as compound_flags_router

    app.include_router(compound_flags_router)

    from cellar.interface.routes.admin_delete import router as admin_delete_router

    app.include_router(admin_delete_router)

    # Health check (unauthenticated)
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
