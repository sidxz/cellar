"""Tests for runtime status + cancel use cases (orchestrator-backed).

These exercise the new application-layer composition: orchestrator first,
DB fallback on NotFound, crash-detected status triggers DB sync.
"""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.cdd_import.cancel_cdd_molecule_import import (
    CancelCddMoleculeImport,
    CancelCddMoleculeImportCommand,
)
from cellar.application.cdd_import.cdd_molecule_import_orchestrator import (
    CddMoleculeImportProgress,
)
from cellar.application.cdd_import.get_cdd_molecule_import_runtime_status import (
    GetCddMoleculeImportRuntimeStatus,
    GetCddMoleculeImportRuntimeStatusQuery,
)
from cellar.application.cdd_import.get_cdd_molecule_import_status import (
    CddMoleculeImportStatusResult,
)
from cellar.application.orchestration.workflow_status import (
    WorkflowOrchestratorUnavailable,
)
from cellar.domain.shared.errors import NotFoundError

from tests.fakes.fake_auth import FakeAuth

WORKSPACE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _auth(role: str = "viewer") -> FakeAuth:
    return FakeAuth(role=role, user_id=USER_ID, workspace_id=WORKSPACE_ID)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeOrchestrator:
    def __init__(self, *, progress=None, raise_exc: Exception | None = None) -> None:
        self._progress = progress
        self._raise = raise_exc
        self.cancelled: list[str] = []

    async def start(self, request):  # pragma: no cover - unused here
        raise NotImplementedError

    async def get_progress(self, workflow_id: str) -> CddMoleculeImportProgress:
        if self._raise is not None:
            raise self._raise
        return self._progress

    async def cancel(self, workflow_id: str) -> None:
        if self._raise is not None:
            raise self._raise
        self.cancelled.append(workflow_id)


class _FakeDbStatus:
    """Mimics GetCddMoleculeImportStatusFromDb.__call__."""

    def __init__(self, result) -> None:
        self._result = result

    async def __call__(self, query, auth=None):
        return self._result


class _FakeSyncFailed:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, str]] = []

    async def run(self, workspace_id: uuid.UUID, import_id: str) -> None:
        self.calls.append((workspace_id, import_id))


def _progress(status: str = "processing", import_id: str = "import-1") -> CddMoleculeImportProgress:
    return CddMoleculeImportProgress(
        import_id=import_id,
        status=status,
        total_count=100,
        registered_count=10,
        duplicate_count=0,
        error_count=0,
        skipped_count=0,
        current_offset=10,
        pages_processed=1,
    )


def _db_status_result(status: str = "processing", import_id: str = "import-1"):
    return Success(
        CddMoleculeImportStatusResult(
            import_id=import_id,
            status=status,
            total_count=100,
            registered_count=10,
            duplicate_count=0,
            error_count=0,
            skipped_count=0,
            current_offset=10,
            pages_processed=0,
        )
    )


# ---------------------------------------------------------------------------
# GetCddMoleculeImportRuntimeStatus
# ---------------------------------------------------------------------------


