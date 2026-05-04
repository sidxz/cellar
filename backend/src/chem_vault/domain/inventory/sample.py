"""Sample aggregate root — a discrete physical container of material from a batch."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from chem_vault.domain.inventory.enums import ContainerType, SampleStatus
from chem_vault.domain.inventory.events import (
    LowStockDetected,
    SampleAliquoted,
    SampleCreated,
    SampleDepleted,
    SampleDisposed,
    SampleMoved,
    SampleQuarantined,
)
from chem_vault.domain.shared.entity import AggregateRoot
from chem_vault.domain.shared.enums import AmountUnit
from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.shared.value_objects import Amount, Barcode, Concentration

# ---------------------------------------------------------------------------
# State-machine transition table
# ---------------------------------------------------------------------------

_SAMPLE_TRANSITIONS: dict[SampleStatus, set[SampleStatus]] = {
    SampleStatus.AVAILABLE: {
        SampleStatus.DEPLETED,
        SampleStatus.EXPIRED,
        SampleStatus.QUARANTINED,
        SampleStatus.DISPOSED,
    },
    SampleStatus.EXPIRED: {SampleStatus.DISPOSED},
    SampleStatus.QUARANTINED: {SampleStatus.AVAILABLE, SampleStatus.DISPOSED},
    SampleStatus.DEPLETED: set(),  # terminal
    SampleStatus.DISPOSED: set(),  # terminal
}

_TERMINAL_STATES = {SampleStatus.DEPLETED, SampleStatus.DISPOSED}


class Sample(AggregateRoot):
    """A discrete physical container of material from a batch.

    Invariants:
        - amount.value >= 0
        - Auto-depletion when amount reaches 0
        - Low stock detection when amount < threshold
        - depleted and disposed are terminal states
        - freeze_thaw_count only increases
    """

    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        batch_id: uuid.UUID,
        barcode: Barcode,
        container_type: ContainerType,
        amount: Amount,
        concentration: Concentration | None = None,
        solvent: str | None = None,
        status: SampleStatus = SampleStatus.AVAILABLE,
        location_id: uuid.UUID | None = None,
        freeze_thaw_count: int = 0,
        low_stock_threshold: float | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)

        if amount.value < 0:
            raise ValidationError("Sample amount must be >= 0")
        if freeze_thaw_count < 0:
            raise ValidationError("freeze_thaw_count must be >= 0")
        if low_stock_threshold is not None and low_stock_threshold < 0:
            raise ValidationError("low_stock_threshold must be >= 0")

        self.workspace_id = workspace_id
        self.batch_id = batch_id
        self.barcode = barcode
        self.container_type = container_type
        self.amount = amount
        self.concentration = concentration
        self.solvent = solvent
        self.status = status
        self.location_id = location_id
        self.freeze_thaw_count = freeze_thaw_count
        self.low_stock_threshold = low_stock_threshold

    # ------------------------------------------------------------------
    # Factory method
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        workspace_id: uuid.UUID,
        batch_id: uuid.UUID,
        barcode: Barcode,
        container_type: ContainerType,
        amount: Amount,
        concentration: Concentration | None = None,
        solvent: str | None = None,
        location_id: uuid.UUID | None = None,
        low_stock_threshold: float | None = None,
    ) -> Sample:
        sample = cls(
            workspace_id=workspace_id,
            batch_id=batch_id,
            barcode=barcode,
            container_type=container_type,
            amount=amount,
            concentration=concentration,
            solvent=solvent,
            location_id=location_id,
            low_stock_threshold=low_stock_threshold,
        )
        sample.register_event(
            SampleCreated(
                aggregate_id=sample.id,
                aggregate_type="Sample",
                workspace_id=workspace_id,
                batch_id=batch_id,
                barcode=barcode.value,
                amount_value=amount.value,
                amount_unit=amount.unit.value,
            )
        )
        return sample

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _guard_transition(self, target: SampleStatus) -> None:
        allowed = _SAMPLE_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            raise ValidationError(
                f"Cannot transition sample status from "
                f"'{self.status}' to '{target}'"
            )

    def _guard_not_terminal(self) -> None:
        if self.status in _TERMINAL_STATES:
            raise ValidationError(
                f"Sample is in terminal state '{self.status}' — no further changes allowed"
            )

    # ------------------------------------------------------------------
    # Amount operations
    # ------------------------------------------------------------------

    def aliquot(self, amount_to_remove: float) -> None:
        """Remove material from this sample."""
        self._guard_not_terminal()
        if amount_to_remove <= 0:
            raise ValidationError("Amount to remove must be > 0")
        if amount_to_remove > self.amount.value:
            raise ValidationError(
                f"Cannot remove {amount_to_remove} — only {self.amount.value} available"
            )

        remaining = self.amount.value - amount_to_remove
        self.amount = Amount(value=remaining, unit=self.amount.unit)
        self.updated_at = datetime.now(UTC)

        self.register_event(
            SampleAliquoted(
                aggregate_id=self.id,
                aggregate_type="Sample",
                workspace_id=self.workspace_id,
                amount_removed=amount_to_remove,
                remaining_amount=remaining,
                amount_unit=self.amount.unit.value,
            )
        )

        # Auto-depletion
        if remaining == 0:
            self.status = SampleStatus.DEPLETED
            self.register_event(
                SampleDepleted(
                    aggregate_id=self.id,
                    aggregate_type="Sample",
                    workspace_id=self.workspace_id,
                    batch_id=self.batch_id,
                )
            )

        # Low stock detection
        elif (
            self.low_stock_threshold is not None
            and remaining < self.low_stock_threshold
        ):
            self.register_event(
                LowStockDetected(
                    aggregate_id=self.id,
                    aggregate_type="Sample",
                    workspace_id=self.workspace_id,
                    batch_id=self.batch_id,
                    current_amount=remaining,
                    threshold=self.low_stock_threshold,
                    amount_unit=self.amount.unit.value,
                )
            )

    # ------------------------------------------------------------------
    # Location
    # ------------------------------------------------------------------

    def move_to(self, location_id: uuid.UUID | None) -> None:
        """Move sample to a new storage location."""
        self._guard_not_terminal()
        old_id = self.location_id
        self.location_id = location_id
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SampleMoved(
                aggregate_id=self.id,
                aggregate_type="Sample",
                workspace_id=self.workspace_id,
                old_location_id=old_id,
                new_location_id=location_id,
            )
        )

    # ------------------------------------------------------------------
    # Freeze-thaw
    # ------------------------------------------------------------------

    def record_freeze_thaw(self) -> None:
        """Record a freeze-thaw cycle (monotonic increase)."""
        self._guard_not_terminal()
        self.freeze_thaw_count += 1
        self.updated_at = datetime.now(UTC)

    # ------------------------------------------------------------------
    # Status changes
    # ------------------------------------------------------------------

    def quarantine(self, *, reason: str) -> None:
        """Mark sample as quarantined due to QC issue."""
        self._guard_transition(SampleStatus.QUARANTINED)
        self.status = SampleStatus.QUARANTINED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SampleQuarantined(
                aggregate_id=self.id,
                aggregate_type="Sample",
                workspace_id=self.workspace_id,
                reason=reason,
            )
        )

    def clear_quarantine(self) -> None:
        """Return quarantined sample to available."""
        self._guard_transition(SampleStatus.AVAILABLE)
        self.status = SampleStatus.AVAILABLE
        self.updated_at = datetime.now(UTC)

    def expire(self) -> None:
        """Mark sample as expired."""
        self._guard_transition(SampleStatus.EXPIRED)
        self.status = SampleStatus.EXPIRED
        self.updated_at = datetime.now(UTC)

    def dispose(self, *, reason: str | None = None) -> None:
        """Dispose of the sample (terminal)."""
        self._guard_transition(SampleStatus.DISPOSED)
        self.status = SampleStatus.DISPOSED
        self.updated_at = datetime.now(UTC)
        self.register_event(
            SampleDisposed(
                aggregate_id=self.id,
                aggregate_type="Sample",
                workspace_id=self.workspace_id,
                batch_id=self.batch_id,
                reason=reason,
            )
        )
