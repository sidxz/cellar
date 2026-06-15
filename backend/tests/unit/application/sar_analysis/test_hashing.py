from __future__ import annotations

import uuid

from cellar.application.sar_analysis.hashing import (
    compute_membership_hash,
    sha256_hex,
)


def test_membership_hash_is_order_independent():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    h1 = compute_membership_hash([(a, 1), (b, 1), (c, 1)])
    h2 = compute_membership_hash([(c, 1), (a, 1), (b, 1)])
    assert h1 == h2


def test_membership_hash_is_version_aware():
    a, b = uuid.uuid4(), uuid.uuid4()
    base = compute_membership_hash([(a, 1), (b, 1)])
    bumped = compute_membership_hash([(a, 2), (b, 1)])
    assert base != bumped  # a merge / structure-correction bumps version -> miss


def test_membership_hash_changes_on_membership_change():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    two = compute_membership_hash([(a, 1), (b, 1)])
    three = compute_membership_hash([(a, 1), (b, 1), (c, 1)])
    assert two != three


def test_membership_hash_empty_is_stable():
    assert compute_membership_hash([]) == compute_membership_hash([])


def test_sha256_hex_is_deterministic_and_distinct():
    assert sha256_hex("c1ccccc1") == sha256_hex("c1ccccc1")
    assert sha256_hex("c1ccccc1") != sha256_hex("c1ccncc1")
