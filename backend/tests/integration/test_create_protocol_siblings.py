"""A new protocol that shares its base name tells its siblings apart in the same save."""

import uuid

from returns.result import Failure

from cellar.application.screening.create_protocol import (
    CreateProtocol,
    CreateProtocolCommand,
    SiblingDiscriminator,
)
from cellar.application.screening.preview_protocol_name import (
    PreviewProtocolName,
    PreviewProtocolNameQuery,
    SiblingRename,
)
from cellar.domain.screening_assay.enums import NameFlag, ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import (
    ConcurrencyConflictError,
    ConflictError,
    DomainError,
    ValidationError,
)
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.infrastructure.di._screening import _name_service
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.target_repository import (
    SQLAlchemyTargetRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_category_repository import (  # noqa: E501
    SQLAlchemyProtocolCategoryRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_form_repository import (  # noqa: E501
    SQLAlchemyProtocolFormRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests._auth import admin_auth

BASE = "M. tuberculosis growth inhibition"
MTB = {
    "term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773",
    "label": "Mycobacterium tuberculosis",
    "ontology_source": "NCBITAXON",
}


class _NoEvents:
    async def dispatch_all(self, events):
        return None


async def _seed_bare(
    session_factory, ws, user, *, status="draft", locked=False, discriminator=None
):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolCategoryRepository(uow).save(
            ProtocolCategory.create(workspace_id=ws, label="Growth inhibition")
        )
        pid = uuid.uuid4()
        p = Protocol.create(
            workspace_id=ws,
            name=f"{BASE} [{discriminator}]" if discriminator else BASE,
            name_base=BASE,
            discriminator=discriminator,
            protocol_type=ProtocolType.WHOLE_CELL,
            category="Growth inhibition",
            created_by=user,
            code="PRT-00001",
            ontology_annotations={"organism": [OntologyTerm(**MTB)]},
            readout_definitions=[
                ReadoutDefinition(protocol_id=pid, name="MIC", data_type=ReadoutDataType.NUMERIC)
            ],
        )
        if status == "active":
            p.publish()
        if locked:
            p.lock(locked_by=user, reason="frozen")
        await SQLAlchemyProtocolRepository(uow).save(p)
        await uow.commit()
    return p


def _uc(session_factory, repo_cls=SQLAlchemyProtocolRepository):
    uow = AsyncUnitOfWork(session_factory)
    return CreateProtocol(
        uow,
        repo_cls(uow),
        _NoEvents(),
        names=_name_service(uow),
        form_repo=SQLAlchemyProtocolFormRepository(uow),
        target_repo=SQLAlchemyTargetRepository(uow),
    )


def _cmd(ws, **kw):
    return CreateProtocolCommand(
        workspace_id=ws,
        protocol_type="whole_cell",
        category="Growth inhibition",
        discriminator="hypoxia",
        ontology_annotations={"organism": [MTB]},
        readout_definitions=[{"name": "MIC", "data_type": "numeric"}],
        **kw,
    )


async def _load(session_factory, ws, pid):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        return await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(ws, pid)


async def test_draft_sibling_is_renamed_in_the_same_save(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id)
    result = await _uc(session_factory)(
        _cmd(
            workspace_id,
            sibling_discriminators=[
                SiblingDiscriminator(protocol_id=bare.id, discriminator="MABA")
            ],
        ),
        auth=admin_auth(workspace_id, user_id),
    )
    assert result.unwrap().name == f"{BASE} [hypoxia]"
    sibling = await _load(session_factory, workspace_id, bare.id)
    assert sibling.name == f"{BASE} [MABA]" and sibling.name_flag is None
    assert any(a.label == BASE for a in sibling.aliases)  # "formerly"


async def test_blank_leaves_the_sibling_flagged(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id)
    (
        await _uc(session_factory)(_cmd(workspace_id), auth=admin_auth(workspace_id, user_id))
    ).unwrap()
    sibling = await _load(session_factory, workspace_id, bare.id)
    assert sibling.name_flag == NameFlag.NEEDS_DISCRIMINATOR


async def test_published_sibling_needs_a_reason_and_nothing_is_saved_without_one(
    session_factory, workspace_id, user_id
):
    bare = await _seed_bare(session_factory, workspace_id, user_id, status="active")
    try:
        result = await _uc(session_factory)(
            _cmd(
                workspace_id,
                sibling_discriminators=[
                    SiblingDiscriminator(protocol_id=bare.id, discriminator="MABA")
                ],
            ),
            auth=admin_auth(workspace_id, user_id),
        )
        failed = isinstance(result, Failure)
    except DomainError:
        failed = True
    assert failed
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        names = [
            p.name for p in await SQLAlchemyProtocolRepository(uow).find_by_workspace(workspace_id)
        ]
    assert names == [BASE]  # the new protocol was not saved either


async def test_published_sibling_with_reason_is_corrected(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id, status="active")
    (
        await _uc(session_factory)(
            _cmd(
                workspace_id,
                sibling_discriminators=[
                    SiblingDiscriminator(
                        protocol_id=bare.id,
                        discriminator="MABA",
                        reason="Distinguish from the new hypoxia assay",
                    )
                ],
            ),
            auth=admin_auth(workspace_id, user_id),
        )
    ).unwrap()
    assert (await _load(session_factory, workspace_id, bare.id)).name == f"{BASE} [MABA]"


async def test_locked_sibling_is_refused_and_nothing_is_saved(
    session_factory, workspace_id, user_id
):
    bare = await _seed_bare(session_factory, workspace_id, user_id, status="active", locked=True)
    try:
        result = await _uc(session_factory)(
            _cmd(
                workspace_id,
                sibling_discriminators=[
                    SiblingDiscriminator(protocol_id=bare.id, discriminator="MABA", reason="x")
                ],
            ),
            auth=admin_auth(workspace_id, user_id),
        )
        failed = isinstance(result, Failure)
    except DomainError:
        failed = True
    assert failed
    assert (await _load(session_factory, workspace_id, bare.id)).name == BASE


async def _names_in(session_factory, ws):
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        return [p.name for p in await SQLAlchemyProtocolRepository(uow).find_by_workspace(ws)]


async def _sibling_failure(session_factory, ws, user, sibling_id, discriminator, uc=None):
    """Create with one sibling rename that must fail: the failure, after checking nothing saved."""
    before = await _names_in(session_factory, ws)
    result = await (uc or _uc(session_factory))(
        _cmd(
            ws,
            sibling_discriminators=[
                SiblingDiscriminator(
                    protocol_id=sibling_id, discriminator=discriminator, reason="x"
                )
            ],
        ),
        auth=admin_auth(ws, user),
    )
    assert isinstance(result, Failure)
    assert await _names_in(session_factory, ws) == before  # rolled back
    return result.failure()


async def test_refused_sibling_is_named_in_the_error(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id, status="active", locked=True)
    error = await _sibling_failure(session_factory, workspace_id, user_id, bare.id, "MABA")
    assert isinstance(error, ConflictError) and error.message.startswith("PRT-00001: ")


async def test_a_sibling_no_longer_bare_is_named_by_its_code(
    session_factory, workspace_id, user_id
):
    other = await _seed_bare(session_factory, workspace_id, user_id, discriminator="MABA")
    error = await _sibling_failure(session_factory, workspace_id, user_id, other.id, "REMA")
    assert isinstance(error, ValidationError)
    assert error.message == "PRT-00001 does not share this protocol's name"


async def test_a_sibling_name_clash_names_the_sibling(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id)
    error = await _sibling_failure(session_factory, workspace_id, user_id, bare.id, "hypoxia")
    # The holder is the new protocol, whose code is rolled back: only the name is said.
    assert isinstance(error, ConflictError)
    assert error.message == f'PRT-00001: "{BASE} [hypoxia]" is already taken'


class _StaleRepo(SQLAlchemyProtocolRepository):
    """Hands out the sibling as someone else saved it after it was loaded."""

    async def find_by_id_in_workspace(self, workspace_id, id):
        protocol = await super().find_by_id_in_workspace(workspace_id, id)
        if protocol is not None and protocol.code == "PRT-00001":
            protocol.version -= 1
        return protocol


async def test_a_sibling_changed_meanwhile_is_named(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id)
    error = await _sibling_failure(
        session_factory,
        workspace_id,
        user_id,
        bare.id,
        "MABA",
        uc=_uc(session_factory, _StaleRepo),
    )
    assert isinstance(error, ConcurrencyConflictError)
    assert error.message.startswith("PRT-00001: ")


async def _preview(session_factory, ws, user, bare, proposed):
    uow = AsyncUnitOfWork(session_factory)
    uc = PreviewProtocolName(
        uow,
        SQLAlchemyProtocolRepository(uow),
        _name_service(uow),
        form_repo=SQLAlchemyProtocolFormRepository(uow),
        target_repo=SQLAlchemyTargetRepository(uow),
    )
    result = await uc(
        PreviewProtocolNameQuery(
            workspace_id=ws,
            category="Growth inhibition",
            ontology_annotations={"organism": [MTB]},
            discriminator="hypoxia",
            sibling_discriminators={bare.id: proposed},
        ),
        auth=admin_auth(ws, user),
    )
    return result.unwrap().sibling_renames


async def test_preview_shows_the_sibling_rename(session_factory, workspace_id, user_id):
    bare = await _seed_bare(session_factory, workspace_id, user_id)
    renames = await _preview(session_factory, workspace_id, user_id, bare, "MABA")
    assert renames == [SiblingRename(bare.id, "PRT-00001", f"{BASE} [MABA]", None)]


async def test_preview_flags_a_sibling_name_the_new_protocol_already_takes(
    session_factory, workspace_id, user_id
):
    bare = await _seed_bare(session_factory, workspace_id, user_id)
    renames = await _preview(session_factory, workspace_id, user_id, bare, "hypoxia")
    assert renames[0].error == "Same name as another protocol"


async def test_nicknames_are_added_at_create(session_factory, workspace_id, user_id):
    await _seed_bare(session_factory, workspace_id, user_id)
    created = (
        await _uc(session_factory)(
            _cmd(workspace_id, nicknames=["LORA", "  low oxygen recovery  "]),
            auth=admin_auth(workspace_id, user_id),
        )
    ).unwrap()
    loaded = await _load(session_factory, workspace_id, created.id)
    assert {a.label for a in loaded.aliases if a.kind.value == "nickname"} == {
        "LORA",
        "low oxygen recovery",
    }
