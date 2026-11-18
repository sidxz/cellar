"""API: bulk registration column mapping (spec 2026-11-18 §2, §5, §7).

Preview / start with ``column_mapping``, ``/suggest-mapping``, the batch forecast on
``/molecules/preview-registration``, and saved mappings.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from cellar.application.chemical_registration.bulk_registration_orchestrator import (
    BulkRegistrationOrchestrator,
    StartBulkRegistrationRequest,
)
from cellar.infrastructure.temporal.orchestrators.bulk_registration import (
    NullBulkRegistrationOrchestrator,
)
from tests.api.conftest import _create_test_app
from tests.fakes.fake_auth import FakeAuth

SMILES = "CCCCCCCCCCCCCCCCCCCCCCO"
MAPPING = {
    "columns": [
        {"header": "Molecule Name", "target": "name"},
        {"header": "SMILES", "target": "smiles"},
        {"header": "Synonyms", "target": "compound_id", "source": "Synonyms"},
        {"header": "Batch Molecule-Batch ID", "target": "batch_id", "source": "CDD batch ID"},
        {"header": "LGCY Batch Name", "target": "batch_id", "source": "CDD legacy batch ID"},
        {"header": "Batch Name", "target": "ignore"},
    ]
}
CSV = (
    "Molecule Name,SMILES,Synonyms,Batch Molecule-Batch ID,LGCY Batch Name,Batch Name\n"
    f"API-0001,{SMILES},JX-1,API-0001-001,LG-0001-001K001,001\n"
    f"API-0001,{SMILES},,API-0001-002,LG-0001-002K001,002\n"
    ",,,,,\n"
).encode()


async def _app_client(
    database_url: str, auth: FakeAuth, orchestrator: object
) -> AsyncIterator[AsyncClient]:
    app = _create_test_app(
        database_url, auth, overrides={BulkRegistrationOrchestrator: orchestrator}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore[arg-type]
        yield ac
    await app.state.container[AsyncEngine].dispose()


@pytest.fixture
async def client(
    database_url: str, _run_migrations: None, fake_auth: FakeAuth
) -> AsyncIterator[AsyncClient]:
    """Admin client; bulk uploads take the in-process path (no Temporal)."""
    async for ac in _app_client(database_url, fake_auth, NullBulkRegistrationOrchestrator()):
        yield ac


class _RecordingOrchestrator:
    """Temporal is up: the upload is handed to a workflow."""

    def __init__(self) -> None:
        self.started: list[StartBulkRegistrationRequest] = []

    async def start(self, request: StartBulkRegistrationRequest) -> str:
        self.started.append(request)
        return f"bulk-reg-{request.workspace_id}-{uuid.uuid4()}"

    async def get_progress(self, workflow_id: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError


@pytest.fixture
def orchestrator() -> _RecordingOrchestrator:
    return _RecordingOrchestrator()


@pytest.fixture
async def async_client(
    database_url: str,
    _run_migrations: None,
    fake_auth: FakeAuth,
    orchestrator: _RecordingOrchestrator,
) -> AsyncIterator[AsyncClient]:
    async for ac in _app_client(database_url, fake_auth, orchestrator):
        yield ac


async def _org(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/organizations",
        json={"name": f"MapOrg-{uuid.uuid4().hex[:6]}", "org_type": "internal"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _preview(client: AsyncClient, content: bytes, mapping: object | None):  # type: ignore[no-untyped-def]
    data = {} if mapping is None else {"column_mapping": _form_value(mapping)}
    return await client.post(
        "/api/v1/bulk-registrations/preview",
        files={"file": ("export.csv", content, "text/csv")},
        data=data,
    )


def _form_value(mapping: object) -> str:
    return mapping if isinstance(mapping, str) else json.dumps(mapping)


# ---------------------------------------------------------------------------
# POST /bulk-registrations/preview
# ---------------------------------------------------------------------------


async def test_preview_with_mapping_returns_file_row_and_batch_ids(client: AsyncClient) -> None:
    resp = await _preview(client, CSV, MAPPING)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"]
    assert [i["file_row"] for i in items] == [2, 3, 4]
    assert items[0]["batch_ids"] == [
        {
            "identifier": "API-0001-001",
            "source": "CDD batch ID",
            "identifier_type": None,
            "decides": True,
        },
        {
            "identifier": "LG-0001-001K001",
            "source": "CDD legacy batch ID",
            "identifier_type": None,
            "decides": True,
        },
    ]
    assert items[0]["external_ids"] == [
        {"identifier": "JX-1", "identifier_type": "custom", "source": "Synonyms"}
    ]
    assert items[1]["external_ids"] == []
    assert items[2]["error"] == "Row 4: no name or structure"
    assert (body["total_count"], body["error_count"]) == (3, 1)


async def test_preview_without_mapping_reads_todays_headers(client: AsyncClient) -> None:
    resp = await _preview(client, b"name,smiles,cas\nA-1,CCO,64-17-5\n", None)

    assert resp.status_code == 200, resp.text
    (item,) = resp.json()["items"]
    assert (item["file_row"], item["name"], item["batch_ids"]) == (2, "A-1", [])
    assert item["external_ids"] == [
        {
            "identifier": "64-17-5",
            "identifier_type": "cas_number",
            "source": None,
            "decides": True,
        }
    ]


_NAME = {"header": "Molecule Name", "target": "name"}
INVALID_MAPPINGS = [
    pytest.param("{not json", ["column_mapping"], id="bad-json"),
    pytest.param(
        {"columns": [_NAME, {"header": "Weird Column", "target": "nope"}]},
        ["'Weird Column'"],
        id="unknown-target",
    ),
    pytest.param(
        {"columns": [_NAME, {"header": "Lot Number", "target": "batch_id", "source": "Lot"}]},
        ["'Lot Number'"],
        id="header-not-in-file",
    ),
    pytest.param(
        {"columns": [_NAME, {"header": "Synonyms", "target": "name"}]},
        ["'Molecule Name'", "'Synonyms'"],
        id="single-target-twice",
    ),
    pytest.param(
        {"columns": [_NAME, {"header": "LGCY Batch Name", "target": "batch_id"}]},
        ["'LGCY Batch Name'"],
        id="no-source",
    ),
    pytest.param(
        {"columns": [{"header": "Synonyms", "target": "compound_id", "source": "Syn"}]},
        ["compound name or the structure"],
        id="no-name-or-structure",
    ),
]


@pytest.mark.parametrize(("mapping", "named"), INVALID_MAPPINGS)
async def test_preview_invalid_mapping_is_422_naming_the_column(
    client: AsyncClient, mapping: object, named: list[str]
) -> None:
    """Review Focus 5: a 422 with a sentence naming the column, never a 500."""
    resp = await _preview(client, CSV, mapping)

    assert resp.status_code == 422, resp.text
    message = resp.json()["message"]
    assert all(n in message for n in named), message


# ---------------------------------------------------------------------------
# POST /bulk-registrations
# ---------------------------------------------------------------------------


async def test_start_hands_the_mapping_to_the_workflow(
    async_client: AsyncClient, orchestrator: _RecordingOrchestrator
) -> None:
    resp = await async_client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("export.csv", CSV, "text/csv")},
        data={
            "originating_org_id": await _org(async_client),
            "file_format": "csv",
            "column_mapping": json.dumps(MAPPING),
        },
    )

    assert resp.status_code == 202, resp.text
    (request,) = orchestrator.started
    assert request.column_mapping == {
        "columns": [{"source": None, "separator": None, **c} for c in MAPPING["columns"]]
    }


@pytest.mark.parametrize(
    ("mapping", "named"),
    [p for p in INVALID_MAPPINGS if p.id in ("header-not-in-file", "single-target-twice")],
)
async def test_start_invalid_mapping_is_422_before_a_workflow_starts(
    async_client: AsyncClient,
    orchestrator: _RecordingOrchestrator,
    mapping: object,
    named: list[str],
) -> None:
    """Review Focus 5 on the start upload: with Temporal up, a mapping that does not
    fit the file must be refused here, not fail later inside the workflow."""
    resp = await async_client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("export.csv", CSV, "text/csv")},
        data={
            "originating_org_id": await _org(async_client),
            "file_format": "csv",
            "column_mapping": _form_value(mapping),
        },
    )

    assert resp.status_code == 422, resp.text
    assert all(n in resp.json()["message"] for n in named)
    assert orchestrator.started == []


async def test_start_in_process_with_invalid_mapping_is_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("export.csv", CSV, "text/csv")},
        data={
            "originating_org_id": await _org(client),
            "file_format": "csv",
            "column_mapping": json.dumps(
                {"columns": [_NAME, {"header": "Lot Number", "target": "batch_id", "source": "L"}]}
            ),
        },
    )
    assert resp.status_code == 422, resp.text
    assert "'Lot Number'" in resp.json()["message"]


# ---------------------------------------------------------------------------
# POST /bulk-registrations/suggest-mapping
# ---------------------------------------------------------------------------


async def test_suggest_mapping(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/bulk-registrations/suggest-mapping",
        json={"headers": ["Molecule Name", "SMILES", "Synonyms", "Lot ID", "LGCY Batch Name"]},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "columns": [
            {"header": "Molecule Name", "target": "name", "source": None, "separator": None},
            {"header": "SMILES", "target": "smiles", "source": None, "separator": None},
            {
                "header": "Synonyms",
                "target": "compound_id",
                "source": "Synonyms",
                "separator": None,
            },
            {"header": "Lot ID", "target": "batch_id", "source": "Lot ID", "separator": None},
            {"header": "LGCY Batch Name", "target": "ignore", "source": None, "separator": None},
        ]
    }


# ---------------------------------------------------------------------------
# POST /molecules/preview-registration — batch forecast
# ---------------------------------------------------------------------------


async def test_preview_registration_forecasts_batches(client: AsyncClient) -> None:
    started = await client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("export.csv", CSV, "text/csv")},
        data={
            "originating_org_id": await _org(client),
            "file_format": "csv",
            "column_mapping": json.dumps(MAPPING),
        },
    )
    assert started.status_code == 200, started.text  # in-process path
    rows = started.json()["items"]
    assert [r["success"] for r in rows] == [True, True, False]
    batch_001 = rows[0]["batch_number"]

    resp = await client.post(
        "/api/v1/molecules/preview-registration",
        json={
            "items": [
                {"name": "API-0001", "smiles": SMILES, "batch_ids": ["LG-0001-001K001"]},
                {"name": "API-0001", "smiles": SMILES, "batch_ids": ["API-0001-003"]},
                {"name": "API-NEW", "smiles": SMILES + "C", "batch_ids": ["API-0001-002"]},
                {
                    "name": "API-0001",
                    "smiles": SMILES,
                    "batch_ids": ["API-0001-001", "API-0001-002"],
                },
                {"name": "API-0001", "smiles": SMILES},  # today's body
                {
                    "name": "UNDISC-1",
                    "smiles": None,
                    "external_ids": [{"identifier": "JX-9", "identifier_type": "custom"}],
                    "batch_ids": ["U-1"],
                },
            ]
        },
    )

    assert resp.status_code == 200, resp.text
    existing, new, other, split, old, undisclosed = resp.json()["items"]
    assert existing["action"] == "deduplicated"
    assert (existing["batch_action"], existing["matched_batch_number"]) == ("existing", batch_001)
    assert existing["batch_problem"] is None
    assert (new["batch_action"], new["matched_batch_number"]) == ("new", None)
    # A new batch for a compound already in ChemCellar says how many batches it has.
    api_0001_batches = {
        r["batch_id"] for r in rows[:2] if r["molecule_id"] == rows[0]["molecule_id"]
    }
    assert new["existing_batch_count"] == len(api_0001_batches)
    assert undisclosed["existing_batch_count"] is None
    assert other["action"] == "registered"
    assert other["batch_action"] == "problem"
    assert "API-0001-002 already belongs to" in other["batch_problem"]
    assert other["batch_problem"].endswith("(another compound)")
    assert split["batch_action"] == "problem"
    assert (
        "API-0001-001 and API-0001-002 belong to two different batches" in split["batch_problem"]
    )
    # Rows of one compound share a key; a different structure has another one.
    assert len(existing["compound_key"]) == 27  # InChIKey
    assert new["compound_key"] == existing["compound_key"] == old["compound_key"]
    assert other["compound_key"] != existing["compound_key"]
    assert undisclosed["compound_key"] == "ids:JX-9|UNDISC-1"
    assert undisclosed["batch_action"] == "new"


async def test_preview_registration_without_batch_ids_has_no_batch_forecast(
    client: AsyncClient,
) -> None:
    """daikon's body: no ``batch_ids`` → the batch fields stay empty."""
    resp = await client.post(
        "/api/v1/molecules/preview-registration",
        json={"items": [{"name": "OLD-1", "smiles": "CCCCCCCCCCCCCCCCCCCCCCCN"}]},
    )

    assert resp.status_code == 200, resp.text
    (item,) = resp.json()["items"]
    assert item["action"] == "registered"
    assert (item["batch_action"], item["matched_batch_number"], item["batch_problem"]) == (
        None,
        None,
        None,
    )
    assert item["warnings"] == []


