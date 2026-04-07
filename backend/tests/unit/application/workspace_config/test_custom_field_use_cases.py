"""Unit tests for custom field CRUD use cases and CustomFieldValidator."""

from __future__ import annotations

import uuid
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.shared.sentinel import UNSET
from chem_vault.application.workspace_config.create_custom_field import (
    CreateCustomField,
    CreateCustomFieldCommand,
)
from chem_vault.application.workspace_config.custom_field_validator import (
    CustomFieldValidator,
)
from chem_vault.application.workspace_config.delete_custom_field import (
    DeleteCustomField,
    DeleteCustomFieldCommand,
)
from chem_vault.application.workspace_config.list_custom_fields import (
    ListCustomFields,
    ListCustomFieldsQuery,
)
from chem_vault.application.workspace_config.update_custom_field import (
    UpdateCustomField,
    UpdateCustomFieldCommand,
)
from chem_vault.domain.shared.errors import ConflictError, NotFoundError, ValidationError
from chem_vault.domain.workspace_config.custom_field_definition import CustomFieldDefinition
from chem_vault.domain.workspace_config.enums import FieldDataType, FieldTarget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeUnitOfWork:
    async def commit(self):
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


def _make_cfd(
    workspace_id: uuid.UUID,
    *,
    name: str = "purity",
    label: str = "Purity (%)",
    data_type: FieldDataType = FieldDataType.NUMBER,
    applies_to: FieldTarget = FieldTarget.MOLECULE,
    is_required: bool = False,
    pick_list_values: list[str] | None = None,
) -> CustomFieldDefinition:
    return CustomFieldDefinition.create(
        workspace_id=workspace_id,
        name=name,
        label=label,
        data_type=data_type,
        applies_to=applies_to,
        is_required=is_required,
        pick_list_values=pick_list_values,
    )


def _fake_editor_auth(workspace_id: uuid.UUID):
    auth = AsyncMock()
    auth.workspace_id = workspace_id
    auth.workspace_role = "editor"
    auth.is_admin = False
    return auth


# ---------------------------------------------------------------------------
# CreateCustomField
# ---------------------------------------------------------------------------


class TestCreateCustomField:
    def _make_uc(self, repo):
        return CreateCustomField(
            uow=FakeUnitOfWork(),
            repo=repo,
            dispatcher=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_creates_field_successfully(self):
        workspace_id = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_workspace.return_value = []
        repo.save.return_value = None

        uc = self._make_uc(repo)
        cmd = CreateCustomFieldCommand(
            workspace_id=workspace_id,
            name="purity",
            label="Purity (%)",
            data_type="number",
            applies_to="molecule",
            is_required=True,
        )
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Success)
        cfd = result.unwrap()
        assert cfd.name == "purity"
        assert cfd.data_type == FieldDataType.NUMBER
        assert cfd.applies_to == FieldTarget.MOLECULE
        assert cfd.is_required is True
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_duplicate_name_for_same_target(self):
        workspace_id = uuid.uuid4()
        existing = _make_cfd(workspace_id, name="purity")
        repo = AsyncMock()
        repo.find_by_workspace.return_value = [existing]

        uc = self._make_uc(repo)
        cmd = CreateCustomFieldCommand(
            workspace_id=workspace_id,
            name="purity",
            label="Purity (%)",
            data_type="number",
            applies_to="molecule",
        )
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ConflictError)

    @pytest.mark.asyncio
    async def test_allows_same_name_for_different_target(self):
        workspace_id = uuid.uuid4()
        # find_by_workspace for "batch" target returns empty (no conflict)
        repo = AsyncMock()
        repo.find_by_workspace.return_value = []
        repo.save.return_value = None

        uc = self._make_uc(repo)
        cmd = CreateCustomFieldCommand(
            workspace_id=workspace_id,
            name="purity",
            label="Purity (%)",
            data_type="number",
            applies_to="batch",
        )
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_creates_picklist_field(self):
        workspace_id = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_workspace.return_value = []
        repo.save.return_value = None

        uc = self._make_uc(repo)
        cmd = CreateCustomFieldCommand(
            workspace_id=workspace_id,
            name="grade",
            label="Grade",
            data_type="picklist",
            applies_to="batch",
            pick_list_values=["A", "B", "C"],
        )
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Success)
        cfd = result.unwrap()
        assert cfd.pick_list_values == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# ListCustomFields
# ---------------------------------------------------------------------------


