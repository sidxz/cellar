"""SQLAlchemyReadoutUsageReader — everything outside a protocol that uses its readouts.

Each test states one kind of usage in the readout's own workspace and the same
reference in another workspace, which must never count.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from cellar.domain.screening_assay.protocol import ReadoutUsage
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import ImportTemplateModel
from cellar.infrastructure.persistence.sqlalchemy.personalization.models import RecentSearchModel
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignChannelModel,
    CampaignModel,
    SavedSearchModel,
    SavedVisualizationModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import MeltingStepModel
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.readout_usage_reader import (
    SQLAlchemyReadoutUsageReader,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration import _screening_seed as seed

DAY = date(2026, 11, 2)
Seed = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]


class _Protocol:
    """A published protocol with a used-or-not readout ``rd`` and a bystander ``other``."""

    def __init__(self) -> None:
        self.ws = uuid.uuid4()
        self.elsewhere = uuid.uuid4()  # another workspace
        self.id = self.rd = self.other = uuid.UUID(int=0)

    async def create(self, uow: AsyncUnitOfWork, *, name: str = "Signal") -> _Protocol:
        async with uow:
            s = uow.session
            self.id = await seed.protocol(s, self.ws)
            self.rd = await seed.readout_def(s, self.id, name=name)
            self.other = await seed.readout_def(s, self.id, name="Bystander")
            await uow.commit()
        return self


async def _do(uow: AsyncUnitOfWork, fn: Callable[[AsyncSession], Awaitable[None]]) -> None:
    async with uow:
        await fn(uow.session)
        await uow.commit()


async def _reasons(uow: AsyncUnitOfWork, p: _Protocol) -> tuple[str, ...]:
    """The readout's reasons, asked both ways; the bystander must stay unused."""
    async with uow:
        reader = SQLAlchemyReadoutUsageReader(uow)
        one = await reader.for_readout(p.ws, p.id, p.rd)
        every = await reader.for_protocol(p.ws, p.id)
        bystander = await reader.for_readout(p.ws, p.id, p.other)
    assert every == ({p.rd: one} if one.in_use else {})
    assert bystander == ReadoutUsage()
    return one.reasons


async def test_a_readout_nothing_refers_to_is_unused(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)
    assert await _reasons(uow, p) == ()


