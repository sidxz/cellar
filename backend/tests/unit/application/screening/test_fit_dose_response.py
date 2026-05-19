"""Tests for FitDoseResponseCurves canonical-layer selection.

Bug 1: the fitter previously filtered ReadoutData rows by readout_definition_id
only — for a normalized Y readout it picked up BOTH raw (is_computed=False)
and post-normalization (is_computed=True) rows, feeding two y-values per
concentration into the 4PL and collapsing the fit to zeros.
"""

from __future__ import annotations

import uuid
from datetime import date
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Failure, Success

from cellar.domain.shared.errors import AuthorizationError

from cellar.application.screening.fit_dose_response import FitDoseResponseCurves
from cellar.domain.screening_assay.curve_fitting import (
    ConcentrationResponsePoint,
    CurveFittingService,
    FittedCurveResult,
)
from cellar.domain.screening_assay.dose_response_config import DoseResponseConfig
from cellar.domain.screening_assay.enums import (
    CurveClass,
    CurveType,
    PlateFormat,
    ProtocolType,
    ReadoutDataType,
    ReadoutNormalization,
    WellType,
)
from cellar.domain.screening_assay.protocol import Protocol, ReadoutDefinition
from cellar.domain.screening_assay.readout_data import ReadoutData
from cellar.domain.screening_assay.run import Plate, Run, Well
from cellar.domain.shared.value_objects import QualifiedValue


WS = uuid.uuid4()
USER = uuid.uuid4()


class _FakeUow:
    @property
    def is_active(self) -> bool:
        return False

    async def commit(self):
        return []

    async def rollback(self) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class _RecordingFitter:
    """Captures the points handed to fit() so tests can assert on them."""

    def __init__(self) -> None:
        self.calls: list[list[ConcentrationResponsePoint]] = []

    def fit(self, points, config):
        self.calls.append(list(points))
        return Success(
            FittedCurveResult(
                fitted_value=1.0,
                hill_slope=1.0,
                top=100.0,
                bottom=0.0,
                r_squared=0.99,
                confidence_interval_low=0.5,
                confidence_interval_high=2.0,
                curve_class=CurveClass.FULL,
                num_points=len(points),
                raw_data=[],
                excluded_points=[],
            )
        )


def _make_protocol_with_y(
    *,
    y_normalization: ReadoutNormalization = ReadoutNormalization.NONE,
    y_is_calculated: bool = False,
) -> tuple[Protocol, ReadoutDefinition, ReadoutDefinition]:
    """Build a protocol with one numeric Y readout + one DOSE_RESPONSE IC50."""
    y_norms = (
        frozenset({y_normalization})
        if y_normalization != ReadoutNormalization.NONE
        else frozenset()
    )
    y_kwargs: dict = dict(
        protocol_id=uuid.uuid4(),
        name="raw AU",
        data_type=ReadoutDataType.NUMERIC,
        normalizations=y_norms,
        is_calculated=y_is_calculated,
    )
    if y_is_calculated:
        y_kwargs["calculation_formula"] = "x"
    y_def = ReadoutDefinition(**y_kwargs)
    ic50_def = ReadoutDefinition(
        protocol_id=y_kwargs["protocol_id"],
        name="IC50",
        data_type=ReadoutDataType.DOSE_RESPONSE,
        dose_response_config=DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="concentration",
            y_readout_name="raw AU",
        ),
    )
    protocol = Protocol.create(
        workspace_id=WS,
        name="Test Protocol",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=[y_def, ic50_def],
    )
    # find_by reference (Protocol.create may copy / re-id)
    y_def = next(rd for rd in protocol.readout_definitions if rd.name == "raw AU")
    ic50_def = next(rd for rd in protocol.readout_definitions if rd.name == "IC50")
    return protocol, y_def, ic50_def


