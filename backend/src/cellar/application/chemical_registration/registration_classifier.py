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
    # What the registration leaves as it is, one line each (a structure the vault id
    # overrode).
    warnings: tuple[str, ...] = ()


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


async def held_elsewhere(
    repo: MoleculeRepository,
    workspace_id: uuid.UUID,
    identifiers: Iterable[str],
    molecule_id: uuid.UUID | None,
) -> dict[str, str]:
    """Stored-only IDs another compound than ``molecule_id`` already holds → that
    compound's registration number. Case-insensitive, as compound lookup by
    identifier is (``find_by_identifier``): a case variant on a second compound
    would make that lookup ambiguous."""
    return await repo.find_identifier_holders(workspace_id, set(identifiers), molecule_id)


def skipped_id_warning(identifier: str, holder: str, this: str) -> str:
    return f"'{identifier}' is already an ID of {holder}; not stored on {this}"


async def _vault_id_holder(
    repo: MoleculeRepository,
    workspace_id: uuid.UUID,
    vault_ids: Iterable[tuple[str, str]],
) -> Molecule | None:
    """The compound holding the row's vault id, ``(text, identifier_type)``. Only the
    vault's own IDs decide which compound a CDD row is (CDD mapper spec 2026-11-18,
    decision 6), so it is the row's compound whatever its structure. The same text
    under another type (a PubChem CID, a number from a file) is not the vault id."""
    wanted = dict(vault_ids)
    if not wanted:
        return None
    found = await repo.find_identifiers_in_workspace(workspace_id, set(wanted))
    owners = set(found.values())
    if len(owners) != 1:
        return None
    holder = await repo.find_by_id_in_workspace(workspace_id, owners.pop())
    if holder is None or holder.merged_into_id is not None:
        return None
    held = {(i.identifier, i.identifier_type) for i in holder.identifiers}
    return holder if all((text, wanted[text]) in held for text in found) else None


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
    vault_ids: Iterable[tuple[str, str]] = (),
) -> RegistrationForecast:
    """Forecast for an input WITH a structure.

    InChIKey match wins (deduplicate). Failing that, an identifier owned by an
    undisclosed molecule means this structure discloses it. Any other identifier
    already taken is a conflict — checked after the two matches so identifiers on
    the matched molecule itself do not count.

    ``vault_ids`` (a CDD row's vault id, ``(text, type)``): the compound holding it is the
    row's compound even when the structure is another compound's or differs from its own;
    nothing is merged or changed, a warning says so. An undisclosed holder whose
    structure matches nothing is disclosed as usual.
    """
    existing = await repo.find_by_inchi_key(workspace_id, inchi_key)
    holder = await _vault_id_holder(repo, workspace_id, vault_ids)
    if (
        holder is not None
        and (existing is None or existing.id != holder.id)
        and (existing is not None or holder.structure_status == StructureStatus.DISCLOSED)
    ):
        reason = await _identifier_conflict(repo, workspace_id, identifiers, holder.id)
        if reason is not None:
            return RegistrationForecast(RegistrationAction.CONFLICT, conflict_reason=reason)
        this = holder.registration_number.value
        warning = (
            f"Structure also matches {existing.registration_number.value}; not merged "
            "(likely a double registration in the vault)"
            if existing is not None
            else f"Structure differs from {this}'s; not changed"
        )
        return RegistrationForecast(
            RegistrationAction.DEDUPLICATED, matched_molecule=holder, warnings=(warning,)
        )

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
    *,
    vault_ids: Iterable[tuple[str, str]] = (),
) -> RegistrationForecast:
    """Forecast for an input WITHOUT a structure: identifiers are all there is.

    ``vault_ids`` (a CDD row's vault id, ``(text, type)``): the compound holding it is the row's
    compound, disclosed or not.
    """
    holder = await _vault_id_holder(repo, workspace_id, vault_ids)
    if holder is not None:
        reason = await _identifier_conflict(repo, workspace_id, identifiers, holder.id)
        if reason is not None:
            return RegistrationForecast(RegistrationAction.CONFLICT, conflict_reason=reason)
        return RegistrationForecast(RegistrationAction.DEDUPLICATED, matched_molecule=holder)

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
