"""Chemical registration bindings: molecule, identifiers, relationships,
search, merge side effects, merge + disclosure services, confirm/reject/resolve,
bulk registration, synthesis routes.
"""

from __future__ import annotations

from lagom import Container, Singleton
from sqlalchemy.ext.asyncio import async_sessionmaker

from cellar.application.admin.admin_delete_registry import register_admin_delete
from cellar.application.chemical_registration.bulk_registration_item_reader import (
    BulkRegistrationItemReader,
)
from cellar.application.chemical_registration.bulk_registration_orchestrator import (
    BulkRegistrationOrchestrator,
)
from cellar.application.chemical_registration.bulk_registration_service import (
    BulkRegistrationService,
)
from cellar.application.chemical_registration.confirm_disclosure import ConfirmDisclosure
from cellar.application.chemical_registration.create_relationship import CreateRelationship
from cellar.application.chemical_registration.delete_relationship import DeleteRelationship
from cellar.application.chemical_registration.depict_molecules import (
    DepictionService,
    DepictMolecules,
)
from cellar.application.chemical_registration.disclosure_service import DisclosureService
from cellar.application.chemical_registration.export_sdf import ExportMoleculesSDF
from cellar.application.chemical_registration.get_bulk_registration_runtime_status import (
    GetBulkRegistrationRuntimeStatus,
)
from cellar.application.chemical_registration.get_disclosure import GetDisclosure
from cellar.application.chemical_registration.get_merge_history import GetMergeHistory
from cellar.application.chemical_registration.get_merge_impact import GetMergeImpact
from cellar.application.chemical_registration.get_molecule import GetMolecule
from cellar.application.chemical_registration.get_molecule_by_identifier import (
    GetMoleculeByIdentifier,
)
from cellar.application.chemical_registration.identifiers import (
    AddIdentifier,
    ListIdentifiers,
    RemoveIdentifier,
)
from cellar.application.chemical_registration.list_bulk_registration_items import (
    ListBulkRegistrationItems,
)
from cellar.application.chemical_registration.list_disclosures import ListDisclosures
from cellar.application.chemical_registration.list_disclosures_by_workspace import (
    ListDisclosuresByWorkspace,
)
from cellar.application.chemical_registration.list_molecules import ListMolecules
from cellar.application.chemical_registration.list_molecules_by_ids import ListMoleculesByIds
from cellar.application.chemical_registration.list_relationships import ListRelationships
from cellar.application.chemical_registration.merge_impact_reader import MergeImpactReader
from cellar.application.chemical_registration.merge_service import MergeService
from cellar.application.chemical_registration.merge_side_effect_registry import (
    MergeSideEffectRegistry,
)
from cellar.application.chemical_registration.molecule_reader import MoleculeReader
from cellar.application.chemical_registration.preview_bulk_registration_file import (
    BulkFileParserProtocol,
    PreviewBulkRegistrationFile,
)
from cellar.application.chemical_registration.protocols import StructureProcessorProtocol
from cellar.application.chemical_registration.register_molecule import RegisterMolecule
from cellar.application.chemical_registration.reject_disclosure import RejectDisclosure
from cellar.application.chemical_registration.resolve_disclosure_conflict import (
    ResolveDisclosureConflict,
)
from cellar.application.chemical_registration.search_molecules import SearchMolecules
from cellar.application.chemical_registration.start_bulk_registration import (
    StartBulkRegistration,
)
from cellar.application.chemical_registration.synthesis_routes import (
    AddReactionStep,
    CreateSynthesisRoute,
    DeleteSynthesisRoute,
    DeprecateSynthesisRoute,
    GetSynthesisRoute,
    ListSynthesisRoutesByMolecule,
    RecordStepOutcome,
    RemoveReactionStep,
    SetPreferredRoute,
    UpdateSynthesisRoute,
    ValidateSynthesisRoute,
)
from cellar.application.chemical_registration.update_molecule import UpdateMolecule
from cellar.application.inventory.salt_matcher import SaltMatcher
from cellar.application.inventory.sync_batch_identifier_mirrors import (
    SyncBatchIdentifierMirrors,
)
from cellar.application.workspace_config.custom_field_validator import CustomFieldValidator
from cellar.infrastructure.messaging.event_dispatcher import EventDispatcher
from cellar.infrastructure.messaging.merge_handlers import (
    BatchMergeSideEffect,
    CompoundFlagMergeSideEffect,
    DoseResponseCurveMergeSideEffect,
    MixtureComponentMergeSideEffect,
    MoleculeRelationshipMergeSideEffect,
    ReadoutDataMergeSideEffect,
    SampleRequestMergeSideEffect,
    SynthesisRequestMergeSideEffect,
    SynthesisRouteMergeSideEffect,
)
from cellar.infrastructure.parsers.chemical_file_parser import BulkFileParserAdapter
from cellar.infrastructure.persistence.sqlalchemy.attachment.attachment_merge_side_effect import (
    AttachmentMergeSideEffect,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_item_reader import (
    SQLAlchemyBulkRegistrationItemReader,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.bulk_registration_repository import (
    SQLAlchemyBulkRegistrationRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.disclosure_request_repository import (
    SQLAlchemyDisclosureRequestRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.merge_event_repository import (
    SQLAlchemyMergeEventRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.merge_impact_reader import (
    SQLAlchemyMergeImpactReader,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_relationship_repository import (
    SQLAlchemyMoleculeRelationshipRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_repository import (
    SQLAlchemyMoleculeRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.synthesis_route_repository import (
    SQLAlchemySynthesisRouteRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.inventory.batch_repository import (
    SQLAlchemyBatchRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.collection_merge_side_effect import (
    CollectionMergeSideEffect,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.custom_field_definition_repository import (
    SQLAlchemyCustomFieldDefinitionRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
    SQLAlchemySaltEntryRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.rdkit.depiction import DepictionGenerator
from cellar.infrastructure.storage.fsspec_client import FsspecStorageClient


def register_chemical_registration(container: Container) -> None:
    # Force cascade rules to register at DI bootstrap.
    import cellar.infrastructure.cascade.rules_chemical_registration  # noqa: F401

    # --- Depiction service (stateless infra, singleton) ---
    container[DepictionGenerator] = Singleton(DepictionGenerator)
    container[DepictionService] = lambda c: c[DepictionGenerator]
    container[DepictMolecules] = lambda c: DepictMolecules(c[DepictionService])

    # --- Molecule use cases ---
    def _mol_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
            return uc_cls(
                uow,
                SQLAlchemyMoleculeRepository(uow),
                c[EventDispatcher],
                c[StructureProcessorProtocol],
                validator,
            )

        return _f

    def _mol_cmd_no_proc(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyMoleculeRepository(uow), c[EventDispatcher])

        return _f

    def _mol_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemyMoleculeRepository(uow))

        return _f

    def _register_molecule(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))

        # DisclosureService gets its own independent UoW — it manages its own txn.
        ds_uow = AsyncUnitOfWork(c[async_sessionmaker])
        ds_mol_repo = SQLAlchemyMoleculeRepository(ds_uow)
        ds_merge_svc = MergeService(
            uow=ds_uow,
            molecule_repo=ds_mol_repo,
            merge_event_repo=SQLAlchemyMergeEventRepository(ds_uow),
            dispatcher=c[EventDispatcher],
            side_effect_registry=c[MergeSideEffectRegistry],
        )
        ds = DisclosureService(
            uow=ds_uow,
            molecule_repo=ds_mol_repo,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(ds_uow),
            structure_processor=c[StructureProcessorProtocol],
            merge_service=ds_merge_svc,
            dispatcher=c[EventDispatcher],
        )

        ws_settings_repo = SQLAlchemyWorkspaceSettingsRepository(uow)

        return RegisterMolecule(
            uow=uow,
            repo=mol_repo,
            dispatcher=c[EventDispatcher],
            structure_processor=c[StructureProcessorProtocol],
            custom_field_validator=validator,
            disclosure_service=ds,
            workspace_settings_repo=ws_settings_repo,
        )

    container.define(RegisterMolecule, _register_molecule)

    def _update_molecule(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        validator = CustomFieldValidator(repo=SQLAlchemyCustomFieldDefinitionRepository(uow))
        return UpdateMolecule(
            uow, SQLAlchemyMoleculeRepository(uow), c[EventDispatcher], validator
        )

    container.define(UpdateMolecule, _update_molecule)
    container.define(GetMolecule, _mol_query(GetMolecule))
    container.define(ListMolecules, _mol_query(ListMolecules))
    container.define(ListMoleculesByIds, _mol_query(ListMoleculesByIds))
    container.define(GetMoleculeByIdentifier, _mol_query(GetMoleculeByIdentifier))
    def _add_identifier(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        batch_repo = SQLAlchemyBatchRepository(uow)
        sync = SyncBatchIdentifierMirrors(batch_repo)
        return AddIdentifier(uow, mol_repo, c[EventDispatcher], sync=sync, batch_repo=batch_repo)

    container.define(AddIdentifier, _add_identifier)
    container.define(RemoveIdentifier, _mol_cmd_no_proc(RemoveIdentifier))
    container.define(ListIdentifiers, _mol_query(ListIdentifiers))

    def _search_molecules(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return SearchMolecules(
            uow,
            SQLAlchemyMoleculeRepository(uow),
            c[MoleculeReader],
            c[StructureProcessorProtocol],
        )

    container.define(
        SQLAlchemyMoleculeReader,
        Singleton(lambda c: SQLAlchemyMoleculeReader(c[async_sessionmaker])),
    )
    container.define(MoleculeReader, lambda c: c[SQLAlchemyMoleculeReader])
    container.define(SearchMolecules, _search_molecules)

    def _export_sdf(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ExportMoleculesSDF(
            uow, SQLAlchemyMoleculeRepository(uow), c[StructureProcessorProtocol]
        )

    container.define(ExportMoleculesSDF, _export_sdf)

    # --- Molecule Relationships ---
    def _rel_cmd(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateRelationship(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            relationship_repo=SQLAlchemyMoleculeRelationshipRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    def _rel_query(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListRelationships(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            relationship_repo=SQLAlchemyMoleculeRelationshipRepository(uow),
        )

    def _rel_delete(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return DeleteRelationship(
            uow=uow,
            relationship_repo=SQLAlchemyMoleculeRelationshipRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(CreateRelationship, _rel_cmd)
    container.define(ListRelationships, _rel_query)
    container.define(DeleteRelationship, _rel_delete)

    # --- Merge & Disclosure ---
    # MergeSideEffectRegistry is a singleton whose attachment side-effect needs
    # the shared FsspecStorageClient — resolved from the container at build time.
    def _build_merge_registry(c: Container):
        return MergeSideEffectRegistry(
            [
                SampleRequestMergeSideEffect(),
                BatchMergeSideEffect(),
                ReadoutDataMergeSideEffect(),
                DoseResponseCurveMergeSideEffect(),
                CompoundFlagMergeSideEffect(),
                MoleculeRelationshipMergeSideEffect(),
                MixtureComponentMergeSideEffect(),
                SynthesisRouteMergeSideEffect(),
                SynthesisRequestMergeSideEffect(),
                CollectionMergeSideEffect(),
                AttachmentMergeSideEffect(c[FsspecStorageClient]),
            ]
        )

    container.define(MergeSideEffectRegistry, Singleton(_build_merge_registry))

    def _merge_service(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return MergeService(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
            dispatcher=c[EventDispatcher],
            side_effect_registry=c[MergeSideEffectRegistry],
        )

    container.define(MergeService, _merge_service)

    def _disclosure_service(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        # MergeService must share the same UoW as DisclosureService because
        # merge_in_transaction() expects the caller to manage the transaction.
        merge_svc = MergeService(
            uow=uow,
            molecule_repo=mol_repo,
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
            dispatcher=c[EventDispatcher],
            side_effect_registry=c[MergeSideEffectRegistry],
        )
        return DisclosureService(
            uow=uow,
            molecule_repo=mol_repo,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            structure_processor=c[StructureProcessorProtocol],
            merge_service=merge_svc,
            dispatcher=c[EventDispatcher],
        )

    container.define(DisclosureService, _disclosure_service)

    def _get_disclosure(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetDisclosure(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
        )

    container.define(GetDisclosure, _get_disclosure)

    def _list_disclosures(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListDisclosures(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
        )

    container.define(ListDisclosures, _list_disclosures)

    def _list_disclosures_by_workspace(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListDisclosuresByWorkspace(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
        )

    container.define(ListDisclosuresByWorkspace, _list_disclosures_by_workspace)

    def _resolve_conflict(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        merge_svc = MergeService(
            uow=uow,
            molecule_repo=mol_repo,
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
            dispatcher=c[EventDispatcher],
            side_effect_registry=c[MergeSideEffectRegistry],
        )
        return ResolveDisclosureConflict(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            molecule_repo=mol_repo,
            merge_service=merge_svc,
            structure_processor=c[StructureProcessorProtocol],
            dispatcher=c[EventDispatcher],
        )

    container.define(ResolveDisclosureConflict, _resolve_conflict)

    def _merge_history(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return GetMergeHistory(
            uow=uow,
            molecule_repo=SQLAlchemyMoleculeRepository(uow),
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
        )

    container.define(GetMergeHistory, _merge_history)

    def _confirm_disclosure(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        mol_repo = SQLAlchemyMoleculeRepository(uow)
        merge_svc = MergeService(
            uow=uow,
            molecule_repo=mol_repo,
            merge_event_repo=SQLAlchemyMergeEventRepository(uow),
            dispatcher=c[EventDispatcher],
            side_effect_registry=c[MergeSideEffectRegistry],
        )
        return ConfirmDisclosure(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            merge_service=merge_svc,
            dispatcher=c[EventDispatcher],
        )

    container.define(ConfirmDisclosure, _confirm_disclosure)

    def _reject_disclosure(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return RejectDisclosure(
            uow=uow,
            disclosure_repo=SQLAlchemyDisclosureRequestRepository(uow),
            dispatcher=c[EventDispatcher],
        )

    container.define(RejectDisclosure, _reject_disclosure)

    container.define(
        MergeImpactReader,
        lambda c: SQLAlchemyMergeImpactReader(c[async_sessionmaker]),
    )
    container.define(
        GetMergeImpact,
        lambda c: GetMergeImpact(reader=c[MergeImpactReader]),
    )

    # --- Bulk Registration ---
    def _bulk_registration_service(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return BulkRegistrationService(
            uow=uow,
            bulk_reg_repo=SQLAlchemyBulkRegistrationRepository(uow),
            mol_repo=SQLAlchemyMoleculeRepository(uow),
            dispatcher=c[EventDispatcher],
            structure_processor=c[StructureProcessorProtocol],
            salt_matcher=SaltMatcher(SQLAlchemySaltEntryRepository(uow)),
            batch_repo=SQLAlchemyBatchRepository(uow),
            settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
        )

    container.define(BulkRegistrationService, _bulk_registration_service)

    # Preview + items list (Change 2/3 of bulk wizard rework)
    container.define(BulkFileParserProtocol, lambda c: BulkFileParserAdapter())
    container.define(
        BulkRegistrationItemReader,
        lambda c: SQLAlchemyBulkRegistrationItemReader(c[async_sessionmaker]),
    )
    container.define(
        PreviewBulkRegistrationFile,
        lambda c: PreviewBulkRegistrationFile(parser=c[BulkFileParserProtocol]),
    )

    def _list_bulk_reg_items(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return ListBulkRegistrationItems(
            uow=uow,
            repo=SQLAlchemyBulkRegistrationRepository(uow),
            reader=c[BulkRegistrationItemReader],
        )

    container.define(ListBulkRegistrationItems, _list_bulk_reg_items)

    container.define(
        StartBulkRegistration,
        lambda c: StartBulkRegistration(
            orchestrator=c[BulkRegistrationOrchestrator],
            sync_service=c[BulkRegistrationService],
            parser=c[BulkFileParserProtocol],
        ),
    )
    container.define(
        GetBulkRegistrationRuntimeStatus,
        lambda c: GetBulkRegistrationRuntimeStatus(
            orchestrator=c[BulkRegistrationOrchestrator],
        ),
    )

    # --- Synthesis Routes ---
    def _synth_route_cmd(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySynthesisRouteRepository(uow), c[EventDispatcher])

        return _f

    def _synth_route_query(uc_cls: type):
        def _f(c: Container):
            uow = AsyncUnitOfWork(c[async_sessionmaker])
            return uc_cls(uow, SQLAlchemySynthesisRouteRepository(uow))

        return _f

    def _create_synth_route(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateSynthesisRoute(
            uow,
            SQLAlchemySynthesisRouteRepository(uow),
            SQLAlchemyMoleculeRepository(uow),
            c[EventDispatcher],
        )

    container.define(CreateSynthesisRoute, _create_synth_route)
    container.define(GetSynthesisRoute, _synth_route_query(GetSynthesisRoute))
    container.define(
        ListSynthesisRoutesByMolecule, _synth_route_query(ListSynthesisRoutesByMolecule)
    )
    container.define(AddReactionStep, _synth_route_cmd(AddReactionStep))
    container.define(RecordStepOutcome, _synth_route_cmd(RecordStepOutcome))
    container.define(ValidateSynthesisRoute, _synth_route_cmd(ValidateSynthesisRoute))
    container.define(SetPreferredRoute, _synth_route_cmd(SetPreferredRoute))
    container.define(DeprecateSynthesisRoute, _synth_route_cmd(DeprecateSynthesisRoute))
    container.define(UpdateSynthesisRoute, _synth_route_cmd(UpdateSynthesisRoute))
    container.define(DeleteSynthesisRoute, _synth_route_cmd(DeleteSynthesisRoute))
    container.define(RemoveReactionStep, _synth_route_cmd(RemoveReactionStep))

    # --- Admin Hard-Delete Registry (Tier 1) ---
    register_admin_delete(
        entity_type="compound_flag",
        table="compound_flags",
        label_field=None,
    )
    register_admin_delete(
        entity_type="molecule_relationship",
        table="molecule_relationships",
        label_field=None,
    )
    register_admin_delete(
        entity_type="synthesis_route",
        table="synthesis_routes",
        label_field="name",
    )
    register_admin_delete(
        entity_type="molecule",
        table="molecules",
        label_field="registration_number",
    )


def build_chemical_registration_admin_repos(uow) -> dict:
    """Build the repo map for chemical-registration Tier-1 admin deletes."""
    from cellar.application.admin._adapter import RepoAdapter
    from cellar.infrastructure.persistence.sqlalchemy.screening_assay.compound_flag_repository import (
        SQLAlchemyCompoundFlagRepository,
    )

    return {
        "compound_flag": RepoAdapter(
            SQLAlchemyCompoundFlagRepository(uow), find="find_by_id_in_workspace"
        ),
        "molecule_relationship": RepoAdapter(
            SQLAlchemyMoleculeRelationshipRepository(uow), find="find_by_id_in_workspace"
        ),
        "synthesis_route": RepoAdapter(
            SQLAlchemySynthesisRouteRepository(uow), find="find_by_id_in_workspace"
        ),
        "molecule": RepoAdapter(SQLAlchemyMoleculeRepository(uow), find="find_by_id_in_workspace"),
    }
