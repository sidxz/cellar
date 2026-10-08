"""Resetting a short label renames protocols: those renames must reach the audit trail."""

import uuid
from dataclasses import dataclass, field

from cellar.application.workspace_config.naming_labels import (
    DeleteNamingLabel,
    DeleteNamingLabelCommand,
)
from cellar.domain.shared.events import DomainEvent
from cellar.domain.shared.protocol_naming import NamingContext
from cellar.domain.workspace_config.naming_label import NamingLabel

WS = uuid.uuid4()
RENAMED = DomainEvent(aggregate_id=uuid.uuid4(), aggregate_type="Protocol", workspace_id=WS)


class _Uow:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def commit(self):
        return [RENAMED]


@dataclass
class _Labels:
    label: NamingLabel
    deleted: list = field(default_factory=list)

    async def find_by_id_in_workspace(self, workspace_id, label_id):
        return self.label

    async def delete(self, workspace_id, label_id):
        self.deleted.append(label_id)


class _Protocols:
    async def find_by_workspace(self, workspace_id, **_):
        return []


class _Names:
    async def context(self, workspace_id):
        return NamingContext()


class _Dispatcher:
    def __init__(self):
        self.events = []

    async def dispatch_all(self, events):
        self.events.extend(events)


@dataclass
class _Auth:
    user_id: uuid.UUID = field(default_factory=uuid.uuid4)
    workspace_id: uuid.UUID = WS
    workspace_role: str = "admin"
    is_admin: bool = True

    def has_role(self, minimum_role):
        return True


async def test_reset_dispatches_the_rename_events():
    label = NamingLabel.create(
        workspace_id=WS, term_id="t", term_label="Mycobacterium tuberculosis",
        ontology_source="NCBITAXON", short_label="Mtb",
    )
    dispatcher = _Dispatcher()
    uc = DeleteNamingLabel(
        _Uow(), _Labels(label), dispatcher, protocol_repo=_Protocols(), names=_Names()
    )
    result = await uc(DeleteNamingLabelCommand(workspace_id=WS, label_id=label.id), auth=_Auth())
    assert result.unwrap() is None
    assert dispatcher.events == [RENAMED]