class TestListCustomFields:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self):
        workspace_id = uuid.uuid4()
        cfds = [
            _make_cfd(workspace_id, name="purity"),
            _make_cfd(workspace_id, name="source"),
        ]
        repo = AsyncMock()
        repo.find_by_workspace.return_value = cfds

        uc = ListCustomFields(uow=FakeUnitOfWork(), repo=repo)
        query = ListCustomFieldsQuery(workspace_id=workspace_id)
        result = await uc(query)

        assert isinstance(result, Success)
        assert result.unwrap() == cfds
        repo.find_by_workspace.assert_called_once_with(
            workspace_id, applies_to=None, active_only=True
        )

    @pytest.mark.asyncio
    async def test_passes_applies_to_filter(self):
        workspace_id = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_workspace.return_value = []

        uc = ListCustomFields(uow=FakeUnitOfWork(), repo=repo)
        query = ListCustomFieldsQuery(
            workspace_id=workspace_id, applies_to="batch", active_only=False
        )
        await uc(query)

        repo.find_by_workspace.assert_called_once_with(
            workspace_id, applies_to=FieldTarget.BATCH, active_only=False
        )

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_none_found(self):
        workspace_id = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_workspace.return_value = []

        uc = ListCustomFields(uow=FakeUnitOfWork(), repo=repo)
        result = await uc(ListCustomFieldsQuery(workspace_id=workspace_id))
        assert result.unwrap() == []


# ---------------------------------------------------------------------------
# UpdateCustomField
# ---------------------------------------------------------------------------


class TestUpdateCustomField:
    def _make_uc(self, repo):
        return UpdateCustomField(
            uow=FakeUnitOfWork(),
            repo=repo,
            dispatcher=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_updates_label(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id, label="Old Label")
        repo = AsyncMock()
        repo.find_by_id.return_value = cfd

        uc = self._make_uc(repo)
        cmd = UpdateCustomFieldCommand(
            workspace_id=workspace_id,
            field_id=cfd.id,
            label="New Label",
        )
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Success)
        assert result.unwrap().label == "New Label"

    @pytest.mark.asyncio
    async def test_deactivates_field(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id)
        assert cfd.is_active is True
        repo = AsyncMock()
        repo.find_by_id.return_value = cfd

        uc = self._make_uc(repo)
        cmd = UpdateCustomFieldCommand(
            workspace_id=workspace_id,
            field_id=cfd.id,
            is_active=False,
        )
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Success)
        assert result.unwrap().is_active is False

    @pytest.mark.asyncio
    async def test_activates_field(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id)
        cfd.deactivate()
        repo = AsyncMock()
        repo.find_by_id.return_value = cfd

        uc = self._make_uc(repo)
        cmd = UpdateCustomFieldCommand(
            workspace_id=workspace_id,
            field_id=cfd.id,
            is_active=True,
        )
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Success)
        assert result.unwrap().is_active is True

    @pytest.mark.asyncio
    async def test_returns_not_found_for_wrong_workspace(self):
        workspace_id = uuid.uuid4()
        other_workspace = uuid.uuid4()
        cfd = _make_cfd(workspace_id)
        repo = AsyncMock()
        repo.find_by_id.return_value = cfd

        uc = self._make_uc(repo)
        cmd = UpdateCustomFieldCommand(
            workspace_id=other_workspace,
            field_id=cfd.id,
            label="Some Label",
        )
        result = await uc(cmd, auth=_fake_editor_auth(other_workspace))

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_returns_not_found_for_missing_field(self):
        workspace_id = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_id.return_value = None

        uc = self._make_uc(repo)
        cmd = UpdateCustomFieldCommand(
            workspace_id=workspace_id,
            field_id=uuid.uuid4(),
            label="Label",
        )
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# DeleteCustomField
# ---------------------------------------------------------------------------


class TestDeleteCustomField:
    def _make_uc(self, repo):
        return DeleteCustomField(
            uow=FakeUnitOfWork(),
            repo=repo,
        )

    @pytest.mark.asyncio
    async def test_deletes_successfully(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id)
        repo = AsyncMock()
        repo.find_by_id.return_value = cfd

        uc = self._make_uc(repo)
        cmd = DeleteCustomFieldCommand(workspace_id=workspace_id, field_id=cfd.id)
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Success)
        assert result.unwrap() is None
        repo.delete.assert_called_once_with(cfd.id)

    @pytest.mark.asyncio
    async def test_returns_not_found_when_missing(self):
        workspace_id = uuid.uuid4()
        repo = AsyncMock()
        repo.find_by_id.return_value = None

        uc = self._make_uc(repo)
        cmd = DeleteCustomFieldCommand(workspace_id=workspace_id, field_id=uuid.uuid4())
        result = await uc(cmd, auth=_fake_editor_auth(workspace_id))

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)

    @pytest.mark.asyncio
    async def test_returns_not_found_for_wrong_workspace(self):
        workspace_id = uuid.uuid4()
        other_workspace = uuid.uuid4()
        cfd = _make_cfd(workspace_id)
        repo = AsyncMock()
        repo.find_by_id.return_value = cfd

        uc = self._make_uc(repo)
        cmd = DeleteCustomFieldCommand(workspace_id=other_workspace, field_id=cfd.id)
        result = await uc(cmd, auth=_fake_editor_auth(other_workspace))

        assert isinstance(result, Failure)
        assert isinstance(result.failure(), NotFoundError)


