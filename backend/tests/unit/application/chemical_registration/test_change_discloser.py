"""Changing who disclosed a compound: an admin or its registrant, to a member and an enabled org."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.application.chemical_registration.change_discloser import (
    ChangeDiscloser,
    ChangeDiscloserCommand,
)
from cellar.domain.chemical_registration.enums import MoleculeType
from cellar.domain.chemical_registration.events import MoleculeDiscloserChanged
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.shared.errors import AuthorizationError, ValidationError
from cellar.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    RegistrationNumber,
)
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

ORG = uuid.uuid4()
NEW_ORG = uuid.uuid4()
_STRUCTURE = ChemicalStructure(
    smiles="CCO",
    cxsmiles="CCO",
    inchi="InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3",
    inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
    molfile="fake",
)
_DESCRIPTORS = ComputedDescriptors(
    molecular_formula="C2H6O",
    molecular_weight=46.07,
    exact_mass=46.04,
    logp=-0.0014,
    tpsa=20.23,
    hbd=1,
    hba=1,
    rotatable_bonds=0,
    aromatic_rings=0,
    ring_count=0,
    heavy_atom_count=3,
    ro5_violations=0,
)


class _Org:
    def __init__(self, org_id: uuid.UUID) -> None:
        self.id, self.enabled = org_id, True


class _Directory:
    async def list_orgs(self) -> list[_Org]:
        return [_Org(ORG), _Org(NEW_ORG)]


def _molecule(ws: uuid.UUID, registrant: uuid.UUID | None, *, disclosed: bool = True) -> Molecule:
    common = dict(
        workspace_id=ws,
        registration_number=RegistrationNumber(value="CV-00007"),
        name="EtOH",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        registered_by=registrant,
        registered_by_org_id=ORG,
    )
    mol = (
        Molecule.register_disclosed(structure=_STRUCTURE, descriptors=_DESCRIPTORS, **common)
        if disclosed
        else Molecule.register_undisclosed(**common)
    )
    mol.clear_events()
    return mol


def _uc(mol: Molecule):
    uow = FakeUnitOfWork()
    repo = AsyncMock()

    async def _find(ws, mid):
        uow.track(mol)
        return mol if mid == mol.id else None

    repo.find_by_id_in_workspace = AsyncMock(side_effect=_find)
    dispatcher = AsyncMock()
    return ChangeDiscloser(uow, repo, dispatcher, _Directory()), repo, dispatcher


def _cmd(auth: FakeAuth, mol: Molecule, person: uuid.UUID, org: uuid.UUID = NEW_ORG):
    return ChangeDiscloserCommand(
        workspace_id=auth.workspace_id,
        molecule_id=mol.id,
        disclosed_by=person,
        disclosed_by_org_id=org,
    )


async def test_registrant_changes_discloser() -> None:
    auth = FakeAuth(role="editor")
    mol = _molecule(auth.workspace_id, auth.user_id)
    uc, repo, dispatcher = _uc(mol)
    result = await uc(_cmd(auth, mol, auth.user_id), auth=auth)
    assert isinstance(result, Success)
    assert result.unwrap().disclosed_by_org_id == NEW_ORG
    (events,) = dispatcher.dispatch_all.await_args.args
    assert [type(e) for e in events] == [MoleculeDiscloserChanged]


async def test_admin_changes_discloser() -> None:
    auth = FakeAuth(role="admin")
    mol = _molecule(auth.workspace_id, uuid.uuid4())
    uc, _, _ = _uc(mol)
    assert isinstance(await uc(_cmd(auth, mol, auth.user_id), auth=auth), Success)


async def test_other_editor_refused() -> None:
    auth = FakeAuth(role="editor")
    mol = _molecule(auth.workspace_id, uuid.uuid4())
    uc, repo, _ = _uc(mol)
    with pytest.raises(AuthorizationError):
        await uc(_cmd(auth, mol, auth.user_id), auth=auth)
    repo.save.assert_not_awaited()


async def test_old_molecule_without_registrant_only_admin() -> None:
    editor = FakeAuth(role="editor")
    mol = _molecule(editor.workspace_id, None)
    uc, _, _ = _uc(mol)
    with pytest.raises(AuthorizationError):
        await uc(_cmd(editor, mol, editor.user_id), auth=editor)


async def test_non_member_discloser_refused() -> None:
    auth = FakeAuth(role="editor", members=[])
    mol = _molecule(auth.workspace_id, auth.user_id)
    uc, repo, _ = _uc(mol)
    result = await uc(_cmd(auth, mol, uuid.uuid4()), auth=auth)
    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)
    repo.save.assert_not_awaited()


async def test_undisclosed_molecule_refused() -> None:
    auth = FakeAuth(role="editor")
    mol = _molecule(auth.workspace_id, auth.user_id, disclosed=False)
    uc, _, _ = _uc(mol)
    result = await uc(_cmd(auth, mol, auth.user_id), auth=auth)
    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)


async def test_org_only_change_keeps_the_person() -> None:
    auth = FakeAuth(role="editor")
    mol = _molecule(auth.workspace_id, auth.user_id)
    uc, _, _ = _uc(mol)
    result = await uc(
        ChangeDiscloserCommand(
            workspace_id=auth.workspace_id, molecule_id=mol.id, disclosed_by_org_id=NEW_ORG
        ),
        auth=auth,
    )
    assert isinstance(result, Success)
    assert (mol.disclosed_by, mol.disclosed_by_org_id) == (auth.user_id, NEW_ORG)


async def test_a_discloser_who_left_needs_no_membership_for_an_org_fix() -> None:
    admin = FakeAuth(role="admin", members=[])
    mol = _molecule(admin.workspace_id, uuid.uuid4())
    departed = mol.disclosed_by
    uc, _, _ = _uc(mol)
    result = await uc(
        ChangeDiscloserCommand(
            workspace_id=admin.workspace_id, molecule_id=mol.id,
            disclosed_by=departed, disclosed_by_org_id=NEW_ORG,
        ),
        auth=admin,
    )
    assert isinstance(result, Success)
    assert mol.disclosed_by_org_id == NEW_ORG


async def test_org_fix_on_a_compound_with_no_discloser_on_file() -> None:
    admin = FakeAuth(role="admin")
    mol = _molecule(admin.workspace_id, None)
    mol.disclosed_by = None  # a backfilled compound with no History record
    uc, _, _ = _uc(mol)
    result = await uc(
        ChangeDiscloserCommand(
            workspace_id=admin.workspace_id, molecule_id=mol.id, disclosed_by_org_id=NEW_ORG
        ),
        auth=admin,
    )
    assert isinstance(result, Success)
    assert (mol.disclosed_by, mol.disclosed_by_org_id) == (None, NEW_ORG)

