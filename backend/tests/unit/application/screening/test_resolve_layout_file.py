"""Unit tests for ResolveLayoutFile."""

from __future__ import annotations

import io
import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from cellar.application.screening.resolve_layout_file import (
    MAX_LAYOUT_ROWS,
    LayoutFile,
    ResolveLayoutFile,
    ResolveLayoutFileQuery,
)
from cellar.domain.screening_assay.enums import HolderKind, WellType
from cellar.domain.screening_assay.holder import position_label
from cellar.domain.screening_assay.run import Run
from cellar.domain.shared.errors import AuthorizationError, NotFoundError, ValidationError
from cellar.domain.shared.value_objects import BatchNumber, RegistrationNumber
from cellar.infrastructure.parsers.tabular_file import TabularFileParser
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_preview_instrument_file import FakeUoW


def P(n: int) -> str:
    return position_label(HolderKind.CASSETTE, "A", n)


def csv(*lines: str) -> bytes:
    return "\n".join(lines).encode("utf-8")


def _molecule(reg: str, name: str = "Compound") -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, registration_number=RegistrationNumber(value=reg)
    )


def _batch(molecule: SimpleNamespace, number: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), molecule_id=molecule.id, batch_number=BatchNumber(value=number)
    )


HEADER = "Position,Label,Role,Compound,Batch,Concentration,Note"


class Harness:
    def __init__(
        self,
        *,
        by_reg: dict[str, SimpleNamespace] | None = None,
        by_identifier: dict[str, SimpleNamespace] | None = None,
        batches: list[SimpleNamespace] | None = None,
        by_batch_identifier: dict[str, SimpleNamespace] | None = None,
        run_missing: bool = False,
    ) -> None:
        self.auth = FakeAuth()
        self.ws = self.auth.workspace_id
        self.run = Run(
            workspace_id=self.ws,
            protocol_id=uuid.uuid4(),
            run_date=date(2026, 11, 13),
            operator=uuid.uuid4(),
        )
        regs = by_reg or {}
        idents = by_identifier or {}
        all_batches = batches or []
        molecules = {m.id: m for m in (*regs.values(), *idents.values())}
        self.uow = FakeUoW()
        self.run_repo = AsyncMock()
        self.run_repo.find_by_id_in_workspace = AsyncMock(
            return_value=None if run_missing else self.run
        )
        self.molecule_repo = AsyncMock()
        self.molecule_repo.find_by_registration_number = AsyncMock(
            side_effect=lambda ws, text: regs.get(text)
        )
        self.molecule_repo.find_by_identifier = AsyncMock(
            side_effect=lambda ws, text: idents.get(text)
        )
        self.molecule_repo.find_by_id_in_workspace = AsyncMock(
            side_effect=lambda ws, id: molecules.get(id)
        )
        self.batch_repo = AsyncMock()
        self.batch_repo.find_by_molecule = AsyncMock(
            side_effect=lambda ws, mid: [b for b in all_batches if b.molecule_id == mid]
        )
        self.batch_repo.find_by_batch_number = AsyncMock(
            side_effect=lambda ws, text: next(
                (b for b in all_batches if b.batch_number.value == text), None
            )
        )
        bid = by_batch_identifier or {}
        self.batch_repo.find_by_external_identifier = AsyncMock(
            side_effect=lambda ws, text: bid.get(text)
        )
        self.uc = ResolveLayoutFile(
            uow=self.uow,
            run_repo=self.run_repo,
            molecule_repo=self.molecule_repo,
            batch_repo=self.batch_repo,
            parser=TabularFileParser(),
        )

    def query(self, content: bytes, filename: str = "layout.csv") -> ResolveLayoutFileQuery:
        return ResolveLayoutFileQuery(
            workspace_id=self.ws, run_id=self.run.id, filename=filename, content=content
        )

    async def __call__(self, content: bytes, filename: str = "layout.csv", auth=None):  # type: ignore[no-untyped-def]
        return await self.uc(self.query(content, filename), auth=auth or self.auth)

    async def ok(self, content: bytes, filename: str = "layout.csv") -> LayoutFile:
        out = (await self(content, filename)).unwrap()
        self.assert_nothing_written()
        return out

    def assert_nothing_written(self) -> None:
        assert self.uow.committed is False


