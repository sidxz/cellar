"""Integration tests for tagging persistence (tag registry + links + backfill)."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from cellar.domain.workspace_config.tagging.events import TagCreated
from cellar.domain.workspace_config.tagging.tag import TagName, TaggableEntityType
from cellar.infrastructure.persistence.sqlalchemy.tagging.backfill_sql import (
    backfill_molecule_tags,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.molecule_tag_merge_side_effect import (
    MoleculeTagMergeSideEffect,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_link_repository import (
    get_tag_link_repository,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_repository import (
    SQLAlchemyTagRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


class TestTagRepository:
    async def test_get_or_create_inserts_and_emits_event(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            tag = await repo.get_or_create(ws_id, TagName(key="Project", value="Alpha"), user_id)
            events = await uow.commit()
        assert tag.key == "Project"
        assert tag.value == "Alpha"
        assert any(isinstance(e, TagCreated) for e in events)

    async def test_get_or_create_dedups_case_insensitively(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            first = await repo.get_or_create(ws_id, TagName(key="Env", value="Prod"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            second = await repo.get_or_create(ws_id, TagName(key="env", value="prod"), user_id)
            events = await uow.commit()
        assert first.id == second.id  # same registry row
        assert not [e for e in events if isinstance(e, TagCreated)]  # no second create

    async def test_valueless_tags_dedup(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            a = await repo.get_or_create(ws_id, TagName(key="favorite"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            b = await repo.get_or_create(ws_id, TagName(key="FAVORITE"), user_id)
            await uow.commit()
        assert a.id == b.id

    async def test_same_name_distinct_across_workspaces(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_a, ws_b, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            ta = await repo.get_or_create(ws_a, TagName(key="shared"), user_id)
            tb = await repo.get_or_create(ws_b, TagName(key="shared"), user_id)
            await uow.commit()
        assert ta.id != tb.id

    async def test_search_substring_and_created_by(self, uow: AsyncUnitOfWork) -> None:
        ws_id = uuid.uuid4()
        alice, bob = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            await repo.get_or_create(ws_id, TagName(key="kinase"), alice)
            await repo.get_or_create(ws_id, TagName(key="kinetics"), bob)
            await repo.get_or_create(ws_id, TagName(key="solubility"), alice)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            kin = await repo.search(ws_id, q="kin")
            mine = await repo.search(ws_id, created_by=alice)
        assert {t.key for t in kin} == {"kinase", "kinetics"}
        assert {t.key for t in mine} == {"kinase", "solubility"}

    async def test_search_key_equals_value(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            await repo.get_or_create(ws_id, TagName(key="own", value="dd"), user)
            await repo.get_or_create(ws_id, TagName(key="own", value="zz"), user)
            await repo.get_or_create(ws_id, TagName(key="tes", value="44"), user)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            own_dd = await repo.search(ws_id, q="own=dd")
            own_all = await repo.search(ws_id, q="own")
        # "own=dd" matches key AND value separately — not the literal "own=dd".
        assert {(t.key, t.value) for t in own_dd} == {("own", "dd")}
        assert {(t.key, t.value) for t in own_all} == {("own", "dd"), ("own", "zz")}

    async def test_search_orders_most_used_first(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            # 'zzz-popular' sorts last alphabetically but is used more.
            popular = await repo.get_or_create(ws_id, TagName(key="zzz-popular"), user)
            rare = await repo.get_or_create(ws_id, TagName(key="aaa-rare"), user)
            m1 = await _insert_molecule(uow, ws_id, "UM1")
            m2 = await _insert_molecule(uow, ws_id, "UM2")
            link = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link.add(ws_id, m1, popular.id, user)
            await link.add(ws_id, m2, popular.id, user)
            await link.add(ws_id, m1, rare.id, user)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            results = await repo.search(ws_id)
        # 2 uses beats 1 use, overriding alphabetical order (zzz before aaa).
        assert [t.key for t in results] == ["zzz-popular", "aaa-rare"]

    async def test_find_by_id_in_workspace_scoping(self, uow: AsyncUnitOfWork) -> None:
        ws_id, other_ws, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            tag = await repo.get_or_create(ws_id, TagName(key="x"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            assert await repo.find_by_id_in_workspace(ws_id, tag.id) is not None
            assert await repo.find_by_id_in_workspace(other_ws, tag.id) is None


async def _insert_molecule(
    uow: AsyncUnitOfWork, workspace_id: uuid.UUID, reg: str
) -> uuid.UUID:
    """Insert a minimal molecules row (+ a backing organization for the
    required originating_org_id FK). Each test uses a fresh workspace_id, so the
    organization's (workspace_id, name) stays unique across calls."""
    org_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
            "VALUES (:id, :ws, :name, 'internal', true, 1)"
        ),
        {"id": org_id, "ws": workspace_id, "name": f"org-{reg}"},
    )
    mol_id = uuid.uuid4()
    await uow.session.execute(
        text(
            "INSERT INTO molecules (id, workspace_id, registration_number, name, "
            "molecule_type, originating_org_id, version) "
            "VALUES (:id, :ws, :reg, :name, :mtype, :org_id, 1)"
        ),
        {
            "id": mol_id,
            "ws": workspace_id,
            "reg": reg,
            "name": reg,
            "mtype": "small_molecule",
            "org_id": org_id,
        },
    )
    return mol_id


