"""CrossProtocolResolver — resolves @ProtocolName.ReadoutName references in formulas.

Cross-protocol formula references use the syntax:
  - ``@ProtocolName.ReadoutName``         (simple names, no spaces)
  - ``@{Protocol Name}.{Readout Name}``   (braces for names with spaces)

Resolution is performed at query time, looking up the most recent active
protocol with the given name and fetching the readout data for the target
molecule.

Binding keys use double-underscore to stay safe for asteval:
  ``{protocol_name}__{readout_name}``
"""

from __future__ import annotations

import re
import uuid

from returns.result import Failure, Result, Success

from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.enums import ProtocolStatus
from cellar.domain.screening_assay.repository import (
    ProtocolRepository,
    ReadoutDataRepository,
)
from cellar.domain.shared.errors import DomainError, NotFoundError, ValidationError

# Matches both forms:
#   @ProtocolName.ReadoutName
#   @{Protocol Name}.{Readout Name}
# Groups: (braced_protocol, bare_protocol, braced_readout, bare_readout)
_REF_RE = re.compile(r"@(?:\{([^}]+)\}|(\w+))\.(?:\{([^}]+)\}|(\w+))")


class CrossProtocolResolver:
    """Resolves ``@Protocol.Readout`` references in formulas to numeric bindings.

    Used by the on-read calculation path to evaluate cross-protocol formulas
    that cannot be resolved at import time (``ReadoutCalculationEngine`` skips
    these intentionally).
    """

    def __init__(
        self,
        *,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        readout_data_repo: ReadoutDataRepository,
    ) -> None:
        self._uow = uow
        self._protocol_repo = protocol_repo
        self._readout_data_repo = readout_data_repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def resolve(
        self,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        formula: str,
    ) -> Result[dict[str, float], DomainError]:
        """Resolve all ``@`` references in *formula* to numeric bindings.

        Args:
            workspace_id: The workspace to search protocols in.
            molecule_id: The molecule whose readout data is fetched.
            formula: The formula string that may contain ``@`` references.

        Returns:
            ``Success(bindings)`` — mapping of ``protocol__readout`` keys to
            float values, ready to merge with intra-protocol bindings before
            formula evaluation.
            ``Failure(DomainError)`` — if any referenced protocol, readout
            definition, or readout data point cannot be found.
        """
        refs = self._extract_refs(formula)
        if not refs:
            return Success({})

        async with self._uow:
            return await self._resolve_refs(workspace_id, molecule_id, refs)

    async def _resolve_refs(
        self,
        workspace_id: uuid.UUID,
        molecule_id: uuid.UUID,
        refs: list[tuple[str, str]],
    ) -> Result[dict[str, float], DomainError]:
        bindings: dict[str, float] = {}

        for protocol_name, readout_name in refs:
            # Look up the active protocol by name
            protocol = await self._protocol_repo.find_by_name(workspace_id, protocol_name)
            if protocol is None or protocol.status != ProtocolStatus.ACTIVE:
                return Failure(
                    NotFoundError(
                        "Protocol",
                        protocol_name,
                        detail=(
                            f"No active protocol named '{protocol_name}' found "
                            f"in workspace {workspace_id}"
                        ),
                    )
                )

            # Find the readout definition by name
            rd = next(
                (r for r in protocol.readout_definitions if r.name == readout_name),
                None,
            )
            if rd is None:
                return Failure(
                    NotFoundError(
                        "ReadoutDefinition",
                        readout_name,
                        detail=(
                            f"Protocol '{protocol_name}' has no readout definition "
                            f"named '{readout_name}'"
                        ),
                    )
                )

            # Fetch readout data for this molecule + definition
            data_points = await self._readout_data_repo.find_by_molecule_and_definition(
                workspace_id, molecule_id, rd.id
            )
            if not data_points:
                return Failure(
                    ValidationError(
                        f"No data for molecule {molecule_id} in readout "
                        f"'{protocol_name}.{readout_name}'"
                    )
                )

            # Use the first data point; skip if value is absent
            point = data_points[0]
            if point.value is None:
                return Failure(
                    ValidationError(
                        f"No numeric value for molecule {molecule_id} in readout "
                        f"'{protocol_name}.{readout_name}'"
                    )
                )

            binding_key = f"{protocol_name}__{readout_name}"
            bindings[binding_key] = point.value.value

        return Success(bindings)

    def rewrite_formula(self, formula: str) -> str:
        """Replace ``@Protocol.Readout`` tokens with ``Protocol__Readout`` identifiers.

        This produces a formula string that is safe for asteval, where the
        bindings dict uses double-underscore keys.

        Example:
            ``@TargetAssay.IC50 * 2``  →  ``TargetAssay__IC50 * 2``
        """

        def _substitute(match: re.Match) -> str:
            protocol_name = match.group(1) or match.group(2)
            readout_name = match.group(3) or match.group(4)
            return f"{protocol_name}__{readout_name}"

        return _REF_RE.sub(_substitute, formula)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_refs(self, formula: str) -> list[tuple[str, str]]:
        """Return a deduplicated list of (protocol_name, readout_name) pairs."""
        seen: set[tuple[str, str]] = set()
        refs: list[tuple[str, str]] = []

        for match in _REF_RE.finditer(formula):
            protocol_name = match.group(1) or match.group(2)
            readout_name = match.group(3) or match.group(4)
            key = (protocol_name, readout_name)
            if key not in seen:
                seen.add(key)
                refs.append(key)

        return refs
