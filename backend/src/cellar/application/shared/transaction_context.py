"""TransactionContext — opaque port for session-scoped writes.

A handful of application paths (admin cascade delete, atomic audit
recording) need to pass the active transaction context into a repository
method so the audit write participates in the caller's transaction. The
concrete implementation is an SQLAlchemy ``AsyncSession``, but the
application layer must not name that infra type — that would re-introduce
the leak the layer-dependency rule forbids.

This Protocol is the narrow public face of the session that audit code
needs. SQLAlchemy's ``AsyncSession`` satisfies it structurally; tests can
substitute a stub with the same two methods.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TransactionContext(Protocol):
    """Opaque transaction handle accepted by session-aware repositories.

    Intentionally minimal — the audit pipeline only needs ``add`` (queue
    an SA model on the active session) and ``flush`` (force a write so
    subsequent reads see it). Anything broader belongs in the concrete
    impl, not on this Protocol.
    """

    def add(self, instance: Any) -> Any: ...
    async def flush(self) -> None: ...
