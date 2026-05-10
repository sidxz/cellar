"""Tests for DataSource aggregate."""

import uuid

from chem_vault.domain.workspace_config.data_source import DataSource


class TestCreateBatchOnDuplicate:
    def test_defaults_to_false_when_key_absent(self) -> None:
        ds = DataSource(
            workspace_id=uuid.uuid4(),
            name="CDD Vault",
            source_type="cdd_vault",
            config={},
            created_by=uuid.uuid4(),
        )
        assert ds.create_batch_on_duplicate is False

    def test_returns_true_when_configured(self) -> None:
        ds = DataSource(
            workspace_id=uuid.uuid4(),
            name="CDD Vault",
            source_type="cdd_vault",
            config={"create_batch_on_duplicate": True},
            created_by=uuid.uuid4(),
        )
        assert ds.create_batch_on_duplicate is True

    def test_returns_false_when_explicitly_false_alongside_other_keys(self) -> None:
        ds = DataSource(
            workspace_id=uuid.uuid4(),
            name="CDD Vault",
            source_type="cdd_vault",
            config={"create_batch_on_duplicate": False, "vault_id": "12345"},
            created_by=uuid.uuid4(),
        )
        assert ds.create_batch_on_duplicate is False
