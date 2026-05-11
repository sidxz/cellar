"""GetPublishedCampaign — read-only query materializing the DAIKON contract (spec §6).

Loads a closed (or superseded) campaign and serializes it into the JSON shape
consumed by DAIKON: one self-contained document per campaign that includes the
campaign header, compound source, source-protocol snapshot, channel definitions,
per-compound result rows (with measurements), and the published Collection.

Uses a single UoW to wrap all repository calls in one read-only transaction.
No event registration.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_editor
from chem_vault.application.shared.command import Command
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.chemical_registration.repository import (
    MoleculeRepository,
)
from chem_vault.domain.inventory.repository import BatchRepository
from chem_vault.domain.research_organization.source_ref import ManualRef, SourceRef
from chem_vault.domain.research_organization.enums import CampaignStatus
from chem_vault.domain.research_organization.repository import (
    CampaignRepository,
    CollectionRepository,
    ProjectRepository,
)
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import (
    AuthorizationError,
    DomainError,
    NotFoundError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Cursor helpers — offset encoded as decimal string
# ---------------------------------------------------------------------------


def _encode_cursor(offset: int) -> str:
    return str(offset)


def _decode_cursor(cursor: str | None, default: int) -> int:
    if cursor is None:
        return default
    try:
        return int(cursor)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Query dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class GetPublishedCampaignQuery(Command):
    workspace_id: uuid.UUID
    campaign_id: uuid.UUID
    cursor: str | None = None       # opaque offset cursor
    page_size: int | None = None    # if None, return all results (no pagination)


# ---------------------------------------------------------------------------
# Use case
# ---------------------------------------------------------------------------


class GetPublishedCampaign:
    """Materialize a closed/superseded campaign into the DAIKON JSON contract.

    Read-only — never mutates aggregates or registers events.
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        campaign_repo: CampaignRepository,
        project_repo: ProjectRepository,
        protocol_repo: ProtocolRepository,
        collection_repo: CollectionRepository,
        molecule_repo: MoleculeRepository,
        batch_repo: BatchRepository,
    ) -> None:
        self._uow = uow
        self._campaign_repo = campaign_repo
        self._project_repo = project_repo
        self._protocol_repo = protocol_repo
        self._collection_repo = collection_repo
        self._molecule_repo = molecule_repo
        self._batch_repo = batch_repo

    async def __call__(
        self,
        input: GetPublishedCampaignQuery,
        auth: AuthContext | None = None,
    ) -> Result[dict[str, Any], DomainError]:
        # Step 1 — auth guard (lowest available: editor).
        # TODO viewer-level auth: replace with require_viewer(auth) once that guard exists.
        try:
            require_editor(auth)
        except AuthorizationError as e:
            return Failure(e)

        async with self._uow:
            return await self._execute(input)

    async def _execute(self, input: GetPublishedCampaignQuery) -> Result[dict[str, Any], DomainError]:
        # Step 2 — load campaign.
        campaign = await self._campaign_repo.find_by_id_in_workspace(
            input.workspace_id, input.campaign_id
        )
        if campaign is None:
            return Failure(NotFoundError("Campaign", str(input.campaign_id)))

        # Step 3 — only closed or superseded campaigns can be published.
        if campaign.status not in (CampaignStatus.CLOSED, CampaignStatus.SUPERSEDED):
            return Failure(
                ValidationError("Only closed/superseded campaigns can be published")
            )

        # Step 4 — load project (None is acceptable).
        project = await self._project_repo.find_by_id_in_workspace(
            input.workspace_id, campaign.project_id
        )

        # Step 5 — build channel protocol lookup (live channel rows, not snapshot).
        distinct_protocol_ids: list[uuid.UUID] = []
        seen_pids: set[uuid.UUID] = set()
        for ch in campaign.channels:
            if ch.protocol_id not in seen_pids:
                seen_pids.add(ch.protocol_id)
                distinct_protocol_ids.append(ch.protocol_id)

        protocol_lookup: dict[uuid.UUID, Any] = {}
        if distinct_protocol_ids:
            loaded_protocols = await self._protocol_repo.find_by_ids(
                input.workspace_id, distinct_protocol_ids
            )
            for p in loaded_protocols:
                protocol_lookup[p.id] = p

        # Step 5b — build readout-definition lookup within loaded protocols.
        readout_lookup: dict[uuid.UUID, Any] = {}
        for p in protocol_lookup.values():
            for rd in p.readout_definitions:
                readout_lookup[rd.id] = rd

        # Step 6 — load published collection + size (if any).
        published_collection_dict: dict[str, Any] | None = None
        if campaign.published_collection_id is not None:
            coll = await self._collection_repo.find_by_id_in_workspace(
                input.workspace_id, campaign.published_collection_id
            )
            if coll is not None:
                coll_size = await self._collection_repo.count_molecules(
                    input.workspace_id, coll.id
                )
                published_collection_dict = {
                    "id": str(coll.id),
                    "name": coll.name,
                    "size": coll_size,
                }

        # Step 7 — apply pagination to results list.
        all_results = list(campaign.results)
        offset = _decode_cursor(input.cursor, 0)
        if input.page_size is not None:
            page = all_results[offset : offset + input.page_size]
        else:
            page = all_results

        # Step 7b — bulk-load molecules for this page.
        mol_ids = list({r.molecule_id for r in page})
        molecules = await self._molecule_repo.find_by_ids(input.workspace_id, mol_ids)
        mol_lookup: dict[uuid.UUID, Any] = {m.id: m for m in molecules}

        # Step 8 — bulk-load batches for this page (iterate find_by_id — no bulk helper).
        batch_ids = list({r.representative_batch_id for r in page if r.representative_batch_id is not None})
        batch_lookup: dict[uuid.UUID, Any] = {}
        for bid in batch_ids:
            # TODO bulk lookup: add find_by_ids to BatchRepository when available.
            b = await self._batch_repo.find_by_id(bid)
            if b is not None:
                batch_lookup[bid] = b

        # Step 9 — build pagination envelope.
        pagination: dict[str, Any] | None = None
        if input.page_size is not None:
            next_offset = offset + input.page_size
            next_cursor = (
                _encode_cursor(next_offset)
                if next_offset < len(all_results)
                else None
            )
            pagination = {
                "next_cursor": next_cursor,
                "total": len(all_results),
            }

        # Step 10 — serialize.
        doc: dict[str, Any] = {
            "campaign": _serialize_campaign(campaign, project),
            "compound_sources": _derive_compound_sources(campaign.results),
            "source_protocols": list(campaign.source_protocols),  # snapshot set at close
            "channels": [
                _serialize_channel(ch, protocol_lookup, readout_lookup)
                for ch in campaign.channels
            ],
            "results": [
                _serialize_result(r, mol_lookup, batch_lookup)
                for r in page
            ],
            "published_collection": published_collection_dict,
        }
        if pagination is not None:
            doc["pagination"] = pagination

        return Success(doc)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_campaign(campaign: Any, project: Any | None) -> dict[str, Any]:
    """Serialize the campaign header, embedding the already-resolved project (or None)."""
    # TODO Sentinel-resolved user name: closed_by is a UUID; name resolution requires Sentinel.
    closed_by_dict: dict[str, Any] | None = None
    if campaign.closed_by is not None:
        closed_by_dict = {
            "id": str(campaign.closed_by),
            "name": None,  # TODO Sentinel-resolved user name
        }

    # TODO audit signature: load from AuditCompliance context when SignatureService lands.
    signature_dict: dict[str, Any] | None = None
    if campaign.signature_id is not None:
        signature_dict = {
            "id": str(campaign.signature_id),
            "signed_at": None,  # TODO audit signature lookup
        }

    return {
        "id": str(campaign.id),
        "name": campaign.name,
        "description": campaign.description,
        "project": (
            {"id": str(project.id), "name": project.name}
            if project is not None
            else None
        ),
        "status": campaign.status.value,
        "closed_at": campaign.closed_at.isoformat() if campaign.closed_at is not None else None,
        "closed_by": closed_by_dict,
        "signature": signature_dict,
        "supersedes_campaign_id": (
            str(campaign.supersedes_campaign_id)
            if campaign.supersedes_campaign_id is not None
            else None
        ),
        "superseded_by_campaign_id": (
            str(campaign.superseded_by_campaign_id)
            if campaign.superseded_by_campaign_id is not None
            else None
        ),
    }