def _make_run_with_dose_series(
    *,
    protocol_id: uuid.UUID,
    concentrations: list[float],
) -> tuple[Run, list[Well]]:
    """Run with one plate and one well per concentration (single molecule/batch)."""
    run = Run.create(
        workspace_id=WS,
        protocol_id=protocol_id,
        run_date=date(2026, 5, 5),
        operator=USER,
    )
    plate = Plate(run_id=run.id, plate_number=1, format=PlateFormat.F96)
    run.plates.append(plate)

    wells: list[Well] = []
    for i, conc in enumerate(concentrations):
        well = Well(
            plate_id=plate.id,
            row="A",
            column=i + 1,
            well_type=WellType.SAMPLE,
            batch_id=uuid.UUID(int=43),
            dose=conc,
        )
        run.wells.append(well)
        wells.append(well)
    return run, wells


def _rd(
    *,
    run_id: uuid.UUID,
    well_id: uuid.UUID,
    readout_definition_id: uuid.UUID,
    value: float,
    is_computed: bool,
    molecule_id: uuid.UUID | None = uuid.UUID(int=42),
    batch_id: uuid.UUID | None = uuid.UUID(int=43),
    normalization_applied: ReadoutNormalization | None = None,
) -> ReadoutData:
    return ReadoutData(
        workspace_id=WS,
        run_id=run_id,
        well_id=well_id,
        molecule_id=molecule_id,
        batch_id=batch_id,
        readout_definition_id=readout_definition_id,
        value=QualifiedValue(value=value),
        is_computed=is_computed,
        normalization_applied=normalization_applied,
    )


def _make_use_case(fitter: _RecordingFitter) -> FitDoseResponseCurves:
    curve_repo = AsyncMock()
    curve_repo.delete_by_run = AsyncMock()
    curve_repo.save = AsyncMock()
    return FitDoseResponseCurves(
        uow=_FakeUow(),
        curve_repo=curve_repo,
        curve_fitter=fitter,
    )


# ---------------------------------------------------------------------------
# Bug 1: layer selection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalized_y_uses_only_computed_rows():
    """Y readout with normalization != NONE → fitter sees only is_computed=True rows."""
    protocol, y_def, _ = _make_protocol_with_y(
        y_normalization=ReadoutNormalization.PERCENT_INHIBITION,
    )
    concs = [0.01, 0.1, 1.0, 10.0, 100.0]
    run, wells = _make_run_with_dose_series(
        protocol_id=protocol.id, concentrations=concs
    )

    raw_y_values = [0.55, 0.50, 0.40, 0.20, 0.05]   # raw AU
    pct_y_values = [5.0, 12.0, 35.0, 75.0, 95.0]   # post % inhibition

    readout_data: list[ReadoutData] = []
    for w, raw_v, pct_v in zip(wells, raw_y_values, pct_y_values, strict=True):
        readout_data.append(
            _rd(run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=raw_v, is_computed=False)
        )
        readout_data.append(
            _rd(run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=pct_v, is_computed=True,
                normalization_applied=ReadoutNormalization.PERCENT_INHIBITION)
        )

    fitter = _RecordingFitter()
    use_case = _make_use_case(fitter)
    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=readout_data, workspace_id=WS,
    )
    assert isinstance(result, Success)

    assert len(fitter.calls) == 1
    points = fitter.calls[0]
    # exactly 5 points, one per concentration
    assert len(points) == len(concs)
    seen_responses = sorted(p.response for p in points)
    assert seen_responses == sorted(pct_y_values)
    # crucially, no raw values bled through
    for raw_v in raw_y_values:
        assert raw_v not in seen_responses


@pytest.mark.asyncio
async def test_raw_y_uses_only_raw_rows():
    """Y readout with normalization=NONE and is_calculated=False → only raw rows."""
    protocol, y_def, _ = _make_protocol_with_y()  # defaults: NONE, not calculated
    concs = [0.1, 1.0, 10.0, 100.0]
    run, wells = _make_run_with_dose_series(
        protocol_id=protocol.id, concentrations=concs
    )

    raw_y_values = [0.55, 0.40, 0.20, 0.05]
    # synthesize stray is_computed=True rows to ensure they're filtered out
    stray_values = [9999.0, 8888.0, 7777.0, 6666.0]

    readout_data: list[ReadoutData] = []
    for w, raw_v, stray in zip(wells, raw_y_values, stray_values, strict=True):
        readout_data.append(
            _rd(run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=raw_v, is_computed=False)
        )
        readout_data.append(
            _rd(run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=stray, is_computed=True)
        )

    fitter = _RecordingFitter()
    use_case = _make_use_case(fitter)
    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=readout_data, workspace_id=WS,
    )
    assert isinstance(result, Success)

    points = fitter.calls[0]
    seen = sorted(p.response for p in points)
    assert seen == sorted(raw_y_values)
    for stray in stray_values:
        assert stray not in seen


