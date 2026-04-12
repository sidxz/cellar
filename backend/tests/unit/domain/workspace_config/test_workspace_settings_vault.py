import uuid
from chem_vault.domain.workspace_config.workspace_settings import WorkspaceSettings


def test_create_default_has_no_external_vault_id():
    ws = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
    assert ws.external_vault_id is None


def test_update_external_vault_id():
    ws = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
    ws.update(external_vault_id="12345")
    assert ws.external_vault_id == "12345"


def test_update_external_vault_id_to_none():
    ws = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
    ws.update(external_vault_id="12345")
    ws.update(external_vault_id=None)
    assert ws.external_vault_id is None
