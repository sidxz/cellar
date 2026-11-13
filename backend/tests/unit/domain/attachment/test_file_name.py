"""Unit tests for numbered_file_name."""

from __future__ import annotations

from cellar.domain.attachment.file_name import numbered_file_name


def test_no_clash_keeps_the_name():
    assert numbered_file_name("run.xlsx", {"other.xlsx"}) == "run.xlsx"


def test_one_clash_numbers_before_the_last_extension():
    assert numbered_file_name("run.v1.xlsx", {"run.v1.xlsx"}) == "run.v1 (2).xlsx"


def test_two_taken_goes_to_three():
    assert numbered_file_name("run.xlsx", {"run.xlsx", "run (2).xlsx"}) == "run (3).xlsx"


def test_no_extension_appends_the_number():
    assert numbered_file_name("run", {"run"}) == "run (2)"


def test_name_already_numbered_counts_on_instead_of_nesting():
    assert numbered_file_name("run (2).xlsx", {"run (2).xlsx"}) == "run (3).xlsx"
