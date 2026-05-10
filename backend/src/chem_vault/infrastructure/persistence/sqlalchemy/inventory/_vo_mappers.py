"""Value-object ↔ column mappers for inventory persistence.

Repeating ``Amount(value=..., unit=AmountUnit(...))`` and concentration
unpacking in every inventory mapper is a small but real source of drift —
add a column on the SA model and you have to touch every repo. These
helpers centralise the unpacking; both directions live here so the
constructor and the update path share one source of truth.
"""

from __future__ import annotations

from typing import Protocol

from chem_vault.domain.shared.enums import AmountUnit, ConcentrationUnit, LightCondition
from chem_vault.domain.shared.value_objects import (
    Amount,
    Concentration,
    StorageCondition,
)


# --- Amount (required field on Batch / Sample) ------------------------------


class _AmountColumns(Protocol):
    amount_value: float
    amount_unit: str


def amount_from_columns(model: _AmountColumns) -> Amount:
    """Build an Amount from the model's ``amount_value`` + ``amount_unit``."""
    return Amount(value=model.amount_value, unit=AmountUnit(model.amount_unit))


def amount_to_columns(amount: Amount) -> dict[str, object]:
    """Render an Amount into a kwargs dict for SA model construction/update."""
    return {"amount_value": amount.value, "amount_unit": amount.unit.value}


# --- Concentration (optional VO) --------------------------------------------


class _ConcentrationColumns(Protocol):
    concentration_value: float | None
    concentration_unit: str | None


def concentration_from_columns(model: _ConcentrationColumns) -> Concentration | None:
    """Build a Concentration from value/unit columns, or None when unset."""
    if model.concentration_value is None or model.concentration_unit is None:
        return None
    return Concentration(
        value=model.concentration_value,
        unit=ConcentrationUnit(model.concentration_unit),
    )


def concentration_to_columns(concentration: Concentration | None) -> dict[str, object | None]:
    """Render a Concentration into kwargs (both columns nullable)."""
    if concentration is None:
        return {"concentration_value": None, "concentration_unit": None}
    return {
        "concentration_value": concentration.value,
        "concentration_unit": concentration.unit.value,
    }


# --- StorageCondition (optional VO with light_condition sub-field) ----------


class _StorageColumns(Protocol):
    storage_temperature_celsius: float | None
    storage_humidity_percent: float | None
    storage_light_condition: str | None


def storage_from_columns(model: _StorageColumns) -> StorageCondition | None:
    """Build a StorageCondition from the storage_* columns, or None when unset."""
    if model.storage_temperature_celsius is None:
        return None
    return StorageCondition(
        temperature_celsius=model.storage_temperature_celsius,
        relative_humidity_percent=model.storage_humidity_percent,
        light_condition=(
            LightCondition(model.storage_light_condition)
            if model.storage_light_condition
            else None
        ),
    )


def storage_to_columns(storage: StorageCondition | None) -> dict[str, object | None]:
    """Render a StorageCondition into the three storage_* kwargs."""
    if storage is None:
        return {
            "storage_temperature_celsius": None,
            "storage_humidity_percent": None,
            "storage_light_condition": None,
        }
    return {
        "storage_temperature_celsius": storage.temperature_celsius,
        "storage_humidity_percent": storage.relative_humidity_percent,
        "storage_light_condition": (
            storage.light_condition.value if storage.light_condition else None
        ),
    }
