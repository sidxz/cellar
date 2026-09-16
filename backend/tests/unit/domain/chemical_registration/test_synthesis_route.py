"""Tests for SynthesisRoute aggregate root."""

import uuid

import pytest

from cellar.domain.chemical_registration.enums import (
    ReagentRole,
    RouteSource,
    RouteStatus,
    RouteType,
)
from cellar.domain.chemical_registration.events import (
    ReactionStepOutcomeRecorded,
    SynthesisRouteCreated,
    SynthesisRouteDeprecated,
    SynthesisRoutePreferred,
    SynthesisRouteValidated,
)
from cellar.domain.chemical_registration.synthesis_route import (
    ReactionReagent,
    ReactionStep,
    SynthesisRoute,
)
from cellar.domain.shared.errors import ValidationError
from cellar.domain.shared.value_objects import ReactionOutcome


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ws_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mol_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_route(
    ws_id: uuid.UUID, mol_id: uuid.UUID, user_id: uuid.UUID, **overrides
) -> SynthesisRoute:
    defaults = dict(
        workspace_id=ws_id,
        target_molecule_id=mol_id,
        name="Route A - Suzuki coupling",
        created_by=user_id,
    )
    defaults.update(overrides)
    return SynthesisRoute.create(**defaults)


def _make_step(route: SynthesisRoute, **overrides) -> ReactionStep:
    defaults = dict(
        route_id=route.id,
        step_number=len(route.steps) + 1,
    )
    defaults.update(overrides)
    return ReactionStep(**defaults)


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


