"""Tests for chemical file parsers (SDF, CSV, XLSX)."""

import io

import pytest

from cellar.domain.chemical_registration.enums import BulkRegistrationFileFormat
from cellar.infrastructure.parsers.chemical_file_parser import (
    SDFParser,
    TabularParser,
    get_parser,
)


# ---------------------------------------------------------------------------
# SDF Parser
# ---------------------------------------------------------------------------


class TestSDFParser:
    def _make_sdf(self, records: list[tuple[str, str, dict[str, str]]]) -> bytes:
        """Build a minimal SDF from (name, smiles, properties) tuples."""
        from rdkit import Chem

        buf = io.StringIO()
        writer = Chem.SDWriter(buf)
        for name, smiles, props in records:
            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                mol.SetProp("_Name", name)
                for k, v in props.items():
                    mol.SetProp(k, v)
                writer.write(mol)
        writer.close()
        return buf.getvalue().encode()

    def test_parse_single_molecule(self) -> None:
        sdf = self._make_sdf([("Aspirin", "CC(=O)Oc1ccccc1C(=O)O", {})])
        parser = SDFParser()
        items = parser.parse(sdf, "test.sdf")

        assert len(items) == 1
        assert items[0].name == "Aspirin"
        assert items[0].smiles is not None
        assert items[0].error is None

    def test_parse_multiple_molecules(self) -> None:
        sdf = self._make_sdf([
            ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O", {}),
            ("Caffeine", "Cn1c(=O)c2c(ncn2C)n(C)c1=O", {}),
        ])
        parser = SDFParser()
        items = parser.parse(sdf, "test.sdf")

        assert len(items) == 2
        assert items[0].name == "Aspirin"
        assert items[1].name == "Caffeine"

    def test_parse_with_cas_number(self) -> None:
        sdf = self._make_sdf([
            ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O", {"CAS_NUMBER": "50-78-2"}),
        ])
        parser = SDFParser()
        items = parser.parse(sdf, "test.sdf")

        assert len(items) == 1
        assert items[0].external_ids == [
            {"identifier": "50-78-2", "identifier_type": "cas_number"}
        ]

    def test_parse_with_vendor_id(self) -> None:
        sdf = self._make_sdf([
            ("Aspirin", "CC(=O)Oc1ccccc1C(=O)O", {"vendor_id": "V-001"}),
        ])
        parser = SDFParser()
        items = parser.parse(sdf, "test.sdf")

        assert len(items) == 1
        assert items[0].external_ids == [
            {"identifier": "V-001", "identifier_type": "vendor_id"}
        ]

    def test_parse_row_indices(self) -> None:
        sdf = self._make_sdf([
            ("A", "C", {}),
            ("B", "CC", {}),
        ])
        parser = SDFParser()
        items = parser.parse(sdf, "test.sdf")

        assert items[0].row_index == 0
        assert items[1].row_index == 1


# ---------------------------------------------------------------------------
# Tabular Parser (CSV / XLSX)
# ---------------------------------------------------------------------------


class TestTabularParser:
    def _make_csv(self, rows: list[dict[str, str]]) -> bytes:
        import pandas as pd

        df = pd.DataFrame(rows)
        return df.to_csv(index=False).encode()

    def _make_xlsx(self, rows: list[dict[str, str]]) -> bytes:
        import pandas as pd

        buf = io.BytesIO()
        df = pd.DataFrame(rows)
        df.to_excel(buf, index=False, engine="openpyxl")
        return buf.getvalue()

    def test_parse_csv_basic(self) -> None:
        csv_bytes = self._make_csv([
            {"name": "Aspirin", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
            {"name": "Caffeine", "smiles": "Cn1c(=O)c2c(ncn2C)n(C)c1=O"},
        ])
        parser = TabularParser()
        items = parser.parse(csv_bytes, "compounds.csv")

        assert len(items) == 2
        assert items[0].name == "Aspirin"
        assert items[0].smiles == "CC(=O)Oc1ccccc1C(=O)O"
        assert items[1].name == "Caffeine"

    def test_parse_xlsx_basic(self) -> None:
        xlsx_bytes = self._make_xlsx([
            {"name": "Aspirin", "smiles": "CC(=O)Oc1ccccc1C(=O)O"},
        ])
        parser = TabularParser()
        items = parser.parse(xlsx_bytes, "compounds.xlsx")

        assert len(items) == 1
        assert items[0].name == "Aspirin"

    def test_parse_with_cas_and_vendor(self) -> None:
        csv_bytes = self._make_csv([
            {
                "name": "Aspirin",
                "smiles": "CC(=O)Oc1ccccc1C(=O)O",
                "cas_number": "50-78-2",
                "vendor_id": "V-001",
            }
        ])
        parser = TabularParser()
        items = parser.parse(csv_bytes, "compounds.csv")

        assert len(items) == 1
        id_types = {eid["identifier_type"] for eid in items[0].external_ids}
        assert "cas_number" in id_types
        assert "vendor_id" in id_types

    def test_parse_column_aliases(self) -> None:
        csv_bytes = self._make_csv([
            {"compound_name": "Aspirin", "canonical_smiles": "CC(=O)Oc1ccccc1C(=O)O"},
        ])
        parser = TabularParser()
        items = parser.parse(csv_bytes, "compounds.csv")

        assert len(items) == 1
        assert items[0].name == "Aspirin"
        assert items[0].smiles == "CC(=O)Oc1ccccc1C(=O)O"

    def test_parse_empty_row_creates_error(self) -> None:
        csv_bytes = self._make_csv([
            {"name": "", "smiles": ""},
        ])
        parser = TabularParser()
        items = parser.parse(csv_bytes, "compounds.csv")

        assert len(items) == 1
        assert items[0].error is not None
        assert "no name or SMILES" in items[0].error

    def test_parse_smiles_only(self) -> None:
        csv_bytes = self._make_csv([
            {"smiles": "CC(=O)Oc1ccccc1C(=O)O"},
        ])
        parser = TabularParser()
        items = parser.parse(csv_bytes, "compounds.csv")

        assert len(items) == 1
        # No name column → parser leaves name None. The application layer
        # supplies a placeholder display name without promoting it as an
        # identifier.
        assert items[0].name is None
        assert items[0].smiles == "CC(=O)Oc1ccccc1C(=O)O"

    def test_parse_molecule_type(self) -> None:
        csv_bytes = self._make_csv([
            {"name": "Peptide-1", "smiles": "CC", "molecule_type": "peptide"},
        ])
        parser = TabularParser()
        items = parser.parse(csv_bytes, "compounds.csv")

        assert items[0].molecule_type == "peptide"

    def test_unsupported_format_raises(self) -> None:
        parser = TabularParser()
        with pytest.raises(ValueError, match="Unsupported file format"):
            parser.parse(b"", "compounds.txt")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestGetParser:
    def test_sdf_returns_sdf_parser(self) -> None:
        parser = get_parser(BulkRegistrationFileFormat.SDF)
        assert isinstance(parser, SDFParser)

    def test_csv_returns_tabular_parser(self) -> None:
        parser = get_parser(BulkRegistrationFileFormat.CSV)
        assert isinstance(parser, TabularParser)

    def test_xlsx_returns_tabular_parser(self) -> None:
        parser = get_parser(BulkRegistrationFileFormat.XLSX)
        assert isinstance(parser, TabularParser)
