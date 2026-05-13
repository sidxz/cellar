"""GET /api/v1/search/algorithms -- frontend renders mode radios from this."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from cellar.domain.sar_analysis.search_modes import MODE_DEFAULTS
from cellar.domain.sar_analysis.similarity_metric import serialize_metric
from cellar.interface.dependencies import AuthDep, FingerprintRegistryDep

router = APIRouter(prefix="/api/v1/search", tags=["search"])

_ALGORITHM_DESCRIPTIONS = {
    "morgan": (
        "Morgan circular fingerprint (ECFP4-equivalent), 2048-bit, stereo-aware. "
        "Industry standard for analog and SAR retrieval."
    ),
    "fcfp": (
        "Feature-class circular fingerprint (FCFP4-equivalent), 2048-bit. "
        "Pharmacophore-aware variant suited to scaffold hopping."
    ),
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
async def list_algorithms(
    _auth: AuthDep,
    registry: FingerprintRegistryDep,
) -> _AlgorithmsResponse:
    """Return available search modes and fingerprint algorithms.

    Frontend uses this to render mode radios and threshold defaults.
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
        for a in registry.all()
    ]
    return _AlgorithmsResponse(modes=modes, algorithms=algorithms)
