"""Tests for the TagName value object (normalization + validation)."""

import pytest
from pydantic import ValidationError

from cellar.domain.workspace_config.tagging.tag import TagName
from cellar.infrastructure.persistence.sqlalchemy.tagging.backfill_sql import (
    _normalize_key,
)


class TestBackfillNormalizationParity:
    """The legacy backfill must normalize keys identically to the runtime
    domain — otherwise a backfilled tag won't match a later get_or_create and a
    duplicate registry row is created (defeating case-insensitive identity)."""

    @pytest.mark.parametrize(
        "raw",
        [
            "Kinase",
            "KINASE",
            "  Env  ",
            "Straße",  # casefold -> 'strasse', lower() would leave 'ß'
            "İstanbul",  # Turkish dotted capital I
            "ΣΟΦΟΣ",  # Greek final sigma
            "café",
        ],
    )
    def test_backfill_key_matches_tagname(self, raw: str) -> None:
        assert _normalize_key(raw) == TagName(key=raw).normalized_key


class TestTagNameNormalization:
    def test_key_only(self) -> None:
        name = TagName(key="favorite")
        assert name.key == "favorite"
        assert name.value is None
        assert name.normalized_key == "favorite"
        assert name.normalized_value is None

    def test_key_and_value(self) -> None:
        name = TagName(key="Project", value="Alpha")
        assert name.key == "Project"
        assert name.value == "Alpha"
        assert name.normalized_key == "project"
        assert name.normalized_value == "alpha"

    def test_key_and_value_are_trimmed(self) -> None:
        name = TagName(key="  Env  ", value="  Prod  ")
        assert name.key == "Env"
        assert name.value == "Prod"

    def test_empty_value_string_becomes_none(self) -> None:
        name = TagName(key="favorite", value="   ")
        assert name.value is None
        assert name.normalized_value is None

    def test_case_insensitive_normalization(self) -> None:
        assert TagName(key="ENV").normalized_key == TagName(key="env").normalized_key
        assert (
            TagName(key="k", value="PROD").normalized_value
            == TagName(key="k", value="prod").normalized_value
        )

    def test_is_frozen(self) -> None:
        name = TagName(key="env")
        with pytest.raises(ValidationError):
            name.key = "other"  # type: ignore[misc]


class TestTagNameValidation:
    def test_empty_key_raises(self) -> None:
        with pytest.raises(ValueError, match="key must not be empty"):
            TagName(key="   ")

    def test_key_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="128"):
            TagName(key="x" * 129)

    def test_value_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="256"):
            TagName(key="k", value="x" * 257)

    def test_control_chars_in_key_raise(self) -> None:
        with pytest.raises(ValueError, match="control"):
            TagName(key="bad\tkey")

    def test_control_chars_in_value_raise(self) -> None:
        with pytest.raises(ValueError, match="control"):
            TagName(key="k", value="bad\nvalue")
