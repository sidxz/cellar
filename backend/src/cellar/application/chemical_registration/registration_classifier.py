"""What a registration WILL do — the one rule shared by RegisterMolecule and the preview.

``RegisterMolecule`` calls these inside its single read-branch-write transaction and acts
on the forecast; ``PreviewRegistration`` calls the same functions in a read-only
transaction and merely reports it. One implementation is the point: a preview carrying
its own copy of the rule would become a lie the first time either side was edited.

Pure reads only (``find_by_inchi_key``, ``find_undisclosed_by_identifiers``,
``find_identifiers_in_workspace``, ``find_by_id_in_workspace``); nothing here writes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from cellar.domain.chemical_registration.enums import RegistrationAction, StructureStatus
from cellar.domain.chemical_registration.molecule import Molecule
from cellar.domain.chemical_registration.repository import MoleculeRepository


@dataclass(frozen=True)
class RegistrationForecast:
    action: RegistrationAction
    # DEDUPLICATED: the molecule the input collapses into.
    # DISCLOSED: the undisclosed molecule the structure would disclose.
    matched_molecule: Molecule | None = None
    conflict_reason: str | None = None


def collect_identifiers(
    name: str | None, external_ids: Iterable[str], *, promote_name: bool
) -> set[str]:
    """Every identifier the registration will claim: external ids plus the name.

    POST /molecules promotes the name to a custom identifier by default, so a
    name-only payload still dedups or conflicts on that name.
    """
    ids = set(external_ids)
    if name and promote_name:
        ids.add(name)
    return ids


async def _identifier_conflict(
    repo: MoleculeRepository,
    workspace_id: uuid.UUID,
    identifiers: set[str],
    allowed_molecule_id: uuid.UUID | None,
) -> str | None:
    """Reason, if any identifier is already owned by a molecule other than ``allowed``."""
    if not identifiers:
        return None
    existing_map = await repo.find_identifiers_in_workspace(workspace_id, identifiers)
    for identifier, owner_id in existing_map.items():
        if allowed_molecule_id is not None and owner_id == allowed_molecule_id:
            continue  # already on the target molecule — not a conflict
        return f"Identifier '{identifier}' is already assigned to another molecule"
    return None


async def classify_disclosed(
    repo: MoleculeRepository,
    workspace_id: uuid.UUID,
    inchi_key: str,
    identifiers: set[str],
    *,
    detect_undisclosed: bool,
) -> RegistrationForecast:
    """Forecast for an input WITH a structure.

    InChIKey match wins (deduplicate). Failing that, an identifier owned by an
    undisclosed molecule means this structure discloses it. Any other identifier
    already taken is a conflict — checked after the two matches so identifiers on
    the matched molecule itself do not count.
    """
    existing = await repo.find_by_inchi_key(workspace_id, inchi_key)
    undisclosed: Molecule | None = None
    if existing is None and detect_undisclosed and identifiers:
        undisclosed = await repo.find_undisclosed_by_identifiers(workspace_id, identifiers)

    allowed = existing.id if existing else (undisclosed.id if undisclosed else None)
    reason = await _identifier_conflict(repo, workspace_id, identifiers, allowed)
    if reason is not None:
        return RegistrationForecast(RegistrationAction.CONFLICT, conflict_reason=reason)
    if undisclosed is not None:
        return RegistrationForecast(RegistrationAction.DISCLOSED, matched_molecule=undisclosed)
    if existing is not None:
        return RegistrationForecast(RegistrationAction.DEDUPLICATED, matched_molecule=existing)
    return RegistrationForecast(RegistrationAction.REGISTERED)


async def classify_undisclosed(
    repo: MoleculeRepository,
    workspace_id: uuid.UUID,
    identifiers: set[str],
) -> RegistrationForecast:
    """Forecast for an input WITHOUT a structure: identifiers are all there is."""
    existing_map = await repo.find_identifiers_in_workspace(workspace_id, identifiers)

    matched_id: uuid.UUID | None = None
    for _identifier, owner_id in existing_map.items():
        if matched_id is None:
            matched_id = owner_id
        elif owner_id != matched_id:
            return RegistrationForecast(
                RegistrationAction.CONFLICT,
                conflict_reason="Identifiers map to different molecules",
            )
    if matched_id is None:
        return RegistrationForecast(RegistrationAction.REGISTERED)

    matched = await repo.find_by_id_in_workspace(workspace_id, matched_id)
    if matched is None:
        return RegistrationForecast(RegistrationAction.REGISTERED)
    if matched.structure_status == StructureStatus.DISCLOSED:
        conflict_id = next(k for k, v in existing_map.items() if v == matched_id)
        return RegistrationForecast(
            RegistrationAction.CONFLICT,
            conflict_reason=(
                f"Identifier '{conflict_id}' belongs to disclosed "
                f"molecule '{matched.registration_number.value}'"
            ),
        )
    return RegistrationForecast(RegistrationAction.DEDUPLICATED, matched_molecule=matched)
