"""Flat export formats (CSV, SDF) carry the protocol code; they have no group row."""

from cellar.application.export.row_streams.base import ColumnSpec


def test_flat_header_carries_the_protocol_code():
    col = ColumnSpec(
        key="k",
        header="IC50",
        kind="number",
        unit="uM",
        group="PRT-00042 PptT inhibition [FP]",
        group_code="PRT-00042",
    )
    assert col.flat_header == "IC50 (uM) [PRT-00042]"


def test_flat_header_without_group_is_the_display_header():
    assert ColumnSpec(key="k", header="Name", kind="text").flat_header == "Name"
