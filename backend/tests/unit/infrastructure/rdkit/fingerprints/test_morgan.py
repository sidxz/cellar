from rdkit import Chem

from cellar.infrastructure.rdkit.fingerprints.morgan import MorganAlgorithm


def test_metadata() -> None:
    alg = MorganAlgorithm()
    assert alg.name == "morgan"
    assert alg.column_name == "morgan_bfp"
    assert alg.cartridge_query_fn == "morganbv_fp"


def test_compute_bytes_returns_256_bytes_for_2048_bit_fp() -> None:
    alg = MorganAlgorithm()
    mol = Chem.MolFromSmiles("CCO")
    fp_bytes = alg.compute_bytes(mol)
    # 2048 bits / 8 = 256 bytes
    assert len(fp_bytes) == 256


def test_chirality_distinguishes_enantiomers() -> None:
    alg = MorganAlgorithm()
    r = Chem.MolFromSmiles("C[C@H](O)c1ccccc1")
    s = Chem.MolFromSmiles("C[C@@H](O)c1ccccc1")
    assert alg.compute_bytes(r) != alg.compute_bytes(s), (
        "Enantiomers must produce different bytes when useChirality=True"
    )


def test_achiral_smiles_independent_of_input_form() -> None:
    alg = MorganAlgorithm()
    a = Chem.MolFromSmiles("c1ccccc1")
    b = Chem.MolFromSmiles("C1=CC=CC=C1")
    assert alg.compute_bytes(a) == alg.compute_bytes(b)