# ---------------------------------------------------------------------------
# CustomFieldValidator
# ---------------------------------------------------------------------------


class TestCustomFieldValidator:
    def _make_validator(self, definitions: list[CustomFieldDefinition]):
        repo = AsyncMock()
        repo.find_by_workspace.return_value = definitions
        return CustomFieldValidator(repo=repo)

    @pytest.mark.asyncio
    async def test_valid_text_field_passes(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id, name="notes", label="Notes", data_type=FieldDataType.TEXT)
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"notes": "some text"},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_valid_number_field_passes(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id, name="purity", label="Purity", data_type=FieldDataType.NUMBER)
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"purity": 98.5},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_missing_required_field_fails(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(
            workspace_id, name="purity", label="Purity",
            data_type=FieldDataType.NUMBER, is_required=True
        )
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "purity" in str(err)

    @pytest.mark.asyncio
    async def test_wrong_type_number_field_with_string_fails(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id, name="purity", label="Purity", data_type=FieldDataType.NUMBER)
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"purity": "not-a-number"},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Failure)
        assert isinstance(result.failure(), ValidationError)
        assert "purity" in str(result.failure())

    @pytest.mark.asyncio
    async def test_invalid_picklist_value_fails(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(
            workspace_id, name="grade", label="Grade",
            data_type=FieldDataType.PICKLIST,
            pick_list_values=["A", "B", "C"],
        )
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"grade": "Z"},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Failure)
        err = result.failure()
        assert isinstance(err, ValidationError)
        assert "grade" in str(err)

    @pytest.mark.asyncio
    async def test_valid_picklist_value_passes(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(
            workspace_id, name="grade", label="Grade",
            data_type=FieldDataType.PICKLIST,
            pick_list_values=["A", "B", "C"],
        )
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"grade": "B"},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_unknown_field_name_rejected(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id, name="purity", label="Purity", data_type=FieldDataType.NUMBER)
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"purity": 98.5, "ghost_field": "value"},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Failure)
        assert "ghost_field" in str(result.failure())

    @pytest.mark.asyncio
    async def test_none_custom_fields_passes_when_no_required(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id, name="notes", label="Notes", data_type=FieldDataType.TEXT)
        validator = self._make_validator([cfd])

        result = await validator.validate(None, FieldTarget.MOLECULE, workspace_id)
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_none_custom_fields_fails_when_required_present(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(
            workspace_id, name="purity", label="Purity",
            data_type=FieldDataType.NUMBER, is_required=True
        )
        validator = self._make_validator([cfd])

        result = await validator.validate(None, FieldTarget.MOLECULE, workspace_id)
        assert isinstance(result, Failure)
        assert "purity" in str(result.failure())

    @pytest.mark.asyncio
    async def test_date_field_accepts_string(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id, name="exp_date", label="Expiry", data_type=FieldDataType.DATE)
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"exp_date": "2025-12-31"},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_date_field_accepts_date_object(self):
        workspace_id = uuid.uuid4()
        cfd = _make_cfd(workspace_id, name="exp_date", label="Expiry", data_type=FieldDataType.DATE)
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"exp_date": date(2025, 12, 31)},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_batch_link_accepts_string(self):
        workspace_id = uuid.uuid4()
        cfd = CustomFieldDefinition.create(
            workspace_id=workspace_id,
            name="ref_batch",
            label="Reference Batch",
            data_type=FieldDataType.BATCH_LINK,
            applies_to=FieldTarget.MOLECULE,
        )
        validator = self._make_validator([cfd])

        result = await validator.validate(
            {"ref_batch": "BN-00123"},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_collects_multiple_errors(self):
        workspace_id = uuid.uuid4()
        cfd_required = _make_cfd(
            workspace_id, name="purity", label="Purity",
            data_type=FieldDataType.NUMBER, is_required=True
        )
        cfd_text = _make_cfd(workspace_id, name="notes", label="Notes", data_type=FieldDataType.TEXT)
        validator = self._make_validator([cfd_required, cfd_text])

        # missing required "purity", wrong type for "notes", unknown "ghost"
        result = await validator.validate(
            {"notes": 123, "ghost": "x"},
            FieldTarget.MOLECULE,
            workspace_id,
        )
        assert isinstance(result, Failure)
        msg = str(result.failure())
        assert "purity" in msg    # missing required
        assert "notes" in msg     # wrong type
        assert "ghost" in msg     # unknown field
