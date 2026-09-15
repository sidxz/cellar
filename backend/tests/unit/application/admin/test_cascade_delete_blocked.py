"""CascadeDelete turns a blocked plan into the Tier-1 refusal: a 409 naming every blocker."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from returns.result import Failure

from cellar.application.admin.admin_delete_registry import register_admin_delete
from cellar.application.admin.admin_hard_delete import BlockedByDependenciesError
from cellar.application.admin.cascade_delete import CascadeDelete, CascadeDeleteCommand
from cellar.application.admin.cascade_service import CascadeBlockedError, InboundReference


class _UoW:
    session = MagicMock()

    async def __aenter__(self) -> _UoW:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def commit(self) -> list:
        raise AssertionError("a refused delete must not commit")


async def test_a_blocked_plan_becomes_a_conflict_naming_every_blocker() -> None:
    register_admin_delete(entity_type="protocol", table="protocols", label_field="name")
    blocker = InboundReference(
        table="campaign",
        fk_column="campaign_channel.protocol_id, campaign_channel.readout_definition_id",
        entity_type="campaign",
        count=2,
        display_label="Campaigns with a channel on this protocol",
    )
    service = MagicMock()
    service.fetch_typed_name_label = AsyncMock(return_value="Kinase assay")
    service.execute = AsyncMock(side_effect=CascadeBlockedError([blocker]))
    audit = MagicMock()
    audit.record = AsyncMock()
    auth = MagicMock(workspace_id=uuid.uuid4(), user_id=uuid.uuid4(), workspace_role="admin")
    auth.is_admin = True
    auth.has_role = lambda role: True

    with patch("cellar.application.admin.cascade_delete.TIER2_ENTITY_TYPES", new={"protocol"}):
        result = await CascadeDelete(uow=_UoW(), audit=audit, cascade_service=service)(
            CascadeDeleteCommand(
                workspace_id=auth.workspace_id,
                entity_type="protocol",
                entity_id=uuid.uuid4(),
                typed_name="Kinase assay",
                reason="duplicate registration",
            ),
            auth=auth,
        )

    assert isinstance(result, Failure)
    error = result.failure()
    assert isinstance(error, BlockedByDependenciesError)
    assert error.body_extras()["blockers"][0]["display_label"] == (
        "Campaigns with a channel on this protocol"
    )
    audit.record.assert_not_called()
