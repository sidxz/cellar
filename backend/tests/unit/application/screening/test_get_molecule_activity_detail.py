"""Tests for GetMoleculeActivityDetail use case."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from unittest.mock import AsyncMock

import pytest
from returns.result import Success

from cellar.application.screening.get_molecule_activity_detail import (
    GetMoleculeActivityDetail,
    GetMoleculeActivityDetailQuery,
    MoleculeActivityDetail,
)
from cellar.domain.screening_assay.dose_response_curve import DoseResponseCurve
from cellar.domain.screening_assay.enums import CurveClass, CurveType, ProtocolType
from cellar.domain.screening_assay.excluded_point_detail import (
    ExcludedPointDetail,
    ExclusionReason,
    ExclusionSource,
)
from cellar.domain.screening_assay.target import TargetRef
from cellar.domain.shared.enums import ConcentrationUnit
from cellar.domain.shared.events import DomainEvent
from tests.fakes.fake_auth import FakeAuth

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

WS = uuid.uuid4()
MOL_ID = uuid.uuid4()
PROTO_A = uuid.uuid4()
PROTO_B = uuid.uuid4()


class _FakeUoW:
    """Minimal UoW stand-in for unit tests."""

    async def commit(self) -> list[DomainEvent]:
        return []

    async def rollback(self) -> None:
        pass

    @property
    def is_active(self) -> bool:
        return True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class _FakeProtocol:
    """Minimal stand-in for AssayProtocol."""

    def __init__(
        self,
        *,
        id: uuid.UUID,
        name: str,
        protocol_type: ProtocolType = ProtocolType.BIOCHEMICAL,
        target_id: uuid.UUID | None = None,
        dose_unit: ConcentrationUnit = ConcentrationUnit.UM,
    ) -> None:
        self.id = id
        self.name = name
        self.protocol_type = protocol_type
        self.target_id = target_id
        self.dose_unit = dose_unit


def _make_curve(
    *,
    molecule_id: uuid.UUID = MOL_ID,
    protocol_id: uuid.UUID = PROTO_A,
    run_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
    curve_type: CurveType = CurveType.IC50,
    fitted_value: float = 5.2,
    hill_slope: float = -1.1,
    top: float = 100.0,
    bottom: float = 0.5,
    r_squared: float = 0.97,
    num_points: int = 8,
    curve_class: CurveClass | None = CurveClass.FULL,
    raw_data: list[dict] | None = None,
    confidence_interval_low: float | None = 3.8,
    confidence_interval_high: float | None = 7.1,
    excluded_points: list[ExcludedPointDetail] | None = None,
) -> DoseResponseCurve:
    return DoseResponseCurve(
        workspace_id=WS,
        molecule_id=molecule_id,
        batch_id=batch_id or uuid.uuid4(),
        protocol_id=protocol_id,
        run_id=run_id or uuid.uuid4(),
        readout_definition_id=uuid.uuid4(),
        curve_type=curve_type,
        fitted_value=fitted_value,
        hill_slope=hill_slope,
        top=top,
        bottom=bottom,
        r_squared=r_squared,
        num_points=num_points,
        curve_class=curve_class,
        raw_data=raw_data,
        confidence_interval_low=confidence_interval_low,
        confidence_interval_high=confidence_interval_high,
        excluded_points=excluded_points,
    )


def _make_uc(
    curve_repo: AsyncMock | None = None,
    protocol_repo: AsyncMock | None = None,
    run_repo: AsyncMock | None = None,
) -> GetMoleculeActivityDetail:
    if run_repo is None:
        run_repo = AsyncMock()
        # Default: no runs registered → curves arrive with run_date=None.
        # Tests that exercise the date-aware selection logic must override
        # this with a populated `{run_id: Run}` dict.
        run_repo.find_by_ids = AsyncMock(return_value={})
    pr = protocol_repo or AsyncMock()
    # Effective-targets resolver must yield a real dict (not a coroutine mock).
    if not isinstance(
        getattr(pr.find_effective_targets_for_protocols, "return_value", None), dict
    ):
        pr.find_effective_targets_for_protocols.return_value = {}
    return GetMoleculeActivityDetail(
        uow=_FakeUoW(),
        curve_repo=curve_repo or AsyncMock(),
        protocol_repo=pr,
        run_repo=run_repo,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGroupedByProtocol:
    """Curves from multiple protocols are correctly grouped."""

    @pytest.mark.asyncio
    async def test_returns_curves_grouped_by_protocol(self) -> None:
        """Two protocols, multiple curves each, should produce two groups."""
        target_id = uuid.uuid4()
        curves = [
            _make_curve(protocol_id=PROTO_A, r_squared=0.95),
            _make_curve(protocol_id=PROTO_A, r_squared=0.99),
            _make_curve(protocol_id=PROTO_B, r_squared=0.80, curve_type=CurveType.EC50),
        ]

        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = curves

        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = [
            _FakeProtocol(id=PROTO_A, name="Kinase IC50"),
            _FakeProtocol(
                id=PROTO_B, name="Cell Viability", protocol_type=ProtocolType.CELL_BASED
            ),
        ]
        protocol_repo.find_effective_targets_for_protocols.return_value = {
            PROTO_A: [TargetRef(id=target_id, name="EGFR", target_type="single_protein")],
            PROTO_B: [],
        }

        auth = FakeAuth(workspace_id=WS)
        query = GetMoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID)

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        detail: MoleculeActivityDetail = result.unwrap()

        assert detail.molecule_id == MOL_ID
        assert len(detail.protocols) == 2

        # Find protocol groups
        proto_a_group = next(g for g in detail.protocols if g.protocol_id == PROTO_A)
        proto_b_group = next(g for g in detail.protocols if g.protocol_id == PROTO_B)

        # Protocol A: 2 curves, sorted by r_squared DESC
        assert proto_a_group.protocol_name == "Kinase IC50"
        assert proto_a_group.protocol_type == "biochemical"
        assert [t.id for t in proto_a_group.targets] == [target_id]
        assert len(proto_a_group.curves) == 2
        assert proto_a_group.curves[0].r_squared == 0.99
        assert proto_a_group.curves[1].r_squared == 0.95

        # Protocol B: 1 curve
        assert proto_b_group.protocol_name == "Cell Viability"
        assert proto_b_group.protocol_type == "cell_based"
        assert proto_b_group.targets == []
        assert len(proto_b_group.curves) == 1
        assert proto_b_group.curves[0].curve_type == "ec50"

    @pytest.mark.asyncio
    async def test_curve_detail_fields(self) -> None:
        """CurveDetail should faithfully map all fields from the domain entity."""
        raw_points = [
            {"concentration": 0.01, "response": 95.0},
            {"concentration": 1.0, "response": 50.0},
        ]
        condensed_points = [
            {"x": 0.01, "y": 95.0},
            {"x": 1.0, "y": 50.0},
        ]
        curve = _make_curve(
            raw_data=raw_points,
            curve_class=CurveClass.PARTIAL,
            confidence_interval_low=2.0,
            confidence_interval_high=8.0,
        )

        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = [curve]

        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = [
            _FakeProtocol(id=PROTO_A, name="Test"),
        ]

        auth = FakeAuth(workspace_id=WS)
        query = GetMoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID)

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(query, auth=auth)

        detail = result.unwrap()
        cd = detail.protocols[0].curves[0]

        assert cd.curve_id == curve.id
        assert cd.run_id == curve.run_id
        assert cd.batch_id == curve.batch_id
        assert cd.curve_type == "ic50"
        assert cd.fitted_value == 5.2
        assert cd.fitted_unit == "uM"
        assert cd.hill_slope == -1.1
        assert cd.r_squared == 0.97
        assert cd.curve_class == "partial"
        assert cd.top == 100.0
        assert cd.bottom == 0.5
        assert cd.num_points == 8
        assert cd.confidence_interval_low == 2.0
        assert cd.confidence_interval_high == 8.0
        assert cd.raw_data == condensed_points


class TestExcludedPointsSerialization:
    """Regression: curves carrying typed ``ExcludedPointDetail`` VOs must
    serialize to plain dicts all the way to the wire response.

    The repo's ``_to_domain`` hydrates the JSONB ``excluded_points`` column
    into typed ``ExcludedPointDetail`` value objects. The activity-detail
    DTO (``CurveDetail``) declares ``excluded_points: list[dict]`` and the
    route's Pydantic ``CurveDetailResponse`` enforces it — so the use case
    must convert the VOs back to dicts. Without that conversion the endpoint
    raised a Pydantic ``ValidationError`` (HTTP 500) for every compound whose
    best/any curve had an auto-3sigma excluded point, and the UI rendered the
    misleading "No dose-response data available" empty state.
    """

    @staticmethod
    def _excluded_point() -> ExcludedPointDetail:
        return ExcludedPointDetail(
            idx=0,
            source=ExclusionSource.AUTO_3SIGMA,
            excluded=False,  # auto-suggested outlier, not yet confirmed
            reason=ExclusionReason.AUTO_3SIGMA,
            author_id=None,
            ts=datetime(2026, 5, 16, 2, 27, 44, tzinfo=UTC),
            concentration=100.0,
            response=61.4,
        )

    @pytest.mark.asyncio
    async def test_excluded_points_are_dicts_in_dto(self) -> None:
        """The application DTO honors its ``list[dict]`` contract."""
        curve = _make_curve(excluded_points=[self._excluded_point()])
        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = [curve]
        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = [_FakeProtocol(id=PROTO_A, name="P")]

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(
            GetMoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID),
            auth=FakeAuth(workspace_id=WS),
        )

        cd = result.unwrap().protocols[0].curves[0]
        assert cd.excluded_points is not None
        assert all(isinstance(ep, dict) for ep in cd.excluded_points)
        assert cd.excluded_points[0]["source"] == "auto_3sigma"
        assert cd.excluded_points[0]["concentration"] == 100.0

    @pytest.mark.asyncio
    async def test_response_model_serializes_without_error(self) -> None:
        """End-to-end: the route response model builds without raising.

        This is the exact path that 500'd in production — reproduces it at
        the DTO→Pydantic boundary that the unit-level use-case tests miss.
        """
        from cellar.interface.routes.molecule_activity import (
            MoleculeActivityDetailResponse,
        )

        curve = _make_curve(excluded_points=[self._excluded_point()])
        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = [curve]
        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = [_FakeProtocol(id=PROTO_A, name="P")]

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        dto = (
            await uc(
                GetMoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID),
                auth=FakeAuth(workspace_id=WS),
            )
        ).unwrap()

        resp = MoleculeActivityDetailResponse.from_dto(dto)

        excluded = resp.protocols[0].curves[0].excluded_points
        assert excluded is not None
        assert excluded[0]["source"] == "auto_3sigma"


class TestEmptyResults:
    """Edge cases when no curves exist."""

    @pytest.mark.asyncio
    async def test_returns_empty_protocols_when_no_curves(self) -> None:
        """An empty protocols list when there are no curves for the molecule."""
        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = []

        protocol_repo = AsyncMock()

        auth = FakeAuth(workspace_id=WS)
        query = GetMoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID)

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(query, auth=auth)

        assert isinstance(result, Success)
        detail = result.unwrap()
        assert detail.molecule_id == MOL_ID
        assert detail.protocols == []

        # Protocol repo should NOT be called when no curves
        protocol_repo.find_by_ids.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_protocol_gets_fallback_name(self) -> None:
        """When protocol_repo doesn't return a protocol, use 'Unknown' fallback."""
        curve = _make_curve(protocol_id=PROTO_A)

        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = [curve]

        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = []  # No protocol found

        auth = FakeAuth(workspace_id=WS)
        query = GetMoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID)

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo)
        result = await uc(query, auth=auth)

        detail = result.unwrap()
        assert len(detail.protocols) == 1
        assert detail.protocols[0].protocol_name == "Unknown"
        assert detail.protocols[0].protocol_type == "unknown"
        assert detail.protocols[0].targets == []