def _derive_compound_sources(results: list[Any]) -> list[dict[str, Any]]:
    """Derive a compound_sources summary from per-result added_from attribution.

    Groups results by (kind, canonical ref dict key, description) and emits a
    list entry per group with a count. Results with added_from=None (or ManualRef)
    group together as kind="manual".

    DAIKON format:
      [{"kind": "collection", "ref": {"collection_id": "..."}, "description": "...", "count": N}, ...]
    """
    # Use a dict keyed by a stable grouping key to preserve insertion order.
    groups: dict[tuple, dict[str, Any]] = {}

    for r in results:
        added_from = getattr(r, "added_from", None)
        if added_from is None or isinstance(added_from, ManualRef):
            key = ("manual", None, None)
            if key not in groups:
                groups[key] = {"kind": "manual", "ref": {}, "description": None, "count": 0}
            groups[key]["count"] += 1
        else:
            d = added_from.to_dict()
            kind = d.get("kind", "unknown")
            description = d.get("description")
            # Build a canonical ref dict (everything except kind and description).
            ref = {k: v for k, v in d.items() if k not in ("kind", "description")}
            # Freeze ref for use as dict key
            frozen_ref = tuple(sorted(ref.items()))
            key = (kind, frozen_ref, description)
            if key not in groups:
                groups[key] = {"kind": kind, "ref": ref, "description": description, "count": 0}
            groups[key]["count"] += 1

    return list(groups.values())


