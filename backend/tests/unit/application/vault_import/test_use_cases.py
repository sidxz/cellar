"""Tests for vault import use cases with fakes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from chem_vault.application.vault_import.import_external_protocol import (
    ImportExternalProtocol,
    ImportExternalProtocolCommand,
)
from chem_vault.application.vault_import.list_external_protocols import (
    ListExternalProtocols,
    ListExternalProtocolsQuery,
)
from chem_vault.application.vault_import.preview_external_protocol_import import (
    PreviewExternalProtocolImport,
    PreviewExternalProtocolImportQuery,
)
from chem_vault.domain.screening_assay.enums import ReadoutDataType
from chem_vault.domain.shared.errors import AuthorizationError
from chem_vault.application.vault_import.errors import VaultAuthError

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
            raise VaultAuthError("Not found")
        return self._detail


class FakeSecretProvider:
    def __init__(self, secrets=None):
        self._secrets = secrets or {}

    async def get_secret(self, key):
        return self._secrets.get(key)

    async def set_secret(self, key, value):
        self._secrets[key] = value

    async def delete_secret(self, key):
        self._secrets.pop(key, None)


class FakeWorkspaceSettingsRepo:
    def __init__(self, external_vault_id="12345"):
        self._external_vault_id = external_vault_id

    async def find_by_id(self, id):
        if self._external_vault_id is None:
            return None
        from chem_vault.domain.workspace_config.workspace_settings import WorkspaceSettings

        ws = WorkspaceSettings.create_default(workspace_id=id)
        ws.external_vault_id = self._external_vault_id
        return ws


class FakeApiKeyRepo:
    def __init__(self, has_active_key=True):
        self._has_active_key = has_active_key

    async def find_by_key_name(self, workspace_id, key_name):
        if not self._has_active_key:
            return None
        from chem_vault.domain.workspace_config.external_api_key import ExternalApiKey

        return ExternalApiKey(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            key_name=key_name,
            label="External Vault",
            key_prefix="abc***",
            is_active=True,
            created_by=uuid.uuid4(),
        )


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


def _secret_key():
    return f"{WORKSPACE_ID}:external_vault"


# ---------------------------------------------------------------------------
# ListExternalProtocols
# ---------------------------------------------------------------------------


class TestListExternalProtocols:
    @pytest.mark.asyncio
    async def test_success(self):
        gateway = FakeGateway(
            protocols=[
                {"id": 1, "name": "P1", "readout_definitions": [{"name": "R1", "data_type": "Number"}]},
            ]
        )
        uc = ListExternalProtocols(
            gateway=gateway,
            secret_provider=FakeSecretProvider({_secret_key(): "key123"}),
            settings_repo=FakeWorkspaceSettingsRepo(),
            api_key_repo=FakeApiKeyRepo(),
            uow=FakeUoW(),
        )
        result = await uc(ListExternalProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Success)
        summaries = result.unwrap()
        assert len(summaries) == 1
        assert summaries[0].name == "P1"

    @pytest.mark.asyncio
    async def test_no_vault_id_configured(self):
        uc = ListExternalProtocols(
            gateway=FakeGateway(),
            secret_provider=FakeSecretProvider(),
            settings_repo=FakeWorkspaceSettingsRepo(external_vault_id=None),
            api_key_repo=FakeApiKeyRepo(),
            uow=FakeUoW(),
        )
        result = await uc(ListExternalProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_no_api_key_configured(self):
        uc = ListExternalProtocols(
            gateway=FakeGateway(),
            secret_provider=FakeSecretProvider(),
            settings_repo=FakeWorkspaceSettingsRepo(),
            api_key_repo=FakeApiKeyRepo(has_active_key=False),
            uow=FakeUoW(),
        )
        result = await uc(ListExternalProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_no_secret_found(self):
        uc = ListExternalProtocols(
            gateway=FakeGateway(),
            secret_provider=FakeSecretProvider(),  # empty — no secret stored
            settings_repo=FakeWorkspaceSettingsRepo(),
            api_key_repo=FakeApiKeyRepo(),
            uow=FakeUoW(),
        )
        result = await uc(ListExternalProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_viewer_rejected(self):
        uc = ListExternalProtocols(
            gateway=FakeGateway(),
            secret_provider=FakeSecretProvider(),
            settings_repo=FakeWorkspaceSettingsRepo(),
            api_key_repo=FakeApiKeyRepo(),
            uow=FakeUoW(),
        )
        with pytest.raises(AuthorizationError):
            await uc(ListExternalProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth(role="viewer"))

    @pytest.mark.asyncio
    async def test_vault_auth_error_returns_failure(self):
        class AuthErrorGateway:
            async def list_protocols(self, vault_id, api_key):
                raise VaultAuthError("Invalid key")

        uc = ListExternalProtocols(
            gateway=AuthErrorGateway(),
            secret_provider=FakeSecretProvider({_secret_key(): "key123"}),
            settings_repo=FakeWorkspaceSettingsRepo(),
            api_key_repo=FakeApiKeyRepo(),
            uow=FakeUoW(),
        )
        result = await uc(ListExternalProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth())
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# PreviewExternalProtocolImport
# ---------------------------------------------------------------------------


class TestPreviewExternalProtocolImport:
    @pytest.mark.asyncio
    async def test_success_with_mapping(self):
        uc = PreviewExternalProtocolImport(
            gateway=FakeGateway(detail=_protocol_detail()),
            secret_provider=FakeSecretProvider({_secret_key(): "key123"}),
            settings_repo=FakeWorkspaceSettingsRepo(),
            api_key_repo=FakeApiKeyRepo(),
            uow=FakeUoW(),
        )
        result = await uc(
            PreviewExternalProtocolImportQuery(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=_make_auth(),
        )
        assert isinstance(result, Success)
        mapping = result.unwrap()
        assert mapping.name == "Kinase IC50"
        assert len(mapping.readouts) == 2
        assert mapping.readouts[0].data_type == ReadoutDataType.NUMERIC

    @pytest.mark.asyncio
    async def test_not_found_returns_failure(self):
        uc = PreviewExternalProtocolImport(
            gateway=FakeGateway(detail=None),  # will raise VaultAuthError
            secret_provider=FakeSecretProvider({_secret_key(): "key123"}),
            settings_repo=FakeWorkspaceSettingsRepo(),
            api_key_repo=FakeApiKeyRepo(),
            uow=FakeUoW(),
        )
        result = await uc(
            PreviewExternalProtocolImportQuery(workspace_id=WORKSPACE_ID, external_protocol_id=999),
            auth=_make_auth(),
        )
        assert isinstance(result, Failure)


# ---------------------------------------------------------------------------
# ImportExternalProtocol
# ---------------------------------------------------------------------------


class TestImportExternalProtocol:
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

        return ImportExternalProtocol(
            gateway=FakeGateway(detail=detail or _protocol_detail()),
            secret_provider=FakeSecretProvider({_secret_key(): "key123"}),
            settings_repo=FakeWorkspaceSettingsRepo(),
            api_key_repo=FakeApiKeyRepo(),
            uow=uow,
            protocol_repo=repo,
            dispatcher=dispatcher,
        ), repo

    @pytest.mark.asyncio
    async def test_success_creates_draft_protocol(self):
        uc, repo = self._make_uc()
        result = await uc(
            ImportExternalProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
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
            ImportExternalProtocolCommand(
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
            ImportExternalProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=_make_auth(),
        )
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_auth_required(self):
        uc, _repo = self._make_uc()
        result = await uc(
            ImportExternalProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=None,
        )
        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_conditions_mapped(self):
        uc, _repo = self._make_uc()
        result = await uc(
            ImportExternalProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
            auth=_make_auth(),
        )
        assert isinstance(result, Success)
        protocol = result.unwrap()
        assert len(protocol.condition_definitions) == 1
        assert protocol.condition_definitions[0].name == "Cell Type"
