"""Tests for Protocol aggregate root, owned entities, and versioning service."""

import uuid

import pytest

from chem_vault.domain.screening_assay.enums import (
    ConditionDataType,
    ProtocolStatus,
    ProtocolType,
    ReadoutAggregation,
    ReadoutDataType,
    ReadoutNormalization,
)
from chem_vault.domain.screening_assay.events import (
    ProtocolCreated,
    ProtocolPublished,
    ProtocolRetired,
    ProtocolVersionCreated,
)
from chem_vault.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from chem_vault.domain.screening_assay.protocol_versioning_service import (
    ProtocolVersioningService,
)
from chem_vault.domain.shared.errors import ConflictError, NotFoundError, ValidationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def workspace_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PLACEHOLDER_ID = uuid.UUID(int=0)


def _make_readout(protocol_id: uuid.UUID = _PLACEHOLDER_ID, **kwargs) -> ReadoutDefinition:
    defaults = dict(
        protocol_id=protocol_id,
        name="IC50",
        data_type=ReadoutDataType.NUMERIC,
        unit="nM",
    )
    defaults.update(kwargs)
    return ReadoutDefinition(**defaults)


def _make_condition(protocol_id: uuid.UUID = _PLACEHOLDER_ID, **kwargs) -> ConditionDefinition:
    defaults = dict(
        protocol_id=protocol_id,
        name="Cell Line",
        data_type=ConditionDataType.TEXT,
    )
    defaults.update(kwargs)
    return ConditionDefinition(**defaults)


def _make_protocol(
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    **kwargs,
) -> Protocol:
    """Create a protocol with one default readout definition.

    Readout and condition definitions have their protocol_id fixed up
    to match the auto-generated protocol id after creation.
    """
    readout_defs = kwargs.pop("readout_definitions", None)
    condition_defs = kwargs.pop("condition_definitions", None)
    if readout_defs is None:
        readout_defs = [_make_readout()]

    defaults = dict(
        workspace_id=workspace_id,
        name="hERG Patch Clamp",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=user_id,
        readout_definitions=readout_defs,
        condition_definitions=condition_defs,
    )
    defaults.update(kwargs)
    protocol = Protocol.create(**defaults)

    # Fix up protocol_id on owned entities
    for rd in protocol.readout_definitions:
        rd.protocol_id = protocol.id
    for cd in protocol.condition_definitions:
        cd.protocol_id = protocol.id

    return protocol


# ---------------------------------------------------------------------------
# TestProtocolCreation
# ---------------------------------------------------------------------------


class TestProtocolCreation:
    def test_create_sets_all_fields(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        target_id = uuid.uuid4()
        protocol = _make_protocol(
            workspace_id,
            user_id,
            name="Kinase Assay",
            description="Measures kinase inhibition",
            protocol_type=ProtocolType.CELL_BASED,
            target_id=target_id,
            category="kinase",
        )

        assert protocol.workspace_id == workspace_id
        assert protocol.name == "Kinase Assay"
        assert protocol.description == "Measures kinase inhibition"
        assert protocol.protocol_type == ProtocolType.CELL_BASED
        assert protocol.target_id == target_id
        assert protocol.category == "kinase"
        assert protocol.protocol_version == 1
        assert protocol.parent_protocol_id is None
        assert protocol.status == ProtocolStatus.DRAFT
        assert protocol.created_by == user_id
        assert len(protocol.readout_definitions) == 1
        assert protocol.condition_definitions == []
        assert protocol.version == 1

    def test_create_emits_protocol_created_event(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        events = protocol.collect_events()

        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, ProtocolCreated)
        assert evt.aggregate_id == protocol.id
        assert evt.aggregate_type == "Protocol"
        assert evt.name == "hERG Patch Clamp"
        assert evt.version == 1
        assert evt.protocol_type == "biochemical"

    def test_create_without_readouts_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="at least one ReadoutDefinition"):
            Protocol.create(
                workspace_id=workspace_id,
                name="Bad Protocol",
                protocol_type=ProtocolType.BIOCHEMICAL,
                created_by=user_id,
                readout_definitions=[],
            )

    def test_create_none_readouts_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="at least one ReadoutDefinition"):
            Protocol.create(
                workspace_id=workspace_id,
                name="Bad Protocol",
                protocol_type=ProtocolType.BIOCHEMICAL,
                created_by=user_id,
                readout_definitions=None,
            )

    def test_empty_name_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            _make_protocol(workspace_id, user_id, name="")

    def test_whitespace_name_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            _make_protocol(workspace_id, user_id, name="   ")

    def test_name_is_stripped(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id, name="  Kinase Assay  ")
        assert protocol.name == "Kinase Assay"


