"""Which realm app made a call: proven by a Duar m2m token in X-Service-Token."""

from __future__ import annotations

import pytest
from duar_auth import DuarError, SystemAuth
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cellar.interface.dependencies import ActingServiceDep


class _StubDuar:
    """Stands in for the lifespan Duar instance: a fixed verdict per token."""

    def verify_m2m_token(self, token: str) -> SystemAuth:
        if token == "daikon-token":
            return SystemAuth(caller="daikon", actions=["*"], svc="daikon-siblings")
        if token == "other-realm-token":
            raise DuarError("m2m token was issued for a different realm", 403)
        raise DuarError("Invalid m2m token", 401)


def _client(duar: object | None) -> TestClient:
    app = FastAPI()
    if duar is not None:
        app.state.duar = duar

    @app.get("/who")
    async def who(acting: ActingServiceDep) -> dict:
        return {"acting_service": acting}

    return TestClient(app)


def test_no_header_is_no_service():
    assert _client(_StubDuar()).get("/who").json() == {"acting_service": None}


def test_verified_token_yields_its_caller():
    response = _client(_StubDuar()).get("/who", headers={"X-Service-Token": "daikon-token"})
    assert response.json() == {"acting_service": "daikon"}


@pytest.mark.parametrize(
    ("duar", "token", "status"),
    [
        (_StubDuar(), "forged", 401),
        (_StubDuar(), "other-realm-token", 403),
        (None, "daikon-token", 401),
    ],
)
def test_a_token_that_fails_verification_is_refused_naming_the_header(duar, token, status):
    response = _client(duar).get("/who", headers={"X-Service-Token": token})
    assert response.status_code == status
    assert "X-Service-Token" in response.json()["detail"]
