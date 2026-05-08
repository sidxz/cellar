"""GET /api/v1/search/algorithms -- frontend renders mode radios from this."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from chem_vault.domain.sar_analysis.search_modes import MODE_DEFAULTS
from chem_vault.domain.sar_analysis.similarity_metric import serialize_metric
from chem_vault.infrastructure.rdkit.fingerprints.registry import FingerprintRegistry

router = APIRouter(prefix="/api/v1/search", tags=["search"])
_registry = FingerprintRegistry.default()

_ALGORITHM_DESCRIPTIONS = {
    "morgan": "Circular topological FP (ECFP4-equivalent), stereo-aware",
    "fcfp": "Pharmacophore-flavored circular FP",
}


class _ModeInfo(BaseModel):
    name: str
    label: str
    description: str
    default_threshold: float
    algorithm: str
    metric: str


class _AlgorithmInfo(BaseModel):
    name: str
    description: str


class _AlgorithmsResponse(BaseModel):
    modes: list[_ModeInfo]
    algorithms: list[_AlgorithmInfo]


@router.get("/algorithms", response_model=_AlgorithmsResponse)
async def list_algorithms() -> _AlgorithmsResponse:
    """Return available search modes and fingerprint algorithms.

    This endpoint is metadata-only — no auth dependency, no DB access.
    Frontend uses it to render mode radios and threshold defaults.
    """
    modes = [
        _ModeInfo(
            name=mode.value,
            label=cfg.label,
            description=cfg.description,
            default_threshold=cfg.threshold,
            algorithm=cfg.algorithm,
            metric=serialize_metric(cfg.metric),
        )
        for mode, cfg in MODE_DEFAULTS.items()
    ]
    algorithms = [
        _AlgorithmInfo(
            name=a.name,
            description=_ALGORITHM_DESCRIPTIONS.get(a.name, ""),
        )
        for a in _registry.all()
    ]
    return _AlgorithmsResponse(modes=modes, algorithms=algorithms)