def _serialize_channel(
    channel: Any,
    protocol_lookup: dict[uuid.UUID, Any],
    readout_lookup: dict[uuid.UUID, Any],
) -> dict[str, Any]:
    proto = protocol_lookup.get(channel.protocol_id)
    if proto is not None:
        protocol_ref: dict[str, Any] = {
            "id": str(proto.id),
            "name": proto.name,
            "version": proto.protocol_version,
        }
    else:
        # defensive: channel references a protocol not in the lookup — don't fail.  # defensive
        protocol_ref = {
            "id": str(channel.protocol_id),
            "name": None,
            "version": None,
        }

    rd = readout_lookup.get(channel.readout_definition_id)
    if rd is not None:
        readout_dict: dict[str, Any] = {
            "id": str(rd.id),
            "name": rd.name,
            "unit": rd.unit,
            "data_type": rd.data_type.value if hasattr(rd.data_type, "value") else str(rd.data_type),
        }
    else:
        # defensive: readout not found in lookup.  # defensive
        readout_dict = {
            "id": str(channel.readout_definition_id),
            "name": None,
            "unit": None,
            "data_type": None,
        }

    hit_threshold: dict[str, Any] | None = None
    if channel.hit_threshold is not None:
        hit_threshold = channel.hit_threshold.to_dict()

    qc_filter: dict[str, Any] | None = channel.qc_filter

    return {
        "id": str(channel.id),
        "label": channel.label,
        "display_order": channel.display_order,
        "protocol_ref": protocol_ref,
        "readout": readout_dict,
        "source_kind": channel.source_kind.value,
        "selection_rule": channel.selection_rule.value,
        "qc_filter": qc_filter,
        "hit_threshold": hit_threshold,
    }


def _serialize_result(
    result: Any,
    mol_lookup: dict[uuid.UUID, Any],
    batch_lookup: dict[uuid.UUID, Any],
) -> dict[str, Any]:
    mol = mol_lookup.get(result.molecule_id)
    if mol is not None:
        smiles: str | None = None
        if mol.structure is not None:
            smiles = mol.structure.smiles
        molecule_dict: dict[str, Any] = {
            "id": str(mol.id),
            "primary_id": mol.registration_number.value,
            "name": mol.name,
            "structure_smiles": smiles,
        }
    else:
        molecule_dict = {
            "id": str(result.molecule_id),
            "primary_id": None,
            "name": None,
            "structure_smiles": None,
        }

    rep_batch: dict[str, Any] | None = None
    if result.representative_batch_id is not None:
        b = batch_lookup.get(result.representative_batch_id)
        if b is not None:
            rep_batch = {
                "id": str(b.id),
                "name": b.batch_number.value,
            }

    measurements = [_serialize_measurement(m) for m in result.measurements]

    return {
        "molecule": molecule_dict,
        "representative_batch": rep_batch,
        "decision": result.decision.value,
        "decision_reason": result.decision_reason,
        "notes": result.notes,
        "measurements": measurements,
    }


def _serialize_measurement(m: Any) -> dict[str, Any]:
    source: dict[str, Any] | None = None
    if m.source_run_id is not None:
        source = {
            "run_id": str(m.source_run_id),
            "run_date": m.run_date_snapshot.isoformat() if m.run_date_snapshot is not None else None,
            "protocol_name": m.protocol_name_snapshot,
            "protocol_version": m.protocol_version_snapshot,
        }

    # Migration 029 — snapshot + audit fields. Flat schema: emit nulls when absent
    # so DAIKON consumers can rely on key presence.
    test_concentration: dict[str, Any] | None = None
    if m.test_concentration_value is not None:
        test_concentration = {
            "value": m.test_concentration_value,
            "unit": m.test_concentration_unit,
        }

    return {
        "channel_id": str(m.channel_id),
        "value": m.value,
        "value_qualifier": m.value_qualifier.value,
        "unit": m.unit,
        "hit_call": m.hit_call.value if m.hit_call is not None else None,
        "is_manual_override": m.is_manual_override,
        "override_reason": m.override_reason,
        "test_concentration": test_concentration,
        "replicate_count": m.replicate_count,
        "qc_pass": m.qc_pass,
        "source": source,
        "contributing_run_ids": (
            [str(rid) for rid in m.contributing_run_ids]
            if m.contributing_run_ids
            else None
        ),
    }

