"""The activity color channel: spec, scalar selection, cache hash, snapshot.

``pick_scalar`` is the server-side port of the FE ``colorSpecScalar``
(``frontend/.../sar-analysis/lib/sar-color-spec.ts``). It does NOT aggregate —
``MoleculeActivityService.enrich_molecules`` already applied the selection rule
and returns a per-cell ``ActivityValue``. The port only *picks* one scalar:
``intercept_key`` set ⇒ match ``av.intercept_values`` by ``(kind, level)`` →
``.value``; else ⇒ ``av.value``. This guarantees parity with what the FE used to
compute client-side.

``channel_hash`` is the cache key's channel half. It normalizes over the
SEMANTIC fields only — what actually determines the scalar — so two channels that
differ only by display ``label`` (or redundant ``protocol_id``/``source``) hash
equal and reuse the cached projection.
"""

from __future__ import annotations

import datetime
import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from cellar.application.sar_analysis.hashing import sha256_hex
from cellar.domain.screening_assay.activity_types import ActivityValue
from cellar.domain.screening_assay.run_scope import RunScope
from cellar.domain.shared.aggregation_types import QualifierHandling, SelectionRule
from cellar.domain.shared.hit_criterion import InterceptKey


@dataclass(frozen=True)
class ActivityChannelSpec:
    """One SAR color channel. ``column`` is the enrich token (``drc:<rd>`` or
    ``rd:<proto>:<rd>``); ``intercept_key`` narrows which scalar on the cell;
    ``run_scopes`` is the raw FE wire shape (mode-keyed), parsed at run time."""

    column: str
    source: str  # "dr_curve" | "readout_data"
    selection_rule: SelectionRule
    qualifier_handling: QualifierHandling
    intercept_key: InterceptKey | None = None
    run_scopes: dict[str, Any] | None = None
    protocol_id: UUID | None = None
    label: str = ""

    def resolved_run_scopes(self) -> dict[str, RunScope] | None:
        if not self.run_scopes:
            return None
        return {k: RunScope.from_wire(v) for k, v in self.run_scopes.items()}

    def to_spec_dict(self) -> dict[str, Any]:
        """Full JSON-safe dict for the ``channel_spec`` JSONB column (carries
        ``label``/``protocol_id`` for provenance; those are excluded from the
        hash)."""
        return {
            "column": self.column,
            "source": self.source,
            "selection_rule": self.selection_rule.value,
            "qualifier_handling": self.qualifier_handling.value,
            "intercept_key": (
                {"kind": self.intercept_key.kind, "level": self.intercept_key.level}
                if self.intercept_key is not None
                else None
            ),
            "run_scopes": self.run_scopes,
            "protocol_id": str(self.protocol_id) if self.protocol_id is not None else None,
            "label": self.label,
        }

    @classmethod
    def from_spec_dict(cls, d: dict[str, Any]) -> ActivityChannelSpec:
        ik = d.get("intercept_key")
        pid = d.get("protocol_id")
        return cls(
            column=d["column"],
            source=d.get("source", "dr_curve"),
            selection_rule=SelectionRule(d["selection_rule"]),
            qualifier_handling=QualifierHandling(d["qualifier_handling"]),
            intercept_key=(
                InterceptKey(kind=ik["kind"], level=float(ik["level"])) if ik else None
            ),
            run_scopes=d.get("run_scopes"),
            protocol_id=uuid.UUID(pid) if pid else None,
            label=d.get("label", ""),
        )


def channel_hash(spec: ActivityChannelSpec) -> str:
    """SHA-256 over the SEMANTIC determinants of the scalar — column, intercept,
    selection rule, qualifier handling, run scopes. ``label``/``protocol_id``/
    ``source`` are excluded (cosmetic or redundant with ``column``)."""
    semantic = {
        "column": spec.column,
        "intercept_key": (
            {"kind": spec.intercept_key.kind, "level": spec.intercept_key.level}
            if spec.intercept_key is not None
            else None
        ),
        "selection_rule": spec.selection_rule.value,
        "qualifier_handling": spec.qualifier_handling.value,
        "run_scopes": spec.run_scopes,
    }
    return sha256_hex(json.dumps(semantic, sort_keys=True, separators=(",", ":")))


def pick_scalar(av: ActivityValue, intercept_key: InterceptKey | None) -> float | None:
    """Port of FE ``colorSpecScalar``. Pre-aggregated ``av`` in, one scalar out."""
    if intercept_key is not None:
        for iv in av.intercept_values or []:
            spec = iv.get("spec") or {}
            level = spec.get("level")
            if (
                spec.get("kind") == intercept_key.kind
                and isinstance(level, (int, float))
                and float(level) == intercept_key.level
            ):
                val = iv.get("value")
                return float(val) if isinstance(val, (int, float)) else None
        return None
    return av.value


def _json_default(o: Any) -> Any:
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    raise TypeError(f"not JSON serializable: {type(o)!r}")


def activity_value_snapshot(av: ActivityValue) -> dict[str, Any]:
    """The ``ActivityValue`` as the same JSON wire shape the search grid consumes
    (``asdict`` + UUID→str / date→isoformat), so curve-expand renders off the
    snapshot without ``props.molecules``."""
    return json.loads(json.dumps(asdict(av), default=_json_default))
