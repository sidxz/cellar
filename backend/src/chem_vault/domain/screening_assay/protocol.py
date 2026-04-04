"""Protocol aggregate root with owned ReadoutDefinition and ConditionDefinition entities."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.screening_assay.enums import (
    ConditionDataType,
    ProtocolStatus,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.events import (
    ProtocolCreated,
    ProtocolPublished,
    ProtocolRetired,
)
from chem_vault.domain.shared.entity import AggregateRoot, Entity
from chem_vault.domain.shared.errors import ConflictError, NotFoundError, ValidationError


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
