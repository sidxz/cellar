"""WorkspaceSettings aggregate — domain configuration per workspace.

Identity: id == workspace_id (singleton per workspace).
Duar owns workspace identity; Cellar stores domain-specific config only.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.workspace_config.events import WorkspaceSettingsUpdated

_PREFIX_PATTERN = re.compile(r"^[A-Z]{2,8}-$")
_DEFAULT_PREFIX = "CC-"
_DEFAULT_WIDTH = 6
_WIDTH_MIN = 4
_WIDTH_MAX = 8
_DEFAULT_BATCH_WIDTH = 3
_BATCH_WIDTH_MIN = 2
_BATCH_WIDTH_MAX = 6


class WorkspaceSettings(AggregateRoot):
    """Workspace-level domain configuration.

    The ``id`` field IS the workspace_id — there is exactly one WorkspaceSettings
    per workspace.
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        registration_rules: dict[str, Any] | None = None,
        custom_field_definitions: list[dict[str, Any]] | None = None,
        default_molecule_type: str | None = None,
        audit_reason_policy: str | None = None,
        signature_required_for: list[str] | None = None,
        audit_retention_days: int | None = None,
        formulation_number_scheme: str | None = None,
        cdd_vault_id: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.registration_rules = registration_rules or {}
        self.custom_field_definitions = (
            custom_field_definitions if isinstance(custom_field_definitions, list) else []
        )
        self.default_molecule_type = default_molecule_type
        self.audit_reason_policy = (
            audit_reason_policy if isinstance(audit_reason_policy, str) else None
        )
        self.signature_required_for = signature_required_for or []
        self.audit_retention_days = audit_retention_days
        self.formulation_number_scheme = (
            formulation_number_scheme if isinstance(formulation_number_scheme, str) else None
        )
        self.cdd_vault_id = cdd_vault_id

    @property
    def workspace_id(self) -> uuid.UUID:
        """Alias — the id IS the workspace_id."""
        return self.id

    @property
    def create_batch_on_duplicate(self) -> bool:
        """Whether re-registering an existing compound also creates a new batch.

        Default ``False`` — re-registration merges identifiers but does not
        create a new batch unless the caller explicitly opts in.
        """
        return bool(self.registration_rules.get("create_batch_on_duplicate", False))

    @property
    def registration_number_prefix(self) -> str:
        """Per-workspace prefix for newly-generated molecule reg numbers.

        Defaults to ``CC-`` when unset or empty. Pattern: ``^[A-Z]{2,8}-$``.
        """
        raw = self.registration_rules.get("registration_number_prefix")
        if isinstance(raw, str) and raw:
            return raw
        return _DEFAULT_PREFIX

    @property
    def registration_number_width(self) -> int:
        """Zero-pad width for the numeric tail of newly-generated reg numbers.

        Defaults to 6 (CC-000001 .. CC-999999). Bounded ``[4, 8]``.
        """
        raw = self.registration_rules.get("registration_number_width")
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        return _DEFAULT_WIDTH

    @property
    def batch_sequence_width(self) -> int:
        """Zero-pad width for the per-compound batch sequence.

        Defaults to 3 (``{reg}-001`` .. ``{reg}-999``). Bounded ``[2, 6]``.
        """
        raw = self.registration_rules.get("batch_sequence_width")
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        return _DEFAULT_BATCH_WIDTH

    @classmethod
    def create_default(cls, *, workspace_id: uuid.UUID) -> WorkspaceSettings:
        """Factory for a new workspace with all default settings."""
        return cls(id=workspace_id)

    def update(self, **fields: object) -> None:
        """Partial update — only keys present in ``fields`` are changed.

        Accepted keys: registration_rules, custom_field_definitions,
        default_molecule_type, audit_reason_policy, signature_required_for,
        audit_retention_days, formulation_number_scheme.
        """
        # Validate registration-number config if present in the new rules
        if "registration_rules" in fields:
            rules = fields["registration_rules"]
            if isinstance(rules, dict):
                if "registration_number_prefix" in rules:
                    pfx = rules["registration_number_prefix"]
                    if not isinstance(pfx, str) or not _PREFIX_PATTERN.match(pfx):
                        raise ValueError(
                            f"registration_number_prefix must match ^[A-Z]{{2,8}}-$ (got: {pfx!r})"
                        )
                if "registration_number_width" in rules:
                    w = rules["registration_number_width"]
                    if not isinstance(w, int) or isinstance(w, bool):
                        raise ValueError(
                            f"registration_number_width must be int (got: {type(w).__name__})"
                        )
                    if not (_WIDTH_MIN <= w <= _WIDTH_MAX):
                        raise ValueError(
                            f"registration_number_width must be in [{_WIDTH_MIN}, {_WIDTH_MAX}] "
                            f"(got: {w})"
                        )
                if "batch_sequence_width" in rules:
                    bw = rules["batch_sequence_width"]
                    if not isinstance(bw, int) or isinstance(bw, bool):
                        raise ValueError(
                            f"batch_sequence_width must be int (got: {type(bw).__name__})"
                        )
                    if not (_BATCH_WIDTH_MIN <= bw <= _BATCH_WIDTH_MAX):
                        raise ValueError(
                            f"batch_sequence_width must be in "
                            f"[{_BATCH_WIDTH_MIN}, {_BATCH_WIDTH_MAX}] (got: {bw})"
                        )

        for key in (
            "registration_rules",
            "custom_field_definitions",
            "default_molecule_type",
            "audit_reason_policy",
            "signature_required_for",
            "audit_retention_days",
            "formulation_number_scheme",
            "cdd_vault_id",
        ):
            if key in fields:
                setattr(self, key, fields[key])
        self.updated_at = datetime.now(UTC)
        self.register_event(
            WorkspaceSettingsUpdated(
                aggregate_id=self.id,
                aggregate_type="WorkspaceSettings",
                workspace_id=self.workspace_id,
            )
        )
