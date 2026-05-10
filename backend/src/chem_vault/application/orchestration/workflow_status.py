"""Application-layer workflow orchestration errors.

Insulates use cases and routes from any specific workflow engine
(Temporal, Celery, in-process). Each workflow family defines its own
``status: str`` vocabulary (e.g. ``"pending"`` / ``"processing"`` /
``"discovering"`` / ``"completed"`` / ``"failed"``); adapters reconcile
engine-native statuses (e.g. ``temporalio.client.WorkflowExecutionStatus``)
into that vocabulary before returning a progress DTO.
"""

from __future__ import annotations

from chem_vault.domain.shared.errors import ServiceUnavailableError


class WorkflowOrchestratorUnavailable(ServiceUnavailableError):
    """Raised when the configured workflow engine is not reachable.

    Use cases catch this to decide whether to fall back to an in-process
    pipeline (e.g. bulk registration) or surface a 503 to the caller.
    """
