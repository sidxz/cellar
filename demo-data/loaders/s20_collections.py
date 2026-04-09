"""Step 20 — Load collections and populate with molecule membership."""

from __future__ import annotations

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext
from ._result import try_create

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from chem_vault.application.research_organization.collection_membership import (
        AddMoleculesToCollection,
        AddMoleculesToCollectionCommand,
    )
    from chem_vault.application.research_organization.create_collection import (
        CreateCollection,
        CreateCollectionCommand,
    )
    from chem_vault.application.research_organization.get_collection import (
        ListCollections,
        ListCollectionsQuery,
    )
    from chem_vault.application.shared.molecule_resolver import MoleculeReference

    data: dict = ctx.data("collections.json")
    create_uc = ctx.container[CreateCollection]
    add_members_uc = ctx.container[AddMoleculesToCollection]
    created = 0

    for key, rec in data.items():
        cmd = CreateCollectionCommand(
            workspace_id=WORKSPACE_ID,
            name=rec["name"],
            description=rec.get("description"),
            project_id=ctx.registry.get_optional(rec.get("project_ref")),
            created_by=USER_ID,
            visibility=rec.get("visibility", "private"),
        )
        entity = await try_create(create_uc(cmd, auth=ctx.auth), "Collection", key)
        if entity is not None:
            ctx.registry.put(key, entity.id)
            created += 1
            logger.info("collection.created", key=key, name=rec["name"])
        else:
            logger.debug("collection.exists", key=key, name=rec["name"])

    # Back-fill registry for any that already existed (conflict path)
    if created < len(data):
        list_uc = ctx.container[ListCollections]
        query = ListCollectionsQuery(workspace_id=WORKSPACE_ID)
        all_result = await list_uc(query)
        all_collections = all_result.unwrap()
        name_to_id = {c.name: c.id for c in all_collections}
        for key, rec in data.items():
            if not ctx.registry.has(key):
                coll_id = name_to_id.get(rec["name"])
                if coll_id is not None:
                    ctx.registry.put(key, coll_id)

    # Add molecule membership to each collection
    for key, rec in data.items():
        molecule_refs_raw = rec.get("molecule_refs", [])
        if not molecule_refs_raw:
            continue

        collection_id = ctx.registry.get(key)
        refs = []
        for mol_ref in molecule_refs_raw:
            mol_id = ctx.registry.get_optional(mol_ref)
            if mol_id is not None:
                refs.append(MoleculeReference(ref_type="uuid", value=str(mol_id)))
            else:
                logger.warning(
                    "collection.molecule_ref_missing",
                    key=key,
                    molecule_ref=mol_ref,
                )

        if not refs:
            continue

        try:
            add_cmd = AddMoleculesToCollectionCommand(
                workspace_id=WORKSPACE_ID,
                collection_id=collection_id,
                refs=refs,
                added_by=USER_ID,
            )
            membership_result = await add_members_uc(add_cmd, auth=ctx.auth)
            outcome = membership_result.unwrap()
            logger.info(
                "collection.members_added",
                key=key,
                added=len(outcome.added),
                already_present=outcome.already_present,
            )
        except Exception:
            logger.warning(
                "collection.membership_failed",
                key=key,
                exc_info=True,
            )

    return created
