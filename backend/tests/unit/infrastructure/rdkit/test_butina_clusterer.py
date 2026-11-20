"""ButinaClusterer unit tests — cluster count varies with threshold, medoid picked."""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import AllChem

from cellar.infrastructure.rdkit.butina_clusterer import ButinaClusterer


def _ecfp4(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    return AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)


ALCOHOLS = ["CCCCCCCCCCCCO", "CCCCCCCCCCCCCO", "CCCCCCCCCCCCCCO"]
NAPHTHOIC_ACIDS = ["O=C(O)c1ccc2ccccc2c1", "O=C(O)c1ccc2ccccc2c1C", "O=C(O)c1ccc2ccccc2c1Cl"]


def test_butina_groups_similar_compounds() -> None:
    fps = [_ecfp4(s) for s in ALCOHOLS + NAPHTHOIC_ACIDS]
    clusters, medoids = ButinaClusterer(threshold=0.7).cluster(fps)
    alcohols, acids = set(clusters[:3]), set(clusters[3:])
    assert len(alcohols) == 1 and len(acids) == 1 and alcohols != acids
    assert sorted(clusters[m] for m in medoids) == [0, 1]


def test_tighter_threshold_splits_the_looser_family() -> None:
    # The parent acid is 0.61 Tanimoto distance from its methyl/chloro analogs.
    fps = [_ecfp4(s) for s in ALCOHOLS + NAPHTHOIC_ACIDS]
    clusters, medoids = ButinaClusterer().cluster(fps, threshold=0.4)
    assert len(set(clusters[:3])) == 1
    assert clusters[3] != clusters[4] == clusters[5]
    assert len(medoids) == 3
