"""Molecule CRUD + search endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.application.chemical_registration.depict_molecules import (
    DepictMoleculesQuery,
)
from cellar.application.chemical_registration.get_molecule import GetMoleculeQuery
from cellar.application.chemical_registration.get_molecule_by_identifier import (
    GetMoleculeByIdentifierQuery,
)
from cellar.application.chemical_registration.identifiers import (
    AddIdentifierCommand,
    ListIdentifiersQuery,
    RemoveIdentifierCommand,
)
from cellar.application.chemical_registration.list_molecules import ListMoleculesQuery
from cellar.application.chemical_registration.list_molecules_by_ids import (
    ListMoleculesByIdsQuery,
)
from cellar.application.chemical_registration.register_molecule import (
    ExternalId,
    RegisterMoleculeCommand,
)
from cellar.application.chemical_registration.search_molecules import SearchMoleculesQuery
from cellar.application.chemical_registration.update_molecule import UpdateMoleculeCommand
from cellar.application.inventory.create_batch import CreateBatchCommand
from cellar.application.inventory.salt_matcher import compute_formula_weight
from cellar.application.research_organization.get_collections_for_molecule import (
    ListCollectionsForMoleculeQuery,
)
from cellar.application.research_organization.manage_molecule_projects import (
    ListMoleculeProjectsQuery,
)
from cellar.application.screening.get_molecule_test_counts import GetMoleculeTestCountsQuery
from cellar.application.shared.sentinel import UNSET
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from cellar.interface.dependencies import (
    AddIdentifierDep,
    AuthDep,
    CreateBatchDep,
    DepictMoleculesDep,
    GetMoleculeByIdentifierDep,
    GetMoleculeDep,
    GetMoleculeTestCountsDep,
    GetWorkspaceSettingsDep,
    ListCollectionsForMoleculeDep,
    ListIdentifiersDep,
    ListMoleculeProjectsDep,
    ListMoleculesByIdsDep,
    ListMoleculesDep,
    MoleculeActivityServiceDep,
    PlateReadModelServiceDep,
    PlateVisibilityUoWDep,
    RegisterMoleculeDep,
    RemoveIdentifierDep,
    SaltMatcherUoWDep,
    SearchMoleculesDep,
    UpdateMoleculeDep,
)
from cellar.interface.error_handlers import result_to_response
from cellar.interface.pagination import (
    PaginatedResponse,
    clamp_limit,
    parse_cursor,
)
from cellar.interface.routes.batches import BatchResponse

router = APIRouter(prefix="/api/v1/molecules", tags=["molecules"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class StructureResponse(BaseModel):
    smiles: str | None = None
    cxsmiles: str | None = None
    inchi: str | None = None
    inchi_key: str | None = None


class DescriptorsResponse(BaseModel):
    molecular_formula: str | None = None
    molecular_weight: float | None = None
    exact_mass: float | None = None
    logp: float | None = None
    tpsa: float | None = None
    hbd: int | None = None
    hba: int | None = None
    rotatable_bonds: int | None = None
    aromatic_rings: int | None = None
    ring_count: int | None = None
    heavy_atom_count: int | None = None
    ro5_violations: int | None = None


class IdentifierResponse(BaseModel):
    id: uuid.UUID
    identifier: str
    identifier_type: str
    source: str
    registered_by: uuid.UUID

    @classmethod
    def from_domain(cls, i: MoleculeIdentifier) -> IdentifierResponse:
        return cls(
            id=i.id,
            identifier=i.identifier,
            identifier_type=i.identifier_type,
            source=i.source,
            registered_by=i.registered_by,
        )


class MirrorSummarySkippedResponse(BaseModel):
    batch_number: str
    mirror_string: str
    reason: str


class MirrorSummaryResponse(BaseModel):
    created: int
    skipped: list[MirrorSummarySkippedResponse]

    @classmethod
    def from_domain(cls, summary) -> MirrorSummaryResponse:
        return cls(
            created=summary.created,
            skipped=[
                MirrorSummarySkippedResponse(
                    batch_number=s.batch_number,
                    mirror_string=s.mirror_string,
                    reason=s.reason,
                )
                for s in summary.skipped
            ],
        )


class AddIdentifierResponse(BaseModel):
    identifiers: list[IdentifierResponse]
    mirror_summary: MirrorSummaryResponse


class MoleculeResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    registration_number: str
    name: str
    molecule_type: str
    structure: StructureResponse | None = None
    descriptors: DescriptorsResponse | None = None
    molecular_formula: str | None = None
    structure_status: str
    registration_status: str
    synthesis_status: str
    lifecycle_stage: str
    stereochemistry: str | None = None
    invention_date: date | None = None
    disclosed_at: datetime | None = None
    merged_into_id: uuid.UUID | None = None
    custom_fields: dict | None = None
    originating_org_id: uuid.UUID
    identifiers: list[IdentifierResponse]
    version: int
    similarity_score: float | None = None  # set only on similarity-search rows

    @classmethod
    def from_domain(cls, mol: Molecule) -> MoleculeResponse:
        structure = None
        if mol.structure:
            structure = StructureResponse(
                smiles=mol.structure.smiles,
                cxsmiles=mol.structure.cxsmiles,
                inchi=mol.structure.inchi,
                inchi_key=mol.structure.inchi_key,
            )
        descriptors = None
        if mol.descriptors:
            descriptors = DescriptorsResponse(
                molecular_formula=mol.descriptors.molecular_formula,
                molecular_weight=mol.descriptors.molecular_weight,
                exact_mass=mol.descriptors.exact_mass,
                logp=mol.descriptors.logp,
                tpsa=mol.descriptors.tpsa,
                hbd=mol.descriptors.hbd,
                hba=mol.descriptors.hba,
                rotatable_bonds=mol.descriptors.rotatable_bonds,
                aromatic_rings=mol.descriptors.aromatic_rings,
                ring_count=mol.descriptors.ring_count,
                heavy_atom_count=mol.descriptors.heavy_atom_count,
                ro5_violations=mol.descriptors.ro5_violations,
            )
        identifiers = [IdentifierResponse.from_domain(i) for i in mol.identifiers]
        return cls(
            id=mol.id,
            workspace_id=mol.workspace_id,
            registration_number=mol.registration_number.value,
            name=mol.name,
            molecule_type=mol.molecule_type.value,
            structure=structure,
            descriptors=descriptors,
            molecular_formula=mol.molecular_formula,
            structure_status=mol.structure_status.value,
            registration_status=mol.registration_status.value,
            synthesis_status=mol.synthesis_status.value,
            lifecycle_stage=mol.lifecycle_stage.value,
            stereochemistry=mol.stereochemistry.value if mol.stereochemistry else None,
            invention_date=mol.invention_date,
            disclosed_at=mol.disclosed_at,
            merged_into_id=mol.merged_into_id,
            custom_fields=mol.custom_fields,
            originating_org_id=mol.originating_org_id,
            identifiers=identifiers,
            version=mol.version,
        )


class SimilaritySearchResult(BaseModel):
    molecule: MoleculeResponse
    similarity: float

    @classmethod
    def from_domain(cls, molecule: Molecule, similarity: float) -> SimilaritySearchResult:
        return cls(
            molecule=MoleculeResponse.from_domain(molecule),
            similarity=round(similarity, 4),
        )


class ActivityValueResponse(BaseModel):
    value: float | None = None
    qualifier: str | None = None
    unit: str | None = None
    source: str
    curve_type: str | None = None
    r_squared: float | None = None
    data_point_count: int = 1


class ProtocolActivityResponse(BaseModel):
    protocol_id: uuid.UUID
    protocol_name: str
    protocol_type: str
    readouts: list[ActivityValueResponse] = []
    best_curves: list[dict[str, Any]] = []
    # Protocol-declared intercept specs (EC50, EC90, IC10, ...). The FE
    # builds one column per spec inside this protocol's Card; matches
    # cell values out of each row's ``intercept_values``.
    intercepts: list[dict[str, Any]] = []


class ActivitySummaryResponse(BaseModel):
    molecule_id: uuid.UUID
    protocols: list[ProtocolActivityResponse] = []

    @classmethod
    def from_domain(cls, summary) -> ActivitySummaryResponse:
        return cls(
            molecule_id=summary.molecule_id,
            protocols=[
                ProtocolActivityResponse(
                    protocol_id=p.protocol_id,
                    protocol_name=p.protocol_name,
                    protocol_type=p.protocol_type,
                    best_curves=p.best_curves,
                    intercepts=p.intercepts,
                )
                for p in summary.protocols
            ],
        )


class StructureSearchResponse(BaseModel):
    """Wrapper for structure search results (exact, substructure, or similarity)."""

    search_type: str
    molecules: list[MoleculeResponse] | None = None
    similarity_results: list[SimilaritySearchResult] | None = None
    count: int


class DetectedSaltResponse(BaseModel):
    salt_smiles: str
    salt_fragment_mw: float
    stoichiometry: int


class RegistrationResponse(BaseModel):
    molecule: MoleculeResponse
    is_new: bool
    qc_warnings: list[str]
    batch: BatchResponse | None = None
    batch_skipped: bool = False
    detected_salt: DetectedSaltResponse | None = None
    action: str = "registered"
    needs_merge_confirmation: bool = False
    matched_molecule_id: uuid.UUID | None = None
    disclosure_id: uuid.UUID | None = None
    conflict_reason: str | None = None


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ExternalIdBody(BaseModel):
    identifier: str
    identifier_type: str


class BatchBody(BaseModel):
    """Optional batch to create alongside molecule registration."""

    source: str
    amount_value: float
    amount_unit: str
    salt_entry_id: uuid.UUID | None = None
    salt_name: str | None = None
    salt_smiles: str | None = None
    salt_stoichiometry: int = 1
    formula_weight: float | None = None
    purity: float | None = None
    concentration_value: float | None = None
    concentration_unit: str | None = None
    supplier_org_id: uuid.UUID | None = None
    vendor_catalog_number: str | None = None
    vendor_lot_number: str | None = None
    synthesis_date: date | None = None
    expiry_date: date | None = None
    notebook_reference: str | None = None
    appearance: str | None = None
    custom_fields: dict | None = None


class RegisterMoleculeBody(BaseModel):
    name: str
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[ExternalIdBody] = []
    originating_org_id: uuid.UUID
    custom_fields: dict | None = None
    batch: BatchBody | None = None
    auto_approve: bool = True
    create_batch_on_duplicate: bool | None = None  # None → use workspace default


class UpdateMoleculeBody(BaseModel):
    lifecycle_stage: str | None = None
    lifecycle_reason: str | None = None
    custom_fields: dict | None = None

    model_config = {"extra": "forbid"}


class AddIdentifierBody(BaseModel):
    identifier: str
    identifier_type: str
    source: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=RegistrationResponse, status_code=201)
async def register_molecule(
    body: RegisterMoleculeBody,
    auth: AuthDep,
    use_case: RegisterMoleculeDep,
    create_batch_uc: CreateBatchDep,
    salt_matcher_uow: SaltMatcherUoWDep,
    settings_uc: GetWorkspaceSettingsDep,
) -> RegistrationResponse:
    command = RegisterMoleculeCommand(
        workspace_id=auth.workspace_id,
        name=body.name,
        smiles=body.smiles,
        molecule_type=body.molecule_type,
        external_ids=[
            ExternalId(identifier=e.identifier, identifier_type=e.identifier_type)
            for e in body.external_ids
        ],
        originating_org_id=body.originating_org_id,
        custom_fields=body.custom_fields,
        registered_by=auth.user_id,
        auto_approve=body.auto_approve,
    )
    outcome = result_to_response(await use_case(command, auth=auth))

    # Resolve batch-creation policy (workspace default unless caller overrides).
    from cellar.application.inventory.batch_policy import should_create_batch
    from cellar.application.workspace_config.get_workspace_settings import (
        GetWorkspaceSettingsQuery,
    )

    settings = result_to_response(
        await settings_uc(GetWorkspaceSettingsQuery(workspace_id=auth.workspace_id), auth=auth)
    )
    workspace_default = settings.create_batch_on_duplicate

    create_batch_now = should_create_batch(
        is_new_molecule=outcome.is_new,
        override=body.create_batch_on_duplicate,
        workspace_default=workspace_default,
    )
    batch_skipped = body.batch is not None and not create_batch_now

    # Optionally create a batch on the (new or existing) molecule
    batch_response: BatchResponse | None = None
    if body.batch is not None and create_batch_now:
        b = body.batch

        # Auto-fill salt from detected_salt if user didn't pick one
        salt_entry_id = b.salt_entry_id
        salt_name = b.salt_name
        salt_smiles = b.salt_smiles
        salt_stoichiometry = b.salt_stoichiometry
        formula_weight = b.formula_weight

        if salt_entry_id is None and outcome.detected_salt is not None:
            _salt_matcher, _salt_uow = salt_matcher_uow
            async with _salt_uow:
                matched = await _salt_matcher.match_by_smiles(
                    auth.workspace_id, outcome.detected_salt.salt_smiles
                )
            if matched is not None:
                salt_entry_id = matched.id
                salt_name = matched.name
                salt_smiles = matched.smiles
                salt_stoichiometry = outcome.detected_salt.stoichiometry
                mol_mw = (
                    outcome.molecule.descriptors.molecular_weight
                    if outcome.molecule.descriptors
                    else None
                )
                if mol_mw is not None:
                    formula_weight = compute_formula_weight(
                        mol_mw, matched.molecular_weight, salt_stoichiometry
                    )

        batch_cmd = CreateBatchCommand(
            workspace_id=auth.workspace_id,
            molecule_id=outcome.molecule.id,
            source=b.source,
            chemist=auth.user_id,
            amount_value=b.amount_value,
            amount_unit=b.amount_unit,
            salt_entry_id=salt_entry_id,
            salt_name=salt_name,
            salt_smiles=salt_smiles,
            salt_stoichiometry=salt_stoichiometry,
            formula_weight=formula_weight,
            purity=b.purity,
            concentration_value=b.concentration_value,
            concentration_unit=b.concentration_unit,
            supplier_org_id=b.supplier_org_id,
            vendor_catalog_number=b.vendor_catalog_number,
            vendor_lot_number=b.vendor_lot_number,
            synthesis_date=b.synthesis_date,
            expiry_date=b.expiry_date,
            notebook_reference=b.notebook_reference,
            appearance=b.appearance,
            custom_fields=b.custom_fields,
        )
        batch_outcome = result_to_response(await create_batch_uc(batch_cmd, auth=auth))
        batch_response = BatchResponse.from_domain(batch_outcome.batch)

    detected_salt_resp: DetectedSaltResponse | None = None
    if outcome.detected_salt is not None:
        detected_salt_resp = DetectedSaltResponse(
            salt_smiles=outcome.detected_salt.salt_smiles,
            salt_fragment_mw=outcome.detected_salt.salt_fragment_mw,
            stoichiometry=outcome.detected_salt.stoichiometry,
        )

    return RegistrationResponse(
        molecule=MoleculeResponse.from_domain(outcome.molecule),
        is_new=outcome.is_new,
        qc_warnings=outcome.qc_warnings,
        batch=batch_response,
        batch_skipped=batch_skipped,
        detected_salt=detected_salt_resp,
        action=outcome.action.value,
        needs_merge_confirmation=outcome.needs_merge_confirmation,
        matched_molecule_id=outcome.matched_molecule_id,
        disclosure_id=outcome.disclosure_id,
        conflict_reason=outcome.conflict_reason,
    )


@router.get("", response_model=PaginatedResponse[MoleculeResponse])
async def list_molecules(
    auth: AuthDep,
    use_case: ListMoleculesDep,
    by_ids_use_case: ListMoleculesByIdsDep,
    molecule_type: str | None = None,
    lifecycle_stage: str | None = None,
    structure_status: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
    ids: str | None = None,
) -> PaginatedResponse[MoleculeResponse]:
    # Bulk-by-ids shortcut: when ?ids=<csv> is provided, skip normal pagination.
    if ids is not None:
        parsed_ids = [uuid.UUID(x.strip()) for x in ids.split(",") if x.strip()]
        by_ids_query = ListMoleculesByIdsQuery(workspace_id=auth.workspace_id, ids=parsed_ids)
        molecules = result_to_response(await by_ids_use_case(by_ids_query, auth=auth))
        return PaginatedResponse(
            items=[MoleculeResponse.from_domain(m) for m in molecules],
            next_cursor=None,
        )
    # When a search term is provided without an explicit limit, default to 20
    # (autocomplete scenario — avoids returning the entire table).
    effective_limit = clamp_limit(limit if limit is not None else (20 if q else None))
    query = ListMoleculesQuery(
        workspace_id=auth.workspace_id,
        molecule_type=molecule_type,
        lifecycle_stage=lifecycle_stage,
        structure_status=structure_status,
        search_term=q,
        cursor_id=parse_cursor(cursor),
        limit=effective_limit,
    )
    page = result_to_response(await use_case(query, auth=auth))
    return PaginatedResponse(
        items=[MoleculeResponse.from_domain(m) for m in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/search", response_model=StructureSearchResponse)
async def search_molecules(
    auth: AuthDep,
    use_case: SearchMoleculesDep,
    search_type: str,
    query: str,
    threshold: float = 0.7,
    limit: int = 100,
    query_kind: str | None = None,
) -> StructureSearchResponse:
    """Structure search: exact (by SMILES), substructure (by SMILES or SMARTS),
    or similarity (by SMILES).

    For substructure, ``query_kind`` selects the cartridge interpretation —
    ``"smiles"`` for plain structures (cartridge handles aromaticity),
    ``"smarts"`` for queries with atom lists / R-groups / query primitives.
    Omitted ⇒ legacy SMARTS path (aromatized defensively).

    Results are capped at ``limit`` (max 500, default 100).
    """
    capped_limit = max(1, min(limit, 500))
    q = SearchMoleculesQuery(
        workspace_id=auth.workspace_id,
        search_type=search_type,
        query=query,
        threshold=threshold,
        query_kind=query_kind,
    )
    results = result_to_response(await use_case(q, auth=auth))

    if search_type == "similarity":
        items = [
            SimilaritySearchResult.from_domain(r.molecule, r.similarity)
            for r in results[:capped_limit]
        ]
        return StructureSearchResponse(
            search_type=search_type,
            similarity_results=items,
            count=len(items),
        )
    mol_items = [MoleculeResponse.from_domain(m) for m in results[:capped_limit]]
    return StructureSearchResponse(
        search_type=search_type,
        molecules=mol_items,
        count=len(mol_items),
    )


@router.get("/by-identifier/{identifier}", response_model=MoleculeResponse)
async def get_molecule_by_identifier(
    identifier: str,
    auth: AuthDep,
    use_case: GetMoleculeByIdentifierDep,
) -> MoleculeResponse:
    """Look up a molecule by any external identifier (CAS, ChEMBL, vendor ID, etc.)."""
    q = GetMoleculeByIdentifierQuery(
        workspace_id=auth.workspace_id,
        identifier=identifier,
    )
    mol = result_to_response(await use_case(q, auth=auth))
    return MoleculeResponse.from_domain(mol)


# ---------------------------------------------------------------------------
# Batch structure depiction (must be above /{molecule_id} routes)
# ---------------------------------------------------------------------------


class DepictRequest(BaseModel):
    smiles_list: list[str]
    width: int = 150
    height: int = 100


class DepictResponse(BaseModel):
    """Maps SMILES -> base64 PNG. Missing entries failed to parse."""

    images: dict[str, str]


@router.post("/depict", response_model=DepictResponse)
async def depict_structures(
    body: DepictRequest,
    auth: AuthDep,
    use_case: DepictMoleculesDep,
) -> DepictResponse:
    """Render 2D structure depictions for a batch of SMILES strings.

    Returns a dict mapping each valid SMILES to a base64-encoded PNG.
    Invalid SMILES are silently skipped. Max 200 SMILES per request.
    """
    images = result_to_response(
        await use_case(
            DepictMoleculesQuery(
                workspace_id=auth.workspace_id,
                smiles_list=body.smiles_list,
                width=body.width,
                height=body.height,
            ),
            auth=auth,
        )
    )
    return DepictResponse(images=images)


# ---------------------------------------------------------------------------
# Protocol test-count bulk query
# ---------------------------------------------------------------------------


class MoleculeTestCountsBody(BaseModel):
    molecule_ids: list[uuid.UUID]
    project_id: uuid.UUID | None = None


class MoleculeTestCountsResponse(BaseModel):
    counts: dict[str, int]


@router.post("/test-counts", response_model=MoleculeTestCountsResponse)
async def get_molecule_test_counts(
    body: MoleculeTestCountsBody,
    auth: AuthDep,
    use_case: GetMoleculeTestCountsDep,
) -> MoleculeTestCountsResponse:
    """Return distinct protocol test counts per molecule.

    For each molecule ID in the request, return how many distinct protocols
    it has at least one dose-response curve in.  When ``project_id`` is
    supplied, only protocols linked to that project are counted.

    Molecules with no DR data are returned with count=0 so the FE never
    has to handle missing keys.
    """
    q = GetMoleculeTestCountsQuery(
        workspace_id=auth.workspace_id,
        molecule_ids=body.molecule_ids,
        project_id=body.project_id,
    )
    counts = await use_case.execute(q, auth=auth)
    return MoleculeTestCountsResponse(counts={str(k): v for k, v in counts.items()})


@router.get("/{molecule_id}", response_model=MoleculeResponse)
async def get_molecule(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetMoleculeDep,
) -> MoleculeResponse:
    query = GetMoleculeQuery(workspace_id=auth.workspace_id, molecule_id=molecule_id)
    mol = result_to_response(await use_case(query, auth=auth))
    return MoleculeResponse.from_domain(mol)


@router.patch("/{molecule_id}", response_model=MoleculeResponse)
async def update_molecule(
    molecule_id: uuid.UUID,
    body: UpdateMoleculeBody,
    auth: AuthDep,
    use_case: UpdateMoleculeDep,
) -> MoleculeResponse:
    command = UpdateMoleculeCommand(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
        lifecycle_stage=body.lifecycle_stage,
        lifecycle_reason=body.lifecycle_reason,
        custom_fields=body.custom_fields if "custom_fields" in body.model_fields_set else UNSET,
        changed_by=auth.user_id,
    )
    mol = result_to_response(await use_case(command, auth=auth))
    return MoleculeResponse.from_domain(mol)


@router.get("/{molecule_id}/activity", response_model=ActivitySummaryResponse)
async def get_molecule_activity(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    activity_service: MoleculeActivityServiceDep,
) -> ActivitySummaryResponse:
    """Get activity summary for a molecule across all protocols."""
    summary = await activity_service.get_activity_summary(auth.workspace_id, molecule_id)
    return ActivitySummaryResponse.from_domain(summary)


@router.get("/{molecule_id}/plates")
async def list_molecule_plates(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    service: PlateReadModelServiceDep,
    plate_visibility_uow: PlateVisibilityUoWDep,
):
    """List all registered plates containing batches of this molecule."""
    from cellar.interface.routes.registered_plates import MoleculePlateResponse

    visibility, visibility_uow = plate_visibility_uow
    async with visibility_uow:
        excluded = await visibility.excluded_org_ids(auth.workspace_id, auth)
        borrowed = await visibility.borrowed_plate_ids(auth.workspace_id, auth)

    entries = await service.find_plates_for_molecule(
        auth.workspace_id, molecule_id, excluded_org_ids=excluded, include_plate_ids=borrowed
    )
    return [MoleculePlateResponse.from_entry(e) for e in entries]


@router.get("/{molecule_id}/collections")
async def list_molecule_collections(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListCollectionsForMoleculeDep,
):
    """List collections containing this molecule."""
    from cellar.interface.routes.collections import CollectionResponse

    result = await use_case(
        ListCollectionsForMoleculeQuery(
            workspace_id=auth.workspace_id,
            molecule_id=molecule_id,
        ),
        auth=auth,
    )
    collections = result_to_response(result)
    return [CollectionResponse.from_domain(c) for c in collections]


# ---------------------------------------------------------------------------
# Identifier sub-resource endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{molecule_id}/identifiers",
    response_model=list[IdentifierResponse],
)
async def list_identifiers(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListIdentifiersDep,
) -> list[IdentifierResponse]:
    """List all external identifiers for a molecule."""
    query = ListIdentifiersQuery(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
    )
    identifiers = result_to_response(await use_case(query, auth=auth))
    return [IdentifierResponse.from_domain(i) for i in identifiers]


@router.post(
    "/{molecule_id}/identifiers",
    response_model=AddIdentifierResponse,
    status_code=201,
)
async def add_identifier(
    molecule_id: uuid.UUID,
    body: AddIdentifierBody,
    auth: AuthDep,
    use_case: AddIdentifierDep,
) -> AddIdentifierResponse:
    """Add an external identifier to a molecule. Returns updated list + mirror summary."""
    command = AddIdentifierCommand(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
        identifier=body.identifier,
        identifier_type=body.identifier_type,
        source=body.source,
        registered_by=auth.user_id,
    )
    outcome = result_to_response(await use_case(command, auth=auth))
    return AddIdentifierResponse(
        identifiers=[IdentifierResponse.from_domain(i) for i in outcome.molecule.identifiers],
        mirror_summary=MirrorSummaryResponse.from_domain(outcome.mirror_summary),
    )


@router.delete(
    "/{molecule_id}/identifiers/{identifier_id}",
    status_code=204,
)
async def remove_identifier(
    molecule_id: uuid.UUID,
    identifier_id: uuid.UUID,
    auth: AuthDep,
    use_case: RemoveIdentifierDep,
) -> None:
    """Remove an identifier from a molecule."""
    command = RemoveIdentifierCommand(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
        identifier_id=identifier_id,
    )
    result_to_response(await use_case(command, auth=auth))


@router.get("/{molecule_id}/projects", response_model=list[uuid.UUID])
async def list_molecule_projects(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListMoleculeProjectsDep,
) -> list[uuid.UUID]:
    result = await use_case(
        ListMoleculeProjectsQuery(
            workspace_id=auth.workspace_id,
            molecule_id=molecule_id,
        ),
        auth=auth,
    )
    return result_to_response(result)