# ---------------------------------------------------------------------------
# TestReadoutDefinition
# ---------------------------------------------------------------------------


class TestReadoutDefinition:
    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            ReadoutDefinition(
                protocol_id=uuid.uuid4(),
                name="",
                data_type=ReadoutDataType.NUMERIC,
            )

    def test_whitespace_name_raises(self) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            ReadoutDefinition(
                protocol_id=uuid.uuid4(),
                name="   ",
                data_type=ReadoutDataType.NUMERIC,
            )

    def test_calculated_requires_formula(self) -> None:
        with pytest.raises(ValidationError, match="calculation_formula"):
            ReadoutDefinition(
                protocol_id=uuid.uuid4(),
                name="Derived Value",
                data_type=ReadoutDataType.NUMERIC,
                is_calculated=True,
            )

    def test_calculated_with_formula_ok(self) -> None:
        rd = ReadoutDefinition(
            protocol_id=uuid.uuid4(),
            name="Derived Value",
            data_type=ReadoutDataType.NUMERIC,
            is_calculated=True,
            calculation_formula="100 - percent_inhibition",
        )
        assert rd.is_calculated is True
        assert rd.calculation_formula == "100 - percent_inhibition"

    def test_defaults(self) -> None:
        rd = ReadoutDefinition(
            protocol_id=uuid.uuid4(),
            name="IC50",
            data_type=ReadoutDataType.NUMERIC,
        )
        assert rd.aggregation == ReadoutAggregation.NONE
        assert rd.normalization == ReadoutNormalization.NONE
        assert rd.is_calculated is False
        assert rd.calculation_formula is None
        assert rd.display_order == 0
        assert rd.unit is None
        assert rd.precision is None

    def test_name_is_stripped(self) -> None:
        rd = ReadoutDefinition(
            protocol_id=uuid.uuid4(),
            name="  IC50  ",
            data_type=ReadoutDataType.NUMERIC,
        )
        assert rd.name == "IC50"


# ---------------------------------------------------------------------------
# TestConditionDefinition
# ---------------------------------------------------------------------------


class TestConditionDefinition:
    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValidationError, match="name must not be empty"):
            ConditionDefinition(
                protocol_id=uuid.uuid4(),
                name="",
                data_type=ConditionDataType.TEXT,
            )

    def test_pick_list_requires_values(self) -> None:
        with pytest.raises(ValidationError, match="pick_list_values"):
            ConditionDefinition(
                protocol_id=uuid.uuid4(),
                name="Cell Line",
                data_type=ConditionDataType.PICK_LIST,
            )

    def test_pick_list_empty_values_raises(self) -> None:
        with pytest.raises(ValidationError, match="pick_list_values"):
            ConditionDefinition(
                protocol_id=uuid.uuid4(),
                name="Cell Line",
                data_type=ConditionDataType.PICK_LIST,
                pick_list_values=[],
            )

    def test_pick_list_with_values_ok(self) -> None:
        cd = ConditionDefinition(
            protocol_id=uuid.uuid4(),
            name="Cell Line",
            data_type=ConditionDataType.PICK_LIST,
            pick_list_values=["HEK293", "CHO", "HeLa"],
        )
        assert cd.data_type == ConditionDataType.PICK_LIST
        assert cd.pick_list_values == ["HEK293", "CHO", "HeLa"]

    def test_text_type_ok(self) -> None:
        cd = ConditionDefinition(
            protocol_id=uuid.uuid4(),
            name="Species",
            data_type=ConditionDataType.TEXT,
        )
        assert cd.pick_list_values is None

    def test_numeric_type_ok(self) -> None:
        cd = ConditionDefinition(
            protocol_id=uuid.uuid4(),
            name="Time Point",
            data_type=ConditionDataType.NUMERIC,
            unit="hours",
        )
        assert cd.unit == "hours"

    def test_name_is_stripped(self) -> None:
        cd = ConditionDefinition(
            protocol_id=uuid.uuid4(),
            name="  Cell Line  ",
            data_type=ConditionDataType.TEXT,
        )
        assert cd.name == "Cell Line"


