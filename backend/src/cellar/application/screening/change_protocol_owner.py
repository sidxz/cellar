"""Change which Duar org owns a protocol (allowed in any status, even locked)."""

from __future__ import annotations

from cellar.application.shared.change_owner import ChangeOwner
from cellar.domain.screening_assay.protocol import Protocol


class ChangeProtocolOwner(ChangeOwner[Protocol]):
    entity_name = "Protocol"
