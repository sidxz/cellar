"""OntologySlotDefinition aggregate — workspace-scoped ontology annotation slot."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.events import (
    OntologySlotDefinitionCreated,
    OntologySlotDefinitionUpdated,
)

__all__ = ["OntologySlotDefinition"]

# Sentinel for "not provided" in update()
UNSET = object()


class OntologySlotDefinition(AggregateRoot):
    """Aggregate root for a workspace-scoped ontology annotation slot.

    An OntologySlotDefinition describes a named slot (e.g. "bioassay_type",
    "cell_line") that can be annotated with ontology terms on entities like
    Protocol. Each slot specifies which ontology sources are valid and whether
    free-text terms are allowed.

    Invariants:
        - name must not be empty
        - label must not be empty
        - ontology_sources must have at least one entry
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        name: str,
        label: str,
        ontology_sources: list[str],
        root_concept_id: str | None = None,
        is_required: bool = False,
        allow_free_text: bool = True,
        display_order: int = 0,
        version: int = 1,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(
            id=id,
            version=version,
            created_at=created_at,
            updated_at=updated_at,
        )
        self.workspace_id = workspace_id
        self.name = name
        self.label = label
        self.ontology_sources = ontology_sources
        self.root_concept_id = root_concept_id
        self.is_required = is_required
        self.allow_free_text = allow_free_text
        self.display_order = display_order

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        label: str,
        ontology_sources: list[str],
        root_concept_id: str | None = None,
        is_required: bool = False,
        allow_free_text: bool = True,
        display_order: int = 0,
    ) -> OntologySlotDefinition:
        """Create and validate a new OntologySlotDefinition."""
        if not name or not name.strip():
            raise ValidationError("name must not be empty")
        if not label or not label.strip():
            raise ValidationError("label must not be empty")
        if not ontology_sources:
            raise ValidationError("ontology_sources must have at least one entry")

        slot = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            name=name.strip(),
            label=label.strip(),
            ontology_sources=list(ontology_sources),
            root_concept_id=root_concept_id.strip() if root_concept_id else None,
            is_required=is_required,
            allow_free_text=allow_free_text,
            display_order=display_order,
        )
        slot.register_event(
            OntologySlotDefinitionCreated(
                aggregate_id=slot.id,
                aggregate_type="OntologySlotDefinition",
                workspace_id=workspace_id,
                name=name.strip(),
            )
        )
        return slot

    # ------------------------------------------------------------------
    # Mutation commands
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        label: str | object = UNSET,
        ontology_sources: list[str] | object = UNSET,
        root_concept_id: str | None | object = UNSET,
        is_required: bool | object = UNSET,
        allow_free_text: bool | object = UNSET,
        display_order: int | object = UNSET,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if label is not UNSET:
            label_str = str(label).strip()
            if not label_str:
                raise ValidationError("label must not be empty")
            self.label = label_str
        if ontology_sources is not UNSET:
            sources = list(ontology_sources)  # type: ignore[arg-type]
            if not sources:
                raise ValidationError("ontology_sources must have at least one entry")
            self.ontology_sources = sources
        if root_concept_id is not UNSET:
            self.root_concept_id = root_concept_id.strip() if isinstance(root_concept_id, str) and root_concept_id else None  # type: ignore[assignment]
        if is_required is not UNSET:
            self.is_required = bool(is_required)
        if allow_free_text is not UNSET:
            self.allow_free_text = bool(allow_free_text)
        if display_order is not UNSET:
            self.display_order = int(display_order)  # type: ignore[arg-type]

        self.updated_at = datetime.now(UTC)
        self.register_event(
            OntologySlotDefinitionUpdated(
                aggregate_id=self.id,
                aggregate_type="OntologySlotDefinition",
                workspace_id=self.workspace_id,
            )
        )
