"""Setup checklist: what an admin still has to configure before protocols work well."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.application.workspace_config.protocol_form_defaults import missing_default_forms
from cellar.domain.screening_assay.repository import TargetRepository
from cellar.domain.shared.errors import DomainError
from cellar.domain.shared.ontology_search_service import OntologySearchService
from cellar.domain.shared.protocol_naming import DEFAULT_CATEGORY_PATTERNS
from cellar.domain.workspace_config.repository import (
    ProtocolCategoryRepository,
    ProtocolFormRepository,
    WorkspaceSettingsRepository,
)


@dataclass(frozen=True, kw_only=True)
class GetWorkspaceSetupQuery(Query):
    workspace_id: uuid.UUID


@dataclass(frozen=True)
class WorkspaceSetup:
    missing_default_categories: list[str]
    missing_default_forms: int
    bioportal_key: bool  # ontology search can authenticate; presence only, never the value
    home_organisms: int
    targets: int


class GetWorkspaceSetup:
    def __init__(
        self,
        uow: UnitOfWork,
        categories: ProtocolCategoryRepository,
        forms: ProtocolFormRepository,
        ontology: OntologySearchService,
        settings: WorkspaceSettingsRepository,
        targets: TargetRepository,
    ) -> None:
        self._uow = uow
        self._categories = categories
        self._forms = forms
        self._ontology = ontology
        self._settings = settings
        self._targets = targets

    async def __call__(
        self, input: GetWorkspaceSetupQuery, auth: AuthContext | None = None
    ) -> Result[WorkspaceSetup, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        async with self._uow:
            categories = await self._categories.find_by_workspace(ws)
            have = {c.label.lower() for c in categories}
            settings = await self._settings.find_by_workspace_id(ws)
            return Success(
                WorkspaceSetup(
                    missing_default_categories=[
                        label for label in DEFAULT_CATEGORY_PATTERNS if label.lower() not in have
                    ],
                    missing_default_forms=len(
                        missing_default_forms(categories, await self._forms.find_by_workspace(ws))
                    ),
                    bioportal_key=await self._ontology.has_api_key(ws),
                    home_organisms=settings.home_organism_count if settings else 0,
                    targets=await self._targets.count_by_workspace(ws),
                )
            )
