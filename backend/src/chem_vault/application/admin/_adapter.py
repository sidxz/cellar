"""Adapter from arbitrary repos to the _DeletableRepo protocol."""
from __future__ import annotations


class RepoAdapter:
    """Wraps a repo with custom method names into find_by_id/delete shape.

    Note: Task 7 changed the repo_resolver signature to (container, uow).
    The adapter is stateless — instantiate it via the resolver, but the
    underlying repo holds the AsyncSession through the active UoW.

    Usage:
        adapter = RepoAdapter(repo, find='find_by_id_in_workspace', delete='delete')
    """

    def __init__(self, repo, *, find: str, delete: str = "delete"):
        self._repo, self._find, self._delete = repo, find, delete

    async def find_by_id(self, workspace_id, id):
        return await getattr(self._repo, self._find)(workspace_id, id)

    async def delete(self, workspace_id, id):
        await getattr(self._repo, self._delete)(workspace_id, id)
