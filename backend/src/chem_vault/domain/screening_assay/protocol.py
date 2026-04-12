"""Protocol aggregate root with owned ReadoutDefinition and ConditionDefinition entities."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.screening_assay.dose_response_config import DoseResponseConfig
from chem_vault.domain.screening_assay.enums import (
    ConditionDataType,
    PlateFormat,
    ProtocolStatus,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.hit_criterion import (
    HitCriterion,
    validate_hit_criteria,
)
from chem_vault.domain.screening_assay.events import (
    ProtocolCreated,
    ProtocolPublished,
    ProtocolRetired,
)
from chem_vault.domain.shared.entity import AggregateRoot, Entity
from chem_vault.domain.shared.errors import ConflictError, NotFoundError, ValidationError
from chem_vault.domain.shared.ontology import OntologyTerm


# ---------------------------------------------------------------------------
# Protocol state machine
# ---------------------------------------------------------------------------

_PROTOCOL_TRANSITIONS: dict[ProtocolStatus, set[ProtocolStatus]] = {
    ProtocolStatus.DRAFT: {ProtocolStatus.ACTIVE},
    ProtocolStatus.ACTIVE: {ProtocolStatus.RETIRED},
    ProtocolStatus.RETIRED: set(),  # terminal
}

_TERMINAL_STATES = {ProtocolStatus.RETIRED}


# ---------------------------------------------------------------------------
# Owned entities
# ---------------------------------------------------------------------------


class ReadoutDefinition(Entity):
    """Defines a measurement column for a protocol.

    Owned by Protocol — created and managed only through the aggregate root.

    Invariants:
        - name cannot be empty
        - calculated readout requires a formula
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        protocol_id: uuid.UUID,
        name: str,
        data_type: ReadoutDataType,
        unit: str | None = None,
        aggregation: ReadoutAggregation = ReadoutAggregation.NONE,
        precision: int | None = None,
        normalization: ReadoutNormalization = ReadoutNormalization.NONE,
        is_calculated: bool = False,
        calculation_formula: str | None = None,
        display_order: int = 0,
        pick_list_values: list[str] | None = None,
        dose_response_config: DoseResponseConfig | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if not name or not name.strip():
            raise ValidationError("ReadoutDefinition name must not be empty")
        if is_calculated and not calculation_formula:
            raise ValidationError(
                "Calculated readout requires a calculation_formula"
            )

        # pick_list type requires values
        if data_type == ReadoutDataType.PICK_LIST and not pick_list_values:
            raise ValidationError(
                "ReadoutDefinition with pick_list data type requires pick_list_values"
            )
        if data_type != ReadoutDataType.PICK_LIST and pick_list_values is not None:
            raise ValidationError(
                "pick_list_values can only be set for pick_list data type"
            )

        # dose_response type requires config
        if data_type == ReadoutDataType.DOSE_RESPONSE and dose_response_config is None:
            raise ValidationError(
                "ReadoutDefinition with dose_response data type requires dose_response_config"
            )
        if data_type != ReadoutDataType.DOSE_RESPONSE and dose_response_config is not None:
            raise ValidationError(
                "dose_response_config can only be set for dose_response data type"
            )

        self.protocol_id = protocol_id
        self.name = name.strip()
        self.data_type = data_type
        self.unit = unit
        self.aggregation = aggregation
        self.precision = precision
        self.normalization = normalization
        self.is_calculated = is_calculated
        self.calculation_formula = calculation_formula
        self.display_order = display_order
        self.pick_list_values = pick_list_values
        self.dose_response_config = dose_response_config


