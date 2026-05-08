"""ImportCddProtocol command -- fetch, map, and create a DRAFT Protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.cdd_import._check_config import check_cdd_configured
from chem_vault.application.cdd_import.gateway import CddProtocolGateway
from chem_vault.application.cdd_import.mapper import map_cdd_protocol
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.enums import ProtocolType
from chem_vault.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import AuthorizationError, DomainError, NotFoundError, ValidationError
from chem_vault.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
)
from chem_vault.application.cdd_import.errors import CddAuthError, CddConnectionError, CddNotFoundError
from chem_vault.application.shared.event_dispatcher import EventDispatcherProtocol


@dataclass(frozen=True, kw_only=True)
class ImportCddProtocolCommand(Command):
    workspace_id: uuid.UUID
    external_protocol_id: int
    name_override: str | None = None


class ImportCddProtocol:
    def __init__(
        self,
        gateway: CddProtocolGateway,
        get_data_source: GetDataSourceForImport,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._gateway = gateway
        self._get_data_source = get_data_source
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: ImportCddProtocolCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        if auth is None:
            return Failure(AuthorizationError("Authentication required"))

        config = await check_cdd_configured(input.workspace_id, self._get_data_source)
        if isinstance(config, Failure):
            return config

        vault_id, api_key = config.unwrap()

        async with self._uow:
            try:
                raw = await self._gateway.get_protocol(vault_id, api_key, input.external_protocol_id)
            except CddAuthError:
                return Failure(ValidationError("CDD Vault API key is invalid or expired"))
            except CddNotFoundError:
                return Failure(NotFoundError("CDD Protocol", str(input.external_protocol_id)))
            except CddConnectionError:
                return Failure(ValidationError("Could not connect to CDD Vault"))

            mapping = map_cdd_protocol(raw)

            if not mapping.readouts:
                return Failure(
                    ValidationError(
                        "No mappable readouts found in CDD protocol. "
                        + (f"Warnings: {'; '.join(w.reason for w in mapping.warnings)}" if mapping.warnings else "")
                    )
                )

            tmp_id = uuid.uuid4()
            readout_defs = [
                ReadoutDefinition(
                    protocol_id=tmp_id,
                    name=r.name,
                    description=r.description,
                    data_type=r.data_type,
                    unit=r.unit,
                    aggregation=r.aggregation,
                    normalizations=r.normalizations,
                    precision=r.precision,
                    pick_list_values=r.pick_list_values,
                    dose_response_config=r.dose_response_config,
                    display_order=r.display_order,
                )
                for r in mapping.readouts
            ]

            condition_defs = [
                ConditionDefinition(
                    protocol_id=tmp_id,
                    name=c.name,
                    data_type=c.data_type,
                    unit=c.unit,
                    pick_list_values=c.pick_list_values,
                )
                for c in mapping.conditions
            ] or None

            # Map category to ProtocolType (case-insensitive)
            protocol_type = ProtocolType.BIOCHEMICAL
            if mapping.category:
                cat_normalized = mapping.category.lower().replace(" ", "_").replace("-", "_")
                try:
                    protocol_type = ProtocolType(cat_normalized)
                except ValueError:
                    pass  # keep default BIOCHEMICAL

            protocol = Protocol.create(
                workspace_id=input.workspace_id,
                name=input.name_override or mapping.name,
                description=mapping.description,
                protocol_type=protocol_type,
                category=mapping.category,
                created_by=auth.user_id,
                readout_definitions=readout_defs,
                condition_definitions=condition_defs,
            )
            await self._protocol_repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
