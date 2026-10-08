"""What an admin naming edit would do to protocol names, computed before it is saved.

Pattern edits, short labels and the home organism all relabel protocols. Each edit is planned
the same way for its preview and for its save, so what the admin approved is what is applied.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_admin, require_same_workspace
from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.application.shared.query import Query
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import ConflictError, DomainError, NotFoundError, ValidationError
from cellar.domain.shared.protocol_naming import NamingContext, validate_pattern
from cellar.domain.workspace_config.naming_label import clean_short_label
from cellar.domain.workspace_config.repository import ProtocolCategoryRepository


@dataclass(frozen=True)
class NameChange:
    protocol_id: uuid.UUID
    code: str | None
    before: str
    after: str


@dataclass(frozen=True)
class NameCollision:
    name: str
    codes: list[str]


@dataclass(frozen=True)
class NamingChangePreview:
    changes: list[NameChange]
    collisions: list[NameCollision]


@dataclass(frozen=True)
class NamingPlan:
    """Which protocols an edit touches and how they render under it."""

    protocols: list[Protocol]
    pattern_for: Callable[[Protocol], str | None]
    ctx: NamingContext


def _key(p: Protocol) -> str:
    return p.code or str(p.id)


async def plan_category(
    *,
    workspace_id: uuid.UUID,
    protocol_repo: ProtocolRepository,
    names: ProtocolNameService,
    label: str,
    pattern: str,
) -> NamingPlan:
    validate_pattern(pattern)
    everyone = await protocol_repo.find_by_workspace(workspace_id)
    key = label.strip().lower()
    return NamingPlan(
        protocols=[p for p in everyone if (p.category or "").strip().lower() == key],
        pattern_for=lambda _p: pattern,
        ctx=await names.context(workspace_id),
    )


async def plan_label(
    *,
    workspace_id: uuid.UUID,
    protocol_repo: ProtocolRepository,
    names: ProtocolNameService,
    term_id: str,
    term_label: str,
    short_label: str | None,
) -> NamingPlan:
    """``short_label=None`` puts the term back on its computed default."""
    ctx = await names.context(workspace_id)
    by_term, by_label = dict(ctx.overrides_by_term), dict(ctx.overrides_by_label)
    by_term.pop(term_id, None)
    by_label.pop(term_label.lower(), None)
    if short_label is not None:
        cleaned = clean_short_label(short_label)
        by_term[term_id] = cleaned
        by_label[term_label.lower()] = cleaned
    return NamingPlan(
        protocols=await protocol_repo.find_by_workspace(workspace_id),
        pattern_for=lambda _p: None,
        ctx=dataclasses.replace(ctx, overrides_by_term=by_term, overrides_by_label=by_label),
    )


async def plan_home_organism(
    *,
    workspace_id: uuid.UUID,
    protocol_repo: ProtocolRepository,
    names: ProtocolNameService,
    term: dict[str, Any] | None,
) -> NamingPlan:
    ctx = await names.context(workspace_id)
    return NamingPlan(
        protocols=await protocol_repo.find_by_workspace(workspace_id),
        pattern_for=lambda _p: None,
        ctx=dataclasses.replace(ctx, home_organism_label=term["label"] if term else None),
    )


async def compute_naming_change(
    *,
    workspace_id: uuid.UUID,
    protocol_repo: ProtocolRepository,
    names: ProtocolNameService,
    plan: NamingPlan,
) -> NamingChangePreview:
    """Re-render the plan's protocols and check every resulting name against every other
    protocol's current name. Versions share a code, so they count once."""
    # ponytail: one derive per affected protocol (2 queries each); fine for hundreds of
    # protocols, batch the target lookups if workspaces reach thousands.
    changes: list[NameChange] = []
    after_by_code: dict[str, str] = {}
    renamed_codes: set[str] = set()
    for p in sorted(plan.protocols, key=lambda q: q.protocol_version):
        d = await names.derive(
            workspace_id,
            category=p.category,
            target_ids=await protocol_repo.find_direct_target_ids(workspace_id, p.id),
            annotations=p.ontology_annotations,
            discriminator=p.discriminator,
            exclude_code=p.code,
            pattern=plan.pattern_for(p),
            ctx=plan.ctx,
            check_siblings=False,
        )
        after = d.rendered.name if d.rendered.complete else p.name
        if after != p.name:
            changes.append(NameChange(p.id, p.code, p.name, after))
            renamed_codes.add(_key(p))
        after_by_code[_key(p)] = after
    everyone = {
        _key(q): q.name
        for q in sorted(
            await protocol_repo.find_by_workspace(workspace_id), key=lambda q: q.protocol_version
        )
    }
    everyone.update(after_by_code)
    by_name: dict[str, list[str]] = {}
    for code, name in everyone.items():
        by_name.setdefault(name.lower(), []).append(code)
    # Only names this edit produces can collide; clashes that already exist are not its doing.
    collisions = [
        NameCollision(name=everyone[codes[0]], codes=sorted(codes))
        for codes in by_name.values()
        if len(codes) > 1 and renamed_codes.intersection(codes)
    ]
    return NamingChangePreview(changes=changes, collisions=collisions)


