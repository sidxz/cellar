import uuid

import pytest

from cellar.domain.chemical_registration.cdd_molecule_import import (
    MAX_PROBLEM_LINES,
    CddMoleculeImport,
)
from cellar.domain.chemical_registration.enums import CddImportMode
from cellar.domain.shared.errors import ValidationError


def _processing() -> CddMoleculeImport:
    imp = CddMoleculeImport.create(
        workspace_id=uuid.uuid4(),
        cdd_vault_id="v",
        import_mode=CddImportMode.FULL_VAULT,
        originating_org_id=uuid.uuid4(),
        submitted_by=uuid.uuid4(),
    )
    imp.start_discovery()
    imp.complete_discovery(10)
    return imp


def test_record_report_adds_counts_and_appends_lines() -> None:
    imp = _processing()
    imp.record_report({"compounds_added": 2, "batches_created": 1, "problem_lines": ["a: x"]})
    imp.record_report({"compounds_added": 1, "values_skipped": 3, "problem_lines": ["b: y"]})
    assert imp.report["compounds_added"] == 3
    assert (imp.report["batches_created"], imp.report["values_skipped"]) == (1, 3)
    assert imp.report["problem_lines"] == ["a: x", "b: y"]


def test_problem_lines_stop_at_the_cap_but_counts_keep_going() -> None:
    imp = _processing()
    imp.record_report({"problems": 499, "problem_lines": [f"m{i}: p" for i in range(499)]})
    imp.record_report({"problems": 5, "problem_lines": [f"n{i}: p" for i in range(5)]})
    assert imp.report["problems"] == 504
    assert len(imp.report["problem_lines"]) == MAX_PROBLEM_LINES
    assert imp.report["problem_lines"][-1] == "n0: p"


def test_record_report_needs_a_processing_import() -> None:
    imp = _processing()
    imp.fail("x")
    with pytest.raises(ValidationError):
        imp.record_report({"problems": 1})


def test_stop_reason_round_trips_through_the_import_record() -> None:
    imp = _processing()
    imp.fail("Cancelled by user")
    assert imp.failure_reason == "Cancelled by user"


def test_plate_import_records_its_stop_reason() -> None:
    from cellar.domain.inventory.cdd_plate_import import CddPlateImport

    imp = CddPlateImport.create(
        workspace_id=uuid.uuid4(), cdd_vault_id="v", submitted_by=uuid.uuid4()
    )
    imp.start_discovery()
    imp.fail("Cancelled by user")
    assert imp.failure_reason == "Cancelled by user"
