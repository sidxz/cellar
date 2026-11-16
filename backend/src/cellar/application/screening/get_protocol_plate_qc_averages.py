"""GetProtocolPlateQcAverages — a protocol's plate QC averaged over its plates.

Reads each run's ``qc_metrics.plates[plate][readout][layer]`` (written by the
readout calculation engine) and reports, per readout x layer, the mean ± SD and
plate count of Z′, of each control's mean, and of each control compound's
per-plate potency (per compound; an inactive fit stores none) — the "Protocol
averages" row of a run's Data summary.
"""

from __future__ import annotations

import math
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_same_workspace, require_workspace_role
from cellar.application.screening.protocol_stats_reader import ProtocolStatsReader
from cellar.application.shared.query import Query
from cellar.domain.shared.errors import DomainError, NotFoundError

_METRICS = ("z_prime", "pos_mean", "neg_mean")


@dataclass(frozen=True, kw_only=True)
class GetProtocolPlateQcAveragesQuery(Query):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID


@dataclass(frozen=True)
class Spread:
    """Mean ± SD over ``n`` plates; ``sd`` is None for a single plate."""

    mean: float
    sd: float | None
    n: int


@dataclass(frozen=True)
class ControlFitAverage:
    role: str  # "positive_control" | "reference"
    molecule_id: str | None  # the control compound, as plate QC stores it
    label: str  # the primary intercept, e.g. "IC50"
    value: Spread  # over the plates that fitted it; a plate with two fits counts once


@dataclass(frozen=True)
class PlateQcAverage:
    readout_definition_id: uuid.UUID
    layer: str  # "raw" or a normalization
    z_prime: Spread | None
    pos_mean: Spread | None
    neg_mean: Spread | None
    control_fits: list[ControlFitAverage]


def _number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v)


def _spread(values: list[float]) -> Spread | None:
    if not values:
        return None
    sd = statistics.stdev(values) if len(values) >= 2 else None
    return Spread(mean=statistics.mean(values), sd=sd, n=len(values))


def _dicts(v: Any) -> list[tuple[str, dict[str, Any]]]:
    return [(k, x) for k, x in v.items() if isinstance(x, dict)] if isinstance(v, dict) else []


def average_plate_qc(qc_metrics: list[dict[str, Any]]) -> list[PlateQcAverage]:
    """One average per readout x layer that any plate stored; malformed entries
    (a hand-edited ``qc_metrics``) are skipped."""
    metrics: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    # (readout, layer) -> (role, molecule, label) -> per-plate mean
    fits: dict[tuple[str, str], dict[tuple[str, str | None, str], list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for qc in qc_metrics:
        for _, readouts in _dicts(qc.get("plates")):
            for rd_id, layers in _dicts(readouts):
                for layer, entry in _dicts(layers):
                    key = (rd_id, layer)
                    for m in _METRICS:
                        if _number(entry.get(m)):
                            metrics[key][m].append(float(entry[m]))
                    on_plate: dict[tuple[str, str | None, str], list[float]] = defaultdict(list)
                    for fit in entry.get("control_fits") or []:
                        if isinstance(fit, dict) and _number(fit.get("value")):
                            molecule = fit.get("molecule_id")
                            compound = (
                                str(fit.get("role")),
                                str(molecule) if molecule is not None else None,
                                str(fit.get("label")),
                            )
                            on_plate[compound].append(float(fit["value"]))
                    for compound, values in on_plate.items():
                        fits[key][compound].append(statistics.mean(values))
                    metrics.setdefault(key, defaultdict(list))

    out: list[PlateQcAverage] = []
    for rd_id, layer in sorted(metrics):
        try:
            readout_id = uuid.UUID(rd_id)
        except ValueError:
            continue
        stats = metrics[(rd_id, layer)]
        out.append(
            PlateQcAverage(
                readout_definition_id=readout_id,
                layer=layer,
                z_prime=_spread(stats["z_prime"]),
                pos_mean=_spread(stats["pos_mean"]),
                neg_mean=_spread(stats["neg_mean"]),
                control_fits=[
                    ControlFitAverage(role=role, molecule_id=molecule, label=label, value=s)
                    for (role, molecule, label), values in sorted(
                        fits[(rd_id, layer)].items(), key=lambda kv: tuple(map(str, kv[0]))
                    )
                    if (s := _spread(values)) is not None
                ],
            )
        )
    return out


class GetProtocolPlateQcAverages:
    """Plate QC averages over every plate of a protocol's runs (rejected runs left out)."""

    def __init__(self, reader: ProtocolStatsReader) -> None:
        self._reader = reader

    async def __call__(
        self,
        input: GetProtocolPlateQcAveragesQuery,
        auth: AuthContext | None = None,
    ) -> Result[list[PlateQcAverage], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        qc = await self._reader.plate_qc_metrics(input.workspace_id, input.protocol_id)
        if qc is None:
            return Failure(NotFoundError("Protocol", str(input.protocol_id)))
        return Success(average_plate_qc(qc))
