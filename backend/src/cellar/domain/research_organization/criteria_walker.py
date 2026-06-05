"""Shared traversal helpers for the FE's nested ``criteria`` JSON shape.

The search payload is a tree where each node is either a leaf criterion
(``{"type": "structure" | "activity" | "property" | ...}``) or a group
(``{"type": "group", "criteria": [...]}``). Multiple application + infra
helpers walk this tree — every one re-encoded the same
``if c.type == "group": recurse else: inspect`` pattern.

This module exposes two primitives:

- ``walk_criteria(root, visit)`` — depth-first pre-order traversal that
  invokes ``visit(node)`` for every leaf criterion. Group nodes are
  recursed into but not visited.
- ``find_first(root, predicate)`` — return the first leaf criterion for
  which ``predicate`` returns truthy, else ``None``.

The walker tolerates malformed input (missing ``type``, non-list
``criteria``) — best-effort traversal mirrors how the FE-supplied JSON
historically arrives.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Criterion = dict[str, Any]


def walk_criteria(root: list[Criterion] | None, visit: Callable[[Criterion], None]) -> None:
    """Depth-first walk; invoke ``visit`` on every non-group leaf node."""
    if not root:
        return
    for c in root:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "group":
            children = c.get("criteria")
            if isinstance(children, list):
                walk_criteria(children, visit)
        else:
            visit(c)


def find_first(
    root: list[Criterion] | None,
    predicate: Callable[[Criterion], bool],
) -> Criterion | None:
    """Return the first leaf criterion matching ``predicate``, else ``None``.

    Short-circuits as soon as a match is found. Search order is depth-first
    pre-order — matches the same traversal as ``walk_criteria``.
    """
    if not root:
        return None
    for c in root:
        if not isinstance(c, dict):
            continue
        if c.get("type") == "group":
            children = c.get("criteria")
            if isinstance(children, list):
                hit = find_first(children, predicate)
                if hit is not None:
                    return hit
        elif predicate(c):
            return c
    return None


def any_match(
    root: list[Criterion] | None,
    predicate: Callable[[Criterion], bool],
) -> bool:
    """True if any leaf criterion matches ``predicate``."""
    return find_first(root, predicate) is not None