class TestGetCddMoleculeImportRuntimeStatus:
    @pytest.mark.asyncio
    async def test_runtime_success_no_sync(self):
        orch = _FakeOrchestrator(progress=_progress(status="processing"))
        sync_failed = _FakeSyncFailed()
        uc = GetCddMoleculeImportRuntimeStatus(
            orchestrator=orch,
            db_status=_FakeDbStatus(_db_status_result()),
            sync_failed=sync_failed,
        )
        result = await uc(
            GetCddMoleculeImportRuntimeStatusQuery(
                workspace_id=WORKSPACE_ID, workflow_id="cdd-mol-import-x"
            ),
            auth=_auth(),
        )
        assert isinstance(result, Success)
        assert result.unwrap().status == "processing"
        assert sync_failed.calls == []

    @pytest.mark.asyncio
    async def test_runtime_failed_triggers_db_sync(self):
        orch = _FakeOrchestrator(progress=_progress(status="failed", import_id="imp-7"))
        sync_failed = _FakeSyncFailed()
        uc = GetCddMoleculeImportRuntimeStatus(
            orchestrator=orch,
            db_status=_FakeDbStatus(_db_status_result()),
            sync_failed=sync_failed,
        )
        result = await uc(
            GetCddMoleculeImportRuntimeStatusQuery(
                workspace_id=WORKSPACE_ID, workflow_id="cdd-mol-import-x"
            ),
            auth=_auth(),
        )
        assert isinstance(result, Success)
        assert result.unwrap().status == "failed"
        assert sync_failed.calls == [(WORKSPACE_ID, "imp-7")]

    @pytest.mark.asyncio
    async def test_runtime_not_found_falls_back_to_db(self):
        orch = _FakeOrchestrator(raise_exc=NotFoundError("Workflow", "cdd-mol-import-x"))
        sync_failed = _FakeSyncFailed()
        uc = GetCddMoleculeImportRuntimeStatus(
            orchestrator=orch,
            db_status=_FakeDbStatus(_db_status_result(status="completed")),
            sync_failed=sync_failed,
        )
        result = await uc(
            GetCddMoleculeImportRuntimeStatusQuery(
                workspace_id=WORKSPACE_ID, workflow_id="cdd-mol-import-x"
            ),
            auth=_auth(),
        )
        assert isinstance(result, Success)
        assert result.unwrap().status == "completed"
        assert sync_failed.calls == []  # not called on the fallback path

    @pytest.mark.asyncio
    async def test_orchestrator_unavailable_falls_back_to_db(self):
        orch = _FakeOrchestrator(
            raise_exc=WorkflowOrchestratorUnavailable("Temporal down")
        )
        uc = GetCddMoleculeImportRuntimeStatus(
            orchestrator=orch,
            db_status=_FakeDbStatus(_db_status_result(status="processing")),
            sync_failed=_FakeSyncFailed(),
        )
        result = await uc(
            GetCddMoleculeImportRuntimeStatusQuery(
                workspace_id=WORKSPACE_ID, workflow_id="cdd-mol-import-x"
            ),
            auth=_auth(),
        )
        assert isinstance(result, Success)
        assert result.unwrap().status == "processing"

    @pytest.mark.asyncio
    async def test_db_fallback_failure_propagates(self):
        orch = _FakeOrchestrator(raise_exc=NotFoundError("Workflow", "x"))
        uc = GetCddMoleculeImportRuntimeStatus(
            orchestrator=orch,
            db_status=_FakeDbStatus(Failure(NotFoundError("CddMoleculeImport", "x"))),
            sync_failed=_FakeSyncFailed(),
        )
        result = await uc(
            GetCddMoleculeImportRuntimeStatusQuery(
                workspace_id=WORKSPACE_ID, workflow_id="x"
            ),
            auth=_auth(),
        )
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# CancelCddMoleculeImport
# ---------------------------------------------------------------------------


class TestCancelCddMoleculeImport:
    @pytest.mark.asyncio
    async def test_workspace_prefix_mismatch_returns_not_found(self):
        orch = _FakeOrchestrator()
        uc = CancelCddMoleculeImport(orchestrator=orch)

        # workflow_id belongs to a different workspace
        other_workspace = uuid.uuid4()
        result = await uc(
            CancelCddMoleculeImportCommand(
                workspace_id=WORKSPACE_ID,
                workflow_id=f"cdd-mol-import-{other_workspace}-{uuid.uuid4()}",
            ),
            auth=_auth(role="editor"),
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)
        assert orch.cancelled == []

    @pytest.mark.asyncio
    async def test_cancel_dispatches_to_orchestrator(self):
        orch = _FakeOrchestrator()
        uc = CancelCddMoleculeImport(orchestrator=orch)
        wf = f"cdd-mol-import-{WORKSPACE_ID}-{uuid.uuid4()}"
        result = await uc(
            CancelCddMoleculeImportCommand(
                workspace_id=WORKSPACE_ID, workflow_id=wf
            ),
            auth=_auth(role="editor"),
        )
        assert isinstance(result, Success)
        assert orch.cancelled == [wf]
