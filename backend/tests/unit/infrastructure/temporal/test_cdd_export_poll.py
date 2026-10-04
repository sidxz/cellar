"""Polling an external-vault export: keep waiting, save it, or stop for good."""

import json
from pathlib import Path

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from cellar.infrastructure.temporal.activities.cdd_fetch import CddFetchActivities
from cellar.infrastructure.temporal.activities.dtos import CddPollExportInput

EXPORT = {"count": 2, "objects": [{"id": 1, "class": "plate"}, {"id": 2, "class": "plate"}]}


class _Secrets:
    async def get_secret(self, ref: str) -> str:
        return "test-api-key"


class _Vault:
    """Reports a fixed export status; downloading writes a small finished export."""

    def __init__(self, status: str) -> None:
        self.status = status

    async def check_export_progress(self, vault_id: str, api_key: str, export_id: int) -> str:
        return self.status

    async def stream_export_to_file(
        self, vault_id: str, api_key: str, export_id: int, dest_path: str
    ) -> None:
        Path(dest_path).write_text(json.dumps(EXPORT))


def _poll(status: str):
    activities = CddFetchActivities(
        session_factory=None, secret_provider=_Secrets(), cdd_client=_Vault(status)
    )
    poll_input = CddPollExportInput(
        workspace_id="ws", secret_ref="ws:cdd_vault", vault_id="4443", export_id=77
    )
    return ActivityEnvironment().run(activities.poll_molecule_export, poll_input)


@pytest.mark.parametrize("status", ["new", "started"])
async def test_running_export_keeps_polling(status):
    out = await _poll(status)
    assert out.finished is False


@pytest.mark.parametrize("status", ["finished", "downloaded"])
async def test_ready_export_is_saved_as_chunks(status, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    out = await _poll(status)
    assert out.finished is True
    assert out.count == 2
    export_dir = tmp_path / "cdd-exports" / "77"
    assert Path(out.storage_path) == export_dir
    assert json.loads((export_dir / "chunk_000000.json").read_text()) == EXPORT["objects"]


@pytest.mark.parametrize("status", ["failed", "canceled"])
async def test_dead_export_fails_without_retrying(status, monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    with pytest.raises(ApplicationError) as exc_info:
        await _poll(status)
    assert exc_info.value.non_retryable
    assert status in str(exc_info.value)
