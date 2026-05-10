"""Batch creation policy for re-registration."""

from __future__ import annotations


def should_create_batch(
    *,
    is_new_molecule: bool,
    override: bool | None,
    workspace_default: bool,
) -> bool:
    if is_new_molecule:
        return True
    return override if override is not None else workspace_default
