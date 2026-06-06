"""Protocol aggregate root with owned ReadoutDefinition and ConditionDefinition entities."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    PlateFormat,
    PosControlSignal,
    ProtocolStatus,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.events import (
    ProtocolCreated,
    ProtocolLocked,
    ProtocolPublished,
    ProtocolRetired,
    ProtocolUnlocked,
)
from cellar.domain.shared.entity import AggregateRoot, Entity
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError
from cellar.domain.shared.hit_criterion import (
    HitCriterion,
    validate_hit_criteria,
)
from cellar.domain.shared.ontology import OntologyTerm


# Sentinel used by partial-update mutators to distinguish "leave unchanged"
# (default) from "explicitly set to None".
class _UnsetT:
    pass


_UNSET: _UnsetT = _UnsetT()


# ---------------------------------------------------------------------------
# Protocol state machine
# ---------------------------------------------------------------------------

_PROTOCOL_TRANSITIONS: dict[ProtocolStatus, set[ProtocolStatus]] = {
    ProtocolStatus.DRAFT: {ProtocolStatus.ACTIVE},
    ProtocolStatus.ACTIVE: {ProtocolStatus.RETIRED},
    ProtocolStatus.RETIRED: set(),  # terminal
}

_TERMINAL_STATES = {ProtocolStatus.RETIRED}


# Names that collide with built-in well metadata. Using these as a readout
# definition name confuses the data model (e.g. a "concentration" readout
# row vs. the well's own concentration property) and is rejected at protocol
# design time — see Bug 4.
RESERVED_READOUT_NAMES: frozenset[str] = frozenset(
    {"concentration", "dose", "well", "plate", "batch", "compound"}
)


def is_reserved_readout_name(name: str) -> bool:
    """True if `name` collides with a cellar well-metadata field.

    These names are stored on the well (well.dose, well.batch_id, well.row+
    column → position) or the plate/protocol context, not as readout
    measurements. Used as a creation-time guard at the use-case boundary —
    NOT in the entity constructor, because legacy data with non-conforming
    names must still hydrate.
    """
    return name.strip().lower() in RESERVED_READOUT_NAMES


# Back-compat aliases — internal callers used these names.
_RESERVED_READOUT_NAMES = RESERVED_READOUT_NAMES
_is_reserved_readout_name = is_reserved_readout_name


# ---------------------------------------------------------------------------
# Pick-list value VO — readout-only (not used for ConditionDefinition)
# ---------------------------------------------------------------------------

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


@dataclass(frozen=True)
class PickListValue:
    """A single allowed value for a pick-list-typed readout.

    `color` is optional — when None, the FE derives a stable color from
    the label hash. When set, must be a 7-char lowercase hex (#rrggbb)
    so the palette stays normalized end-to-end. The FE picks from a
    fixed palette; arbitrary hexes from the API are still validated to
    the format but otherwise accepted.
    """

    label: str
    color: str | None = None

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValidationError("PickListValue label must not be empty")
        if self.color is not None and not _HEX_COLOR_RE.match(self.color):
            raise ValidationError(
                f"PickListValue color must be 7-char hex (#rrggbb), got {self.color!r}"
            )

    def to_dict(self) -> dict[str, str | None]:
        return {"label": self.label, "color": self.color}

    @classmethod
    def from_dict(cls, raw: dict[str, object] | str) -> PickListValue:
        """Tolerant deserializer: accepts the rich {label, color} shape OR
        a bare string (legacy: list[str] rows pre-dating this VO)."""
        if isinstance(raw, str):
            return cls(label=raw)
        if isinstance(raw, dict):
            label = raw.get("label")
            color = raw.get("color")
            if not isinstance(label, str):
                raise ValidationError(f"PickListValue dict missing 'label' string: {raw!r}")
            return cls(
                label=label,
                color=color if isinstance(color, str) else None,
            )
        raise ValidationError(f"PickListValue must be str or dict, got {type(raw).__name__}")


def _normalize_pick_list_values(
    raw: list[PickListValue | str | dict[str, object]] | None,
) -> list[PickListValue] | None:
    """Lift mixed inputs (legacy strings, dicts from JSON, already-VO) to
    a homogeneous list[PickListValue]. None passes through unchanged so
    the entity can keep "no pick list" semantics for non-pick-list types."""
    if raw is None:
        return None
    out: list[PickListValue] = []
    for item in raw:
        if isinstance(item, PickListValue):
            out.append(item)
        else:
            out.append(PickListValue.from_dict(item))  # type: ignore[arg-type]
    return out


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
        description: str | None = None,
        data_type: ReadoutDataType,
        unit: str | None = None,
        aggregation: ReadoutAggregation = ReadoutAggregation.NONE,
        precision: int | None = None,
        normalizations: frozenset[ReadoutNormalization] | None = None,
        is_calculated: bool = False,
        calculation_formula: str | None = None,
        display_order: int = 0,
        pick_list_values: list[PickListValue | str | dict[str, object]] | None = None,
        dose_response_config: DoseResponseConfig | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at)

        if not name or not name.strip():
            raise ValidationError("ReadoutDefinition name must not be empty")
        # Reserved-name validation lives at the use-case boundary
        # (Protocol.add_readout_definition, update_readout_definition, the CDD
        # mapper). Constructor stays permissive so legacy data with
        # non-conforming names hydrates cleanly from the database.
        if is_calculated and not calculation_formula:
            raise ValidationError("Calculated readout requires a calculation_formula")

        # pick_list type requires values
        if data_type == ReadoutDataType.PICK_LIST and not pick_list_values:
            raise ValidationError(
                "ReadoutDefinition with pick_list data type requires pick_list_values"
            )
        if data_type != ReadoutDataType.PICK_LIST and pick_list_values is not None:
            raise ValidationError("pick_list_values can only be set for pick_list data type")

        # dose_response type requires config
        if data_type == ReadoutDataType.DOSE_RESPONSE and dose_response_config is None:
            raise ValidationError(
                "ReadoutDefinition with dose_response data type requires dose_response_config"
            )
        if data_type != ReadoutDataType.DOSE_RESPONSE and dose_response_config is not None:
            raise ValidationError(
                "dose_response_config can only be set for dose_response data type"
            )

        resolved_normalizations: frozenset[ReadoutNormalization] = (
            frozenset(normalizations) if normalizations is not None else frozenset()
        )

        self.protocol_id = protocol_id
        self.name = name.strip()
        # Optional documentation — surfaced in the readout-data table
        # header tooltip, the import wizard, and the viewer dialog. Pure
        # cosmetic: editable on unlocked ACTIVE since no run-data
        # interpretation depends on it.
        self.description = description.strip() if description else None
        self.data_type = data_type
        self.unit = unit
        self.aggregation = aggregation
        self.precision = precision
        self.normalizations = resolved_normalizations
        self.is_calculated = is_calculated
        self.calculation_formula = calculation_formula
        self.display_order = display_order
        # Normalize whatever shape came in (list[str] from legacy, list[dict]
        # from JSONB hydration, list[PickListValue] from fresh construction)
        # to a homogeneous list[PickListValue].
        self.pick_list_values: list[PickListValue] | None = _normalize_pick_list_values(
            pick_list_values
        )
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
        category: str | None = None,
        protocol_version: int = 1,
        parent_protocol_id: uuid.UUID | None = None,
        status: ProtocolStatus = ProtocolStatus.DRAFT,
        created_by: uuid.UUID,
        dose_unit: ConcentrationUnit = ConcentrationUnit.UM,
        pos_control_signal: PosControlSignal = PosControlSignal.HIGH,
        readout_definitions: list[ReadoutDefinition] | None = None,
        condition_definitions: list[ConditionDefinition] | None = None,
        control_layouts: dict[str, uuid.UUID] | None = None,
        ontology_annotations: dict[str, list[OntologyTerm]] | None = None,
        recommended_hit_criteria: list[HitCriterion] | None = None,
        is_locked: bool = False,
        locked_by: uuid.UUID | None = None,
        lock_reason: str | None = None,
        locked_at: datetime | None = None,
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
        self.category = category
        self.protocol_version = protocol_version
        self.parent_protocol_id = parent_protocol_id
        self.status = status
        self.created_by = created_by
        # The canonical concentration unit for this assay's well doses (and IC50
        # fits). Single source of truth — every well of every run inherits this.
        self.dose_unit = dose_unit
        # Direction of the POS control's raw signal. Drives normalization +
        # Z' formula dispatch so labs can keep their wet-lab "POS = inhibitor"
        # naming without inverting the math.
        self.pos_control_signal = pos_control_signal
        self.readout_definitions: list[ReadoutDefinition] = readout_definitions or []
        self.condition_definitions: list[ConditionDefinition] = condition_definitions or []
        self.control_layouts: dict[str, uuid.UUID] = control_layouts or {}
        self.ontology_annotations: dict[str, list[OntologyTerm]] = ontology_annotations or {}
        self.recommended_hit_criteria: list[HitCriterion] | None = recommended_hit_criteria
        # Lock state — orthogonal to status. Mirrors Run.is_locked semantics:
        # an explicit freeze gate, independent of DRAFT/ACTIVE/RETIRED. Used
        # to hold a protocol still during regulatory review or cross-team
        # coordination. While locked, even safe-on-ACTIVE additions are
        # blocked; unlock to make changes.
        self.is_locked = is_locked
        self.locked_by = locked_by
        self.lock_reason = lock_reason
        self.locked_at = locked_at

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
            raise ConflictError(f"Cannot transition protocol from '{self.status}' to '{target}'")

    def _guard_draft(self) -> None:
        """Strict guard for STRUCTURAL changes (rename, remove, change
        data_type / formula / DR config) — DRAFT only. The lock check is
        included because DRAFT-locked is also a thing (e.g. reviewing a
        draft before publish).
        """
        if self.is_locked:
            raise ConflictError(
                f"Protocol is locked. Reason: {self.lock_reason or '(none)'}. "
                "Unlock to make changes."
            )
        if self.status != ProtocolStatus.DRAFT:
            raise ConflictError(
                f"Cannot modify definitions of protocol in '{self.status}' status — "
                "only DRAFT protocols are editable"
            )

    def _guard_metadata_mutable(self) -> None:
        """Permissive guard for SAFE additions and cosmetic edits — DRAFT
        or unlocked ACTIVE. Used by add_readout_definition,
        add_condition_definition, set_control_layout (new format only),
        and the cosmetic-fields branch of update_readout_definition.

        Why ACTIVE qualifies: a published protocol can grow (new readouts,
        new conditions, new plate format) without invalidating prior runs
        — they simply don't have data for the new field. Renames and
        removals still require versioning (those break references).
        """
        if self.is_locked:
            raise ConflictError(
                f"Protocol is locked. Reason: {self.lock_reason or '(none)'}. "
                "Unlock to make changes."
            )
        if self.status == ProtocolStatus.RETIRED:
            raise ConflictError("Cannot modify a retired protocol — version a successor instead")

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
        category: str | None = None,
        dose_unit: ConcentrationUnit = ConcentrationUnit.UM,
        pos_control_signal: PosControlSignal = PosControlSignal.HIGH,
        readout_definitions: list[ReadoutDefinition] | None = None,
        condition_definitions: list[ConditionDefinition] | None = None,
    ) -> Protocol:
        if not readout_definitions:
            raise ValidationError("Protocol must have at least one ReadoutDefinition")

        protocol = cls(
            workspace_id=workspace_id,
            name=name,
            description=description,
            protocol_type=protocol_type,
            category=category,
            created_by=created_by,
            dose_unit=dose_unit,
            pos_control_signal=pos_control_signal,
            readout_definitions=readout_definitions,
            condition_definitions=condition_definitions,
        )
        protocol.register_event(
            ProtocolCreated(
                aggregate_id=protocol.id,
                aggregate_type="Protocol",
                workspace_id=workspace_id,
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
        if self.is_locked:
            raise ConflictError("Cannot publish a locked protocol — unlock first")
        self._guard_transition(ProtocolStatus.ACTIVE)
        self.status = ProtocolStatus.ACTIVE
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolPublished(
                aggregate_id=self.id,
                aggregate_type="Protocol",
                workspace_id=self.workspace_id,
            )
        )

    def retire(self, *, reason: str | None = None) -> None:
        """Retire an ACTIVE protocol."""
        if self.is_locked:
            raise ConflictError("Cannot retire a locked protocol — unlock first")
        self._guard_transition(ProtocolStatus.RETIRED)
        self.status = ProtocolStatus.RETIRED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolRetired(
                aggregate_id=self.id,
                aggregate_type="Protocol",
                workspace_id=self.workspace_id,
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
        category: str | None = ...,  # type: ignore[assignment]
        pos_control_signal: PosControlSignal | None = None,
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
        if category is not ...:
            self.category = category
        if pos_control_signal is not None:
            self.pos_control_signal = pos_control_signal
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Mutators allowed on ACTIVE (NOT draft-guarded)
    # ------------------------------------------------------------------
    # These two — set_pos_control_signal and set_recommended_hit_criteria —
    # intentionally bypass `_guard_draft`. They alter labeling/QC
    # convention without changing what was measured, so versioning is
    # overkill and historical raw data stays valid. They DO honor the
    # lock — when a protocol is locked for review, no convention flips
    # either.

    def set_pos_control_signal(self, signal: PosControlSignal) -> None:
        """Set the POS control signal direction.

        Allowed on ACTIVE protocols too — flipping the convention does not
        invalidate any historical raw data; it only changes how downstream
        normalization and QC are computed when Recompute is run. Locking
        this behind ``_guard_draft`` would force users to version a
        protocol just to fix a labeling slip, which the use case is
        specifically meant to avoid.
        """
        self._guard_metadata_mutable()
        self.pos_control_signal = signal
        self.updated_at = datetime.now(UTC)

    def set_recommended_hit_criteria(self, criteria: list[HitCriterion] | None) -> None:
        """Set or clear recommended hit criteria for this protocol.

        Intentionally NOT draft-guarded — protocol owners set criteria on
        active protocols after publishing.
        """
        self._guard_metadata_mutable()
        if criteria is not None:
            validate_hit_criteria(criteria)
        self.recommended_hit_criteria = criteria

    # ------------------------------------------------------------------
    # Locking
    # ------------------------------------------------------------------

    def lock(self, *, locked_by: uuid.UUID, reason: str) -> None:
        """Freeze the protocol metadata.

        Locking is orthogonal to the DRAFT/ACTIVE/RETIRED status — it's a
        workflow gate the screener opts into during regulatory submission,
        external review, or cross-team coordination ("don't add stuff
        mid-screen"). While locked, every mutation method raises
        ConflictError until ``unlock`` is called.

        Cannot lock a RETIRED protocol — retired is already terminal
        read-only; locking is meaningless there.
        """
        if not reason or not reason.strip():
            raise ValidationError("Lock reason is required")
        if self.status == ProtocolStatus.RETIRED:
            raise ConflictError("Cannot lock a retired protocol — already read-only")
        if self.is_locked:
            raise ConflictError("Protocol is already locked")

        self.is_locked = True
        self.locked_by = locked_by
        self.lock_reason = reason.strip()
        self.locked_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolLocked(
                aggregate_id=self.id,
                aggregate_type="Protocol",
                workspace_id=self.workspace_id,
                locked_by=locked_by,
                lock_reason=reason.strip(),
            )
        )

    def unlock(self, *, unlocked_by: uuid.UUID, reason: str) -> None:
        """Release the lock so the protocol can be mutated again.

        Idempotent on already-unlocked protocols — re-calling is a no-op
        with a fresh audit entry. The reason is required so the audit
        log explains why the freeze was lifted.
        """
        if not reason or not reason.strip():
            raise ValidationError("Unlock reason is required")
        if not self.is_locked:
            raise ConflictError("Protocol is not locked")

        self.is_locked = False
        self.locked_by = None
        self.lock_reason = None
        self.locked_at = None
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolUnlocked(
                aggregate_id=self.id,
                aggregate_type="Protocol",
                workspace_id=self.workspace_id,
                unlocked_by=unlocked_by,
                reason=reason.strip(),
            )
        )

    # ------------------------------------------------------------------
    # Readout definition management
    # ------------------------------------------------------------------

    def add_readout_definition(self, definition: ReadoutDefinition) -> None:
        """Add a readout definition to this protocol.

        Allowed on DRAFT or unlocked ACTIVE — adding a new readout never
        invalidates existing runs (they simply lack data for it). Removing
        or renaming, by contrast, requires versioning (see
        ``remove_readout_definition``, ``update_readout_definition``).
        """
        self._guard_metadata_mutable()
        if is_reserved_readout_name(definition.name):
            raise ValidationError(
                f"ReadoutDefinition name '{definition.name}' collides with a "
                f"reserved well-metadata name. Reserved: "
                f"{sorted(RESERVED_READOUT_NAMES)}."
            )
        if any(rd.name == definition.name for rd in self.readout_definitions):
            raise ConflictError(f"ReadoutDefinition with name '{definition.name}' already exists")

        # Cross-readout validation for dose_response type. x_readout_name is
        # optional — None means "use the well's concentration as X".
        if (
            definition.data_type == ReadoutDataType.DOSE_RESPONSE
            and definition.dose_response_config is not None
        ):
            existing_by_name = {rd.name: rd for rd in self.readout_definitions}
            cfg = definition.dose_response_config
            if cfg.x_readout_name is not None and cfg.x_readout_name not in existing_by_name:
                raise ValidationError(
                    f"Dose-response X-axis readout '{cfg.x_readout_name}' "
                    "not found among existing readout definitions"
                )
            if cfg.y_readout_name not in existing_by_name:
                raise ValidationError(
                    f"Dose-response Y-axis readout '{cfg.y_readout_name}' "
                    "not found among existing readout definitions"
                )
            # When y_normalization is set, the referenced Y readout def must
            # actually emit that formula.
            if cfg.y_normalization is not None:
                y_rd = existing_by_name[cfg.y_readout_name]
                if cfg.y_normalization not in y_rd.normalizations:
                    raise ValidationError(
                        f"Dose-response Y-normalization '{cfg.y_normalization.value}' "
                        f"is not emitted by readout '{cfg.y_readout_name}' "
                        f"(emits: {sorted(n.value for n in y_rd.normalizations)})"
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

    def update_readout_definition(
        self,
        definition_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None | _UnsetT = _UNSET,
        data_type: ReadoutDataType | None = None,
        unit: str | None | _UnsetT = _UNSET,
        aggregation: ReadoutAggregation | None = None,
        precision: int | None | _UnsetT = _UNSET,
        normalizations: frozenset[ReadoutNormalization] | None | _UnsetT = _UNSET,
        is_calculated: bool | None = None,
        calculation_formula: str | None | _UnsetT = _UNSET,
        display_order: int | None = None,
        pick_list_values: (
            list[PickListValue | str | dict[str, object]] | None | _UnsetT
        ) = _UNSET,
        dose_response_config: DoseResponseConfig | None | _UnsetT = _UNSET,
    ) -> None:
        """Update fields on an existing readout definition.

        On DRAFT protocols: any field is editable.
        On unlocked ACTIVE protocols: only cosmetic fields (display_order,
        precision, unit) are editable. Structural changes (rename,
        data_type, aggregation, normalizations, is_calculated/formula,
        dose_response_config, pick_list_values) require versioning — see
        ``ProtocolVersioningService.create_new_version``.

        On locked or RETIRED protocols: nothing is editable.

        The structural-diff check is computed against the resulting
        replacement entity so partial-update sentinels (`_UNSET`) don't
        accidentally count as changes.
        """
        # Lock + RETIRED gates first — they apply regardless of which
        # fields are touched.
        self._guard_metadata_mutable()

        idx = next(
            (i for i, d in enumerate(self.readout_definitions) if d.id == definition_id),
            None,
        )
        if idx is None:
            raise NotFoundError("ReadoutDefinition", str(definition_id))

        existing = self.readout_definitions[idx]

        new_name = (name if name is not None else existing.name).strip()
        if is_reserved_readout_name(new_name):
            raise ValidationError(
                f"ReadoutDefinition name '{new_name}' collides with a "
                f"reserved well-metadata name. Reserved: "
                f"{sorted(RESERVED_READOUT_NAMES)}."
            )
        if any(rd.name == new_name and rd.id != definition_id for rd in self.readout_definitions):
            raise ConflictError(f"ReadoutDefinition with name '{new_name}' already exists")

        # Resolve normalizations set: explicit normalizations= updates,
        # _UNSET (sentinel) carries forward existing.
        if normalizations is not _UNSET:
            new_normalizations = (
                frozenset(normalizations) if normalizations is not None else frozenset()
            )
        else:
            new_normalizations = existing.normalizations

        replacement = ReadoutDefinition(
            id=existing.id,
            protocol_id=existing.protocol_id,
            name=new_name,
            description=(
                existing.description if description is _UNSET else description  # type: ignore[arg-type]
            ),
            data_type=data_type if data_type is not None else existing.data_type,
            unit=existing.unit if unit is _UNSET else unit,  # type: ignore[arg-type]
            aggregation=aggregation if aggregation is not None else existing.aggregation,
            precision=existing.precision if precision is _UNSET else precision,  # type: ignore[arg-type]
            normalizations=new_normalizations,
            is_calculated=is_calculated if is_calculated is not None else existing.is_calculated,
            calculation_formula=(
                existing.calculation_formula
                if calculation_formula is _UNSET
                else calculation_formula  # type: ignore[arg-type]
            ),
            display_order=display_order if display_order is not None else existing.display_order,
            pick_list_values=(
                existing.pick_list_values if pick_list_values is _UNSET else pick_list_values  # type: ignore[arg-type]
            ),
            dose_response_config=(
                existing.dose_response_config
                if dose_response_config is _UNSET
                else dose_response_config  # type: ignore[arg-type]
            ),
            created_at=existing.created_at,
        )

        # Cross-readout validation — same rules as add_readout_definition.
        # When the replacement is a dose-response def, x_readout_name must
        # either be None (use well.dose) or match an existing readout in
        # this protocol; y_readout_name must always match.
        if (
            replacement.data_type == ReadoutDataType.DOSE_RESPONSE
            and replacement.dose_response_config is not None
        ):
            existing_by_name = {
                rd.name: rd
                for rd in self.readout_definitions
                if rd.id != definition_id  # exclude the row being replaced
            }
            existing_by_name[replacement.name] = replacement
            cfg = replacement.dose_response_config
            if cfg.x_readout_name is not None and cfg.x_readout_name not in existing_by_name:
                raise ValidationError(
                    f"Dose-response X-axis readout '{cfg.x_readout_name}' "
                    "not found among existing readout definitions"
                )
            if cfg.y_readout_name not in existing_by_name:
                raise ValidationError(
                    f"Dose-response Y-axis readout '{cfg.y_readout_name}' "
                    "not found among existing readout definitions"
                )
            if cfg.y_normalization is not None:
                y_def = existing_by_name[cfg.y_readout_name]
                if cfg.y_normalization not in y_def.normalizations:
                    raise ValidationError(
                        f"Dose-response y_normalization "
                        f"'{cfg.y_normalization.value}' is not in "
                        f"y readout '{cfg.y_readout_name}' normalizations "
                        f"{sorted(n.value for n in y_def.normalizations)}"
                    )

        # Structural-diff guard for non-DRAFT protocols. Cosmetic fields
        # (display_order, precision, unit text) can be edited on unlocked
        # ACTIVE — they only affect display, not the run-data contract.
        # Structural changes break references on existing runs, so the
        # only safe path is versioning.
        if self.status != ProtocolStatus.DRAFT:
            structural: list[str] = []
            if replacement.name != existing.name:
                structural.append(f"name ('{existing.name}' → '{replacement.name}')")
            if replacement.data_type != existing.data_type:
                structural.append("data_type")
            if replacement.aggregation != existing.aggregation:
                structural.append("aggregation")
            if replacement.normalizations != existing.normalizations:
                structural.append("normalizations")
            if replacement.is_calculated != existing.is_calculated:
                structural.append("is_calculated")
            if replacement.calculation_formula != existing.calculation_formula:
                structural.append("calculation_formula")
            if replacement.pick_list_values != existing.pick_list_values:
                structural.append("pick_list_values")
            if replacement.dose_response_config != existing.dose_response_config:
                structural.append("dose_response_config")
            if structural:
                raise ConflictError(
                    f"Cannot change {', '.join(structural)} on a non-draft "
                    f"protocol — create a new version. Cosmetic fields "
                    f"(display_order, precision, unit) are allowed on "
                    f"unlocked ACTIVE."
                )

        self.readout_definitions[idx] = replacement
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Condition definition management
    # ------------------------------------------------------------------

    def add_condition_definition(self, definition: ConditionDefinition) -> None:
        """Add a condition definition to this protocol.

        Allowed on DRAFT or unlocked ACTIVE — adding a new condition never
        invalidates existing runs. They simply lack a value for the new
        key in their ``conditions`` JSONB. Removing or renaming requires
        versioning (run records reference conditions by name).
        """
        self._guard_metadata_mutable()
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

    def update_condition_definition(
        self,
        definition_id: uuid.UUID,
        *,
        name: str | None = None,
        data_type: ConditionDataType | None = None,
        unit: str | None | _UnsetT = _UNSET,
        pick_list_values: list[str] | None | _UnsetT = _UNSET,
    ) -> None:
        """Update fields on an existing condition definition."""
        self._guard_draft()

        idx = next(
            (i for i, d in enumerate(self.condition_definitions) if d.id == definition_id),
            None,
        )
        if idx is None:
            raise NotFoundError("ConditionDefinition", str(definition_id))

        existing = self.condition_definitions[idx]
        new_name = (name if name is not None else existing.name).strip()
        if any(
            cd.name == new_name and cd.id != definition_id for cd in self.condition_definitions
        ):
            raise ConflictError(f"ConditionDefinition with name '{new_name}' already exists")

        replacement = ConditionDefinition(
            id=existing.id,
            protocol_id=existing.protocol_id,
            name=new_name,
            data_type=data_type if data_type is not None else existing.data_type,
            unit=existing.unit if unit is _UNSET else unit,  # type: ignore[arg-type]
            pick_list_values=(
                existing.pick_list_values if pick_list_values is _UNSET else pick_list_values  # type: ignore[arg-type]
            ),
            created_at=existing.created_at,
        )
        self.condition_definitions[idx] = replacement
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Control layout management
    # ------------------------------------------------------------------

    def set_control_layout(self, plate_format: PlateFormat, template_id: uuid.UUID) -> None:
        """Set a default control layout (plate template) for a plate format.

        Adding a layout for a *new* plate format is safe on unlocked ACTIVE —
        existing runs ran on different formats and are unaffected.

        REPLACING an existing format's layout requires DRAFT — every run
        that already used this format had its Z′ + normalization computed
        against the old layout, and silently swapping it would change how
        Recompute interprets historical data.
        """
        if plate_format.value in self.control_layouts:
            self._guard_draft()
        else:
            self._guard_metadata_mutable()
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
