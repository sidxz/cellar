"""Tests for CDD import use cases with fakes."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from returns.result import Failure, Success

from cellar.application.cdd_import.check_cdd_molecule_identifiers import (
    CheckCddMoleculeIdentifiers,
    CheckCddMoleculeIdentifiersQuery,
)
from cellar.application.cdd_import.errors import CddAuthError
from cellar.application.cdd_import.import_cdd_protocol import (
    ImportCddProtocol,
    ImportCddProtocolCommand,
)
from cellar.application.cdd_import.list_cdd_protocols import (
    ListCddProtocols,
    ListCddProtocolsQuery,
)
from cellar.application.cdd_import.molecule_identifiers import MAX_IDENTIFIERS
from cellar.application.cdd_import.preview_cdd_protocol_import import (
    PreviewCddProtocolImport,
    PreviewCddProtocolImportQuery,
)
from cellar.application.cdd_import.registration_mapping import default_cdd_registration_mapping
from cellar.application.cdd_import.start_cdd_molecule_import import (
    StartCddMoleculeImport,
    StartCddMoleculeImportCommand,
)
from cellar.application.screening.protocol_naming_service import NameDerivation
from cellar.application.workspace_config.get_data_source_for_import import (
    DataSourceImportConfig,
)
from cellar.domain.screening_assay.enums import ReadoutDataType
from cellar.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ValidationError,
)
from cellar.domain.shared.protocol_naming import RenderedName
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
    def __init__(
        self, vault_id="12345", create_batch_on_duplicate: bool = False, registration_mapping=...
    ):
        self.config = {"vault_id": vault_id} if vault_id else {}
        self.api_key_name = "key123"
        self.entity_mappings = []
        self.registration_mapping = (
            default_cdd_registration_mapping()
            if registration_mapping is ...
            else registration_mapping
        )
        self._create_batch_on_duplicate = create_batch_on_duplicate

    @property
    def create_batch_on_duplicate(self) -> bool:
        return self._create_batch_on_duplicate


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
        create_batch_on_duplicate: bool = False,
        registration_mapping=...,
        result=None,
    ):
        if result is None:
            result = Success(
                DataSourceImportConfig(
                    data_source=_FakeDataSource(
                        vault_id=vault_id,
                        create_batch_on_duplicate=create_batch_on_duplicate,
                        registration_mapping=registration_mapping,
                    ),
                    api_key=api_key,
                )
            )
        self._result = result

    async def __call__(self, query):
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
                {
                    "id": 1,
                    "name": "P1",
                    "readout_definitions": [{"name": "R1", "data_type": "Number"}],
                },
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
            await uc(
                ListCddProtocolsQuery(workspace_id=WORKSPACE_ID), auth=_make_auth(role="viewer")
            )

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

        names = MagicMock()
        names.derive = AsyncMock(
            return_value=NameDerivation(
                RenderedName(
                    name="Generated name",
                    base="Generated name",
                    missing=(),
                    discriminator_in_pattern=False,
                ),
                None,
                (),
                (),
                False,
            )
        )
        names.check = MagicMock(return_value=Success(None))
        names.flag_siblings = AsyncMock()
        return ImportCddProtocol(
            gateway=FakeGateway(detail=detail or _protocol_detail()),
            get_data_source=FakeGetDataSource(),
            uow=uow,
            protocol_repo=repo,
            dispatcher=dispatcher,
            names=names,
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
        # names are generated; the vault's name is kept as a nickname
        assert protocol.name == "Generated name"
        assert [a.label for a in protocol.aliases] == ["Kinase IC50"]
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
        # names are generated; the override is kept as a nickname
        assert result.unwrap().name == "Generated name"
        assert [a.label for a in result.unwrap().aliases] == ["My Custom Name"]

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
        with pytest.raises(AuthorizationError):
            await uc(
                ImportCddProtocolCommand(workspace_id=WORKSPACE_ID, external_protocol_id=1),
                auth=None,
            )

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


# ---------------------------------------------------------------------------
# StartCddMoleculeImport
# ---------------------------------------------------------------------------


class TestStartCddMoleculeImport:
    def _make_command(self) -> StartCddMoleculeImportCommand:
        return StartCddMoleculeImportCommand(
            workspace_id=WORKSPACE_ID,
            submitted_by=USER_ID,
            import_mode="full_vault",
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("create_batch_on_duplicate", [True, False])
    async def test_create_batch_on_duplicate_propagates_to_orchestrator(
        self, create_batch_on_duplicate: bool
    ):
        orchestrator = AsyncMock()
        orchestrator.start = AsyncMock(return_value="wf-123")

        uc = StartCddMoleculeImport(
            get_data_source=FakeGetDataSource(create_batch_on_duplicate=create_batch_on_duplicate),
            orchestrator=orchestrator,
        )
        result = await uc(self._make_command(), auth=_make_auth())

        assert isinstance(result, Success)
        orchestrator.start.assert_called_once()
        captured_request = orchestrator.start.call_args[0][0]
        assert captured_request.create_batch_on_duplicate is create_batch_on_duplicate

    @pytest.mark.asyncio
    async def test_no_vault_id_returns_failure(self):
        orchestrator = AsyncMock()
        uc = StartCddMoleculeImport(
            get_data_source=FakeGetDataSource(vault_id=None),
            orchestrator=orchestrator,
        )
        result = await uc(self._make_command(), auth=_make_auth())
        assert isinstance(result, Failure)
        orchestrator.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_the_field_mapping_is_snapshot_into_the_run(self):
        orchestrator = AsyncMock()
        orchestrator.start = AsyncMock(return_value="wf-1")
        uc = StartCddMoleculeImport(get_data_source=FakeGetDataSource(), orchestrator=orchestrator)

        await uc(self._make_command(), auth=_make_auth())

        request = orchestrator.start.call_args[0][0]
        assert request.registration_mapping == default_cdd_registration_mapping()

    @pytest.mark.asyncio
    async def test_a_source_without_field_mapping_never_starts(self):
        orchestrator = AsyncMock()
        uc = StartCddMoleculeImport(
            get_data_source=FakeGetDataSource(registration_mapping=None),
            orchestrator=orchestrator,
        )
        result = await uc(self._make_command(), auth=_make_auth())
        assert isinstance(result, Failure)
        assert "no field mapping" in str(result.failure())
        orchestrator.start.assert_not_called()

    def _filtered(self, filter_criteria: dict | None, *, mode: str = "filtered"):
        return StartCddMoleculeImportCommand(
            workspace_id=WORKSPACE_ID,
            submitted_by=USER_ID,
            import_mode=mode,
            filter_criteria=filter_criteria,
        )

    def _make_uc(self):
        orchestrator = AsyncMock()
        orchestrator.start = AsyncMock(return_value="wf-789")
        uc = StartCddMoleculeImport(get_data_source=FakeGetDataSource(), orchestrator=orchestrator)
        return uc, orchestrator

    @pytest.mark.asyncio
    async def test_filtered_import_hands_the_tidied_names_to_the_orchestrator(self):
        uc, orchestrator = self._make_uc()
        command = self._filtered({"names": [" SACC-0001 ", "sacc-0001", "", "SACC-0002"]})
        result = await uc(command, auth=_make_auth())

        assert isinstance(result, Success)
        request = orchestrator.start.call_args[0][0]
        assert request.import_mode == "filtered"
        assert request.filter_criteria == {"names": ["SACC-0001", "SACC-0002"]}

    @pytest.mark.asyncio
    async def test_filtered_import_keeps_a_name_with_spaces_whole(self):
        uc, orchestrator = self._make_uc()
        result = await uc(
            self._filtered({"names": ["16:0  CoA", "Palmitoyl CoA"]}), auth=_make_auth()
        )

        assert isinstance(result, Success)
        request = orchestrator.start.call_args[0][0]
        assert request.filter_criteria == {"names": ["16:0 CoA", "Palmitoyl CoA"]}

    @pytest.mark.parametrize("filter_criteria", [None, {}, {"names": []}, {"names": ["  "]}])
    @pytest.mark.asyncio
    async def test_filtered_import_without_names_never_starts(self, filter_criteria):
        uc, orchestrator = self._make_uc()
        result = await uc(self._filtered(filter_criteria), auth=_make_auth())
        assert isinstance(result.failure(), ValidationError)
        orchestrator.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_filtered_import_refuses_more_names_than_the_limit(self):
        uc, orchestrator = self._make_uc()
        names = [f"SACC-{i}" for i in range(MAX_IDENTIFIERS + 1)]
        result = await uc(self._filtered({"names": names}), auth=_make_auth())
        assert isinstance(result.failure(), ValidationError)
        orchestrator.start.assert_not_called()

    @pytest.mark.parametrize("mode", ["full_vault", "sync"])
    @pytest.mark.asyncio
    async def test_names_with_an_unfiltered_mode_are_refused_not_ignored(self, mode):
        uc, orchestrator = self._make_uc()
        command = self._filtered({"names": ["SACC-0001"]}, mode=mode)
        result = await uc(command, auth=_make_auth())
        assert isinstance(result.failure(), ValidationError)
        orchestrator.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_viewer_cannot_start_a_filtered_import(self):
        uc, orchestrator = self._make_uc()
        with pytest.raises(AuthorizationError):
            await uc(self._filtered({"names": ["SACC-0001"]}), auth=_make_auth(role="viewer"))
        orchestrator.start.assert_not_called()


# ---------------------------------------------------------------------------
# CheckCddMoleculeIdentifiers
# ---------------------------------------------------------------------------


class FakeMoleculeGateway:
    """Answers a name lookup from a fixed set of vault molecules; records what was asked."""

    def __init__(self, molecules=None, error: Exception | None = None):
        self._molecules = molecules or []
        self._error = error
        self.calls: list[tuple[str, str, list[str]]] = []

    async def find_molecules_by_names(self, vault_id, api_key, names):
        self.calls.append((vault_id, api_key, names))
        if self._error:
            raise self._error
        wanted = {n.casefold() for n in names}
        return [
            m
            for m in self._molecules
            if {m["name"].casefold(), *(s.casefold() for s in m["synonyms"])} & wanted
        ]


VAULT_MOLECULES = [
    {"id": 11, "name": "SACC-0001", "synonyms": ["ASA"]},
    {"id": 12, "name": "SACC-0002", "synonyms": []},
    {"id": 14, "name": "16:0 CoA", "synonyms": ["Palmitoyl CoA"]},
]


class TestCheckCddMoleculeIdentifiers:
    def _query(self, text, workspace_id=WORKSPACE_ID):
        return CheckCddMoleculeIdentifiersQuery(workspace_id=workspace_id, text=text)

    def _make_uc(self, gateway=None, get_data_source=None):
        gateway = gateway or FakeMoleculeGateway(VAULT_MOLECULES)
        uc = CheckCddMoleculeIdentifiers(
            gateway=gateway, get_data_source=get_data_source or FakeGetDataSource()
        )
        return uc, gateway

    @pytest.mark.asyncio
    async def test_reports_found_and_not_found(self):
        uc, gateway = self._make_uc()
        result = await uc(self._query("SACC-0001\nASA\nSACC-0099"), auth=_make_auth())

        match = result.unwrap()
        assert match.found == ["SACC-0001", "ASA"]
        assert match.not_found == ["SACC-0099"]
        assert gateway.calls == [("12345", "key123", ["SACC-0001", "ASA", "SACC-0099"])]

    @pytest.mark.asyncio
    async def test_a_name_with_spaces_is_asked_about_whole(self):
        uc, gateway = self._make_uc()
        result = await uc(self._query("16:0 CoA\nPalmitoyl  CoA, Acetyl CoA"), auth=_make_auth())

        match = result.unwrap()
        assert match.found == ["16:0 CoA", "Palmitoyl CoA"]
        assert match.not_found == ["Acetyl CoA"]
        assert gateway.calls[0][2] == ["16:0 CoA", "Palmitoyl CoA", "Acetyl CoA"]

    @pytest.mark.asyncio
    async def test_duplicates_and_blanks_are_asked_about_once(self):
        uc, gateway = self._make_uc()
        result = await uc(
            self._query("SACC-0002\n sacc-0002\n\nSACC-0099, SACC-0099"),
            auth=_make_auth(),
        )

        match = result.unwrap()
        assert match.found == ["SACC-0002"]
        assert match.not_found == ["SACC-0099"]
        assert gateway.calls[0][2] == ["SACC-0002", "SACC-0099"]

    @pytest.mark.parametrize("text", ["", " \n , ;\t"])
    @pytest.mark.asyncio
    async def test_an_empty_list_is_refused_without_asking_the_vault(self, text):
        uc, gateway = self._make_uc()
        result = await uc(self._query(text), auth=_make_auth())
        assert isinstance(result.failure(), ValidationError)
        assert gateway.calls == []

    @pytest.mark.asyncio
    async def test_more_identifiers_than_the_limit_are_refused(self):
        uc, gateway = self._make_uc()
        text = "\n".join(f"SACC-{i}" for i in range(MAX_IDENTIFIERS + 1))
        result = await uc(self._query(text), auth=_make_auth())
        assert isinstance(result.failure(), ValidationError)
        assert gateway.calls == []

    @pytest.mark.asyncio
    async def test_viewer_rejected(self):
        uc, gateway = self._make_uc()
        with pytest.raises(AuthorizationError):
            await uc(self._query("SACC-0001"), auth=_make_auth(role="viewer"))
        assert gateway.calls == []

    @pytest.mark.asyncio
    async def test_another_workspace_is_refused(self):
        uc, gateway = self._make_uc()
        with pytest.raises(NotFoundError):
            await uc(self._query("SACC-0001", workspace_id=uuid.uuid4()), auth=_make_auth())
        assert gateway.calls == []

    @pytest.mark.asyncio
    async def test_no_data_source_configured(self):
        uc, gateway = self._make_uc(
            get_data_source=FakeGetDataSource(
                result=Failure(NotFoundError("DataSource", "no active CDD source"))
            )
        )
        result = await uc(self._query("SACC-0001"), auth=_make_auth())
        assert isinstance(result, Failure)
        assert gateway.calls == []

    @pytest.mark.asyncio
    async def test_vault_refusing_the_key_is_a_failure_not_a_crash(self):
        uc, _ = self._make_uc(gateway=FakeMoleculeGateway(error=CddAuthError("Invalid key")))
        result = await uc(self._query("SACC-0001"), auth=_make_auth())
        assert isinstance(result.failure(), ValidationError)


class TestImportCddProtocolLegacyNames:
    @pytest.mark.asyncio
    async def test_vault_name_with_forbidden_characters_becomes_a_clean_nickname(self):
        uc, _ = TestImportCddProtocol()._make_uc()
        result = await uc(
            ImportCddProtocolCommand(
                workspace_id=WORKSPACE_ID,
                external_protocol_id=1,
                name_override="Kinase · IC50 — 2019",
            ),
            auth=_make_auth(),
        )
        assert isinstance(result, Success)
        assert [a.label for a in result.unwrap().aliases] == ["Kinase IC50 - 2019"]
