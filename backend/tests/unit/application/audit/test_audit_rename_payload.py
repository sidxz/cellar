import uuid

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.domain.audit_compliance.enums import AuditAction
from cellar.domain.screening_assay.events import ProtocolRenamed


class _Repo:
    def __init__(self):
        self.saved = []

    async def save(self, operation):
        self.saved.append(operation)


async def test_rename_is_audited_with_old_new_and_reason():
    repo = _Repo()
    await AuditRecordingService(repo).handle_event(
        ProtocolRenamed(
            aggregate_id=uuid.uuid4(),
            aggregate_type="Protocol",
            workspace_id=uuid.uuid4(),
            old_name="A",
            new_name="B",
            reason="Registry renamed PptT",
        )
    )
    (op,) = repo.saved
    assert op.reason == "Registry renamed PptT"
    change = next(e for e in op.entries if e.field_name == "name")
    assert (change.action, change.old_value, change.new_value) == (AuditAction.UPDATE, "A", "B")
