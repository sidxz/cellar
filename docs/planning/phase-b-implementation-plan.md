# Phase B: Unified Registration & Disclosure Wizard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the registration dialog + inline disclosure form with a single full-page wizard that handles both single and bulk registration with automatic disclosure detection, Temporal processing for bulk, and batch-confirm merge review.

**Architecture:** Enhance `RegisterMolecule` use case with identifier-match → disclosure detection. Shared Temporal activity (`process_chunk`) serves both wizard and CDD import. Frontend is a Zustand-driven step wizard at `/compounds/register` with 5 steps: Input → Processing → Results → Batch → Summary.

**Tech Stack:** Python/FastAPI (backend), Temporal (bulk workflows), React/Next.js/TypeScript (frontend), Zustand (wizard state), TanStack Query (server state), shadcn/ui (components)

**Design doc:** `docs/planning/phase-b-unified-wizard-design.md`

**Mandatory reads before coding:**
- `docs/backend-code-guidelines.md`
- `docs/patterns-and-conventions.md`
- `docs/planning/phase-b-unified-wizard-design.md`

---

### Task 1: RegistrationAction Enum + RegistrationOutcome Enhancement

**Files:**
- Modify: `backend/src/chem_vault/domain/chemical_registration/enums.py`
- Modify: `backend/src/chem_vault/application/chemical_registration/register_molecule.py`
- Test: `backend/tests/unit/chemical_registration/test_register_molecule.py`

- [ ] **Step 1: Add RegistrationAction enum**

In `backend/src/chem_vault/domain/chemical_registration/enums.py`, add after `BulkRegistrationFileFormat`:

```python
class RegistrationAction(str, Enum):
    """Outcome action from the unified registration pipeline."""

    REGISTERED = "registered"
    DEDUPLICATED = "deduplicated"
    DISCLOSED = "disclosed"
    MERGE_CANDIDATE = "merge_candidate"
    CONFLICT = "conflict"
```

- [ ] **Step 2: Enhance RegistrationOutcome**

In `backend/src/chem_vault/application/chemical_registration/register_molecule.py`, replace the `RegistrationOutcome` dataclass (lines 33-40):

```python
from chem_vault.domain.chemical_registration.enums import MoleculeType, RegistrationAction

@dataclass(frozen=True)
class RegistrationOutcome:
    """Result of a molecule registration."""

    molecule: Molecule
    is_new: bool
    action: RegistrationAction = RegistrationAction.REGISTERED
    qc_warnings: list[str] = field(default_factory=list)
    detected_salt: DetectedSaltDTO | None = None
    # Disclosure detection fields
    needs_merge_confirmation: bool = False
    matched_molecule_id: uuid.UUID | None = None
    disclosure_id: uuid.UUID | None = None
    conflict_reason: str | None = None
```

- [ ] **Step 3: Update existing return paths to include action**

In `_register_disclosed` (line 263), update the dedup return:

```python
return Success(
    RegistrationOutcome(
        molecule=existing_by_inchi, is_new=False,
        action=RegistrationAction.DEDUPLICATED,
        qc_warnings=qc_warnings,
        detected_salt=processed.detected_salt,
    )
)
```

In `_register_disclosed` (line 297), update the new molecule return:

```python
return Success(
    RegistrationOutcome(
        molecule=mol, is_new=True,
        action=RegistrationAction.REGISTERED,
        qc_warnings=qc_warnings,
        detected_salt=processed.detected_salt,
    )
)
```

In `_register_undisclosed` (line 345), update the matched return:

```python
return Success(
    RegistrationOutcome(
        molecule=matched_molecule, is_new=False,
        action=RegistrationAction.DEDUPLICATED,
    )
)
```

In `_register_undisclosed` (line 371), update the new molecule return:

```python
return Success(RegistrationOutcome(
    molecule=mol, is_new=True,
    action=RegistrationAction.REGISTERED,
))
```

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `cd backend && uv run pytest tests/unit/chemical_registration/test_register_molecule.py -v`
Expected: All existing tests PASS (the new `action` field has a default value, so no breaking changes).

- [ ] **Step 5: Commit**

```bash
git add backend/src/chem_vault/domain/chemical_registration/enums.py backend/src/chem_vault/application/chemical_registration/register_molecule.py
git commit -m "feat: add RegistrationAction enum + enhance RegistrationOutcome"
```

---

### Task 2: find_undisclosed_by_identifiers — Protocol + Implementation

**Files:**
- Modify: `backend/src/chem_vault/domain/chemical_registration/repository.py`
- Modify: `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py`
- Test: `backend/tests/integration/chemical_registration/test_molecule_repository.py`

- [ ] **Step 1: Write the failing integration test**

In `backend/tests/integration/chemical_registration/test_molecule_repository.py`, add:

```python
async def test_find_undisclosed_by_identifiers_single_match(
    molecule_repo: SQLAlchemyMoleculeRepository,
    uow: AsyncUnitOfWork,
    workspace_id: uuid.UUID,
):
    """When one identifier matches one undisclosed molecule, return that molecule."""
    # Create an undisclosed molecule with a custom identifier
    async with uow:
        mol = Molecule.register_undisclosed(
            workspace_id=workspace_id,
            registration_number=RegistrationNumber("CV-00100"),
            name="SACC-0419109",
            molecule_type=MoleculeType.SMALL_MOLECULE,
            originating_org_id=uuid.uuid4(),
        )
        mol.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol.id,
                identifier="SACC-0419109",
                identifier_type="custom",
                source="test",
                registered_by=uuid.uuid4(),
            )
        )
        await molecule_repo.save(mol)
        await uow.commit()

    # Search by identifier
    async with uow:
        result = await molecule_repo.find_undisclosed_by_identifiers(
            workspace_id, {"SACC-0419109"}
        )

    assert result is not None
    assert result.id == mol.id


async def test_find_undisclosed_by_identifiers_no_match(
    molecule_repo: SQLAlchemyMoleculeRepository,
    uow: AsyncUnitOfWork,
    workspace_id: uuid.UUID,
):
    """When no identifier matches, return None."""
    async with uow:
        result = await molecule_repo.find_undisclosed_by_identifiers(
            workspace_id, {"NONEXISTENT-ID"}
        )
    assert result is None


async def test_find_undisclosed_by_identifiers_ambiguous(
    molecule_repo: SQLAlchemyMoleculeRepository,
    uow: AsyncUnitOfWork,
    workspace_id: uuid.UUID,
):
    """When identifiers match multiple undisclosed molecules, return None (ambiguous)."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with uow:
        mol1 = Molecule.register_undisclosed(
            workspace_id=workspace_id,
            registration_number=RegistrationNumber("CV-00200"),
            name="MOL-A",
            molecule_type=MoleculeType.SMALL_MOLECULE,
            originating_org_id=org_id,
        )
        mol1.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol1.id, identifier="MOL-A",
                identifier_type="custom", source="test", registered_by=user_id,
            )
        )
        mol2 = Molecule.register_undisclosed(
            workspace_id=workspace_id,
            registration_number=RegistrationNumber("CV-00201"),
            name="MOL-B",
            molecule_type=MoleculeType.SMALL_MOLECULE,
            originating_org_id=org_id,
        )
        mol2.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol2.id, identifier="MOL-B",
                identifier_type="custom", source="test", registered_by=user_id,
            )
        )
        await molecule_repo.save(mol1)
        await molecule_repo.save(mol2)
        await uow.commit()

    async with uow:
        result = await molecule_repo.find_undisclosed_by_identifiers(
            workspace_id, {"MOL-A", "MOL-B"}
        )
    assert result is None  # ambiguous — two different molecules matched


async def test_find_undisclosed_by_identifiers_skips_disclosed(
    molecule_repo: SQLAlchemyMoleculeRepository,
    uow: AsyncUnitOfWork,
    workspace_id: uuid.UUID,
):
    """Only match undisclosed molecules, not disclosed ones."""
    # Create a disclosed molecule with an identifier — should NOT match
    async with uow:
        structure = MoleculeStructure(smiles="CCO", cxsmiles=None, inchi="...", inchi_key="LFQSCWFLJHTTHZ-UHFFFAOYSA-N")
        descriptors = MoleculeDescriptors(molecular_formula="C2H6O", molecular_weight=46.07)
        mol = Molecule.register_disclosed(
            workspace_id=workspace_id,
            registration_number=RegistrationNumber("CV-00300"),
            name="Ethanol",
            molecule_type=MoleculeType.SMALL_MOLECULE,
            structure=structure,
            descriptors=descriptors,
            originating_org_id=uuid.uuid4(),
        )
        mol.add_identifier(
            MoleculeIdentifier.create(
                molecule_id=mol.id, identifier="Ethanol",
                identifier_type="custom", source="test", registered_by=uuid.uuid4(),
            )
        )
        await molecule_repo.save(mol)
        await uow.commit()

    async with uow:
        result = await molecule_repo.find_undisclosed_by_identifiers(
            workspace_id, {"Ethanol"}
        )
    assert result is None  # disclosed molecules should not match
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/integration/chemical_registration/test_molecule_repository.py -k "find_undisclosed_by_identifiers" -v`
Expected: FAIL with `AttributeError: 'SQLAlchemyMoleculeRepository' object has no attribute 'find_undisclosed_by_identifiers'`

