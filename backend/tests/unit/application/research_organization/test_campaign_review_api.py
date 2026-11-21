"""The search route validates input and forwards the caller's workspace and filters."""

import uuid
from types import SimpleNamespace
from typing import get_args
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from returns.result import Success

from cellar.application.research_organization.list_campaign_results import (
    ListCampaignResultsOutput,
)
from cellar.application.shared.pagination import PageResult
from cellar.interface.routes.campaigns_results import AuthDep, ListCampaignResultsDep, router


def test_search_route_validation_and_query_contract():
    app = FastAPI()
    app.include_router(router)
    auth = SimpleNamespace(workspace_id=uuid.uuid4(), user_id=uuid.uuid4())
    uc = AsyncMock(
        return_value=Success(
            ListCampaignResultsOutput(page=PageResult(items=[], total_count=0), outcomes={})
        )
    )
    app.dependency_overrides[get_args(AuthDep)[1].dependency] = lambda: auth
    app.dependency_overrides[get_args(ListCampaignResultsDep)[1].dependency] = lambda: uc
    with TestClient(app) as client:
        url = f"/api/v1/campaigns/{uuid.uuid4()}/results/search"
        stage, channel = uuid.uuid4(), uuid.uuid4()
        body = {
            "stage_id": str(stage),
            "outcome": ["hit"],
            "limit": 50,
            "filters": {
                "search": " Ref ",
                "overridden": False,
                "measurements": [
                    {"channel_id": str(channel), "minimum": 0, "unit": "uM", "qc": "verified"}
                ],
            },
        }
        response = client.post(url, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["total_count"] == 0
        query = uc.call_args.args[0]
        assert query.workspace_id == auth.workspace_id
        assert query.stage_id == stage
        assert query.filters.search == "Ref"
        assert query.filters.overridden is False
        assert query.filters.measurements[0].minimum == 0
        assert uc.call_args.kwargs["auth"] is auth
        body["filters"]["measurements"][0]["maximum"] = -1
        assert client.post(url, json=body).status_code == 422
        assert client.post(url, json={"filters": {"search": "x" * 201}}).status_code == 422
        assert client.post(url, json={"filters": {"unsupported": True}}).status_code == 422