async def test_resolves_compound_by_registration_number_then_identifier():
    mol_a, mol_b = _molecule("REG-0001", "A"), _molecule("REG-0002", "B")
    h = Harness(by_reg={"REG-0001": mol_a}, by_identifier={"ABC-0000001": mol_b})
    out = await h.ok(csv(HEADER, f"{P(1)},,,REG-0001,,,", f"{P(2)},,,ABC-0000001,,,"))
    assert [r.compound.molecule_id for r in out.rows] == [mol_a.id, mol_b.id]  # type: ignore[union-attr]
    first = out.rows[0].compound
    assert first is not None
    assert (first.molecule_name, first.registration_number) == ("A", "REG-0001")
    assert out.rows[1].compound.registration_number == "REG-0002"  # type: ignore[union-attr]
    h.molecule_repo.find_by_identifier.assert_awaited_once_with(h.ws, "ABC-0000001")


async def test_compound_with_one_batch_gets_it_and_with_several_needs_a_choice():
    m1, m2, m3 = _molecule("REG-0001"), _molecule("REG-0002"), _molecule("REG-0003")
    only = _batch(m1, "B-1")
    h = Harness(
        by_reg={"REG-0001": m1, "REG-0002": m2, "REG-0003": m3},
        batches=[only, _batch(m2, "B-2"), _batch(m2, "B-3")],
    )
    out = await h.ok(
        csv(HEADER, f"{P(1)},,,REG-0001,,,", f"{P(2)},,,REG-0002,,,", f"{P(3)},,,REG-0003,,,")
    )
    one, many, none = (r.compound for r in out.rows)
    assert one is not None and many is not None and none is not None
    assert (one.batch_id, one.batch_number, one.needs_batch_choice) == (only.id, "B-1", False)
    assert (many.batch_id, many.batch_number, many.needs_batch_choice) == (None, None, True)
    assert (none.batch_id, none.needs_batch_choice) == (None, False)


async def test_batch_is_resolved_by_number_or_registered_identifier_and_brings_its_compound():
    m1, m2 = _molecule("REG-0001", "One"), _molecule("REG-0002", "Two")
    b1, b2 = _batch(m1, "B-1"), _batch(m2, "B-2")
    h = Harness(
        by_reg={"REG-0001": m1, "REG-0002": m2},
        batches=[b1, b2],
        by_batch_identifier={"EXT-9": b2},
    )
    out = await h.ok(csv(HEADER, f"{P(1)},,,,B-1,,", f"{P(2)},,,,EXT-9,,"))
    c1, c2 = (r.compound for r in out.rows)
    assert c1 is not None and c2 is not None
    assert (c1.molecule_id, c1.registration_number, c1.batch_id, c1.batch_number) == (
        m1.id,
        "REG-0001",
        b1.id,
        "B-1",
    )
    assert (c2.molecule_id, c2.molecule_name, c2.batch_id, c2.batch_number) == (
        m2.id,
        "Two",
        b2.id,
        "B-2",
    )
    assert not c1.needs_batch_choice and not c2.needs_batch_choice
    assert all(r.problems == () for r in out.rows)


async def test_compound_and_its_own_batch_fill_together():
    m1 = _molecule("REG-0001")
    b1 = _batch(m1, "B-1")
    h = Harness(by_reg={"REG-0001": m1}, batches=[b1, _batch(m1, "B-2")])
    (row,) = (await h.ok(csv(HEADER, f"{P(1)},,,REG-0001,B-1,,"))).rows
    assert row.compound is not None
    assert (row.compound.batch_id, row.compound.needs_batch_choice, row.problems) == (
        b1.id,
        False,
        (),
    )


async def test_batch_of_another_compound_is_a_problem_and_other_columns_still_fill():
    m1, m2 = _molecule("REG-0001"), _molecule("REG-0002")
    h = Harness(by_reg={"REG-0001": m1, "REG-0002": m2}, batches=[_batch(m2, "B-2")])
    out = await h.ok(csv(HEADER, f"{P(1)},x,Reference,REG-0001,B-2,5,"))
    (row,) = out.rows
    assert row.compound is None and "does not belong" in row.problems[0]
    assert row.problems == ("Batch 'B-2' does not belong to compound 'REG-0001'",)
    assert (row.label, row.dose, row.well_type) == ("x", 5.0, WellType.REFERENCE)


