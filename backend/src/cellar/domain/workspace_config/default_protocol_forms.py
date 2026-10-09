"""Shipped starting points, one or more per default category.

General conventions only. A category with more than one common readout convention ships each
as its own form and none is the default; a category with one form gets it as its default.
"""

from __future__ import annotations

from dataclasses import dataclass

from cellar.domain.workspace_config.protocol_form import (
    ProtocolFormCondition,
    ProtocolFormReadout,
)

BAO = "http://www.bioassayontology.org/bao#"


@dataclass(frozen=True)
class DefaultForm:
    category: str
    name: str
    protocol_type: str
    readouts: tuple[ProtocolFormReadout, ...]
    conditions: tuple[ProtocolFormCondition, ...] = ()
    assay_format: tuple[str, str] | None = None  # (BAO code, label)
    assay_format_from_target: bool = False
    is_default: bool = False


def _signal(normalization: str) -> ProtocolFormReadout:
    return ProtocolFormReadout(name="Signal", data_type="numeric", normalization=normalization)


def _fit(name: str, curve: str, normalization: str) -> ProtocolFormReadout:
    return ProtocolFormReadout(
        name=name,
        data_type="dose_response",
        unit="µM",
        dose_response_config={
            "curve_type": curve,
            "y_readout_name": "Signal",
            "y_normalization": normalization,
        },
    )


def _value(name: str, unit: str | None = None) -> ProtocolFormReadout:
    return ProtocolFormReadout(name=name, data_type="numeric", unit=unit)


def _pick(name: str, *values: str) -> ProtocolFormReadout:
    return ProtocolFormReadout(name=name, data_type="pick_list", pick_list_values=list(values))


def _cond(name: str, data_type: str = "numeric", unit: str | None = None) -> ProtocolFormCondition:
    return ProtocolFormCondition(name=name, data_type=data_type, unit=unit)


_BIOCHEMICAL = ("BAO_0000217", "biochemical format")
_ORGANISM = ("BAO_0000218", "organism-based format")
_CELL = ("BAO_0000219", "cell based format")
_PHYSCHEM = ("BAO_0000100", "small-molecule physicochemical format")
_PLASMA = ("BAO_0020003", "plasma format")
_MICROSOME = ("BAO_0000251", "microsome format")
_CELL_FREE = ("BAO_0000366", "cell-free format")

_INH, _ACT, _CTRL = "percent_inhibition", "percent_activation", "percent_control"
_IN_VIVO_DOSING = (_cond("Dose", unit="mg/kg"), _cond("Route", "text"))
_GENOTOX_RESULT = _pick("Result", "positive", "negative", "equivocal")


def _dr(category, name, ptype, fmt, curve, norm, **kw) -> DefaultForm:
    return DefaultForm(
        category,
        name,
        ptype,
        (_signal(norm), _fit(name.split()[0], curve, norm)),
        assay_format=fmt,
        **kw,
    )


