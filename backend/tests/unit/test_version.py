"""Unit tests for build identity resolution."""

from __future__ import annotations

import pytest

from cellar import version as version_mod
from cellar.version import build_info


def test_version_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELLAR_VERSION", "1.4.0")
    assert build_info().version == "1.4.0"


def test_version_falls_back_to_package_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CELLAR_VERSION", raising=False)
    # `cellar` is installed in the test env, so metadata resolves a non-empty version.
    assert build_info().version


def test_version_dev_fallback_when_unpackaged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CELLAR_VERSION", raising=False)

    def _raise(_name: str) -> str:
        raise version_mod.metadata.PackageNotFoundError(_name)

    monkeypatch.setattr(version_mod.metadata, "version", _raise)
    assert build_info().version == "0.0.0+dev"


def test_git_sha_and_build_date_default_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CELLAR_GIT_SHA", raising=False)
    monkeypatch.delenv("CELLAR_BUILD_DATE", raising=False)
    info = build_info()
    assert info.git_sha == "unknown"
    assert info.build_date == "unknown"


def test_git_sha_and_build_date_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CELLAR_GIT_SHA", "84e7848")
    monkeypatch.setenv("CELLAR_BUILD_DATE", "2026-06-17T12:00:00Z")
    info = build_info()
    assert info.git_sha == "84e7848"
    assert info.build_date == "2026-06-17T12:00:00Z"