async def test_compound_or_batch_not_found_is_a_problem():
    h = Harness()
    out = await h.ok(csv(HEADER, f"{P(1)},x,,NOPE,,,", f"{P(2)},y,,,B-404,,"))
    assert [r.problems for r in out.rows] == [
        ("Compound 'NOPE' was not found",),
        ("Batch 'B-404' was not found",),
    ]
    assert [(r.compound, r.label) for r in out.rows] == [(None, "x"), (None, "y")]


@pytest.mark.parametrize(
    "column,cell,word",
    [
        ("Role", "Standard", "Unknown role"),
        ("Concentration", "-1", "0 or more"),
        ("Concentration", "abc", "0 or more"),
        ("Concentration", "nan", "0 or more"),
        ("Concentration", "1_000", "0 or more"),
        ("Concentration", "\u0661\u0662", "0 or more"),
        ("Label", "x" * 201, "200"),
        ("Note", "n" * 1001, "1000"),
        ("Use", "maybe", "Yes or No"),
    ],
)
async def test_unknown_role_bad_concentration_long_label_long_note_are_row_problems(
    column, cell, word
):
    good = {"Label": "lbl", "Role": "Sample", "Concentration": "3", "Note": "nt", "Use": "Yes"}
    values = {**good, column: cell}
    names = list(good)
    h = Harness()
    out = await h.ok(
        csv("Position," + ",".join(names), P(1) + "," + ",".join(values[n] for n in names))
    )
    (row,) = out.rows
    assert len(row.problems) == 1 and word in row.problems[0]
    got = {
        "Label": row.label,
        "Role": row.well_type,
        "Concentration": row.dose,
        "Note": row.note,
        "Use": row.use,
    }
    want = {
        "Label": "lbl",
        "Role": WellType.SAMPLE,
        "Concentration": 3.0,
        "Note": "nt",
        "Use": True,
    }
    assert got == {**want, column: None}
    assert row.position == P(1)


async def test_unknown_role_message_names_the_roles():
    h = Harness()
    (row,) = (await h.ok(csv("Position,Role", f"{P(1)},Standard"))).rows
    assert row.problems == (
        "Unknown role 'Standard'. "
        "Use Sample, Reference, Blank, Positive control or Negative control",
    )


async def test_empty_cells_are_none():
    h = Harness()
    out = await h.ok(
        csv("Position,Label,Role,Compound,Batch,Concentration,Note", f"{P(1)},,,,,12.5,")
    )
    (row,) = out.rows
    assert (row.label, row.note, row.well_type, row.compound, row.use, row.problems) == (
        None,
        None,
        None,
        None,
        None,
        (),
    )
    assert row.dose == 12.5 and row.position == P(1)
    h.molecule_repo.find_by_identifier.assert_not_awaited()
    h.batch_repo.find_by_batch_number.assert_not_awaited()


async def test_role_names_are_matched_in_any_case():
    h = Harness()
    out = await h.ok(
        csv(
            "Position,Role",
            f"{P(1)},positive CONTROL",
            f"{P(2)},  negative   control ",
            f"{P(3)},BLANK",
        )
    )
    assert [r.well_type for r in out.rows] == [
        WellType.POSITIVE_CONTROL,
        WellType.NEGATIVE_CONTROL,
        WellType.BLANK,
    ]


async def test_concentration_header_with_a_unit_is_recognised_and_unknown_headers_are_reported():
    h = Harness()
    out = await h.ok(csv(" position ,Concentration (µM),Plate", f" {P(1)} ,7.5,P1"))
    (row,) = out.rows
    assert (row.position, row.dose) == (P(1), 7.5)
    assert out.unrecognised_columns == ("Plate",)


async def test_use_column_yes_and_no():
    h = Harness()
    out = await h.ok(csv("Position,Use", f"{P(1)},Yes", f"{P(2)},no", f"{P(3)},"))
    assert [r.use for r in out.rows] == [True, False, None]


async def test_one_lookup_per_distinct_compound_and_batch_text():
    m1 = _molecule("REG-0001")
    b1 = _batch(m1, "B-1")
    h = Harness(by_identifier={"ABC-0000001": m1}, batches=[b1])
    lines = [f"{P(n)},,,ABC-0000001,,," for n in range(1, 4)] + [
        f"{P(n)},,,,B-1,," for n in range(4, 7)
    ]
    out = await h.ok(csv(HEADER, *lines))
    assert all(r.compound is not None and r.compound.batch_id == b1.id for r in out.rows)
    assert h.molecule_repo.find_by_registration_number.await_count == 1
    assert h.molecule_repo.find_by_identifier.await_count == 1
    assert h.batch_repo.find_by_batch_number.await_count == 1
    assert h.batch_repo.find_by_molecule.await_count == 1