# ---------------------------------------------------------------------------
# TestProtocolDefinitionManagement
# ---------------------------------------------------------------------------


class TestProtocolDefinitionManagement:
    def test_add_readout_to_draft(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        assert len(protocol.readout_definitions) == 1

        new_rd = _make_readout(protocol.id, name="% Inhibition")
        protocol.add_readout_definition(new_rd)
        assert len(protocol.readout_definitions) == 2

    def test_add_readout_to_active_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()

        new_rd = _make_readout(protocol.id, name="% Inhibition")
        with pytest.raises(ConflictError, match="only DRAFT"):
            protocol.add_readout_definition(new_rd)

    def test_remove_readout_ok(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        rd1 = _make_readout(name="IC50")
        rd2 = _make_readout(name="% Inhibition")
        protocol = _make_protocol(
            workspace_id, user_id, readout_definitions=[rd1, rd2]
        )
        protocol.remove_readout_definition(rd1.id)
        assert len(protocol.readout_definitions) == 1
        assert protocol.readout_definitions[0].id == rd2.id

    def test_remove_last_readout_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        rd_id = protocol.readout_definitions[0].id

        with pytest.raises(ValidationError, match="at least one"):
            protocol.remove_readout_definition(rd_id)

    def test_remove_nonexistent_readout_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        with pytest.raises(NotFoundError, match="ReadoutDefinition"):
            protocol.remove_readout_definition(uuid.uuid4())

    def test_update_readout_changes_normalization(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        rd = protocol.readout_definitions[0]
        assert rd.normalization == ReadoutNormalization.NONE

        protocol.update_readout_definition(
            rd.id, normalization=ReadoutNormalization.PERCENT_INHIBITION
        )
        updated = protocol.readout_definitions[0]
        assert updated.id == rd.id  # same id, replaced object
        assert updated.normalization == ReadoutNormalization.PERCENT_INHIBITION
        # other fields preserved
        assert updated.name == rd.name

    def test_update_readout_rejects_duplicate_name(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        rd1 = _make_readout(name="IC50")
        rd2 = _make_readout(name="% Inhibition")
        protocol = _make_protocol(
            workspace_id, user_id, readout_definitions=[rd1, rd2]
        )
        with pytest.raises(ConflictError, match="already exists"):
            protocol.update_readout_definition(rd1.id, name="% Inhibition")

    def test_update_readout_on_active_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        rd = protocol.readout_definitions[0]
        protocol.publish()
        with pytest.raises(ConflictError, match="only DRAFT"):
            protocol.update_readout_definition(rd.id, name="Renamed")

    def test_update_nonexistent_readout_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        with pytest.raises(NotFoundError, match="ReadoutDefinition"):
            protocol.update_readout_definition(uuid.uuid4(), name="X")

    def test_update_condition_changes_name(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        cd = _make_condition(protocol.id, name="Buffer pH")
        protocol.add_condition_definition(cd)

        protocol.update_condition_definition(cd.id, name="pH")
        assert protocol.condition_definitions[0].name == "pH"
        assert protocol.condition_definitions[0].id == cd.id

    def test_update_condition_on_active_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        cd = _make_condition(protocol.id, name="Buffer pH")
        protocol.add_condition_definition(cd)
        protocol.publish()
        with pytest.raises(ConflictError, match="only DRAFT"):
            protocol.update_condition_definition(cd.id, name="pH")

    def test_add_condition_to_draft(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        assert len(protocol.condition_definitions) == 0

        cd = _make_condition(protocol.id)
        protocol.add_condition_definition(cd)
        assert len(protocol.condition_definitions) == 1

    def test_add_condition_to_active_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()

        cd = _make_condition(protocol.id)
        with pytest.raises(ConflictError, match="only DRAFT"):
            protocol.add_condition_definition(cd)

    def test_remove_condition_ok(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        cd = _make_condition(protocol.id)
        protocol.add_condition_definition(cd)
        assert len(protocol.condition_definitions) == 1

        protocol.remove_condition_definition(cd.id)
        assert len(protocol.condition_definitions) == 0

    def test_remove_nonexistent_condition_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        with pytest.raises(NotFoundError, match="ConditionDefinition"):
            protocol.remove_condition_definition(uuid.uuid4())

    def test_remove_readout_from_active_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        rd1 = _make_readout(name="IC50")
        rd2 = _make_readout(name="% Inhibition")
        protocol = _make_protocol(
            workspace_id, user_id, readout_definitions=[rd1, rd2]
        )
        protocol.publish()

        with pytest.raises(ConflictError, match="only DRAFT"):
            protocol.remove_readout_definition(rd1.id)


# ---------------------------------------------------------------------------
# TestProtocolStatusTransitions
# ---------------------------------------------------------------------------


class TestProtocolStatusTransitions:
    def test_publish_draft(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        assert protocol.status == ProtocolStatus.DRAFT

        protocol.publish()
        assert protocol.status == ProtocolStatus.ACTIVE

        events = protocol.collect_events()
        publish_events = [e for e in events if isinstance(e, ProtocolPublished)]
        assert len(publish_events) == 1
        assert publish_events[0].aggregate_id == protocol.id

    def test_retire_active(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()
        protocol.clear_events()

        protocol.retire(reason="Replaced by newer version")
        assert protocol.status == ProtocolStatus.RETIRED

        events = protocol.collect_events()
        assert len(events) == 1
        evt = events[0]
        assert isinstance(evt, ProtocolRetired)
        assert evt.reason == "Replaced by newer version"

    def test_retire_without_reason(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()
        protocol.retire()
        assert protocol.status == ProtocolStatus.RETIRED

        events = protocol.collect_events()
        retire_events = [e for e in events if isinstance(e, ProtocolRetired)]
        assert retire_events[0].reason is None

    def test_cannot_publish_active(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()
        with pytest.raises(ConflictError, match="Cannot transition"):
            protocol.publish()

    def test_cannot_retire_draft(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        with pytest.raises(ConflictError, match="Cannot transition"):
            protocol.retire()

    def test_retired_is_terminal(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()
        protocol.retire()

        with pytest.raises(ConflictError, match="Cannot transition"):
            protocol.publish()
        with pytest.raises(ConflictError, match="Cannot transition"):
            protocol.retire()


# ---------------------------------------------------------------------------
# TestProtocolUpdate
# ---------------------------------------------------------------------------


class TestProtocolUpdate:
    def test_update_draft_name(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        old_updated = protocol.updated_at
        protocol.update(name="Updated Name")
        assert protocol.name == "Updated Name"
        assert protocol.updated_at >= old_updated

    def test_update_draft_description(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id, description="Old")
        protocol.update(description="New description")
        assert protocol.description == "New description"

    def test_update_clear_description(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id, description="Old")
        protocol.update(description=None)
        assert protocol.description is None

    def test_update_preserves_unset_fields(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(
            workspace_id, user_id, description="Keep me", category="kinase"
        )
        protocol.update(name="New Name")
        assert protocol.description == "Keep me"
        assert protocol.category == "kinase"

    def test_update_active_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()
        with pytest.raises(ConflictError, match="only DRAFT"):
            protocol.update(name="Nope")

    def test_update_empty_name_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        with pytest.raises(ValidationError, match="name must not be empty"):
            protocol.update(name="")


# ---------------------------------------------------------------------------
# TestProtocolVersioning
# ---------------------------------------------------------------------------


class TestProtocolVersioning:
    def test_version_active_protocol(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()
        protocol.clear_events()

        service = ProtocolVersioningService()
        new_version = service.create_new_version(protocol)

        # Parent stays ACTIVE — only retired when new version is published
        assert protocol.status == ProtocolStatus.ACTIVE

        # New version fields
        assert new_version.protocol_version == 2
        assert new_version.parent_protocol_id == protocol.id
        assert new_version.status == ProtocolStatus.DRAFT
        assert new_version.workspace_id == protocol.workspace_id
        assert new_version.name == protocol.name
        assert new_version.protocol_type == protocol.protocol_type
        assert new_version.created_by == protocol.created_by
        assert new_version.id != protocol.id

    def test_version_emits_events(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()
        protocol.clear_events()

        service = ProtocolVersioningService()
        new_version = service.create_new_version(protocol)

        # Parent has NO events — it's not retired yet
        parent_events = protocol.collect_events()
        assert len(parent_events) == 0

        # New version should have ProtocolVersionCreated event
        new_events = new_version.collect_events()
        assert len(new_events) == 1
        evt = new_events[0]
        assert isinstance(evt, ProtocolVersionCreated)
        assert evt.parent_protocol_id == protocol.id
        assert evt.version == 2

    def test_version_draft_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        service = ProtocolVersioningService()
        with pytest.raises(ConflictError, match="only ACTIVE"):
            service.create_new_version(protocol)

    def test_version_retired_raises(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        protocol = _make_protocol(workspace_id, user_id)
        protocol.publish()
        protocol.retire()
        service = ProtocolVersioningService()
        with pytest.raises(ConflictError, match="only ACTIVE"):
            service.create_new_version(protocol)

    def test_cloned_definitions_have_new_ids(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        rd = _make_readout(name="IC50", unit="nM")
        cd = _make_condition(name="Cell Line")
        protocol = _make_protocol(
            workspace_id,
            user_id,
            readout_definitions=[rd],
            condition_definitions=[cd],
        )
        protocol.publish()

        service = ProtocolVersioningService()
        new_version = service.create_new_version(protocol)

        # Readout cloned
        assert len(new_version.readout_definitions) == 1
        new_rd = new_version.readout_definitions[0]
        assert new_rd.id != rd.id
        assert new_rd.name == "IC50"
        assert new_rd.unit == "nM"
        assert new_rd.protocol_id == new_version.id

        # Condition cloned
        assert len(new_version.condition_definitions) == 1
        new_cd = new_version.condition_definitions[0]
        assert new_cd.id != cd.id
        assert new_cd.name == "Cell Line"
        assert new_cd.protocol_id == new_version.id

    def test_cloned_definitions_are_independent(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Mutating cloned definitions does not affect originals."""
        rd = _make_readout(name="IC50")
        protocol = _make_protocol(
            workspace_id, user_id, readout_definitions=[rd]
        )
        protocol.publish()

        service = ProtocolVersioningService()
        new_version = service.create_new_version(protocol)

        # Mutate the clone
        new_version.readout_definitions[0].name = "Changed"
        assert rd.name == "IC50"  # original unchanged

    def test_cloned_pick_list_values_are_independent(
        self, workspace_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """pick_list_values are deep-copied so mutations are independent."""
        rd = _make_readout()
        cd = ConditionDefinition(
            protocol_id=_PLACEHOLDER_ID,
            name="Cell Line",
            data_type=ConditionDataType.PICK_LIST,
            pick_list_values=["HEK293", "CHO"],
        )
        protocol = _make_protocol(
            workspace_id,
            user_id,
            readout_definitions=[rd],
            condition_definitions=[cd],
        )
        protocol.publish()

        service = ProtocolVersioningService()
        new_version = service.create_new_version(protocol)

        # Mutate the clone's pick_list_values
        new_version.condition_definitions[0].pick_list_values.append("HeLa")
        assert cd.pick_list_values == ["HEK293", "CHO"]  # original unchanged
