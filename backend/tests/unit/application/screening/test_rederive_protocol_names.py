"""System re-derivation: per-protocol units of work, one retry on a version conflict."""

import uuid

from cellar.application.screening.rederive_protocol_names import (
    RederiveProtocolNames,
    RederiveProtocolNamesCommand,
)
from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import ConcurrencyConflictError
from tests.unit.application.research_organization._helpers import FakeUnitOfWork

WS = uuid.uuid4()


def _protocol() -> Protocol:
    pid = uuid.uuid4()
    p = Protocol.create(
        workspace_id=WS,
        name="Pks13TE Domain inhibition [FP]",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=uuid.uuid4(),
        code="PRT-00001",
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="Signal", data_type=ReadoutDataType.NUMERIC)
        ],
    )
    p.clear_events()
    return p


class _Repo:
    def __init__(self, protocol):
        self.protocol = protocol
        self.saved = 0

    async def find_by_id_in_workspace(self, workspace_id, protocol_id):
        return self.protocol

    async def save(self, protocol):
        self.saved += 1


class _Names:
    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    async def apply(self, protocol, **_):
        self.calls += 1
        if self.calls <= self.failures:
            raise ConcurrencyConflictError("Protocol", str(protocol.id))
        protocol.apply_derived_name(
            name="Pks13 TE domain inhibition [FP]",
            base="Pks13 TE domain inhibition",
            flag=None,
            reason="Registry renamed",
        )


class _Dispatcher:
    async def dispatch_all(self, events):
        return None


def _use_case(protocol, names):
    repo = _Repo(protocol)
    return (
        RederiveProtocolNames(
            uow_factory=FakeUnitOfWork,
            names_factory=lambda _uow: names,
            repo_factory=lambda _uow: repo,
            dispatcher=_Dispatcher(),
        ),
        repo,
    )


async def test_a_version_conflict_is_retried_once():
    p, names = _protocol(), _Names(failures=1)
    uc, _ = _use_case(p, names)
    cmd = RederiveProtocolNamesCommand(workspace_id=WS, protocol_ids=[p.id], reason="Registry renamed")
    report = (await uc(cmd, auth=None)).unwrap()
    assert names.calls == 2 and report.renamed == 1 and report.failed == []


async def test_persistent_conflict_is_reported_not_raised():
    p, names = _protocol(), _Names(failures=99)
    uc, repo = _use_case(p, names)
    cmd = RederiveProtocolNamesCommand(workspace_id=WS, protocol_ids=[p.id], reason="Registry renamed")
    report = (await uc(cmd, auth=None)).unwrap()
    assert report.failed == [str(p.id)] and repo.saved == 0
