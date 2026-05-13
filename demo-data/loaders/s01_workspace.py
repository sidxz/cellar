"""Step 01 — Ensure workspace settings exist."""

from __future__ import annotations

import structlog

from ._context import WORKSPACE_ID, DemoContext
from ._result import unwrap

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.workspace_config.update_workspace_settings import (
        UpdateWorkspaceSettings,
        UpdateWorkspaceSettingsCommand,
    )

    uc = ctx.container[UpdateWorkspaceSettings]
    cmd = UpdateWorkspaceSettingsCommand(workspace_id=WORKSPACE_ID)
    result = await uc(cmd, auth=ctx.auth)
    unwrap(result, "WorkspaceSettings", str(WORKSPACE_ID))
    logger.info("workspace_settings.ensured", workspace_id=str(WORKSPACE_ID))
    return 1
