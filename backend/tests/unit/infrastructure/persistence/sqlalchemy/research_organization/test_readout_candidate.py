"""The readout_data row -> campaign candidate mapper's qualifier handling."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from cellar.domain.shared.aggregation_types import ValueQualifier
from cellar.infrastructure.persistence.sqlalchemy.research_organization.channel_resolution_query import (  # noqa: E501
    _readout_candidate,
)


def _row(qualifier: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        value_numeric=40.0,
        value_qualifier=qualifier,
        run_id=uuid.uuid4(),
        run_date=date(2026, 9, 15),
        status="approved",
        qc_metrics=None,
        name="Proto",
        protocol_version=1,
        unit="uM",
        dose_response_config=None,
    )


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (">", ValueQualifier.GT),
        (">=", ValueQualifier.GT),
        ("<", ValueQualifier.LT),
        ("<=", ValueQualifier.LT),
        ("=", ValueQualifier.EQ),
        (None, ValueQualifier.EQ),
    ],
)
def test_import_qualifiers_map_onto_campaign_qualifiers(stored, expected):
    """The summary import accepts ">=" / "<="; a ">=40" is still censored, never an exact 40."""
    assert _readout_candidate(_row(stored), None).qualifier is expected
