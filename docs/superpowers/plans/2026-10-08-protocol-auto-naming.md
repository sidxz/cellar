# Protocol names generated from structured fields: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protocol names stop being typed: each name is rendered from the protocol's category pattern and its structured fields, with an immutable protocol code as the citation handle and aliases for recall.

**Architecture:** A pure naming policy in the shared domain kernel (`domain/shared/protocol_naming.py`, shared because both `screening_assay` and `workspace_config` use it and the import contract forbids cross-context domain imports) renders a category's pattern from targets, organism, cell line, assay format and a discriminator, using short labels. An application `ProtocolNameService` gathers those inputs, checks collisions, and sets the name through `Protocol.apply_derived_name`, which records the former name as an alias and emits `ProtocolRenamed` (audited with old/new/reason). Every path that changes an input (create, edit, correction, registry sync, admin pattern/label edits) re-derives through that one service.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2 async / Alembic / Lagom DI / returns (Railway) / pytest + testcontainers; Next.js 16 / React 19 / TanStack Query / react-hook-form + zod / shadcn/ui / vitest / orval.

**Spec:** `docs/superpowers/specs/2026-10-08-protocol-auto-naming-design.md` (read it before Task 1; every task argues from it).

**Branch:** `feat/protocol-auto-naming` (already created from `fix/protocol-bao-annotations`).

## Global Constraints

- Read `docs/backend-code-guidelines.md` and `docs/patterns-and-conventions.md` before any backend task. Every new use case: role guard first line, `require_same_workspace` second, `Result[T, DomainError]`, `async with self._uow:`, dispatch after commit.
- Protocol names never contain `·`, `—` or `–`. Hyphens inside terms (`SARS-CoV-2`) are fine.
- Protocol code: prefix `^[A-Z]{2,8}-$`, default `PRT-`; width default 5, range 3..8; immutable; never reused; versions share it.
- Discriminator: at most 40 characters; rejects stage words, library names, years/dates, version marks; required on both protocols when their base names collide.
- Generated names are at most 400 characters (`protocols.name` widened to 400).
- Frontend: never hand-roll a type that mirrors a backend DTO. New `Protocol` fields are typed off the generated `ProtocolResponse` (`code: ProtocolResponse["code"]`), like the existing `can_delete`. Regenerate orval in the same task that changes a DTO (`cd frontend && pnpm generate:api`, backend running on :8000), then revert files whose only change is the OpenAPI version stamp (see "orval churn" below).
- Commits: explicit pathspecs only (`git add <new files>` then `git commit -m "..." -- <paths>`); the working tree has unrelated user changes (`.gitignore`, `Makefile`, `frontend/next-env.d.ts`, `frontend/AGENTS.md`) that must never be committed. Messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; never add a `Claude-Session:` trailer.
- `backend/data/` is gitignored (local loader scripts); changes there are not committed.
- Never write to prot-cellar without the user's explicit confirmation in chat (Task 22).
- Integration and API tests need `DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock`.
- Migrations are numbered `NNN_snake_name` with `down_revision` the previous id; head today is `080_campaign_collections`. Apply with `make migrate` from the repo root.
- Walkthrough: every task that adds user-visible UI or a setting appends a line to spec section 7 if it is missing there (the user's end-of-implementation Chrome tour).

**orval churn** (after every `pnpm generate:api`):

```bash
cd frontend
for f in $(git diff --name-only -- src/shared/lib/api); do
  if [ -z "$(git diff -U0 -- "$f" | grep '^[+-]' | grep -v '^+++\|^---' | grep -vi 'version')" ]; then git checkout -- "$f"; fi
done
git status --short -- src/shared/lib/api
```

(The tool shell is fish; run this block with `bash -c '...'` or paste into bash.)

## Review Focus

1. **Two people create the same protocol at the same moment**: both pass the uniqueness check, two identical names land. Expected: the second create gets a clean 409. Task 13 serializes name checks per workspace with the same advisory lock used for code minting; Task 13 has the concurrency test.
2. **A protocol whose category is not in the category list** (legacy "Enzyme Assay", blank, or a category an admin deleted): derivation must not crash. Expected: name shows `(category needed) …`, flag `needs_facts`, publish refused. Tests in Tasks 13 and 14.
3. **A registry target renamed to something very long or with forbidden characters**: expected: forbidden characters are normalized (the policy already does this); a name over 400 characters is refused for person-initiated changes (`ValidationError`), while a system-initiated re-derivation keeps the current name, sets flag `needs_facts` and logs `protocol.name.too_long`. Test in Task 20.
4. **Case and spacing variants**: `FP` vs `fp`, `PptT  inhibition` vs `PptT inhibition`, nickname `MABA` added twice in different case. Expected: collisions, sibling checks and alias de-duplication are case-insensitive and whitespace-normalized. Tests in Tasks 1, 6 and 13.
5. **Relabels on locked or retired protocols, and a relabel racing a user edit**: expected: relabels apply regardless of lock/retire (labels, not facts), while corrections refuse; the system re-derive runs each protocol in its own unit of work and retries once on `ConcurrencyConflictError`. Tests in Tasks 20 and 21.

## File map

**Backend, new**
- `backend/src/cellar/domain/shared/protocol_naming.py`: naming policy (pure).
- `backend/src/cellar/application/screening/protocol_codes.py`: `mint_protocol_code`.
- `backend/src/cellar/application/screening/protocol_naming_service.py`: `ProtocolNameService`.
- `backend/src/cellar/application/screening/manage_protocol_aliases.py`: nickname use cases.
- `backend/src/cellar/application/screening/preview_protocol_name.py`: preview + discriminator list queries.
- `backend/src/cellar/application/screening/correct_protocol.py`: `CorrectProtocol`.
- `backend/src/cellar/application/screening/rederive_protocol_names.py`: `RederiveProtocolNames`, `RederiveAllProtocolNames`, `ListNameFlags`.
- `backend/src/cellar/application/screening/target_renamed_handler.py`: `TargetRenamed` → re-derive.
- `backend/src/cellar/domain/workspace_config/protocol_category.py`, `naming_label.py`.
- `backend/src/cellar/application/workspace_config/{protocol_categories,naming_labels,naming_changes}.py`.
- `backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/{protocol_category_repository,naming_label_repository}.py`.
- `backend/src/cellar/interface/routes/{protocol_categories,naming_labels,protocol_names}.py`.
- Migrations `081`..`086` (named in tasks).

**Backend, modified**: `domain/screening_assay/{protocol.py,enums.py,events.py,repository.py,protocol_versioning_service.py}`, `domain/workspace_config/{workspace_settings.py,events.py,repository.py}`, `application/screening/{create_protocol.py,manage_protocol.py,manage_ontology_annotations.py,list_protocol_summaries.py,cross_protocol_resolver.py,readout_calculation_engine.py,sync_targets.py}`, `application/cdd_import/import_cdd_protocol.py`, `application/audit/audit_recording_service.py`, `application/export/row_streams/{base.py,search_results.py}`, renderers `csv_renderer.py`/`sdf_renderer.py`, `application/research_organization/{close_campaign.py,get_published_campaign.py}`, `application/workspace_config/update_workspace_settings.py`, persistence models/repos, DI registrars, dependencies, `interface/routes/{protocols.py,settings.py}`, `interface/app.py`.

**Frontend, new**: `features/screening-assay/components/{protocol-name-preview.tsx,discriminator-input.tsx,protocol-aliases-card.tsx,correct-protocol-dialog.tsx,protocol-option-label.tsx}`, `features/screening-assay/hooks/{use-protocol-name-preview.ts,use-protocol-names-admin.ts}`, `features/workspace-config/components/{protocol-category-admin.tsx,naming-label-admin.tsx,protocol-names-admin.tsx,naming-change-preview.tsx}`, `features/workspace-config/hooks/{use-protocol-categories.ts,use-naming-labels.ts}`, admin pages `app/(dashboard)/admin/{protocol-categories,naming-labels,protocol-names}/page.tsx`.

**Frontend, modified**: `features/screening-assay/{types/index.ts,hooks/use-protocols.ts,hooks/use-protocol-facet-slots.ts,lib/protocol-facets.ts,lib/formula-tokens.ts,components/create-protocol-dialog.tsx,components/protocol-detail.tsx,components/protocol-category-input.tsx,components/formula-input.tsx,components/protocol-library-row.tsx,components/protocol-grid.tsx,components/protocol-browser.tsx,components/grouped-protocol-list.tsx,components/detail-tabs/{overview-tab.tsx,design-tab.tsx,design-tab-protocol-card.tsx,readout-definition-dialog.tsx}}`, `shared/components/detail-shell.tsx`, `shared/lib/navigation.ts`, `features/workspace-config/components/workspace-settings-form.tsx`, protocol pickers listed in Task 7. Delete `features/screening-assay/lib/suggest-protocol-name.ts` and its test.

---

# Part 1: Foundations

### Task 1: Naming policy (pure domain)

**Files:**
- Create: `backend/src/cellar/domain/shared/protocol_naming.py`
- Test: `backend/tests/unit/domain/shared/test_protocol_naming.py`

**Interfaces:**
- Consumes: `cellar.domain.shared.errors.ValidationError`.
- Produces (used by Tasks 10-21):
  - `NamingTerm(term_id: str, label: str, ontology_source: str)`
  - `NamingTarget(name: str, organism: str | None = None)`
  - `NamingInputs(targets: tuple[NamingTarget, ...] = (), organisms: tuple[NamingTerm, ...] = (), cell_lines: tuple[NamingTerm, ...] = (), matrices: tuple[NamingTerm, ...] = (), discriminator: str | None = None)`
  - `NamingContext(overrides_by_term: Mapping[str, str] = {}, overrides_by_label: Mapping[str, str] = {}, home_organism_label: str | None = None)`
  - `RenderedName(name: str, base: str, missing: tuple[str, ...], discriminator_in_pattern: bool)` with `.complete`
  - `render_protocol_name(pattern: str, inputs: NamingInputs, ctx: NamingContext) -> RenderedName`
  - `short_label(term: NamingTerm, ctx: NamingContext) -> str`, `organism_short_label(label: str, ctx: NamingContext) -> str`
  - `clean_discriminator(value: str | None, *, library_names: Iterable[str] = ()) -> str | None` (raises `ValidationError`)
  - `validate_pattern(pattern: str) -> None`, `validate_name_text(value: str, *, what: str) -> None`, `normalize_name_text(value: str) -> str`
  - `generic_pattern(category_label: str) -> str`
  - `DEFAULT_CATEGORY_PATTERNS: dict[str, str]`, `SHIPPED_SHORT_LABELS: tuple[ShippedLabel, ...]`, `SLOTS`, `MAX_NAME_LENGTH = 400`, `MAX_DISCRIMINATOR_LENGTH = 40`, `NCBITAXON`, `BAO` (URI prefixes)

- [ ] **Step 1: Write the failing tests**

```python
"""Naming policy: patterns rendered from facts, short labels, discriminator guard."""

import pytest

from cellar.domain.shared.protocol_naming import (
    BAO,
    DEFAULT_CATEGORY_PATTERNS,
    NCBITAXON,
    NamingContext,
    NamingInputs,
    NamingTarget,
    NamingTerm,
    clean_discriminator,
    generic_pattern,
    render_protocol_name,
    validate_pattern,
)
from cellar.domain.shared.errors import ValidationError

HOME = NamingContext(home_organism_label="Mycobacterium tuberculosis")
MTB = NamingTerm(f"{NCBITAXON}1773", "Mycobacterium tuberculosis", "NCBITAXON")
SMEG = NamingTerm(f"{NCBITAXON}1772", "Mycolicibacterium smegmatis", "NCBITAXON")
MYCO_GENUS = NamingTerm(f"{NCBITAXON}1763", "Mycobacterium", "NCBITAXON")
BACTERIA = NamingTerm(f"{NCBITAXON}2", "Bacteria", "NCBITAXON")
CRYPTO = NamingTerm(f"{NCBITAXON}5806", "Cryptosporidium", "NCBITAXON")
ECOLI = NamingTerm(f"{NCBITAXON}562", "Escherichia coli", "NCBITAXON")
HEPG2 = NamingTerm("http://purl.obolibrary.org/obo/CLO_0003703", "HepG2 cell", "CLO")
CACO2 = NamingTerm("http://purl.obolibrary.org/obo/CLO_0002172", "Caco-2 cell", "CLO")
MACROPHAGE = NamingTerm("http://purl.obolibrary.org/obo/CL_0000235", "macrophage", "CL")
MICROSOME = NamingTerm(f"{BAO}BAO_0000251", "microsome format", "BAO")
MTB_ORG = "Mycobacterium tuberculosis"
SARS = "Severe acute respiratory syndrome-related coronavirus"
MERS = "Middle East respiratory syndrome-related coronavirus"


def _render(pattern, ctx=HOME, **inputs):
    return render_protocol_name(pattern, NamingInputs(**inputs), ctx)


@pytest.mark.parametrize(
    ("pattern", "inputs", "expected"),
    [
        ("{target} inhibition", {"targets": (NamingTarget("PptT", MTB_ORG),), "discriminator": "FP"}, "PptT inhibition [FP]"),
        ("{target} binding", {"targets": (NamingTarget("GlcB", MTB_ORG),), "discriminator": "nanoDSF"}, "GlcB binding [nanoDSF]"),
        ("{target} inhibition", {"targets": (NamingTarget("hERG", None),)}, "hERG inhibition"),
        ("{target} inhibition", {"targets": (NamingTarget("MDH2", "Homo sapiens"),)}, "Human MDH2 inhibition"),
        ("{target} inhibition", {"targets": (NamingTarget("Mpro", SARS),), "discriminator": "FRET"}, "SARS-CoV-2 Mpro inhibition [FRET]"),
        ("{target} inhibition", {"targets": (NamingTarget("3CLpro", MERS),)}, "MERS-CoV 3CLpro inhibition"),
        ("{target} inhibition", {"targets": (NamingTarget("PanD", MTB_ORG), NamingTarget("PanC", MTB_ORG))}, "PanD/PanC inhibition"),
        ("{target} {discriminator}", {"targets": (NamingTarget("Kinin receptor", None),), "discriminator": "activation"}, "Kinin receptor activation"),
        ("{organism} growth inhibition", {"organisms": (MTB,), "discriminator": "hypoxia"}, "M. tuberculosis growth inhibition [hypoxia]"),
        ("{organism} growth inhibition", {"organisms": (SMEG,), "discriminator": "resazurin"}, "M. smegmatis growth inhibition [resazurin]"),
        ("{organism} growth inhibition", {"organisms": (MYCO_GENUS,), "discriminator": "resazurin"}, "Mycobacterium spp. growth inhibition [resazurin]"),
        ("{organism} growth inhibition", {"organisms": (BACTERIA,)}, "Bacterial growth inhibition"),
        ("Intracellular {organism} growth inhibition", {"organisms": (MTB,), "discriminator": "luciferase reporter"}, "Intracellular M. tuberculosis growth inhibition [luciferase reporter]"),
        ("{organism} in vivo efficacy", {"organisms": (CRYPTO,)}, "Cryptosporidium in vivo efficacy"),
        ("{organism} membrane potential", {"organisms": (ECOLI,)}, "E. coli membrane potential"),
        ("{cell_line} cytotoxicity", {"cell_lines": (HEPG2,), "discriminator": "CellTiter-Glo"}, "HepG2 cytotoxicity [CellTiter-Glo]"),
        ("{cell_line} cytotoxicity", {"cell_lines": (MACROPHAGE,)}, "Macrophage cytotoxicity"),
        ("{matrix} stability", {"matrices": (MICROSOME,)}, "Microsomal stability"),
        ("Plasma protein binding", {}, "Plasma protein binding"),
        ("{cell_line?} permeability", {"cell_lines": (CACO2,)}, "Caco-2 permeability"),
        ("{cell_line?} permeability", {"discriminator": "PAMPA"}, "Permeability [PAMPA]"),
        ("{discriminator?} solubility", {"discriminator": "kinetic"}, "Kinetic solubility"),
        ("{discriminator?} solubility", {}, "Solubility"),
        ("{subject?} {discriminator} prediction", {"targets": (NamingTarget("Mdh", MTB_ORG),), "discriminator": "docking score"}, "Mdh docking score prediction"),
        ("{subject?} {discriminator} prediction", {"discriminator": "toxicity score"}, "Toxicity score prediction"),
        ("{discriminator} interference", {"discriminator": "AMC quenching"}, "AMC quenching interference"),
        ("{target} inhibition", {"targets": (NamingTarget("RNA polymerase·NusG", MTB_ORG),)}, "RNA polymerase NusG inhibition"),
    ],
)
def test_renders_names(pattern, inputs, expected):
    assert _render(pattern, **inputs).name == expected


def test_base_drops_trailing_discriminator_but_keeps_placed_one():
    assert _render("{target} inhibition", targets=(NamingTarget("PptT", MTB_ORG),), discriminator="FP").base == "PptT inhibition"
    placed = _render("{discriminator?} solubility", discriminator="kinetic")
    assert placed.base == "Kinetic solubility" and placed.discriminator_in_pattern


def test_missing_required_slot_is_reported_with_a_placeholder():
    r = _render("{organism} growth inhibition")
    assert r.missing == ("organism",) and not r.complete
    assert r.name == "(organism needed) growth inhibition"


def test_missing_placed_discriminator_is_reported():
    assert _render("{subject?} {discriminator} prediction").missing == ("discriminator",)


def test_without_home_organism_every_target_gets_its_organism():
    r = render_protocol_name("{target} inhibition", NamingInputs(targets=(NamingTarget("PptT", MTB_ORG),)), NamingContext())
    assert r.name == "M. tuberculosis PptT inhibition"


def test_admin_override_beats_rule_and_shipped_label():
    ctx = NamingContext(overrides_by_term={MTB.term_id: "Mtb"}, home_organism_label=MTB_ORG)
    assert render_protocol_name("{organism} growth inhibition", NamingInputs(organisms=(MTB,)), ctx).name == "Mtb growth inhibition"


def test_target_organism_override_by_label():
    ctx = NamingContext(overrides_by_label={"homo sapiens": "hs"}, home_organism_label=MTB_ORG)
    r = render_protocol_name("{target} inhibition", NamingInputs(targets=(NamingTarget("MDH2", "Homo sapiens"),)), ctx)
    assert r.name == "hs MDH2 inhibition"


@pytest.mark.parametrize("bad", ["HTS", "dose response", "2021", "12/05", "v2", "corrected", "IC50"])
def test_discriminator_rejects_clutter(bad):
    with pytest.raises(ValidationError):
        clean_discriminator(f"resazurin {bad}")


def test_discriminator_rejects_library_names():
    with pytest.raises(ValidationError, match="SAC3"):
        clean_discriminator("SAC3 plates", library_names=["SAC3 library"])


def test_discriminator_cleans_and_accepts_methods():
    assert clean_discriminator("  FP  ") == "FP"
    assert clean_discriminator("4-MUH") == "4-MUH"
    assert clean_discriminator("method not stated") == "method not stated"
    assert clean_discriminator("   ") is None
    assert clean_discriminator(None) is None


@pytest.mark.parametrize("bad", ["a·b", "a—b", "x" * 41, "[FP]"])
def test_discriminator_rejects_bad_text(bad):
    with pytest.raises(ValidationError):
        clean_discriminator(bad)


@pytest.mark.parametrize("bad", ["", "{species} growth", "{target growth", "PptT — inhibition"])
def test_pattern_validation(bad):
    with pytest.raises(ValidationError):
        validate_pattern(bad)


def test_every_default_pattern_is_valid_and_has_27_categories():
    assert len(DEFAULT_CATEGORY_PATTERNS) == 27
    for pattern in DEFAULT_CATEGORY_PATTERNS.values():
        validate_pattern(pattern)


def test_generic_pattern_for_new_categories():
    assert generic_pattern("Biofilm inhibition") == "{subject?} biofilm inhibition"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/unit/domain/shared/test_protocol_naming.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'cellar.domain.shared.protocol_naming'`.

- [ ] **Step 3: Write the policy**

```python
"""Protocol names generated from structured fields.

A protocol category carries a name pattern made of plain words and slots. The
pattern is rendered from the protocol's facts using short labels. Pure: no I/O.
Spec: docs/superpowers/specs/2026-10-08-protocol-auto-naming-design.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from cellar.domain.shared.errors import ValidationError

MAX_NAME_LENGTH = 400
MAX_DISCRIMINATOR_LENGTH = 40
SLOTS = ("target", "organism", "cell_line", "matrix", "subject", "discriminator")
NCBITAXON = "http://purl.bioontology.org/ontology/NCBITAXON/"
BAO = "http://www.bioassayontology.org/bao#"

_SLOT_RE = re.compile(r"\{([a-z_]+)(\?)?\}")
_FORBIDDEN = {"·": " ", "—": "-", "–": "-"}
_STAGE_RE = re.compile(
    r"\b(hts|re-?test|primary screen|hit confirmation|dose[ -]?response|ic\d{2}|single[ -]point|triplicate)\b",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"\b(?:19|20)\d{2}\b|\b\d{1,2}[/.]\d{1,2}(?:[/.]\d{2,4})?\b")
_VERSION_RE = re.compile(r"\b(v\d+|corrected|before|after|new|old)\b", re.IGNORECASE)


@dataclass(frozen=True)
class NamingTerm:
    term_id: str
    label: str
    ontology_source: str


@dataclass(frozen=True)
class NamingTarget:
    name: str
    organism: str | None = None


@dataclass(frozen=True)
class NamingInputs:
    targets: tuple[NamingTarget, ...] = ()
    organisms: tuple[NamingTerm, ...] = ()
    cell_lines: tuple[NamingTerm, ...] = ()
    matrices: tuple[NamingTerm, ...] = ()
    discriminator: str | None = None


@dataclass(frozen=True)
class NamingContext:
    overrides_by_term: Mapping[str, str] = field(default_factory=dict)
    # lower-cased term label -> short label; registry targets carry organism as text
    overrides_by_label: Mapping[str, str] = field(default_factory=dict)
    home_organism_label: str | None = None


@dataclass(frozen=True)
class RenderedName:
    name: str
    base: str
    missing: tuple[str, ...]
    discriminator_in_pattern: bool

    @property
    def complete(self) -> bool:
        return not self.missing


@dataclass(frozen=True)
class ShippedLabel:
    term_id: str
    label: str
    short: str


SHIPPED_SHORT_LABELS: tuple[ShippedLabel, ...] = (
    ShippedLabel(f"{NCBITAXON}9606", "Homo sapiens", "Human"),
    ShippedLabel(f"{NCBITAXON}694009", "Severe acute respiratory syndrome-related coronavirus", "SARS-CoV-2"),
    ShippedLabel(f"{NCBITAXON}1335626", "Middle East respiratory syndrome-related coronavirus", "MERS-CoV"),
    ShippedLabel(f"{NCBITAXON}2", "Bacteria", "Bacterial"),
    ShippedLabel(f"{NCBITAXON}11019", "Alphavirus", "Alphavirus"),
    ShippedLabel(f"{NCBITAXON}5806", "Cryptosporidium", "Cryptosporidium"),
    ShippedLabel(f"{BAO}BAO_0000251", "microsome format", "Microsomal"),
    ShippedLabel(f"{BAO}BAO_0020003", "plasma format", "Plasma"),
)
_SHIPPED_BY_TERM = {s.term_id: s.short for s in SHIPPED_SHORT_LABELS}
_SHIPPED_BY_LABEL = {s.label.lower(): s.short for s in SHIPPED_SHORT_LABELS}

DEFAULT_CATEGORY_PATTERNS: dict[str, str] = {
    "Enzyme inhibition": "{target} inhibition",
    "Enzyme activation": "{target} activation",
    "Binding": "{target} binding",
    "Receptor function": "{target} {discriminator}",
    "Ion-channel inhibition": "{target} inhibition",
    "Growth inhibition": "{organism} growth inhibition",
    "Bactericidal activity": "{organism} bactericidal activity",
    "Intracellular growth inhibition": "Intracellular {organism} growth inhibition",
    "Metabolite rescue": "{organism} metabolite rescue",
    "Membrane potential": "{organism} membrane potential",
    "Resistance selection": "{organism?} resistant mutant selection",
    "Combination (checkerboard)": "{subject?} combination",
    "Cytotoxicity": "{cell_line} cytotoxicity",
    "Infection inhibition": "{organism} infection inhibition",
    "In vitro translation inhibition": "{organism} in vitro translation inhibition",
    "Intrabacterial pH homeostasis": "{organism} intrabacterial pH disruption",
    "Detection interference": "{discriminator} interference",
    "Metabolic stability": "{matrix} stability",
    "Plasma stability": "Plasma stability",
    "Plasma protein binding": "Plasma protein binding",
    "Permeability": "{cell_line?} permeability",
    "Solubility": "{discriminator?} solubility",
    "Lipophilicity": "Lipophilicity",
    "Pharmacokinetics": "{organism?} pharmacokinetics",
    "In vivo efficacy": "{organism} in vivo efficacy",
    "Compound identity / purity": "Compound identity and purity",
    "Prediction": "{subject?} {discriminator} prediction",
}


def normalize_name_text(value: str) -> str:
    for bad, good in _FORBIDDEN.items():
        value = value.replace(bad, good)
    return " ".join(value.split())


def validate_name_text(value: str, *, what: str) -> None:
    if any(ch in value for ch in _FORBIDDEN):
        raise ValidationError(f"{what} cannot contain '·', '—' or '–'")


def validate_pattern(pattern: str) -> None:
    if not pattern or not pattern.strip():
        raise ValidationError("Name pattern must not be empty")
    validate_name_text(pattern, what="Name pattern")
    unknown = [m.group(1) for m in _SLOT_RE.finditer(pattern) if m.group(1) not in SLOTS]
    if unknown:
        allowed = ", ".join("{" + s + "}" for s in SLOTS)
        raise ValidationError(f"Unknown slot {{{unknown[0]}}}; use one of {allowed}")
    if "{" in _SLOT_RE.sub("", pattern) or "}" in _SLOT_RE.sub("", pattern):
        raise ValidationError("Name pattern has an unmatched '{' or '}'")


def generic_pattern(category_label: str) -> str:
    label = normalize_name_text(category_label)
    return f"{{subject?}} {label[:1].lower()}{label[1:]}"


def _taxon_short(label: str) -> str:
    words = label.split()
    if len(words) == 2 and words[1].islower():
        return f"{words[0][0]}. {words[1]}"
    if len(words) == 1:
        return f"{words[0]} spp."
    return label


def short_label(term: NamingTerm, ctx: NamingContext) -> str:
    if term.term_id in ctx.overrides_by_term:
        return ctx.overrides_by_term[term.term_id]
    if term.term_id in _SHIPPED_BY_TERM:
        return _SHIPPED_BY_TERM[term.term_id]
    label = normalize_name_text(term.label)
    source = term.ontology_source.upper()
    if source == "NCBITAXON":
        return _taxon_short(label)
    if source in ("CLO", "CL"):
        return re.sub(r"\s+cell$", "", label, flags=re.IGNORECASE)
    if source == "BAO":
        return re.sub(r"\s+format$", "", label, flags=re.IGNORECASE)
    return label


def organism_short_label(label: str, ctx: NamingContext) -> str:
    key = label.strip().lower()
    if key in ctx.overrides_by_label:
        return ctx.overrides_by_label[key]
    if key in _SHIPPED_BY_LABEL:
        return _SHIPPED_BY_LABEL[key]
    return _taxon_short(normalize_name_text(label))


def _target_label(target: NamingTarget, ctx: NamingContext) -> str:
    name = normalize_name_text(target.name)
    home = (ctx.home_organism_label or "").strip().lower()
    if target.organism and target.organism.strip().lower() != home:
        return f"{organism_short_label(target.organism, ctx)} {name}"
    return name


def _joined(terms: tuple[NamingTerm, ...], ctx: NamingContext) -> str | None:
    return "/".join(short_label(t, ctx) for t in terms) or None


def render_protocol_name(pattern: str, inputs: NamingInputs, ctx: NamingContext) -> RenderedName:
    target = "/".join(_target_label(t, ctx) for t in inputs.targets) or None
    organism = _joined(inputs.organisms, ctx)
    cell_line = _joined(inputs.cell_lines, ctx)
    subject_from, subject = next(
        ((k, v) for k, v in (("target", target), ("organism", organism), ("cell_line", cell_line)) if v),
        (None, None),
    )
    values = {
        "target": target,
        "organism": organism,
        "cell_line": cell_line,
        "matrix": _joined(inputs.matrices, ctx),
        "subject": subject,
        "discriminator": inputs.discriminator or None,
    }
    discriminator_in_pattern = any(m.group(1) == "discriminator" for m in _SLOT_RE.finditer(pattern))
    missing: list[str] = []
    pieces: list[str] = []
    # Only a registry target keeps its own case at the start (hERG); everything else is capitalized.
    keeps_case: bool | None = None
    pos = 0
    for m in _SLOT_RE.finditer(pattern):
        literal = pattern[pos : m.start()]
        if literal.strip() and keeps_case is None:
            keeps_case = False
        pieces.append(literal)
        slot, optional = m.group(1), m.group(2) == "?"
        value = values.get(slot)
        if value:
            if keeps_case is None:
                keeps_case = slot == "target" or (slot == "subject" and subject_from == "target")
            pieces.append(value)
        elif not optional:
            missing.append(slot)
            if keeps_case is None:
                keeps_case = False
            pieces.append(f"({slot.replace('_', ' ')} needed)")
        pos = m.end()
    pieces.append(pattern[pos:])
    base = normalize_name_text("".join(pieces))
    if base and not keeps_case:
        base = base[0].upper() + base[1:]
    discriminator = values["discriminator"]
    name = base if discriminator_in_pattern or not discriminator else f"{base} [{discriminator}]"
    return RenderedName(name=name, base=base, missing=tuple(missing), discriminator_in_pattern=discriminator_in_pattern)


def clean_discriminator(value: str | None, *, library_names: Iterable[str] = ()) -> str | None:
    if value is None:
        return None
    validate_name_text(value, what="Discriminator")
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if len(cleaned) > MAX_DISCRIMINATOR_LENGTH:
        raise ValidationError(f"Discriminator must be at most {MAX_DISCRIMINATOR_LENGTH} characters")
    if "[" in cleaned or "]" in cleaned:
        raise ValidationError("Discriminator cannot contain '[' or ']'")
    if m := _STAGE_RE.search(cleaned):
        raise ValidationError(f"'{m.group(0)}' is a screening stage; record it on the run, not in the protocol name")
    if m := _DATE_RE.search(cleaned):
        raise ValidationError(f"'{m.group(0)}' looks like a date; dates belong on runs")
    if m := _VERSION_RE.search(cleaned):
        raise ValidationError(f"'{m.group(0)}' marks a version; protocol versions are tracked separately")
    for library in library_names:
        core = re.sub(r"\s+library$", "", library.strip(), flags=re.IGNORECASE)
        if len(core) >= 2 and re.search(rf"(?<!\w){re.escape(core)}(?!\w)", cleaned, re.IGNORECASE):
            raise ValidationError(f"'{core}' is a compound library; it belongs on the campaign, not the protocol name")
    return cleaned
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/domain/shared/test_protocol_naming.py -q`
Expected: all pass. If `test_renders_names[...Kinin receptor...]` fails on case, check `keeps_case`: the slot is `target`, so the value keeps its case.

- [ ] **Step 5: Lint and commit**

```bash
cd backend && uv run ruff check src/cellar/domain/shared/protocol_naming.py tests/unit/domain/shared/test_protocol_naming.py && uv run ruff format src/cellar/domain/shared/protocol_naming.py tests/unit/domain/shared/test_protocol_naming.py && uv run lint-imports
cd .. && git add backend/src/cellar/domain/shared/protocol_naming.py backend/tests/unit/domain/shared/test_protocol_naming.py
git commit -m "feat(protocols): naming policy renders names from category patterns

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/domain/shared/protocol_naming.py backend/tests/unit/domain/shared/test_protocol_naming.py
```

---

### Task 2: Protocol naming settings (code prefix, width, home organism storage)

**Files:**
- Modify: `backend/src/cellar/domain/workspace_config/workspace_settings.py`
- Modify: `backend/src/cellar/application/workspace_config/update_workspace_settings.py`
- Modify: `backend/src/cellar/interface/routes/settings.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/models.py` (`WorkspaceSettingsModel`), `.../workspace_config/workspace_settings_repository.py`
- Create: `backend/alembic/versions/081_protocol_naming_settings.py`
- Modify: `frontend/src/features/workspace-config/components/workspace-settings-form.tsx`, `frontend/src/features/workspace-config/types/index.ts`
- Test: `backend/tests/unit/domain/workspace_config/test_workspace_settings.py`, `backend/tests/api/test_settings_protocol_naming.py` (new)

**Interfaces:**
- Produces: `WorkspaceSettings.protocol_naming: dict`; properties `protocol_code_prefix -> str` (default `"PRT-"`), `protocol_code_width -> int` (default 5), `home_organism -> dict | None` (`{"term_id","label","ontology_source"}`), `home_organism_label -> str | None`; method `set_home_organism(term: dict | None) -> None`. `update(protocol_naming={...})` accepts only `code_prefix`/`code_width` and merges. Invalid values raise `ValidationError` (422), never `ValueError`.

- [ ] **Step 1: Write the failing domain tests** (append to `backend/tests/unit/domain/workspace_config/test_workspace_settings.py`)

```python
import uuid

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


class TestProtocolNamingSettings:
    def _settings(self):
        return WorkspaceSettings.create_default(workspace_id=uuid.uuid4())

    def test_defaults(self):
        s = self._settings()
        assert s.protocol_code_prefix == "PRT-"
        assert s.protocol_code_width == 5
        assert s.home_organism is None and s.home_organism_label is None

    def test_update_merges_code_settings(self):
        s = self._settings()
        s.update(protocol_naming={"code_prefix": "ASY-"})
        s.update(protocol_naming={"code_width": 6})
        assert (s.protocol_code_prefix, s.protocol_code_width) == ("ASY-", 6)

    @pytest.mark.parametrize("bad", [{"code_prefix": "prt-"}, {"code_prefix": "P-"}, {"code_width": 2}, {"code_width": 9}, {"code_width": True}, {"colour": "red"}])
    def test_update_rejects_bad_values(self, bad):
        with pytest.raises(ValidationError):
            self._settings().update(protocol_naming=bad)

    def test_home_organism_is_not_set_through_update(self):
        with pytest.raises(ValidationError, match="home organism"):
            self._settings().update(protocol_naming={"home_organism": {"term_id": "x", "label": "y"}})

    def test_set_home_organism_and_clear(self):
        s = self._settings()
        s.set_home_organism({"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"})
        assert s.home_organism_label == "Mycobacterium tuberculosis"
        s.update(protocol_naming={"code_width": 4})
        assert s.home_organism_label == "Mycobacterium tuberculosis"  # update keeps it
        s.set_home_organism(None)
        assert s.home_organism is None

    def test_set_home_organism_needs_id_and_label(self):
        with pytest.raises(ValidationError):
            self._settings().set_home_organism({"term_id": "", "label": "x"})
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest tests/unit/domain/workspace_config/test_workspace_settings.py -q -k ProtocolNaming`
Expected: FAIL (`AttributeError: 'WorkspaceSettings' object has no attribute 'protocol_code_prefix'`).

- [ ] **Step 3: Implement in the domain**

In `workspace_settings.py`:
1. Add constants after `_BATCH_WIDTH_MAX`:

```python
_DEFAULT_PROTOCOL_CODE_PREFIX = "PRT-"
_DEFAULT_PROTOCOL_CODE_WIDTH = 5
_PROTOCOL_CODE_WIDTH_MIN = 3
_PROTOCOL_CODE_WIDTH_MAX = 8
_PROTOCOL_NAMING_KEYS = frozenset({"code_prefix", "code_width"})
```

2. Add `protocol_naming: dict | None = None,` to `__init__` kwargs and `self.protocol_naming = protocol_naming or {}` beside `self.registration_rules = ...`.
3. Add properties and the setter (place after `batch_sequence_width`):

```python
    @property
    def protocol_code_prefix(self) -> str:
        raw = self.protocol_naming.get("code_prefix")
        return raw if isinstance(raw, str) and raw else _DEFAULT_PROTOCOL_CODE_PREFIX

    @property
    def protocol_code_width(self) -> int:
        raw = self.protocol_naming.get("code_width")
        if isinstance(raw, int) and not isinstance(raw, bool):
            return raw
        return _DEFAULT_PROTOCOL_CODE_WIDTH

    @property
    def home_organism(self) -> dict | None:
        raw = self.protocol_naming.get("home_organism")
        if isinstance(raw, dict) and raw.get("term_id") and raw.get("label"):
            return raw
        return None

    @property
    def home_organism_label(self) -> str | None:
        home = self.home_organism
        return home["label"] if home else None

    def set_home_organism(self, term: dict | None) -> None:
        """The organism protocol names leave unstated (targets from it get no prefix).
        Changing it relabels protocols, so it has its own path (preview + confirm)."""
        naming = dict(self.protocol_naming)
        if term is None:
            naming.pop("home_organism", None)
        else:
            if not (term.get("term_id") and term.get("label")):
                raise ValidationError("Home organism needs a term id and a label")
            naming["home_organism"] = {
                "term_id": term["term_id"],
                "label": term["label"],
                "ontology_source": term.get("ontology_source") or "NCBITAXON",
            }
        self.protocol_naming = naming
        self.updated_at = datetime.now(UTC)
        self.register_event(
            WorkspaceSettingsUpdated(aggregate_id=self.id, aggregate_type="WorkspaceSettings", workspace_id=self.workspace_id)
        )
```

(Match the `WorkspaceSettingsUpdated(...)` constructor exactly as `update()` builds it today; copy its arguments.)

4. In `update(self, **fields)`, before the `setattr` loop, add:

```python
        if "protocol_naming" in fields:
            incoming = fields["protocol_naming"]
            if not isinstance(incoming, dict):
                raise ValidationError("protocol_naming must be an object")
            if "home_organism" in incoming:
                raise ValidationError("Set the home organism through its own setting (it relabels protocols)")
            unknown = set(incoming) - _PROTOCOL_NAMING_KEYS
            if unknown:
                raise ValidationError(f"Unknown protocol naming setting(s): {', '.join(sorted(unknown))}")
            if "code_prefix" in incoming:
                pfx = incoming["code_prefix"]
                if not isinstance(pfx, str) or not _PREFIX_PATTERN.match(pfx):
                    raise ValidationError(f"Protocol code prefix must look like PRT- (2-8 capital letters and a hyphen); got {pfx!r}")
            if "code_width" in incoming:
                width = incoming["code_width"]
                if (
                    not isinstance(width, int)
                    or isinstance(width, bool)
                    or not _PROTOCOL_CODE_WIDTH_MIN <= width <= _PROTOCOL_CODE_WIDTH_MAX
                ):
                    raise ValidationError(
                        f"Protocol code width must be {_PROTOCOL_CODE_WIDTH_MIN}-{_PROTOCOL_CODE_WIDTH_MAX} digits; got {width!r}"
                    )
            fields["protocol_naming"] = {**self.protocol_naming, **incoming}
```

and add `"protocol_naming"` to the tuple of keys the `setattr` loop assigns. Import `ValidationError` from `cellar.domain.shared.errors` if not imported.

- [ ] **Step 4: Run domain tests**

Run: `cd backend && uv run pytest tests/unit/domain/workspace_config/test_workspace_settings.py -q`
Expected: PASS.

- [ ] **Step 5: Persistence, migration, command, route**

Migration `backend/alembic/versions/081_protocol_naming_settings.py`:

```python
"""workspace protocol naming settings (code prefix/width, home organism)

Revision ID: 081_protocol_naming_settings
Revises: 080_campaign_collections
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "081_protocol_naming_settings"
down_revision: str | None = "080_campaign_collections"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_settings",
        sa.Column("protocol_naming", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("workspace_settings", "protocol_naming")
```

- `WorkspaceSettingsModel`: `protocol_naming: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)`.
- Repository `_to_domain` passes `protocol_naming=model.protocol_naming or {}`; `_to_model` and `_update_model` assign `protocol_naming=aggregate.protocol_naming`.
- `UpdateWorkspaceSettingsCommand`: add `protocol_naming: dict | object = UNSET` and add `"protocol_naming"` to the use case's key tuple.
- `interface/routes/settings.py`: `WorkspaceSettingsResponse.protocol_naming: dict = {}` (fill in `from_domain`), `UpdateWorkspaceSettingsBody.protocol_naming: dict | None = None`, and add `"protocol_naming"` to the route's key tuple.

Run `make migrate` from the repo root. Expected: `Running upgrade 080_campaign_collections -> 081_protocol_naming_settings`.

- [ ] **Step 6: API test** (`backend/tests/api/test_settings_protocol_naming.py`)

```python
"""PATCH /settings protocol_naming: merged, validated as 422."""


async def test_patch_protocol_naming_round_trips(client):
    r = await client.patch("/api/v1/settings", json={"protocol_naming": {"code_prefix": "ASY-", "code_width": 4}})
    assert r.status_code == 200, r.text
    assert r.json()["protocol_naming"] == {"code_prefix": "ASY-", "code_width": 4}


async def test_patch_protocol_naming_bad_prefix_is_422(client):
    r = await client.patch("/api/v1/settings", json={"protocol_naming": {"code_prefix": "bad"}})
    assert r.status_code == 422, r.text
```

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_settings_protocol_naming.py -q`
Expected: PASS.

- [ ] **Step 7: Frontend settings card**

Regenerate orval (`cd frontend && pnpm generate:api`, then the orval churn block). In `workspace-settings-form.tsx`:
- schema: `protocolCodePrefix: z.string().regex(/^[A-Z]{2,8}-$/, "2-8 capital letters then a hyphen, e.g. PRT-")`, `protocolCodeWidth: z.coerce.number().int().min(3).max(8)`.
- defaults/reset: `const naming = (settings.protocol_naming ?? {}) as ProtocolNamingSettings;` then `protocolCodePrefix: naming.code_prefix ?? "PRT-"`, `protocolCodeWidth: naming.code_width ?? 5`.
- save payload: `protocol_naming: { code_prefix: values.protocolCodePrefix, code_width: values.protocolCodeWidth }`.
- a new `<Card className="p-6">` titled "Protocols" after the "Registration" card, with the two inputs copied from the registration prefix/width inputs (ids `protocolCodePrefix`, `protocolCodeWidth`, placeholder `PRT-`, `maxLength={9}`, `className="uppercase"`, width `min={3} max={8}`) and helper text: "New protocols get codes like PRT-00142. Existing codes never change."
- `features/workspace-config/types/index.ts`: `export interface ProtocolNamingSettings { code_prefix?: string; code_width?: number; home_organism?: { term_id: string; label: string; ontology_source: string } }`.

Run: `cd frontend && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/workspace-config`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/081_protocol_naming_settings.py backend/tests/api/test_settings_protocol_naming.py
git commit -m "feat(settings): protocol code prefix/width and home organism storage

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/domain/workspace_config/workspace_settings.py backend/src/cellar/application/workspace_config/update_workspace_settings.py backend/src/cellar/interface/routes/settings.py backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config backend/alembic/versions/081_protocol_naming_settings.py backend/tests/unit/domain/workspace_config/test_workspace_settings.py backend/tests/api/test_settings_protocol_naming.py frontend/src/features/workspace-config frontend/src/shared/lib/api
```

---

### Task 3: Protocol code (backend)

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/protocol.py` (`Protocol.__init__`, `create`)
- Modify: `backend/src/cellar/domain/screening_assay/protocol_versioning_service.py`
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` (`ProtocolRepository`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/{models.py,protocol_repository.py}`
- Create: `backend/src/cellar/application/screening/protocol_codes.py`
- Modify: `backend/src/cellar/application/screening/create_protocol.py`, `backend/src/cellar/application/cdd_import/import_cdd_protocol.py`, `backend/src/cellar/application/screening/list_protocol_summaries.py`
- Modify: `backend/src/cellar/infrastructure/di/_screening.py`, `backend/src/cellar/infrastructure/di/_cdd_import.py`
- Modify: `backend/src/cellar/interface/routes/protocols.py` (`ProtocolResponse`, `ProtocolSummaryResponse`)
- Create: `backend/alembic/versions/082_protocol_code.py`
- Test: `backend/tests/integration/test_protocol_code.py` (new), `backend/tests/unit/domain/screening_assay/test_protocol_versioning_service.py` (extend or create), `backend/tests/api/test_protocol_code_route.py` (new)

**Interfaces:**
- Produces: `Protocol.code: str | None` (constructor/`create` kwarg `code: str | None = None`); `ProtocolRepository.next_protocol_code(workspace_id, *, prefix: str, width: int) -> str`; `mint_protocol_code(*, settings_repo: WorkspaceSettingsRepository | None, protocol_repo: ProtocolRepository, workspace_id: uuid.UUID) -> str`; `ProtocolResponse.code: str | None`; `ProtocolSummaryResponse.code: str | None`.
- Lock name used for minting AND for name checks (Task 13): `f"protocol_naming:{workspace_id}"`.

- [ ] **Step 1: Failing integration test** (`backend/tests/integration/test_protocol_code.py`)

```python
"""Protocol codes: minted per workspace, sequential, shared by versions."""

import asyncio
import uuid

from cellar.domain.screening_assay.enums import ProtocolStatus, ProtocolType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.protocol_versioning_service import ProtocolVersioningService
from cellar.infrastructure.persistence.sqlalchemy.screening_assay.protocol_repository import (
    SQLAlchemyProtocolRepository,
)
from cellar.infrastructure.persistence.unit_of_work import AsyncUnitOfWork


def _protocol(ws, user, code):
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=ws, name=f"P {code}", protocol_type=ProtocolType.BIOCHEMICAL, created_by=user, code=code,
        readout_definitions=[ReadoutDefinition(protocol_id=pid, name="Signal", data_type="numeric")],
    )


async def test_codes_are_sequential_per_workspace(uow, workspace_id, user_id):
    async with uow:
        repo = SQLAlchemyProtocolRepository(uow)
        first = await repo.next_protocol_code(workspace_id, prefix="PRT-", width=5)
        await repo.save(_protocol(workspace_id, user_id, first))
        second = await repo.next_protocol_code(workspace_id, prefix="PRT-", width=5)
        await uow.commit()
    assert (first, second) == ("PRT-00001", "PRT-00002")


async def test_concurrent_mints_never_collide(session_factory, workspace_id, user_id):
    async def mint_and_save():
        uow = AsyncUnitOfWork(session_factory)
        async with uow:
            repo = SQLAlchemyProtocolRepository(uow)
            code = await repo.next_protocol_code(workspace_id, prefix="PRT-", width=5)
            await repo.save(_protocol(workspace_id, user_id, code))
            await uow.commit()
        return code

    codes = await asyncio.gather(*(mint_and_save() for _ in range(4)))
    assert len(set(codes)) == 4


async def test_new_version_shares_the_code(uow, workspace_id, user_id):
    p = _protocol(workspace_id, user_id, "PRT-00007")
    p.publish()
    child = ProtocolVersioningService().create_new_version(p)
    assert child.code == "PRT-00007" and child.protocol_version == 2
```

(Check `ReadoutDefinition`'s constructor in `protocol.py` before running; match its required args. If `publish()` requires more state, copy the setup from `tests/unit/application/screening/test_delete_protocol.py`.)

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_protocol_code.py -q`
Expected: FAIL (`TypeError: Protocol.create() got an unexpected keyword argument 'code'`).

- [ ] **Step 3: Domain + versioning**

- `Protocol.__init__`: add kwarg `code: str | None = None` and `self.code = code` (after `self.name`). `create(...)`: add kwarg `code: str | None = None` and pass `code=code` to `cls(...)`.
- `ProtocolVersioningService.create_new_version`: pass `code=parent.code` to the new `Protocol(...)`.
- `ProtocolRepository` (domain protocol): add

```python
    async def next_protocol_code(self, workspace_id: uuid.UUID, *, prefix: str, width: int) -> str: ...
```

- [ ] **Step 4: Persistence + migration**

`ProtocolModel`: `code: Mapped[str | None] = mapped_column(String(20))`; add to `__table_args__`: `Index("uq_protocol_ws_code_version", "workspace_id", "code", "protocol_version", unique=True)`. Map `code` in `_to_domain` (`code=model.code`), `_to_model` (`code=aggregate.code`), `_update_model` (`model.code = aggregate.code`).

Repository method (follow `next_registration_number` in `chemical_registration/molecule_repository.py:416`):

```python
    async def next_protocol_code(self, workspace_id: uuid.UUID, *, prefix: str, width: int) -> str:
        # Serialize per workspace: the MAX+1 read and the INSERT share this transaction and the
        # advisory lock is held until commit. The same lock guards name checks (ProtocolNameService).
        # ponytail: one protocol create at a time per workspace; a SEQUENCE if throughput ever matters.
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtext(f"protocol_naming:{workspace_id}")))
        )
        stmt = select(
            func.coalesce(
                func.max(func.cast(func.substring(ProtocolModel.code, sa.literal(r"[0-9]+$")), sa.Integer)), 0
            )
        ).where(ProtocolModel.workspace_id == workspace_id)
        max_num: int = (await self._session.execute(stmt)).scalar_one()
        return f"{prefix}{max_num + 1:0{width}d}"
```

(`import sqlalchemy as sa` and `func` if the module lacks them.)

Migration `backend/alembic/versions/082_protocol_code.py`:

```python
"""protocol code: immutable citation handle shared by a protocol's versions

Revision ID: 082_protocol_code
Revises: 081_protocol_naming_settings
Create Date: 2026-10-08
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "082_protocol_code"
down_revision: str | None = "081_protocol_naming_settings"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("protocols", sa.Column("code", sa.String(20), nullable=True))
    # Lineage roots numbered in creation order per workspace; versions inherit the root's code.
    op.execute(
        """
        WITH RECURSIVE roots AS (
            SELECT id, row_number() OVER (PARTITION BY workspace_id ORDER BY created_at, id) AS n
            FROM protocols WHERE parent_protocol_id IS NULL
        ), tree AS (
            SELECT p.id, r.n FROM protocols p JOIN roots r ON r.id = p.id
            UNION ALL
            SELECT c.id, t.n FROM protocols c JOIN tree t ON c.parent_protocol_id = t.id
        )
        UPDATE protocols p SET code = 'PRT-' || lpad(t.n::text, 5, '0') FROM tree t WHERE t.id = p.id
        """
    )
    op.create_index(
        "uq_protocol_ws_code_version", "protocols", ["workspace_id", "code", "protocol_version"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_protocol_ws_code_version", table_name="protocols")
    op.drop_column("protocols", "code")
```

Run `make migrate`, then check every row got a code:

```bash
docker exec -i chem-vault2-postgres-1 psql -U cellar -d cellar -At -c "select count(*) filter (where code is null), count(*), count(distinct (workspace_id, code)) from protocols"
```

Expected: `0|<n>|<lineages>`.

- [ ] **Step 5: Mint on create**

`backend/src/cellar/application/screening/protocol_codes.py`:

```python
"""Protocol codes are minted from the workspace's prefix and width."""

from __future__ import annotations

import uuid

from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.workspace_config.repository import WorkspaceSettingsRepository
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings


async def mint_protocol_code(
    *,
    settings_repo: WorkspaceSettingsRepository | None,
    protocol_repo: ProtocolRepository,
    workspace_id: uuid.UUID,
) -> str:
    settings = await settings_repo.find_by_workspace_id(workspace_id) if settings_repo else None
    settings = settings or WorkspaceSettings.create_default(workspace_id=workspace_id)
    return await protocol_repo.next_protocol_code(
        workspace_id, prefix=settings.protocol_code_prefix, width=settings.protocol_code_width
    )
```

- `CreateProtocol.__init__`: add kwarg `settings_repo: WorkspaceSettingsRepository | None = None`; inside the UoW, before `Protocol.create(...)`: `code = await mint_protocol_code(settings_repo=self._settings_repo, protocol_repo=self._repo, workspace_id=input.workspace_id)` and pass `code=code`.
- `ImportCddProtocol`: same (constructor kwarg + mint before `Protocol.create`).
- DI `_screening.py`: replace `container.define(CreateProtocol, _protocol_cmd(CreateProtocol))` with:

```python
    def _create_protocol(c: Container):
        uow = AsyncUnitOfWork(c[async_sessionmaker])
        return CreateProtocol(
            uow, SQLAlchemyProtocolRepository(uow), c[EventDispatcher],
            settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
        )

    container.define(CreateProtocol, _create_protocol)
```

(import `SQLAlchemyWorkspaceSettingsRepository` from `cellar.infrastructure.persistence.sqlalchemy.workspace_config.workspace_settings_repository`). Do the same in `_cdd_import.py` for `ImportCddProtocol`.
- `list_protocol_summaries.py`: `ProtocolSummary.code: str | None = None`; set `code=p.code` where summaries are built.
- Routes: `ProtocolResponse.code: str | None = None` (`code=p.code` in `from_domain`); `ProtocolSummaryResponse.code: str | None = None`.

- [ ] **Step 6: API test** (`backend/tests/api/test_protocol_code_route.py`)

```python
"""POST /protocols returns a minted code; the next create gets the next number."""

import re

BODY = {"name": "x", "protocol_type": "biochemical", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}]}


async def test_create_mints_sequential_codes(client):
    a = (await client.post("/api/v1/protocols", json=BODY | {"name": "A"})).json()
    b = (await client.post("/api/v1/protocols", json=BODY | {"name": "B"})).json()
    assert re.fullmatch(r"PRT-\d{5}", a["code"])
    assert int(b["code"][4:]) == int(a["code"][4:]) + 1
```

(`name` is still a request field until Task 14 removes it.)

- [ ] **Step 7: Run tests**

```bash
cd backend && uv run pytest tests/unit -q -x
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_protocol_code.py tests/api/test_protocol_code_route.py tests/api/test_protocol_create_ontology_annotations.py -q
```

Expected: PASS. Fix any unit test that builds `CreateProtocol(...)` positionally (the new kwarg is optional, so none should break).

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/082_protocol_code.py backend/src/cellar/application/screening/protocol_codes.py backend/tests/integration/test_protocol_code.py backend/tests/api/test_protocol_code_route.py
git commit -m "feat(protocols): immutable protocol codes minted per workspace

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/domain/screening_assay backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay backend/src/cellar/application/screening backend/src/cellar/application/cdd_import backend/src/cellar/infrastructure/di backend/src/cellar/interface/routes/protocols.py backend/alembic/versions/082_protocol_code.py backend/tests/integration/test_protocol_code.py backend/tests/api/test_protocol_code_route.py
```

---

### Task 4: Protocol code in the UI

**Files:**
- Modify: `frontend/src/shared/components/detail-shell.tsx`
- Modify: `frontend/src/features/screening-assay/types/index.ts`
- Modify: `frontend/src/features/screening-assay/components/{protocol-detail.tsx,protocol-library-row.tsx,protocol-grid.tsx,detail-tabs/overview-tab.tsx}`
- Test: `frontend/src/shared/components/detail-shell.test.tsx` (new), `frontend/src/features/screening-assay/components/protocol-library-row.test.tsx` (new)

**Interfaces:**
- Consumes: generated `ProtocolResponse.code` (Task 3; regenerate orval first).
- Produces: `DetailShell` prop `subtitle?: (entity: T) => ReactNode` rendered under the title; `Protocol.code: ProtocolResponse["code"]`.

- [ ] **Step 1: Regenerate orval and type the field**

`cd frontend && pnpm generate:api` (backend running), then the orval churn block. In `types/index.ts` add to `interface Protocol`, beside `can_delete`:

```ts
  /** Immutable citation handle shared by every version (`PRT-00142`). Typed off the DTO. */
  code: ProtocolResponse["code"];
```

- [ ] **Step 2: Failing tests**

`detail-shell.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DetailShell } from "./detail-shell";

