"""RegisterMolecule command — register a new molecule (disclosed or undisclosed)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from typing import TYPE_CHECKING, Any

from returns.pipeline import is_successful
from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.chemical_registration.discloser_pick import check_discloser_pick
from cellar.application.chemical_registration.protocols import (
    DetectedSaltDTO,
    StructureProcessorProtocol,
)
from cellar.application.chemical_registration.registration_classifier import (
    RegistrationForecast,
    classify_disclosed,
    classify_undisclosed,
    collect_identifiers,
    held_elsewhere,
    skipped_id_warning,
)
from cellar.application.research_organization.project_links import (
    ProjectAccess,
    link_molecules_to_projects,
)
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.org_directory import OrgDirectoryPort
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.custom_field_validator import CustomFieldValidator
from cellar.domain.chemical_registration.disclosure_request import DisclosureRequest
from cellar.domain.chemical_registration.enums import MoleculeType, RegistrationAction
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_identifier import (
    MoleculeIdentifier,
    normalize_identifier,
)
from cellar.domain.chemical_registration.repository import (
    DisclosureRequestRepository,
    MoleculeRepository,
)
from cellar.domain.shared.errors import ConflictError, DomainError, ValidationError
from cellar.domain.shared.events import DomainEvent
from cellar.domain.workspace_config.enums import FieldTarget
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings

if TYPE_CHECKING:
    from cellar.application.chemical_registration.disclosure_service import DisclosureService


@dataclass(frozen=True)
class RegistrationOutcome:
    """Result of a molecule registration."""

    molecule: Molecule
    is_new: bool
    action: RegistrationAction = RegistrationAction.REGISTERED
    qc_warnings: list[str] = field(default_factory=list)
    detected_salt: DetectedSaltDTO | None = None
    # Disclosure detection fields (populated by Task 3)
    needs_merge_confirmation: bool = False
    matched_molecule_id: uuid.UUID | None = None
    disclosure_id: uuid.UUID | None = None
    conflict_reason: str | None = None
    # Stored-only IDs another compound holds, one warning each (not stored here).
    skipped_ids: tuple[str, ...] = ()
    # What the registration left as it was: a structure the vault id overrode.
    notes: tuple[str, ...] = ()
    ids_added: int = 0  # identifiers this call stored on the compound (the name included)


@dataclass(frozen=True, kw_only=True)
class ExternalId:
    identifier: str
    identifier_type: str
    source: str | None = None  # a Source label from the file; None → "Registration (…)"
    # False = stored only: never matches or conflicts; kept only when no other
    # compound holds the text (CDD mapper spec 2026-11-18 §3a).
    decides: bool = True
    # The row's own id in the source it came from (a CDD vault molecule id): the compound
    # holding this text with this type is the row's compound (decision 6).
    vault_id: bool = False


def external_ids(raw: Iterable[Mapping[str, Any]]) -> list[ExternalId]:
    """Item dicts ``{"identifier", "identifier_type", "source"?, "decides"?}``."""
    return [
        ExternalId(
            identifier=d["identifier"],
            identifier_type=d["identifier_type"],
            source=d.get("source"),
            decides=d.get("decides", True),
            vault_id=d.get("vault_id", False),
        )
        for d in raw
    ]


@dataclass(frozen=True, kw_only=True)
class RegisterMoleculeCommand(Command):
    workspace_id: uuid.UUID
    name: str
    smiles: str | None = None  # None for undisclosed
    molecule_type: str = MoleculeType.SMALL_MOLECULE.value
    external_ids: list[ExternalId] = field(default_factory=list)
    registered_by: uuid.UUID
    # The registrant's Duar org — from their token, or the job's starter in a worker.
    registered_by_org_id: uuid.UUID | None = None
    # Who disclosed it and for which Duar org; None = the registrant and their org.
    disclosed_by: uuid.UUID | None = None
    disclosed_by_org_id: uuid.UUID | None = None
    scientist_name: str | None = None
    # Declared (possibly historic) disclosure date; only meaningful with a structure.
    disclosure_date: date | None = None
    custom_fields: dict[str, Any] | None = None
    qc_reject_threshold: int | None = None
    qc_warn_threshold: int | None = None
    promote_name_as_identifier: bool = True  # False for auto-generated names
    auto_approve: bool = True  # False from wizard — merge candidates need confirmation
    # Projects to put the surviving compound in (new, matched or disclosed).
    project_ids: list[uuid.UUID] = field(default_factory=list)


def _discloser_org(input: RegisterMoleculeCommand) -> uuid.UUID | None:
    """The Duar org the structure is disclosed for: the pick, else the registrant's."""
    return input.disclosed_by_org_id or input.registered_by_org_id


