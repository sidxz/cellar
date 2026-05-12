"""Step 18 — Load sample requests and advance through lifecycle transitions."""

from __future__ import annotations

import structlog

from ._context import USER_ID, WORKSPACE_ID, DemoContext
from ._result import unwrap_or_skip

logger = structlog.get_logger()


async def load(ctx: DemoContext) -> int:
    from cellar.application.inventory.get_batch import (
        ListBatchesByMolecule,
        ListBatchesByMoleculeQuery,
    )
    from cellar.application.inventory.get_sample import (
        ListSamplesByBatch,
        ListSamplesByBatchQuery,
    )
    from cellar.application.inventory.sample_requests import (
        ApproveSampleRequest,
        ApproveSampleRequestCommand,
        CreateSampleRequest,
        CreateSampleRequestCommand,
        FulfillSampleRequest,
        FulfillSampleRequestCommand,
        StartPreparingSampleRequest,
        StartPreparingSampleRequestCommand,
    )

    data: dict = ctx.data("sample_requests.json")
    create_uc = ctx.container[CreateSampleRequest]
    approve_uc = ctx.container[ApproveSampleRequest]
    prepare_uc = ctx.container[StartPreparingSampleRequest]
    fulfill_uc = ctx.container[FulfillSampleRequest]
    list_batches_uc = ctx.container[ListBatchesByMolecule]
    list_samples_uc = ctx.container[ListSamplesByBatch]
    created = 0

    for key, rec in data.items():
        molecule_id = ctx.registry.get(rec["molecule_ref"])
        cmd = CreateSampleRequestCommand(
            workspace_id=WORKSPACE_ID,
            requester_id=USER_ID,
            molecule_id=molecule_id,
            amount_value=rec["amount_value"],
            amount_unit=rec["amount_unit"],
            purpose=rec["purpose"],
            priority=rec.get("priority", "routine"),
        )
        result = await create_uc(cmd, auth=ctx.auth)
        entity = unwrap_or_skip(result, "SampleRequest", key)
        if entity is None:
            logger.debug("sample_request.exists", key=key)
            continue

        request_id = entity.id
        ctx.registry.put(key, request_id)
        created += 1
        logger.info("sample_request.created", key=key, purpose=rec["purpose"])

        transitions = rec.get("transitions", [])

        for transition in transitions:
            try:
                if transition == "approve":
                    await approve_uc(
                        ApproveSampleRequestCommand(
                            workspace_id=WORKSPACE_ID,
                            request_id=request_id,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "prepare":
                    await prepare_uc(
                        StartPreparingSampleRequestCommand(
                            workspace_id=WORKSPACE_ID,
                            request_id=request_id,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "fulfill":
                    # Find a sample via molecule -> first batch -> first sample
                    sample_id = await _find_sample_for_molecule(
                        molecule_id, list_batches_uc, list_samples_uc, ctx.auth
                    )
                    if sample_id is not None:
                        await fulfill_uc(
                            FulfillSampleRequestCommand(
                                workspace_id=WORKSPACE_ID,
                                request_id=request_id,
                                sample_id=sample_id,
                            ),
                            auth=ctx.auth,
                        )
                    else:
                        logger.warning(
                            "sample_request.fulfill_skipped",
                            key=key,
                            reason="no sample found for molecule",
                        )
                logger.debug("sample_request.transition", key=key, transition=transition)
            except Exception:
                logger.warning(
                    "sample_request.transition_failed",
                    key=key,
                    transition=transition,
                    exc_info=True,
                )

    return created


async def _find_sample_for_molecule(
    molecule_id, list_batches_uc, list_samples_uc, auth
):
    """Walk molecule -> first batch -> first sample to find a fulfillment sample."""
    from cellar.application.inventory.get_batch import ListBatchesByMoleculeQuery
    from cellar.application.inventory.get_sample import ListSamplesByBatchQuery

    batches_result = await list_batches_uc(
        ListBatchesByMoleculeQuery(
            workspace_id=WORKSPACE_ID,
            molecule_id=molecule_id,
        ),
        auth=auth,
    )
    batches = batches_result.unwrap()
    for batch in batches:
        samples_result = await list_samples_uc(
            ListSamplesByBatchQuery(
                workspace_id=WORKSPACE_ID,
                batch_id=batch.id,
            ),
            auth=auth,
        )
        samples = samples_result.unwrap()
        if samples:
            return samples[0].id
    return None