vi.mock("next/navigation", () => ({ usePathname: () => "/assays/protocols/p-1" }));

describe("DetailShell subtitle", () => {
  it("renders the subtitle under the title", () => {
    render(
      <DetailShell
        query={{ data: { name: "PptT inhibition [FP]", code: "PRT-00042" }, isLoading: false }}
        title={(e) => e.name}
        subtitle={(e) => <span>{e.code}</span>}
      >
        {() => null}
      </DetailShell>,
    );
    expect(screen.getByRole("heading", { name: "PptT inhibition [FP]" })).toBeInTheDocument();
    expect(screen.getByText("PRT-00042")).toBeInTheDocument();
  });
});
```

`protocol-library-row.test.tsx`: render `ProtocolLibraryRow` with a minimal protocol (`{ id: "p", name: "PptT inhibition [FP]", code: "PRT-00042", protocol_type: "biochemical", status: "draft", targets: [], category: "Enzyme inhibition", readout_definitions: [] } as Protocol`) and assert `screen.getByText("PRT-00042")`. Read the component's props first and pass whatever else it requires.

Run: `cd frontend && pnpm exec vitest run src/shared/components/detail-shell.test.tsx src/features/screening-assay/components/protocol-library-row.test.tsx`
Expected: FAIL (no `subtitle` prop; code not rendered). If `DetailShell` needs the breadcrumb store mocked, mock `@/shared/lib/stores/breadcrumb-store` with no-op `useBreadcrumbTrail`/`useBreadcrumbOverride`.

- [ ] **Step 3: Implement**

- `DetailShell`: add `subtitle?: (entity: T) => ReactNode;` to props; destructure; directly under the `<h1>` row render `{subtitle ? <div className="mt-1 text-sm text-muted-foreground">{subtitle(entity)}</div> : null}` (use the variable the component already holds for the loaded entity).
- `protocol-detail.tsx`: pass `subtitle={(p) => p.code ? <span className="font-mono">{p.code}</span> : null}`; pass `entityLabel={protocol.code ?? protocol.name}` to `CascadeDeleteDialog` (typing a generated name is painful; the code is short and unique). Also show the code in the plain delete dialog text: `"{protocol?.name}" ({protocol?.code}, v{protocol?.protocol_version})`.
- `protocol-library-row.tsx`: before the name span add `<span className="w-24 shrink-0 font-mono text-xs text-muted-foreground">{protocol.code}</span>`.
- `protocol-grid.tsx`: add a first column `{ headerName: "Code", field: "code", width: 110, cellClass: "font-mono text-xs" }`.
- `overview-tab.tsx`: add a "Code" cell first in the details grid: `<p className="text-sm text-muted-foreground">Code</p><p className="font-mono font-medium">{protocol.code ?? "—"}</p>`.

- [ ] **Step 4: Run tests, typecheck, lint**

```bash
cd frontend && pnpm exec vitest run src/shared/components src/features/screening-assay && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/shared/components/detail-shell.tsx src/features/screening-assay
```

Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shared/components/detail-shell.test.tsx frontend/src/features/screening-assay/components/protocol-library-row.test.tsx
git commit -m "feat(protocols): show protocol codes in the header, library, grid and overview

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/shared/components/detail-shell.tsx frontend/src/shared/components/detail-shell.test.tsx frontend/src/features/screening-assay frontend/src/shared/lib/api
```

---

### Task 5: Protocol code in exports and campaign payloads

**Files:**
- Modify: `backend/src/cellar/application/export/row_streams/base.py` (`ColumnSpec`)
- Modify: `backend/src/cellar/application/export/row_streams/search_results.py`
- Modify: `backend/src/cellar/application/export/renderers/{csv_renderer.py,sdf_renderer.py}` (find exact paths with `grep -rn "display_header" backend/src/cellar/application/export`)
- Modify: `backend/src/cellar/application/screening/molecule_activity_service.py` (the `any` entries)
- Modify: `backend/src/cellar/application/research_organization/{close_campaign.py,get_published_campaign.py}`
- Test: `backend/tests/unit/application/export/test_column_spec_flat_header.py` (new); extend the existing search-results row stream test (find with `grep -rln "_expand_protocol_column\|SearchResultsRowStream" backend/tests`).

