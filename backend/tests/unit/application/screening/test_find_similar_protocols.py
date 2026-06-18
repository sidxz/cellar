from __future__ import annotations

import uuid

import pytest
from returns.result import Success

from cellar.application.screening.find_similar_protocols import (
    FindSimilarProtocols,
    FindSimilarProtocolsQuery,
)
from cellar.domain.screening_assay.protocol_similarity import ProtocolSimilarityMatch
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.errors import NotFoundError
from tests.fakes.fake_auth import FakeAuth

WS = uuid.uuid4()


class _FakeUoW:
    async def __aenter__(self) -> "_FakeUoW":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeRepo:
    def __init__(self, matches: list[ProtocolSimilarityMatch], targets: dict) -> None:
        self._matches = matches
        self._targets = targets
        self.call: dict | None = None

    async def find_similar(self, workspace_id, *, name, protocol_type, target_ids, readout_names, name_floor=0.3, limit=5):
        self.call = {"name": name, "target_ids": list(target_ids), "readout_names": list(readout_names)}
        return self._matches

    async def find_effective_targets_for_protocols(self, workspace_id, protocol_ids):
        return {pid: self._targets.get(pid, []) for pid in protocol_ids}


@pytest.fixture
def match() -> ProtocolSimilarityMatch:
    return ProtocolSimilarityMatch(
        protocol_id=uuid.uuid4(), name="RNAP core IC50", protocol_type="biochemical",
        status="active", score=0.82, is_run_candidate=True,
        shared_target_ids=[], shared_readout_kinds=["ic50"],
    )


async def test_returns_matches_with_targets(match: ProtocolSimilarityMatch) -> None:
    tref = TargetRef(id=uuid.uuid4(), name="RNAP", target_type="protein")
    repo = _FakeRepo([match], {match.protocol_id: [tref]})
    uc = FindSimilarProtocols(_FakeUoW(), repo)
    result = await uc(
        FindSimilarProtocolsQuery(workspace_id=WS, name="RNAP core IC50 GSK", readout_names=["IC50"]),
        auth=FakeAuth(role="viewer", workspace_id=WS),
    )
    assert isinstance(result, Success)
    items = result.unwrap()
    assert len(items) == 1
    assert items[0].match.name == "RNAP core IC50"
    assert items[0].targets[0].name == "RNAP"


async def test_blank_name_short_circuits(match: ProtocolSimilarityMatch) -> None:
    repo = _FakeRepo([match], {})
    uc = FindSimilarProtocols(_FakeUoW(), repo)
    result = await uc(
        FindSimilarProtocolsQuery(workspace_id=WS, name="   "),
        auth=FakeAuth(role="viewer", workspace_id=WS),
    )
    assert result.unwrap() == []
    assert repo.call is None  # repo never queried


async def test_rejects_cross_workspace() -> None:
    repo = _FakeRepo([], {})
    uc = FindSimilarProtocols(_FakeUoW(), repo)
    with pytest.raises(NotFoundError):
        await uc(
            FindSimilarProtocolsQuery(workspace_id=uuid.uuid4(), name="x"),
            auth=FakeAuth(role="viewer", workspace_id=WS),
        )
