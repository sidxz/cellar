"""Resume a failed CDD import from where it stopped, with the settings it started with."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.cdd_import.cdd_molecule_import_orchestrator import (
    ResumeCddMoleculeImportRequest,
)
from cellar.application.cdd_import.get_cdd_molecule_import_status import (
    SyncFailedCddMoleculeImport,
)
from cellar.application.cdd_import.resume_cdd_molecule_import import (
    ResumeCddMoleculeImport,
    ResumeCddMoleculeImportCommand,
)
from cellar.domain.chemical_registration.cdd_molecule_import import CddMoleculeImport
from cellar.domain.chemical_registration.enums import CddImportMode, CddMoleculeImportStatus
from cellar.domain.chemical_registration.events import CddMoleculeImportResumed
from cellar.domain.shared.errors import (
    AuthorizationError,
    ConcurrencyConflictError,
    ValidationError,
)
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()
RESUMER = uuid.uuid4()
SETTINGS = {
    "registration_mapping": [{"header": "name", "target": "name"}],
    "entity_mappings": [{"entity_type": "molecule"}],
    "create_batch_on_duplicate": False,
    "max_molecules": None,
    "secret_ref": f"{WS}:cdd_vault",
}


def _import(*, failed: bool = True, export_id: int | None = 82939461, settings=SETTINGS):
    imp = CddMoleculeImport.create(
        workspace_id=WS,
        cdd_vault_id="4443",
        import_mode=CddImportMode.FULL_VAULT,
        originating_org_id=uuid.uuid4(),
        submitted_by=uuid.uuid4(),
        workflow_id="wf-1",
        run_settings=settings,
    )
    imp.start_discovery()
    imp.complete_discovery(489425, export_id=export_id)
    imp.record_registered(49455)
    imp.record_duplicate(936)
    imp.record_error(359)
    imp.update_offset(50750)
    if failed:
        imp.fail("chunk failed")
    imp.clear_events()
    return imp


class _Repo:
    def __init__(self, *imports: CddMoleculeImport, fail_save_on: int | None = None) -> None:
        self.rows = {i.id: i for i in imports}
        self.saved: list[CddMoleculeImport] = []
        self._fail_save_on = fail_save_on

    async def find_by_id_in_workspace(self, workspace_id, id):
        return self.rows.get(id)

    async def find_by_workspace(self, workspace_id):
        return list(self.rows.values())

    async def save(self, aggregate):
        if self._fail_save_on == len(self.saved) + 1:
            raise ConcurrencyConflictError("CddMoleculeImport", str(aggregate.id))
        self.saved.append(aggregate)


class _UoW:
    def __init__(self, repo: _Repo) -> None:
        self._repo = repo

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def commit(self):
        events = [e for a in self._repo.saved for e in a.collect_events()]
        for a in self._repo.saved:
            a.clear_events()
        return events


class _Orchestrator:
    def __init__(self, raises: Exception | None = None) -> None:
        self.requests: list[ResumeCddMoleculeImportRequest] = []
        self.cancelled: list[str] = []
        self._raises = raises

    async def resume(self, request: ResumeCddMoleculeImportRequest) -> str:
        if self._raises is not None:
            raise self._raises
        self.requests.append(request)
        return "wf-2"

    async def cancel(self, workflow_id: str) -> None:
        self.cancelled.append(workflow_id)


class _Dispatcher:
    def __init__(self) -> None:
        self.events: list = []

    async def dispatch_all(self, events) -> None:
        self.events.extend(events)


def _use_case(repo: _Repo, orchestrator: _Orchestrator, dispatcher: _Dispatcher | None = None):
    return ResumeCddMoleculeImport(
        uow=_UoW(repo),
        repo=repo,
        orchestrator=orchestrator,
        dispatcher=dispatcher or _Dispatcher(),
    )


def _cmd(imp: CddMoleculeImport) -> ResumeCddMoleculeImportCommand:
    return ResumeCddMoleculeImportCommand(workspace_id=WS, import_id=imp.id, resumed_by=RESUMER)


def _auth(role: str = "editor") -> FakeAuth:
    return FakeAuth(role=role, user_id=RESUMER, workspace_id=WS)


async def test_resume_starts_from_the_saved_offset_with_the_runs_settings() -> None:
    imp = _import()
    repo, orch, dispatcher = _Repo(imp), _Orchestrator(), _Dispatcher()

    result = await _use_case(repo, orch, dispatcher)(_cmd(imp), auth=_auth())

    assert isinstance(result, Success)
    assert result.unwrap().workflow_id == "wf-2"
    (request,) = orch.requests
    assert (request.resume_offset, request.cdd_export_id) == (50750, 82939461)
    assert request.run_settings == SETTINGS
    assert (request.registered_count, request.duplicate_count, request.error_count) == (
        49455,
        936,
        359,
    )
    assert (request.total_count, request.submitted_by) == (489425, RESUMER)
    assert (imp.status, imp.workflow_id) == (CddMoleculeImportStatus.PROCESSING, "wf-2")
    assert [type(e) for e in dispatcher.events] == [CddMoleculeImportResumed]


async def test_resume_is_refused_while_another_import_runs() -> None:
    imp, running = _import(), _import(failed=False)
    orch = _Orchestrator()

    result = await _use_case(_Repo(imp, running), orch)(_cmd(imp), auth=_auth())

    assert isinstance(result, Failure)
    assert str(result.failure()) == "Another import is running; resume this one when it ends"
    assert orch.requests == []


@pytest.mark.parametrize(("export_id", "settings"), [(None, SETTINGS), (82939461, None)])
async def test_an_import_without_a_saved_export_is_refused(export_id, settings) -> None:
    imp = _import(export_id=export_id, settings=settings)

    result = await _use_case(_Repo(imp), _Orchestrator())(_cmd(imp), auth=_auth())

    assert isinstance(result, Failure)
    assert str(result.failure()) == (
        "This import can't be resumed: it stopped before its export was saved. Start a new import."
    )


async def test_only_a_failed_import_resumes() -> None:
    imp = _import()
    imp.resume("wf-x", resumed_by=RESUMER)  # running again

    result = await _use_case(_Repo(imp), _Orchestrator())(_cmd(imp), auth=_auth())

    assert isinstance(result, Failure)
    assert str(result.failure()) == "Only a failed import can be resumed"


async def test_viewer_may_not_resume() -> None:
    imp = _import()

    with pytest.raises(AuthorizationError):
        await _use_case(_Repo(imp), _Orchestrator())(_cmd(imp), auth=_auth("viewer"))


async def test_export_gone_from_disk_is_refused_and_the_record_stays_failed() -> None:
    imp = _import()
    gone = ValidationError("The export for this run is no longer on disk. Start a new import.")

    result = await _use_case(_Repo(imp), _Orchestrator(raises=gone))(_cmd(imp), auth=_auth())

    assert isinstance(result, Failure) and result.failure() is gone
    assert imp.status is CddMoleculeImportStatus.FAILED


async def test_a_failed_record_update_cancels_the_started_run() -> None:
    imp = _import()
    orch = _Orchestrator()

    with pytest.raises(ConcurrencyConflictError):
        await _use_case(_Repo(imp, fail_save_on=1), orch)(_cmd(imp), auth=_auth())

    assert orch.cancelled == ["wf-2"]


async def test_a_poll_of_the_old_workflow_leaves_the_resumed_import_alone() -> None:
    imp = _import()
    imp.resume("wf-2", resumed_by=RESUMER)
    repo = _Repo(imp)
    sync = SyncFailedCddMoleculeImport(uow=_UoW(repo), repo=repo)

    await sync.run(WS, str(imp.id), "wf-1")
    assert imp.status is CddMoleculeImportStatus.PROCESSING

    await sync.run(WS, str(imp.id), "wf-2")
    assert imp.status is CddMoleculeImportStatus.FAILED
