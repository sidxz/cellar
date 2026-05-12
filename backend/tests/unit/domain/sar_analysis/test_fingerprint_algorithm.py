from cellar.domain.sar_analysis.fingerprint_algorithm import (
    FingerprintAlgorithm,
)


class _FakeAlgorithm:
    name = "fake"
    column_name = "fake_bfp"
    cartridge_query_fn = "fake_fp"


def test_protocol_attributes_match() -> None:
    alg: FingerprintAlgorithm = _FakeAlgorithm()
    assert alg.name == "fake"
    assert alg.column_name == "fake_bfp"
    assert alg.cartridge_query_fn == "fake_fp"