class TestSynthesisRouteCreation:
    def test_create_basic(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)

        assert route.workspace_id == ws_id
        assert route.target_molecule_id == mol_id
        assert route.name == "Route A - Suzuki coupling"
        assert route.status == RouteStatus.DRAFT
        assert route.route_type == RouteType.LINEAR
        assert route.source == RouteSource.MANUAL
        assert route.total_steps == 0
        assert route.overall_yield is None
        assert route.version == 1

    def test_create_emits_event(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        events = route.collect_events()

        assert len(events) == 1
        assert isinstance(events[0], SynthesisRouteCreated)
        assert events[0].target_molecule_id == mol_id
        assert events[0].route_type == RouteType.LINEAR.value


    def test_create_empty_name_raises(self, ws_id, mol_id, user_id):
        with pytest.raises(ValidationError, match="name"):
            _make_route(ws_id, mol_id, user_id, name="   ")


# ---------------------------------------------------------------------------
# Step management
# ---------------------------------------------------------------------------


class TestStepManagement:
    def test_add_step(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        step = _make_step(route, name="Suzuki coupling")

        route.add_step(step)

        assert len(route.steps) == 1
        assert route.total_steps == 1

    def test_remove_step(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        step = _make_step(route)
        route.add_step(step)

        route.remove_step(step.id)

        assert len(route.steps) == 0
        assert route.total_steps == 0

    def test_add_step_non_draft_raises(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        step = _make_step(route)
        route.add_step(step)
        route.validate_route()

        with pytest.raises(ValidationError, match="draft"):
            route.add_step(_make_step(route))

    def test_remove_step_non_draft_raises(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        step = _make_step(route)
        route.add_step(step)
        route.validate_route()

        with pytest.raises(ValidationError, match="draft"):
            route.remove_step(step.id)

    def test_record_step_outcome(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        step = _make_step(route)
        route.add_step(step)

        outcome = ReactionOutcome(yield_percent=85.0)
        batch_id = uuid.uuid4()
        route.record_step_outcome(step.id, outcome, batch_id=batch_id)

        assert route.steps[0].outcome == outcome
        assert route.steps[0].batch_id == batch_id
        assert route.overall_yield == 85.0

    def test_record_outcome_emits_event(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        step = _make_step(route)
        route.add_step(step)
        route.clear_events()

        outcome = ReactionOutcome(yield_percent=90.0)
        route.record_step_outcome(step.id, outcome)

        events = route.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], ReactionStepOutcomeRecorded)
        assert events[0].step_id == step.id
        assert events[0].yield_percent == 90.0

    def test_record_outcome_unknown_step_raises(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        outcome = ReactionOutcome(yield_percent=50.0)

        with pytest.raises(ValidationError, match="not found"):
            route.record_step_outcome(uuid.uuid4(), outcome)

    def test_overall_yield_multiple_steps(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        s1 = _make_step(route, step_number=1)
        s2 = _make_step(route, step_number=2, preceding_step_ids=[s1.id])
        route.add_step(s1)
        route.add_step(s2)

        route.record_step_outcome(s1.id, ReactionOutcome(yield_percent=80.0))
        route.record_step_outcome(s2.id, ReactionOutcome(yield_percent=90.0))

        # 0.80 * 0.90 = 0.72 -> 72.0%
        assert route.overall_yield == 72.0


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


class TestStateTransitions:
    def test_validate(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        route.add_step(_make_step(route))
        route.clear_events()

        route.validate_route()

        assert route.status == RouteStatus.VALIDATED
        events = route.collect_events()
        assert len(events) == 1
        assert isinstance(events[0], SynthesisRouteValidated)

    def test_validate_empty_route_raises(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)

        with pytest.raises(ValidationError, match="no steps"):
            route.validate_route()

    def test_set_preferred(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        route.add_step(_make_step(route))
        route.validate_route()
        route.clear_events()

        prev_id = uuid.uuid4()
        route.set_preferred(previous_preferred_id=prev_id)

        assert route.status == RouteStatus.PREFERRED
        events = route.collect_events()
        assert isinstance(events[0], SynthesisRoutePreferred)
        assert events[0].previous_preferred_id == prev_id

    def test_deprecate_from_validated(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        route.add_step(_make_step(route))
        route.validate_route()
        route.clear_events()

        route.deprecate(reason="Better route found")

        assert route.status == RouteStatus.DEPRECATED
        events = route.collect_events()
        assert isinstance(events[0], SynthesisRouteDeprecated)
        assert events[0].reason == "Better route found"

    def test_deprecate_from_preferred(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        route.add_step(_make_step(route))
        route.validate_route()
        route.set_preferred()

        route.deprecate()

        assert route.status == RouteStatus.DEPRECATED

    def test_revalidate_from_deprecated(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        route.add_step(_make_step(route))
        route.validate_route()
        route.deprecate()

        route.revalidate()

        assert route.status == RouteStatus.VALIDATED

    def test_invalid_transition_draft_to_preferred(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)

        with pytest.raises(ValidationError, match="Cannot transition"):
            route.set_preferred()

    def test_invalid_transition_draft_to_deprecated(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)

        with pytest.raises(ValidationError, match="Cannot transition"):
            route.deprecate()


# ---------------------------------------------------------------------------
# DAG validation
# ---------------------------------------------------------------------------


class TestDAGValidation:
    def test_linear_route_valid(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        s1 = _make_step(route, step_number=1)
        s2 = _make_step(route, step_number=2, preceding_step_ids=[s1.id])
        route.add_step(s1)
        route.add_step(s2)

        route.validate_route()  # Should not raise
        assert route.status == RouteStatus.VALIDATED

    def test_convergent_route_valid(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id, route_type=RouteType.CONVERGENT)
        s1 = _make_step(route, step_number=1, branch_label="branch_A")
        s2 = _make_step(route, step_number=1, branch_label="branch_B")
        s3 = _make_step(route, step_number=2, preceding_step_ids=[s1.id, s2.id])
        route.add_step(s1)
        route.add_step(s2)
        route.add_step(s3)

        route.validate_route()
        assert route.status == RouteStatus.VALIDATED

    def test_cycle_detected(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        s1_id = uuid.uuid4()
        s2_id = uuid.uuid4()
        s1 = ReactionStep(id=s1_id, route_id=route.id, step_number=1, preceding_step_ids=[s2_id])
        s2 = ReactionStep(id=s2_id, route_id=route.id, step_number=2, preceding_step_ids=[s1_id])
        route.add_step(s1)
        route.add_step(s2)

        with pytest.raises(ValidationError, match="cycle"):
            route.validate_route()

    def test_unknown_preceding_step(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id)
        step = _make_step(route, preceding_step_ids=[uuid.uuid4()])
        route.add_step(step)

        with pytest.raises(ValidationError, match="unknown preceding"):
            route.validate_route()

    def test_linear_multi_predecessor_raises(self, ws_id, mol_id, user_id):
        route = _make_route(ws_id, mol_id, user_id, route_type=RouteType.LINEAR)
        s1 = _make_step(route, step_number=1)
        s2 = _make_step(route, step_number=2)
        s3 = _make_step(route, step_number=3, preceding_step_ids=[s1.id, s2.id])
        route.add_step(s1)
        route.add_step(s2)
        route.add_step(s3)

        with pytest.raises(ValidationError, match="multiple predecessors"):
            route.validate_route()


# ---------------------------------------------------------------------------
# ReactionReagent VO
# ---------------------------------------------------------------------------


class TestReactionReagent:
    def test_create(self):
        reagent = ReactionReagent(
            role=ReagentRole.CATALYST,
            name="Pd(PPh3)4",
            cas_number="14221-01-3",
            equivalents=0.05,
        )

        assert reagent.role == ReagentRole.CATALYST
        assert reagent.name == "Pd(PPh3)4"
        assert reagent.cas_number == "14221-01-3"
        assert reagent.equivalents == 0.05

    def test_frozen(self):
        reagent = ReactionReagent(role=ReagentRole.SOLVENT, name="THF")
        with pytest.raises(AttributeError):
            reagent.name = "DCM"  # type: ignore[misc]
