"""Tests for RegisterMolecule — disclosure detection via identifier match."""

from __future__ import annotations

import uuid
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.chemical_registration.disclosure_service import (
    DisclosureOutcome,
    SubmitDisclosureCommand,
)
from chem_vault.application.chemical_registration.protocols import (
    ProcessedStructureDTO,
    QCResultDTO,
)
from chem_vault.application.chemical_registration.register_molecule import (
    ExternalId,
    RegisterMolecule,
    RegisterMoleculeCommand,
    RegistrationOutcome,
)
from chem_vault.domain.chemical_registration.disclosure_request import DisclosureRequest
from chem_vault.domain.chemical_registration.enums import (
    MoleculeType,
    RegistrationAction,
    StructureStatus,
)
from chem_vault.domain.chemical_registration.molecule import Molecule
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.events import DomainEvent
from chem_vault.domain.shared.value_objects import (
    ChemicalStructure,
    ComputedDescriptors,
    RegistrationNumber,
)
from tests.fakes.fake_auth import FakeAuth


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

WS_ID = uuid.uuid4()
ORG_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

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
    fingerprints={},
    qc_result=QCResultDTO(total_penalty=0, issues=[]),
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeUnitOfWork:
    """Minimal UoW that tracks commit/rollback calls."""

    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class FakeEventDispatcher:
    """Captures dispatched events for assertions."""

    def __init__(self) -> None:
        self.dispatched: list[DomainEvent] = []

    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        self.dispatched.extend(events)


def _make_undisclosed_molecule(
    mol_id: uuid.UUID | None = None,
    name: str = "Undisclosed-001",
) -> Molecule:
    """Create an undisclosed molecule for testing."""
    mol = Molecule.register_undisclosed(
        workspace_id=WS_ID,
        registration_number=RegistrationNumber(value="CV-00001"),
        name=name,
        molecule_type=MoleculeType.SMALL_MOLECULE,
        originating_org_id=ORG_ID,
    )
    if mol_id is not None:
        object.__setattr__(mol, "_id", mol_id)
    mol.clear_events()
    return mol


def _make_disclosure_request(molecule_id: uuid.UUID) -> DisclosureRequest:
    """Create a disclosure request for testing."""
    return DisclosureRequest.create(
        workspace_id=WS_ID,
        molecule_id=molecule_id,
        disclosed_smiles="c1ccccc1",
        requested_by=USER_ID,
    )


def _make_repo(
    *,
    find_by_inchi_key: Molecule | None = None,
    find_undisclosed_by_identifiers: Molecule | None = None,
    find_identifiers_in_workspace: dict[str, uuid.UUID] | None = None,
) -> AsyncMock:
    """Create a mock MoleculeRepository with configurable return values."""
    repo = AsyncMock()
    repo.find_by_inchi_key = AsyncMock(return_value=find_by_inchi_key)
    repo.find_undisclosed_by_identifiers = AsyncMock(
        return_value=find_undisclosed_by_identifiers
    )
    repo.find_identifiers_in_workspace = AsyncMock(
        return_value=find_identifiers_in_workspace or {}
    )
    repo.next_registration_number = AsyncMock(
        return_value=RegistrationNumber(value="CV-00099")
    )
    repo.save = AsyncMock()
    return repo


def _make_processor(*, success: bool = True) -> MagicMock:
    """Create a mock StructureProcessorProtocol."""
    proc = MagicMock()
    if success:
        proc.process.return_value = Success(_PROCESSED)
    else:
        proc.process.return_value = Failure(ValidationError("Bad SMILES"))
    return proc


def _make_command(
    *,
    smiles: str | None = "c1ccccc1",
    name: str = "Test Compound",
    auto_approve: bool = True,
    external_ids: list[ExternalId] | None = None,
) -> RegisterMoleculeCommand:
    return RegisterMoleculeCommand(
        workspace_id=WS_ID,
        name=name,
        smiles=smiles,
        originating_org_id=ORG_ID,
        registered_by=USER_ID,
        auto_approve=auto_approve,
        external_ids=external_ids or [],
    )


