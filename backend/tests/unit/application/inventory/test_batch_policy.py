from chem_vault.application.inventory.batch_policy import should_create_batch


def test_new_molecule_always_creates_batch_regardless_of_policy():
    assert should_create_batch(is_new_molecule=True, override=None, workspace_default=False) is True
    assert should_create_batch(is_new_molecule=True, override=False, workspace_default=False) is True


def test_duplicate_with_no_override_uses_workspace_default():
    assert should_create_batch(is_new_molecule=False, override=None, workspace_default=False) is False
    assert should_create_batch(is_new_molecule=False, override=None, workspace_default=True) is True


def test_duplicate_with_override_takes_precedence():
    assert should_create_batch(is_new_molecule=False, override=True, workspace_default=False) is True
    assert should_create_batch(is_new_molecule=False, override=False, workspace_default=True) is False
