"""Unit tests for ExternalApiKey aggregate."""

import uuid

import pytest

from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.external_api_key import (
    ExternalApiKey,
    ExternalApiKeyCreated,
    ExternalApiKeyUpdated,
)


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


class TestExternalApiKeyCreate:
    def test_factory(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> None:
        key = ExternalApiKey.create(
            workspace_id=ws_id,
            key_name="bioportal",
            label="BioPortal API Key",
            description="For ontology lookups",
            key_prefix="abc1...xyz9",
            created_by=user_id,
        )
        assert key.workspace_id == ws_id
        assert key.key_name == "bioportal"
        assert key.label == "BioPortal API Key"
        assert key.description == "For ontology lookups"
        assert key.key_prefix == "abc1...xyz9"
        assert key.is_active is True
        assert key.created_by == user_id
        assert key.last_used_at is None
        assert key.id is not None
        assert key.version == 1

    def test_factory_emits_created_event(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = ExternalApiKey.create(
            workspace_id=ws_id,
            key_name="cdd_vault",
            label="External Vault Token",
            key_prefix="tk_...abc",
            created_by=user_id,
        )
        events = key.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ExternalApiKeyCreated)
        assert event.aggregate_id == key.id
        assert event.aggregate_type == "ExternalApiKey"
        assert event.workspace_id == ws_id
        assert event.key_name == "cdd_vault"

    def test_factory_no_description(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = ExternalApiKey.create(
            workspace_id=ws_id,
            key_name="bioportal",
            label="BioPortal",
            key_prefix="abc1...xyz9",
            created_by=user_id,
        )
        assert key.description is None

    def test_factory_strips_whitespace(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = ExternalApiKey.create(
            workspace_id=ws_id,
            key_name="  bioportal  ",
            label="  BioPortal  ",
            description="  some desc  ",
            key_prefix="  abc1...xyz9  ",
            created_by=user_id,
        )
        assert key.key_name == "bioportal"
        assert key.label == "BioPortal"
        assert key.description == "some desc"
        assert key.key_prefix == "abc1...xyz9"

    def test_empty_key_name_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="key_name"):
            ExternalApiKey.create(
                workspace_id=ws_id,
                key_name="",
                label="Test",
                key_prefix="abc",
                created_by=user_id,
            )

    def test_whitespace_key_name_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="key_name"):
            ExternalApiKey.create(
                workspace_id=ws_id,
                key_name="   ",
                label="Test",
                key_prefix="abc",
                created_by=user_id,
            )

    def test_empty_label_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="label"):
            ExternalApiKey.create(
                workspace_id=ws_id,
                key_name="bioportal",
                label="",
                key_prefix="abc",
                created_by=user_id,
            )

    def test_empty_key_prefix_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="key_prefix"):
            ExternalApiKey.create(
                workspace_id=ws_id,
                key_name="bioportal",
                label="BioPortal",
                key_prefix="",
                created_by=user_id,
            )

    def test_whitespace_key_prefix_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="key_prefix"):
            ExternalApiKey.create(
                workspace_id=ws_id,
                key_name="bioportal",
                label="BioPortal",
                key_prefix="   ",
                created_by=user_id,
            )


class TestExternalApiKeyUpdate:
    def _make(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> ExternalApiKey:
        key = ExternalApiKey.create(
            workspace_id=ws_id,
            key_name="bioportal",
            label="BioPortal API Key",
            key_prefix="abc1...xyz9",
            created_by=user_id,
        )
        key.clear_events()
        return key

    def test_update_label(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        key.update(label="New Label")
        assert key.label == "New Label"
        events = key.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ExternalApiKeyUpdated)

    def test_update_description(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        key.update(description="Updated description")
        assert key.description == "Updated description"

    def test_update_description_to_none(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        key.update(description="something")
        key.clear_events()
        key.update(description=None)
        assert key.description is None
        assert len(key.collect_events()) == 1

    def test_update_empty_label_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        with pytest.raises(ValidationError, match="label"):
            key.update(label="")

    def test_update_no_args_emits_event(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        key.update()
        assert len(key.collect_events()) == 1

    def test_update_prefix(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        key.update_prefix("new1...new9")
        assert key.key_prefix == "new1...new9"
        events = key.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ExternalApiKeyUpdated)

    def test_update_prefix_empty_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        with pytest.raises(ValidationError, match="key_prefix"):
            key.update_prefix("")

    def test_update_prefix_whitespace_raises(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        with pytest.raises(ValidationError, match="key_prefix"):
            key.update_prefix("   ")


class TestExternalApiKeyActivation:
    def _make(self, ws_id: uuid.UUID, user_id: uuid.UUID) -> ExternalApiKey:
        key = ExternalApiKey.create(
            workspace_id=ws_id,
            key_name="bioportal",
            label="BioPortal API Key",
            key_prefix="abc1...xyz9",
            created_by=user_id,
        )
        key.clear_events()
        return key

    def test_deactivate(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        key.deactivate()
        assert key.is_active is False
        events = key.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ExternalApiKeyUpdated)

    def test_activate(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = self._make(ws_id, user_id)
        key.deactivate()
        key.clear_events()
        key.activate()
        assert key.is_active is True
        events = key.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ExternalApiKeyUpdated)


class TestExternalApiKeyMarkUsed:
    def test_mark_used_sets_timestamp(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = ExternalApiKey.create(
            workspace_id=ws_id,
            key_name="bioportal",
            label="BioPortal API Key",
            key_prefix="abc1...xyz9",
            created_by=user_id,
        )
        assert key.last_used_at is None
        key.mark_used()
        assert key.last_used_at is not None

    def test_mark_used_no_event(
        self, ws_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        key = ExternalApiKey.create(
            workspace_id=ws_id,
            key_name="bioportal",
            label="BioPortal API Key",
            key_prefix="abc1...xyz9",
            created_by=user_id,
        )
        key.clear_events()
        key.mark_used()
        # mark_used is high-frequency — no domain event emitted
        assert len(key.collect_events()) == 0