class TestTagLinkRepository:
    async def test_add_find_remove(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="hit"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "REG-1")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            tags = await link_repo.find_tags_for_entity(ws_id, mol_id)
            assert [t.key for t in tags] == ["hit"]
            await link_repo.remove(ws_id, mol_id, tag.id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert await link_repo.find_tags_for_entity(ws_id, mol_id) == []

    async def test_add_is_idempotent(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "REG-2")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert len(await link_repo.find_tags_for_entity(ws_id, mol_id)) == 1

    async def test_add_noop_when_entity_in_other_workspace(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, other_ws, user_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "REG-3")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(other_ws, mol_id, tag.id, user_id)  # wrong ws → no-op
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert await link_repo.find_tags_for_entity(ws_id, mol_id) == []

    async def test_find_entity_ids_any_and_all(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            t1 = await tag_repo.get_or_create(ws_id, TagName(key="a"), user_id)
            t2 = await tag_repo.get_or_create(ws_id, TagName(key="b"), user_id)
            m1 = await _insert_molecule(uow, ws_id, "M1")
            m2 = await _insert_molecule(uow, ws_id, "M2")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, m1, t1.id, user_id)
            await link_repo.add(ws_id, m1, t2.id, user_id)
            await link_repo.add(ws_id, m2, t1.id, user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            any_ids = await link_repo.find_entity_ids_for_tags(
                ws_id, [t1.id, t2.id], match_all=False
            )
            all_ids = await link_repo.find_entity_ids_for_tags(
                ws_id, [t1.id, t2.id], match_all=True
            )
        assert set(any_ids) == {m1, m2}
        assert set(all_ids) == {m1}

    async def test_set_for_entity_reconciles(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            t1 = await tag_repo.get_or_create(ws_id, TagName(key="a"), user_id)
            t2 = await tag_repo.get_or_create(ws_id, TagName(key="b"), user_id)
            t3 = await tag_repo.get_or_create(ws_id, TagName(key="c"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "M-set")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.set_for_entity(ws_id, mol_id, [t1.id, t2.id], user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.set_for_entity(ws_id, mol_id, [t2.id, t3.id], user_id)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            keys = {t.key for t in await link_repo.find_tags_for_entity(ws_id, mol_id)}
        assert keys == {"b", "c"}

    async def test_cascade_on_molecule_delete(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "M-del")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        async with uow:
            await uow.session.execute(
                text("DELETE FROM molecules WHERE id = :id"), {"id": mol_id}
            )
            await uow.commit()
        async with uow:
            res = await uow.session.execute(
                text("SELECT count(*) FROM molecule_tags WHERE molecule_id = :id"),
                {"id": mol_id},
            )
            assert res.scalar_one() == 0

    async def test_cascade_on_tag_delete(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "M-tagdel")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            await tag_repo.delete(ws_id, tag.id)
            await uow.commit()
        async with uow:
            res = await uow.session.execute(
                text("SELECT count(*) FROM molecule_tags WHERE tag_id = :id"),
                {"id": tag.id},
            )
            assert res.scalar_one() == 0

    async def test_add_returns_whether_row_inserted(self, uow: AsyncUnitOfWork) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "M-add")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            first = await link_repo.add(ws_id, mol_id, tag.id, user_id)
            second = await link_repo.add(ws_id, mol_id, tag.id, user_id)
            await uow.commit()
        assert first is True  # new row inserted
        assert second is False  # already linked — no insert

    async def test_tombstoned_molecule_is_not_a_valid_tag_target(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            tag = await tag_repo.get_or_create(ws_id, TagName(key="x"), user_id)
            mol_id = await _insert_molecule(uow, ws_id, "M-tomb")
            await uow.session.execute(
                text("UPDATE molecules SET merged_into_id = :t WHERE id = :id"),
                {"t": uuid.uuid4(), "id": mol_id},
            )
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert await link_repo.entity_exists_in_workspace(ws_id, mol_id) is False
            assert await link_repo.add(ws_id, mol_id, tag.id, user_id) is False
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            assert await link_repo.find_tags_for_entity(ws_id, mol_id) == []


class TestTagSearchEscaping:
    async def test_like_metacharacters_are_literal(self, uow: AsyncUnitOfWork) -> None:
        # '%' in the query must match literally, not act as a wildcard, or the
        # autocomplete/filter pickers return the wrong candidate set.
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            await repo.get_or_create(ws_id, TagName(key="50%"), user_id)
            await repo.get_or_create(ws_id, TagName(key="500"), user_id)
            await uow.commit()
        async with uow:
            repo = SQLAlchemyTagRepository(uow)
            hits = await repo.search(ws_id, q="50%")
        assert {t.key for t in hits} == {"50%"}


class TestMoleculeTagMergeSideEffect:
    async def test_transfers_tags_from_source_to_target(
        self, uow: AsyncUnitOfWork
    ) -> None:
        ws_id, user_id = uuid.uuid4(), uuid.uuid4()
        async with uow:
            tag_repo = SQLAlchemyTagRepository(uow)
            shared = await tag_repo.get_or_create(ws_id, TagName(key="shared"), user_id)
            only_src = await tag_repo.get_or_create(ws_id, TagName(key="onlysrc"), user_id)
            only_tgt = await tag_repo.get_or_create(ws_id, TagName(key="onlytgt"), user_id)
            src = await _insert_molecule(uow, ws_id, "MERGE-SRC")
            tgt = await _insert_molecule(uow, ws_id, "MERGE-TGT")
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            await link_repo.add(ws_id, src, shared.id, user_id)
            await link_repo.add(ws_id, src, only_src.id, user_id)
            await link_repo.add(ws_id, tgt, shared.id, user_id)
            await link_repo.add(ws_id, tgt, only_tgt.id, user_id)
            await uow.commit()
        async with uow:
            await MoleculeTagMergeSideEffect().on_merge(uow, src, tgt)
            await uow.commit()
        async with uow:
            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            tgt_tags = {t.key for t in await link_repo.find_tags_for_entity(ws_id, tgt)}
            src_tags = {t.key for t in await link_repo.find_tags_for_entity(ws_id, src)}
        # Survivor gains the union; source keeps none (dedup avoids PK clash).
        assert tgt_tags == {"shared", "onlysrc", "onlytgt"}
        assert src_tags == set()


class TestBackfillMoleculeTags:
    async def test_casefold_parity_dedup_and_links(self, uow: AsyncUnitOfWork) -> None:
        # The whole transaction (incl. the temporary tags column) rolls back on
        # exit because we never commit — keeping migration 048's drop intact.
        ws_id = uuid.uuid4()
        async with uow:
            await uow.session.execute(
                text("ALTER TABLE molecules ADD COLUMN IF NOT EXISTS tags JSON")
            )
            m1 = await _insert_molecule(uow, ws_id, "BK-1")
            m2 = await _insert_molecule(uow, ws_id, "BK-2")
            await uow.session.execute(
                text("UPDATE molecules SET tags = CAST(:t AS JSON) WHERE id = :id"),
                {"t": json.dumps(["Kinase", "kinase", "Straße", " "]), "id": m1},
            )
            await uow.session.execute(
                text("UPDATE molecules SET tags = CAST(:t AS JSON) WHERE id = :id"),
                {"t": json.dumps(["KINASE"]), "id": m2},
            )

            conn = await uow.session.connection()
            await conn.run_sync(backfill_molecule_tags)

            # Casefold dedup: 'Kinase'/'kinase'/'KINASE' -> one tag; 'Straße' uses
            # casefold ('strasse'), matching the runtime domain. Whitespace skipped.
            norm = (
                await uow.session.execute(
                    text(
                        "SELECT normalized_key FROM tags "
                        "WHERE workspace_id = :ws ORDER BY normalized_key"
                    ),
                    {"ws": ws_id},
                )
            ).scalars().all()
            assert norm == ["kinase", "strasse"]

            # Parity: runtime get_or_create with the same display matches the
            # backfilled row (no duplicate), which the old SQL lower() would miss.
            repo = SQLAlchemyTagRepository(uow)
            await repo.get_or_create(ws_id, TagName(key="Straße"), uuid.uuid4())
            cnt = (
                await uow.session.execute(
                    text(
                        "SELECT count(*) FROM tags "
                        "WHERE workspace_id = :ws AND normalized_key = 'strasse'"
                    ),
                    {"ws": ws_id},
                )
            ).scalar_one()
            assert cnt == 1

            link_repo = get_tag_link_repository(TaggableEntityType.MOLECULE, uow)
            m1_keys = {
                t.normalized_key for t in await link_repo.find_tags_for_entity(ws_id, m1)
            }
            m2_keys = {
                t.normalized_key for t in await link_repo.find_tags_for_entity(ws_id, m2)
            }
            assert m1_keys == {"kinase", "strasse"}
            assert m2_keys == {"kinase"}
            # intentionally no commit -> rollback drops the temp column + rows
