"""AsyncUnitOfWork turns a DB constraint violation into the domain's ConflictError."""

from __future__ import annotations

import uuid

import pytest

from cellar.domain.shared.errors import ConflictError
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork
from tests.integration.chemical_registration.test_molecule_repository import (
    _insert_molecule_raw,
)


@pytest.mark.integration
async def test_constraint_violation_surfaces_as_conflict_error(session_factory) -> None:
    """A unique violation leaves the UoW as ConflictError (rendered 409 with a body),
    not as a raw IntegrityError (rendered as a bare 500)."""
    ws = uuid.uuid4()
    async with AsyncUnitOfWork(session_factory) as uow:
        await _insert_molecule_raw(uow, uuid.uuid4(), ws, "CC-000001")
        await uow.commit()

    with pytest.raises(ConflictError) as exc_info:
        async with AsyncUnitOfWork(session_factory) as uow:
            await _insert_molecule_raw(uow, uuid.uuid4(), ws, "CC-000001")
            await uow.commit()

    assert "uq_mol_ws_regnum" in exc_info.value.message
    assert "CC-000001" in (exc_info.value.detail or "")
