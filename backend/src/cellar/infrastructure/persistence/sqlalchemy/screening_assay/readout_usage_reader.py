"""SQLAlchemy implementation of ReadoutUsageReader."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import Select, Text, cast, func, or_, select

from cellar.application.screening.cross_protocol_resolver import formula_refs
from cellar.domain.screening_assay.protocol import ReadoutUsage
from cellar.infrastructure.persistence.sqlalchemy._sql import any_id
from cellar.infrastructure.persistence.sqlalchemy.inventory.models import ImportTemplateModel
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignChannelModel,
    CampaignModel,
    SavedSearchModel,
    SavedVisualizationModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    DoseResponseCurveModel,
    MeltingStepModel,
    ProtocolModel,
    ReadoutDataModel,
    ReadoutDefinitionModel,
    RunModel,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _said(n: int | None, sentence: str, one: str, many: str | None = None) -> list[str]:
    """``sentence`` with its count ("has values in 3 runs"), or nothing for none."""
    if not n:
        return []
    return [sentence.format(f"{n} {one if n == 1 else many or one + 's'}")]


class SQLAlchemyReadoutUsageReader:
    """Reads inside the caller's unit of work, so a check and the change it allows
    share one transaction."""

    def __init__(self, uow: AsyncUnitOfWork) -> None:
        self._uow = uow

    async def for_readout(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, definition_id: uuid.UUID
    ) -> ReadoutUsage:
        usage = await self._usage(workspace_id, protocol_id, definition_id)
        return usage.get(definition_id, ReadoutUsage())

    async def for_protocol(
        self, workspace_id: uuid.UUID, protocol_id: uuid.UUID
    ) -> dict[uuid.UUID, ReadoutUsage]:
        return await self._usage(workspace_id, protocol_id, None)

    async def _usage(
        self, ws: uuid.UUID, pid: uuid.UUID, only: uuid.UUID | None
    ) -> dict[uuid.UUID, ReadoutUsage]:
        """One grouped query per kind of usage, whatever the number of readouts.

        Rows that carry a readout id (values, curves, campaign columns) are counted by
        it. JSON that holds the id (plate QC keys, ``readout:<id>`` template targets,
        search conditions and ``drc:<id>`` / ``rd:<protocol>:<id>`` column tokens,
        ``rd:<id>:<layer>`` view keys) is matched by the id's text, so a new token
        shape needs no change here. Hit rules, temperature windows and other
        protocols' formulas refer to a readout by name. Recent searches are history
        and are not read.
        """
        session = self._uow.session
        rd, protocol = ReadoutDefinitionModel, ProtocolModel
        stmt = (
            select(rd.id, rd.name, rd.melt_config["window"].astext.label("window"), protocol.code)
            .join(protocol, rd.protocol_id == protocol.id)
            .where(protocol.workspace_id == ws, protocol.id == pid)
        )
        if only is not None:
            stmt = stmt.where(rd.id == only)
        readouts = (await session.execute(stmt)).all()
        if not readouts:
            return {}
        ids = [r.id for r in readouts]

        async def counts(stmt: Select[Any]) -> dict[Any, int]:
            return {key: n for key, n in await session.execute(stmt)}

        def runs_holding(model: Any) -> Select[Any]:
            # Distinct (readout, run) pairs first: a hash aggregate, where
            # count(distinct run_id) would sort every row.
            # ponytail: reads every row of the readouts (index on readout_definition_id).
            # If a protocol with millions of values makes this slow, add an index on
            # (readout_definition_id, run_id) or answer without the run count.
            pairs = (
                select(model.readout_definition_id.label("rd"), model.run_id)
                .where(model.workspace_id == ws, any_id(model.readout_definition_id, ids))
                .distinct()
                .subquery()
            )
            return select(pairs.c.rd, func.count()).group_by(pairs.c.rd)

        def mentioning(owner: Any, *json_columns: Any, where: tuple[Any, ...] = ()) -> Select[Any]:
            # ponytail: serializes each document once per readout. Fine for the runs of
            # one protocol and a workspace's saved searches, views and templates.
            rd_id = cast(rd.id, Text)
            return (
                select(rd.id, func.count())
                .join(owner, or_(*(cast(c, Text).contains(rd_id) for c in json_columns)))
                .where(any_id(rd.id, ids), owner.workspace_id == ws, *where)
                .group_by(rd.id)
            )

        own_runs = (RunModel.workspace_id == ws, RunModel.protocol_id == pid)

        values = await counts(runs_holding(ReadoutDataModel))
        curves = await counts(runs_holding(DoseResponseCurveModel))
        qc = await counts(
            mentioning(RunModel, RunModel.qc_metrics, where=(RunModel.protocol_id == pid,))
        )

        peaks: dict[str, int] = {}
        if windows := {r.window for r in readouts if r.window}:
            step = MeltingStepModel
            peaks = await counts(
                select(step.assigned_window, func.count(step.run_id.distinct()))
                .join(RunModel, step.run_id == RunModel.id)
                .where(step.workspace_id == ws, *own_runs, step.assigned_window.in_(windows))
                .group_by(step.assigned_window)
            )

        rules: Counter[str] = Counter()
        for criteria in await session.scalars(
            select(RunModel.hit_criteria).where(*own_runs, RunModel.hit_criteria.is_not(None))
        ):
            rules.update({c.get("readout_name") for c in criteria or [] if isinstance(c, dict)})

        channel = CampaignChannelModel
        campaigns = await counts(
            select(channel.readout_definition_id, func.count(channel.campaign_id.distinct()))
            .join(CampaignModel, channel.campaign_id == CampaignModel.id)
            .where(CampaignModel.workspace_id == ws, any_id(channel.readout_definition_id, ids))
            .group_by(channel.readout_definition_id)
        )
        templates = await counts(
            mentioning(ImportTemplateModel, ImportTemplateModel.column_mappings)
        )
        searches = await counts(
            mentioning(SavedSearchModel, SavedSearchModel.query, SavedSearchModel.columns)
        )
        views = await counts(mentioning(SavedVisualizationModel, SavedVisualizationModel.config))

        # ``@CODE.<name>`` in any other readout's formula, in this workspace.
        formulas: dict[uuid.UUID, list[str]] = {}
        if code := readouts[0].code:
            by_name = {r.name: r.id for r in readouts}
            for other_id, other_name, formula, where in await session.execute(
                select(
                    rd.id,
                    rd.name,
                    rd.calculation_formula,
                    func.coalesce(protocol.code, protocol.name),
                )
                .join(protocol, rd.protocol_id == protocol.id)
                .where(
                    protocol.workspace_id == ws,
                    rd.calculation_formula.contains(code, autoescape=True),
                )
                .order_by(protocol.code, rd.name)
            ):
                for ref_code, ref_name in formula_refs(formula):
                    target = by_name.get(ref_name) if ref_code == code else None
                    if target is not None and target != other_id:
                        formulas.setdefault(target, []).append(
                            f"named by the formula of '{other_name}' in {where}"
                        )

        usage: dict[uuid.UUID, ReadoutUsage] = {}
        for r in readouts:
            reasons = (
                _said(values.get(r.id), "has values in {}", "run")
                + _said(curves.get(r.id), "has fitted curves in {}", "run")
                + _said(qc.get(r.id), "has plate QC in {}", "run")
                + _said(
                    peaks.get(r.window),
                    "has peaks assigned to its temperature window in {}",
                    "run",
                )
                + _said(rules.get(r.name), "named by the hit rule of {}", "run")
                + _said(campaigns.get(r.id), "used by a column of {}", "campaign")
                + _said(templates.get(r.id), "mapped by {}", "import template")
                + _said(searches.get(r.id), "used by {}", "saved search", "saved searches")
                + _said(views.get(r.id), "used by {}", "saved view")
                + formulas.get(r.id, [])
            )
            if reasons:
                usage[r.id] = ReadoutUsage(reasons=tuple(reasons))
        return usage
