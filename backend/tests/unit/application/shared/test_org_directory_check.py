"""A picked org must be one Duar lists and has not disabled."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from cellar.application.shared.org_directory import unpickable_org
from cellar.domain.shared.errors import ValidationError


@dataclass(frozen=True)
class _Org:
    id: uuid.UUID
    enabled: bool = True


class _Directory:
    def __init__(self, *orgs: _Org) -> None:
        self._orgs = list(orgs)

    async def list_orgs(self) -> list[_Org]:
        return self._orgs


@pytest.mark.asyncio
async def test_enabled_org_is_pickable() -> None:
    org = _Org(uuid.uuid4())
    assert await unpickable_org(_Directory(org), org.id) is None


@pytest.mark.asyncio
async def test_unknown_org_is_refused() -> None:
    err = await unpickable_org(_Directory(_Org(uuid.uuid4())), uuid.uuid4())
    assert isinstance(err, ValidationError)


@pytest.mark.asyncio
async def test_disabled_org_is_refused() -> None:
    org = _Org(uuid.uuid4(), enabled=False)
    assert isinstance(await unpickable_org(_Directory(org), org.id), ValidationError)
