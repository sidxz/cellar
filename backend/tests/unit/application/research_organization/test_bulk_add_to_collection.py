"""Tests for BulkAddToCollection use case — find-and-add CSV row pipeline."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from cellar.application.research_organization.bulk_add_to_collection import (
    BulkAddToCollection,
    BulkAddToCollectionCommand,
    CachedPreview,
    StashedUnregisteredRows,
)
from cellar.application.shared.molecule_resolver import (
    ResolvedMolecule,
    UnresolvedMolecule,
)
from cellar.domain.research_organization.bulk_add_types import (
    BulkAddRow,
    RowStatus,
)
from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)


@dataclass
class FakeResolver:
    """Stub: returns canned (resolved, unresolved) by reference value."""

    resolved_map: dict[str, uuid.UUID]
    ambiguous_values: set[str]
    calls: list[list] = field(default_factory=list)

    async def resolve(self, workspace_id, refs):
        self.calls.append(list(refs))
        resolved, unresolved = [], []
        for r in refs:
            if r.value in self.resolved_map:
                resolved.append(
                    ResolvedMolecule(ref=r, molecule_id=self.resolved_map[r.value])
                )
            elif r.value in self.ambiguous_values:
                unresolved.append(UnresolvedMolecule(ref=r, reason="ambiguous"))
            else:
                unresolved.append(UnresolvedMolecule(ref=r, reason="not_found"))
        return resolved, unresolved


@dataclass
class FakeCollectionRepo:
    members: set[uuid.UUID]
    collection_exists: bool = True

    async def find_by_id_in_workspace(self, ws, cid):
        return object() if self.collection_exists else None

    async def add_molecules(self, ws, cid, ids):
        new = [i for i in ids if i not in self.members]
        self.members.update(new)
        return len(new)

    async def get_molecule_ids(self, ws, cid, *, offset=0, limit=100):
        return list(self.members)[offset : offset + limit]


@dataclass
class FakeMoleculeRepo:
    """Stub: returns SimpleNamespace mol-like objects keyed by id.

    Stamps registration_number as "CC-<first6 of id, upper>" by default; name
    comes from the dict. The use case prefers registration_number for display
    but falls back to name when reg is missing.
    """

    names_by_id: dict[uuid.UUID, str] = field(default_factory=dict)
    include_registration_number: bool = True

    async def find_by_ids(self, ws, ids):
        result = []
        for mid in ids:
            if mid in self.names_by_id:
                reg = (
                    f"CC-{str(mid)[:6].upper()}"
                    if self.include_registration_number
                    else None
                )
                result.append(
                    SimpleNamespace(
                        id=mid,
                        name=self.names_by_id[mid],
                        registration_number=reg,
                    )
                )
        return result


@dataclass
class FakeUoW:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def commit(self):
        return []


@dataclass
class FakeTemplateRepo:
    """Stub: holds templates keyed by (workspace_id, template_id)."""

    items: dict[tuple[uuid.UUID, uuid.UUID], CollectionImportTemplate] = field(
        default_factory=dict
    )

    async def find_by_id_in_workspace(self, ws, tid):
        return self.items.get((ws, tid))

    async def save(self, t):
        self.items[(t.workspace_id, t.id)] = t


@pytest.mark.asyncio
async def test_dry_run_classifies_all_five_statuses():
    existing = uuid.uuid4()
    already = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-000001": existing, "CC-000002": already},
        ambiguous_values={"aspirin"},
    )
    repo = FakeCollectionRepo(members={already})
    molecule_repo = FakeMoleculeRepo(
        names_by_id={existing: "Phenol", already: "Acetone"}
    )
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=FakeTemplateRepo(),
    )

    rows = [
        BulkAddRow(row_index=0, registration_number="CC-000001"),
        BulkAddRow(row_index=1, registration_number="CC-000002"),
        BulkAddRow(row_index=2, smiles="c1ccccc1O"),
        BulkAddRow(row_index=3, name="aspirin"),
        BulkAddRow(row_index=4, notes="just a note"),
    ]
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=rows,
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    statuses = {o.row_index: o.status for o in result.outcomes}
    assert statuses == {
        0: RowStatus.RESOLVED,
        1: RowStatus.ALREADY_PRESENT,
        2: RowStatus.UNREGISTERED,
        3: RowStatus.AMBIGUOUS,
        4: RowStatus.ERROR,
    }
    assert result.preview_id is not None


@pytest.mark.asyncio
async def test_commit_adds_only_resolved_rows():
    resolver = FakeResolver(
        resolved_map={"CC-1": uuid.uuid4(), "CC-2": uuid.uuid4()},
        ambiguous_values=set(),
    )
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo()
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=FakeTemplateRepo(),
    )

    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[
            BulkAddRow(row_index=0, registration_number="CC-1"),
            BulkAddRow(row_index=1, registration_number="CC-2"),
            BulkAddRow(row_index=2, smiles="c1ccccc1O"),
        ],
        dry_run=False,
    )
    result = (await use_case(cmd)).unwrap()
    assert result.resolved_count == 2
    assert result.unregistered_count == 1
    assert len(repo.members) == 2


@pytest.mark.asyncio
async def test_stash_persists_unregistered_rows_for_handoff():
    resolver = FakeResolver(resolved_map={}, ambiguous_values=set())
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo()
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=FakeTemplateRepo(),
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, smiles="c1ccccc1O", name="phenol")],
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    stashed = use_case.fetch_stash(result.preview_id)
    assert isinstance(stashed, CachedPreview)
    # StashedUnregisteredRows is a backwards-compat alias for CachedPreview.
    assert isinstance(stashed, StashedUnregisteredRows)
    # The stash now holds ALL input rows (so commit can reuse outcomes);
    # filtering to unregistered happens at the handoff endpoint.
    assert stashed.rows[0].smiles == "c1ccccc1O"
    assert stashed.rows[0].name == "phenol"
    # Outcomes are cached too.
    assert len(stashed.outcomes) == 1
    assert stashed.outcomes[0].status == RowStatus.UNREGISTERED


@pytest.mark.asyncio
async def test_collection_not_found_returns_failure():
    resolver = FakeResolver(resolved_map={}, ambiguous_values=set())
    repo = FakeCollectionRepo(members=set(), collection_exists=False)
    molecule_repo = FakeMoleculeRepo()
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=FakeTemplateRepo(),
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=True,
    )
    result = await use_case(cmd)
    assert result.failure() is not None  # NotFoundError


@pytest.mark.asyncio
async def test_fetch_stash_returns_none_after_ttl_expiry():
    resolver = FakeResolver(resolved_map={}, ambiguous_values=set())
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo()
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=FakeTemplateRepo(),
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, smiles="c1ccccc1O")],
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    preview_id = result.preview_id
    assert use_case.fetch_stash(preview_id) is not None

    # Manually expire the stash entry by overwriting its expires_at to the past.
    entry = use_case._stash[preview_id]
    use_case._stash[preview_id] = type(entry)(
        workspace_id=entry.workspace_id,
        collection_id=entry.collection_id,
        rows=entry.rows,
        outcomes=entry.outcomes,
        expires_at=0.0,
    )
    assert use_case.fetch_stash(preview_id) is None


@pytest.mark.asyncio
async def test_resolved_outcomes_carry_molecule_name():
    """Preview rows for resolved/already_present molecules must show the
    chemist a display name — fixes the all-em-dash bug in the import wizard.
    """
    existing = uuid.uuid4()
    already = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-000001": existing, "CC-000002": already},
        ambiguous_values=set(),
    )
    repo = FakeCollectionRepo(members={already})
    molecule_repo = FakeMoleculeRepo(
        names_by_id={existing: "Phenol", already: "Acetone"}
    )
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=FakeTemplateRepo(),
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[
            BulkAddRow(row_index=0, registration_number="CC-000001"),
            BulkAddRow(row_index=1, registration_number="CC-000002"),
            BulkAddRow(row_index=2, smiles="c1ccccc1O"),
        ],
        dry_run=True,
    )
    result = (await use_case(cmd)).unwrap()
    by_idx = {o.row_index: o for o in result.outcomes}

    # Resolved row: name must be populated (either reg_number or fallback name).
    assert by_idx[0].status == RowStatus.RESOLVED
    assert by_idx[0].molecule_name is not None
    assert by_idx[0].molecule_name != ""

    # Already-present row: same — chemist needs to know which mol is dupe.
    assert by_idx[1].status == RowStatus.ALREADY_PRESENT
    assert by_idx[1].molecule_name is not None
    assert by_idx[1].molecule_name != ""

    # Unregistered row: molecule_id is None, so molecule_name stays None.
    assert by_idx[2].status == RowStatus.UNREGISTERED
    assert by_idx[2].molecule_id is None
    assert by_idx[2].molecule_name is None


@pytest.mark.asyncio
async def test_commit_with_template_id_records_usage():
    """On commit with template_id + at least one resolved row, the template
    records the collection in its used_in_collections list.
    """
    existing_mol = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-1": existing_mol}, ambiguous_values=set()
    )
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo(names_by_id={existing_mol: "Phenol"})

    template_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    tpl = CollectionImportTemplate(
        id=template_id,
        workspace_id=workspace_id,
        name="t",
        column_mapping={"registration_number": "Reg No."},
        created_by=uuid.uuid4(),
    )
    template_repo = FakeTemplateRepo(items={(workspace_id, template_id): tpl})

    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=template_repo,
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=workspace_id,
        collection_id=collection_id,
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=False,
        template_id=template_id,
    )
    result = (await use_case(cmd)).unwrap()

    assert result.resolved_count == 1
    # Template was updated with the usage
    assert collection_id in tpl.used_in_collections


@pytest.mark.asyncio
async def test_commit_with_template_id_but_no_resolved_rows_skips_usage():
    """If nothing actually resolved, the template usage list stays empty —
    we don't pollute the chemist's "used here before" filter with no-ops.
    """
    resolver = FakeResolver(resolved_map={}, ambiguous_values=set())
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo()

    template_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    tpl = CollectionImportTemplate(
        id=template_id,
        workspace_id=workspace_id,
        name="t",
        column_mapping={"registration_number": "Reg No."},
        created_by=uuid.uuid4(),
    )
    template_repo = FakeTemplateRepo(items={(workspace_id, template_id): tpl})

    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=template_repo,
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=workspace_id,
        collection_id=collection_id,
        rows=[BulkAddRow(row_index=0, registration_number="CC-NOPE")],
        dry_run=False,
        template_id=template_id,
    )
    await use_case(cmd)

    assert collection_id not in tpl.used_in_collections
    assert tpl.used_in_collections == []


@pytest.mark.asyncio
async def test_commit_without_template_id_does_not_touch_template_repo():
    """No template_id on the command means the template repo is never read."""
    resolver = FakeResolver(
        resolved_map={"CC-1": uuid.uuid4()}, ambiguous_values=set()
    )
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo()
    template_repo = FakeTemplateRepo()

    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=template_repo,
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=False,
        template_id=None,
    )
    result = (await use_case(cmd)).unwrap()

    assert result.resolved_count == 1
    assert template_repo.items == {}


@pytest.mark.asyncio
async def test_dry_run_with_template_id_does_not_record_usage():
    """Preview / dry-run must never mutate the template — usage only on commit."""
    existing_mol = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-1": existing_mol}, ambiguous_values=set()
    )
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo(names_by_id={existing_mol: "Phenol"})

    template_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    tpl = CollectionImportTemplate(
        id=template_id,
        workspace_id=workspace_id,
        name="t",
        column_mapping={"registration_number": "Reg No."},
        created_by=uuid.uuid4(),
    )
    template_repo = FakeTemplateRepo(items={(workspace_id, template_id): tpl})

    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=template_repo,
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=workspace_id,
        collection_id=collection_id,
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=True,
        template_id=template_id,
    )
    await use_case(cmd)

    assert tpl.used_in_collections == []


@pytest.mark.asyncio
async def test_commit_with_preview_id_reuses_cached_outcomes():
    """Commit with a valid preview_id reuses cached outcomes and does NOT
    call the resolver again — the perf fix that motivated this change.
    """
    existing_mol = uuid.uuid4()
    workspace_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-1": existing_mol}, ambiguous_values=set()
    )
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo(names_by_id={existing_mol: "Phenol"})
    template_repo = FakeTemplateRepo()
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=template_repo,
    )

    # Step 1: preview
    preview_cmd = BulkAddToCollectionCommand(
        workspace_id=workspace_id,
        collection_id=collection_id,
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=True,
    )
    preview_result = (await use_case(preview_cmd)).unwrap()
    assert preview_result.preview_id is not None
    assert preview_result.resolved_count == 1
    assert len(resolver.calls) == 1

    # Step 2: commit with preview_id reuses cache — resolver call count stays at 1.
    commit_cmd = BulkAddToCollectionCommand(
        workspace_id=workspace_id,
        collection_id=collection_id,
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=False,
        preview_id=preview_result.preview_id,
    )
    commit_result = (await use_case(commit_cmd)).unwrap()
    assert commit_result.resolved_count == 1
    assert existing_mol in repo.members
    # The critical assertion: resolver was NOT re-invoked on commit.
    assert len(resolver.calls) == 1


@pytest.mark.asyncio
async def test_commit_without_preview_id_falls_back_to_full_resolve():
    """Backwards-compat path — commit without preview_id resolves fresh."""
    existing_mol = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-1": existing_mol}, ambiguous_values=set()
    )
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo(names_by_id={existing_mol: "Phenol"})
    template_repo = FakeTemplateRepo()
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=template_repo,
    )
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=False,
        # No preview_id — full resolve path.
    )
    result = (await use_case(cmd)).unwrap()
    assert result.resolved_count == 1
    assert existing_mol in repo.members
    assert len(resolver.calls) == 1


@pytest.mark.asyncio
async def test_commit_with_stale_preview_id_falls_back():
    """Stale preview_id (random UUID, not in stash) → fall back to fresh resolve."""
    existing_mol = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-1": existing_mol}, ambiguous_values=set()
    )
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo(names_by_id={existing_mol: "Phenol"})
    template_repo = FakeTemplateRepo()
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=template_repo,
    )
    # No preview run — just send a random UUID as preview_id.
    cmd = BulkAddToCollectionCommand(
        workspace_id=uuid.uuid4(),
        collection_id=uuid.uuid4(),
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=False,
        preview_id=uuid.uuid4(),  # Not in stash.
    )
    result = (await use_case(cmd)).unwrap()
    # Fallback path still resolves correctly.
    assert result.resolved_count == 1
    assert existing_mol in repo.members
    assert len(resolver.calls) == 1


@pytest.mark.asyncio
async def test_commit_with_preview_id_from_different_workspace_falls_back():
    """Workspace mismatch in cached preview → fall back to fresh resolve."""
    existing_mol = uuid.uuid4()
    resolver = FakeResolver(
        resolved_map={"CC-1": existing_mol}, ambiguous_values=set()
    )
    repo = FakeCollectionRepo(members=set())
    molecule_repo = FakeMoleculeRepo(names_by_id={existing_mol: "Phenol"})
    template_repo = FakeTemplateRepo()
    use_case = BulkAddToCollection(
        uow=FakeUoW(),
        resolver=resolver,
        repo=repo,
        molecule_repo=molecule_repo,
        template_repo=template_repo,
    )

    # Preview against workspace A.
    workspace_a = uuid.uuid4()
    collection_id = uuid.uuid4()
    preview_cmd = BulkAddToCollectionCommand(
        workspace_id=workspace_a,
        collection_id=collection_id,
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=True,
    )
    preview_result = (await use_case(preview_cmd)).unwrap()
    assert preview_result.preview_id is not None

    # Commit with the same preview_id but a DIFFERENT workspace.
    workspace_b = uuid.uuid4()
    commit_cmd = BulkAddToCollectionCommand(
        workspace_id=workspace_b,
        collection_id=collection_id,
        rows=[BulkAddRow(row_index=0, registration_number="CC-1")],
        dry_run=False,
        preview_id=preview_result.preview_id,
    )
    # Workspace-mismatch should bypass cache and go through the full resolve path.
    # (Both calls to resolver — preview + commit — fired.)
    result = (await use_case(commit_cmd)).unwrap()
    assert result.resolved_count == 1
    assert len(resolver.calls) == 2
