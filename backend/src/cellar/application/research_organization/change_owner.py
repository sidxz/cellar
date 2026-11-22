"""Change which Duar org owns a collection or a project."""

from __future__ import annotations

from cellar.application.shared.change_owner import ChangeOwner
from cellar.domain.research_organization.collection import Collection
from cellar.domain.research_organization.project import Project


class ChangeCollectionOwner(ChangeOwner[Collection]):
    entity_name = "Collection"


class ChangeProjectOwner(ChangeOwner[Project]):
    entity_name = "Project"
