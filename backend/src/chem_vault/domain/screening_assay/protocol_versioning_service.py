"""Protocol versioning domain service."""

from __future__ import annotations

import copy
import uuid

from chem_vault.domain.screening_assay.enums import ProtocolStatus
from chem_vault.domain.screening_assay.events import ProtocolVersionCreated
from chem_vault.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
)
from chem_vault.domain.shared.errors import ConflictError


class ProtocolVersioningService:
    """Creates a new version of an existing protocol.

    Guards:
        - Parent must be ACTIVE (only active protocols can be versioned).

    Side effects:
        - Parent protocol is retired.
        - New protocol is created in DRAFT status with cloned definitions.
    """

    def create_new_version(self, parent: Protocol) -> Protocol:
        """Create a new version from an active protocol.

        Args:
            parent: The active protocol to version.

        Returns:
            A new DRAFT protocol with incremented version and cloned definitions.

        Raises:
            ConflictError: If parent is not in ACTIVE status.
        """
        if parent.status != ProtocolStatus.ACTIVE:
            raise ConflictError(
                f"Cannot version protocol in '{parent.status}' status — "
                "only ACTIVE protocols can be versioned"
            )

        new_protocol_id = uuid.uuid4()

        # Clone readout definitions with new IDs
        cloned_readouts = [
            ReadoutDefinition(
                protocol_id=new_protocol_id,
                name=rd.name,
                data_type=rd.data_type,
                unit=rd.unit,
                aggregation=rd.aggregation,
                precision=rd.precision,
                normalization=rd.normalization,
                is_calculated=rd.is_calculated,
                calculation_formula=rd.calculation_formula,
                display_order=rd.display_order,
                pick_list_values=list(rd.pick_list_values) if rd.pick_list_values else None,
                dose_response_config=rd.dose_response_config,  # frozen dataclass — safe to share
            )
            for rd in parent.readout_definitions
        ]

        # Clone condition definitions with new IDs
        cloned_conditions = [
            ConditionDefinition(
                protocol_id=new_protocol_id,
                name=cd.name,
                data_type=cd.data_type,
                unit=cd.unit,
                pick_list_values=list(cd.pick_list_values) if cd.pick_list_values else None,
            )
            for cd in parent.condition_definitions
        ]

        # Create new version in DRAFT (before retiring parent to avoid partial mutation)
        new_protocol = Protocol(
            id=new_protocol_id,
            workspace_id=parent.workspace_id,
            name=parent.name,
            description=parent.description,
            protocol_type=parent.protocol_type,
            target_id=parent.target_id,
            category=parent.category,
            protocol_version=parent.protocol_version + 1,
            parent_protocol_id=parent.id,
            status=ProtocolStatus.DRAFT,
            created_by=parent.created_by,
            dose_unit=parent.dose_unit,
            readout_definitions=cloned_readouts,
            condition_definitions=cloned_conditions,
            control_layouts=dict(parent.control_layouts) if parent.control_layouts else None,
            ontology_annotations=copy.deepcopy(parent.ontology_annotations) if parent.ontology_annotations else None,
        )
        # NOTE: Parent is NOT retired here. It stays ACTIVE until the new
        # version is published. PublishProtocol use case retires the parent.

        new_protocol.register_event(
            ProtocolVersionCreated(
                aggregate_id=new_protocol.id,
                aggregate_type="Protocol",
                workspace_id=parent.workspace_id,
                parent_protocol_id=parent.id,
                version=new_protocol.protocol_version,
            )
        )
        return new_protocol
