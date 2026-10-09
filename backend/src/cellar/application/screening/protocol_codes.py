"""Protocol codes are minted from the workspace's prefix and width."""

from __future__ import annotations

import uuid

from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


async def mint_protocol_code(
    *,
    settings_repo: WorkspaceSettingsRepository | None,
    protocol_repo: ProtocolRepository,
    workspace_id: uuid.UUID,
) -> str:
    settings = await settings_repo.find_by_workspace_id(workspace_id) if settings_repo else None
    settings = settings or WorkspaceSettings.create_default(workspace_id=workspace_id)
    return await protocol_repo.next_protocol_code(
        workspace_id, prefix=settings.protocol_code_prefix, width=settings.protocol_code_width
    )
