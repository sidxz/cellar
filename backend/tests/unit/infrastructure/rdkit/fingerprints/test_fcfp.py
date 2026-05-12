from cellar.infrastructure.rdkit.fingerprints.fcfp import FCFPAlgorithm


def test_metadata() -> None:
    alg = FCFPAlgorithm()
    assert alg.name == "fcfp"
    assert alg.column_name == "fcfp_bfp"
    assert alg.cartridge_query_fn == "featmorganbv_fp"