async def test_preview_registration_stored_only_ids_held_elsewhere_warn_not_conflict(
    client: AsyncClient,
) -> None:
    """Stored-only IDs (CDD mapper spec §3a) never match or conflict; one another
    compound or batch holds is forecast as a warning."""
    smiles = "CCCCCCCCCCCCCCCCCCCCCCCCO"
    csv = (
        "Molecule Name,SMILES,Synonyms,Batch Molecule-Batch ID,LGCY Batch Name,Batch Name\n"
        f"SO-0001,{smiles},SO-SYN-1,SO-0001-001,SO-LG-1,001\n"
        f"SO-0001,{smiles},,SO-0001-002,SO-LG-2,002\n"
    ).encode()
    started = await client.post(
        "/api/v1/bulk-registrations",
        files={"file": ("export.csv", csv, "text/csv")},
        data={
            "originating_org_id": await _org(client),
            "file_format": "csv",
            "column_mapping": json.dumps(MAPPING),
        },
    )
    assert started.status_code == 200, started.text
    rows = started.json()["items"]
    reg = (await client.get(f"/api/v1/molecules/{rows[0]['molecule_id']}")).json()[
        "registration_number"
    ]
    number_001, number_002 = rows[0]["batch_number"], rows[1]["batch_number"]

    resp = await client.post(
        "/api/v1/molecules/preview-registration",
        json={
            "items": [
                {"name": "SO-NEW", "smiles": smiles + "C", "stored_only_ids": ["SO-SYN-1"]},
                {
                    "name": "SO-NEW",
                    "smiles": smiles + "C",
                    "external_ids": [{"identifier": "SO-SYN-1", "identifier_type": "custom"}],
                },
                {
                    "name": "SO-0001",
                    "smiles": smiles,
                    "batch_ids": ["SO-0001-001"],
                    "stored_only_batch_ids": ["SO-LG-2"],
                },
                {"name": "SO-0001", "smiles": smiles, "batch_ids": ["SO-0001-001", "SO-LG-2"]},
            ]
        },
    )

    assert resp.status_code == 200, resp.text
    stored_only, deciding, batch_stored_only, batch_deciding = resp.json()["items"]
    assert stored_only["action"] == "registered"
    assert stored_only["warnings"] == [
        f"'SO-SYN-1' is already an ID of {reg}; not stored on SO-NEW"
    ]
    assert deciding["action"] == "conflict"  # the same ID as a deciding one
    assert batch_stored_only["action"] == "deduplicated"
    assert (batch_stored_only["batch_action"], batch_stored_only["matched_batch_number"]) == (
        "existing",
        number_001,
    )
    assert batch_stored_only["batch_problem"] is None
    assert batch_stored_only["warnings"] == [
        f"'SO-LG-2' is already an ID of batch {number_002}; not stored on {number_001}"
    ]
    assert batch_deciding["batch_action"] == "problem"


