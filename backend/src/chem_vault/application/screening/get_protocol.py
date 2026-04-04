"""GetProtocol and ListProtocols query use cases."""

from __future__ import annotations

import uuid

from returns.result import Failure, Result, Success

from chem_vault.application.auth import AuthContext, require_same_workspace
from chem_vault.application.shared.unit_of_work import UnitOfWork
from chem_vault.domain.screening_assay.protocol import Protocol
from chem_vault.domain.screening_assay.repository import ProtocolRepository
from chem_vault.domain.shared.errors import DomainError, NotFoundError


class GetProtocol:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, protocol_id: uuid.UUID, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        async with self._uow:
            protocol = await self._repo.find_by_id(protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol"))
            require_same_workspace(auth, protocol.workspace_id)
            return Success(protocol)


class ListProtocols:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository) -> None:
        self._uow = uow
        self._repo = repo

    async def __call__(
        self, auth: AuthContext | None = None
    ) -> Result[list[Protocol], DomainError]:
        if auth is None:
            return Failure(NotFoundError("Protocol"))
        async with self._uow:
            protocols = await self._repo.find_by_workspace(auth.workspace_id)
            return Success(protocols)
