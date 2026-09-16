from __future__ import annotations

from cellar.infrastructure.logging.settings import LoggingSettings



def test_reads_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "console")
    s = LoggingSettings(_env_file=None)
    assert s.level == "DEBUG"
    assert s.format == "console"


def test_level_overrides_parsed_from_string(monkeypatch):
    monkeypatch.setenv(
        "LOG_LEVEL_OVERRIDES",
        "sqlalchemy.engine=WARNING, cellar.infrastructure.temporal=DEBUG",
    )
    s = LoggingSettings(_env_file=None)
    assert s.level_overrides == {
        "sqlalchemy.engine": "WARNING",
        "cellar.infrastructure.temporal": "DEBUG",
    }


def test_level_overrides_empty_string():
    s = LoggingSettings(_env_file=None, level_overrides="")
    assert s.level_overrides == {}


def test_level_overrides_ignores_malformed_entries():
    s = LoggingSettings(_env_file=None, level_overrides="good=DEBUG,garbage,=,x=")
    assert s.level_overrides == {"good": "DEBUG"}
