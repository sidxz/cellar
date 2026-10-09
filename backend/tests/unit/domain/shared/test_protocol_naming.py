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

HOME = NamingContext(home_organism_labels=frozenset({"mycobacterium tuberculosis"}))
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


def test_several_home_organisms_drop_every_home_prefix():
    ctx = NamingContext(home_organism_labels=frozenset({"homo sapiens", MTB_ORG.lower()}))
    herg = render_protocol_name(
        "{target} inhibition", NamingInputs(targets=(NamingTarget("hERG", "Homo sapiens"),)), ctx
    )
    inha = render_protocol_name(
        "{target} inhibition", NamingInputs(targets=(NamingTarget("InhA", MTB_ORG),)), ctx
    )
    mouse = render_protocol_name(
        "{target} inhibition", NamingInputs(targets=(NamingTarget("DHFR", "Mus musculus"),)), ctx
    )
    assert (herg.name, inha.name) == ("hERG inhibition", "InhA inhibition")
    assert mouse.name == "Mouse DHFR inhibition"


def test_admin_override_beats_rule_and_shipped_label():
    ctx = NamingContext(
        overrides_by_term={MTB.term_id: "Mtb"}, home_organism_labels=frozenset({MTB_ORG.lower()})
    )
    assert (
        render_protocol_name(
            "{organism} growth inhibition", NamingInputs(organisms=(MTB,)), ctx
        ).name
        == "Mtb growth inhibition"
    )


def test_target_organism_override_by_label():
    ctx = NamingContext(
        overrides_by_label={"homo sapiens": "hs"},
        home_organism_labels=frozenset({MTB_ORG.lower()}),
    )
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


def test_every_default_pattern_is_valid_and_has_47_categories():
    assert len(DEFAULT_CATEGORY_PATTERNS) == 47
    for pattern in DEFAULT_CATEGORY_PATTERNS.values():
        validate_pattern(pattern)


def test_generic_pattern_for_new_categories():
    assert generic_pattern("Biofilm inhibition") == "{subject?} biofilm inhibition"


@pytest.mark.parametrize(
    ("pattern", "discriminator", "expected"),
    [
        ("{discriminator} interference", "pLDH", "pLDH interference"),
        ("{discriminator?} solubility", "mRNA-based", "mRNA-based solubility"),
        ("{discriminator?} solubility", "kinetic", "Kinetic solubility"),
    ],
)
def test_leading_discriminator_with_its_own_capitals_keeps_its_case(
    pattern, discriminator, expected
):
    assert _render(pattern, discriminator=discriminator).name == expected


def test_non_ascii_first_letter_is_not_uppercased():
    assert _render("β-hematin formation inhibition").name == "β-hematin formation inhibition"
    assert (
        _render(generic_pattern("β-Hematin formation inhibition")).name
        == "β-Hematin formation inhibition"
    )


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Plasmodium falciparum 3D7", "P. falciparum 3D7"),
        ("Mycobacterium tuberculosis H37Rv", "M. tuberculosis H37Rv"),
        ("Mycobacterium tuberculosis variant bovis BCG", "M. tuberculosis variant bovis BCG"),
        ("Escherichia coli K-12", "E. coli K-12"),
        ("Zika virus", "Zika virus"),
        ("Dengue virus", "Dengue virus"),
        ("Japanese encephalitis virus", "Japanese encephalitis virus"),
        ("Human immunodeficiency virus 1", "Human immunodeficiency virus 1"),
        ("Alphavirus", "Alphavirus"),
        ("[Mycobacterium] stephanolepidis", "[Mycobacterium] stephanolepidis"),
    ],
)
def test_taxon_short_label(label, expected):
    term = NamingTerm(f"{NCBITAXON}0", label, "NCBITAXON")
    assert _render("{organism} growth inhibition", organisms=(term,)).name == (
        f"{expected} growth inhibition"
    )


@pytest.mark.parametrize(
    ("taxon_id", "label", "expected"),
    [("10090", "Mus musculus", "Mouse"), ("10116", "Rattus norvegicus", "Rat")],
)
def test_lab_animals_ship_common_names(taxon_id, label, expected):
    term = NamingTerm(f"{NCBITAXON}{taxon_id}", label, "NCBITAXON")
    assert _render("{organism?} pharmacokinetics", organisms=(term,)).name == (
        f"{expected} pharmacokinetics"
    )
    target = NamingTarget("Cyp3a11", label)
    assert _render("{target} inhibition", ctx=NamingContext(), targets=(target,)).name == (
        f"{expected} Cyp3a11 inhibition"
    )


PF = NamingTerm(f"{NCBITAXON}5833", "Plasmodium falciparum", "NCBITAXON")
PF_3D7 = NamingTerm("free_text:3D7", "3D7", "free_text")
STRAIN_PATTERN = "{organism} {strain?} growth inhibition"


def test_strain_follows_the_organism_as_typed():
    r = _render(STRAIN_PATTERN, organisms=(PF,), strains=(PF_3D7,))
    assert r.name == "P. falciparum 3D7 growth inhibition" and r.complete


def test_without_a_strain_the_optional_slot_leaves_no_gap():
    assert _render(STRAIN_PATTERN, organisms=(PF,)).name == "P. falciparum growth inhibition"


def test_a_required_strain_with_none_is_missing():
    r = _render("{organism} {strain} growth inhibition", organisms=(PF,))
    assert r.missing == ("strain",)
    assert r.name == "P. falciparum (strain needed) growth inhibition"


def test_strain_gets_no_short_label_rule_but_an_override_applies():
    # An NCBITaxon-looking strain still reads as typed; no "spp." or genus abbreviation.
    h37rv = NamingTerm(f"{NCBITAXON}83332", "H37Rv", "NCBITAXON")
    assert _render(STRAIN_PATTERN, organisms=(MTB,), strains=(h37rv,)).name == (
        "M. tuberculosis H37Rv growth inhibition"
    )
    ctx = NamingContext(overrides_by_term={PF_3D7.term_id: "3D7 (CQ-sensitive)"})
    assert (
        _render(STRAIN_PATTERN, ctx=ctx, organisms=(PF,), strains=(PF_3D7,)).name
        == "P. falciparum 3D7 (CQ-sensitive) growth inhibition"
    )


@pytest.mark.parametrize("pattern", [STRAIN_PATTERN, "{organism} {strain} growth inhibition"])
def test_strain_is_a_valid_slot(pattern):
    validate_pattern(pattern)
