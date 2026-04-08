"""Unit tests for SaltEntry aggregate."""

import uuid

import pytest

from chem_vault.domain.shared.errors import ValidationError
from chem_vault.domain.workspace_config.salt_entry import (
    SaltEntry,
    SaltEntryCreated,
    SaltEntryUpdated,
)


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


class TestSaltEntryCreate:
    def test_factory(self, ws_id: uuid.UUID) -> None:
        entry = SaltEntry.create(
            workspace_id=ws_id,
            code="HCl",
            name="hydrochloride",
            smiles="[Cl-]",
            molecular_weight=36.46,
        )
        assert entry.workspace_id == ws_id
        assert entry.code == "HCl"
        assert entry.name == "hydrochloride"
        assert entry.smiles == "[Cl-]"
        assert entry.molecular_weight == 36.46
        assert entry.is_default is False
        assert entry.is_active is True
        assert entry.id is not None
        assert entry.version == 1

    def test_factory_emits_created_event(self, ws_id: uuid.UUID) -> None:
        entry = SaltEntry.create(
            workspace_id=ws_id,
            code="Na",
            name="sodium",
            smiles="[Na+]",
            molecular_weight=22.99,
        )
        events = entry.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, SaltEntryCreated)
        assert event.aggregate_id == entry.id
        assert event.aggregate_type == "SaltEntry"
        assert event.workspace_id == ws_id
        assert event.code == "Na"

    def test_create_as_default(self, ws_id: uuid.UUID) -> None:
        entry = SaltEntry.create(
            workspace_id=ws_id,
            code="TFA",
            name="trifluoroacetate",
            smiles="[O-]C(=O)C(F)(F)F",
            molecular_weight=113.02,
            is_default=True,
        )
        assert entry.is_default is True

    def test_empty_code_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="code"):
            SaltEntry.create(
                workspace_id=ws_id,
                code="",
                name="hydrochloride",
                smiles="[Cl-]",
                molecular_weight=36.46,
            )

    def test_whitespace_code_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="code"):
            SaltEntry.create(
                workspace_id=ws_id,
                code="   ",
                name="hydrochloride",
                smiles="[Cl-]",
                molecular_weight=36.46,
            )

    def test_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name"):
            SaltEntry.create(
                workspace_id=ws_id,
                code="HCl",
                name="",
                smiles="[Cl-]",
                molecular_weight=36.46,
            )

    def test_empty_smiles_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="smiles"):
            SaltEntry.create(
                workspace_id=ws_id,
                code="HCl",
                name="hydrochloride",
                smiles="",
                molecular_weight=36.46,
            )

    def test_zero_molecular_weight_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="molecular_weight"):
            SaltEntry.create(
                workspace_id=ws_id,
                code="HCl",
                name="hydrochloride",
                smiles="[Cl-]",
                molecular_weight=0.0,
            )

    def test_negative_molecular_weight_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="molecular_weight"):
            SaltEntry.create(
                workspace_id=ws_id,
                code="HCl",
                name="hydrochloride",
                smiles="[Cl-]",
                molecular_weight=-5.0,
            )


class TestSaltEntryUpdate:
    def _make(self, ws_id: uuid.UUID) -> SaltEntry:
        entry = SaltEntry.create(
            workspace_id=ws_id,
            code="HCl",
            name="hydrochloride",
            smiles="[Cl-]",
            molecular_weight=36.46,
        )
        entry.clear_events()
        return entry

    def test_update_name(self, ws_id: uuid.UUID) -> None:
        entry = self._make(ws_id)
        entry.update(name="Hydrochloride Salt")
        assert entry.name == "Hydrochloride Salt"
        events = entry.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], SaltEntryUpdated)

    def test_update_smiles(self, ws_id: uuid.UUID) -> None:
        entry = self._make(ws_id)
        entry.update(smiles="Cl")
        assert entry.smiles == "Cl"

    def test_update_molecular_weight(self, ws_id: uuid.UUID) -> None:
        entry = self._make(ws_id)
        entry.update(molecular_weight=36.47)
        assert entry.molecular_weight == 36.47

    def test_update_negative_mw_raises(self, ws_id: uuid.UUID) -> None:
        entry = self._make(ws_id)
        with pytest.raises(ValidationError, match="molecular_weight"):
            entry.update(molecular_weight=-1.0)

    def test_update_zero_mw_raises(self, ws_id: uuid.UUID) -> None:
        entry = self._make(ws_id)
        with pytest.raises(ValidationError, match="molecular_weight"):
            entry.update(molecular_weight=0.0)

    def test_update_no_args_emits_event(self, ws_id: uuid.UUID) -> None:
        entry = self._make(ws_id)
        entry.update()
        # Still emits SaltEntryUpdated even with no changes
        assert len(entry.collect_events()) == 1

    def test_deactivate(self, ws_id: uuid.UUID) -> None:
        entry = self._make(ws_id)
        entry.deactivate()
        assert entry.is_active is False
        events = entry.collect_events()
        assert len(events) == 1

    def test_activate(self, ws_id: uuid.UUID) -> None:
        entry = self._make(ws_id)
        entry.deactivate()
        entry.clear_events()
        entry.activate()
        assert entry.is_active is True
        events = entry.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], SaltEntryUpdated)
