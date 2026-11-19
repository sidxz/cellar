"""Chemical file parsers for bulk registration — SDF, CSV, XLSX.

Infrastructure layer. Parses chemical data files into a flat list of
ParsedMoleculeItem dicts that the application layer can feed into the
RegisterMolecule use case.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Protocol

import pandas as pd
from rdkit import Chem

from cellar.application.chemical_registration.bulk_column_mapping import (
    SDF_TITLE_HEADER,
    ColumnMapping,
    extract_row,
    suggest_column_mapping,
)
from cellar.domain.chemical_registration.enums import BulkRegistrationFileFormat
from cellar.domain.shared.errors import ValidationError


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
    # The compound registers but this row gets no batch (e.g. a batch ID shared by
    # several compounds of the file).
    batch_problem: str | None = None
    # Values the row had but that are not stored (e.g. too long for an ID).
    warnings: list[str] = field(default_factory=list)
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

    def headers(self, content: bytes, filename: str) -> list[str]: ...


# ---------------------------------------------------------------------------
# Mapping-driven row extraction (shared by the SDF and tabular parsers)
# ---------------------------------------------------------------------------


def _default_mapping(headers: list[str]) -> ColumnMapping:
    """No mapping sent: the suggestions, stored with today's sources (synonym and
    batch-ID headers are read too; see ``bulk_column_mapping``)."""
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
    row = extract_row(get, mapping, structure=structure)
    if row is None:
        return ParsedMoleculeItem(
            row_index=row_index,
            file_row=file_row,
            error=f"Row {file_row}: no name or structure",
        )
    # A name left as None is filled "Compound-{idx+1}" by the application layer, which
    # keeps promote_name_as_identifier off — auto-generated names must never be
    # promoted as identifiers, or re-importing a file without a name column collides.
    return ParsedMoleculeItem(row_index=row_index, file_row=file_row, **asdict(row))


def _compound_key(it: ParsedMoleculeItem) -> str | None:
    """Which compound a row is, as the run will see it: its structure (canonical SMILES
    standing in for the InChIKey), else its name. Two names of one structure are one
    compound."""
    # ponytail: no salt stripping, so a salt form and its parent count as two compounds
    # here; use the registration's StructureProcessor if that ever flags a real file.
    if it.smiles:
        mol = Chem.MolFromSmiles(it.smiles)
        return "smiles:" + (Chem.MolToSmiles(mol) if mol is not None else it.smiles)
    return f"name:{it.name}" if it.name else None


def _flag_shared_batch_ids(items: list[ParsedMoleculeItem]) -> list[ParsedMoleculeItem]:
    """A batch ID on rows of different compounds of one file can't be unique in the
    workspace (e.g. a bare "001" column): every such row registers its compound but
    gets no batch."""
    keys_by_id: dict[str, set[str]] = {}
    for it in items:
        if it.error or not it.batch_ids:
            continue
        key = _compound_key(it)
        if not key:
            continue
        for b in it.batch_ids:
            keys_by_id.setdefault(b["identifier"], set()).add(key)
    shared = {i: len(k) for i, k in keys_by_id.items() if len(k) > 1}
    if not shared:
        return items
    out: list[ParsedMoleculeItem] = []
    for it in items:
        hit = next((b["identifier"] for b in it.batch_ids if b["identifier"] in shared), None)
        out.append(
            replace(
                it,
                batch_problem=f"{hit} is on {shared[hit]} compounds. Batch IDs must be unique "
                "in the workspace. Map the column with the full batch name instead.",
            )
            if hit is not None and not it.error
            else it
        )
    return out


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

    @staticmethod
    def _headers(mols: list[Chem.Mol | None]) -> list[str]:
        headers = [SDF_TITLE_HEADER]
        for mol in mols:
            if mol is None:
                continue
            for p in mol.GetPropsAsDict():
                if not p.startswith("_") and p not in headers:
                    headers.append(p)
        return headers

    def headers(self, content: bytes, filename: str) -> list[str]:
        return self._headers(list(Chem.ForwardSDMolSupplier(io.BytesIO(content))))

    def parse(
        self, content: bytes, filename: str, mapping: ColumnMapping | None = None
    ) -> list[ParsedMoleculeItem]:
        mols = list(Chem.ForwardSDMolSupplier(io.BytesIO(content)))
        headers = self._headers(mols)
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
        return _flag_shared_batch_ids(items)


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
        headers = _trimmed(df.columns)
        if mapping is None:
            mapping = _default_mapping(headers)
        else:
            _check(mapping, headers, structure_implied=False)
        df.columns = headers
        items: list[ParsedMoleculeItem] = []
        for idx, row in df.iterrows():
            i = int(idx)

            def get(header: str, row: pd.Series = row) -> str | None:
                return _safe_str(row.get(header))

            items.append(
                _extract_item(
                    get,
                    mapping,
                    row_index=i,
                    file_row=i + 2,  # header is row 1
                )
            )
        return _flag_shared_batch_ids(items)

    def headers(self, content: bytes, filename: str) -> list[str]:
        """The header row only (no rows read)."""
        buf = io.BytesIO(content)
        fmt = self._detect_format(filename)
        try:
            if fmt == BulkRegistrationFileFormat.CSV:
                df = pd.read_csv(buf, dtype=str, keep_default_na=False, nrows=0)
            else:
                df = pd.read_excel(
                    buf, dtype=str, keep_default_na=False, engine="openpyxl", nrows=0
                )
        except pd.errors.EmptyDataError:
            return []
        return _trimmed(df.columns)

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


def _trimmed(columns: pd.Index) -> list[str]:
    """Header cells, trimmed: exports often pad them and the wizard shows them trimmed.
    Two that are the same once trimmed can't be told apart, so the file is refused."""
    seen: dict[str, str] = {}
    for raw in map(str, columns):
        h = raw.strip()
        if h in seen:
            raise ValidationError(
                f"Columns {seen[h]!r} and {raw!r} have the same name once spaces are "
                "trimmed; rename one"
            )
        seen[h] = raw
    return list(seen)


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


# ---------------------------------------------------------------------------
# Application-port adapter
# ---------------------------------------------------------------------------


class BulkFileParserAdapter:
    """Adapter that satisfies the application BulkFileParserProtocol.

    Bridges the infra ``ChemicalFileParser`` factory and the application
    ``ParsedItemDTO``. Lives in infrastructure so the application layer never
    imports infra modules.
    """

    def headers(
        self, *, content: bytes, filename: str, file_format: BulkRegistrationFileFormat
    ) -> list[str]:
        """The file's column names, without parsing its rows. Raises ``ValidationError``
        when two are the same once trimmed."""
        return get_parser(file_format).headers(content, filename)

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
                batch_problem=i.batch_problem,
                warnings=list(i.warnings),
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