@pytest.mark.asyncio
async def test_calculated_y_uses_only_computed_rows():
    """Y readout with is_calculated=True (formula output) → only is_computed=True rows."""
    protocol, y_def, _ = _make_protocol_with_y(y_is_calculated=True)
    concs = [0.1, 1.0, 10.0, 100.0]
    run, wells = _make_run_with_dose_series(
        protocol_id=protocol.id, concentrations=concs
    )

    formula_values = [10.0, 25.0, 60.0, 90.0]
    # there should not be is_computed=False rows for a calculated readout, but
    # if any leaked through (e.g. an upstream import bug), they must be ignored.
    leaked_raw = [0.1, 0.2, 0.3, 0.4]

    readout_data: list[ReadoutData] = []
    for w, fv, lv in zip(wells, formula_values, leaked_raw, strict=True):
        readout_data.append(
            _rd(run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=fv, is_computed=True)
        )
        readout_data.append(
            _rd(run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=lv, is_computed=False)
        )

    fitter = _RecordingFitter()
    use_case = _make_use_case(fitter)
    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=readout_data, workspace_id=WS,
    )
    assert isinstance(result, Success)

    points = fitter.calls[0]
    seen = sorted(p.response for p in points)
    assert seen == sorted(formula_values)
    for lv in leaked_raw:
        assert lv not in seen


@pytest.mark.asyncio
async def test_normalized_y_no_double_feed_per_concentration():
    """Regression: each concentration must yield exactly ONE point to the fitter.

    Prior to the fix, both raw and computed rows were forwarded so each
    concentration produced two y-values, collapsing the optimizer.
    """
    protocol, y_def, _ = _make_protocol_with_y(
        y_normalization=ReadoutNormalization.PERCENT_INHIBITION,
    )
    concs = [0.01, 0.1, 1.0, 10.0, 100.0]
    run, wells = _make_run_with_dose_series(
        protocol_id=protocol.id, concentrations=concs
    )

    readout_data: list[ReadoutData] = []
    for w, conc in zip(wells, concs, strict=True):
        readout_data.append(
            _rd(run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=0.5, is_computed=False)
        )
        readout_data.append(
            _rd(run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=50.0, is_computed=True,
                normalization_applied=ReadoutNormalization.PERCENT_INHIBITION)
        )

    fitter = _RecordingFitter()
    use_case = _make_use_case(fitter)
    await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=readout_data, workspace_id=WS,
    )

    points = fitter.calls[0]
    points_by_conc: dict[float, list[float]] = {}
    for p in points:
        points_by_conc.setdefault(p.concentration, []).append(p.response)
    for conc, ys in points_by_conc.items():
        assert len(ys) == 1, f"concentration {conc} got {len(ys)} y-values: {ys}"


