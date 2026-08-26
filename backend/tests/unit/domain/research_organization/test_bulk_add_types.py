import uuid

from cellar.domain.research_organization.bulk_add_types import (
    BulkAddRow,
    BulkAddResult,
    RowOutcome,
    RowStatus,
)



def test_bulk_add_result_aggregates_counts_from_outcomes():
    mol_id = uuid.uuid4()
    outcomes = [
        RowOutcome(row_index=0, status=RowStatus.RESOLVED, molecule_id=mol_id),
        RowOutcome(row_index=1, status=RowStatus.ALREADY_PRESENT, molecule_id=mol_id),
        RowOutcome(row_index=2, status=RowStatus.UNREGISTERED, message="not found"),
        RowOutcome(row_index=3, status=RowStatus.AMBIGUOUS, candidates=(uuid.uuid4(),)),
        RowOutcome(row_index=4, status=RowStatus.ERROR, message="no usable identifier"),
    ]
    result = BulkAddResult.from_outcomes(outcomes)
    assert result.resolved_count == 1
    assert result.already_present_count == 1
    assert result.unregistered_count == 1
    assert result.ambiguous_count == 1
    assert result.error_count == 1


def test_has_identifier_returns_false_when_only_notes_set():
    row = BulkAddRow(row_index=0, notes="just a comment")
    assert row.has_identifier() is False


def test_has_identifier_returns_false_when_all_fields_unset():
    row = BulkAddRow(row_index=0)
    assert row.has_identifier() is False


def test_has_identifier_returns_true_when_any_identifier_set():
    assert BulkAddRow(row_index=0, registration_number="CC-1").has_identifier() is True
    assert BulkAddRow(row_index=0, smiles="c1ccccc1").has_identifier() is True
    assert BulkAddRow(row_index=0, name="phenol").has_identifier() is True


def test_bulk_add_result_from_empty_outcomes_has_zero_counts():
    result = BulkAddResult.from_outcomes([])
    assert result.resolved_count == 0
    assert result.already_present_count == 0
    assert result.unregistered_count == 0
    assert result.ambiguous_count == 0
    assert result.error_count == 0
    assert result.outcomes == []
