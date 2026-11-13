import uuid

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.domain.screening_assay.enums import HolderKind
from cellar.domain.screening_assay.events import (
    FieldChange,
    PositionChange,
    RunInstrumentFileImported,
    RunPositionsRelabelled,
)
from cellar.domain.screening_assay.holder import position_label


class _Repo:
    def __init__(self):
        self.saved = []

    async def save(self, operation):
        self.saved.append(operation)


async def test_instrument_import_is_audited_with_file_reader_and_counts():
    repo = _Repo()
    await AuditRecordingService(repo).handle_event(
        RunInstrumentFileImported(
            aggregate_id=uuid.uuid4(),
            aggregate_type="Run",
            workspace_id=uuid.uuid4(),
            reader="some-reader",
            file_name="run.xlsx",
            positions=3,
            curves=12,
            readout_values=2,
        )
    )
    (op,) = repo.saved
    assert {e.field_name: e.new_value for e in op.entries} == {
        "event": "RunInstrumentFileImported",
        "file_name": "run.xlsx",
        "reader": "some-reader",
        "positions": "3",
        "curves": "12",
        "readout_values": "2",
    }


async def test_relabelled_positions_are_audited_field_by_field_with_the_reason():
    repo = _Repo()
    run_id = uuid.uuid4()
    label = position_label(HolderKind.CASSETTE, "A", 2)
    await AuditRecordingService(repo).handle_event(
        RunPositionsRelabelled(
            aggregate_id=run_id,
            aggregate_type="Run",
            workspace_id=uuid.uuid4(),
            positions=(
                PositionChange(
                    uuid.uuid4(),
                    label,
                    (
                        FieldChange("label", "x", "y"),
                        FieldChange("concentration", "10.0", "12.5"),
                    ),
                ),
            ),
            reason="typo",
        )
    )
    (op,) = repo.saved
    assert op.reason == "typo" and op.entity_id == run_id
    assert [(e.field_name, e.old_value, e.new_value) for e in op.entries] == [
        ("event", None, "RunPositionsRelabelled"),
        (f"{label}: label", "x", "y"),
        (f"{label}: concentration", "10.0", "12.5"),
    ]
