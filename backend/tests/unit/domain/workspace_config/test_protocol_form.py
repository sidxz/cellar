"""Unit tests for ProtocolForm aggregate and related VOs."""

from __future__ import annotations

import uuid
from uuid import uuid4

import pytest

from cellar.domain.shared.errors import ValidationError
from cellar.domain.workspace_config.protocol_form import (
    ProtocolForm,
    ProtocolFormCreated,
    ProtocolFormReadout,
    ProtocolFormUpdated,
)


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid4()


def _readout(name: str = "IC50", data_type: str = "numeric") -> ProtocolFormReadout:
    return ProtocolFormReadout(name=name, data_type=data_type, unit="nM")


# ---------------------------------------------------------------------------
# Value Objects
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ProtocolForm — create
# ---------------------------------------------------------------------------


class TestProtocolFormCreate:
    def test_factory(self, ws_id: uuid.UUID) -> None:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="Biochemical Assay",
            readout_templates=[_readout()],
        )
        assert form.description is None
        assert form.protocol_type is None
        assert form.is_default is False
        assert form.condition_templates == []
        assert form.ontology_defaults == []
        assert form.version == 1

    def test_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="",
                readout_templates=[_readout()],
            )

    def test_whitespace_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="name"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="   ",
                readout_templates=[_readout()],
            )

    def test_name_is_stripped(self, ws_id: uuid.UUID) -> None:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="  Trimmed  ",
            readout_templates=[_readout()],
        )
        assert form.name == "Trimmed"

    def test_no_readouts_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="readout"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="Bad Form",
                readout_templates=[],
            )

    def test_none_readouts_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="readout"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="Bad Form",
            )

    def test_readout_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="readout template name"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="Form",
                readout_templates=[ProtocolFormReadout(name="", data_type="numeric")],
            )

    def test_factory_emits_created_event(self, ws_id: uuid.UUID) -> None:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="Standard",
            readout_templates=[_readout()],
        )
        events = form.collect_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, ProtocolFormCreated)
        assert event.aggregate_id == form.id
        assert event.aggregate_type == "ProtocolForm"
        assert event.workspace_id == ws_id
        assert event.name == "Standard"

    def test_readout_templates_are_independent_copy(self, ws_id: uuid.UUID) -> None:
        src = [_readout()]
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="F",
            readout_templates=src,
        )
        src.clear()
        assert len(form.readout_templates) == 1


# ---------------------------------------------------------------------------
# ProtocolForm — update
# ---------------------------------------------------------------------------


class TestProtocolFormUpdate:
    def _make(self, ws_id: uuid.UUID) -> ProtocolForm:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="Original",
            readout_templates=[_readout()],
        )
        form.clear_events()
        return form

    def test_rename(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        form.update(name="Renamed")
        assert form.name == "Renamed"
        events = form.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ProtocolFormUpdated)

    def test_update_readouts(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        new_readout = _readout("EC50")
        form.update(readout_templates=[new_readout])
        assert len(form.readout_templates) == 1
        assert form.readout_templates[0].name == "EC50"

    def test_update_readouts_empty_raises(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        with pytest.raises(ValidationError, match="readout"):
            form.update(readout_templates=[])

    def test_update_readout_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        with pytest.raises(ValidationError, match="readout template name"):
            form.update(readout_templates=[ProtocolFormReadout(name="", data_type="text")])

    def test_update_empty_name_raises(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        with pytest.raises(ValidationError, match="name"):
            form.update(name="")

    def test_update_no_args_is_noop_with_event(self, ws_id: uuid.UUID) -> None:
        form = self._make(ws_id)
        original_name = form.name
        form.update()
        assert form.name == original_name
        assert len(form.collect_events()) == 1


def test_form_carries_category_and_assay_format_rule():
    ws, cat = uuid.uuid4(), uuid.uuid4()
    form = ProtocolForm.create(
        workspace_id=ws,
        name="IC50 dose-response",
        category_id=cat,
        assay_format_from_target=True,
        readout_templates=[ProtocolFormReadout(name="Signal", data_type="numeric")],
    )
    assert form.category_id == cat and form.assay_format_from_target is True
    form.update(category_id=None, assay_format_from_target=False)
    assert form.category_id is None and form.assay_format_from_target is False


# ---------------------------------------------------------------------------
# A form's curve names a readout in the same form
# ---------------------------------------------------------------------------


def _signal(
    name: str = "Signal", normalization: str = "percent_inhibition"
) -> ProtocolFormReadout:
    return ProtocolFormReadout(name=name, data_type="numeric", normalization=normalization)


def _form_curve(**cfg: object) -> ProtocolFormReadout:
    return ProtocolFormReadout(
        name="IC50",
        data_type="dose_response",
        unit="µM",
        dose_response_config={"curve_type": "ic50", **cfg},
    )


class TestFormCurves:
    def test_every_shipped_form_passes(self, ws_id: uuid.UUID) -> None:
        from cellar.domain.workspace_config.default_protocol_forms import DEFAULT_PROTOCOL_FORMS

        for spec in DEFAULT_PROTOCOL_FORMS:
            ProtocolForm.create(
                workspace_id=ws_id, name=spec.name, readout_templates=list(spec.readouts)
            )

    def test_refuses_a_y_readout_that_is_not_in_the_form(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="'IC50' fits 'Signal'"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="IC50 dose-response",
                readout_templates=[
                    _signal("THF Fluorescence Slope"),
                    _form_curve(y_readout_name="Signal"),
                ],
            )

    def test_refuses_an_x_readout_that_is_not_in_the_form(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="'IC50' uses 'Conc' for concentration"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="IC50 dose-response",
                readout_templates=[
                    _signal(),
                    _form_curve(y_readout_name="Signal", x_readout_name="Conc"),
                ],
            )

    def test_refuses_a_layer_the_y_readout_does_not_calculate(self, ws_id: uuid.UUID) -> None:
        with pytest.raises(ValidationError, match="'IC50' fits the z_score layer"):
            ProtocolForm.create(
                workspace_id=ws_id,
                name="IC50 dose-response",
                readout_templates=[
                    _signal(),
                    _form_curve(y_readout_name="Signal", y_normalization="z_score"),
                ],
            )

    def test_update_refuses_renaming_the_plotted_readout(self, ws_id: uuid.UUID) -> None:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="IC50 dose-response",
            readout_templates=[_signal(), _form_curve(y_readout_name="Signal")],
        )
        with pytest.raises(ValidationError, match="'IC50' fits 'Signal'"):
            form.update(
                readout_templates=[
                    _signal("Slope"),
                    _form_curve(y_readout_name="Signal"),
                ]
            )

    def test_a_curve_left_to_the_scientist_is_allowed(self, ws_id: uuid.UUID) -> None:
        form = ProtocolForm.create(
            workspace_id=ws_id,
            name="Curve only",
            readout_templates=[
                _signal(),
                ProtocolFormReadout(name="IC50", data_type="dose_response"),
            ],
        )
        assert len(form.readout_templates) == 2
