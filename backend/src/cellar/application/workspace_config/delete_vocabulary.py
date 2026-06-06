"""DeleteVocabulary command — remove a controlled vocabulary."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError
from cellar.domain.workspace_config.repository import (
    ControlledVocabularyRepository,
    WorkspaceSettingsRepository,
)


@dataclass(frozen=True, kw_only=True)
class DeleteVocabularyCommand(Command):
    workspace_id: uuid.UUID
    vocab_id: uuid.UUID


class DeleteVocabulary:
    def __init__(
        self,
        uow: UnitOfWork,
        repo: ControlledVocabularyRepository,
        settings_repo: WorkspaceSettingsRepository,
        dispatcher: EventDispatcherProtocol,
    ) -> None:
        self._uow = uow
        self._repo = repo
        self._settings_repo = settings_repo
        self._dispatcher = dispatcher

    async def __call__(
        self, input: DeleteVocabularyCommand, auth: AuthContext | None = None
    ) -> Result[None, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)

        async with self._uow:
            vocab = await self._repo.find_by_id_in_workspace(input.workspace_id, input.vocab_id)
            if vocab is None:
                return Failure(NotFoundError("ControlledVocabulary", str(input.vocab_id)))

            if vocab.is_locked:
                return Failure(ValidationError("Cannot delete a locked vocabulary"))

            # Guard: vocabulary must not be referenced by custom field definitions
            settings = await self._settings_repo.find_by_workspace_id(input.workspace_id)
            if settings and settings.custom_field_definitions:
                for field_def in settings.custom_field_definitions:
                    if (
                        isinstance(field_def, dict)
                        and field_def.get("vocabulary_name") == vocab.name
                    ):
                        return Failure(
                            ConflictError(
                                f"Vocabulary '{vocab.name}' is referenced by "
                                f"custom field '{field_def.get('label', field_def.get('name'))}'"
                            )
                        )

            await self._repo.delete(input.workspace_id, input.vocab_id)
            events = await self._uow.commit()

        await self._dispatcher.dispatch_all(events)
        return Success(None)
