from __future__ import annotations

from cellar.infrastructure.logging.processors import REDACTED, redact_sensitive


def _run(event_dict):
    return redact_sensitive(None, "info", event_dict)


def test_redacts_top_level_sensitive_keys():
    out = _run({"event": "login", "password": "hunter2", "api_key": "abc"})
    assert out["password"] == REDACTED
    assert out["api_key"] == REDACTED
    assert out["event"] == "login"


def test_case_insensitive_and_substring():
    out = _run({"Authorization": "Bearer x", "user_email": "a@b.com"})
    assert out["Authorization"] == REDACTED
    assert out["user_email"] == REDACTED


def test_preserves_non_sensitive():
    out = _run({"molecule_id": "m-1", "smiles": "CCO", "workspace_id": "w-1"})
    assert out == {"molecule_id": "m-1", "smiles": "CCO", "workspace_id": "w-1"}


def test_recurses_into_nested_dicts_and_lists():
    out = _run(
        {
            "event": "call",
            "payload": {"token": "t", "nested": {"secret": "s"}},
            "items": [{"refresh_token": "r"}, {"name": "ok"}],
        }
    )
    assert out["payload"]["token"] == REDACTED
    assert out["payload"]["nested"]["secret"] == REDACTED
    assert out["items"][0]["refresh_token"] == REDACTED
    assert out["items"][1]["name"] == "ok"