@pytest.mark.asyncio
async def test_y_normalization_picks_correct_formula_layer():
    """Multi-emit normalization: y_normalization tells the fitter which
    formula's output to feed (e.g. %inh, not z-score) when the Y readout
    def emits both."""
    # Y def emits %inh AND z_score; DR config picks %inh.
    y_def = ReadoutDefinition(
        protocol_id=uuid.uuid4(),
        name="raw AU",
        data_type=ReadoutDataType.NUMERIC,
        normalizations=frozenset(
            {
                ReadoutNormalization.PERCENT_INHIBITION,
                ReadoutNormalization.Z_SCORE,
            }
        ),
    )
    ic50_def = ReadoutDefinition(
        protocol_id=y_def.protocol_id,
        name="IC50",
        data_type=ReadoutDataType.DOSE_RESPONSE,
        dose_response_config=DoseResponseConfig(
            curve_type=CurveType.IC50,
            x_readout_name="concentration",
            y_readout_name="raw AU",
            y_normalization=ReadoutNormalization.PERCENT_INHIBITION,
        ),
    )
    protocol = Protocol.create(
        workspace_id=WS,
        name="multi-emit",
        protocol_type=ProtocolType.BIOCHEMICAL,
        created_by=USER,
        readout_definitions=[y_def, ic50_def],
    )
    y_def = next(rd for rd in protocol.readout_definitions if rd.name == "raw AU")

    concs = [0.01, 0.1, 1.0, 10.0, 100.0]
    run, wells = _make_run_with_dose_series(
        protocol_id=protocol.id, concentrations=concs
    )

    pct_y = [5.0, 12.0, 35.0, 75.0, 95.0]
    z_y = [-2.0, -1.0, 0.0, 1.0, 2.0]

    readout_data: list[ReadoutData] = []
    for w, pct_v, z_v in zip(wells, pct_y, z_y, strict=True):
        readout_data.append(_rd(
            run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
            value=pct_v, is_computed=True,
            normalization_applied=ReadoutNormalization.PERCENT_INHIBITION,
        ))
        readout_data.append(_rd(
            run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
            value=z_v, is_computed=True,
            normalization_applied=ReadoutNormalization.Z_SCORE,
        ))

    fitter = _RecordingFitter()
    use_case = _make_use_case(fitter)
    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=readout_data, workspace_id=WS,
    )
    assert isinstance(result, Success)

    points = fitter.calls[0]
    seen = sorted(p.response for p in points)
    assert seen == sorted(pct_y)
    for z_v in z_y:
        assert z_v not in seen


# ---------------------------------------------------------------------------
# F3: workspace_id assertion at entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_workspace_mismatch_rejected():
    protocol, _, _ = _make_protocol_with_y()
    run, _ = _make_run_with_dose_series(protocol_id=protocol.id, concentrations=[0.1, 1.0, 10.0])

    other_ws = uuid.uuid4()
    fitter = _RecordingFitter()
    use_case = _make_use_case(fitter)
    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=[], workspace_id=other_ws,
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), AuthorizationError)
    assert "Run workspace mismatch" in str(result.failure())


@pytest.mark.asyncio
async def test_protocol_workspace_mismatch_rejected():
    protocol, _, _ = _make_protocol_with_y()
    run, _ = _make_run_with_dose_series(protocol_id=protocol.id, concentrations=[0.1, 1.0, 10.0])
    # Forge a protocol from a different workspace
    object.__setattr__(protocol, "workspace_id", uuid.uuid4())

    fitter = _RecordingFitter()
    use_case = _make_use_case(fitter)
    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=[], workspace_id=WS,
    )
    assert isinstance(result, Failure)
    assert isinstance(result.failure(), AuthorizationError)
    assert "Protocol workspace mismatch" in str(result.failure())


# ---------------------------------------------------------------------------
# F11: silent fit failures surface as warnings
# ---------------------------------------------------------------------------


class _FailingFitter:
    """Returns Failure for the second compound's fit; succeeds otherwise."""

    def __init__(self, fail_for_response: float) -> None:
        self._fail_for = fail_for_response
        self.calls: int = 0

    def fit(self, points, config):
        self.calls += 1
        from cellar.domain.shared.errors import ValidationError
        # Trigger failure when the points contain the sentinel response.
        if any(p.response == self._fail_for for p in points):
            return Failure(ValidationError("synthetic fit failure"))
        return Success(
            FittedCurveResult(
                fitted_value=1.0, hill_slope=1.0, top=100.0, bottom=0.0,
                r_squared=0.99,
                confidence_interval_low=0.5, confidence_interval_high=2.0,
                curve_class=CurveClass.FULL,
                num_points=len(points), raw_data=[], excluded_points=[],
            )
        )


