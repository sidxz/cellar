"""Chemical file parsers for bulk registration — SDF, CSV, XLSX.

Infrastructure layer. Parses chemical data files into a flat list of
ParsedMoleculeItem dicts that the application layer can feed into the
RegisterMolecule use case.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd
from rdkit import Chem

from cellar.application.chemical_registration.bulk_column_mapping import (
    COMPOUND_ID_TYPES,
    SDF_TITLE_HEADER,
    ColumnMapping,
    ColumnTarget,
    split_multi,
    suggest_column_mapping,
)
from cellar.domain.chemical_registration.enums import BulkRegistrationFileFormat


@dataclass(frozen=True)
class ParsedMoleculeItem:
    """A single parsed molecule record from a bulk import file."""

    row_index: int
    file_row: int = 0  # the row number a person sees in the file
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    # {"identifier", "identifier_type", optional "source"}
    external_ids: list[dict[str, str]] = field(default_factory=list)
    # {"identifier", "source"} — stored on the row's batch
    batch_ids: list[dict[str, str]] = field(default_factory=list)
    custom_fields: dict | None = None
    error: str | None = None
    # Batch fields
    amount_value: float | None = None
    amount_unit: str = "mg"
    salt_code: str | None = None
    salt_stoichiometry: int = 1
    purity: float | None = None
    batch_source: str = "synthesized"
    appearance: str | None = None


class ChemicalFileParser(Protocol):
    """Protocol for parsing chemical data files."""

    def parse(
        self, content: bytes, filename: str, mapping: ColumnMapping | None = None
    ) -> list[ParsedMoleculeItem]: ...


# ---------------------------------------------------------------------------
# Mapping-driven row extraction (shared by the SDF and tabular parsers)
# ---------------------------------------------------------------------------

_DEFAULT_BATCH_ID_SOURCE = "Bulk registration"


def _default_mapping(headers: list[str]) -> ColumnMapping:
    """No mapping sent: today's header names, stored with today's sources."""
    return suggest_column_mapping(headers).without_sources()


def _extract_item(
    get: Callable[[str], str | None],
    mapping: ColumnMapping,
    *,
    row_index: int,
    file_row: int,
    structure: str | None = None,
) -> ParsedMoleculeItem:
    """Build one item from a row. ``get(header)`` returns the trimmed cell or None.

    ``structure`` (SDF) is the record's own structure; it wins over a mapped column.
    """
    single: dict[ColumnTarget, str] = {}
    external_ids: list[dict[str, str]] = []
    batch_ids: list[dict[str, str]] = []
    for col in mapping.columns:
        if col.target == ColumnTarget.IGNORE:
            continue
        val = get(col.header)
        if not val:
            continue
        if col.target == ColumnTarget.BATCH_ID:
            for v in split_multi(val):
                batch_ids.append(
                    {"identifier": v, "source": col.source or _DEFAULT_BATCH_ID_SOURCE}
                )
        elif col.target in COMPOUND_ID_TYPES:
            values = split_multi(val) if col.target == ColumnTarget.COMPOUND_ID else [val]
            for v in values:
                eid = {"identifier": v, "identifier_type": COMPOUND_ID_TYPES[col.target]}
                if col.source:
                    eid["source"] = col.source
                external_ids.append(eid)
        else:
            single[col.target] = val

    name = single.get(ColumnTarget.NAME)
    smiles = structure or single.get(ColumnTarget.SMILES)
    if not name and not smiles:
        return ParsedMoleculeItem(
            row_index=row_index,
            file_row=file_row,
            error=f"Row {file_row}: no name or structure",
        )

    stoich = _safe_int(single.get(ColumnTarget.SALT_STOICHIOMETRY))
    # Leave name as None when the row has none. The application layer falls back
    # to "Compound-{idx+1}" for a placeholder display name AND keeps
    # promote_name_as_identifier off — auto-generated names must never be
    # promoted as identifiers, otherwise re-importing any file without a name
    # column collides on "Compound-1", "Compound-2", ... in the workspace.
    return ParsedMoleculeItem(
        row_index=row_index,
        file_row=file_row,
        name=name,
        smiles=smiles,
        molecule_type=single.get(ColumnTarget.MOLECULE_TYPE) or "small_molecule",
        external_ids=external_ids,
        batch_ids=batch_ids,
        amount_value=_safe_float(single.get(ColumnTarget.AMOUNT_VALUE)),
        amount_unit=single.get(ColumnTarget.AMOUNT_UNIT) or "mg",
        salt_code=single.get(ColumnTarget.SALT_CODE),
        salt_stoichiometry=stoich if stoich is not None else 1,
        purity=_safe_float(single.get(ColumnTarget.PURITY)),
        batch_source=single.get(ColumnTarget.BATCH_SOURCE) or "synthesized",
        appearance=single.get(ColumnTarget.APPEARANCE),
    )


def _check(mapping: ColumnMapping, headers: list[str], *, structure_implied: bool) -> None:
    err = mapping.validate(headers, structure_implied=structure_implied)
    if err is not None:
        raise err


# ---------------------------------------------------------------------------
# SDF Parser (RDKit)
# ---------------------------------------------------------------------------


class SDFParser:
    """Parse SDF/MOL files using RDKit's ForwardSDMolSupplier.

    Columns are the record's properties plus ``SDF_TITLE_HEADER`` (the title line).
    The structure always comes from the record itself.
    """

    def parse(
        self, content: bytes, filename: str, mapping: ColumnMapping | None = None
    ) -> list[ParsedMoleculeItem]:
        mols = list(Chem.ForwardSDMolSupplier(io.BytesIO(content)))
        headers = [SDF_TITLE_HEADER]
        for mol in mols:
            if mol is None:
                continue
            for p in mol.GetPropsAsDict():
                if not p.startswith("_") and p not in headers:
                    headers.append(p)
        if mapping is None:
            mapping = _default_mapping(headers)
        else:
            _check(mapping, headers, structure_implied=True)

        items: list[ParsedMoleculeItem] = []
        for idx, mol in enumerate(mols):
            if mol is None:
                items.append(
                    ParsedMoleculeItem(
                        row_index=idx,
                        file_row=idx + 1,
                        error=f"Record {idx + 1}: structure could not be read",
                    )
                )
                continue

            def get(header: str, mol: Chem.Mol = mol) -> str | None:
                if header == SDF_TITLE_HEADER:
                    return _safe_str(mol.GetProp("_Name")) if mol.HasProp("_Name") else None
                return _safe_str(mol.GetProp(header)) if mol.HasProp(header) else None

            items.append(
                _extract_item(
                    get,
                    mapping,
                    row_index=idx,
                    file_row=idx + 1,
                    structure=Chem.MolToSmiles(mol),
                )
            )
        return items


# ---------------------------------------------------------------------------
# Tabular Parser (CSV / XLSX via pandas)
# ---------------------------------------------------------------------------


class TabularParser:
    """Parse CSV and XLSX files using pandas."""

    def parse(
        self, content: bytes, filename: str, mapping: ColumnMapping | None = None
    ) -> list[ParsedMoleculeItem]:
        fmt = self._detect_format(filename)
        df = self._read_dataframe(content, fmt)
        headers = [str(c) for c in df.columns]
        if mapping is None:
            mapping = _default_mapping(headers)
        else:
            _check(mapping, headers, structure_implied=False)
        df.columns = headers
        items: list[ParsedMoleculeItem] = []
        for idx, row in df.iterrows():
            i = int(idx)  # type: ignore[arg-type]
            items.append(
                _extract_item(
                    lambda h, row=row: _safe_str(row.get(h)),
                    mapping,
                    row_index=i,
                    file_row=i + 2,  # header is row 1
                )
            )
        return items

    def _detect_format(self, filename: str) -> BulkRegistrationFileFormat:
        suffix = Path(filename).suffix.lower()
        if suffix == ".csv":
            return BulkRegistrationFileFormat.CSV
        if suffix in (".xlsx", ".xls"):
            return BulkRegistrationFileFormat.XLSX
        raise ValueError(f"Unsupported file format: {suffix}")

    def _read_dataframe(self, content: bytes, fmt: BulkRegistrationFileFormat) -> pd.DataFrame:
        buf = io.BytesIO(content)
        try:
            if fmt == BulkRegistrationFileFormat.CSV:
                return pd.read_csv(buf, dtype=str, keep_default_na=False)
            return pd.read_excel(buf, dtype=str, keep_default_na=False, engine="openpyxl")
        except pd.errors.EmptyDataError:
            return pd.DataFrame()


def _safe_str(val: object) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _safe_float(val: object) -> float | None:
    """Parse a value to float, returning None on failure."""
    s = _safe_str(val)
    if s is None:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _safe_int(val: object) -> int | None:
    """Parse a value to int, returning None on failure."""
    s = _safe_str(val)
    if s is None:
        return None
    try:
        return int(float(s))  # handles "1.0" style strings
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_parser(file_format: BulkRegistrationFileFormat) -> ChemicalFileParser:
    """Return the appropriate parser for the given file format."""
    if file_format == BulkRegistrationFileFormat.SDF:
        return SDFParser()  # type: ignore[return-value]
    return TabularParser()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Application-port adapter
# ---------------------------------------------------------------------------


class BulkFileParserAdapter:
    """Adapter that satisfies the application BulkFileParserProtocol.

    Bridges the infra ``ChemicalFileParser`` factory and the application
    ``ParsedItemDTO``. Lives in infrastructure so the application layer never
    imports infra modules.
    """

    def parse(
        self,
        *,
        content: bytes,
        filename: str,
        file_format: BulkRegistrationFileFormat,
        column_mapping: ColumnMapping | None = None,
    ) -> list:
        """Raises ``ValidationError`` when ``column_mapping`` doesn't fit the file."""
        from cellar.application.chemical_registration.preview_bulk_registration_file import (
            ParsedItemDTO,
        )

        parser = get_parser(file_format)
        items = parser.parse(content, filename, column_mapping)
        return [
            ParsedItemDTO(
                row_index=i.row_index,
                file_row=i.file_row,
                name=i.name,
                smiles=i.smiles,
                molecule_type=i.molecule_type,
                external_ids=list(i.external_ids),
                batch_ids=list(i.batch_ids),
                amount_value=i.amount_value,
                amount_unit=i.amount_unit,
                salt_code=i.salt_code,
                salt_stoichiometry=i.salt_stoichiometry,
                purity=i.purity,
                batch_source=i.batch_source,
                appearance=i.appearance,
                error=i.error,
            )
            for i in items
        ]
