"""Starting a vault export for a list of molecule names: only the molecules they name."""

from __future__ import annotations

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from cellar.infrastructure.temporal.activities.cdd_fetch import CddFetchActivities
from cellar.infrastructure.temporal.activities.dtos import CddStartExportInput

VAULT_TOTAL = 502375


class _Secrets:
    async def get_secret(self, ref: str) -> str:
        return "test-api-key"


class _Vault:
    """Answers the name lookup with fixed molecules; records lookups and exports."""

    def __init__(self, molecules: list[dict]) -> None:
        self.molecules = molecules
        self.lookups: list[list[str]] = []
        self.exports: list[dict] = []

    async def get_molecule_count(self, vault_id: str, api_key: str) -> int:
        return VAULT_TOTAL

    async def find_molecules_by_names(
        self, vault_id: str, api_key: str, names: list[str]
    ) -> list[dict]:
        self.lookups.append(names)
        return self.molecules

    async def start_molecule_export(self, vault_id: str, api_key: str, **filters) -> int:
        self.exports.append(filters)
        return 77


def _start(vault: _Vault, **filters):
    activities = CddFetchActivities(
        session_factory=None, secret_provider=_Secrets(), cdd_client=vault
    )
    start_input = CddStartExportInput(
        workspace_id="ws", secret_ref="ws:cdd_vault", vault_id="4443", **filters
    )
    return ActivityEnvironment().run(activities.start_molecule_export, start_input)


async def test_names_become_an_export_of_the_molecules_they_name():
    vault = _Vault(
        [
            {"id": 11, "name": "SACC-0001", "synonyms": ["ASA"]},
            {"id": 12, "name": "SACC-0002", "synonyms": []},
            {"id": 13, "name": "SACC-00010", "synonyms": []},  # a looser match by the vault
        ]
    )
    out = await _start(vault, names=["SACC-0001", "asa", "SACC-0002", "SACC-0099"])

    assert vault.lookups == [["SACC-0001", "asa", "SACC-0002", "SACC-0099"]]
    assert [export["molecule_ids"] for export in vault.exports] == [[11, 12]]
    assert out.export_id == 77
    assert out.total_count == 2


@pytest.mark.parametrize("names", [["SACC-0099"], []])
async def test_names_that_match_nothing_fail_for_good_and_export_nothing(names):
    vault = _Vault([])
    with pytest.raises(ApplicationError) as exc_info:
        await _start(vault, names=names)
    assert exc_info.value.non_retryable
    assert vault.exports == []


async def test_without_names_the_whole_vault_is_exported_as_before():
    vault = _Vault([])
    out = await _start(vault)

    assert vault.lookups == []
    assert [export["molecule_ids"] for export in vault.exports] == [None]
    assert out.total_count == VAULT_TOTAL
