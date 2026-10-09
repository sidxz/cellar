"""CreateProtocol use case."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import (
    AuthContext,
    require_authenticated,
    require_editor,
    require_same_workspace,
)
from cellar.application.screening._dose_response_config_serde import (
    deserialize_dose_response_config,
)
from cellar.application.screening.form_assay_format import assay_format_from_form
from cellar.application.screening.manage_protocol import (
    correction_reason,
    set_discriminator_and_rename,
)
from cellar.application.screening.protocol_codes import mint_protocol_code
from cellar.application.screening.protocol_naming_service import (
    NameTakenError,
    ProtocolNameService,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    PosControlSignal,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import (
    RESERVED_READOUT_NAMES,
    ConditionDefinition,
    Protocol,
    ProtocolReference,
    ReadoutDefinition,
    is_reserved_readout_name,
)
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    TargetLinkResult,
    TargetRepository,
)
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.errors import (
    ConcurrencyConflictError,
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.workspace_config.repository import (
    ProtocolFormRepository,
    WorkspaceSettingsRepository,
)


def _about(label: str, error: DomainError) -> DomainError:
    """The same error (type, detail, retry hint), saying which sibling it is about."""
    error.message = f"{label}: {error.message}"
    error.args = (error.message,)
    return error


@dataclass(frozen=True)
class SiblingDiscriminator:
    """A discriminator for a bare sibling, set in the same save as the new protocol."""

    protocol_id: uuid.UUID
    discriminator: str
    reason: str | None = None  # required when the sibling is published


@dataclass(frozen=True, kw_only=True)
class CreateProtocolCommand(Command):
    workspace_id: uuid.UUID
    description: str | None = None
    protocol_type: str
    target_ids: list[uuid.UUID] = field(default_factory=list)
    category: str | None = None
    dose_unit: str = "uM"
    pos_control_signal: str = "high"
    readout_definitions: list[dict[str, Any]] = field(default_factory=list)
    condition_definitions: list[dict[str, Any]] = field(default_factory=list)
    # Facets, keyed by slot name → list of {term_id, label, ontology_source,
    # uri?}. Persisted as part of the create transaction so the fingerprint is
    # computed once with facets in place and multi-slot sets can't race.
    ontology_annotations: dict[str, list[dict]] = field(default_factory=dict)
    # The free part of the generated name (method or fixed condition).
    discriminator: str | None = None
    # Importers may create a protocol whose name still needs facts (flagged, cannot publish).
    allow_incomplete: bool = False
    # The form the dialog started from; decides whether the assay format follows the targets.
    form_id: uuid.UUID | None = None
    # Bare siblings (same base name, no discriminator) told apart in the same save.
    sibling_discriminators: list[SiblingDiscriminator] = field(default_factory=list)
    # What people call the new protocol, added in the same save (cosmetic; any status).
    nicknames: list[str] = field(default_factory=list)
    # Where it comes from: [{kind, value}] (ChEMBL assay, PubChem AID, DOI, PMID, URL).
    references: list[dict[str, str]] = field(default_factory=list)


class CreateProtocol:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ProtocolRepository,
        dispatcher: EventDispatcherProtocol,
        *,
        names: ProtocolNameService,
        form_repo: ProtocolFormRepository,
        target_repo: TargetRepository,
        settings_repo: WorkspaceSettingsRepository | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._names = names
        self._settings_repo = settings_repo
        self._forms = form_repo
        self._targets = target_repo

    async def __call__(
        self, input: CreateProtocolCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_authenticated(auth)
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        # Reserved-name guard runs at the use-case boundary (the entity
        # constructor stays permissive so legacy DB rows hydrate cleanly).
        for rd in input.readout_definitions:
            rd_name = rd.get("name", "")
            if is_reserved_readout_name(rd_name):
                return Failure(
                    ValidationError(
                        f"ReadoutDefinition name '{rd_name}' collides with a "
                        f"reserved well-metadata name. Reserved: "
                        f"{sorted(RESERVED_READOUT_NAMES)}."
                    )
                )

        # Use a temporary protocol_id for building owned entities;
        # Protocol.__init__ will rebind them to the actual aggregate ID.
        tmp_protocol_id = uuid.uuid4()

        readout_defs = []
        for rd in input.readout_definitions:
            dr_config = None
            if rd.get("data_type") == "dose_response" and rd.get("dose_response_config"):
                dr_config = deserialize_dose_response_config(rd["dose_response_config"])

            # Resolve normalizations from new (preferred) or legacy
            # (single-value) request shape. Legacy NONE / "none" / missing →
            # empty set.
            raw_norms = rd.get("normalizations")
            if raw_norms is not None:
                resolved_norms: frozenset[ReadoutNormalization] = frozenset(
                    ReadoutNormalization(n) for n in raw_norms
                )
            elif rd.get("normalization"):
                legacy = ReadoutNormalization(rd["normalization"])
                resolved_norms = (
                    frozenset({legacy}) if legacy != ReadoutNormalization.NONE else frozenset()
                )
            else:
                resolved_norms = frozenset()

            readout_defs.append(
                ReadoutDefinition(
                    protocol_id=tmp_protocol_id,
                    name=rd["name"],
                    description=rd.get("description"),
                    data_type=ReadoutDataType(rd["data_type"]),
                    unit=rd.get("unit"),
                    aggregation=ReadoutAggregation(rd["aggregation"])
                    if rd.get("aggregation")
                    else ReadoutAggregation.NONE,
                    precision=rd.get("precision"),
                    normalizations=resolved_norms,
                    is_calculated=rd.get("is_calculated", False),
                    calculation_formula=rd.get("calculation_formula"),
                    display_order=rd.get("display_order", 0),
                    pick_list_values=rd.get("pick_list_values"),
                    dose_response_config=dr_config,
                )
            )

        condition_defs = [
            ConditionDefinition(
                protocol_id=tmp_protocol_id,
                name=cd["name"],
                data_type=ConditionDataType(cd["data_type"]),
                unit=cd.get("unit"),
                pick_list_values=cd.get("pick_list_values"),
                fixed_value=cd.get("fixed_value"),
            )
            for cd in input.condition_definitions
        ]
        references = [
            ProtocolReference(kind=r["kind"], value=r["value"])  # type: ignore[arg-type]
            for r in input.references
        ]

        ontology_annotations = {
            slot: [
                OntologyTerm(
                    term_id=t["term_id"],
                    label=t["label"],
                    ontology_source=t["ontology_source"],
                    uri=t.get("uri"),
                )
                for t in terms
            ]
            for slot, terms in input.ontology_annotations.items()
            if terms
        }

        target_ids = list(dict.fromkeys(input.target_ids))
        async with self._uow:
            await self._repo.lock_naming(input.workspace_id)
            fmt = await assay_format_from_form(
                self._forms,
                self._targets,
                input.workspace_id,
                input.form_id,
                target_ids,
                ontology_annotations,
            )
            if isinstance(fmt, Failure):
                return fmt
            if fmt.unwrap() is not None:
                ontology_annotations["assay_format"] = [fmt.unwrap()]
            discriminator = await self._names.clean_discriminator(
                input.workspace_id, input.discriminator
            )
            derivation = await self._names.derive(
                input.workspace_id,
                category=input.category,
                target_ids=target_ids,
                annotations=ontology_annotations,
                discriminator=discriminator,
            )
            checked = self._names.check(
                derivation, person=True, allow_incomplete=input.allow_incomplete
            )
            if isinstance(checked, Failure):
                return checked
            code = await mint_protocol_code(
                settings_repo=self._settings_repo,
                protocol_repo=self._repo,
                workspace_id=input.workspace_id,
            )
            try:
                protocol = Protocol.create(
                    workspace_id=input.workspace_id,
                    name=derivation.rendered.name,
                    name_base=derivation.rendered.base,
                    name_flag=checked.unwrap(),
                    discriminator=discriminator,
                    code=code,
                    description=input.description,
                    protocol_type=ProtocolType(input.protocol_type),
                    category=input.category,
                    created_by=auth.user_id,
                    dose_unit=ConcentrationUnit(input.dose_unit),
                    pos_control_signal=PosControlSignal(input.pos_control_signal),
                    readout_definitions=readout_defs,
                    condition_definitions=condition_defs or None,
                    ontology_annotations=ontology_annotations or None,
                    references=references,
                )
            except DomainError as exc:  # e.g. two readouts or two conditions with one name
                return Failure(exc)
            for nickname in input.nicknames:
                protocol.add_nickname(nickname)
            await self._repo.save(protocol)
            # Initial direct targets — idempotent, workspace-checked in the repo.
            # An unknown/cross-workspace target aborts the create (404) instead
            # of being silently dropped from the new protocol.
            for target_id in target_ids:
                link = await self._repo.add_direct_target(
                    input.workspace_id, protocol.id, target_id
                )
                if link is TargetLinkResult.TARGET_NOT_FOUND:
                    return Failure(NotFoundError("Target", str(target_id)))
            await self._names.flag_siblings(input.workspace_id, derivation)
            offered = {s.protocol_id for s in derivation.bare_siblings}
            for item in input.sibling_discriminators:
                # Every failure below names the sibling, and returning before the commit
                # rolls back the new protocol with it.
                sibling = await self._repo.find_by_id_in_workspace(
                    input.workspace_id, item.protocol_id
                )
                if sibling is None:
                    return Failure(NotFoundError("Protocol", str(item.protocol_id)))
                label = sibling.code or sibling.name
                if item.protocol_id not in offered:
                    return Failure(ValidationError(f"{label} does not share this protocol's name"))
                try:
                    renamed = await set_discriminator_and_rename(
                        self._names,
                        sibling,
                        item.discriminator,
                        reason=item.reason,
                        audit_reason=correction_reason(
                            item.reason, f"Distinguished from {protocol.code}"
                        ),
                        user_id=auth.user_id if auth else None,
                    )
                    if isinstance(renamed, Failure):
                        error = renamed.failure()
                        if isinstance(error, NameTakenError):
                            # The holder may be the new protocol, whose code is rolled back.
                            return Failure(
                                ConflictError(f'{label}: "{error.name}" is already taken')
                            )
                        return Failure(_about(label, error))
                    await self._repo.save(sibling)
                except (ConflictError, ValidationError, ConcurrencyConflictError) as exc:
                    # Published, locked or retired since the preview, or saved meanwhile.
                    return Failure(_about(label, exc))
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(protocol)
