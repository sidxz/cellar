"""Unit tests for new criterion types in SearchQueryComposer."""

import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)

_WS = uuid.UUID("00000000-0000-0000-0000-ffffffffffff")


class TestActivityClause:
    def test_curve_type_filter(self):
        query = {
            "criteria": [
                {
                    "type": "activity",
                    "protocol_id": "00000000-0000-0000-0000-000000000001",
                    "curve_type": "ic50",
                    "operator": "lt",
                    "value": 10.0,
                }
            ],
        }
        clause = compose_criteria(query, workspace_id=_WS)
        assert clause is not None

    def test_readout_definition_filter(self):
        query = {
            "criteria": [
                {
                    "type": "activity",
                    "protocol_id": "00000000-0000-0000-0000-000000000001",
                    "readout_definition_id": "00000000-0000-0000-0000-000000000002",
                    "operator": "gte",
                    "value": 50.0,
                }
            ],
        }
        clause = compose_criteria(query, workspace_id=_WS)
        assert clause is not None

    def test_invalid_operator_raises(self):
        query = {
            "criteria": [
                {
                    "type": "activity",
                    "protocol_id": "00000000-0000-0000-0000-000000000001",
                    "curve_type": "ic50",
                    "operator": "nope",
                    "value": 10.0,
                }
            ],
        }
        with pytest.raises(ValueError, match="Unknown activity operator"):
            compose_criteria(query, workspace_id=_WS)


class TestCollectionClause:
    def test_collection_filter(self):
        query = {
            "criteria": [
                {"type": "collection", "collection_id": "00000000-0000-0000-0000-000000000001"}
            ],
        }
        clause = compose_criteria(query, workspace_id=_WS)
        assert clause is not None


class TestKeywordListClause:
    def test_registration_number(self):
        query = {
            "criteria": [
                {"type": "keyword_list", "values": ["CV-0001", "CV-0002"], "ref_type": "registration_number"}
            ],
        }
        clause = compose_criteria(query, workspace_id=_WS)
        assert clause is not None

    def test_empty_values_raises(self):
        query = {
            "criteria": [
                {"type": "keyword_list", "values": [], "ref_type": "name"}
            ],
        }
        with pytest.raises(ValueError, match="must not be empty"):
            compose_criteria(query, workspace_id=_WS)

    def test_uuid_ref_type(self):
        query = {
            "criteria": [
                {
                    "type": "keyword_list",
                    "values": ["00000000-0000-0000-0000-000000000001"],
                    "ref_type": "uuid",
                }
            ],
        }
        clause = compose_criteria(query, workspace_id=_WS)
        assert clause is not None


class TestRunDateClause:
    def test_date_range(self):
        query = {
            "criteria": [
                {"type": "run_date", "date_from": "2026-01-01", "date_to": "2026-03-31"}
            ],
        }
        clause = compose_criteria(query, workspace_id=_WS)
        assert clause is not None

    def test_date_from_only(self):
        query = {
            "criteria": [{"type": "run_date", "date_from": "2026-01-01"}],
        }
        clause = compose_criteria(query, workspace_id=_WS)
        assert clause is not None


class TestCombinedCriteria:
    def test_activity_and_collection(self):
        query = {
            "criteria": [
                {"type": "collection", "collection_id": "00000000-0000-0000-0000-000000000001"},
                {
                    "type": "activity",
                    "protocol_id": "00000000-0000-0000-0000-000000000002",
                    "curve_type": "ic50",
                    "operator": "lt",
                    "value": 100.0,
                },
            ],
            "logic": "and",
        }
        clause = compose_criteria(query, workspace_id=_WS)
        assert clause is not None
