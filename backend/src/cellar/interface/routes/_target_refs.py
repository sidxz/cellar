"""Shared API response models for target references.

Reused by the protocol, run, and molecule-activity routes so the target shape
stays identical across every surface that renders target chips.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel

from cellar.domain.screening_assay.target import EffectiveTarget, TargetRef


class TargetRefResponse(BaseModel):
    """Lightweight target reference — id + name + type, for chips/grids."""

    id: uuid.UUID
    name: str
    target_type: str

    @classmethod
    def from_ref(cls, ref: TargetRef) -> TargetRefResponse:
        return cls(id=ref.id, name=ref.name, target_type=ref.target_type)


class ProtocolTargetRefResponse(TargetRefResponse):
    """A protocol's effective target, with provenance for the design tab.

    ``is_direct`` — attached directly at the protocol (survives auto-prune).
    ``run_count`` — how many of the protocol's runs reference it.
    """

    is_direct: bool
    run_count: int

    @classmethod
    def from_effective(cls, t: EffectiveTarget) -> ProtocolTargetRefResponse:
        return cls(
            id=t.id,
            name=t.name,
            target_type=t.target_type,
            is_direct=t.is_direct,
            run_count=t.run_count,
        )
