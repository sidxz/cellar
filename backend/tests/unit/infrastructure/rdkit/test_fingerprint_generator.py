from rdkit import Chem

from cellar.infrastructure.rdkit.fingerprint_generator import (
    FingerprintGenerator,
    Fingerprints,
)


def test_generates_only_morgan_chiral() -> None:
    gen = FingerprintGenerator()
    mol = Chem.MolFromSmiles("CCO")
    result = gen.compute(mol)
    assert isinstance(result, Fingerprints)
    assert isinstance(result.morgan, bytes)
    assert len(result.morgan) == 256  # 2048 bits / 8


def test_chirality_distinguishes_enantiomers() -> None:
    gen = FingerprintGenerator()
    r = gen.compute(Chem.MolFromSmiles("C[C@H](O)c1ccccc1")).morgan
    s = gen.compute(Chem.MolFromSmiles("C[C@@H](O)c1ccccc1")).morgan
    assert r != s
