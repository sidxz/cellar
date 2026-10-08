"""One place that turns a protocol's facts into its generated name.

Every path that changes an input (create, edit, correction, registry sync, admin pattern or
label edits) derives here, so a protocol's name always reads the same way.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.domain.research_organization.enums import CollectionType
from cellar.domain.research_organization.repository import CollectionRepository
from cellar.domain.screening_assay.enums import NameFlag
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import (
    NameSibling,
    ProtocolRepository,
    TargetRepository,
)
from cellar.domain.shared.errors import ConflictError, DomainError, ValidationError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.shared.protocol_naming import (
    MAX_NAME_LENGTH,
    NamingContext,
    NamingInputs,
    NamingTarget,
    NamingTerm,
    RenderedName,
    clean_discriminator,
    render_protocol_name,
)
from cellar.domain.workspace_config.repository import (
    NamingLabelRepository,
    ProtocolCategoryRepository,
    WorkspaceSettingsRepository,
)

MISSING_FIELD_LABELS = {
    "category": "a category",
    "target": "a target",
    "organism": "an organism",
    "cell_line": "a cell line",
    "matrix": "an assay format",
    "subject": "a target, organism or cell line",
    "discriminator": "a discriminator",
}


@dataclass(frozen=True)
class NameDerivation:
    rendered: RenderedName
    clash: NameSibling | None
    siblings: tuple[NameSibling, ...]
    bare_siblings: tuple[NameSibling, ...]
    needs_discriminator: bool


def _terms(terms: Sequence[OntologyTerm] | None) -> tuple[NamingTerm, ...]:
    return tuple(NamingTerm(t.term_id, t.label, t.ontology_source) for t in terms or ())


class ProtocolNameService:
    def __init__(
        self,
        *,
        protocol_repo: ProtocolRepository,
        target_repo: TargetRepository,
        category_repo: ProtocolCategoryRepository,
        label_repo: NamingLabelRepository,
        settings_repo: WorkspaceSettingsRepository,
        collection_repo: CollectionRepository,
    ) -> None:
        self._protocols = protocol_repo
        self._targets = target_repo
        self._categories = category_repo
        self._labels = label_repo
        self._settings = settings_repo
        self._collections = collection_repo

    async def context(self, workspace_id: uuid.UUID) -> NamingContext:
        labels = await self._labels.find_by_workspace(workspace_id)
        settings = await self._settings.find_by_workspace_id(workspace_id)
        return NamingContext(
            overrides_by_term={lb.term_id: lb.short_label for lb in labels},
            overrides_by_label={lb.term_label.lower(): lb.short_label for lb in labels},
            home_organism_label=settings.home_organism_label if settings else None,
        )

    async def target_name(self, workspace_id: uuid.UUID, target_id: uuid.UUID) -> str:
        """For audit reasons ("Target added: PptT"); falls back to the id."""
        found = await self._targets.find_by_ids(workspace_id, [target_id])
        return found[0].name if found else str(target_id)

    async def clean_discriminator(self, workspace_id: uuid.UUID, value: str | None) -> str | None:
        libraries = [
            c.name
            for c in await self._collections.find_by_workspace(workspace_id)
            if c.type == CollectionType.LIBRARY
        ]
        return clean_discriminator(value, library_names=libraries)

    async def derive(
        self,
        workspace_id: uuid.UUID,
        *,
        category: str | None,
        target_ids: Sequence[uuid.UUID],
        annotations: Mapping[str, Sequence[OntologyTerm]],
        discriminator: str | None,
        exclude_code: str | None = None,
        pattern: str | None = None,
        ctx: NamingContext | None = None,
        check_siblings: bool = True,
    ) -> NameDerivation:
        """``pattern``/``ctx`` override the saved category pattern and labels, so an admin edit
        can be rendered before it is saved; ``check_siblings=False`` skips collision lookups."""
        if pattern is None:
            found = (
                await self._categories.find_by_label(workspace_id, category) if category else None
            )
            pattern = found.name_pattern if found else None
        if pattern is None:
            label = "(category needed)" + (f" [{discriminator}]" if discriminator else "")
            rendered = RenderedName(
                name=label,
                base="(category needed)",
                missing=("category",),
                discriminator_in_pattern=False,
            )
            return NameDerivation(rendered, None, (), (), False)
        targets = sorted(
            await self._targets.find_by_ids(workspace_id, list(target_ids)),
            key=lambda t: t.name.lower(),
        )
        inputs = NamingInputs(
            targets=tuple(NamingTarget(t.name, t.organism) for t in targets),
            organisms=_terms(annotations.get("organism")),
            cell_lines=_terms(annotations.get("cell_line")),
            matrices=_terms(annotations.get("assay_format")),
            discriminator=discriminator,
        )
        rendered = render_protocol_name(pattern, inputs, ctx or await self.context(workspace_id))
        if not rendered.complete or not check_siblings:
            return NameDerivation(rendered, None, (), (), False)
        siblings = tuple(
            await self._protocols.find_name_siblings(
                workspace_id, base=rendered.base, exclude_code=exclude_code
            )
        )
        clash = next((s for s in siblings if s.name.lower() == rendered.name.lower()), None)
        if rendered.discriminator_in_pattern:
            return NameDerivation(rendered, clash, siblings, (), False)
        bare = tuple(s for s in siblings if not s.discriminator and s is not clash)
        return NameDerivation(
            rendered, clash, siblings, bare, bool(siblings) and not discriminator
        )

    def check(
        self, derivation: NameDerivation, *, person: bool, allow_incomplete: bool
    ) -> Result[NameFlag | None, DomainError]:
        r = derivation.rendered
        if not r.complete:
            if person and not allow_incomplete:
                needs = ", ".join(MISSING_FIELD_LABELS.get(m, m) for m in r.missing)
                return Failure(ValidationError(f"This protocol's name needs {needs}"))
            return Success(NameFlag.NEEDS_FACTS)
        if len(r.name) > MAX_NAME_LENGTH:
            if person:
                return Failure(
                    ValidationError(
                        f"The generated name is longer than {MAX_NAME_LENGTH} characters; "
                        "shorten the discriminator or a short label"
                    )
                )
            return Success(NameFlag.NEEDS_FACTS)
        if derivation.clash is not None:
            if person:
                return Failure(
                    ConflictError(
                        f"'{r.name}' is already the name of {derivation.clash.code}; "
                        "give one of them a different discriminator"
                    )
                )
            return Success(NameFlag.NAME_CONFLICT)
        if derivation.needs_discriminator:
            if person:
                codes = ", ".join(s.code or "?" for s in derivation.siblings)
                return Failure(
                    ConflictError(
                        f"Other protocols are also '{r.base}' ({codes}); "
                        "add a discriminator such as the method"
                    )
                )
            return Success(NameFlag.NEEDS_DISCRIMINATOR)
        return Success(None)

    async def flag_siblings(
        self, workspace_id: uuid.UUID, derivation: NameDerivation, *, clash_flag: bool = False
    ) -> None:
        """Bare siblings need a discriminator too; a system-made exact clash flags the other."""
        for sibling in derivation.bare_siblings:
            await self._flag(workspace_id, sibling, NameFlag.NEEDS_DISCRIMINATOR)
        if clash_flag and derivation.clash is not None:
            await self._flag(workspace_id, derivation.clash, NameFlag.NAME_CONFLICT)

    async def _flag(self, workspace_id: uuid.UUID, sibling: NameSibling, flag: NameFlag) -> None:
        other = await self._protocols.find_by_id_in_workspace(workspace_id, sibling.protocol_id)
        if other is not None and other.name_flag != flag:
            other.flag_name(flag)
            await self._protocols.save(other)

    async def apply(
        self,
        protocol: Protocol,
        *,
        reason: str,
        person: bool,
        allow_incomplete: bool,
        user_id: uuid.UUID | None = None,
        pattern: str | None = None,
        ctx: NamingContext | None = None,
    ) -> Result[NameDerivation, DomainError]:
        await self._protocols.lock_naming(protocol.workspace_id)
        derivation = await self.derive(
            protocol.workspace_id,
            category=protocol.category,
            target_ids=await self._protocols.find_direct_target_ids(
                protocol.workspace_id, protocol.id
            ),
            annotations=protocol.ontology_annotations,
            discriminator=protocol.discriminator,
            exclude_code=protocol.code,
            pattern=pattern,
            ctx=ctx,
        )
        checked = self.check(derivation, person=person, allow_incomplete=allow_incomplete)
        if isinstance(checked, Failure):
            return checked
        flag = checked.unwrap()
        await self.flag_siblings(
            protocol.workspace_id, derivation, clash_flag=flag == NameFlag.NAME_CONFLICT
        )
        if not derivation.rendered.complete:
            # A name with a gap never replaces a real one: keep it and flag what is missing.
            protocol.flag_name(flag)
            return Success(derivation)
        protocol.apply_derived_name(
            name=derivation.rendered.name,
            base=derivation.rendered.base,
            flag=flag,
            reason=reason,
            user_id=user_id,
        )
        return Success(derivation)
