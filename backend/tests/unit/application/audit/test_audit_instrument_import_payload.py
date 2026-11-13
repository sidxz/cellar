import uuid

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.domain.screening_assay.events import RunInstrumentFileImported


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
