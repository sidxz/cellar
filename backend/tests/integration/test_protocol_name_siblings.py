"""Generated-name collisions against the real database: siblings, flags, and the create race."""

import asyncio
import uuid

from cellar.domain.screening_assay.enums import NameFlag, ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.infrastructure.di._screening import _name_service
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.protocol_category_repository import (  # noqa: E501
    SQLAlchemyProtocolCategoryRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

BASE = "M. tuberculosis growth inhibition"
MTB = OntologyTerm(
    term_id="http://purl.bioontology.org/ontology/NCBITAXON/1773",
    label="Mycobacterium tuberculosis",
    ontology_source="NCBITAXON",
)


def _protocol(ws, user, code, *, name=BASE, discriminator=None):
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=ws,
        name=name,
        name_base=BASE,
        discriminator=discriminator,
        protocol_type=ProtocolType.WHOLE_CELL,
        category="Growth inhibition",
        created_by=user,
        code=code,
        ontology_annotations={"organism": [MTB]},
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name="Signal", data_type=ReadoutDataType.NUMERIC)
        ],
    )


async def _seed(uow, ws, user):
    async with uow:
        await SQLAlchemyProtocolCategoryRepository(uow).save(
            ProtocolCategory.create(workspace_id=ws, label="Growth inhibition")
        )
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(
            _protocol(ws, user, "PRT-00001", name=f"{BASE} [OD600]", discriminator="OD600")
        )
        bare = _protocol(ws, user, "PRT-00002")
        await repo.save(bare)
        await uow.commit()
    return bare


async def test_siblings_share_the_base_one_per_code(uow, workspace_id, user_id):
    await _seed(uow, workspace_id, user_id)
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        both = await repo.find_name_siblings(
            workspace_id, base=BASE.lower(), exclude_code="PRT-00003"
        )
        one = await repo.find_name_siblings(workspace_id, base=BASE, exclude_code="PRT-00002")
    assert {s.code for s in both} == {"PRT-00001", "PRT-00002"}
    assert [s.code for s in one] == ["PRT-00001"]


async def test_system_apply_flags_the_bare_sibling(session_factory, uow, workspace_id, user_id):
    bare = await _seed(uow, workspace_id, user_id)
    third = _protocol(workspace_id, user_id, "PRT-00003", discriminator="hypoxia")
    work = AsyncUnitOfWork(session_factory)
    async with work:
        result = await _name_service(work).apply(
            third, reason="Created", person=False, allow_incomplete=True
        )
        assert result.unwrap().rendered.name == f"{BASE} [hypoxia]"
        await SQLAlchemyProtocolRepository(work).save(third)
        await work.commit()
    async with uow:
        reloaded = await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(
            workspace_id, bare.id
        )
    assert reloaded.name_flag == NameFlag.NEEDS_DISCRIMINATOR
    assert third.name == f"{BASE} [hypoxia]" and third.name_flag is None


async def test_concurrent_creates_see_each_other(session_factory, workspace_id, user_id):
    async with AsyncUnitOfWork(session_factory) as seed:
        await SQLAlchemyProtocolCategoryRepository(seed).save(
            ProtocolCategory.create(workspace_id=workspace_id, label="Growth inhibition")
        )
        await seed.commit()

    async def create(code):
        work = AsyncUnitOfWork(session_factory)
        async with work:
            service = _name_service(work)
            await SQLAlchemyProtocolRepository(work).lock_naming(workspace_id)
            derivation = await service.derive(
                workspace_id,
                category="Growth inhibition",
                target_ids=[],
                annotations={"organism": [MTB]},
                discriminator=None,
                exclude_code=code,
            )
            if not derivation.needs_discriminator:
                await SQLAlchemyProtocolRepository(work).save(
                    _protocol(workspace_id, user_id, code)
                )
            await asyncio.sleep(0.2)  # hold the lock while the other create waits
            await work.commit()
        return derivation.needs_discriminator

    outcomes = await asyncio.gather(create("PRT-00011"), create("PRT-00012"))
    assert sorted(outcomes) == [False, True]
    async with AsyncUnitOfWork(session_factory) as check:
        siblings = await SQLAlchemyProtocolRepository(check).find_name_siblings(
            workspace_id, base=BASE, exclude_code=None
        )
    assert len(siblings) == 1
