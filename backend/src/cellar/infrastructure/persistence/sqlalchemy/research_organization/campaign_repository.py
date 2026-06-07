"""SQLAlchemy implementation of the CampaignRepository protocol."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from cellar.domain.research_organization.campaign import Campaign
from cellar.domain.research_organization.campaign_channel import CampaignChannel
from cellar.domain.research_organization.campaign_measurement import (
    CampaignMeasurement,
)
from cellar.domain.research_organization.campaign_result import CampaignResult
from cellar.domain.research_organization.enums import (
    CampaignDecision,
    CampaignStatus,
    ChannelSourceKind,
    HitCall,
    QualifierHandling,
    SelectionRule,
    ValueQualifier,
)
from cellar.domain.research_organization.source_ref import SourceRef
from cellar.domain.shared.hit_criterion import HitCriterion, InterceptKey
from cellar.domain.shared.target_ref import TargetRef
from cellar.infrastructure.persistence.sqlalchemy.base_repository import (
    SQLAlchemyRepository,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.campaign_target_filter import (  # noqa: E501
    campaign_target_filter_subquery,
)
from cellar.infrastructure.persistence.sqlalchemy.research_organization.models import (
    CampaignChannelModel,
    CampaignMeasurementModel,
    CampaignModel,
    CampaignResultModel,
)
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import (
    RunModel,
    TargetModel,
    run_targets,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.models import (
    CampaignTagLinkModel,
)
from cellar.infrastructure.persistence.sqlalchemy.tagging.tag_filter import (
    tag_filter_subquery,
)


class SQLAlchemyCampaignRepository(SQLAlchemyRepository[Campaign, CampaignModel]):
    """Aggregate-cascade mapping for Campaign + channels + results + measurements.

    The owned-child collections are reconciled by id in :meth:`_update_model`
    (update existing, append new, remove missing) so that SQLAlchemy emits
    targeted UPDATE/INSERT/DELETE statements rather than rebuilding the row
    set on every save.
    """

    model_class = CampaignModel

    # ------------------------------------------------------------------
    # Mapping: SA model <-> domain aggregate
    # ------------------------------------------------------------------

    def _to_domain(self, model: CampaignModel) -> Campaign:
        channels = [self._channel_to_domain(cm) for cm in model.channels]
        results = [self._result_to_domain(rm) for rm in model.results]
        return Campaign(
            id=model.id,
            workspace_id=model.workspace_id,
            project_id=model.project_id,
            name=model.name,
            description=model.description,
            status=CampaignStatus(model.status),
            publishes_collection=model.publishes_collection,
            source_protocols=list(model.source_protocols or []),
            closed_at=model.closed_at,
            closed_by=model.closed_by,
            signature_id=model.signature_id,
            supersedes_campaign_id=model.supersedes_campaign_id,
            superseded_by_campaign_id=model.superseded_by_campaign_id,
            published_collection_id=model.published_collection_id,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
            version=model.version,
            channels=channels,
            results=results,
        )

    def _to_model(self, aggregate: Campaign) -> CampaignModel:
        return CampaignModel(
            id=aggregate.id,
            workspace_id=aggregate.workspace_id,
            project_id=aggregate.project_id,
            name=aggregate.name,
            description=aggregate.description,
            status=aggregate.status.value,
            publishes_collection=aggregate.publishes_collection,
            source_protocols=list(aggregate.source_protocols),
            closed_at=aggregate.closed_at,
            closed_by=aggregate.closed_by,
            signature_id=aggregate.signature_id,
            supersedes_campaign_id=aggregate.supersedes_campaign_id,
            superseded_by_campaign_id=aggregate.superseded_by_campaign_id,
            published_collection_id=aggregate.published_collection_id,
            created_by=aggregate.created_by,
            version=aggregate.version,
            channels=[self._channel_to_model(c) for c in aggregate.channels],
            results=[self._result_to_model(r) for r in aggregate.results],
        )

    def _update_model(self, model: CampaignModel, aggregate: Campaign) -> None:
        model.name = aggregate.name
        model.description = aggregate.description
        model.status = aggregate.status.value
        model.publishes_collection = aggregate.publishes_collection
        model.source_protocols = list(aggregate.source_protocols)
        model.closed_at = aggregate.closed_at
        model.closed_by = aggregate.closed_by
        model.signature_id = aggregate.signature_id
        model.supersedes_campaign_id = aggregate.supersedes_campaign_id
        model.superseded_by_campaign_id = aggregate.superseded_by_campaign_id
        model.published_collection_id = aggregate.published_collection_id

        # Reconcile channels by id
        existing_channels = {ch.id: ch for ch in model.channels}
        aggregate_channel_ids = {c.id for c in aggregate.channels}
        for ch in aggregate.channels:
            if ch.id in existing_channels:
                self._channel_update_model(existing_channels[ch.id], ch)
            else:
                model.channels.append(self._channel_to_model(ch))
        for existing_id, existing_ch in list(existing_channels.items()):
            if existing_id not in aggregate_channel_ids:
                model.channels.remove(existing_ch)

        # Reconcile results by id
        existing_results = {r.id: r for r in model.results}
        aggregate_result_ids = {r.id for r in aggregate.results}
        for r in aggregate.results:
            if r.id in existing_results:
                self._result_update_model(existing_results[r.id], r)
            else:
                model.results.append(self._result_to_model(r))
        for existing_id, existing_r in list(existing_results.items()):
            if existing_id not in aggregate_result_ids:
                model.results.remove(existing_r)

    # ------------------------------------------------------------------
    # Channel mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _channel_to_domain(model: CampaignChannelModel) -> CampaignChannel:
        return CampaignChannel(
            id=model.id,
            campaign_id=model.campaign_id,
            label=model.label,
            display_order=model.display_order,
            protocol_id=model.protocol_id,
            readout_definition_id=model.readout_definition_id,
            source_kind=ChannelSourceKind(model.source_kind),
            selection_rule=SelectionRule(model.selection_rule),
            qualifier_handling=QualifierHandling(model.qualifier_handling),
            qc_filter=model.qc_filter,
            hit_threshold=(
                HitCriterion.from_dict(model.hit_threshold) if model.hit_threshold else None
            ),
            normalization_applied=model.normalization_applied,
            intercept_key=(
                InterceptKey.from_dict(model.intercept_key) if model.intercept_key else None
            ),
        )

    @staticmethod
    def _channel_to_model(ch: CampaignChannel) -> CampaignChannelModel:
        return CampaignChannelModel(
            id=ch.id,
            campaign_id=ch.campaign_id,
            label=ch.label,
            display_order=ch.display_order,
            protocol_id=ch.protocol_id,
            readout_definition_id=ch.readout_definition_id,
            source_kind=ch.source_kind.value,
            selection_rule=ch.selection_rule.value,
            qualifier_handling=ch.qualifier_handling.value,
            qc_filter=ch.qc_filter,
            hit_threshold=ch.hit_threshold.to_dict() if ch.hit_threshold else None,
            normalization_applied=ch.normalization_applied,
            intercept_key=ch.intercept_key.to_dict() if ch.intercept_key else None,
        )

    @staticmethod
    def _channel_update_model(model: CampaignChannelModel, ch: CampaignChannel) -> None:
        model.label = ch.label
        model.display_order = ch.display_order
        model.protocol_id = ch.protocol_id
        model.readout_definition_id = ch.readout_definition_id
        model.source_kind = ch.source_kind.value
        model.selection_rule = ch.selection_rule.value
        model.qualifier_handling = ch.qualifier_handling.value
        model.qc_filter = ch.qc_filter
        model.hit_threshold = ch.hit_threshold.to_dict() if ch.hit_threshold else None
        model.normalization_applied = ch.normalization_applied
        model.intercept_key = ch.intercept_key.to_dict() if ch.intercept_key else None

    # ------------------------------------------------------------------
    # Result mapping
    # ------------------------------------------------------------------

    def _result_to_domain(self, model: CampaignResultModel) -> CampaignResult:
        added_from = (
            SourceRef.from_dict(model.added_from) if model.added_from is not None else None
        )
        return CampaignResult(
            id=model.id,
            campaign_id=model.campaign_id,
            molecule_id=model.molecule_id,
            representative_batch_id=model.representative_batch_id,
            decision=CampaignDecision(model.decision),
            decision_reason=model.decision_reason,
            notes=model.notes,
            added_from=added_from,
            measurements=[self._measurement_to_domain(mm) for mm in model.measurements],
        )

    def _result_to_model(self, r: CampaignResult) -> CampaignResultModel:
        return CampaignResultModel(
            id=r.id,
            campaign_id=r.campaign_id,
            molecule_id=r.molecule_id,
            representative_batch_id=r.representative_batch_id,
            decision=r.decision.value,
            decision_reason=r.decision_reason,
            notes=r.notes,
            added_from=r.added_from.to_dict() if r.added_from is not None else None,
            measurements=[self._measurement_to_model(m) for m in r.measurements],
        )

    def _result_update_model(self, model: CampaignResultModel, r: CampaignResult) -> None:
        model.molecule_id = r.molecule_id
        model.representative_batch_id = r.representative_batch_id
        model.decision = r.decision.value
        model.decision_reason = r.decision_reason
        model.notes = r.notes
        # added_from is immutable after first write — only set if not already persisted
        if model.added_from is None and r.added_from is not None:
            model.added_from = r.added_from.to_dict()

        # Reconcile measurements by id
        existing = {m.id: m for m in model.measurements}
        aggregate_ids = {m.id for m in r.measurements}
        for m in r.measurements:
            if m.id in existing:
                self._measurement_update_model(existing[m.id], m)
            else:
                model.measurements.append(self._measurement_to_model(m))
        for existing_id, existing_m in list(existing.items()):
            if existing_id not in aggregate_ids:
                model.measurements.remove(existing_m)

    # ------------------------------------------------------------------
    # Measurement mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _measurement_to_domain(
        model: CampaignMeasurementModel,
    ) -> CampaignMeasurement:
        return CampaignMeasurement(
            id=model.id,
            result_id=model.result_id,
            channel_id=model.channel_id,
            value=model.value,
            value_qualifier=ValueQualifier(model.value_qualifier),
            unit=model.unit,
            hit_call=HitCall(model.hit_call) if model.hit_call else None,
            is_manual_override=model.is_manual_override,
            source_run_id=model.source_run_id,
            source_curve_id=model.source_curve_id,
            source_readout_id=model.source_readout_id,
            protocol_name_snapshot=model.protocol_name_snapshot,
            protocol_version_snapshot=model.protocol_version_snapshot,
            run_date_snapshot=model.run_date_snapshot,
            override_reason=model.override_reason,
            test_concentration_value=model.test_concentration_value,
            test_concentration_unit=model.test_concentration_unit,
            replicate_count=model.replicate_count,
            qc_pass=model.qc_pass,
            contributing_run_ids=model.contributing_run_ids,
            curve_snapshot=model.curve_snapshot,
        )

    @staticmethod
    def _measurement_to_model(m: CampaignMeasurement) -> CampaignMeasurementModel:
        return CampaignMeasurementModel(
            id=m.id,
            result_id=m.result_id,
            channel_id=m.channel_id,
            value=m.value,
            value_qualifier=m.value_qualifier.value,
            unit=m.unit,
            hit_call=m.hit_call.value if m.hit_call else None,
            is_manual_override=m.is_manual_override,
            source_run_id=m.source_run_id,
            source_curve_id=m.source_curve_id,
            source_readout_id=m.source_readout_id,
            protocol_name_snapshot=m.protocol_name_snapshot,
            protocol_version_snapshot=m.protocol_version_snapshot,
            run_date_snapshot=m.run_date_snapshot,
            override_reason=m.override_reason,
            test_concentration_value=m.test_concentration_value,
            test_concentration_unit=m.test_concentration_unit,
            replicate_count=m.replicate_count,
            qc_pass=m.qc_pass,
            contributing_run_ids=m.contributing_run_ids,
            curve_snapshot=m.curve_snapshot,
        )

    @staticmethod
    def _measurement_update_model(
        model: CampaignMeasurementModel,
        m: CampaignMeasurement,
    ) -> None:
        model.value = m.value
        model.value_qualifier = m.value_qualifier.value
        model.unit = m.unit
        model.hit_call = m.hit_call.value if m.hit_call else None
        model.is_manual_override = m.is_manual_override
        model.source_run_id = m.source_run_id
        model.source_curve_id = m.source_curve_id
        model.source_readout_id = m.source_readout_id
        model.protocol_name_snapshot = m.protocol_name_snapshot
        model.protocol_version_snapshot = m.protocol_version_snapshot
        model.run_date_snapshot = m.run_date_snapshot
        model.override_reason = m.override_reason
        model.test_concentration_value = m.test_concentration_value
        model.test_concentration_unit = m.test_concentration_unit
        model.replicate_count = m.replicate_count
        model.qc_pass = m.qc_pass
        model.contributing_run_ids = m.contributing_run_ids
        model.curve_snapshot = m.curve_snapshot

    # ------------------------------------------------------------------
    # Protocol-required reads
    # ------------------------------------------------------------------

    async def find_by_project(
        self,
        workspace_id: uuid.UUID,
        project_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
        target_ids: list[uuid.UUID] | None = None,
        target_logic: str = "any",
    ) -> list[Campaign]:
        stmt = select(CampaignModel).where(
            CampaignModel.workspace_id == workspace_id,
            CampaignModel.project_id == project_id,
        )
        if tags:
            stmt = stmt.where(
                CampaignModel.id.in_(
                    tag_filter_subquery(
                        CampaignTagLinkModel, "campaign_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
        if target_ids:
            stmt = stmt.where(
                CampaignModel.id.in_(
                    campaign_target_filter_subquery(target_ids, match_all=target_logic == "all")
                )
            )
        stmt = stmt.order_by(CampaignModel.id)
        if cursor_id is not None:
            stmt = stmt.where(CampaignModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def find_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        cursor_id: uuid.UUID | None = None,
        limit: int | None = None,
        tags: list[uuid.UUID] | None = None,
        tag_logic: str = "any",
        target_ids: list[uuid.UUID] | None = None,
        target_logic: str = "any",
    ) -> list[Campaign]:
        stmt = select(CampaignModel).where(CampaignModel.workspace_id == workspace_id)
        if tags:
            stmt = stmt.where(
                CampaignModel.id.in_(
                    tag_filter_subquery(
                        CampaignTagLinkModel, "campaign_id", tags, match_all=tag_logic == "all"
                    )
                )
            )
        if target_ids:
            stmt = stmt.where(
                CampaignModel.id.in_(
                    campaign_target_filter_subquery(target_ids, match_all=target_logic == "all")
                )
            )
        stmt = stmt.order_by(CampaignModel.id)
        if cursor_id is not None:
            stmt = stmt.where(CampaignModel.id > cursor_id)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return [self._to_domain_tracked(m) for m in result.scalars().all()]

    async def is_locked(self, workspace_id: uuid.UUID, campaign_id: uuid.UUID) -> bool:
        stmt = select(CampaignModel.status).where(
            CampaignModel.id == campaign_id,
            CampaignModel.workspace_id == workspace_id,
        )
        status = (await self._session.execute(stmt)).scalar_one_or_none()
        return status in {
            CampaignStatus.CLOSED.value,
            CampaignStatus.SUPERSEDED.value,
        }

    async def project_targets(
        self, workspace_id: uuid.UUID, campaigns: list[Campaign]
    ) -> dict[uuid.UUID, list[TargetRef]]:
        # Collect every run id referenced by each campaign's measurements
        # (source_run_id union contributing_run_ids) — aggregate already loaded.
        run_ids_by_campaign: dict[uuid.UUID, set[uuid.UUID]] = {}
        all_run_ids: set[uuid.UUID] = set()
        for c in campaigns:
            run_ids: set[uuid.UUID] = set()
            for result in c.results:
                for m in result.measurements:
                    if m.source_run_id is not None:
                        run_ids.add(m.source_run_id)
                    for rid in m.contributing_run_ids or ():
                        run_ids.add(rid)
            if run_ids:
                run_ids_by_campaign[c.id] = run_ids
                all_run_ids |= run_ids

        if not all_run_ids:
            return {}

        # One batched query: run_id -> TargetRef columns. Mirrors
        # find_target_refs_for_runs — select only the 3 fields TargetRef needs
        # and join through RunModel so tenant isolation is enforced on the owner
        # side too, not just the TargetModel filter.
        rows = (
            await self._session.execute(
                select(
                    run_targets.c.run_id,
                    TargetModel.id,
                    TargetModel.name,
                    TargetModel.target_type,
                )
                .select_from(
                    run_targets.join(TargetModel, run_targets.c.target_id == TargetModel.id).join(
                        RunModel, run_targets.c.run_id == RunModel.id
                    )
                )
                .where(
                    run_targets.c.run_id.in_(all_run_ids),
                    RunModel.workspace_id == workspace_id,
                    TargetModel.workspace_id == workspace_id,
                )
            )
        ).all()
        targets_by_run: dict[uuid.UUID, list[TargetRef]] = {}
        for run_id, tid, name, tt in rows:
            targets_by_run.setdefault(run_id, []).append(
                TargetRef(id=tid, name=name, target_type=tt)
            )

        out: dict[uuid.UUID, list[TargetRef]] = {}
        for campaign_id, run_ids in run_ids_by_campaign.items():
            seen: dict[uuid.UUID, TargetRef] = {}
            for rid in run_ids:
                for t in targets_by_run.get(rid, ()):
                    seen[t.id] = t
            if seen:
                out[campaign_id] = sorted(seen.values(), key=lambda r: r.name.lower())
        return out

    async def delete(self, workspace_id: uuid.UUID, id: uuid.UUID) -> None:
        """Delete a campaign (cascades to channels/results/measurements via FK)."""
        stmt = select(CampaignModel).where(
            CampaignModel.id == id,
            CampaignModel.workspace_id == workspace_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is not None:
            await self._session.delete(model)
