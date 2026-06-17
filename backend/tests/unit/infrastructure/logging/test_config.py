from __future__ import annotations

import io
import json
import logging

import structlog

from cellar.infrastructure.logging.config import (
    DEFAULT_NOISY_LOGGERS,
    configure_logging,
)
from cellar.infrastructure.logging.settings import LoggingSettings


def test_configure_sets_root_level():
    configure_logging(LoggingSettings(_env_file=None, level="WARNING"))
    assert logging.getLogger().level == logging.WARNING


def test_noisy_loggers_muted_by_default():
    configure_logging(LoggingSettings(_env_file=None))
    for name in DEFAULT_NOISY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_level_override_applied():
    configure_logging(
        LoggingSettings(_env_file=None, level_overrides={"sqlalchemy.engine": "ERROR"})
    )
    assert logging.getLogger("sqlalchemy.engine").level == logging.ERROR


def test_invalid_level_falls_back_to_info():
    configure_logging(LoggingSettings(_env_file=None, level="NOPE"))
    assert logging.getLogger().level == logging.INFO


def test_json_output_has_expected_keys(capsys):
    configure_logging(LoggingSettings(_env_file=None, format="json", level="INFO"))
    structlog.contextvars.clear_contextvars()
    structlog.get_logger("test").info("thing.happened", widget="w1", token="SECRET")
    out = capsys.readouterr().out.strip().splitlines()[-1]
    payload = json.loads(out)
    assert payload["event"] == "thing.happened"
    assert payload["level"] == "info"
    assert payload["widget"] == "w1"
    assert payload["token"] == "***REDACTED***"
    assert "timestamp" in payload
