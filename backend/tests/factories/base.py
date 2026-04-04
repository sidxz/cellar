"""Base factory with common defaults for all domain factories."""

from __future__ import annotations

import uuid

import factory


class BaseFactory(factory.Factory):
    """Common defaults for all domain entity factories.

    Provides workspace_id and user_id so callers can rely on them.
    Override per-test with ``BaseFactory(workspace_id=my_ws_id)``.
    """

    class Meta:
        abstract = True

    id = factory.LazyFunction(uuid.uuid4)
    workspace_id: uuid.UUID = factory.LazyFunction(uuid.uuid4)  # type: ignore[assignment]
