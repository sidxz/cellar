"""Validate and resolve CSV import rows for shipment creation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from chem_vault.application.shared.amount_parser import parse_amount
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import MoleculeRepository
from chem_vault.domain.inventory.repository import BatchRepository, SampleRepository


@dataclass(frozen=True)
class ImportRow:
    """Raw row from CSV."""

    compound: str
    batch: str
    sample: str
    amount: str


@dataclass
class FieldCorrection:
    field: str  # "compound", "batch", "sample", "amount"
    original: str
    corrected: str
    reason: str


@dataclass
class ResolvedRow:
    row_number: int
    status: str  # "valid", "corrected", "error"
    original: ImportRow
    # Resolved references
    compound_id: str | None = None
    compound_display: str | None = None
    batch_id: str | None = None
    batch_display: str | None = None
    sample_id: str | None = None
    sample_display: str | None = None
    amount_value: float | None = None
    amount_unit: str | None = None
    # Tracking
    corrections: list[FieldCorrection] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class ImportPreviewResult:
    rows: list[ResolvedRow]
    total: int
    valid_count: int
    corrected_count: int
    error_count: int


class PreviewShipmentImport:
    def __init__(
        self,
        uow: UnitOfWork,
        molecule_repo: MoleculeRepository,
        batch_repo: BatchRepository,
        sample_repo: SampleRepository,
    ) -> None:
        self._uow = uow
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo
        self._sample_repo = sample_repo

    async def __call__(
        self, workspace_id: uuid.UUID, rows: list[ImportRow]
    ) -> ImportPreviewResult:
        results: list[ResolvedRow] = []

        async with self._uow:
            for i, row in enumerate(rows):
                resolved = ResolvedRow(row_number=i + 1, status="valid", original=row)
                await self._resolve_row(workspace_id, row, resolved)

                # Determine status
                if resolved.errors:
                    resolved.status = "error"
                elif resolved.corrections:
                    resolved.status = "corrected"
                else:
                    resolved.status = "valid"

                results.append(resolved)

        valid_count = sum(1 for r in results if r.status == "valid")
        corrected_count = sum(1 for r in results if r.status == "corrected")
        error_count = sum(1 for r in results if r.status == "error")

        return ImportPreviewResult(
            rows=results,
            total=len(results),
            valid_count=valid_count,
            corrected_count=corrected_count,
            error_count=error_count,
        )

    async def _resolve_row(
        self, workspace_id: uuid.UUID, row: ImportRow, resolved: ResolvedRow
    ) -> None:
        # --- Resolve compound ---
        compound_input = row.compound.strip()
        if not compound_input:
            resolved.errors.append("Compound is required")
        else:
            mol = await self._resolve_compound(workspace_id, compound_input, resolved)
            if mol is None:
                resolved.errors.append(f"Compound not found: '{compound_input}'")

        # --- Resolve batch ---
        batch_input = row.batch.strip()
        if not batch_input:
            resolved.errors.append("Batch is required")
        elif resolved.compound_id:
            batch = await self._resolve_batch(workspace_id, batch_input, resolved)
            if batch is None:
                resolved.errors.append(f"Batch not found: '{batch_input}'")

        # --- Resolve sample ---
        sample_input = row.sample.strip()
        if not sample_input:
            resolved.errors.append("Sample is required")
        elif resolved.batch_id:
            sample = await self._resolve_sample(workspace_id, sample_input, resolved)
            if sample is None:
                resolved.errors.append(f"Sample not found: '{sample_input}'")

        # --- Parse amount ---
        amount_input = row.amount.strip()
        if not amount_input:
            resolved.errors.append("Amount is required")
        else:
            parsed = parse_amount(amount_input)
            if parsed is None:
                resolved.errors.append(f"Cannot parse amount: '{amount_input}'")
            else:
                value, unit = parsed
                resolved.amount_value = value
                resolved.amount_unit = unit
                # Check if we normalized something
                canonical = f"{value} {unit}"
                if amount_input != canonical:
                    resolved.corrections.append(
                        FieldCorrection(
                            field="amount",
                            original=amount_input,
                            corrected=canonical,
                            reason="Normalized format",
                        )
                    )

    async def _resolve_compound(
        self, workspace_id: uuid.UUID, raw: str, resolved: ResolvedRow
    ) -> object | None:
        """Try to find a molecule by reg number, name, or identifier. Case-insensitive."""
        # Try registration number first (most specific)
        mol = await self._molecule_repo.find_by_registration_number(
            workspace_id, raw.upper()
        )
        if mol:
            resolved.compound_id = str(mol.id)
            display_name = mol.name or ""
            reg = mol.registration_number.value if mol.registration_number else ""
            resolved.compound_display = (
                f"{reg} -- {display_name}" if display_name else reg
            )
            if raw != (reg or raw):
                resolved.corrections.append(
                    FieldCorrection(
                        field="compound",
                        original=raw,
                        corrected=reg,
                        reason="Case normalized",
                    )
                )
            return mol

        # Try with original case (maybe it's already correct)
        mol = await self._molecule_repo.find_by_registration_number(workspace_id, raw)
        if mol:
            resolved.compound_id = str(mol.id)
            reg = mol.registration_number.value if mol.registration_number else ""
            resolved.compound_display = f"{reg} -- {mol.name or ''}"
            return mol

        # Try by external identifier
        mol = await self._molecule_repo.find_by_identifier(workspace_id, raw)
        if mol:
            resolved.compound_id = str(mol.id)
            reg = mol.registration_number.value if mol.registration_number else ""
            resolved.compound_display = f"{reg} -- {mol.name or ''}"
            resolved.corrections.append(
                FieldCorrection(
                    field="compound",
                    original=raw,
                    corrected=reg,
                    reason="Matched by external identifier",
                )
            )
            return mol

        # Try case-insensitive identifier
        mol = await self._molecule_repo.find_by_identifier(workspace_id, raw.upper())
        if mol is None:
            mol = await self._molecule_repo.find_by_identifier(
                workspace_id, raw.lower()
            )
        if mol:
            resolved.compound_id = str(mol.id)
            reg = mol.registration_number.value if mol.registration_number else ""
            resolved.compound_display = f"{reg} -- {mol.name or ''}"
            resolved.corrections.append(
                FieldCorrection(
                    field="compound",
                    original=raw,
                    corrected=reg,
                    reason="Case-insensitive identifier match",
                )
            )
            return mol

        return None

    async def _resolve_batch(
        self, workspace_id: uuid.UUID, raw: str, resolved: ResolvedRow
    ) -> object | None:
        """Try to find batch by batch_number. Case-insensitive."""
        # Try exact
        batch = await self._batch_repo.find_by_batch_number(workspace_id, raw)
        if batch:
            resolved.batch_id = str(batch.id)
            bn = (
                batch.batch_number.value
                if hasattr(batch.batch_number, "value")
                else str(batch.batch_number)
            )
            resolved.batch_display = bn
            return batch

        # Try uppercase
        batch = await self._batch_repo.find_by_batch_number(workspace_id, raw.upper())
        if batch:
            resolved.batch_id = str(batch.id)
            bn = (
                batch.batch_number.value
                if hasattr(batch.batch_number, "value")
                else str(batch.batch_number)
            )
            resolved.batch_display = bn
            if raw != bn:
                resolved.corrections.append(
                    FieldCorrection(
                        field="batch",
                        original=raw,
                        corrected=bn,
                        reason="Case normalized",
                    )
                )
            return batch

        return None

    async def _resolve_sample(
        self, workspace_id: uuid.UUID, raw: str, resolved: ResolvedRow
    ) -> object | None:
        """Try to find sample by barcode. Case-insensitive."""
        # Try exact
        sample = await self._sample_repo.find_by_barcode(workspace_id, raw)
        if sample:
            resolved.sample_id = str(sample.id)
            resolved.sample_display = sample.barcode.value
            return sample

        # Try uppercase
        sample = await self._sample_repo.find_by_barcode(workspace_id, raw.upper())
        if sample:
            resolved.sample_id = str(sample.id)
            resolved.sample_display = sample.barcode.value
            if raw != sample.barcode.value:
                resolved.corrections.append(
                    FieldCorrection(
                        field="sample",
                        original=raw,
                        corrected=sample.barcode.value,
                        reason="Case normalized",
                    )
                )
            return sample

        return None
