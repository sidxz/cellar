"""Molecule CRUD + search endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from lagom import Container
from pydantic import BaseModel

from chem_vault.application.chemical_registration.get_molecule import GetMoleculeQuery
from chem_vault.application.chemical_registration.identifiers import (
    AddIdentifierCommand,
    ListIdentifiersQuery,
    RemoveIdentifierCommand,
)
from chem_vault.application.chemical_registration.list_molecules import ListMoleculesQuery
from chem_vault.application.chemical_registration.get_molecule_by_identifier import (
    GetMoleculeByIdentifierQuery,
)
from chem_vault.application.chemical_registration.register_molecule import (
    ExternalId,
    RegisterMoleculeCommand,
)
from chem_vault.application.inventory.create_batch import CreateBatch, CreateBatchCommand
from chem_vault.application.inventory.salt_matcher import SaltMatcher, compute_formula_weight
from chem_vault.interface.routes.batches import BatchResponse
from chem_vault.application.chemical_registration.search_molecules import SearchMoleculesQuery
from chem_vault.application.chemical_registration.update_molecule import UpdateMoleculeCommand
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.chemical_registration.molecule_identifier import MoleculeIdentifier
from chem_vault.application.research_organization.manage_molecule_projects import (
    ListMoleculeProjectsQuery,
)
from chem_vault.interface.dependencies import (
    AddIdentifierDep,
    AuthDep,
    GetMoleculeByIdentifierDep,
    GetMoleculeDep,
    ListCollectionsForMoleculeDep,
    ListIdentifiersDep,
    ListMoleculeProjectsDep,
    ListMoleculesDep,
    MoleculeActivityServiceDep,
    RegisterMoleculeDep,
    RemoveIdentifierDep,
    SearchMoleculesDep,
    UpdateMoleculeDep,
    get_container,
)
from chem_vault.interface.error_handlers import result_to_response
from chem_vault.interface.pagination import (
    PaginatedResponse,
    clamp_limit,
    parse_cursor,
)

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
            identifier_type=i.identifier_type.value,
            source=i.source,
            registered_by=i.registered_by,
        )


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
    tags: list[str]
    invention_date: date | None = None
    disclosed_at: datetime | None = None
    merged_into_id: uuid.UUID | None = None
    custom_fields: dict | None = None
    originating_org_id: uuid.UUID
    identifiers: list[IdentifierResponse]
    version: int

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
            tags=mol.tags,
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
    detected_salt: DetectedSaltResponse | None = None


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


class UpdateMoleculeBody(BaseModel):
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None
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


def _get_create_batch(c: Annotated[Container, Depends(get_container)]) -> CreateBatch:
    return c[CreateBatch]


def _get_salt_matcher_uow(
    c: Annotated[Container, Depends(get_container)],
) -> tuple[SaltMatcher, Any]:
    """Return (SaltMatcher, uow) — caller must use ``async with uow:``."""
    from chem_vault.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
    from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.salt_entry_repository import (
        SQLAlchemySaltEntryRepository,
    )
    from sqlalchemy.ext.asyncio import async_sessionmaker

    uow = AsyncUnitOfWork(c[async_sessionmaker])
    return SaltMatcher(SQLAlchemySaltEntryRepository(uow)), uow


@router.post("", response_model=RegistrationResponse, status_code=201)
async def register_molecule(
    body: RegisterMoleculeBody,
    auth: AuthDep,
    use_case: RegisterMoleculeDep,
    create_batch_uc: Annotated[CreateBatch, Depends(_get_create_batch)],
    salt_matcher_uow: Annotated[tuple[SaltMatcher, Any], Depends(_get_salt_matcher_uow)],
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
    )
    outcome = result_to_response(await use_case(command, auth=auth))

    # Optionally create a batch on the (new or existing) molecule
    batch_response: BatchResponse | None = None
    if body.batch is not None:
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
        batch_response = BatchResponse.from_domain(batch_outcome)

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
        detected_salt=detected_salt_resp,
    )


@router.get("", response_model=PaginatedResponse[MoleculeResponse])
async def list_molecules(
    auth: AuthDep,
    use_case: ListMoleculesDep,
    molecule_type: str | None = None,
    lifecycle_stage: str | None = None,
    structure_status: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int | None = None,
) -> PaginatedResponse[MoleculeResponse]:
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
    page = result_to_response(await use_case(query))
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
) -> StructureSearchResponse:
    """Structure search: exact (by SMILES), substructure (by SMARTS), or similarity (by SMILES).

    Results are capped at ``limit`` (max 500, default 100).
    """
    capped_limit = max(1, min(limit, 500))
    q = SearchMoleculesQuery(
        workspace_id=auth.workspace_id,
        search_type=search_type,
        query=query,
        threshold=threshold,
    )
    results = result_to_response(await use_case(q))

    if search_type == "similarity":
        from chem_vault.application.chemical_registration.search_molecules import SimilarityResult

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
    mol = result_to_response(await use_case(q))
    return MoleculeResponse.from_domain(mol)


@router.get("/{molecule_id}", response_model=MoleculeResponse)
async def get_molecule(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: GetMoleculeDep,
) -> MoleculeResponse:
    query = GetMoleculeQuery(workspace_id=auth.workspace_id, molecule_id=molecule_id)
    mol = result_to_response(await use_case(query))
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
        add_tags=body.add_tags,
        remove_tags=body.remove_tags,
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
    summary = await activity_service.get_activity_summary(
        auth.workspace_id, molecule_id
    )
    return ActivitySummaryResponse.from_domain(summary)


@router.get("/{molecule_id}/plates")
async def list_molecule_plates(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    c: Annotated[Container, Depends(get_container)],
):
    """List all registered plates containing batches of this molecule."""
    from chem_vault.application.inventory.plate_read_model import PlateReadModelService
    from chem_vault.interface.routes.registered_plates import MoleculePlateResponse

    service: PlateReadModelService = c[PlateReadModelService]
    entries = await service.find_plates_for_molecule(auth.workspace_id, molecule_id)
    return [MoleculePlateResponse.from_entry(e) for e in entries]


@router.get("/{molecule_id}/collections")
async def list_molecule_collections(
    molecule_id: uuid.UUID,
    auth: AuthDep,
    use_case: ListCollectionsForMoleculeDep,
):
    """List collections containing this molecule."""
    from chem_vault.application.research_organization.get_collections_for_molecule import (
        ListCollectionsForMoleculeQuery,
    )
    from chem_vault.interface.routes.collections import CollectionResponse

    result = await use_case(
        ListCollectionsForMoleculeQuery(
            workspace_id=auth.workspace_id,
            molecule_id=molecule_id,
        )
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
    identifiers = result_to_response(await use_case(query))
    return [IdentifierResponse.from_domain(i) for i in identifiers]


@router.post(
    "/{molecule_id}/identifiers",
    response_model=list[IdentifierResponse],
    status_code=201,
)
async def add_identifier(
    molecule_id: uuid.UUID,
    body: AddIdentifierBody,
    auth: AuthDep,
    use_case: AddIdentifierDep,
) -> list[IdentifierResponse]:
    """Add an external identifier to a molecule. Returns the updated list."""
    command = AddIdentifierCommand(
        workspace_id=auth.workspace_id,
        molecule_id=molecule_id,
        identifier=body.identifier,
        identifier_type=body.identifier_type,
        source=body.source,
        registered_by=auth.user_id,
    )
    mol = result_to_response(await use_case(command, auth=auth))
    return [IdentifierResponse.from_domain(i) for i in mol.identifiers]


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
        )
    )
    return result_to_response(result)


# ---------------------------------------------------------------------------
# Batch structure depiction
# ---------------------------------------------------------------------------


class DepictRequest(BaseModel):
    smiles_list: list[str]
    width: int = 150
    height: int = 100


class DepictResponse(BaseModel):
    """Maps SMILES → base64 PNG. Missing entries failed to parse."""
    images: dict[str, str]


@router.post("/depict", response_model=DepictResponse)
async def depict_structures(body: DepictRequest) -> DepictResponse:
    """Render 2D structure depictions for a batch of SMILES strings.

    Returns a dict mapping each valid SMILES to a base64-encoded PNG.
    Invalid SMILES are silently skipped.
    """
    import base64
    import io

    from rdkit import Chem
    from rdkit.Chem import Draw

    images: dict[str, str] = {}
    for smiles in body.smiles_list:
        if not smiles or smiles in images:
            continue
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            continue
        img = Draw.MolToImage(mol, size=(body.width, body.height))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        images[smiles] = base64.b64encode(buf.getvalue()).decode()

    return DepictResponse(images=images)