DEFAULT_PROTOCOL_FORMS: tuple[DefaultForm, ...] = (
    _dr(
        "Enzyme inhibition",
        "IC50 dose-response",
        "biochemical",
        _BIOCHEMICAL,
        "ic50",
        _INH,
        assay_format_from_target=True,
    ),
    DefaultForm(
        "Enzyme inhibition",
        "% inhibition single point",
        "biochemical",
        (_signal(_INH),),
        assay_format=_BIOCHEMICAL,
        assay_format_from_target=True,
    ),
    DefaultForm(
        "Enzyme inhibition",
        "Ki",
        "biochemical",
        (
            _value("Ki", "µM"),
            _pick("Mechanism", "competitive", "noncompetitive", "uncompetitive", "mixed"),
        ),
        (_cond("Substrate concentration", unit="µM"),),
        assay_format=_BIOCHEMICAL,
        assay_format_from_target=True,
    ),
    DefaultForm(
        "Enzyme inhibition",
        "kinact/KI",
        "biochemical",
        (_value("kinact", "s⁻¹"), _value("KI", "µM"), _value("kinact/KI", "M⁻¹s⁻¹")),
        assay_format=_BIOCHEMICAL,
        assay_format_from_target=True,
    ),
    _dr(
        "Enzyme activation",
        "EC50 dose-response",
        "biochemical",
        _BIOCHEMICAL,
        "ec50",
        _ACT,
        assay_format_from_target=True,
    ),
    DefaultForm(
        "Enzyme activation",
        "% activation single point",
        "biochemical",
        (_signal(_ACT),),
        assay_format=_BIOCHEMICAL,
        assay_format_from_target=True,
    ),
    DefaultForm(
        "Binding",
        "Kd",
        "biochemical",
        (_value("Kd", "µM"),),
        assay_format=_BIOCHEMICAL,
        assay_format_from_target=True,
    ),
    DefaultForm(
        "Binding",
        "Thermal shift (ΔTm)",
        "biochemical",
        (_value("ΔTm", "°C"),),
        assay_format=_BIOCHEMICAL,
        assay_format_from_target=True,
    ),
    _dr(
        "Receptor function",
        "EC50 dose-response",
        "cell_based",
        _CELL,
        "ec50",
        _ACT,
        is_default=True,
    ),
    _dr(
        "Ion-channel inhibition",
        "IC50 dose-response",
        "cell_based",
        _CELL,
        "ic50",
        _INH,
        is_default=True,
    ),
    DefaultForm(
        "Growth inhibition", "MIC", "whole_cell", (_value("MIC", "µM"),), assay_format=_ORGANISM
    ),
    _dr("Growth inhibition", "IC50 dose-response", "whole_cell", _ORGANISM, "ic50", _INH),
    DefaultForm(
        "Growth inhibition",
        "% inhibition single point",
        "whole_cell",
        (_signal(_INH),),
        assay_format=_ORGANISM,
    ),
    DefaultForm(
        "Bactericidal activity",
        "MBC",
        "whole_cell",
        (_value("MBC", "µM"),),
        assay_format=_ORGANISM,
        is_default=True,
    ),
    _dr(
        "Intracellular growth inhibition",
        "IC50 dose-response",
        "cell_based",
        _CELL,
        "ic50",
        _INH,
        is_default=True,
    ),
    DefaultForm(
        "Metabolite rescue",
        "MIC",
        "whole_cell",
        (_value("MIC", "µM"),),
        (_cond("Metabolite", "text"),),
        assay_format=_ORGANISM,
        is_default=True,
    ),
    _dr(
        "Membrane potential",
        "EC50 dose-response",
        "whole_cell",
        _ORGANISM,
        "ec50",
        _CTRL,
        is_default=True,
    ),
    DefaultForm(
        "Resistance selection",
        "Frequency of resistance",
        "whole_cell",
        (_value("Frequency of resistance"),),
        (_cond("Selecting concentration", unit="µM"),),
        assay_format=_ORGANISM,
        is_default=True,
    ),
    DefaultForm(
        "Combination (checkerboard)",
        "FICI",
        "whole_cell",
        (_value("FICI"),),
        assay_format=_ORGANISM,
        is_default=True,
    ),
    _dr("Cytotoxicity", "CC50 dose-response", "cell_based", _CELL, "ic50", _CTRL, is_default=True),
    _dr(
        "Infection inhibition",
        "EC50 dose-response",
        "cell_based",
        _CELL,
        "ec50",
        _INH,
        is_default=True,
    ),
    _dr(
        "In vitro translation inhibition",
        "IC50 dose-response",
        "biochemical",
        _CELL_FREE,
        "ic50",
        _INH,
        is_default=True,
    ),
    _dr(
        "Intrabacterial pH homeostasis",
        "EC50 dose-response",
        "whole_cell",
        _ORGANISM,
        "ec50",
        _CTRL,
        is_default=True,
    ),
    DefaultForm(
        "Detection interference",
        "% inhibition single point",
        "biochemical",
        (_signal(_INH),),
        assay_format=_BIOCHEMICAL,
        is_default=True,
    ),
    DefaultForm(
        "Metabolic stability",
        "Metabolic stability",
        "admet",
        (_value("% remaining", "%"), _value("CLint", "µL/min/mg")),
        (_cond("Incubation time", unit="min"),),
        assay_format=_MICROSOME,
        is_default=True,
    ),
    DefaultForm(
        "Plasma stability",
        "Plasma stability",
        "admet",
        (_value("% remaining", "%"),),
        (_cond("Incubation time", unit="min"),),
        assay_format=_PLASMA,
        is_default=True,
    ),
    DefaultForm(
        "Plasma protein binding",
        "Plasma protein binding",
        "admet",
        (_value("Fraction unbound", "fraction"),),
        assay_format=_PLASMA,
        is_default=True,
    ),
    # Cell-monolayer and artificial-membrane permeability are both common; none is preselected.
    DefaultForm(
        "Permeability",
        "Bidirectional",
        "admet",
        (
            _value("Papp A→B", "×10⁻⁶ cm/s"),
            _value("Papp B→A", "×10⁻⁶ cm/s"),
            _value("Efflux ratio"),
        ),
        assay_format=_CELL,
    ),
    DefaultForm(
        "Permeability",
        "PAMPA",
        "admet",
        (_value("Pe", "×10⁻⁶ cm/s"),),
        assay_format=_CELL_FREE,
    ),
    DefaultForm(
        "Solubility",
        "Solubility",
        "physicochemical",
        (_value("Solubility", "µM"),),
        (_cond("pH"),),
        assay_format=_PHYSCHEM,
        is_default=True,
    ),
    DefaultForm(
        "Lipophilicity",
        "LogD",
        "physicochemical",
        (_value("LogD"),),
        (_cond("pH"),),
        assay_format=_PHYSCHEM,
        is_default=True,
    ),
    DefaultForm(
        "Compound identity / purity",
        "Purity",
        "analytical",
        (_value("Purity", "%"),),
        assay_format=_PHYSCHEM,
        is_default=True,
    ),
    DefaultForm(
        "Pharmacokinetics",
        "Pharmacokinetics",
        "in_vivo",
        (_value("Cmax", "ng/mL"), _value("AUC", "ng·h/mL"), _value("t1/2", "h")),
        _IN_VIVO_DOSING,
        assay_format=_ORGANISM,
        is_default=True,
    ),
    # Efficacy is read three common ways (bacterial burden, parasitemia, tumour growth); each is
    # its own form and none is preselected.
    *(
        DefaultForm(
            "In vivo efficacy",
            name,
            "in_vivo",
            (readout,),
            _IN_VIVO_DOSING,
            assay_format=_ORGANISM,
        )
        for name, readout in (
            ("log₁₀ CFU reduction", _value("log₁₀ CFU reduction")),
            ("% parasitemia reduction", _value("% parasitemia reduction", "%")),
            ("% tumour growth inhibition", _value("TGI", "%")),
        )
    ),
    DefaultForm(
        "Prediction",
        "Prediction score",
        "in_silico",
        (_value("Prediction score"),),
        is_default=True,
    ),
    _dr("Cell-line growth inhibition", "GI50 dose-response", "cell_based", _CELL, "ic50", _INH),
    _dr("Cell-line growth inhibition", "IC50 dose-response", "cell_based", _CELL, "ic50", _INH),
    _dr(
        "CYP inhibition",
        "IC50 dose-response",
        "biochemical",
        _BIOCHEMICAL,
        "ic50",
        _INH,
        is_default=True,
    ),
    DefaultForm(
        "CYP time-dependent inhibition",
        "IC50 shift",
        "biochemical",
        (
            _value("IC50 −NADPH", "µM"),  # noqa: RUF001 -- typographic minus, pairs with "+NADPH"
            _value("IC50 +NADPH", "µM"),
            _value("Fold shift"),
        ),
        assay_format=_BIOCHEMICAL,
    ),
    DefaultForm(
        "CYP time-dependent inhibition",
        "kinact/KI",
        "biochemical",
        (_value("kinact", "s⁻¹"), _value("KI", "µM")),
        assay_format=_BIOCHEMICAL,
    ),
    DefaultForm(
        "CYP induction",
        "Fold induction",
        "cell_based",
        (_value("Fold induction"), _value("EC50", "µM"), _value("Emax")),
        assay_format=_CELL,
        is_default=True,
    ),
    DefaultForm(
        "Target engagement", "CETSA", "cell_based", (_value("ΔTagg", "°C"),), assay_format=_CELL
    ),
    DefaultForm(
        "Target engagement",
        "NanoBRET IC50 dose-response",
        "cell_based",
        (_signal(_INH), _fit("IC50", "ic50", _INH)),
        assay_format=_CELL,
    ),
    DefaultForm(
        "Genotoxicity",
        "Ames",
        "cell_based",
        (_GENOTOX_RESULT,),
        (
            _cond("Strain", "text"),
            ProtocolFormCondition(
                name="S9", data_type="pick_list", pick_list_values=["with", "without"]
            ),
        ),
        assay_format=_CELL,
    ),
    DefaultForm(
        "Genotoxicity",
        "Micronucleus",
        "cell_based",
        (_value("% micronucleated cells", "%"), _GENOTOX_RESULT),
        assay_format=_CELL,
    ),
    DefaultForm(
        "Mitochondrial toxicity",
        "Glu/Gal",
        "cell_based",
        (_value("IC50 glucose", "µM"), _value("IC50 galactose", "µM"), _value("Ratio")),
        assay_format=_CELL,
        is_default=True,
    ),
    DefaultForm(
        "Hemolysis",
        "HC50",
        "cell_based",
        (_value("HC50", "µM"), _value("% hemolysis", "%")),
        assay_format=_CELL,
        is_default=True,
    ),
    DefaultForm(
        "Blood-to-plasma ratio",
        "B/P",
        "admet",
        (_value("B/P ratio"),),
        assay_format=_PLASMA,
        is_default=True,
    ),
    DefaultForm(
        "Tissue binding",
        "Fraction unbound",
        "admet",
        (_value("Fraction unbound", "fraction"),),
        assay_format=_MICROSOME,
        is_default=True,
    ),
    DefaultForm(
        "Ionization constant",
        "pKa",
        "physicochemical",
        (_value("pKa"),),
        assay_format=_PHYSCHEM,
        is_default=True,
    ),
    DefaultForm(
        "Chemical stability",
        "Chemical stability",
        "physicochemical",
        (_value("% remaining", "%"),),
        (_cond("pH"), _cond("Incubation time", unit="min")),
        assay_format=_PHYSCHEM,
        is_default=True,
    ),
    DefaultForm(
        "Time-kill",
        "Time-kill",
        "whole_cell",
        (_value("log₁₀ CFU reduction"),),
        (_cond("Concentration", unit="×MIC"), _cond("Time", unit="h")),
        assay_format=_ORGANISM,
        is_default=True,
    ),
    _dr(
        "Liver-stage inhibition",
        "IC50 dose-response",
        "cell_based",
        _CELL,
        "ic50",
        _INH,
        conditions=(_cond("Host cell line", "text"),),
        is_default=True,
    ),
    DefaultForm(
        "Transmission blocking",
        "SMFA",
        "whole_cell",
        (
            _value("% oocyst intensity inhibition", "%"),
            _value("% prevalence reduction", "%"),
        ),
        assay_format=_ORGANISM,
        is_default=True,
    ),
    _dr(
        "Gametocytocidal activity",
        "IC50 dose-response",
        "whole_cell",
        _ORGANISM,
        "ic50",
        _INH,
        is_default=True,
    ),
    DefaultForm(
        "Parasite killing rate",
        "PRR",
        "whole_cell",
        (_value("log PRR"), _value("PCT99.9", "h"), _value("Lag phase", "h")),
        assay_format=_ORGANISM,
        is_default=True,
    ),
    _dr(
        "β-Hematin formation inhibition",
        "IC50 dose-response",
        "biochemical",
        _BIOCHEMICAL,
        "ic50",
        _INH,
        is_default=True,
    ),
    DefaultForm(
        "Tolerability",
        "MTD",
        "in_vivo",
        (_value("MTD", "mg/kg"),),
        (_cond("Route", "text"), _cond("Dosing regimen", "text")),
        assay_format=_ORGANISM,
        is_default=True,
    ),
    DefaultForm(
        "Pharmacodynamics",
        "Biomarker response",
        "in_vivo",
        (_value("% change", "%"),),
        _IN_VIVO_DOSING,
        assay_format=_ORGANISM,
        is_default=True,
    ),
)
