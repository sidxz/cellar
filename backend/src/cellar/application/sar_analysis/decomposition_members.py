"""Batched member streaming for decomposition runs.

Streams ``(molecule_id, smiles, version)`` in pages so a >100K collection is
never materialized in one fetch. For a collection, member ids are paged via the
workspace-scoped collection repo (auth already enforced at the start route) and
each page is projected to ``(id, smiles, version)``; for an ad-hoc explicit set,
the bounded id list is chunked. Re-expansion at run time is why the job input
carries ``collection_id``, not ~1M ids through Temporal history.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from cellar.application.shared.pagination import COLLECTION_FETCH_MAX_PAGE_SIZE

MemberRow = tuple[UUID, str | None, int]


class MoleculeDecompositionFetcher(Protocol):
    async def fetch_for_decomposition(
        self, *, molecule_ids: list[UUID], workspace_id: UUID
    ) -> list[MemberRow]: ...


class CollectionMemberIdReader(Protocol):
    async def get_molecule_ids(
        self, workspace_id: UUID, collection_id: UUID, *, offset: int, limit: int
    ) -> list[UUID]: ...


class DecompositionMemberStream:
    def __init__(
        self,
        *,
        molecule_fetcher: MoleculeDecompositionFetcher,
        collection_reader: CollectionMemberIdReader,
        page_size: int = COLLECTION_FETCH_MAX_PAGE_SIZE,
    ) -> None:
        self._fetcher = molecule_fetcher
        self._collections = collection_reader
        self._page_size = page_size

    async def stream(
        self,
        *,
        workspace_id: UUID,
        collection_id: UUID | None,
        molecule_ids: list[UUID] | None,
    ) -> AsyncIterator[list[MemberRow]]:
        if collection_id is not None:
            offset = 0
            while True:
                page_ids = await self._collections.get_molecule_ids(
                    workspace_id, collection_id, offset=offset, limit=self._page_size
                )
                if not page_ids:
                    break
                rows = await self._fetcher.fetch_for_decomposition(
                    molecule_ids=page_ids, workspace_id=workspace_id
                )
                if rows:
                    yield rows
                if len(page_ids) < self._page_size:
                    break
                offset += self._page_size
            return

        ids = molecule_ids or []
        for i in range(0, len(ids), self._page_size):
            chunk = ids[i : i + self._page_size]
            rows = await self._fetcher.fetch_for_decomposition(
                molecule_ids=chunk, workspace_id=workspace_id
            )
            if rows:
                yield rows
