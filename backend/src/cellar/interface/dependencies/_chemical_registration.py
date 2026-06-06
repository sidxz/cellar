"""Chemical-registration, disclosure, merge, and bulk-registration deps."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from cellar.application.chemical_registration.bulk_registration_service import (
    BulkRegistrationService,
)
from cellar.application.chemical_registration.confirm_disclosure import ConfirmDisclosure
from cellar.application.chemical_registration.create_relationship import CreateRelationship
from cellar.application.chemical_registration.decide_merge_candidates import (
    DecideMergeCandidates,
)
from cellar.application.chemical_registration.delete_relationship import DeleteRelationship
from cellar.application.chemical_registration.depict_molecules import DepictMolecules
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
from cellar.application.chemical_registration.merge_service import MergeService
from cellar.application.chemical_registration.preview_bulk_registration_file import (
    PreviewBulkRegistrationFile,
)
from cellar.application.chemical_registration.register_molecule import RegisterMolecule
from cellar.application.chemical_registration.reject_disclosure import RejectDisclosure
from cellar.application.chemical_registration.resolve_disclosure_conflict import (
    ResolveDisclosureConflict,
)
from cellar.application.chemical_registration.search_molecules import SearchMolecules
from cellar.application.chemical_registration.start_bulk_registration import StartBulkRegistration
from cellar.application.chemical_registration.update_molecule import UpdateMolecule

from ._core import _get_use_case

__all__ = [
    "AddIdentifierDep",
    # Bulk registration
    "BulkRegistrationServiceDep",
    "ConfirmDisclosureDep",
    "CreateRelationshipDep",
    "DecideMergeCandidatesDep",
    "DeleteRelationshipDep",
    "DepictMoleculesDep",
    # Disclosure + merge
    "DisclosureServiceDep",
    "ExportMoleculesSDFDep",
    "GetBulkRegistrationRuntimeStatusDep",
    "GetDisclosureDep",
    "GetMergeHistoryDep",
    "GetMergeImpactDep",
    "GetMoleculeByIdentifierDep",
    "GetMoleculeDep",
    "ListBulkRegistrationItemsDep",
    "ListDisclosuresByWorkspaceDep",
    "ListDisclosuresDep",
    "ListIdentifiersDep",
    "ListMoleculesByIdsDep",
    "ListMoleculesDep",
    "ListRelationshipsDep",
    "MergeServiceDep",
    "PreviewBulkRegistrationFileDep",
    # Chemical registration
    "RegisterMoleculeDep",
    "RejectDisclosureDep",
    "RemoveIdentifierDep",
    "ResolveDisclosureConflictDep",
    "SearchMoleculesDep",
    "StartBulkRegistrationDep",
    "UpdateMoleculeDep",
]

# --- Chemical Registration dependencies ---
RegisterMoleculeDep = Annotated[RegisterMolecule, Depends(_get_use_case(RegisterMolecule))]
GetMoleculeDep = Annotated[GetMolecule, Depends(_get_use_case(GetMolecule))]
ListMoleculesDep = Annotated[ListMolecules, Depends(_get_use_case(ListMolecules))]
ListMoleculesByIdsDep = Annotated[ListMoleculesByIds, Depends(_get_use_case(ListMoleculesByIds))]
UpdateMoleculeDep = Annotated[UpdateMolecule, Depends(_get_use_case(UpdateMolecule))]
SearchMoleculesDep = Annotated[SearchMolecules, Depends(_get_use_case(SearchMolecules))]
DepictMoleculesDep = Annotated[DepictMolecules, Depends(_get_use_case(DepictMolecules))]
ExportMoleculesSDFDep = Annotated[ExportMoleculesSDF, Depends(_get_use_case(ExportMoleculesSDF))]
GetMoleculeByIdentifierDep = Annotated[
    GetMoleculeByIdentifier, Depends(_get_use_case(GetMoleculeByIdentifier))
]
AddIdentifierDep = Annotated[AddIdentifier, Depends(_get_use_case(AddIdentifier))]
RemoveIdentifierDep = Annotated[RemoveIdentifier, Depends(_get_use_case(RemoveIdentifier))]
ListIdentifiersDep = Annotated[ListIdentifiers, Depends(_get_use_case(ListIdentifiers))]
CreateRelationshipDep = Annotated[CreateRelationship, Depends(_get_use_case(CreateRelationship))]
ListRelationshipsDep = Annotated[ListRelationships, Depends(_get_use_case(ListRelationships))]
DeleteRelationshipDep = Annotated[DeleteRelationship, Depends(_get_use_case(DeleteRelationship))]

# --- Disclosure & Merge dependencies ---
DisclosureServiceDep = Annotated[DisclosureService, Depends(_get_use_case(DisclosureService))]
MergeServiceDep = Annotated[MergeService, Depends(_get_use_case(MergeService))]
GetDisclosureDep = Annotated[GetDisclosure, Depends(_get_use_case(GetDisclosure))]
ListDisclosuresDep = Annotated[ListDisclosures, Depends(_get_use_case(ListDisclosures))]
ListDisclosuresByWorkspaceDep = Annotated[
    ListDisclosuresByWorkspace, Depends(_get_use_case(ListDisclosuresByWorkspace))
]
ResolveDisclosureConflictDep = Annotated[
    ResolveDisclosureConflict, Depends(_get_use_case(ResolveDisclosureConflict))
]
GetMergeHistoryDep = Annotated[GetMergeHistory, Depends(_get_use_case(GetMergeHistory))]
ConfirmDisclosureDep = Annotated[ConfirmDisclosure, Depends(_get_use_case(ConfirmDisclosure))]
RejectDisclosureDep = Annotated[RejectDisclosure, Depends(_get_use_case(RejectDisclosure))]
DecideMergeCandidatesDep = Annotated[
    DecideMergeCandidates, Depends(_get_use_case(DecideMergeCandidates))
]
GetMergeImpactDep = Annotated[GetMergeImpact, Depends(_get_use_case(GetMergeImpact))]
BulkRegistrationServiceDep = Annotated[
    BulkRegistrationService, Depends(_get_use_case(BulkRegistrationService))
]
StartBulkRegistrationDep = Annotated[
    StartBulkRegistration, Depends(_get_use_case(StartBulkRegistration))
]
GetBulkRegistrationRuntimeStatusDep = Annotated[
    GetBulkRegistrationRuntimeStatus,
    Depends(_get_use_case(GetBulkRegistrationRuntimeStatus)),
]
PreviewBulkRegistrationFileDep = Annotated[
    PreviewBulkRegistrationFile, Depends(_get_use_case(PreviewBulkRegistrationFile))
]
ListBulkRegistrationItemsDep = Annotated[
    ListBulkRegistrationItems, Depends(_get_use_case(ListBulkRegistrationItems))
]
