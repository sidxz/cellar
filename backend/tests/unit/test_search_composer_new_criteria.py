"""Malformed activity and keyword-list criteria are refused by the SearchQueryComposer."""

import uuid

import pytest

from cellar.infrastructure.persistence.sqlalchemy.chemical_registration.search_query_composer import (
    compose_criteria,
)

_WS = uuid.UUID("00000000-0000-0000-0000-ffffffffffff")


class TestActivityClause:
    def test_invalid_operator_raises(self):
        query = {
            "criteria": [
                {
                    "type": "activity",
                    "protocol_id": "00000000-0000-0000-0000-000000000001",
                    "source": "dr_curve",
                    "readout_definition_id": "00000000-0000-0000-0000-000000000003",
                    "operator": "nope",
                    "value": 10.0,
                }
            ],
        }
        with pytest.raises(ValueError, match="Unknown activity operator"):
            compose_criteria(query, workspace_id=_WS)


class TestKeywordListClause:
    def test_empty_values_raises(self):
        query = {
            "criteria": [
                {"type": "keyword_list", "values": [], "ref_type": "name"}
            ],
        }
        with pytest.raises(ValueError, match="must not be empty"):
            compose_criteria(query, workspace_id=_WS)
