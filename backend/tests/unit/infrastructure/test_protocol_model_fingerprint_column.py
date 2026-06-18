from __future__ import annotations

from cellar.infrastructure.persistence.sqlalchemy.screening_assay.models import ProtocolModel


def test_protocol_model_has_fingerprint_column() -> None:
    assert "fingerprint" in ProtocolModel.__table__.columns
    assert ProtocolModel.__table__.columns["fingerprint"].nullable is True
