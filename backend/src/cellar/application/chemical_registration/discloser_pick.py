"""Check who a registrant says disclosed a compound, and for which Duar org."""

from __future__ import annotations

import uuid

from cellar.application.auth import AuthContext, is_workspace_member
from cellar.application.shared.org_directory import OrgDirectoryPort, unpickable_org
from cellar.domain.shared.errors import DomainError, ValidationError


async def check_discloser_pick(
    auth: AuthContext | None,
    directory: OrgDirectoryPort | None,
    *,
    disclosed_by: uuid.UUID | None,
    disclosed_by_org_id: uuid.UUID | None,
) -> DomainError | None:
    """The org must be one Duar lists and has not disabled; a person other than the caller
    must be a current workspace member. Workers (no auth) run what a person already checked."""
    if auth is None:
        return None
    if (
        disclosed_by_org_id is not None
        and directory is not None
        and (err := await unpickable_org(directory, disclosed_by_org_id)) is not None
    ):
        return err
    if (
        disclosed_by is not None
        and disclosed_by != auth.user_id
        and not await is_workspace_member(auth, disclosed_by)
    ):
        return ValidationError(f"{disclosed_by} is not a member of this workspace")
    return None