- [ ] **Step 3: Add to Protocol**

In `backend/src/chem_vault/domain/chemical_registration/repository.py`, add to the `MoleculeRepository` Protocol:

```python
async def find_undisclosed_by_identifiers(
    self, workspace_id: uuid.UUID, identifiers: set[str]
) -> Molecule | None:
    """Find a single undisclosed molecule whose identifiers overlap with the given set.

    Returns None if no match or if identifiers map to multiple different molecules (ambiguous).
    Only matches molecules with structure_status == UNDISCLOSED and no tombstone.
    """
    ...
```

- [ ] **Step 4: Implement in SQLAlchemy repository**

In `backend/src/chem_vault/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py`, add the implementation:

```python
async def find_undisclosed_by_identifiers(
    self, workspace_id: uuid.UUID, identifiers: set[str]
) -> Molecule | None:
    if not identifiers:
        return None

    # Find molecule IDs whose identifiers match, filtering to undisclosed + non-tombstone
    stmt = (
        select(MoleculeIdentifierModel.molecule_id)
        .join(MoleculeModel, MoleculeIdentifierModel.molecule_id == MoleculeModel.id)
        .where(
            MoleculeModel.workspace_id == workspace_id,
            MoleculeModel.structure_status == "undisclosed",
            MoleculeModel.merged_into_id.is_(None),
            func.lower(MoleculeIdentifierModel.identifier).in_(
                [v.lower() for v in identifiers]
            ),
        )
        .distinct()
    )
    result = await self._session.execute(stmt)
    mol_ids = [row[0] for row in result.all()]

    if len(mol_ids) == 0:
        return None
    if len(mol_ids) > 1:
        return None  # ambiguous — multiple different molecules matched

    return await self.find_by_id_in_workspace(workspace_id, mol_ids[0])
```

Add necessary imports at the top of the file:
```python
from sqlalchemy import func
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/integration/chemical_registration/test_molecule_repository.py -k "find_undisclosed_by_identifiers" -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/chem_vault/domain/chemical_registration/repository.py backend/src/chem_vault/infrastructure/persistence/sqlalchemy/chemical_registration/molecule_repository.py backend/tests/integration/chemical_registration/test_molecule_repository.py
git commit -m "feat: add find_undisclosed_by_identifiers to MoleculeRepository"
```

---

### Task 3: Enhance RegisterMolecule with Disclosure Detection

**Files:**
- Modify: `backend/src/chem_vault/application/chemical_registration/register_molecule.py`
- Modify: `backend/src/chem_vault/infrastructure/di/container.py`
- Test: `backend/tests/unit/chemical_registration/test_register_molecule.py`

**Context:** When a row has SMILES and identifiers match an existing undisclosed molecule, RegisterMolecule should delegate to DisclosureService instead of creating a new molecule.

- [ ] **Step 1: Write failing unit tests for the new disclosure detection path**

In `backend/tests/unit/chemical_registration/test_register_molecule.py`, add tests:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from returns.result import Success, Failure

from chem_vault.application.chemical_registration.register_molecule import (
    RegisterMolecule, RegisterMoleculeCommand, RegistrationOutcome, ExternalId,
)
from chem_vault.application.chemical_registration.disclosure_service import (
    DisclosureService, DisclosureOutcome, SubmitDisclosureCommand,
)
from chem_vault.domain.chemical_registration.enums import (
    MoleculeType, RegistrationAction, StructureStatus,
)


@pytest.fixture
def mock_disclosure_service():
    return AsyncMock(spec=DisclosureService)


class TestDisclosureDetection:
    """Tests for the identifier-match → disclosure detection path."""

    async def test_disclosed_smiles_matching_undisclosed_molecule_triggers_disclosure(
        self,
        mock_uow,
        mock_mol_repo,
        mock_dispatcher,
        mock_structure_processor,
        mock_disclosure_service,
    ):
        """When SMILES provided and identifiers match an undisclosed mol, delegate to DisclosureService."""
        # Setup: undisclosed molecule exists with matching identifier
        undisclosed_mol = _make_undisclosed_molecule(name="SACC-0419109")
        mock_mol_repo.find_by_inchi_key.return_value = None  # no InChIKey match
        mock_mol_repo.find_undisclosed_by_identifiers.return_value = undisclosed_mol
        mock_mol_repo.find_identifiers_in_workspace.return_value = {}

        # Setup: disclosure service returns needs_confirmation
        disclosure_outcome = DisclosureOutcome(
            disclosure_request=MagicMock(id=uuid.uuid4()),
            was_merged=False,
            needs_confirmation=True,
            matched_molecule_id=uuid.uuid4(),
        )
        mock_disclosure_service.return_value = Success(disclosure_outcome)

        # Setup: structure processor returns valid result
        mock_structure_processor.process.return_value = Success(_make_processed_structure())

        uc = RegisterMolecule(
            uow=mock_uow,
            repo=mock_mol_repo,
            dispatcher=mock_dispatcher,
            structure_processor=mock_structure_processor,
            disclosure_service=mock_disclosure_service,
        )

        result = await uc(RegisterMoleculeCommand(
            workspace_id=uuid.uuid4(),
            name="SACC-0419109",
            smiles="CC(=O)Oc1ccccc1C(O)=O",
            originating_org_id=uuid.uuid4(),
            registered_by=uuid.uuid4(),
            external_ids=[ExternalId(identifier="SACC-0419109", identifier_type="custom")],
        ))

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.MERGE_CANDIDATE
        assert outcome.needs_merge_confirmation is True
        mock_disclosure_service.assert_called_once()

    async def test_disclosed_smiles_no_undisclosed_match_registers_normally(
        self,
        mock_uow,
        mock_mol_repo,
        mock_dispatcher,
        mock_structure_processor,
        mock_disclosure_service,
    ):
        """When SMILES provided but no identifier matches undisclosed, register as new."""
        mock_mol_repo.find_by_inchi_key.return_value = None
        mock_mol_repo.find_undisclosed_by_identifiers.return_value = None
        mock_mol_repo.find_identifiers_in_workspace.return_value = {}
        mock_mol_repo.next_registration_number.return_value = RegistrationNumber("CV-00001")
        mock_structure_processor.process.return_value = Success(_make_processed_structure())

        uc = RegisterMolecule(
            uow=mock_uow,
            repo=mock_mol_repo,
            dispatcher=mock_dispatcher,
            structure_processor=mock_structure_processor,
            disclosure_service=mock_disclosure_service,
        )

        result = await uc(RegisterMoleculeCommand(
            workspace_id=uuid.uuid4(),
            name="NewCompound",
            smiles="CCO",
            originating_org_id=uuid.uuid4(),
            registered_by=uuid.uuid4(),
        ))

        assert isinstance(result, Success)
        outcome = result.unwrap()
        assert outcome.action == RegistrationAction.REGISTERED
        mock_disclosure_service.assert_not_called()

    async def test_ambiguous_identifiers_return_conflict(
        self,
        mock_uow,
        mock_mol_repo,
        mock_dispatcher,
        mock_structure_processor,
        mock_disclosure_service,
    ):
        """When identifiers could match multiple undisclosed molecules, return CONFLICT."""
        mock_mol_repo.find_by_inchi_key.return_value = None
        # Ambiguous: find_undisclosed_by_identifiers returns None (multiple matches)
        mock_mol_repo.find_undisclosed_by_identifiers.return_value = None
        # But find_identifiers_in_workspace shows they belong to different mols
        mock_mol_repo.find_identifiers_in_workspace.return_value = {
            "ID-A": uuid.uuid4(),
            "ID-B": uuid.uuid4(),  # different molecule
        }
        mock_structure_processor.process.return_value = Success(_make_processed_structure())

        uc = RegisterMolecule(
            uow=mock_uow,
            repo=mock_mol_repo,
            dispatcher=mock_dispatcher,
            structure_processor=mock_structure_processor,
            disclosure_service=mock_disclosure_service,
        )

        result = await uc(RegisterMoleculeCommand(
            workspace_id=uuid.uuid4(),
            name="Ambiguous",
            smiles="CCO",
            originating_org_id=uuid.uuid4(),
            registered_by=uuid.uuid4(),
            external_ids=[
                ExternalId(identifier="ID-A", identifier_type="custom"),
                ExternalId(identifier="ID-B", identifier_type="custom"),
            ],
        ))

        assert isinstance(result, Failure)  # conflict error
