"""StartBulkRegistration — dispatch async workflow with sync in-process fallback.

When the orchestrator is reachable: hand the upload to the workflow engine and
return a workflow_id (the Accepted/202 path).

When the orchestrator is unavailable (no Temporal): parse the file in-process
and run ``BulkRegistrationService`` directly (the Created/201 path). This use
case absorbs the branching that previously lived in the route.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor
from cellar.application.chemical_registration.bulk_registration_orchestrator import (
    BulkRegistrationOrchestrator,
    StartBulkRegistrationRequest,
)
from cellar.application.chemical_registration.bulk_registration_service import (
    BulkRegistrationItem,
    BulkRegistrationOutcome,
    BulkRegistrationService,
    StartBulkRegistrationCommand as SyncStartBulkRegistrationCommand,
)
from cellar.application.chemical_registration.preview_bulk_registration_file import (
    BulkFileParserProtocol,
)
from cellar.application.orchestration.workflow_status import (
    WorkflowOrchestratorUnavailable,
)
from cellar.application.shared.command import Command
from cellar.domain.chemical_registration.enums import BulkRegistrationFileFormat
from cellar.domain.shared.errors import DomainError, ValidationError

_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


@dataclass(frozen=True, kw_only=True)
class StartBulkRegistrationFromFileCommand(Command):
    workspace_id: uuid.UUID
    originating_org_id: uuid.UUID
    submitted_by: uuid.UUID
    filename: str
    file_format: str
    content: bytes
    create_batch_on_duplicate: bool | None = None  # None → use workspace default


@dataclass(frozen=True)
class StartBulkRegistrationResult:
    """Tagged result.

    ``mode == "async"``: ``workflow_id`` is set, ``sync_outcome`` is ``None``.
    The route should reply with 202.

    ``mode == "sync"``: ``sync_outcome`` is set, ``workflow_id`` is ``None``.
    The route should reply with 201.
    """

    mode: Literal["async", "sync"]
    workflow_id: str | None = None
    sync_outcome: BulkRegistrationOutcome | None = None


class StartBulkRegistration:
    def __init__(
        self,
        orchestrator: BulkRegistrationOrchestrator,
        sync_service: BulkRegistrationService,
        parser: BulkFileParserProtocol,
    ) -> None:
        self._orchestrator = orchestrator
        self._sync_service = sync_service
        self._parser = parser

    async def __call__(
        self,
        input: StartBulkRegistrationFromFileCommand,
        auth: AuthContext | None = None,
    ) -> Result[StartBulkRegistrationResult, DomainError]:
        require_editor(auth)

        if not input.content:
            return Failure(ValidationError("file is empty"))
        if len(input.content) > _MAX_UPLOAD_BYTES:
            return Failure(
                ValidationError(f"File too large (max {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB)")
            )

        try:
            file_format = BulkRegistrationFileFormat(input.file_format)
        except ValueError:
            return Failure(ValidationError(f"Unsupported file format: {input.file_format!r}"))

        request = StartBulkRegistrationRequest(
            workspace_id=input.workspace_id,
            originating_org_id=input.originating_org_id,
            submitted_by=input.submitted_by,
            filename=input.filename,
            file_format=input.file_format,
            content=input.content,
            create_batch_on_duplicate=input.create_batch_on_duplicate,
        )

        try:
            workflow_id = await self._orchestrator.start(request)
            return Success(StartBulkRegistrationResult(mode="async", workflow_id=workflow_id))
        except WorkflowOrchestratorUnavailable:
            pass  # Fall through to in-process pipeline

        # --- Sync fallback: parse in-process and run BulkRegistrationService ---
        parsed = self._parser.parse(
            content=input.content,
            filename=input.filename,
            file_format=file_format,
        )
        items = [
            BulkRegistrationItem(
                row_index=p.row_index,
                name=p.name,
                smiles=p.smiles,
                molecule_type=p.molecule_type,
                external_ids=p.external_ids,
                error=p.error,
                amount_value=p.amount_value,
                amount_unit=p.amount_unit,
                salt_code=p.salt_code,
                salt_stoichiometry=p.salt_stoichiometry,
                purity=p.purity,
                batch_source=p.batch_source,
                appearance=p.appearance,
            )
            for p in parsed
        ]

        sync_result = await self._sync_service(
            SyncStartBulkRegistrationCommand(
                workspace_id=input.workspace_id,
                source_file=input.filename,
                file_format=input.file_format,
                items=items,
                submitted_by=input.submitted_by,
                originating_org_id=input.originating_org_id,
                create_batch_on_duplicate=input.create_batch_on_duplicate,
            ),
            auth=auth,
        )
        if isinstance(sync_result, Failure):
            return sync_result

        return Success(StartBulkRegistrationResult(mode="sync", sync_outcome=sync_result.unwrap()))
