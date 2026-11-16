"""SavedVisualization aggregate — a named workbench view: what it shows and how it looks.

A view stores how to look, never data: ``source`` names protocols/runs by id, ``config`` holds
plots, filters and the labels of the columns they use. No row ids, no values.
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from types import EllipsisType
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from cellar.domain.research_organization.enums import SearchVisibility
from cellar.domain.research_organization.events import (
    SavedVisualizationCreated,
    SavedVisualizationDeleted,
    SavedVisualizationUpdated,
)
from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import StaleEditError, ValidationError

VIEW_CONFIG_VERSION = 2
MAX_VIEW_CONFIG_BYTES = 65_536
MAX_NAME_LENGTH = 255
MAX_DESCRIPTION_LENGTH = 2_000
STALE_VIEW_MESSAGE = (
    "This view changed since you opened it. Reload it, or save your version as a new view."
)


class ViewPanel(BaseModel):
    """A plot; its settings beyond id and type pass through untouched. The types are the
    workbench's own (its panel schema), one for one."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=64)
    type: Literal["scatter", "histogram", "bar", "box", "rgroup-matrix"]


class ViewFilter(BaseModel):
    """A range or category filter on a column."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=64)
    kind: Literal["range", "category"]
    key: str = Field(min_length=1, max_length=256)


class ViewSubstructureFilter(BaseModel):
    """A substructure query. Its matches are data, so a view keeps the query alone and the
    workbench matches it again on open."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    kind: Literal["substructure"]
    query: str = Field(min_length=1)
    queryKind: Literal["smiles", "smarts"]