```

Note: You will need to add helper functions `_make_undisclosed_molecule()` and `_make_processed_structure()` to the test file's fixtures, matching existing patterns in that test module.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/chemical_registration/test_register_molecule.py -k "TestDisclosureDetection" -v`
Expected: FAIL — `RegisterMolecule.__init__` doesn't accept `disclosure_service` parameter.

- [ ] **Step 3: Add DisclosureService as optional dependency to RegisterMolecule**

In `register_molecule.py`, update `__init__` (line 78):

```python
from chem_vault.application.chemical_registration.disclosure_service import (
    DisclosureService,
    SubmitDisclosureCommand,
    DisclosureOutcome,
)

class RegisterMolecule:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: MoleculeRepository,
        dispatcher: EventDispatcherProtocol,
        structure_processor: StructureProcessorProtocol,
        custom_field_validator: CustomFieldValidator | None = None,
        disclosure_repo: DisclosureRequestRepository | None = None,
        disclosure_service: DisclosureService | None = None,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._dispatcher = dispatcher
        self._processor = structure_processor
        self._custom_field_validator = custom_field_validator
        self._disclosure_repo = disclosure_repo
        self._disclosure_service = disclosure_service
```

Also add `auto_approve: bool = True` to `RegisterMoleculeCommand`:

```python
@dataclass(frozen=True, kw_only=True)
class RegisterMoleculeCommand(Command):
    workspace_id: uuid.UUID
    name: str
    smiles: str | None = None
    molecule_type: str = MoleculeType.SMALL_MOLECULE.value
    external_ids: list[ExternalId] = field(default_factory=list)
    originating_org_id: uuid.UUID
    registered_by: uuid.UUID
    scientist_name: str | None = None
    custom_fields: dict[str, Any] | None = None
    qc_reject_threshold: int | None = None
    qc_warn_threshold: int | None = None
    promote_name_as_identifier: bool = True
    auto_approve: bool = True  # False from wizard — merge candidates need confirmation
```

- [ ] **Step 4: Add disclosure detection to _register_disclosed**

In `_register_disclosed`, after the InChIKey dedup check (after line 252, the conflict check) and before the "4a. Duplicate InChIKey" block, add the disclosure detection:

```python
        # NEW: Check if identifiers match an existing undisclosed molecule
        if existing_by_inchi is None and self._disclosure_service is not None:
            all_ids = self._collect_all_identifiers(input)
            if all_ids:
                undisclosed_match = await self._repo.find_undisclosed_by_identifiers(
                    input.workspace_id, all_ids
                )
                if undisclosed_match is not None:
                    # Delegate to DisclosureService — this is a disclosure, not a registration
                    disclosure_result = await self._disclosure_service(
                        SubmitDisclosureCommand(
                            workspace_id=input.workspace_id,
                            molecule_id=undisclosed_match.id,
                            disclosed_smiles=input.smiles,  # type: ignore[arg-type]
                            requested_by=input.registered_by,
                            disclosing_org_id=input.originating_org_id,
                            scientist_name=input.scientist_name,
                            auto_approve=input.auto_approve,
                            notes="Auto-detected via identifier match during registration",
                        )
                    )
                    if isinstance(disclosure_result, Failure):
                        return Failure(disclosure_result.failure())

                    d_outcome: DisclosureOutcome = disclosure_result.unwrap()
                    if d_outcome.needs_confirmation:
                        action = RegistrationAction.MERGE_CANDIDATE
                    elif d_outcome.was_merged:
                        action = RegistrationAction.DEDUPLICATED
                    else:
                        action = RegistrationAction.DISCLOSED

                    return Success(RegistrationOutcome(
                        molecule=undisclosed_match,
                        is_new=False,
                        action=action,
                        qc_warnings=qc_warnings,
                        detected_salt=processed.detected_salt,
                        needs_merge_confirmation=d_outcome.needs_confirmation,
                        matched_molecule_id=d_outcome.matched_molecule_id,
                        disclosure_id=d_outcome.disclosure_request.id,
                    ))
```

Important: This block must be placed AFTER the InChIKey dedup check (`existing_by_inchi` lookup) and the identifier conflict check, but BEFORE the "4a. Duplicate InChIKey" block. The disclosure service manages its own UoW, so this works correctly.

- [ ] **Step 5: Run tests**

Run: `cd backend && uv run pytest tests/unit/chemical_registration/test_register_molecule.py -v`
Expected: All tests PASS including the new disclosure detection tests.

- [ ] **Step 6: Update DI container**

In `backend/src/chem_vault/infrastructure/di/container.py`, find the `RegisterMolecule` factory and update it to optionally inject `DisclosureService`. The exact wiring depends on the existing factory pattern — look for where `RegisterMolecule` is defined via `_mol_cmd` and add `disclosure_service` as an optional parameter when the `DisclosureService` is available.

- [ ] **Step 7: Run full chem-reg test suite**

Run: `cd backend && uv run pytest tests/unit/chemical_registration/ -v`
Expected: All tests PASS (226+ existing + new tests).

- [ ] **Step 8: Commit**

```bash
git add backend/src/chem_vault/application/chemical_registration/register_molecule.py backend/src/chem_vault/infrastructure/di/container.py backend/tests/unit/chemical_registration/test_register_molecule.py
git commit -m "feat: add identifier-match disclosure detection to RegisterMolecule"
```

---

### Task 4: Update Temporal DTOs + Activity for Richer Outcomes

**Files:**
- Modify: `backend/src/chem_vault/infrastructure/temporal/activities/dtos.py`
- Modify: `backend/src/chem_vault/infrastructure/temporal/activities/registration.py`
- Modify: `backend/src/chem_vault/infrastructure/temporal/workflows/bulk_registration.py`
- Modify: `backend/src/chem_vault/interface/routes/bulk_registration.py`

