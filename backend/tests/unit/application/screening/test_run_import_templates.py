"""Unit tests for RunImportTemplate use cases + scoring helper."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self

import pytest
from returns.result import Failure, Success

from chem_vault.application.screening.run_import_templates import (
    CreateRunImportTemplate,
    CreateRunImportTemplateCommand,
    DeleteRunImportTemplate,
    DeleteRunImportTemplateCommand,
    ListRunImportTemplates,
    ListRunImportTemplatesQuery,
    UpdateRunImportTemplate,
    UpdateRunImportTemplateCommand,
    score_template_against_headers,
)
from chem_vault.domain.screening_assay.run_import_template import RunImportTemplate
from chem_vault.domain.shared.errors import NotFoundError, ValidationError
from chem_vault.domain.shared.events import DomainEvent


class FakeUoW:
    def __init__(self) -> None:
        self.committed = False

    async def commit(self) -> list[DomainEvent]:
        self.committed = True
        return []

    async def rollback(self) -> None:  # pragma: no cover
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        return None


class FakeDispatcher:
    async def dispatch_all(self, events: list[DomainEvent]) -> None:
        return None


class FakeRepo:
    def __init__(self) -> None:
        self.items: dict[uuid.UUID, RunImportTemplate] = {}

    async def find_by_id_in_workspace(
        self, workspace_id: uuid.UUID, id: uuid.UUID
    ) -> RunImportTemplate | None:
        t = self.items.get(id)
        if t is None or t.workspace_id != workspace_id:
            return None
        return t

    async def find_by_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[RunImportTemplate]:
        return [t for t in self.items.values() if t.workspace_id == workspace_id]

    async def save(self, entity: RunImportTemplate) -> None:
        self.items[entity.id] = entity

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        t = self.items.get(id)
        if t and t.workspace_id == workspace_id:
            del self.items[id]


@dataclass
class FakeAuth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_role: str = "editor"
    is_admin: bool = False

    def has_role(self, minimum_role: str) -> bool:
        roles = ["viewer", "editor", "admin"]
        return roles.index(self.workspace_role) >= roles.index(minimum_role)


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


class TestDomain:
    def test_create_validates_name(self) -> None:
        with pytest.raises(ValidationError):
            RunImportTemplate.create(
                workspace_id=uuid.uuid4(),
                name="  ",
                column_mapping={"well": "Well"},
                created_by=uuid.uuid4(),
            )

    def test_create_validates_well_in_mapping(self) -> None:
        with pytest.raises(ValidationError):
            RunImportTemplate.create(
                workspace_id=uuid.uuid4(),
                name="Standard",
                column_mapping={"plate_name": "Plate"},
                created_by=uuid.uuid4(),
            )

    def test_update_changes_fields(self) -> None:
        t = RunImportTemplate.create(
            workspace_id=uuid.uuid4(),
            name="Old",
            column_mapping={"well": "Well"},
            created_by=uuid.uuid4(),
        )
        t.update(name="New", description="desc")
        assert t.name == "New"
        assert t.description == "desc"


# ---------------------------------------------------------------------------
# CRUD use cases
# ---------------------------------------------------------------------------


class TestCRUD:
    @pytest.mark.asyncio
    async def test_create_round_trip(self) -> None:
        auth = FakeAuth()
        repo = FakeRepo()
        uc = CreateRunImportTemplate(FakeUoW(), repo, FakeDispatcher())
        cmd = CreateRunImportTemplateCommand(
            workspace_id=auth.workspace_id,
            name="Standard",
            column_mapping={"well": "Well", "plate_name": "Plate Name"},
            description="d",
            created_by=auth.user_id,
        )
        result = await uc(cmd, auth=auth)
        assert isinstance(result, Success), result
        t = result.unwrap()
        assert repo.items[t.id].name == "Standard"

    @pytest.mark.asyncio
    async def test_list_only_workspace_scope(self) -> None:
        auth = FakeAuth()
        repo = FakeRepo()
        # Seed one in this workspace + one in another
        repo.items[uuid.uuid4()] = RunImportTemplate.create(
            workspace_id=auth.workspace_id,
            name="Mine",
            column_mapping={"well": "Well"},
            created_by=auth.user_id,
        )
        repo.items[uuid.uuid4()] = RunImportTemplate.create(
            workspace_id=uuid.uuid4(),  # different ws
            name="NotMine",
            column_mapping={"well": "Well"},
            created_by=uuid.uuid4(),
        )
        uc = ListRunImportTemplates(FakeUoW(), repo)
        result = await uc(
            ListRunImportTemplatesQuery(workspace_id=auth.workspace_id), auth=auth
        )
        out = result.unwrap()
        assert len(out) == 1
        assert out[0].name == "Mine"

    @pytest.mark.asyncio
    async def test_update_not_found(self) -> None:
        auth = FakeAuth()
        repo = FakeRepo()
        uc = UpdateRunImportTemplate(FakeUoW(), repo, FakeDispatcher())
        result = await uc(
            UpdateRunImportTemplateCommand(
                workspace_id=auth.workspace_id,
                template_id=uuid.uuid4(),
                name="x",
            ),
            auth=auth,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_delete_round_trip(self) -> None:
        auth = FakeAuth()
        repo = FakeRepo()
        existing = RunImportTemplate.create(
            workspace_id=auth.workspace_id,
            name="DropMe",
            column_mapping={"well": "Well"},
            created_by=auth.user_id,
        )
        repo.items[existing.id] = existing

        uc = DeleteRunImportTemplate(FakeUoW(), repo, FakeDispatcher())
        result = await uc(
            DeleteRunImportTemplateCommand(
                workspace_id=auth.workspace_id, template_id=existing.id
            ),
            auth=auth,
        )
        assert isinstance(result, Success)
        assert existing.id not in repo.items


# ---------------------------------------------------------------------------
# Header-match scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def _template(self, mapping: dict) -> RunImportTemplate:
        return RunImportTemplate.create(
            workspace_id=uuid.uuid4(),
            name="t",
            column_mapping=mapping,
            created_by=uuid.uuid4(),
        )

    def test_full_match(self) -> None:
        t = self._template(
            {
                "well": "Well",
                "plate_name": "Plate Name",
                "concentration": "Concentration",
                "batch_ref": "LGCY BATCH NAME",
                "scientist": "Scientist",
                "readout_headers": ["Raw Data"],
            }
        )
        score = score_template_against_headers(
            t,
            ["Plate Name", "Well", "Concentration", "LGCY BATCH NAME", "Raw Data", "Scientist"],
        )
        assert score == 1.0

    def test_partial_match(self) -> None:
        t = self._template(
            {
                "well": "Well",
                "plate_name": "Plate Name",
                "readout_headers": ["Raw Data"],
            }
        )
        # Only well + readout match — plate_name absent.
        score = score_template_against_headers(t, ["Well", "Raw Data"])
        assert 0.5 < score < 1.0

    def test_zero_when_well_missing(self) -> None:
        t = self._template({"well": "Well", "plate_name": "Plate"})
        # File has no Well column → zero.
        score = score_template_against_headers(t, ["Plate", "Other"])
        assert score == 0.0
