"""Migration 107: CDD data source mappings become a registration mapping; numeric
vault batch ids become batch IDs."""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from cellar.application.cdd_import.registration_mapping import (
    default_cdd_registration_mapping,
    validate_registration_mapping,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork

_M107 = Path(__file__).parents[2] / "alembic" / "versions" / "107_cdd_registration_mapping.py"


def _load():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("m107", _M107)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fm(src: str, tgt: str, typ: str) -> dict:
    return {"source_field": src, "target_field": tgt, "target_type": typ}


def _mappings(molecule: list[dict], batch: list[dict]) -> list[dict]:
    plate = [_fm("name", "barcode", "core")]
    well = [_fm("batch", "cdd_batch_id", "core")]
    return [
        {
            "entity_type": "molecule",
            "id_field": "id",
            "id_storage": {"storage_type": "custom_field", "custom_field_name": "cdd_molecule_id"},
            "field_mappings": molecule,
        },
        {
            "entity_type": "batch",
            "id_field": "id",
            "id_storage": {"storage_type": "custom_field", "custom_field_name": "cdd_batch_id"},
            "parent_path": "batches",
            "field_mappings": batch,
        },
        {"entity_type": "plate", "id_field": "id", "id_storage": {}, "field_mappings": plate},
        {"entity_type": "well", "id_field": "", "id_storage": {}, "field_mappings": well},
    ]


DEFAULT_MOL = [
    _fm("name|cdd_registry_number", "name", "core"),
    _fm("smiles|cxsmiles", "smiles", "core"),
    _fm("synonyms", "custom", "identifier"),
    _fm("modified_at", "modified_at", "core"),
]
DEFAULT_BATCH = [
    _fm("molecule_batch_identifier|name", "vendor_catalog_number", "core"),
    _fm("salt_name", "salt_name", "core"),
]


async def test_conversion_and_backfill(session_factory, workspace_id) -> None:
    m107 = _load()
    default_id, custom_id, chembl_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    mol_id, actor = uuid.uuid4(), uuid.uuid4()
    b_new, b_taken, b_has = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        session = uow.session

        def run(fn) -> None:  # type: ignore[no-untyped-def]
            def go(sync_session) -> None:  # type: ignore[no-untyped-def]
                with Operations.context(MigrationContext.configure(sync_session.connection())):
                    fn()

            return go

        await session.run_sync(run(m107.downgrade))  # back to the pre-107 schema

        async def ds(id_: uuid.UUID, name: str, typ: str, mappings: list[dict]) -> None:
            await session.execute(
                sa.text(
                    "INSERT INTO data_sources (id, workspace_id, name, source_type, "
                    "entity_mappings, created_by, version) "
                    "VALUES (:id, :ws, :n, :t, CAST(:m AS jsonb), :cb, 1)"
                ),
                {
                    "id": id_,
                    "ws": workspace_id,
                    "n": name,
                    "t": typ,
                    "m": json.dumps(mappings),
                    "cb": actor,
                },
            )

        await ds(default_id, "defaults", "cdd_vault", _mappings(DEFAULT_MOL, DEFAULT_BATCH))
        await ds(
            custom_id,
            "custom",
            "cdd_vault",
            _mappings(
                [
                    *DEFAULT_MOL,
                    _fm("molecule_fields.Alternate Names", "custom", "identifier"),
                ],
                [*DEFAULT_BATCH, _fm("batch_fields.Amount", "amount_value", "core")],
            ),
        )
        await ds(chembl_id, "chembl", "chembl", _mappings([_fm("pref_name", "name", "core")], []))

        await session.execute(
            sa.text(
                "INSERT INTO organizations (id, workspace_id, name, org_type, is_active, version) "
                "VALUES (:id, :ws, 'T-Org', 'internal', true, 1)"
            ),
            {"id": actor, "ws": workspace_id},
        )
        await session.execute(
            sa.text(
                "INSERT INTO molecules (id, workspace_id, registration_number, name, "
                "molecule_type, originating_org_id, version) "
                "VALUES (:id, :ws, :rn, 'm', 'small_molecule', :org, 1)"
            ),
            {"id": mol_id, "ws": workspace_id, "rn": f"T-{uuid.uuid4().hex[:8]}", "org": actor},
        )
        for bid, bn, cdd in ((b_new, "1", "9001"), (b_taken, "2", "9002"), (b_has, "3", "9003")):
            await session.execute(
                sa.text(
                    "INSERT INTO batches (id, workspace_id, molecule_id, batch_number, "
                    "amount_value, amount_unit, source, chemist, version, custom_fields) "
                    "VALUES (:id, :ws, :mol, :bn, 1, 'mg', 'purchased', :c, 1, "
                    "CAST(:cf AS json))"
                ),
                {
                    "id": bid,
                    "ws": workspace_id,
                    "mol": mol_id,
                    "bn": f"BN-{uuid.uuid4().hex[:6]}-{bn}",
                    "c": actor,
                    "cf": json.dumps({"cdd_batch_id": cdd}),
                },
            )
        # 9002 is already a batch ID (another type) on b_has; 9003 is already b_has's own.
        for bid, ident, typ in ((b_has, "9002", "custom"), (b_has, "9003", "cdd_batch_id")):
            await session.execute(
                sa.text(
                    "INSERT INTO batch_identifiers (id, batch_id, workspace_id, identifier, "
                    "identifier_type, source, registered_by) "
                    "VALUES (gen_random_uuid(), :b, :ws, :i, :t, 'x', :rb)"
                ),
                {"b": bid, "ws": workspace_id, "i": ident, "t": typ, "rb": actor},
            )

        await session.run_sync(run(m107.upgrade))

        async def state() -> tuple[dict, list]:
            rows = (
                await session.execute(
                    sa.text(
                        "SELECT id, registration_mapping, entity_mappings FROM data_sources "
                        "WHERE workspace_id = :ws"
                    ),
                    {"ws": workspace_id},
                )
            ).all()
            ids = (
                await session.execute(
                    sa.text(
                        "SELECT batch_id, identifier, identifier_type, source "
                        "FROM batch_identifiers WHERE workspace_id = :ws ORDER BY identifier"
                    ),
                    {"ws": workspace_id},
                )
            ).all()
            return {r.id: r for r in rows}, [tuple(r) for r in ids]

        by_id, ids = await state()
        again_ds, again_ids = None, None
        await session.run_sync(run(m107.convert_sources))
        await session.run_sync(run(m107.backfill_cdd_batch_ids))
        again_ds, again_ids = await state()
        await session.rollback()  # leave the shared test database as it was

    # defaults convert to exactly the application defaults
    assert by_id[default_id].registration_mapping == default_cdd_registration_mapping()
    # admin additions are kept; modified_at is not a mapping
    custom = by_id[custom_id].registration_mapping
    assert validate_registration_mapping(custom) is None
    assert {
        "header": "molecule_fields.Alternate Names",
        "target": "compound_id",
        "source": "Alternate Names",
        "separator": None,
    } in custom
    assert {
        "header": "batch.batch_fields.Amount",
        "target": "amount_value",
        "source": None,
        "separator": None,
    } in custom
    assert not any("modified_at" in c["header"] for c in custom)
    # molecule/batch field_mappings emptied; plate/well untouched; non-CDD sources untouched
    for id_ in (default_id, custom_id):
        em = {e["entity_type"]: e for e in by_id[id_].entity_mappings}
        assert em["molecule"]["field_mappings"] == [] and em["batch"]["field_mappings"] == []
        assert em["plate"]["field_mappings"] == [_fm("name", "barcode", "core")]
        assert em["well"]["field_mappings"] == [_fm("batch", "cdd_batch_id", "core")]
    assert by_id[chembl_id].registration_mapping is None
    assert by_id[chembl_id].entity_mappings[0]["field_mappings"] == [
        _fm("pref_name", "name", "core")
    ]
    # numeric id backfilled for b_new only; 9002 is taken, 9003 already there
    assert (b_new, "9001", "cdd_batch_id", "CDD import") in ids
    assert not any(i[1] == "9002" and i[0] == b_taken for i in ids)
    assert sum(1 for i in ids if i[1] == "9003") == 1
    # second run changes nothing
    assert again_ids == ids
    assert {k: v.registration_mapping for k, v in again_ds.items()} == {
        k: v.registration_mapping for k, v in by_id.items()
    }


async def test_downgrade_gives_the_old_importer_its_field_mappings_back(
    session_factory, workspace_id
) -> None:
    """An image rollback to before 107 reads molecule/batch ``field_mappings`` again; empty,
    it would register every molecule as ``EXT-<id>``."""
    m107 = _load()
    ds_id = uuid.uuid4()
    after_107 = _mappings([], [])
    async with session_factory() as session:
        await session.execute(
            sa.text(
                "INSERT INTO data_sources (id, workspace_id, name, source_type, entity_mappings, "
                "registration_mapping, created_by, version) VALUES (:id, :ws, 'vault', "
                "'cdd_vault', CAST(:m AS jsonb), CAST(:rm AS jsonb), :cb, 1)"
            ),
            {
                "id": ds_id,
                "ws": workspace_id,
                "m": json.dumps(after_107),
                "rm": json.dumps(default_cdd_registration_mapping()),
                "cb": uuid.uuid4(),
            },
        )

        def go(sync_session) -> None:  # type: ignore[no-untyped-def]
            with Operations.context(MigrationContext.configure(sync_session.connection())):
                m107.downgrade()

        await session.run_sync(go)
        (mappings,) = (
            await session.execute(
                sa.text("SELECT entity_mappings FROM data_sources WHERE id = :id"), {"id": ds_id}
            )
        ).one()
        await session.rollback()

    by_type = {em["entity_type"]: em for em in mappings}
    assert by_type["molecule"]["field_mappings"] == DEFAULT_MOL
    assert by_type["batch"]["field_mappings"] == DEFAULT_BATCH
    assert by_type["plate"] == after_107[2] and by_type["well"] == after_107[3]