**Context:** The activity and workflow need to track the new action categories (disclosed, merge_candidate, conflict) in addition to registered/duplicate/error.

- [ ] **Step 1: Update ChunkItemResult DTO**

In `dtos.py`, update `ChunkItemResult`:

```python
@dataclass
class ChunkItemResult:
    """Result for a single molecule within a chunk."""

    row_index: int
    success: bool
    is_new: bool = False
    action: str = "registered"  # registered | deduplicated | disclosed | merge_candidate | conflict
    molecule_id: str | None = None
    batch_id: str | None = None
    batch_number: str | None = None
    salt_matched: bool = False
    error: str | None = None
    # Disclosure detection fields
    needs_merge_confirmation: bool = False
    matched_molecule_id: str | None = None
    disclosure_id: str | None = None
    conflict_reason: str | None = None
    # CDD fields
    cdd_molecule_id: int | None = None
    cdd_modified_at: str | None = None
```

- [ ] **Step 2: Update ChunkOutput DTO**

In `dtos.py`, update `ChunkOutput`:

```python
@dataclass
class ChunkOutput:
    """Output of the process_chunk activity."""

    registered: int = 0
    duplicate: int = 0
    error: int = 0
    disclosed: int = 0
    merge_candidate: int = 0
    conflict: int = 0
    # Molecule-level counts
    mol_registered: int = 0
    mol_duplicate: int = 0
    mol_error: int = 0
    results: list[ChunkItemResult] = field(default_factory=list)
```

- [ ] **Step 3: Update RegistrationActivities.process_chunk**

In `registration.py`, update the result tracking in `process_chunk` (after line 112):

```python
            outcome = result.unwrap()

            # Map RegistrationOutcome to ChunkItemResult action
            action = outcome.action.value  # "registered", "deduplicated", etc.

            if outcome.action == RegistrationAction.REGISTERED:
                output.registered += 1
            elif outcome.action == RegistrationAction.DEDUPLICATED:
                output.duplicate += 1
            elif outcome.action == RegistrationAction.DISCLOSED:
                output.disclosed += 1
            elif outcome.action == RegistrationAction.MERGE_CANDIDATE:
                output.merge_candidate += 1
            elif outcome.action == RegistrationAction.CONFLICT:
                output.conflict += 1
```

And update the `ChunkItemResult` creation (line 128):

```python
            output.results.append(
                ChunkItemResult(
                    row_index=item.row_index,
                    success=True,
                    is_new=outcome.is_new,
                    action=action,
                    molecule_id=str(outcome.molecule.id),
                    batch_id=str(batch_id) if batch_id else None,
                    batch_number=batch_number,
                    salt_matched=salt_matched,
                    needs_merge_confirmation=outcome.needs_merge_confirmation,
                    matched_molecule_id=str(outcome.matched_molecule_id) if outcome.matched_molecule_id else None,
                    disclosure_id=str(outcome.disclosure_id) if outcome.disclosure_id else None,
                    conflict_reason=outcome.conflict_reason,
                    cdd_molecule_id=item.cdd_molecule_id,
                    cdd_modified_at=item.cdd_modified_at,
                )
            )
```

Add the import at the top:

```python
from chem_vault.domain.chemical_registration.enums import RegistrationAction
```

Skip batch creation for merge_candidate and conflict actions (no batch needed):

```python
            # Skip batch creation for merge candidates and conflicts
            batch_id = None
            batch_number = None
            salt_matched = False
            if outcome.action not in (RegistrationAction.MERGE_CANDIDATE, RegistrationAction.CONFLICT):
                batch_id, batch_number, salt_matched = await _create_batch(...)
```

- [ ] **Step 4: Inject DisclosureService into RegistrationActivities**

Update `RegistrationActivities.process_chunk` to create `RegisterMolecule` with `disclosure_service`:

```python
        # Build DisclosureService so RegisterMolecule can detect disclosures
        disclosure_uow = AsyncUnitOfWork(session_factory)
        disclosure_repo = SQLAlchemyDisclosureRequestRepository(disclosure_uow)
        merge_svc = MergeService(...)  # follow existing pattern from confirm_disclosure DI
        disclosure_svc = DisclosureService(
            uow=disclosure_uow,
            molecule_repo=SQLAlchemyMoleculeRepository(disclosure_uow),
            disclosure_repo=disclosure_repo,
            structure_processor=structure_processor,
            merge_service=merge_svc,
            dispatcher=dispatcher,
        )

        reg_uow = AsyncUnitOfWork(session_factory)
        register_uc = RegisterMolecule(
            uow=reg_uow,
            repo=SQLAlchemyMoleculeRepository(reg_uow),
            dispatcher=dispatcher,
            structure_processor=structure_processor,
            disclosure_service=disclosure_svc,
        )
```

Note: Look at the existing `_disclosure_service` factory in `container.py` (lines 698-719) for the exact MergeService wiring pattern.

- [ ] **Step 5: Update BulkRegistrationProgress**

In `bulk_registration.py`, update `BulkRegistrationProgress`:

```python
@dataclass
class BulkRegistrationProgress:
    """Progress state queryable from the workflow."""

    bulk_reg_id: str = ""
    status: str = "pending"
    total_count: int = 0
    registered_count: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    disclosed_count: int = 0
    merge_candidate_count: int = 0
    conflict_count: int = 0
    chunks_processed: int = 0
    chunks_total: int = 0
    # Merge candidates for review (populated after processing completes)
    merge_candidates: list[dict] = field(default_factory=list)

    @property
    def processed_count(self) -> int:
        return (
            self.registered_count + self.duplicate_count + self.error_count
            + self.disclosed_count + self.merge_candidate_count + self.conflict_count
        )
```

- [ ] **Step 6: Update workflow chunk processing to track new counts**

In the chunk processing loop of `BulkRegistrationWorkflow.run` (after line 168):

```python
            self._progress.registered_count += chunk_result.registered
            self._progress.duplicate_count += chunk_result.duplicate
            self._progress.error_count += chunk_result.error
            self._progress.disclosed_count += chunk_result.disclosed
            self._progress.merge_candidate_count += chunk_result.merge_candidate
            self._progress.conflict_count += chunk_result.conflict
            self._progress.chunks_processed = (input.resume_chunk_index or 0) + i + 1

            # Collect merge candidates for review
            for r in chunk_result.results:
                if r.needs_merge_confirmation and r.disclosure_id:
                    self._progress.merge_candidates.append({
                        "row_index": r.row_index,
                        "molecule_id": r.molecule_id,
                        "matched_molecule_id": r.matched_molecule_id,
                        "disclosure_id": r.disclosure_id,
                    })
```

Also update `BulkRegistrationWorkflowInput` resume fields and `continue_as_new` to carry the new counts:

```python
@dataclass
class BulkRegistrationWorkflowInput:
    # ... existing fields ...
    resume_disclosed: int = 0
    resume_merge_candidate: int = 0
    resume_conflict: int = 0
    resume_merge_candidates_list: list[dict] = field(default_factory=list)
```

And in the resume path and continue-as-new call, carry these fields.

- [ ] **Step 7: Update status endpoint response**

In `bulk_registration.py` routes, update `BulkRegistrationStatusResponse`:

```python
class BulkRegistrationStatusResponse(BaseModel):
    bulk_reg_id: str
    status: str
    total_count: int
    registered_count: int
    duplicate_count: int
    error_count: int
    disclosed_count: int = 0
    merge_candidate_count: int = 0
    conflict_count: int = 0
    chunks_processed: int
    chunks_total: int
    merge_candidates: list[dict] = []
```

And update `get_bulk_registration_status` to return the new fields from progress.

- [ ] **Step 8: Run existing tests**

