"""Polling an external-vault export: keep waiting, save it, or stop for good."""

import asyncio
import json
import time
from pathlib import Path

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from cellar.infrastructure.temporal.activities import cdd_fetch
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


class _SlowVault(_Vault):
    """A finished export whose download takes a while; counts the heartbeats meanwhile."""

    def __init__(self, beats: list) -> None:
        super().__init__("finished")
        self.beats = beats
        self.beats_during_download = 0

    async def stream_export_to_file(
        self, vault_id: str, api_key: str, export_id: int, dest_path: str
    ) -> None:
        before = len(self.beats)
        await asyncio.sleep(0.05)
        self.beats_during_download = len(self.beats) - before
        await super().stream_export_to_file(vault_id, api_key, export_id, dest_path)


def _poll(status: str, vault: _Vault | None = None, beats: list | None = None):
    activities = CddFetchActivities(
        session_factory=None, secret_provider=_Secrets(), cdd_client=vault or _Vault(status)
    )
    poll_input = CddPollExportInput(
        workspace_id="ws", secret_ref="ws:cdd_vault", vault_id="4443", export_id=77
    )
    env = ActivityEnvironment()
    if beats is not None:
        env.on_heartbeat = lambda *details: beats.append(details)
    return env.run(activities.poll_molecule_export, poll_input)


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


async def test_download_keeps_heartbeating(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(cdd_fetch, "_HEARTBEAT_EVERY", 0.01, raising=False)
    beats: list = []
    vault = _SlowVault(beats)
    out = await _poll("finished", vault=vault, beats=beats)
    assert vault.beats_during_download >= 2
    assert out.finished is True
    assert out.count == 2


async def test_parse_keeps_heartbeating_off_the_event_loop(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    monkeypatch.setattr(cdd_fetch, "_HEARTBEAT_EVERY", 0.01, raising=False)
    beats: list = []
    beats_during_parse = 0

    def slow_split(raw_path: Path, export_dir: Path) -> tuple[int, int]:
        nonlocal beats_during_parse
        before = len(beats)
        time.sleep(0.05)  # blocks its thread, the way parsing a huge export does
        beats_during_parse = len(beats) - before
        return 2, 2

    monkeypatch.setattr(cdd_fetch, "_split_export", slow_split, raising=False)
    out = await _poll("finished", beats=beats)
    assert beats_during_parse >= 2
    assert out.count == 2