**Interfaces:**
- Produces: `ColumnSpec.group_code: str | None = None`; `ColumnSpec.flat_header -> str` (`"IC50 (uM) [PRT-00042]"` when `group_code`, else `display_header`). CSV and SDF renderers use `flat_header`; XLSX keeps `display_header` under a group label `"PRT-00042 PptT inhibition [FP]"`.
- Published campaign `protocol_ref` and `source_protocols` items gain `"code"`; "Active in" entries gain `protocol_code`.

- [ ] **Step 1: Failing unit test**

```python
from cellar.application.export.row_streams.base import ColumnSpec


def test_flat_header_carries_the_protocol_code():
    col = ColumnSpec(key="k", header="IC50", kind="number", unit="uM", group="PRT-00042 PptT inhibition [FP]", group_code="PRT-00042")
    assert col.flat_header == "IC50 (uM) [PRT-00042]"


def test_flat_header_without_group_is_the_display_header():
    assert ColumnSpec(key="k", header="Name", kind="text").flat_header == "Name"
```

Run: `cd backend && uv run pytest tests/unit/application/export/test_column_spec_flat_header.py -q` → FAIL.

- [ ] **Step 2: Implement**

`ColumnSpec`:

```python
    group_code: str | None = None  # protocol code of the group; flat formats (CSV, SDF) append it

    @property
    def flat_header(self) -> str:
        """CSV and SDF have no group row: without the code, IC50 from two protocols collide."""
        return f"{self.display_header} [{self.group_code}]" if self.group_code else self.display_header
```

`search_results.py` `_expand_protocol_column`: where `proto_name = proto.name if proto else "Protocol"`, add `proto_code = proto.code if proto else None` and `group_label = f"{proto_code} {proto_name}" if proto_code else proto_name`; every `ColumnSpec(... group=proto_name)` becomes `group=group_label, group_code=proto_code`. In `_format_any_entries`, prefix the protocol with its code: `label = f"{e.get('protocol_code')} {protocol_name}" if e.get("protocol_code") else protocol_name`. CSV and SDF renderers: replace `c.display_header` / `col.display_header` with `flat_header`.

`molecule_activity_service.py` where `protocol_name=proto.name` is set for the `any` entries: add `protocol_code=proto.code` to the same dict/dataclass.

`close_campaign.py` snapshot dict: add `"code": p.code`. `get_published_campaign.py` `protocol_ref`: add `"code": proto.code`.

- [ ] **Step 3: Run tests**

```bash
cd backend && uv run pytest tests/unit/application/export tests/unit/application/research_organization -q
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api -q -k "published or export"
```

Expected: PASS. Update any snapshot assertion that compares the whole `protocol_ref` dict to include `"code"`.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/unit/application/export/test_column_spec_flat_header.py
git commit -m "feat(exports): protocol code in export headers and campaign payloads

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/application/export backend/src/cellar/application/screening/molecule_activity_service.py backend/src/cellar/application/research_organization backend/tests
```

---

### Task 6: Aliases (former names + nicknames)

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/enums.py` (add `AliasKind`)
- Modify: `backend/src/cellar/domain/screening_assay/protocol.py` (`ProtocolAlias`, `Protocol.aliases`, `add_nickname`, `remove_nickname`)
- Modify: `backend/src/cellar/domain/screening_assay/protocol_versioning_service.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/{models.py,protocol_repository.py}`
- Create: `backend/alembic/versions/083_protocol_aliases.py`
- Create: `backend/src/cellar/application/screening/manage_protocol_aliases.py`
- Modify: `backend/src/cellar/application/screening/list_protocol_summaries.py`, `backend/src/cellar/infrastructure/di/_screening.py`, `backend/src/cellar/interface/dependencies/_screening.py`, `backend/src/cellar/interface/routes/protocols.py`
- Create: `frontend/src/features/screening-assay/components/protocol-aliases-card.tsx`
- Modify: `frontend/src/features/screening-assay/{types/index.ts,hooks/use-protocols.ts,components/detail-tabs/overview-tab.tsx}`
- Test: `backend/tests/unit/domain/screening_assay/test_protocol_aliases.py`, `backend/tests/integration/test_protocol_aliases_persistence.py`, `backend/tests/api/test_protocol_nicknames.py`, `frontend/src/features/screening-assay/components/protocol-aliases-card.test.tsx`

**Interfaces:**
- Produces: `AliasKind(StrEnum)`: `FORMER = "former"`, `NICKNAME = "nickname"`; `ProtocolAlias(label: str, kind: AliasKind, recorded_at: datetime, reason: str | None = None)` (frozen dataclass in `protocol.py`); `Protocol.aliases: list[ProtocolAlias]` (kwarg `aliases: list[ProtocolAlias] | None = None`); `Protocol.add_nickname(label: str) -> None`; `Protocol.remove_nickname(label: str) -> None`. Task 12 adds former-name recording. Routes `POST /api/v1/protocols/{id}/nicknames {label}` and `DELETE /api/v1/protocols/{id}/nicknames?label=` return `ProtocolResponse`. `ProtocolResponse.aliases: list[ProtocolAliasResponse]`; `ProtocolSummaryResponse.aliases: list[str]`.

- [ ] **Step 1: Failing domain tests** (`backend/tests/unit/domain/screening_assay/test_protocol_aliases.py`)

```python
import uuid

import pytest

from cellar.domain.screening_assay.enums import AliasKind, ProtocolType
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import ConflictError, NotFoundError, ValidationError


def _protocol():
    pid = uuid.uuid4()
    return Protocol.create(
        workspace_id=uuid.uuid4(), name="M. tuberculosis growth inhibition [resazurin]",
        protocol_type=ProtocolType.WHOLE_CELL, created_by=uuid.uuid4(), code="PRT-00001",
        readout_definitions=[ReadoutDefinition(protocol_id=pid, name="Signal", data_type="numeric")],
    )


def test_add_nickname_normalizes_spacing():
    p = _protocol()
    p.add_nickname("  MABA   assay ")
    assert [(a.label, a.kind) for a in p.aliases] == [("MABA assay", AliasKind.NICKNAME)]


def test_duplicate_nickname_any_case_conflicts():
    p = _protocol()
    p.add_nickname("MABA")
    with pytest.raises(ConflictError):
        p.add_nickname("maba")


def test_nickname_equal_to_the_name_conflicts():
    with pytest.raises(ConflictError):
        _protocol().add_nickname("m. tuberculosis growth inhibition [resazurin]")


@pytest.mark.parametrize("bad", ["", "   ", "MABA · REMA", "x" * 401])
def test_bad_nicknames_rejected(bad):
    with pytest.raises(ValidationError):
        _protocol().add_nickname(bad)


def test_remove_nickname_any_case():
    p = _protocol()
    p.add_nickname("LORA")
    p.remove_nickname("lora")
    assert p.aliases == []


def test_remove_unknown_nickname_is_not_found():
    with pytest.raises(NotFoundError):
        _protocol().remove_nickname("REMA")
```

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_protocol_aliases.py -q` → FAIL (no `AliasKind`).

- [ ] **Step 2: Domain**

`enums.py`:

```python
class AliasKind(StrEnum):
    """Why a protocol answers to another name."""

    FORMER = "former"  # a name it had before a rename (recorded automatically)
    NICKNAME = "nickname"  # what people call it (MABA, LORA, HLM CLint)
```

`protocol.py` (beside `PickListValue`):

```python
_MAX_ALIAS_LENGTH = 400


@dataclass(frozen=True)
class ProtocolAlias:
    """Another name a protocol answers to. Searchable; never rendered as the name."""

    label: str
    kind: AliasKind
    recorded_at: datetime
    reason: str | None = None
```

`Protocol.__init__`: kwarg `aliases: list[ProtocolAlias] | None = None` and `self.aliases: list[ProtocolAlias] = list(aliases or [])`. Methods:

```python
    def add_nickname(self, label: str) -> None:
        """What people call this protocol. Cosmetic: allowed in any status, even locked."""
        validate_name_text(label, what="Nickname")
        cleaned = " ".join(label.split())
        if not cleaned:
            raise ValidationError("Nickname must not be empty")
        if len(cleaned) > _MAX_ALIAS_LENGTH:
            raise ValidationError(f"Nickname must be at most {_MAX_ALIAS_LENGTH} characters")
        key = cleaned.lower()
        if key == self.name.lower() or any(a.label.lower() == key for a in self.aliases):
            raise ConflictError(f"'{cleaned}' is already a name or alias of this protocol")
        self.aliases.append(ProtocolAlias(label=cleaned, kind=AliasKind.NICKNAME, recorded_at=datetime.now(UTC)))
        self.updated_at = datetime.now(UTC)

    def remove_nickname(self, label: str) -> None:
        key = " ".join(label.split()).lower()
        keep = [a for a in self.aliases if not (a.kind == AliasKind.NICKNAME and a.label.lower() == key)]
        if len(keep) == len(self.aliases):
            raise NotFoundError("Nickname", label)
        self.aliases = keep
        self.updated_at = datetime.now(UTC)
```

Imports: `from cellar.domain.shared.protocol_naming import validate_name_text`, `NotFoundError` from errors, `AliasKind` from enums. Check `NotFoundError`'s signature in `domain/shared/errors.py` and match it. Versioning service: pass `aliases=list(parent.aliases)` to the new `Protocol(...)`.

Run the domain tests → PASS.

- [ ] **Step 3: Persistence + migration**

`models.py` (after `ProtocolModel`):

```python
class ProtocolAliasModel(Base):
    __tablename__ = "protocol_aliases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("protocols.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(400), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    protocol: Mapped["ProtocolModel"] = relationship(back_populates="aliases")
    __table_args__ = (Index("ix_protocol_aliases_protocol", "protocol_id"),)
```

and on `ProtocolModel`:

```python
    aliases: Mapped[list["ProtocolAliasModel"]] = relationship(
        "ProtocolAliasModel", cascade="all, delete-orphan", lazy="selectin",
        order_by="ProtocolAliasModel.position", back_populates="protocol",
    )
