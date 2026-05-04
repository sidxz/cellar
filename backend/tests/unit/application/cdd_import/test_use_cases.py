"""Tests for CDD import use cases with fakes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.cdd_import.import_cdd_protocol import (
    ImportCddProtocol,
    ImportCddProtocolCommand,
)
from chem_vault.application.cdd_import.list_cdd_protocols import (
    ListCddProtocols,
    ListCddProtocolsQuery,
)
from chem_vault.application.cdd_import.preview_cdd_protocol_import import (
    PreviewCddProtocolImport,
    PreviewCddProtocolImportQuery,
)
from chem_vault.application.workspace_config.get_data_source_for_import import (
    DataSourceImportConfig,
)
from chem_vault.domain.screening_assay.enums import ReadoutDataType
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from chem_vault.application.cdd_import.errors import CddAuthError

from tests.fakes.fake_auth import FakeAuth

WORKSPACE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeGateway:
    def __init__(self, protocols=None, detail=None):
        self._protocols = protocols or []
        self._detail = detail

    async def list_protocols(self, vault_id, api_key):
        return self._protocols

    async def get_protocol(self, vault_id, api_key, protocol_id):
        if self._detail is None:
            raise CddAuthError("Not found")
        return self._detail


class _FakeDataSource:
    def __init__(self, vault_id="12345"):
        self.config = {"vault_id": vault_id} if vault_id else {}


class FakeGetDataSource:
    """Stand-in for GetDataSourceForImport.

    By default returns a DataSourceImportConfig pointing at vault_id=12345
    with api_key="key123". Pass `result=Failure(...)` to simulate config errors.
    """

    def __init__(
        self,
        *,
        vault_id: str | None = "12345",
        api_key: str | None = "key123",
        result=None,
    ):
        if result is None:
            result = Success(
                DataSourceImportConfig(
                    data_source=_FakeDataSource(vault_id=vault_id),
                    api_key=api_key,
                )
            )
        self._result = result

    async def __call__(self, query):  # noqa: ARG002
        return self._result


class FakeUoW:
    async def commit(self):
        return []

    async def rollback(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _protocol_detail(protocol_id=1, name="Kinase IC50"):
    return {
        "id": protocol_id,
        "name": name,
        "readout_definitions": [
            {"name": "% Inhibition", "data_type": "Number", "unit_label": "%"},
            {"name": "Notes", "data_type": "Text", "unit_label": None},
            {"name": "Cell Type", "data_type": "Text", "protocol_condition": True},
        ],
    }


def _make_auth(*, role="editor"):
    return FakeAuth(role=role, user_id=USER_ID, workspace_id=WORKSPACE_ID)


# ---------------------------------------------------------------------------
# ListCddProtocols
# ---------------------------------------------------------------------------


class TestListCddProtocols:
    @pytest.mark.asyncio
    async def test_success(self):
        gateway = FakeGateway(
            protocols=[
                {"id": 1, "name": "P1", "readout_definitions": [{"name": "R1", "data_type": "Number"}]},
            ]
        )
        uc = ListCddProtocols(gateway=gateway, get_data_source=FakeGetDataSource())
        result = await uc(ListCddProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Success)
        summaries = result.unwrap()
        assert len(summaries) == 1
        assert summaries[0].name == "P1"

    @pytest.mark.asyncio
    async def test_no_vault_id_configured(self):
        uc = ListCddProtocols(
            gateway=FakeGateway(),
            get_data_source=FakeGetDataSource(vault_id=None),
        )
        result = await uc(ListCddProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_no_data_source_configured(self):
        uc = ListCddProtocols(
            gateway=FakeGateway(),
            get_data_source=FakeGetDataSource(
                result=Failure(NotFoundError("DataSource", "no active CDD source")),
            ),
        )
        result = await uc(ListCddProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_no_secret_found(self):
        uc = ListCddProtocols(
            gateway=FakeGateway(),
            get_data_source=FakeGetDataSource(
                result=Failure(ValidationError("API key secret is empty")),
            ),
        )
        result = await uc(ListCddProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_viewer_rejected(self):
        uc = ListCddProtocols(gateway=FakeGateway(), get_data_source=FakeGetDataSource())
        with pytest.raises(AuthorizationError):
            await uc(ListCddProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth(role="viewer"))

    @pytest.mark.asyncio
    async def test_cdd_auth_error_returns_failure(self):
        class AuthErrorGateway:
            async def list_protocols(self, vault_id, api_key):
                raise CddAuthError("Invalid key")

        uc = ListCddProtocols(gateway=AuthErrorGateway(), get_data_source=FakeGetDataSource())
        result = await uc(ListCddProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# PreviewCddProtocolImport
# ---------------------------------------------------------------------------


class TestPreviewCddProtocolImport:
    @pytest.mark.asyncio
    async def test_success_with_mapping(self):
        uc = PreviewCddProtocolImport(
            gateway=FakeGateway(detail=_protocol_detail()),
            get_data_source=FakeGetDataSource(),
        )
        result = await uc(
            PreviewCddProtocolImportQuery(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=_make_auth(),
        )
        assert isinstance(result, Success)
        mapping = result.unwrap()
        assert mapping.name == "Kinase IC50"
        assert len(mapping.readouts) == 2
        assert mapping.readouts[0].data_type == ReadoutDataType.NUMERIC

    @pytest.mark.asyncio
    async def test_not_found_returns_failure(self):
        uc = PreviewCddProtocolImport(
            gateway=FakeGateway(detail=None),  # gateway raises CddAuthError
            get_data_source=FakeGetDataSource(),
        )
        result = await uc(
            PreviewCddProtocolImportQuery(workspace_id=WORKSPACE_ID, external_protocol_id=999),
            auth=_make_auth(),
        )
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# ImportCddProtocol
# ---------------------------------------------------------------------------


class TestImportCddProtocol:
    def _make_uc(self, *, detail=None, uow=None, repo=None, dispatcher=None):
        if uow is None:
            uow = AsyncMock()
            uow.__aenter__ = AsyncMock(return_value=uow)
            uow.__aexit__ = AsyncMock(return_value=False)
            uow.commit = AsyncMock(return_value=[])
        if repo is None:
            repo = AsyncMock()
            repo.save = AsyncMock()
        if dispatcher is None:
            dispatcher = AsyncMock()
            dispatcher.dispatch_all = AsyncMock()

        return ImportCddProtocol(
            gateway=FakeGateway(detail=detail or _protocol_detail()),
            get_data_source=FakeGetDataSource(),
            uow=uow,
            protocol_repo=repo,
            dispatcher=dispatcher,
        ), repo

    @pytest.mark.asyncio
    async def test_success_creates_draft_protocol(self):
        uc, repo = self._make_uc()
        result = await uc(
            ImportCddProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=_make_auth(),
        )
        assert isinstance(result, Success)
        protocol = result.unwrap()
        assert protocol.name == "Kinase IC50"
        assert protocol.status.value == "draft"
        assert len(protocol.readout_definitions) == 2
        repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_name_override(self):
        uc, _repo = self._make_uc()
        result = await uc(
            ImportCddProtocolCommand(
                workspace_id=WORKSPACE_ID,
                external_protocol_id=1,
                name_override="My Custom Name",
            ),
            auth=_make_auth(),
        )
        assert isinstance(result, Success)
        assert result.unwrap().name == "My Custom Name"

    @pytest.mark.asyncio
    async def test_no_mappable_readouts_fails(self):
        detail = {
            "id": 1,
            "name": "Empty",
            "readout_definitions": [{"name": "X", "data_type": "UnknownType"}],
            "conditions": [],
        }
        uc, _repo = self._make_uc(detail=detail)
        result = await uc(
            ImportCddProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=_make_auth(),
        )
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_auth_required(self):
        uc, _repo = self._make_uc()
        result = await uc(
            ImportCddProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=None,
        )
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_conditions_mapped(self):
        uc, _repo = self._make_uc()
        result = await uc(
            ImportCddProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=_make_auth(),
        )
        assert isinstance(result, Success)
        protocol = result.unwrap()
        assert len(protocol.condition_definitions) == 1
        assert protocol.condition_definitions[0].name == "Cell Type"
