"""Step 17 — Load synthesis requests and advance through lifecycle transitions."""

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
    from cellar.application.inventory.synthesis_requests import (
        ApproveSynthesisRequest,
        ApproveSynthesisRequestCommand,
        AssignSynthesisRequest,
        AssignSynthesisRequestCommand,
        CompleteSynthesis,
        CompleteSynthesisCommand,
        CreateSynthesisRequest,
        CreateSynthesisRequestCommand,
        FulfillSynthesisRequest,
        FulfillSynthesisRequestCommand,
        RejectSynthesisRequest,
        RejectSynthesisRequestCommand,
        StartSynthesis,
        StartSynthesisCommand,
        SubmitSynthesisRequest,
        SubmitSynthesisRequestCommand,
    )

    data: dict = ctx.data("synthesis_requests.json")
    create_uc = ctx.container[CreateSynthesisRequest]
    submit_uc = ctx.container[SubmitSynthesisRequest]
    approve_uc = ctx.container[ApproveSynthesisRequest]
    reject_uc = ctx.container[RejectSynthesisRequest]
    assign_uc = ctx.container[AssignSynthesisRequest]
    start_uc = ctx.container[StartSynthesis]
    complete_uc = ctx.container[CompleteSynthesis]
    fulfill_uc = ctx.container[FulfillSynthesisRequest]
    list_batches_uc = ctx.container[ListBatchesByMolecule]
    created = 0

    for key, rec in data.items():
        molecule_id = ctx.registry.get(rec["molecule_ref"])
        cmd = CreateSynthesisRequestCommand(
            workspace_id=WORKSPACE_ID,
            requester_id=USER_ID,
            molecule_id=molecule_id,
            amount_value=rec["amount_value"],
            amount_unit=rec["amount_unit"],
            purpose=rec["purpose"],
            priority=rec.get("priority", "routine"),
            target_purity=rec.get("target_purity"),
            project_id=ctx.registry.get_optional(rec.get("project_ref")),
        )
        result = await create_uc(cmd, auth=ctx.auth)
        entity = unwrap_or_skip(result, "SynthesisRequest", key)
        if entity is None:
            logger.debug("synthesis_request.exists", key=key)
            continue

        request_id = entity.id
        ctx.registry.put(key, request_id)
        created += 1
        logger.info("synthesis_request.created", key=key, purpose=rec["purpose"])

        transitions = rec.get("transitions", [])

        # Walk through the requested lifecycle transitions in order
        for transition in transitions:
            try:
                if transition == "submit":
                    await submit_uc(
                        SubmitSynthesisRequestCommand(
                            workspace_id=WORKSPACE_ID,
                            request_id=request_id,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "approve":
                    await approve_uc(
                        ApproveSynthesisRequestCommand(
                            workspace_id=WORKSPACE_ID,
                            request_id=request_id,
                            approved_by=USER_ID,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "reject":
                    await reject_uc(
                        RejectSynthesisRequestCommand(
                            workspace_id=WORKSPACE_ID,
                            request_id=request_id,
                            reason=rec.get("reject_reason", "Rejected"),
                            rejected_by=USER_ID,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "assign":
                    await assign_uc(
                        AssignSynthesisRequestCommand(
                            workspace_id=WORKSPACE_ID,
                            request_id=request_id,
                            assignment_type=rec.get("assign_type", "INTERNAL"),
                            assigned_to=USER_ID,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "start":
                    await start_uc(
                        StartSynthesisCommand(
                            workspace_id=WORKSPACE_ID,
                            request_id=request_id,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "complete":
                    await complete_uc(
                        CompleteSynthesisCommand(
                            workspace_id=WORKSPACE_ID,
                            request_id=request_id,
                        ),
                        auth=ctx.auth,
                    )
                elif transition == "fulfill":
                    # Find first batch for the molecule to use as fulfillment
                    batches_result = await list_batches_uc(
                        ListBatchesByMoleculeQuery(
                            workspace_id=WORKSPACE_ID,
                            molecule_id=molecule_id,
                        ),
                        auth=ctx.auth,
                    )
                    batches = batches_result.unwrap()
                    if batches:
                        await fulfill_uc(
                            FulfillSynthesisRequestCommand(
                                workspace_id=WORKSPACE_ID,
                                request_id=request_id,
                                batch_id=batches[0].id,
                            ),
                            auth=ctx.auth,
                        )
                    else:
                        logger.warning(
                            "synthesis_request.fulfill_skipped",
                            key=key,
                            reason="no batches found for molecule",
                        )
                logger.debug("synthesis_request.transition", key=key, transition=transition)
            except Exception:
                logger.warning(
                    "synthesis_request.transition_failed",
                    key=key,
                    transition=transition,
                    exc_info=True,
                )

    return created
