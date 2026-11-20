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