def _matched(forecast: RegistrationForecast) -> Molecule:
    """The molecule a DEDUPLICATED / DISCLOSED forecast names; never None by contract."""
    if forecast.matched_molecule is None:
        raise AssertionError(f"forecast {forecast.action} carried no matched molecule")
    return forecast.matched_molecule


class RegisterMolecule:
    """Use case: register a new molecule or add to existing one.

    For disclosed (smiles provided):
      standardize -> QC check -> InChIKey dedup -> ID dedup -> create or add batch

    For undisclosed (smiles is None):
      ID dedup only -> create

    Names are always auto-promoted to custom identifiers and subject to
    workspace-unique enforcement (per US-001 design guardrails).
    """

    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        structure_processor: StructureProcessorProtocol,
        custom_field_validator: CustomFieldValidator | None = None,
        disclosure_repo: DisclosureRequestRepository | None = None,
        disclosure_service: DisclosureService | None = None,
        workspace_settings_repo: WorkspaceSettingsRepository | None = None,
        project_access: ProjectAccess | None = None,
        org_directory: OrgDirectoryPort | None = None,
    ) -> None:
        self._org_directory = org_directory
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._processor = structure_processor
        self._custom_field_validator = custom_field_validator
        self._disclosure_repo = disclosure_repo
        self._disclosure_service = disclosure_service
        self._workspace_settings_repo = workspace_settings_repo
        self._project_access = project_access

    async def __call__(
        self,
        input: RegisterMoleculeCommand,
        auth: AuthContext | None = None,
    ) -> Result[RegistrationOutcome, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        # Every check below compares this text with what a compound has stored; raw
        # text with a trailing non-breaking space matched nothing and was stored twice.
        input = replace(
            input,
            name=normalize_identifier(input.name),
            external_ids=[
                replace(e, identifier=normalize_identifier(e.identifier))
                for e in input.external_ids
            ],
        )
        if input.molecule_type not in MoleculeType:
            return Failure(ValidationError(f"Unknown molecule type '{input.molecule_type}'"))
        if err := await check_discloser_pick(
            auth,
            self._org_directory,
            disclosed_by=input.disclosed_by,
            disclosed_by_org_id=input.disclosed_by_org_id,
        ):
            return Failure(err)
        if input.project_ids and self._project_access is not None and auth is not None:
            # Read-only: enter and leave the UoW without committing.
            async with self._uow:
                denied = await self._project_access.check_editable(
                    input.workspace_id, input.project_ids, auth
                )
            if denied is not None:
                return Failure(denied)

        if input.smiles is not None:
            return await self._register_disclosed(input)
        if input.disclosure_date is not None:
            return Failure(ValidationError("disclosure_date requires a structure (smiles)"))
        return await self._register_undisclosed(input)

    async def _link_projects(
        self, input: RegisterMoleculeCommand, molecule_id: uuid.UUID
    ) -> list[DomainEvent]:
        """Link the surviving compound to the command's projects inside the
        caller's open unit of work; returns the audit events to dispatch."""
        if not input.project_ids:
            return []
        return list(
            await link_molecules_to_projects(
                self._repo, input.workspace_id, input.project_ids, [molecule_id]
            )
        )

    def _collect_all_identifiers(self, input: RegisterMoleculeCommand) -> set[str]:
        """Name + deciding external ids — what finds or conflicts with a compound."""
        return collect_identifiers(
            input.name,
            (ext.identifier for ext in input.external_ids if ext.decides),
            promote_name=input.promote_name_as_identifier,
        )

    def _vault_ids(self, input: RegisterMoleculeCommand) -> list[tuple[str, str]]:
        """The row's vault id, (text, type): it decides which compound a CDD row is."""
        return [
            (e.identifier, e.identifier_type)
            for e in input.external_ids
            if e.decides and e.vault_id
        ]

    async def _resolve_reg_number_config(self, workspace_id: uuid.UUID) -> tuple[str, int]:
        """Read prefix + width from WorkspaceSettings; fall back to defaults."""
        if self._workspace_settings_repo is None:
            settings = WorkspaceSettings.create_default(workspace_id=workspace_id)
        else:
            settings = await self._workspace_settings_repo.find_by_workspace_id(workspace_id)
            if settings is None:
                settings = WorkspaceSettings.create_default(workspace_id=workspace_id)
        return settings.registration_number_prefix, settings.registration_number_width

    async def _add_name_and_ids(
        self,
        mol: Molecule,
        input: RegisterMoleculeCommand,
        source: str,
    ) -> tuple[tuple[str, ...], int]:
        """Add name as custom identifier + the external_ids to molecule.

        Stored-only IDs another compound already holds are left off. Returns one
        warning per such ID, and how many identifiers were added.
        """
        existing_values = {i.identifier for i in mol.identifiers}
        own = {v.lower() for v in existing_values}
        held = await held_elsewhere(
            self._repo,
            input.workspace_id,
            (
                e.identifier
                for e in input.external_ids
                if not e.decides and e.identifier.lower() not in own
            ),
            mol.id,
        )
        skipped: list[str] = []
        before = len(mol.identifiers)

        # Auto-promote name as custom identifier (skip for auto-generated names)
        if input.name and input.promote_name_as_identifier and input.name not in existing_values:
            mol.add_identifier(
                MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=input.name,
                    identifier_type="custom",
                    source=f"Registration ({source})",
                    registered_by=input.registered_by,
                )
            )
            existing_values.add(input.name)
            own.add(input.name.lower())

        # Add explicit external IDs; deciding ones first, so a text given both
        # ways is stored as the deciding one.
        for ext_id in sorted(input.external_ids, key=lambda e: not e.decides):
            if ext_id.identifier in existing_values:
                continue
            if not ext_id.decides and ext_id.identifier.lower() in own:
                continue  # already on the compound, in another case
            if not ext_id.decides and ext_id.identifier in held:
                skipped.append(
                    skipped_id_warning(
                        ext_id.identifier,
                        held[ext_id.identifier],
                        mol.registration_number.value,
                    )
                )
                existing_values.add(ext_id.identifier)  # one warning per text
                continue
            mol.add_identifier(
                MoleculeIdentifier.create(
                    molecule_id=mol.id,
                    identifier=ext_id.identifier,
                    identifier_type=ext_id.identifier_type,
                    source=ext_id.source or f"Registration ({source})",
                    registered_by=input.registered_by,
                )
            )
            existing_values.add(ext_id.identifier)
            own.add(ext_id.identifier.lower())
        return tuple(skipped), len(mol.identifiers) - before

    async def _record_disclosure_provenance(
        self,
        input: RegisterMoleculeCommand,
        molecule_id: uuid.UUID,
        canonical_smiles: str,
        inchi_key: str,
        *,
        is_new: bool,
        resolved_to_molecule_id: uuid.UUID | None = None,
    ) -> None:
        """Create an auto-resolved DisclosureRequest for provenance tracking.

        Only records if a disclosure_repo was injected (opt-in).
        """
        if self._disclosure_repo is None:
            return

        dr = DisclosureRequest.create(
            workspace_id=input.workspace_id,
            molecule_id=molecule_id,
            disclosed_smiles=input.smiles,  # type: ignore[arg-type]
            requested_by=input.registered_by,
            requested_by_org_id=input.registered_by_org_id,
            disclosing_org_id=_discloser_org(input),
            scientist_name=input.scientist_name,
            notes="Auto-recorded during registration",
            disclosure_date=input.disclosure_date,
        )
        dr.start_processing()

        if is_new:
            dr.resolve_as_new_structure(
                canonical_smiles=canonical_smiles,
                inchi_key=inchi_key,
            )
        else:
            dr.resolve_as_merged(
                canonical_smiles=canonical_smiles,
                inchi_key=inchi_key,
                resolved_to_molecule_id=resolved_to_molecule_id,  # type: ignore[arg-type]
            )

        await self._disclosure_repo.save(dr)

    async def _register_disclosed(
        self, input: RegisterMoleculeCommand
    ) -> Result[RegistrationOutcome, DomainError]:
        # 1. Process structure (standardize + descriptors + fingerprints)
        proc_result = self._processor.process(
            input.smiles,  # type: ignore[arg-type]
            qc_reject_threshold=input.qc_reject_threshold,
        )
        if isinstance(proc_result, Failure):
            return Failure(proc_result.failure())

        processed = proc_result.unwrap()
        qc_warnings: list[str] = []
        if (
            input.qc_warn_threshold is not None
            and processed.qc_result.total_penalty >= input.qc_warn_threshold
        ):
            qc_warnings = processed.qc_result.issues

        inchi_key = processed.structure.inchi_key
        if inchi_key is None:
            return Failure(ValidationError("Structure processor returned no InChI key"))

        # Custom-field validation runs before opening the UoW since it has
        # its own session lifecycle and shouldn't share our transaction.
        if self._custom_field_validator and input.custom_fields:
            validation = await self._custom_field_validator.validate(
                input.custom_fields, FieldTarget.MOLECULE, input.workspace_id
            )
            if not is_successful(validation):
                return Failure(validation.failure())

        # Single UoW: read + branch + write happen in one transaction so
        # concurrent registrations of the same InChIKey can't both succeed
        # (the loser hits uq_molecules_ws_inchi_active on commit, surfaced as
        # a 409 by the UoW, rather than silently double-registering).
        delegate_to_disclosure: Molecule | None = None
        outcome: RegistrationOutcome | None = None
        events: list = []

        async with self._uow:
            # 2. One shared rule decides what this registration will do
            #    (PreviewRegistration asks the same function, read-only).
            forecast = await classify_disclosed(
                self._repo,
                input.workspace_id,
                inchi_key,
                self._collect_all_identifiers(input),
                detect_undisclosed=self._disclosure_service is not None,
                vault_ids=self._vault_ids(input),
            )
            existing_by_inchi: Molecule | None = None

            # 3. Branch on the forecast — every action handled, nothing falls through.
            match forecast.action:
                case RegistrationAction.CONFLICT:
                    return Failure(
                        ConflictError(forecast.conflict_reason or "Identifier conflict")
                    )
                case RegistrationAction.DISCLOSED:
                    # Defer to disclosure_service — it manages its own UoW so we
                    # exit ours first, no writes pending.
                    delegate_to_disclosure = _matched(forecast)
                case RegistrationAction.DEDUPLICATED:
                    existing_by_inchi = _matched(forecast)
                case RegistrationAction.REGISTERED:
                    pass
                case _:
                    raise AssertionError(f"unexpected registration forecast {forecast.action}")
            if existing_by_inchi is not None:
                # 6a. Duplicate InChIKey (or the compound the vault id names) — add
                # identifiers to the existing molecule
                skipped, added = await self._add_name_and_ids(
                    existing_by_inchi, input, source="duplicate"
                )
                await self._repo.save(existing_by_inchi)
                if not forecast.warnings:  # its structure is the input's
                    await self._record_disclosure_provenance(
                        input,
                        existing_by_inchi.id,
                        processed.structure.smiles,
                        inchi_key,
                        is_new=False,
                        resolved_to_molecule_id=existing_by_inchi.id,
                    )
                link_events = await self._link_projects(input, existing_by_inchi.id)
                events = [*await self._uow.commit(), *link_events]
                outcome = RegistrationOutcome(
                    molecule=existing_by_inchi,
                    is_new=False,
                    action=RegistrationAction.DEDUPLICATED,
                    qc_warnings=qc_warnings,
                    detected_salt=processed.detected_salt,
                    skipped_ids=skipped,
                    notes=forecast.warnings,
                    ids_added=added,
                )
            elif forecast.action is RegistrationAction.REGISTERED:
                # 6b. New molecule — same transaction as the conflict check, so
                # the unique InChIKey + identifier constraints are enforced
                # against the same snapshot we read above.
                prefix, width = await self._resolve_reg_number_config(input.workspace_id)
                reg_number = await self._repo.next_registration_number(
                    input.workspace_id, prefix=prefix, width=width
                )
                mol = Molecule.register_disclosed(
                    workspace_id=input.workspace_id,
                    registration_number=reg_number,
                    name=input.name,
                    molecule_type=MoleculeType(input.molecule_type),
                    structure=processed.structure,
                    descriptors=processed.descriptors,
                    custom_fields=input.custom_fields,
                    scientist_name=input.scientist_name,
                    disclosure_date=input.disclosure_date,
                    stereochemistry=processed.stereochemistry,
                    registered_by=input.registered_by,
                    registered_by_org_id=input.registered_by_org_id,
                    disclosed_by=input.disclosed_by,
                    disclosed_by_org_id=input.disclosed_by_org_id,
                )
                mol.morgan_fp = processed.fingerprints.morgan
                mol.bemis_murcko_smiles = processed.bemis_murcko_smiles
                skipped, added = await self._add_name_and_ids(mol, input, source="name")
                await self._repo.save(mol)
                await self._record_disclosure_provenance(
                    input,
                    mol.id,
                    processed.structure.smiles,
                    inchi_key,
                    is_new=True,
                )
                link_events = await self._link_projects(input, mol.id)
                events = [*await self._uow.commit(), *link_events]
                outcome = RegistrationOutcome(
                    molecule=mol,
                    is_new=True,
                    action=RegistrationAction.REGISTERED,
                    qc_warnings=qc_warnings,
                    detected_salt=processed.detected_salt,
                    skipped_ids=skipped,
                    ids_added=added,
                )

        if delegate_to_disclosure is not None and self._disclosure_service is not None:
            from cellar.application.chemical_registration.disclosure_service import (
                SubmitDisclosureCommand,
            )

            disclosure_result = await self._disclosure_service(
                SubmitDisclosureCommand(
                    workspace_id=input.workspace_id,
                    molecule_id=delegate_to_disclosure.id,
                    disclosed_smiles=input.smiles,  # type: ignore[arg-type]
                    requested_by=input.registered_by,
                    requested_by_org_id=input.registered_by_org_id,
                    disclosed_by=input.disclosed_by,
                    disclosing_org_id=_discloser_org(input),
                    scientist_name=input.scientist_name,
                    auto_approve=input.auto_approve,
                    notes="Auto-detected via identifier match during registration",
                    disclosure_date=input.disclosure_date,
                )
            )
            if isinstance(disclosure_result, Failure):
                return Failure(disclosure_result.failure())

            d_outcome = disclosure_result.unwrap()
            if d_outcome.needs_confirmation:
                action = RegistrationAction.MERGE_CANDIDATE
            elif d_outcome.was_merged:
                action = RegistrationAction.DEDUPLICATED
            else:
                action = RegistrationAction.DISCLOSED

            surviving_id = (
                d_outcome.merged_into_molecule_id
                if d_outcome.was_merged and d_outcome.merged_into_molecule_id
                else delegate_to_disclosure.id
            )
            if input.project_ids:
                # The disclosure service committed on its own UoW; link in a
                # short one of ours.
                async with self._uow:
                    link_events = await self._link_projects(input, surviving_id)
                    await self._uow.commit()
                await self._dispatcher.dispatch_all(link_events)

            return Success(
                RegistrationOutcome(
                    molecule=delegate_to_disclosure,
                    is_new=False,
                    action=action,
                    qc_warnings=qc_warnings,
                    detected_salt=processed.detected_salt,
                    needs_merge_confirmation=d_outcome.needs_confirmation,
                    matched_molecule_id=d_outcome.matched_molecule_id,
                    disclosure_id=d_outcome.disclosure_request.id,
                )
            )

        await self._dispatcher.dispatch_all(events)
        assert outcome is not None  # one of the branches above sets it
        return Success(outcome)

    async def _register_undisclosed(
        self, input: RegisterMoleculeCommand
    ) -> Result[RegistrationOutcome, DomainError]:
        async with self._uow:
            # 1. Same shared rule as the preview: identifiers are all there is.
            forecast = await classify_undisclosed(
                self._repo,
                input.workspace_id,
                self._collect_all_identifiers(input),
                vault_ids=self._vault_ids(input),
            )
            matched_molecule: Molecule | None = None
            match forecast.action:
                case RegistrationAction.CONFLICT:
                    return Failure(
                        ConflictError(forecast.conflict_reason or "Identifier conflict")
                    )
                case RegistrationAction.DEDUPLICATED:
                    matched_molecule = _matched(forecast)
                case RegistrationAction.REGISTERED:
                    pass
                case _:
                    raise AssertionError(f"unexpected registration forecast {forecast.action}")

            # 3a. Matched existing undisclosed — add new IDs
            events = []
            skipped: tuple[str, ...] = ()
            added = 0
            if matched_molecule is not None:
                skipped, added = await self._add_name_and_ids(
                    matched_molecule, input, source="duplicate"
                )
                await self._repo.save(matched_molecule)
                link_events = await self._link_projects(input, matched_molecule.id)
                events = [*await self._uow.commit(), *link_events]

        if matched_molecule is not None:
            await self._dispatcher.dispatch_all(events)
            return Success(
                RegistrationOutcome(
                    molecule=matched_molecule,
                    is_new=False,
                    action=RegistrationAction.DEDUPLICATED,
                    skipped_ids=skipped,
                    ids_added=added,
                )
            )

        # 4. New undisclosed molecule
        if self._custom_field_validator and input.custom_fields:
            validation = await self._custom_field_validator.validate(
                input.custom_fields, FieldTarget.MOLECULE, input.workspace_id
            )
            if not is_successful(validation):
                return Failure(validation.failure())

        async with self._uow:
            prefix, width = await self._resolve_reg_number_config(input.workspace_id)
            reg_number = await self._repo.next_registration_number(
                input.workspace_id, prefix=prefix, width=width
            )
            mol = Molecule.register_undisclosed(
                workspace_id=input.workspace_id,
                registration_number=reg_number,
                name=input.name,
                molecule_type=MoleculeType(input.molecule_type),
                custom_fields=input.custom_fields,
                scientist_name=input.scientist_name,
                registered_by=input.registered_by,
                registered_by_org_id=input.registered_by_org_id,
            )
            skipped, added = await self._add_name_and_ids(mol, input, source="name")

            await self._repo.save(mol)
            link_events = await self._link_projects(input, mol.id)
            events = [*await self._uow.commit(), *link_events]

        await self._dispatcher.dispatch_all(events)
        return Success(
            RegistrationOutcome(
                molecule=mol,
                is_new=True,
                action=RegistrationAction.REGISTERED,
                skipped_ids=skipped,
                ids_added=added,
            )
        )