class ConditionDefinition(Entity):
    """Defines an experimental variable for categorizing runs.

    Owned by Protocol — created and managed only through the aggregate root.

    Invariants:
        - name cannot be empty
        - pick_list data type requires pick_list_values
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        protocol_id: uuid.UUID,
        name: str,
        data_type: ConditionDataType,
        unit: str | None = None,
        pick_list_values: list[str] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if not name or not name.strip():
            raise ValidationError("ConditionDefinition name must not be empty")
        if data_type == ConditionDataType.PICK_LIST and not pick_list_values:
            raise ValidationError(
                "ConditionDefinition with pick_list data type requires pick_list_values"
            )

        self.protocol_id = protocol_id
        self.name = name.strip()
        self.data_type = data_type
        self.unit = unit
        self.pick_list_values = pick_list_values


# ---------------------------------------------------------------------------
# Protocol aggregate root
# ---------------------------------------------------------------------------


class Protocol(AggregateRoot):
    """A versioned template describing an experimental procedure and its measurements.

    Invariants:
        - At least one ReadoutDefinition required on create
        - Only DRAFT protocols can have definitions modified
        - Name cannot be empty
        - Status transitions follow the state machine

    State machine:
        draft -[publish]-> active -[retire]-> retired (terminal)
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        name: str,
        description: str | None = None,
        protocol_type: ProtocolType,
        target_id: uuid.UUID | None = None,
        category: str | None = None,
        protocol_version: int = 1,
        parent_protocol_id: uuid.UUID | None = None,
        status: ProtocolStatus = ProtocolStatus.DRAFT,
        created_by: uuid.UUID,
        readout_definitions: list[ReadoutDefinition] | None = None,
        condition_definitions: list[ConditionDefinition] | None = None,
        control_layouts: dict[str, uuid.UUID] | None = None,
        ontology_annotations: dict[str, list[OntologyTerm]] | None = None,
        recommended_hit_criteria: list[HitCriterion] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        if not name or not name.strip():
            raise ValidationError("Protocol name must not be empty")

        self.workspace_id = workspace_id
        self.name = name.strip()
        self.description = description
        self.protocol_type = protocol_type
        self.target_id = target_id
        self.category = category
        self.protocol_version = protocol_version
        self.parent_protocol_id = parent_protocol_id
        self.status = status
        self.created_by = created_by
        self.readout_definitions: list[ReadoutDefinition] = readout_definitions or []
        self.condition_definitions: list[ConditionDefinition] = condition_definitions or []
        self.control_layouts: dict[str, uuid.UUID] = control_layouts or {}
        self.ontology_annotations: dict[str, list[OntologyTerm]] = ontology_annotations or {}
        self.recommended_hit_criteria: list[HitCriterion] | None = recommended_hit_criteria

        # Bind owned entities to this aggregate
        for rd in self.readout_definitions:
            rd.protocol_id = self.id
        for cd in self.condition_definitions:
            cd.protocol_id = self.id

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------

    def _guard_transition(self, target: ProtocolStatus) -> None:
        allowed = _PROTOCOL_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ConflictError(
                f"Cannot transition protocol from '{self.status}' to '{target}'"
            )

    def _guard_draft(self) -> None:
        """Only DRAFT protocols allow definition modifications."""
        if self.status != ProtocolStatus.DRAFT:
            raise ConflictError(
                f"Cannot modify definitions of protocol in '{self.status}' status — "
                "only DRAFT protocols are editable"
            )

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        name: str,
        protocol_type: ProtocolType,
        created_by: uuid.UUID,
        description: str | None = None,
        target_id: uuid.UUID | None = None,
        category: str | None = None,
        readout_definitions: list[ReadoutDefinition] | None = None,
        condition_definitions: list[ConditionDefinition] | None = None,
    ) -> Protocol:
        if not readout_definitions:
            raise ValidationError(
                "Protocol must have at least one ReadoutDefinition"
            )

        protocol = cls(
            workspace_id=workspace_id,
            name=name,
            description=description,
            protocol_type=protocol_type,
            target_id=target_id,
            category=category,
            created_by=created_by,
            readout_definitions=readout_definitions,
            condition_definitions=condition_definitions,
        )
        protocol.register_event(
            ProtocolCreated(
                aggregate_id=protocol.id,
                aggregate_type="Protocol",
                name=protocol.name,
                version=protocol.protocol_version,
                protocol_type=protocol.protocol_type.value,
            )
        )
        return protocol

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def publish(self) -> None:
        """Promote a DRAFT protocol to ACTIVE."""
        self._guard_transition(ProtocolStatus.ACTIVE)
        self.status = ProtocolStatus.ACTIVE
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolPublished(
                aggregate_id=self.id,
                aggregate_type="Protocol",
            )
        )

    def retire(self, *, reason: str | None = None) -> None:
        """Retire an ACTIVE protocol."""
        self._guard_transition(ProtocolStatus.RETIRED)
        self.status = ProtocolStatus.RETIRED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolRetired(
                aggregate_id=self.id,
                aggregate_type="Protocol",
                reason=reason,
            )
        )

    # ------------------------------------------------------------------
    # Metadata updates
    # ------------------------------------------------------------------

    def update(
        self,
        *,
        name: str | None = None,
        description: str | None = ...,  # type: ignore[assignment]
        target_id: uuid.UUID | None = ...,  # type: ignore[assignment]
        category: str | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update mutable metadata fields.

        Only DRAFT protocols can be updated.
        Uses sentinel ``...`` for nullable fields.
        """
        self._guard_draft()

        if name is not None:
            if not name.strip():
                raise ValidationError("Protocol name must not be empty")
            self.name = name.strip()
        if description is not ...:
            self.description = description
        if target_id is not ...:
            self.target_id = target_id
        if category is not ...:
            self.category = category
        self.updated_at = datetime.now(UTC)

    def set_recommended_hit_criteria(
        self, criteria: list[HitCriterion] | None
    ) -> None:
        """Set or clear recommended hit criteria for this protocol."""
        if criteria is not None:
            validate_hit_criteria(criteria)
        self.recommended_hit_criteria = criteria

    # ------------------------------------------------------------------
    # Readout definition management
    # ------------------------------------------------------------------

    def add_readout_definition(self, definition: ReadoutDefinition) -> None:
        """Add a readout definition to this protocol."""
        self._guard_draft()
        if any(rd.name == definition.name for rd in self.readout_definitions):
            raise ConflictError(
                f"ReadoutDefinition with name '{definition.name}' already exists"
            )

        # Cross-readout validation for dose_response type
        if (
            definition.data_type == ReadoutDataType.DOSE_RESPONSE
            and definition.dose_response_config is not None
        ):
            existing_names = {rd.name for rd in self.readout_definitions}
            cfg = definition.dose_response_config
            if cfg.x_readout_name not in existing_names:
                raise ValidationError(
                    f"Dose-response X-axis readout '{cfg.x_readout_name}' "
                    "not found among existing readout definitions"
                )
            if cfg.y_readout_name not in existing_names:
                raise ValidationError(
                    f"Dose-response Y-axis readout '{cfg.y_readout_name}' "
                    "not found among existing readout definitions"
                )

        definition.protocol_id = self.id
        self.readout_definitions.append(definition)
        self.updated_at = datetime.now(UTC)

    def remove_readout_definition(self, definition_id: uuid.UUID) -> None:
        """Remove a readout definition by ID.

        Raises NotFoundError if the definition does not exist.
        Raises ValidationError if removal would leave zero readout definitions.
        """
        self._guard_draft()

        idx = next(
            (i for i, d in enumerate(self.readout_definitions) if d.id == definition_id),
            None,
        )
        if idx is None:
            raise NotFoundError("ReadoutDefinition", str(definition_id))

        if len(self.readout_definitions) <= 1:
            raise ValidationError(
                "Cannot remove last ReadoutDefinition — protocol must have at least one"
            )

        self.readout_definitions.pop(idx)
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Condition definition management
    # ------------------------------------------------------------------

    def add_condition_definition(self, definition: ConditionDefinition) -> None:
        """Add a condition definition to this protocol."""
        self._guard_draft()
        if any(cd.name == definition.name for cd in self.condition_definitions):
            raise ConflictError(
                f"ConditionDefinition with name '{definition.name}' already exists"
            )
        definition.protocol_id = self.id
        self.condition_definitions.append(definition)
        self.updated_at = datetime.now(UTC)

    def remove_condition_definition(self, definition_id: uuid.UUID) -> None:
        """Remove a condition definition by ID.

        Raises NotFoundError if the definition does not exist.
        """
        self._guard_draft()

        idx = next(
            (i for i, d in enumerate(self.condition_definitions) if d.id == definition_id),
            None,
        )
        if idx is None:
            raise NotFoundError("ConditionDefinition", str(definition_id))

        self.condition_definitions.pop(idx)
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Control layout management
    # ------------------------------------------------------------------

    def set_control_layout(
        self, plate_format: PlateFormat, template_id: uuid.UUID
    ) -> None:
        """Set a default control layout (plate template) for a plate format."""
        self._guard_draft()
        self.control_layouts[plate_format.value] = template_id
        self.updated_at = datetime.now(UTC)

    def remove_control_layout(self, plate_format: PlateFormat) -> None:
        """Remove the default control layout for a plate format."""
        self._guard_draft()
        if plate_format.value in self.control_layouts:
            del self.control_layouts[plate_format.value]
            self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Ontology annotation management
    # ------------------------------------------------------------------

    def set_ontology_annotation(self, slot: str, terms: list[OntologyTerm]) -> None:
        """Set ontology terms for a named annotation slot."""
        self._guard_draft()
        if not slot or not slot.strip():
            raise ValidationError("Ontology annotation slot name must not be empty")
        self.ontology_annotations[slot.strip()] = terms
        self.updated_at = datetime.now(UTC)

    def remove_ontology_annotation(self, slot: str) -> None:
        """Remove all ontology terms for a named annotation slot."""
        self._guard_draft()
        if slot in self.ontology_annotations:
            del self.ontology_annotations[slot]
            self.updated_at = datetime.now(UTC)