Run: `cd backend && uv run pytest tests/ -k "bulk_registration or process_chunk" -v`
Expected: All tests PASS.

- [ ] **Step 9: Commit**

```bash
git add backend/src/chem_vault/infrastructure/temporal/activities/dtos.py backend/src/chem_vault/infrastructure/temporal/activities/registration.py backend/src/chem_vault/infrastructure/temporal/workflows/bulk_registration.py backend/src/chem_vault/interface/routes/bulk_registration.py
git commit -m "feat: track disclosure/merge_candidate/conflict in Temporal activity + workflow"
```

---

### Task 5: Confirm-Merges Batch Endpoint

**Files:**
- Modify: `backend/src/chem_vault/interface/routes/bulk_registration.py`
- Modify: `backend/src/chem_vault/interface/dependencies.py`

- [ ] **Step 1: Add confirm-merges endpoint**

In `bulk_registration.py`, add request/response models and the route:

```python
from chem_vault.application.chemical_registration.confirm_disclosure import (
    ConfirmDisclosure,
    ConfirmDisclosureCommand,
)
from chem_vault.application.chemical_registration.reject_disclosure import (
    RejectDisclosure,
    RejectDisclosureCommand,
)


class MergeDecisionInput(BaseModel):
    disclosure_id: uuid.UUID
    action: str  # "confirm" | "reject"
    reason: str | None = None


class ConfirmMergesBody(BaseModel):
    decisions: list[MergeDecisionInput]


class MergeDecisionResult(BaseModel):
    disclosure_id: uuid.UUID
    action: str
    success: bool
    error: str | None = None
    merged_into_molecule_id: uuid.UUID | None = None


class ConfirmMergesResponse(BaseModel):
    results: list[MergeDecisionResult]
    confirmed_count: int
    rejected_count: int
    error_count: int


@router.post("/{workflow_id}/confirm-merges", response_model=ConfirmMergesResponse)
async def confirm_merges(
    auth: AuthDep,
    workflow_id: str,
    body: ConfirmMergesBody,
    confirm_uc: ConfirmDisclosureDep,
    reject_uc: RejectDisclosureDep,
) -> ConfirmMergesResponse:
    """Batch confirm or reject merge candidates from a bulk registration."""
    results: list[MergeDecisionResult] = []
    confirmed = 0
    rejected = 0
    errors = 0

    for decision in body.decisions:
        if decision.action == "confirm":
            result = await confirm_uc(
                ConfirmDisclosureCommand(
                    workspace_id=auth.workspace_id,
                    disclosure_id=decision.disclosure_id,
                    confirmed_by=auth.user_id,
                )
            )
            if isinstance(result, Failure):
                errors += 1
                results.append(MergeDecisionResult(
                    disclosure_id=decision.disclosure_id,
                    action="confirm",
                    success=False,
                    error=str(result.failure()),
                ))
            else:
                confirmed += 1
                outcome = result.unwrap()
                results.append(MergeDecisionResult(
                    disclosure_id=decision.disclosure_id,
                    action="confirm",
                    success=True,
                    merged_into_molecule_id=outcome.merged_into_molecule_id,
                ))

        elif decision.action == "reject":
            result = await reject_uc(
                RejectDisclosureCommand(
                    workspace_id=auth.workspace_id,
                    disclosure_id=decision.disclosure_id,
                    reason=decision.reason,
                    rejected_by=auth.user_id,
                )
            )
            if isinstance(result, Failure):
                errors += 1
                results.append(MergeDecisionResult(
                    disclosure_id=decision.disclosure_id,
                    action="reject",
                    success=False,
                    error=str(result.failure()),
                ))
            else:
                rejected += 1
                results.append(MergeDecisionResult(
                    disclosure_id=decision.disclosure_id,
                    action="reject",
                    success=True,
                ))

    return ConfirmMergesResponse(
        results=results,
        confirmed_count=confirmed,
        rejected_count=rejected,
        error_count=errors,
    )
```

- [ ] **Step 2: Add DI dependencies**

In `backend/src/chem_vault/interface/dependencies.py`, add:

```python
from chem_vault.application.chemical_registration.confirm_disclosure import ConfirmDisclosure
from chem_vault.application.chemical_registration.reject_disclosure import RejectDisclosure

ConfirmDisclosureDep = Annotated[ConfirmDisclosure, Depends(get(ConfirmDisclosure))]
RejectDisclosureDep = Annotated[RejectDisclosure, Depends(get(RejectDisclosure))]
```

Note: Check if these already exist — they may already be wired for the disclosure routes. If so, just import them into the bulk_registration routes.

- [ ] **Step 3: Add import of `Failure` and dependency types to routes file**

```python
from returns.result import Failure
from chem_vault.interface.dependencies import AuthDep, BulkRegistrationServiceDep, ConfirmDisclosureDep, RejectDisclosureDep
```

- [ ] **Step 4: Run the backend to verify routes register**

Run: `cd backend && uv run python -c "from chem_vault.interface.routes.bulk_registration import router; print([r.path for r in router.routes])"`
Expected: Prints list including `/{workflow_id}/confirm-merges`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/chem_vault/interface/routes/bulk_registration.py backend/src/chem_vault/interface/dependencies.py
git commit -m "feat: add POST /bulk-registrations/{id}/confirm-merges batch endpoint"
```

---

### Task 6: Update POST /molecules Response with Action

**Files:**
- Modify: `backend/src/chem_vault/interface/routes/molecules.py`

- [ ] **Step 1: Update RegistrationResponse model**

Find the `RegistrationResponse` Pydantic model in `molecules.py` and add the new fields:

```python
class RegistrationResponse(BaseModel):
    molecule: MoleculeResponse
    is_new: bool
    action: str = "registered"  # registered | deduplicated | disclosed | merge_candidate | conflict
    qc_warnings: list[str] = []
    batch: BatchBriefResponse | None = None
    detected_salt: DetectedSaltResponse | None = None
    # Disclosure detection fields
    needs_merge_confirmation: bool = False
    matched_molecule_id: uuid.UUID | None = None
    disclosure_id: uuid.UUID | None = None
    conflict_reason: str | None = None
```

- [ ] **Step 2: Update the from_domain or route handler**

Update the route handler `register_molecule` to map the new fields from `RegistrationOutcome`:

```python
    return RegistrationResponse(
        molecule=MoleculeResponse.from_domain(outcome.molecule),
        is_new=outcome.is_new,
        action=outcome.action.value,
        qc_warnings=outcome.qc_warnings,
        batch=batch_response,
        detected_salt=salt_response,
        needs_merge_confirmation=outcome.needs_merge_confirmation,
        matched_molecule_id=outcome.matched_molecule_id,
        disclosure_id=outcome.disclosure_id,
        conflict_reason=outcome.conflict_reason,
    )
```

- [ ] **Step 3: Run API tests**

Run: `cd backend && uv run pytest tests/api/ -k "molecule" -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/src/chem_vault/interface/routes/molecules.py
git commit -m "feat: include action + disclosure fields in POST /molecules response"
```

---

### Task 7: Frontend Types + Hooks

**Files:**
- Create: `frontend/src/features/chemical-registration/types/registration-wizard.ts`
- Create: `frontend/src/features/chemical-registration/hooks/use-registration-wizard-api.ts`
- Modify: `frontend/src/features/chemical-registration/types/index.ts`

- [ ] **Step 1: Create wizard types**

```typescript
// frontend/src/features/chemical-registration/types/registration-wizard.ts

import type { Molecule, BatchInput, RegistrationResponse } from "./index";
import type { DisclosureRequest, MergeImpact } from "./disclosure";

export type WizardMode = "single" | "bulk";

export type RegistrationAction =
  | "registered"
  | "deduplicated"
  | "disclosed"
  | "merge_candidate"
  | "conflict";