```

Repository: `_to_domain` → `aliases=[ProtocolAlias(label=a.label, kind=AliasKind(a.kind), recorded_at=a.recorded_at, reason=a.reason) for a in model.aliases]`; `_to_model` and `_update_model` → `model.aliases = [ProtocolAliasModel(position=i, label=a.label, kind=a.kind.value, recorded_at=a.recorded_at, reason=a.reason) for i, a in enumerate(aggregate.aliases)]` (follow how readout definitions are rebuilt wholesale in `_update_model`).

Migration `083_protocol_aliases.py` (header as in 082, `down_revision = "082_protocol_code"`):

```python
def upgrade() -> None:
    op.create_table(
        "protocol_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("protocol_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(400), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_protocol_aliases_protocol", "protocol_aliases", ["protocol_id"])


def downgrade() -> None:
    op.drop_index("ix_protocol_aliases_protocol", table_name="protocol_aliases")
    op.drop_table("protocol_aliases")
```

`make migrate`. Integration test `backend/tests/integration/test_protocol_aliases_persistence.py`: save a protocol with two nicknames, reload in a fresh UoW, assert labels and order; remove one, save, reload, assert one left. Run with `DOCKER_HOST=... uv run pytest tests/integration/test_protocol_aliases_persistence.py -q`. Also run `uv run pytest tests/unit/cascade/test_fk_coverage.py -q` (the new FK column must pass the coverage check).

- [ ] **Step 4: Use cases, routes, DTOs**

`manage_protocol_aliases.py`:

```python
"""Nicknames: names people use for a protocol. Searchable; never the name."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from returns.result import Failure, Result, Success

from cellar.application.auth import AuthContext, require_editor, require_same_workspace
from cellar.application.shared.command import Command
from cellar.application.shared.event_dispatcher import EventDispatcherProtocol
from cellar.application.shared.unit_of_work import UnitOfWork
from cellar.domain.screening_assay.protocol import Protocol
from cellar.domain.screening_assay.repository import ProtocolRepository
from cellar.domain.shared.errors import DomainError, NotFoundError


@dataclass(frozen=True, kw_only=True)
class ProtocolNicknameCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    label: str


class _NicknameUseCase:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository, dispatcher: EventDispatcherProtocol) -> None:
        self._uow, self._repo, self._dispatcher = uow, repo, dispatcher

    def _apply(self, protocol: Protocol, label: str) -> None:
        raise NotImplementedError

    async def __call__(
        self, input: ProtocolNicknameCommand, auth: AuthContext | None = None
    ) -> Result[Protocol, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", input.protocol_id))
            self._apply(protocol, input.label)
            await self._repo.save(protocol)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all(events)
        return Success(protocol)


class AddProtocolNickname(_NicknameUseCase):
    def _apply(self, protocol: Protocol, label: str) -> None:
        protocol.add_nickname(label)


class RemoveProtocolNickname(_NicknameUseCase):
    def _apply(self, protocol: Protocol, label: str) -> None:
        protocol.remove_nickname(label)
```

(Domain errors raised by `add_nickname`/`remove_nickname` propagate to the global `DomainError` handler as 409/404/422, the same way `UpdateProtocol` lets `protocol.update(...)` raise.)

DI `_screening.py`: `container.define(AddProtocolNickname, _protocol_cmd(AddProtocolNickname))` and the same for `RemoveProtocolNickname`. Dependencies (`interface/dependencies/_screening.py`, add to `__all__`): `AddProtocolNicknameDep`, `RemoveProtocolNicknameDep`.

Routes in `protocols.py`:

```python
class ProtocolAliasResponse(BaseModel):
    label: str
    kind: str
    recorded_at: datetime
    reason: str | None = None


class AddNicknameRequest(BaseModel):
    label: str
    model_config = {"extra": "forbid"}


@router.post("/protocols/{protocol_id}/nicknames", response_model=ProtocolResponse, tags=["protocols"])
async def add_protocol_nickname(
    protocol_id: uuid.UUID, body: AddNicknameRequest, auth: AuthDep,
    targets_uc: ResolveProtocolTargetsDep, uc: AddProtocolNicknameDep,
) -> ProtocolResponse:
    cmd = ProtocolNicknameCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id, label=body.label)
    return await _protocol_response(targets_uc, auth, await uc(cmd, auth=auth))


@router.delete("/protocols/{protocol_id}/nicknames", response_model=ProtocolResponse, tags=["protocols"])
async def remove_protocol_nickname(
    protocol_id: uuid.UUID, auth: AuthDep, targets_uc: ResolveProtocolTargetsDep,
    uc: RemoveProtocolNicknameDep, label: str = Query(..., min_length=1),
) -> ProtocolResponse:
    cmd = ProtocolNicknameCommand(workspace_id=auth.workspace_id, protocol_id=protocol_id, label=label)
    return await _protocol_response(targets_uc, auth, await uc(cmd, auth=auth))
```

`ProtocolResponse.aliases: list[ProtocolAliasResponse] = []`, filled in `from_domain` from `p.aliases` (`kind=a.kind.value`). `ProtocolSummary.aliases: list[str] = field(default_factory=list)` set to `[a.label for a in p.aliases]`; `ProtocolSummaryResponse.aliases: list[str] = []`.

API test `backend/tests/api/test_protocol_nicknames.py`: create a protocol (POST /protocols as in Task 3's test), POST nickname `MABA` → 200 and `aliases[0] == {"label": "MABA", "kind": "nickname", ...}`; POST `maba` → 409; DELETE `?label=MABA` → 200 with `aliases == []`; `viewer_client` POST → 403.

```bash
cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_protocol_nicknames.py tests/integration/test_protocol_aliases_persistence.py -q
```

- [ ] **Step 5: Frontend card**

Regenerate orval + churn block. `types/index.ts`: `aliases: ProtocolResponse["aliases"];` on `Protocol`. Hooks in `use-protocols.ts` (follow `useSetOntologyAnnotation`'s style there):

```ts
export function useAddProtocolNickname(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (label: string) =>
      customInstance<Protocol>({ url: `${API_V1}/protocols/${protocolId}/nicknames`, method: "POST", data: { label } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Nickname added");
    },
    onError: (err: Error) => showError(err.message),
  });
}

export function useRemoveProtocolNickname(protocolId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (label: string) =>
      customInstance<Protocol>({ url: `${API_V1}/protocols/${protocolId}/nicknames`, method: "DELETE", params: { label } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROTOCOLS_KEY });
      showSuccess("Nickname removed");
    },
    onError: (err: Error) => showError(err.message),
  });
}
```

`protocol-aliases-card.tsx`:

```tsx
"use client";

import { Badge } from "@/shared/components/ui/badge";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/components/ui/card";
import { Input } from "@/shared/components/ui/input";
import { X } from "lucide-react";
import { useState } from "react";
import { useAddProtocolNickname, useRemoveProtocolNickname } from "../hooks/use-protocols";
import type { Protocol } from "../types";

interface ProtocolAliasesCardProps {
  protocol: Protocol;
  canEdit: boolean;
}

/** Names people use for a protocol (MABA, HLM CLint) plus the names it had before.
 *  Searchable everywhere; never rendered as the protocol's name. */
export function ProtocolAliasesCard({ protocol, canEdit }: ProtocolAliasesCardProps) {
  const [draft, setDraft] = useState("");
  const add = useAddProtocolNickname(protocol.id);
  const remove = useRemoveProtocolNickname(protocol.id);
  const aliases = protocol.aliases ?? [];
  const nicknames = aliases.filter((a) => a.kind === "nickname");
  const formers = aliases.filter((a) => a.kind === "former");

  return (
    <Card>
      <CardHeader>
        <CardTitle>Also known as</CardTitle>
        <CardDescription>Names people use for this protocol. They are searchable but never become its name.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-1">
          {nicknames.length === 0 && <p className="text-sm text-muted-foreground">No nicknames yet.</p>}
          {nicknames.map((a) => (
            <Badge key={a.label} variant="secondary" className="gap-1 pr-1">
              {a.label}
              {canEdit && (
                <button
                  type="button"
                  aria-label={`Remove ${a.label}`}
                  onClick={() => remove.mutate(a.label)}
                  className="rounded p-0.5 hover:bg-muted"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
        {canEdit && (
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const label = draft.trim();
              if (label) add.mutate(label, { onSuccess: () => setDraft("") });
            }}
          >
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="e.g. MABA, HLM CLint"
              aria-label="New nickname"
              className="max-w-xs"
            />
            <Button type="submit" variant="outline" size="sm" disabled={!draft.trim() || add.isPending}>
              Add
            </Button>
          </form>
        )}
        {formers.length > 0 && (
          <div className="text-sm text-muted-foreground">
            <p className="font-medium">Former names</p>
            <ul className="mt-1 space-y-0.5">
              {formers.map((a) => (
                <li key={`${a.label}-${a.recorded_at}`}>
                  {a.label}{" "}
                  <span className="text-xs">
                    (until {new Date(a.recorded_at).toLocaleDateString()}
                    {a.reason ? `, ${a.reason}` : ""})
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
```

In `overview-tab.tsx`, render `<ProtocolAliasesCard protocol={protocol} canEdit={canEdit} />` after the Details card, where `const canEdit = useAuthzHasRole("editor");` (import from `@duar-auth/nextjs`, as `protocol-detail.tsx` does).

Test `protocol-aliases-card.test.tsx` (mock `../hooks/use-protocols` returning `{ mutate: addMutate, isPending: false }` / `{ mutate: removeMutate }`): typing `"  MABA "` and clicking Add calls `addMutate` with `"MABA"`; clicking "Remove LORA" calls `removeMutate("LORA")`; a former alias renders under "Former names"; with `canEdit={false}` there is no input.

```bash
cd frontend && pnpm exec vitest run src/features/screening-assay/components/protocol-aliases-card.test.tsx && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/screening-assay
```

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/083_protocol_aliases.py backend/src/cellar/application/screening/manage_protocol_aliases.py backend/tests/unit/domain/screening_assay/test_protocol_aliases.py backend/tests/integration/test_protocol_aliases_persistence.py backend/tests/api/test_protocol_nicknames.py frontend/src/features/screening-assay/components/protocol-aliases-card.tsx frontend/src/features/screening-assay/components/protocol-aliases-card.test.tsx
git commit -m "feat(protocols): aliases (nicknames now, former names on rename)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/alembic/versions/083_protocol_aliases.py backend/tests frontend/src/features/screening-assay frontend/src/shared/lib/api
```

---

### Task 7: Search by code, alias, organism, cell line and condition values

**Files:**
- Modify: `frontend/src/features/screening-assay/lib/protocol-facets.ts`
- Modify: `frontend/src/features/screening-assay/components/{protocol-browser.tsx,grouped-protocol-list.tsx,protocol-library-row.tsx,protocol-grid.tsx}`
- Create: `frontend/src/features/screening-assay/components/protocol-option-label.tsx`
- Modify pickers: `frontend/src/features/research-organization/components/search/protocol-section.tsx` (haystack line ~127, row ~147, trigger ~703), `frontend/src/features/research-organization/components/criterion-rows/advanced-rows.tsx` (~85-90), `.../criterion-rows/structure-rows.tsx` (~213-226, ~260-273), `.../search/advanced-filters.tsx` (~123-126), `frontend/src/features/sar-analysis/components/{rgroup-color-control.tsx,scaffold-color-picker.tsx,color-mode-picker.tsx}`, `frontend/src/features/screen-campaign/components/{channel-popover.tsx,add-from-runs-dialog.tsx,sections/channels-section.tsx}`, `frontend/src/features/inventory/components/import-wizard.tsx` (~380-391)
- Test: `frontend/src/features/screening-assay/lib/protocol-facets.test.ts`

Cellar has no global protocol search (the command palette is static navigation, and `GET /protocols` has no text parameter): protocol search is the library filter, the grid quick filter and the pickers, all client-side over loaded protocols. This task covers exactly those.

**Interfaces:**
- Produces: `type ProtocolMatchField = "name" | "code" | "alias" | "target" | "organism" | "cell line" | "category" | "condition"`; `interface ProtocolTextMatch { field: ProtocolMatchField; value: string }`; `protocolTextMatch(p: Protocol, query: string): ProtocolTextMatch | null`; `matchesProtocolText(p, query): boolean` (unchanged signature); `<ProtocolOptionLabel code={...} name={...} />`. Task 17 adds `"discriminator"`.

- [ ] **Step 1: Failing tests** (add to `protocol-facets.test.ts`; reuse that file's protocol fixture builder, adding `code`, `aliases`, `condition_definitions`, `ontology_annotations`)

```ts
describe("protocolTextMatch", () => {
  const p = makeProtocol({
    name: "M. tuberculosis growth inhibition [resazurin]",
    code: "PRT-00142",
    aliases: [{ label: "MABA", kind: "nickname", recorded_at: "2026-10-08T00:00:00Z", reason: null }],
    ontology_annotations: {
      organism: [{ term_id: "t1", label: "Mycobacterium tuberculosis", ontology_source: "NCBITAXON", uri: null }],
    },
    condition_definitions: [
      { id: "c", name: "Genetic perturbation", data_type: "pick_list", unit: null, pick_list_values: [{ label: "SecA1 knockdown", color: null }] },
    ],
  });

  it.each([
    ["growth", "name"],
    ["prt-00142", "code"],
    ["maba", "alias"],
    ["mycobacterium", "organism"],
    ["seca1", "condition"],
  ])("matches %s on %s", (q, field) => {
    expect(protocolTextMatch(p, q)?.field).toBe(field);
  });

  it("returns null when nothing matches", () => {
    expect(protocolTextMatch(p, "luciferase")).toBeNull();
  });
});
```

(If the fixture builder does not exist, write `makeProtocol(overrides)` returning a full `Protocol` with sensible defaults; match `ConditionDefinition`'s actual type for `pick_list_values`.)

Run: `cd frontend && pnpm exec vitest run src/features/screening-assay/lib/protocol-facets.test.ts` → FAIL.

- [ ] **Step 2: Implement the matcher**

Replace `matchesProtocolText` in `protocol-facets.ts`:

```ts
export type ProtocolMatchField =
  | "name"
  | "code"
  | "alias"
  | "target"
  | "organism"
  | "cell line"
  | "category"
  | "condition";

export interface ProtocolTextMatch {
  field: ProtocolMatchField;
  value: string;
}

function termLabels(p: Protocol, slot: string): string[] {
  return (p.ontology_annotations?.[slot] ?? []).map((t) => t.label);
}

function conditionTexts(p: Protocol): string[] {
  return (p.condition_definitions ?? []).flatMap((c) => [
    c.name,
    ...(c.pick_list_values ?? []).map((v) => (typeof v === "string" ? v : v.label)),
  ]);
}

/** Which field a free-text query hits, in display priority. Null when none. */
export function protocolTextMatch(p: Protocol, query: string): ProtocolTextMatch | null {
  const q = query.trim().toLowerCase();
  if (!q) return { field: "name", value: p.name };
  const candidates: [ProtocolMatchField, string[]][] = [
    ["name", [p.name]],
    ["code", p.code ? [p.code] : []],
    ["alias", (p.aliases ?? []).map((a) => a.label)],
    ["target", p.targets.map((t) => t.name)],
    ["organism", termLabels(p, "organism")],
    ["cell line", termLabels(p, "cell_line")],
    ["category", p.category ? [p.category] : []],
    ["condition", conditionTexts(p)],
  ];
  for (const [field, values] of candidates) {
    const value = values.find((v) => v.toLowerCase().includes(q));
    if (value) return { field, value };
  }
  return null;
}

export function matchesProtocolText(p: Protocol, query: string): boolean {
  return protocolTextMatch(p, query) !== null;
}
```

Run the test → PASS.

- [ ] **Step 3: Show why a row matched**

- `protocol-browser.tsx`: keep `librarySource = protocols.filter((p) => matchesProtocolText(p, search))`; pass `search` down to the library view and on to `GroupedProtocolList` → `ProtocolLibraryRow` (add a `search?: string` prop at each level; read each component's props and thread it through).
- `protocol-library-row.tsx`: `const match = search ? protocolTextMatch(protocol, search) : null;` and after the name span: `{match && match.field !== "name" && <span className="ml-2 truncate text-xs text-muted-foreground">matched {match.field}: {match.value}</span>}`.
- `protocol-grid.tsx`: on the Name column add `getQuickFilterText: (p) => [p.data?.name, p.data?.code, ...(p.data?.aliases ?? []).map((a) => a.label)].join(" ")` (keep the existing Targets quick filter).

- [ ] **Step 4: Pickers show and search the code**

`protocol-option-label.tsx`:

```tsx
interface ProtocolOptionLabelProps {
  code?: string | null;
  name: string;
}

/** Protocol in a picker: the code first (stable, short), then the generated name. */
export function ProtocolOptionLabel({ code, name }: ProtocolOptionLabelProps) {
  return (
    <span className="flex min-w-0 items-baseline gap-2">
      {code && <span className="shrink-0 font-mono text-xs text-muted-foreground">{code}</span>}
      <span className="truncate">{name}</span>
    </span>
  );
}
```

Export it from `features/screening-assay/index.ts`. In each picker listed under Files, replace the item's `{p.name}` child with `<ProtocolOptionLabel code={p.code} name={p.name} />`. In `protocol-section.tsx` add `protocol.code` and `...(protocol.aliases ?? [])` to the haystack array at ~127 and render the label at ~147 and in the trigger at ~703. `advanced-filters.tsx` group label becomes `` `${p.code ?? ""} ${p.name}`.trim() ``.

- [ ] **Step 5: Verify and commit**

```bash
cd frontend && pnpm exec vitest run src/features && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features
git add frontend/src/features/screening-assay/components/protocol-option-label.tsx
git commit -m "feat(protocols): search by code, alias, organism, cell line and condition values

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/features
```

---

### Task 8: Cross-protocol formulas reference codes

**Files:**
- Modify: `backend/src/cellar/application/screening/cross_protocol_resolver.py`
- Modify: `backend/src/cellar/application/screening/readout_calculation_engine.py:49`
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` (remove `find_by_name`, add `find_latest_active_by_code`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py` (remove `find_by_name` at ~89-99, add the new method)
- Modify: `frontend/src/features/screening-assay/lib/formula-tokens.ts`, `components/formula-input.tsx`, `components/create-protocol-dialog.tsx` (~181-182, ~787), `components/detail-tabs/design-tab.tsx` (~93-99, 554, 634), `components/detail-tabs/readout-definition-dialog.tsx` (~702, ~871-881)
- Test: `backend/tests/unit/application/screening/test_cross_protocol_resolver.py` (rewrite expectations), `backend/tests/unit/application/screening/test_readout_calculation_engine.py` (~467-470), `frontend/src/features/screening-assay/lib/formula-tokens.test.ts` (new)

**Interfaces:**
- Produces: `ProtocolRepository.find_latest_active_by_code(workspace_id: uuid.UUID, code: str) -> AssayProtocol | None`; resolver binding key `binding_key(code, readout) -> str` = `re.sub(r"\W", "_", f"{code}__{readout}")`; formula syntax `@{PRT-00142}.{IC50}` or `@PRT-00142.IC50`. Frontend `buildSuggestions(token, readoutNames, protocols: readonly { code: string; name: string }[])`; `FormulaInput` prop `protocols?: readonly { code: string; name: string }[]` replaces `protocolNames`.
- Note: the resolver has no runtime consumer today (only DI and tests; the engine skips cross-protocol formulas). Wiring it into calculation is out of scope.

- [ ] **Step 1: Rewrite the resolver tests**

In `test_cross_protocol_resolver.py` switch every reference from names to codes and every `find_by_name` mock to `find_latest_active_by_code`:

```python
async def test_resolves_by_code(...):
    resolver, protocol_repo, readout_repo = _make_resolver(...)
    protocol_repo.find_latest_active_by_code.return_value = active_protocol  # readout "IC50"
    result = await resolver.resolve(WS, MOL, "@{PRT-00142}.{IC50} * 2")
    protocol_repo.find_latest_active_by_code.assert_awaited_once_with(WS, "PRT-00142")
    assert result.unwrap() == {"PRT_00142__IC50": 1.5}


def test_rewrite_formula_uses_identifier_safe_keys():
    assert CrossProtocolResolver.rewrite_formula("@{PRT-00142}.{IC50 nM} + @PRT-00007.Raw") == "PRT_00142__IC50_nM + PRT_00007__Raw"


def test_names_are_no_longer_references():
    assert CrossProtocolResolver._extract_refs("@{Target Assay}.IC50") == []
```

(Adapt to the file's existing helper names and to whether `rewrite_formula`/`_extract_refs` are static; keep their call style.) In `test_readout_calculation_engine.py:467-470` use `"@{PRT-00001}.IC50 * Raw"`.

Run: `cd backend && uv run pytest tests/unit/application/screening/test_cross_protocol_resolver.py tests/unit/application/screening/test_readout_calculation_engine.py -q` → FAIL.

- [ ] **Step 2: Implement**

Resolver:

```python
_CODE = r"[A-Z]{2,8}-\d+"
# @{PRT-00142}.{IC50 nM} or @PRT-00142.IC50. Groups: (braced code, bare code, braced readout, bare readout)
_REF_RE = re.compile(rf"@(?:\{{({_CODE})\}}|({_CODE}))\.(?:\{{([^}}]+)\}}|(\w+))")


def binding_key(code: str, readout: str) -> str:
    """asteval identifier for a reference: PRT-00142 + IC50 nM -> PRT_00142__IC50_nM."""
    return re.sub(r"\W", "_", f"{code}__{readout}")
```

`_resolve_refs`: `protocol = await self._protocol_repo.find_latest_active_by_code(workspace_id, code)`; failure message `f"Protocol {code} has no active version"`; key `binding_key(code, readout_name)`. `rewrite_formula` substitutes `binding_key(...)` for each match. Update the module docstring to the code syntax.

Repository (domain protocol + implementation; delete `find_by_name` from both and from any test fake that implements it: `grep -rn "find_by_name" backend/src/cellar/domain/screening_assay backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay backend/tests`):

```python
    async def find_latest_active_by_code(self, workspace_id: uuid.UUID, code: str) -> Protocol | None:
        stmt = (
            select(ProtocolModel)
            .where(
                ProtocolModel.workspace_id == workspace_id,
                ProtocolModel.code == code,
                ProtocolModel.status == ProtocolStatus.ACTIVE.value,
            )
            .order_by(ProtocolModel.protocol_version.desc())
            .limit(1)
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return self._to_domain_tracked(model) if model else None
```

(Use the same "map + track" helper the repo's other finders use.) Engine line 49: `_CROSS_PROTOCOL_RE = re.compile(r"@\{?[A-Z]{2,8}-\d+\}?\.")`.

Run the backend tests → PASS. Also `uv run pytest tests/unit -q -x`.

- [ ] **Step 3: Frontend tokens**

`formula-tokens.ts`:
- `const CROSS_PROTOCOL_RE = /@\{?[A-Z]{2,8}-\d+\}?\.(?:\{[^}]+\}|\w+)/g;` (update the "mirrored from" comment).
- In `tokenAtCursor`: `const atMatch = before.match(/@[\w-]*$/);`.
- `buildSuggestions(token, readoutNames, protocols: readonly ProtocolRef[])` with `export interface ProtocolRef { code: string; name: string }`; the `@protocol` branch:

```ts
  if (token.kind === "@protocol") {
    const partial = token.raw.slice(1).toLowerCase();
    const matches = protocols.filter(
      (p) => p.code.toLowerCase().includes(partial) || p.name.toLowerCase().includes(partial),
    );
    return matches.slice(0, MAX_SUGGESTIONS).map((p) => ({
      value: `@{${p.code}}.`,
      kind: "protocol",
      hint: p.name,
    }));
  }
```

`formula-input.tsx`: prop `protocols?: readonly ProtocolRef[]` (default `[]`) passed to `buildSuggestions`. Callers: `create-protocol-dialog.tsx` builds `crossProtocols = useMemo(() => (allProtocols ?? []).filter((p) => p.code).map((p) => ({ code: p.code as string, name: p.name })), [allProtocols])`; `design-tab.tsx` the same (excluding the current protocol); `readout-definition-dialog.tsx` renames its `protocolNames` prop to `protocols` and forwards it.

`formula-tokens.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { buildSuggestions, tokenAtCursor, validateFormula } from "./formula-tokens";

const protocols = [{ code: "PRT-00142", name: "PptT inhibition [FP]" }];

describe("cross-protocol references by code", () => {
  it("suggests by name and inserts the code", () => {
    const token = tokenAtCursor("@ppt", 4);
    expect(buildSuggestions(token, [], protocols)).toEqual([{ value: "@{PRT-00142}.", kind: "protocol", hint: "PptT inhibition [FP]" }]);
  });

  it("keeps the token while typing a code with a hyphen", () => {
    expect(tokenAtCursor("@PRT-001", 8).kind).toBe("@protocol");
  });

  it("does not flag code references as unknown identifiers", () => {
    expect(validateFormula("@{PRT-00142}.{IC50} * Raw", ["Raw"]).unknownIdentifiers).toEqual([]);
  });
});
```

(Check `validateFormula`'s exported name and signature in the file and match it.)

```bash
cd frontend && pnpm exec vitest run src/features/screening-assay/lib/formula-tokens.test.ts && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/screening-assay
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/screening-assay/lib/formula-tokens.test.ts
git commit -m "feat(formulas): cross-protocol references use protocol codes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar/application/screening backend/src/cellar/domain/screening_assay/repository.py backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/protocol_repository.py backend/tests frontend/src/features/screening-assay
```

---

### Task 9: Cell line facet

**Files:**
- Modify: `frontend/src/features/screening-assay/hooks/use-protocol-facet-slots.ts`
- Modify: `frontend/src/features/screening-assay/lib/protocol-facets.ts` (`FacetDimension`, `FACET_DIMENSIONS`, `ONTOLOGY_SLOTS`)
- Modify (local, gitignored): `backend/data/vault-protocols/curated/load_curated.py` (`SLOTS`)
- Test: `frontend/src/features/screening-assay/lib/protocol-facets.test.ts`, `frontend/src/features/screening-assay/components/detail-tabs/design-tab-protocol-card.test.tsx`

**Interfaces:**
- Produces: standard facet slot `{ name: "cell_line", label: "Cell line", ontology_sources: ["CLO", "CL"] }`; facet dimension `"cell_line"` labelled "Cell line". Annotation slot key `cell_line` is what the naming service reads (Task 13).

- [ ] **Step 1: Failing tests**

In `design-tab-protocol-card.test.tsx` extend the standard-facets test: `expect(screen.getByText("Cell line")).toBeInTheDocument();`. In `protocol-facets.test.ts`: a protocol with `ontology_annotations.cell_line = [{ term_id: "c1", label: "HepG2 cell", ontology_source: "CLO", uri: null }]` yields `extractFacetItems(p, "cell_line")` → `[{ value: "c1", label: "HepG2 cell" }]`.

Run both → FAIL.

- [ ] **Step 2: Implement**

`use-protocol-facet-slots.ts` `STANDARD_FACET_SLOTS`: insert `{ name: "cell_line", label: "Cell line", ontology_sources: ["CLO", "CL"] }` after `organism`. `protocol-facets.ts`: add `"cell_line"` to `FacetDimension`, `{ dimension: "cell_line", label: "Cell line" }` after Organism in `FACET_DIMENSIONS`, and `cell_line: "cell_line"` in `ONTOLOGY_SLOTS`. In `load_curated.py` add `("cell_line", "Cell line", ["CLO", "CL"], None, True)` to `SLOTS` after organism (not committed; `backend/data/` is gitignored).

- [ ] **Step 3: Verify and commit**

```bash
cd frontend && pnpm exec vitest run src/features/screening-assay && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/screening-assay
git commit -m "feat(protocols): Cell line facet (CLO, CL)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/features/screening-assay
```

---

# Part 2: Naming

### Task 10: Protocol categories with name patterns

**Files:**
- Create: `backend/src/cellar/domain/workspace_config/protocol_category.py`
- Modify: `backend/src/cellar/domain/workspace_config/{events.py,repository.py}`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/models.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/protocol_category_repository.py`
- Create: `backend/alembic/versions/084_protocol_categories.py`
- Create: `backend/src/cellar/application/workspace_config/protocol_categories.py`
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` + implementation (`count_by_category`)
- Modify: `backend/src/cellar/infrastructure/di/_workspace_config.py`, `backend/src/cellar/interface/dependencies/_workspace_config.py`
- Create: `backend/src/cellar/interface/routes/protocol_categories.py`; modify `backend/src/cellar/interface/app.py` (include router)
- Create: `frontend/src/features/workspace-config/hooks/use-protocol-categories.ts`, `frontend/src/features/workspace-config/components/protocol-category-admin.tsx`, `frontend/src/app/(dashboard)/admin/protocol-categories/page.tsx`
- Modify: `frontend/src/shared/lib/navigation.ts`, `frontend/src/features/workspace-config/types/index.ts`, `frontend/src/features/screening-assay/components/protocol-category-input.tsx`
- Modify (local): `backend/data/vault-protocols/curated/load_curated.py` (`ensure_workspace_config` seeds categories instead of the vocabulary)
- Test: `backend/tests/unit/domain/workspace_config/test_protocol_category.py`, `backend/tests/api/test_protocol_categories.py`, `frontend/src/features/screening-assay/components/protocol-category-input.test.tsx`

**Interfaces:**
- Produces: `ProtocolCategory(AggregateRoot)` with `workspace_id`, `label`, `name_pattern`, `create(*, workspace_id, label, name_pattern=None)` (defaults to the shipped pattern or `generic_pattern(label)`), `update(*, label=None, name_pattern=None)`, property `default_pattern`; events `ProtocolCategoryCreated(label)`, `ProtocolCategoryUpdated(label, name_pattern)`. `ProtocolCategoryRepository`: `find_by_id_in_workspace`, `find_by_workspace` (ordered by label), `find_by_label(workspace_id, label)` (case-insensitive), `save`, `delete`. `ProtocolRepository.count_by_category(workspace_id, label) -> int`. Use cases: `ListProtocolCategories` (viewer), `CreateProtocolCategory`, `UpdateProtocolCategory`, `DeleteProtocolCategory`, `SeedDefaultProtocolCategories` (admin). Routes under `/api/v1/protocol-categories`: `GET ""`, `POST ""`, `PATCH "/{id}"`, `DELETE "/{id}"`, `POST "/defaults"`. Response `ProtocolCategoryResponse { id, label, name_pattern, default_pattern, version }`.
- Task 19 changes `UpdateProtocolCategory` and `DeleteProtocolCategory` to relabel/preview; in this task they apply directly (names are not generated until Task 14).

- [ ] **Step 1: Failing domain tests**

```python
import uuid

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.protocol_category import ProtocolCategory

WS = uuid.uuid4()


def test_create_uses_the_shipped_pattern():
    c = ProtocolCategory.create(workspace_id=WS, label="Cytotoxicity")
    assert c.name_pattern == "{cell_line} cytotoxicity" == c.default_pattern


def test_create_new_category_gets_the_generic_pattern():
    assert ProtocolCategory.create(workspace_id=WS, label="Biofilm inhibition").name_pattern == "{subject?} biofilm inhibition"


def test_update_validates_the_pattern():
    c = ProtocolCategory.create(workspace_id=WS, label="Cytotoxicity")
    with pytest.raises(ValidationError):
        c.update(name_pattern="{cellline} cytotoxicity")


@pytest.mark.parametrize("bad", ["", "  ", "Cyto · toxicity"])
def test_label_rules(bad):
    with pytest.raises(ValidationError):
        ProtocolCategory.create(workspace_id=WS, label=bad)


def test_events():
    c = ProtocolCategory.create(workspace_id=WS, label="Binding")
    assert [type(e).__name__ for e in c.collect_events()] == ["ProtocolCategoryCreated"]
```

Run → FAIL (module missing).

- [ ] **Step 2: Domain**

`protocol_category.py`:

```python
"""ProtocolCategory: a protocol category and the pattern its protocol names follow."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from cellar.domain.shared.entity import AggregateRoot
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.protocol_naming import (
    DEFAULT_CATEGORY_PATTERNS,
    generic_pattern,
    validate_name_text,
    validate_pattern,
)
from cellar.domain.workspace_config.events import ProtocolCategoryCreated, ProtocolCategoryUpdated

_MAX_LABEL_LENGTH = 100


def _clean_label(label: str) -> str:
    if not label or not label.strip():
        raise ValidationError("Category label must not be empty")
    validate_name_text(label, what="Category label")
    cleaned = " ".join(label.split())
    if len(cleaned) > _MAX_LABEL_LENGTH:
        raise ValidationError(f"Category label must be at most {_MAX_LABEL_LENGTH} characters")
    return cleaned


class ProtocolCategory(AggregateRoot):
    def __init__(
        self,
        *,
        id: uuid.UUID | None = None,
        workspace_id: uuid.UUID,
        label: str,
        name_pattern: str,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        version: int = 1,
    ) -> None:
        super().__init__(id=id, created_at=created_at, updated_at=updated_at, version=version)
        self.workspace_id = workspace_id
        self.label = _clean_label(label)
        validate_pattern(name_pattern)
        self.name_pattern = name_pattern.strip()

    @classmethod
    def create(cls, *, workspace_id: uuid.UUID, label: str, name_pattern: str | None = None) -> ProtocolCategory:
        cleaned = _clean_label(label)
        pattern = name_pattern or DEFAULT_CATEGORY_PATTERNS.get(cleaned) or generic_pattern(cleaned)
        category = cls(workspace_id=workspace_id, label=cleaned, name_pattern=pattern)
        category.register_event(
            ProtocolCategoryCreated(
                aggregate_id=category.id, aggregate_type="ProtocolCategory", workspace_id=workspace_id, label=cleaned
            )
        )
        return category

    @property
    def default_pattern(self) -> str:
        return DEFAULT_CATEGORY_PATTERNS.get(self.label) or generic_pattern(self.label)

    def update(self, *, label: str | None = None, name_pattern: str | None = None) -> None:
        if label is not None:
            self.label = _clean_label(label)
        if name_pattern is not None:
            validate_pattern(name_pattern)
            self.name_pattern = name_pattern.strip()
        self.updated_at = datetime.now(UTC)
        self.register_event(
            ProtocolCategoryUpdated(
                aggregate_id=self.id, aggregate_type="ProtocolCategory", workspace_id=self.workspace_id,
                label=self.label, name_pattern=self.name_pattern,
            )
        )
```

`events.py` (new banner `# --- Protocol Categories ---`):

```python
@dataclass(frozen=True, kw_only=True)
class ProtocolCategoryCreated(DomainEvent):
    label: str


@dataclass(frozen=True, kw_only=True)
class ProtocolCategoryUpdated(DomainEvent):
    label: str
    name_pattern: str
```

`repository.py`: `ProtocolCategoryRepository(Protocol)` with the methods listed in Interfaces (copy the `ControlledVocabularyRepository` shape; `find_by_label` replaces `find_by_name`).

Run the domain tests → PASS.

- [ ] **Step 3: Persistence + migration**

Model (in `workspace_config/models.py`):

```python
class ProtocolCategoryModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin):
    __tablename__ = "protocol_categories"
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    name_pattern: Mapped[str] = mapped_column(String(400), nullable=False)
    __table_args__ = (Index("uq_protocol_category_ws_label", "workspace_id", func.lower(label), unique=True),)
```

(If a functional index in `__table_args__` is awkward with the mapped column, declare it only in the migration and leave a comment on the model.)

Repository `protocol_category_repository.py`: copy `controlled_vocabulary_repository.py`; `find_by_label` uses `func.lower(ProtocolCategoryModel.label) == label.strip().lower()`; `find_by_workspace` orders by label.

Migration `084_protocol_categories.py` (`down_revision = "083_protocol_aliases"`): create the table (columns as in `064_kiosk_devices.py`: id, workspace_id, label, name_pattern, created_at, updated_at, version), the unique functional index `CREATE UNIQUE INDEX uq_protocol_category_ws_label ON protocol_categories (workspace_id, lower(label))`, then convert the "Protocol Categories" vocabulary:

```python
DEFAULT_PATTERNS = {  # copy of DEFAULT_CATEGORY_PATTERNS at the time of this migration
    "Enzyme inhibition": "{target} inhibition",
    "Enzyme activation": "{target} activation",
    "Binding": "{target} binding",
    "Receptor function": "{target} {discriminator}",
    "Ion-channel inhibition": "{target} inhibition",
    "Growth inhibition": "{organism} growth inhibition",
    "Bactericidal activity": "{organism} bactericidal activity",
    "Intracellular growth inhibition": "Intracellular {organism} growth inhibition",
    "Metabolite rescue": "{organism} metabolite rescue",
    "Membrane potential": "{organism} membrane potential",
    "Resistance selection": "{organism?} resistant mutant selection",
    "Combination (checkerboard)": "{subject?} combination",
    "Cytotoxicity": "{cell_line} cytotoxicity",
    "Infection inhibition": "{organism} infection inhibition",
    "In vitro translation inhibition": "{organism} in vitro translation inhibition",
    "Intrabacterial pH homeostasis": "{organism} intrabacterial pH disruption",
    "Detection interference": "{discriminator} interference",
    "Metabolic stability": "{matrix} stability",
    "Plasma stability": "Plasma stability",
    "Plasma protein binding": "Plasma protein binding",
    "Permeability": "{cell_line?} permeability",
    "Solubility": "{discriminator?} solubility",
    "Lipophilicity": "Lipophilicity",
    "Pharmacokinetics": "{organism?} pharmacokinetics",
    "In vivo efficacy": "{organism} in vivo efficacy",
    "Compound identity / purity": "Compound identity and purity",
    "Prediction": "{subject?} {discriminator} prediction",
}


def upgrade() -> None:
    op.create_table(
        "protocol_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("name_pattern", sa.String(400), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_protocol_categories_workspace_id", "protocol_categories", ["workspace_id"])
    op.execute("CREATE UNIQUE INDEX uq_protocol_category_ws_label ON protocol_categories (workspace_id, lower(label))")
    conn = op.get_bind()
    rows = conn.execute(sa.text("select workspace_id, terms from controlled_vocabularies where name = 'Protocol Categories'")).all()
    for workspace_id, terms in rows:
        for label in terms:
            pattern = DEFAULT_PATTERNS.get(label) or "{subject?} " + label[:1].lower() + label[1:]
            conn.execute(
                sa.text(
                    "insert into protocol_categories (id, workspace_id, label, name_pattern, created_at, updated_at, version) "
                    "values (gen_random_uuid(), :ws, :label, :pattern, now(), now(), 1)"
                ),
                {"ws": workspace_id, "label": label, "pattern": pattern},
            )
    conn.execute(sa.text("delete from controlled_vocabularies where name = 'Protocol Categories'"))
```

(Migrations must not import application code; the pattern table is copied verbatim on purpose.) `downgrade()` drops the index and table (the vocabulary is not recreated; say so in a comment).

`make migrate`; check `select count(*) from protocol_categories` on the dev DB is 27 for SACLAB-DEV.

- [ ] **Step 4: Use cases**

`application/workspace_config/protocol_categories.py` with commands `ListProtocolCategoriesQuery(workspace_id)`, `CreateProtocolCategoryCommand(workspace_id, label, name_pattern: str | None = None)`, `UpdateProtocolCategoryCommand(workspace_id, category_id, label: str | None = None, name_pattern: str | None = None)`, `DeleteProtocolCategoryCommand(workspace_id, category_id)`, `SeedDefaultProtocolCategoriesCommand(workspace_id)`. Each follows the `CreateVocabulary` shape (guards, UoW, commit, dispatch):
- Create: `require_admin`; `find_by_label` → `Failure(ConflictError(f"Category '{label}' already exists"))`.
- Update: `require_admin`; NotFound; if the label changes and another category has it → Conflict.
- Delete: `require_admin`; NotFound; `if await protocol_repo.count_by_category(ws, category.label) > 0: return Failure(ConflictError(f"{n} protocols use '{label}'; move them to another category first"))`.
- Seed: `require_admin`; for each `DEFAULT_CATEGORY_PATTERNS` label not present (`find_by_label`), create it; return the full list.
- List: `require_workspace_role(auth, "viewer")`.

`ProtocolRepository.count_by_category(workspace_id, label) -> int`: `select count(*) from protocols where workspace_id = :ws and lower(category) = lower(:label)`.

DI: the protocol-touching use cases (`DeleteProtocolCategory`) get `SQLAlchemyProtocolRepository(uow)` from the same UoW. Dependencies + `__all__`.

- [ ] **Step 5: Routes + API tests**

`interface/routes/protocol_categories.py` (copy `vocabularies.py`): `router = APIRouter(prefix="/api/v1/protocol-categories", tags=["protocol-categories"])`, `ProtocolCategoryResponse(id, workspace_id, label, name_pattern, default_pattern, version)` with `from_domain`, bodies `CreateProtocolCategoryBody(label, name_pattern: str | None = None)`, `UpdateProtocolCategoryBody(label: str | None = None, name_pattern: str | None = None)`, endpoints as in Interfaces (`POST /defaults` returns `list[ProtocolCategoryResponse]`). Include the router in `app.py` next to `vocab_router`.

`backend/tests/api/test_protocol_categories.py`: POST `/defaults` → 27 rows; POST `{"label": "Biofilm inhibition"}` → 201 with the generic pattern; duplicate label (any case) → 409; PATCH bad pattern → 422; DELETE a category used by a protocol (create one with `category: "Cytotoxicity"`) → 409; `editor_client` POST → 403; `viewer_client` GET → 200.

```bash
cd backend && uv run pytest tests/unit/domain/workspace_config -q && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_protocol_categories.py -q
```

- [ ] **Step 6: Frontend**

Regenerate orval + churn. Types: `export type ProtocolCategory = ProtocolCategoryResponse;` (+ create/update body aliases). Hook `use-protocol-categories.ts`:

```ts
const categoryHooks = createCrudHooks<ProtocolCategory, CreateProtocolCategoryInput, UpdateProtocolCategoryInput>({
  entityName: "Category",
  baseUrl: `${API_V1}/protocol-categories`,
  queryKey: ["protocol-categories"],
});
export const useProtocolCategories = categoryHooks.useList;
export const useCreateProtocolCategory = categoryHooks.useCreate;
export const useUpdateProtocolCategory = categoryHooks.useUpdate;
export const useDeleteProtocolCategory = categoryHooks.useDelete;

export function useSeedDefaultProtocolCategories() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => customInstance<ProtocolCategory[]>({ url: `${API_V1}/protocol-categories/defaults`, method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["protocol-categories"] });
      showSuccess("Default categories added");
    },
    onError: (err: Error) => showError(err.message),
  });
}
```

`protocol-category-admin.tsx` (follow `vocabulary-list.tsx` + `vocabulary-dialog.tsx`): `PageHeader` "Protocol categories" with subtitle "Each category's pattern builds the names of its protocols.", buttons "Add category" and "Add default categories" (`useSeedDefaultProtocolCategories`); table columns Label / Name pattern (mono) / Default (shows "custom" badge when `name_pattern !== default_pattern`) / actions (Edit, Delete). Dialog fields: Label, Name pattern, a slot legend listing `{target} {organism} {cell_line} {matrix} {subject} {discriminator}` with one-line meanings and "add ? to make a slot optional", and a "Reset to default" button that sets the pattern field to `default_pattern`. Empty state: "No categories yet. Add the default categories to start." Page `app/(dashboard)/admin/protocol-categories/page.tsx` renders `<ProtocolCategoryAdmin />`. Navigation: under the "Vocabularies" group add `{ title: "Protocol Categories", href: "/admin/protocol-categories", icon: BookOpen, requires: "admin" }`.

`protocol-category-input.tsx`: read labels from `useProtocolCategories()` instead of the vocabulary (`const labels = (data ?? []).map((c) => c.label)`); keep the off-list behaviour; remove `PROTOCOL_CATEGORIES_VOCABULARY` and its import of `useVocabularyTerms`. `protocol-category-input.test.tsx`: mocks `useProtocolCategories` with two categories; the select lists both; an off-list value ("Enzyme Assay") stays visible; with no categories it renders the autocomplete fallback.

Update `load_curated.py` `ensure_workspace_config` to call `SeedDefaultProtocolCategories` instead of creating the vocabulary (not committed).

```bash
cd frontend && pnpm exec vitest run src/features && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features src/app src/shared/lib/navigation.ts
```

- [ ] **Step 7: Commit**

```bash
git add backend/src/cellar/domain/workspace_config/protocol_category.py backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/protocol_category_repository.py backend/alembic/versions/084_protocol_categories.py backend/src/cellar/application/workspace_config/protocol_categories.py backend/src/cellar/interface/routes/protocol_categories.py backend/tests/unit/domain/workspace_config/test_protocol_category.py backend/tests/api/test_protocol_categories.py "frontend/src/app/(dashboard)/admin/protocol-categories/page.tsx" frontend/src/features/workspace-config/hooks/use-protocol-categories.ts frontend/src/features/workspace-config/components/protocol-category-admin.tsx frontend/src/features/screening-assay/components/protocol-category-input.test.tsx
git commit -m "feat(protocols): protocol categories carry admin-editable name patterns

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/alembic/versions/084_protocol_categories.py backend/tests frontend/src
```

---

### Task 11: Short labels

**Files:**
- Create: `backend/src/cellar/domain/workspace_config/naming_label.py`
- Modify: `backend/src/cellar/domain/workspace_config/{events.py,repository.py}`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/models.py`
- Create: `backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/naming_label_repository.py`
- Create: `backend/alembic/versions/085_naming_labels.py`
- Create: `backend/src/cellar/application/workspace_config/naming_labels.py`
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` + implementation (`list_annotation_terms`), `TargetRepository` + implementation (`list_organisms`)
- Create: `backend/src/cellar/interface/routes/naming_labels.py`; modify `app.py`, DI, dependencies
- Create: `frontend/src/features/workspace-config/hooks/use-naming-labels.ts`, `frontend/src/features/workspace-config/components/naming-label-admin.tsx`, `frontend/src/app/(dashboard)/admin/naming-labels/page.tsx`
- Modify: `frontend/src/shared/lib/navigation.ts`, `frontend/src/features/workspace-config/types/index.ts`
- Test: `backend/tests/unit/domain/workspace_config/test_naming_label.py`, `backend/tests/api/test_naming_labels.py`, `frontend/src/features/workspace-config/components/naming-label-admin.test.tsx`

**Interfaces:**
- Produces: `NamingLabel(AggregateRoot)`: `workspace_id`, `term_id`, `term_label`, `ontology_source`, `short_label`; `create(*, workspace_id, term_id, term_label, ontology_source, short_label)`; `update(*, short_label)`; events `NamingLabelCreated(term_id)`, `NamingLabelUpdated(term_id, short_label)`. `NamingLabelRepository`: `find_by_id_in_workspace`, `find_by_workspace`, `find_by_term(workspace_id, term_id)`, `save`, `delete`. `ProtocolRepository.list_annotation_terms(workspace_id, slots: Sequence[str]) -> list[AnnotationTermUse]` where `AnnotationTermUse(slot: str, term_id: str, label: str, ontology_source: str, protocol_count: int)` (domain dataclass in `repository.py`). `TargetRepository.list_organisms(workspace_id) -> list[str]` (distinct non-null organisms of mirrored targets). Use cases `ListNamingLabels`, `ListNamingTermsInUse` (viewer), `CreateNamingLabel`, `UpdateNamingLabel`, `DeleteNamingLabel` (admin; relabel added in Task 19). Routes `/api/v1/naming-labels` (`GET`, `POST`, `PATCH /{id}`, `DELETE /{id}`) and `GET /api/v1/naming-labels/terms-in-use` → `list[NamingTermInUseResponse { slot, term_id, term_label, ontology_source, protocol_count, default_short_label, override_id, override_short_label }]`.

- [ ] **Step 1: Failing domain tests**

```python
import uuid

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.naming_label import NamingLabel

MTB = "http://purl.bioontology.org/ontology/NCBITAXON/1773"


def _label(short="Mtb"):
    return NamingLabel.create(
        workspace_id=uuid.uuid4(), term_id=MTB, term_label="Mycobacterium tuberculosis",
        ontology_source="NCBITAXON", short_label=short,
    )


def test_create_and_update():
    label = _label()
    label.update(short_label="  M.  tb ")
    assert label.short_label == "M. tb"


@pytest.mark.parametrize("bad", ["", "  ", "Mtb · H37Rv", "x" * 61])
def test_short_label_rules(bad):
    with pytest.raises(ValidationError):
        _label(short=bad)
```

Run → FAIL.

- [ ] **Step 2: Domain** (`naming_label.py`, same shape as `ProtocolCategory`):

```python
_MAX_SHORT_LABEL = 60


def _clean_short_label(value: str) -> str:
    if not value or not value.strip():
        raise ValidationError("Short label must not be empty")
    validate_name_text(value, what="Short label")
    cleaned = " ".join(value.split())
    if len(cleaned) > _MAX_SHORT_LABEL:
        raise ValidationError(f"Short label must be at most {_MAX_SHORT_LABEL} characters")
    return cleaned
```

`__init__(*, id=None, workspace_id, term_id, term_label, ontology_source, short_label, created_at=None, updated_at=None, version=1)` validating `term_id`/`term_label` non-empty and cleaning `short_label`; `create(...)` registers `NamingLabelCreated`; `update(*, short_label)` registers `NamingLabelUpdated`. Events in `events.py` under `# --- Naming Labels ---`. Repository protocol `NamingLabelRepository`.

- [ ] **Step 3: Persistence + migration**

`NamingLabelModel(Base, EntityModelMixin, WorkspaceIdMixin, VersionMixin)`, table `naming_labels`: `term_id String(300)`, `term_label String(300)`, `ontology_source String(40)`, `short_label String(60)`, `UniqueConstraint("workspace_id", "term_id", name="uq_naming_label_ws_term")`. Migration `085_naming_labels.py` (`down_revision = "084_protocol_categories"`) creates it (copy the 064 column block). `make migrate`.

`list_annotation_terms` (protocol repository):

```python
    async def list_annotation_terms(self, workspace_id: uuid.UUID, slots: Sequence[str]) -> list[AnnotationTermUse]:
        rows = (
            await self._session.execute(
                text(
                    """
                    select a.key as slot, t->>'term_id' as term_id, min(t->>'label') as label,
                           min(t->>'ontology_source') as source, count(distinct p.id) as n
                    from protocols p
                    cross join lateral jsonb_each(p.ontology_annotations) as a(key, terms)
                    cross join lateral jsonb_array_elements(a.terms) as t
                    where p.workspace_id = :ws and jsonb_typeof(p.ontology_annotations) = 'object'
                      and a.key = any(:slots)
                    group by a.key, t->>'term_id'
                    order by a.key, min(t->>'label')
                    """
                ),
                {"ws": workspace_id, "slots": list(slots)},
            )
        ).all()
        return [AnnotationTermUse(slot=r.slot, term_id=r.term_id, label=r.label, ontology_source=r.source, protocol_count=r.n) for r in rows]
```

`TargetRepository.list_organisms`: `select distinct organism from targets where workspace_id = :ws and organism is not null order by 1`.

- [ ] **Step 4: Use cases + routes**

`naming_labels.py`: CRUD as for categories (`require_admin` for writes; Create returns Conflict if `find_by_term` exists). `ListNamingTermsInUse`:

```python
class ListNamingTermsInUse:
    """Every term a protocol name can draw on, with the short label it renders as."""

    def __init__(self, uow: UnitOfWork, protocol_repo: ProtocolRepository, target_repo: TargetRepository, label_repo: NamingLabelRepository) -> None: ...

    async def __call__(self, input: ListNamingTermsInUseQuery, auth: AuthContext | None = None) -> Result[list[NamingTermInUse], DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            uses = await self._protocol_repo.list_annotation_terms(input.workspace_id, ("organism", "cell_line", "assay_format"))
            organisms = await self._target_repo.list_organisms(input.workspace_id)
            overrides = {l.term_id: l for l in await self._label_repo.find_by_workspace(input.workspace_id)}
        empty = NamingContext()
        out = [
            NamingTermInUse(
                slot=u.slot, term_id=u.term_id, term_label=u.label, ontology_source=u.ontology_source,
                protocol_count=u.protocol_count,
                default_short_label=short_label(NamingTerm(u.term_id, u.label, u.ontology_source), empty),
                override=overrides.get(u.term_id),
            )
            for u in uses
        ]
        known_labels = {u.label.lower() for u in uses if u.slot == "organism"}
        for organism in organisms:  # registry target organisms not used as an Organism facet yet
            if organism.lower() not in known_labels:
                out.append(NamingTermInUse(slot="target organism", term_id="", term_label=organism, ontology_source="NCBITAXON", protocol_count=0, default_short_label=organism_short_label(organism, empty), override=None))
        return Success(out)
```

(`NamingTermInUse` is a dataclass in this module with an `override: NamingLabel | None`. A target organism with no taxon id cannot get an override here; it gets one once any protocol uses that organism as a facet, which gives it a term id. Note this limitation in the admin page's help text.)

Routes `naming_labels.py` (prefix `/api/v1/naming-labels`); `terms-in-use` is declared before `/{label_id}` routes. API test: create override → 201; duplicate term → 409; terms-in-use returns `default_short_label == "M. tuberculosis"` for an Mtb-annotated protocol and its override after one is created; `editor_client` POST → 403.

- [ ] **Step 5: Frontend admin page**

Regenerate orval + churn. `use-naming-labels.ts`: crud hooks over `/naming-labels` (key `["naming-labels"]`) plus `useNamingTermsInUse()` (GET `/naming-labels/terms-in-use`, key `["naming-labels", "terms-in-use"]`; crud mutations also invalidate it via `parentQueryKeys` if `createCrudHooks` supports it, else invalidate manually). `naming-label-admin.tsx`: `PageHeader` "Short labels" (subtitle "How ontology terms read inside protocol names"); a table grouped by slot (Organism, Cell line, Assay format, Target organism) with columns Term / Source / Protocols / Short label (override shown bold with a "default" muted line beneath, or the default alone) / action ("Edit" opens a dialog with one Short label input and "Reset to default" which deletes the override). Page `app/(dashboard)/admin/naming-labels/page.tsx`; navigation under "Vocabularies": `{ title: "Short Labels", href: "/admin/naming-labels", icon: BookOpen, requires: "admin" }`.

Test `naming-label-admin.test.tsx`: mocked hooks return one Mtb term with default "M. tuberculosis" and no override → row shows "M. tuberculosis"; clicking Edit, typing "Mtb", Save calls the create mutation with `{ term_id, term_label, ontology_source, short_label: "Mtb" }`.

```bash
cd backend && uv run pytest tests/unit/domain/workspace_config -q && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_naming_labels.py -q
cd ../frontend && pnpm exec vitest run src/features/workspace-config && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/workspace-config src/app src/shared/lib/navigation.ts
```

- [ ] **Step 6: Commit**

```bash
git add backend/src/cellar/domain/workspace_config/naming_label.py backend/src/cellar/infrastructure/persistence/sqlalchemy/workspace_config/naming_label_repository.py backend/alembic/versions/085_naming_labels.py backend/src/cellar/application/workspace_config/naming_labels.py backend/src/cellar/interface/routes/naming_labels.py backend/tests/unit/domain/workspace_config/test_naming_label.py backend/tests/api/test_naming_labels.py "frontend/src/app/(dashboard)/admin/naming-labels/page.tsx" frontend/src/features/workspace-config/hooks/use-naming-labels.ts frontend/src/features/workspace-config/components/naming-label-admin.tsx frontend/src/features/workspace-config/components/naming-label-admin.test.tsx
git commit -m "feat(protocols): admin-editable short labels for ontology terms in names

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/alembic/versions/085_naming_labels.py backend/tests frontend/src
```

---

### Task 12: Naming fields on the protocol, and audited renames

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/enums.py` (`NameFlag`)
- Modify: `backend/src/cellar/domain/screening_assay/protocol.py`
- Modify: `backend/src/cellar/domain/screening_assay/events.py` (`ProtocolRenamed`)
- Modify: `backend/src/cellar/domain/screening_assay/protocol_versioning_service.py`
- Modify: `backend/src/cellar/application/audit/audit_recording_service.py` (`handle_event`)
- Modify: `backend/src/cellar/application/screening/manage_protocol.py` (`UpdateProtocol`), `backend/src/cellar/application/screening/manage_ontology_annotations.py`
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/{models.py,protocol_repository.py}`
- Create: `backend/alembic/versions/086_protocol_name_fields.py`
- Modify: `backend/src/cellar/interface/routes/protocols.py` (`ProtocolResponse`, `UpdateProtocolRequest`, ontology routes)
- Modify: `frontend/src/features/screening-assay/{types/index.ts,hooks/use-protocols.ts,components/protocol-detail.tsx}` (edit dialog stops sending `name`)
- Test: `backend/tests/unit/domain/screening_assay/test_protocol_naming_fields.py`, `backend/tests/unit/application/audit/test_audit_rename_payload.py`

**Interfaces:**
- Produces:
  - `NameFlag(StrEnum)`: `NEEDS_FACTS = "needs_facts"`, `NEEDS_DISCRIMINATOR = "needs_discriminator"`, `NAME_CONFLICT = "name_conflict"`.
  - `Protocol` kwargs/attrs: `discriminator: str | None`, `name_base: str` (defaults to `name`), `name_flag: NameFlag | None`.
  - `Protocol.apply_derived_name(*, name: str, base: str, flag: NameFlag | None, reason: str, user_id: uuid.UUID | None = None) -> bool` (allowed in any status; records the old name as a `FORMER` alias; emits `ProtocolRenamed` when the name changes).
  - `Protocol.flag_name(flag: NameFlag | None) -> None` (any status).
  - `Protocol.set_discriminator(value: str | None, *, reason: str | None = None) -> None`, `Protocol.set_category(category: str | None, *, reason: str | None = None) -> None`, `set_ontology_annotation(slot, terms, *, reason=None)`, `remove_ontology_annotation(slot, *, reason=None)`: all through `_guard_correction(reason)` (draft: no reason; unlocked active: reason required → `ValidationError`; locked or retired: `ConflictError`).
  - `Protocol.update(*, description=..., pos_control_signal=None)`: `name` and `category` removed.
  - `Protocol.publish()` refuses (`ConflictError`) while `name_flag` is `NEEDS_FACTS` or `NAME_CONFLICT`.
  - `ProtocolRenamed(DomainEvent)`: `old_name`, `new_name`, `reason`, `user_id`; `audit_reason` property; `audit_changes() -> list[tuple[str, str | None, str | None]]`.
  - Audit: any event with `audit_changes()` adds one `UPDATE` entry per change; `audit_reason` fills `AuditOperation.reason`.
  - `ProtocolResponse.discriminator: str | None`, `ProtocolResponse.name_flag: str | None`.

- [ ] **Step 1: Failing domain tests** (`test_protocol_naming_fields.py`)

```python
import uuid

import pytest

from cellar.domain.screening_assay.enums import AliasKind, NameFlag, ProtocolStatus, ProtocolType
from cellar.domain.screening_assay.events import ProtocolRenamed
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.shared.errors import ConflictError, ValidationError


def _protocol(name="PptT inhibition"):
    pid = uuid.uuid4()
    p = Protocol.create(
        workspace_id=uuid.uuid4(), name=name, protocol_type=ProtocolType.BIOCHEMICAL, created_by=uuid.uuid4(),
        code="PRT-00001", readout_definitions=[ReadoutDefinition(protocol_id=pid, name="Signal", data_type="numeric")],
    )
    p.clear_events()
    return p


def test_rename_records_former_alias_and_event():
    p = _protocol()
    assert p.apply_derived_name(name="PptT inhibition [FP]", base="PptT inhibition", flag=None, reason="Discriminator added")
    assert p.name == "PptT inhibition [FP]" and p.name_base == "PptT inhibition"
    assert [(a.label, a.kind, a.reason) for a in p.aliases] == [("PptT inhibition", AliasKind.FORMER, "Discriminator added")]
    (event,) = p.collect_events()
    assert isinstance(event, ProtocolRenamed) and event.audit_changes() == [("name", "PptT inhibition", "PptT inhibition [FP]")]


def test_same_name_is_not_a_rename():
    p = _protocol()
    assert not p.apply_derived_name(name="PptT inhibition", base="PptT inhibition", flag=NameFlag.NEEDS_DISCRIMINATOR, reason="x")
    assert p.collect_events() == [] and p.aliases == [] and p.name_flag == NameFlag.NEEDS_DISCRIMINATOR


def test_returning_to_a_former_name_drops_it_from_aliases():
    p = _protocol()
    p.apply_derived_name(name="B", base="B", flag=None, reason="r1")
    p.apply_derived_name(name="PptT inhibition", base="PptT inhibition", flag=None, reason="r2")
    assert [a.label for a in p.aliases] == ["B"]


def test_relabel_allowed_when_locked_or_retired():
    p = _protocol()
    p.publish()
    p.retire(reason="old")
    p.apply_derived_name(name="PptT inhibition [FP]", base="PptT inhibition", flag=None, reason="Registry rename")
    assert p.name == "PptT inhibition [FP]"


def test_names_over_400_characters_refused():
    with pytest.raises(ValidationError):
        _protocol().apply_derived_name(name="x" * 401, base="x", flag=None, reason="r")


def test_correction_rules():
    p = _protocol()
    p.set_category("Binding")  # draft: no reason needed
    p.publish()
    with pytest.raises(ValidationError, match="reason"):
        p.set_category("Enzyme inhibition")
    p.set_category("Enzyme inhibition", reason="It was always an enzyme assay")
    assert p.category == "Enzyme inhibition"


def test_locked_protocol_refuses_corrections():
    p = _protocol()
    p.publish()
    p.lock(locked_by=uuid.uuid4(), reason="review")
    with pytest.raises(ConflictError):
        p.set_discriminator("FP", reason="r")


def test_discriminator_is_cleaned():
    p = _protocol()
    p.set_discriminator("  FP ")
    assert p.discriminator == "FP"
    with pytest.raises(ValidationError):
        p.set_discriminator("HTS")


def test_publish_refused_while_facts_missing():
    p = _protocol()
    p.flag_name(NameFlag.NEEDS_FACTS)
    with pytest.raises(ConflictError, match="name"):
        p.publish()
```

(Check `lock(...)`'s real signature in `protocol.py` and match it.)

Run: `cd backend && uv run pytest tests/unit/domain/screening_assay/test_protocol_naming_fields.py -q` → FAIL.

- [ ] **Step 2: Domain changes**

`enums.py`:

```python
class NameFlag(StrEnum):
    """Why a protocol's generated name needs attention."""

    NEEDS_FACTS = "needs_facts"  # a field the category's pattern needs is empty; cannot publish
    NEEDS_DISCRIMINATOR = "needs_discriminator"  # another protocol shares the base name
    NAME_CONFLICT = "name_conflict"  # a registry rename made two names identical; cannot publish
```

`events.py`:

```python
@dataclass(frozen=True, kw_only=True)
class ProtocolRenamed(DomainEvent):
    """The generated name changed. Audited with the old name, the new one and why."""

    old_name: str
    new_name: str
    reason: str
    user_id: uuid.UUID | None = None

    @property
    def audit_reason(self) -> str:
        return self.reason

    def audit_changes(self) -> list[tuple[str, str | None, str | None]]:
        return [("name", self.old_name, self.new_name)]
```

`protocol.py`:
- `__init__` kwargs: `discriminator: str | None = None`, `name_base: str | None = None`, `name_flag: NameFlag | None = None`; assign `self.discriminator = discriminator`, `self.name_base = name_base or self.name`, `self.name_flag = name_flag`. `create(...)` accepts and passes the same three.
- Add:

```python
    def _guard_correction(self, reason: str | None) -> None:
        """Facts that feed the generated name. Drafts change freely; a published protocol
        only through a correction with a reason; locked and retired ones not at all."""
        if self.is_locked:
            raise ConflictError(f"Protocol is locked. Reason: {self.lock_reason or '(none)'}. Unlock to make changes.")
        if self.status == ProtocolStatus.RETIRED:
            raise ConflictError("Cannot change a retired protocol")
        if self.status == ProtocolStatus.ACTIVE and not (reason and reason.strip()):
            raise ValidationError("A published protocol can only be corrected with a reason")

    def set_category(self, category: str | None, *, reason: str | None = None) -> None:
        self._guard_correction(reason)
        self.category = " ".join(category.split()) if category and category.strip() else None
        self.updated_at = datetime.now(UTC)

    def set_discriminator(self, value: str | None, *, reason: str | None = None) -> None:
        self._guard_correction(reason)
        self.discriminator = clean_discriminator(value)
        self.updated_at = datetime.now(UTC)

    def flag_name(self, flag: NameFlag | None) -> None:
        self.name_flag = flag

    def apply_derived_name(
        self, *, name: str, base: str, flag: NameFlag | None, reason: str, user_id: uuid.UUID | None = None
    ) -> bool:
        """Set the generated name. Allowed in any status: a relabel changes words, not facts."""
        name, base = normalize_name_text(name), normalize_name_text(base)
        if not name:
            raise ValidationError("Protocol name must not be empty")
        if len(name) > MAX_NAME_LENGTH:
            raise ValidationError(
                f"The generated name is longer than {MAX_NAME_LENGTH} characters; shorten the discriminator or a short label"
            )
        self.name_base = base
        self.name_flag = flag
        if name == self.name:
            return False
        old = self.name
        now = datetime.now(UTC)
        self.aliases = [a for a in self.aliases if a.label.lower() != name.lower()]
        if not any(a.label.lower() == old.lower() for a in self.aliases):
            self.aliases.append(ProtocolAlias(label=old, kind=AliasKind.FORMER, recorded_at=now, reason=reason))
        self.name = name
        self.updated_at = now
        self.register_event(
            ProtocolRenamed(
                aggregate_id=self.id, aggregate_type="Protocol", workspace_id=self.workspace_id,
                old_name=old, new_name=name, reason=reason, user_id=user_id,
            )
        )
        return True
```

- `set_ontology_annotation(self, slot, terms, *, reason: str | None = None)` and `remove_ontology_annotation(self, slot, *, reason: str | None = None)`: replace `self._guard_draft()` with `self._guard_correction(reason)`.
- `update(...)`: delete the `name` and `category` parameters and their branches (keep `description`, `pos_control_signal`, draft guard).
- `publish()`: after the lock check add

```python
        if self.name_flag in (NameFlag.NEEDS_FACTS, NameFlag.NAME_CONFLICT):
            raise ConflictError(
                "This protocol's name is incomplete or clashes with another; fix it before publishing"
            )
```

- Imports: `MAX_NAME_LENGTH`, `clean_discriminator`, `normalize_name_text` from `cellar.domain.shared.protocol_naming`; `NameFlag` from enums; `ProtocolRenamed` from events.
- Versioning service: pass `discriminator=parent.discriminator, name_base=parent.name_base, name_flag=parent.name_flag`.

Run the domain tests → PASS. Then run all unit tests and fix callers of the removed `update(name=..., category=...)`:

```bash
cd backend && uv run pytest tests/unit -q -x
grep -rn "\.update(name=\|\.update(.*category=" src/cellar/application/screening tests | head
```

- [ ] **Step 3: Audit payload**

Test `backend/tests/unit/application/audit/test_audit_rename_payload.py`:

```python
import uuid

from cellar.application.audit.audit_recording_service import AuditRecordingService
from cellar.domain.audit_compliance.enums import AuditAction
from cellar.domain.screening_assay.events import ProtocolRenamed


class _Repo:
    def __init__(self):
        self.saved = []

    async def save(self, operation):
        self.saved.append(operation)


async def test_rename_is_audited_with_old_new_and_reason():
    repo = _Repo()
    await AuditRecordingService(repo).handle_event(
        ProtocolRenamed(aggregate_id=uuid.uuid4(), aggregate_type="Protocol", workspace_id=uuid.uuid4(),
                        old_name="A", new_name="B", reason="Registry renamed PptT")
    )
    (op,) = repo.saved
    assert op.reason == "Registry renamed PptT"
    change = next(e for e in op.entries if e.field_name == "name")
    assert (change.action, change.old_value, change.new_value) == (AuditAction.UPDATE, "A", "B")
```

(Match `AuditRecordingService`'s constructor and the attribute holding entries on `AuditOperation`; read both first.) In `handle_event`: build `AuditOperation(..., reason=getattr(event, "audit_reason", None))`, and after the existing `"event"` entry:

```python
        changes = getattr(event, "audit_changes", None)
        if callable(changes):
            for field_name, old_value, new_value in changes():
                operation.add_entry(
                    AuditEntry(
                        entity_type=event.aggregate_type, entity_id=event.aggregate_id, field_name=field_name,
                        action=AuditAction.UPDATE, old_value=old_value, new_value=new_value, timestamp=event.occurred_at,
                    )
                )
```

Run: `uv run pytest tests/unit/application/audit -q` → PASS.

- [ ] **Step 4: Persistence + migration**

Migration `086_protocol_name_fields.py` (`down_revision = "085_naming_labels"`):

```python
def upgrade() -> None:
    op.alter_column("protocols", "name", type_=sa.String(400), existing_type=sa.String(200), existing_nullable=False)
    op.add_column("protocols", sa.Column("discriminator", sa.String(40), nullable=True))
    op.add_column("protocols", sa.Column("name_base", sa.String(400), nullable=True))
    op.add_column("protocols", sa.Column("name_flag", sa.String(30), nullable=True))
    op.execute("UPDATE protocols SET name_base = name")
    op.alter_column("protocols", "name_base", nullable=False)
    op.create_index("ix_protocol_ws_name_base", "protocols", ["workspace_id", sa.text("lower(name_base)")])


def downgrade() -> None:
    op.drop_index("ix_protocol_ws_name_base", table_name="protocols")
    op.drop_column("protocols", "name_flag")
    op.drop_column("protocols", "name_base")
    op.drop_column("protocols", "discriminator")
    op.alter_column("protocols", "name", type_=sa.String(200), existing_type=sa.String(400), existing_nullable=False)
```

`ProtocolModel`: `name: Mapped[str] = mapped_column(String(400), nullable=False)`, `discriminator: Mapped[str | None] = mapped_column(String(40))`, `name_base: Mapped[str] = mapped_column(String(400), nullable=False)`, `name_flag: Mapped[str | None] = mapped_column(String(30))`. Map in `_to_domain` (`name_flag=NameFlag(model.name_flag) if model.name_flag else None`), `_to_model`, `_update_model` (`model.name_flag = aggregate.name_flag.value if aggregate.name_flag else None`). `make migrate`.

- [ ] **Step 5: Use cases and routes follow the new domain API**

- `UpdateProtocolCommand`: delete `name`. `UpdateProtocol`: description via `protocol.update(description=...)`; category via `protocol.set_category(category)` when provided (draft-only in practice: no reason is passed). Task 14 adds name re-derivation.
- `SetOntologyAnnotationCommand` / `RemoveOntologyAnnotationCommand`: add `reason: str | None = None` and pass it through.
- `UpdateProtocolRequest`: delete `name`. `SetOntologyAnnotationRequest`: add `reason: str | None = None`; the DELETE annotation route takes `reason: str | None = Query(None)`.
- `ProtocolResponse`: `discriminator: str | None = None`, `name_flag: str | None = None` (`name_flag=p.name_flag.value if p.name_flag else None`).
- Frontend: regenerate orval + churn; `Protocol` gains `discriminator: ProtocolResponse["discriminator"]; name_flag: ProtocolResponse["name_flag"];`; `use-protocols.ts` update type drops `name`; `protocol-detail.tsx` edit dialog drops the Name input and `editName` state and the `name:` key in the payload (the save button is enabled without a name).

```bash
cd backend && uv run pytest tests/unit -q && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api -q -k protocol
cd ../frontend && pnpm exec tsc --noEmit -p . && pnpm exec vitest run src/features/screening-assay && pnpm exec biome check src/features/screening-assay
```

Fix API tests that PATCH `name` (they now get 422: change them to PATCH `description`).

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/086_protocol_name_fields.py backend/tests/unit/domain/screening_assay/test_protocol_naming_fields.py backend/tests/unit/application/audit/test_audit_rename_payload.py
git commit -m "feat(protocols): naming fields, correction guard and audited renames

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/alembic/versions/086_protocol_name_fields.py backend/tests frontend/src/features/screening-assay frontend/src/shared/lib/api
```

---

### Task 13: ProtocolNameService

**Files:**
- Create: `backend/src/cellar/application/screening/protocol_naming_service.py`
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` (`NameSibling`, `ProtocolRepository.find_name_siblings`, `lock_naming`, `list_discriminators`; `TargetRepository.find_by_ids`)
- Modify: `backend/src/cellar/infrastructure/persistence/sqlalchemy/screening_assay/{protocol_repository.py,target_repository.py}`
- Modify: `backend/src/cellar/infrastructure/di/_screening.py` (factory helper)
- Test: `backend/tests/unit/application/screening/test_protocol_naming_service.py`, `backend/tests/integration/test_protocol_name_siblings.py`

**Interfaces:**
- Consumes: Task 1 policy; Task 10 `ProtocolCategoryRepository.find_by_label`; Task 11 `NamingLabelRepository.find_by_workspace`; Task 2 settings `home_organism_label`; `CollectionRepository.find_by_workspace(workspace_id)` filtered to `CollectionType.LIBRARY`.
- Produces:
  - `NameSibling(protocol_id: uuid.UUID, code: str | None, name: str, discriminator: str | None)` (domain dataclass in `repository.py`).
  - `ProtocolRepository.find_name_siblings(workspace_id, *, base: str, exclude_code: str | None) -> list[NameSibling]` (case-insensitive on `name_base`, one row per code); `lock_naming(workspace_id) -> None` (advisory lock `protocol_naming:{ws}`); `list_discriminators(workspace_id, *, base: str | None, q: str | None, limit: int = 20) -> list[str]`.
  - `TargetRepository.find_by_ids(workspace_id, ids: Sequence[uuid.UUID]) -> list[Target]`.
  - `NameDerivation(rendered: RenderedName, clash: NameSibling | None, siblings: tuple[NameSibling, ...], bare_siblings: tuple[NameSibling, ...], needs_discriminator: bool)`.
  - `ProtocolNameService(*, protocol_repo, target_repo, category_repo, label_repo, settings_repo, collection_repo)` with:
    - `async context(workspace_id) -> NamingContext`
    - `async clean_discriminator(workspace_id, value: str | None) -> str | None` (domain rules + library names)
    - `async derive(workspace_id, *, category: str | None, target_ids: Sequence[uuid.UUID], annotations: Mapping[str, Sequence[OntologyTerm]], discriminator: str | None, exclude_code: str | None = None) -> NameDerivation`
    - `check(derivation, *, person: bool, allow_incomplete: bool) -> Result[NameFlag | None, DomainError]`
    - `async flag_siblings(workspace_id, derivation, *, clash_flag: bool = False) -> None`
    - `async apply(protocol: Protocol, *, reason: str, person: bool, allow_incomplete: bool, user_id: uuid.UUID | None = None) -> Result[NameDerivation, DomainError]`
  - `MISSING_FIELD_LABELS: dict[str, str]` (slot → "an organism", …).
  - DI helper `_name_service(uow) -> ProtocolNameService` in `_screening.py` used by every use case that re-derives.

- [ ] **Step 1: Failing unit tests** (`test_protocol_naming_service.py`; in-memory fakes, no DB)

```python
import uuid
from dataclasses import dataclass

import pytest

from cellar.application.screening.protocol_naming_service import ProtocolNameService
from cellar.domain.screening_assay.enums import NameFlag
from cellar.domain.screening_assay.repository import NameSibling
from cellar.domain.shared.errors import ConflictError, ValidationError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.workspace_config.protocol_category import ProtocolCategory
from cellar.domain.workspace_config.workspace_settings import WorkspaceSettings

WS = uuid.uuid4()
MTB = OntologyTerm(term_id="http://purl.bioontology.org/ontology/NCBITAXON/1773", label="Mycobacterium tuberculosis", ontology_source="NCBITAXON")


@dataclass
class _Target:
    id: uuid.UUID
    name: str
    organism: str | None


class _Protocols:
    def __init__(self, siblings=()):
        self.siblings = list(siblings)
        self.flagged = {}

    async def find_name_siblings(self, workspace_id, *, base, exclude_code):
        return [s for s in self.siblings if s.name.lower().startswith(base.lower()) and s.code != exclude_code]

    async def lock_naming(self, workspace_id):
        return None

    async def find_by_id_in_workspace(self, workspace_id, protocol_id):
        return None  # sibling flagging is covered by the integration test

    async def find_direct_target_ids(self, workspace_id, protocol_id):
        return []


class _Targets:
    def __init__(self, targets=()):
        self.targets = {t.id: t for t in targets}

    async def find_by_ids(self, workspace_id, ids):
        return [self.targets[i] for i in ids if i in self.targets]


class _Categories:
    async def find_by_label(self, workspace_id, label):
        if label and label.lower() in ("growth inhibition", "enzyme inhibition"):
            return ProtocolCategory.create(workspace_id=workspace_id, label=label.capitalize())
        return None


class _Labels:
    async def find_by_workspace(self, workspace_id):
        return []


class _Settings:
    async def find_by_workspace_id(self, workspace_id):
        s = WorkspaceSettings.create_default(workspace_id=workspace_id)
        s.set_home_organism({"term_id": MTB.term_id, "label": MTB.label})
        return s


class _Collections:
    async def find_by_workspace(self, workspace_id, **_):
        return []


def _service(siblings=(), targets=()):
    return ProtocolNameService(
        protocol_repo=_Protocols(siblings), target_repo=_Targets(targets), category_repo=_Categories(),
        label_repo=_Labels(), settings_repo=_Settings(), collection_repo=_Collections(),
    )


async def test_derives_from_category_and_organism():
    d = await _service().derive(WS, category="Growth inhibition", target_ids=[], annotations={"organism": [MTB]}, discriminator="resazurin")
    assert d.rendered.name == "M. tuberculosis growth inhibition [resazurin]" and d.clash is None


async def test_unknown_category_is_missing_not_a_crash():
    d = await _service().derive(WS, category="Enzyme Assay", target_ids=[], annotations={}, discriminator=None)
    assert d.rendered.missing == ("category",)
    assert _service().check(d, person=True, allow_incomplete=False).failure().__class__ is ValidationError
    assert _service().check(d, person=True, allow_incomplete=True).unwrap() == NameFlag.NEEDS_FACTS


async def test_same_base_without_discriminator_conflicts_for_people_and_flags_for_the_system():
    sibling = NameSibling(protocol_id=uuid.uuid4(), code="PRT-00002", name="M. tuberculosis growth inhibition [OD600]", discriminator="OD600")
    d = await _service([sibling]).derive(WS, category="Growth inhibition", target_ids=[], annotations={"organism": [MTB]}, discriminator=None)
    assert d.needs_discriminator
    assert isinstance(_service().check(d, person=True, allow_incomplete=False).failure(), ConflictError)
    assert _service().check(d, person=False, allow_incomplete=False).unwrap() == NameFlag.NEEDS_DISCRIMINATOR


async def test_exact_clash_names_the_other_code():
    sibling = NameSibling(protocol_id=uuid.uuid4(), code="PRT-00002", name="M. tuberculosis growth inhibition [OD600]", discriminator="OD600")
    d = await _service([sibling]).derive(WS, category="Growth inhibition", target_ids=[], annotations={"organism": [MTB]}, discriminator="od600")
    assert d.clash == sibling
    assert "PRT-00002" in str(_service().check(d, person=True, allow_incomplete=False).failure())


async def test_bare_sibling_is_reported_for_flagging():
    bare = NameSibling(protocol_id=uuid.uuid4(), code="PRT-00003", name="M. tuberculosis growth inhibition", discriminator=None)
    d = await _service([bare]).derive(WS, category="Growth inhibition", target_ids=[], annotations={"organism": [MTB]}, discriminator="hypoxia")
    assert d.bare_siblings == (bare,) and not d.needs_discriminator and d.clash is None


async def test_targets_come_from_the_registry_in_name_order():
    a, b = _Target(uuid.uuid4(), "PanD", MTB.label), _Target(uuid.uuid4(), "PanC", MTB.label)
    d = await _service(targets=[a, b]).derive(WS, category="Enzyme inhibition", target_ids=[a.id, b.id], annotations={}, discriminator=None)
    assert d.rendered.name == "PanC/PanD inhibition"
```

Run → FAIL (module missing).

- [ ] **Step 2: Repository additions**

Domain `repository.py`:

```python
@dataclass(frozen=True)
class NameSibling:
    """Another protocol (by code) whose generated base name equals this one's."""

    protocol_id: uuid.UUID
    code: str | None
    name: str
    discriminator: str | None
```

`ProtocolRepository` methods (signatures from Interfaces). Implementation:

```python
    async def lock_naming(self, workspace_id: uuid.UUID) -> None:
        # Same key as next_protocol_code: one create-or-rename name check at a time per workspace.
        await self._session.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"protocol_naming:{workspace_id}"))))

    async def find_name_siblings(self, workspace_id: uuid.UUID, *, base: str, exclude_code: str | None) -> list[NameSibling]:
        stmt = select(ProtocolModel.id, ProtocolModel.code, ProtocolModel.name, ProtocolModel.discriminator).where(
            ProtocolModel.workspace_id == workspace_id,
            func.lower(ProtocolModel.name_base) == base.strip().lower(),
        )
        if exclude_code is not None:
            stmt = stmt.where(ProtocolModel.code.is_distinct_from(exclude_code))
        seen: dict[str | None, NameSibling] = {}
        for row in (await self._session.execute(stmt.order_by(ProtocolModel.protocol_version.desc()))).all():
            seen.setdefault(row.code or str(row.id), NameSibling(protocol_id=row.id, code=row.code, name=row.name, discriminator=row.discriminator))
        return list(seen.values())

    async def list_discriminators(self, workspace_id: uuid.UUID, *, base: str | None, q: str | None, limit: int = 20) -> list[str]:
        stmt = select(ProtocolModel.discriminator).where(
            ProtocolModel.workspace_id == workspace_id, ProtocolModel.discriminator.is_not(None)
        )
        if base:
            stmt = stmt.where(func.lower(ProtocolModel.name_base) == base.strip().lower())
        if q:
            stmt = stmt.where(ProtocolModel.discriminator.ilike(f"%{q.strip()}%"))
        rows = (await self._session.execute(stmt.distinct().order_by(ProtocolModel.discriminator).limit(limit))).scalars()
        return list(rows)
```

`TargetRepository.find_by_ids` (+ implementation `select(TargetModel).where(TargetModel.workspace_id == ws, TargetModel.id.in_(ids))`).

- [ ] **Step 3: The service**

```python
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
from cellar.domain.screening_assay.repository import NameSibling, ProtocolRepository, TargetRepository
from cellar.domain.shared.errors import ConflictError, DomainError, ValidationError
from cellar.domain.shared.ontology import OntologyTerm
from cellar.domain.shared.protocol_naming import (
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
            overrides_by_term={l.term_id: l.short_label for l in labels},
            overrides_by_label={l.term_label.lower(): l.short_label for l in labels},
            home_organism_label=settings.home_organism_label if settings else None,
        )

    async def clean_discriminator(self, workspace_id: uuid.UUID, value: str | None) -> str | None:
        libraries = [
            c.name for c in await self._collections.find_by_workspace(workspace_id) if c.type == CollectionType.LIBRARY
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
    ) -> NameDerivation:
        found = await self._categories.find_by_label(workspace_id, category) if category else None
        if found is None:
            label = "(category needed)" + (f" [{discriminator}]" if discriminator else "")
            rendered = RenderedName(name=label, base="(category needed)", missing=("category",), discriminator_in_pattern=False)
            return NameDerivation(rendered, None, (), (), False)
        targets = sorted(await self._targets.find_by_ids(workspace_id, list(target_ids)), key=lambda t: t.name.lower())
        inputs = NamingInputs(
            targets=tuple(NamingTarget(t.name, t.organism) for t in targets),
            organisms=_terms(annotations.get("organism")),
            cell_lines=_terms(annotations.get("cell_line")),
            matrices=_terms(annotations.get("assay_format")),
            discriminator=discriminator,
        )
        rendered = render_protocol_name(found.name_pattern, inputs, await self.context(workspace_id))
        if not rendered.complete:
            return NameDerivation(rendered, None, (), (), False)
        siblings = tuple(await self._protocols.find_name_siblings(workspace_id, base=rendered.base, exclude_code=exclude_code))
        clash = next((s for s in siblings if s.name.lower() == rendered.name.lower()), None)
        if rendered.discriminator_in_pattern:
            return NameDerivation(rendered, clash, siblings, (), False)
        bare = tuple(s for s in siblings if not s.discriminator and s is not clash)
        return NameDerivation(rendered, clash, siblings, bare, bool(siblings) and not discriminator)

    def check(self, derivation: NameDerivation, *, person: bool, allow_incomplete: bool) -> Result[NameFlag | None, DomainError]:
        r = derivation.rendered
        if not r.complete:
            if person and not allow_incomplete:
                needs = ", ".join(MISSING_FIELD_LABELS.get(m, m) for m in r.missing)
                return Failure(ValidationError(f"This protocol's name needs {needs}"))
            return Success(NameFlag.NEEDS_FACTS)
        if derivation.clash is not None:
            if person:
                return Failure(
                    ConflictError(f"'{r.name}' is already the name of {derivation.clash.code}; give one of them a different discriminator")
                )
            return Success(NameFlag.NAME_CONFLICT)
        if derivation.needs_discriminator:
            if person:
                codes = ", ".join(s.code or "?" for s in derivation.siblings)
                return Failure(ConflictError(f"Other protocols are also '{r.base}' ({codes}); add a discriminator such as the method"))
            return Success(NameFlag.NEEDS_DISCRIMINATOR)
        return Success(None)

    async def flag_siblings(self, workspace_id: uuid.UUID, derivation: NameDerivation, *, clash_flag: bool = False) -> None:
        """Bare siblings need a discriminator too; a system-made exact clash flags the other protocol."""
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
        self, protocol: Protocol, *, reason: str, person: bool, allow_incomplete: bool, user_id: uuid.UUID | None = None
    ) -> Result[NameDerivation, DomainError]:
        await self._protocols.lock_naming(protocol.workspace_id)
        derivation = await self.derive(
            protocol.workspace_id,
            category=protocol.category,
            target_ids=await self._protocols.find_direct_target_ids(protocol.workspace_id, protocol.id),
            annotations=protocol.ontology_annotations,
            discriminator=protocol.discriminator,
            exclude_code=protocol.code,
        )
        checked = self.check(derivation, person=person, allow_incomplete=allow_incomplete)
        if isinstance(checked, Failure):
            return checked
        flag = checked.unwrap()
        await self.flag_siblings(protocol.workspace_id, derivation, clash_flag=flag == NameFlag.NAME_CONFLICT)
        name = derivation.rendered.name
        protocol.apply_derived_name(name=name, base=derivation.rendered.base, flag=flag, reason=reason, user_id=user_id)
        return Success(derivation)
```

(If `protocol.ontology_annotations` stores `OntologyTerm` lists, pass it straight through; it does per `protocol.py`.) DI helper in `_screening.py`:

```python
def _name_service(uow) -> ProtocolNameService:
    return ProtocolNameService(
        protocol_repo=SQLAlchemyProtocolRepository(uow),
        target_repo=SQLAlchemyTargetRepository(uow),
        category_repo=SQLAlchemyProtocolCategoryRepository(uow),
        label_repo=SQLAlchemyNamingLabelRepository(uow),
        settings_repo=SQLAlchemyWorkspaceSettingsRepository(uow),
        collection_repo=SQLAlchemyCollectionRepository(uow),
    )
```

(Find the collection repository class name with `grep -rn "class SQLAlchemyCollectionRepository" backend/src`.)

Run the unit tests → PASS.

- [ ] **Step 4: Integration test for siblings, flags and the race** (`test_protocol_name_siblings.py`)

Write three tests against the real DB using the `uow`/`session_factory` fixtures, building the service with `_name_service`-equivalent construction:
1. Two saved protocols `M. tuberculosis growth inhibition [OD600]` (code PRT-00001) and `M. tuberculosis growth inhibition` (bare, PRT-00002) with `name_base` set; `find_name_siblings(base="m. tuberculosis growth inhibition", exclude_code="PRT-00003")` returns both; `exclude_code="PRT-00002"` returns one.
2. `apply(person=False)` on a third protocol with discriminator `hypoxia` flags PRT-00002 `needs_discriminator` after commit.
3. Race: two concurrent tasks, each in its own `AsyncUnitOfWork`, call `lock_naming`, derive a bare name with no siblings, save a protocol with that name, sleep 0.2 s inside the lock, commit. Assert the second derivation (after the first commits) sees the first as a sibling (`needs_discriminator` True), so only one bare protocol is saved.

```bash
cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_protocol_name_siblings.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/screening/protocol_naming_service.py backend/tests/unit/application/screening/test_protocol_naming_service.py backend/tests/integration/test_protocol_name_siblings.py
git commit -m "feat(protocols): ProtocolNameService derives names and checks collisions

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/tests
```

---

### Task 14: Names derived on create, edit, import and target changes

**Files:**
- Modify: `backend/src/cellar/application/screening/create_protocol.py`
- Modify: `backend/src/cellar/application/screening/manage_protocol.py` (`UpdateProtocol`, `AddProtocolTarget`, `RemoveProtocolTarget`, new `SetProtocolDiscriminator`)
- Modify: `backend/src/cellar/application/screening/manage_ontology_annotations.py`
- Modify: `backend/src/cellar/application/cdd_import/import_cdd_protocol.py`, `backend/src/cellar/interface/routes/cdd_import.py` (`name_override` becomes a nickname)
- Modify: `backend/src/cellar/infrastructure/di/{_screening.py,_cdd_import.py}`, `backend/src/cellar/interface/dependencies/_screening.py`
- Modify: `backend/src/cellar/interface/routes/protocols.py` (`CreateProtocolRequest`, target routes, discriminator route)
- Modify: `frontend/src/features/screening-assay/{types/index.ts,components/create-protocol-dialog.tsx,components/detail-tabs/design-tab-protocol-card.tsx}`; delete `frontend/src/features/screening-assay/lib/suggest-protocol-name.ts` and `suggest-protocol-name.test.ts`
- Test: `backend/tests/api/test_protocol_generated_names.py` (new); update API tests that POST `name`

**Interfaces:**
- Consumes: Task 13 service and DI helper `_name_service(uow)`.
- Produces:
  - `CreateProtocolCommand`: `name` removed; adds `discriminator: str | None = None`, `allow_incomplete: bool = False`. Strict for people: missing facts → 422, clash or needs discriminator → 409.
  - `UpdateProtocol`, `SetOntologyAnnotation`, `RemoveOntologyAnnotation`, `AddProtocolTarget`, `RemoveProtocolTarget`: re-derive with `person=True, allow_incomplete=True` (drafts may be temporarily incomplete; they cannot publish).
  - `AddProtocolTargetCommand` / `RemoveProtocolTargetCommand`: `reason: str | None = None`; an ACTIVE protocol requires it (422).
  - `SetProtocolDiscriminatorCommand(workspace_id, protocol_id, discriminator: str | None, reason: str | None = None)` + route `PUT /api/v1/protocols/{id}/discriminator {discriminator, reason?}` → `ProtocolResponse`.
  - `CreateProtocolRequest`: `name` removed; `discriminator: str | None = None`.
  - CDD import: creates with `allow_incomplete=True`; the vault name (or `name_override`) is added as a nickname.
  - Reasons used: "Created", "Category changed", "<Slot> changed" (`Organism changed`, `Cell line changed`, `Assay format changed`, `Detection method changed`), "Target added: <name>", "Target removed: <name>", "Discriminator changed".

- [ ] **Step 1: Failing API tests** (`backend/tests/api/test_protocol_generated_names.py`)

```python
"""Names are generated: from the category pattern and the facts, never typed."""

import pytest

MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}
READOUTS = [{"name": "Signal", "data_type": "numeric"}]


@pytest.fixture
async def categories(client):
    assert (await client.post("/api/v1/protocol-categories/defaults")).status_code == 200


def _body(**over):
    body = {
        "protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": READOUTS,
        "ontology_annotations": {"organism": [MTB]},
    }
    return body | over


async def test_create_generates_the_name(client, categories):
    r = await client.post("/api/v1/protocols", json=_body(discriminator="resazurin"))
    assert r.status_code == 201, r.text
    # no home organism set in this workspace: organisms still read as their short label
    assert r.json()["name"] == "M. tuberculosis growth inhibition [resazurin]"


async def test_missing_fact_is_422(client, categories):
    r = await client.post("/api/v1/protocols", json=_body(ontology_annotations={}))
    assert r.status_code == 422 and "organism" in r.text


async def test_second_bare_protocol_is_409_and_names_the_first(client, categories):
    first = (await client.post("/api/v1/protocols", json=_body())).json()
    r = await client.post("/api/v1/protocols", json=_body())
    assert r.status_code == 409 and first["code"] in r.text


async def test_discriminator_resolves_and_flags_the_bare_one(client, categories):
    bare = (await client.post("/api/v1/protocols", json=_body())).json()
    r = await client.post("/api/v1/protocols", json=_body(discriminator="OD600"))
    assert r.status_code == 201
    again = (await client.get(f"/api/v1/protocols/{bare['id']}")).json()
    assert again["name_flag"] == "needs_discriminator"


async def test_name_field_is_rejected(client, categories):
    assert (await client.post("/api/v1/protocols", json=_body(name="My name"))).status_code == 422


async def test_changing_the_organism_renames_and_keeps_the_old_name_as_alias(client, categories):
    p = (await client.post("/api/v1/protocols", json=_body(discriminator="resazurin"))).json()
    smeg = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1772", "label": "Mycolicibacterium smegmatis", "ontology_source": "NCBITAXON"}
    r = await client.put(f"/api/v1/protocols/{p['id']}/ontology-annotations", json={"slot": "organism", "terms": [smeg]})
    assert r.json()["name"] == "M. smegmatis growth inhibition [resazurin]"
    assert r.json()["aliases"][0]["label"] == "M. tuberculosis growth inhibition [resazurin]"


async def test_discriminator_route(client, categories):
    p = (await client.post("/api/v1/protocols", json=_body())).json()
    r = await client.put(f"/api/v1/protocols/{p['id']}/discriminator", json={"discriminator": "OD600"})
    assert r.json()["name"] == "M. tuberculosis growth inhibition [OD600]"
    assert (await client.put(f"/api/v1/protocols/{p['id']}/discriminator", json={"discriminator": "HTS"})).status_code == 422


async def test_publish_refused_while_incomplete(client, categories):
    p = (await client.post("/api/v1/protocols", json=_body())).json()
    await client.delete(f"/api/v1/protocols/{p['id']}/ontology-annotations/organism")
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 409
```

Run: `cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_protocol_generated_names.py -q` → FAIL.

- [ ] **Step 2: CreateProtocol**

Command: delete `name`, add `discriminator: str | None = None`, `allow_incomplete: bool = False`. Constructor adds `names: ProtocolNameService` (kwarg). In `__call__`, inside the UoW and before `Protocol.create`:

```python
            await self._repo.lock_naming(input.workspace_id)
            discriminator = await self._names.clean_discriminator(input.workspace_id, input.discriminator)
            derivation = await self._names.derive(
                input.workspace_id,
                category=input.category,
                target_ids=list(dict.fromkeys(input.target_ids)),
                annotations=ontology_annotations,  # the OntologyTerm dict already built above
                discriminator=discriminator,
            )
            checked = self._names.check(derivation, person=True, allow_incomplete=input.allow_incomplete)
            if isinstance(checked, Failure):
                return checked
            code = await mint_protocol_code(settings_repo=self._settings_repo, protocol_repo=self._repo, workspace_id=input.workspace_id)
            protocol = Protocol.create(
                workspace_id=input.workspace_id,
                name=derivation.rendered.name,
                name_base=derivation.rendered.base,
                name_flag=checked.unwrap(),
                discriminator=discriminator,
                code=code,
                ...  # the existing arguments, minus name
            )
            await self._repo.save(protocol)
            # existing target linking loop
            await self._names.flag_siblings(input.workspace_id, derivation)
```

(Discriminator `ValidationError` raised by `clean_discriminator` propagates as 422, like other domain validation.) DI: `CreateProtocol(..., names=_name_service(uow), settings_repo=...)` with the same `uow`.

- [ ] **Step 3: Edits re-derive**

In each use case, after the domain mutation and before `save`:

```python
            renamed = await self._names.apply(
                protocol, reason=REASON, person=True, allow_incomplete=True, user_id=auth.user_id if auth else None
            )
            if isinstance(renamed, Failure):
                return renamed
```

- `UpdateProtocol`: only when `category` was provided; `REASON = "Category changed"`.
- `SetOntologyAnnotation` / `RemoveOntologyAnnotation`: `REASON = f"{SLOT_LABELS.get(slot, slot)} changed"` with `SLOT_LABELS = {"organism": "Organism", "cell_line": "Cell line", "assay_format": "Assay format", "detection": "Detection method"}` (detection does not feed names, so `apply` leaves the name unchanged; calling it keeps flags fresh).
- `AddProtocolTarget` / `RemoveProtocolTarget`: today they use `find_lock_state` without loading the aggregate. Keep the link change, then load the aggregate (`find_by_id_in_workspace`), check `if protocol.status == ProtocolStatus.ACTIVE and not (input.reason and input.reason.strip()): return Failure(ValidationError("A published protocol can only be corrected with a reason"))` before changing the link, and after the link change call `apply` with `REASON = f"Target added: {target_name}"` (look the target name up with `TargetRepository.find_by_ids`). Routes take `reason: str | None = Query(None)`.
- New `SetProtocolDiscriminator` in `manage_protocol.py`: `require_editor`, same workspace, load or NotFound, `value = await self._names.clean_discriminator(ws, input.discriminator)`, `protocol.set_discriminator(value, reason=input.reason)`, `apply(..., reason=input.reason or "Discriminator changed")`, save, commit, dispatch. Route `PUT /protocols/{protocol_id}/discriminator` with body `SetDiscriminatorRequest(discriminator: str | None, reason: str | None = None)`.

All these use cases get `names=_name_service(uow)` in DI with the shared `uow`; switch their DI definitions from `_protocol_cmd(...)` to explicit factories.

- [ ] **Step 4: CDD import**

`ImportCddProtocol`: derive with `category=mapping.category`, no targets or annotations, `allow_incomplete=True`; `Protocol.create(name=derivation.rendered.name, name_base=..., name_flag=checked.unwrap(), code=code, ...)`; then `protocol.add_nickname(input.name_override or mapping.name)` wrapped in `contextlib.suppress(ConflictError)` (the generated name could equal it). Update the route docstring for `name_override`: "Recorded as a nickname; protocol names are generated."

- [ ] **Step 5: Frontend follows the API**

Regenerate orval + churn. `CreateProtocolInput` (hand-written in `types/index.ts`) loses `name` and gains `discriminator?: string | null`. In `create-protocol-dialog.tsx`: remove the Name `<Input>`, its error text, the "Suggest name" button and `suggestedName`; replace them with a muted line "The name is generated from the category and fields below." (Task 16 replaces this with the live preview); remove `name` from the zod schema, `defaultValues`, `resetForm`, `canSubmit` and the submit payload; pass `name: ""` nowhere. `SimilarProtocolsPanel` keeps receiving `draft.name` as `""` until Task 16. Delete `lib/suggest-protocol-name.ts` and its test. `design-tab-protocol-card.tsx`: `const canEditTargets = isDraft && !isLocked;` (published protocols change targets through the correction dialog, Task 18).

```bash
cd backend && uv run pytest tests/unit -q && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api -q
cd ../frontend && pnpm exec tsc --noEmit -p . && pnpm exec vitest run src/features && pnpm exec biome check src/features
```

API tests that POST `/api/v1/protocols` with `name` must be updated: drop `name`, seed the default categories in a fixture (`POST /api/v1/protocol-categories/defaults`), and give each body either the facts its category pattern needs or a category whose pattern needs none (`"Plasma stability"`, `"Lipophilicity"`). Where two tests create protocols in the same workspace, give them different discriminators. Fix each one; do not loosen assertions.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/api/test_protocol_generated_names.py
git rm frontend/src/features/screening-assay/lib/suggest-protocol-name.ts frontend/src/features/screening-assay/lib/suggest-protocol-name.test.ts
git commit -m "feat(protocols): names are generated on create, edit, import and target changes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/tests frontend/src
```

---

### Task 15: Name preview and discriminator suggestions

**Files:**
- Create: `backend/src/cellar/application/screening/preview_protocol_name.py`
- Modify: DI, dependencies, `backend/src/cellar/interface/routes/protocols.py`
- Test: `backend/tests/api/test_protocol_name_preview.py`

**Interfaces:**
- Produces:
  - `PreviewProtocolNameQuery(workspace_id, category: str | None, target_ids: list[uuid.UUID], ontology_annotations: dict[str, list[dict]], discriminator: str | None, protocol_id: uuid.UUID | None = None)`; `PreviewProtocolName` (viewer) → `NamePreview(name: str, base: str, missing: list[str], missing_labels: list[str], clash: NameSibling | None, siblings: list[NameSibling], needs_discriminator: bool, discriminator_error: str | None, discriminator_in_pattern: bool)`.
  - `ListDiscriminatorsQuery(workspace_id, base: str | None, q: str | None)`; `ListDiscriminators` (viewer) → `list[str]`.
  - Routes: `POST /api/v1/protocols/name-preview` → `NamePreviewResponse` (fields as above; siblings/clash as `{protocol_id, code, name, discriminator}`); `GET /api/v1/protocols/discriminators?base=&q=` → `list[str]`. Declare both before any `/protocols/{protocol_id}` route.

- [ ] **Step 1: Failing API tests**

```python
MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}


async def test_preview_renders_and_reports_missing(client):
    await client.post("/api/v1/protocol-categories/defaults")
    r = await client.post("/api/v1/protocols/name-preview", json={"category": "Growth inhibition", "target_ids": [], "ontology_annotations": {}, "discriminator": None})
    body = r.json()
    assert r.status_code == 200 and body["missing"] == ["organism"] and body["missing_labels"] == ["an organism"]
    r = await client.post("/api/v1/protocols/name-preview", json={"category": "Growth inhibition", "target_ids": [], "ontology_annotations": {"organism": [MTB]}, "discriminator": "HTS"})
    assert r.json()["discriminator_error"] and r.json()["name"] == "M. tuberculosis growth inhibition"


async def test_preview_reports_a_clash_and_excludes_itself(client):
    await client.post("/api/v1/protocol-categories/defaults")
    body = {"protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}}
    p = (await client.post("/api/v1/protocols", json=body)).json()
    q = {"category": "Growth inhibition", "target_ids": [], "ontology_annotations": {"organism": [MTB]}, "discriminator": None}
    assert (await client.post("/api/v1/protocols/name-preview", json=q)).json()["clash"]["code"] == p["code"]
    assert (await client.post("/api/v1/protocols/name-preview", json=q | {"protocol_id": p["id"]})).json()["clash"] is None


async def test_discriminator_suggestions(client):
    await client.post("/api/v1/protocol-categories/defaults")
    body = {"protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}, "discriminator": "resazurin"}
    await client.post("/api/v1/protocols", json=body)
    r = await client.get("/api/v1/protocols/discriminators", params={"base": "M. tuberculosis growth inhibition"})
    assert r.json() == ["resazurin"]
```

Run → FAIL.

- [ ] **Step 2: Implement**

`preview_protocol_name.py`:

```python
class PreviewProtocolName:
    def __init__(self, uow: UnitOfWork, protocol_repo: ProtocolRepository, names: ProtocolNameService) -> None: ...

    async def __call__(self, input: PreviewProtocolNameQuery, auth: AuthContext | None = None) -> Result[NamePreview, DomainError]:
        require_workspace_role(auth, "viewer")
        require_same_workspace(auth, input.workspace_id)
        async with self._uow:
            discriminator_error = None
            try:
                discriminator = await self._names.clean_discriminator(input.workspace_id, input.discriminator)
            except ValidationError as exc:
                discriminator, discriminator_error = None, exc.message
            exclude_code = None
            if input.protocol_id is not None:
                existing = await self._protocols.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
                exclude_code = existing.code if existing else None
            annotations = {
                slot: [OntologyTerm(term_id=t["term_id"], label=t["label"], ontology_source=t["ontology_source"], uri=t.get("uri")) for t in terms]
                for slot, terms in input.ontology_annotations.items()
            }
            d = await self._names.derive(
                input.workspace_id, category=input.category, target_ids=input.target_ids,
                annotations=annotations, discriminator=discriminator, exclude_code=exclude_code,
            )
        return Success(
            NamePreview(
                name=d.rendered.name, base=d.rendered.base, missing=list(d.rendered.missing),
                missing_labels=[MISSING_FIELD_LABELS.get(m, m) for m in d.rendered.missing],
                clash=d.clash, siblings=list(d.siblings), needs_discriminator=d.needs_discriminator,
                discriminator_error=discriminator_error, discriminator_in_pattern=d.rendered.discriminator_in_pattern,
            )
        )
```

(Check that `ValidationError` exposes `.message`; `error_handlers.py` reads `error.message`, so it does.) `ListDiscriminators` calls `protocol_repo.list_discriminators(...)` inside the UoW. DI: both get `uow`, `SQLAlchemyProtocolRepository(uow)`, `_name_service(uow)`. Routes with request/response models; mark `NamePreviewResponse.clash: NameSiblingResponse | None`.

Run the API tests → PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/src/cellar/application/screening/preview_protocol_name.py backend/tests/api/test_protocol_name_preview.py
git commit -m "feat(protocols): name preview and discriminator suggestions endpoints

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/tests
```

---

### Task 16: Create dialog shows the generated name

**Files:**
- Create: `frontend/src/features/screening-assay/hooks/use-protocol-name-preview.ts`
- Create: `frontend/src/features/screening-assay/components/protocol-name-preview.tsx`, `frontend/src/features/screening-assay/components/discriminator-input.tsx`
- Modify: `frontend/src/features/screening-assay/components/create-protocol-dialog.tsx`
- Test: `frontend/src/features/screening-assay/components/protocol-name-preview.test.tsx`, `frontend/src/features/screening-assay/components/create-protocol-dialog.test.tsx` (new)

**Interfaces:**
- Consumes: Task 15 endpoints (regenerate orval: `NamePreviewResponse`).
- Produces:
  - `useProtocolNamePreview(draft: NamePreviewDraft | null)` → `{ data: NamePreviewResponse | undefined, isFetching: boolean }` where `NamePreviewDraft = { category: string | null; target_ids: string[]; ontology_annotations: Record<string, OntologyTerm[]>; discriminator: string | null; protocol_id?: string }`; debounced 300 ms; query key `["protocols", "name-preview", draft]`.
  - `useDiscriminatorSuggestions(base: string | null, q: string)` → `string[]` (GET `/protocols/discriminators`).
  - `<ProtocolNamePreview preview={...} isFetching={...} />`; `<DiscriminatorInput value onChange base />`.
  - `isPreviewSavable(preview?: NamePreviewResponse): boolean` (exported from `protocol-name-preview.tsx`): complete, no clash, no `needs_discriminator`, no `discriminator_error`.
  - `CreateProtocolDialog` prop `prefill?: Protocol` (copies type, category, targets, readouts, conditions, facets; leaves the discriminator empty).

- [ ] **Step 1: Failing component test** (`protocol-name-preview.test.tsx`)

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProtocolNamePreview, isPreviewSavable } from "./protocol-name-preview";

const base = {
  name: "M. tuberculosis growth inhibition [resazurin]", base: "M. tuberculosis growth inhibition",
  missing: [], missing_labels: [], clash: null, siblings: [], needs_discriminator: false,
  discriminator_error: null, discriminator_in_pattern: false,
};

describe("ProtocolNamePreview", () => {
  it("shows the name and that the code comes on save", () => {
    render(<ProtocolNamePreview preview={base} isFetching={false} />);
    expect(screen.getByText("M. tuberculosis growth inhibition [resazurin]")).toBeInTheDocument();
    expect(screen.getByText(/code is assigned when you create/i)).toBeInTheDocument();
    expect(isPreviewSavable(base)).toBe(true);
  });

  it("lists what is missing", () => {
    const p = { ...base, missing: ["organism"], missing_labels: ["an organism"] };
    render(<ProtocolNamePreview preview={p} isFetching={false} />);
    expect(screen.getByText(/needs an organism/i)).toBeInTheDocument();
    expect(isPreviewSavable(p)).toBe(false);
  });

  it("explains a clash with the other code", () => {
    const p = { ...base, clash: { protocol_id: "x", code: "PRT-00002", name: base.name, discriminator: "resazurin" } };
    render(<ProtocolNamePreview preview={p} isFetching={false} />);
    expect(screen.getByText(/PRT-00002/)).toBeInTheDocument();
    expect(isPreviewSavable(p)).toBe(false);
  });

  it("asks for a discriminator when siblings share the name", () => {
    const sib = { protocol_id: "y", code: "PRT-00003", name: "M. tuberculosis growth inhibition [OD600]", discriminator: "OD600" };
    const p = { ...base, name: base.base, siblings: [sib], needs_discriminator: true };
    render(<ProtocolNamePreview preview={p} isFetching={false} />);
    expect(screen.getByText(/add a discriminator/i)).toBeInTheDocument();
  });
});
```

Run → FAIL.

- [ ] **Step 2: Hook and components**

`use-protocol-name-preview.ts`:

```ts
"use client";

import { API_V1, customInstance } from "@/shared/lib/api/custom-instance";
import type { NamePreviewResponse } from "@/shared/lib/api/model";
import { useDebounce } from "@/shared/hooks/use-debounce";
import { useQuery } from "@tanstack/react-query";
import type { OntologyTerm } from "@/shared/components/ontology-search-input";

export interface NamePreviewDraft {
  category: string | null;
  target_ids: string[];
  ontology_annotations: Record<string, OntologyTerm[]>;
  discriminator: string | null;
  protocol_id?: string;
}

export function useProtocolNamePreview(draft: NamePreviewDraft | null) {
  const debounced = useDebounce(draft, 300);
  return useQuery({
    queryKey: ["protocols", "name-preview", debounced],
    queryFn: () =>
      customInstance<NamePreviewResponse>({ url: `${API_V1}/protocols/name-preview`, method: "POST", data: debounced }),
    enabled: debounced !== null,
    placeholderData: (previous) => previous,
  });
}

export function useDiscriminatorSuggestions(base: string | null, q: string) {
  const debouncedQ = useDebounce(q, 200);
  return useQuery({
    queryKey: ["protocols", "discriminators", base, debouncedQ],
    queryFn: () =>
      customInstance<string[]>({ url: `${API_V1}/protocols/discriminators`, method: "GET", params: { base, q: debouncedQ || undefined } }),
  }).data ?? [];
}
```

(Check `useDebounce`'s import path and signature in `@/shared/hooks/use-debounce`; `VocabularyAutocomplete` uses it.)

`protocol-name-preview.tsx`:

```tsx
"use client";

import type { NamePreviewResponse } from "@/shared/lib/api/model";
import { Loader2 } from "lucide-react";

export function isPreviewSavable(p?: NamePreviewResponse): boolean {
  return !!p && p.missing.length === 0 && !p.clash && !p.needs_discriminator && !p.discriminator_error;
}

export function ProtocolNamePreview({ preview, isFetching }: { preview?: NamePreviewResponse; isFetching: boolean }) {
  if (!preview) return <p className="text-sm text-muted-foreground">Pick a category to see the name.</p>;
  return (
    <div className="rounded-md border bg-muted/40 p-3" aria-live="polite">
      <div className="flex items-center gap-2">
        <span className="text-xs uppercase tracking-wide text-muted-foreground">Name</span>
        {isFetching && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" aria-hidden />}
      </div>
      <p className="mt-1 font-medium">{preview.name}</p>
      <p className="text-xs text-muted-foreground">The code is assigned when you create the protocol.</p>
      {preview.missing_labels.length > 0 && (
        <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">This name needs {preview.missing_labels.join(", ")}.</p>
      )}
      {preview.clash && (
        <p className="mt-2 text-sm text-destructive">
          {preview.clash.code} already has this exact name. Use a different discriminator.
        </p>
      )}
      {!preview.clash && preview.needs_discriminator && (
        <p className="mt-2 text-sm text-amber-700 dark:text-amber-400">
          Other protocols are also "{preview.base}" ({preview.siblings.map((s) => s.code).join(", ")}). Add a
          discriminator, such as the method.
        </p>
      )}
      {preview.discriminator_error && <p className="mt-2 text-sm text-destructive">{preview.discriminator_error}</p>}
    </div>
  );
}
```

`discriminator-input.tsx` (follow `vocabulary-autocomplete.tsx`, using `SearchCombobox`):

```tsx
"use client";

import { SearchCombobox } from "@/shared/components/search-combobox";
import { useState } from "react";
import { useDiscriminatorSuggestions } from "../hooks/use-protocol-name-preview";

interface DiscriminatorInputProps {
  value: string;
  onChange: (value: string) => void;
  base: string | null;
}

/** The one free part of a protocol name: a method or a fixed defining condition. */
export function DiscriminatorInput({ value, onChange, base }: DiscriminatorInputProps) {
  const [focused, setFocused] = useState(false);
  const suggestions = useDiscriminatorSuggestions(base, value).filter((s) => s.toLowerCase() !== value.toLowerCase());
  return (
    <SearchCombobox<string>
      searchValue={value}
      onSearchChange={onChange}
      items={suggestions.slice(0, 6)}
      getItemKey={(s) => s}
      renderItem={(s) => s}
      onSelect={(s) => {
        onChange(s);
        setFocused(false);
      }}
      open={focused && suggestions.length > 0}
      onOpenChange={(o) => !o && setFocused(false)}
      onInputFocus={() => setFocused(true)}
      placeholder="e.g. resazurin, hypoxia (only when needed)"
    />
  );
}
```

(Match `SearchCombobox`'s actual props, as `VocabularyAutocomplete` does.)

- [ ] **Step 3: Wire into the create dialog**

In `create-protocol-dialog.tsx`:
- add `discriminator: z.string()` to the schema (default `""`);
- `const preview = useProtocolNamePreview(categoryValue ? { category: categoryValue, target_ids: form.watch("target_ids"), ontology_annotations: ontologyAnnotations, discriminator: form.watch("discriminator") || null } : null);` where `categoryValue = form.watch("category") || null`;
- replace the Task 14 placeholder line with `<ProtocolNamePreview preview={preview.data} isFetching={preview.isFetching} />` and, under it, a "Discriminator (optional)" label with `<Controller name="discriminator" render={({ field }) => <DiscriminatorInput value={field.value} onChange={field.onChange} base={preview.data?.base ?? null} />} />` and helper text "Only needed when another protocol would get the same name. A method or a fixed condition, never a stage, library or date.";
- `canSubmit` additionally requires `isPreviewSavable(preview.data)`;
- payload adds `discriminator: values.discriminator.trim() || null`;
- `SimilarProtocolsPanel draft={{ name: preview.data?.name ?? "", ... }}` (its 2-character gate now sees the generated name);
- prop `prefill?: Protocol`: when set and the dialog opens, `form.reset({...})` from the protocol (protocol_type, target_ids from `prefill.targets`, category, description, dose_unit, readouts, conditions mapped the way `applyForm` maps a template) and `setOntologyAnnotations(prefill.ontology_annotations ?? {})`; title becomes "New protocol from {prefill.code}".

`create-protocol-dialog.test.tsx`: mock `../hooks/use-protocol-name-preview` (preview data with `missing_labels: ["an organism"]`), `../hooks/use-protocols`, `../hooks/use-targets`, `@/features/research-organization/hooks/use-projects`, `@/features/workspace-config/hooks/use-protocol-forms`, `@/features/workspace-config/hooks/use-protocol-categories`; render open; assert there is no textbox labelled "Name", the preview text "needs an organism" is visible, and "Create Protocol" is disabled. Copy the Radix stubs from `hit-criteria-dialog.test.tsx`.

```bash
cd frontend && pnpm generate:api   # then the orval churn block
pnpm exec vitest run src/features/screening-assay && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/screening-assay
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/screening-assay/hooks/use-protocol-name-preview.ts frontend/src/features/screening-assay/components/protocol-name-preview.tsx frontend/src/features/screening-assay/components/protocol-name-preview.test.tsx frontend/src/features/screening-assay/components/discriminator-input.tsx frontend/src/features/screening-assay/components/create-protocol-dialog.test.tsx
git commit -m "feat(protocols): create dialog previews the generated name

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src
```

---

### Task 17: Protocol page: discriminator, flags, search by discriminator

**Files:**
- Modify: `frontend/src/features/screening-assay/components/protocol-detail.tsx` (edit dialog)
- Modify: `frontend/src/features/screening-assay/components/detail-tabs/overview-tab.tsx`
- Modify: `frontend/src/features/screening-assay/hooks/use-protocols.ts` (`useSetProtocolDiscriminator`)
- Modify: `frontend/src/features/screening-assay/lib/protocol-facets.ts` (discriminator match field)
- Modify: `frontend/src/features/screening-assay/components/protocol-library-row.tsx` (flag badge)
- Test: `frontend/src/features/screening-assay/components/detail-tabs/overview-tab.test.tsx` (new or extend), `protocol-facets.test.ts`

**Interfaces:**
- Consumes: `PUT /protocols/{id}/discriminator` (Task 14), preview (Task 15).
- Produces: `useSetProtocolDiscriminator(protocolId)` mutation `({ discriminator, reason? })`; `<NameFlagNotice protocol />` (in `overview-tab.tsx`); `ProtocolMatchField` gains `"discriminator"`.

- [ ] **Step 1: Failing tests**

`overview-tab.test.tsx`: a protocol with `name_flag: "needs_facts"` shows text matching `/name is missing a field/i` and a link to the Design tab; `"needs_discriminator"` shows `/share this name/i`; `"name_conflict"` shows `/exact same name/i`; `null` shows none. `protocol-facets.test.ts`: `protocolTextMatch({...p, discriminator: "hypoxia"}, "hypox")?.field === "discriminator"` (place discriminator after alias in priority).

Run → FAIL.

- [ ] **Step 2: Implement**

- `protocol-facets.ts`: add `"discriminator"` to `ProtocolMatchField` and `["discriminator", p.discriminator ? [p.discriminator] : []]` after `alias`.
- `overview-tab.tsx`:

```tsx
const FLAG_TEXT: Record<string, string> = {
  needs_facts: "This protocol's name is missing a field its category needs. Fill it in on the Design tab; it cannot be published until then.",
  needs_discriminator: "Other protocols share this name. Add a discriminator (the method, or a fixed condition) so each one reads differently.",
  name_conflict: "A registry rename gave another protocol the exact same name. Change one of the discriminators.",
};

function NameFlagNotice({ protocol }: { protocol: Protocol }) {
  if (!protocol.name_flag) return null;
  return (
    <div role="status" className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
      {FLAG_TEXT[protocol.name_flag] ?? protocol.name_flag}{" "}
      {protocol.name_flag === "needs_facts" && <a className="underline" href="#design">Open the Design tab</a>}
    </div>
  );
}
```

Render it at the top of the overview. Add a "Discriminator" cell to the details grid (`protocol.discriminator ?? "—"`).
- `use-protocols.ts`: `useSetProtocolDiscriminator(protocolId)` → `PUT /protocols/${protocolId}/discriminator` with `data`, invalidates `PROTOCOLS_KEY`, `showSuccess("Discriminator saved")`, `showError` on failure.
- `protocol-detail.tsx` edit dialog (drafts): fields Description, Category (`ProtocolCategoryInput`), Discriminator (`DiscriminatorInput` with `base={preview.data?.base ?? null}`), and `<ProtocolNamePreview>` fed by `useProtocolNamePreview({ category: editCategory || null, target_ids: protocol.targets.map((t) => t.id), ontology_annotations: protocol.ontology_annotations ?? {}, discriminator: editDiscriminator || null, protocol_id: protocol.id })`. Save calls `updateMutation.mutate({ description, category })` and, when the discriminator changed, `setDiscriminator.mutate({ discriminator: editDiscriminator || null })`. Enable Save when `const draftSavable = !!preview.data && !preview.data.clash && !preview.data.needs_discriminator && !preview.data.discriminator_error;` (missing facts are allowed on drafts; they only block publishing).
- `protocol-library-row.tsx`: when `protocol.name_flag` is set, render `<Badge variant="warning" className="ml-2">{protocol.name_flag === "needs_facts" ? "incomplete name" : protocol.name_flag === "name_conflict" ? "name conflict" : "needs discriminator"}</Badge>`.

- [ ] **Step 3: Verify and commit**

```bash
cd frontend && pnpm exec vitest run src/features/screening-assay && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/screening-assay
git commit -m "feat(protocols): discriminator editing, name flags and preview on the protocol page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- frontend/src/features/screening-assay
```

---

# Part 3: Change handling

### Task 18: Correction, or a new assay

**Files:**
- Create: `backend/src/cellar/application/screening/correct_protocol.py`
- Modify: DI, dependencies, `backend/src/cellar/interface/routes/protocols.py`
- Create: `frontend/src/features/screening-assay/components/correct-protocol-dialog.tsx`
- Modify: `frontend/src/features/screening-assay/{hooks/use-protocols.ts,components/protocol-detail.tsx,components/detail-tabs/design-tab-protocol-card.tsx}`
- Test: `backend/tests/api/test_protocol_correction.py`, `frontend/src/features/screening-assay/components/correct-protocol-dialog.test.tsx`

**Interfaces:**
- Consumes: Task 12 correction guard; Task 13 service; Task 16 `CreateProtocolDialog prefill`; Task 15 preview.
- Produces: `CorrectProtocolCommand(workspace_id, protocol_id, reason: str, category: str | None | object = UNSET, discriminator: str | None | object = UNSET, ontology_annotations: dict[str, list[dict]] | object = UNSET, target_ids: list[uuid.UUID] | object = UNSET)`; `CorrectProtocol` (editor; ACTIVE only; one re-derivation and one audit entry per correction); route `POST /api/v1/protocols/{id}/correct` → `ProtocolResponse`; `useCorrectProtocol(protocolId)`; `<CorrectProtocolDialog protocol open onOpenChange />`.

- [ ] **Step 1: Failing API tests** (`test_protocol_correction.py`)

```python
MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}
SMEG = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1772", "label": "Mycolicibacterium smegmatis", "ontology_source": "NCBITAXON"}


async def _published(client, **over):
    await client.post("/api/v1/protocol-categories/defaults")
    body = {"protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}, "discriminator": "resazurin"} | over
    p = (await client.post("/api/v1/protocols", json=body)).json()
    assert (await client.post(f"/api/v1/protocols/{p['id']}/publish")).status_code == 200
    return p


async def test_correction_renames_with_reason(client):
    p = await _published(client)
    r = await client.post(f"/api/v1/protocols/{p['id']}/correct", json={"reason": "Strain was always M. smegmatis", "ontology_annotations": {"organism": [SMEG]}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "M. smegmatis growth inhibition [resazurin]" and body["code"] == p["code"]
    assert body["aliases"][0]["reason"] == "Correction: Strain was always M. smegmatis"


async def test_correction_needs_a_reason(client):
    p = await _published(client)
    r = await client.post(f"/api/v1/protocols/{p['id']}/correct", json={"reason": "  ", "discriminator": "OD600"})
    assert r.status_code == 422


async def test_drafts_are_edited_not_corrected(client):
    await client.post("/api/v1/protocol-categories/defaults")
    body = {"protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}}
    p = (await client.post("/api/v1/protocols", json=body)).json()
    assert (await client.post(f"/api/v1/protocols/{p['id']}/correct", json={"reason": "x", "discriminator": "OD600"})).status_code == 409


async def test_correction_cannot_leave_a_published_name_incomplete(client):
    p = await _published(client)
    r = await client.post(f"/api/v1/protocols/{p['id']}/correct", json={"reason": "x", "ontology_annotations": {"organism": []}})
    assert r.status_code == 422


async def test_correction_into_a_clash_is_409(client):
    a = await _published(client)
    b = await _published(client, discriminator="OD600")
    r = await client.post(f"/api/v1/protocols/{b['id']}/correct", json={"reason": "same method", "discriminator": "resazurin"})
    assert r.status_code == 409 and a["code"] in r.text
```

Run → FAIL.

- [ ] **Step 2: Implement `CorrectProtocol`**

```python
"""Correct a published protocol's name-feeding facts: one reason, one rename, one audit entry."""

@dataclass(frozen=True, kw_only=True)
class CorrectProtocolCommand(Command):
    workspace_id: uuid.UUID
    protocol_id: uuid.UUID
    reason: str
    category: str | None | object = UNSET
    discriminator: str | None | object = UNSET
    ontology_annotations: dict[str, list[dict]] | object = UNSET  # slot -> full replacement ([] clears)
    target_ids: list[uuid.UUID] | object = UNSET  # full set of direct targets


class CorrectProtocol:
    def __init__(self, uow: UnitOfWork, repo: ProtocolRepository, names: ProtocolNameService, dispatcher: EventDispatcherProtocol) -> None:
        self._uow, self._repo, self._names, self._dispatcher = uow, repo, names, dispatcher

    async def __call__(self, input: CorrectProtocolCommand, auth: AuthContext | None = None) -> Result[Protocol, DomainError]:
        require_editor(auth)
        require_same_workspace(auth, input.workspace_id)
        reason = " ".join(input.reason.split())
        if not reason:
            return Failure(ValidationError("A correction needs a reason"))
        user_id = auth.user_id if auth else None
        extra_events: list[DomainEvent] = []
        async with self._uow:
            protocol = await self._repo.find_by_id_in_workspace(input.workspace_id, input.protocol_id)
            if protocol is None:
                return Failure(NotFoundError("Protocol", input.protocol_id))
            if protocol.status != ProtocolStatus.ACTIVE:
                return Failure(ConflictError("Only published protocols are corrected; edit a draft directly"))
            if input.category is not UNSET:
                protocol.set_category(input.category, reason=reason)
            if input.discriminator is not UNSET:
                value = await self._names.clean_discriminator(input.workspace_id, input.discriminator)
                protocol.set_discriminator(value, reason=reason)
            if input.ontology_annotations is not UNSET:
                for slot, terms in input.ontology_annotations.items():
                    if terms:
                        protocol.set_ontology_annotation(slot, [OntologyTerm(**t) for t in terms], reason=reason)
                    else:
                        protocol.remove_ontology_annotation(slot, reason=reason)
            if input.target_ids is not UNSET:
                current = set(await self._repo.find_direct_target_ids(input.workspace_id, protocol.id))
                wanted = set(input.target_ids)
                for target_id in wanted - current:
                    linked = await self._repo.add_direct_target(input.workspace_id, protocol.id, target_id)
                    if linked == TargetLinkResult.TARGET_NOT_FOUND:
                        return Failure(NotFoundError("Target", target_id))
                    extra_events.append(ProtocolTargetAdded(aggregate_id=protocol.id, aggregate_type="Protocol", workspace_id=input.workspace_id, target_id=target_id, user_id=user_id))
                for target_id in current - wanted:
                    await self._repo.remove_direct_target(input.workspace_id, protocol.id, target_id)
                    extra_events.append(ProtocolTargetRemoved(aggregate_id=protocol.id, aggregate_type="Protocol", workspace_id=input.workspace_id, target_id=target_id, user_id=user_id))
            renamed = await self._names.apply(protocol, reason=f"Correction: {reason}", person=True, allow_incomplete=False, user_id=user_id)
            if isinstance(renamed, Failure):
                return renamed
            await self._repo.save(protocol)
            events = await self._uow.commit()
        await self._dispatcher.dispatch_all([*events, *extra_events])
        return Success(protocol)
```

(Leaving the `async with` without `commit()` rolls the session back; confirm in `AsyncUnitOfWork.__aexit__`. `OntologyTerm(**t)` must match the VO's fields; build it the way `SetOntologyAnnotation` does.) Route body `CorrectProtocolRequest(reason: str, category: str | None = None, discriminator: str | None = None, ontology_annotations: dict[str, list[OntologyTermRequest]] | None = None, target_ids: list[uuid.UUID] | None = None, model_config={"extra": "forbid"})`, mapping omitted fields to `UNSET` with `model_fields_set`.

Run the API tests → PASS.

- [ ] **Step 3: Frontend dialog**

Regenerate orval + churn. `useCorrectProtocol(protocolId)` → `POST /protocols/${id}/correct`, invalidates `PROTOCOLS_KEY`, `showSuccess("Protocol corrected")`.

`correct-protocol-dialog.tsx` (Dialog, two steps):
1. Choice, as a `RadioGroup` with two options: "Correction: it was always this" (helper: "The recorded facts were wrong. Same code; past results keep their protocol.") and "The assay changed" (helper: "A different experiment. It gets a new protocol and code; this one keeps its name and data."). "Continue".
2a. Correction: Category (`ProtocolCategoryInput`), Discriminator (`DiscriminatorInput`), the name-feeding facet slots from `useProtocolFacetSlots()` filtered to `organism`, `cell_line`, `assay_format` (`OntologySearchInput`), Targets (`TargetMultiSelect`, seeded from `useProtocolTargets(protocol.id)` direct targets), Reason (`Textarea`, required), and `<ProtocolNamePreview>` fed by `useProtocolNamePreview({...current edits, protocol_id: protocol.id})`. "Save correction" is enabled when the reason is non-blank and `isPreviewSavable(preview.data)`; it sends only the fields the user changed.
2b. Assay changed: text "We'll open a new protocol with this one's fields filled in. Change what is different; the name updates as you go." and a button "Create new protocol from this one" that closes this dialog and opens `CreateProtocolDialog` with `prefill={protocol}`.

`protocol-detail.tsx`: for `status === "active" && !is_locked` add a More-menu item "Correct details…" (opens the dialog) next to "New Version"; render `CreateProtocolDialog` with `prefill` when chosen. `design-tab-protocol-card.tsx`: for active protocols show a one-line hint under Targets and Ontology Annotations: "Published: use Correct details in the More menu."

`correct-protocol-dialog.test.tsx` (mock the hooks): choosing "The assay changed" and continuing shows the "Create new protocol from this one" button; on the correction path, Save stays disabled with an empty reason and enables after typing one (with a savable preview mocked).

```bash
cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_protocol_correction.py -q
cd ../frontend && pnpm exec vitest run src/features/screening-assay && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/screening-assay
```

- [ ] **Step 4: Commit**

```bash
git add backend/src/cellar/application/screening/correct_protocol.py backend/tests/api/test_protocol_correction.py frontend/src/features/screening-assay/components/correct-protocol-dialog.tsx frontend/src/features/screening-assay/components/correct-protocol-dialog.test.tsx
git commit -m "feat(protocols): correct a published protocol with a reason, or start a new assay from it

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/tests frontend/src
```

---

### Task 19: Admin edits preview their relabels

**Files:**
- Create: `backend/src/cellar/application/workspace_config/naming_changes.py`
- Modify: `backend/src/cellar/application/screening/protocol_naming_service.py` (`derive`/`apply` overrides)
- Modify: `backend/src/cellar/application/workspace_config/{protocol_categories.py,naming_labels.py}`, `backend/src/cellar/domain/screening_assay/protocol.py` (`relabel_category`)
- Create: `backend/src/cellar/application/workspace_config/set_home_organism.py`
- Modify: routes `protocol_categories.py`, `naming_labels.py`, `settings.py`; create route module `backend/src/cellar/interface/routes/protocol_names.py` (preview endpoint lives here; Task 21 adds more)
- Create: `frontend/src/features/workspace-config/components/naming-change-preview.tsx`
- Modify: `frontend/src/features/workspace-config/components/{protocol-category-admin.tsx,naming-label-admin.tsx,workspace-settings-form.tsx}`
- Test: `backend/tests/api/test_naming_change_preview.py`, `frontend/src/features/workspace-config/components/naming-change-preview.test.tsx`

**Interfaces:**
- Produces:
  - `ProtocolNameService.derive(..., pattern: str | None = None, ctx: NamingContext | None = None, check_siblings: bool = True)` and `apply(..., pattern: str | None = None, ctx: NamingContext | None = None)`: overrides used to compute a relabel before it is saved.
  - `Protocol.relabel_category(label: str) -> None` (any status; the same fact under a new word).
  - `NamingChangeRequest` (one of): `{"kind": "category", "category_id", "label"?: str, "name_pattern"?: str}`, `{"kind": "label", "term_id", "term_label", "ontology_source", "short_label": str | null}` (null = back to default), `{"kind": "home_organism", "term": {term_id,label,ontology_source} | null}`.
  - `PreviewNamingChange` (admin) → `NamingChangePreview(changes: list[NameChange(protocol_id, code, before, after)], collisions: list[NameCollision(name, codes: list[str])])`.
  - `UpdateProtocolCategory`, `CreateNamingLabel`, `UpdateNamingLabel`, `DeleteNamingLabel`, `SetHomeOrganism` all: compute the same preview; any collision → `Failure(ConflictError("… would give {codes} the same name …"))`; otherwise save the setting and apply each change with reason `"Category pattern changed"` / `"Category renamed"` / `"Short label changed: {term_label}"` / `"Home organism changed"`.
  - Routes: `POST /api/v1/protocol-names/preview-change` (body = NamingChangeRequest) → `NamingChangePreviewResponse`; `PUT /api/v1/settings/home-organism {term: {...} | null}` → `WorkspaceSettingsResponse`.
  - `<NamingChangePreview request onApply open onOpenChange />` frontend dialog: before → after table, collisions in red, "Apply" disabled while collisions exist.

- [ ] **Step 1: Failing API tests** (`test_naming_change_preview.py`)

```python
MTB = {"term_id": "http://purl.bioontology.org/ontology/NCBITAXON/1773", "label": "Mycobacterium tuberculosis", "ontology_source": "NCBITAXON"}


async def _setup(client):
    cats = (await client.post("/api/v1/protocol-categories/defaults")).json()
    body = {"protocol_type": "whole_cell", "category": "Growth inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}}
    a = (await client.post("/api/v1/protocols", json=body | {"discriminator": "resazurin"})).json()
    b = (await client.post("/api/v1/protocols", json=body | {"discriminator": "OD600"})).json()
    growth = next(c for c in cats if c["label"] == "Growth inhibition")
    return growth, a, b


async def test_label_override_preview_and_apply(client):
    growth, a, _ = await _setup(client)
    req = {"kind": "label", "term_id": MTB["term_id"], "term_label": MTB["label"], "ontology_source": "NCBITAXON", "short_label": "Mtb"}
    preview = (await client.post("/api/v1/protocol-names/preview-change", json=req)).json()
    assert {(c["before"], c["after"]) for c in preview["changes"]} >= {("M. tuberculosis growth inhibition [resazurin]", "Mtb growth inhibition [resazurin]")}
    assert preview["collisions"] == []
    r = await client.post("/api/v1/naming-labels", json={k: req[k] for k in ("term_id", "term_label", "ontology_source", "short_label")})
    assert r.status_code == 201
    assert (await client.get(f"/api/v1/protocols/{a['id']}")).json()["name"] == "Mtb growth inhibition [resazurin]"


async def test_pattern_edit_that_collides_is_refused(client):
    cats = (await client.post("/api/v1/protocol-categories/defaults")).json()
    bactericidal = next(c for c in cats if c["label"] == "Bactericidal activity")
    base = {"protocol_type": "whole_cell", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "ontology_annotations": {"organism": [MTB]}, "discriminator": "resazurin"}
    a = (await client.post("/api/v1/protocols", json=base | {"category": "Growth inhibition"})).json()
    c = (await client.post("/api/v1/protocols", json=base | {"category": "Bactericidal activity"})).json()
    req = {"kind": "category", "category_id": bactericidal["id"], "name_pattern": "{organism} growth inhibition"}
    preview = (await client.post("/api/v1/protocol-names/preview-change", json=req)).json()
    assert set(preview["collisions"][0]["codes"]) == {a["code"], c["code"]}
    r = await client.patch(f"/api/v1/protocol-categories/{bactericidal['id']}", json={"name_pattern": "{organism} growth inhibition"})
    assert r.status_code == 409


async def test_home_organism_drops_the_prefix(client, make_target):
    await client.post("/api/v1/protocol-categories/defaults")
    target = await make_target("PptT", organism="Mycobacterium tuberculosis")
    body = {"protocol_type": "biochemical", "category": "Enzyme inhibition", "readout_definitions": [{"name": "Signal", "data_type": "numeric"}], "target_ids": [str(target.id)]}
    p = (await client.post("/api/v1/protocols", json=body)).json()
    assert p["name"] == "M. tuberculosis PptT inhibition"
    preview = (await client.post("/api/v1/protocol-names/preview-change", json={"kind": "home_organism", "term": MTB})).json()
    assert ("M. tuberculosis PptT inhibition", "PptT inhibition") in {(x["before"], x["after"]) for x in preview["changes"]}
    assert (await client.put("/api/v1/settings/home-organism", json={"term": MTB})).status_code == 200
    assert (await client.get(f"/api/v1/protocols/{p['id']}")).json()["name"] == "PptT inhibition"
```

(`make_target` lives in `tests/api/conftest.py`; extend it with an `organism` keyword if it lacks one. The label test above also needs `growth` only for setup; drop the unused variable if ruff flags it.)

Run → FAIL.

- [ ] **Step 2: Service overrides**

`derive(...)` gains `pattern: str | None = None, ctx: NamingContext | None = None, check_siblings: bool = True`: when `pattern` is given skip the category lookup; when `ctx` is given use it instead of `await self.context(ws)`; when `check_siblings` is False return the rendered name with no sibling lookups. `apply(...)` passes `pattern`/`ctx` through to `derive`. Add `Protocol.relabel_category(label)` (sets `category`, `updated_at`; no guard; docstring "A category renamed by an admin: the same fact under a new word").

- [ ] **Step 3: `naming_changes.py`**

```python
"""What an admin naming edit would do to protocol names, computed before it is saved."""

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


async def compute_naming_change(
    *, workspace_id: uuid.UUID, protocol_repo: ProtocolRepository, names: ProtocolNameService,
    protocols: list[Protocol], pattern_for: Callable[[Protocol], str | None], ctx: NamingContext,
) -> NamingChangePreview:
    """Re-render `protocols` under the new pattern/labels and check every resulting name
    against every other protocol's current name in the workspace."""
    # ponytail: one derive per affected protocol (2 queries each); fine for hundreds of protocols,
    # batch the target lookups if workspaces reach thousands.
    changes: list[NameChange] = []
    after_by_code: dict[str, str] = {}
    for p in protocols:
        d = await names.derive(
            workspace_id, category=p.category, target_ids=await protocol_repo.find_direct_target_ids(workspace_id, p.id),
            annotations=p.ontology_annotations, discriminator=p.discriminator, exclude_code=p.code,
            pattern=pattern_for(p), ctx=ctx, check_siblings=False,
        )
        if d.rendered.complete and d.rendered.name != p.name:
            changes.append(NameChange(p.id, p.code, p.name, d.rendered.name))
        after_by_code[p.code or str(p.id)] = d.rendered.name if d.rendered.complete else p.name
    everyone = {(q.code or str(q.id)): q.name for q in await protocol_repo.find_by_workspace(workspace_id)}
    everyone.update(after_by_code)
    by_name: dict[str, list[str]] = {}
    for code, name in everyone.items():
        by_name.setdefault(name.lower(), []).append(code)
    collisions = [
        NameCollision(name=next(n for c, n in everyone.items() if c == codes[0]), codes=sorted(codes))
        for codes in by_name.values()
        if len(codes) > 1 and any(c in after_by_code for c in codes)
    ]
    return NamingChangePreview(changes=changes, collisions=collisions)
```

(`find_by_workspace` returns every version of every protocol; dedupe by code before building `everyone` so versions sharing a code don't count as a collision: `{q.code or str(q.id): q.name for q in sorted(rows, key=lambda q: q.protocol_version)}`.)

`PreviewNamingChange` (admin) dispatches on `kind`:
- `category`: load the category (NotFound), `pattern = new name_pattern or category.name_pattern`, `protocols = [p for p in all if (p.category or "").lower() == category.label.lower()]`, `pattern_for = lambda p: pattern`, `ctx = await names.context(ws)`. A label change alone produces no name changes (the label is not in names) but must still be checked for an existing category with that label (Conflict).
- `label`: `ctx` = current context with the override added/replaced (or removed when `short_label` is null) for both `overrides_by_term[term_id]` and `overrides_by_label[term_label.lower()]`; `protocols` = all; `pattern_for = lambda p: None` (normal lookup).
- `home_organism`: `ctx` = current context with `home_organism_label` replaced; `protocols` = all.

Each admin write use case calls `compute_naming_change` with the same inputs inside its UoW, returns `Failure(ConflictError(f"This would give {', '.join(c.codes)} the same name '{c.name}'"))` for the first collision, else saves the setting and, for each change, loads the protocol and calls `names.apply(protocol, reason=..., person=False, allow_incomplete=True, pattern=..., ctx=...)` and saves it; `UpdateProtocolCategory` with a new label also calls `protocol.relabel_category(new_label)` on every protocol in that category. `SetHomeOrganism` (`require_admin`) loads settings (or `create_default`), runs the preview, calls `settings.set_home_organism(term)`, applies, commits.

- [ ] **Step 4: Routes and frontend**

Routes per Interfaces (`protocol_names.py` router with prefix `/api/v1/protocol-names`; include in `app.py`). Regenerate orval + churn.

`naming-change-preview.tsx`:

```tsx
"use client";

import { Button } from "@/shared/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/shared/components/ui/dialog";
import type { NamingChangePreviewResponse } from "@/shared/lib/api/model";

interface NamingChangePreviewProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preview: NamingChangePreviewResponse | undefined;
  isLoading: boolean;
  onApply: () => void;
  isApplying: boolean;
}

/** Before -> after for every protocol an admin naming edit renames. Apply is an explicit gesture
 *  and stays disabled while any two protocols would end up with the same name. */
export function NamingChangePreview({ open, onOpenChange, preview, isLoading, onApply, isApplying }: NamingChangePreviewProps) {
  const collisions = preview?.collisions ?? [];
  const changes = preview?.changes ?? [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Protocols this renames</DialogTitle>
          <DialogDescription>
            {isLoading ? "Working out the new names..." : `${changes.length} protocol${changes.length === 1 ? "" : "s"} will be renamed. Old names stay searchable as former names.`}
          </DialogDescription>
        </DialogHeader>
        {collisions.length > 0 && (
          <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
            {collisions.map((c) => (
              <p key={c.name}>{c.codes.join(", ")} would all be named "{c.name}". Change a discriminator first.</p>
            ))}
          </div>
        )}
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr><th className="py-1 pr-3">Code</th><th className="py-1 pr-3">Now</th><th className="py-1">After</th></tr>
            </thead>
            <tbody>
              {changes.map((c) => (
                <tr key={c.protocol_id} className="border-t">
                  <td className="py-1 pr-3 font-mono text-xs">{c.code}</td>
                  <td className="py-1 pr-3 text-muted-foreground">{c.before}</td>
                  <td className="py-1">{c.after}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={onApply} disabled={isLoading || isApplying || collisions.length > 0}>
            {isApplying ? "Applying..." : "Apply"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

Hook `usePreviewNamingChange()` in `use-protocol-categories.ts` (or a new `use-naming-changes.ts`): a mutation POSTing to `/protocol-names/preview-change` returning the preview. Wire it:
- Category dialog Save → preview (`kind: "category"`) → `NamingChangePreview` → Apply calls the existing update mutation.
- Short label Save/Reset → preview (`kind: "label"`, `short_label` or `null`) → Apply calls create/update/delete.
- Settings "Protocols" card: add "Home organism" with `OntologySearchInput` (`ontologySources={["NCBITAXON"]}`, single term), helper "Targets from this organism are named without it (PptT inhibition, not M. tuberculosis PptT inhibition).", and a "Change" button → preview (`kind: "home_organism"`) → Apply calls `PUT /settings/home-organism`.

`naming-change-preview.test.tsx`: renders two changes and no collisions → Apply enabled and calls `onApply`; with a collision → alert text lists the codes and Apply is disabled.

```bash
cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_naming_change_preview.py tests/api/test_protocol_categories.py tests/api/test_naming_labels.py -q
cd ../frontend && pnpm exec vitest run src/features/workspace-config && pnpm exec tsc --noEmit -p . && pnpm exec biome check src/features/workspace-config
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/workspace_config/naming_changes.py backend/src/cellar/application/workspace_config/set_home_organism.py backend/src/cellar/interface/routes/protocol_names.py backend/tests/api/test_naming_change_preview.py frontend/src/features/workspace-config/components/naming-change-preview.tsx frontend/src/features/workspace-config/components/naming-change-preview.test.tsx
git commit -m "feat(protocols): admin naming edits preview and apply their relabels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/tests frontend/src
```

---

### Task 20: Registry renames propagate

**Files:**
- Modify: `backend/src/cellar/domain/screening_assay/events.py` (`TargetRenamed`)
- Modify: `backend/src/cellar/application/screening/sync_targets.py`
- Create: `backend/src/cellar/application/screening/rederive_protocol_names.py` (`RederiveProtocolNames`)
- Create: `backend/src/cellar/application/screening/target_renamed_handler.py`
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` + implementation (`find_protocol_ids_by_direct_target`)
- Modify: `backend/src/cellar/infrastructure/di/_screening.py`, `backend/src/cellar/interface/app.py` (handler registration)
- Test: `backend/tests/unit/application/screening/test_sync_targets.py` (extend), `backend/tests/integration/test_target_rename_rederive.py`

**Interfaces:**
- Produces:
  - `TargetRenamed(DomainEvent)`: `old_name: str`, `new_name: str`, `old_organism: str | None`, `new_organism: str | None` (aggregate_type `"Target"`, aggregate_id = target id).
  - `SyncTargetsFromProtCellar(uow, repo, source, freshness, dispatcher)`; emits `TargetRenamed` after commit for every existing target whose name or organism changed.
  - `ProtocolRepository.find_protocol_ids_by_direct_target(workspace_id, target_id) -> list[uuid.UUID]`.
  - `RederiveProtocolNamesCommand(workspace_id, protocol_ids: list[uuid.UUID], reason: str)`; `RederiveProtocolNames(uow_factory, names_factory, repo_factory, dispatcher)` → `Result[RederiveReport(renamed: int, flagged: int, failed: list[str]), DomainError]`; each protocol in its own UoW; one retry on `ConcurrencyConflictError`; a name over 400 characters keeps the old name, flags `needs_facts`, logs `protocol.name.too_long`.
  - `TargetRenamedHandler(rederive: Callable[[], RederiveProtocolNames], repo_factory)` registered for `TargetRenamed` in the app lifespan.

- [ ] **Step 1: Failing unit test for the sync** (extend `test_sync_targets.py`)

```python
class FakeDispatcher:
    def __init__(self):
        self.events = []

    async def dispatch_all(self, events):
        self.events.extend(events)


async def test_rename_emits_target_renamed_after_commit():
    tid = uuid.uuid4()
    existing = {tid: Target.from_mirror(id=tid, workspace_id=WS, name="Pks13TE Domain", target_type=TargetType.SINGLE_PROTEIN, organism="Mtb", chembl_id=None, source_version=1)}
    dispatcher = FakeDispatcher()
    uc, uow, repo, fresh = _build(FakeSource([_src(tid, "Pks13 TE domain", version=2)]), existing, ttl=0, dispatcher=dispatcher)
    await uc(SyncTargetsCommand(workspace_id=WS, forwarded_headers={}, force=True), auth=FakeAuth(role="admin"))
    (event,) = dispatcher.events
    assert (event.old_name, event.new_name, event.aggregate_id) == ("Pks13TE Domain", "Pks13 TE domain", tid)


async def test_version_bump_without_rename_emits_nothing():
    tid = uuid.uuid4()
    existing = {tid: Target.from_mirror(id=tid, workspace_id=WS, name="PptT", target_type=TargetType.SINGLE_PROTEIN, organism="Mtb", chembl_id=None, source_version=1)}
    dispatcher = FakeDispatcher()
    uc, uow, repo, fresh = _build(FakeSource([_src(tid, "PptT", version=2)]), existing, ttl=0, dispatcher=dispatcher)
    await uc(SyncTargetsCommand(workspace_id=WS, forwarded_headers={}, force=True), auth=FakeAuth(role="admin"))
    assert dispatcher.events == []
```

(Extend `_build` with a `dispatcher` argument defaulting to a `FakeDispatcher()`; match `Target.from_mirror`'s and `FakeAuth`'s real signatures in that file.)

Run → FAIL.

- [ ] **Step 2: Sync emits renames**

`SyncTargetsFromProtCellar.__init__` adds `dispatcher: EventDispatcherProtocol`. In the diff loop's update branch:

```python
                if current is not None and (current.name != st.name or current.organism != st.organism):
                    renamed.append(
                        TargetRenamed(
                            aggregate_id=st.id, aggregate_type="Target", workspace_id=input.workspace_id,
                            old_name=current.name, new_name=st.name,
                            old_organism=current.organism, new_organism=st.organism,
                        )
                    )
```

and after the `async with` block: `await self._dispatcher.dispatch_all(renamed)`. DI `_sync_targets` passes `c[EventDispatcher]`.

- [ ] **Step 3: Re-derive use case and handler**

`rederive_protocol_names.py`:

```python
"""Re-derive protocol names after something outside the protocol changed (registry, admin)."""

_log = structlog.get_logger(__name__)


@dataclass(frozen=True, kw_only=True)
class RederiveProtocolNamesCommand(Command):
    workspace_id: uuid.UUID
    protocol_ids: list[uuid.UUID]
    reason: str


@dataclass(frozen=True)
class RederiveReport:
    renamed: int
    flagged: int
    failed: list[str]


class RederiveProtocolNames:
    """System path: never refuses. Each protocol is its own unit of work so one concurrent edit
    cannot sink the whole batch; a version conflict is retried once."""

    def __init__(self, *, uow_factory, names_factory, repo_factory, dispatcher: EventDispatcherProtocol) -> None:
        self._uow_factory, self._names_factory, self._repo_factory, self._dispatcher = uow_factory, names_factory, repo_factory, dispatcher

    async def __call__(self, input: RederiveProtocolNamesCommand, auth: AuthContext | None = None) -> Result[RederiveReport, DomainError]:
        require_admin(auth)
        require_same_workspace(auth, input.workspace_id)
        renamed = flagged = 0
        failed: list[str] = []
        for protocol_id in input.protocol_ids:
            for attempt in (1, 2):
                try:
                    outcome = await self._one(input.workspace_id, protocol_id, input.reason)
                    renamed += outcome == "renamed"
                    flagged += outcome == "flagged"
                    break
                except ConcurrencyConflictError:
                    if attempt == 2:
                        failed.append(str(protocol_id))
                        _log.warning("protocol.name.rederive_conflict", protocol_id=str(protocol_id))
        return Success(RederiveReport(renamed=renamed, flagged=flagged, failed=failed))

    async def _one(self, workspace_id: uuid.UUID, protocol_id: uuid.UUID, reason: str) -> str:
        uow = self._uow_factory()
        async with uow:
            repo = self._repo_factory(uow)
            protocol = await repo.find_by_id_in_workspace(workspace_id, protocol_id)
            if protocol is None:
                return "missing"
            before = protocol.name
            try:
                await self._names_factory(uow).apply(protocol, reason=reason, person=False, allow_incomplete=True)
            except ValidationError:
                protocol.flag_name(NameFlag.NEEDS_FACTS)
                _log.warning("protocol.name.too_long", protocol_id=str(protocol_id))
            await repo.save(protocol)
            events = await uow.commit()
        await self._dispatcher.dispatch_all(events)
        if protocol.name != before:
            return "renamed"
        return "flagged" if protocol.name_flag else "unchanged"
```

(`require_admin(None)` returns early for system calls, per the guidelines.) `target_renamed_handler.py`:

```python
class TargetRenamedHandler:
    def __init__(self, rederive: Callable[[], RederiveProtocolNames], ids_for_target: Callable[[uuid.UUID, uuid.UUID], Awaitable[list[uuid.UUID]]]) -> None:
        self._rederive, self._ids_for_target = rederive, ids_for_target

    async def __call__(self, event: TargetRenamed) -> None:
        protocol_ids = await self._ids_for_target(event.workspace_id, event.aggregate_id)
        if protocol_ids:
            await self._rederive()(
                RederiveProtocolNamesCommand(
                    workspace_id=event.workspace_id, protocol_ids=protocol_ids,
                    reason=f"Registry renamed {event.old_name} to {event.new_name}",
                ),
                auth=None,
            )
```

`find_protocol_ids_by_direct_target`: `select protocol_id from protocol_targets join protocols ... where protocols.workspace_id = :ws and protocol_targets.target_id = :tid`. In `app.py` lifespan, after the audit registration:

```python
        from cellar.application.screening.rederive_protocol_names import RederiveProtocolNames
        from cellar.application.screening.target_renamed_handler import TargetRenamedHandler
        from cellar.domain.screening_assay.events import TargetRenamed

        async def _ids_for_target(workspace_id, target_id):
            uow = AsyncUnitOfWork(session_factory)
            async with uow:
                return await SQLAlchemyProtocolRepository(uow).find_protocol_ids_by_direct_target(workspace_id, target_id)

        dispatcher.register(TargetRenamed, TargetRenamedHandler(lambda: container[RederiveProtocolNames], _ids_for_target))
```

DI: `container.define(RederiveProtocolNames, lambda c: RederiveProtocolNames(uow_factory=lambda: AsyncUnitOfWork(c[async_sessionmaker]), names_factory=_name_service, repo_factory=SQLAlchemyProtocolRepository, dispatcher=c[EventDispatcher]))`.

Unit test `backend/tests/unit/application/screening/test_rederive_protocol_names.py`: with a fake `uow_factory` (the `FakeUnitOfWork` from `tests/unit/application/research_organization/_helpers.py`), a fake repo returning one protocol, and a fake names service whose `apply` raises `ConcurrencyConflictError` on the first call only, the report is `renamed=0 or 1, failed=[]` and `apply` was called twice; when it raises every time, `failed == [str(protocol_id)]` and no exception escapes.

- [ ] **Step 4: Integration test** (`test_target_rename_rederive.py`)

Seed: default categories, home organism Mtb, a target `Pks13TE Domain` (organism "Mycobacterium tuberculosis"), a protocol (category "Enzyme inhibition", target linked, discriminator "FP") named `Pks13TE Domain inhibition [FP]`. Run `RederiveProtocolNames` after renaming the target row to `Pks13 TE domain`. Assert the protocol reads `Pks13 TE domain inhibition [FP]`, its first alias is the old name with reason "Registry renamed …". Second test: lock the protocol first; the relabel still applies. Third test: rename the target to 450 characters; the protocol keeps its name and gets `name_flag == "needs_facts"`.

```bash
cd backend && uv run pytest tests/unit/application/screening/test_sync_targets.py -q && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration/test_target_rename_rederive.py tests/api/test_targets_sync.py -q
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/cellar/application/screening/rederive_protocol_names.py backend/src/cellar/application/screening/target_renamed_handler.py backend/tests/integration/test_target_rename_rederive.py
git commit -m "feat(protocols): registry target renames re-derive linked protocol names

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/tests
```

---

### Task 21: Re-derive all names, and the name flags page

**Files:**
- Modify: `backend/src/cellar/application/screening/rederive_protocol_names.py` (`RederiveAllProtocolNames`, `ListNameFlags`)
- Modify: `backend/src/cellar/domain/screening_assay/repository.py` + implementation (`find_flagged`, `list_lineage_ids`)
- Modify: `backend/src/cellar/interface/routes/protocol_names.py`, DI, dependencies
- Create: `frontend/src/features/workspace-config/components/protocol-names-admin.tsx`, `frontend/src/features/screening-assay/hooks/use-protocol-names-admin.ts`, `frontend/src/app/(dashboard)/admin/protocol-names/page.tsx`
- Modify: `frontend/src/shared/lib/navigation.ts`
- Test: `backend/tests/api/test_protocol_names_admin.py`, `frontend/src/features/workspace-config/components/protocol-names-admin.test.tsx`

**Interfaces:**
- Produces:
  - `RederiveAllProtocolNamesCommand(workspace_id, dry_run: bool, reason: str)` (admin): dry run returns `list[NameChange]` plus the flag each protocol would get (no writes); apply runs `RederiveProtocolNames` over every protocol id and returns its report.
  - `ListNameFlags` (viewer) → `list[FlaggedProtocol(protocol_id, code, name, flag)]`.
  - Routes: `GET /api/v1/protocol-names/flags`, `POST /api/v1/protocol-names/rederive {dry_run: bool, reason: str}` → `{changes: [...], report: {...} | null}`.
  - Admin page `/admin/protocol-names`: flags table (code, name linking to the protocol, flag), "Check all names" (dry run) → before/after table → "Apply" (explicit) → report toast.

- [ ] **Step 1: Failing API test**

Create two protocols, then directly break one's name in the DB (`UPDATE protocols SET name = 'Old hand-typed name', name_base = 'Old hand-typed name' WHERE id = :id` through the `db_session` fixture). `POST /protocol-names/rederive {"dry_run": true, "reason": "check"}` lists exactly that protocol with `before == "Old hand-typed name"` and the generated `after`, and the DB is unchanged; `{"dry_run": false, "reason": "Names generated from fields"}` → report `renamed == 1`, the protocol's aliases now include the old name. A protocol with no category shows up in `GET /flags` as `needs_facts` after the apply. `editor_client` POST → 403.

Run → FAIL.

- [ ] **Step 2: Implement**

`RederiveAllProtocolNames`: `require_admin`; `ids = await protocol_repo.list_lineage_ids(workspace_id)` (one id per code: the latest version; `select distinct on (coalesce(code, id::text)) id ... order by coalesce(code, id::text), protocol_version desc`). Dry run: inside one UoW, for each protocol `derive(...)` + `check(person=False, allow_incomplete=True)` → collect `NameChange` where the name differs, plus `flag`. Apply: call `RederiveProtocolNames` (injected) with all ids. Versions sharing a code: after applying the latest version, apply the same name to the older versions of that code in the same pass (iterate all ids, not only the latest, when applying; each version derives the same facts in practice, and `exclude_code` keeps them from clashing with each other). Use `find_by_workspace` ids for the apply, `list_lineage_ids` for the dry-run listing.

`ListNameFlags`: `find_flagged(workspace_id)` → `select id, code, name, name_flag from protocols where workspace_id = :ws and name_flag is not null order by code`, one row per code.

- [ ] **Step 3: Frontend page**

`use-protocol-names-admin.ts`: `useNameFlags()` (GET flags, key `["protocol-names", "flags"]`), `useRederiveNames()` (mutation POST rederive; invalidates `PROTOCOLS_KEY` and the flags key on apply). `protocol-names-admin.tsx`: `PageHeader` "Protocol names" (subtitle "Names are generated from each protocol's category and fields."); section "Needs attention" (flags table; empty state "Every protocol name is complete and unique."); section "Check all names" with a button that runs the dry run and shows the changes in the same before/after table layout as `NamingChangePreview` (reuse that component with `collisions=[]`), then "Apply" with reason "Names generated from fields". Page + navigation entry under "Vocabularies": `{ title: "Protocol Names", href: "/admin/protocol-names", icon: BookOpen, requires: "admin" }`. Test: flags render with codes; dry run result shows before/after; Apply calls the mutation with `dry_run: false`.

```bash
cd backend && DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/api/test_protocol_names_admin.py -q
cd ../frontend && pnpm exec vitest run src/features && pnpm exec tsc --noEmit -p . && pnpm exec biome check src
```

- [ ] **Step 4: Commit**

```bash
git add backend/tests/api/test_protocol_names_admin.py "frontend/src/app/(dashboard)/admin/protocol-names/page.tsx" frontend/src/features/workspace-config/components/protocol-names-admin.tsx frontend/src/features/workspace-config/components/protocol-names-admin.test.tsx frontend/src/features/screening-assay/hooks/use-protocol-names-admin.ts
git commit -m "feat(protocols): re-derive all names and a name flags page for admins

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- backend/src/cellar backend/tests frontend/src
```

---

# Part 4: Migration and wrap-up

### Task 22: SACLAB-DEV facts and targets (user confirmations required)

**Files (local, gitignored):** `backend/data/vault-protocols/curated/load_curated.py`, `backend/data/vault-protocols/curated/naming_facts.json` (new), `backend/data/vault-protocols/curated/older_protocols.json` (new), `backend/data/vault-protocols/curated/VERIFICATION.md`

**Interfaces:**
- Consumes: Tasks 9-21 (slots, categories, labels, correction-free draft edits, rederive).
- Produces: every SACLAB-DEV protocol has the facts its category pattern needs, or a recorded reason it doesn't.

This task changes shared dev data and, with permission, another application. Each sub-step that writes outside Cellar's local DB waits for the user's explicit "yes" in chat.

- [ ] **Step 1: Setup in SACLAB-DEV**

Through the running app (these are also walkthrough steps): set Home organism = Mycobacterium tuberculosis (Settings → Protocols, preview + apply); confirm the 27 categories exist (Admin → Protocol Categories); create the Cell line ontology slot if the admin slot list is used (Admin → Ontology Slots: name `cell_line`, label "Cell line", sources CLO, CL, search mode, free text allowed).

- [ ] **Step 2: Missing targets list → user**

From `catalog.json` list every protocol whose curated target is not linked (`target_in_registry` false or unmatched) with: target name in registry style (gene symbol where one exists, per the naming rule memory), organism, and the protocols needing it. Write it to `naming_facts.json` → `"missing_targets"` and show the user the table. **User ruling (2026-10-08): import them into prot-cellar.** Prepare `backend/data/vault-protocols/curated/prot_cellar_targets.csv` (`pref_name,gene_symbol,organism`) and import it through prot-cellar's own import path; show the user the list right before running the import.

- [ ] **Step 3: Sync and link**

After the targets exist: `POST /api/v1/targets/sync` (force), then `load_curated.py --link-targets` adds each protocol's direct target through `AddProtocolTarget` (drafts: no reason; the name re-derives). Report linked / still missing.

- [ ] **Step 4: Facts from the curated decisions**

`load_curated.py --prepare-naming` (dry run first, printing every change):
- Cell line facet: for each protocol whose members state one fixed cell line (curated `cell_line`; not those with a Cell line condition), resolve the CLO term by exact label search in BioPortal (`HepG2` → "HepG2 cell" etc.) or CL for cell types (`Macrophage`). Print the mapping table and have the user approve it before applying through `SetOntologyAnnotation`.
- Organism genus for panels: `Mycobacterial growth inhibition …` → NCBITaxon 1763 "Mycobacterium"; `Bacterial growth inhibition` → 2 "Bacteria"; `Alphavirus infection inhibition` → 11019 "Alphavirus" (verify each id with BioPortal before applying).
- Discriminator: the bracket of each current curated name (`[resazurin]` → `resazurin`), through `SetProtocolDiscriminator`.
- Category fixes for the user to approve: `Redox cycling detection` → Detection interference (discriminator `redox cycling`); new category "Protein-protein interaction inhibition" with pattern `{target} interaction inhibition` for `RNA polymerase-NusG interaction inhibition` (discriminator `NusG`); `Unspecified enzyme inhibition`: ask the user (keep as `needs_facts`, or a named target).

- [ ] **Step 5: The 19 older protocols**

Read each one individually (name, description, readouts, conditions, runs), the same way the 195 were curated (rule: curate by hand, not by regex). Record one decision per protocol in `older_protocols.json` (category, organism / cell line / format, target, discriminator, or "leave as needs_facts" with a reason). **User ruling (2026-10-08):** protocols that fit get their facts applied; those that don't fit go on a "revisit later" list (`older_protocols.json` → `"revisit_later"`, each with the reason) and keep `needs_facts`. Show the user both lists at the end of the task.

- [ ] **Step 6: Record**

Append the rulings and mappings to `VERIFICATION.md` under "Auto-naming facts (2026-10-xx)". Nothing to commit (gitignored).

---

### Task 23: Generate names for existing protocols

**Files (local):** `backend/data/vault-protocols/curated/load_curated.py`; scratchpad review file.

- [ ] **Step 1: Dry run**

`POST /api/v1/protocol-names/rederive {"dry_run": true, "reason": "Names generated from fields"}` (admin session, or the use case through the container in a script like `load_curated.py`). Save the result to the scratchpad as JSON.

- [ ] **Step 2: Read every change**

Go through every before → after pair individually and note anything wrong (an unexpected organism prefix, a short label that reads badly, a discriminator that should not be there). Fix the cause (a short label, a fact, a pattern), never the output, and re-run the dry run until clean.

- [ ] **Step 3: User review**

Show the user the full before → after list (publish it as an Artifact page if it is longer than ~60 rows) with the counts: renamed / unchanged / flagged, and the flags with their reasons. Apply only after the user approves.

- [ ] **Step 4: Apply and verify**

`POST /api/v1/protocol-names/rederive {"dry_run": false, "reason": "Names generated from fields"}`. Verify in the DB: every protocol's former name is an alias; `select name_flag, count(*) from protocols where workspace_id = '442df0cf-e618-4938-a089-80ae2f1e43e7' group by 1` matches the reviewed flags; no two codes share a name (`select lower(name), count(distinct code) from protocols where workspace_id = ... group by 1 having count(distinct code) > 1` returns nothing).

- [ ] **Step 5: Loader on the new create path**

`load_curated.py`: drop `name=` from `CreateProtocolCommand`, pass `discriminator`, the cell line annotation and the panel genus organisms; seed categories (`SeedDefaultProtocolCategories`), set the home organism, then create. Keep `--unload`. Run `--dry-run` to confirm it builds every command (not committed).

---

### Task 24: Wrap-up, review, walkthrough

- [ ] **Step 1: Backlog notes** (force-add; `docs/` is gitignored)

`docs/backlog/workspace-settings-valueerror-500.md`: `WorkspaceSettings.update()` raises `ValueError` for bad registration prefix/width; there is no `ValueError` handler, so `PATCH /settings` returns 500 instead of 422; fix: raise `ValidationError` (the new protocol naming settings already do). `docs/backlog/frontend-protocol-type-hand-rolled.md`: `Protocol`, `CreateProtocolInput` and `ProtocolType` in `features/screening-assay/types/index.ts` are hand-written mirrors of DTOs (CLAUDE.md forbids it); new fields were typed off `ProtocolResponse`; aliasing the whole type is its own change.

```bash
git add -f docs/backlog/workspace-settings-valueerror-500.md docs/backlog/frontend-protocol-type-hand-rolled.md
git commit -m "docs(backlog): settings ValueError 500, hand-rolled Protocol type

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/backlog/workspace-settings-valueerror-500.md docs/backlog/frontend-protocol-type-hand-rolled.md
```

- [ ] **Step 2: daikon heads-up (draft for the user to send)**

Draft a short message: protocol names are now generated and will change when facts or labels change; key on protocol `id`; new fields on protocol responses and summaries: `code` (stable, `PRT-00142`), `discriminator`, `aliases`, `name_flag`; published campaign `protocol_ref` and `source_protocols` gain `code`. Show it to the user; the user sends it.

- [ ] **Step 3: Full verification**

```bash
cd backend && uv run ruff check src tests && uv run ruff format --check src tests && uv run lint-imports && uv run pytest tests/unit -q
DOCKER_HOST=unix:///Users/sidx/.docker/run/docker.sock uv run pytest tests/integration tests/api -q
cd ../frontend && pnpm exec tsc --noEmit -p . && pnpm exec vitest run && pnpm lint; echo "lint exit=$status"
```

Expected: all green; `pnpm lint` exit 0 (check the exit code, not the piped output). Record any pre-existing unrelated failure in `docs/backlog/` instead of fixing it here.

- [ ] **Step 4: One whole-branch review**

Use superpowers:requesting-code-review once for the whole branch (`git diff main...feat/protocol-auto-naming`), with the spec and this plan as context. Fix confirmed findings, re-run Step 3.

- [ ] **Step 5: Audit display check**

Open the audit trail page for a renamed protocol (Admin → Audit). Expected: the rename entry shows old name, new name and reason. If the page shows only entity ids (no current name beside the name at the time, spec section 3), record it in `docs/backlog/audit-current-entity-name.md` rather than building it here.

- [ ] **Step 6: Status and board**

Update `docs/implementation-status.md` (local) with the feature. Update or create the GitHub project board issue for protocol auto-naming (`gh issue list --repo sidxz/cellar --search "protocol name"`; ask the user before creating a new issue).

- [ ] **Step 7: Walkthrough in Claude-in-Chrome**

With the user, in their signed-in Chrome on localhost:3000, go through spec section 7 item by item (first-time setup, then daily use), including the live registry-rename demo. Record a GIF of the flow if the user wants one.
