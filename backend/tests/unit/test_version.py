"""Unit tests for build identity resolution."""

from __future__ import annotations

import pytest

from cellar.version import DEV_VERSION, build_info

ALL = (
    "APP_VERSION",
    "CELLAR_VERSION",
    "APP_GIT_SHA",
    "CELLAR_GIT_SHA",
    "APP_BUILD_DATE",
    "CELLAR_BUILD_DATE",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ALL:
        monkeypatch.delenv(name, raising=False)


def test_app_version_wins_over_legacy_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "1.4.0")
    monkeypatch.setenv("CELLAR_VERSION", "0.9.0")
    assert build_info().version == "1.4.0"


def test_legacy_cellar_names_still_work(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELLAR_VERSION", "1.2.3")
    monkeypatch.setenv("CELLAR_GIT_SHA", "84e7848")
    monkeypatch.setenv("CELLAR_BUILD_DATE", "2026-06-17T12:00:00Z")
    info = build_info()
    assert info.version == "1.2.3"
    assert info.git_sha == "84e7848"
    assert info.build_date == "2026-06-17T12:00:00Z"


def test_nothing_baked_is_the_dev_fallback_even_though_the_package_is_installed() -> None:
    # pyproject.toml's version is a placeholder, never displayed (RELEASING.md).
    info = build_info()
    assert info == build_info()
    assert info.version == DEV_VERSION == "0.0.0+dev"
    assert info.git_sha == "unknown"
    assert info.build_date == "unknown"


def test_empty_env_values_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "")
    monkeypatch.setenv("APP_GIT_SHA", "")
    assert build_info().version == DEV_VERSION
    assert build_info().git_sha == "unknown"