def refuse_collisions(preview: NamingChangePreview) -> Result[None, DomainError]:
    if preview.collisions:
        c = preview.collisions[0]
        return Failure(
            ConflictError(
                f"This would give {', '.join(c.codes)} the same name '{c.name}'. "
                "Change a discriminator first."
            )
        )
    return Success(None)


async def apply_naming_change(
    *,
    protocol_repo: ProtocolRepository,
    names: ProtocolNameService,
    plan: NamingPlan,
    preview: NamingChangePreview,
    reason: str,
    user_id: uuid.UUID | None,
    also_save: list[Protocol] | None = None,
) -> None:
    """Rename what the preview said would change (system relabel: flags, never refuses).
    ``also_save``: protocols the caller changed otherwise (a renamed category); each protocol
    is saved once."""
    by_id = {p.id: p for p in plan.protocols}
    touched = {p.id: p for p in also_save or []}
    for change in preview.changes:
        protocol = by_id[change.protocol_id]
        await names.apply(
            protocol,
            reason=reason,
            person=False,
            allow_incomplete=True,
            user_id=user_id,
            pattern=plan.pattern_for(protocol),
            ctx=plan.ctx,
        )
        touched[protocol.id] = protocol
    for protocol in touched.values():
        await protocol_repo.save(protocol)


@dataclass(frozen=True, kw_only=True)
class PreviewNamingChangeQuery(Query):
    """One admin edit: ``kind`` is category, label or home_organism."""

    workspace_id: uuid.UUID
    kind: str
    category_id: uuid.UUID | None = None
    name_pattern: str | None = None
    label: str | None = None
    term_id: str | None = None
    term_label: str | None = None
    short_label: str | None = None
    home_organism: dict[str, Any] | None = None


class PreviewNamingChange:
    def __init__(
        self,
        uow: UnitOfWork,
        protocol_repo: ProtocolRepository,
        category_repo: ProtocolCategoryRepository,
        names: ProtocolNameService,
    ) -> None:
        self._uow = uow
        self._protocols = protocol_repo
        self._categories = category_repo
        self._names = names

    async def __call__(
        self, input: PreviewNamingChangeQuery, auth: AuthContext | None = None
    ) -> Result[NamingChangePreview, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        ws = input.workspace_id
        async with self._uow:
            if input.kind == "category":
                if input.category_id is None:
                    return Failure(ValidationError("A category change needs category_id"))
                category = await self._categories.find_by_id_in_workspace(ws, input.category_id)
                if category is None:
                    return Failure(NotFoundError("ProtocolCategory", str(input.category_id)))
                if input.label:
                    other = await self._categories.find_by_label(ws, input.label)
                    if other is not None and other.id != category.id:
                        return Failure(
                            ConflictError(f"Category '{input.label.strip()}' already exists")
                        )
                plan = await plan_category(
                    workspace_id=ws,
                    protocol_repo=self._protocols,
                    names=self._names,
                    label=category.label,
                    pattern=input.name_pattern or category.name_pattern,
                )
            elif input.kind == "label":
                if not input.term_id or not input.term_label:
                    return Failure(ValidationError("A short label change needs the term"))
                plan = await plan_label(
                    workspace_id=ws,
                    protocol_repo=self._protocols,
                    names=self._names,
                    term_id=input.term_id,
                    term_label=input.term_label,
                    short_label=input.short_label,
                )
            elif input.kind == "home_organism":
                plan = await plan_home_organism(
                    workspace_id=ws,
                    protocol_repo=self._protocols,
                    names=self._names,
                    term=input.home_organism,
                )
            else:
                return Failure(ValidationError(f"Unknown naming change '{input.kind}'"))
            return Success(
                await compute_naming_change(
                    workspace_id=ws, protocol_repo=self._protocols, names=self._names, plan=plan
                )
            )