class ViewRGroups(BaseModel):
    """R-group columns: a decomposition of the dataset's compounds on a core."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^rg[0-9]{1,6}$")
    kind: Literal["rgroups"]
    coreSmiles: str = Field(min_length=1, max_length=2_000)
    name: str = Field(min_length=1, max_length=60)


class ViewClusters(BaseModel):
    """Cluster columns: Butina clusters at a similarity threshold."""

    model_config = ConfigDict(extra="forbid")

    id: Literal["clusters"]
    kind: Literal["clusters"]
    threshold: float = Field(ge=0.05, le=0.95)


class ViewSeriesMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    scaffold: str | None = Field(default=None, min_length=1, max_length=2_000)
    rgroupsId: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _one_source(self) -> ViewSeriesMember:
        if (self.scaffold is None) == (self.rgroupsId is None):
            raise ValueError("a series member needs either a scaffold or an R-groups core")
        return self


class ViewSeries(BaseModel):
    """A Series column: compounds under a scaffold or matching an R-groups core."""

    model_config = ConfigDict(extra="forbid")

    id: Literal["series"]
    kind: Literal["series"]
    members: list[ViewSeriesMember] = Field(min_length=1, max_length=8)


class ViewConfig(BaseModel):
    """A selection (``rows`` filter) is never part of a view. ``derived`` holds how each
    chemistry column set was computed (never its values): the workbench recomputes them on
    open."""

    model_config = ConfigDict(extra="forbid")

    config_version: int = Field(ge=1, le=VIEW_CONFIG_VERSION)
    panels: list[ViewPanel] = Field(max_length=4)
    filters: list[Annotated[ViewFilter | ViewSubstructureFilter, Field(discriminator="kind")]] = (
        Field(max_length=100)
    )
    labels: dict[str, str] = {}
    derived: list[
        Annotated[ViewRGroups | ViewClusters | ViewSeries, Field(discriminator="kind")]
    ] = []


def validate_view_config(config: dict[str, Any]) -> dict[str, Any]:
    """``config`` unchanged (unknown panel/filter keys kept) if it is a savable view config."""
    size = len(json.dumps(config, separators=(",", ":"), ensure_ascii=False).encode())
    if size > MAX_VIEW_CONFIG_BYTES:
        raise ValidationError(
            f"These settings are too large to save ({math.ceil(size / 1024)} KB of 64 KB)."
        )
    try:
        ViewConfig.model_validate(config)
    except PydanticValidationError as exc:
        raise ValidationError(_readable(exc)) from None
    return config


def _readable(exc: PydanticValidationError) -> str:
    error = exc.errors()[0]
    loc = error["loc"]
    if error["type"] == "union_tag_invalid" and error.get("ctx", {}).get("tag") == "rows":
        return "Selections aren't saved in a view."
    if loc == ("config_version",) and error["type"] == "less_than_equal":
        return "This view was saved by a newer version of ChemCellar. Reload the page to open it."
    where = ".".join(str(part) for part in loc)
    detail = f"{where}: {error['msg']}" if where else error["msg"]
    return f"These view settings can't be saved: {detail}"


def _clean_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValidationError("A view needs a name.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValidationError(f"A view name can be at most {MAX_NAME_LENGTH} characters.")
    return cleaned


def _clean_description(description: str | None) -> str | None:
    cleaned = (description or "").strip() or None
    if cleaned and len(cleaned) > MAX_DESCRIPTION_LENGTH:
        raise ValidationError(
            f"A view description can be at most {MAX_DESCRIPTION_LENGTH:,} characters."
        )
    return cleaned


def _check_visibility(visibility: SearchVisibility, project_id: uuid.UUID | None) -> None:
    if visibility == SearchVisibility.PROJECT and project_id is None:
        raise ValidationError("Sharing a view with a project needs the project.")


def _project_of(visibility: SearchVisibility, project_id: uuid.UUID | None) -> uuid.UUID | None:
    """A private view belongs to no project."""
    return project_id if visibility == SearchVisibility.PROJECT else None


def _text(value: object) -> str | None:
    return None if value is None else str(value)


# Fields audited with old and new values; source (with its protocol ids) and config are
# named only.
_AUDITED = ("name", "description", "visibility", "project_id", "level")


class SavedVisualization(AggregateRoot):
    """Invariants: name stripped, 1 to 255 chars; description ≤ 2,000; PROJECT visibility needs a
    project, PRIVATE has none; ``config`` passes ``validate_view_config``. Only the owner or a
    workspace admin edits; private views are the owner's alone."""

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        source: dict[str, Any],
        protocol_ids: Sequence[uuid.UUID],
        level: str,
        config: dict[str, Any],
        visibility: SearchVisibility = SearchVisibility.PRIVATE,
        project_id: uuid.UUID | None = None,
        created_by: uuid.UUID,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        _check_visibility(visibility, project_id)
        self.workspace_id = workspace_id
        self.name = _clean_name(name)
        self.description = _clean_description(description)
        self.source = dict(source)
        self.protocol_ids = tuple(protocol_ids)
        self.level = level
        self.config = validate_view_config(config)
        self.visibility = visibility
        self.project_id = _project_of(visibility, project_id)
        self.created_by = created_by

    @classmethod
    def create(cls, **kwargs: Any) -> SavedVisualization:
        view = cls(**kwargs)
        view.register_event(
            SavedVisualizationCreated(
                aggregate_id=view.id,
                aggregate_type="SavedVisualization",
                workspace_id=view.workspace_id,
                name=view.name,
                visibility=view.visibility.value,
            )
        )
        return view

    def update(
        self,
        *,
        expected_version: int,
        name: str | None = None,
        description: str | EllipsisType | None = ...,
        source: dict[str, Any] | None = None,
        protocol_ids: Sequence[uuid.UUID] | None = None,
        level: str | None = None,
        config: dict[str, Any] | None = None,
        visibility: SearchVisibility | None = None,
        project_id: uuid.UUID | EllipsisType | None = ...,
    ) -> bool:
        """Apply the given fields (``...`` = leave a nullable field as is); whether anything
        changed. All or nothing: a stale version or an invalid value changes nothing."""
        if expected_version != self.version:
            raise StaleEditError(STALE_VIEW_MESSAGE)
        after: dict[str, Any] = {
            "name": self.name if name is None else _clean_name(name),
            "description": (
                self.description if description is ... else _clean_description(description)
            ),
            "visibility": visibility or self.visibility,
            "project_id": self.project_id if project_id is ... else project_id,
            "level": level or self.level,
            "source": self.source if source is None else dict(source),
            "protocol_ids": self.protocol_ids if protocol_ids is None else tuple(protocol_ids),
            "config": self.config if config is None else validate_view_config(config),
        }
        _check_visibility(after["visibility"], after["project_id"])
        after["project_id"] = _project_of(after["visibility"], after["project_id"])

        changed = {field for field, value in after.items() if value != getattr(self, field)}
        changes = [(f, _text(getattr(self, f)), _text(after[f])) for f in _AUDITED if f in changed]
        if changed & {"source", "protocol_ids"}:
            changes.append(("source", None, None))
        if "config" in changed:
            changes.append(("config", None, None))
        if not changes:
            return False

        for field in changed:
            setattr(self, field, after[field])
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SavedVisualizationUpdated(
                aggregate_id=self.id,
                aggregate_type="SavedVisualization",
                workspace_id=self.workspace_id,
                changes=tuple(changes),
            )
        )
        return True

    def can_be_edited_by(self, user_id: uuid.UUID, *, is_admin: bool) -> bool:
        return is_admin or user_id == self.created_by

    def is_visible_to(self, user_id: uuid.UUID, *, is_admin: bool, is_member: bool) -> bool:
        if user_id == self.created_by:
            return True
        return self.visibility == SearchVisibility.PROJECT and (is_admin or is_member)

    def mark_deleted(self) -> None:
        self.register_event(
            SavedVisualizationDeleted(
                aggregate_id=self.id,
                aggregate_type="SavedVisualization",
                workspace_id=self.workspace_id,
                name=self.name,
            )
        )
