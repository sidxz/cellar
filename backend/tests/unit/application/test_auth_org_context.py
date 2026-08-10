"""AuthContext protocol carries org identity; FakeAuth satisfies it."""

import uuid

from cellar.application.auth import AuthContext
from tests.fakes.fake_auth import FakeAuth


def test_fake_auth_satisfies_auth_context_with_org():
    org_id = uuid.uuid4()
    auth = FakeAuth(org_id=org_id, org_slug="abbvie")
    assert isinstance(auth, AuthContext)
    assert auth.org_id == org_id
    assert auth.org_slug == "abbvie"


def test_fake_auth_org_defaults_none():
    auth = FakeAuth()
    assert auth.org_id is None
    assert auth.org_slug is None
