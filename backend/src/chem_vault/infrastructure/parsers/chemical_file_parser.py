"""Chemical file parsers for bulk registration — SDF, CSV, XLSX.

Infrastructure layer. Parses chemical data files into a flat list of
ParsedMoleculeItem dicts that the application layer can feed into the
RegisterMolecule use case.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd
from rdkit import Chem

from chem_vault.domain.chemical_registration.enums import BulkRegistrationFileFormat


@dataclass(frozen=True)
class ParsedMoleculeItem:
    """A single parsed molecule record from a bulk import file."""

    row_index: int
    name: str | None = None
    smiles: str | None = None
    molecule_type: str = "small_molecule"
    external_ids: list[dict[str, str]] = field(default_factory=list)
    custom_fields: dict | None = None
    error: str | None = None


class ChemicalFileParser(Protocol):
    """Protocol for parsing chemical data files."""

    def parse(self, content: bytes, filename: str) -> list[ParsedMoleculeItem]: ...


# ---------------------------------------------------------------------------
# Column name normalization
# ---------------------------------------------------------------------------

_NAME_ALIASES = {"name", "compound_name", "mol_name", "molecule_name", "title"}
_SMILES_ALIASES = {"smiles", "canonical_smiles", "structure", "mol_smiles"}
_TYPE_ALIASES = {"molecule_type", "mol_type", "type"}
_CAS_ALIASES = {"cas", "cas_number", "cas_no"}
_VENDOR_ALIASES = {"vendor_id", "vendor_code", "catalog_number", "catalog_no"}


def _find_column(columns: list[str], aliases: set[str]) -> str | None:
    lower_map = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        if alias in lower_map:
            return lower_map[alias]
    return None


# ---------------------------------------------------------------------------
# SDF Parser (RDKit)
# ---------------------------------------------------------------------------


class SDFParser:
    """Parse SDF/MOL files using RDKit's ForwardSDMolSupplier."""

    def parse(self, content: bytes, filename: str) -> list[ParsedMoleculeItem]:
        items: list[ParsedMoleculeItem] = []
        supplier = Chem.ForwardSDMolSupplier(io.BytesIO(content))

        for idx, mol in enumerate(supplier):
            if mol is None:
                items.append(
                    ParsedMoleculeItem(
                        row_index=idx,
                        error=f"Failed to parse molecule at record {idx}",
                    )
                )
                continue

            smiles = Chem.MolToSmiles(mol)
            name = mol.GetProp("_Name") if mol.HasProp("_Name") else None

            external_ids: list[dict[str, str]] = []
            for prop_name in mol.GetPropsAsDict():
                if prop_name.startswith("_"):
                    continue
                prop_lower = prop_name.lower()
                if prop_lower in _CAS_ALIASES:
                    external_ids.append(
                        {"identifier": str(mol.GetProp(prop_name)), "identifier_type": "cas_number"}
                    )
                elif prop_lower in _VENDOR_ALIASES:
                    external_ids.append(
                        {"identifier": str(mol.GetProp(prop_name)), "identifier_type": "vendor_id"}
                    )

            items.append(
                ParsedMoleculeItem(
                    row_index=idx,
                    name=name or f"Compound-{idx + 1}",
                    smiles=smiles,
                    external_ids=external_ids,
                )
            )

        return items


# ---------------------------------------------------------------------------
# Tabular Parser (CSV / XLSX via pandas)
# ---------------------------------------------------------------------------


class TabularParser:
    """Parse CSV and XLSX files using pandas."""

    def parse(self, content: bytes, filename: str) -> list[ParsedMoleculeItem]:
        fmt = self._detect_format(filename)
        df = self._read_dataframe(content, fmt)
        return self._dataframe_to_items(df)

    def _detect_format(self, filename: str) -> BulkRegistrationFileFormat:
        suffix = Path(filename).suffix.lower()
        if suffix == ".csv":
            return BulkRegistrationFileFormat.CSV
        if suffix in (".xlsx", ".xls"):
            return BulkRegistrationFileFormat.XLSX
        raise ValueError(f"Unsupported file format: {suffix}")

    def _read_dataframe(
        self, content: bytes, fmt: BulkRegistrationFileFormat
    ) -> pd.DataFrame:
        buf = io.BytesIO(content)
        try:
            if fmt == BulkRegistrationFileFormat.CSV:
                return pd.read_csv(buf, dtype=str, keep_default_na=False)
            return pd.read_excel(buf, dtype=str, keep_default_na=False, engine="openpyxl")
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    def _dataframe_to_items(self, df: pd.DataFrame) -> list[ParsedMoleculeItem]:
        columns = list(df.columns)
        name_col = _find_column(columns, _NAME_ALIASES)
        smiles_col = _find_column(columns, _SMILES_ALIASES)
        type_col = _find_column(columns, _TYPE_ALIASES)
        cas_col = _find_column(columns, _CAS_ALIASES)
        vendor_col = _find_column(columns, _VENDOR_ALIASES)

        items: list[ParsedMoleculeItem] = []
        for idx, row in df.iterrows():
            name = _safe_str(row.get(name_col)) if name_col else None
            smiles = _safe_str(row.get(smiles_col)) if smiles_col else None
            mol_type = _safe_str(row.get(type_col)) if type_col else "small_molecule"

            external_ids: list[dict[str, str]] = []
            if cas_col and _safe_str(row.get(cas_col)):
                external_ids.append(
                    {"identifier": _safe_str(row.get(cas_col)), "identifier_type": "cas_number"}  # type: ignore[arg-type]
                )
            if vendor_col and _safe_str(row.get(vendor_col)):
                external_ids.append(
                    {"identifier": _safe_str(row.get(vendor_col)), "identifier_type": "vendor_id"}  # type: ignore[arg-type]
                )

            if not name and not smiles:
                items.append(
                    ParsedMoleculeItem(
                        row_index=int(idx),  # type: ignore[arg-type]
                        error=f"Row {idx}: no name or SMILES provided",
                    )
                )
                continue

            items.append(
                ParsedMoleculeItem(
                    row_index=int(idx),  # type: ignore[arg-type]
                    name=name or f"Compound-{int(idx) + 1}",  # type: ignore[arg-type]
                    smiles=smiles,
                    molecule_type=mol_type or "small_molecule",
                    external_ids=external_ids,
                )
            )

        return items


def _safe_str(val: object) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_parser(file_format: BulkRegistrationFileFormat) -> ChemicalFileParser:
    """Return the appropriate parser for the given file format."""
    if file_format == BulkRegistrationFileFormat.SDF:
        return SDFParser()  # type: ignore[return-value]
    return TabularParser()  # type: ignore[return-value]
