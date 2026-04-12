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

    def parse(self, content: bytes, filename: str) -> list[ParsedMoleculeItem]: ...


# ---------------------------------------------------------------------------
# Column name normalization
# ---------------------------------------------------------------------------

_NAME_ALIASES = {"name", "compound_name", "mol_name", "molecule_name", "title"}
_SMILES_ALIASES = {"smiles", "canonical_smiles", "structure", "mol_smiles"}
_TYPE_ALIASES = {"molecule_type", "mol_type", "type"}
_CAS_ALIASES = {"cas", "cas_number", "cas_no"}
_VENDOR_ALIASES = {"vendor_id", "vendor_code", "catalog_number", "catalog_no"}
_CHEMBL_ALIASES = {"chembl_id", "chembl"}
_PUBCHEM_ALIASES = {"pubchem_cid", "pubchem", "pubchem_id"}
_CUSTOM_ID_PREFIX = "custom_id"  # custom_id, custom_id_1, custom_id_2, etc.

# Batch-related column aliases
_AMOUNT_ALIASES = {"amount", "amount_value", "quantity"}
_AMOUNT_UNIT_ALIASES = {"amount_unit", "unit"}
_SALT_CODE_ALIASES = {"salt", "salt_code", "salt_form"}
_SALT_STOICH_ALIASES = {"salt_stoichiometry", "stoichiometry"}
_PURITY_ALIASES = {"purity", "purity_percent"}
_BATCH_SOURCE_ALIASES = {"source", "batch_source"}
_APPEARANCE_ALIASES = {"appearance"}


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
            # Batch fields from SDF properties
            amount_value: float | None = None
            amount_unit: str = "mg"
            salt_code: str | None = None
            salt_stoichiometry: int = 1
            purity: float | None = None
            batch_source: str = "synthesized"
            appearance: str | None = None

            for prop_name in mol.GetPropsAsDict():
                if prop_name.startswith("_"):
                    continue
                prop_lower = prop_name.lower()
                val = str(mol.GetProp(prop_name)).strip()
                if not val:
                    continue
                if prop_lower in _CAS_ALIASES:
                    external_ids.append({"identifier": val, "identifier_type": "cas_number"})
                elif prop_lower in _VENDOR_ALIASES:
                    external_ids.append({"identifier": val, "identifier_type": "vendor_id"})
                elif prop_lower in _CHEMBL_ALIASES:
                    external_ids.append({"identifier": val, "identifier_type": "chembl_id"})
                elif prop_lower in _PUBCHEM_ALIASES:
                    external_ids.append({"identifier": val, "identifier_type": "pubchem_cid"})
                elif prop_lower.startswith(_CUSTOM_ID_PREFIX):
                    external_ids.append({"identifier": val, "identifier_type": "custom"})
                elif prop_lower in _AMOUNT_ALIASES:
                    amount_value = _safe_float(val)
                elif prop_lower in _AMOUNT_UNIT_ALIASES:
                    amount_unit = val or "mg"
                elif prop_lower in _SALT_CODE_ALIASES:
                    salt_code = val or None
                elif prop_lower in _SALT_STOICH_ALIASES:
                    salt_stoichiometry = _safe_int(val) or 1
                elif prop_lower in _PURITY_ALIASES:
                    purity = _safe_float(val)
                elif prop_lower in _BATCH_SOURCE_ALIASES:
                    batch_source = val or "synthesized"
                elif prop_lower in _APPEARANCE_ALIASES:
                    appearance = val or None

            items.append(
                ParsedMoleculeItem(
                    row_index=idx,
                    name=name or f"Compound-{idx + 1}",
                    smiles=smiles,
                    external_ids=external_ids,
                    amount_value=amount_value,
                    amount_unit=amount_unit,
                    salt_code=salt_code,
                    salt_stoichiometry=salt_stoichiometry,
                    purity=purity,
                    batch_source=batch_source,
                    appearance=appearance,
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
        chembl_col = _find_column(columns, _CHEMBL_ALIASES)
        pubchem_col = _find_column(columns, _PUBCHEM_ALIASES)

        # Batch-related columns
        amount_col = _find_column(columns, _AMOUNT_ALIASES)
        amount_unit_col = _find_column(columns, _AMOUNT_UNIT_ALIASES)
        salt_code_col = _find_column(columns, _SALT_CODE_ALIASES)
        salt_stoich_col = _find_column(columns, _SALT_STOICH_ALIASES)
        purity_col = _find_column(columns, _PURITY_ALIASES)
        batch_source_col = _find_column(columns, _BATCH_SOURCE_ALIASES)
        appearance_col = _find_column(columns, _APPEARANCE_ALIASES)

        # Detect custom_id columns: custom_id, custom_id_1, custom_id_2, ...
        lower_map = {c.lower().strip(): c for c in columns}
        custom_cols = [
            lower_map[k] for k in sorted(lower_map)
            if k.startswith(_CUSTOM_ID_PREFIX)
        ]

        # Map of (column, identifier_type) for all recognized ID columns
        id_columns: list[tuple[str | None, str]] = [
            (cas_col, "cas_number"),
            (vendor_col, "vendor_id"),
            (chembl_col, "chembl_id"),
            (pubchem_col, "pubchem_cid"),
        ]
        for cc in custom_cols:
            id_columns.append((cc, "custom"))

        items: list[ParsedMoleculeItem] = []
        for idx, row in df.iterrows():
            name = _safe_str(row.get(name_col)) if name_col else None
            smiles = _safe_str(row.get(smiles_col)) if smiles_col else None
            mol_type = _safe_str(row.get(type_col)) if type_col else "small_molecule"

            external_ids: list[dict[str, str]] = []
            for col, id_type in id_columns:
                if col is not None:
                    val = _safe_str(row.get(col))
                    if val:
                        external_ids.append({"identifier": val, "identifier_type": id_type})

            # Batch fields
            amount_value = _safe_float(row.get(amount_col)) if amount_col else None
            amount_unit = _safe_str(row.get(amount_unit_col)) if amount_unit_col else "mg"
            salt_code = _safe_str(row.get(salt_code_col)) if salt_code_col else None
            salt_stoich = _safe_int(row.get(salt_stoich_col)) if salt_stoich_col else 1
            purity = _safe_float(row.get(purity_col)) if purity_col else None
            batch_source = _safe_str(row.get(batch_source_col)) if batch_source_col else "synthesized"
            appearance = _safe_str(row.get(appearance_col)) if appearance_col else None

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
                    amount_value=amount_value,
                    amount_unit=amount_unit or "mg",
                    salt_code=salt_code,
                    salt_stoichiometry=salt_stoich if salt_stoich is not None else 1,
                    purity=purity,
                    batch_source=batch_source or "synthesized",
                    appearance=appearance,
                )
            )

        return items


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
