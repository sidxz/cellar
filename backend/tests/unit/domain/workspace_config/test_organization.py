"""Tests for Organization aggregate."""

import uuid

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.enums import OrganizationType
from cellar.domain.workspace_config.events import (
    OrganizationCreated,
    OrganizationDeactivated,
    OrganizationUpdated,
)
from cellar.domain.workspace_config.organization import Organization


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


class TestOrganizationCreate:
    def test_factory_sets_fields(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id,
            name="Merck",
            org_type=OrganizationType.PHARMA_PARTNER,
            contact_name="Alice",
            contact_email="alice@merck.com",
            notes="Key partner",
        )
        assert org.workspace_id == ws_id
        assert org.name == "Merck"
        assert org.org_type == OrganizationType.PHARMA_PARTNER
        assert org.contact_name == "Alice"
        assert org.contact_email == "alice@merck.com"
        assert org.notes == "Key partner"
        assert org.is_active is True
        assert org.version == 1

    def test_factory_emits_created_event(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="SaccLabs", org_type=OrganizationType.INTERNAL
        )
        events = org.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], OrganizationCreated)
        assert events[0].aggregate_id == org.id
        assert events[0].name == "SaccLabs"
        assert events[0].org_type == OrganizationType.INTERNAL

    def test_name_is_stripped(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="  Pfizer  ", org_type=OrganizationType.PHARMA_PARTNER
        )
        assert org.name == "Pfizer"

    def test_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            Organization.create(workspace_id=ws_id, name="", org_type=OrganizationType.INTERNAL)

    def test_blank_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            Organization.create(workspace_id=ws_id, name="   ", org_type=OrganizationType.INTERNAL)


class TestOrganizationUpdate:
    def test_partial_update(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="Old Name", org_type=OrganizationType.CRO
        )
        org.clear_events()
        org.update(name="New Name")
        assert org.name == "New Name"
        assert org.org_type == OrganizationType.CRO  # unchanged

    def test_update_emits_event(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="Lab", org_type=OrganizationType.INTERNAL
        )
        org.clear_events()
        org.update(contact_email="lab@example.com")
        events = org.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], OrganizationUpdated)

    def test_update_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="Lab", org_type=OrganizationType.INTERNAL
        )
        with pytest.raises(ValidationError):
            org.update(name="")

    def test_update_nullable_fields_to_none(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id,
            name="Lab",
            org_type=OrganizationType.INTERNAL,
            contact_name="Alice",
        )
        org.update(contact_name=None)
        assert org.contact_name is None


class TestOrganizationActivation:
    def test_deactivate(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="Lab", org_type=OrganizationType.INTERNAL
        )
        org.clear_events()
        org.deactivate()
        assert org.is_active is False
        events = org.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], OrganizationDeactivated)

    def test_deactivate_twice_raises(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="Lab", org_type=OrganizationType.INTERNAL
        )
        org.deactivate()
        with pytest.raises(ValidationError, match="already inactive"):
            org.deactivate()

    def test_activate(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="Lab", org_type=OrganizationType.INTERNAL
        )
        org.deactivate()
        org.activate()
        assert org.is_active is True

    def test_activate_when_active_raises(self, ws_id: uuid.UUID) -> None:
        org = Organization.create(
            workspace_id=ws_id, name="Lab", org_type=OrganizationType.INTERNAL
        )
        with pytest.raises(ValidationError, match="already active"):
            org.activate()