async def test_spreadsheet_file_is_read_from_its_active_sheet():
    wb = Workbook()
    wb.active.title = "Layout"  # type: ignore[union-attr]
    wb.active.append(["Position", "Label", "Concentration (µM)"])  # type: ignore[union-attr]
    wb.active.append([P(1), "first", 2.5])  # type: ignore[union-attr]
    other = wb.create_sheet("Other")
    other.append(["Nothing"])
    buf = io.BytesIO()
    wb.save(buf)
    h = Harness()
    (row,) = (await h.ok(buf.getvalue(), "layout.xlsx")).rows
    assert (row.position, row.label, row.dose) == (P(1), "first", 2.5)


async def test_the_apostrophe_a_template_puts_before_a_formula_character_is_dropped():
    """The downloaded template writes ' before a text cell that starts with = + - or @, so
    a spreadsheet does not read it as a formula. Read back, the file means the same."""
    m1 = _molecule("=REG-1")
    b1 = _batch(m1, "-B-1")
    h = Harness(by_reg={"=REG-1": m1}, batches=[b1, _batch(m1, "-B-2")])
    long_label = "=" + "x" * 199
    out = await h.ok(
        csv(HEADER, f"'+{P(1)},'{long_label},,'=REG-1,'-B-1,,'@note", f"{P(2)},'plain,,,,,")
    )
    first, second = out.rows
    assert (first.position, first.label, first.note, first.problems) == (
        f"+{P(1)}",
        long_label,
        "@note",
        (),
    )
    assert first.compound is not None and first.compound.batch_id == b1.id
    assert second.label == "'plain"


async def test_missing_position_column_is_validation_error():
    h = Harness()
    failure = (await h(csv("Label,Note", "x,y"))).failure()
    assert isinstance(failure, ValidationError)
    assert str(failure) == "The file has no Position column"


async def test_unparseable_file_is_validation_error():
    h = Harness()
    failure = (await h(b"")).failure()
    assert isinstance(failure, ValidationError) and "empty" in str(failure)


async def test_file_over_20_mb_is_validation_error():
    h = Harness()
    failure = (await h(b"x" * (20 * 1024 * 1024 + 1))).failure()
    assert isinstance(failure, ValidationError) and str(failure) == "File is larger than 20 MB"


async def test_too_many_rows_is_validation_error():
    h = Harness()
    lines = [f"P{n}" for n in range(MAX_LAYOUT_ROWS + 1)]
    failure = (await h(csv("Position", *lines))).failure()
    assert isinstance(failure, ValidationError) and str(MAX_LAYOUT_ROWS) in str(failure)


async def test_too_many_rows_is_refused_without_building_every_row():
    built: list[int] = []

    class CountingParser(TabularFileParser):
        def parse(self, content: bytes, filename: str = "", max_rows: int | None = None):  # type: ignore[no-untyped-def]
            table = super().parse(content, filename, max_rows=max_rows)
            built.append(table.row_count)
            return table

    h = Harness()
    h.uc._parser = CountingParser()
    lines = [f"P{n}" for n in range(MAX_LAYOUT_ROWS * 5)]
    failure = (await h(csv("Position", *lines))).failure()
    assert isinstance(failure, ValidationError) and str(MAX_LAYOUT_ROWS) in str(failure)
    assert built == [MAX_LAYOUT_ROWS + 1]


async def test_run_not_found():
    h = Harness(run_missing=True)
    failure = (await h(csv("Position", P(1)))).failure()
    assert isinstance(failure, NotFoundError)
    h.run_repo.find_by_id_in_workspace.assert_awaited_once_with(h.ws, h.run.id)


async def test_viewer_raises_authorization_error():
    h = Harness()
    with pytest.raises(AuthorizationError):
        await h(csv("Position", P(1)), auth=FakeAuth(role="viewer", workspace_id=h.ws))
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()


async def test_other_workspace_raises_not_found():
    h = Harness()
    with pytest.raises(NotFoundError):
        await h(csv("Position", P(1)), auth=FakeAuth())
    h.run_repo.find_by_id_in_workspace.assert_not_awaited()