export interface ExternalIdentifierInput {
  identifier: string;
  identifier_type: string;
}

export interface SingleInput {
  name: string;
  smiles: string | null;
  moleculeType: string;
  originatingOrgId: string | null;
  externalIds: ExternalIdentifierInput[];
  customFields: Record<string, unknown>;
  // Disclosure mode
  disclosureMode: boolean;
  moleculeId: string | null;
}

export interface BulkRow {
  rowIndex: number;
  name: string | null;
  smiles: string | null;
  moleculeType: string;
  externalIds: { identifier: string; identifier_type: string }[];
  // Batch fields from CSV
  amountValue: number | null;
  amountUnit: string;
  saltCode: string | null;
  purity: number | null;
  batchSource: string;
  appearance: string | null;
  // Validation
  error: string | null;
}

export interface BulkInput {
  file: File | null;
  fileFormat: "csv" | "sdf";
  parsedRows: BulkRow[];
  originatingOrgId: string | null;
}

export type JobStatus = "pending" | "processing" | "completed" | "failed";

export interface BulkProgress {
  bulkRegId: string;
  status: JobStatus;
  totalCount: number;
  registeredCount: number;
  duplicateCount: number;
  errorCount: number;
  disclosedCount: number;
  mergeCandidateCount: number;
  conflictCount: number;
  chunksProcessed: number;
  chunksTotal: number;
  mergeCandidates: MergeCandidateRef[];
}

export interface MergeCandidateRef {
  rowIndex: number;
  moleculeId: string;
  matchedMoleculeId: string;
  disclosureId: string;
}

export interface MergeDecision {
  disclosureId: string;
  action: "confirm" | "reject";
  reason?: string;
}

export interface MergeDecisionResult {
  disclosureId: string;
  action: string;
  success: boolean;
  error: string | null;
  mergedIntoMoleculeId: string | null;
}

export interface ConfirmMergesResponse {
  results: MergeDecisionResult[];
  confirmedCount: number;
  rejectedCount: number;
  errorCount: number;
}
```

- [ ] **Step 2: Update RegistrationResponse type**

In `frontend/src/features/chemical-registration/types/index.ts`, update:

```typescript
interface RegistrationResponse {
  molecule: Molecule;
  is_new: boolean;
  action: string; // "registered" | "deduplicated" | "disclosed" | "merge_candidate" | "conflict"
  qc_warnings: string[];
  batch?: { id: string; batch_number: string } | null;
  needs_merge_confirmation: boolean;
  matched_molecule_id: string | null;
  disclosure_id: string | null;
  conflict_reason: string | null;
}
```

- [ ] **Step 3: Create API hooks**

```typescript
// frontend/src/features/chemical-registration/hooks/use-registration-wizard-api.ts

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/shared/lib/api";
import type {
  BulkProgress,
  ConfirmMergesResponse,
  MergeDecision,
} from "../types/registration-wizard";
import type { RegistrationResponse, RegisterMoleculeInput } from "../types/index";
import { MOLECULES_KEY } from "./use-molecules";
import { toast } from "sonner";

/**
 * Single registration — enhanced POST /api/v1/molecules.
 * Now returns action + disclosure detection fields.
 */
export function useSubmitRegistration() {
  const qc = useQueryClient();
  return useMutation<RegistrationResponse, unknown, RegisterMoleculeInput>({
    mutationFn: (data) => api.post("/api/v1/molecules", data).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [MOLECULES_KEY] });
    },
  });
}

/**
 * Start bulk registration via Temporal.
 * Returns { workflow_id, status }.
 */
export function useStartBulkRegistration() {
  return useMutation<{ workflow_id: string; status: string }, unknown, FormData>({
    mutationFn: (formData) =>
      api
        .post("/api/v1/bulk-registrations", formData, {
          headers: { "Content-Type": "multipart/form-data" },
        })
        .then((r) => r.data),
  });
}

/**
 * Poll bulk registration progress.
 */
export function useBulkRegistrationStatus(
  workflowId: string | null,
  enabled: boolean
) {
  return useQuery<BulkProgress>({
    queryKey: ["bulk-registration-status", workflowId],
    queryFn: () =>
      api
        .get(`/api/v1/bulk-registrations/${workflowId}/status`)
        .then((r) => r.data),
    enabled: enabled && !!workflowId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.status === "completed" || data?.status === "failed") return false;
      return 3000; // poll every 3s
    },
  });
}

/**
 * Batch confirm/reject merge candidates.
 */
export function useConfirmMerges(workflowId: string | null) {
  const qc = useQueryClient();
  return useMutation<ConfirmMergesResponse, unknown, MergeDecision[]>({
    mutationFn: (decisions) =>
      api
        .post(`/api/v1/bulk-registrations/${workflowId}/confirm-merges`, {
          decisions,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: [MOLECULES_KEY] });
      toast.success(
        `${data.confirmedCount} merged, ${data.rejectedCount} rejected`
      );
    },
  });
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/chemical-registration/types/registration-wizard.ts frontend/src/features/chemical-registration/types/index.ts frontend/src/features/chemical-registration/hooks/use-registration-wizard-api.ts
git commit -m "feat: add wizard types + API hooks for unified registration"
```

---

### Task 8: Zustand Wizard Store

**Files:**
- Create: `frontend/src/features/chemical-registration/hooks/use-registration-wizard.ts`

- [ ] **Step 1: Create the store**

```typescript
// frontend/src/features/chemical-registration/hooks/use-registration-wizard.ts

import { create } from "zustand";
import type {
  WizardMode,
  SingleInput,
  BulkInput,
  BulkProgress,
  MergeCandidateRef,
  BulkRow,
  RegistrationAction,
} from "../types/registration-wizard";
import type { RegistrationResponse } from "../types/index";

export interface RegistrationWizardState {
  // Mode & navigation
  mode: WizardMode | null;
  currentStep: number;

  // Single input
  singleInput: SingleInput;

  // Bulk input
  bulkInput: BulkInput;

  // Processing
  workflowId: string | null;
  jobStatus: string | null;
  progress: BulkProgress | null;

  // Results (single mode)
  singleResult: RegistrationResponse | null;

  // Merge candidates
  mergeCandidates: MergeCandidateRef[];
  mergeDecisions: Record<string, "confirm" | "reject">;

  // Batch (single only)
  batchInput: {
    source: string;
    amountValue: number | null;
    amountUnit: string;
    purity: number | null;
    saltEntryId: string | null;
    saltStoichiometry: number;
    appearance: string | null;
  } | null;

  // Actions
  setMode: (mode: WizardMode) => void;
  setCurrentStep: (step: number) => void;
  nextStep: () => void;
  prevStep: () => void;
  updateSingleInput: (updates: Partial<SingleInput>) => void;
  updateBulkInput: (updates: Partial<BulkInput>) => void;
  setWorkflowId: (id: string) => void;
  setProgress: (p: BulkProgress) => void;
  setSingleResult: (r: RegistrationResponse) => void;
  setMergeCandidates: (candidates: MergeCandidateRef[]) => void;
  setMergeDecision: (disclosureId: string, decision: "confirm" | "reject") => void;
  confirmAllMerges: () => void;
  rejectAllMerges: () => void;
  setBatchInput: (input: RegistrationWizardState["batchInput"]) => void;
  reset: () => void;
}

const INITIAL_SINGLE_INPUT: SingleInput = {
  name: "",
  smiles: null,
  moleculeType: "small_molecule",
  originatingOrgId: null,
  externalIds: [],
  customFields: {},
  disclosureMode: false,
  moleculeId: null,
};

const INITIAL_BULK_INPUT: BulkInput = {
  file: null,
  fileFormat: "csv",
  parsedRows: [],
  originatingOrgId: null,
};