async def test_stored_values_count_per_run(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def values(s: AsyncSession) -> None:
        for _ in range(2):
            run = await seed.run(s, p.ws, p.id, DAY)
            await seed.readout(s, p.ws, run, p.rd, uuid.uuid4(), 1.0)
            # A normalized row of the same run is the same run.
            await seed.readout(
                s, p.ws, run, p.rd, uuid.uuid4(), 2.0, normalization="percent_inhibition"
            )

    await _do(uow, values)
    assert await _reasons(uow, p) == ("has values in 2 runs",)


async def test_fitted_curves_count(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def curve(s: AsyncSession) -> None:
        run = await seed.run(s, p.ws, p.id, DAY)
        await seed.curve(s, p.ws, p.id, run, uuid.uuid4(), p.rd, with_well=False)

    await _do(uow, curve)
    assert await _reasons(uow, p) == ("has fitted curves in 1 run",)


async def test_a_plate_qc_entry_counts(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def qc(s: AsyncSession) -> None:
        plates = {str(uuid.uuid4()): {str(p.rd): {"raw": {"z_prime": 0.7}}}}
        await seed.run(s, p.ws, p.id, DAY, qc_metrics={"z_prime": {}, "plates": plates})
        await seed.run(s, p.ws, p.id, DAY, qc_metrics={"z_prime": {}, "plates": {}})
        await seed.run(s, p.ws, p.id, DAY)  # no QC at all

    await _do(uow, qc)
    assert await _reasons(uow, p) == ("has plate QC in 1 run",)


async def test_a_peak_assigned_to_the_readouts_window_counts(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow, name="Tm (Main)")

    def step(ws: uuid.UUID, run: uuid.UUID, window: str | None) -> MeltingStepModel:
        return MeltingStepModel(
            workspace_id=ws,
            run_id=run,
            well_id=uuid.uuid4(),
            channel_key="ratio",
            source="instrument",
            value=52.1,
            status="unreviewed",
            assigned_window=window,
        )

    async def peaks(s: AsyncSession) -> None:
        melt = '{"window": "Main", "measure": "tm", "channel_key": "ratio", "low": 40, "high": 60}'
        await s.execute(
            sa.text(
                "UPDATE readout_definitions SET melt_config = cast(:m as jsonb) WHERE id = :id"
            ),
            {"m": melt, "id": p.rd},
        )
        run = await seed.run(s, p.ws, p.id, DAY)
        # Another protocol of the workspace with a window of the same name.
        other_run = await seed.run(s, p.ws, await seed.protocol(s, p.ws), DAY)
        s.add_all(
            [
                step(p.ws, run, "Main"),
                step(p.ws, run, "Main"),
                step(p.ws, run, "Shoulder"),
                step(p.ws, run, None),
                step(p.ws, other_run, "Main"),
            ]
        )

    await _do(uow, peaks)
    assert await _reasons(uow, p) == ("has peaks assigned to its temperature window in 1 run",)


async def test_an_unassigned_window_readout_is_unused(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow, name="Tm (Main)")

    async def window_only(s: AsyncSession) -> None:
        await s.execute(
            sa.text(
                "UPDATE readout_definitions SET melt_config = "
                """'{"window": "Main", "measure": "tm"}'::jsonb WHERE id = :id"""
            ),
            {"id": p.rd},
        )
        await seed.run(s, p.ws, p.id, DAY)

    await _do(uow, window_only)
    assert await _reasons(uow, p) == ()


async def test_a_runs_hit_rule_naming_it_counts(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def rules(s: AsyncSession) -> None:
        rule = '[{"readout_name": "Signal", "operator": "gt", "value": 50}]'
        longer = '[{"readout_name": "Signal 2", "operator": "gt", "value": 50}]'
        for criteria, protocol_id in (
            (rule, p.id),
            (rule, p.id),
            (longer, p.id),  # another readout's name
            ("[]", p.id),  # a recorded "show all"
            (rule, await seed.protocol(s, p.ws)),  # another protocol's readout of that name
        ):
            run = await seed.run(s, p.ws, protocol_id, DAY)
            await s.execute(
                sa.text("UPDATE runs SET hit_criteria = cast(:c as jsonb) WHERE id = :id"),
                {"c": criteria, "id": run},
            )

    await _do(uow, rules)
    assert await _reasons(uow, p) == ("named by the hit rule of 2 runs",)


def _campaign(ws: uuid.UUID, name: str) -> CampaignModel:
    return CampaignModel(
        id=uuid.uuid4(), workspace_id=ws, project_id=uuid.uuid4(), name=name, created_by=seed.USER
    )


def _channel(
    campaign: CampaignModel, protocol_id: uuid.UUID, rd: uuid.UUID
) -> CampaignChannelModel:
    return CampaignChannelModel(
        campaign_id=campaign.id,
        label="Signal",
        protocol_id=protocol_id,
        readout_definition_id=rd,
        source_kind="readout_data",
        selection_rule="latest_run",
        qualifier_handling="include_qualified",
    )


async def test_a_campaign_column_counts_per_campaign(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def channels(s: AsyncSession) -> None:
        one, two, foreign = _campaign(p.ws, "A"), _campaign(p.ws, "B"), _campaign(p.elsewhere, "C")
        s.add_all([one, two, foreign])
        await s.flush()
        s.add_all(
            [
                _channel(one, p.id, p.rd),
                _channel(one, p.id, p.rd),  # two columns of one campaign
                _channel(two, p.id, p.rd),
                _channel(foreign, p.id, p.rd),
            ]
        )

    await _do(uow, channels)
    assert await _reasons(uow, p) == ("used by a column of 2 campaigns",)


async def test_an_import_template_mapping_a_column_to_it_counts(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def templates(s: AsyncSession) -> None:
        for ws, mappings in (
            (p.ws, {"Signal (AU)": f"readout:{p.rd}", "Well": "well"}),
            (p.ws, {"Well": "well"}),
            (p.elsewhere, {"Signal (AU)": f"readout:{p.rd}"}),
        ):
            s.add(
                ImportTemplateModel(
                    workspace_id=ws, name="Reader", column_mappings=mappings, created_by=seed.USER
                )
            )

    await _do(uow, templates)
    assert await _reasons(uow, p) == ("mapped by 1 import template",)


def _search(ws: uuid.UUID, name: str, query: dict, columns: dict | None) -> SavedSearchModel:
    return SavedSearchModel(
        workspace_id=ws, name=name, query=query, columns=columns, created_by=seed.USER
    )


async def test_saved_searches_count_by_condition_and_by_column(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)
    condition = {"activity": [{"readout_definition_id": str(p.rd), "operator": "lt", "value": 10}]}

    async def searches(s: AsyncSession) -> None:
        s.add_all(
            [
                _search(p.ws, "By condition", condition, None),
                _search(p.ws, "By curve column", {}, {"visible": ["name", f"drc:{p.rd}:ic:50"]}),
                _search(p.ws, "By readout column", {}, {"visible": [f"rd:{p.id}:{p.rd}"]}),
                # Names the protocol, never the readout.
                _search(p.ws, "Unrelated", {"protocol_id": str(p.id)}, {"visible": ["name"]}),
                _search(p.elsewhere, "Elsewhere", condition, {"visible": [f"drc:{p.rd}"]}),
            ]
        )

    await _do(uow, searches)
    assert await _reasons(uow, p) == ("used by 3 saved searches",)


async def test_a_recent_search_is_history_and_does_not_count(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def recent(s: AsyncSession) -> None:
        s.add(
            RecentSearchModel(
                workspace_id=p.ws,
                user_id=seed.USER,
                query_key="k",
                query={"activity": [{"readout_definition_id": str(p.rd)}]},
                columns={"visible": [f"drc:{p.rd}"]},
                ran_at=datetime.now(UTC),
            )
        )

    await _do(uow, recent)
    assert await _reasons(uow, p) == ()


async def test_a_saved_view_plotting_it_counts(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    def view(ws: uuid.UUID, key: str) -> SavedVisualizationModel:
        return SavedVisualizationModel(
            workspace_id=ws,
            name="Plate drift",
            source={"kind": "protocols", "protocol_ids": [str(p.id)]},
            protocol_ids=[p.id],
            level="wells",
            config={"config_version": 1, "panels": [{"kind": "scatter", "y": key}]},
            created_by=seed.USER,
        )

    async def views(s: AsyncSession) -> None:
        s.add_all(
            [
                view(p.ws, f"rd:{p.rd}:raw"),
                view(p.ws, "dose"),
                view(p.elsewhere, f"rd:{p.rd}:raw"),
            ]
        )

    await _do(uow, views)
    assert await _reasons(uow, p) == ("used by 1 saved view",)


async def test_another_protocols_formula_naming_it_by_code_counts(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow, name="IC50 nM")

    async def formulas(s: AsyncSession) -> None:
        await s.execute(
            sa.text("UPDATE protocols SET code = 'PRT-00001' WHERE id = :id"), {"id": p.id}
        )
        for ws, code, name, formula in (
            (p.ws, "PRT-00002", "Selectivity", "@{PRT-00001}.{IC50 nM} / [Counter IC50]"),
            # The bare form cannot name a readout with a space; this names 'IC50'.
            (p.ws, "PRT-00003", "Other", "@PRT-00001.IC50 * 2"),
            (p.ws, "PRT-00004", "Unrelated", "@{PRT-00011}.{IC50 nM} * 2"),
            (p.elsewhere, "PRT-00002", "Elsewhere", "@{PRT-00001}.{IC50 nM} * 2"),
        ):
            other = await seed.protocol(s, ws)
            await s.execute(
                sa.text("UPDATE protocols SET code = :c WHERE id = :id"), {"c": code, "id": other}
            )
            rd = await seed.readout_def(s, other, name=name)
            await s.execute(
                sa.text(
                    "UPDATE readout_definitions SET is_calculated = true, "
                    "calculation_formula = :f WHERE id = :id"
                ),
                {"f": formula, "id": rd},
            )

    await _do(uow, formulas)
    assert await _reasons(uow, p) == ("named by the formula of 'Selectivity' in PRT-00002",)


async def test_values_in_another_workspace_never_count(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def foreign(s: AsyncSession) -> None:
        # Rows that point at this readout but belong to another workspace.
        plates = {str(uuid.uuid4()): {str(p.rd): {"raw": {"z_prime": 0.7}}}}
        run = await seed.run(s, p.elsewhere, p.id, DAY, qc_metrics={"plates": plates})
        await s.execute(
            sa.text("UPDATE runs SET hit_criteria = cast(:c as jsonb) WHERE id = :id"),
            {"c": '[{"readout_name": "Signal", "operator": "gt", "value": 1}]', "id": run},
        )
        await seed.readout(s, p.elsewhere, run, p.rd, uuid.uuid4(), 1.0)
        await seed.curve(s, p.elsewhere, p.id, run, uuid.uuid4(), p.rd, with_well=False)

    await _do(uow, foreign)
    assert await _reasons(uow, p) == ()


async def test_asking_from_another_workspace_finds_nothing(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def values(s: AsyncSession) -> None:
        run = await seed.run(s, p.ws, p.id, DAY)
        await seed.readout(s, p.ws, run, p.rd, uuid.uuid4(), 1.0)

    await _do(uow, values)
    async with uow:
        reader = SQLAlchemyReadoutUsageReader(uow)
        assert await reader.for_readout(p.elsewhere, p.id, p.rd) == ReadoutUsage()
        assert await reader.for_protocol(p.elsewhere, p.id) == {}


async def test_every_readout_of_a_protocol_is_answered_at_once(uow: AsyncUnitOfWork) -> None:
    p = await _Protocol().create(uow)

    async def both(s: AsyncSession) -> None:
        run = await seed.run(s, p.ws, p.id, DAY)
        await seed.readout(s, p.ws, run, p.rd, uuid.uuid4(), 1.0)
        await seed.readout(s, p.ws, run, p.other, uuid.uuid4(), 1.0)
        campaign = _campaign(p.ws, "A")
        s.add(campaign)
        await s.flush()
        s.add(_channel(campaign, p.id, p.other))

    await _do(uow, both)
    async with uow:
        usage = await SQLAlchemyReadoutUsageReader(uow).for_protocol(p.ws, p.id)
    assert usage == {
        p.rd: ReadoutUsage(reasons=("has values in 1 run",)),
        p.other: ReadoutUsage(reasons=("has values in 1 run", "used by a column of 1 campaign")),
    }
