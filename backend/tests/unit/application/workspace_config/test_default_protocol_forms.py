"""Every shipped form is a valid starting point for a protocol."""

import uuid

import pytest

from cellar.application.screening._dose_response_config_serde import (
    deserialize_dose_response_config,
)
from cellar.domain.screening_assay.enums import (
    ConditionDataType,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
)
from cellar.domain.screening_assay.protocol import (
    ConditionDefinition,
    Protocol,
    ReadoutDefinition,
    is_reserved_readout_name,
)
from cellar.domain.shared.protocol_naming import DEFAULT_CATEGORY_PATTERNS
from cellar.domain.shared.units import COMMON_UNITS, canonical_unit
from cellar.domain.workspace_config.default_protocol_forms import DEFAULT_PROTOCOL_FORMS


def test_shipped_form_count():
    assert len(DEFAULT_PROTOCOL_FORMS) == 61


def test_every_default_category_has_a_form_and_forms_name_real_categories():
    assert {f.category for f in DEFAULT_PROTOCOL_FORMS} == set(DEFAULT_CATEGORY_PATTERNS)


def test_one_default_only_where_a_category_has_one_form():
    by_cat: dict[str, list] = {}
    for f in DEFAULT_PROTOCOL_FORMS:
        by_cat.setdefault(f.category, []).append(f)
    for forms in by_cat.values():
        assert sum(f.is_default for f in forms) == (1 if len(forms) == 1 else 0)


def test_form_names_are_unique_within_a_category():
    keys = [(f.category, f.name.lower()) for f in DEFAULT_PROTOCOL_FORMS]
    assert len(keys) == len(set(keys))


def test_readout_and_condition_names_are_unique_within_a_form():
    for f in DEFAULT_PROTOCOL_FORMS:
        readouts = [r.name.lower() for r in f.readouts]
        conditions = [c.name.lower() for c in f.conditions]
        assert len(readouts) == len(set(readouts)), f.name
        assert len(conditions) == len(set(conditions)), f.name


def test_every_shipped_unit_is_canonical_and_suggested():
    suggested = {s.unit for s in COMMON_UNITS}
    for f in DEFAULT_PROTOCOL_FORMS:
        for unit in [r.unit for r in f.readouts] + [c.unit for c in f.conditions]:
            if unit is not None:
                assert canonical_unit(unit) == unit, (f.name, unit)
                assert unit in suggested, (f.name, unit)


@pytest.mark.parametrize("form", DEFAULT_PROTOCOL_FORMS, ids=lambda f: f"{f.category}: {f.name}")
def test_each_form_builds_a_valid_protocol(form):
    pid = uuid.uuid4()
    readouts = [
        ReadoutDefinition(
            protocol_id=pid,
            name=r.name,
            data_type=ReadoutDataType(r.data_type),
            unit=r.unit,
            pick_list_values=r.pick_list_values,
            normalizations=frozenset(
                {ReadoutNormalization(r.normalization)} if r.normalization != "none" else set()
            ),
            dose_response_config=deserialize_dose_response_config(r.dose_response_config)
            if r.dose_response_config
            else None,
        )
        for r in form.readouts
    ]
    Protocol.create(
        workspace_id=uuid.uuid4(),
        name="x",
        protocol_type=ProtocolType(form.protocol_type),
        created_by=uuid.uuid4(),
        readout_definitions=readouts,
        condition_definitions=[
            ConditionDefinition(
                protocol_id=pid,
                name=c.name,
                data_type=ConditionDataType(c.data_type),
                unit=c.unit,
                pick_list_values=c.pick_list_values,
            )
            for c in form.conditions
        ]
        or None,
    )

    # The create path checks dose-response references later (add_readout_definition), not in
    # the constructor, so assert the invariant here.
    by_name: dict[str, object] = {}
    for r in form.readouts:
        assert not is_reserved_readout_name(r.name)
        if r.data_type == "dose_response":
            cfg = r.dose_response_config
            y = by_name[cfg["y_readout_name"]]  # must name an earlier readout of this form
            if cfg.get("y_normalization"):
                assert y.normalization == cfg["y_normalization"]
        by_name[r.name] = r
