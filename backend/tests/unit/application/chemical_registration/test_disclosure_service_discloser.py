"""A structure disclosed as new is credited to the person the registrant picked, if any."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from returns.result import Success

from cellar.application.chemical_registration.disclosure_service import (
    DisclosureService,
    SubmitDisclosureCommand,
)
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.chemical_registration.test_resolve_disclosure_conflict import (
    WS_ID,
    FakeDisclosureRepo,
    FakeEventDispatcher,
    FakeMoleculeRepo,
    FakeStructureProcessor,
    FakeUnitOfWork,
    _make_undisclosed_mol,
)


def _service(mol_repo: FakeMoleculeRepo) -> DisclosureService:
    return DisclosureService(
        uow=FakeUnitOfWork(),
        molecule_repo=mol_repo,
        disclosure_repo=FakeDisclosureRepo(),
        structure_processor=FakeStructureProcessor(),
        merge_service=AsyncMock(),
        dispatcher=FakeEventDispatcher(),
    )


async def test_new_structure_credits_the_picked_discloser() -> None:
    mol_repo = FakeMoleculeRepo()
    mol = _make_undisclosed_mol()
    mol_repo.add(mol)
    registrant, picked, picked_org = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    result = await _service(mol_repo)(
        SubmitDisclosureCommand(
            workspace_id=WS_ID,
            molecule_id=mol.id,
            disclosed_smiles="c1ccccc1",
            requested_by=registrant,
            disclosed_by=picked,
            disclosing_org_id=picked_org,
        ),
        auth=FakeAuth(workspace_id=WS_ID, user_id=registrant),
    )

    assert isinstance(result, Success)
    assert (mol.disclosed_by, mol.disclosed_by_org_id) == (picked, picked_org)


async def test_without_a_pick_the_requester_is_credited() -> None:
    mol_repo = FakeMoleculeRepo()
    mol = _make_undisclosed_mol()
    mol_repo.add(mol)
    requester = uuid.uuid4()
    await _service(mol_repo)(
        SubmitDisclosureCommand(
            workspace_id=WS_ID, molecule_id=mol.id, disclosed_smiles="c1ccccc1",
            requested_by=requester,
        ),
        auth=FakeAuth(workspace_id=WS_ID, user_id=requester),
    )
    assert mol.disclosed_by == requester
