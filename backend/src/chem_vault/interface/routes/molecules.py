"""Molecule CRUD + search endpoints."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.application.chemical_registration.get_molecule import GetMoleculeQuery
from chem_vault.application.chemical_registration.list_molecules import ListMoleculesQuery
from chem_vault.application.chemical_registration.register_molecule import (
    ExternalId,
    RegisterMoleculeCommand,
)
from chem_vault.application.chemical_registration.update_molecule import UpdateMoleculeCommand
from chem_vault.application.shared.sentinel import UNSET
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.interface.dependencies import (
    AuthDep,
    GetMoleculeDep,
    ListMoleculesDep,
    RegisterMoleculeDep,
    UpdateMoleculeDep,
)
from chem_vault.interface.error_handlers import result_to_response

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
        identifiers = [
            IdentifierResponse(
                id=i.id,
                identifier=i.identifier,
                identifier_type=i.identifier_type.value,
                source=i.source,
                registered_by=i.registered_by,
            )
            for i in mol.identifiers
        ]
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


class RegistrationResponse(BaseModel):
    molecule: MoleculeResponse
    is_new: bool
    qc_warnings: list[str]


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ExternalIdBody(BaseModel):
    identifier: str
    identifier_type: str


class RegisterMoleculeBody(BaseModel):
    name: str
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[ExternalIdBody] = []
    originating_org_id: uuid.UUID
    custom_fields: dict | None = None


class UpdateMoleculeBody(BaseModel):
    add_tags: list[str] | None = None
    remove_tags: list[str] | None = None
    lifecycle_stage: str | None = None
    lifecycle_reason: str | None = None
    custom_fields: dict | None = None

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=RegistrationResponse, status_code=201)
async def register_molecule(
    body: RegisterMoleculeBody,
    auth: AuthDep,
    use_case: RegisterMoleculeDep,
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
    return RegistrationResponse(
        molecule=MoleculeResponse.from_domain(outcome.molecule),
        is_new=outcome.is_new,
        qc_warnings=outcome.qc_warnings,
    )


@router.get("", response_model=list[MoleculeResponse])
async def list_molecules(
    auth: AuthDep,
    use_case: ListMoleculesDep,
    molecule_type: str | None = None,
    lifecycle_stage: str | None = None,
    structure_status: str | None = None,
) -> list[MoleculeResponse]:
    query = ListMoleculesQuery(
        workspace_id=auth.workspace_id,
        molecule_type=molecule_type,
        lifecycle_stage=lifecycle_stage,
        structure_status=structure_status,
    )
    mols = result_to_response(await use_case(query))
    return [MoleculeResponse.from_domain(m) for m in mols]


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
