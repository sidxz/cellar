"""A failed CDD import that saved its export picks up where it stopped."""

import uuid

import pytest

from cellar.domain.chemical_registration.cdd_molecule_import import (
    TERMINAL_STATUSES,
    CddMoleculeImport,
)
from cellar.domain.chemical_registration.enums import CddImportMode, CddMoleculeImportStatus
from cellar.domain.chemical_registration.events import CddMoleculeImportResumed
from cellar.domain.shared.errors import ValidationError

USER = uuid.uuid4()
SETTINGS = {"registration_mapping": [{"header": "name", "target": "name"}], "max_molecules": None}


def _processing(
    *, export_id: int | None = 82939461, settings: dict | None = SETTINGS
) -> CddMoleculeImport:
    imp = CddMoleculeImport.create(
        workspace_id=uuid.uuid4(),
        cdd_vault_id="4443",
        import_mode=CddImportMode.FULL_VAULT,
        originating_org_id=uuid.uuid4(),
        submitted_by=uuid.uuid4(),
        workflow_id="wf-1",
        run_settings=settings,
    )
    imp.start_discovery()
    imp.complete_discovery(489425, export_id=export_id)
    return imp


def _failed(**kwargs) -> CddMoleculeImport:
    imp = _processing(**kwargs)
    imp.record_registered(49455)
    imp.update_offset(50750)
    imp.fail("chunk failed")
    imp.clear_events()
    return imp


def test_a_failed_import_with_its_export_resumes_on_a_new_workflow() -> None:
    imp = _failed()
    assert imp.resumable
    assert imp.failure_reason == "chunk failed"

    imp.resume("wf-2", resumed_by=USER)

    assert imp.status is CddMoleculeImportStatus.PROCESSING
    assert imp.failure_reason is None
    assert (imp.workflow_id, imp.completed_at, imp.last_processed_offset) == ("wf-2", None, 50750)
    (event,) = imp.collect_events()
    assert isinstance(event, CddMoleculeImportResumed)
    assert (event.workflow_id, event.resumed_by, event.from_offset) == ("wf-2", USER, 50750)


def test_resumed_import_keeps_counting_and_can_complete() -> None:
    imp = _failed()
    imp.resume("wf-2", resumed_by=USER)

    imp.record_registered(10)
    imp.complete()

    assert imp.registered_count == 49465
    assert imp.status is CddMoleculeImportStatus.COMPLETED


@pytest.mark.parametrize(("export_id", "settings"), [(None, SETTINGS), (7, None)])
def test_an_import_without_export_or_settings_is_not_resumable(
    export_id: int | None, settings: dict | None
) -> None:
    imp = _failed(export_id=export_id, settings=settings)

    assert not imp.resumable
    with pytest.raises(ValidationError):
        imp.resume("wf-2", resumed_by=USER)


def test_only_a_failed_import_resumes() -> None:
    running = _processing()
    done = _processing()
    done.complete()

    for imp in (running, done):
        assert not imp.resumable
        with pytest.raises(ValidationError):
            imp.resume("wf-2", resumed_by=USER)


def test_failed_stays_terminal() -> None:
    assert "failed" in TERMINAL_STATUSES