@pytest.mark.asyncio
async def test_fit_failures_surface_in_warnings():
    """F11: when one compound's fit fails, the result still succeeds for the
    others and the failed compound is named in the warnings list."""
    protocol, y_def, _ = _make_protocol_with_y()
    concs = [0.1, 1.0, 10.0, 100.0]
    run, wells = _make_run_with_dose_series(protocol_id=protocol.id, concentrations=concs)

    sentinel_response = -42.0  # used by _FailingFitter to detect the bad compound
    bad_mol = uuid.UUID(int=99)
    good_mol = uuid.UUID(int=100)

    readout_data: list[ReadoutData] = []
    for w in wells:
        readout_data.append(
            _rd(
                run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=sentinel_response, is_computed=False,
                molecule_id=bad_mol, batch_id=uuid.UUID(int=44),
            )
        )
    # Add a good compound on a separate well per concentration
    for w in wells:
        readout_data.append(
            _rd(
                run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=10.0, is_computed=False,
                molecule_id=good_mol, batch_id=uuid.UUID(int=45),
            )
        )

    fitter = _FailingFitter(fail_for_response=sentinel_response)
    curve_repo = AsyncMock()
    curve_repo.delete_by_run = AsyncMock()
    curve_repo.save = AsyncMock()
    use_case = FitDoseResponseCurves(
        uow=_FakeUow(), curve_repo=curve_repo, curve_fitter=fitter,
    )

    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=readout_data, workspace_id=WS,
    )
    assert isinstance(result, Success)
    fit_result = result.unwrap()
    # Only the good compound got a curve.
    assert len(fit_result.curves) == 1
    # The failure for bad_mol surfaced as a warning naming it.
    assert any(str(bad_mol) in w for w in fit_result.warnings), (
        f"warnings did not name failed molecule: {fit_result.warnings}"
    )


# ---------------------------------------------------------------------------
# FitOverrides preserves multi-emit + multi-intercept fields
# ---------------------------------------------------------------------------


def test_fit_overrides_preserves_y_normalization_and_intercepts():
    """Recompute (FitOverrides.apply) tweaks constraints — it must not
    silently drop the protocol's `y_normalization` selection or `intercepts`
    list. Otherwise IC50+IC90 protocols collapse to IC50-only after a
    refit and the y-layer selection reverts to the default."""
    from cellar.application.screening.fit_dose_response import FitOverrides
    from cellar.domain.screening_assay.dose_response_config import (
        InterceptSpec,
    )
    from cellar.domain.screening_assay.enums import InterceptKind

    base = DoseResponseConfig(
        curve_type=CurveType.IC50,
        x_readout_name=None,
        y_readout_name="raw AU",
        y_normalization=ReadoutNormalization.PERCENT_INHIBITION,
        intercepts=(
            InterceptSpec(InterceptKind.IC, 50),
            InterceptSpec(InterceptKind.IC, 90),
        ),
    )
    # Apply a non-empty override that touches Top only.
    overrides = FitOverrides(override_top=True, top=100.0)
    result = overrides.apply(base)

    assert result.y_normalization == ReadoutNormalization.PERCENT_INHIBITION, (
        "FitOverrides.apply must preserve y_normalization"
    )
    assert result.intercepts is not None
    assert len(result.intercepts) == 2, (
        "FitOverrides.apply must preserve all intercepts"
    )
    assert result.intercepts[1].level == 90
    # And the override actually applied.
    assert result.top_constraint == 100.0


# ---------------------------------------------------------------------------
# Sprint 2 — auto-3σ becomes suggestion (no silent removal)
# ---------------------------------------------------------------------------


class _FitterWithOneSuggestion:
    """Returns a fitted result that nominates a single outlier suggestion.

    Mimics the new fitter contract: the offending point stays in the fit
    (num_points unchanged); the candidate rides along on ``outlier_suggestions``.
    """

    def __init__(self, *, suggestion_idx: int, conc: float, response: float) -> None:
        from cellar.domain.screening_assay.outlier_suggestion import OutlierSuggestion

        self._suggestion = OutlierSuggestion(
            idx=suggestion_idx,
            concentration=conc,
            response=response,
            residual_sigma=4.2,
        )
        self.calls: list[list[ConcentrationResponsePoint]] = []

    def fit(self, points, config):
        self.calls.append(list(points))
        return Success(
            FittedCurveResult(
                fitted_value=10.0,
                hill_slope=1.0,
                top=100.0,
                bottom=0.0,
                r_squared=0.97,
                confidence_interval_low=8.0,
                confidence_interval_high=12.0,
                curve_class=CurveClass.FULL,
                num_points=len(points),
                raw_data=[
                    {"concentration": p.concentration, "response": p.response}
                    for p in points
                ],
                excluded_points=[],
                outlier_suggestions=(self._suggestion,),
            )
        )


