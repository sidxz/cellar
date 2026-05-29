import uuid

from cellar.domain.research_organization.bulk_add_types import (
    BulkAddRow,
    BulkAddResult,
    RowOutcome,
    RowStatus,
)


def test_bulk_add_row_carries_optional_identifiers():
    row = BulkAddRow(
        row_index=3,
        registration_number="CC-000001",
        smiles="c1ccccc1O",
        name="phenol",
    )
    assert row.row_index == 3
    assert row.external_id is None
    assert row.notes is None


def test_bulk_add_result_aggregates_counts_from_outcomes():
    mol_id = uuid.uuid4()
    outcomes = [
        RowOutcome(row_index=0, status=RowStatus.RESOLVED, molecule_id=mol_id),
        RowOutcome(row_index=1, status=RowStatus.ALREADY_PRESENT, molecule_id=mol_id),
        RowOutcome(row_index=2, status=RowStatus.UNREGISTERED, message="not found"),
        RowOutcome(row_index=3, status=RowStatus.AMBIGUOUS, candidates=[uuid.uuid4()]),
        RowOutcome(row_index=4, status=RowStatus.ERROR, message="no usable identifier"),
    ]
    result = BulkAddResult.from_outcomes(outcomes)
    assert result.resolved_count == 1
    assert result.already_present_count == 1
    assert result.unregistered_count == 1
    assert result.ambiguous_count == 1
    assert result.error_count == 1
