"""Importing chosen vault molecules over HTTP: who may, and for which workspace."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from returns.result import Success

from cellar.application.cdd_import.check_cdd_molecule_identifiers import (
    CheckCddMoleculeIdentifiers,
)
from cellar.application.cdd_import.registration_mapping import default_cdd_registration_mapping
from cellar.application.cdd_import.start_cdd_molecule_import import StartCddMoleculeImport
from cellar.application.workspace_config.get_data_source_for_import import (
    DataSourceImportConfig,
)
from cellar.interface.dependencies import get_auth
from cellar.interface.error_handlers import register_error_handlers
from cellar.interface.routes.cdd_molecule_import import router
from tests.fakes.fake_auth import FakeAuth

CHECK = "/api/v1/cdd-import/molecules/check"
START = "/api/v1/cdd-import/molecules"


class _DataSource:
    config = {"vault_id": "4443"}
    api_key_name = "cdd"
    entity_mappings: list = []
    registration_mapping = default_cdd_registration_mapping()
    create_batch_on_duplicate = False


class _GetDataSource:
    """Always configured; records which workspace it was asked about."""

    def __init__(self) -> None:
        self.workspaces: list[uuid.UUID] = []

    async def __call__(self, query, auth=None):  # type: ignore[no-untyped-def]
        self.workspaces.append(query.workspace_id)
        return Success(DataSourceImportConfig(data_source=_DataSource(), api_key="key"))


class _Vault:
    """Knows two molecules; records the names it was asked about."""

    def __init__(self) -> None:
        self.asked: list[list[str]] = []

    async def find_molecules_by_names(self, vault_id: str, api_key: str, names: list[str]):
        self.asked.append(names)
        return [
            {"id": 11, "name": "SACC-0001", "synonyms": []},
            {"id": 14, "name": "16:0 CoA", "synonyms": ["Palmitoyl CoA"]},
        ]


class _App:
    def __init__(self, role: str) -> None:
        self.auth = FakeAuth(role=role)
        self.get_data_source = _GetDataSource()
        self.orchestrator = AsyncMock()
        self.orchestrator.start = AsyncMock(return_value="wf-1")
        self.vault = _Vault()
        app = FastAPI()
        register_error_handlers(app)
        app.include_router(router)
        app.dependency_overrides[get_auth] = lambda: self.auth
        app.state.container = {
            CheckCddMoleculeIdentifiers: CheckCddMoleculeIdentifiers(
                gateway=self.vault, get_data_source=self.get_data_source
            ),
            StartCddMoleculeImport: StartCddMoleculeImport(
                get_data_source=self.get_data_source, orchestrator=self.orchestrator
            ),
        }
        self.client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _filtered_body(filter_criteria: dict | None) -> dict:
    return {
        "originating_org_id": str(uuid.uuid4()),
        "import_mode": "filtered",
        "filter_criteria": filter_criteria,
    }


async def test_check_reports_found_and_not_found_in_the_callers_workspace():
    app = _App("editor")
    response = await app.client.post(
        CHECK,
        json={"text": "SACC-0001\nSACC-0099", "workspace_id": str(uuid.uuid4())},
    )

    assert response.status_code == 200
    assert response.json() == {"found": ["SACC-0001"], "not_found": ["SACC-0099"]}
    assert app.get_data_source.workspaces == [app.auth.workspace_id]


async def test_check_parses_the_pasted_text_and_keeps_names_with_spaces_whole():
    app = _App("editor")
    pasted = "SACC-0001\r\n16:0 CoA\r\nPalmitoyl  CoA, sacc-0001;\tAcetyl CoA\r\n"
    response = await app.client.post(CHECK, json={"text": pasted})

    assert response.status_code == 200
    assert app.vault.asked == [["SACC-0001", "16:0 CoA", "Palmitoyl CoA", "Acetyl CoA"]]
    assert response.json() == {
        "found": ["SACC-0001", "16:0 CoA", "Palmitoyl CoA"],
        "not_found": ["Acetyl CoA"],
    }


async def test_viewer_may_not_check():
    app = _App("viewer")
    response = await app.client.post(CHECK, json={"text": "SACC-0001"})

    assert response.status_code == 403
    assert app.get_data_source.workspaces == []


async def test_check_takes_the_pasted_text():
    app = _App("editor")
    for body in ({"identifiers": ["SACC-0001"]}, {"text": ["SACC-0001"]}):
        response = await app.client.post(CHECK, json=body)
        assert response.status_code == 422
    blank = await app.client.post(CHECK, json={"text": " \n ,"})
    assert blank.status_code == 422
    assert app.vault.asked == []


async def test_filtered_import_starts_with_the_names_in_the_callers_workspace():
    app = _App("editor")
    response = await app.client.post(START, json=_filtered_body({"names": ["SACC-0001"]}))

    assert response.status_code == 202
    assert response.json()["workflow_id"] == "wf-1"
    request = app.orchestrator.start.call_args[0][0]
    assert request.workspace_id == app.auth.workspace_id
    assert request.submitted_by == app.auth.user_id
    assert request.import_mode == "filtered"
    assert request.filter_criteria == {"names": ["SACC-0001"]}


async def test_viewer_may_not_start_a_filtered_import():
    app = _App("viewer")
    response = await app.client.post(START, json=_filtered_body({"names": ["SACC-0001"]}))

    assert response.status_code == 403
    app.orchestrator.start.assert_not_called()


async def test_a_filter_without_names_starts_nothing():
    app = _App("editor")
    for filter_criteria in (None, {}, {"names": []}):
        response = await app.client.post(START, json=_filtered_body(filter_criteria))
        assert response.status_code == 422
    app.orchestrator.start.assert_not_called()
