"""Stored unit spellings are rewritten once; anything that is not a variant stays."""

import json
import uuid

from sqlalchemy import text

from cellar.domain.screening_assay.enums import ProtocolType, ReadoutDataType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from cellar.infrastructure.persistence.unit_rewrite import (
    _DISPLAY_UNIT_COLUMNS,
    rewrite_saved_search_units,
    rewrite_stored_units,
)
from tests.integration.cascade import _rows


async def _save_protocol(session_factory, workspace_id, user_id, names=("a", "b", "c")):
    pid = uuid.uuid4()
    protocol = Protocol.create(
        workspace_id=workspace_id,
        name="p",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=user_id,
        readout_definitions=[
            ReadoutDefinition(protocol_id=pid, name=n, data_type=ReadoutDataType.NUMERIC)
            for n in names
        ],
    )
    uow = AsyncUnitOfWork(session_factory)
    async with uow:
        await SQLAlchemyProtocolRepository(uow).save(protocol)
        await uow.commit()
    return protocol


async def test_rewrites_variants_and_leaves_the_rest(session_factory, workspace_id, user_id):
    protocol = await _save_protocol(session_factory, workspace_id, user_id)
    async with session_factory() as s:
        for name, legacy in (("a", "uM"), ("b", "U/mL"), ("c", "ug/ml")):
            await s.execute(
                text("update readout_definitions set unit=:u where protocol_id=:p and name=:n"),
                {"u": legacy, "p": protocol.id, "n": name},
            )
        await s.run_sync(lambda sync: rewrite_stored_units(sync.connection()))
        await s.commit()
        rows = await s.execute(
            text("select name, unit from readout_definitions where protocol_id=:p"),
            {"p": protocol.id},
        )
        units = dict(rows.all())
    assert units == {"a": "µM", "b": "U/mL", "c": "µg/mL"}


async def test_closed_campaign_snapshot_is_left_untouched(session_factory, workspace_id, user_id):
    protocol = await _save_protocol(session_factory, workspace_id, user_id, names=("a",))
    async with session_factory() as s:
        readout_id = await s.scalar(
            text("select id from readout_definitions where protocol_id=:p"), {"p": protocol.id}
        )
        org = await _rows.org(s, workspace_id)
        mol = await _rows.molecule(s, workspace_id, org)
        camp = await _rows.campaign(s, workspace_id)
        chan = await _rows.channel(s, camp, protocol.id, readout_id)
        res = await _rows.result(s, camp, mol)
        meas = await _rows.measurement(s, res, chan)  # planted with unit 'uM'
        await _rows.set_campaign_status(s, camp, "closed")
        await s.run_sync(lambda sync: rewrite_stored_units(sync.connection()))
        await s.commit()
        unit = await s.scalar(
            text("select unit from campaign_measurement where id=:id"), {"id": meas}
        )
        trigger_state = await s.scalar(
            text(
                "select tgenabled::text from pg_trigger "
                "where tgname='campaign_measurement_reject_locked'"
            )
        )
    assert unit == "uM"  # frozen record: the filter compares canonical spellings instead
    assert trigger_state == "O"  # the lock trigger is never disabled


def test_only_live_definition_units_are_rewritten():
    assert _DISPLAY_UNIT_COLUMNS == (
        ("readout_definitions", "unit"),
        ("condition_definitions", "unit"),
    )
    # Frozen campaign snapshots and ConcentrationUnit enum columns ("uM", parsed back) stay.
    assert "campaign_measurement" not in {t for t, _ in _DISPLAY_UNIT_COLUMNS}
    assert not {c for _, c in _DISPLAY_UNIT_COLUMNS} & {"test_concentration_unit", "dose_unit"}


async def test_form_template_units_are_rewritten(session_factory, workspace_id):
    form_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            text(
                "insert into protocol_forms (id, workspace_id, name, readout_templates, "
                "condition_templates) values (:id, :ws, 'f', "
                """cast('[{"name": "a", "unit": "uM"}, {"name": "b"}]' as jsonb), """
                """cast('[{"name": "t", "unit": "hrs"}]' as jsonb))"""
            ),
            {"id": form_id, "ws": workspace_id},
        )
        await s.run_sync(lambda sync: rewrite_stored_units(sync.connection()))
        await s.commit()
        row = (
            await s.execute(
                text(
                    "select readout_templates, condition_templates "
                    "from protocol_forms where id=:id"
                ),
                {"id": form_id},
            )
        ).one()
    assert row.readout_templates == [{"name": "a", "unit": "µM"}, {"name": "b"}]
    assert row.condition_templates == [{"name": "t", "unit": "h"}]


async def test_saved_search_criterion_units_are_rewritten(session_factory, workspace_id, user_id):
    """Saved searches are live queries: an any-protocol readout criterion's unit follows the
    stored readouts' spelling, so the search still matches and reopens on its option."""

    def readout(name, unit):
        return {"source": "readout_data", "readout_name": name, "unit": unit, "operator": "gt"}

    query = {
        "criteria": [
            {
                "type": "group",
                "logic": "or",
                "criteria": [
                    {"type": "activity", "protocol_id": None, "where": [readout("IC50", "uM")]}
                ],
            },
            {
                "type": "activity",
                "protocol_id": None,
                "where": [readout("Papp", "x10-6 cm/s"), readout("Signal", "U/mL")],
            },
            {"type": "text", "field": "name", "operator": "contains", "value": "uM"},
        ],
        "logic": "and",
    }
    columns = {"protocolColumns": ["any"], "reportConfig": {"imageSize": "medium"}}
    search_id = uuid.uuid4()
    async with session_factory() as s:
        await s.execute(
            text(
                "insert into saved_searches (id, workspace_id, name, query, columns, visibility, "
                "created_by, version) values (:id, :ws, 's', cast(:q as jsonb), "
                "cast(:c as jsonb), 'private', :user, 1)"
            ),
            {
                "id": search_id,
                "ws": workspace_id,
                "q": json.dumps(query),
                "c": json.dumps(columns),
                "user": user_id,
            },
        )
        await s.run_sync(lambda sync: rewrite_saved_search_units(sync.connection()))
        await s.commit()
        row = (
            await s.execute(
                text("select query, columns from saved_searches where id=:id"), {"id": search_id}
            )
        ).one()
    group, activity, text_criterion = row.query["criteria"]
    assert group["criteria"][0]["where"][0]["unit"] == "µM"
    assert [w["unit"] for w in activity["where"]] == ["×10⁻⁶ cm/s", "U/mL"]
    assert text_criterion["value"] == "uM"  # only units change
    assert row.columns == columns