def _make_use_case(
    *,
    repo: AsyncMock | None = None,
    disclosure_service: AsyncMock | None = None,
    uow: FakeUnitOfWork | None = None,
) -> RegisterMolecule:
    return RegisterMolecule(
        uow=uow or FakeUnitOfWork(),
        repo=repo or _make_repo(),
        dispatcher=FakeEventDispatcher(),
        structure_processor=_make_processor(),
        disclosure_service=disclosure_service,
    )


# ---------------------------------------------------------------------------
# Tests — Disclosure Detection
# ---------------------------------------------------------------------------


class TestDisclosureDetection:
    """Tests for the disclosure detection path in _register_disclosed."""

    async def test_identifier_matches_undisclosed_needs_confirmation(self) -> None:
        """When SMILES + identifier match an undisclosed molecule and auto_approve=False,
        DisclosureService returns needs_confirmation=True, and we get MERGE_CANDIDATE."""
        undisclosed_mol = _make_undisclosed_molecule()
        dr = _make_disclosure_request(undisclosed_mol.id)
        target_mol_id = uuid.uuid4()

        repo = _make_repo(
            find_undisclosed_by_identifiers=undisclosed_mol,
        )

        mock_ds = AsyncMock()
        mock_ds.return_value = Success(
            DisclosureOutcome(
                disclosure_request=dr,
                was_merged=False,
                needs_confirmation=True,
                matched_molecule_id=target_mol_id,
            )
        )

        uc = _make_use_case(repo=repo, disclosure_service=mock_ds)
        cmd = _make_command(auto_approve=False, name="Undisclosed-001")

        result = await uc(cmd, auth=FakeAuth())

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.MERGE_CANDIDATE
        assert outcome.is_new is False
        assert outcome.needs_merge_confirmation is True
        assert outcome.matched_molecule_id == target_mol_id
        assert outcome.disclosure_id == dr.id
        assert outcome.molecule is undisclosed_mol

        # Verify DisclosureService was called with correct args
        mock_ds.assert_awaited_once()
        call_args = mock_ds.call_args[0][0]
        assert isinstance(call_args, SubmitDisclosureCommand)
        assert call_args.molecule_id == undisclosed_mol.id
        assert call_args.auto_approve is False

    async def test_identifier_matches_undisclosed_simple_disclosure(self) -> None:
        """When SMILES + identifier match an undisclosed molecule and disclosure
        resolves as new structure (no InChIKey match), we get DISCLOSED."""
        undisclosed_mol = _make_undisclosed_molecule()
        dr = _make_disclosure_request(undisclosed_mol.id)

        repo = _make_repo(
            find_undisclosed_by_identifiers=undisclosed_mol,
        )

        mock_ds = AsyncMock()
        mock_ds.return_value = Success(
            DisclosureOutcome(
                disclosure_request=dr,
                was_merged=False,
                needs_confirmation=False,
                matched_molecule_id=None,
            )
        )

        uc = _make_use_case(repo=repo, disclosure_service=mock_ds)
        cmd = _make_command(name="Undisclosed-001")

        result = await uc(cmd, auth=FakeAuth())

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.DISCLOSED
        assert outcome.is_new is False
        assert outcome.needs_merge_confirmation is False
        assert outcome.matched_molecule_id is None

    async def test_identifier_matches_undisclosed_auto_merge(self) -> None:
        """When disclosure auto-approves and merges, we get DEDUPLICATED."""
        undisclosed_mol = _make_undisclosed_molecule()
        dr = _make_disclosure_request(undisclosed_mol.id)
        target_id = uuid.uuid4()

        repo = _make_repo(
            find_undisclosed_by_identifiers=undisclosed_mol,
        )

        mock_ds = AsyncMock()
        mock_ds.return_value = Success(
            DisclosureOutcome(
                disclosure_request=dr,
                was_merged=True,
                merged_into_molecule_id=target_id,
                needs_confirmation=False,
                matched_molecule_id=None,
            )
        )

        uc = _make_use_case(repo=repo, disclosure_service=mock_ds)
        cmd = _make_command(name="Undisclosed-001", auto_approve=True)

        result = await uc(cmd, auth=FakeAuth())

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.DEDUPLICATED
        assert outcome.is_new is False

    async def test_no_undisclosed_match_registers_normally(self) -> None:
        """When identifiers don't match any undisclosed molecule, registration
        proceeds normally and creates a new molecule (REGISTERED)."""
        repo = _make_repo(
            find_undisclosed_by_identifiers=None,
        )

        mock_ds = AsyncMock()  # should not be called

        uc = _make_use_case(repo=repo, disclosure_service=mock_ds)
        cmd = _make_command(name="Brand New Compound")

        result = await uc(cmd, auth=FakeAuth())

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.REGISTERED
        assert outcome.is_new is True
        mock_ds.assert_not_awaited()

    async def test_disclosure_service_not_injected_skips_detection(self) -> None:
        """When disclosure_service is None (not injected), disclosure detection
        is skipped and registration proceeds as normal."""
        repo = _make_repo()

        uc = _make_use_case(repo=repo, disclosure_service=None)
        cmd = _make_command(name="Normal Compound")

        result = await uc(cmd, auth=FakeAuth())

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.REGISTERED
        assert outcome.is_new is True
        # find_undisclosed_by_identifiers should NOT have been called
        repo.find_undisclosed_by_identifiers.assert_not_awaited()

    async def test_disclosure_service_failure_propagated(self) -> None:
        """When DisclosureService returns a Failure, it is propagated."""
        undisclosed_mol = _make_undisclosed_molecule()

        repo = _make_repo(
            find_undisclosed_by_identifiers=undisclosed_mol,
        )

        mock_ds = AsyncMock()
        mock_ds.return_value = Failure(
            ValidationError("Structure processing failed: Bad SMILES")
        )

        uc = _make_use_case(repo=repo, disclosure_service=mock_ds)
        cmd = _make_command(name="Undisclosed-001")

        result = await uc(cmd, auth=FakeAuth())

        assert isinstance(result, Failure)
        assert "Structure processing failed" in str(result.failure())

    async def test_inchi_key_match_takes_priority_over_disclosure(self) -> None:
        """When InChIKey matches an existing disclosed molecule, the dedup path
        is taken even if disclosure_service is injected. Undisclosed detection
        is skipped when InChIKey already matches."""
        existing_disclosed = Molecule.register_disclosed(
            workspace_id=WS_ID,
            registration_number=RegistrationNumber(value="CV-00002"),
            name="Existing",
            molecule_type=MoleculeType.SMALL_MOLECULE,
            structure=_STRUCTURE,
            descriptors=_DESCRIPTORS,
            originating_org_id=ORG_ID,
        )
        existing_disclosed.clear_events()

        repo = _make_repo(find_by_inchi_key=existing_disclosed)

        mock_ds = AsyncMock()

        uc = _make_use_case(repo=repo, disclosure_service=mock_ds)
        cmd = _make_command(name="Dup Compound")

        result = await uc(cmd, auth=FakeAuth())

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.DEDUPLICATED
        assert outcome.is_new is False
        # DisclosureService should NOT have been called — InChIKey match took priority
        mock_ds.assert_not_awaited()
        # find_undisclosed_by_identifiers should NOT have been called
        repo.find_undisclosed_by_identifiers.assert_not_awaited()

    async def test_undisclosed_match_allows_identifier_through_conflict_check(
        self,
    ) -> None:
        """When an undisclosed molecule is matched, its identifiers should be
        allowed through the conflict check (allowed_molecule_id) so we don't
        get a false ConflictError."""
        undisclosed_mol = _make_undisclosed_molecule()
        dr = _make_disclosure_request(undisclosed_mol.id)

        # Simulate identifier owned by the undisclosed molecule
        repo = _make_repo(
            find_undisclosed_by_identifiers=undisclosed_mol,
            find_identifiers_in_workspace={
                "Undisclosed-001": undisclosed_mol.id,
            },
        )

        mock_ds = AsyncMock()
        mock_ds.return_value = Success(
            DisclosureOutcome(
                disclosure_request=dr,
                was_merged=False,
                needs_confirmation=False,
            )
        )

        uc = _make_use_case(repo=repo, disclosure_service=mock_ds)
        cmd = _make_command(name="Undisclosed-001")

        result = await uc(cmd, auth=FakeAuth())

        # Should succeed (not fail with ConflictError) because the matched
        # molecule's ID is passed as allowed_molecule_id
        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.DISCLOSED
