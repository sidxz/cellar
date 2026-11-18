"""PreviewCddImport: a sample of vault molecules mapped like a run would (mocked client)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from returns.result import Failure

from cellar.application.cdd_import.preview_cdd_import import (
    SAMPLE_SIZE,
    PreviewCddImport,
    PreviewCddImportQuery,
)
from cellar.domain.shared.errors import AuthorizationError, ValidationError
from cellar.domain.workspace_config.data_source import get_default_template
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.cdd_import.test_molecule_mapper_mapping import (
    MAPPING,
    batch,
    molecule,
)
from tests.unit.application.cdd_import.test_use_cases import FakeGetDataSource

WS = uuid.uuid4()
MOL_IDS, BATCH_IDS = get_default_template("cdd_vault")[:2]


class FakeVault:
    def __init__(self, molecules: list[dict[str, Any]]) -> None:
        self.molecules = molecules
        self.sampled: list[tuple[list[int] | None, int]] = []

    async def find_molecules_by_names(self, vault_id, api_key, names):
        wanted = {n.casefold() for n in names}
        return [m for m in self.molecules if m["name"].casefold() in wanted]

    async def sample_molecules(self, vault_id, api_key, molecule_ids, limit):
        self.sampled.append((molecule_ids, limit))
        pool = [m for m in self.molecules if molecule_ids is None or m["id"] in molecule_ids]
        return pool[:limit]


def _uc(vault: FakeVault) -> PreviewCddImport:
    ds = FakeGetDataSource()
    ds._result.unwrap().data_source.entity_mappings = [MOL_IDS, BATCH_IDS]
    ds._result.unwrap().data_source.registration_mapping = MAPPING.to_dict()["columns"]
    return PreviewCddImport(gateway=vault, get_data_source=ds)


def _auth(role: str = "editor") -> FakeAuth:
    return FakeAuth(role=role, user_id=uuid.uuid4(), workspace_id=WS)


@pytest.mark.asyncio
async def test_one_row_per_batch_and_one_for_a_molecule_without() -> None:
    vault = FakeVault(
        [
            molecule(
                1, "SACC-1", "CCO", batches=[batch(10, "SACC-1-001"), batch(11, "SACC-1-002")]
            ),
            molecule(2, "SACC-2", "CCN"),
        ]
    )
    out = (await _uc(vault)(PreviewCddImportQuery(workspace_id=WS), auth=_auth())).unwrap()

    assert [i.name for i in out.items] == ["SACC-1", "SACC-1", "SACC-2"]
    assert [i.row_index for i in out.items] == [0, 1, 2]
    assert out.total_count == 3
    first = out.items[0]
    assert any(b["identifier"] == "SACC-1-001" and b["decides"] for b in first.batch_ids)
    assert out.items[2].batch_ids == []
    assert vault.sampled == [(None, SAMPLE_SIZE)]


@pytest.mark.asyncio
async def test_names_pick_the_sample_and_stored_only_ids_do_not_decide() -> None:
    vault = FakeVault(
        [
            molecule(1, "SACC-1", "CCO"),
            molecule(2, "SACC-2", "CCN", molecule_fields={"Alternate Names": "JSF-1; 51-52-5"}),
        ]
    )
    q = PreviewCddImportQuery(workspace_id=WS, names=["sacc-2"])
    out = (await _uc(vault)(q, auth=_auth())).unwrap()

    assert [i.name for i in out.items] == ["SACC-2"]
    assert vault.sampled == [([2], SAMPLE_SIZE)]
    ids = {e["identifier"]: e.get("decides", True) for e in out.items[0].external_ids}
    assert ids["JSF-1"] is False
    assert ids["2"] is True  # the vault id decides


@pytest.mark.asyncio
async def test_sample_is_capped_at_20() -> None:
    vault = FakeVault([molecule(i, f"M-{i}", "CCO") for i in range(1, 40)])
    out = (await _uc(vault)(PreviewCddImportQuery(workspace_id=WS), auth=_auth())).unwrap()
    assert SAMPLE_SIZE == 20
    assert out.total_count == 20


@pytest.mark.asyncio
async def test_names_matching_nothing_is_a_validation_error() -> None:
    q = PreviewCddImportQuery(workspace_id=WS, names=["nope"])
    result = await _uc(FakeVault([molecule(1, "A", "C")]))(q, auth=_auth())
    assert isinstance(result, Failure) and isinstance(result.failure(), ValidationError)


@pytest.mark.asyncio
async def test_viewer_cannot_preview() -> None:
    with pytest.raises(AuthorizationError):
        await _uc(FakeVault([]))(PreviewCddImportQuery(workspace_id=WS), auth=_auth("viewer"))