export const useRegistrationWizard = create<RegistrationWizardState>((set, get) => ({
  mode: null,
  currentStep: 0,
  singleInput: { ...INITIAL_SINGLE_INPUT },
  bulkInput: { ...INITIAL_BULK_INPUT },
  workflowId: null,
  jobStatus: null,
  progress: null,
  singleResult: null,
  mergeCandidates: [],
  mergeDecisions: {},
  batchInput: null,

  setMode: (mode) => set({ mode }),
  setCurrentStep: (step) => set({ currentStep: step }),

  nextStep: () => set((s) => ({ currentStep: s.currentStep + 1 })),
  prevStep: () => set((s) => ({ currentStep: Math.max(0, s.currentStep - 1) })),

  updateSingleInput: (updates) =>
    set((s) => ({ singleInput: { ...s.singleInput, ...updates } })),

  updateBulkInput: (updates) =>
    set((s) => ({ bulkInput: { ...s.bulkInput, ...updates } })),

  setWorkflowId: (id) => set({ workflowId: id }),
  setProgress: (p) => set({ progress: p, jobStatus: p.status }),

  setSingleResult: (r) => set({ singleResult: r }),

  setMergeCandidates: (candidates) => {
    const decisions: Record<string, "confirm" | "reject"> = {};
    for (const c of candidates) {
      decisions[c.disclosureId] = "confirm"; // default: all checked
    }
    set({ mergeCandidates: candidates, mergeDecisions: decisions });
  },

  setMergeDecision: (disclosureId, decision) =>
    set((s) => ({
      mergeDecisions: { ...s.mergeDecisions, [disclosureId]: decision },
    })),

  confirmAllMerges: () =>
    set((s) => {
      const decisions: Record<string, "confirm" | "reject"> = {};
      for (const c of s.mergeCandidates) {
        decisions[c.disclosureId] = "confirm";
      }
      return { mergeDecisions: decisions };
    }),

  rejectAllMerges: () =>
    set((s) => {
      const decisions: Record<string, "confirm" | "reject"> = {};
      for (const c of s.mergeCandidates) {
        decisions[c.disclosureId] = "reject";
      }
      return { mergeDecisions: decisions };
    }),

  setBatchInput: (input) => set({ batchInput: input }),

  reset: () =>
    set({
      mode: null,
      currentStep: 0,
      singleInput: { ...INITIAL_SINGLE_INPUT },
      bulkInput: { ...INITIAL_BULK_INPUT },
      workflowId: null,
      jobStatus: null,
      progress: null,
      singleResult: null,
      mergeCandidates: [],
      mergeDecisions: {},
      batchInput: null,
    }),
}));
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/chemical-registration/hooks/use-registration-wizard.ts
git commit -m "feat: add Zustand wizard store for unified registration"
```

---

### Task 9: Wizard Shell + Route + Step Input

**Files:**
- Create: `frontend/src/app/(dashboard)/compounds/register/page.tsx`
- Create: `frontend/src/features/chemical-registration/components/registration-wizard/registration-wizard.tsx`
- Create: `frontend/src/features/chemical-registration/components/registration-wizard/step-input.tsx`

- [ ] **Step 1: Create the route page**

```typescript
// frontend/src/app/(dashboard)/compounds/register/page.tsx
import { RegistrationWizard } from "@/features/chemical-registration/components/registration-wizard/registration-wizard";

export default function RegisterPage() {
  return <RegistrationWizard />;
}
```

- [ ] **Step 2: Create the wizard shell**

Build `registration-wizard.tsx` — the step engine that:
- Reads `mode`, `currentStep` from the store
- Reads URL params: `?mode=bulk`, `?disclose={moleculeId}`
- On mount: if URL has `disclose` param, set `mode: "single"`, `disclosureMode: true`, `moleculeId`
- If URL has `mode=bulk`, set `mode: "bulk"`
- Renders the current step component based on `currentStep`
- Shows step indicator (progress dots or breadcrumb)
- Handles browser back with `beforeunload` warning
- Calls `reset()` on unmount

Step mapping:
```typescript
const SINGLE_STEPS = ["Input", "Processing", "Results", "Batch", "Summary"];
const BULK_STEPS = ["Input", "Processing", "Results", "Summary"];

function getStepComponent(mode: WizardMode, step: number) {
  if (mode === "single") {
    switch (step) {
      case 0: return <StepInput />;
      case 1: return <StepProcessing />;
      case 2: return <StepResults />;
      case 3: return <StepBatch />;
      case 4: return <StepSummary />;
    }
  } else {
    switch (step) {
      case 0: return <StepInput />;
      case 1: return <StepProcessing />;
      case 2: return <StepResults />;
      case 3: return <StepSummary />;
    }
  }
}
```

Use shadcn Card as the wizard container. Use a simple step indicator row at the top showing step names with active state highlighting.

- [ ] **Step 3: Create StepInput component**

Build `step-input.tsx` that renders:

**If mode is null:** Mode selection cards — "Register Single Compound" and "Bulk Upload" cards with icons, clicking sets mode and stays on step 0 showing the form.

**Single mode form:**
- Reuse form field structure from `molecule-registration-dialog.tsx` (lines 61-78) but as a full-page form, not a dialog
- Fields: Name, SMILES editor (with draw button), molecule type select, organization select, external identifiers (add/remove rows), custom fields
- If `disclosureMode`: show a banner "Disclosing [molecule name]", pre-fill the molecule context, hide name/type fields (already set)
- "Next" button validates and calls `nextStep()`

**Bulk mode form:**
- File drop zone (CSV/SDF) — use existing pattern from bulk registration dialog if one exists
- File format selector (csv/sdf)
- Organization selector
- After file upload: parse client-side (Papa Parse for CSV) and show preview table with first 10 rows
- "Download Template" button — generates CSV with required headers + 2 example rows
- Column mapping if needed (auto-detect common headers)
- "Next" button validates file is selected and parsed

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/\\(dashboard\\)/compounds/register/page.tsx frontend/src/features/chemical-registration/components/registration-wizard/
git commit -m "feat: add registration wizard shell + route + step-input component"
```

---

### Task 10: Step Processing + Step Results

**Files:**
- Create: `frontend/src/features/chemical-registration/components/registration-wizard/step-processing.tsx`
- Create: `frontend/src/features/chemical-registration/components/registration-wizard/step-results.tsx`
- Create: `frontend/src/features/chemical-registration/components/registration-wizard/merge-candidate-card.tsx`

- [ ] **Step 1: Create StepProcessing**

Build `step-processing.tsx`:

**Single mode:**
- On mount: call `useSubmitRegistration().mutateAsync()` with the single input from store
- Show spinner with "Processing compound..."
- On success: store result via `setSingleResult()`, auto-advance to results step
- On error: show error message with "Back" button

**Bulk mode:**
- On mount: build FormData from `bulkInput.file`, call `useStartBulkRegistration().mutateAsync()`
- Store workflow ID via `setWorkflowId()`
- Use `useBulkRegistrationStatus(workflowId, true)` to poll progress
- Render progress bar: `progress.chunksProcessed / progress.chunksTotal`
- Show running counts: Registered, Deduped, Disclosed, Merge Candidates, Conflicts
- On status === "completed": extract merge candidates from progress, call `setMergeCandidates()`, auto-advance to results step
- On status === "failed": show error with retry option

- [ ] **Step 2: Create MergeCandidateCard**

Build `merge-candidate-card.tsx`:

Props:
```typescript
interface MergeCandidateCardProps {
  candidate: MergeCandidateRef;
  decision: "confirm" | "reject";
  onDecisionChange: (decision: "confirm" | "reject") => void;
  disabled?: boolean; // true when blockers present
}
```

