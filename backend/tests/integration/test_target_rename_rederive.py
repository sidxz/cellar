"""A registry target rename re-derives the linked protocol's name (real database)."""

import uuid

from cellar.application.screening.rederive_protocol_names import (
    RederiveProtocolNames,
    RederiveProtocolNamesCommand,
)
from cellar.domain.screening_assay.enums import (
    AliasKind,
    NameFlag,
    ProtocolType,
    ReadoutDataType,
    TargetType,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.target import Target
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings
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
from cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository import (  # noqa: E501
    SQLAlchemyWorkspaceSettingsRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

MTB = "Mycobacterium tuberculosis"
OLD = "Pks13TE Domain inhibition [FP]"


class _Dispatcher:
    async def dispatch_all(self, events):
        return None


def _target(ws, tid, name):
    return Target.from_mirror(
        id=tid,
        workspace_id=ws,
        name=name,
        target_type=TargetType.SINGLE_PROTEIN,
        organism=MTB,
        chembl_id=None,
        source_version=1,
    )


async def _seed(session_factory, ws, user, *, locked=False):
    tid = uuid.uuid4()
    pid = uuid.uuid4()
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyProtocolCategoryRepository(uow).save(
            ProtocolCategory.create(workspace_id=ws, label="Enzyme inhibition")
        )
        settings = WorkspaceSettings.create_default(workspace_id=ws)
        settings.set_home_organism({"term_id": "NCBITaxon:1773", "label": MTB})
        await SQLAlchemyWorkspaceSettingsRepository(uow).save(settings)
        await SQLAlchemyTargetRepository(uow).save(_target(ws, tid, "Pks13TE Domain"))
        protocol = Protocol.create(
            workspace_id=ws,
            name=OLD,
            name_base="Pks13TE Domain inhibition",
            discriminator="FP",
            category="Enzyme inhibition",
            protocol_type=ProtocolType.BIOCHEMICAL,
            created_by=user,
            code="PRT-00001",
            readout_definitions=[
                ReadoutDefinition(
                    protocol_id=pid, name="Signal", data_type=ReadoutDataType.NUMERIC
                )
            ],
        )
        if locked:
            protocol.publish()
            protocol.lock(locked_by=user, reason="review")
        repo = SQLAlchemyProtocolRepository(uow)
        await repo.save(protocol)
        await repo.add_direct_target(ws, protocol.id, tid)
        await uow.commit()
    return tid, protocol.id


async def _rename_and_rederive(session_factory, ws, tid, new_name):
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyTargetRepository(uow).save(_target(ws, tid, new_name))
        await uow.commit()
        ids = await SQLAlchemyProtocolRepository(uow).find_protocol_ids_by_direct_target(ws, tid)
    rederive = RederiveProtocolNames(
        uow_factory=lambda: AsyncUnitOfWork(session_factory),
        names_factory=_name_service,
        repo_factory=SQLAlchemyProtocolRepository,
        dispatcher=_Dispatcher(),
    )
    cmd = RederiveProtocolNamesCommand(
        workspace_id=ws, protocol_ids=ids, reason=f"Registry renamed Pks13TE Domain to {new_name}"
    )
    return (await rederive(cmd, auth=None)).unwrap()


async def _load(session_factory, ws, pid):
    async with AsyncUnitOfWork(session_factory) as uow:
        return await SQLAlchemyProtocolRepository(uow).find_by_id_in_workspace(ws, pid)


async def test_rename_follows_and_keeps_the_old_name(session_factory, workspace_id, user_id):
    tid, pid = await _seed(session_factory, workspace_id, user_id)
    report = await _rename_and_rederive(session_factory, workspace_id, tid, "Pks13 TE domain")
    p = await _load(session_factory, workspace_id, pid)
    assert report.renamed == 1
    assert p.name == "Pks13 TE domain inhibition [FP]"
    (alias,) = p.aliases
    assert (alias.label, alias.kind) == (OLD, AliasKind.FORMER)
    assert alias.reason.startswith("Registry renamed")


async def test_a_locked_protocol_is_still_relabeled(session_factory, workspace_id, user_id):
    tid, pid = await _seed(session_factory, workspace_id, user_id, locked=True)
    await _rename_and_rederive(session_factory, workspace_id, tid, "Pks13 TE domain")
    p = await _load(session_factory, workspace_id, pid)
    assert p.is_locked and p.name == "Pks13 TE domain inhibition [FP]"


async def test_a_name_over_the_limit_keeps_the_old_one_and_flags(
    session_factory, workspace_id, user_id
):
    tid, pid = await _seed(session_factory, workspace_id, user_id)
    # Target names cap at 200 characters; two long linked targets push the name past 400.
    other = uuid.uuid4()
    async with AsyncUnitOfWork(session_factory) as uow:
        await SQLAlchemyTargetRepository(uow).save(_target(workspace_id, other, "Y" * 199))
        await SQLAlchemyProtocolRepository(uow).add_direct_target(workspace_id, pid, other)
        await uow.commit()
    report = await _rename_and_rederive(session_factory, workspace_id, tid, "X" * 199)
    p = await _load(session_factory, workspace_id, pid)
    assert p.name == OLD and p.name_flag == NameFlag.NEEDS_FACTS
    assert report.flagged == 1