class TestRunDateSurfaced:
    """``run_date`` is fetched from the Run repo and threaded onto each curve.

    The drawer needs ``run_date`` so its selection logic can honor the
    toolbar's "latest run" rule. The curve table doesn't carry the date;
    the use case batches a Run-by-ids lookup and joins it back per curve.
    """

    @pytest.mark.asyncio
    async def test_run_date_threaded_from_run_repo(self) -> None:
        from datetime import date

        run_id_a = uuid.uuid4()
        run_id_b = uuid.uuid4()
        curves = [
            _make_curve(run_id=run_id_a, r_squared=0.95),
            _make_curve(run_id=run_id_b, r_squared=0.99),
        ]

        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = curves

        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = [_FakeProtocol(id=PROTO_A, name="P")]

        class _FakeRun:
            def __init__(self, rid: uuid.UUID, rd: date) -> None:
                self.id = rid
                self.run_date = rd

        run_repo = AsyncMock()
        run_repo.find_by_ids = AsyncMock(
            return_value={
                run_id_a: _FakeRun(run_id_a, date(2026, 1, 1)),
                run_id_b: _FakeRun(run_id_b, date(2026, 5, 1)),
            }
        )

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo, run_repo=run_repo)
        auth = FakeAuth(workspace_id=WS)
        result = await uc(
            GetMoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID),
            auth=auth,
        )

        detail = result.unwrap()
        # Curves are sorted by R² desc — the 0.99 R² curve (run_id_b) comes first.
        cds = detail.protocols[0].curves
        assert cds[0].run_id == run_id_b
        assert cds[0].run_date == date(2026, 5, 1)
        assert cds[1].run_id == run_id_a
        assert cds[1].run_date == date(2026, 1, 1)

    @pytest.mark.asyncio
    async def test_run_date_is_none_when_run_missing(self) -> None:
        """Curve whose owning run was deleted out-of-band surfaces as None.

        Defensive — we don't want a missing run_id to crash the entire
        molecule detail; the drawer's "latest" rule treats None-dated rows
        as eldest (matches existing run_date-aware sort semantics).
        """
        curve = _make_curve(run_id=uuid.uuid4())
        curve_repo = AsyncMock()
        curve_repo.find_by_molecule.return_value = [curve]

        protocol_repo = AsyncMock()
        protocol_repo.find_by_ids.return_value = [_FakeProtocol(id=PROTO_A, name="P")]

        run_repo = AsyncMock()
        run_repo.find_by_ids = AsyncMock(return_value={})  # Run deleted

        uc = _make_uc(curve_repo=curve_repo, protocol_repo=protocol_repo, run_repo=run_repo)
        auth = FakeAuth(workspace_id=WS)
        result = await uc(
            GetMoleculeActivityDetailQuery(workspace_id=WS, molecule_id=MOL_ID),
            auth=auth,
        )

        detail = result.unwrap()
        assert detail.protocols[0].curves[0].run_date is None
