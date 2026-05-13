"""Unit tests for the mode-driven ``search_similarity`` signature.

No database required — these tests exercise the method signature and
parameter dispatch logic only.
"""

from __future__ import annotations

import inspect

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.molecule_reader import (
    SQLAlchemyMoleculeReader,
)


def test_search_similarity_signature_is_mode_driven():
    sig = inspect.signature(SQLAlchemyMoleculeReader.search_similarity)
    params = sig.parameters
    assert "mode" in params
    assert "threshold" in params
    assert "algorithm" in params
    assert "metric" in params
    assert "cursor_id" in params
    assert "limit" in params


def test_search_similarity_default_mode_is_similar():
    from cellar.domain.sar_analysis.search_modes import SearchMode

    sig = inspect.signature(SQLAlchemyMoleculeReader.search_similarity)
    assert sig.parameters["mode"].default == SearchMode.SIMILAR


def test_search_similarity_threshold_default_is_none():
    sig = inspect.signature(SQLAlchemyMoleculeReader.search_similarity)
    assert sig.parameters["threshold"].default is None


def test_search_similarity_limit_default_is_none():
    sig = inspect.signature(SQLAlchemyMoleculeReader.search_similarity)
    assert sig.parameters["limit"].default is None


def test_search_similarity_cursor_id_default_is_none():
    sig = inspect.signature(SQLAlchemyMoleculeReader.search_similarity)
    assert sig.parameters["cursor_id"].default is None


def test_search_similarity_mode_algorithm_metric_are_keyword_only():
    """mode/threshold/algorithm/metric/cursor_id/limit must all be keyword-only
    (after the bare ``*``) so positional callers can't accidentally supply them.
    """
    sig = inspect.signature(SQLAlchemyMoleculeReader.search_similarity)
    kw_only_params = {
        name
        for name, p in sig.parameters.items()
        if p.kind == inspect.Parameter.KEYWORD_ONLY
    }
    for expected in ("mode", "threshold", "algorithm", "metric", "cursor_id", "limit"):
        assert expected in kw_only_params, f"{expected!r} should be keyword-only"
