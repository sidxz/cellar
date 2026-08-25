"""Current-actor context — the authenticated user id for the running request.

Set once per request by the interface layer (next to the logging-context
binding in ``get_auth``); read by side-effect handlers that run after commit
without an ``auth`` in hand (the audit catch-all). A ``ContextVar`` is
task-local, so concurrent requests never see each other's actor, and a
worker/kiosk path that never calls ``get_auth`` reads ``None``.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_current_actor_id: ContextVar[uuid.UUID | None] = ContextVar("current_actor_id", default=None)


def set_current_actor(user_id: uuid.UUID | None) -> None:
    _current_actor_id.set(user_id)


def current_actor() -> uuid.UUID | None:
    return _current_actor_id.get()
