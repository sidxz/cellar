from __future__ import annotations

import pytest
from scripts.seed_visualization_benchmark import is_dev_database

LOCAL = "postgresql+asyncpg://u:p@localhost:5432/cellar"
REMOTE = "postgresql+asyncpg://u:p@db.example.org:5432/cellar"


@pytest.mark.parametrize(
    ("url", "app_env", "allowed"),
    [
        (LOCAL, None, True),
        ("postgresql+asyncpg://u:p@127.0.0.1/cellar", None, True),
        (REMOTE, "development", True),
        (REMOTE, None, False),
        (REMOTE, "production", False),
        (LOCAL, "production", False),
    ],
)
def test_runs_only_against_a_dev_database(url: str, app_env: str | None, allowed: bool) -> None:
    assert is_dev_database(url, app_env) is allowed
