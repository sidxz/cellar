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
# middle dot, em dash, en dash: never in a protocol name
_FORBIDDEN = {"\u00b7": " ", "\u2014": "-", "\u2013": "-"}
_STAGE_RE = re.compile(
    r"\b(hts|re-?test|primary screen|hit confirmation|dose[ -]?response|ic\d{2}"
    r"|single[ -]point|triplicate)\b",
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
    ShippedLabel(f"{NCBITAXON}10090", "Mus musculus", "Mouse"),
    ShippedLabel(f"{NCBITAXON}10116", "Rattus norvegicus", "Rat"),
    ShippedLabel(
        f"{NCBITAXON}694009", "Severe acute respiratory syndrome-related coronavirus", "SARS-CoV-2"
    ),
    ShippedLabel(
        f"{NCBITAXON}1335626", "Middle East respiratory syndrome-related coronavirus", "MERS-CoV"
    ),
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
        raise ValidationError(f"{what} cannot contain '\u00b7', '\u2014' or '\u2013'")


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
    # Virus names are not binomials: "Zika virus" stays whole.
    if re.search(r"vir(us|oid)|phage", label, re.IGNORECASE):
        return label
    words = label.split()
    if len(words) >= 2 and words[0].isalpha() and words[0][0].isupper() and words[1].islower():
        # Species and below (strain, variant): "Plasmodium falciparum 3D7" -> "P. falciparum 3D7".
        return f"{words[0][0]}. {' '.join(words[1:])}"
    if len(words) == 1:
        return f"{words[0]} spp."
    return label


def _capitalize(name: str) -> str:
    """Capitalize a plain lowercase first word; leave "pLDH", "mRNA" and non-ASCII ("β") alone."""
    first = name.split(" ", 1)[0]
    if "a" <= name[:1] <= "z" and first == first.lower():
        return name[0].upper() + name[1:]
    return name


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


def with_discriminator(base: str, discriminator: str) -> str:
    """The name a protocol gets when its discriminator trails the base in brackets."""
    return f"{base} [{discriminator}]"


def render_protocol_name(pattern: str, inputs: NamingInputs, ctx: NamingContext) -> RenderedName:
    target = "/".join(_target_label(t, ctx) for t in inputs.targets) or None
    organism = _joined(inputs.organisms, ctx)
    cell_line = _joined(inputs.cell_lines, ctx)
    subject_from, subject = next(
        (
            (k, v)
            for k, v in (("target", target), ("organism", organism), ("cell_line", cell_line))
            if v
        ),
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
    discriminator_in_pattern = any(
        m.group(1) == "discriminator" for m in _SLOT_RE.finditer(pattern)
    )
    missing: list[str] = []
    pieces: list[str] = []
    # Only a registry target keeps its own case at the start (hERG); the rest is capitalized.
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
        base = _capitalize(base)
    discriminator = values["discriminator"]
    name = (
        base
        if discriminator_in_pattern or not discriminator
        else with_discriminator(base, discriminator)
    )
    return RenderedName(
        name=name,
        base=base,
        missing=tuple(missing),
        discriminator_in_pattern=discriminator_in_pattern,
    )


def clean_discriminator(value: str | None, *, library_names: Iterable[str] = ()) -> str | None:
    if value is None:
        return None
    validate_name_text(value, what="Discriminator")
    cleaned = " ".join(value.split())
    if not cleaned:
        return None
    if len(cleaned) > MAX_DISCRIMINATOR_LENGTH:
        raise ValidationError(
            f"Discriminator must be at most {MAX_DISCRIMINATOR_LENGTH} characters"
        )
    if "[" in cleaned or "]" in cleaned:
        raise ValidationError("Discriminator cannot contain '[' or ']'")
    if m := _STAGE_RE.search(cleaned):
        raise ValidationError(
            f"'{m.group(0)}' is a screening stage; record it on the run, not in the protocol name"
        )
    if m := _DATE_RE.search(cleaned):
        raise ValidationError(f"'{m.group(0)}' looks like a date; dates belong on runs")
    if m := _VERSION_RE.search(cleaned):
        raise ValidationError(
            f"'{m.group(0)}' marks a version; protocol versions are tracked separately"
        )
    for library in library_names:
        core = re.sub(r"\s+library$", "", library.strip(), flags=re.IGNORECASE)
        if len(core) >= 2 and re.search(
            rf"(?<!\w){re.escape(core)}(?!\w)", cleaned, re.IGNORECASE
        ):
            raise ValidationError(
                f"'{core}' is a compound library; it belongs on the campaign, "
                "not the protocol name"
            )
    return cleaned
