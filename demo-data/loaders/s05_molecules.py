"""Step 05 — Register molecules (FDA-approved drugs with public SMILES)."""

from __future__ import annotations

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.chemical_registration.register_molecule import (
        RegisterMolecule,
        RegisterMoleculeCommand,
    )

    data: dict = ctx.data("molecules.json")
    register_uc = ctx.container[RegisterMolecule]
    created = 0

    for key, rec in data.items():
        # Skip metadata entries (keys starting with _)
        if key.startswith("_"):
            continue

        org_id = ctx.registry.get(rec["org_ref"])

        cmd = RegisterMoleculeCommand(
            workspace_id=WORKSPACE_ID,
            name=rec["name"],
            smiles=rec["smiles"],
            molecule_type="small_molecule",
            originating_org_id=org_id,
            registered_by=USER_ID,
        )
        result = await register_uc(cmd, auth=None)

        # RegisterMolecule is already idempotent on SMILES — returns existing
        # molecule on duplicate InChI key. Never returns ConflictError for dupes.
        from returns.result import Failure

        if isinstance(result, Failure):
            logger.warning("molecule.failed", key=key, name=rec["name"], error=str(result.failure()))
            continue

        outcome = result.unwrap()
        ctx.registry.put(key, outcome.molecule.id)

        if outcome.is_new:
            created += 1
            logger.info(
                "molecule.registered",
                key=key,
                name=rec["name"],
                reg_number=outcome.molecule.registration_number.value,
            )
        else:
            logger.debug(
                "molecule.exists",
                key=key,
                name=rec["name"],
                reg_number=outcome.molecule.registration_number.value,
            )

    return created
