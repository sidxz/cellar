"""Shared helpers for similarity/substructure search integration tests."""

from __future__ import annotations

import uuid

import pytest
from rdkit import Chem
from sqlalchemy.ext.asyncio import AsyncSession

from chem_vault.infrastructure.persistence.sqlalchemy.chemical_registration.models import (
    MoleculeModel,
)
from chem_vault.infrastructure.persistence.sqlalchemy.workspace_config.models import (
    OrganizationModel,
)
from chem_vault.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm

_morgan = MorganAlgorithm()


@pytest.fixture
async def org_id(db_session: AsyncSession, workspace_id: uuid.UUID) -> uuid.UUID:
    oid = uuid.uuid4()
    org = OrganizationModel(
        id=oid,
        workspace_id=workspace_id,
        name=f"TestOrg-{oid.hex[:6]}",
        org_type="internal",
        is_active=True,
        version=1,
    )
    db_session.add(org)
    await db_session.flush()
    return oid


def _make_molecule_model(
    workspace_id: uuid.UUID,
    org_id: uuid.UUID,
    *,
    smiles: str,
    name: str,
    inchi_key: str | None = None,
) -> MoleculeModel:
    """Build a MoleculeModel with stereo-aware Morgan bytes pre-computed.

    Uses RDKit to compute the canonical InChIKey if not supplied. The trigger
    will lift fp_morgan into morgan_bfp on insert. Skips ComputedDescriptors
    (its all-or-none invariant doesn't matter for these tests).
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"unparseable SMILES in test fixture: {smiles!r}")
    fp_morgan = _morgan.compute_bytes(mol)
    if inchi_key is None:
        inchi = Chem.MolToInchi(mol)
        inchi_key = Chem.InchiToInchiKey(inchi)

    return MoleculeModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        registration_number=f"CV-{uuid.uuid4().hex[:5]}",
        name=name,
        molecule_type="small_molecule",
        smiles=smiles,
        inchi_key=inchi_key,
        fp_morgan=fp_morgan,
        structure_status="disclosed",
        registration_status="approved",
        synthesis_status="virtual",
        lifecycle_stage="active",
        originating_org_id=org_id,
        version=1,
    )
