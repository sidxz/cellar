"""PreviewRegistration — advisory, read-only forecast of what POST /molecules would do."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, MagicMock

from returns.result import Failure, Success

from cellar.application.chemical_registration.preview_registration import (
    MAX_PREVIEW_ITEMS,
    PreviewRegistration,
    PreviewRegistrationItem,
    PreviewRegistrationQuery,
)
from cellar.application.chemical_registration.protocols import (
    ProcessedStructureDTO,
    QCResultDTO,
)
from cellar.domain.chemical_registration.enums import (
    MoleculeType,
    RegistrationAction,
    Stereochemistry,
)
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    RegistrationNumber,
)
from cellar.infrastructure.rdkit.fingerprint_generator import Fingerprints
from tests.fakes.fake_auth import FakeAuth

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
_STRUCTURE = ChemicalStructure(
    smiles="c1ccccc1",
    cxsmiles="c1ccccc1",
    inchi="InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H",
    inchi_key="UHOVQNZJYSORNB-UHFFFAOYSA-N",
    molfile="fake",
)
_DESCRIPTORS = ComputedDescriptors(
    molecular_formula="C6H6",
    molecular_weight=78.11,
    exact_mass=78.047,
    logp=1.56,
    tpsa=0.0,
    hbd=0,
    hba=0,
    rotatable_bonds=0,
    aromatic_rings=1,
    ring_count=1,
    heavy_atom_count=6,
    ro5_violations=0,
)
_PROCESSED = ProcessedStructureDTO(
    structure=_STRUCTURE,
    descriptors=_DESCRIPTORS,
    fingerprints=Fingerprints(morgan=b"\x00" * 256),
    qc_result=QCResultDTO(total_penalty=0, issues=[]),
    stereochemistry=Stereochemistry.ACHIRAL,
)


class _SpyUoW:
    def __init__(self) -> None:
        self.entered = 0
        self.committed = False

    async def commit(self):
        self.committed = True
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        self.entered += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        pass


def _known() -> Molecule:
    return Molecule.register_disclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CC-000001"),
        name="Known-001",
        molecule_type=MoleculeType.SMALL_MOLECULE,
        structure=_STRUCTURE,
        descriptors=_DESCRIPTORS,
        originating_org_id=ORG_ID,
    )


def _processor(*, ok: bool = True) -> MagicMock:
    proc = MagicMock()
    proc.process.return_value = (
        Success(_PROCESSED) if ok else Failure(ValidationError("Bad SMILES"))
    )
    return proc


def _uc(repo: AsyncMock, uow: _SpyUoW, *, ok: bool = True) -> PreviewRegistration:
    return PreviewRegistration(uow=uow, repo=repo, structure_processor=_processor(ok=ok))


def _repo(*, by_inchi=None, owners=None, by_id=None) -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_inchi_key = AsyncMock(return_value=by_inchi)
    repo.find_undisclosed_by_identifiers = AsyncMock(return_value=None)
    repo.find_identifiers_in_workspace = AsyncMock(return_value=owners or {})
    repo.find_by_id_in_workspace = AsyncMock(return_value=by_id)
    return repo


class TestPreviewRegistration:
    async def test_forecasts_each_item_and_never_commits(self) -> None:
        known = _known()
        uow = _SpyUoW()
        uc = _uc(_repo(by_inchi=known, owners={"Known-001": known.id}, by_id=known), uow)
        result = await uc(
            PreviewRegistrationQuery(
                workspace_id=WS_ID,
                items=[
                    PreviewRegistrationItem(name="Alias-2", smiles="c1ccccc1", external_ids=[]),
                    PreviewRegistrationItem(name="Known-001", smiles=None, external_ids=[]),
                ],
            ),
            auth=FakeAuth(workspace_id=WS_ID),
        )
        assert isinstance(result, Success)
        items = result.unwrap().items
        assert [i.index for i in items] == [0, 1]
        assert items[0].action == RegistrationAction.DEDUPLICATED
        assert items[0].matched_molecule_id == known.id
        assert (
            items[1].action == RegistrationAction.CONFLICT
        )  # name claimed by a disclosed molecule
        assert uow.entered == 1
        assert uow.committed is False

    async def test_bad_structure_is_reported_per_item_not_as_a_failure(self) -> None:
        uc = _uc(_repo(), _SpyUoW(), ok=False)
        result = await uc(
            PreviewRegistrationQuery(
                workspace_id=WS_ID,
                items=[PreviewRegistrationItem(name="X", smiles="not-smiles", external_ids=[])],
            ),
            auth=FakeAuth(workspace_id=WS_ID),
        )
        assert isinstance(result, Success)
        item = result.unwrap().items[0]
        assert item.action is None
        assert "Bad SMILES" in (item.error or "")

    async def test_batch_over_the_cap_is_rejected(self) -> None:
        uc = _uc(_repo(), _SpyUoW())
        too_many = [
            PreviewRegistrationItem(name=f"N{i}", smiles=None, external_ids=[])
            for i in range(MAX_PREVIEW_ITEMS + 1)
        ]
        result = await uc(
            PreviewRegistrationQuery(workspace_id=WS_ID, items=too_many),
            auth=FakeAuth(workspace_id=WS_ID),
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
        assert str(MAX_PREVIEW_ITEMS) in str(result.failure())
