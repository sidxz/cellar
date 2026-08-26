import uuid
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings



def test_update_cdd_vault_id():
    ws = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
    ws.update(cdd_vault_id="12345")
    assert ws.cdd_vault_id == "12345"


def test_update_cdd_vault_id_to_none():
    ws = WorkspaceSettings.create_default(workspace_id=uuid.uuid4())
    ws.update(cdd_vault_id="12345")
    ws.update(cdd_vault_id=None)
    assert ws.cdd_vault_id is None
