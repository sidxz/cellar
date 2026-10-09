"""ImportCddProtocol command -- fetch, map, and create a DRAFT Protocol."""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.cdd_import._check_config import check_cdd_configured
from cellar.application.cdd_import.errors import CddAuthError, CddConnectionError, CddNotFoundError
from cellar.application.cdd_import.gateway import CddProtocolGateway
from cellar.application.cdd_import.mapper import map_cdd_protocol
from cellar.application.screening.protocol_codes import mint_protocol_code
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.get_data_source_for_import import (
    GetDataSourceForImport,
)
from cellar.domain.screening_assay.enums import ProtocolType
from cellar.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.protocol_naming import normalize_name_text
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository


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
        settings_repo: WorkspaceSettingsRepository | None = None,
        *,
        names: ProtocolNameService,
    ) -> None:
        self._gateway = gateway
        self._get_data_source = get_data_source
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._dispatcher = dispatcher
        self._settings_repo = settings_repo
        self._names = names

    async def __call__(
        self, input: ImportCddProtocolCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        config = await check_cdd_configured(input.workspace_id, self._get_data_source)
        if isinstance(config, Failure):
            return config

        vault_id, api_key = config.unwrap()

        async with self._uow:
            try:
                raw = await self._gateway.get_protocol(
                    vault_id, api_key, input.external_protocol_id
                )
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
                        + (
                            f"Warnings: {'; '.join(w.reason for w in mapping.warnings)}"
                            if mapping.warnings
                            else ""
                        )
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
                with contextlib.suppress(ValueError):  # keep default BIOCHEMICAL
                    protocol_type = ProtocolType(cat_normalized)

            # The name is generated; the import only knows the category, so the protocol
            # usually lands flagged (needs facts) until someone fills in its fields.
            await self._protocol_repo.lock_naming(input.workspace_id)
            derivation = await self._names.derive(
                input.workspace_id,
                category=mapping.category,
                target_ids=[],
                annotations={},
                discriminator=None,
            )
            checked = self._names.check(derivation, person=True, allow_incomplete=True)
            if isinstance(checked, Failure):
                return checked
            code = await mint_protocol_code(
                settings_repo=self._settings_repo,
                protocol_repo=self._protocol_repo,
                workspace_id=input.workspace_id,
            )
            protocol = Protocol.create(
                workspace_id=input.workspace_id,
                name=derivation.rendered.name,
                name_base=derivation.rendered.base,
                name_flag=checked.unwrap(),
                code=code,
                description=mapping.description,
                protocol_type=protocol_type,
                category=mapping.category,
                created_by=auth.user_id,
                readout_definitions=readout_defs,
                condition_definitions=condition_defs,
            )
            # The vault's name stays findable: it becomes a nickname.
            with contextlib.suppress(ConflictError):  # the generated name may equal it
                # Legacy names may carry the middle dot or long dashes names never use: normalize.
                protocol.add_nickname(normalize_name_text(input.name_override or mapping.name))
            await self._names.flag_siblings(input.workspace_id, derivation)
            await self._protocol_repo.save(protocol)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
