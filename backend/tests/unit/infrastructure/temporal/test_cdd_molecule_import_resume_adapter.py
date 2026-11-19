"""The Temporal side of a resume: what the restarted run gets, and when it does not start."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from cellar.application.cdd_import.cdd_molecule_import_orchestrator import (
    ResumeCddMoleculeImportRequest,
)
from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.infrastructure.temporal.orchestrators import cdd_molecule_import as adapter
from cellar.infrastructure.temporal.orchestrators.cdd_molecule_import import (
    TemporalCddMoleculeImportOrchestrator,
    _resume_input,
)

WS, IMP = uuid.uuid4(), uuid.uuid4()
SETTINGS = {
    "registration_mapping": [{"header": "name", "target": "name"}],
    "entity_mappings": [{"entity_type": "molecule"}],
    "create_batch_on_duplicate": True,
    "max_molecules": None,
    "secret_ref": f"{WS}:cdd_vault",
}


def _request() -> ResumeCddMoleculeImportRequest:
    return ResumeCddMoleculeImportRequest(
        workspace_id=WS,
        import_id=IMP,
        cdd_vault_id="4443",
        import_mode="full_vault",
        submitted_by=uuid.uuid4(),
        originating_org_id=uuid.uuid4(),
        filter_criteria=None,
        run_settings=SETTINGS,
        cdd_export_id=82939461,
        resume_offset=50750,
        total_count=489425,
        registered_count=49455,
        duplicate_count=936,
        error_count=359,
        skipped_count=0,
    )


class _Handle:
    def __init__(self, raises: Exception | None) -> None:
        self.reasons: list[str | None] = []
        self._raises = raises

    async def terminate(self, *, reason: str | None = None) -> None:
        if self._raises is not None:
            raise self._raises
        self.reasons.append(reason)


class _Client:
    def __init__(self, raises: Exception | None = None, handle_raises=None) -> None:  # type: ignore[no-untyped-def]
        self.started: list[dict] = []
        self._raises = raises
        self.handles: dict[str, _Handle] = {}
        self._handle_raises = handle_raises

    def get_workflow_handle(self, workflow_id: str) -> _Handle:
        return self.handles.setdefault(workflow_id, _Handle(self._handle_raises))

    async def start_workflow(self, run, arg, *, id: str, task_queue: str):  # type: ignore[no-untyped-def]
        if self._raises is not None:
            raise self._raises
        self.started.append({"arg": arg, "id": id, "task_queue": task_queue})


@pytest.fixture
def export_dir(tmp_path: Path, monkeypatch) -> Path:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(adapter, "cdd_export_dir", lambda export_id: tmp_path / str(export_id))
    path = tmp_path / "82939461"
    path.mkdir()
    return path


def test_resume_input_starts_at_the_saved_chunk_with_the_runs_settings() -> None:
    request = _request()

    run = _resume_input(request, "/data/storage/cdd-exports/82939461")

    assert (run.import_id, run.storage_path) == (str(IMP), "/data/storage/cdd-exports/82939461")
    assert (run.resume_offset, run.resume_chunk_index, run.total_count) == (50750, 203, 489425)
    assert (run.cumulative_registered, run.cumulative_duplicate) == (49455, 936)
    assert (run.cumulative_error, run.cumulative_skipped) == (359, 0)
    assert run.registration_mapping == SETTINGS["registration_mapping"]
    assert run.entity_mappings == SETTINGS["entity_mappings"]
    assert (run.create_batch_on_duplicate, run.secret_ref) == (True, SETTINGS["secret_ref"])
    assert run.submitted_by == str(request.submitted_by)


async def test_resume_starts_the_run_on_the_export_on_disk(export_dir: Path) -> None:
    (export_dir / "manifest.json").write_text('{"count": 489425}')
    client = _Client()

    workflow_id = await TemporalCddMoleculeImportOrchestrator(client).resume(_request())  # type: ignore[arg-type]

    assert workflow_id == f"cdd-mol-import-{WS}-{IMP}-from-50750"
    (started,) = client.started
    assert (started["id"], started["arg"].storage_path) == (workflow_id, str(export_dir))


async def test_resume_without_the_export_on_disk_starts_nothing(export_dir: Path) -> None:
    client = _Client()

    with pytest.raises(ValidationError, match="never finished downloading, or has been removed"):
        await TemporalCddMoleculeImportOrchestrator(client).resume(_request())  # type: ignore[arg-type]

    assert client.started == []


async def test_a_second_resume_of_the_same_run_is_refused(export_dir: Path) -> None:
    (export_dir / "manifest.json").write_text('{"count": 489425}')
    running = WorkflowAlreadyStartedError("cdd-mol-import-x", "CddVaultImportWorkflow")

    with pytest.raises(ConflictError, match="already resuming"):
        await TemporalCddMoleculeImportOrchestrator(_Client(raises=running)).resume(_request())  # type: ignore[arg-type]


async def test_terminate_stops_the_run_at_once() -> None:
    client = _Client()

    await TemporalCddMoleculeImportOrchestrator(client).terminate("wf-1", "Superseded")  # type: ignore[arg-type]

    assert client.handles["wf-1"].reasons == ["Superseded"]


async def test_terminate_leaves_a_run_that_already_ended_alone() -> None:
    ended = RPCError("workflow execution already completed", RPCStatusCode.NOT_FOUND, b"")

    orchestrator = TemporalCddMoleculeImportOrchestrator(_Client(handle_raises=ended))  # type: ignore[arg-type]

    await orchestrator.terminate("wf-1", "x")
