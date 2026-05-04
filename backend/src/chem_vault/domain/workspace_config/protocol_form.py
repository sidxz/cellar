"""ProtocolForm aggregate — workspace-scoped template for protocol creation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.events import (
    ProtocolFormCreated,
    ProtocolFormUpdated,
)

__all__ = [
    "ProtocolForm",
    "ProtocolFormCondition",
    "ProtocolFormCreated",
    "ProtocolFormOntologyDefault",
    "ProtocolFormReadout",
    "ProtocolFormUpdated",
]

# Sentinel for "not provided" in update()
UNSET = object()


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProtocolFormReadout:
    """Pre-configured readout definition for a protocol form template."""

    name: str
    data_type: str  # "numeric", "text", "pick_list", "dose_response", "batch_link", "file", "date"
    unit: str | None = None
    aggregation: str = "none"
    normalization: str = "none"
    is_calculated: bool = False
    calculation_formula: str | None = None
    pick_list_values: list[str] | None = None
    dose_response_config: dict | None = None  # stored as dict, converted to DoseResponseConfig at protocol creation


@dataclass(frozen=True)
class ProtocolFormCondition:
    """Pre-configured condition definition for a protocol form template."""

    name: str
    data_type: str  # "text", "numeric", "pick_list"
    unit: str | None = None
    pick_list_values: list[str] | None = None


@dataclass(frozen=True)
class ProtocolFormOntologyDefault:
    """Default ontology annotation for a slot."""

    slot_name: str
    terms: list = field(default_factory=list)  # list of dicts {term_id, label, ontology_source, uri}


# ---------------------------------------------------------------------------
# Aggregate Root
# ---------------------------------------------------------------------------


class ProtocolForm(AggregateRoot):
    """A template for creating protocols with pre-configured definitions.

    Pre-fills readout definitions, condition definitions, and ontology
    annotations when a user selects this form during protocol creation.
    At most one form per workspace may be flagged as ``is_default``.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        protocol_type: str | None = None,
        is_default: bool = False,
        readout_templates: list[ProtocolFormReadout] | None = None,
        condition_templates: list[ProtocolFormCondition] | None = None,
        ontology_defaults: list[ProtocolFormOntologyDefault] | None = None,
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
        self.description = description
        self.protocol_type = protocol_type
        self.is_default = is_default
        self.readout_templates: list[ProtocolFormReadout] = list(readout_templates) if readout_templates else []
        self.condition_templates: list[ProtocolFormCondition] = list(condition_templates) if condition_templates else []
        self.ontology_defaults: list[ProtocolFormOntologyDefault] = list(ontology_defaults) if ontology_defaults else []

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        protocol_type: str | None = None,
        is_default: bool = False,
        readout_templates: list[ProtocolFormReadout] | None = None,
        condition_templates: list[ProtocolFormCondition] | None = None,
        ontology_defaults: list[ProtocolFormOntologyDefault] | None = None,
    ) -> ProtocolForm:
        """Create and validate a new ProtocolForm."""
        if not name or not name.strip():
            raise ValidationError("name must not be empty")

        templates = list(readout_templates) if readout_templates else []
        if not templates:
            raise ValidationError("at least one readout template is required")
        for rt in templates:
            if not rt.name or not rt.name.strip():
                raise ValidationError("readout template name must not be empty")

        form = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            name=name.strip(),
            description=description,
            protocol_type=protocol_type,
            is_default=is_default,
            readout_templates=templates,
            condition_templates=condition_templates,
            ontology_defaults=ontology_defaults,
        )
        form.register_event(
            ProtocolFormCreated(
                aggregate_id=form.id,
                aggregate_type="ProtocolForm",
                workspace_id=workspace_id,
                name=name.strip(),
            )
        )
        return form

    # ------------------------------------------------------------------
    # Mutation commands
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str | object = UNSET,
        description: str | None | object = UNSET,
        protocol_type: str | None | object = UNSET,
        is_default: bool | object = UNSET,
        readout_templates: list[ProtocolFormReadout] | None | object = UNSET,
        condition_templates: list[ProtocolFormCondition] | None | object = UNSET,
        ontology_defaults: list[ProtocolFormOntologyDefault] | None | object = UNSET,
    ) -> None:
        """Partial update — only provided fields are changed."""
        if name is not UNSET:
            if not name or not str(name).strip():
                raise ValidationError("name must not be empty")
            self.name = str(name).strip()

        if description is not UNSET:
            self.description = description  # type: ignore[assignment]

        if protocol_type is not UNSET:
            self.protocol_type = protocol_type  # type: ignore[assignment]

        if is_default is not UNSET:
            self.is_default = bool(is_default)

        if readout_templates is not UNSET:
            templates = list(readout_templates) if readout_templates else []  # type: ignore[arg-type]
            if not templates:
                raise ValidationError("at least one readout template is required")
            for rt in templates:
                if not rt.name or not rt.name.strip():
                    raise ValidationError("readout template name must not be empty")
            self.readout_templates = templates

        if condition_templates is not UNSET:
            self.condition_templates = list(condition_templates) if condition_templates else []  # type: ignore[arg-type]

        if ontology_defaults is not UNSET:
            self.ontology_defaults = list(ontology_defaults) if ontology_defaults else []  # type: ignore[arg-type]

        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolFormUpdated(
                aggregate_id=self.id,
                aggregate_type="ProtocolForm",
                workspace_id=self.workspace_id,
            )
        )

    def set_default(self, is_default: bool) -> None:
        """Set or unset this form as the workspace default."""
        self.is_default = is_default
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolFormUpdated(
                aggregate_id=self.id,
                aggregate_type="ProtocolForm",
                workspace_id=self.workspace_id,
            )
        )
