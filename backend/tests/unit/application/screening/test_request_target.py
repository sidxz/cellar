"""RequestTarget — create a target in prot-cellar with the caller's tokens, mirror it at once."""

from __future__ import annotations

import uuid

import pytest
from returns.result import Failure, Success

from cellar.application.screening.request_target import RequestTarget, RequestTargetCommand
from cellar.application.screening.target_source import NewTarget, SourceTarget
from cellar.domain.screening_assay.enums import TargetType
from cellar.domain.shared.errors import (
    AuthorizationError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from tests.fakes.fake_auth import FakeAuth
from tests.unit.application.screening.test_sync_targets import FakeRepo, FakeUoW

pytestmark = pytest.mark.asyncio

WS = uuid.uuid4()
HEADERS = {"authorization": "Bearer x", "x-authz-token": "y"}
HUMAN = "http://purl.bioontology.org/ontology/NCBITAXON/9606"
NEW_ID = uuid.uuid4()


class FakeSource:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[NewTarget, dict]] = []

    async def create_target(self, request: NewTarget, *, forwarded_headers) -> SourceTarget:
        self.calls.append((request, dict(forwarded_headers)))
        if self.error:
            raise self.error
        return SourceTarget(
            NEW_ID, request.name, request.target_type, "Homo sapiens", request.chembl_id, 1
        )


def _cmd(**overrides) -> RequestTargetCommand:
    fields = {
        "workspace_id": WS,
        "name": " hERG ",
        "target_type": "single_protein",
        "organism_term_id": HUMAN,
        "organism_label": "Homo sapiens",
        "chembl_id": " chembl240 ",
        "protein_identifier": " Q12809 ",
        "forwarded_headers": HEADERS,
    }
    return RequestTargetCommand(**{**fields, **overrides})


def _uc(source: FakeSource, repo: FakeRepo | None = None, uow: FakeUoW | None = None):
    return RequestTarget(uow or FakeUoW(), repo or FakeRepo(), source)


async def test_success_creates_in_source_and_upserts_the_mirror():
    source, repo, uow = FakeSource(), FakeRepo(), FakeUoW()

    result = await _uc(source, repo, uow)(_cmd(), auth=FakeAuth(role="editor", workspace_id=WS))

    assert isinstance(result, Success)
    target = result.unwrap()
    assert source.calls == [
        (
            NewTarget(
                name="hERG",
                target_type="single_protein",
                organism_tax_id=9606,
                organism_label="Homo sapiens",
                chembl_id="CHEMBL240",
                protein_identifier="Q12809",
            ),
            HEADERS,
        )
    ]
    assert repo.saved == [target]
    assert target.id == NEW_ID
    assert target.workspace_id == WS
    assert target.name == "hERG"
    assert target.target_type is TargetType.SINGLE_PROTEIN
    assert target.organism == "Homo sapiens"
    assert target.source_version == 1
    assert uow.commits == 1


async def test_component_free_type_drops_a_stale_protein_identifier():
    source = FakeSource()
    result = await _uc(source)(
        _cmd(target_type="cell_line", chembl_id=None),
        auth=FakeAuth(role="editor", workspace_id=WS),
    )
    assert isinstance(result, Success)
    assert source.calls[0][0].protein_identifier is None


async def test_viewer_is_refused_before_prot_cellar_is_called():
    source = FakeSource()
    with pytest.raises(AuthorizationError):
        await _uc(source)(_cmd(), auth=FakeAuth(role="viewer", workspace_id=WS))
    assert source.calls == []


async def test_prot_cellar_403_maps_to_forbidden_and_nothing_is_mirrored():
    source = FakeSource(error=AuthorizationError("You need editor access in ProtCellar"))
    repo = FakeRepo()
    result = await _uc(source, repo)(_cmd(), auth=FakeAuth(role="editor", workspace_id=WS))
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), AuthorizationError)
    assert result.failure().message == "You need editor access in ProtCellar"
    assert repo.saved == []


async def test_organism_missing_in_prot_cellar_maps_to_not_found():
    source = FakeSource(error=NotFoundError("Organism", "Homo sapiens"))
    result = await _uc(source)(_cmd(), auth=FakeAuth(role="editor", workspace_id=WS))
    assert isinstance(result.failure(), NotFoundError)


async def test_prot_cellar_down_maps_to_service_unavailable():
    source = FakeSource(error=ServiceUnavailableError("prot-cellar unreachable"))
    result = await _uc(source)(_cmd(), auth=FakeAuth(role="editor", workspace_id=WS))
    assert isinstance(result.failure(), ServiceUnavailableError)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"name": "  "}, "name"),
        ({"target_type": "protein_complex"}, "type"),
        ({"target_type": "martian"}, "type"),
        ({"organism_term_id": "free_text:human"}, "organism"),
        ({"organism_term_id": "http://purl.obolibrary.org/obo/CLO_0000001"}, "organism"),
        ({"protein_identifier": None}, "UniProt"),
        ({"protein_identifier": "  "}, "UniProt"),
        ({"target_type": "domain", "protein_identifier": None}, "UniProt"),
        ({"chembl_id": "240"}, "ChEMBL"),
    ],
)
async def test_invalid_input_fails_without_calling_prot_cellar(overrides, message):
    source = FakeSource()
    result = await _uc(source)(_cmd(**overrides), auth=FakeAuth(role="editor", workspace_id=WS))
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), ValidationError)
    assert message in result.failure().message
    assert source.calls == []