# ---------------------------------------------------------------------------
# /bulk-registration-mappings
# ---------------------------------------------------------------------------

MAPPINGS = "/api/v1/bulk-registration-mappings"


@pytest.fixture
async def other_workspace_client(
    database_url: str, _run_migrations: None
) -> AsyncIterator[AsyncClient]:
    auth = FakeAuth(role="admin", workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    async for ac in _app_client(database_url, auth, NullBulkRegistrationOrchestrator()):
        yield ac


async def test_saved_mapping_crud(client: AsyncClient, user_id: uuid.UUID) -> None:
    created = await client.post(MAPPINGS, json={"name": "CDD export", **MAPPING})
    assert created.status_code == 201, created.text
    saved = created.json()
    assert saved["name"] == "CDD export"
    assert saved["created_by"] == str(user_id)
    assert saved["columns"] == [
        {"source": None, "separator": None, **c} for c in MAPPING["columns"]
    ]

    listed = await client.get(MAPPINGS)
    assert [m["id"] for m in listed.json()] == [saved["id"]]

    renamed = await client.patch(
        f"{MAPPINGS}/{saved['id']}",
        json={"name": "CDD export v2", "columns": MAPPING["columns"][:2]},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "CDD export v2"
    assert [c["header"] for c in renamed.json()["columns"]] == ["Molecule Name", "SMILES"]

    assert (await client.delete(f"{MAPPINGS}/{saved['id']}")).status_code == 204
    assert (await client.get(MAPPINGS)).json() == []
    assert (await client.delete(f"{MAPPINGS}/{saved['id']}")).status_code == 404


async def test_saved_mapping_duplicate_name_is_409(client: AsyncClient) -> None:
    first = await client.post(MAPPINGS, json={"name": "CDD export", **MAPPING})
    assert first.status_code == 201, first.text
    other = await client.post(MAPPINGS, json={"name": "Plate vendor", **MAPPING})
    assert other.status_code == 201, other.text

    assert (await client.post(MAPPINGS, json={"name": "cdd EXPORT", **MAPPING})).status_code == 409
    renamed = await client.patch(f"{MAPPINGS}/{other.json()['id']}", json={"name": "CDD export"})
    assert renamed.status_code == 409, renamed.text


async def test_saved_mapping_columns_are_validated(client: AsyncClient) -> None:
    twice = {"columns": [_NAME, {"header": "Title", "target": "name"}]}
    resp = await client.post(MAPPINGS, json={"name": "Bad", **twice})
    assert resp.status_code == 422, resp.text
    assert "'Molecule Name'" in resp.json()["message"]


async def test_saved_mappings_are_scoped_to_the_workspace(
    client: AsyncClient, other_workspace_client: AsyncClient
) -> None:
    saved = (await client.post(MAPPINGS, json={"name": "CDD export", **MAPPING})).json()

    assert (await other_workspace_client.get(MAPPINGS)).json() == []
    patched = await other_workspace_client.patch(f"{MAPPINGS}/{saved['id']}", json={"name": "X"})
    assert patched.status_code == 404
    assert (await other_workspace_client.delete(f"{MAPPINGS}/{saved['id']}")).status_code == 404
    # Names are unique per workspace only.
    same_name = await other_workspace_client.post(MAPPINGS, json={"name": "CDD export", **MAPPING})
    assert same_name.status_code == 201, same_name.text
    assert [m["name"] for m in (await client.get(MAPPINGS)).json()] == ["CDD export"]


async def test_viewer_lists_but_cannot_save_mappings(viewer_client: AsyncClient) -> None:
    assert (await viewer_client.get(MAPPINGS)).status_code == 200
    assert (await viewer_client.post(MAPPINGS, json={"name": "V", **MAPPING})).status_code == 403