Component:
- Checkbox (checked = confirm, unchecked = reject)
- Source molecule name + reg number → Target molecule name + reg number (fetch with `useMolecule()`)
- Expandable "Show impact details" section using Collapsible from shadcn
- When expanded: call `useMergeImpact(sourceId, targetId)` and render the `ImpactRow` pattern from `merge-preview-page.tsx` (lines 339-369)
- If blockers present: checkbox disabled, red banner with blocker text

- [ ] **Step 3: Create StepResults**

Build `step-results.tsx`:

**Single mode, no merge candidate:**
- Brief success message: "Registered as {reg_number}" or "Disclosed — structure applied"
- Auto-advance to batch step after 2 seconds (or "Continue" button)

**Single mode, merge candidate:**
- Full merge preview inline (single MergeCandidateCard, expanded by default)
- Confirm / Reject buttons at bottom

**Bulk mode:**
- Summary badges row: Registered (N), Deduped (N), Disclosed (N), Merge Candidates (N), Conflicts (N)
- Tab group: "All" | "Merge Candidates (N)" | "Conflicts (N)"
- Merge Candidates tab: "Confirm All" / "Reject All" buttons + list of `MergeCandidateCard` components
- Conflicts tab: read-only list with error messages and links to compound detail pages
- "Confirm Selected & Continue" button:
  - Builds `MergeDecision[]` from `mergeDecisions` store
  - Calls `useConfirmMerges(workflowId).mutateAsync(decisions)`
  - On success: advance to summary step

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/chemical-registration/components/registration-wizard/step-processing.tsx frontend/src/features/chemical-registration/components/registration-wizard/step-results.tsx frontend/src/features/chemical-registration/components/registration-wizard/merge-candidate-card.tsx
git commit -m "feat: add step-processing + step-results with merge candidate review"
```

---

### Task 11: Step Batch + Step Summary

**Files:**
- Create: `frontend/src/features/chemical-registration/components/registration-wizard/step-batch.tsx`
- Create: `frontend/src/features/chemical-registration/components/registration-wizard/step-summary.tsx`

- [ ] **Step 1: Create StepBatch (single mode only)**

Build `step-batch.tsx`:

- Only rendered in single mode (bulk sources batch from CSV)
- Optional form — "Skip" button auto-creates batch with defaults
- Fields: Source (select: synthesized/purchased/donated), Amount + Unit, Purity, Salt form (select from workspace salt entries), Stoichiometry, Appearance
- Reuse the batch field pattern from `molecule-registration-dialog.tsx` (lines 70-77)
- "Create Batch" button: calls `useCreateBatch()` (existing hook from inventory) with molecule ID from `singleResult`
- "Skip & Auto-Create" button: calls same hook with default values (source: "synthesized", amount: 0)
- On success: advance to summary step

- [ ] **Step 2: Create StepSummary**

Build `step-summary.tsx`:

**Single mode:**
```
✓ Compound registered successfully

Registration Number: CV-00XXX
Name: [name]
Action: Registered / Deduplicated / Disclosed / Merged

[View Compound →]   [Register Another]
```

**Bulk mode:**
```
✓ Bulk registration complete

┌─────────┬─────┐
│ Action   │ Count │
├─────────┼─────┤
│ Registered │ 189 │
│ Deduplicated │ 31 │
│ Disclosed │ 18 │
│ Merged │ 3 │
│ Rejected │ 1 │
│ Conflicts │ 5 │
└─────────┴─────┘

5 conflicts require manual resolution.
[View Compound List →]  [Register More]
```

- "View Compound" / "View Compound List" navigates to the compound detail or list page
- "Register Another" / "Register More" calls `reset()` and stays on the wizard
- Conflicts row links to the Review Queue (disclosure list filtered by status=conflict)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/chemical-registration/components/registration-wizard/step-batch.tsx frontend/src/features/chemical-registration/components/registration-wizard/step-summary.tsx
git commit -m "feat: add step-batch + step-summary for registration wizard"
```

---

### Task 12: Entry Point Updates + Cleanup

**Files:**
- Modify: `frontend/src/features/chemical-registration/components/molecule-list.tsx`
- Modify: `frontend/src/features/chemical-registration/components/compound-detail.tsx`
- Modify: `frontend/src/features/chemical-registration/components/detail-tabs/overview-tab.tsx`
- Delete: `frontend/src/features/chemical-registration/components/molecule-registration-dialog.tsx`

- [ ] **Step 1: Update molecule-list.tsx**

Replace dialog-based registration with navigation:

```typescript
import { useRouter } from "next/navigation";

const router = useRouter();

// Replace: onClick={() => setDialogOpen(true)}
// With:
onClick={() => router.push("/compounds/register")}

// Replace: onClick={() => setBulkOpen(true)}
// With:
onClick={() => router.push("/compounds/register?mode=bulk")}

// Replace "Disclose" action in grid column:
// From: navigates to `/compounds/{id}#disclose`
// To: navigates to `/compounds/register?disclose=${mol.id}`
```

Remove the `dialogOpen` and `bulkOpen` state variables, the `MoleculeRegistrationDialog` import and JSX usage, and any `BulkRegistrationDialog` import and JSX usage.

- [ ] **Step 2: Update overview-tab.tsx**

Remove the `DisclosureSection` component (lines 277-428) entirely.

In its place, add a simple banner for undisclosed molecules:

```typescript
{molecule.structure_status === "undisclosed" && (
  <Card className="border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950">
    <CardContent className="flex items-center justify-between p-4">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-600" />
        <span className="text-sm text-amber-800 dark:text-amber-200">
          This compound is undisclosed — no structure on file.
        </span>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() => router.push(`/compounds/register?disclose=${molecule.id}`)}
      >
        Disclose Compound →
      </Button>
    </CardContent>
  </Card>
)}
```

Remove the `#disclose` hash fragment handling and `autoOpenDisclose` logic.

- [ ] **Step 3: Update compound-detail.tsx**

Remove any `#disclose` hash-based tab switching logic. The overview tab no longer needs to auto-open a disclosure form.

- [ ] **Step 4: Delete the old registration dialog**

```bash
rm frontend/src/features/chemical-registration/components/molecule-registration-dialog.tsx
```

Verify no other files import it:

```bash
cd frontend && grep -r "molecule-registration-dialog" src/
```

If any imports remain, update them to remove the dead references.

- [ ] **Step 5: Verify the app builds**

Run: `cd frontend && pnpm build`
Expected: Build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add -u frontend/src/
git commit -m "feat: wire wizard entry points + remove old registration dialog + inline disclosure"
```

---

## Execution Notes

**Layer order followed:** Domain (Task 1) → Persistence (Task 2) → Application (Task 3) → Temporal (Task 4) → API (Tasks 5-6) → Frontend (Tasks 7-12)

**CDD import compatibility:** The CDD import workflow calls `RegistrationActivities.process_chunk` which calls `RegisterMolecule`. After Task 3, `RegisterMolecule` gains disclosure detection but only when `disclosure_service` is injected. Task 4 injects it for the wizard's Temporal activities. The CDD import's activity instance must ALSO receive the disclosure service injection to share the same activity code. If CDD imports should NOT trigger disclosure detection (they shouldn't — CDD molecules are already disclosed), pass `auto_approve=True` in the `RegisterMoleculeCommand` which auto-merges rather than creating merge candidates.

**What about `auto_approve`?** CDD import items don't set `auto_approve` on the command (it defaults to `True`). This means even with disclosure detection enabled, matches auto-merge — no `MERGE_CANDIDATE` results. Only the wizard UI sends `auto_approve=False`.

**What to verify after all tasks:**
1. Single registration from wizard works (new compound + dedup + disclosure + merge candidate)
2. Bulk registration from wizard works (Temporal processing + progress + merge review)
3. CDD import still works (no regressions)
4. "Disclose" from compound list/detail routes to wizard
5. Old dialog is gone, inline disclosure is gone
6. Merge preview page still works for any Phase A pending confirmations
