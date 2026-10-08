"""Naming policy: patterns rendered from facts, short labels, discriminator guard."""

import pytest

from cellar.domain.shared.errors import ValidationError
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
        (
            "{target} inhibition",
            {"targets": (NamingTarget("PptT", MTB_ORG),), "discriminator": "FP"},
            "PptT inhibition [FP]",
        ),
        (
            "{target} binding",
            {"targets": (NamingTarget("GlcB", MTB_ORG),), "discriminator": "nanoDSF"},
            "GlcB binding [nanoDSF]",
        ),
        ("{target} inhibition", {"targets": (NamingTarget("hERG", None),)}, "hERG inhibition"),
        (
            "{target} inhibition",
            {"targets": (NamingTarget("MDH2", "Homo sapiens"),)},
            "Human MDH2 inhibition",
        ),
        (
            "{target} inhibition",
            {"targets": (NamingTarget("Mpro", SARS),), "discriminator": "FRET"},
            "SARS-CoV-2 Mpro inhibition [FRET]",
        ),
        (
            "{target} inhibition",
            {"targets": (NamingTarget("3CLpro", MERS),)},
            "MERS-CoV 3CLpro inhibition",
        ),
        (
            "{target} inhibition",
            {"targets": (NamingTarget("PanD", MTB_ORG), NamingTarget("PanC", MTB_ORG))},
            "PanD/PanC inhibition",
        ),
        (
            "{target} {discriminator}",
            {"targets": (NamingTarget("Kinin receptor", None),), "discriminator": "activation"},
            "Kinin receptor activation",
        ),
        (
            "{organism} growth inhibition",
            {"organisms": (MTB,), "discriminator": "hypoxia"},
            "M. tuberculosis growth inhibition [hypoxia]",
        ),
        (
            "{organism} growth inhibition",
            {"organisms": (SMEG,), "discriminator": "resazurin"},
            "M. smegmatis growth inhibition [resazurin]",
        ),
        (
            "{organism} growth inhibition",
            {"organisms": (MYCO_GENUS,), "discriminator": "resazurin"},
            "Mycobacterium spp. growth inhibition [resazurin]",
        ),
        (
            "{organism} growth inhibition",
            {"organisms": (BACTERIA,)},
            "Bacterial growth inhibition",
        ),
        (
            "Intracellular {organism} growth inhibition",
            {"organisms": (MTB,), "discriminator": "luciferase reporter"},
            "Intracellular M. tuberculosis growth inhibition [luciferase reporter]",
        ),
        (
            "{organism} in vivo efficacy",
            {"organisms": (CRYPTO,)},
            "Cryptosporidium in vivo efficacy",
        ),
        ("{organism} membrane potential", {"organisms": (ECOLI,)}, "E. coli membrane potential"),
        (
            "{cell_line} cytotoxicity",
            {"cell_lines": (HEPG2,), "discriminator": "CellTiter-Glo"},
            "HepG2 cytotoxicity [CellTiter-Glo]",
        ),
        ("{cell_line} cytotoxicity", {"cell_lines": (MACROPHAGE,)}, "Macrophage cytotoxicity"),
        ("{matrix} stability", {"matrices": (MICROSOME,)}, "Microsomal stability"),
        ("Plasma protein binding", {}, "Plasma protein binding"),
        ("{cell_line?} permeability", {"cell_lines": (CACO2,)}, "Caco-2 permeability"),
        ("{cell_line?} permeability", {"discriminator": "PAMPA"}, "Permeability [PAMPA]"),
        ("{discriminator?} solubility", {"discriminator": "kinetic"}, "Kinetic solubility"),
        ("{discriminator?} solubility", {}, "Solubility"),
        (
            "{subject?} {discriminator} prediction",
            {"targets": (NamingTarget("Mdh", MTB_ORG),), "discriminator": "docking score"},
            "Mdh docking score prediction",
        ),
        (
            "{subject?} {discriminator} prediction",
            {"discriminator": "toxicity score"},
            "Toxicity score prediction",
        ),
        (
            "{discriminator} interference",
            {"discriminator": "AMC quenching"},
            "AMC quenching interference",
        ),
        (
            "{target} inhibition",
            {"targets": (NamingTarget("RNA polymerase·NusG", MTB_ORG),)},
            "RNA polymerase NusG inhibition",
        ),
    ],
)
def test_renders_names(pattern, inputs, expected):
    assert _render(pattern, **inputs).name == expected


def test_base_drops_trailing_discriminator_but_keeps_placed_one():
    assert (
        _render(
            "{target} inhibition", targets=(NamingTarget("PptT", MTB_ORG),), discriminator="FP"
        ).base
        == "PptT inhibition"
    )
    placed = _render("{discriminator?} solubility", discriminator="kinetic")
    assert placed.base == "Kinetic solubility" and placed.discriminator_in_pattern


def test_missing_required_slot_is_reported_with_a_placeholder():
    r = _render("{organism} growth inhibition")
    assert r.missing == ("organism",) and not r.complete
    assert r.name == "(organism needed) growth inhibition"


def test_missing_placed_discriminator_is_reported():
    assert _render("{subject?} {discriminator} prediction").missing == ("discriminator",)


def test_without_home_organism_every_target_gets_its_organism():
    r = render_protocol_name(
        "{target} inhibition",
        NamingInputs(targets=(NamingTarget("PptT", MTB_ORG),)),
        NamingContext(),
    )
    assert r.name == "M. tuberculosis PptT inhibition"


def test_admin_override_beats_rule_and_shipped_label():
    ctx = NamingContext(overrides_by_term={MTB.term_id: "Mtb"}, home_organism_label=MTB_ORG)
    assert (
        render_protocol_name(
            "{organism} growth inhibition", NamingInputs(organisms=(MTB,)), ctx
        ).name
        == "Mtb growth inhibition"
    )


def test_target_organism_override_by_label():
    ctx = NamingContext(overrides_by_label={"homo sapiens": "hs"}, home_organism_label=MTB_ORG)
    r = render_protocol_name(
        "{target} inhibition", NamingInputs(targets=(NamingTarget("MDH2", "Homo sapiens"),)), ctx
    )
    assert r.name == "hs MDH2 inhibition"


@pytest.mark.parametrize(
    "bad", ["HTS", "dose response", "2021", "12/05", "v2", "corrected", "IC50"]
)
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
