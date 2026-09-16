import uuid
from dataclasses import dataclass

import pytest

from cellar.application.research_organization.collection_import_templates import (
    CreateCollectionImportTemplate,
    CreateCollectionImportTemplateCommand,
    score_template_against_headers,
)
from cellar.domain.research_organization.collection_import_template import (
    CollectionImportTemplate,
)


@dataclass
class FakeRepo:
    items: dict[tuple, CollectionImportTemplate]

    async def save(self, t):
        self.items[(t.workspace_id, t.id)] = t

    async def find_by_id_in_workspace(self, ws, tid):
        return self.items.get((ws, tid))

    async def find_by_workspace(self, ws):
        return [t for (w, _), t in self.items.items() if w == ws]

    async def delete(self, ws, tid):
        self.items.pop((ws, tid), None)


@dataclass
class FakeUoW:
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None
    async def commit(self): return []


@dataclass
class FakeDispatcher:
    async def dispatch_all(self, events): pass


@pytest.mark.asyncio
async def test_create_persists_a_template():
    repo = FakeRepo(items={})
    uc = CreateCollectionImportTemplate(FakeUoW(), repo, FakeDispatcher())
    ws = uuid.uuid4()
    result = await uc(
        CreateCollectionImportTemplateCommand(
            workspace_id=ws,
            name="ACME Q3",
            column_mapping={"registration_number": "Reg No."},
            created_by=uuid.uuid4(),
        )
    )
    tpl = result.unwrap()
    assert tpl.name == "ACME Q3"
    assert len(await repo.find_by_workspace(ws)) == 1


def test_scoring_overlap_threshold():
    tpl = CollectionImportTemplate.create(
        workspace_id=uuid.uuid4(),
        name="t",
        column_mapping={"registration_number": "Reg No.", "name": "Compound"},
        created_by=uuid.uuid4(),
    )
    assert score_template_against_headers(tpl, ["Reg No.", "Compound"]) == 1.0
    assert score_template_against_headers(tpl, ["Reg No.", "Foo"]) == 0.5
    assert score_template_against_headers(tpl, ["X", "Y"]) == 0.0