@pytest.mark.asyncio
async def test_initial_fit_persists_outlier_suggestion_as_excluded_point_detail():
    """The initial-fit use case translates fitter ``outlier_suggestions`` into
    ``ExcludedPointDetail(source=AUTO_3SIGMA, excluded=False)`` on the curve.

    These show up in the UI as yellow-halo "suggested for exclusion" markers
    that the chemist can explicitly accept or reject."""
    from cellar.domain.screening_assay.excluded_point_detail import (
        ExcludedPointDetail,
        ExclusionReason,
        ExclusionSource,
    )

    protocol, y_def, _ = _make_protocol_with_y()
    concs = [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]
    run, wells = _make_run_with_dose_series(
        protocol_id=protocol.id, concentrations=concs
    )

    # Healthy values everywhere except the third position — the fitter spy
    # will nominate idx=2 as a suggestion.
    values = [5.0, 12.0, 99.0, 75.0, 90.0, 95.0]
    readout_data: list[ReadoutData] = []
    for w, v in zip(wells, values, strict=True):
        readout_data.append(
            _rd(
                run_id=run.id,
                well_id=w.id,
                readout_definition_id=y_def.id,
                value=v,
                is_computed=False,
            )
        )

    fitter = _FitterWithOneSuggestion(
        suggestion_idx=2, conc=10.0, response=99.0,
    )
    curve_repo = AsyncMock()
    curve_repo.delete_by_run = AsyncMock()
    saved_curves: list = []

    async def _capture_save(curve):
        saved_curves.append(curve)

    curve_repo.save = _capture_save
    use_case = FitDoseResponseCurves(
        uow=_FakeUow(), curve_repo=curve_repo, curve_fitter=fitter,
    )

    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=readout_data, workspace_id=WS,
    )
    assert isinstance(result, Success)
    assert len(saved_curves) == 1
    curve = saved_curves[0]
    assert curve.excluded_points is not None
    suggestions = [
        e for e in curve.excluded_points
        if isinstance(e, ExcludedPointDetail) and e.is_suggestion
    ]
    assert len(suggestions) == 1
    s = suggestions[0]
    assert s.idx == 2
    assert s.source == ExclusionSource.AUTO_3SIGMA
    assert s.reason == ExclusionReason.AUTO_3SIGMA
    assert s.excluded is False
    assert s.author_id is None
    assert s.concentration == 10.0
    assert s.response == 99.0


@pytest.mark.asyncio
async def test_initial_fit_no_suggestions_yields_empty_excluded_points():
    """When the fitter nominates nothing, the curve's ``excluded_points``
    stays empty — no spurious entries."""
    protocol, y_def, _ = _make_protocol_with_y()
    concs = [0.1, 1.0, 10.0, 100.0]
    run, wells = _make_run_with_dose_series(
        protocol_id=protocol.id, concentrations=concs
    )
    readout_data: list[ReadoutData] = []
    for w, v in zip(wells, [5.0, 30.0, 70.0, 95.0], strict=True):
        readout_data.append(
            _rd(
                run_id=run.id, well_id=w.id, readout_definition_id=y_def.id,
                value=v, is_computed=False,
            )
        )

    fitter = _RecordingFitter()  # writes excluded_points=[] + no suggestions
    curve_repo = AsyncMock()
    curve_repo.delete_by_run = AsyncMock()
    saved_curves: list = []

    async def _capture_save(curve):
        saved_curves.append(curve)

    curve_repo.save = _capture_save
    use_case = FitDoseResponseCurves(
        uow=_FakeUow(), curve_repo=curve_repo, curve_fitter=fitter,
    )

    result = await use_case.fit_for_run(
        run=run, protocol=protocol, readout_data=readout_data, workspace_id=WS,
    )
    assert isinstance(result, Success)
    assert len(saved_curves) == 1
    assert saved_curves[0].excluded_points == []
