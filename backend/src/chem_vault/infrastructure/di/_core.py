"""Core infrastructure bindings: DB, UoW, EventDispatcher, shared clients.

Shared by all bounded contexts.
"""

from __future__ import annotations

import os

import httpx
from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from chem_vault.application.chemical_registration.protocols import StructureProcessorProtocol
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.curve_fitting import CurveFittingService
from chem_vault.domain.shared.secret_provider import SecretProvider
from chem_vault.infrastructure.lmfit.curve_fitter import LmfitCurveFitter
from chem_vault.infrastructure.messaging.event_dispatcher import EventDispatcher
from chem_vault.infrastructure.persistence.database import create_engine, create_session_factory
from chem_vault.infrastructure.persistence.settings import DatabaseSettings
from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from chem_vault.infrastructure.rdkit.structure_processor import StructureProcessor
from chem_vault.infrastructure.secrets.chain_provider import ChainSecretProvider
from chem_vault.infrastructure.secrets.env_provider import EnvSecretProvider
from chem_vault.infrastructure.storage.fsspec_client import FsspecStorageClient, StorageSettings
from chem_vault.infrastructure.temporal.settings import TemporalSettings


def _build_secret_provider() -> SecretProvider:
    """Infisical (if configured) → env vars."""
    providers: list = []

    infisical_token = os.environ.get("INFISICAL_TOKEN")
    infisical_project = os.environ.get("INFISICAL_PROJECT_ID")
    infisical_url = os.environ.get("INFISICAL_BASE_URL", "http://localhost:8089")

    if infisical_token and infisical_project:
        from chem_vault.infrastructure.secrets.infisical_provider import InfisicalSecretProvider
        providers.append(InfisicalSecretProvider(
            base_url=infisical_url,
            token=infisical_token,
            project_id=infisical_project,
            client=httpx.AsyncClient(),
        ))

    providers.append(EnvSecretProvider())
    return ChainSecretProvider(*providers)


def register_core(container: Container, db_settings: DatabaseSettings | None = None) -> None:
    # --- Database ---
    settings = db_settings or DatabaseSettings()  # type: ignore[call-arg]
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    container.define(AsyncEngine, Singleton(lambda: engine))
    container.define(async_sessionmaker, Singleton(lambda: session_factory))
    container.define(
        AsyncUnitOfWork, lambda c: AsyncUnitOfWork(c[async_sessionmaker])
    )
    container.define(UnitOfWork, lambda c: c[AsyncUnitOfWork])

    # --- Event Dispatcher ---
    container.define(EventDispatcher, Singleton(EventDispatcher))

    # --- Shared HTTP client ---
    httpx_client = httpx.AsyncClient()
    container.define(httpx.AsyncClient, Singleton(lambda: httpx_client))

    # --- File Storage ---
    storage_settings = StorageSettings()
    storage_client = FsspecStorageClient(storage_settings)
    container.define(FsspecStorageClient, Singleton(lambda: storage_client))

    # --- Structure Processor (RDKit) ---
    container.define(StructureProcessor, Singleton(StructureProcessor))
    container.define(StructureProcessorProtocol, lambda c: c[StructureProcessor])

    # --- Curve Fitting ---
    container.define(LmfitCurveFitter, Singleton(LmfitCurveFitter))
    container.define(CurveFittingService, lambda c: c[LmfitCurveFitter])

    # --- Secret Provider chain ---
    container.define(SecretProvider, Singleton(_build_secret_provider))

    # --- Temporal ---
    container.define(TemporalSettings, Singleton(TemporalSettings))
